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
import yaml
from openai import OpenAI
from bertopic import BERTopic
from umap import UMAP
from hdbscan import HDBSCAN
from sklearn.feature_extraction.text import CountVectorizer
from collections import defaultdict

# 抑制jieba的日志输出
jieba.setLogLevel(60)

from ..utils.logging.logging import (
    setup_logger, log_success, log_error, log_module_start, log_save_success
)
from ..utils.setting.env_loader import get_api_key, load_env_file
from ..utils.setting.paths import get_project_root, bucket
from ..utils.io.excel import read_jsonl, write_jsonl
from ..utils.setting.settings import settings
from ..project.manager import get_project_manager
from ..fetch.data_fetch import get_topic_available_date_range

# 配置常量
TARGET_TOPICS = 8  # 大模型合并后的目标主题数
LLM_MODEL_NAME = "qwen-plus"


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


def _run_bertopic(
    texts: List[str],
    topic_name: str,
    start_date: str,
    end_date: str,
    output_dir: Path,
    logger
) -> bool:
    """运行BERTopic主题分析"""
    try:
        # 设置BERTopic参数
        vectorizer_model = CountVectorizer(
            stop_words=None,  # 已在前端处理停用词
            ngram_range=(1, 2),
            min_df=2,
            max_df=0.8
        )

        umap_model = UMAP(
            n_neighbors=15,
            n_components=5,
            min_dist=0.0,
            metric='cosine',
            random_state=42
        )

        hdbscan_model = HDBSCAN(
            min_cluster_size=10,
            min_samples=5,
            metric='euclidean',
            cluster_selection_method='eom'
        )

        # 初始化BERTopic
        topic_model = BERTopic(
            vectorizer_model=vectorizer_model,
            umap_model=umap_model,
            hdbscan_model=hdbscan_model,
            language="chinese",
            calculate_probabilities=False,
            verbose=True
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
                topic_stats.append({
                    "topic_id": int(row['Topic']),
                    "topic_name": str(row['Name']),
                    "count": int(row['Count']),
                    "frequency": float(row['Count'] / len(texts))
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
                    logger
                )
            except Exception as e:
                log_error(logger, f"大模型聚类失败: {e}", "TopicBertopic")

        log_success(logger, "BERTopic分析完成", "TopicBertopic")
        return True

    except Exception as e:
        log_error(logger, f"BERTopic运行失败: {e}", "TopicBertopic")
        return False


def _generate_llm_clustering(topic_stats: List[Dict], output_dir: Path, logger):
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

        # 准备主题描述
        topic_descriptions = []
        for i, topic in enumerate(topic_stats):
            topic_descriptions.append(f"{i+1}. {topic['topic_name']} ({topic['count']}篇)")

        # 构建提示词
        prompt = f"""
请将以下主题分析结果合并为{TARGET_TOPICS}个更大的主题类别：

原始主题列表：
{chr(10).join(topic_descriptions)}

请按照以下格式输出JSON：
{{
    "clusters": [
        {{
            "cluster_name": "类别名称",
            "topics": ["原始主题1", "原始主题2"],
            "description": "类别描述"
        }}
    ]
}}
"""

        log_success(logger, "调用大模型进行主题聚类...", "TopicBertopic")

        # 调用大模型
        response = client.chat.completions.create(
            model=LLM_MODEL_NAME,
            messages=[
                {"role": "system", "content": "你是一个专业的文本分析专家，擅长对主题进行分类和总结。"},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3
        )

        # 解析结果
        result_text = response.choices[0].message.content
        # 提取JSON部分
        json_match = re.search(r'\{.*\}', result_text, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())

            # 保存4号文件：大模型再聚类结果
            with open(output_dir / "4大模型再聚类结果.json", 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

            # 为每个聚类生成新的关键词
            clusters = result.get('clusters', [])
            cluster_keywords = {}

            for cluster in clusters:
                cluster_name = cluster['cluster_name']
                topics = cluster['topics']

                # 生成聚类关键词的提示词
                keywords_prompt = f"""
为以下主题类别生成5-8个核心关键词：

类别名称：{cluster_name}
包含主题：{', '.join(topics)}
描述：{cluster.get('description', '')}

请直接输出关键词列表，用逗号分隔：
"""

                try:
                    keywords_response = client.chat.completions.create(
                        model=LLM_MODEL_NAME,
                        messages=[
                            {"role": "system", "content": "你是一个专业的文本分析专家。"},
                            {"role": "user", "content": keywords_prompt}
                        ],
                        temperature=0.3
                    )

                    keywords_text = keywords_response.choices[0].message.content
                    keywords = [kw.strip() for kw in keywords_text.split(',') if kw.strip()]
                    cluster_keywords[cluster_name] = keywords[:8]  # 最多8个关键词

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
            logger
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
