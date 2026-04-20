from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from server_support.archive_locator import ArchiveLocator
from server_support.topic_context import TopicContext


ANALYZE_FILE_MAP: Dict[str, str] = {
    "volume": "volume.json",
    "attitude": "attitude.json",
    "trends": "trends.json",
    "geography": "geography.json",
    "publishers": "publishers.json",
    "keywords": "keywords.json",
    "classification": "classification.json",
}

ANALYZE_LABELS: Dict[str, str] = {
    "volume": "声量概览",
    "attitude": "情绪结构",
    "trends": "趋势变化",
    "geography": "地域分布",
    "publishers": "发布者结构",
    "keywords": "高频关键词",
    "classification": "议题分类",
}

BERTOPIC_FILE_MAP: Dict[str, str] = {
    "summary": "1主题统计结果.json",
    "keywords": "2主题关键词.json",
    "coords": "3文档2D坐标.json",
    "llm_clusters": "4大模型再聚类结果.json",
    "llm_keywords": "5大模型主题关键词.json",
    "temporal": "6主题时间趋势.json",
}


def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


def _safe_int(value: Any) -> int:
    try:
        return int(float(value))
    except Exception:
        return 0


def _extract_rows(payload: Any) -> List[Dict[str, Any]]:
    if isinstance(payload, dict) and isinstance(payload.get("data"), list):
        return [item for item in payload.get("data") or [] if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _iter_numbers(value: Any) -> Iterable[float]:
    if isinstance(value, bool):
        return
    if isinstance(value, (int, float)):
        yield float(value)
        return
    if isinstance(value, list):
        for item in value:
            yield from _iter_numbers(item)
        return
    if isinstance(value, dict):
        for item in value.values():
            yield from _iter_numbers(item)


def _iter_records(value: Any) -> Iterable[Dict[str, Any]]:
    if isinstance(value, dict):
        if any(key in value for key in ("date", "day", "name", "value", "count", "label")):
            yield value
        for item in value.values():
            yield from _iter_records(item)
        return
    if isinstance(value, list):
        for item in value:
            yield from _iter_records(item)


def _collect_top_labels(payload: Any, *, max_items: int = 6) -> List[Dict[str, Any]]:
    ranked: List[Dict[str, Any]] = []
    for item in _iter_records(payload):
        label = str(
            item.get("name")
            or item.get("label")
            or item.get("keyword")
            or item.get("topic")
            or item.get("classification")
            or ""
        ).strip()
        if not label:
            continue
        values = list(_iter_numbers(item.get("value") if "value" in item else item.get("count") if "count" in item else item))
        ranked.append({"label": label, "value": max((int(num) for num in values), default=0)})
    ranked.sort(key=lambda item: int(item.get("value") or 0), reverse=True)
    return ranked[: max(1, max_items)]


def _guess_total_volume(volume_payload: Any) -> int:
    if not isinstance(volume_payload, dict):
        return 0
    candidates = [
        volume_payload.get("total"),
        volume_payload.get("total_count"),
        volume_payload.get("volume"),
        volume_payload.get("count"),
        volume_payload.get("summary"),
    ]
    values = [int(num) for item in candidates for num in _iter_numbers(item)]
    return max(values) if values else 0


def _guess_peak_from_trends(trends_payload: Any) -> Dict[str, Any]:
    best = {"date": "", "value": 0}
    for item in _iter_records(trends_payload):
        label = str(item.get("date") or item.get("day") or item.get("name") or item.get("label") or "").strip()
        values = [int(num) for num in _iter_numbers(item.get("value") if "value" in item else item.get("count") if "count" in item else item)]
        if not values:
            continue
        current = max(values)
        if current > int(best["value"] or 0):
            best = {"date": label, "value": current}
    return best


def _guess_sentiment(attitude_payload: Any) -> Dict[str, int]:
    out = {"positive": 0, "neutral": 0, "negative": 0}
    if isinstance(attitude_payload, dict):
        iterable: Iterable[tuple[Any, Any]] = attitude_payload.items()
    else:
        iterable = []
    for key, value in iterable:
        lowered = str(key or "").lower()
        total = max((int(num) for num in _iter_numbers(value)), default=0)
        if any(token in lowered for token in ("positive", "积极", "正向")):
            out["positive"] = max(out["positive"], total)
        elif any(token in lowered for token in ("neutral", "中性")):
            out["neutral"] = max(out["neutral"], total)
        elif any(token in lowered for token in ("negative", "消极", "负向")):
            out["negative"] = max(out["negative"], total)
    for item in _iter_records(attitude_payload):
        label = str(
            item.get("name")
            or item.get("label")
            or item.get("sentiment")
            or item.get("polarity")
            or ""
        ).strip().lower()
        total = max((int(num) for num in _iter_numbers(item.get("value") if "value" in item else item.get("count") if "count" in item else item)), default=0)
        if any(token in label for token in ("positive", "积极", "正向")):
            out["positive"] = max(out["positive"], total)
        elif any(token in label for token in ("neutral", "中性")):
            out["neutral"] = max(out["neutral"], total)
        elif any(token in label for token in ("negative", "消极", "负向")):
            out["negative"] = max(out["negative"], total)
    return out


def _build_trace(
    *,
    topic_identifier: str,
    start: str,
    end: str,
    source_root: Path | None,
    hit_files: List[str],
    missing_files: List[str],
    availability_flags: List[str],
) -> Dict[str, Any]:
    return {
        "topic_identifier": str(topic_identifier or "").strip(),
        "time_range": {"start": str(start or "").strip(), "end": str(end or "").strip()},
        "source_paths": [str(source_root)] if source_root else [],
        "hit_files": hit_files,
        "missing_files": missing_files,
        "availability_flags": availability_flags,
    }


def _bertopic_summary_rows(summary_payload: Any) -> List[Dict[str, Any]]:
    if not isinstance(summary_payload, dict):
        return []
    rows: List[Dict[str, Any]] = []
    topic_stats = summary_payload.get("主题文档统计") if isinstance(summary_payload.get("主题文档统计"), dict) else summary_payload
    if not isinstance(topic_stats, dict):
        return rows
    for topic_name, item in topic_stats.items():
        if not isinstance(item, dict):
            continue
        rows.append({"name": str(topic_name).strip(), "count": _safe_int(item.get("文档数") or item.get("count") or item.get("value"))})
    rows.sort(key=lambda item: int(item.get("count") or 0), reverse=True)
    return rows


def _bertopic_cluster_rows(cluster_payload: Any, keyword_payload: Any) -> List[Dict[str, Any]]:
    if not isinstance(cluster_payload, dict):
        return []
    keyword_map = keyword_payload if isinstance(keyword_payload, dict) else {}
    rows: List[Dict[str, Any]] = []
    for cluster_name, item in cluster_payload.items():
        if not isinstance(item, dict):
            continue
        keywords = keyword_map.get(cluster_name) if isinstance(keyword_map.get(cluster_name), list) else []
        rows.append(
            {
                "name": str(cluster_name).strip(),
                "count": _safe_int(item.get("文档数") or item.get("count") or item.get("value")),
                "description": str(item.get("主题描述") or "").strip(),
                "keywords": [str(token).strip() for token in keywords if str(token or "").strip()][:8],
                "original_topics": [str(token).strip() for token in (item.get("原始主题集合") or []) if str(token or "").strip()][:12],
            }
        )
    rows.sort(key=lambda item: int(item.get("count") or 0), reverse=True)
    return rows


def _bertopic_temporal_rows(temporal_payload: Any) -> List[Dict[str, Any]]:
    if not isinstance(temporal_payload, dict):
        return []
    rows: List[Dict[str, Any]] = []
    time_nodes = temporal_payload.get("time_nodes") if isinstance(temporal_payload.get("time_nodes"), list) else []
    for item in time_nodes:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or item.get("date") or "").strip()
        rows.append({"label": label, "value": _safe_int(item.get("total") or item.get("count") or item.get("value"))})
    if rows:
        return rows
    series = ((temporal_payload.get("llm_clusters") or {}) if isinstance(temporal_payload.get("llm_clusters"), dict) else temporal_payload.get("raw_topics")) or {}
    if isinstance(series, dict):
        source_series = series.get("series") if isinstance(series.get("series"), list) else []
    else:
        source_series = []
    bucket_counts: Dict[str, int] = {}
    for item in source_series:
        if not isinstance(item, dict):
            continue
        for point in item.get("points") or []:
            if not isinstance(point, dict):
                continue
            key = str(point.get("label") or point.get("date") or "").strip()
            if not key:
                continue
            bucket_counts[key] = bucket_counts.get(key, 0) + _safe_int(point.get("count") or point.get("value"))
    return [{"label": key, "value": bucket_counts[key]} for key in sorted(bucket_counts)]


def _bertopic_temporal_nodes(temporal_payload: Any) -> List[Dict[str, Any]]:
    if not isinstance(temporal_payload, dict):
        return []
    nodes = temporal_payload.get("time_nodes") if isinstance(temporal_payload.get("time_nodes"), list) else []
    rows: List[Dict[str, Any]] = []
    for item in nodes:
        if not isinstance(item, dict):
            continue
        themes = item.get("themes") if isinstance(item.get("themes"), list) else []
        cleaned_themes: List[Dict[str, Any]] = []
        for theme in themes:
            if not isinstance(theme, dict):
                continue
            name = str(theme.get("name") or "").strip()
            if not name:
                continue
            cleaned_themes.append({"name": name, "value": _safe_int(theme.get("value") or theme.get("count"))})
        cleaned_themes.sort(key=lambda theme: int(theme.get("value") or 0), reverse=True)
        rows.append(
            {
                "date": str(item.get("date") or "").strip(),
                "label": str(item.get("label") or item.get("date") or "").strip(),
                "total": _safe_int(item.get("total") or item.get("count") or item.get("value")),
                "top_theme": str(item.get("topTheme") or "").strip(),
                "top_value": _safe_int(item.get("topValue") or 0),
                "themes": cleaned_themes[:6],
            }
        )
    return rows


def _summarize_theme_profiles(llm_clusters: List[Dict[str, Any]], temporal_nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    peak_map: Dict[str, List[Dict[str, Any]]] = {}
    for node in temporal_nodes:
        label = str(node.get("label") or "").strip()
        for theme in node.get("themes") or []:
            if not isinstance(theme, dict):
                continue
            name = str(theme.get("name") or "").strip()
            if not name:
                continue
            peak_map.setdefault(name, []).append(
                {"label": label, "value": _safe_int(theme.get("value") or 0), "date": str(node.get("date") or "").strip()}
            )
    profiles: List[Dict[str, Any]] = []
    for item in llm_clusters[:5]:
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        peaks = sorted(peak_map.get(name) or [], key=lambda entry: int(entry.get("value") or 0), reverse=True)[:3]
        profiles.append(
            {
                "name": name,
                "count": _safe_int(item.get("count") or 0),
                "description": str(item.get("description") or "").strip(),
                "keywords": [str(token).strip() for token in (item.get("keywords") or []) if str(token or "").strip()][:6],
                "peak_weeks": peaks,
            }
        )
    return profiles


def _summarize_temporal_highlights(temporal_nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    highlights: List[Dict[str, Any]] = []
    for node in sorted(temporal_nodes, key=lambda entry: int(entry.get("total") or 0), reverse=True)[:5]:
        top_themes = []
        for theme in (node.get("themes") or [])[:3]:
            if not isinstance(theme, dict):
                continue
            name = str(theme.get("name") or "").strip()
            if not name:
                continue
            top_themes.append({"name": name, "value": _safe_int(theme.get("value") or 0)})
        highlights.append(
            {
                "label": str(node.get("label") or "").strip(),
                "date": str(node.get("date") or "").strip(),
                "total": _safe_int(node.get("total") or 0),
                "top_theme": str(node.get("top_theme") or "").strip(),
                "top_value": _safe_int(node.get("top_value") or 0),
                "top_themes": top_themes,
            }
        )
    return highlights


def _summarize_dominant_phases(temporal_nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    phases: List[Dict[str, Any]] = []
    current: Dict[str, Any] | None = None
    for node in temporal_nodes:
        top_theme = str(node.get("top_theme") or "").strip()
        if not top_theme:
            continue
        if current and current.get("top_theme") == top_theme:
            current["end_label"] = str(node.get("label") or current.get("end_label") or "").strip()
            current["end_date"] = str(node.get("date") or current.get("end_date") or "").strip()
            current["weeks"] = int(current.get("weeks") or 0) + 1
            current["max_total"] = max(int(current.get("max_total") or 0), _safe_int(node.get("total") or 0))
            continue
        if current:
            phases.append(current)
        current = {
            "top_theme": top_theme,
            "start_label": str(node.get("label") or "").strip(),
            "end_label": str(node.get("label") or "").strip(),
            "start_date": str(node.get("date") or "").strip(),
            "end_date": str(node.get("date") or "").strip(),
            "weeks": 1,
            "max_total": _safe_int(node.get("total") or 0),
        }
    if current:
        phases.append(current)
    phases.sort(key=lambda item: (int(item.get("weeks") or 0), int(item.get("max_total") or 0)), reverse=True)
    return phases[:5]


def collect_basic_analysis_snapshot(
    topic_identifier: str,
    start: str,
    end: Optional[str],
    *,
    topic_label: str = "",
    ctx: Optional[TopicContext] = None,
) -> Dict[str, Any]:
    end_text = str(end or start).strip() or str(start or "").strip()
    context = ctx or TopicContext(identifier=topic_identifier, display_name=topic_label or topic_identifier, aliases=[])
    root = ArchiveLocator(context).resolve_result_dir("analyze", start, end_text)
    available_functions: List[str] = []
    missing_functions: List[str] = []
    hit_files: List[str] = []
    missing_files: List[str] = []
    function_payloads: Dict[str, Any] = {}
    function_rows: List[Dict[str, Any]] = []
    if root:
        for func_name, filename in ANALYZE_FILE_MAP.items():
            target = root / func_name / "总体" / filename
            payload = _load_json(target)
            if payload is None:
                missing_functions.append(func_name)
                missing_files.append(str(target))
                continue
            available_functions.append(func_name)
            hit_files.append(str(target))
            function_payloads[func_name] = payload
            rows = _extract_rows(payload)
            function_rows.append(
                {
                    "name": func_name,
                    "label": ANALYZE_LABELS.get(func_name, func_name),
                    "file": filename,
                    "path": str(target),
                    "row_count": len(rows),
                    "top_items": _collect_top_labels(payload),
                }
            )
    else:
        missing_functions = list(ANALYZE_FILE_MAP.keys())
        missing_files = [f"analyze::{name}" for name in ANALYZE_FILE_MAP.keys()]
    availability_flags = ["archive_found" if root else "archive_missing"]
    if available_functions:
        availability_flags.append("snapshot_ready")
    if missing_functions:
        availability_flags.append("partial_coverage")
    overview = {
        "total_volume": _guess_total_volume(function_payloads.get("volume")),
        "peak": _guess_peak_from_trends(function_payloads.get("trends")),
        "sentiment": _guess_sentiment(function_payloads.get("attitude")),
        "top_topics": _collect_top_labels(function_payloads.get("classification")),
        "top_keywords": _collect_top_labels(function_payloads.get("keywords")),
        "top_publishers": _collect_top_labels(function_payloads.get("publishers")),
        "top_geography": _collect_top_labels(function_payloads.get("geography")),
    }
    trace = _build_trace(
        topic_identifier=topic_identifier,
        start=start,
        end=end_text,
        source_root=root,
        hit_files=hit_files,
        missing_files=missing_files,
        availability_flags=availability_flags,
    )
    return {
        "snapshot_id": f"basic-analysis::{topic_identifier}::{start}::{end_text}",
        "topic_identifier": topic_identifier,
        "topic_label": topic_label or topic_identifier,
        "time_range": {"start": str(start or "").strip(), "end": end_text},
        "available": bool(root and available_functions),
        "source_root": str(root) if root else "",
        "available_functions": available_functions,
        "missing_functions": missing_functions,
        "overview": overview,
        "functions": function_rows,
        "trace": trace,
    }


def build_basic_analysis_insight(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    overview = snapshot.get("overview") if isinstance(snapshot.get("overview"), dict) else {}
    sentiment = overview.get("sentiment") if isinstance(overview.get("sentiment"), dict) else {}
    top_topics = overview.get("top_topics") if isinstance(overview.get("top_topics"), list) else []
    top_keywords = overview.get("top_keywords") if isinstance(overview.get("top_keywords"), list) else []
    peak = overview.get("peak") if isinstance(overview.get("peak"), dict) else {}
    available = bool(snapshot.get("available"))
    summary_parts: List[str] = []
    if available:
        total_volume = _safe_int(overview.get("total_volume"))
        if total_volume > 0:
            summary_parts.append(f"基础分析显示当前区间累计声量约 {total_volume} 条。")
        if str(peak.get("date") or "").strip():
            summary_parts.append(f"讨论峰值出现在 {str(peak.get('date') or '').strip()}。")
        if top_topics:
            summary_parts.append(f"讨论重心主要集中在 {str(top_topics[0].get('label') or '').strip()} 等议题。")
    summary = "".join(summary_parts).strip() or "当前区间已读取基础分析归档，可用于量、质、人、场、效的综合判断。"
    findings = [
        f"情绪结构中，正向 {int(sentiment.get('positive') or 0)}、中性 {int(sentiment.get('neutral') or 0)}、负向 {int(sentiment.get('negative') or 0)}。"
        if any(int(sentiment.get(key) or 0) for key in ("positive", "neutral", "negative"))
        else "",
        f"头部议题包括 {str(top_topics[0].get('label') or '').strip()}、{str(top_topics[1].get('label') or '').strip()}。"
        if len(top_topics) >= 2
        else (f"头部议题为 {str(top_topics[0].get('label') or '').strip()}。" if top_topics else ""),
        f"高频表达聚焦 {str(top_keywords[0].get('label') or '').strip()}。"
        if top_keywords
        else "",
    ]
    uncertainty_notes = []
    for func_name in snapshot.get("missing_functions") or []:
        uncertainty_notes.append(f"{ANALYZE_LABELS.get(str(func_name), str(func_name))}结果缺失，当前只能基于已完成模块判断。")
    chart_refs = [
        "volume.overall",
        "trends.overall",
        "trends.trend-flow",
        "trends.trend-share",
        "attitude.overall",
        "classification.overall",
        "keywords.overall",
        "publishers.overall",
        "geography.overall",
    ]
    return {
        "section_id": "basic-analysis-insight",
        "section_title": "基础分析洞察",
        "summary": summary,
        "key_findings": [item for item in findings if item],
        "chart_refs": chart_refs,
        "evidence_refs": [f"analysis::{name}" for name in snapshot.get("available_functions") or []],
        "uncertainty_notes": uncertainty_notes or ["基础分析归档已就绪，当前章节可直接复用现有统计图表。"],
        "trace": snapshot.get("trace") if isinstance(snapshot.get("trace"), dict) else {},
    }


def ensure_bertopic_results(
    topic_identifier: str,
    *,
    start: str,
    end: Optional[str],
    ctx: TopicContext,
    run_if_missing: bool,
) -> Dict[str, Any]:
    end_text = str(end or start).strip() or str(start or "").strip()
    locator = ArchiveLocator(ctx)
    existing_root = locator.resolve_result_dir("topic", start, end_text)
    if existing_root:
        return {
            "prepared": False,
            "ready": True,
            "output_dir": str(existing_root),
            "message": "",
            "source": "archive",
        }
    if not run_if_missing:
        return {
            "prepared": False,
            "ready": False,
            "output_dir": "",
            "message": "BERTopic 结果未就绪，本轮按当前文书策略跳过自动补跑。",
            "source": "missing",
        }
    try:
        from src.topic.api import run_topic_bertopic_job

        response = run_topic_bertopic_job(
            {
                "topic": str(ctx.display_name or ctx.identifier).strip(),
                "project": str(ctx.log_project or ctx.display_name or ctx.identifier).strip(),
                "start_date": str(start or "").strip(),
                "end_date": end_text if end_text != str(start or "").strip() else "",
            }
        )
    except Exception as exc:
        return {
            "prepared": False,
            "ready": False,
            "output_dir": "",
            "message": f"BERTopic 自动补跑失败：{exc}",
            "source": "sync_error",
        }
    refreshed_root = locator.resolve_result_dir("topic", start, end_text)
    if str(response.get("status") or "").strip() == "ok" and refreshed_root:
        return {
            "prepared": True,
            "ready": True,
            "output_dir": str(refreshed_root),
            "message": "已按需补跑 BERTopic 并生成主题演化结果。",
            "source": "sync_run",
        }
    return {
        "prepared": False,
        "ready": False,
        "output_dir": str(refreshed_root) if refreshed_root else "",
        "message": str(response.get("message") or "BERTopic 自动补跑失败。").strip() or "BERTopic 自动补跑失败。",
        "source": "sync_failed",
    }


def collect_bertopic_snapshot(
    topic_identifier: str,
    start: str,
    end: Optional[str],
    *,
    topic_label: str = "",
    ctx: Optional[TopicContext] = None,
) -> Dict[str, Any]:
    end_text = str(end or start).strip() or str(start or "").strip()
    context = ctx or TopicContext(identifier=topic_identifier, display_name=topic_label or topic_identifier, aliases=[])
    root = ArchiveLocator(context).resolve_result_dir("topic", start, end_text)
    payloads: Dict[str, Any] = {}
    hit_files: List[str] = []
    missing_files: List[str] = []
    available_files: List[str] = []
    if root:
        for key, filename in BERTOPIC_FILE_MAP.items():
            path = root / filename
            payload = _load_json(path)
            if payload is None:
                missing_files.append(str(path))
                continue
            payloads[key] = payload
            available_files.append(key)
            hit_files.append(str(path))
    else:
        missing_files = [f"topic::{name}" for name in BERTOPIC_FILE_MAP.keys()]
    raw_topics = _bertopic_summary_rows(payloads.get("summary"))
    llm_clusters = _bertopic_cluster_rows(payloads.get("llm_clusters"), payloads.get("llm_keywords"))
    temporal_rows = _bertopic_temporal_rows(payloads.get("temporal"))
    temporal_nodes = _bertopic_temporal_nodes(payloads.get("temporal"))
    availability_flags = ["archive_found" if root else "archive_missing"]
    if llm_clusters:
        availability_flags.append("cluster_ready")
    if temporal_rows:
        availability_flags.append("temporal_ready")
    if missing_files:
        availability_flags.append("partial_coverage")
    trace = _build_trace(
        topic_identifier=topic_identifier,
        start=start,
        end=end_text,
        source_root=root,
        hit_files=hit_files,
        missing_files=missing_files,
        availability_flags=availability_flags,
    )
    return {
        "snapshot_id": f"bertopic::{topic_identifier}::{start}::{end_text}",
        "topic_identifier": topic_identifier,
        "topic_label": topic_label or topic_identifier,
        "time_range": {"start": str(start or "").strip(), "end": end_text},
        "available": bool(root and available_files),
        "source_root": str(root) if root else "",
        "available_files": available_files,
        "raw_topics": raw_topics,
        "llm_clusters": llm_clusters,
        "temporal_points": temporal_rows,
        "temporal_nodes": temporal_nodes,
        "trace": trace,
    }


def build_bertopic_insight(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    raw_topics = snapshot.get("raw_topics") if isinstance(snapshot.get("raw_topics"), list) else []
    llm_clusters = snapshot.get("llm_clusters") if isinstance(snapshot.get("llm_clusters"), list) else []
    temporal_points = snapshot.get("temporal_points") if isinstance(snapshot.get("temporal_points"), list) else []
    temporal_nodes = snapshot.get("temporal_nodes") if isinstance(snapshot.get("temporal_nodes"), list) else []
    theme_profiles = _summarize_theme_profiles(llm_clusters, temporal_nodes)
    temporal_highlights = _summarize_temporal_highlights(temporal_nodes)
    dominant_phases = _summarize_dominant_phases(temporal_nodes)
    summary_parts: List[str] = []
    if llm_clusters:
        summary_parts.append(f"BERTopic 结果显示当前区间形成 {len(llm_clusters)} 个高层主题簇。")
        summary_parts.append(f"其中 {str(llm_clusters[0].get('name') or '').strip()} 是当前最主要的讨论主线。")
        if len(llm_clusters) >= 2:
            summary_parts.append(f"与之并行的高权重主题还包括 {str(llm_clusters[1].get('name') or '').strip()}。")
    elif raw_topics:
        summary_parts.append(f"BERTopic 原始主题统计显示当前共有 {len(raw_topics)} 个可识别主题。")
    if temporal_highlights:
        top_node = temporal_highlights[0]
        summary_parts.append(
            f"从时序上看，{str(top_node.get('label') or '').strip()}是最显著的热度峰值周，主导主题为{str(top_node.get('top_theme') or '').strip()}。"
        )
    elif temporal_points:
        summary_parts.append("主题热度在时间轴上存在明显迁移，可结合时序节点观察主线切换。")
    summary = "".join(summary_parts).strip() or "当前区间尚未形成完整的 BERTopic 主题演化结果，本章节仅保留缺口说明。"
    findings: List[str] = []
    if theme_profiles:
        top_a = theme_profiles[0]
        findings.append(
            f"{str(top_a.get('name') or '').strip()}是最强主题簇，主要围绕{str(top_a.get('description') or '').strip() or '相关议题'}展开，关键词包括{'、'.join(top_a.get('keywords') or [])}。"
        )
    if len(theme_profiles) >= 2:
        top_b = theme_profiles[1]
        findings.append(
            f"{str(top_b.get('name') or '').strip()}构成第二条主线，峰值周集中在{'、'.join(str(item.get('label') or '').strip() for item in (top_b.get('peak_weeks') or [])[:2])}。"
        )
    elif raw_topics:
        findings.append(f"原始主题中，{str(raw_topics[0].get('name') or '').strip()} 文档量最高。")
    if temporal_highlights:
        highlight = temporal_highlights[0]
        findings.append(
            f"最强波峰出现在{str(highlight.get('label') or '').strip()}，当周总量为{int(highlight.get('total') or 0)}，并由{str(highlight.get('top_theme') or '').strip()}主导。"
        )
    if dominant_phases:
        phase = dominant_phases[0]
        findings.append(
            f"持续性最强的阶段主线是{str(phase.get('top_theme') or '').strip()}，覆盖{str(phase.get('start_label') or '').strip()}至{str(phase.get('end_label') or '').strip()}。"
        )
    uncertainty_notes = []
    available_files = {str(item) for item in snapshot.get("available_files") or []}
    if "llm_clusters" not in available_files:
        uncertainty_notes.append("缺少再聚类结果，当前无法稳定输出高层主题簇判断。")
    if "temporal" not in available_files:
        uncertainty_notes.append("缺少主题时间趋势结果，当前无法对主题迁移节奏做完整判断。")
    if not raw_topics and not llm_clusters:
        uncertainty_notes.append("BERTopic 结果未就绪或归档缺失，本章节仅展示能力缺口。")
    chart_refs = ["bertopic.summary", "bertopic.clusters", "bertopic.temporal"]
    evidence_refs = [f"bertopic::{item.get('name')}" for item in llm_clusters[:6] if str(item.get("name") or "").strip()]
    return {
        "section_id": "bertopic-evolution",
        "section_title": "BERTopic 主题演化",
        "summary": summary,
        "key_findings": [item for item in findings if item],
        "chart_refs": chart_refs,
        "evidence_refs": evidence_refs,
        "uncertainty_notes": uncertainty_notes or ["BERTopic 结果已就绪，可用于主题簇、迁移路径与时序切换分析。"],
        "theme_profiles": theme_profiles,
        "temporal_highlights": temporal_highlights,
        "dominant_phases": dominant_phases,
        "trace": snapshot.get("trace") if isinstance(snapshot.get("trace"), dict) else {},
    }


__all__ = [
    "ANALYZE_FILE_MAP",
    "ANALYZE_LABELS",
    "BERTOPIC_FILE_MAP",
    "build_basic_analysis_insight",
    "build_bertopic_insight",
    "collect_basic_analysis_snapshot",
    "collect_bertopic_snapshot",
    "ensure_bertopic_results",
]
