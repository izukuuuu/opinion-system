#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BERTopic + Qwen 主题分析数据处理模块 (V2)
集成数据拉取流程，从远程数据库获取数据
"""
import re
import json
import warnings
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Iterable, Any

# 严格抑制所有警告
warnings.filterwarnings("ignore")
warnings.simplefilter("ignore")
warnings.filterwarnings("ignore", message=".*pkg_resources.*")
warnings.filterwarnings("ignore", category=UserWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=FutureWarning)

import pandas as pd
import numpy as np
import jieba
from openai import OpenAI
from bertopic import BERTopic
from umap import UMAP
from hdbscan import HDBSCAN
from sklearn.feature_extraction.text import CountVectorizer

# 抑制jieba的日志输出
jieba.setLogLevel(60)

from ..utils.logging.logging import (
    setup_logger, log_success, log_error, log_module_start, log_save_success, log_skip
)
from ..utils.setting.env_loader import get_api_key, load_env_file
from ..utils.setting.paths import get_project_root, bucket
from ..utils.io.excel import read_jsonl, write_jsonl
from ..utils.setting.settings import settings
from ..project.manager import get_project_manager
from ..fetch.data_fetch import get_topic_available_date_range
from .prompt_config import (
    DEFAULT_KEYWORDS_SYSTEM_PROMPT,
    DEFAULT_KEYWORDS_USER_PROMPT,
    DEFAULT_RECLUSTER_SYSTEM_PROMPT,
    DEFAULT_RECLUSTER_USER_PROMPT,
    DEFAULT_TOPIC_BERTOPIC_TARGET_TOPICS,
    load_topic_bertopic_prompt_config,
)

# 配置常量
TARGET_TOPICS = DEFAULT_TOPIC_BERTOPIC_TARGET_TOPICS  # 大模型合并后的目标主题数
LLM_MODEL_NAME = "qwen-plus"
DEFAULT_RUN_PARAMS: Dict[str, Any] = {
    "vectorizer": {
        "ngram_min": 1,
        "ngram_max": 2,
        "min_df": 2,
        "max_df": 0.8,
    },
    "umap": {
        "n_neighbors": 15,
        "n_components": 5,
        "min_dist": 0.0,
        "metric": "cosine",
        "random_state": 42,
    },
    "hdbscan": {
        "min_cluster_size": 10,
        "min_samples": 5,
        "metric": "euclidean",
        "cluster_selection_method": "eom",
    },
    "bertopic": {
        "top_n_words": 10,
        "calculate_probabilities": False,
        "verbose": True,
    },
}


def _coerce_int(value: Any, default: int, minimum: Optional[int] = None, maximum: Optional[int] = None) -> int:
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        parsed = int(default)
    if minimum is not None:
        parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed


def _coerce_float(value: Any, default: float, minimum: Optional[float] = None, maximum: Optional[float] = None) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = float(default)
    if minimum is not None:
        parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "on"}:
            return True
        if lowered in {"false", "0", "no", "off"}:
            return False
    if value is None:
        return default
    return bool(value)


def _coerce_df_threshold(value: Any, default: Any) -> Any:
    """CountVectorizer min_df/max_df 支持 int 或 float(0,1]。"""
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if parsed <= 0:
        return default
    if parsed < 1:
        return parsed
    return int(parsed)


def _resolve_run_params(raw: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    params: Dict[str, Any] = json.loads(json.dumps(DEFAULT_RUN_PARAMS))
    if not isinstance(raw, dict):
        return params

    vectorizer_raw = raw.get("vectorizer")
    if isinstance(vectorizer_raw, dict):
        ngram_min = _coerce_int(
            vectorizer_raw.get("ngram_min"),
            params["vectorizer"]["ngram_min"],
            minimum=1,
            maximum=5,
        )
        ngram_max = _coerce_int(
            vectorizer_raw.get("ngram_max"),
            params["vectorizer"]["ngram_max"],
            minimum=1,
            maximum=5,
        )
        if ngram_min > ngram_max:
            ngram_min, ngram_max = ngram_max, ngram_min
        params["vectorizer"]["ngram_min"] = ngram_min
        params["vectorizer"]["ngram_max"] = ngram_max
        params["vectorizer"]["min_df"] = _coerce_df_threshold(
            vectorizer_raw.get("min_df"),
            params["vectorizer"]["min_df"],
        )
        params["vectorizer"]["max_df"] = _coerce_df_threshold(
            vectorizer_raw.get("max_df"),
            params["vectorizer"]["max_df"],
        )

    umap_raw = raw.get("umap")
    if isinstance(umap_raw, dict):
        params["umap"]["n_neighbors"] = _coerce_int(
            umap_raw.get("n_neighbors"),
            params["umap"]["n_neighbors"],
            minimum=2,
            maximum=200,
        )
        params["umap"]["n_components"] = _coerce_int(
            umap_raw.get("n_components"),
            params["umap"]["n_components"],
            minimum=2,
            maximum=50,
        )
        params["umap"]["min_dist"] = _coerce_float(
            umap_raw.get("min_dist"),
            params["umap"]["min_dist"],
            minimum=0.0,
            maximum=0.99,
        )
        metric = str(umap_raw.get("metric") or "").strip()
        params["umap"]["metric"] = metric or params["umap"]["metric"]
        params["umap"]["random_state"] = _coerce_int(
            umap_raw.get("random_state"),
            params["umap"]["random_state"],
        )

    hdbscan_raw = raw.get("hdbscan")
    if isinstance(hdbscan_raw, dict):
        params["hdbscan"]["min_cluster_size"] = _coerce_int(
            hdbscan_raw.get("min_cluster_size"),
            params["hdbscan"]["min_cluster_size"],
            minimum=2,
            maximum=1000,
        )
        params["hdbscan"]["min_samples"] = _coerce_int(
            hdbscan_raw.get("min_samples"),
            params["hdbscan"]["min_samples"],
            minimum=1,
            maximum=1000,
        )
        h_metric = str(hdbscan_raw.get("metric") or "").strip()
        params["hdbscan"]["metric"] = h_metric or params["hdbscan"]["metric"]
        method = str(hdbscan_raw.get("cluster_selection_method") or "").strip().lower()
        if method in {"eom", "leaf"}:
            params["hdbscan"]["cluster_selection_method"] = method

    bertopic_raw = raw.get("bertopic")
    if isinstance(bertopic_raw, dict):
        params["bertopic"]["top_n_words"] = _coerce_int(
            bertopic_raw.get("top_n_words"),
            params["bertopic"]["top_n_words"],
            minimum=5,
            maximum=50,
        )
        params["bertopic"]["calculate_probabilities"] = _coerce_bool(
            bertopic_raw.get("calculate_probabilities"),
            params["bertopic"]["calculate_probabilities"],
        )
        params["bertopic"]["verbose"] = _coerce_bool(
            bertopic_raw.get("verbose"),
            params["bertopic"]["verbose"],
        )

    return params


def _default_paths(topic: str, start_date: str, end_date: str = None, bucket_topic: Optional[str] = None) -> Dict[str, Path]:
    """获取默认路径配置"""
    project_root = get_project_root()
    configs_root = project_root / "configs"

    storage_topic = bucket_topic or topic

    # 使用与analyze相同的日期范围格式
    if end_date:
        folder_name = f"{start_date}_{end_date}"
    else:
        folder_name = start_date

    fetch_dir = bucket("fetch", storage_topic, folder_name)
    userdict = configs_root / "userdict.txt"
    stopwords = configs_root / "stopwords.txt"
    out_analyze = bucket("topic", storage_topic, folder_name)

    return {
        "fetch_dir": fetch_dir,
        "userdict": userdict,
        "stopwords": stopwords,
        "out_analyze": out_analyze,
    }


def _ensure_fetch_data(topic: str, start_date: str, end_date: str, logger, bucket_topic: Optional[str] = None, db_topic: Optional[str] = None) -> bool:
    """
    确保fetch数据存在，如果不存在则触发fetch流程
    """
    from ..fetch.data_fetch import fetch_range

    storage_topic = bucket_topic or topic
    db_name = db_topic or topic

    # 检查fetch缓存是否已存在
    paths = _default_paths(storage_topic, start_date, end_date, bucket_topic=storage_topic)
    fetch_dir = paths["fetch_dir"]

    if fetch_dir.exists() and (fetch_dir / "总体.jsonl").exists():
        log_success(logger, f"使用缓存数据: {fetch_dir}", "TopicBertopic")
        return True

    # 检查数据可用性
    availability = get_topic_available_date_range(db_name)
    if isinstance(availability, dict):
        avail_start = availability.get("start")
        avail_end = availability.get("end")
    else:
        avail_start, avail_end = availability
    if avail_start and avail_end:
        req_start = pd.to_datetime(start_date).date()
        req_end = pd.to_datetime(end_date).date()
        avail_start_date = pd.to_datetime(avail_start).date()
        avail_end_date = pd.to_datetime(avail_end).date()

        if req_start < avail_start_date or req_end > avail_end_date:
            log_error(
                logger,
                f"请求的日期范围 {start_date}~{end_date} 超出可用范围 {avail_start}~{avail_end}",
                "TopicBertopic"
            )
            return False

    # 执行fetch
    log_success(logger, f"开始拉取数据: {db_name} {start_date}~{end_date}", "TopicBertopic")
    output_date = f"{start_date}_{end_date}" if end_date else start_date
    success = fetch_range(storage_topic, start_date, end_date, output_date, logger, db_topic=db_name)

    if success:
        log_success(logger, f"数据拉取完成", "TopicBertopic")
    else:
        log_error(logger, f"数据拉取失败", "TopicBertopic")

    return success


def _load_and_merge_data(fetch_dir: Path, logger) -> pd.DataFrame:
    """
    从fetch目录读取所有数据并合并
    优先读取总体.jsonl，其次合并各渠道数据
    """
    if not fetch_dir.exists():
        log_error(logger, f"fetch目录不存在: {fetch_dir}", "TopicBertopic")
        return pd.DataFrame()

    # 优先读取总体数据
    overall_file = fetch_dir / "总体.jsonl"
    if overall_file.exists():
        try:
            df = read_jsonl(overall_file)
            if not df.empty:
                log_success(logger, f"读取总体数据: {len(df)}条", "TopicBertopic")
                # 确保有content字段
                if 'content' in df.columns:
                    df = df.rename(columns={'content': 'contents'})
                elif 'contents' not in df.columns:
                    # 尝试其他可能的字段名
                    for col in ['text', 'body', '正文']:
                        if col in df.columns:
                            df = df.rename(columns={col: 'contents'})
                            break
                    else:
                        log_error(logger, "未找到内容字段", "TopicBertopic")
                        return pd.DataFrame()

                # 去重
                before_count = len(df)
                df = df.drop_duplicates(subset=['contents'], keep='last')
                after_count = len(df)
                if before_count != after_count:
                    log_success(logger, f"去重: {before_count} -> {after_count}", "TopicBertopic")

                return df
        except Exception as e:
            log_error(logger, f"读取总体数据失败: {e}", "TopicBertopic")

    # 如果没有总体数据，则合并各渠道数据
    jsonl_files = list(fetch_dir.glob("*.jsonl"))
    if not jsonl_files:
        log_error(logger, f"未找到任何JSONL文件", "TopicBertopic")
        return pd.DataFrame()

    log_success(logger, f"找到{len(jsonl_files)}个渠道文件，开始合并", "TopicBertopic")

    all_data = []
    for file_path in jsonl_files:
        try:
            df = read_jsonl(file_path)
            if not df.empty:
                # 确保有contents字段
                if 'content' in df.columns:
                    df = df.rename(columns={'content': 'contents'})
                elif 'contents' not in df.columns:
                    for col in ['text', 'body', '正文']:
                        if col in df.columns:
                            df = df.rename(columns={col: 'contents'})
                            break
                    else:
                        log_skip(logger, f"文件 {file_path.name} 无内容字段", "TopicBertopic")
                        continue

                all_data.append(df)
                log_success(logger, f"读取: {file_path.name} - {len(df)}条", "TopicBertopic")
        except Exception as e:
            log_error(logger, f"读取失败 {file_path.name}: {e}", "TopicBertopic")

    if not all_data:
        log_error(logger, "所有文件读取失败", "TopicBertopic")
        return pd.DataFrame()

    # 合并数据
    merged = pd.concat(all_data, ignore_index=True)

    # 去重
    before_count = len(merged)
    merged = merged.drop_duplicates(subset=['contents'], keep='last')
    after_count = len(merged)
    if before_count != after_count:
        log_success(logger, f"合并去重: {before_count} -> {after_count}", "TopicBertopic")

    return merged


def _load_dict_file(file_path: Path, logger) -> set:
    """加载词典文件"""
    if not file_path.exists():
        log_skip(logger, f"词典文件不存在: {file_path}", "TopicBertopic")
        return set()

    try:
        words = set()
        with open(file_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    words.add(line)
        log_success(logger, f"加载词典: {file_path.name} - {len(words)}个词", "TopicBertopic")
        return words
    except Exception as e:
        log_error(logger, f"加载词典失败 {file_path.name}: {e}", "TopicBertopic")
        return set()


def _preprocess_text(texts: List[str], user_words: set, stop_words: set, logger) -> List[str]:
    """文本预处理和分词"""
    # 添加用户词典
    for word in user_words:
        jieba.add_word(word)

    processed_texts = []
    for i, text in enumerate(texts):
        if pd.isna(text) or not text.strip():
            continue

        # 清理文本
        text = re.sub(r'\s+', ' ', str(text).strip())

        # 分词
        words = jieba.lcut(text)

        # 过滤停用词和短词
        words = [
            w for w in words
            if len(w) >= 2
            and w not in stop_words
            and not re.match(r'^[^\u4e00-\u9fa5]+$', w)  # 过滤纯非中文字符
        ]

        if words:
            processed_texts.append(' '.join(words))

        # 进度提示
        if (i + 1) % 1000 == 0:
            log_success(logger, f"已处理 {i + 1}/{len(texts)} 条文本", "TopicBertopic")

    log_success(logger, f"文本预处理完成，有效文本: {len(processed_texts)}", "TopicBertopic")
    return processed_texts


class _SafeFormatDict(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def _render_prompt_template(template: str, values: Dict[str, Any]) -> str:
    """渲染提示词模板，优先兼容 format 风格，失败时回退到 replace。"""

    text = str(template or "")
    normalised_values = {k: str(v) for k, v in values.items()}
    try:
        return text.format_map(_SafeFormatDict(normalised_values))
    except Exception:
        rendered = text
        for key, value in normalised_values.items():
            rendered = rendered.replace("{" + key + "}", value)
        return rendered


def _extract_json_payload(text: str) -> Optional[Dict[str, Any]]:
    """从模型输出中尽量提取 JSON 对象。"""

    if not isinstance(text, str):
        return None
    cleaned = text.strip()
    if not cleaned:
        return None
    if "```json" in cleaned:
        cleaned = cleaned.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in cleaned:
        cleaned = cleaned.split("```", 1)[1].split("```", 1)[0].strip()

    try:
        parsed = json.loads(cleaned)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass

    match = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        return None
    return None


def _parse_clusters(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    """兼容解析 clusters 或旧版合并方案字段。"""

    clusters = payload.get("clusters")
    if isinstance(clusters, list):
        normalised: List[Dict[str, Any]] = []
        for idx, cluster in enumerate(clusters):
            if not isinstance(cluster, dict):
                continue
            name = str(cluster.get("cluster_name") or cluster.get("name") or f"类别{idx + 1}").strip()
            topics = cluster.get("topics")
            if not isinstance(topics, list):
                topics = []
            topics = [str(item).strip() for item in topics if str(item or "").strip()]
            description = str(cluster.get("description") or "").strip()
            normalised.append(
                {
                    "cluster_name": name,
                    "topics": topics,
                    "description": description,
                }
            )
        return normalised

    merge_plan = payload.get("合并方案")
    if not isinstance(merge_plan, list):
        return []

    converted: List[Dict[str, Any]] = []
    for idx, item in enumerate(merge_plan):
        if not isinstance(item, dict):
            continue
        name = str(
            item.get("主题命名")
            or item.get("新主题名称")
            or item.get("cluster_name")
            or f"类别{idx + 1}"
        ).strip()
        topics = item.get("原始主题集合")
        if not isinstance(topics, list):
            topics = item.get("topics")
        if not isinstance(topics, list):
            topics = []
        description = str(item.get("主题描述") or item.get("description") or "").strip()
        converted.append(
            {
                "cluster_name": name,
                "topics": [str(v).strip() for v in topics if str(v or "").strip()],
                "description": description,
            }
        )
    return converted


def _split_keywords(text: str) -> List[str]:
    if not isinstance(text, str):
        return []
    raw = re.split(r"[,\n，、;；]+", text)
    return [item.strip() for item in raw if item and item.strip()]


def _run_bertopic(
    texts: List[str],
    topic_name: str,
    start_date: str,
    end_date: str,
    output_dir: Path,
    logger,
    prompt_config: Optional[Dict[str, Any]] = None,
    run_params: Optional[Dict[str, Any]] = None,
) -> bool:
    """运行BERTopic主题分析"""
    try:
        resolved_params = _resolve_run_params(run_params)
        vectorizer_params = resolved_params["vectorizer"]
        umap_params = resolved_params["umap"]
        hdbscan_params = resolved_params["hdbscan"]
        bertopic_params = resolved_params["bertopic"]

        log_success(
            logger,
            (
                "运行参数: "
                f"vectorizer={vectorizer_params}, "
                f"umap={umap_params}, "
                f"hdbscan={hdbscan_params}, "
                f"bertopic={bertopic_params}"
            ),
            "TopicBertopic",
        )

        # 设置BERTopic参数
        vectorizer_model = CountVectorizer(
            stop_words=None,  # 已在前端处理停用词
            ngram_range=(
                int(vectorizer_params["ngram_min"]),
                int(vectorizer_params["ngram_max"]),
            ),
            min_df=vectorizer_params["min_df"],
            max_df=vectorizer_params["max_df"]
        )

        umap_model = UMAP(
            n_neighbors=int(umap_params["n_neighbors"]),
            n_components=int(umap_params["n_components"]),
            min_dist=float(umap_params["min_dist"]),
            metric=str(umap_params["metric"]),
            random_state=int(umap_params["random_state"])
        )

        hdbscan_model = HDBSCAN(
            min_cluster_size=int(hdbscan_params["min_cluster_size"]),
            min_samples=int(hdbscan_params["min_samples"]),
            metric=str(hdbscan_params["metric"]),
            cluster_selection_method=str(hdbscan_params["cluster_selection_method"])
        )

        # 初始化BERTopic
        topic_model = BERTopic(
            vectorizer_model=vectorizer_model,
            umap_model=umap_model,
            hdbscan_model=hdbscan_model,
            language="chinese",
            top_n_words=int(bertopic_params["top_n_words"]),
            calculate_probabilities=bool(bertopic_params["calculate_probabilities"]),
            verbose=bool(bertopic_params["verbose"])
        )

        # 训练模型
        log_success(logger, "开始训练BERTopic模型...", "TopicBertopic")
        topics, probs = topic_model.fit_transform(texts)

        # 获取主题信息
        topic_info = topic_model.get_topic_info()

        # 1. 保存主题统计结果
        topic_stats = []
        for idx, row in topic_info.iterrows():
            if row['Topic'] != -1:  # 排除离群点
                topic_words = topic_model.get_topic(int(row['Topic'])) or []
                topic_keywords = [str(item[0]).strip() for item in topic_words[:10] if item and item[0]]
                topic_stats.append({
                    "topic_id": int(row['Topic']),
                    "topic_name": str(row['Name']),
                    "count": int(row['Count']),
                    "frequency": float(row['Count'] / len(texts)),
                    "keywords": topic_keywords,
                })

        # 按频率排序
        topic_stats.sort(key=lambda x: x['count'], reverse=True)

        # 保存1号文件：主题统计结果
        with open(output_dir / "1主题统计结果.json", 'w', encoding='utf-8') as f:
            json.dump({
                "topic": topic_name,
                "date_range": f"{start_date}_{end_date}",
                "total_documents": len(texts),
                "topics": topic_stats
            }, f, ensure_ascii=False, indent=2)

        # 2. 保存主题关键词
        topic_keywords = {}
        for topic_id in set(topics):
            if topic_id != -1:
                words = topic_model.get_topic(topic_id)
                if words:
                    topic_keywords[f"Topic_{topic_id}"] = words[:10]  # 取前10个关键词

        with open(output_dir / "2主题关键词.json", 'w', encoding='utf-8') as f:
            json.dump(topic_keywords, f, ensure_ascii=False, indent=2)

        # 3. 保存文档2D坐标（用于可视化）
        if hasattr(topic_model, 'topic_embeddings_') and topic_model.topic_embeddings_ is not None:
            # 获取文档嵌入
            doc_embeddings = topic_model.document_embeddings_
            # 获取主题嵌入
            topic_embeddings = topic_model.topic_embeddings_

            # 保存文档坐标
            doc_coords = []
            for i, (topic_id, embedding) in enumerate(zip(topics, doc_embeddings)):
                if topic_id != -1:  # 排除离群点
                    doc_coords.append({
                        "doc_id": i,
                        "topic_id": int(topic_id),
                        "x": float(embedding[0]),
                        "y": float(embedding[1])
                    })

            with open(output_dir / "3文档2D坐标.json", 'w', encoding='utf-8') as f:
                json.dump({
                    "documents": doc_coords
                }, f, ensure_ascii=False, indent=2)

        # 4-5. 使用大模型进行主题聚类和生成新关键词
        if topic_stats and len(topic_stats) > 0:
            try:
                _generate_llm_clustering(
                    topic_stats[:min(20, len(topic_stats))],  # 最多取前20个主题
                    output_dir,
                    logger,
                    prompt_config=prompt_config,
                )
            except Exception as e:
                log_error(logger, f"大模型聚类失败: {e}", "TopicBertopic")

        log_success(logger, "BERTopic分析完成", "TopicBertopic")
        return True

    except Exception as e:
        log_error(logger, f"BERTopic运行失败: {e}", "TopicBertopic")
        return False


def _generate_llm_clustering(
    topic_stats: List[Dict],
    output_dir: Path,
    logger,
    prompt_config: Optional[Dict[str, Any]] = None,
):
    """使用大模型进行主题聚类"""
    # 获取API密钥
    load_env_file()
    api_key = get_api_key()
    if not api_key:
        log_error(logger, "未找到API密钥，跳过大模型聚类", "TopicBertopic")
        return

    try:
        client = OpenAI(
            api_key=api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
        )

        config = prompt_config or {}
        try:
            target_topics = int(config.get("target_topics", TARGET_TOPICS))
        except (TypeError, ValueError):
            target_topics = TARGET_TOPICS
        target_topics = max(2, min(50, target_topics))

        recluster_system_prompt = str(
            config.get("recluster_system_prompt") or DEFAULT_RECLUSTER_SYSTEM_PROMPT
        )
        recluster_user_prompt = str(
            config.get("recluster_user_prompt") or DEFAULT_RECLUSTER_USER_PROMPT
        )
        keyword_system_prompt = str(
            config.get("keyword_system_prompt") or DEFAULT_KEYWORDS_SYSTEM_PROMPT
        )
        keyword_user_prompt = str(
            config.get("keyword_user_prompt") or DEFAULT_KEYWORDS_USER_PROMPT
        )

        # 准备主题描述
        topic_descriptions = []
        for i, topic in enumerate(topic_stats):
            keywords = topic.get("keywords")
            if isinstance(keywords, list):
                keyword_text = "、".join([str(item).strip() for item in keywords if str(item or "").strip()])
            else:
                keyword_text = ""
            if keyword_text:
                topic_descriptions.append(
                    f"{i+1}. {topic.get('topic_name', '未知主题')} ({topic.get('count', 0)}篇) 关键词: {keyword_text}"
                )
            else:
                topic_descriptions.append(
                    f"{i+1}. {topic.get('topic_name', '未知主题')} ({topic.get('count', 0)}篇)"
                )

        prompt_payload = {
            "topics": topic_stats,
            "topic_list": topic_descriptions,
        }
        prompt_values = {
            "TARGET_TOPICS": target_topics,
            "input_data": json.dumps(prompt_payload, ensure_ascii=False, indent=2),
            "topic_list": "\n".join(topic_descriptions),
            "topic_stats_json": json.dumps(topic_stats, ensure_ascii=False, indent=2),
        }
        prompt = _render_prompt_template(recluster_user_prompt, prompt_values)

        log_success(logger, "调用大模型进行主题聚类...", "TopicBertopic")

        # 调用大模型
        response = client.chat.completions.create(
            model=LLM_MODEL_NAME,
            messages=[
                {"role": "system", "content": recluster_system_prompt},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )

        # 解析结果
        result_text = response.choices[0].message.content or ""
        parsed_payload = _extract_json_payload(result_text)
        if not parsed_payload:
            log_error(logger, "大模型返回未解析出有效 JSON，跳过再聚类结果写入", "TopicBertopic")
            return

        clusters = _parse_clusters(parsed_payload)
        if not clusters:
            log_error(logger, "大模型返回中未找到可用聚类字段(clusters/合并方案)", "TopicBertopic")
            return

        topic_count_map: Dict[str, int] = {}
        for topic in topic_stats:
            topic_name = str(topic.get("topic_name") or "").strip()
            if not topic_name:
                continue
            try:
                topic_count_map[topic_name] = int(topic.get("count") or 0)
            except (TypeError, ValueError):
                topic_count_map[topic_name] = 0

        normalized_result: Dict[str, Dict[str, Any]] = {}
        for idx, cluster in enumerate(clusters):
            base_name = str(cluster.get("cluster_name") or "").strip() or f"新主题{idx + 1}"
            cluster_name = base_name
            dedupe_idx = 2
            while cluster_name in normalized_result:
                cluster_name = f"{base_name}_{dedupe_idx}"
                dedupe_idx += 1

            topics = cluster.get("topics")
            if not isinstance(topics, list):
                topics = []
            clean_topics = [str(item).strip() for item in topics if str(item or "").strip()]
            doc_count = sum(topic_count_map.get(name, 0) for name in clean_topics)
            description = str(cluster.get("description") or "").strip()

            normalized_result[cluster_name] = {
                "主题命名": cluster_name,
                "原始主题集合": clean_topics,
                "主题描述": description,
                "文档数": int(doc_count),
            }

        with open(output_dir / "4大模型再聚类结果.json", 'w', encoding='utf-8') as f:
            json.dump(normalized_result, f, ensure_ascii=False, indent=2)

        # 为每个聚类生成新的关键词
        cluster_keywords: Dict[str, List[str]] = {}
        for cluster_name, cluster_data in normalized_result.items():
            topics = cluster_data.get("原始主题集合")
            if not isinstance(topics, list):
                topics = []
            description = str(cluster_data.get("主题描述") or "").strip()

            keywords_values = {
                "cluster_name": cluster_name,
                "topics": "、".join([str(item).strip() for item in topics if str(item or "").strip()]),
                "topics_csv": ", ".join([str(item).strip() for item in topics if str(item or "").strip()]),
                "topics_json": json.dumps(topics, ensure_ascii=False),
                "description": description,
            }
            keywords_prompt = _render_prompt_template(keyword_user_prompt, keywords_values)

            try:
                keywords_response = client.chat.completions.create(
                    model=LLM_MODEL_NAME,
                    messages=[
                        {"role": "system", "content": keyword_system_prompt},
                        {"role": "user", "content": keywords_prompt}
                    ],
                    temperature=0.3
                )
                keywords_text = keywords_response.choices[0].message.content or ""
                keywords = _split_keywords(keywords_text)
                cluster_keywords[cluster_name] = keywords[:8]
            except Exception as e:
                log_error(logger, f"生成聚类关键词失败: {e}", "TopicBertopic")
                cluster_keywords[cluster_name] = []

        # 保存5号文件：大模型主题关键词
        with open(output_dir / "5大模型主题关键词.json", 'w', encoding='utf-8') as f:
            json.dump(cluster_keywords, f, ensure_ascii=False, indent=2)

        log_success(logger, "大模型聚类完成", "TopicBertopic")

    except Exception as e:
        log_error(logger, f"大模型聚类失败: {e}", "TopicBertopic")


def run_topic_bertopic(
    topic: str,
    start_date: str,
    end_date: str = None,
    fetch_dir: str = None,
    userdict: str = None,
    stopwords: str = None,
    run_params: Optional[Dict[str, Any]] = None,
    bucket_topic: str = None,
    db_topic: str = None,
    display_topic: str = None,
) -> bool:
    """
    运行BERTopic主题分析主函数

    Args:
        topic: 专题名称
        start_date: 开始日期
        end_date: 结束日期（可选）
        fetch_dir: 自定义fetch目录路径（可选）
        userdict: 自定义用户词典路径（可选）
        stopwords: 自定义停用词路径（可选）

    Returns:
        bool: 是否成功
    """
    storage_topic = bucket_topic or topic
    db_name = db_topic or topic
    topic_label = display_topic or topic

    logger = setup_logger("topic_bertopic")
    log_module_start(logger, f"BERTopic主题分析: {topic_label} {start_date}~{end_date or start_date}")

    try:
        prompt_config = load_topic_bertopic_prompt_config(storage_topic)
        if prompt_config.get("exists"):
            log_success(
                logger,
                f"已加载提示词配置: {prompt_config.get('path', '')}",
                "TopicBertopic",
            )
        else:
            log_skip(
                logger,
                f"未找到专题提示词配置，使用默认模板: {prompt_config.get('path', '')}",
                "TopicBertopic",
            )
    except Exception as exc:
        log_error(logger, f"加载提示词配置失败，改用默认模板: {exc}", "TopicBertopic")
        prompt_config = {
            "target_topics": TARGET_TOPICS,
            "recluster_system_prompt": DEFAULT_RECLUSTER_SYSTEM_PROMPT,
            "recluster_user_prompt": DEFAULT_RECLUSTER_USER_PROMPT,
            "keyword_system_prompt": DEFAULT_KEYWORDS_SYSTEM_PROMPT,
            "keyword_user_prompt": DEFAULT_KEYWORDS_USER_PROMPT,
        }

    try:
        # 处理参数
        if not end_date:
            end_date = start_date

        # 确保数据已拉取
        if not fetch_dir:
            # 自动fetch数据
            if not _ensure_fetch_data(db_name, start_date, end_date, logger, bucket_topic=storage_topic, db_topic=db_name):
                return False
            paths = _default_paths(storage_topic, start_date, end_date, bucket_topic=storage_topic)
        else:
            # 使用指定的fetch目录
            fetch_path = Path(fetch_dir)
            if not fetch_path.exists():
                log_error(logger, f"指定的fetch目录不存在: {fetch_dir}", "TopicBertopic")
                return False
            paths = _default_paths(storage_topic, start_date, end_date, bucket_topic=storage_topic)
            paths["fetch_dir"] = fetch_path

        # 加载词典
        user_words = set()
        stop_words = set()

        # 加载自定义词典
        if userdict:
            user_dict_path = Path(userdict)
            if user_dict_path.exists():
                user_words = _load_dict_file(user_dict_path, logger)
        else:
            user_words = _load_dict_file(paths["userdict"], logger)

        # 加载停用词
        if stopwords:
            stop_words_path = Path(stopwords)
            if stop_words_path.exists():
                stop_words = _load_dict_file(stop_words_path, logger)
        else:
            stop_words = _load_dict_file(paths["stopwords"], logger)

        # 加载和预处理数据
        df = _load_and_merge_data(paths["fetch_dir"], logger)
        if df.empty:
            log_error(logger, "没有可用的数据", "TopicBertopic")
            return False

        # 提取文本内容
        texts = df['contents'].dropna().tolist()
        if not texts:
            log_error(logger, "没有有效的文本内容", "TopicBertopic")
            return False

        log_success(logger, f"加载文本数据: {len(texts)}条", "TopicBertopic")

        # 文本预处理
        processed_texts = _preprocess_text(texts, user_words, stop_words, logger)
        if not processed_texts:
            log_error(logger, "文本预处理后没有有效内容", "TopicBertopic")
            return False

        # 确保输出目录存在
        output_dir = paths["out_analyze"]
        output_dir.mkdir(parents=True, exist_ok=True)

        # 运行BERTopic分析
        success = _run_bertopic(
            processed_texts,
            topic_label,
            start_date,
            end_date,
            output_dir,
            logger,
            prompt_config=prompt_config,
            run_params=run_params,
        )

        if success:
            log_save_success(logger, f"主题分析结果已保存到: {output_dir}", "TopicBertopic")

        return success

    except Exception as e:
        log_error(logger, f"主题分析失败: {e}", "TopicBertopic")
        return False


if __name__ == "__main__":
    # 测试用例
    run_topic_bertopic(
        topic="测试专题",
        start_date="2024-01-01",
        end_date="2024-01-31"
    )
