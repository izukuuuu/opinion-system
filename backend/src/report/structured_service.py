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
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from ..utils.ai import call_langchain_chat, call_langchain_with_tools
from ..utils.logging.logging import log_module_start, log_success, setup_logger
from ..utils.setting.paths import bucket, ensure_bucket, get_data_root
from .knowledge_loader import load_report_knowledge
from .skills import load_report_skill_context
from .tools import REPORT_ANALYSIS_TOOLS
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
    build_section_agent_analysis_prompt,
    build_section_agent_system_prompt,
    build_bertopic_insight_prompt,
    build_bertopic_temporal_narrative_prompt,
    build_interpretation_prompt,
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
REPORT_CACHE_VERSION = 7

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


def _normalize_bertopic_temporal_series(rows: Any) -> List[Dict[str, Any]]:
    if not isinstance(rows, list):
        return []

    series_rows: List[Dict[str, Any]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or item.get("name") or "").strip()
        if not title:
            continue
        raw_points = item.get("points")
        if not isinstance(raw_points, list):
            continue
        points: List[Dict[str, Any]] = []
        for point in raw_points:
            if not isinstance(point, dict):
                continue
            date_text = _extract_date_text(point.get("date"))
            if not date_text:
                continue
            count = _parse_int(point.get("count") or point.get("value"))
            if count <= 0:
                continue
            points.append(
                {
                    "date": date_text,
                    "label": str(point.get("label") or _format_label_date(date_text)),
                    "count": count,
                }
            )
        if not points:
            continue
        points.sort(key=lambda point: _parse_date_value(point.get("date") or "") or datetime.min)
        total_count = _parse_int(item.get("total_count"))
        if total_count <= 0:
            total_count = sum(point["count"] for point in points)
        series_rows.append(
            {
                "name": str(item.get("name") or title).strip() or title,
                "title": title,
                "description": str(item.get("description") or "").strip(),
                "total_count": total_count,
                "original_topics": [
                    str(topic).strip()
                    for topic in (item.get("original_topics") or [])
                    if str(topic or "").strip()
                ],
                "points": points,
            }
        )

    series_rows.sort(key=lambda item: item.get("total_count", 0), reverse=True)
    return series_rows


def _build_time_nodes_from_series(series_rows: List[Dict[str, Any]], aggregation: str) -> List[Dict[str, Any]]:
    node_counts: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for item in series_rows:
        theme_name = str(item.get("title") or item.get("name") or "").strip()
        if not theme_name:
            continue
        points = item.get("points")
        if not isinstance(points, list):
            continue
        for point in points:
            if not isinstance(point, dict):
                continue
            date_text = _extract_date_text(point.get("date"))
            count = _parse_int(point.get("count") or point.get("value"))
            if not date_text or count <= 0:
                continue
            node_counts[date_text][theme_name] += count

    nodes: List[Dict[str, Any]] = []
    for date_text in sorted(node_counts.keys(), key=lambda item: _parse_date_value(item) or datetime.min):
        theme_rows = sorted(
            [{"name": name, "value": value} for name, value in node_counts[date_text].items() if value > 0],
            key=lambda item: item["value"],
            reverse=True,
        )
        if not theme_rows:
            continue
        total = sum(item["value"] for item in theme_rows)
        top_theme = theme_rows[0]
        nodes.append(
            {
                "date": date_text,
                "label": _format_label_date(date_text),
                "total": total,
                "topTheme": top_theme["name"],
                "topValue": top_theme["value"],
                "themes": theme_rows,
                "aggregation": aggregation,
            }
        )
    return nodes


def _build_bertopic_temporal_series_from_nodes(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    series_points: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for node in nodes:
        date_text = _extract_date_text(node.get("date"))
        if not date_text:
            continue
        label = str(node.get("label") or _format_label_date(date_text))
        for theme in (node.get("themes") or []):
            if not isinstance(theme, dict):
                continue
            theme_name = str(theme.get("name") or "").strip()
            value = _parse_int(theme.get("value"))
            if not theme_name or value <= 0:
                continue
            series_points[theme_name].append(
                {
                    "date": date_text,
                    "label": label,
                    "count": value,
                }
            )

    series_rows: List[Dict[str, Any]] = []
    for theme_name, points in series_points.items():
        points.sort(key=lambda point: _parse_date_value(point.get("date") or "") or datetime.min)
        total_count = sum(point.get("count", 0) for point in points)
        if total_count <= 0:
            continue
        series_rows.append(
            {
                "name": theme_name,
                "title": theme_name,
                "description": "",
                "total_count": total_count,
                "original_topics": [],
                "points": points,
            }
        )
    series_rows.sort(key=lambda item: item.get("total_count", 0), reverse=True)
    return series_rows


def _build_bertopic_temporal_heatmap(series_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not series_rows:
        return {"dates": [], "dateLabels": [], "themes": [], "matrix": [], "max": 0}

    date_labels: Dict[str, str] = {}
    date_set = set()
    for item in series_rows:
        for point in item.get("points") or []:
            date_text = _extract_date_text(point.get("date"))
            if not date_text:
                continue
            date_set.add(date_text)
            date_labels[date_text] = str(point.get("label") or _format_label_date(date_text))

    dates = sorted(date_set, key=lambda item: _parse_date_value(item) or datetime.min)
    themes = [str(item.get("title") or item.get("name") or "").strip() for item in series_rows]
    matrix: List[List[int]] = []
    max_value = 0
    for item in series_rows:
        point_map = {
            _extract_date_text(point.get("date")): _parse_int(point.get("count"))
            for point in (item.get("points") or [])
            if isinstance(point, dict)
        }
        row = [point_map.get(date_text, 0) for date_text in dates]
        max_value = max(max_value, max(row) if row else 0)
        matrix.append(row)

    return {
        "dates": dates,
        "dateLabels": [date_labels.get(date_text, date_text) for date_text in dates],
        "themes": themes,
        "matrix": matrix,
        "max": max_value,
    }


def _build_bertopic_temporal_hotspots(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    hotspots = [
        {
            "date": item.get("date"),
            "label": item.get("label"),
            "total": _parse_int(item.get("total")),
            "topTheme": str(item.get("topTheme") or "").strip(),
            "topValue": _parse_int(item.get("topValue")),
            "dominance": round(
                _parse_int(item.get("topValue")) / max(1, _parse_int(item.get("total"))),
                4,
            ),
        }
        for item in nodes
        if isinstance(item, dict)
    ]
    hotspots.sort(key=lambda item: _parse_int(item.get("total")), reverse=True)
    return hotspots[:12]


def _build_standardized_bertopic_temporal_context(temporal_payload: Any) -> Dict[str, Any]:
    if not isinstance(temporal_payload, dict):
        return {
            "overview": {},
            "meta": {},
            "time_nodes": [],
            "series": [],
            "raw_series": [],
            "llm_series": [],
            "heatmap": {},
            "hotspots": [],
            "leading_themes": [],
            "series_source": "",
        }

    overview = temporal_payload.get("overview") if isinstance(temporal_payload.get("overview"), dict) else {}
    meta = temporal_payload.get("meta") if isinstance(temporal_payload.get("meta"), dict) else {}
    nodes, _, _ = _extract_temporal_time_context(temporal_payload)

    llm_payload = temporal_payload.get("llm_clusters") if isinstance(temporal_payload.get("llm_clusters"), dict) else {}
    raw_payload = temporal_payload.get("raw_topics") if isinstance(temporal_payload.get("raw_topics"), dict) else {}
    llm_series = _normalize_bertopic_temporal_series(llm_payload.get("series"))
    raw_series = _normalize_bertopic_temporal_series(raw_payload.get("series"))

    series_source = ""
    series_rows: List[Dict[str, Any]] = []
    if llm_series:
        series_rows = llm_series
        series_source = "llm_clusters"
    elif raw_series:
        series_rows = raw_series
        series_source = "raw_topics"
    elif nodes:
        series_rows = _build_bertopic_temporal_series_from_nodes(nodes)
        series_source = "time_nodes"

    if not nodes and series_rows:
        aggregation = str(overview.get("aggregation") or meta.get("aggregation") or "day").strip() or "day"
        nodes = _build_time_nodes_from_series(series_rows, aggregation)

    heatmap = _build_bertopic_temporal_heatmap(series_rows)
    hotspots = _build_bertopic_temporal_hotspots(nodes)
    leading_themes = [
        str(item.get("title") or item.get("name") or "").strip()
        for item in series_rows[:5]
        if str(item.get("title") or item.get("name") or "").strip()
    ]

    return {
        "overview": dict(overview or {}),
        "meta": dict(meta or {}),
        "time_nodes": nodes,
        "series": series_rows,
        "raw_series": raw_series,
        "llm_series": llm_series,
        "heatmap": heatmap,
        "hotspots": hotspots,
        "leading_themes": leading_themes,
        "series_source": series_source,
    }


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
        return {
            "themes": [],
            "time_nodes": [],
            "series": [],
            "raw_series": [],
            "llm_series": [],
            "overview": {},
            "heatmap": {},
            "hotspots": [],
            "leading_themes": [],
            "meta": {"source": ""},
        }

    summary_payload = _load_json_safely(topic_root / BERTOPIC_FILE_MAP["summary"])
    cluster_payload = _load_json_safely(topic_root / BERTOPIC_FILE_MAP["llm_clusters"])
    keyword_payload = _load_json_safely(topic_root / BERTOPIC_FILE_MAP["llm_keywords"])
    temporal_payload = _load_json_safely(topic_root / BERTOPIC_FILE_MAP["temporal"])

    themes, cluster_by_topic_name, cluster_by_topic_id = _parse_bertopic_themes(cluster_payload, keyword_payload)
    cluster_doc_total = sum(_parse_int(item.get("value")) for item in themes)
    temporal_context = _build_standardized_bertopic_temporal_context(temporal_payload)
    temporal_nodes = temporal_context.get("time_nodes") if isinstance(temporal_context, dict) else []
    temporal_series = temporal_context.get("series") if isinstance(temporal_context, dict) else []
    temporal_heatmap = temporal_context.get("heatmap") if isinstance(temporal_context, dict) else {}
    temporal_hotspots = temporal_context.get("hotspots") if isinstance(temporal_context, dict) else []
    temporal_leading_themes = temporal_context.get("leading_themes") if isinstance(temporal_context, dict) else []
    temporal_meta = temporal_context.get("meta") if isinstance(temporal_context, dict) else {}
    temporal_overview = temporal_context.get("overview") if isinstance(temporal_context, dict) else {}
    temporal_series_source = str(
        temporal_context.get("series_source") if isinstance(temporal_context, dict) else ""
    ).strip()
    if temporal_nodes or temporal_series:
        temporal_docs = _parse_int(temporal_meta.get("temporal_documents"))
        mapped_docs = _parse_int(temporal_meta.get("llm_mapped_documents"))
        if mapped_docs <= 0:
            mapped_docs = sum(_parse_int(item.get("total")) for item in temporal_nodes)
        coverage = float(temporal_meta.get("llm_coverage_rate") or 0.0)
        if coverage <= 0 and temporal_docs > 0:
            coverage = mapped_docs / max(1, temporal_docs)
        overview = dict(temporal_overview or {})
        if temporal_nodes:
            overview.setdefault("rangeStart", str(temporal_nodes[0].get("date") or "").strip())
            overview.setdefault("rangeEnd", str(temporal_nodes[-1].get("date") or "").strip())
        overview.setdefault("bucketCount", len(temporal_nodes))
        overview.setdefault("days", overview.get("bucketCount") or len(temporal_nodes))
        overview.setdefault("totalMappedDocs", mapped_docs)
        overview.setdefault("totalTemporalDocs", temporal_docs)
        return {
            "themes": themes,
            "time_nodes": temporal_nodes,
            "series": temporal_series if isinstance(temporal_series, list) else [],
            "raw_series": temporal_context.get("raw_series") if isinstance(temporal_context, dict) else [],
            "llm_series": temporal_context.get("llm_series") if isinstance(temporal_context, dict) else [],
            "overview": overview,
            "heatmap": temporal_heatmap if isinstance(temporal_heatmap, dict) else {},
            "hotspots": temporal_hotspots if isinstance(temporal_hotspots, list) else [],
            "leading_themes": temporal_leading_themes if isinstance(temporal_leading_themes, list) else [],
            "meta": {
                "source": str(topic_root),
                "time_source": "temporal",
                "series_source": temporal_series_source or "temporal",
                "cluster_count": len(themes),
                "cluster_doc_total": cluster_doc_total,
                "time_node_count": len(temporal_nodes),
                "series_count": len(temporal_series) if isinstance(temporal_series, list) else 0,
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
    legacy_series = _build_bertopic_temporal_series_from_nodes(time_nodes)
    legacy_heatmap = _build_bertopic_temporal_heatmap(legacy_series)
    legacy_hotspots = _build_bertopic_temporal_hotspots(time_nodes)
    legacy_leading_themes = [
        str(item.get("title") or item.get("name") or "").strip()
        for item in legacy_series[:5]
        if str(item.get("title") or item.get("name") or "").strip()
    ]
    legacy_overview = {
        "mode": "legacy_doc_mapping",
        "aggregation": "day",
        "aggregationLabel": "日",
        "description": "基于文档日期回填生成的主题时序估计。",
        "bucketCount": len(time_nodes),
        "days": len(time_nodes),
        "rangeStart": str(time_nodes[0].get("date") or "").strip() if time_nodes else "",
        "rangeEnd": str(time_nodes[-1].get("date") or "").strip() if time_nodes else "",
        "totalMappedDocs": _parse_int(time_node_stats.get("mapped_docs")),
        "totalTemporalDocs": _parse_int(time_node_stats.get("dated_docs")),
    }

    return {
        "themes": themes,
        "time_nodes": time_nodes,
        "series": legacy_series,
        "raw_series": legacy_series,
        "llm_series": [],
        "overview": legacy_overview,
        "heatmap": legacy_heatmap,
        "hotspots": legacy_hotspots,
        "leading_themes": legacy_leading_themes,
        "meta": {
            "source": str(topic_root),
            "time_source": "legacy_doc_mapping",
            "series_source": "legacy_doc_mapping",
            "cluster_count": len(themes),
            "cluster_doc_total": cluster_doc_total,
            "topicid_cluster_count": len(topicid_cluster_map),
            "time_node_count": len(time_nodes),
            "series_count": len(legacy_series),
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


def _infer_event_type(topic_label: str) -> str:
    text = str(topic_label or "").strip()
    mapping = [
        ("品牌危机", ["品牌", "企业", "公司", "产品", "营销", "舆情危机"]),
        ("突发事故", ["事故", "爆炸", "燃爆", "伤亡", "坠落", "安全"]),
        ("公共政策", ["政策", "规定", "条例", "办法", "改革", "新规"]),
        ("教育舆情", ["教育", "学校", "高校", "高考", "教师", "校园"]),
        ("餐饮消费", ["餐饮", "预制菜", "食品", "外卖", "门店", "火锅"]),
        ("汽车舆情", ["汽车", "车企", "新能源", "智驾", "充电宝"]),
        ("平台争议", ["平台", "社交媒体", "微博", "抖音", "小红书", "电商"]),
    ]
    for label, keywords in mapping:
        if any(keyword in text for keyword in keywords):
            return label
    return "社会事件"


def _infer_domain(topic_label: str) -> str:
    text = str(topic_label or "").strip()
    mapping = [
        ("教育", ["教育", "学校", "高校", "高考", "校园"]),
        ("汽车", ["汽车", "车企", "新能源", "智驾", "SU7"]),
        ("餐饮", ["餐饮", "预制菜", "火锅", "外卖", "门店"]),
        ("互联网", ["平台", "微博", "抖音", "小红书", "APP", "应用"]),
        ("消费", ["品牌", "产品", "消费者", "售后"]),
        ("公共治理", ["政策", "监管", "执法", "通报", "回应"]),
    ]
    for label, keywords in mapping:
        if any(keyword in text for keyword in keywords):
            return label
    return ""


def _infer_stage_from_timeline(
    timeline: List[Dict[str, Any]],
    sentiment: Dict[str, int],
) -> str:
    if not timeline:
        return "观察期"
    values = [_parse_int(item.get("value")) for item in timeline]
    if not values:
        return "观察期"
    peak_value = max(values)
    peak_index = values.index(peak_value)
    last_value = values[-1]
    sentiment_total = max(1, sum(max(0, _parse_int(value)) for value in sentiment.values()))
    negative_rate = sentiment.get("negative", 0) / sentiment_total

    if len(values) == 1:
        return "爆发期" if peak_value > 0 else "观察期"
    if peak_index >= len(values) - 1:
        return "爆发期"
    if last_value <= peak_value * 0.35:
        return "回落期"
    if negative_rate >= 0.38:
        return "对抗期"
    return "扩散期"


def _select_theory_names(
    *,
    timeline: List[Dict[str, Any]],
    channels: List[Dict[str, Any]],
    sentiment: Dict[str, int],
    content_split: Dict[str, int],
    knowledge_context: Dict[str, Any],
) -> List[str]:
    theory_hints = [
        str(item).strip()
        for item in (knowledge_context.get("theoryHints") or [])
        if str(item or "").strip()
    ]
    available = set(theory_hints)
    if not available:
        available = {
            "生命周期规律",
            "议程设置规律",
            "沉默螺旋规律",
            "框架理论",
            "风险传播理论",
            "社会燃烧规律",
        }

    sentiment_total = max(1, sum(max(0, _parse_int(value)) for value in sentiment.values()))
    negative_rate = sentiment.get("negative", 0) / sentiment_total
    content_total = max(1, content_split.get("factual", 0) + content_split.get("opinion", 0))
    opinion_ratio = content_split.get("opinion", 0) / content_total

    candidates: List[str] = []
    if len(timeline) >= 3:
        candidates.append("生命周期规律")
    if channels:
        candidates.append("议程设置规律")
    if negative_rate >= 0.28:
        candidates.append("风险传播理论")
    if opinion_ratio >= 0.45:
        candidates.append("框架理论")
    if negative_rate >= 0.42:
        candidates.append("沉默螺旋规律")

    picked: List[str] = []
    for name in candidates:
        if name in available and name not in picked:
            picked.append(name)
        if len(picked) >= 3:
            break
    return picked


def _build_fallback_deep_analysis(
    *,
    topic_label: str,
    metrics: Dict[str, Any],
    channels: List[Dict[str, Any]],
    timeline: List[Dict[str, Any]],
    sentiment: Dict[str, int],
    content_split: Dict[str, int],
    keywords: List[Dict[str, Any]],
    themes: List[Dict[str, Any]],
    main_finding: str,
    knowledge_context: Dict[str, Any],
) -> Dict[str, Any]:
    top_channels = "、".join(
        f"{str(item.get('name') or '').strip()}({ _parse_int(item.get('value')) })"
        for item in channels[:3]
        if str(item.get("name") or "").strip()
    ) or "暂无明显头部渠道"
    top_keywords = "、".join(
        str(item.get("term") or "").strip()
        for item in keywords[:5]
        if str(item.get("term") or "").strip()
    ) or "暂无高频关键词"
    top_themes = "、".join(
        str(item.get("name") or "").strip()
        for item in themes[:4]
        if str(item.get("name") or "").strip()
    ) or "暂无稳定主题"

    stage = _infer_stage_from_timeline(timeline, sentiment)
    event_type = _infer_event_type(topic_label)
    domain = _infer_domain(topic_label)

    peak = metrics.get("peak") if isinstance(metrics.get("peak"), dict) else {}
    peak_date = str(peak.get("date") or "峰值日").strip()
    peak_value = _parse_int(peak.get("value"))
    total_volume = _parse_int(metrics.get("totalVolume"))

    sentiment_total = max(1, sentiment.get("positive", 0) + sentiment.get("neutral", 0) + sentiment.get("negative", 0))
    negative_rate = sentiment.get("negative", 0) / sentiment_total
    content_total = max(1, content_split.get("factual", 0) + content_split.get("opinion", 0))
    opinion_ratio = content_split.get("opinion", 0) / content_total

    narrative_summary = (
        f"{topic_label}在本轮监测周期内呈现明显的阶段性传播特征，"
        f"整体处于{stage}。全周期累计声量约 {total_volume}，"
        f"并在 {peak_date} 达到峰值 {peak_value}。"
        f"渠道关注主要集中在 {top_channels}，讨论焦点围绕 {top_themes} 展开。"
    )
    if main_finding:
        narrative_summary += f" 综合既有分析结果，核心判断为：{main_finding}"
    else:
        narrative_summary += f" 从关键词与主题看，核心争议集中在 {top_keywords} 等议题。"

    key_events: List[str] = []
    if timeline:
        first_item = timeline[0]
        peak_item = max(timeline, key=lambda item: item.get("value", 0))
        last_item = timeline[-1]
        key_events.append(
            f"{str(first_item.get('date') or '').strip()}进入观察窗口，相关讨论开始持续出现。"
        )
        key_events.append(
            f"{str(peak_item.get('date') or '').strip()}达到声量峰值 { _parse_int(peak_item.get('value')) }，成为传播拐点。"
        )
        if str(last_item.get("date") or "").strip() != str(peak_item.get("date") or "").strip():
            key_events.append(
                f"{str(last_item.get('date') or '').strip()}后讨论进入{stage}，需关注长尾扩散与次生议题。"
            )

    key_risks: List[str] = []
    if negative_rate >= 0.3:
        key_risks.append(
            f"负向情绪占比约 {round(negative_rate * 100, 1)}%，若回应节奏失衡，可能进一步放大对立情绪。"
        )
    if opinion_ratio >= 0.45:
        key_risks.append(
            f"观点类内容占比约 {round(opinion_ratio * 100, 1)}%，说明讨论已不止于事实复述，存在议题泛化风险。"
        )
    if channels and len(channels) >= 1:
        dominant_channel = channels[0]
        dominant_ratio = _parse_int(dominant_channel.get("value")) / max(1, total_volume)
        if dominant_ratio >= 0.45:
            key_risks.append(
                f"{str(dominant_channel.get('name') or '').strip()}承载主要声量，单平台情绪波动可能显著改变整体走势。"
            )
    if not key_risks:
        key_risks.append("当前主要风险来自热点切换后的次生议题外溢，需持续跟踪话题迁移。")

    indicator_dimensions = ["count", "timeline", "channel", "sentiment", "theme"]
    if opinion_ratio >= 0.4:
        indicator_dimensions.append("frame")
    indicator_dimensions = indicator_dimensions[:6]

    theory_names = _select_theory_names(
        timeline=timeline,
        channels=channels,
        sentiment=sentiment,
        content_split=content_split,
        knowledge_context=knowledge_context,
    )

    return {
        "narrativeSummary": narrative_summary.strip(),
        "keyEvents": key_events[:5],
        "keyRisks": key_risks[:5],
        "eventType": event_type,
        "domain": domain,
        "stage": stage,
        "indicatorDimensions": indicator_dimensions,
        "theoryNames": theory_names[:3],
    }


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


def _build_fallback_bertopic_temporal_narrative(
    *,
    topic_label: str,
    start: str,
    end: str,
    bertopic_overview: Dict[str, Any],
    bertopic_meta: Dict[str, Any],
    bertopic_nodes: List[Dict[str, Any]],
    bertopic_series: List[Dict[str, Any]],
    bertopic_hotspots: List[Dict[str, Any]],
    leading_themes: List[str],
) -> Dict[str, Any]:
    if not bertopic_nodes and not bertopic_series:
        return {
            "summary": "暂无可用的 BERTopic 时序结果，报告当前无法给出稳定的主题迁移解读。",
            "shiftSignals": [],
            "watchpoints": ["请先完成 BERTopic 时序挖掘，并确认结果目录中存在主题时间趋势输出。"],
        }

    coverage_start = str(
        bertopic_overview.get("rangeStart")
        or (bertopic_nodes[0].get("date") if bertopic_nodes else "")
        or ""
    ).strip()
    coverage_end = str(
        bertopic_overview.get("rangeEnd")
        or (bertopic_nodes[-1].get("date") if bertopic_nodes else "")
        or ""
    ).strip()
    bucket_count = _parse_int(
        bertopic_overview.get("bucketCount") or bertopic_overview.get("days") or len(bertopic_nodes)
    )
    mapped_docs = _parse_int(
        bertopic_overview.get("totalMappedDocs")
        or bertopic_meta.get("mapped_docs")
        or bertopic_meta.get("mappedDocs")
        or sum(_parse_int(item.get("total")) for item in bertopic_nodes)
    )
    dated_docs = _parse_int(
        bertopic_overview.get("totalTemporalDocs")
        or bertopic_meta.get("dated_docs")
        or bertopic_meta.get("datedDocs")
    )
    try:
        coverage_rate = float(
            bertopic_meta.get("coverage_rate")
            or bertopic_meta.get("coverageRate")
            or 0.0
        )
    except Exception:
        coverage_rate = 0.0

    top_theme_names = [str(item).strip() for item in leading_themes if str(item or "").strip()][:3]
    if not top_theme_names and bertopic_series:
        top_theme_names = [
            str(item.get("title") or item.get("name") or "").strip()
            for item in bertopic_series[:3]
            if str(item.get("title") or item.get("name") or "").strip()
        ]
    top_theme_text = "、".join(top_theme_names) if top_theme_names else "暂无稳定主导主题"

    switches: List[str] = []
    previous_theme = ""
    for node in bertopic_nodes:
        current_theme = str(node.get("topTheme") or "").strip()
        if not current_theme:
            continue
        if previous_theme and previous_theme != current_theme:
            switches.append(
                f"{str(node.get('label') or node.get('date') or '').strip()} 由 {previous_theme} 切换至 {current_theme}"
            )
        previous_theme = current_theme

    hotspot_signals = [
        (
            f"{str(item.get('label') or item.get('date') or '').strip()} 讨论量 {_parse_int(item.get('total'))}，"
            f"主导主题为 {str(item.get('topTheme') or '').strip()}，占比约 {round(float(item.get('dominance') or 0) * 100, 1)}%"
        )
        for item in bertopic_hotspots[:3]
        if isinstance(item, dict) and str(item.get("topTheme") or "").strip()
    ]
    shift_signals = (switches[:2] + hotspot_signals)[:4]

    series_source = str(
        bertopic_meta.get("series_source") or bertopic_meta.get("seriesSource") or ""
    ).strip()
    source_text = {
        "llm_clusters": "LLM 重组主题",
        "raw_topics": "BERTopic 原始主题",
        "legacy_doc_mapping": "文档日期回填结果",
        "time_nodes": "主导主题节点结果",
    }.get(series_source, "BERTopic 主题时序")

    summary = (
        f"{topic_label} 在 {coverage_start or start} 至 {coverage_end or end} 期间共形成 "
        f"{bucket_count or len(bertopic_nodes)} 个时间桶，映射 {mapped_docs} 条讨论。"
        f"当前报告引用 {source_text} 作为时序主线，主题焦点主要围绕 {top_theme_text} 展开，"
        "讨论热度会在少数关键日期集中抬升，并伴随主导主题切换。"
    )

    watchpoints: List[str] = []
    if coverage_start and coverage_end and (coverage_start > start or coverage_end < end):
        watchpoints.append(
            f"BERTopic 时序覆盖仅到 {coverage_start} 至 {coverage_end}，与报告区间 {start} 至 {end} 不完全一致。"
        )
    if dated_docs > 0 and coverage_rate > 0 and coverage_rate < 0.6:
        watchpoints.append(f"主题时序映射覆盖率仅 {round(coverage_rate * 100, 1)}%，需注意未映射文档对结论的影响。")
    if bucket_count > 0 and bucket_count < 3:
        watchpoints.append("时间桶数量过少，当前更适合做节点说明，不适合过度解读长期迁移。")
    if bertopic_hotspots:
        strongest = max(
            (float(item.get("dominance") or 0.0) for item in bertopic_hotspots if isinstance(item, dict)),
            default=0.0,
        )
        if strongest >= 0.75:
            watchpoints.append("存在单主题占比极高的爆发窗口，解读时需区分事件峰值与长期主线。")
    if not watchpoints:
        watchpoints.append("当前覆盖范围与主题集中度整体可用，但仍建议结合原始热点事件做交叉核验。")

    return {
        "summary": summary,
        "shiftSignals": shift_signals,
        "watchpoints": watchpoints[:3],
    }


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


def _truncate_inline_text(value: str, max_chars: int) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "..."


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
    log_module_start(
        logger,
        "ReportStructured",
        f"生成结构化报告 {topic_label or topic_identifier} {date_folder}",
    )
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


def _call_langchain_json(
    user_prompt: str,
    *,
    max_tokens: int = 1800,
    model_role: Optional[str] = None,
    system_prompt: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    raw_text = _safe_async_call(
        call_langchain_chat(
            [
                {"role": "system", "content": str(system_prompt or REPORT_SYSTEM_PROMPT)},
                {"role": "user", "content": user_prompt},
            ],
            task="report",
            model_role=model_role,
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


def _call_langchain_json_with_tools(
    user_prompt: str,
    *,
    tools: List[Any],
    max_tokens: int = 1800,
    model_role: Optional[str] = None,
    system_prompt: Optional[str] = None,
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    result = _safe_async_call(
        call_langchain_with_tools(
            [
                {"role": "system", "content": str(system_prompt or REPORT_SYSTEM_PROMPT)},
                {"role": "user", "content": user_prompt},
            ],
            tools=tools,
            task="report",
            model_role=model_role,
            temperature=0.2,
            max_tokens=max_tokens,
        )
    )
    if not isinstance(result, dict):
        return None, {"tool_calls": [], "tool_results": [], "content": ""}

    raw_text = str(result.get("content") or "").strip()
    if not raw_text:
        return None, result
    candidate = _extract_json_text(raw_text)
    if not candidate:
        return None, result
    try:
        payload = json.loads(candidate)
    except Exception:
        return None, result
    if not isinstance(payload, dict):
        return None, result
    return payload, result


@dataclass
class SectionAgentSpec:
    name: str
    focus: str
    prompt_builder: Callable[[Dict[str, Any]], str]
    model_role: Optional[str] = None
    max_tokens: int = 1800
    tools: Optional[List[Any]] = None
    analysis_goal: str = ""
    analysis_max_tokens: int = 900
    analysis_model_role: Optional[str] = None


def _normalize_section_agent_analysis(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    evidence = payload.get("evidence")
    watchpoints = payload.get("watchpoints")
    normalized = {
        "judgement": str(payload.get("judgement") or "").strip(),
        "evidence": [
            str(item).strip()
            for item in (evidence or [])
            if str(item or "").strip()
        ][:4]
        if isinstance(evidence, list)
        else [],
        "watchpoints": [
            str(item).strip()
            for item in (watchpoints or [])
            if str(item or "").strip()
        ][:3]
        if isinstance(watchpoints, list)
        else [],
        "angle": str(payload.get("angle") or "").strip(),
    }
    if not any(
        [
            normalized["judgement"],
            normalized["evidence"],
            normalized["watchpoints"],
            normalized["angle"],
        ]
    ):
        return {}
    return normalized


def _build_tool_results_preview(results: Any) -> List[Dict[str, Any]]:
    if not isinstance(results, list):
        return []
    previews: List[Dict[str, Any]] = []
    for item in results:
        if not isinstance(item, dict):
            continue
        previews.append(
            {
                "name": str(item.get("name") or "").strip(),
                "id": str(item.get("id") or "").strip(),
                "output_preview": _truncate_text(str(item.get("output") or "").strip(), 600),
            }
        )
    return previews


def _run_section_agent(
    spec: SectionAgentSpec,
    facts: Dict[str, Any],
) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    section_facts = dict(facts or {})
    system_prompt = build_section_agent_system_prompt(spec.name, spec.focus)
    analysis_payload: Dict[str, Any] = {}
    analysis_source = "none"
    if spec.analysis_goal:
        analysis_payload = _normalize_section_agent_analysis(
            _call_langchain_json(
                build_section_agent_analysis_prompt(spec.name, spec.analysis_goal, section_facts),
                max_tokens=spec.analysis_max_tokens,
                model_role=spec.analysis_model_role or spec.model_role,
                system_prompt=system_prompt,
            )
        )
        if analysis_payload:
            analysis_source = "llm"
            section_facts["section_agent_analysis"] = analysis_payload

    tool_trace: Dict[str, Any] = {"tool_calls": [], "tool_results": [], "content": ""}
    if spec.tools:
        payload, tool_trace = _call_langchain_json_with_tools(
            spec.prompt_builder(section_facts),
            tools=spec.tools,
            max_tokens=spec.max_tokens,
            model_role=spec.model_role,
            system_prompt=system_prompt,
        )
    else:
        payload = _call_langchain_json(
            spec.prompt_builder(section_facts),
            max_tokens=spec.max_tokens,
            model_role=spec.model_role,
            system_prompt=system_prompt,
        )

    trace = {
        "section": spec.name,
        "focus": spec.focus,
        "source": "llm" if isinstance(payload, dict) else "fallback",
        "model_role": spec.model_role or "",
        "used_tools": bool(spec.tools),
        "analysis_source": analysis_source,
        "analysis": analysis_payload,
        "tool_call_count": len(tool_trace.get("tool_calls") or []),
        "tool_calls": tool_trace.get("tool_calls") or [],
        "tool_results": _build_tool_results_preview(tool_trace.get("tool_results")),
        "model": tool_trace.get("model") or "",
        "provider": tool_trace.get("provider") or "",
    }
    return payload, trace


def _merge_deep_analysis_payload(
    fallback: Dict[str, Any],
    payload: Any,
) -> Tuple[Dict[str, Any], str]:
    merged = dict(fallback or {})
    source = "fallback"
    if not isinstance(payload, dict):
        return merged, source

    narrative_summary_candidate = str(payload.get("narrativeSummary") or "").strip()
    event_type_candidate = str(payload.get("eventType") or "").strip()
    domain_candidate = str(payload.get("domain") or "").strip()
    stage_candidate = str(payload.get("stage") or "").strip()
    indicator_dimensions_candidate = payload.get("indicatorDimensions")
    theory_names_candidate = payload.get("theoryNames")
    key_events_candidate = payload.get("keyEvents")
    key_risks_candidate = payload.get("keyRisks")

    if narrative_summary_candidate:
        merged["narrativeSummary"] = narrative_summary_candidate
        source = "llm"
    if event_type_candidate:
        merged["eventType"] = event_type_candidate
    if domain_candidate:
        merged["domain"] = domain_candidate
    if stage_candidate:
        merged["stage"] = stage_candidate
    if isinstance(key_events_candidate, list):
        parsed_key_events = [str(item).strip() for item in key_events_candidate if str(item or "").strip()]
        if parsed_key_events:
            merged["keyEvents"] = parsed_key_events[:5]
            source = "llm"
    if isinstance(key_risks_candidate, list):
        parsed_key_risks = [str(item).strip() for item in key_risks_candidate if str(item or "").strip()]
        if parsed_key_risks:
            merged["keyRisks"] = parsed_key_risks[:5]
            source = "llm"
    if isinstance(indicator_dimensions_candidate, list):
        parsed_dimensions = [str(item).strip() for item in indicator_dimensions_candidate if str(item or "").strip()]
        if parsed_dimensions:
            merged["indicatorDimensions"] = parsed_dimensions[:6]
    if isinstance(theory_names_candidate, list):
        parsed_theories = [str(item).strip() for item in theory_names_candidate if str(item or "").strip()]
        if parsed_theories:
            merged["theoryNames"] = parsed_theories[:3]
    return merged, source


def _extract_bertopic_insight_from_payload(payload: Any) -> Optional[str]:
    if not isinstance(payload, dict):
        return None
    candidate = str(
        payload.get("insight_markdown")
        or payload.get("insight")
        or payload.get("summary")
        or ""
    ).strip()
    return candidate or None


def _merge_bertopic_temporal_narrative_payload(
    fallback: Dict[str, Any],
    payload: Any,
) -> Tuple[Dict[str, Any], str]:
    merged = dict(fallback or {})
    source = "fallback"
    if not isinstance(payload, dict):
        return merged, source

    summary_candidate = str(payload.get("summary") or "").strip()
    shift_signals_candidate = payload.get("shiftSignals")
    watchpoints_candidate = payload.get("watchpoints")
    if summary_candidate:
        merged["summary"] = summary_candidate
        source = "llm"
    if isinstance(shift_signals_candidate, list):
        parsed_shift_signals = [str(item).strip() for item in shift_signals_candidate if str(item or "").strip()]
        if parsed_shift_signals:
            merged["shiftSignals"] = parsed_shift_signals[:4]
            source = "llm"
    if isinstance(watchpoints_candidate, list):
        parsed_watchpoints = [str(item).strip() for item in watchpoints_candidate if str(item or "").strip()]
        if parsed_watchpoints:
            merged["watchpoints"] = parsed_watchpoints[:3]
            source = "llm"
    return merged, source


def _extract_title_subtitle_from_payload(payload: Any) -> Tuple[str, str]:
    if not isinstance(payload, dict):
        return "", ""
    return (
        str(payload.get("title") or "").strip(),
        str(payload.get("subtitle") or "").strip(),
    )


def _extract_stage_notes_from_payload(payload: Any) -> List[Dict[str, Any]]:
    if not isinstance(payload, dict) or not isinstance(payload.get("stageNotes"), list):
        return []
    parsed_notes = []
    for idx, item in enumerate(payload.get("stageNotes") or []):
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
    return parsed_notes[:3]


def _extract_insights_from_payload(payload: Any) -> Tuple[List[str], List[Dict[str, Any]]]:
    parsed_points: List[str] = []
    parsed_cards: List[Dict[str, Any]] = []
    if not isinstance(payload, dict):
        return parsed_points, parsed_cards

    points_payload = payload.get("highlight_points")
    if isinstance(points_payload, list):
        parsed_points = [str(item).strip() for item in points_payload if str(item or "").strip()][:4]

    cards_payload = payload.get("insights")
    if isinstance(cards_payload, list):
        for item in cards_payload:
            if not isinstance(item, dict):
                continue
            title_value = str(item.get("title") or "").strip()
            headline_value = str(item.get("headline") or "").strip()
            points_value = item.get("points")
            if not title_value:
                continue
            points_list: List[str] = []
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
    return parsed_points, parsed_cards[:6]


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
    bertopic_series_from_context = bertopic_context.get("series") if isinstance(bertopic_context, dict) else []
    bertopic_hotspots_from_context = bertopic_context.get("hotspots") if isinstance(bertopic_context, dict) else []
    bertopic_heatmap_from_context = bertopic_context.get("heatmap") if isinstance(bertopic_context, dict) else {}
    bertopic_leading_themes_from_context = (
        bertopic_context.get("leading_themes") if isinstance(bertopic_context, dict) else []
    )
    bertopic_meta_from_context = bertopic_context.get("meta") if isinstance(bertopic_context, dict) else {}
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

    bertopic_nodes_payload: List[Dict[str, Any]] = []
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
    bertopic_series_payload: List[Dict[str, Any]] = []
    if isinstance(bertopic_series_from_context, list):
        for item in bertopic_series_from_context:
            if not isinstance(item, dict):
                continue
            theme_name = str(item.get("title") or item.get("name") or "").strip()
            if not theme_name:
                continue
            raw_points = item.get("points")
            if not isinstance(raw_points, list):
                continue
            points = []
            for point in raw_points:
                if not isinstance(point, dict):
                    continue
                date_text = str(point.get("date") or "").strip()
                if not date_text:
                    continue
                points.append(
                    {
                        "date": date_text,
                        "label": str(point.get("label") or _format_label_date(date_text)).strip() or _format_label_date(date_text),
                        "count": _parse_int(point.get("count") or point.get("value")),
                    }
                )
            points = [point for point in points if point["count"] > 0]
            if not points:
                continue
            points.sort(key=lambda point: _parse_date_value(point.get("date") or "") or datetime.min)
            bertopic_series_payload.append(
                {
                    "name": str(item.get("name") or theme_name).strip() or theme_name,
                    "title": theme_name,
                    "description": str(item.get("description") or "").strip(),
                    "totalCount": _parse_int(item.get("total_count") or item.get("totalCount") or sum(point["count"] for point in points)),
                    "originalTopics": [
                        str(topic).strip()
                        for topic in (item.get("original_topics") or item.get("originalTopics") or [])
                        if str(topic or "").strip()
                    ],
                    "points": points,
                }
            )
    bertopic_series_payload.sort(key=lambda item: item.get("totalCount", 0), reverse=True)

    if not bertopic_nodes_payload and bertopic_series_payload:
        aggregation = str(
            bertopic_overview_from_context.get("aggregation")
            if isinstance(bertopic_overview_from_context, dict)
            else ""
        ).strip() or "day"
        bertopic_time_nodes = _build_time_nodes_from_series(bertopic_series_payload, aggregation)
        for item in bertopic_time_nodes:
            if not isinstance(item, dict):
                continue
            node_themes = item.get("themes")
            compact_themes = []
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
                    "date": str(item.get("date") or "").strip(),
                    "label": str(item.get("label") or "").strip(),
                    "total": _parse_int(item.get("total")),
                    "topTheme": str(item.get("topTheme") or "").strip(),
                    "topValue": _parse_int(item.get("topValue")),
                    "dominance": round(
                        _parse_int(item.get("topValue")) / max(1, _parse_int(item.get("total"))),
                        4,
                    ),
                    "themes": compact_themes,
                }
            )
        bertopic_nodes_payload.sort(key=lambda item: _parse_date_value(str(item.get("date") or "")) or datetime.min)

    bertopic_hotspots_payload: List[Dict[str, Any]] = []
    if isinstance(bertopic_hotspots_from_context, list):
        for item in bertopic_hotspots_from_context:
            if not isinstance(item, dict):
                continue
            theme_name = str(item.get("topTheme") or "").strip()
            date_text = str(item.get("date") or "").strip()
            if not theme_name or not date_text:
                continue
            bertopic_hotspots_payload.append(
                {
                    "date": date_text,
                    "label": str(item.get("label") or _format_label_date(date_text)).strip() or _format_label_date(date_text),
                    "total": _parse_int(item.get("total")),
                    "topTheme": theme_name,
                    "topValue": _parse_int(item.get("topValue")),
                    "dominance": round(float(item.get("dominance") or 0.0), 4),
                }
            )
    if not bertopic_hotspots_payload:
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

    bertopic_leading_themes_payload = [
        str(item).strip()
        for item in (bertopic_leading_themes_from_context or [])
        if str(item or "").strip()
    ][:5]
    if not bertopic_leading_themes_payload and bertopic_series_payload:
        bertopic_leading_themes_payload = [
            str(item.get("title") or item.get("name") or "").strip()
            for item in bertopic_series_payload[:5]
            if str(item.get("title") or item.get("name") or "").strip()
        ]
    if not bertopic_leading_themes_payload and bertopic_nodes_payload:
        theme_totals: Dict[str, int] = defaultdict(int)
        for node in bertopic_nodes_payload:
            for theme in (node.get("themes") or []):
                if not isinstance(theme, dict):
                    continue
                theme_name = str(theme.get("name") or "").strip()
                if not theme_name:
                    continue
                theme_totals[theme_name] += _parse_int(theme.get("value"))
        bertopic_leading_themes_payload = [
            name for name, _ in sorted(theme_totals.items(), key=lambda item: item[1], reverse=True)[:5]
        ]

    bertopic_overview = dict(bertopic_overview_from_context or {})
    total_mapped_docs = sum(_parse_int(item.get("total")) for item in bertopic_nodes_payload)
    if not bertopic_overview:
        bertopic_overview = {
            "mode": "legacy_doc_mapping",
            "aggregation": "day",
            "aggregationLabel": "日",
            "description": "基于文档日期回填生成的主题时序估计。",
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
    bertopic_overview.setdefault("rangeStart", str(bertopic_nodes_payload[0].get("date") or "").strip() if bertopic_nodes_payload else "")
    bertopic_overview.setdefault("rangeEnd", str(bertopic_nodes_payload[-1].get("date") or "").strip() if bertopic_nodes_payload else "")
    bertopic_overview.setdefault(
        "totalTemporalDocs",
        _parse_int(
            bertopic_overview.get("totalTemporalDocs")
            or bertopic_meta_from_context.get("dated_docs")
            or bertopic_meta_from_context.get("datedDocs")
        ),
    )

    bertopic_heatmap_payload = bertopic_heatmap_from_context if isinstance(bertopic_heatmap_from_context, dict) else {}
    if not bertopic_heatmap_payload and bertopic_series_payload:
        heatmap_source_rows = [
            {
                "title": item.get("title"),
                "name": item.get("name"),
                "points": item.get("points"),
            }
            for item in bertopic_series_payload
        ]
        bertopic_heatmap_payload = _build_bertopic_temporal_heatmap(heatmap_source_rows)

    try:
        bertopic_coverage_rate = float(
            bertopic_meta_from_context.get("coverage_rate")
            or bertopic_meta_from_context.get("coverageRate")
            or 0.0
        )
    except Exception:
        bertopic_coverage_rate = 0.0
    bertopic_temporal_meta = {
        "source": str(bertopic_meta_from_context.get("source") or "").strip(),
        "timeSource": str(bertopic_meta_from_context.get("time_source") or "").strip(),
        "seriesSource": str(
            bertopic_meta_from_context.get("series_source")
            or bertopic_meta_from_context.get("seriesSource")
            or ""
        ).strip(),
        "clusterCount": _parse_int(bertopic_meta_from_context.get("cluster_count") or bertopic_meta_from_context.get("clusterCount")),
        "clusterDocTotal": _parse_int(
            bertopic_meta_from_context.get("cluster_doc_total") or bertopic_meta_from_context.get("clusterDocTotal")
        ),
        "timeNodeCount": len(bertopic_nodes_payload),
        "seriesCount": len(bertopic_series_payload),
        "mappedDocs": _parse_int(
            bertopic_meta_from_context.get("mapped_docs")
            or bertopic_meta_from_context.get("mappedDocs")
            or total_mapped_docs
        ),
        "datedDocs": _parse_int(
            bertopic_meta_from_context.get("dated_docs")
            or bertopic_meta_from_context.get("datedDocs")
            or bertopic_overview.get("totalTemporalDocs")
        ),
        "coverageRate": round(bertopic_coverage_rate, 4),
        "temporalMeta": bertopic_meta_from_context.get("temporal_meta")
        if isinstance(bertopic_meta_from_context.get("temporal_meta"), dict)
        else {},
    }
    if not bertopic_temporal_meta["seriesSource"]:
        bertopic_temporal_meta["seriesSource"] = bertopic_temporal_meta["timeSource"] or "time_nodes"

    bertopic_temporal_payload = {
        "overview": bertopic_overview,
        "meta": bertopic_temporal_meta,
        "timeNodes": bertopic_nodes_payload,
        "hotspots": bertopic_hotspots_payload,
        "series": bertopic_series_payload,
        "heatmap": bertopic_heatmap_payload,
        "leadingThemes": bertopic_leading_themes_payload,
    }

    metrics = _compute_metrics(channels, timeline, sentiment, content_split)
    main_finding = _load_main_finding(analyze_root)
    legacy_context = _build_legacy_report_context(
        topic_identifier=topic_identifier,
        topic_label=topic_label,
        date_folder=analyze_root.name,
    )
    knowledge_context = load_report_knowledge(topic_label or topic_identifier)
    skill_context = load_report_skill_context(topic_label or topic_identifier)
    methodology_context_text = _truncate_text(str(knowledge_context.get("summary") or ""), 6000)
    reference_snippets = [
        {
            "title": str(item.get("title") or "").strip(),
            "snippet": _truncate_inline_text(str(item.get("snippet") or "").strip(), 280),
        }
        for item in (knowledge_context.get("referenceSnippets") or [])
        if isinstance(item, dict) and str(item.get("snippet") or "").strip()
    ][:4]
    reference_links = [
        {
            "name": str(item.get("name") or "").strip(),
            "url": str(item.get("url") or "").strip(),
            "usage": str(item.get("usage") or "").strip(),
        }
        for item in (knowledge_context.get("referenceLinks") or [])
        if isinstance(item, dict) and str(item.get("name") or "").strip() and str(item.get("url") or "").strip()
    ][:4]
    theory_hints = [
        str(item).strip()
        for item in (knowledge_context.get("theoryHints") or [])
        if str(item or "").strip()
    ][:4]
    dynamic_theories = [
        str(item).strip()
        for item in (knowledge_context.get("dynamicTheories") or [])
        if str(item or "").strip()
    ][:4]
    expert_notes = [
        {
            "title": str(item.get("title") or "").strip(),
            "snippet": _truncate_inline_text(str(item.get("snippet") or "").strip(), 280),
        }
        for item in (knowledge_context.get("expertNotes") or [])
        if isinstance(item, dict) and str(item.get("snippet") or "").strip()
    ][:4]

    section_agents_meta: Dict[str, Any] = {}

    deep_analysis = _build_fallback_deep_analysis(
        topic_label=topic_label,
        metrics=metrics,
        channels=channels,
        timeline=timeline,
        sentiment=sentiment,
        content_split=content_split,
        keywords=keywords,
        themes=themes,
        main_finding=main_finding,
        knowledge_context=knowledge_context,
    )
    deep_analysis_source = "fallback"
    interpretation_facts = {
        "topic": topic_label,
        "time_range": {"start": start, "end": end},
        "metrics": metrics,
        "channels": channels[:8],
        "timeline": [
            {
                "date": str(item.get("raw_date") or item.get("date") or "").strip(),
                "label": str(item.get("date") or "").strip(),
                "value": _parse_int(item.get("value")),
            }
            for item in timeline
        ],
        "sentiment": sentiment,
        "content_split": content_split,
        "keywords": keywords[:10],
        "themes": themes[:8],
        "bertopic_overview": bertopic_overview,
        "bertopic_hotspots": bertopic_hotspots_payload[:8],
        "main_finding": main_finding,
        "legacy_rag_sections": legacy_context.get("sections_text_short", ""),
        "legacy_report_text": legacy_context.get("full_text_short", ""),
        "methodology_context": methodology_context_text,
        "reference_snippets": reference_snippets,
        "reference_links": reference_links,
        "expert_notes": expert_notes,
        "dynamic_theories": dynamic_theories,
        "theory_hints": theory_hints,
        "skill_context": skill_context,
    }
    deep_analysis_payload, deep_analysis_trace = _run_section_agent(
        SectionAgentSpec(
            name="解释与研判",
            focus="负责综合指标、时间线、情感、主题与方法论，输出事件叙事骨架、关键风险和观察维度。",
            prompt_builder=build_interpretation_prompt,
            model_role="tools",
            max_tokens=1800,
            tools=REPORT_ANALYSIS_TOOLS,
        ),
        interpretation_facts,
    )
    if deep_analysis_payload is None:
        deep_analysis_payload = _call_langchain_json(
            build_interpretation_prompt(interpretation_facts),
            max_tokens=1800,
            model_role="tools",
            system_prompt=build_section_agent_system_prompt(
                "解释与研判",
                "负责综合指标、时间线、情感、主题与方法论，输出事件叙事骨架、关键风险和观察维度。",
            ),
        )
        deep_analysis_trace["source"] = "llm" if isinstance(deep_analysis_payload, dict) else "fallback"
    deep_analysis, deep_analysis_source = _merge_deep_analysis_payload(deep_analysis, deep_analysis_payload)
    deep_analysis_trace["source"] = deep_analysis_source
    section_agents_meta["deep_analysis"] = deep_analysis_trace

    deep_analysis["referenceSnippets"] = reference_snippets
    deep_analysis["referenceLinks"] = reference_links
    deep_analysis["expertNotes"] = expert_notes
    deep_analysis["dynamicTheories"] = dynamic_theories
    deep_analysis["source"] = deep_analysis_source

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
        "bertopic_temporal": {
            "overview": bertopic_overview,
            "meta": bertopic_temporal_meta,
            "leading_themes": bertopic_leading_themes_payload,
            "series_source": bertopic_temporal_meta.get("seriesSource"),
        },
        "main_finding": main_finding,
        "deep_analysis": {
            "narrativeSummary": deep_analysis.get("narrativeSummary"),
            "keyEvents": deep_analysis.get("keyEvents"),
            "keyRisks": deep_analysis.get("keyRisks"),
            "eventType": deep_analysis.get("eventType"),
            "domain": deep_analysis.get("domain"),
            "stage": deep_analysis.get("stage"),
            "indicatorDimensions": deep_analysis.get("indicatorDimensions"),
            "theoryNames": deep_analysis.get("theoryNames"),
        },
        "methodology_context": methodology_context_text,
        "reference_snippets": reference_snippets,
        "reference_links": reference_links,
        "expert_notes": expert_notes,
        "dynamic_theories": dynamic_theories,
        "theory_hints": theory_hints,
        "skill_context": skill_context,
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
    bertopic_series_summary = []
    for item in bertopic_series_payload[:6]:
        points = item.get("points") if isinstance(item.get("points"), list) else []
        peak_point = max(points, key=lambda point: _parse_int(point.get("count")), default={})
        bertopic_series_summary.append(
            {
                "theme": str(item.get("title") or item.get("name") or "").strip(),
                "totalCount": _parse_int(item.get("totalCount")),
                "activeBuckets": len(points),
                "peakDate": str(peak_point.get("date") or "").strip(),
                "peakCount": _parse_int(peak_point.get("count")),
            }
        )
    bertopic_switches_for_llm = []
    previous_theme = ""
    for item in bertopic_nodes_payload:
        current_theme = str(item.get("topTheme") or "").strip()
        if previous_theme and current_theme and previous_theme != current_theme:
            bertopic_switches_for_llm.append(
                {
                    "date": str(item.get("date") or "").strip(),
                    "fromTheme": previous_theme,
                    "toTheme": current_theme,
                    "total": _parse_int(item.get("total")),
                    "topValue": _parse_int(item.get("topValue")),
                }
            )
        if current_theme:
            previous_theme = current_theme
    bertopic_insight_facts = {
        "topic": topic_label,
        "time_range": {"start": start, "end": end},
        "bertopic_overview": bertopic_overview,
        "bertopic_series_source": bertopic_temporal_meta.get("seriesSource"),
        "bertopic_leading_themes": bertopic_leading_themes_payload,
        "bertopic_hotspots": bertopic_hotspots_payload[:10],
        "bertopic_timeline": bertopic_timeline_for_llm,
        "bertopic_series_summary": bertopic_series_summary,
        "deep_analysis": {
            "narrativeSummary": deep_analysis.get("narrativeSummary"),
            "keyEvents": deep_analysis.get("keyEvents"),
            "keyRisks": deep_analysis.get("keyRisks"),
            "stage": deep_analysis.get("stage"),
            "theoryNames": deep_analysis.get("theoryNames"),
        },
        "methodology_context": methodology_context_text,
        "reference_snippets": reference_snippets,
        "reference_links": reference_links,
        "expert_notes": expert_notes,
        "dynamic_theories": dynamic_theories,
        "theory_hints": theory_hints,
        "skill_context": skill_context,
        "main_finding": main_finding,
        "legacy_rag_sections": legacy_context.get("sections_text_short", ""),
        "legacy_report_text": legacy_context.get("full_text_short", ""),
    }
    bertopic_temporal_narrative_facts = {
        "topic": topic_label,
        "time_range": {"start": start, "end": end},
        "bertopic_overview": bertopic_overview,
        "bertopic_meta": bertopic_temporal_meta,
        "bertopic_leading_themes": bertopic_leading_themes_payload,
        "bertopic_hotspots": bertopic_hotspots_payload[:8],
        "bertopic_switches": bertopic_switches_for_llm[:8],
        "bertopic_series_summary": bertopic_series_summary,
        "deep_analysis": {
            "narrativeSummary": deep_analysis.get("narrativeSummary"),
            "keyEvents": deep_analysis.get("keyEvents"),
            "keyRisks": deep_analysis.get("keyRisks"),
            "stage": deep_analysis.get("stage"),
            "theoryNames": deep_analysis.get("theoryNames"),
        },
        "methodology_context": methodology_context_text,
        "reference_snippets": reference_snippets,
        "reference_links": reference_links,
        "expert_notes": expert_notes,
        "dynamic_theories": dynamic_theories,
        "theory_hints": theory_hints,
        "skill_context": skill_context,
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
    bertopic_insight_payload, bertopic_insight_trace = _run_section_agent(
        SectionAgentSpec(
            name="BERTopic主题演化解读",
            focus="负责把 BERTopic 时间线转成业务方可读的主题迁移判断，说明长期主题、爆发主题和切换原因。",
            prompt_builder=build_bertopic_insight_prompt,
            model_role="report",
            max_tokens=1800,
            analysis_goal="先判断主题演化的主线、关键切换节点、哪些主题是长期背景、哪些主题是短时爆发。",
        ),
        bertopic_insight_facts,
    )
    bertopic_insight_candidate = _extract_bertopic_insight_from_payload(bertopic_insight_payload)
    if bertopic_insight_candidate:
        bertopic_insight = bertopic_insight_candidate
        bertopic_insight_source = "llm"
    bertopic_insight_trace["source"] = bertopic_insight_source
    section_agents_meta["bertopic_insight"] = bertopic_insight_trace

    bertopic_temporal_narrative = _build_fallback_bertopic_temporal_narrative(
        topic_label=topic_label,
        start=start,
        end=end,
        bertopic_overview=bertopic_overview,
        bertopic_meta=bertopic_temporal_meta,
        bertopic_nodes=bertopic_nodes_payload,
        bertopic_series=bertopic_series_payload,
        bertopic_hotspots=bertopic_hotspots_payload,
        leading_themes=bertopic_leading_themes_payload,
    )
    bertopic_temporal_narrative_source = "fallback"
    bertopic_temporal_narrative_payload, bertopic_temporal_trace = _run_section_agent(
        SectionAgentSpec(
            name="BERTopic时序研判",
            focus="负责把 BERTopic 时间序列压缩成结构化迁移摘要、切换信号和监测提醒。",
            prompt_builder=build_bertopic_temporal_narrative_prompt,
            model_role="report",
            max_tokens=1200,
            analysis_goal="先概括时间主线、主题切换强度、覆盖率问题和异常峰值风险，再生成最终结构化解读。",
        ),
        bertopic_temporal_narrative_facts,
    )
    bertopic_temporal_narrative, bertopic_temporal_narrative_source = _merge_bertopic_temporal_narrative_payload(
        bertopic_temporal_narrative,
        bertopic_temporal_narrative_payload,
    )
    bertopic_temporal_trace["source"] = bertopic_temporal_narrative_source
    section_agents_meta["bertopic_temporal_narrative"] = bertopic_temporal_trace

    report_facts_with_bertopic = dict(report_facts)
    report_facts_with_bertopic["bertopic_insight"] = bertopic_insight
    report_facts_with_bertopic["bertopic_temporal_narrative"] = bertopic_temporal_narrative

    title = f"{topic_label}舆情分析报告"
    subtitle = (
        main_finding
        or _truncate_inline_text(str(deep_analysis.get("narrativeSummary") or "").strip(), 90)
        or "基于结构化统计结果自动生成，覆盖声量、趋势、态度与主题。"
    )

    stage_notes = _build_fallback_stage_notes(timeline)
    stage_payload, stage_trace = _run_section_agent(
        SectionAgentSpec(
            name="传播节奏阶段说明",
            focus="负责按时间切分传播阶段，解释每一段的触发原因、节奏变化和阶段风险。",
            prompt_builder=build_stage_notes_prompt,
            model_role="report",
            max_tokens=1400,
            analysis_goal="先判断时间线应如何分段，每段最核心的驱动因素与风险边界是什么。",
        ),
        report_facts_with_bertopic,
    )
    parsed_stage_notes = _extract_stage_notes_from_payload(stage_payload)
    if parsed_stage_notes:
        stage_notes = parsed_stage_notes
    stage_trace["source"] = "llm" if parsed_stage_notes else "fallback"
    section_agents_meta["stage_notes"] = stage_trace

    highlight_points, insights = _build_fallback_insights(channels, timeline, sentiment, keywords, themes, main_finding)
    if str(deep_analysis.get("narrativeSummary") or "").strip():
        highlight_points[-1] = _truncate_inline_text(str(deep_analysis.get("narrativeSummary") or "").strip(), 120)
    if isinstance(deep_analysis.get("keyRisks"), list):
        risk_items = [str(item).strip() for item in (deep_analysis.get("keyRisks") or []) if str(item or "").strip()]
        if risk_items:
            insights[-1]["points"] = risk_items[:3]
            insights[-1]["headline"] = "建议优先围绕高风险点配置回应策略"
    insights_facts = dict(report_facts_with_bertopic)
    insights_facts["stage_notes"] = stage_notes
    insights_payload, insights_trace = _run_section_agent(
        SectionAgentSpec(
            name="洞察亮点与重点结论",
            focus="负责把统计结果、深度研判和 BERTopic 迁移信息压缩成亮点列表与六张结论卡片。",
            prompt_builder=build_insights_prompt,
            model_role="report",
            max_tokens=2200,
            analysis_goal="先判断最值得强调的结论主线、建议优先级和应规避的空话，再生成卡片。",
        ),
        insights_facts,
    )
    parsed_points, parsed_cards = _extract_insights_from_payload(insights_payload)
    if parsed_points:
        highlight_points = parsed_points
    if parsed_cards:
        insights = parsed_cards
    insights_trace["source"] = "llm" if parsed_points or parsed_cards else "fallback"
    section_agents_meta["insights"] = insights_trace

    title_facts = dict(report_facts_with_bertopic)
    title_facts["stage_notes"] = stage_notes
    title_facts["highlight_points"] = highlight_points
    title_facts["insights"] = insights
    title_payload, title_trace = _run_section_agent(
        SectionAgentSpec(
            name="标题与副标题",
            focus="负责以编辑视角压缩整份报告的主线、阶段态势和风险重点，输出可直接展示的标题与副标题。",
            prompt_builder=lambda facts: build_title_subtitle_prompt(topic_label, facts),
            model_role="main",
            max_tokens=500,
            analysis_goal="先判断整份报告最值得被标题化的主线、传播态势和表达边界，再生成标题与副标题。",
        ),
        title_facts,
    )
    title_candidate, subtitle_candidate = _extract_title_subtitle_from_payload(title_payload)
    if title_candidate:
        title = title_candidate
    if subtitle_candidate:
        subtitle = subtitle_candidate
    title_trace["source"] = "llm" if title_candidate or subtitle_candidate else "fallback"
    section_agents_meta["title_subtitle"] = title_trace

    now_text = datetime.now().strftime("%Y-%m-%d %H:%M")
    if bertopic_insight_source == "fallback" and str(deep_analysis.get("narrativeSummary") or "").strip():
        bertopic_insight = (
            f"**总体研判**：{str(deep_analysis.get('narrativeSummary') or '').strip()}\n\n"
            f"{bertopic_insight}"
        ).strip()

    log_success(
        logger,
        (
            f"结构化报告组装完成 | 深度研判:{deep_analysis_source} "
            f"| BERTopic:{bertopic_insight_source}/{bertopic_temporal_narrative_source}"
        ),
        "ReportStructured",
    )

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
        "bertopicTemporal": bertopic_temporal_payload,
        "bertopicInsight": bertopic_insight,
        "bertopicTemporalNarrative": bertopic_temporal_narrative,
        "deepAnalysis": deep_analysis,
        "stageNotes": stage_notes,
        "highlightPoints": highlight_points,
        "insights": insights,
        "meta": {
            "topic_identifier": topic_identifier,
            "topic_label": topic_label,
            "analyze_root": str(analyze_root),
            "theme_source": theme_source,
            "bertopic_context": bertopic_context.get("meta") if isinstance(bertopic_context, dict) else {},
            "title_source": section_agents_meta.get("title_subtitle", {}).get("source") or "fallback",
            "stage_notes_source": section_agents_meta.get("stage_notes", {}).get("source") or "fallback",
            "insights_source": section_agents_meta.get("insights", {}).get("source") or "fallback",
            "bertopic_insight_source": bertopic_insight_source,
            "bertopic_temporal_narrative_source": bertopic_temporal_narrative_source,
            "deep_analysis_source": deep_analysis_source,
            "deep_analysis_tool_trace": {
                "tool_call_count": len(deep_analysis_trace.get("tool_calls") or []),
                "tool_calls": deep_analysis_trace.get("tool_calls") or [],
                "tool_results": deep_analysis_trace.get("tool_results") or [],
                "model": deep_analysis_trace.get("model") or "",
                "provider": deep_analysis_trace.get("provider") or "",
                "model_role": deep_analysis_trace.get("model_role") or "",
            },
            "section_agents": section_agents_meta,
            "knowledge_context": knowledge_context.get("meta") if isinstance(knowledge_context, dict) else {},
            "skill_context": skill_context,
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
    logger = setup_logger(f"ReportStructured_{topic_identifier}", folder)
    try:
        with cache_path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        log_success(logger, f"报告缓存写入成功: {cache_path}", "ReportStructured")
    except Exception:
        pass
    log_success(logger, "模块执行完成", "ReportStructured")
    return payload
