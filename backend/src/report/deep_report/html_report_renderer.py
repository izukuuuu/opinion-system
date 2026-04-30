from __future__ import annotations

import hashlib
import html
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from langchain_core.messages import HumanMessage, SystemMessage

from ...utils.ai import build_langchain_chat_model


REPORT_CONFIG_ANCHOR = "__REPORT_CONFIG_JSON__"
REPORT_DATA_ANCHOR = "__REPORT_JSON_DATA__"
RENDERER_VERSION = "html-report-artifact.v1"

_TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "templates" / "html"
_TEMPLATE_PATH = _TEMPLATE_DIR / "report_html_morandi_template.html"
_FILL_PROMPT_PATH = _TEMPLATE_DIR / "report_html_template_fill.txt"

_PLACEHOLDER_KEYS = frozenset(
    {
        "REPORT_TITLE",
        "REPORT_SUBTITLE",
        "EVENT_TYPE",
        "OBJECT_NAME",
        "PHASE_STATUS",
        "KPI_TOTAL",
        "KPI_EFFECTIVE",
        "KPI_POS_RATIO",
        "KPI_NEG_RATIO",
        "INTRO_BACKGROUND",
        "INTRO_TRIGGERS",
        "SUMMARY_BULLETS",
        "CHART_SENTIMENT_ANALYSIS",
        "CHART_TIMELINE_ANALYSIS",
        "CHART_VOLUME_ANALYSIS",
        "CHART_REGION_ANALYSIS",
        "CHART_AUTHOR_ANALYSIS",
        "CHART_KEYWORD_ANALYSIS",
        "CHART_RADAR_ANALYSIS",
        "CHART_LIFECYCLE_ANALYSIS",
        "THEORY_SILENCE",
        "THEORY_AGENDA",
        "THEORY_BUTTERFLY",
        "RESPONSE_ANALYSIS_BULLETS",
        "RECAP_DISCOURSE",
        "RECAP_TRENDS",
        "RECAP_DRIVERS_BULLETS",
        "DATA_SOURCE",
        "DATA_PERIOD",
        "SAMPLE_SIZE",
        "EFFECTIVE_VOLUME",
        "NATURE",
        "RISK_LEVEL",
        "EVENT_BACKGROUND",
        "5W_WHO",
        "5W_WHAT",
        "5W_WHERE",
        "5W_WHEN",
        "5W_WHY",
        "SENTIMENT_ANALYSIS",
        "TREND_ANALYSIS",
        "THEORY_RISK",
        "STRATEGY_RISK",
        "STRATEGY_SHORT",
        "STRATEGY_GUIDE",
        "STRATEGY_LONG",
        "AUTHOR",
        "DEPARTMENT",
        "GEN_TIME",
    }
)

_LIST_PLACEHOLDER_KEYS = {
    "SUMMARY_BULLETS",
    "CHART_SENTIMENT_ANALYSIS",
    "CHART_TIMELINE_ANALYSIS",
    "CHART_VOLUME_ANALYSIS",
    "CHART_REGION_ANALYSIS",
    "CHART_AUTHOR_ANALYSIS",
    "CHART_KEYWORD_ANALYSIS",
    "CHART_RADAR_ANALYSIS",
    "CHART_LIFECYCLE_ANALYSIS",
    "RESPONSE_ANALYSIS_BULLETS",
    "RECAP_DRIVERS_BULLETS",
}


def _json_hash(value: Any) -> str:
    try:
        raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    except Exception:
        raw = str(value)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _clean_text(value: Any, limit: int = 0) -> str:
    text = str(value or "").strip()
    return text[:limit] if limit and len(text) > limit else text


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _first_text(mapping: Dict[str, Any], keys: Iterable[str], limit: int = 0) -> str:
    for key in keys:
        text = _clean_text(mapping.get(key), limit=limit)
        if text:
            return text
    return ""


def _unwrap_payload(value: Any) -> Any:
    if isinstance(value, dict):
        result = value.get("result")
        if result not in (None, ""):
            return result
        data = value.get("data")
        if data not in (None, ""):
            return data
    return value


def _as_list(value: Any) -> List[Any]:
    value = _unwrap_payload(value)
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in ["items", "rows", "entries", "data", "top_items", "events", "timeline", "cards", "evidence_cards", "metrics", "keywords", "actors"]:
            nested = value.get(key)
            if isinstance(nested, list):
                return nested
    return []


def _as_dict(value: Any) -> Dict[str, Any]:
    value = _unwrap_payload(value)
    return value if isinstance(value, dict) else {}


def _iter_dicts(value: Any) -> List[Dict[str, Any]]:
    return [dict(item) for item in _as_list(value) if isinstance(item, dict)]


def _find_named_payload(state: Dict[str, Any], name: str) -> Any:
    candidates: List[Any] = [state]
    payload = state.get("payload") if isinstance(state.get("payload"), dict) else {}
    report_ir = state.get("report_ir") if isinstance(state.get("report_ir"), dict) else {}
    candidates.extend([payload, report_ir])
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    candidates.append(metadata)
    for source in candidates:
        if not isinstance(source, dict):
            continue
        if name in source:
            return source.get(name)
        json_key = f"{name}.json"
        if json_key in source:
            return source.get(json_key)
        state_map = source.get("state") if isinstance(source.get("state"), dict) else {}
        if name in state_map:
            return state_map.get(name)
        if json_key in state_map:
            return state_map.get(json_key)
        artifacts = source.get("artifacts") if isinstance(source.get("artifacts"), dict) else {}
        if name in artifacts:
            return artifacts.get(name)
        if json_key in artifacts:
            return artifacts.get(json_key)
    return None


def _keyword_pos(word: str) -> str:
    text = _clean_text(word)
    if any(token in text for token in ["北京", "上海", "广东", "浙江", "江苏", "四川", "山东", "湖北", "河南", "福建", "站台", "校园"]):
        return "地名"
    if any(token in text for token in ["监管", "执法", "投诉", "劝阻", "回应", "处置", "扩散", "治理"]):
        return "动词"
    if any(token in text for token in ["严重", "明显", "高频", "焦虑", "负面", "正面"]):
        return "形容词"
    return "名词"


def _normalize_label(text: Any) -> str:
    raw = _clean_text(text).lower()
    if not raw:
        return ""
    if raw in {"positive", "pos", "正向", "正面", "支持", "积极"} or "正面" in raw or "支持" in raw:
        return "正面"
    if raw in {"negative", "neg", "负向", "负面", "反对", "消极"} or "负面" in raw or "反对" in raw:
        return "负面"
    return "中立"


def _month_bucket(text: str) -> str:
    raw = _clean_text(text)
    if not raw:
        return ""
    match = re.search(r"(20\d{2})[-/.年](\d{1,2})", raw)
    if match:
        return f"{int(match.group(2))}月"
    match = re.search(r"(^|\D)(\d{1,2})月", raw)
    if match:
        return f"{int(match.group(2))}月"
    return raw[:10]


def _top_counts(rows: Iterable[Tuple[str, int]], limit: int = 12) -> List[Dict[str, Any]]:
    totals: Dict[str, int] = {}
    for name, value in rows:
        clean = _clean_text(name)
        if not clean or clean in {"未知", "无", "—"}:
            continue
        totals[clean] = totals.get(clean, 0) + max(0, _safe_int(value, 1))
    return [
        {"name": name, "value": value}
        for name, value in sorted(totals.items(), key=lambda item: item[1], reverse=True)[:limit]
    ]


def _rows_from_figure(figure: Dict[str, Any]) -> List[Dict[str, Any]]:
    dataset = figure.get("dataset") if isinstance(figure.get("dataset"), dict) else {}
    rows = dataset.get("rows") or dataset.get("preview_rows")
    if isinstance(rows, list):
        return [dict(item) for item in rows if isinstance(item, dict)]
    return []


def _figure_text(figure: Dict[str, Any]) -> str:
    return " ".join(
        str(part or "")
        for part in [
            figure.get("figure_id"),
            figure.get("caption"),
            figure.get("placement_anchor"),
            ((figure.get("chart_spec") or {}).get("chart_type") if isinstance(figure.get("chart_spec"), dict) else ""),
        ]
    ).lower()


def _normal_rows(rows: List[Dict[str, Any]], limit: int = 20) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for item in rows:
        name = _clean_text(item.get("name") or item.get("label") or item.get("word") or item.get("province") or item.get("author"))
        value = item.get("value")
        if value is None:
            value = item.get("count") or item.get("score")
        if name:
            out.append({"name": name, "value": _safe_int(value)})
    out.sort(key=lambda row: row["value"], reverse=True)
    return out[:limit]


def _extract_figures(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    candidates: List[Any] = []
    for source in [
        state.get("report_ir"),
        state.get("payload"),
        (state.get("payload") or {}).get("artifact_manifest") if isinstance(state.get("payload"), dict) else {},
    ]:
        if isinstance(source, dict):
            candidates.extend(source.get("figures") if isinstance(source.get("figures"), list) else [])
            candidates.extend(source.get("figure_artifacts") if isinstance(source.get("figure_artifacts"), list) else [])
    seen: set[str] = set()
    figures: List[Dict[str, Any]] = []
    for item in candidates:
        if not isinstance(item, dict):
            continue
        key = str(item.get("figure_id") or item.get("dataset_ref") or _json_hash(item)).strip()
        if key in seen:
            continue
        seen.add(key)
        figures.append(item)
    return figures


def _build_volume_from_bundle(state: Dict[str, Any]) -> tuple[List[str], List[int]]:
    bundle = state.get("draft_bundle_v2") if isinstance(state.get("draft_bundle_v2"), dict) else {}
    units = bundle.get("units") if isinstance(bundle.get("units"), list) else []
    section_counts: Dict[str, int] = {}
    for unit in units:
        if not isinstance(unit, dict):
            continue
        section = _clean_text(unit.get("section_id") or unit.get("section_title") or "正文")
        section_counts[section] = section_counts.get(section, 0) + 1
    if section_counts:
        return list(section_counts.keys())[:12], list(section_counts.values())[:12]
    return ["正文"], [1 if _clean_text(state.get("final_markdown_current") or state.get("markdown")) else 0]


def _build_lifecycle(dates: List[str], values: List[int]) -> Dict[str, Any]:
    if not dates:
        dates = ["正文"]
        values = [0]
    max_v = max(values or [0]) or 1
    stages = []
    for value in values:
        if value >= max_v * 0.8:
            stages.append("爆发")
        elif value >= max_v * 0.35:
            stages.append("扩散")
        else:
            stages.append("潜伏")
    boundaries = []
    for index in range(1, len(stages)):
        if stages[index] != stages[index - 1]:
            boundaries.append({"xAxis": dates[index], "name": f"{stages[index - 1]}→{stages[index]}"})
    return {"dates": dates, "values": values, "stages": stages, "boundaries": boundaries}


def _evidence_cards_from_state(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    cards = _iter_dicts(_find_named_payload(state, "evidence_cards"))
    if cards:
        return cards
    report_ir = state.get("report_ir") if isinstance(state.get("report_ir"), dict) else {}
    ledger = report_ir.get("evidence_ledger") if isinstance(report_ir.get("evidence_ledger"), dict) else {}
    return _iter_dicts(ledger.get("entries"))


def _timeline_nodes_from_state(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    nodes = _iter_dicts(_find_named_payload(state, "timeline_nodes"))
    if nodes:
        return nodes
    report_ir = state.get("report_ir") if isinstance(state.get("report_ir"), dict) else {}
    return _iter_dicts(report_ir.get("timeline") or report_ir.get("timeline_nodes"))


def _metric_rows_from_state(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = _iter_dicts(_find_named_payload(state, "metrics_bundle"))
    if rows:
        return rows
    report_ir = state.get("report_ir") if isinstance(state.get("report_ir"), dict) else {}
    return _iter_dicts(report_ir.get("metrics") or report_ir.get("metric_bundle"))


def _actor_rows_from_state(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = _iter_dicts(_find_named_payload(state, "actor_positions"))
    if rows:
        return rows
    report_ir = state.get("report_ir") if isinstance(state.get("report_ir"), dict) else {}
    conflict = report_ir.get("conflict_map") if isinstance(report_ir.get("conflict_map"), dict) else {}
    return _iter_dicts(conflict.get("actor_positions") or report_ir.get("actor_positions"))


def _event_analysis_from_state(state: Dict[str, Any]) -> Dict[str, Any]:
    return _as_dict(_find_named_payload(state, "event_analysis"))


def _normalized_task_from_state(state: Dict[str, Any]) -> Dict[str, Any]:
    return _as_dict(_find_named_payload(state, "normalized_task"))


def _sentiment_rows_from_state(state: Dict[str, Any], cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    analysis_rows = _iter_dicts(_find_named_payload(state, "analysis_attitude"))
    if analysis_rows:
        counts: Dict[str, int] = {}
        for item in analysis_rows:
            label = _normalize_label(item.get("name") or item.get("label"))
            if label:
                counts[label] = counts.get(label, 0) + _safe_int(item.get("value") or item.get("count"), 0)
        colors = {"正面": "#1e90ff", "中立": "#22c55e", "负面": "#ef4444"}
        return [
            {"value": counts.get(label, 0), "name": label, "itemStyle": {"color": colors[label]}}
            for label in ["正面", "中立", "负面"]
            if counts.get(label, 0) > 0
        ]
    analysis = _event_analysis_from_state(state)
    sentiment = analysis.get("sentiment_summary") if isinstance(analysis.get("sentiment_summary"), dict) else {}
    counts: Dict[str, int] = {}
    for key, value in sentiment.items():
        label = _normalize_label(key)
        if label:
            if isinstance(value, dict):
                value = value.get("count") or value.get("value") or value.get("total")
            counts[label] = counts.get(label, 0) + _safe_int(value, 0)
    for card in cards:
        label = _normalize_label(_first_text(card, ["sentiment", "attitude", "emotion", "stance", "polarity"]))
        if label:
            counts[label] = counts.get(label, 0) + 1
    if not counts and cards:
        counts["中立"] = len(cards)
    colors = {"正面": "#1e90ff", "中立": "#22c55e", "负面": "#ef4444"}
    return [
        {"value": counts.get(label, 0), "name": label, "itemStyle": {"color": colors[label]}}
        for label in ["正面", "中立", "负面"]
        if counts.get(label, 0) > 0
    ]


def _volume_series_from_state(
    state: Dict[str, Any],
    cards: List[Dict[str, Any]],
    timeline_nodes: List[Dict[str, Any]],
    metric_rows: List[Dict[str, Any]],
) -> Tuple[List[str], List[int]]:
    analysis_rows = _iter_dicts(_find_named_payload(state, "analysis_trends"))
    if analysis_rows:
        rows = [
            (_first_text(item, ["date", "time", "name", "label", "period"], limit=20), _safe_int(item.get("value") or item.get("count"), 0))
            for item in analysis_rows
        ]
        rows = [(name, value) for name, value in rows if name]
        if rows:
            return [name for name, _ in rows[:360]], [value for _, value in rows[:360]]
    metric_points: List[Tuple[str, int]] = []
    for row in metric_rows:
        date = _first_text(row, ["date", "day", "time", "month", "name", "label", "period"])
        value = row.get("value")
        if value is None:
            value = row.get("count") or row.get("volume") or row.get("total") or row.get("mentions")
        if date and value is not None:
            metric_points.append((_month_bucket(date), _safe_int(value, 0)))
    if metric_points:
        rows = list(reversed(_top_counts(metric_points, limit=18)))
        return [row["name"] for row in rows], [row["value"] for row in rows]

    points: List[Tuple[str, int]] = []
    for row in timeline_nodes:
        date = _month_bucket(_first_text(row, ["time", "date", "occurred_at", "published_at", "period"]))
        if date:
            points.append((date, 1))
    for card in cards:
        date = _month_bucket(_first_text(card, ["published_at", "created_at", "date", "time", "publish_time"]))
        if date:
            points.append((date, 1))
    rows = list(reversed(_top_counts(points, limit=18))) if points else []
    if rows:
        return [row["name"] for row in rows], [row["value"] for row in rows]
    return _build_volume_from_bundle(state)


def _region_rows_from_cards(cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = []
    for card in cards:
        region = _first_text(card, ["province", "region", "location", "city", "area"])
        if not region:
            region = _first_text(card, ["platform", "source_platform"])
        if region:
            rows.append((region, 1))
    return _top_counts(rows, limit=10)


def _region_rows_from_state(state: Dict[str, Any], cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = _normal_rows(_iter_dicts(_find_named_payload(state, "analysis_geography")), limit=12)
    return rows or _region_rows_from_cards(cards)


def _author_rows_from_cards(cards: List[Dict[str, Any]], actors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Tuple[str, int]] = []
    for actor in actors:
        name = _first_text(actor, ["actor", "actor_name", "name", "label", "subject"])
        value = actor.get("count") or actor.get("evidence_count") or actor.get("mentions") or 1
        if name:
            rows.append((name, _safe_int(value, 1)))
    for card in cards:
        name = _first_text(card, ["author", "account", "source", "media", "source_name", "publisher"])
        if name:
            rows.append((name, 1))
    return _top_counts(rows, limit=10)


def _author_rows_from_state(state: Dict[str, Any], cards: List[Dict[str, Any]], actors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows = _normal_rows(_iter_dicts(_find_named_payload(state, "analysis_publishers")), limit=12)
    return rows or _author_rows_from_cards(cards, actors)


def _keyword_rows_from_state(state: Dict[str, Any], cards: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Tuple[str, int]] = []
    for item in _iter_dicts(_find_named_payload(state, "analysis_keywords")):
        name = _first_text(item, ["name", "label", "word", "keyword", "term"])
        if name:
            rows.append((name, _safe_int(item.get("value") or item.get("count"), 1)))
    analysis = _event_analysis_from_state(state)
    keywords = analysis.get("keywords")
    if isinstance(keywords, dict):
        keyword_items = keywords.get("items") or keywords.get("top_keywords") or keywords.get("terms") or []
        if isinstance(keyword_items, dict):
            rows.extend((str(key), _safe_int(value, 1)) for key, value in keyword_items.items())
        elif isinstance(keyword_items, list):
            for item in keyword_items:
                if isinstance(item, dict):
                    rows.append((_first_text(item, ["word", "term", "name", "keyword"]), _safe_int(item.get("count") or item.get("value"), 1)))
                else:
                    rows.append((str(item), 1))
    elif isinstance(keywords, list):
        for item in keywords:
            if isinstance(item, dict):
                rows.append((_first_text(item, ["word", "term", "name", "keyword"]), _safe_int(item.get("count") or item.get("value"), 1)))
            else:
                rows.append((str(item), 1))

    normalized = _normalized_task_from_state(state)
    for word in normalized.get("keywords") if isinstance(normalized.get("keywords"), list) else []:
        rows.append((str(word), 3))
    for card in cards:
        card_keywords = card.get("keywords")
        if isinstance(card_keywords, list):
            rows.extend((str(word), 1) for word in card_keywords)
        elif isinstance(card_keywords, str):
            rows.extend((word.strip(), 1) for word in re.split(r"[,，、\s]+", card_keywords) if word.strip())
        text = " ".join(str(card.get(key) or "") for key in ["title", "snippet", "content", "summary"])
        for word in re.findall(r"[\u4e00-\u9fff]{2,8}", text):
            if word not in {"报告", "舆情", "分析", "当前", "需要", "建议", "可能", "进行", "相关"}:
                rows.append((word, 1))

    if not rows:
        markdown = _clean_text(state.get("final_markdown_current") or state.get("markdown"))
        for word in re.findall(r"[\u4e00-\u9fff]{2,8}", markdown):
            if word not in {"报告", "舆情", "分析", "当前", "需要", "建议", "可能"}:
                rows.append((word, 1))

    top = _top_counts(rows, limit=120)
    return [{"name": row["name"], "value": row["value"], "pos": _keyword_pos(row["name"])} for row in top]


def _timeline_output(timeline_nodes: List[Dict[str, Any]], dates: List[str], values: List[int]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for item in timeline_nodes[:25]:
        time = _first_text(item, ["time", "date", "occurred_at", "period"], limit=32) or "—"
        event = _first_text(item, ["event", "title", "summary", "description", "content"], limit=160) or "—"
        out.append({"time": time, "event": event})
    if out:
        return out
    return [{"time": date, "event": f"声量/证据记录 {value} 条"} for date, value in zip(dates, values)] or [{"time": "—", "event": "证据不足"}]


def _build_report_data(state: Dict[str, Any]) -> Dict[str, Any]:
    figures = _extract_figures(state)
    sentiment_rows: List[Dict[str, Any]] = []
    keyword_rows: List[Dict[str, Any]] = []
    region_rows: List[Dict[str, Any]] = []
    author_rows: List[Dict[str, Any]] = []
    for figure in figures:
        rows = _normal_rows(_rows_from_figure(figure), limit=120)
        if not rows:
            continue
        text = _figure_text(figure)
        if any(token in text for token in ["sentiment", "attitude", "情感", "态度", "倾向"]):
            sentiment_rows = [{**row, "name": _normalize_label(row.get("name"))} for row in rows[:8]]
        elif any(token in text for token in ["keyword", "word", "关键词", "词云"]):
            keyword_rows = rows[:120]
        elif any(token in text for token in ["region", "province", "地域", "地区", "省"]):
            region_rows = rows[:12]
        elif any(token in text for token in ["author", "account", "作者", "账号"]):
            author_rows = rows[:12]
    cards = _evidence_cards_from_state(state)
    timeline_nodes = _timeline_nodes_from_state(state)
    metric_rows = _metric_rows_from_state(state)
    actor_rows = _actor_rows_from_state(state)
    dates, values = _volume_series_from_state(state, cards, timeline_nodes, metric_rows)
    if not sentiment_rows:
        sentiment_rows = _sentiment_rows_from_state(state, cards)
    if not region_rows:
        region_rows = _region_rows_from_state(state, cards)
    if not author_rows:
        author_rows = _author_rows_from_state(state, cards, actor_rows)
    if not keyword_rows:
        keyword_rows = _keyword_rows_from_state(state, cards)
    return {
        "charts": {
            "sentiment": sentiment_rows or [{"value": 1, "name": "中性", "itemStyle": {"color": "#22c55e"}}],
            "volume": {"dates": dates or ["正文"], "values": values or [0]},
            "region": {"names": [row["name"] for row in region_rows] or ["证据不足"], "values": [row["value"] for row in region_rows] or [0]},
            "author": {"names": [row["name"] for row in author_rows] or ["证据不足"], "values": [row["value"] for row in author_rows] or [0]},
            "keyword": keyword_rows or [{"name": "证据不足", "value": 0}],
            "radarValues": [max(2, min(10, len(figures) + 2)), max(2, min(10, len(keyword_rows) // 5 or 2)), 4, 5, max(2, min(10, max(values or [0])) )],
            "lifecycle": _build_lifecycle(dates, values),
        },
        "timeline": _timeline_output(timeline_nodes, dates, values),
    }


def _build_meta(state: Dict[str, Any], report_data: Dict[str, Any]) -> Dict[str, str]:
    task = state.get("task") if isinstance(state.get("task"), dict) else {}
    report_ir = state.get("report_ir") if isinstance(state.get("report_ir"), dict) else {}
    topic = _clean_text(task.get("topic_label") or task.get("topic_identifier") or ((report_ir.get("meta") or {}).get("topic_label") if isinstance(report_ir.get("meta"), dict) else "") or "舆情分析报告")
    dates = list((report_data.get("charts") or {}).get("volume", {}).get("dates", []) or [])
    values = list((report_data.get("charts") or {}).get("volume", {}).get("values", []) or [])
    total = sum(_safe_int(item) for item in values)
    return {
        "REPORT_TITLE": topic,
        "REPORT_SUBTITLE": "基于正式文稿与中间分析产物生成",
        "EVENT_TYPE": _clean_text(((state.get("scene_profile") or {}).get("scene_label") if isinstance(state.get("scene_profile"), dict) else "") or "舆情事件"),
        "OBJECT_NAME": topic[:30],
        "DATA_PERIOD": f"{dates[0]} 至 {dates[-1]}" if dates else "证据不足",
        "SAMPLE_SIZE": str(total or "—"),
        "EFFECTIVE_VOLUME": str(total or "—"),
        "GEN_TIME": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "DATA_SOURCE": "调研产物、中间 JSON、正式 Markdown",
    }


def _plain_markdown_summary(value: Any, limit: int = 360) -> str:
    text = _clean_text(value)
    text = re.sub(r"```.*?```", " ", text, flags=re.S)
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.M)
    text = re.sub(r"^\s*[-*+]\s*", "", text, flags=re.M)
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit].strip()


def _top_names(rows: List[Dict[str, Any]], limit: int = 3) -> List[str]:
    out: List[str] = []
    for row in rows[:limit]:
        name = _clean_text(row.get("name") if isinstance(row, dict) else "")
        if name and name not in out:
            out.append(name)
    return out


def _safe_join(items: Iterable[str], fallback: str) -> str:
    values = [_clean_text(item) for item in items if _clean_text(item)]
    return "、".join(values) if values else fallback


def _first_event_summary(cards: List[Dict[str, Any]], timeline: List[Dict[str, Any]]) -> str:
    if timeline:
        first = timeline[0]
        event = _first_text(first, ["event", "title", "summary", "description", "content"], limit=120)
        time = _first_text(first, ["time", "date", "occurred_at", "period"], limit=24)
        if event:
            return f"{time + '，' if time else ''}{event}"
    if cards:
        first = cards[0]
        title = _first_text(first, ["title", "summary"], limit=80)
        snippet = _first_text(first, ["snippet", "content"], limit=100)
        if title and snippet:
            return f"{title}：{snippet}"
        return title or snippet
    return ""


def _default_narrative(state: Dict[str, Any], meta: Dict[str, str], report_data: Dict[str, Any]) -> Dict[str, Any]:
    markdown = _plain_markdown_summary(state.get("final_markdown_current") or state.get("markdown"), 520)
    title = meta.get("REPORT_TITLE") or "舆情分析报告"
    cards = _evidence_cards_from_state(state)
    timeline_nodes = _timeline_nodes_from_state(state)
    charts = report_data.get("charts") if isinstance(report_data.get("charts"), dict) else {}
    sentiment_rows = charts.get("sentiment") if isinstance(charts.get("sentiment"), list) else []
    keyword_rows = charts.get("keyword") if isinstance(charts.get("keyword"), list) else []
    timeline = report_data.get("timeline") if isinstance(report_data.get("timeline"), list) else []
    volume = charts.get("volume") if isinstance(charts.get("volume"), dict) else {}
    regions = charts.get("region") if isinstance(charts.get("region"), dict) else {}
    authors = charts.get("author") if isinstance(charts.get("author"), dict) else {}
    dates = list(volume.get("dates") or [])
    values = [_safe_int(item) for item in list(volume.get("values") or [])]
    total = sum(values)
    peak_index = max(range(len(values)), key=lambda index: values[index]) if values else -1
    peak_text = f"{dates[peak_index]}达到阶段峰值（{values[peak_index]}）" if peak_index >= 0 and peak_index < len(dates) else ""
    top_sentiment = ""
    sentiment_total = sum(_safe_int(row.get("value")) for row in sentiment_rows if isinstance(row, dict))
    if sentiment_total:
        top = max((row for row in sentiment_rows if isinstance(row, dict)), key=lambda row: _safe_int(row.get("value")))
        top_sentiment = f"{_clean_text(top.get('name'))}占比约{round(_safe_int(top.get('value')) * 100.0 / sentiment_total, 1)}%"
    top_keywords = _top_names(keyword_rows, 6)
    trigger = _first_event_summary(cards, timeline_nodes)
    if not trigger and top_keywords:
        trigger = f"{_safe_join(top_keywords[:3], title)}等议题推动讨论扩散。"
    background = markdown or f"{title}围绕{_safe_join(top_keywords[:4], '核心议题')}展开，需结合证据卡、时间线和声量指标持续跟踪。"
    summary_bullets = [
        f"本轮样本有效声量约 {total or meta.get('EFFECTIVE_VOLUME', '—')}，重点集中在{_safe_join(top_keywords[:4], '核心控烟议题')}。",
        f"舆情触发点来自{trigger}" if trigger else f"舆情触发点集中在{_safe_join(top_keywords[:3], '公共场所控烟')}。",
        f"情绪结构显示{top_sentiment}，需优先处理高敏投诉和治理反馈。" if top_sentiment else "情绪结构以治理诉求和公共健康关切为主。",
        "报告已保留证据、图表数据与正式文稿的来源链路。",
    ]
    region_names = [str(item) for item in list(regions.get("names") or [])[:4]]
    author_names = [str(item) for item in list(authors.get("names") or [])[:4]]
    lifecycle = charts.get("lifecycle") if isinstance(charts.get("lifecycle"), dict) else {}
    stages = list(lifecycle.get("stages") or []) if isinstance(lifecycle.get("stages"), list) else []
    title = meta.get("REPORT_TITLE") or "舆情分析报告"
    return {
        "REPORT_TITLE": title,
        "REPORT_SUBTITLE": meta.get("REPORT_SUBTITLE", ""),
        "EVENT_TYPE": meta.get("EVENT_TYPE", "舆情事件"),
        "OBJECT_NAME": meta.get("OBJECT_NAME", title[:30]),
        "PHASE_STATUS": f"{stages[-1]}期" if stages else "持续扩散期",
        "KPI_TOTAL": meta.get("SAMPLE_SIZE", "—"),
        "KPI_EFFECTIVE": meta.get("EFFECTIVE_VOLUME", "—"),
        "KPI_POS_RATIO": top_sentiment or "持续观察",
        "KPI_NEG_RATIO": f"{stages[-1]}期" if stages else "治理响应期",
        "INTRO_BACKGROUND": background,
        "INTRO_TRIGGERS": trigger or f"{_safe_join(top_keywords[:3], '控烟相关议题')}形成传播触发点。",
        "SUMMARY_BULLETS": summary_bullets,
        "CHART_SENTIMENT_ANALYSIS": [
            f"情绪分布以{top_sentiment}为主要特征。" if top_sentiment else "情绪分布呈现多元诉求。",
            "负面讨论通常围绕被动吸烟、劝阻无效和反馈不及时展开。",
            "正向讨论主要来自科普宣传、地方治理动作和未成年人保护倡议。",
        ],
        "CHART_TIMELINE_ANALYSIS": [
            f"时间线显示，{_first_event_summary(cards, timeline_nodes) or '前期讨论已形成可追踪节点'}",
            f"当前共识别 {len(timeline)} 个关键节点，适合按月复盘治理动作。",
            "后续应关注投诉事件是否从个案扩散为制度执行讨论。",
        ],
        "CHART_VOLUME_ANALYSIS": [
            peak_text or "声量指标已形成阶段性波动。",
            f"累计有效声量约 {total}，可用于定位传播高峰。" if total else "声量仍需结合更多样本持续观察。",
            "峰值节点应回查对应证据卡，确认是否由突发事件或政策节点驱动。",
        ],
        "CHART_REGION_ANALYSIS": [
            f"地域分布集中在{_safe_join(region_names, '重点地区')}。",
            "地域差异可反映线下执法密度、公共场所管理和媒体曝光差异。",
            "建议把高频地区与投诉场景交叉核对，区分全国性议题和地方事件。",
        ],
        "CHART_AUTHOR_ANALYSIS": [
            f"主要参与主体包括{_safe_join(author_names, '媒体、政务账号和公众用户')}。",
            "媒体与政务账号负责议题放大和政策解释，公众账号提供现场体验反馈。",
            "需关注高影响主体是否推动议题从生活投诉转向治理问责。",
        ],
        "CHART_KEYWORD_ANALYSIS": [
            f"关键词集中在{_safe_join(top_keywords[:6], '核心议题')}。",
            "词云显示控烟议题同时覆盖场景、对象和治理动作。",
            "后续可按关键词簇拆分为交通枢纽、餐饮空间、未成年人保护和电子烟监管等子议题。",
        ],
        "CHART_RADAR_ANALYSIS": [
            "雷达指标用于呈现证据丰富度、议题集中度、扩散强度和治理敏感度。",
            "当前样本已能支撑基础图表和报告概览。",
            "若进入正式研判，应继续补齐平台差异和主体立场交叉验证。",
        ],
        "CHART_LIFECYCLE_ANALYSIS": [
            f"生命周期判断为{stages[-1]}期。" if stages else "生命周期仍处于持续观察阶段。",
            "若声量高峰后仍有投诉和媒体跟进，议题可能进入治理问责阶段。",
            "处置节奏应覆盖提示、巡查、反馈和复盘四个环节。",
        ],
        "THEORY_SILENCE": "少数现场投诉可能因反馈链条不清而放大沉默螺旋，公众会用线上曝光替代线下申诉。",
        "THEORY_AGENDA": "媒体、政务账号和公共健康节点共同塑造议程，把个体体验转化为公共治理议题。",
        "THEORY_BUTTERFLY": "单个场景的劝阻争议可能触发跨平台扩散，并带动对法规执行和场所责任的连锁讨论。",
        "RESPONSE_ANALYSIS_BULLETS": [
            "优先回应高频场景，明确控烟提示、巡查频次和投诉反馈时限。",
            "对电子烟和未成年人保护议题，应同步给出监管依据和线索处置入口。",
            "在声量峰值后复盘传播源和关键节点，避免同类场景反复触发。",
        ],
        "RECAP_DISCOURSE": background[:260],
        "RECAP_TRENDS": peak_text or f"{title}仍会围绕公共场所执行、电子烟监管和健康科普持续发酵。",
        "RECAP_DRIVERS_BULLETS": [
            f"场景驱动：{_safe_join(top_keywords[:3], '公共场所控烟')}持续提供讨论入口。",
            "情绪驱动：被动吸烟体验和投诉反馈影响公众耐心。",
            "治理驱动：政策解释、现场执法和平台传播共同决定议题走向。",
        ],
    }


def _analysis_text_from_state(state: Dict[str, Any]) -> str:
    parts = ["## 正式 Markdown\n", _clean_text(state.get("final_markdown_current") or state.get("markdown"), 20000)]
    for name in [
        "report_ir",
        "draft_bundle_v2",
        "validation_result_v2",
        "repair_plan_v2",
        "graph_state_v2",
        "section_markdown_manifest",
        "section_trace_annotations",
        "factual_conformance",
    ]:
        value = state.get(name)
        if value:
            parts.append(f"\n## 文件: {name}.json\n")
            parts.append(_clean_text(json.dumps(value, ensure_ascii=False, indent=2), 12000))
    return "\n".join(parts)


def _parse_json_object(text: str) -> Dict[str, Any]:
    raw = str(text or "").strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\s*```\s*$", "", raw)
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        parsed = json.loads(raw[start : end + 1])
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _call_narrative_model(state: Dict[str, Any], meta: Dict[str, str], warnings: List[str]) -> Dict[str, Any]:
    if not _FILL_PROMPT_PATH.is_file():
        warnings.append("html_template_fill_prompt_missing")
        return {}
    llm, _ = build_langchain_chat_model(task="report", model_role="report", temperature=0.15, max_tokens=4800, timeout=180, max_retries=2)
    if llm is None:
        warnings.append("report_llm_unavailable")
        return {}
    prompt_template = _FILL_PROMPT_PATH.read_text(encoding="utf-8")
    prompt = (
        prompt_template.replace("{event_introduction}", meta.get("REPORT_TITLE", ""))
        .replace("{analysis_results}", _analysis_text_from_state(state))
        .replace("{methodology}", "沿用当前项目报告技能、模板和证据边界要求。")
        .replace("{meta_json}", json.dumps(meta, ensure_ascii=False, indent=2))
    )
    try:
        response = llm.invoke(
            [
                SystemMessage(content="你只输出一个 JSON 对象，键名必须与用户要求完全一致，不要输出其它任何字符。"),
                HumanMessage(content=prompt),
            ]
        )
        return _parse_json_object(getattr(response, "content", response))
    except Exception as exc:
        warnings.append(f"narrative_llm_failed:{type(exc).__name__}")
        return {}


def _to_bulleted_list_html(value: Any) -> str:
    items = value if isinstance(value, list) else [value]
    clean = [_clean_text(item) for item in items if _clean_text(item)]
    if not clean:
        clean = ["证据不足"]
    return "".join(f"<li>{html.escape(item, quote=True)}</li>" for item in clean[:8])


def _merge_template(template_html: str, text_map: Dict[str, Any], report_data: Dict[str, Any]) -> str:
    out = template_html.replace(REPORT_CONFIG_ANCHOR, json.dumps({}, ensure_ascii=False, separators=(",", ":")))
    out = out.replace(REPORT_DATA_ANCHOR, json.dumps(report_data, ensure_ascii=False, separators=(",", ":")))
    for key in _PLACEHOLDER_KEYS:
        token = "{{" + key + "}}"
        value = text_map.get(key, "—")
        if key in _LIST_PLACEHOLDER_KEYS:
            out = out.replace(token, _to_bulleted_list_html(value))
        else:
            out = out.replace(token, html.escape(_clean_text(value), quote=True))
    return out


def _sanitize_html(html_text: str) -> str:
    text = str(html_text or "").strip()
    text = re.sub(r"^```(?:html)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```\s*$", "", text)
    return text.strip()


def build_html_report_artifact(state: Dict[str, Any]) -> Dict[str, Any]:
    warnings: List[str] = []
    if not _TEMPLATE_PATH.is_file():
        raise FileNotFoundError(f"HTML report template missing: {_TEMPLATE_PATH}")
    report_data = _build_report_data(state)
    meta = _build_meta(state, report_data)
    defaults = _default_narrative(state, meta, report_data)
    narrative = _call_narrative_model(state, meta, warnings)
    text_map: Dict[str, Any] = dict(defaults)
    for key, value in narrative.items():
        if key in _PLACEHOLDER_KEYS and value is not None:
            text_map[key] = value
    text_map.update(meta)
    text_map["KPI_TOTAL"] = meta.get("SAMPLE_SIZE", "—")
    text_map["KPI_EFFECTIVE"] = meta.get("EFFECTIVE_VOLUME", "—")
    lifecycle = report_data.get("charts", {}).get("lifecycle", {}) if isinstance(report_data.get("charts"), dict) else {}
    stages = lifecycle.get("stages") if isinstance(lifecycle, dict) and isinstance(lifecycle.get("stages"), list) else []
    if stages:
        text_map["PHASE_STATUS"] = f"{stages[-1]}期"
        text_map["KPI_NEG_RATIO"] = text_map["PHASE_STATUS"]
    sentiment_rows = report_data.get("charts", {}).get("sentiment", []) if isinstance(report_data.get("charts"), dict) else []
    total_sentiment = sum(_safe_int(row.get("value")) for row in sentiment_rows if isinstance(row, dict))
    if total_sentiment > 0:
        top = max((row for row in sentiment_rows if isinstance(row, dict)), key=lambda row: _safe_int(row.get("value")))
        text_map["KPI_POS_RATIO"] = f"{_clean_text(top.get('name')) or '中立'}（{round(_safe_int(top.get('value')) * 100.0 / total_sentiment, 1)}%）"
    template_html = _TEMPLATE_PATH.read_text(encoding="utf-8")
    html_text = _sanitize_html(_merge_template(template_html, text_map, report_data))
    input_digests = {
        name: _json_hash(state.get(name))
        for name in [
            "report_ir",
            "draft_bundle_v2",
            "validation_result_v2",
            "repair_plan_v2",
            "graph_state_v2",
            "section_markdown_manifest",
            "section_trace_annotations",
            "factual_conformance",
        ]
        if state.get(name) is not None
    }
    input_digests["markdown"] = hashlib.sha256(_clean_text(state.get("final_markdown_current") or state.get("markdown")).encode("utf-8")).hexdigest()[:16]
    return {
        "html": html_text,
        "renderer_version": RENDERER_VERSION,
        "source_artifact_ids": [
            "full_markdown",
            "report_ir",
            "draft_bundle_v2",
            "validation_result_v2",
            "repair_plan_v2",
            "graph_state_v2",
            "section_markdown_manifest",
            "section_trace_annotations",
        ],
        "input_digests": input_digests,
        "byte_length": len(html_text.encode("utf-8")),
        "warnings": warnings,
        "template": "report_html_morandi_template.html",
        "narrative_source": "llm_placeholder_json" if narrative else "default_placeholder_json",
        "report_data_summary": {
            "sentiment_count": len(report_data.get("charts", {}).get("sentiment", []) if isinstance(report_data.get("charts"), dict) else []),
            "volume_points": len(report_data.get("charts", {}).get("volume", {}).get("dates", []) if isinstance(report_data.get("charts"), dict) else []),
            "keyword_count": len(report_data.get("charts", {}).get("keyword", []) if isinstance(report_data.get("charts"), dict) else []),
            "timeline_count": len(report_data.get("timeline", []) if isinstance(report_data.get("timeline"), list) else []),
        },
    }
