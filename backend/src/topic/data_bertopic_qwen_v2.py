#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BERTopic + Qwen 主题分析数据处理模块 (V2)
集成数据拉取流程，从远程数据库获取数据
"""
import re
import json
import gc
import asyncio
import random
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
from bertopic import BERTopic
from umap import UMAP
from hdbscan import HDBSCAN
from sklearn.feature_extraction.text import CountVectorizer

# 抑制jieba的日志输出
jieba.setLogLevel(60)

from ..utils.logging.logging import (
    setup_logger, log_success, log_error, log_module_start, log_save_success, log_skip
)
from ..utils.setting.env_loader import load_env_file
from ..utils.setting.paths import get_project_root, bucket
from ..utils.io.excel import read_jsonl, write_jsonl
from ..utils.setting.settings import settings
from ..utils.ai import call_langchain_chat
from ..project.manager import get_project_manager
from ..fetch.data_fetch import get_topic_available_date_range
from .prompt_config import (
    DEFAULT_DROP_RULE_PROMPT,
    DEFAULT_KEYWORDS_SYSTEM_PROMPT,
    DEFAULT_KEYWORDS_USER_PROMPT,
    DEFAULT_RECLUSTER_SYSTEM_PROMPT,
    DEFAULT_RECLUSTER_USER_PROMPT,
    DEFAULT_TOPIC_BERTOPIC_TARGET_TOPICS,
    load_topic_bertopic_prompt_config,
)
from sentence_transformers import SentenceTransformer
from .config import load_bertopic_config

# 配置常量
TARGET_TOPICS = DEFAULT_TOPIC_BERTOPIC_TARGET_TOPICS  # 大模型合并后的目标主题数
DEFAULT_RECLUSTER_TOPIC_LIMIT = 80
DEFAULT_TOPIC_SAMPLE_SIZE = 4
DEFAULT_TOPIC_SAMPLE_CHARS = 220
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

MAX_PREPROCESSED_TOKENS = 4096
MAX_PREPROCESSED_CHARS = 12000


def _normalize_contents_column(df: pd.DataFrame, logger, source: str) -> pd.DataFrame:
    """Normalize text column to `contents` for downstream BERTopic pipeline."""
    if df.empty:
        return df
    if 'content' in df.columns:
        return df.rename(columns={'content': 'contents'})
    if 'contents' in df.columns:
        return df
    for col in ['text', 'body', '正文']:
        if col in df.columns:
            return df.rename(columns={col: 'contents'})
    log_error(logger, f"{source} 未找到内容字段", "TopicBertopic")
    return pd.DataFrame()


def _read_jsonl_contents_stream(file_path: Path, logger) -> List[str]:
    """
    Stream read a large JSONL file and deduplicate by contents (keep first),
    avoiding pandas full-file load OOM.
    """
    deduped: List[str] = []
    seen: set = set()
    total_rows = 0
    valid_rows = 0
    duplicate_rows = 0

    try:
        with file_path.open('r', encoding='utf-8') as fh:
            for line in fh:
                total_rows += 1
                raw = line.strip()
                if not raw:
                    continue
                try:
                    item = json.loads(raw)
                except Exception:
                    continue
                if not isinstance(item, dict):
                    continue

                content = (
                    item.get('contents')
                    or item.get('content')
                    or item.get('text')
                    or item.get('body')
                    or item.get('正文')
                )
                if content is None:
                    continue
                content_text = str(content).strip()
                if not content_text:
                    continue
                valid_rows += 1

                if content_text in seen:
                    duplicate_rows += 1
                    continue

                seen.add(content_text)
                deduped.append(content_text)
    except Exception as exc:
        log_error(logger, f"流式读取失败 {file_path.name}: {exc}", "TopicBertopic")
        return []

    log_success(
        logger,
        (
            f"流式读取完成 {file_path.name}: 原始{total_rows}条, 有效{valid_rows}条, "
            f"重复{duplicate_rows}条, 去重后{len(deduped)}条"
        ),
        "TopicBertopic",
    )
    return deduped


def _extract_texts_from_df(df: pd.DataFrame, logger, source: str) -> List[str]:
    """从 DataFrame 提取文本并去重，返回 Python 列表以避免 Arrow 大内存转换。"""
    if df.empty:
        return []

    normalized = _normalize_contents_column(df, logger, source)
    if normalized.empty or 'contents' not in normalized.columns:
        return []

    texts: List[str] = []
    for value in normalized['contents']:
        if value is None or pd.isna(value):
            continue
        text = str(value).strip()
        if not text:
            continue
        texts.append(text)

    if not texts:
        return []

    deduped: List[str] = []
    seen: set = set()
    duplicate_rows = 0
    for text in texts:
        if text in seen:
            duplicate_rows += 1
            continue
        seen.add(text)
        deduped.append(text)

    if duplicate_rows > 0:
        log_success(
            logger,
            f"{source} 去重: {len(texts)} -> {len(deduped)}",
            "TopicBertopic",
        )
    return deduped


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


def _resolve_recluster_topic_limit(prompt_config: Optional[Dict[str, Any]]) -> int:
    if not isinstance(prompt_config, dict):
        return DEFAULT_RECLUSTER_TOPIC_LIMIT
    try:
        parsed = int(prompt_config.get("recluster_topic_limit", DEFAULT_RECLUSTER_TOPIC_LIMIT))
    except (TypeError, ValueError):
        parsed = DEFAULT_RECLUSTER_TOPIC_LIMIT
    return max(20, min(200, parsed))


def _resolve_topic_sample_size(prompt_config: Optional[Dict[str, Any]]) -> int:
    if not isinstance(prompt_config, dict):
        return DEFAULT_TOPIC_SAMPLE_SIZE
    try:
        parsed = int(prompt_config.get("topic_sample_size", DEFAULT_TOPIC_SAMPLE_SIZE))
    except (TypeError, ValueError):
        parsed = DEFAULT_TOPIC_SAMPLE_SIZE
    return max(2, min(8, parsed))


def _trim_sample_text(text: str, max_chars: int = DEFAULT_TOPIC_SAMPLE_CHARS) -> str:
    cleaned = re.sub(r"\s+", " ", str(text or "")).strip()
    if not cleaned:
        return ""
    if len(cleaned) <= max_chars:
        return cleaned
    return f"{cleaned[:max_chars - 1]}…"


def _build_topic_doc_samples(
    texts: List[str],
    topics: Iterable[int],
    *,
    sample_size: int = DEFAULT_TOPIC_SAMPLE_SIZE,
    max_chars: int = DEFAULT_TOPIC_SAMPLE_CHARS,
) -> Dict[int, List[str]]:
    """
    Build per-topic representative text samples via reservoir sampling.
    """
    sample_size = max(1, int(sample_size))
    rng = random.Random(42)
    reservoirs: Dict[int, List[str]] = {}
    seen_counts: Dict[int, int] = {}

    for topic_id, text in zip(topics, texts):
        try:
            tid = int(topic_id)
        except (TypeError, ValueError):
            continue
        if tid < 0:
            continue
        snippet = _trim_sample_text(text, max_chars=max_chars)
        if not snippet:
            continue

        current_seen = seen_counts.get(tid, 0) + 1
        seen_counts[tid] = current_seen

        bucket = reservoirs.setdefault(tid, [])
        if len(bucket) < sample_size:
            bucket.append(snippet)
            continue

        replace_at = rng.randint(1, current_seen)
        if replace_at <= sample_size:
            bucket[replace_at - 1] = snippet

    return reservoirs


def _select_topics_for_recluster(topic_stats: List[Dict[str, Any]], limit: int) -> List[Dict[str, Any]]:
    """
    Pick reclustering candidates with a head+tail strategy:
    - keep most high-volume topics
    - add evenly sampled long-tail topics for semantic diversity
    """
    if limit <= 0 or not topic_stats:
        return []
    if len(topic_stats) <= limit:
        return list(topic_stats)

    head_size = max(1, int(round(limit * 0.7)))
    head_size = min(head_size, limit, len(topic_stats))
    tail_slots = max(0, limit - head_size)

    selected = list(topic_stats[:head_size])
    if tail_slots <= 0:
        return selected

    tail = topic_stats[head_size:]
    if len(tail) <= tail_slots:
        selected.extend(tail)
        return selected

    # Evenly sample from long tail to increase thematic spread.
    picked_indices: set = set()
    for i in range(tail_slots):
        # midpoint sampling in each segment
        pos = int(((i + 0.5) * len(tail)) / tail_slots)
        pos = max(0, min(len(tail) - 1, pos))
        if pos in picked_indices:
            # fallback: find next unused index
            cursor = pos
            while cursor < len(tail) and cursor in picked_indices:
                cursor += 1
            if cursor >= len(tail):
                cursor = pos
                while cursor >= 0 and cursor in picked_indices:
                    cursor -= 1
            if cursor < 0 or cursor >= len(tail):
                continue
            pos = cursor
        picked_indices.add(pos)

    for idx in sorted(picked_indices):
        selected.append(tail[idx])
    return selected[:limit]


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
        log_success(logger, f"数据拉取完成: {success}条", "TopicBertopic")
    else:
        log_error(logger, f"数据拉取失败", "TopicBertopic")

    return bool(success)


def _load_and_merge_data(fetch_dir: Path, logger) -> List[str]:
    """
    从fetch目录读取所有数据并合并
    优先读取总体.jsonl，其次合并各渠道数据
    """
    if not fetch_dir.exists():
        log_error(logger, f"fetch目录不存在: {fetch_dir}", "TopicBertopic")
        return []

    # 优先读取总体数据
    overall_file = fetch_dir / "总体.jsonl"
    if overall_file.exists():
        try:
            df = read_jsonl(overall_file)
            if df.empty:
                log_skip(logger, "总体数据为空，尝试渠道文件", "TopicBertopic")
            else:
                log_success(logger, f"读取总体数据: {len(df)}条", "TopicBertopic")
                texts = _extract_texts_from_df(df, logger, "总体数据")
                if texts:
                    return texts
        except MemoryError:
            try:
                del df
            except Exception:
                pass
            gc.collect()
            log_skip(logger, f"总体数据过大，切换流式读取: {overall_file}", "TopicBertopic")
            texts = _read_jsonl_contents_stream(overall_file, logger)
            if texts:
                return texts
        except Exception as e:
            log_error(logger, f"读取总体数据失败: {e}", "TopicBertopic")

    # 如果没有总体数据，则合并各渠道数据
    jsonl_files = list(fetch_dir.glob("*.jsonl"))
    if not jsonl_files:
        log_error(logger, f"未找到任何JSONL文件", "TopicBertopic")
        return []

    log_success(logger, f"找到{len(jsonl_files)}个渠道文件，开始合并", "TopicBertopic")

    merged_texts: List[str] = []
    seen: set = set()

    def _append_unique(items: Iterable[str]) -> int:
        appended = 0
        for text in items:
            if text in seen:
                continue
            seen.add(text)
            merged_texts.append(text)
            appended += 1
        return appended

    for file_path in jsonl_files:
        try:
            df = read_jsonl(file_path)
            if not df.empty:
                texts = _extract_texts_from_df(df, logger, file_path.name)
                if not texts:
                    continue
                added = _append_unique(texts)
                log_success(
                    logger,
                    f"读取: {file_path.name} - 原始{len(texts)}条, 新增{added}条",
                    "TopicBertopic",
                )
        except MemoryError:
            try:
                del df
            except Exception:
                pass
            gc.collect()
            log_skip(logger, f"文件过大，切换流式读取: {file_path.name}", "TopicBertopic")
            texts = _read_jsonl_contents_stream(file_path, logger)
            if texts:
                added = _append_unique(texts)
                log_success(
                    logger,
                    f"读取(流式): {file_path.name} - 原始{len(texts)}条, 新增{added}条",
                    "TopicBertopic",
                )
        except Exception as e:
            log_error(logger, f"读取失败 {file_path.name}: {e}", "TopicBertopic")

    if not merged_texts:
        log_error(logger, "所有文件读取失败", "TopicBertopic")
        return []

    log_success(logger, f"合并后文本总量: {len(merged_texts)}条", "TopicBertopic")
    return merged_texts


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


def _preprocess_text(
    texts: Iterable[str],
    user_words: set,
    stop_words: set,
    logger,
    total_count: Optional[int] = None,
) -> List[str]:
    """文本预处理和分词"""
    # 添加用户词典
    for word in user_words:
        jieba.add_word(word)

    processed_texts = []
    truncated_count = 0
    cleaned_empty_count = 0
    for i, text in enumerate(texts):
        if text is None or pd.isna(text):
            continue

        # 清理文本
        text = str(text).replace("\x00", " ")
        text = text.encode("utf-8", errors="ignore").decode("utf-8", errors="ignore")
        text = re.sub(r'[\u0000-\u001f\u007f-\u009f]+', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        if not text:
            cleaned_empty_count += 1
            continue

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
            doc_truncated = False
            if len(words) > MAX_PREPROCESSED_TOKENS:
                words = words[:MAX_PREPROCESSED_TOKENS]
                doc_truncated = True

            processed = ' '.join(words)
            if len(processed) > MAX_PREPROCESSED_CHARS:
                processed = processed[:MAX_PREPROCESSED_CHARS].rstrip()
                doc_truncated = True

            if processed:
                processed_texts.append(processed)
                if doc_truncated:
                    truncated_count += 1

        # 进度提示
        if (i + 1) % 1000 == 0:
            if total_count:
                log_success(logger, f"已处理 {i + 1}/{total_count} 条文本", "TopicBertopic")
            else:
                log_success(logger, f"已处理 {i + 1} 条文本", "TopicBertopic")

    log_success(logger, f"文本预处理完成，有效文本: {len(processed_texts)}", "TopicBertopic")
    if truncated_count > 0:
        log_skip(
            logger,
            (
                f"存在超长文本，已截断 {truncated_count} 条 "
                f"(max_tokens={MAX_PREPROCESSED_TOKENS}, max_chars={MAX_PREPROCESSED_CHARS})"
            ),
            "TopicBertopic",
        )
    if cleaned_empty_count > 0:
        log_skip(logger, f"清洗后空文本已跳过: {cleaned_empty_count}条", "TopicBertopic")
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


def _safe_async_call(coro: Any) -> Any:
    try:
        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


def _coerce_optional_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes", "y", "是", "需要", "drop", "discard", "exclude"}:
            return True
        if lowered in {"false", "0", "no", "n", "否", "保留", "keep"}:
            return False
    return None


_DROP_HINTS = (
    "无关主题",
    "与专题无关",
    "无关",
    "噪声",
    "噪音",
    "irrelevant",
    "off-topic",
    "offtopic",
    "noise",
)


def _contains_drop_hint(text: str) -> bool:
    normalized = str(text or "").strip().lower()
    if not normalized:
        return False
    return any(hint in normalized for hint in _DROP_HINTS)


def _parse_cluster_drop_flag(
    cluster: Dict[str, Any],
    cluster_name: str,
    description: str,
) -> Tuple[bool, str]:
    drop_reason = str(
        cluster.get("drop_reason")
        or cluster.get("剔除理由")
        or cluster.get("dropReason")
        or cluster.get("exclude_reason")
        or ""
    ).strip()

    drop_flag = _coerce_optional_bool(
        cluster.get("drop")
        if "drop" in cluster
        else cluster.get("exclude")
    )
    if drop_flag is None:
        drop_flag = _coerce_optional_bool(cluster.get("discard"))
    if drop_flag is None:
        drop_flag = _coerce_optional_bool(cluster.get("is_drop"))

    if drop_flag is None:
        is_relevant = _coerce_optional_bool(
            cluster.get("is_relevant")
            if "is_relevant" in cluster
            else cluster.get("related")
        )
        if is_relevant is None:
            is_relevant = _coerce_optional_bool(cluster.get("relevant"))
        if is_relevant is not None:
            drop_flag = not is_relevant

    if drop_flag is None:
        drop_flag = (
            _contains_drop_hint(cluster_name)
            or _contains_drop_hint(description)
            or _contains_drop_hint(drop_reason)
        )

    if drop_flag and not drop_reason:
        drop_reason = "模型判定为与专题关联度低"
    return bool(drop_flag), drop_reason


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
            drop_flag, drop_reason = _parse_cluster_drop_flag(cluster, name, description)
            normalised.append(
                {
                    "cluster_name": name,
                    "topics": topics,
                    "description": description,
                    "drop": drop_flag,
                    "drop_reason": drop_reason,
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
        drop_flag, drop_reason = _parse_cluster_drop_flag(item, name, description)
        converted.append(
            {
                "cluster_name": name,
                "topics": [str(v).strip() for v in topics if str(v or "").strip()],
                "description": description,
                "drop": drop_flag,
                "drop_reason": drop_reason,
            }
        )
    return converted


def _split_keywords(text: str) -> List[str]:
    if not isinstance(text, str):
        return []
    raw = re.split(r"[,\n，、;；]+", text)
    return [item.strip() for item in raw if item and item.strip()]


def _call_langchain_text(
    messages: List[Dict[str, str]],
    *,
    task: str = "topic_bertopic",
    temperature: float = 0.2,
    max_tokens: int = 1800,
) -> Optional[str]:
    raw_text = _safe_async_call(
        call_langchain_chat(
            messages,
            task=task,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    )
    if not isinstance(raw_text, str):
        return None
    cleaned = raw_text.strip()
    return cleaned or None


def _append_drop_instruction(prompt: str, focus_topic: str, drop_rule_prompt: str) -> str:
    topic_label = str(focus_topic or "").strip() or "当前专题"
    template = str(drop_rule_prompt or "").strip() or DEFAULT_DROP_RULE_PROMPT
    snippet = _render_prompt_template(
        template,
        {
            "FOCUS_TOPIC": topic_label,
            "focus_topic": topic_label,
            "topic": topic_label,
        },
    )
    if not snippet.strip():
        return prompt.rstrip()
    return f"{prompt.rstrip()}\n\n{snippet.strip()}"


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

        # 动态调整配置：根据数据量自动优化 min_cluster_size
        # 策略倾向于“保留更多可交给 LLM 合并的细粒度主题”，避免过早合并。
        n_docs = len(texts)
        if n_docs >= 2000:
            current_min_cluster = int(hdbscan_params["min_cluster_size"])
            # 仅在当前设置较小（默认值附近）时触发自动调整
            if current_min_cluster <= 20:
                # 启发式规则（上限控制在 60，避免对大盘数据过度粗聚类）：
                # 2k ~ 20k   : n/250
                # 20k ~ 100k : n/3000 + 16
                # 100k+      : n/10000 + 28
                if n_docs < 20000:
                    suggested_size = int(n_docs / 250)
                elif n_docs < 100000:
                    suggested_size = max(24, int(n_docs / 3000) + 16)
                else:
                    suggested_size = max(36, int(n_docs / 10000) + 28)
                
                # 确保不低于原始值，且不低于 10；同时避免极端放大导致主题过少
                suggested_size = max(suggested_size, current_min_cluster, 10)
                suggested_size = min(suggested_size, 60)
                
                if suggested_size > current_min_cluster:
                    log_success(
                        logger,
                        f"检测到数据量较大({n_docs}条)，自动调整 min_cluster_size: {current_min_cluster} -> {suggested_size}",
                        "TopicBertopic"
                    )
                    hdbscan_params["min_cluster_size"] = suggested_size

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
            random_state=int(umap_params["random_state"]),
            low_memory=True,
            n_jobs=1,
        )

        hdbscan_model = HDBSCAN(
            min_cluster_size=int(hdbscan_params["min_cluster_size"]),
            min_samples=int(hdbscan_params["min_samples"]),
            metric=str(hdbscan_params["metric"]),
            cluster_selection_method=str(hdbscan_params["cluster_selection_method"])
        )

        # 加载嵌入模型配置
        try:
            config = load_bertopic_config()
            embedding_config = config.get("embedding", {})
            model_name = embedding_config.get("model_name", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
            requested_device = str(embedding_config.get("device", "cpu") or "cpu").strip().lower()
            batch_size = int(embedding_config.get("batch_size") or 32)
            try:
                import torch
            except Exception as exc:
                raise RuntimeError(f"无法导入 torch: {exc}")

            if requested_device == "auto":
                device = "cuda" if torch.cuda.is_available() else "cpu"
            else:
                device = requested_device

            if device == "cuda":
                if not torch.cuda.is_available():
                    raise RuntimeError("配置要求 CUDA，但当前环境未检测到可用 GPU")
                gpu_name = torch.cuda.get_device_name(0) if torch.cuda.device_count() > 0 else "Unknown GPU"
                log_success(logger, f"使用本地 CUDA 嵌入推理: {gpu_name}", "TopicBertopic")

            log_success(
                logger,
                f"加载嵌入模型: {model_name} (device={device}, batch_size={batch_size})",
                "TopicBertopic",
            )
            embedding_model = SentenceTransformer(model_name, device=device)
        except Exception as e:
            log_error(logger, f"加载本地嵌入模型失败: {e}", "TopicBertopic")
            return False

        # 初始化BERTopic
        topic_model = BERTopic(
            embedding_model=embedding_model,
            vectorizer_model=vectorizer_model,
            umap_model=umap_model,
            hdbscan_model=hdbscan_model,
            language="chinese (simplified)",
            top_n_words=int(bertopic_params["top_n_words"]),
            calculate_probabilities=bool(bertopic_params["calculate_probabilities"]),
            verbose=bool(bertopic_params["verbose"])
        )

        previous_string_storage = None
        string_storage_changed = False
        try:
            previous_string_storage = pd.get_option("mode.string_storage")
            if previous_string_storage != "python":
                pd.set_option("mode.string_storage", "python")
                string_storage_changed = True
                log_success(
                    logger,
                    "检测到 pandas Arrow 字符串后端，训练阶段临时切换为 python 字符串后端",
                    "TopicBertopic",
                )
        except Exception as exc:
            log_skip(logger, f"无法设置 pandas 字符串后端: {exc}", "TopicBertopic")

        # 训练模型
        log_success(logger, "开始训练BERTopic模型...", "TopicBertopic")
        try:
            topics, probs = topic_model.fit_transform(texts)
        finally:
            if string_storage_changed:
                try:
                    pd.set_option("mode.string_storage", previous_string_storage)
                except Exception:
                    pass

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

        topic_sample_size = _resolve_topic_sample_size(prompt_config)
        topic_samples_by_id = _build_topic_doc_samples(
            texts,
            topics,
            sample_size=topic_sample_size,
            max_chars=DEFAULT_TOPIC_SAMPLE_CHARS,
        )
        if topic_samples_by_id:
            log_success(
                logger,
                f"已生成主题样本文本: {len(topic_samples_by_id)} 个主题, 每主题最多 {topic_sample_size} 条",
                "TopicBertopic",
            )

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
        doc_coords: List[Dict[str, Any]] = []
        try:
            reduced_doc_embeddings = None

            # BERTopic 0.17.x 可稳定从 UMAP 模型读取降维结果；
            # 一些版本不再暴露 document_embeddings_，因此这里优先读取 embedding_。
            umap_embedding = getattr(getattr(topic_model, "umap_model", None), "embedding_", None)
            if umap_embedding is not None:
                reduced_doc_embeddings = np.asarray(umap_embedding)
                log_success(logger, "使用 UMAP embedding_ 生成文档坐标", "TopicBertopic")
            else:
                doc_embedding_attr = getattr(topic_model, "document_embeddings_", None)
                if doc_embedding_attr is not None:
                    raw_doc_embeddings = np.asarray(doc_embedding_attr)
                    if raw_doc_embeddings.ndim == 2 and raw_doc_embeddings.shape[1] >= 2:
                        if raw_doc_embeddings.shape[1] == 2:
                            reduced_doc_embeddings = raw_doc_embeddings
                        else:
                            reducer_2d = UMAP(
                                n_neighbors=15,
                                n_components=2,
                                min_dist=0.0,
                                metric="cosine",
                                random_state=42,
                                low_memory=True,
                            )
                            reduced_doc_embeddings = reducer_2d.fit_transform(raw_doc_embeddings)
                        log_success(logger, "使用 document_embeddings_ 生成文档坐标", "TopicBertopic")

            if (
                reduced_doc_embeddings is not None
                and len(reduced_doc_embeddings) == len(topics)
                and reduced_doc_embeddings.ndim == 2
                and reduced_doc_embeddings.shape[1] >= 2
            ):
                for i, (topic_id, embedding) in enumerate(zip(topics, reduced_doc_embeddings)):
                    if topic_id != -1:  # 排除离群点
                        doc_coords.append({
                            "doc_id": i,
                            "topic_id": int(topic_id),
                            "x": float(embedding[0]),
                            "y": float(embedding[1]),
                        })
            else:
                log_skip(logger, "未获取到可用的文档2D坐标，跳过可视化坐标输出", "TopicBertopic")
        except Exception as e:
            log_error(logger, f"生成文档2D坐标失败，已跳过: {e}", "TopicBertopic")
            doc_coords = []

        if doc_coords:
            with open(output_dir / "3文档2D坐标.json", 'w', encoding='utf-8') as f:
                json.dump(
                    {
                        "documents": doc_coords
                    },
                    f,
                    ensure_ascii=False,
                    indent=2,
                )

        # 4-5. 使用大模型进行主题聚类和生成新关键词
        if topic_stats and len(topic_stats) > 0:
            try:
                topic_limit = _resolve_recluster_topic_limit(prompt_config)
                target_limit = min(topic_limit, len(topic_stats))
                topic_stats_for_llm = _select_topics_for_recluster(topic_stats, target_limit)

                enriched_topic_stats: List[Dict[str, Any]] = []
                for topic in topic_stats_for_llm:
                    topic_id = topic.get("topic_id")
                    try:
                        topic_id_int = int(topic_id)
                    except (TypeError, ValueError):
                        topic_id_int = None
                    samples = topic_samples_by_id.get(topic_id_int, []) if topic_id_int is not None else []
                    enriched_topic_stats.append(
                        {
                            **topic,
                            "samples": samples[:topic_sample_size],
                        }
                    )

                if len(topic_stats) > target_limit:
                    head_size = max(1, int(round(target_limit * 0.7)))
                    head_size = min(head_size, target_limit)
                    diversity_size = max(0, target_limit - head_size)
                    log_success(
                        logger,
                        (
                            f"重分类输入主题选择: 总{len(topic_stats)}个, 使用{target_limit}个 "
                            f"(高频{head_size} + 发散{diversity_size})"
                        ),
                        "TopicBertopic",
                    )

                use_multi_agent = _coerce_bool(
                    (prompt_config or {}).get("use_multi_agent"),
                    True,
                )
                if use_multi_agent:
                    _generate_llm_clustering_multi_agent(
                        enriched_topic_stats,
                        output_dir,
                        logger,
                        topic_name=topic_name,
                        prompt_config=prompt_config,
                    )
                else:
                    _generate_llm_clustering(
                        enriched_topic_stats,
                        output_dir,
                        logger,
                        topic_name=topic_name,
                        prompt_config=prompt_config,
                    )
            except Exception as e:
                log_error(logger, f"大模型聚类失败: {e}", "TopicBertopic")

        log_success(logger, "BERTopic分析完成", "TopicBertopic")
        return True

    except Exception as e:
        import traceback
        log_error(logger, f"BERTopic运行失败: {e}\n{traceback.format_exc()}", "TopicBertopic")
        return False


def _generate_llm_clustering_multi_agent(
    topic_stats: List[Dict],
    output_dir: Path,
    logger,
    topic_name: str = "",
    prompt_config: Optional[Dict[str, Any]] = None,
):
    """使用多 Agent 协作进行主题聚类（LangGraph StateGraph）"""
    from .multi_agent_recluster import run_multi_agent_recluster

    log_success(logger, "启动多 Agent 协作聚类...", "TopicBertopic")

    result = run_multi_agent_recluster(
        topic_stats=topic_stats,
        focus_topic=str(topic_name or "").strip(),
        prompt_config=prompt_config,
        logger=logger,
    )

    final_clusters = result.get("clusters", [])
    dropped_clusters = result.get("dropped", [])
    iterations = result.get("iterations", 1)
    scope_reasoning = result.get("scope_reasoning", "")
    recommended = result.get("recommended_max_topics", 8)

    log_success(
        logger,
        f"多 Agent 聚类完成: {len(final_clusters)} 个保留, "
        f"{len(dropped_clusters)} 个丢弃, "
        f"{iterations} 轮迭代, 推荐 max_topics={recommended}",
        "TopicBertopic",
    )

    if scope_reasoning:
        log_success(logger, f"Scope Analyst 理由: {scope_reasoning}", "TopicBertopic")

    if dropped_clusters:
        log_skip(logger, f"LLM 多Agent协作已丢弃无关主题簇: {len(dropped_clusters)} 个", "TopicBertopic")

    # Build topic count map for doc_count calculation
    topic_count_map: Dict[str, int] = {}
    for t in topic_stats:
        tname = str(t.get("topic_name") or "").strip()
        if tname:
            try:
                topic_count_map[tname] = int(t.get("count") or 0)
            except (TypeError, ValueError):
                topic_count_map[tname] = 0

    # Write file 4: 大模型再聚类结果
    normalized_result: Dict[str, Dict[str, Any]] = {}
    assigned_topics: set = set()
    for idx, cluster in enumerate(final_clusters):
        base_name = str(cluster.get("cluster_name") or "").strip() or f"新主题{idx + 1}"
        cluster_name = base_name
        dedupe_idx = 2
        while cluster_name in normalized_result:
            cluster_name = f"{base_name}_{dedupe_idx}"
            dedupe_idx += 1

        topics = cluster.get("topics", [])
        clean_topics: List[str] = []
        for item in topics:
            name = str(item).strip()
            if not name or name in assigned_topics:
                continue
            clean_topics.append(name)
            assigned_topics.add(name)

        doc_count = sum(topic_count_map.get(n, 0) for n in clean_topics)
        description = str(cluster.get("description") or "").strip()

        normalized_result[cluster_name] = {
            "主题命名": cluster_name,
            "原始主题集合": clean_topics,
            "主题描述": description,
            "文档数": int(doc_count),
        }

    with open(output_dir / "4大模型再聚类结果.json", "w", encoding="utf-8") as f:
        json.dump(normalized_result, f, ensure_ascii=False, indent=2)

    # Write file 5: 大模型主题关键词
    cluster_keywords: Dict[str, List[str]] = {}
    for cluster in final_clusters:
        cname = str(cluster.get("cluster_name") or "").strip()
        kws = cluster.get("keywords", [])
        if cname and cname in normalized_result:
            cluster_keywords[cname] = kws[:8] if isinstance(kws, list) else []

    with open(output_dir / "5大模型主题关键词.json", "w", encoding="utf-8") as f:
        json.dump(cluster_keywords, f, ensure_ascii=False, indent=2)

    log_success(logger, "多 Agent 聚类结果已保存", "TopicBertopic")


def _generate_llm_clustering(
    topic_stats: List[Dict],
    output_dir: Path,
    logger,
    topic_name: str = "",
    prompt_config: Optional[Dict[str, Any]] = None,
):
    """使用大模型进行主题聚类"""
    load_env_file()

    try:
        config = prompt_config or {}
        try:
            target_topics = int(config.get("target_topics", TARGET_TOPICS))
        except (TypeError, ValueError):
            target_topics = TARGET_TOPICS
        target_topics = max(3, min(50, target_topics))

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
        drop_rule_prompt = str(
            config.get("drop_rule_prompt") or DEFAULT_DROP_RULE_PROMPT
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
            "FOCUS_TOPIC": str(topic_name or "").strip(),
        }
        prompt = _append_drop_instruction(
            _render_prompt_template(recluster_user_prompt, prompt_values),
            str(topic_name or "").strip(),
            drop_rule_prompt,
        )

        log_success(logger, "调用 LangChain 大模型进行主题聚类...", "TopicBertopic")

        result_text = _call_langchain_text(
            [
                {"role": "system", "content": recluster_system_prompt},
                {"role": "user", "content": prompt},
            ],
            task="topic_bertopic",
            temperature=0.2,
            max_tokens=3600,
        )
        if not result_text:
            log_error(
                logger,
                "LangChain 聚类调用失败或返回为空（请检查 llm.langchain 配置与凭据）",
                "TopicBertopic",
            )
            return

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
        assigned_topics: set = set()
        dropped_count = 0
        for idx, cluster in enumerate(clusters):
            if bool(cluster.get("drop")):
                dropped_count += 1
                continue

            base_name = str(cluster.get("cluster_name") or "").strip() or f"新主题{idx + 1}"
            cluster_name = base_name
            dedupe_idx = 2
            while cluster_name in normalized_result:
                cluster_name = f"{base_name}_{dedupe_idx}"
                dedupe_idx += 1

            topics = cluster.get("topics")
            if not isinstance(topics, list):
                topics = []
            clean_topics: List[str] = []
            for item in topics:
                name = str(item).strip()
                if not name:
                    continue
                if name in assigned_topics:
                    continue
                clean_topics.append(name)
                assigned_topics.add(name)
            doc_count = sum(topic_count_map.get(name, 0) for name in clean_topics)
            description = str(cluster.get("description") or "").strip()

            normalized_result[cluster_name] = {
                "主题命名": cluster_name,
                "原始主题集合": clean_topics,
                "主题描述": description,
                "文档数": int(doc_count),
            }

        if dropped_count > 0:
            log_skip(logger, f"LLM 重分类已丢弃无关主题簇: {dropped_count} 个", "TopicBertopic")

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
                keywords_text = _call_langchain_text(
                    [
                        {"role": "system", "content": keyword_system_prompt},
                        {"role": "user", "content": keywords_prompt},
                    ],
                    task="topic_bertopic",
                    temperature=0.2,
                    max_tokens=300,
                )
                if not keywords_text:
                    raise RuntimeError("关键词返回为空")
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

    # 确定日志使用的日期标识
    log_date_str = f"{start_date}_{end_date}" if end_date else start_date
    logger = setup_logger("topic_bertopic", log_date_str)
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
            "drop_rule_prompt": DEFAULT_DROP_RULE_PROMPT,
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
        texts = _load_and_merge_data(paths["fetch_dir"], logger)
        if not texts:
            log_error(logger, "没有可用的数据", "TopicBertopic")
            return False

        text_count = len(texts)
        if text_count <= 0:
            log_error(logger, "没有有效的文本内容", "TopicBertopic")
            return False

        log_success(logger, f"加载文本数据: {text_count}条", "TopicBertopic")

        # 文本预处理
        processed_texts = _preprocess_text(
            texts,
            user_words,
            stop_words,
            logger,
            total_count=text_count,
        )
        del texts
        gc.collect()
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
