"""
结构化报告生成服务。

设计目标：
1. 报告数值部分（KPI/图表数据）尽量由分析结果直接计算，保证可复现；
2. 报告文字部分（副标题/阶段解读/洞察卡片）通过 LangChain 统一入口生成；
3. 与 ``frontend/src/views/analysis/ReportGenerationView.vue`` 的数据结构对齐。
"""
from __future__ import annotations

import asyncio
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..utils.ai import call_langchain_chat
from ..utils.logging.logging import setup_logger
from ..utils.setting.paths import bucket, ensure_bucket, get_data_root
from .data_report import (
    _collect_sections as legacy_collect_sections,
    _compose_llm_input as legacy_compose_llm_input,
    _llm_call_report as legacy_llm_call_report,
    _load_manual_report_text as legacy_load_manual_report_text,
    _load_prompt_yaml as legacy_load_prompt_yaml,
    _sections_to_block as legacy_sections_to_block,
)
from .structured_prompts import (
    REPORT_SYSTEM_PROMPT,
    build_bertopic_insight_prompt,
    build_insights_prompt,
    build_stage_notes_prompt,
    build_title_subtitle_prompt,
)


ANALYZE_FILE_MAP = {
    "volume": "volume.json",
    "attitude": "attitude.json",
    "trends": "trends.json",
    "geography": "geography.json",
    "publishers": "publishers.json",
    "keywords": "keywords.json",
    "classification": "classification.json",
}

BERTOPIC_FILE_MAP = {
    "summary": "1主题统计结果.json",
    "coords": "3文档2D坐标.json",
    "llm_clusters": "4大模型再聚类结果.json",
    "llm_keywords": "5大模型主题关键词.json",
    "temporal": "6主题时间趋势.json",
}

DEFAULT_ANALYZE_FILENAME = "result.json"
REPORT_CACHE_FILENAME = "report_payload.json"
REPORT_CACHE_VERSION = 4

SENTIMENT_POSITIVE = {"positive", "正面", "积极", "pos", "p"}
SENTIMENT_NEUTRAL = {"neutral", "中性", "客观", "neu"}
SENTIMENT_NEGATIVE = {"negative", "负面", "消极", "neg", "n"}

FACTUAL_HINTS = ("报道", "新闻", "资讯", "快讯", "消息", "事实")
OPINION_HINTS = ("评论", "观点", "解读", "分析", "社评", "态度", "讨论")


def _safe_async_call(coro: Any) -> Any:
    try:
        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


def _compose_folder(start: str, end: Optional[str]) -> str:
    start_text = str(start or "").strip()
    end_text = str(end or "").strip()
    if not start_text:
        return ""
    if end_text and end_text != start_text:
        return f"{start_text}_{end_text}"
    return start_text


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _find_json_file(dir_path: Path, preferred_filename: str) -> Optional[Path]:
    preferred = dir_path / preferred_filename
    if preferred.exists():
        return preferred
    candidates = sorted(dir_path.glob("*.json"))
    if candidates:
        return candidates[0]
    return None


def _get_analyze_root(topic: str, start: str, end: Optional[str]) -> Path:
    start_text = str(start or "").strip()
    end_text = str(end or "").strip()
    if not start_text:
        raise ValueError("Missing required field(s): start")

    folder_candidates: List[str] = []
    # Align with analyze stage folder format: start_end (including single-day start_start).
    if end_text:
        folder_candidates.append(f"{start_text}_{end_text}")
    for candidate in (
        _compose_folder(start_text, end_text or None),
        start_text,
        f"{start_text}_{start_text}",
    ):
        token = str(candidate or "").strip()
        if token and token not in folder_candidates:
            folder_candidates.append(token)

    missing_root = bucket("analyze", topic, folder_candidates[0])
    for folder in folder_candidates:
        root = bucket("analyze", topic, folder)
        if root.exists():
            return root
    raise ValueError(f"未找到分析结果目录: {missing_root}")


def _extract_rows(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, dict):
        data = payload.get("data")
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _parse_int(value: Any) -> int:
    try:
        return int(float(value))
    except Exception:
        return 0


def _normalize_name(value: Any) -> str:
    return str(value or "").strip()


def _format_label_date(raw: str) -> str:
    try:
        dt = datetime.strptime(raw[:10], "%Y-%m-%d")
        return f"{dt.month}月{dt.day}日"
    except Exception:
        return raw


def _parse_date_value(raw: str) -> Optional[datetime]:
    try:
        return datetime.strptime(raw[:10], "%Y-%m-%d")
    except Exception:
        return None


def _load_function_rows(analyze_root: Path, func_name: str) -> List[Dict[str, Any]]:
    func_dir = analyze_root / func_name / "总体"
    if not func_dir.exists():
        return []
    filename = ANALYZE_FILE_MAP.get(func_name, DEFAULT_ANALYZE_FILENAME)
    file_path = _find_json_file(func_dir, filename)
    if not file_path:
        return []
    try:
        payload = _load_json(file_path)
    except Exception:
        return []
    return _extract_rows(payload)


def _resolve_bucket_folder_root(layer: str, topic: str, folder_candidates: List[str]) -> Optional[Path]:
    for folder in folder_candidates:
        folder_text = str(folder or "").strip()
        if not folder_text:
            continue
        candidate = bucket(layer, topic, folder_text)
        if candidate.exists():
            return candidate
    return None


def _extract_topic_id(value: Any) -> Optional[int]:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    match = re.search(r"-?\d+", raw)
    if not match:
        return None
    try:
        return int(match.group(0))
    except Exception:
        return None


def _normalize_topic_name(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return re.sub(r"\s+", " ", text)


def _extract_date_text(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    match = re.search(r"(20\d{2}-\d{2}-\d{2})", raw)
    return match.group(1) if match else ""


def _load_json_safely(path: Optional[Path]) -> Any:
    if not path or not path.exists():
        return None
    try:
        return _load_json(path)
    except Exception:
        return None


def _parse_bertopic_themes(
    cluster_payload: Any,
    keyword_payload: Any,
) -> Tuple[List[Dict[str, Any]], Dict[str, str], Dict[int, str]]:
    if isinstance(keyword_payload, dict):
        keyword_map = {
            _normalize_topic_name(name): value
            for name, value in keyword_payload.items()
            if isinstance(value, list)
        }
    else:
        keyword_map = {}

    if isinstance(cluster_payload, dict):
        items = list(cluster_payload.items())
    elif isinstance(cluster_payload, list):
        items = [(str(index + 1), item) for index, item in enumerate(cluster_payload)]
    else:
        items = []

    themes: List[Dict[str, Any]] = []
    cluster_by_topic_name: Dict[str, str] = {}
    cluster_by_topic_id: Dict[int, str] = {}

    for fallback_name, raw in items:
        if not isinstance(raw, dict):
            continue
        cluster_name = str(raw.get("主题命名") or raw.get("cluster_name") or fallback_name).strip()
        if not cluster_name:
            continue

        original_topics_raw = raw.get("原始主题集合")
        original_topics = []
        if isinstance(original_topics_raw, list):
            original_topics = [str(item).strip() for item in original_topics_raw if str(item or "").strip()]

        doc_count = _parse_int(raw.get("文档数"))
        description = str(raw.get("主题描述") or raw.get("description") or "").strip()

        keyword_value = keyword_map.get(_normalize_topic_name(cluster_name), [])
        keywords = [str(item).strip() for item in keyword_value if str(item or "").strip()] if isinstance(keyword_value, list) else []

        for topic_name in original_topics:
            normalized_name = _normalize_topic_name(topic_name)
            if normalized_name:
                cluster_by_topic_name[normalized_name] = cluster_name
            topic_id = _extract_topic_id(topic_name)
            if topic_id is not None:
                cluster_by_topic_id[topic_id] = cluster_name

        themes.append(
            {
                "name": cluster_name,
                "value": doc_count,
                "description": description,
                "keywords": keywords[:8],
                "originalTopics": original_topics,
            }
        )

    themes.sort(key=lambda item: item.get("value", 0), reverse=True)
    return themes, cluster_by_topic_name, cluster_by_topic_id


def _build_topicid_cluster_map(
    summary_payload: Any,
    cluster_by_topic_name: Dict[str, str],
    cluster_by_topic_id: Dict[int, str],
) -> Dict[int, str]:
    mapping = dict(cluster_by_topic_id)
    if not isinstance(summary_payload, dict):
        return mapping

    topic_rows: List[Dict[str, Any]] = []
    raw_topic_rows = summary_payload.get("topics")
    if isinstance(raw_topic_rows, list):
        topic_rows = [row for row in raw_topic_rows if isinstance(row, dict)]
    else:
        # Legacy BERTopic summary format:
        # {"主题文档统计": {"主题0": {"文档数": ..., "文档ID": [...]}, ...}, ...}
        legacy_stats = summary_payload.get("主题文档统计")
        if isinstance(legacy_stats, dict):
            for topic_name, legacy_row in legacy_stats.items():
                if not str(topic_name or "").strip():
                    continue
                topic_rows.append(
                    {
                        "topic_id": topic_name,
                        "topic_name": topic_name,
                        "count": legacy_row.get("文档数") if isinstance(legacy_row, dict) else 0,
                    }
                )

    if not topic_rows:
        return mapping

    for row in topic_rows:
        topic_id = _extract_topic_id(row.get("topic_id"))
        if topic_id is None:
            continue
        topic_name = _normalize_topic_name(row.get("topic_name"))
        if topic_name and topic_name in cluster_by_topic_name:
            mapping[topic_id] = cluster_by_topic_name[topic_name]
    return mapping


def _load_fetch_doc_dates(topic_identifier: str, folder_candidates: List[str]) -> Dict[int, str]:
    fetch_root = _resolve_bucket_folder_root("fetch", topic_identifier, folder_candidates)
    if not fetch_root:
        return _load_upload_doc_dates(topic_identifier)

    overall_path = fetch_root / "总体.jsonl"
    if not overall_path.exists():
        return _load_upload_doc_dates(topic_identifier)

    records: List[Tuple[str, str]] = []
    try:
        with overall_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                raw = line.strip()
                if not raw:
                    continue
                try:
                    row = json.loads(raw)
                except Exception:
                    continue
                if not isinstance(row, dict):
                    continue

                content = row.get("contents")
                if content is None:
                    content = row.get("content")
                if content is None:
                    continue
                content_text = str(content)

                published_at = (
                    row.get("published_at")
                    or row.get("publish_time")
                    or row.get("date")
                    or row.get("created_at")
                )
                date_text = _extract_date_text(published_at)
                records.append((content_text, date_text))
    except Exception:
        return _load_upload_doc_dates(topic_identifier)

    if not records:
        return _load_upload_doc_dates(topic_identifier)

    return _build_doc_date_map(records)


def _load_upload_doc_dates(topic_identifier: str) -> Dict[int, str]:
    uploads_jsonl_dir = get_data_root() / "projects" / topic_identifier / "uploads" / "jsonl"
    if not uploads_jsonl_dir.exists() or not uploads_jsonl_dir.is_dir():
        return {}

    jsonl_files = sorted(
        [path for path in uploads_jsonl_dir.glob("*.jsonl") if path.is_file()],
        key=lambda path: path.stat().st_mtime if path.exists() else 0,
        reverse=True,
    )
    if not jsonl_files:
        return {}

    records: List[Tuple[str, str]] = []
    for file_path in jsonl_files:
        try:
            with file_path.open("r", encoding="utf-8") as fh:
                for line in fh:
                    raw = line.strip()
                    if not raw:
                        continue
                    try:
                        row = json.loads(raw)
                    except Exception:
                        continue
                    if not isinstance(row, dict):
                        continue

                    content = row.get("contents")
                    if content is None:
                        content = row.get("content")
                    if content is None:
                        continue
                    content_text = str(content)

                    published_at = (
                        row.get("published_at")
                        or row.get("publish_time")
                        or row.get("date")
                        or row.get("created_at")
                    )
                    date_text = _extract_date_text(published_at)
                    records.append((content_text, date_text))
        except Exception:
            continue

    if not records:
        return {}

    return _build_doc_date_map(records)


def _build_doc_date_map(records: List[Tuple[str, str]]) -> Dict[int, str]:
    last_index: Dict[str, int] = {}
    for idx, (content_text, _) in enumerate(records):
        last_index[content_text] = idx

    deduped: List[Tuple[str, str]] = []
    for idx, item in enumerate(records):
        content_text = item[0]
        if last_index.get(content_text) != idx:
            continue
        deduped.append(item)

    return {idx: date_text for idx, (_, date_text) in enumerate(deduped)}


def _build_bertopic_time_nodes(
    coords_payload: Any,
    topicid_cluster_map: Dict[int, str],
    doc_date_map: Dict[int, str],
) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    docs = []
    if isinstance(coords_payload, dict):
        payload_docs = coords_payload.get("documents")
        if isinstance(payload_docs, list):
            docs = payload_docs
    elif isinstance(coords_payload, list):
        docs = coords_payload

    if not docs or not topicid_cluster_map or not doc_date_map:
        return [], {"coords_docs": len(docs), "mapped_docs": 0, "dated_docs": 0}

    node_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    mapped_docs = 0
    dated_docs = 0

    for row in docs:
        if not isinstance(row, dict):
            continue

        doc_id = _extract_topic_id(row.get("doc_id"))
        if doc_id is None:
            continue
        date_text = doc_date_map.get(doc_id, "")
        if not date_text:
            continue
        dated_docs += 1

        topic_id = _extract_topic_id(row.get("topic_id"))
        if topic_id is None:
            continue
        cluster_name = topicid_cluster_map.get(topic_id)
        if not cluster_name:
            continue

        mapped_docs += 1
        node_counts[date_text][cluster_name] += 1

    time_nodes: List[Dict[str, Any]] = []
    for date_text in sorted(node_counts.keys()):
        cluster_counts = node_counts[date_text]
        sorted_clusters = sorted(
            [{"name": name, "value": value} for name, value in cluster_counts.items()],
            key=lambda item: item["value"],
            reverse=True,
        )
        total = sum(item["value"] for item in sorted_clusters)
        top_theme = sorted_clusters[0] if sorted_clusters else {"name": "", "value": 0}
        time_nodes.append(
            {
                "date": date_text,
                "label": _format_label_date(date_text),
                "total": total,
                "topTheme": top_theme.get("name", ""),
                "topValue": _parse_int(top_theme.get("value")),
                "themes": sorted_clusters[:5],
            }
        )

    stats = {
        "coords_docs": len(docs),
        "mapped_docs": mapped_docs,
        "dated_docs": dated_docs,
    }
    return time_nodes, stats


def _normalize_bertopic_time_nodes(rows: Any) -> List[Dict[str, Any]]:
    if not isinstance(rows, list):
        return []

    nodes: List[Dict[str, Any]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        date_text = str(item.get("date") or "").strip()
        top_theme = str(item.get("topTheme") or "").strip()
        if not date_text or not top_theme:
            continue
        raw_themes = item.get("themes")
        themes: List[Dict[str, Any]] = []
        if isinstance(raw_themes, list):
            for theme in raw_themes:
                if not isinstance(theme, dict):
                    continue
                name = str(theme.get("name") or "").strip()
                if not name:
                    continue
                themes.append({"name": name, "value": _parse_int(theme.get("value"))})
        themes.sort(key=lambda theme: theme.get("value", 0), reverse=True)
        nodes.append(
            {
                "date": date_text,
                "label": str(item.get("label") or _format_label_date(date_text)),
                "total": _parse_int(item.get("total")),
                "topTheme": top_theme,
                "topValue": _parse_int(item.get("topValue")),
                "themes": themes,
            }
        )

    nodes.sort(key=lambda item: _parse_date_value(str(item.get("date") or "")) or datetime.min)
    return nodes


def _extract_temporal_time_context(temporal_payload: Any) -> Tuple[List[Dict[str, Any]], Dict[str, Any], Dict[str, Any]]:
    if not isinstance(temporal_payload, dict):
        return [], {}, {}

    nodes_raw = temporal_payload.get("time_nodes")
    if not isinstance(nodes_raw, list):
        llm_payload = temporal_payload.get("llm_clusters")
        if isinstance(llm_payload, dict) and isinstance(llm_payload.get("time_nodes"), list):
            nodes_raw = llm_payload.get("time_nodes")
    if not isinstance(nodes_raw, list):
        raw_payload = temporal_payload.get("raw_topics")
        if isinstance(raw_payload, dict) and isinstance(raw_payload.get("time_nodes"), list):
            nodes_raw = raw_payload.get("time_nodes")

    nodes = _normalize_bertopic_time_nodes(nodes_raw)
    meta = temporal_payload.get("meta") if isinstance(temporal_payload.get("meta"), dict) else {}
    overview = temporal_payload.get("overview") if isinstance(temporal_payload.get("overview"), dict) else {}
    return nodes, meta, overview


def _load_bertopic_report_context(
    topic_identifier: str,
    folder_candidates: List[str],
) -> Dict[str, Any]:
    topic_root = _resolve_bucket_folder_root("topic", topic_identifier, folder_candidates)
    if not topic_root:
        return {"themes": [], "time_nodes": [], "overview": {}, "meta": {"source": ""}}

    summary_payload = _load_json_safely(topic_root / BERTOPIC_FILE_MAP["summary"])
    cluster_payload = _load_json_safely(topic_root / BERTOPIC_FILE_MAP["llm_clusters"])
    keyword_payload = _load_json_safely(topic_root / BERTOPIC_FILE_MAP["llm_keywords"])
    temporal_payload = _load_json_safely(topic_root / BERTOPIC_FILE_MAP["temporal"])

    themes, cluster_by_topic_name, cluster_by_topic_id = _parse_bertopic_themes(cluster_payload, keyword_payload)
    cluster_doc_total = sum(_parse_int(item.get("value")) for item in themes)
    temporal_nodes, temporal_meta, temporal_overview = _extract_temporal_time_context(temporal_payload)
    if temporal_nodes:
        temporal_docs = _parse_int(temporal_meta.get("temporal_documents"))
        mapped_docs = _parse_int(temporal_meta.get("llm_mapped_documents"))
        if mapped_docs <= 0:
            mapped_docs = sum(_parse_int(item.get("total")) for item in temporal_nodes)
        coverage = float(temporal_meta.get("llm_coverage_rate") or 0.0)
        if coverage <= 0 and temporal_docs > 0:
            coverage = mapped_docs / max(1, temporal_docs)
        return {
            "themes": themes,
            "time_nodes": temporal_nodes,
            "overview": temporal_overview,
            "meta": {
                "source": str(topic_root),
                "time_source": "temporal",
                "cluster_count": len(themes),
                "cluster_doc_total": cluster_doc_total,
                "time_node_count": len(temporal_nodes),
                "mapped_docs": mapped_docs,
                "dated_docs": temporal_docs,
                "coverage_rate": round(coverage, 4),
                "temporal_meta": temporal_meta,
            },
        }

    coords_payload = _load_json_safely(topic_root / BERTOPIC_FILE_MAP["coords"])
    topicid_cluster_map = _build_topicid_cluster_map(summary_payload, cluster_by_topic_name, cluster_by_topic_id)
    doc_date_map = _load_fetch_doc_dates(topic_identifier, folder_candidates)
    time_nodes, time_node_stats = _build_bertopic_time_nodes(coords_payload, topicid_cluster_map, doc_date_map)
    coverage = 0.0
    if time_node_stats.get("dated_docs", 0) > 0:
        coverage = time_node_stats["mapped_docs"] / max(1, time_node_stats["dated_docs"])

    return {
        "themes": themes,
        "time_nodes": time_nodes,
        "overview": {},
        "meta": {
            "source": str(topic_root),
            "time_source": "legacy_doc_mapping",
            "cluster_count": len(themes),
            "cluster_doc_total": cluster_doc_total,
            "topicid_cluster_count": len(topicid_cluster_map),
            "time_node_count": len(time_nodes),
            "mapped_docs": time_node_stats.get("mapped_docs", 0),
            "dated_docs": time_node_stats.get("dated_docs", 0),
            "coverage_rate": round(coverage, 4),
        },
    }


def _build_channel_data(volume_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = []
    for row in volume_rows:
        name = _normalize_name(row.get("name") or row.get("label") or row.get("key"))
        if not name:
            continue
        rows.append({"name": name, "value": _parse_int(row.get("value"))})
    rows.sort(key=lambda item: item["value"], reverse=True)
    return rows


def _build_timeline_data(trend_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    enriched: List[Tuple[Optional[datetime], Dict[str, Any]]] = []
    for row in trend_rows:
        raw_name = _normalize_name(row.get("name") or row.get("label") or row.get("key"))
        if not raw_name:
            continue
        value = _parse_int(row.get("value"))
        dt = _parse_date_value(raw_name)
        enriched.append(
            (
                dt,
                {
                    "date": _format_label_date(raw_name),
                    "raw_date": raw_name,
                    "value": value,
                },
            )
        )

    enriched.sort(key=lambda item: item[0] or datetime.min)
    return [item[1] for item in enriched]


def _build_sentiment_counts(attitude_rows: List[Dict[str, Any]]) -> Dict[str, int]:
    positive = 0
    neutral = 0
    negative = 0
    for row in attitude_rows:
        name = _normalize_name(row.get("name")).lower()
        value = _parse_int(row.get("value"))
        if name in SENTIMENT_POSITIVE:
            positive += value
        elif name in SENTIMENT_NEUTRAL:
            neutral += value
        elif name in SENTIMENT_NEGATIVE:
            negative += value
    return {"positive": positive, "neutral": neutral, "negative": negative}


def _build_classification_split(classification_rows: List[Dict[str, Any]]) -> Dict[str, int]:
    factual = 0
    opinion = 0
    total = 0
    for row in classification_rows:
        name = _normalize_name(row.get("name"))
        value = _parse_int(row.get("value"))
        if value <= 0:
            continue
        total += value
        if any(hint in name for hint in FACTUAL_HINTS):
            factual += value
        elif any(hint in name for hint in OPINION_HINTS):
            opinion += value

    if total > 0 and factual == 0 and opinion == 0:
        factual = int(total * 0.6)
        opinion = total - factual
    elif total > 0 and factual > 0 and opinion == 0:
        opinion = total - factual
    elif total > 0 and opinion > 0 and factual == 0:
        factual = total - opinion

    factual = max(0, factual)
    opinion = max(0, opinion)
    return {"factual": factual, "opinion": opinion}


def _build_theme_data(classification_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    themes = []
    for row in classification_rows:
        name = _normalize_name(row.get("name"))
        if not name:
            continue
        themes.append({"name": name, "value": _parse_int(row.get("value"))})
    themes.sort(key=lambda item: item["value"], reverse=True)
    return themes[:8]


def _build_keyword_data(keyword_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    keywords = []
    for row in keyword_rows:
        name = _normalize_name(row.get("name"))
        if not name:
            continue
        keywords.append({"term": name, "value": _parse_int(row.get("value"))})
    keywords.sort(key=lambda item: item["value"], reverse=True)
    return keywords[:20]


def _clamp_rate(value: float) -> float:
    return max(0.0, min(1.0, value))


def _compute_metrics(
    channels: List[Dict[str, Any]],
    timeline: List[Dict[str, Any]],
    sentiment: Dict[str, int],
    content_split: Dict[str, int],
) -> Dict[str, Any]:
    total_volume = sum(item["value"] for item in channels) if channels else sum(item["value"] for item in timeline)
    peak = {"value": 0, "date": "未提供"}
    if timeline:
        peak_item = max(timeline, key=lambda item: item.get("value", 0))
        peak = {"value": _parse_int(peak_item.get("value")), "date": peak_item.get("date") or "未提供"}

    sentiment_total = max(0, sentiment.get("positive", 0) + sentiment.get("neutral", 0) + sentiment.get("negative", 0))
    if sentiment_total > 0:
        positive_rate = sentiment.get("positive", 0) / sentiment_total
        neutral_rate = sentiment.get("neutral", 0) / sentiment_total
    else:
        positive_rate = 0.0
        neutral_rate = 0.0

    content_total = max(0, content_split.get("factual", 0) + content_split.get("opinion", 0))
    factual_ratio = (content_split.get("factual", 0) / content_total) if content_total > 0 else 0.0

    return {
        "totalVolume": total_volume,
        "peak": peak,
        "positiveRate": _clamp_rate(float(positive_rate)),
        "neutralRate": _clamp_rate(float(neutral_rate)),
        "factualRatio": _clamp_rate(float(factual_ratio)),
    }


def _calc_change_ratio(start_value: int, end_value: int) -> str:
    if start_value <= 0:
        return "波动明显"
    ratio = (end_value - start_value) / start_value * 100
    if ratio >= 0:
        return f"增幅约{ratio:.1f}%"
    return f"回落约{abs(ratio):.1f}%"


def _build_fallback_stage_notes(timeline: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    if not timeline:
        return []
    if len(timeline) == 1:
        only = timeline[0]
        return [
            {
                "title": "单日集中期",
                "range": only.get("date") or "当日",
                "delta": "单日样本",
                "highlight": f"当日声量为 {only.get('value', 0)}，建议结合渠道分布进一步判断传播结构。",
                "badge": "P1",
            }
        ]

    peak_idx = max(range(len(timeline)), key=lambda idx: timeline[idx].get("value", 0))
    pre = timeline[:peak_idx] if peak_idx > 0 else timeline[:1]
    peak_item = timeline[peak_idx]
    post = timeline[peak_idx + 1 :] if peak_idx + 1 < len(timeline) else timeline[-1:]

    pre_start = pre[0]
    pre_end = pre[-1]
    post_start = post[0]
    post_end = post[-1]

    pre_note = {
        "title": "预热爬升期",
        "range": f"{pre_start.get('date')}到{pre_end.get('date')}",
        "delta": _calc_change_ratio(_parse_int(pre_start.get("value")), _parse_int(pre_end.get("value"))),
        "highlight": (
            f"声量从 {_parse_int(pre_start.get('value'))} 变化至 {_parse_int(pre_end.get('value'))}，"
            "呈持续升温态势，说明议题关注度在启动阶段已开始扩散。"
        ),
        "badge": "P1",
    }
    peak_note = {
        "title": "峰值爆发期",
        "range": str(peak_item.get("date") or "峰值日"),
        "delta": f"峰值 {_parse_int(peak_item.get('value'))}",
        "highlight": (
            f"在 {peak_item.get('date')} 达到全周期最高声量 {_parse_int(peak_item.get('value'))}，"
            "通常对应关键事件触发与跨平台集中传播。"
        ),
        "badge": "P2",
    }
    post_note = {
        "title": "回落沉淀期",
        "range": f"{post_start.get('date')}到{post_end.get('date')}",
        "delta": _calc_change_ratio(_parse_int(post_start.get("value")), _parse_int(post_end.get("value"))),
        "highlight": (
            f"峰值后声量由 {_parse_int(post_start.get('value'))} 逐步变化至 {_parse_int(post_end.get('value'))}，"
            "传播进入长尾讨论阶段。"
        ),
        "badge": "P3",
    }
    return [pre_note, peak_note, post_note]


def _build_fallback_insights(
    channels: List[Dict[str, Any]],
    timeline: List[Dict[str, Any]],
    sentiment: Dict[str, int],
    keywords: List[Dict[str, Any]],
    themes: List[Dict[str, Any]],
    main_finding: str,
) -> Tuple[List[str], List[Dict[str, Any]]]:
    top_channels = channels[:3]
    top_channel_text = "、".join(f"{item['name']}({item['value']})" for item in top_channels) if top_channels else "暂无渠道数据"
    peak_text = "暂无趋势数据"
    if timeline:
        peak = max(timeline, key=lambda item: item.get("value", 0))
        peak_text = f"{peak.get('date')}达到峰值 {peak.get('value')}"

    sentiment_total = sentiment["positive"] + sentiment["neutral"] + sentiment["negative"]
    sentiment_text = "暂无情感数据"
    if sentiment_total > 0:
        sentiment_text = (
            f"正向{sentiment['positive']}、中性{sentiment['neutral']}、负向{sentiment['negative']}，"
            "整体情绪以中性和正向为主。"
        )

    top_keyword_text = "、".join(item["term"] for item in keywords[:5]) if keywords else "暂无关键词数据"
    top_theme_text = "、".join(item["name"] for item in themes[:4]) if themes else "暂无主题数据"

    highlight_points = [
        f"渠道分布显示重点平台为：{top_channel_text}。",
        f"时间趋势表现为：{peak_text}。",
        sentiment_text,
        main_finding or f"主题聚焦于：{top_theme_text}。",
    ]

    insights = [
        {
            "title": "声量",
            "headline": "渠道分布呈头部集中",
            "points": [
                f"头部渠道：{top_channel_text}。",
                "建议持续跟踪头部渠道的二次传播效率。",
                "中腰部渠道可作为增量触达补充。",
            ],
        },
        {
            "title": "趋势",
            "headline": "传播节奏具备阶段性",
            "points": [
                peak_text,
                "建议围绕峰值窗口布置回应与澄清内容。",
                "长尾阶段可转向深度内容沉淀。",
            ],
        },
        {
            "title": "态度",
            "headline": "整体情绪相对稳定",
            "points": [
                sentiment_text,
                "负向议题建议按来源和主题分层处置。",
                "正向与中性内容可用于延续讨论热度。",
            ],
        },
        {
            "title": "关键词",
            "headline": "高频词勾勒核心关注",
            "points": [
                f"高频关键词：{top_keyword_text}。",
                "建议按关键词簇追踪议题分叉。",
                "可对高热词配置预警与回应模板。",
            ],
        },
        {
            "title": "主题",
            "headline": "主题结构呈主次分层",
            "points": [
                f"核心主题：{top_theme_text}。",
                "建议针对主主题构建一致性叙事框架。",
                "次级主题可用于扩展受众覆盖面。",
            ],
        },
        {
            "title": "建议",
            "headline": "聚焦节奏、渠道与内容协同",
            "points": [
                "峰值前后设置差异化沟通策略。",
                "围绕高频关键词预置问答与素材。",
                "建立跨平台复盘机制，持续优化发布节奏。",
            ],
        },
    ]
    return highlight_points, insights


def _build_fallback_bertopic_insight(
    *,
    topic_label: str,
    start: str,
    end: str,
    bertopic_nodes: List[Dict[str, Any]],
) -> str:
    if not bertopic_nodes:
        return "暂无可用的 BERTopic 时间线数据，建议先完成 BERTopic 分析后再重新生成报告。"

    coverage_start = str(bertopic_nodes[0].get("date") or "").strip()
    coverage_end = str(bertopic_nodes[-1].get("date") or "").strip()
    covered_days = len(bertopic_nodes)
    mapped_docs = sum(_parse_int(item.get("total")) for item in bertopic_nodes)

    theme_stats: Dict[str, int] = defaultdict(int)
    for node in bertopic_nodes:
        themes = node.get("themes")
        if not isinstance(themes, list):
            continue
        for theme in themes:
            if not isinstance(theme, dict):
                continue
            theme_name = str(theme.get("name") or "").strip()
            if not theme_name:
                continue
            theme_stats[theme_name] += _parse_int(theme.get("value"))

    top_themes = sorted(theme_stats.items(), key=lambda item: item[1], reverse=True)[:3]
    top_theme_text = "、".join(f"{name}({value})" for name, value in top_themes) if top_themes else "暂无稳定主导主题"

    hotspot_nodes = sorted(bertopic_nodes, key=lambda item: _parse_int(item.get("total")), reverse=True)[:3]
    hotspot_text = "；".join(
        f"{str(item.get('label') or item.get('date') or '').strip()}：{str(item.get('topTheme') or '').strip()}（{_parse_int(item.get('topValue'))}）"
        for item in hotspot_nodes
        if str(item.get("topTheme") or "").strip()
    ) or "暂无明显爆发节点"

    mismatch_note = ""
    if coverage_start and coverage_end and (coverage_start > start or coverage_end < end):
        mismatch_note = (
            f"\n\n**覆盖说明**：BERTopic 时间线当前仅覆盖 {coverage_start} 至 {coverage_end}，"
            f"与报告区间 {start} 至 {end} 不完全一致。"
        )

    return (
        f"**{topic_label} 主题演化概览**：在 {coverage_start} 至 {coverage_end} 的 {covered_days} 个日期里，"
        f"BERTopic 共映射 {mapped_docs} 条讨论，主导关注点主要集中在 {top_theme_text}。\n\n"
        f"从传播节奏看，热点并非均匀分布，而是在少数关键日期集中抬升，代表性节点为：{hotspot_text}。"
        "这通常意味着外部事件触发后，讨论会快速聚焦到单一议题，再向相关议题扩散。"
        f"{mismatch_note}"
    )


def _extract_json_text(raw_text: str) -> Optional[str]:
    text = str(raw_text or "").strip()
    if not text:
        return None
    if text.startswith("{") and text.endswith("}"):
        return text
    object_match = re.search(r"\{[\s\S]*\}", text)
    if object_match:
        return object_match.group(0)
    return None


def _truncate_text(value: str, max_chars: int) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n...[内容已截断]"


def _build_legacy_report_context(
    *,
    topic_identifier: str,
    topic_label: str,
    date_folder: str,
) -> Dict[str, Any]:
    """
    复用原版 run_report 的核心链路，补充 RAG 增强上下文。

    顺序保持与原版一致：
    1) 手工报告文本（manual_report.*）
    2) explain/*/总体/*_rag_enhanced.json + 原提示词链路产出整文
    """
    logger = setup_logger(f"ReportStructured_{topic_identifier}", date_folder)
    topic_candidates: List[str] = []
    for candidate in [topic_identifier, topic_label]:
        value = str(candidate or "").strip()
        if value and value not in topic_candidates:
            topic_candidates.append(value)

    manual_text = ""
    manual_topic = ""
    for candidate in topic_candidates:
        text = legacy_load_manual_report_text(candidate, date_folder, logger)
        if text:
            manual_text = text
            manual_topic = candidate
            break

    sections: List[Tuple[str, str]] = []
    sections_topic = ""
    for candidate in topic_candidates:
        rows = legacy_collect_sections(candidate, date_folder, logger)
        if rows:
            sections = rows
            sections_topic = candidate
            break

    sections_text = legacy_sections_to_block(sections) if sections else ""
    full_text = manual_text

    if not full_text and sections_text:
        prompt_topic = topic_label or topic_identifier
        prompt_template = legacy_load_prompt_yaml(prompt_topic, logger)
        messages = legacy_compose_llm_input(prompt_topic, date_folder, sections_text, prompt_template)
        generated_text = _safe_async_call(
            legacy_llm_call_report(
                messages,
                logger,
                model=None,
                timeout=200.0,
                max_retries=2,
            )
        )
        full_text = str(generated_text or "").strip() or sections_text

    return {
        "manual_text": manual_text,
        "manual_topic": manual_topic,
        "sections": sections,
        "sections_topic": sections_topic,
        "sections_text": sections_text,
        "full_text": full_text,
        "sections_text_short": _truncate_text(sections_text, 5000),
        "full_text_short": _truncate_text(full_text, 6000),
    }


def _call_langchain_json(user_prompt: str, *, max_tokens: int = 1800) -> Optional[Dict[str, Any]]:
    raw_text = _safe_async_call(
        call_langchain_chat(
            [
                {"role": "system", "content": REPORT_SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            task="report",
            temperature=0.2,
            max_tokens=max_tokens,
        )
    )
    if not isinstance(raw_text, str) or not raw_text.strip():
        return None
    candidate = _extract_json_text(raw_text)
    if not candidate:
        return None
    try:
        payload = json.loads(candidate)
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _load_main_finding(analyze_root: Path) -> str:
    path = analyze_root / "ai_summary.json"
    if not path.exists():
        return ""
    try:
        payload = _load_json(path)
    except Exception:
        return ""
    if not isinstance(payload, dict):
        return ""
    main_finding = payload.get("main_finding")
    if isinstance(main_finding, dict):
        summary = str(main_finding.get("summary") or "").strip()
        if summary:
            return summary
    return ""


def _build_report_payload(
    *,
    topic_identifier: str,
    topic_label: str,
    start: str,
    end: str,
    analyze_root: Path,
) -> Dict[str, Any]:
    volume_rows = _load_function_rows(analyze_root, "volume")
    trend_rows = _load_function_rows(analyze_root, "trends")
    attitude_rows = _load_function_rows(analyze_root, "attitude")
    keyword_rows = _load_function_rows(analyze_root, "keywords")
    classification_rows = _load_function_rows(analyze_root, "classification")

    folder_candidates: List[str] = []
    for candidate in (analyze_root.name, _compose_folder(start, end), start):
        token = str(candidate or "").strip()
        if token and token not in folder_candidates:
            folder_candidates.append(token)

    bertopic_context = _load_bertopic_report_context(topic_identifier, folder_candidates)
    bertopic_themes = bertopic_context.get("themes") if isinstance(bertopic_context, dict) else []
    bertopic_time_nodes = bertopic_context.get("time_nodes") if isinstance(bertopic_context, dict) else []
    bertopic_overview_from_context = (
        bertopic_context.get("overview") if isinstance(bertopic_context, dict) else {}
    )

    channels = _build_channel_data(volume_rows)
    timeline = _build_timeline_data(trend_rows)
    sentiment = _build_sentiment_counts(attitude_rows)
    content_split = _build_classification_split(classification_rows)
    keywords = _build_keyword_data(keyword_rows)
    theme_source = "classification"
    theme_details = _build_theme_data(classification_rows)
    has_valid_bertopic_theme = isinstance(bertopic_themes, list) and any(
        isinstance(item, dict) and _parse_int(item.get("value")) > 0 and str(item.get("name") or "").strip()
        for item in bertopic_themes
    )
    if has_valid_bertopic_theme:
        theme_source = "bertopic"
        theme_details = bertopic_themes
    themes = [
        {
            "name": str(item.get("name") or "").strip(),
            "value": _parse_int(item.get("value")),
        }
        for item in theme_details
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    ]
    themes.sort(key=lambda item: item.get("value", 0), reverse=True)
    themes = themes[:8]

    bertopic_nodes_payload = []
    if isinstance(bertopic_time_nodes, list):
        for item in bertopic_time_nodes:
            if not isinstance(item, dict):
                continue
            date_text = str(item.get("date") or "").strip()
            top_theme = str(item.get("topTheme") or "").strip()
            if not date_text or not top_theme:
                continue
            node_themes = item.get("themes")
            compact_themes: List[Dict[str, Any]] = []
            if isinstance(node_themes, list):
                for node_theme in node_themes[:5]:
                    if not isinstance(node_theme, dict):
                        continue
                    name = str(node_theme.get("name") or "").strip()
                    if not name:
                        continue
                    compact_themes.append({"name": name, "value": _parse_int(node_theme.get("value"))})

            bertopic_nodes_payload.append(
                {
                    "date": date_text,
                    "label": str(item.get("label") or _format_label_date(date_text)),
                    "total": _parse_int(item.get("total")),
                    "topTheme": top_theme,
                    "topValue": _parse_int(item.get("topValue")),
                    "dominance": round(
                        _parse_int(item.get("topValue")) / max(1, _parse_int(item.get("total"))),
                        4,
                    ),
                    "themes": compact_themes,
                }
            )

    bertopic_nodes_payload.sort(key=lambda item: _parse_date_value(str(item.get("date") or "")) or datetime.min)
    bertopic_hotspots_payload = sorted(
        [
            {
                "date": item.get("date"),
                "label": item.get("label"),
                "total": _parse_int(item.get("total")),
                "topTheme": item.get("topTheme"),
                "topValue": _parse_int(item.get("topValue")),
                "dominance": float(item.get("dominance") or 0),
            }
            for item in bertopic_nodes_payload
        ],
        key=lambda item: _parse_int(item.get("total")),
        reverse=True,
    )[:12]
    bertopic_overview = dict(bertopic_overview_from_context or {})
    total_mapped_docs = sum(_parse_int(item.get("total")) for item in bertopic_nodes_payload)
    if not bertopic_overview:
        bertopic_overview = {
            "mode": "daily_dominant_theme",
            "aggregation": "day",
            "aggregationLabel": "日",
            "description": "按日期聚合文档后展示当日主导主题，不表示主题持续时长。",
            "bucketCount": len(bertopic_nodes_payload),
            "days": len(bertopic_nodes_payload),
            "totalMappedDocs": total_mapped_docs,
        }
    else:
        bertopic_overview.setdefault("mode", "native_topics_over_time")
        bertopic_overview.setdefault("aggregation", "day")
        bertopic_overview.setdefault("aggregationLabel", "日")
        bertopic_overview.setdefault("description", "基于 BERTopic temporal 结果的主题热度分布。")
        bertopic_overview.setdefault("bucketCount", len(bertopic_nodes_payload))
        bertopic_overview.setdefault("days", bertopic_overview.get("bucketCount") or len(bertopic_nodes_payload))
        bertopic_overview.setdefault("totalMappedDocs", total_mapped_docs)

    metrics = _compute_metrics(channels, timeline, sentiment, content_split)
    main_finding = _load_main_finding(analyze_root)
    legacy_context = _build_legacy_report_context(
        topic_identifier=topic_identifier,
        topic_label=topic_label,
        date_folder=analyze_root.name,
    )

    report_facts = {
        "topic": topic_label,
        "time_range": {"start": start, "end": end},
        "metrics": metrics,
        "channels": channels[:8],
        "timeline": timeline,
        "sentiment": sentiment,
        "content_split": content_split,
        "keywords": keywords[:10],
        "themes": themes[:8],
        "theme_source": theme_source,
        "bertopic_time_nodes": bertopic_hotspots_payload,
        "main_finding": main_finding,
        "legacy_rag_sections": legacy_context.get("sections_text_short", ""),
        "legacy_report_text": legacy_context.get("full_text_short", ""),
    }
    bertopic_timeline_for_llm = [
        {
            "date": str(item.get("date") or "").strip(),
            "topTheme": str(item.get("topTheme") or "").strip(),
            "topValue": _parse_int(item.get("topValue")),
            "total": _parse_int(item.get("total")),
            "secondaryThemes": [
                str(theme.get("name") or "").strip()
                for theme in (item.get("themes") or [])
                if isinstance(theme, dict) and str(theme.get("name") or "").strip()
            ][:2],
        }
        for item in bertopic_nodes_payload
    ]
    bertopic_insight_facts = {
        "topic": topic_label,
        "time_range": {"start": start, "end": end},
        "bertopic_overview": bertopic_overview,
        "bertopic_hotspots": bertopic_hotspots_payload[:10],
        "bertopic_timeline": bertopic_timeline_for_llm,
        "main_finding": main_finding,
        "legacy_rag_sections": legacy_context.get("sections_text_short", ""),
        "legacy_report_text": legacy_context.get("full_text_short", ""),
    }

    bertopic_insight = _build_fallback_bertopic_insight(
        topic_label=topic_label,
        start=start,
        end=end,
        bertopic_nodes=bertopic_nodes_payload,
    )
    bertopic_insight_source = "fallback"
    bertopic_insight_payload = _call_langchain_json(
        build_bertopic_insight_prompt(bertopic_insight_facts),
        max_tokens=1800,
    )
    if isinstance(bertopic_insight_payload, dict):
        bertopic_insight_candidate = str(
            bertopic_insight_payload.get("insight_markdown")
            or bertopic_insight_payload.get("insight")
            or bertopic_insight_payload.get("summary")
            or ""
        ).strip()
        if bertopic_insight_candidate:
            bertopic_insight = bertopic_insight_candidate
            bertopic_insight_source = "llm"

    title = f"{topic_label}舆情分析报告"
    subtitle = main_finding or "基于结构化统计结果自动生成，覆盖声量、趋势、态度与主题。"

    title_payload = _call_langchain_json(build_title_subtitle_prompt(topic_label, report_facts), max_tokens=500)
    if isinstance(title_payload, dict):
        title_candidate = str(title_payload.get("title") or "").strip()
        subtitle_candidate = str(title_payload.get("subtitle") or "").strip()
        if title_candidate:
            title = title_candidate
        if subtitle_candidate:
            subtitle = subtitle_candidate

    stage_notes = _build_fallback_stage_notes(timeline)
    stage_payload = _call_langchain_json(build_stage_notes_prompt(report_facts), max_tokens=1400)
    if isinstance(stage_payload, dict) and isinstance(stage_payload.get("stageNotes"), list):
        parsed_notes = []
        for idx, item in enumerate(stage_payload.get("stageNotes") or []):
            if not isinstance(item, dict):
                continue
            title_value = str(item.get("title") or "").strip()
            range_value = str(item.get("range") or "").strip()
            delta_value = str(item.get("delta") or "").strip()
            highlight_value = str(item.get("highlight") or "").strip()
            badge = str(item.get("badge") or f"P{idx + 1}").strip() or f"P{idx + 1}"
            if not (title_value and highlight_value):
                continue
            parsed_notes.append(
                {
                    "title": title_value,
                    "range": range_value or "未提供",
                    "delta": delta_value or "波动明显",
                    "highlight": highlight_value,
                    "badge": badge,
                }
            )
        if parsed_notes:
            stage_notes = parsed_notes[:3]

    highlight_points, insights = _build_fallback_insights(channels, timeline, sentiment, keywords, themes, main_finding)
    insights_payload = _call_langchain_json(build_insights_prompt(report_facts), max_tokens=2200)
    if isinstance(insights_payload, dict):
        points_payload = insights_payload.get("highlight_points")
        if isinstance(points_payload, list):
            parsed_points = [str(item).strip() for item in points_payload if str(item or "").strip()]
            if parsed_points:
                highlight_points = parsed_points[:4]

        cards_payload = insights_payload.get("insights")
        if isinstance(cards_payload, list):
            parsed_cards: List[Dict[str, Any]] = []
            for item in cards_payload:
                if not isinstance(item, dict):
                    continue
                title_value = str(item.get("title") or "").strip()
                headline_value = str(item.get("headline") or "").strip()
                points_value = item.get("points")
                if not title_value:
                    continue
                points_list = []
                if isinstance(points_value, list):
                    points_list = [str(point).strip() for point in points_value if str(point or "").strip()]
                if not points_list:
                    points_list = ["暂无补充要点"]
                parsed_cards.append(
                    {
                        "title": title_value,
                        "headline": headline_value or "结构化摘要",
                        "points": points_list[:5],
                    }
                )
            if parsed_cards:
                insights = parsed_cards[:6]

    now_text = datetime.now().strftime("%Y-%m-%d %H:%M")
    return {
        "title": title,
        "subtitle": subtitle,
        "rangeText": f"{start} → {end}",
        "lastUpdated": now_text,
        "metrics": metrics,
        "channels": channels,
        "timeline": [{"date": item.get("date"), "value": item.get("value")} for item in timeline],
        "sentiment": sentiment,
        "contentSplit": content_split,
        "keywords": keywords,
        "themes": themes,
        "themeSource": theme_source,
        "bertopicTimeNodes": bertopic_nodes_payload,
        "bertopicHotspots": bertopic_hotspots_payload,
        "bertopicOverview": bertopic_overview,
        "bertopicInsight": bertopic_insight,
        "stageNotes": stage_notes,
        "highlightPoints": highlight_points,
        "insights": insights,
        "meta": {
            "topic_identifier": topic_identifier,
            "topic_label": topic_label,
            "analyze_root": str(analyze_root),
            "theme_source": theme_source,
            "bertopic_context": bertopic_context.get("meta") if isinstance(bertopic_context, dict) else {},
            "bertopic_insight_source": bertopic_insight_source,
            "legacy_context": {
                "sections_source_topic": legacy_context.get("sections_topic") or "",
                "manual_source_topic": legacy_context.get("manual_topic") or "",
                "sections_count": len(legacy_context.get("sections") or []),
                "has_legacy_report_text": bool(str(legacy_context.get("full_text") or "").strip()),
            },
            "cache_version": REPORT_CACHE_VERSION,
            "generated_at": now_text,
        },
    }


def generate_report_payload(
    topic_identifier: str,
    start: str,
    end: Optional[str] = None,
    *,
    topic_label: Optional[str] = None,
    regenerate: bool = False,
) -> Dict[str, Any]:
    """
    生成报告页面所需的结构化数据。

    Args:
        topic_identifier: 专题目录标识。
        start: 开始日期（YYYY-MM-DD）。
        end: 结束日期，缺省时与 start 相同。
        topic_label: 前端展示名称，缺省时使用 topic_identifier。
        regenerate: 是否强制跳过缓存重新生成文字部分。
    """
    start_text = str(start or "").strip()
    end_text = str(end or "").strip() or start_text
    if not start_text:
        raise ValueError("Missing required field(s): start")

    analyze_root = _get_analyze_root(topic_identifier, start_text, end_text)
    folder = analyze_root.name
    report_dir = ensure_bucket("reports", topic_identifier, folder)
    cache_path = report_dir / REPORT_CACHE_FILENAME

    if cache_path.exists() and not regenerate:
        try:
            cached = _load_json(cache_path)
            if isinstance(cached, dict):
                cache_version = (
                    cached.get("meta", {}).get("cache_version")
                    if isinstance(cached.get("meta"), dict)
                    else None
                )
                if cache_version == REPORT_CACHE_VERSION:
                    return cached
        except Exception:
            pass

    payload = _build_report_payload(
        topic_identifier=topic_identifier,
        topic_label=str(topic_label or topic_identifier),
        start=start_text,
        end=end_text,
        analyze_root=analyze_root,
    )
    try:
        with cache_path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return payload
