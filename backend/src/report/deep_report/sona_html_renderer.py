from __future__ import annotations

import hashlib
import html
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from ...utils.ai import build_langchain_chat_model


REPORT_CONFIG_ANCHOR = "__REPORT_CONFIG_JSON__"
REPORT_DATA_ANCHOR = "__REPORT_JSON_DATA__"
RENDERER_VERSION = "sona-html-artifact.v1"

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
            sentiment_rows = rows[:8]
        elif any(token in text for token in ["keyword", "word", "关键词", "词云"]):
            keyword_rows = rows[:120]
        elif any(token in text for token in ["region", "province", "地域", "地区", "省"]):
            region_rows = rows[:12]
        elif any(token in text for token in ["author", "account", "作者", "账号"]):
            author_rows = rows[:12]
    dates, values = _build_volume_from_bundle(state)
    if not keyword_rows:
        markdown = _clean_text(state.get("final_markdown_current") or state.get("markdown"))
        words = re.findall(r"[\u4e00-\u9fff]{2,8}", markdown)
        counts: Dict[str, int] = {}
        for word in words:
            if word in {"报告", "舆情", "分析", "当前", "需要", "建议", "可能"}:
                continue
            counts[word] = counts.get(word, 0) + 1
        keyword_rows = [{"name": key, "value": value} for key, value in sorted(counts.items(), key=lambda item: item[1], reverse=True)[:80]]
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
        "timeline": [{"time": date, "event": f"章节证据单元 {value} 条"} for date, value in zip(dates, values)] or [{"time": "—", "event": "证据不足"}],
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
        "REPORT_SUBTITLE": "基于结构化报告、正式文稿与中间分析产物生成",
        "EVENT_TYPE": _clean_text(((state.get("scene_profile") or {}).get("scene_label") if isinstance(state.get("scene_profile"), dict) else "") or "舆情事件"),
        "OBJECT_NAME": topic[:30],
        "DATA_PERIOD": f"{dates[0]} 至 {dates[-1]}" if dates else "证据不足",
        "SAMPLE_SIZE": str(total or "—"),
        "EFFECTIVE_VOLUME": str(total or "—"),
        "GEN_TIME": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "DATA_SOURCE": "结构化报告、中间 JSON、正式 Markdown",
    }


def _default_narrative(state: Dict[str, Any], meta: Dict[str, str]) -> Dict[str, Any]:
    markdown = _clean_text(state.get("final_markdown_current") or state.get("markdown"), 900)
    stub = "证据不足"
    title = meta.get("REPORT_TITLE") or "舆情分析报告"
    return {
        "REPORT_TITLE": title,
        "REPORT_SUBTITLE": meta.get("REPORT_SUBTITLE", ""),
        "EVENT_TYPE": meta.get("EVENT_TYPE", "舆情事件"),
        "OBJECT_NAME": meta.get("OBJECT_NAME", title[:30]),
        "PHASE_STATUS": "待评估（证据不足）",
        "KPI_TOTAL": meta.get("SAMPLE_SIZE", "—"),
        "KPI_EFFECTIVE": meta.get("EFFECTIVE_VOLUME", "—"),
        "KPI_POS_RATIO": "待评估",
        "KPI_NEG_RATIO": "待评估",
        "INTRO_BACKGROUND": markdown or stub,
        "INTRO_TRIGGERS": stub,
        "SUMMARY_BULLETS": [markdown[:180] or stub, "报告已保留结构化证据与正式文稿的来源链路。", "后续建议结合人工复核确认关键结论。"],
        "CHART_SENTIMENT_ANALYSIS": [stub, stub, stub],
        "CHART_TIMELINE_ANALYSIS": [stub, stub, stub],
        "CHART_VOLUME_ANALYSIS": [stub, stub, stub],
        "CHART_REGION_ANALYSIS": [stub, stub, stub],
        "CHART_AUTHOR_ANALYSIS": [stub, stub, stub],
        "CHART_KEYWORD_ANALYSIS": [stub, stub, stub],
        "CHART_RADAR_ANALYSIS": [stub, stub, stub],
        "CHART_LIFECYCLE_ANALYSIS": [stub, stub, stub],
        "THEORY_SILENCE": stub,
        "THEORY_AGENDA": stub,
        "THEORY_BUTTERFLY": stub,
        "RESPONSE_ANALYSIS_BULLETS": [stub, stub, stub],
        "RECAP_DISCOURSE": markdown[:260] or stub,
        "RECAP_TRENDS": stub,
        "RECAP_DRIVERS_BULLETS": [stub, stub, stub],
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
        warnings.append("sona_template_fill_prompt_missing")
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


def build_sona_html_artifact(state: Dict[str, Any]) -> Dict[str, Any]:
    warnings: List[str] = []
    if not _TEMPLATE_PATH.is_file():
        raise FileNotFoundError(f"Sona HTML template missing: {_TEMPLATE_PATH}")
    report_data = _build_report_data(state)
    meta = _build_meta(state, report_data)
    defaults = _default_narrative(state, meta)
    narrative = _call_narrative_model(state, meta, warnings)
    text_map: Dict[str, Any] = dict(defaults)
    for key, value in narrative.items():
        if key in _PLACEHOLDER_KEYS and value is not None:
            text_map[key] = value
    text_map.update(meta)
    text_map["KPI_TOTAL"] = meta.get("SAMPLE_SIZE", "—")
    text_map["KPI_EFFECTIVE"] = meta.get("EFFECTIVE_VOLUME", "—")
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
    }
