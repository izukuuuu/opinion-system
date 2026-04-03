"""
AI full-report generation service.
"""
from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import quote

from ..utils.ai import call_langchain_chat
from ..utils.logging.logging import log_success, setup_logger
from ..utils.setting.paths import ensure_bucket
from .knowledge_loader import load_report_knowledge
from .skills import load_report_skill_context
from .structured_prompts import (
    build_full_report_brief_prompt,
    build_full_report_markdown_prompt,
    build_full_report_revise_prompt,
)
from .structured_service import generate_report_payload

AI_FULL_REPORT_CACHE_FILENAME = "ai_full_report_payload.json"
AI_FULL_REPORT_CACHE_VERSION = 1

FULL_REPORT_SYSTEM_PROMPT = (
    "你是一名资深舆情分析报告编辑。"
    "请严格基于输入事实、方法论和复核约束写作。"
    "不得编造数字、日期、事件、评论来源或组织动作。"
)


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
    end_text = str(end or "").strip() or start_text
    return f"{start_text}_{end_text}" if end_text and end_text != start_text else start_text


def _extract_json_text(raw_text: str) -> str:
    text = str(raw_text or "").strip()
    if not text:
        return ""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, flags=re.S)
    if fenced:
        return fenced.group(1).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1].strip()
    return ""


def _call_json_agent(prompt: str, *, max_tokens: int = 1800) -> Optional[Dict[str, Any]]:
    raw_text = _safe_async_call(
        call_langchain_chat(
            [
                {"role": "system", "content": FULL_REPORT_SYSTEM_PROMPT + "必须输出合法 JSON。"},
                {"role": "user", "content": prompt},
            ],
            task="report",
            model_role="report",
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
        parsed = json.loads(candidate)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def _call_markdown_agent(prompt: str, *, max_tokens: int = 3200) -> str:
    raw_text = _safe_async_call(
        call_langchain_chat(
            [
                {"role": "system", "content": FULL_REPORT_SYSTEM_PROMPT + "只输出 Markdown。"},
                {"role": "user", "content": prompt},
            ],
            task="report",
            model_role="report",
            temperature=0.25,
            max_tokens=max_tokens,
        )
    )
    return str(raw_text or "").strip()


def _emit_event(event_callback: Optional[Callable[[Dict[str, Any]], None]], payload: Dict[str, Any]) -> None:
    if not callable(event_callback):
        return
    try:
        event_callback(payload)
    except Exception:
        return


def _truncate_text(value: Any, max_chars: int) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "..."


def _list_strings(rows: Any, *, max_items: int = 6, max_chars: int = 80) -> List[str]:
    if not isinstance(rows, list):
        return []
    return [
        _truncate_text(item, max_chars)
        for item in rows
        if str(item or "").strip()
    ][: max(1, max_items)]


def _extract_brief_sections(brief_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows = brief_payload.get("sections")
    if not isinstance(rows, list):
        return []
    sections: List[Dict[str, Any]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        section_id = str(item.get("id") or "").strip()
        goal = str(item.get("goal") or "").strip()
        evidence = _list_strings(item.get("evidence"), max_items=4, max_chars=120)
        if not (title and section_id):
            continue
        sections.append(
            {
                "id": section_id,
                "title": title,
                "goal": goal,
                "evidence": evidence,
            }
        )
    return sections


def _build_compact_report_facts(
    structured_payload: Dict[str, Any],
    *,
    topic_identifier: str,
    topic_label: str,
    knowledge_context: Dict[str, Any],
    skill_context: Dict[str, Any],
) -> Dict[str, Any]:
    metrics = structured_payload.get("metrics") if isinstance(structured_payload.get("metrics"), dict) else {}
    deep_analysis = structured_payload.get("deepAnalysis") if isinstance(structured_payload.get("deepAnalysis"), dict) else {}
    review_verdict = structured_payload.get("reviewVerdict") if isinstance(structured_payload.get("reviewVerdict"), dict) else {}
    legacy_context = structured_payload.get("legacyContext") if isinstance(structured_payload.get("legacyContext"), dict) else {}
    bertopic_temporal = structured_payload.get("bertopicTemporalNarrative") if isinstance(structured_payload.get("bertopicTemporalNarrative"), dict) else {}

    module_narratives: List[Dict[str, str]] = []
    for item in structured_payload.get("moduleNarratives") or []:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        summary = str(item.get("summary") or "").strip()
        explain_text = str(item.get("explainText") or "").strip()
        if not (label and (summary or explain_text)):
            continue
        module_narratives.append(
            {
                "label": label,
                "summary": _truncate_text(summary, 180),
                "explain_text": _truncate_text(explain_text, 240),
                "source": str(item.get("source") or "").strip(),
            }
        )

    insight_cards: List[Dict[str, Any]] = []
    for item in structured_payload.get("insights") or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        headline = str(item.get("headline") or "").strip()
        points = _list_strings(item.get("points"), max_items=4, max_chars=90)
        if title:
            insight_cards.append({"title": title, "headline": headline, "points": points})

    stage_notes: List[Dict[str, str]] = []
    for item in structured_payload.get("stageNotes") or []:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        highlight = str(item.get("highlight") or "").strip()
        range_text = str(item.get("range") or "").strip()
        if not (title and highlight):
            continue
        stage_notes.append(
            {
                "title": title,
                "range": range_text,
                "highlight": _truncate_text(highlight, 200),
            }
        )

    reference_snippets = []
    for item in knowledge_context.get("referenceSnippets") or []:
        if not isinstance(item, dict):
            continue
        snippet = str(item.get("snippet") or "").strip()
        title = str(item.get("title") or "").strip()
        if snippet:
            reference_snippets.append({"title": title, "snippet": _truncate_text(snippet, 240)})

    expert_notes = []
    for item in knowledge_context.get("expertNotes") or []:
        if not isinstance(item, dict):
            continue
        snippet = str(item.get("snippet") or "").strip()
        title = str(item.get("title") or "").strip()
        if snippet:
            expert_notes.append({"title": title, "snippet": _truncate_text(snippet, 220)})

    return {
        "topic_identifier": topic_identifier,
        "topic_label": topic_label,
        "title": str(structured_payload.get("title") or "").strip(),
        "subtitle": str(structured_payload.get("subtitle") or "").strip(),
        "range_text": str(structured_payload.get("rangeText") or "").strip(),
        "metrics": {
            "total_volume": int(metrics.get("totalVolume") or 0),
            "peak_date": str((metrics.get("peak") or {}).get("date") or "").strip()
            if isinstance(metrics.get("peak"), dict)
            else "",
            "peak_value": int((metrics.get("peak") or {}).get("value") or 0)
            if isinstance(metrics.get("peak"), dict)
            else 0,
            "positive_rate": float(metrics.get("positiveRate") or 0),
            "neutral_rate": float(metrics.get("neutralRate") or 0),
            "negative_rate": float(metrics.get("negativeRate") or 0),
            "factual_ratio": float(metrics.get("factualRatio") or 0),
            "opinion_ratio": float(metrics.get("opinionRatio") or 0),
        },
        "deep_analysis": {
            "narrative_summary": str(deep_analysis.get("narrativeSummary") or "").strip(),
            "key_events": _list_strings(deep_analysis.get("keyEvents"), max_items=5, max_chars=100),
            "key_risks": _list_strings(deep_analysis.get("keyRisks"), max_items=5, max_chars=100),
            "event_type": str(deep_analysis.get("eventType") or "").strip(),
            "domain": str(deep_analysis.get("domain") or "").strip(),
            "stage": str(deep_analysis.get("stage") or "").strip(),
            "indicator_dimensions": _list_strings(deep_analysis.get("indicatorDimensions"), max_items=6, max_chars=40),
            "theory_names": _list_strings(deep_analysis.get("theoryNames"), max_items=4, max_chars=40),
        },
        "stage_notes": stage_notes[:3],
        "highlight_points": _list_strings(structured_payload.get("highlightPoints"), max_items=6, max_chars=90),
        "insight_cards": insight_cards[:6],
        "module_narratives": module_narratives[:7],
        "bertopic": {
            "insight": _truncate_text(structured_payload.get("bertopicInsight") or "", 900),
            "temporal_summary": str(bertopic_temporal.get("summary") or "").strip(),
            "shift_signals": _list_strings(bertopic_temporal.get("shiftSignals"), max_items=4, max_chars=90),
            "watchpoints": _list_strings(bertopic_temporal.get("watchpoints"), max_items=3, max_chars=90),
        },
        "keywords": [
            {
                "name": str(item.get("name") or "").strip(),
                "value": int(item.get("value") or 0),
            }
            for item in (structured_payload.get("keywords") or [])[:10]
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        ],
        "themes": [
            {
                "name": str(item.get("name") or "").strip(),
                "value": int(item.get("value") or 0),
            }
            for item in (structured_payload.get("themes") or [])[:8]
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        ],
        "review_verdict": {
            "status": str(review_verdict.get("status") or "").strip(),
            "verdict": str(review_verdict.get("verdict") or "").strip(),
            "confidence_label": str(review_verdict.get("confidence_label") or review_verdict.get("confidenceLabel") or "").strip(),
            "issues": _list_strings(review_verdict.get("issues"), max_items=4, max_chars=50),
            "focus_areas": _list_strings(review_verdict.get("focus_areas") or review_verdict.get("focusAreas"), max_items=4, max_chars=60),
            "requires_manual_review": bool(review_verdict.get("requires_manual_review") or review_verdict.get("requiresManualReview")),
        },
        "knowledge_context": {
            "summary": _truncate_text(knowledge_context.get("summary") or "", 3200),
            "theory_hints": _list_strings(knowledge_context.get("theoryHints"), max_items=6, max_chars=32),
            "dynamic_theories": _list_strings(knowledge_context.get("dynamicTheories"), max_items=6, max_chars=32),
            "reference_snippets": reference_snippets[:4],
            "expert_notes": expert_notes[:4],
        },
        "skill_context": {
            "goal": str(skill_context.get("goal") or "").strip(),
            "reasoning_style": _list_strings(skill_context.get("reasoningStyle"), max_items=5, max_chars=80),
            "constraints": _list_strings(skill_context.get("constraints"), max_items=5, max_chars=80),
            "section_guidance": skill_context.get("sectionGuidance") if isinstance(skill_context.get("sectionGuidance"), dict) else {},
        },
        "legacy_context": {
            "sections_count": int(legacy_context.get("sectionsCount") or 0),
            "full_text_excerpt": _truncate_text(legacy_context.get("fullText") or "", 1800),
            "manual_text_excerpt": _truncate_text(legacy_context.get("manualText") or "", 1200),
        },
    }


def _fallback_brief(facts: Dict[str, Any]) -> Dict[str, Any]:
    theories = facts.get("knowledge_context", {}).get("dynamic_theories") or facts.get("knowledge_context", {}).get("theory_hints") or []
    preferred_terms = [str(item).strip() for item in theories if str(item or "").strip()][:6]
    sections = [
        {"id": "summary", "title": "执行摘要", "goal": "先用最短路径交代主线、阶段和结论。", "evidence": facts.get("highlight_points") or []},
        {"id": "trend", "title": "传播态势与阶段变化", "goal": "解释时间线、峰值和阶段切换。", "evidence": facts.get("deep_analysis", {}).get("key_events") or []},
        {"id": "structure", "title": "议题结构与情绪拆解", "goal": "拆解主题、关键词、情绪和渠道结构。", "evidence": [item.get("label") for item in facts.get("module_narratives") or [] if isinstance(item, dict)]},
        {"id": "risk", "title": "风险研判与监测重点", "goal": "归纳关键风险、观察维度和理论锚点。", "evidence": facts.get("deep_analysis", {}).get("key_risks") or []},
        {"id": "action", "title": "建议与复核提醒", "goal": "提出行动建议，并提示需要人工复核的边界。", "evidence": facts.get("review_verdict", {}).get("focus_areas") or []},
    ]
    return {
        "core_thesis": str(facts.get("deep_analysis", {}).get("narrative_summary") or facts.get("subtitle") or "").strip(),
        "tone_notes": [
            "先结论后展开，避免流水账。",
            "每段都要落回事实和结构化证据。",
            "建议使用方法论术语，但不能把理论当成新事实。",
        ],
        "preferred_terms": preferred_terms,
        "sections": sections,
    }


def _strip_code_fences(markdown: str) -> str:
    text = str(markdown or "").strip()
    if not text:
        return ""
    fenced = re.match(r"```(?:markdown|md)?\s*(.*?)\s*```$", text, flags=re.S)
    return fenced.group(1).strip() if fenced else text


def _clean_markdown(markdown: str, *, title: str) -> str:
    text = _strip_code_fences(markdown)
    text = re.sub(r"<\s*(script|style|iframe|object|embed)[^>]*>.*?<\s*/\s*\1\s*>", "", text, flags=re.I | re.S)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        return ""
    if not re.search(r"^\s*#\s+", text, flags=re.M):
        safe_title = str(title or "AI 完整报告").strip() or "AI 完整报告"
        text = f"# {safe_title}\n\n{text}"
    return text


def _fallback_markdown(facts: Dict[str, Any], brief: Dict[str, Any]) -> str:
    title = str(facts.get("title") or f"{facts.get('topic_label') or facts.get('topic_identifier') or '专题'}完整报告").strip()
    subtitle = str(facts.get("subtitle") or "").strip()
    deep_analysis = facts.get("deep_analysis") or {}
    review_verdict = facts.get("review_verdict") or {}

    lines = [f"# {title}"]
    if subtitle:
        lines.extend(["", subtitle])
    lines.extend(
        [
            "",
            "## 执行摘要",
            str(brief.get("core_thesis") or deep_analysis.get("narrative_summary") or "当前报告已完成结构化整合。").strip(),
            "",
            "## 传播态势与阶段变化",
            str(deep_analysis.get("narrative_summary") or "当前缺少完整叙事摘要，建议结合时间线与峰值节点复核。").strip(),
        ]
    )
    key_events = deep_analysis.get("key_events") or []
    if key_events:
        lines.extend(["", "关键节点："])
        lines.extend([f"- {item}" for item in key_events])
    stage_notes = facts.get("stage_notes") or []
    if stage_notes:
        lines.extend(["", "阶段说明："])
        for item in stage_notes:
            lines.append(f"- {item.get('title')}: {item.get('highlight')}")

    lines.extend(["", "## 议题结构与情绪拆解"])
    module_narratives = facts.get("module_narratives") or []
    if module_narratives:
        for item in module_narratives[:5]:
            lines.append(f"- {item.get('label')}: {item.get('summary') or item.get('explain_text')}")
    else:
        lines.append("当前缺少模块级叙事，建议结合基础分析结果补齐。")

    lines.extend(["", "## 风险研判与监测重点"])
    key_risks = deep_analysis.get("key_risks") or []
    if key_risks:
        lines.extend([f"- {item}" for item in key_risks])
    else:
        lines.append("当前未提取到显性高风险项，但仍需持续跟踪情绪和议题迁移。")

    indicator_dimensions = deep_analysis.get("indicator_dimensions") or []
    if indicator_dimensions:
        lines.extend(["", f"建议持续观察：{'、'.join(indicator_dimensions)}。"])

    lines.extend(["", "## 建议与复核提醒"])
    focus_areas = review_verdict.get("focus_areas") or []
    if focus_areas:
        lines.extend([f"- {item}" for item in focus_areas])
    elif review_verdict.get("verdict"):
        lines.append(str(review_verdict.get("verdict") or "").strip())
    else:
        lines.append("建议围绕时间线、情绪结构和主题迁移继续做滚动复核。")

    return "\n".join(lines).strip()


def _escape_xml(text: Any) -> str:
    value = str(text or "")
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&apos;")
    )


def _svg_data_url(svg: str) -> str:
    return f"data:image/svg+xml;charset=UTF-8,{quote(svg)}"


def _wrap_svg(title: str, body: str, *, width: int = 1200, height: int = 680) -> str:
    safe_title = _escape_xml(title)
    return (
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{width}' height='{height}' viewBox='0 0 {width} {height}'>"
        "<defs>"
        "<linearGradient id='bg' x1='0' y1='0' x2='1' y2='1'>"
        "<stop offset='0%' stop-color='#f6fbff'/>"
        "<stop offset='100%' stop-color='#eef6ff'/>"
        "</linearGradient>"
        "</defs>"
        f"<title>{safe_title}</title>"
        f"<rect x='0' y='0' width='{width}' height='{height}' rx='36' fill='url(#bg)'/>"
        "<rect x='26' y='26' width='1148' height='628' rx='28' fill='#ffffff' stroke='#dbeafe' stroke-width='2'/>"
        f"{body}</svg>"
    )


def _build_cover_asset(structured_payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    metrics = structured_payload.get("metrics") if isinstance(structured_payload.get("metrics"), dict) else {}
    deep_analysis = structured_payload.get("deepAnalysis") if isinstance(structured_payload.get("deepAnalysis"), dict) else {}
    title = str(structured_payload.get("title") or "").strip()
    if not title:
        return None

    subtitle = _truncate_text(structured_payload.get("subtitle") or "", 64)
    range_text = _truncate_text(structured_payload.get("rangeText") or "", 40)
    total_volume = int(metrics.get("totalVolume") or 0)
    peak = metrics.get("peak") if isinstance(metrics.get("peak"), dict) else {}
    peak_text = f"{str(peak.get('date') or '').strip() or '未提供'} / {int(peak.get('value') or 0)}"
    stage = _truncate_text(deep_analysis.get("stage") or "阶段待判定", 18)
    event_type = _truncate_text(deep_analysis.get("eventType") or "事件类型待判定", 18)

    body = (
        "<rect x='76' y='82' width='1048' height='180' rx='28' fill='#0f172a'/>"
        f"<text x='112' y='148' fill='#e0f2fe' font-size='22' font-family='Segoe UI, Microsoft YaHei, sans-serif'>AI 完整报告</text>"
        f"<text x='112' y='204' fill='#ffffff' font-size='42' font-weight='700' font-family='Segoe UI, Microsoft YaHei, sans-serif'>{_escape_xml(_truncate_text(title, 28))}</text>"
        f"<text x='112' y='244' fill='#cbd5e1' font-size='20' font-family='Segoe UI, Microsoft YaHei, sans-serif'>{_escape_xml(subtitle)}</text>"
        "<rect x='76' y='298' width='324' height='128' rx='24' fill='#eff6ff' stroke='#bfdbfe'/>"
        "<rect x='438' y='298' width='324' height='128' rx='24' fill='#f0fdf4' stroke='#bbf7d0'/>"
        "<rect x='800' y='298' width='324' height='128' rx='24' fill='#fff7ed' stroke='#fed7aa'/>"
        "<text x='108' y='336' fill='#64748b' font-size='18' font-family='Segoe UI, Microsoft YaHei, sans-serif'>时间区间</text>"
        f"<text x='108' y='388' fill='#0f172a' font-size='28' font-weight='700' font-family='Segoe UI, Microsoft YaHei, sans-serif'>{_escape_xml(range_text)}</text>"
        "<text x='470' y='336' fill='#64748b' font-size='18' font-family='Segoe UI, Microsoft YaHei, sans-serif'>总声量</text>"
        f"<text x='470' y='388' fill='#0f172a' font-size='28' font-weight='700' font-family='Segoe UI, Microsoft YaHei, sans-serif'>{total_volume:,}</text>"
        "<text x='832' y='336' fill='#64748b' font-size='18' font-family='Segoe UI, Microsoft YaHei, sans-serif'>峰值节点</text>"
        f"<text x='832' y='388' fill='#0f172a' font-size='24' font-weight='700' font-family='Segoe UI, Microsoft YaHei, sans-serif'>{_escape_xml(_truncate_text(peak_text, 26))}</text>"
        "<rect x='76' y='466' width='498' height='114' rx='24' fill='#f8fafc' stroke='#e2e8f0'/>"
        "<rect x='626' y='466' width='498' height='114' rx='24' fill='#f8fafc' stroke='#e2e8f0'/>"
        "<text x='108' y='504' fill='#64748b' font-size='18' font-family='Segoe UI, Microsoft YaHei, sans-serif'>当前阶段</text>"
        f"<text x='108' y='552' fill='#0f172a' font-size='30' font-weight='700' font-family='Segoe UI, Microsoft YaHei, sans-serif'>{_escape_xml(stage)}</text>"
        "<text x='658' y='504' fill='#64748b' font-size='18' font-family='Segoe UI, Microsoft YaHei, sans-serif'>事件类型</text>"
        f"<text x='658' y='552' fill='#0f172a' font-size='30' font-weight='700' font-family='Segoe UI, Microsoft YaHei, sans-serif'>{_escape_xml(event_type)}</text>"
    )
    return {
        "key": "cover",
        "title": "报告扉页图",
        "description": "自动摘要卡片",
        "dataUrl": _svg_data_url(_wrap_svg("报告扉页图", body)),
    }


def _build_timeline_asset(structured_payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    rows = structured_payload.get("timeline")
    if not isinstance(rows, list) or len(rows) < 2:
        return None

    points = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        date = str(item.get("date") or "").strip()
        value = int(item.get("value") or 0)
        if date:
            points.append({"date": date, "value": value})
    if len(points) < 2:
        return None

    max_value = max(point["value"] for point in points) or 1
    min_value = min(point["value"] for point in points)
    left, top, width, height = 120, 180, 960, 320
    polyline_parts: List[str] = []
    fill_parts = [f"{left},{top + height}"]
    labels = [points[0]["date"], points[len(points) // 2]["date"], points[-1]["date"]]
    for index, point in enumerate(points):
        ratio_x = index / max(1, len(points) - 1)
        ratio_y = point["value"] / max_value
        x = left + width * ratio_x
        y = top + height - height * ratio_y
        polyline_parts.append(f"{x:.1f},{y:.1f}")
        fill_parts.append(f"{x:.1f},{y:.1f}")
    fill_parts.append(f"{left + width},{top + height}")

    label_xs = [left, left + width / 2, left + width]
    body = [
        "<text x='120' y='110' fill='#0f172a' font-size='30' font-weight='700' font-family='Segoe UI, Microsoft YaHei, sans-serif'>传播趋势图</text>",
        "<text x='120' y='144' fill='#64748b' font-size='18' font-family='Segoe UI, Microsoft YaHei, sans-serif'>以报告时间线自动生成的趋势插图</text>",
        f"<line x1='{left}' y1='{top + height}' x2='{left + width}' y2='{top + height}' stroke='#cbd5e1' stroke-width='3'/>",
        f"<line x1='{left}' y1='{top}' x2='{left}' y2='{top + height}' stroke='#cbd5e1' stroke-width='3'/>",
        f"<polygon points='{' '.join(fill_parts)}' fill='#bae6fd' opacity='0.55'/>",
        f"<polyline points='{' '.join(polyline_parts)}' fill='none' stroke='#0284c7' stroke-width='6' stroke-linecap='round' stroke-linejoin='round'/>",
        f"<text x='{left}' y='{top - 18}' fill='#0369a1' font-size='18' font-family='Segoe UI, Microsoft YaHei, sans-serif'>峰值 {max_value:,}</text>",
        f"<text x='{left + width - 120}' y='{top + 18}' fill='#94a3b8' font-size='16' font-family='Segoe UI, Microsoft YaHei, sans-serif'>低点 {min_value:,}</text>",
    ]
    for label, x in zip(labels, label_xs):
        body.append(
            f"<text x='{x:.1f}' y='{top + height + 42}' text-anchor='middle' fill='#64748b' font-size='16' font-family='Segoe UI, Microsoft YaHei, sans-serif'>{_escape_xml(label)}</text>"
        )

    return {
        "key": "timeline",
        "title": "传播趋势图",
        "description": "时间线走势",
        "dataUrl": _svg_data_url(_wrap_svg("传播趋势图", "".join(body))),
    }


def _build_sentiment_asset(structured_payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    sentiment = structured_payload.get("sentiment")
    if not isinstance(sentiment, dict):
        return None
    positive = int(sentiment.get("positive") or 0)
    neutral = int(sentiment.get("neutral") or 0)
    negative = int(sentiment.get("negative") or 0)
    total = max(1, positive + neutral + negative)
    segments = [
        ("正向", positive, "#16a34a"),
        ("中性", neutral, "#64748b"),
        ("负向", negative, "#dc2626"),
    ]
    x = 120
    width = 960
    y = 250
    height = 82
    rects: List[str] = [
        "<text x='120' y='110' fill='#0f172a' font-size='30' font-weight='700' font-family='Segoe UI, Microsoft YaHei, sans-serif'>情绪结构图</text>",
        "<text x='120' y='144' fill='#64748b' font-size='18' font-family='Segoe UI, Microsoft YaHei, sans-serif'>按正向 / 中性 / 负向占比自动生成</text>",
    ]
    cursor = x
    label_y = 420
    for index, (label, value, color) in enumerate(segments):
        segment_width = width * (value / total)
        if index == len(segments) - 1:
            segment_width = x + width - cursor
        rects.append(
            f"<rect x='{cursor:.1f}' y='{y}' width='{max(segment_width, 0):.1f}' height='{height}' rx='18' fill='{color}'/>"
        )
        center_x = cursor + max(segment_width, 0) / 2
        rects.append(
            f"<text x='{center_x:.1f}' y='{y + 50}' text-anchor='middle' fill='#ffffff' font-size='22' font-weight='700' font-family='Segoe UI, Microsoft YaHei, sans-serif'>{_escape_xml(label)}</text>"
        )
        rects.append(
            f"<text x='{120 + index * 320:.1f}' y='{label_y}' fill='{color}' font-size='22' font-weight='700' font-family='Segoe UI, Microsoft YaHei, sans-serif'>{_escape_xml(label)} {value:,}</text>"
        )
        rects.append(
            f"<text x='{120 + index * 320:.1f}' y='{label_y + 34}' fill='#64748b' font-size='18' font-family='Segoe UI, Microsoft YaHei, sans-serif'>{value / total:.1%}</text>"
        )
        cursor += segment_width

    return {
        "key": "sentiment",
        "title": "情绪结构图",
        "description": "情绪占比",
        "dataUrl": _svg_data_url(_wrap_svg("情绪结构图", "".join(rects))),
    }


def _build_channels_asset(structured_payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    channels = structured_payload.get("channels")
    if not isinstance(channels, list):
        return None
    rows = [
        {
            "name": str(item.get("name") or "").strip(),
            "value": int(item.get("value") or 0),
        }
        for item in channels
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    ]
    rows = sorted(rows, key=lambda item: item["value"], reverse=True)[:5]
    if not rows:
        return None

    max_value = max(item["value"] for item in rows) or 1
    body: List[str] = [
        "<text x='120' y='110' fill='#0f172a' font-size='30' font-weight='700' font-family='Segoe UI, Microsoft YaHei, sans-serif'>渠道分布图</text>",
        "<text x='120' y='144' fill='#64748b' font-size='18' font-family='Segoe UI, Microsoft YaHei, sans-serif'>自动选取头部渠道生成横向对比插图</text>",
    ]
    colors = ["#2563eb", "#0ea5e9", "#14b8a6", "#f97316", "#ef4444"]
    for index, row in enumerate(rows):
        y = 200 + index * 82
        bar_width = 760 * (row["value"] / max_value)
        body.append(f"<text x='120' y='{y + 28}' fill='#0f172a' font-size='20' font-weight='700' font-family='Segoe UI, Microsoft YaHei, sans-serif'>{_escape_xml(_truncate_text(row['name'], 14))}</text>")
        body.append(f"<rect x='280' y='{y}' width='780' height='34' rx='17' fill='#e2e8f0'/>")
        body.append(f"<rect x='280' y='{y}' width='{bar_width:.1f}' height='34' rx='17' fill='{colors[index % len(colors)]}'/>")
        body.append(f"<text x='1088' y='{y + 24}' text-anchor='end' fill='#334155' font-size='18' font-family='Segoe UI, Microsoft YaHei, sans-serif'>{row['value']:,}</text>")

    return {
        "key": "channels",
        "title": "渠道分布图",
        "description": "头部渠道横向对比",
        "dataUrl": _svg_data_url(_wrap_svg("渠道分布图", "".join(body))),
    }


def _build_theme_asset(structured_payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    themes = structured_payload.get("themes")
    if not isinstance(themes, list):
        return None
    rows = [
        {
            "name": str(item.get("name") or "").strip(),
            "value": int(item.get("value") or 0),
        }
        for item in themes
        if isinstance(item, dict) and str(item.get("name") or "").strip()
    ]
    rows = sorted(rows, key=lambda item: item["value"], reverse=True)[:6]
    if not rows:
        return None

    body: List[str] = [
        "<text x='120' y='110' fill='#0f172a' font-size='30' font-weight='700' font-family='Segoe UI, Microsoft YaHei, sans-serif'>核心议题图</text>",
        "<text x='120' y='144' fill='#64748b' font-size='18' font-family='Segoe UI, Microsoft YaHei, sans-serif'>自动抽取高频议题标签生成</text>",
    ]
    chip_colors = ["#eff6ff", "#ecfeff", "#f5f3ff", "#fff7ed", "#f0fdf4", "#fef2f2"]
    text_colors = ["#1d4ed8", "#0f766e", "#6d28d9", "#c2410c", "#15803d", "#b91c1c"]
    for index, row in enumerate(rows):
        col = index % 2
        slot = index // 2
        x = 120 + col * 470
        y = 210 + slot * 118
        body.append(f"<rect x='{x}' y='{y}' width='390' height='76' rx='24' fill='{chip_colors[index % len(chip_colors)]}' stroke='#e2e8f0'/>")
        body.append(f"<text x='{x + 28}' y='{y + 34}' fill='{text_colors[index % len(text_colors)]}' font-size='24' font-weight='700' font-family='Segoe UI, Microsoft YaHei, sans-serif'>{_escape_xml(_truncate_text(row['name'], 16))}</text>")
        body.append(f"<text x='{x + 28}' y='{y + 60}' fill='#64748b' font-size='18' font-family='Segoe UI, Microsoft YaHei, sans-serif'>权重 / 声量 {row['value']:,}</text>")

    return {
        "key": "themes",
        "title": "核心议题图",
        "description": "主题标签插图",
        "dataUrl": _svg_data_url(_wrap_svg("核心议题图", "".join(body))),
    }


def _build_visual_assets(structured_payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    builders = [
        _build_cover_asset,
        _build_timeline_asset,
        _build_sentiment_asset,
        _build_channels_asset,
        _build_theme_asset,
    ]
    assets: List[Dict[str, Any]] = []
    for builder in builders:
        try:
            asset = builder(structured_payload)
        except Exception:
            asset = None
        if isinstance(asset, dict) and str(asset.get("key") or "").strip():
            assets.append(asset)
    return assets


def _inject_visual_assets(markdown: str, assets: List[Dict[str, Any]]) -> str:
    text = str(markdown or "").strip()
    if not text or not assets:
        return text

    asset_keys = {str(item.get("key") or "").strip() for item in assets}
    if "cover" in asset_keys and "report-asset://cover" not in text:
        text = re.sub(
            r"^(# .+)$",
            r"\1\n\n![报告扉页图](report-asset://cover)",
            text,
            count=1,
            flags=re.M,
        )

    appended_keys: List[str] = []
    lines = [text.rstrip(), "", "## 关键图示", ""]
    for item in assets:
        key = str(item.get("key") or "").strip()
        title = str(item.get("title") or key).strip()
        description = str(item.get("description") or "").strip()
        if not key or key == "cover" or f"report-asset://{key}" in text:
            continue
        appended_keys.append(key)
        lines.append(f"### {title}")
        lines.append("")
        lines.append(f"![{title}](report-asset://{key})")
        if description:
            lines.extend(["", description])
        lines.append("")

    return text if not appended_keys else "\n".join(lines).strip()


def generate_full_report_payload(
    topic_identifier: str,
    start: str,
    end: Optional[str] = None,
    *,
    topic_label: Optional[str] = None,
    regenerate: bool = False,
    structured_payload: Optional[Dict[str, Any]] = None,
    event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    start_text = str(start or "").strip()
    end_text = str(end or "").strip() or start_text
    if not start_text:
        raise ValueError("Missing required field(s): start")

    folder = _compose_folder(start_text, end_text)
    report_dir = ensure_bucket("reports", topic_identifier, folder)
    cache_path = report_dir / AI_FULL_REPORT_CACHE_FILENAME
    display_name = str(topic_label or topic_identifier).strip() or topic_identifier

    if cache_path.exists() and not regenerate:
        try:
            with cache_path.open("r", encoding="utf-8") as fh:
                cached = json.load(fh)
            if (
                isinstance(cached, dict)
                and isinstance(cached.get("meta"), dict)
                and int(cached["meta"].get("cache_version") or 0) == AI_FULL_REPORT_CACHE_VERSION
            ):
                return cached
        except Exception:
            pass

    logger = setup_logger(f"ReportFull_{topic_identifier}", folder)
    if not isinstance(structured_payload, dict):
        structured_payload = generate_report_payload(
            topic_identifier,
            start_text,
            end_text,
            topic_label=display_name,
            regenerate=False,
        )
    knowledge_context = load_report_knowledge(display_name)
    skill_context = load_report_skill_context(display_name)
    facts = _build_compact_report_facts(
        structured_payload,
        topic_identifier=topic_identifier,
        topic_label=display_name,
        knowledge_context=knowledge_context,
        skill_context=skill_context,
    )

    _emit_event(
        event_callback,
        {
            "type": "phase.started",
            "phase": "write",
            "title": "完整报告编排",
            "message": "Integrator 正在整合结构化结果、知识库方法论和 reviewer 裁决。",
        },
    )
    _emit_event(
        event_callback,
        {
            "type": "agent.started",
            "phase": "write",
            "agent": "integrator",
            "title": "Integrator 已启动",
            "message": "正在组装 AI 完整报告写作 brief。",
        },
    )
    brief_payload = _call_json_agent(build_full_report_brief_prompt(facts), max_tokens=1800)
    brief_source = "llm" if isinstance(brief_payload, dict) else "fallback"
    if not isinstance(brief_payload, dict):
        brief_payload = _fallback_brief(facts)
    brief_payload["sections"] = _extract_brief_sections(brief_payload)
    _emit_event(
        event_callback,
        {
            "type": "agent.memo",
            "phase": "write",
            "agent": "integrator",
            "title": "Integrator 公开备忘录",
            "message": "写作 brief 已生成，开始进入长报告草拟。",
            "delta": "写作 brief 已生成，开始进入长报告草拟。",
            "payload": {
                "source": brief_source,
                "core_thesis": str(brief_payload.get("core_thesis") or "").strip(),
                "preferred_terms": brief_payload.get("preferred_terms") or [],
                "sections": brief_payload.get("sections") or [],
            },
        },
    )

    _emit_event(
        event_callback,
        {
            "type": "agent.started",
            "phase": "write",
            "agent": "writer",
            "title": "Writer 已启动",
            "message": "Writer 正在生成 Markdown 长报告草稿。",
        },
    )
    draft_markdown = _call_markdown_agent(
        build_full_report_markdown_prompt({"facts": facts, "brief": brief_payload}),
        max_tokens=3200,
    )
    draft_source = "llm" if draft_markdown.strip() else "fallback"
    if not draft_markdown.strip():
        draft_markdown = _fallback_markdown(facts, brief_payload)
    _emit_event(
        event_callback,
        {
            "type": "agent.memo",
            "phase": "write",
            "agent": "writer",
            "title": "Writer 公开备忘录",
            "message": "长报告草稿已生成，开始进行 revise 收口。",
            "delta": "长报告草稿已生成，开始进行 revise 收口。",
            "payload": {
                "source": draft_source,
                "preview": _truncate_text(draft_markdown, 600),
            },
        },
    )

    _emit_event(
        event_callback,
        {
            "type": "phase.progress",
            "phase": "review",
            "title": "完整报告修订",
            "message": "Reviser 正在压缩重复表述并强化证据边界。",
        },
    )
    _emit_event(
        event_callback,
        {
            "type": "agent.started",
            "phase": "review",
            "agent": "reviser",
            "title": "Reviser 已启动",
            "message": "Reviser 正在对 Markdown 报告进行 revise。",
        },
    )
    revised_markdown = _call_markdown_agent(
        build_full_report_revise_prompt(
            {
                "facts": facts,
                "brief": brief_payload,
                "draft_markdown": draft_markdown,
            }
        ),
        max_tokens=3400,
    )
    revise_source = "llm" if revised_markdown.strip() else "fallback"

    final_markdown = _clean_markdown(
        revised_markdown or draft_markdown,
        title=structured_payload.get("title") or display_name,
    )
    if not final_markdown:
        final_markdown = _fallback_markdown(facts, brief_payload)
        revise_source = "fallback"

    assets = _build_visual_assets(structured_payload)
    final_markdown = _inject_visual_assets(final_markdown, assets)
    now_text = datetime.now().strftime("%Y-%m-%d %H:%M")
    review_verdict = structured_payload.get("reviewVerdict") if isinstance(structured_payload.get("reviewVerdict"), dict) else {}
    _emit_event(
        event_callback,
        {
            "type": "agent.memo",
            "phase": "review",
            "agent": "reviser",
            "title": "Reviser 公开备忘录",
            "message": "Markdown 长报告已完成 revise，并自动插入关键图示。",
            "delta": "Markdown 长报告已完成 revise，并自动插入关键图示。",
            "payload": {
                "source": revise_source,
                "asset_count": len(assets),
                "preview": _truncate_text(final_markdown, 600),
            },
        },
    )

    payload = {
        "title": str(structured_payload.get("title") or f"{display_name}AI 完整报告").strip(),
        "subtitle": str(structured_payload.get("subtitle") or "").strip(),
        "rangeText": str(structured_payload.get("rangeText") or f"{start_text} → {end_text}").strip(),
        "lastUpdated": now_text,
        "markdown": final_markdown,
        "assets": assets,
        "reviewVerdict": review_verdict,
        "meta": {
            "topic_identifier": topic_identifier,
            "topic_label": display_name,
            "cache_version": AI_FULL_REPORT_CACHE_VERSION,
            "generated_at": now_text,
            "brief_source": brief_source,
            "draft_source": draft_source,
            "revise_source": revise_source,
            "asset_count": len(assets),
            "requires_manual_review": bool(review_verdict.get("requires_manual_review") or review_verdict.get("requiresManualReview")),
            "knowledge_terms": (
                facts.get("knowledge_context", {}).get("dynamic_theories")
                or facts.get("knowledge_context", {}).get("theory_hints")
                or []
            )[:6],
        },
    }

    try:
        with cache_path.open("w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        log_success(logger, f"AI 完整报告缓存写入成功: {cache_path}", "ReportFull")
    except Exception:
        pass

    _emit_event(
        event_callback,
        {
            "type": "artifact.ready",
            "phase": "persist",
            "title": "AI 完整报告已写入",
            "message": "Markdown 长报告和自动图示已写入缓存。",
            "payload": {
                "full_report_ready": True,
                "full_report_cache_path": str(cache_path),
                "full_report_title": str(payload.get("title") or "").strip(),
            },
        },
    )

    return payload
