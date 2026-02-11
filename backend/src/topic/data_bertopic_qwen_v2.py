#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
主题智能聚类数据处理模块 (V2)
集成数据拉取流程，从远程数据库获取数据
"""
import re
import json
import gc
import asyncio
import random
import warnings
from collections import defaultdict
from datetime import datetime, timedelta
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
    DEFAULT_PREFILTER_ENABLED,
    DEFAULT_PREFILTER_MAX_DROP_RATIO,
    DEFAULT_PREFILTER_NEGATIVE_HINT,
    DEFAULT_PREFILTER_QUERY_HINT,
    DEFAULT_PREFILTER_SIMILARITY_FLOOR,
    DEFAULT_KEYWORDS_USER_PROMPT,
    DEFAULT_RECLUSTER_TARGET_COVERAGE_RATIO,
    DEFAULT_RECLUSTER_TOPIC_LIMIT as DEFAULT_PROMPT_RECLUSTER_TOPIC_LIMIT,
    DEFAULT_RECLUSTER_SYSTEM_PROMPT,
    DEFAULT_RECLUSTER_USER_PROMPT,
    DEFAULT_TOPIC_BERTOPIC_TARGET_TOPICS,
    load_topic_bertopic_prompt_config,
)
from sentence_transformers import SentenceTransformer
from .config import load_bertopic_config

# 配置常量
TARGET_TOPICS = DEFAULT_TOPIC_BERTOPIC_TARGET_TOPICS  # 大模型合并后的目标主题数
DEFAULT_RECLUSTER_TOPIC_LIMIT = DEFAULT_PROMPT_RECLUSTER_TOPIC_LIMIT
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
DEFAULT_PREFILTER_SAMPLE_SIZE = 2048
MIN_PREFILTER_DOCS = 50
MIN_PREFILTER_ANCHOR_HITS = 5
TOPIC_HINT_GENERIC_TERMS = {
    "专题",
    "舆情",
    "分析",
    "数据库",
    "数据",
    "主题",
    "项目",
    "事件",
    "观察",
}

DATE_FIELD_CANDIDATES = (
    "published_at",
    "publish_time",
    "date",
    "created_at",
    "pubtime",
    "发布时间",
    "发布日期",
    "时间",
    "日期",
)


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


def _extract_date_text(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    match = re.search(r"(20\d{2}-\d{2}-\d{2})", raw)
    return match.group(1) if match else ""


def _prefer_earlier_date(current: str, candidate: str) -> str:
    current_text = _extract_date_text(current)
    candidate_text = _extract_date_text(candidate)
    if not current_text:
        return candidate_text
    if not candidate_text:
        return current_text
    return candidate_text if candidate_text < current_text else current_text


def _dedupe_text_records(records: Iterable[Tuple[Any, Any]]) -> Tuple[List[Tuple[str, str]], int]:
    record_dates: Dict[str, str] = {}
    ordered_texts: List[str] = []
    duplicate_rows = 0

    for raw_text, raw_date in records:
        text = str(raw_text or "").strip()
        if not text:
            continue
        date_text = _extract_date_text(raw_date)
        if text in record_dates:
            duplicate_rows += 1
            record_dates[text] = _prefer_earlier_date(record_dates[text], date_text)
            continue
        record_dates[text] = date_text
        ordered_texts.append(text)

    return [(text, record_dates.get(text, "")) for text in ordered_texts], duplicate_rows


def _read_jsonl_records_stream(file_path: Path, logger) -> List[Tuple[str, str]]:
    """
    Stream read a large JSONL file and deduplicate by contents,
    avoiding pandas full-file load OOM.
    """
    deduped: List[Tuple[str, str]] = []
    record_index: Dict[str, int] = {}
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
                date_text = ""
                for key in DATE_FIELD_CANDIDATES:
                    date_text = _extract_date_text(item.get(key))
                    if date_text:
                        break

                if content_text in record_index:
                    duplicate_rows += 1
                    idx = record_index[content_text]
                    existing_text, existing_date = deduped[idx]
                    deduped[idx] = (existing_text, _prefer_earlier_date(existing_date, date_text))
                    continue

                record_index[content_text] = len(deduped)
                deduped.append((content_text, date_text))
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


def _extract_records_from_df(df: pd.DataFrame, logger, source: str) -> List[Tuple[str, str]]:
    """从 DataFrame 提取文本与日期并去重，返回 Python 列表以避免 Arrow 大内存转换。"""
    if df.empty:
        return []

    normalized = _normalize_contents_column(df, logger, source)
    if normalized.empty or 'contents' not in normalized.columns:
        return []

    candidate_columns = ["contents"] + [col for col in DATE_FIELD_CANDIDATES if col in normalized.columns]
    subset = normalized[candidate_columns]
    records_iter = []
    for row in subset.itertuples(index=False, name=None):
        value = row[0] if row else None
        if value is None or pd.isna(value):
            continue
        text = str(value).strip()
        if not text:
            continue
        date_text = ""
        for raw_date in row[1:]:
            date_text = _extract_date_text(raw_date)
            if date_text:
                break
        records_iter.append((text, date_text))

    if not records_iter:
        return []

    deduped, duplicate_rows = _dedupe_text_records(records_iter)

    if duplicate_rows > 0:
        log_success(
            logger,
            f"{source} 去重: {len(records_iter)} -> {len(deduped)}",
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


def _resolve_recluster_target_coverage(prompt_config: Optional[Dict[str, Any]]) -> float:
    if not isinstance(prompt_config, dict):
        return DEFAULT_RECLUSTER_TARGET_COVERAGE_RATIO
    return _coerce_float(
        prompt_config.get(
            "recluster_target_coverage_ratio",
            DEFAULT_RECLUSTER_TARGET_COVERAGE_RATIO,
        ),
        DEFAULT_RECLUSTER_TARGET_COVERAGE_RATIO,
        minimum=0.2,
        maximum=0.95,
    )


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
    return _select_topics_for_recluster_with_metadata(
        topic_stats,
        limit,
        DEFAULT_RECLUSTER_TARGET_COVERAGE_RATIO,
    )[0]


def _select_topics_for_recluster_with_metadata(
    topic_stats: List[Dict[str, Any]],
    limit: int,
    coverage_target: float,
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if limit <= 0 or not topic_stats:
        return [], {
            "configured_limit": max(0, int(limit)),
            "effective_limit": 0,
            "coverage_target": float(coverage_target),
            "selected_docs": 0,
            "total_docs": 0,
            "coverage_ratio": 0.0,
            "head_size": 0,
            "diversity_size": 0,
            "coverage_head_size": 0,
        }

    ordered = list(topic_stats)
    effective_limit = min(len(ordered), max(1, int(limit)))

    topic_counts: List[int] = []
    total_docs = 0
    for topic in ordered:
        try:
            count = max(0, int(topic.get("count") or 0))
        except (TypeError, ValueError):
            count = 0
        topic_counts.append(count)
        total_docs += count

    if len(ordered) <= effective_limit:
        return ordered, {
            "configured_limit": int(limit),
            "effective_limit": len(ordered),
            "coverage_target": float(coverage_target),
            "selected_docs": int(total_docs),
            "total_docs": int(total_docs),
            "coverage_ratio": 1.0 if total_docs else 0.0,
            "head_size": len(ordered),
            "diversity_size": 0,
            "coverage_head_size": len(ordered),
        }

    coverage_head_size = 0
    coverage_docs = 0
    if total_docs > 0:
        required_docs = total_docs * float(coverage_target)
        for idx, count in enumerate(topic_counts):
            coverage_docs += count
            coverage_head_size = idx + 1
            if coverage_docs >= required_docs:
                break
    if coverage_head_size <= 0:
        coverage_head_size = min(len(ordered), effective_limit)

    base_head_size = max(1, int(round(effective_limit * 0.7)))
    if coverage_head_size > effective_limit:
        head_size = effective_limit
    else:
        head_size = min(effective_limit, max(base_head_size, coverage_head_size))
    tail_slots = max(0, effective_limit - head_size)

    selected = list(ordered[:head_size])
    tail = ordered[head_size:]
    picked_indices: set = set()
    if tail_slots > 0 and tail:
        if len(tail) <= tail_slots:
            selected.extend(tail)
        else:
            for i in range(tail_slots):
                pos = int(((i + 0.5) * len(tail)) / tail_slots)
                pos = max(0, min(len(tail) - 1, pos))
                if pos in picked_indices:
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

    selected = selected[:effective_limit]
    selected_docs = 0
    for topic in selected:
        try:
            selected_docs += max(0, int(topic.get("count") or 0))
        except (TypeError, ValueError):
            continue

    actual_diversity_size = max(0, len(selected) - min(head_size, len(selected)))
    return selected, {
        "configured_limit": int(limit),
        "effective_limit": len(selected),
        "coverage_target": float(coverage_target),
        "selected_docs": int(selected_docs),
        "total_docs": int(total_docs),
        "coverage_ratio": float(selected_docs / total_docs) if total_docs else 0.0,
        "head_size": min(head_size, len(selected)),
        "diversity_size": int(actual_diversity_size),
        "coverage_head_size": int(coverage_head_size),
    }


def _resolve_effective_topic_sample_size(requested_sample_size: int, selected_topic_count: int) -> int:
    sample_size = max(1, int(requested_sample_size))
    if selected_topic_count >= 120:
        return min(sample_size, 2)
    if selected_topic_count >= 80:
        return min(sample_size, 3)
    return sample_size


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


def _load_and_merge_data(fetch_dir: Path, logger) -> List[Tuple[str, str]]:
    """
    从fetch目录读取所有数据并合并，保留文本与日期
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
                records = _extract_records_from_df(df, logger, "总体数据")
                if records:
                    return records
        except MemoryError:
            try:
                del df
            except Exception:
                pass
            gc.collect()
            log_skip(logger, f"总体数据过大，切换流式读取: {overall_file}", "TopicBertopic")
            records = _read_jsonl_records_stream(overall_file, logger)
            if records:
                return records
        except Exception as e:
            log_error(logger, f"读取总体数据失败: {e}", "TopicBertopic")

    # 如果没有总体数据，则合并各渠道数据
    jsonl_files = list(fetch_dir.glob("*.jsonl"))
    if not jsonl_files:
        log_error(logger, f"未找到任何JSONL文件", "TopicBertopic")
        return []

    log_success(logger, f"找到{len(jsonl_files)}个渠道文件，开始合并", "TopicBertopic")

    merged_records: List[Tuple[str, str]] = []
    record_index: Dict[str, int] = {}

    def _append_unique(items: Iterable[Tuple[str, str]]) -> int:
        appended = 0
        for text, date_text in items:
            if text in record_index:
                idx = record_index[text]
                existing_text, existing_date = merged_records[idx]
                merged_records[idx] = (
                    existing_text,
                    _prefer_earlier_date(existing_date, date_text),
                )
                continue
            record_index[text] = len(merged_records)
            merged_records.append((text, date_text))
            appended += 1
        return appended

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
                
                # 添加渠道字段
                if 'channel' not in df.columns:
                    # 从文件名推断渠道 (去除扩展名)
                    channel_name = file_path.stem
                    # 如果文件名包含日期等后缀，可能需要处理，这里简单处理
                    df['channel'] = channel_name

                all_data.append(df)
                log_success(logger, f"读取: {file_path.name} - {len(df)}条", "TopicBertopic")
        except Exception as e:
            log_error(logger, f"读取失败 {file_path.name}: {e}", "TopicBertopic")

    if not merged_records:
        log_error(logger, "所有文件读取失败", "TopicBertopic")
        return []

    log_success(logger, f"合并后文本总量: {len(merged_records)}条", "TopicBertopic")
    return merged_records


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


import hashlib

def _preprocess_text(texts: List[str], ids: List[str], channels: List[str], user_words: set, stop_words: set, logger) -> Tuple[List[str], List[str], List[str]]:
    """文本预处理和分词"""
    # 添加用户词典
    for word in user_words:
        jieba.add_word(word)

    processed_texts = []
    processed_ids = []
    processed_channels = []
    
    # Handle case where channels might be shorter or None if logic failed, though zip handles shortest
    if not channels:
        channels = ["未知"] * len(texts)

    for i, (text, doc_id, channel) in enumerate(zip(texts, ids, channels)):
        if pd.isna(text) or not str(text).strip():
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
            processed_texts.append(' '.join(words))
            processed_ids.append(str(doc_id))
            processed_channels.append(str(channel))

        # 进度提示
        if (i + 1) % 1000 == 0:
            if total_count:
                log_success(logger, f"已处理 {i + 1}/{total_count} 条文本", "TopicBertopic")
            else:
                log_success(logger, f"已处理 {i + 1} 条文本", "TopicBertopic")

    log_success(logger, f"文本预处理完成，有效文本: {len(processed_texts)}", "TopicBertopic")
    return processed_texts, processed_ids, processed_channels


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
    ids: List[str],
    channels: List[str],
    topic_name: str,
    start_date: str,
    end_date: str,
    output_dir: Path,
    logger,
    prompt_config: Optional[Dict[str, Any]] = None,
    run_params: Optional[Dict[str, Any]] = None,
    embedding_model: Optional[SentenceTransformer] = None,
    progress_callback=None,
) -> bool:
    """运行BERTopic主题分析"""
    try:
        def _emit_progress(phase: str, percentage: int, message: str, **extra: Any) -> None:
            if not callable(progress_callback):
                return
            payload = {
                "phase": phase,
                "percentage": percentage,
                "message": message,
                "current_step": str(extra.get("current_step") or phase).strip() or phase,
            }
            payload.update(extra)
            progress_callback(payload)

        resolved_params = _resolve_run_params(run_params)
        vectorizer_params = resolved_params["vectorizer"]
        umap_params = resolved_params["umap"]
        hdbscan_params = resolved_params["hdbscan"]
        bertopic_params = resolved_params["bertopic"]

        # 动态调整配置：根据数据量自动优化 min_cluster_size
        # 策略倾向于“保留更多可交给 LLM 合并的细粒度主题”，避免过早合并。
        n_docs = len(vectorizer_texts)
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

        if embedding_model is None:
            log_error(logger, "未提供嵌入模型实例", "TopicBertopic")
            return False
        if raw_embeddings.size == 0:
            log_error(logger, "未提供可用文档嵌入", "TopicBertopic")
            return False

        def _build_topic_model(current_vectorizer_params: Dict[str, Any]) -> BERTopic:
            vectorizer_model = CountVectorizer(
                stop_words=None,  # 已在前端处理停用词
                ngram_range=(
                    int(current_vectorizer_params["ngram_min"]),
                    int(current_vectorizer_params["ngram_max"]),
                ),
                min_df=current_vectorizer_params["min_df"],
                max_df=current_vectorizer_params["max_df"],
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
                cluster_selection_method=str(hdbscan_params["cluster_selection_method"]),
            )

            return BERTopic(
                embedding_model=embedding_model,
                vectorizer_model=vectorizer_model,
                umap_model=umap_model,
                hdbscan_model=hdbscan_model,
                language="chinese (simplified)",
                top_n_words=int(bertopic_params["top_n_words"]),
                calculate_probabilities=bool(bertopic_params["calculate_probabilities"]),
                verbose=bool(bertopic_params["verbose"]),
            )

        topic_model = _build_topic_model(vectorizer_params)

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
        _emit_progress("cluster", 60, "正在训练 BERTopic 模型。", current_step="cluster")
        log_success(logger, "开始训练BERTopic模型...", "TopicBertopic")
        try:
            try:
                topics, probs = topic_model.fit_transform(vectorizer_texts, embeddings=raw_embeddings)
            except ValueError as exc:
                if "max_df corresponds to < documents than min_df" not in str(exc):
                    raise
                fallback_vectorizer_params = dict(vectorizer_params)
                fallback_vectorizer_params["min_df"] = 1
                fallback_vectorizer_params["max_df"] = 1.0
                log_skip(
                    logger,
                    (
                        "预过滤后主题样本过少，触发 CountVectorizer 回退: "
                        f"min_df {vectorizer_params['min_df']} -> 1, "
                        f"max_df {vectorizer_params['max_df']} -> 1.0"
                    ),
                    "TopicBertopic",
                )
                topic_model = _build_topic_model(fallback_vectorizer_params)
                topics, probs = topic_model.fit_transform(vectorizer_texts, embeddings=raw_embeddings)
        finally:
            if string_storage_changed:
                try:
                    pd.set_option("mode.string_storage", previous_string_storage)
                except Exception:
                    pass

        _emit_progress("persist", 74, "正在整理 BERTopic 原始主题结果。", current_step="persist")

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
                    "frequency": float(row['Count'] / len(vectorizer_texts)),
                    "keywords": topic_keywords,
                })

        # 按频率排序
        topic_stats.sort(key=lambda x: x['count'], reverse=True)

        topic_sample_size = _resolve_topic_sample_size(prompt_config)
        topic_samples_by_id = _build_topic_doc_samples(
            raw_texts,
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
                "total_documents": len(vectorizer_texts),
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
            for i, (topic_id, embedding, doc_id, channel) in enumerate(zip(topics, doc_embeddings, ids, channels)):
                if topic_id != -1:  # 排除离群点
                    doc_coords.append({
                        "doc_id": i,
                        "post_id": str(doc_id),
                        "channel": str(channel),
                        "topic_id": int(topic_id),
                        "x": float(embedding[0]),
                        "y": float(embedding[1])
                    })

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
        _emit_progress("recluster", 84, "正在执行 LLM 再聚类。", current_step="recluster")
        if topic_stats and len(topic_stats) > 0:
            try:
                recluster_topic_stats, _ = _filter_recluster_topic_stats(
                    topic_stats,
                    topic_samples_by_id,
                    topic_name=topic_name,
                    prompt_config=prompt_config,
                    logger=logger,
                )
                if not recluster_topic_stats:
                    recluster_topic_stats = list(topic_stats)

                topic_limit = _resolve_recluster_topic_limit(prompt_config)
                coverage_target = _resolve_recluster_target_coverage(prompt_config)
                target_limit = min(topic_limit, len(recluster_topic_stats))
                topic_stats_for_llm, selection_meta = _select_topics_for_recluster_with_metadata(
                    recluster_topic_stats,
                    target_limit,
                    coverage_target,
                )
                effective_topic_sample_size = _resolve_effective_topic_sample_size(
                    topic_sample_size,
                    len(topic_stats_for_llm),
                )

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
                            "samples": samples[:effective_topic_sample_size],
                        }
                    )

                total_docs = int(selection_meta.get("total_docs") or 0)
                selected_docs = int(selection_meta.get("selected_docs") or 0)
                coverage_ratio = float(selection_meta.get("coverage_ratio") or 0.0)
                head_size = int(selection_meta.get("head_size") or 0)
                diversity_size = int(selection_meta.get("diversity_size") or 0)
                if len(recluster_topic_stats) > len(topic_stats_for_llm):
                    doc_coverage_text = (
                        f"{selected_docs}/{total_docs} ({coverage_ratio * 100:.2f}%)"
                        if total_docs > 0
                        else "0/0 (0.00%)"
                    )
                    log_success(
                        logger,
                        (
                            f"重分类输入主题选择: 总{len(recluster_topic_stats)}个, 使用{len(topic_stats_for_llm)}个 "
                            f"(主题文档覆盖率目标{coverage_target * 100:.2f}%, 实际{doc_coverage_text}, "
                            f"高频{head_size} + 发散{diversity_size})"
                        ),
                        "TopicBertopic",
                    )
                if effective_topic_sample_size != topic_sample_size:
                    log_skip(
                        logger,
                        (
                            f"重分类主题较多({len(topic_stats_for_llm)}个)，"
                            f"样本文本数 {topic_sample_size} -> {effective_topic_sample_size}"
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

        _emit_progress("persist", 92, "正在生成时间趋势与最终结果。", current_step="temporal")
        temporal_payload = _build_temporal_payload(
            topic_model,
            vectorizer_texts,
            list(topics),
            raw_dates,
            topic_stats,
            topic_name,
            start_date,
            end_date,
            logger,
            llm_cluster_payload=_load_json_if_exists(output_dir / "4大模型再聚类结果.json"),
        )
        if temporal_payload:
            with open(output_dir / "6主题时间趋势.json", "w", encoding="utf-8") as f:
                json.dump(temporal_payload, f, ensure_ascii=False, indent=2)
            log_success(logger, "已保存 BERTopic temporal 结果: 6主题时间趋势.json", "TopicBertopic")

        _emit_progress("persist", 98, "分析结果写入完成，正在收尾。", current_step="finalize")
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
    progress_callback=None,
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

    def _emit_progress(phase: str, percentage: int, message: str, **extra: Any) -> None:
        if not callable(progress_callback):
            return
        payload = {
            "phase": phase,
            "percentage": percentage,
            "message": message,
            "current_step": str(extra.get("current_step") or phase).strip() or phase,
        }
        payload.update(extra)
        progress_callback(payload)

    try:
        _emit_progress("prepare", 4, "正在加载 BERTopic 提示词配置。", current_step="prompt")
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
            _emit_progress("collect", 10, "正在确认本地缓存与采集数据。", current_step="fetch")
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

        project_stop_words = {
            str(item or "").strip()
            for item in (prompt_config.get("project_stopwords") or [])
            if str(item or "").strip()
        }
        if project_stop_words:
            before_merge_count = len(stop_words)
            stop_words.update(project_stop_words)
            merged_added_count = len(stop_words) - before_merge_count
            log_success(
                logger,
                (
                    f"加载项目停用词: {len(project_stop_words)}个, "
                    f"合并新增 {merged_added_count} 个"
                ),
                "TopicBertopic",
            )

        # 加载和预处理数据
        _emit_progress("prepare", 24, "正在读取待分析文本。", current_step="load_texts")
        texts = _load_and_merge_data(paths["fetch_dir"], logger)
        if not texts:
            log_error(logger, "没有可用的数据", "TopicBertopic")
            return False

    # 提取文本内容
        df_clean = df.dropna(subset=['contents'])
        texts = df_clean['contents'].tolist()
        
        # 提取ID
        if 'id' in df_clean.columns:
            ids = df_clean['id'].tolist()
        elif 'post_id' in df_clean.columns:
            ids = df_clean['post_id'].tolist()
        elif 'url' in df_clean.columns:
            ids = df_clean['url'].tolist()
        else:
            log_error(logger, "未找到ID字段，使用内容哈希作为ID", "TopicBertopic")
            ids = [hashlib.md5(str(t).encode('utf-8')).hexdigest() for t in texts]

        # 提取渠道
        if 'channel' in df_clean.columns:
            channels = df_clean['channel'].tolist()
        else:
            channels = ["未知"] * len(texts)

        if not texts:
            log_error(logger, "没有有效的文本内容", "TopicBertopic")
            return False

        log_success(logger, f"加载文本数据: {text_count}条", "TopicBertopic")
        _emit_progress("prepare", 34, f"已读取 {text_count} 条文本，正在标准化内容。", current_step="normalize", text_count=text_count)

        raw_texts, raw_dates = _normalise_raw_texts(
            texts,
            logger,
            total_count=text_count,
        )
        del texts
        gc.collect()
        if not raw_texts:
            log_error(logger, "原文清洗后没有有效内容", "TopicBertopic")
            return False

        _emit_progress("embed", 44, "正在生成文本向量。", current_step="embed", text_count=len(raw_texts))
        try:
            embedding_model, _, _, embedding_batch_size = _load_embedding_model(logger)
        except Exception as exc:
            log_error(logger, f"加载本地嵌入模型失败: {exc}", "TopicBertopic")
            return False

        raw_embeddings = _encode_text_embeddings(
            raw_texts,
            embedding_model,
            batch_size=embedding_batch_size,
            logger=logger,
            log_label="原文语义嵌入",
        )
        if raw_embeddings.size == 0:
            log_error(logger, "原文嵌入生成失败", "TopicBertopic")
            return False

        _emit_progress("prepare", 54, "向量生成完成，正在执行预过滤与文本预处理。", current_step="prefilter", text_count=len(raw_texts))
        raw_texts, raw_embeddings, raw_dates = _apply_topic_relevance_prefilter(
            raw_texts,
            raw_embeddings,
            topic_label,
            prompt_config,
            embedding_model,
            raw_dates=raw_dates,
            batch_size=embedding_batch_size,
            logger=logger,
        )
        if not raw_texts or raw_embeddings.size == 0:
            log_error(logger, "预过滤后没有可用文本", "TopicBertopic")
            return False

        # 文本预处理
        processed_texts, processed_ids, processed_channels = _preprocess_text(texts, ids, channels, user_words, stop_words, logger)
        if not processed_texts:
            log_error(logger, "文本预处理后没有有效内容", "TopicBertopic")
            return False
        if len(kept_indices) != len(raw_texts):
            raw_texts = [raw_texts[idx] for idx in kept_indices]
            raw_dates = [raw_dates[idx] for idx in kept_indices]
            raw_embeddings = np.asarray(raw_embeddings[kept_indices], dtype=np.float32)

        # 确保输出目录存在
        output_dir = paths["out_analyze"]
        output_dir.mkdir(parents=True, exist_ok=True)

        # 运行BERTopic分析
        success = _run_bertopic(
            raw_texts,
            processed_texts,
            processed_ids,
            processed_channels,
            topic_label,
        start_date,
        end_date,
        output_dir,
        logger,
        prompt_config=prompt_config,
        run_params=run_params,
    )

        if success:
            _emit_progress("persist", 99, "BERTopic 结果已生成。", current_step="done")
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
