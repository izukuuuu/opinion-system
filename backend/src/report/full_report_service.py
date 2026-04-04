"""
AI full-report generation service.
"""
from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, TypedDict
from urllib.parse import quote

from ..utils.ai import call_langchain_chat, call_langchain_with_tools
from ..utils.logging.logging import log_success, setup_logger
from ..utils.setting.paths import ensure_bucket
from .agent_runtime import (
    build_section_tool_policy,
    create_analysis_agent_runner,
    ensure_langchain_uuid_compat,
    run_report_agent_step,
    run_section_exploration,
    run_section_writer_agent,
)
from .knowledge_loader import load_report_knowledge
from .evidence_retriever import summarize_source_scope, verify_claim_with_records
from .scene_profile import (
    fallback_select_full_report_scene,
    load_full_report_scene_catalog,
)
from .skills import load_report_skill_context
from .style_profile import load_full_report_style_profile
from .tools import get_report_tool_bundle, get_report_tool_rounds
from .structured_prompts import (
    build_full_report_fact_critic_prompt,
    build_full_report_budget_prompt,
    build_full_report_layout_prompt,
    build_full_report_brief_prompt,
    build_full_report_markdown_prompt,
    build_full_report_mechanism_prompt,
    build_full_report_revise_prompt,
    build_full_report_risk_map_prompt,
    build_full_report_scene_prompt,
    build_full_report_section_prompt,
    build_full_report_style_critic_prompt,
    build_title_subtitle_prompt,
)
from .structured_service import generate_report_payload

AI_FULL_REPORT_CACHE_FILENAME = "ai_full_report_payload.json"
AI_FULL_REPORT_CACHE_VERSION = 7

FULL_REPORT_SYSTEM_PROMPT = (
    "你是一名资深舆情分析报告编辑。"
    "请严格基于输入事实、方法论和证据边界写作。"
    "不得编造数字、日期、事件、评论来源或组织动作。"
    "成稿体裁、场景选择、章节组织、篇幅规划、图示标题和语气由输入的 style_profile、scene_profile、layout_plan、section_budget 与 language_requirements 决定。"
    "不得暴露内部字段名、模块名、英文键名或技术审计口吻。"
)


class FullReportAnalysisState(TypedDict, total=False):
    topic_identifier: str
    topic_label: str
    start: str
    end: str
    structured_payload: Dict[str, Any]
    knowledge_context: Dict[str, Any]
    skill_context: Dict[str, Any]
    style_profile: Dict[str, Any]
    scene_profile: Dict[str, Any]
    scene_source: str
    scene_reason: str
    event_callback: Optional[Callable[[Dict[str, Any]], None]]
    base_facts: Dict[str, Any]
    analysis_outputs: Dict[str, Any]
    analysis_iterations: int
    analysis_status: str
    analysis_issues: List[str]
    analysis_graph_source: str
    analysis_trace: Dict[str, Any]


class FullReportWritingState(TypedDict, total=False):
    topic_label: str
    structured_payload: Dict[str, Any]
    skill_context: Dict[str, Any]
    style_profile: Dict[str, Any]
    scene_profile: Dict[str, Any]
    facts: Dict[str, Any]
    event_callback: Optional[Callable[[Dict[str, Any]], None]]
    layout_plan: Dict[str, Any]
    layout_source: str
    section_budget: Dict[str, Any]
    budget_source: str
    brief_payload: Dict[str, Any]
    brief_source: str
    sections: List[Dict[str, Any]]
    section_index: int
    current_section: Dict[str, Any]
    current_output: Dict[str, Any]
    current_rewrite_count: int
    section_rewrite_count: int
    section_outputs: List[Dict[str, Any]]
    section_outcomes: List[Dict[str, Any]]
    style_review: Dict[str, Any]
    fact_review: Dict[str, Any]
    final_markdown: str
    writing_graph_source: str
    revise_source: str
    exploration_sections: List[str]
    tool_call_count_total: int
    exploration_turns_total: int
    section_stop_reasons: Dict[str, str]


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


def _safe_json_loads_text(raw_text: str) -> Dict[str, Any]:
    candidate = _extract_json_text(raw_text)
    if not candidate:
        return {}
    try:
        parsed = json.loads(candidate)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


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


def _call_markdown_agent_with_tools(
    prompt: str,
    *,
    tools: List[Any],
    max_tokens: int = 2200,
    max_tool_rounds: Optional[int] = None,
) -> Dict[str, Any]:
    result = _safe_async_call(
        call_langchain_with_tools(
            [
                {"role": "system", "content": FULL_REPORT_SYSTEM_PROMPT + "只输出 Markdown。"},
                {"role": "user", "content": prompt},
            ],
            tools=tools,
            task="report",
            model_role="report",
            temperature=0.25,
            max_tokens=max_tokens,
            max_tool_rounds=max_tool_rounds,
        )
    )
    if not isinstance(result, dict):
        return {"content": "", "tool_calls": [], "tool_results": []}
    return {
        "content": str(result.get("content") or "").strip(),
        "tool_calls": result.get("tool_calls") if isinstance(result.get("tool_calls"), list) else [],
        "tool_results": result.get("tool_results") if isinstance(result.get("tool_results"), list) else [],
        "model": str(result.get("model") or "").strip(),
        "provider": str(result.get("provider") or "").strip(),
    }


def _emit_event(event_callback: Optional[Callable[[Dict[str, Any]], None]], payload: Dict[str, Any]) -> None:
    if not callable(event_callback):
        return
    try:
        event_callback(payload)
    except Exception:
        return


def _tool_names_from_objects(tools: Any) -> List[str]:
    if not isinstance(tools, list):
        return []
    return [
        str(getattr(tool, "name", "") or "").strip()
        for tool in tools
        if str(getattr(tool, "name", "") or "").strip()
    ]


def _build_agent_trace_payload(
    *,
    agent_runtime: str = "",
    tools_allowed: Optional[List[str]] = None,
    tool_policy_mode: str = "",
    tool_call_count: int = 0,
    tool_result_count: int = 0,
    stop_reason: str = "",
    section_id: str = "",
    scene_id: str = "",
) -> Dict[str, Any]:
    return {
        "agent_runtime": str(agent_runtime or "").strip(),
        "tools_allowed": [
            str(item).strip()
            for item in (tools_allowed or [])
            if str(item or "").strip()
        ],
        "tool_policy_mode": str(tool_policy_mode or "").strip(),
        "tool_call_count": int(tool_call_count or 0),
        "tool_result_count": int(tool_result_count or 0),
        "stop_reason": str(stop_reason or "").strip(),
        "section_id": str(section_id or "").strip(),
        "scene_id": str(scene_id or "").strip(),
    }


def _emit_agent_started_event(
    event_callback: Optional[Callable[[Dict[str, Any]], None]],
    *,
    agent: str,
    phase: str,
    message: str,
    title: str = "",
    agent_runtime: str = "",
    tools_allowed: Optional[List[str]] = None,
    tool_policy_mode: str = "",
    section_id: str = "",
    scene_id: str = "",
) -> None:
    _emit_event(
        event_callback,
        {
            "type": "agent.started",
            "phase": phase,
            "agent": agent,
            "title": title or f"{agent} 已启动",
            "message": message,
            "payload": _build_agent_trace_payload(
                agent_runtime=agent_runtime,
                tools_allowed=tools_allowed,
                tool_policy_mode=tool_policy_mode,
                section_id=section_id,
                scene_id=scene_id,
            ),
        },
    )


def _emit_agent_trace_events(
    event_callback: Optional[Callable[[Dict[str, Any]], None]],
    *,
    agent: str,
    phase: str,
    trace: Dict[str, Any],
    tools_allowed: Optional[List[str]] = None,
    tool_policy_mode: str = "",
    scene_id: str = "",
    section_id: str = "",
    agent_runtime: str = "langchain_create_agent",
    start_message: str = "",
    memo_title: str = "",
) -> None:
    trace_payload = trace if isinstance(trace, dict) else {}
    tool_calls = trace_payload.get("tool_calls") if isinstance(trace_payload.get("tool_calls"), list) else []
    tool_results = trace_payload.get("tool_results") if isinstance(trace_payload.get("tool_results"), list) else []
    stop_reason = str(trace_payload.get("stop_reason") or "").strip()
    tool_call_count = int(trace_payload.get("tool_call_count") or len(tool_calls) or 0)
    tool_result_count = len(tool_results)
    payload_base = _build_agent_trace_payload(
        agent_runtime=agent_runtime,
        tools_allowed=tools_allowed,
        tool_policy_mode=tool_policy_mode,
        tool_call_count=tool_call_count,
        tool_result_count=tool_result_count,
        stop_reason=stop_reason,
        section_id=section_id,
        scene_id=scene_id,
    )
    _emit_agent_started_event(
        event_callback,
        agent=agent,
        phase=phase,
        message=start_message or "Agent 正在执行。",
        title="",
        agent_runtime=agent_runtime,
        tools_allowed=tools_allowed,
        tool_policy_mode=tool_policy_mode,
        section_id=section_id,
        scene_id=scene_id,
    )
    for index, item in enumerate(tool_calls, start=1):
        tool_name = str((item or {}).get("name") or "").strip() or f"tool_{index}"
        _emit_event(
            event_callback,
            {
                "type": "tool.called",
                "phase": phase,
                "agent": agent,
                "title": f"{tool_name} 调用",
                "message": f"{agent} 正在调用 {tool_name}。",
                "payload": {
                    **payload_base,
                    "tool_name": tool_name,
                    "tool_args": (item or {}).get("args") or {},
                    "tool_call_id": str((item or {}).get("id") or "").strip(),
                },
            },
        )
    for index, item in enumerate(tool_results, start=1):
        tool_name = str((item or {}).get("name") or "").strip() or f"tool_{index}"
        _emit_event(
            event_callback,
            {
                "type": "tool.result",
                "phase": phase,
                "agent": agent,
                "title": f"{tool_name} 回执",
                "message": f"{agent} 已拿到 {tool_name} 的结果。",
                "payload": {
                    **payload_base,
                    "tool_name": tool_name,
                    "tool_call_id": str((item or {}).get("tool_call_id") or "").strip(),
                    "tool_output_preview": _truncate_text((item or {}).get("output") or "", 240),
                },
            },
        )
    if tools_allowed:
        if tool_call_count > 0:
            memo_message = f"已调用 {tool_call_count} 次工具。"
        else:
            memo_message = "本轮未触发工具。"
    else:
        memo_message = "无需工具。"
    if stop_reason:
        memo_message = f"{memo_message} stop_reason={stop_reason}"
    _emit_event(
        event_callback,
        {
            "type": "agent.memo",
            "phase": phase,
            "agent": agent,
            "title": memo_title or f"{agent} 公开备忘录",
            "message": memo_message,
            "delta": memo_message,
            "payload": payload_base,
        },
    )


def _emit_static_agent_activity(
    event_callback: Optional[Callable[[Dict[str, Any]], None]],
    *,
    agent: str,
    phase: str,
    message: str,
    title: str = "",
    section_id: str = "",
    scene_id: str = "",
) -> None:
    _emit_agent_started_event(
        event_callback,
        agent=agent,
        phase=phase,
        message=message,
        title=title,
        agent_runtime="langgraph_node",
        tools_allowed=[],
        tool_policy_mode="off",
        section_id=section_id,
        scene_id=scene_id,
    )
    _emit_event(
        event_callback,
        {
            "type": "agent.memo",
            "phase": phase,
            "agent": agent,
            "title": title or f"{agent} 公开备忘录",
            "message": "无需工具。",
            "delta": "无需工具。",
            "payload": _build_agent_trace_payload(
                agent_runtime="langgraph_node",
                tools_allowed=[],
                tool_policy_mode="off",
                section_id=section_id,
                scene_id=scene_id,
            ),
        },
    )


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


def _compact_skill_context(skill_context: Dict[str, Any], *, include_excerpt: bool = True) -> Dict[str, Any]:
    payload = {
        "name": str(skill_context.get("name") or "").strip(),
        "display_name": str(skill_context.get("displayName") or "").strip(),
        "description": _truncate_text(skill_context.get("description") or "", 220),
        "goal": str(skill_context.get("goal") or "").strip(),
        "document_type": str(skill_context.get("documentType") or "").strip(),
        "reasoning_style": _list_strings(skill_context.get("reasoningStyle"), max_items=5, max_chars=80),
        "language_requirements": _list_strings(skill_context.get("languageRequirements"), max_items=8, max_chars=120),
        "language_contract": skill_context.get("languageContract") if isinstance(skill_context.get("languageContract"), dict) else {},
        "style_language_requirements": (
            skill_context.get("styleLanguageRequirements")
            if isinstance(skill_context.get("styleLanguageRequirements"), dict)
            else {}
        ),
        "constraints": _list_strings(skill_context.get("constraints"), max_items=5, max_chars=80),
        "section_guidance": skill_context.get("sectionGuidance") if isinstance(skill_context.get("sectionGuidance"), dict) else {},
        "tool_names": _list_strings(skill_context.get("toolNames"), max_items=12, max_chars=48),
    }
    if include_excerpt:
        payload["instructions_excerpt"] = _truncate_text(skill_context.get("instructionsMarkdown") or "", 1400)
    return payload


def _looks_internal_identifier(token: str) -> bool:
    text = str(token or "").strip()
    if len(text) < 4:
        return False
    return (
        "_" in text
        or bool(re.search(r"[a-z][A-Z]", text))
        or bool(re.search(r"[A-Z]{2,}", text))
    )


def _collect_internal_identifiers(value: Any, *, depth: int = 0, bucket: Optional[set[str]] = None) -> set[str]:
    results = bucket if bucket is not None else set()
    if depth > 3:
        return results
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key or "").strip()
            if _looks_internal_identifier(key_text):
                results.add(key_text)
            _collect_internal_identifiers(item, depth=depth + 1, bucket=results)
    elif isinstance(value, list):
        for item in value[:6]:
            _collect_internal_identifiers(item, depth=depth + 1, bucket=results)
    return results


def _derive_guardrail_subject(text: Any) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    raw = raw.replace("“", "").replace("”", "").replace("‘", "").replace("’", "")
    parts = re.split(r"(是否确由|是否基于|是否|对应|基于|由)", raw, maxsplit=1)
    subject = str(parts[0] or "").strip("，。；：: ")
    subject = re.sub(r"(建议|效果预判|栏目效果预判)$", "", subject).strip("，。；：: ")
    return subject or raw


def _extract_guardrail_keywords(text: Any) -> List[str]:
    raw = str(text or "").strip()
    if not raw:
        return []
    candidates = [raw]
    candidates.extend(re.findall(r"[\u4e00-\u9fffA-Za-z0-9_-]{2,12}", raw))
    keywords: List[str] = []
    seen = set()
    for item in candidates:
        token = str(item or "").strip("，。；：: ")
        if len(token) < 2:
            continue
        key = token.lower()
        if key in seen:
            continue
        seen.add(key)
        keywords.append(token)
    return keywords[:6]


def _build_recommendation_guardrails(claim_verifications: List[Dict[str, Any]]) -> Dict[str, Any]:
    action_guardrails: List[Dict[str, Any]] = []
    claim_guardrails: List[Dict[str, Any]] = []

    for item in claim_verifications:
        if not isinstance(item, dict):
            continue
        status = str(item.get("verification_status") or "").strip().lower()
        category = str(item.get("claim_category") or "").strip()
        claim = str(item.get("claim") or "").strip()
        if status not in {"unverified", "conflicting"} or not claim:
            continue
        subject = _derive_guardrail_subject(claim)
        if category == "action":
            action_guardrails.append(
                {
                    "subject": subject,
                    "keywords": _extract_guardrail_keywords(subject),
                    "rule": "该动作的直接执行前提尚未获得充分证据支撑，正文中不得写成可立即启动动作。",
                }
            )
        elif category == "event_causality":
            claim_guardrails.append(
                {
                    "subject": subject,
                    "keywords": _extract_guardrail_keywords(subject),
                    "mode": "causal_uncertain",
                    "rule": "未验证触发点只能写成时间同步、相关性或观察线索，不得写成已证实因果。",
                }
            )
        elif category == "attribution":
            claim_guardrails.append(
                {
                    "subject": subject,
                    "keywords": _extract_guardrail_keywords(subject),
                    "mode": "attribution_uncertain",
                    "rule": "未经验证的传播链路或操盘归因只能写成待核验线索，不得写成事实判断。",
                }
            )

    return {
        "action_guardrails": action_guardrails,
        "claim_guardrails": claim_guardrails,
    }


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


def _build_scene_selection_input(
    structured_payload: Dict[str, Any],
    *,
    topic_label: str,
    skill_context: Dict[str, Any],
    scene_catalog: List[Dict[str, Any]],
) -> Dict[str, Any]:
    metrics = structured_payload.get("metrics") if isinstance(structured_payload.get("metrics"), dict) else {}
    deep_analysis = structured_payload.get("deepAnalysis") if isinstance(structured_payload.get("deepAnalysis"), dict) else {}
    themes = structured_payload.get("themes") if isinstance(structured_payload.get("themes"), list) else []
    highlight_points = structured_payload.get("highlightPoints") if isinstance(structured_payload.get("highlightPoints"), list) else []
    return {
        "topic_label": topic_label,
        "title": str(structured_payload.get("title") or "").strip(),
        "subtitle": str(structured_payload.get("subtitle") or "").strip(),
        "document_type": str(skill_context.get("documentType") or "").strip(),
        "skill_context": _compact_skill_context(skill_context, include_excerpt=False),
        "deep_analysis": {
            "event_type": str(deep_analysis.get("eventType") or "").strip(),
            "domain": str(deep_analysis.get("domain") or "").strip(),
            "stage": str(deep_analysis.get("stage") or "").strip(),
            "narrative_summary": _truncate_text(deep_analysis.get("narrativeSummary") or "", 320),
            "key_events": _list_strings(deep_analysis.get("keyEvents"), max_items=4, max_chars=90),
            "key_risks": _list_strings(deep_analysis.get("keyRisks"), max_items=4, max_chars=90),
        },
        "metrics": {
            "total_volume": int(metrics.get("totalVolume") or 0),
            "peak_date": str((metrics.get("peak") or {}).get("date") or "").strip()
            if isinstance(metrics.get("peak"), dict)
            else "",
            "peak_value": int((metrics.get("peak") or {}).get("value") or 0)
            if isinstance(metrics.get("peak"), dict)
            else 0,
        },
        "themes": [
            {
                "name": str(item.get("name") or "").strip(),
                "value": int(item.get("value") or 0),
            }
            for item in themes[:4]
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        ],
        "highlight_points": _list_strings(highlight_points, max_items=4, max_chars=90),
        "scene_catalog": [
            {
                "scene_id": str(item.get("scene_id") or "").strip(),
                "scene_label": str(item.get("scene_label") or "").strip(),
                "description": str(item.get("description") or "").strip(),
                "reference_template_name": str(item.get("reference_template_name") or item.get("reference_template") or "").strip(),
                "selection_hints": _list_strings(item.get("selection_hints") or item.get("keyword_hints"), max_items=6, max_chars=24),
                "layout_focus": _list_strings(item.get("layout_focus"), max_items=3, max_chars=80),
            }
            for item in scene_catalog
            if isinstance(item, dict)
        ],
    }


def _resolve_scene_profile(
    scene_payload: Optional[Dict[str, Any]],
    *,
    scene_catalog: List[Dict[str, Any]],
    document_type: str,
    topic_label: str,
    structured_payload: Dict[str, Any],
) -> tuple[Dict[str, Any], str]:
    selected_id = str((scene_payload or {}).get("scene_id") or "").strip()
    if selected_id:
        for item in scene_catalog:
            if not isinstance(item, dict):
                continue
            if str(item.get("scene_id") or "").strip() == selected_id:
                return item, "llm"

    deep_analysis = structured_payload.get("deepAnalysis") if isinstance(structured_payload.get("deepAnalysis"), dict) else {}
    return (
        fallback_select_full_report_scene(
            document_type,
            topic_label=topic_label,
            title=str(structured_payload.get("title") or "").strip(),
            subtitle=str(structured_payload.get("subtitle") or "").strip(),
            event_type=str(deep_analysis.get("eventType") or "").strip(),
            domain=str(deep_analysis.get("domain") or "").strip(),
            stage=str(deep_analysis.get("stage") or "").strip(),
        ),
        "fallback",
    )


def select_full_report_scene(
    structured_payload: Dict[str, Any],
    *,
    topic_label: str,
    skill_context: Dict[str, Any],
) -> tuple[Dict[str, Any], str]:
    scene_catalog = load_full_report_scene_catalog(skill_context.get("documentType"))
    scene_selection = _call_json_agent(
        build_full_report_scene_prompt(
            _build_scene_selection_input(
                structured_payload,
                topic_label=topic_label,
                skill_context=skill_context,
                scene_catalog=scene_catalog,
            )
        ),
        max_tokens=900,
    )
    return _resolve_scene_profile(
        scene_selection,
        scene_catalog=scene_catalog,
        document_type=str(skill_context.get("documentType") or "").strip(),
        topic_label=topic_label,
        structured_payload=structured_payload,
    )


def _build_layout_input(
    structured_payload: Dict[str, Any],
    *,
    topic_label: str,
    skill_context: Dict[str, Any],
    style_profile: Dict[str, Any],
    scene_profile: Dict[str, Any],
) -> Dict[str, Any]:
    metrics = structured_payload.get("metrics") if isinstance(structured_payload.get("metrics"), dict) else {}
    deep_analysis = structured_payload.get("deepAnalysis") if isinstance(structured_payload.get("deepAnalysis"), dict) else {}
    return {
        "topic_label": topic_label,
        "title": str(structured_payload.get("title") or "").strip(),
        "subtitle": str(structured_payload.get("subtitle") or "").strip(),
        "document_type": str(skill_context.get("documentType") or "").strip(),
        "skill_context": _compact_skill_context(skill_context),
        "style_profile": {
            "document_label": str(style_profile.get("document_label") or "").strip(),
            "fallback_sections": style_profile.get("fallback_sections") if isinstance(style_profile.get("fallback_sections"), list) else [],
            "fallback_tone_notes": _list_strings(style_profile.get("fallback_tone_notes"), max_items=5, max_chars=90),
        },
        "scene_profile": {
            "scene_id": str(scene_profile.get("scene_id") or "").strip(),
            "scene_label": str(scene_profile.get("scene_label") or "").strip(),
            "description": str(scene_profile.get("description") or "").strip(),
            "reference_template_name": str(scene_profile.get("reference_template_name") or scene_profile.get("reference_template") or "").strip(),
            "layout_focus": _list_strings(scene_profile.get("layout_focus"), max_items=4, max_chars=90),
            "hero_focus": _list_strings(scene_profile.get("hero_focus"), max_items=4, max_chars=80),
            "section_blueprint": scene_profile.get("section_blueprint") if isinstance(scene_profile.get("section_blueprint"), list) else [],
            "recommendation_policy": str(scene_profile.get("recommendation_policy") or "").strip(),
        },
        "deep_analysis": {
            "event_type": str(deep_analysis.get("eventType") or "").strip(),
            "domain": str(deep_analysis.get("domain") or "").strip(),
            "stage": str(deep_analysis.get("stage") or "").strip(),
            "narrative_summary": _truncate_text(deep_analysis.get("narrativeSummary") or "", 320),
            "key_events": _list_strings(deep_analysis.get("keyEvents"), max_items=5, max_chars=90),
            "key_risks": _list_strings(deep_analysis.get("keyRisks"), max_items=4, max_chars=90),
        },
        "metrics": {
            "total_volume": int(metrics.get("totalVolume") or 0),
            "peak_date": str((metrics.get("peak") or {}).get("date") or "").strip()
            if isinstance(metrics.get("peak"), dict)
            else "",
            "peak_value": int((metrics.get("peak") or {}).get("value") or 0)
            if isinstance(metrics.get("peak"), dict)
            else 0,
        },
        "highlight_points": _list_strings(structured_payload.get("highlightPoints"), max_items=5, max_chars=90),
        "themes": [
            {
                "name": str(item.get("name") or "").strip(),
                "value": int(item.get("value") or 0),
            }
            for item in (structured_payload.get("themes") or [])[:5]
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        ],
    }


def build_full_report_layout(
    structured_payload: Dict[str, Any],
    *,
    topic_label: str,
    skill_context: Dict[str, Any],
    style_profile: Dict[str, Any],
    scene_profile: Dict[str, Any],
) -> tuple[Dict[str, Any], str]:
    layout_payload = _call_json_agent(
        build_full_report_layout_prompt(
            _build_layout_input(
                structured_payload,
                topic_label=topic_label,
                skill_context=skill_context,
                style_profile=style_profile,
                scene_profile=scene_profile,
            )
        ),
        max_tokens=1400,
    )
    return _normalize_layout_plan(layout_payload, scene_profile), ("llm" if isinstance(layout_payload, dict) else "fallback")


def _fallback_layout_plan(scene_profile: Dict[str, Any]) -> Dict[str, Any]:
    sections = scene_profile.get("section_blueprint") if isinstance(scene_profile.get("section_blueprint"), list) else []
    total_words = int(scene_profile.get("default_total_words") or 2200)
    budget_weights = scene_profile.get("budget_weights") if isinstance(scene_profile.get("budget_weights"), dict) else {}
    default_weight = 1 / max(1, len(sections))
    section_plan: List[Dict[str, Any]] = []
    for item in sections:
        if not isinstance(item, dict):
            continue
        section_id = str(item.get("id") or "").strip()
        title = str(item.get("title") or "").strip()
        goal = str(item.get("goal") or "").strip()
        if not (section_id and title):
            continue
        target_words = int(total_words * float(budget_weights.get(section_id) or default_weight))
        section_plan.append(
            {
                "id": section_id,
                "title": title,
                "goal": goal,
                "priority": "high" if len(section_plan) < 2 else "medium",
                "evidence_focus": [],
                "target_words": max(140, target_words),
            }
        )
    if not section_plan:
        section_plan.append(
            {
                "id": "summary",
                "title": "摘要",
                "goal": "概括核心判断与主要边界。",
                "priority": "high",
                "evidence_focus": [],
                "target_words": 240,
            }
        )
    return {
        "layout_summary": str(scene_profile.get("description") or "").strip(),
        "hero_focus": _list_strings(scene_profile.get("hero_focus"), max_items=4, max_chars=60),
        "writing_guidelines": _list_strings(scene_profile.get("layout_focus"), max_items=5, max_chars=90),
        "section_plan": section_plan,
    }


def _normalize_layout_plan(layout_payload: Optional[Dict[str, Any]], scene_profile: Dict[str, Any]) -> Dict[str, Any]:
    fallback = _fallback_layout_plan(scene_profile)
    if not isinstance(layout_payload, dict):
        return fallback

    blueprint_map = {
        str(item.get("id") or "").strip(): item
        for item in (scene_profile.get("section_blueprint") or [])
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    normalized_sections: List[Dict[str, Any]] = []
    for item in layout_payload.get("section_plan") or []:
        if not isinstance(item, dict):
            continue
        section_id = str(item.get("id") or "").strip()
        if not section_id or section_id not in blueprint_map:
            continue
        base = blueprint_map[section_id]
        title = str(item.get("title") or base.get("title") or "").strip()
        goal = str(item.get("goal") or base.get("goal") or "").strip()
        if not (title and goal):
            continue
        target_words = int(item.get("target_words") or 0)
        normalized_sections.append(
            {
                "id": section_id,
                "title": title,
                "goal": goal,
                "priority": str(item.get("priority") or "medium").strip() or "medium",
                "evidence_focus": _list_strings(item.get("evidence_focus"), max_items=4, max_chars=90),
                "target_words": target_words if target_words > 0 else next(
                    (sec.get("target_words") for sec in fallback.get("section_plan") or [] if sec.get("id") == section_id),
                    220,
                ),
            }
        )
    if not normalized_sections:
        normalized_sections = fallback.get("section_plan") or []

    return {
        "layout_summary": str(layout_payload.get("layout_summary") or fallback.get("layout_summary") or "").strip(),
        "hero_focus": _list_strings(layout_payload.get("hero_focus"), max_items=4, max_chars=60)
        or fallback.get("hero_focus")
        or [],
        "writing_guidelines": _list_strings(layout_payload.get("writing_guidelines"), max_items=5, max_chars=90)
        or fallback.get("writing_guidelines")
        or [],
        "section_plan": normalized_sections,
    }


def build_full_report_budget(
    structured_payload: Dict[str, Any],
    *,
    topic_label: str,
    skill_context: Dict[str, Any],
    scene_profile: Dict[str, Any],
    layout_plan: Dict[str, Any],
) -> tuple[Dict[str, Any], str]:
    metrics = structured_payload.get("metrics") if isinstance(structured_payload.get("metrics"), dict) else {}
    deep_analysis = structured_payload.get("deepAnalysis") if isinstance(structured_payload.get("deepAnalysis"), dict) else {}
    facts = {
        "topic_label": topic_label,
        "document_type": str(skill_context.get("documentType") or "").strip(),
        "skill_context": _compact_skill_context(skill_context, include_excerpt=False),
        "scene_profile": {
            "scene_id": str(scene_profile.get("scene_id") or "").strip(),
            "scene_label": str(scene_profile.get("scene_label") or "").strip(),
            "description": str(scene_profile.get("description") or "").strip(),
            "default_total_words": int(scene_profile.get("default_total_words") or 0),
            "budget_weights": scene_profile.get("budget_weights") if isinstance(scene_profile.get("budget_weights"), dict) else {},
            "recommendation_policy": str(scene_profile.get("recommendation_policy") or "").strip(),
        },
        "layout_plan": layout_plan,
        "deep_analysis": {
            "event_type": str(deep_analysis.get("eventType") or "").strip(),
            "domain": str(deep_analysis.get("domain") or "").strip(),
            "stage": str(deep_analysis.get("stage") or "").strip(),
            "narrative_summary": _truncate_text(deep_analysis.get("narrativeSummary") or "", 320),
            "key_risks": _list_strings(deep_analysis.get("keyRisks"), max_items=4, max_chars=90),
        },
        "metrics": {
            "total_volume": int(metrics.get("totalVolume") or 0),
            "peak_date": str((metrics.get("peak") or {}).get("date") or "").strip()
            if isinstance(metrics.get("peak"), dict)
            else "",
            "peak_value": int((metrics.get("peak") or {}).get("value") or 0)
            if isinstance(metrics.get("peak"), dict)
            else 0,
        },
        "highlight_points": _list_strings(structured_payload.get("highlightPoints"), max_items=5, max_chars=90),
    }
    budget_payload = _call_json_agent(build_full_report_budget_prompt(facts), max_tokens=1200)
    return _normalize_section_budget(budget_payload, scene_profile, layout_plan), ("llm" if isinstance(budget_payload, dict) else "fallback")


def _fallback_section_budget(scene_profile: Dict[str, Any], layout_plan: Dict[str, Any]) -> Dict[str, Any]:
    fallback_layout = _normalize_layout_plan(layout_plan, scene_profile)
    total_words = int(scene_profile.get("default_total_words") or 2200)
    weights = scene_profile.get("budget_weights") if isinstance(scene_profile.get("budget_weights"), dict) else {}
    section_budget: List[Dict[str, Any]] = []
    for item in fallback_layout.get("section_plan") or []:
        if not isinstance(item, dict):
            continue
        section_id = str(item.get("id") or "").strip()
        if not section_id:
            continue
        target_words = int(item.get("target_words") or 0)
        if target_words <= 0:
            weight = float(weights.get(section_id) or (1 / max(1, len(fallback_layout.get("section_plan") or []))))
            target_words = int(total_words * weight)
        min_words = max(100, int(target_words * 0.7))
        max_words = max(min_words + 40, int(target_words * 1.3))
        section_budget.append(
            {
                "id": section_id,
                "target_words": target_words,
                "min_words": min_words,
                "max_words": max_words,
                "priority": str(item.get("priority") or "medium").strip() or "medium",
                "focus": str(item.get("goal") or "").strip(),
            }
        )
    return {
        "total_words": sum(int(item.get("target_words") or 0) for item in section_budget) or total_words,
        "global_guidelines": [
            "正文详略应服从章节职责，不平均分配篇幅。",
            "摘要、关键转折和风险桥接优先保留完整信息。",
            "缺乏直接证据的部分宁可压缩，也不要靠抽象论断拉长篇幅。",
        ],
        "sections": section_budget,
    }


def _normalize_section_budget(section_budget_payload: Optional[Dict[str, Any]], scene_profile: Dict[str, Any], layout_plan: Dict[str, Any]) -> Dict[str, Any]:
    fallback = _fallback_section_budget(scene_profile, layout_plan)
    if not isinstance(section_budget_payload, dict):
        return fallback

    layout_ids = {
        str(item.get("id") or "").strip(): item
        for item in (layout_plan.get("section_plan") or [])
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }
    sections: List[Dict[str, Any]] = []
    for item in section_budget_payload.get("sections") or []:
        if not isinstance(item, dict):
            continue
        section_id = str(item.get("id") or "").strip()
        if section_id not in layout_ids:
            continue
        target_words = int(item.get("target_words") or 0)
        min_words = int(item.get("min_words") or 0)
        max_words = int(item.get("max_words") or 0)
        if target_words <= 0:
            continue
        if min_words <= 0:
            min_words = max(100, int(target_words * 0.7))
        if max_words <= 0:
            max_words = max(min_words + 40, int(target_words * 1.3))
        if min_words > target_words:
            min_words = max(80, min(target_words, int(target_words * 0.8)))
        if max_words < target_words:
            max_words = target_words + 40
        sections.append(
            {
                "id": section_id,
                "target_words": target_words,
                "min_words": min_words,
                "max_words": max_words,
                "priority": str(item.get("priority") or layout_ids[section_id].get("priority") or "medium").strip() or "medium",
                "focus": str(item.get("focus") or layout_ids[section_id].get("goal") or "").strip(),
            }
        )
    if not sections:
        sections = fallback.get("sections") or []

    total_words = int(section_budget_payload.get("total_words") or 0)
    if total_words <= 0:
        total_words = sum(int(item.get("target_words") or 0) for item in sections)

    return {
        "total_words": total_words,
        "global_guidelines": _list_strings(section_budget_payload.get("global_guidelines"), max_items=5, max_chars=120)
        or fallback.get("global_guidelines")
        or [],
        "sections": sections,
    }


def _section_budget_map(section_budget: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {
        str(item.get("id") or "").strip(): item
        for item in (section_budget.get("sections") or [])
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    }


def _section_should_use_tools(section_id: str) -> bool:
    return section_id in {
        "evolution",
        "propagation",
        "timeline",
        "risk",
        "action",
        "response",
        "evidence_matrix",
        "sample_pack",
        "boundary",
    }


def _get_section_tool_focus(scene_id: str, section_id: str) -> List[str]:
    focus_map = {
        ("policy_dynamics", "evolution"): [
            "优先核查关键时间锚点、前后窗口的传播变化与讨论迁移。",
            "如需判断传播重心是否偏向场景冲突或生活化表达，可比较语义桶。",
        ],
        ("policy_dynamics", "response"): [
            "优先回查公众讨论样本，区分观点表达、生活实操和场景冲突。",
        ],
        ("policy_dynamics", "impact"): [
            "如需判断影响方向，先比较不同语义焦点，再引用风险或核验结果。",
        ],
        ("public_hotspot", "propagation"): [
            "优先围绕峰值时间窗和关键传播样本核查扩散路径。",
        ],
        ("crisis_response", "timeline"): [
            "优先围绕首发、峰值和后续窗口回查关键时间线样本。",
        ],
        ("crisis_response", "propagation"): [
            "优先核查传播节点、放大样本和焦点迁移，不要只看总量。",
        ],
    }
    return focus_map.get((str(scene_id or "").strip(), str(section_id or "").strip()), [])


def _build_section_context(section: Dict[str, Any], facts: Dict[str, Any], brief: Dict[str, Any], section_budget_map: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    section_id = str(section.get("id") or "").strip()
    scene_id = str(((facts.get("scene_profile") or {}) if isinstance(facts.get("scene_profile"), dict) else {}).get("scene_id") or "").strip()
    section_budget = section_budget_map.get(section_id) or {}
    section_evidence = _list_strings(section.get("evidence"), max_items=5, max_chars=120)
    section_evidence_pack = []
    if isinstance(facts.get("section_evidence_packs"), dict):
        pack = facts.get("section_evidence_packs", {}).get(section_id)
        section_evidence_pack = pack if isinstance(pack, list) else []
    section_fact_view = {
        "title": str(section.get("title") or "").strip(),
        "goal": str(section.get("goal") or "").strip(),
        "evidence_focus": section_evidence,
        "target_words": int(section_budget.get("target_words") or 0),
        "min_words": int(section_budget.get("min_words") or 0),
        "max_words": int(section_budget.get("max_words") or 0),
        "priority": str(section_budget.get("priority") or "medium").strip() or "medium",
        "focus": str(section_budget.get("focus") or "").strip(),
        "rewrite_instruction": str(section.get("rewrite_instruction") or "").strip(),
    }
    return {
        "topic_identifier": str(facts.get("topic_identifier") or "").strip(),
        "topic_label": str(facts.get("topic_label") or "").strip(),
        "time_range": facts.get("time_range") if isinstance(facts.get("time_range"), dict) else {},
        "section": section_fact_view,
        "brief": {
            "core_thesis": str(brief.get("core_thesis") or "").strip(),
            "tone_notes": _list_strings(brief.get("tone_notes"), max_items=4, max_chars=100),
            "preferred_terms": _list_strings(brief.get("preferred_terms"), max_items=8, max_chars=40),
        },
        "style_profile": facts.get("style_profile") if isinstance(facts.get("style_profile"), dict) else {},
        "scene_profile": facts.get("scene_profile") if isinstance(facts.get("scene_profile"), dict) else {},
        "layout_plan": facts.get("layout_plan") if isinstance(facts.get("layout_plan"), dict) else {},
        "section_budget": section_budget,
        "skill_context": facts.get("skill_context") if isinstance(facts.get("skill_context"), dict) else {},
        "deep_analysis": facts.get("deep_analysis") if isinstance(facts.get("deep_analysis"), dict) else {},
        "time_framework": facts.get("time_framework") if isinstance(facts.get("time_framework"), dict) else {},
        "indicator_relationships": facts.get("indicator_relationships") if isinstance(facts.get("indicator_relationships"), list) else [],
        "evidence_semantics": facts.get("evidence_semantics") if isinstance(facts.get("evidence_semantics"), list) else [],
        "subject_scope": facts.get("subject_scope") if isinstance(facts.get("subject_scope"), dict) else {},
        "risk_action_map": facts.get("risk_action_map") if isinstance(facts.get("risk_action_map"), list) else [],
        "claim_verifications": facts.get("claim_verifications") if isinstance(facts.get("claim_verifications"), list) else [],
        "claim_matrix": facts.get("claim_matrix") if isinstance(facts.get("claim_matrix"), list) else [],
        "section_evidence_pack": section_evidence_pack,
        "recommendation_guardrails": facts.get("recommendation_guardrails") if isinstance(facts.get("recommendation_guardrails"), dict) else {},
        "knowledge_context": facts.get("knowledge_context") if isinstance(facts.get("knowledge_context"), dict) else {},
        "tooling_context": {
            "scene_id": scene_id,
            "section_id": section_id,
            "tool_focus": _get_section_tool_focus(scene_id, section_id),
            "available_tools": [
                str(getattr(tool, "name", "") or "").strip()
                for tool in get_report_tool_bundle(scene_id, section_id)
                if str(getattr(tool, "name", "") or "").strip()
            ],
        },
    }


def generate_section_markdown(section: Dict[str, Any], facts: Dict[str, Any], brief: Dict[str, Any], section_budget: Dict[str, Any]) -> Dict[str, Any]:
    section_budget_map = _section_budget_map(section_budget)
    section_context = _build_section_context(section, facts, brief, section_budget_map)
    prompt = build_full_report_section_prompt(section_context)
    section_id = str(section.get("id") or "").strip()
    scene_profile = facts.get("scene_profile") if isinstance(facts.get("scene_profile"), dict) else {}
    scene_id = str(scene_profile.get("scene_id") or "").strip()
    section_tools = get_report_tool_bundle(scene_id, section_id)
    tool_policy = build_section_tool_policy(scene_id, section_id)
    exploration_mode = str(tool_policy.get("exploration_mode") or "off").strip()
    if _section_should_use_tools(section_id) and section_tools and exploration_mode in {"deep", "light"}:
        reuse_exploration = section.get("exploration_result") if isinstance(section.get("exploration_result"), dict) else {}
        if bool(section.get("force_reexplore")):
            reuse_exploration = {}
        exploration_result = reuse_exploration or run_section_exploration(section_context, tool_policy)
        writer_result = run_section_writer_agent(section_context, exploration_result)
        markdown = str(writer_result.get("markdown") or "").strip()
        trace = writer_result.get("trace") if isinstance(writer_result.get("trace"), dict) else {}
        exploration_trace = exploration_result.get("trace") if isinstance(exploration_result.get("trace"), dict) else {}
        combined_tool_calls = []
        combined_tool_results = []
        for source_trace in (exploration_trace, trace):
            if not isinstance(source_trace, dict):
                continue
            combined_tool_calls.extend(source_trace.get("tool_calls") or [])
            combined_tool_results.extend(source_trace.get("tool_results") or [])
        return {
            "markdown": markdown,
            "source": "langchain_agent" if markdown else "fallback",
            "tool_calls": combined_tool_calls,
            "tool_results": combined_tool_results,
            "exploration_result": {k: v for k, v in exploration_result.items() if not str(k).startswith("_")},
            "exploration_trace": exploration_trace,
            "writer_trace": trace,
            "exploration_policy": exploration_result.get("policy") if isinstance(exploration_result.get("policy"), dict) else tool_policy,
            "writer_policy": writer_result.get("policy") if isinstance(writer_result.get("policy"), dict) else {},
            "stop_reason": str((trace or {}).get("stop_reason") or (exploration_trace or {}).get("stop_reason") or "").strip(),
            "tool_call_count": int((exploration_trace or {}).get("tool_call_count") or 0) + int((trace or {}).get("tool_call_count") or 0),
            "exploration_turns": int((exploration_trace or {}).get("exploration_turns") or 0) + int((trace or {}).get("exploration_turns") or 0),
        }
    if _section_should_use_tools(section_id) and section_tools:
        result = _call_markdown_agent_with_tools(
            prompt,
            tools=section_tools,
            max_tokens=2200,
            max_tool_rounds=get_report_tool_rounds(scene_id, section_id),
        )
        markdown = str(result.get("content") or "").strip()
        return {
            "markdown": markdown,
            "source": "llm_tools" if markdown else "fallback",
            "tool_calls": result.get("tool_calls") or [],
            "tool_results": result.get("tool_results") or [],
            "exploration_result": {},
            "exploration_trace": {},
            "writer_trace": {
                "tool_calls": result.get("tool_calls") or [],
                "tool_results": result.get("tool_results") or [],
                "stop_reason": "light_tool_loop",
                "tool_call_count": len(result.get("tool_calls") or []),
                "exploration_turns": len(result.get("tool_calls") or []),
            },
            "exploration_policy": {},
            "writer_policy": tool_policy,
            "stop_reason": "light_tool_loop",
            "tool_call_count": len(result.get("tool_calls") or []),
            "exploration_turns": len(result.get("tool_calls") or []),
        }
    markdown = _call_markdown_agent(prompt, max_tokens=2200)
    return {
        "markdown": markdown,
        "source": "llm" if markdown else "fallback",
        "tool_calls": [],
        "tool_results": [],
        "exploration_result": {},
        "exploration_trace": {},
        "writer_trace": {
            "tool_calls": [],
            "tool_results": [],
            "stop_reason": "no_tools",
            "tool_call_count": 0,
            "exploration_turns": 0,
        },
        "exploration_policy": {},
        "writer_policy": tool_policy,
        "stop_reason": "no_tools",
        "tool_call_count": 0,
        "exploration_turns": 0,
    }


def _compose_section_markdown(section_outputs: List[Dict[str, Any]]) -> str:
    blocks: List[str] = []
    for item in section_outputs:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        body = str(item.get("body") or "").strip()
        if not title:
            continue
        blocks.append(f"## {title}")
        if body:
            blocks.append("")
            blocks.append(body)
        blocks.append("")
    return "\n".join(blocks).strip()

def _build_analysis_briefs(module_narratives: List[Dict[str, str]]) -> List[Dict[str, str]]:
    briefs: List[Dict[str, str]] = []
    for item in module_narratives[:7]:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or "").strip()
        finding = str(item.get("summary") or item.get("explain_text") or "").strip()
        if not (label and finding):
            continue
        briefs.append(
            {
                "dimension": label,
                "finding": finding,
                "source_note": f"基于报告时间区间内{label}相关统计与样本解读整理。",
            }
        )
    return briefs


def _build_time_framework(
    stage_notes: List[Dict[str, str]],
    bertopic_temporal: Dict[str, Any],
    metrics: Dict[str, Any],
) -> Dict[str, Any]:
    narrative_stages: List[Dict[str, str]] = []
    for item in stage_notes[:3]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        range_text = str(item.get("range") or "").strip()
        meaning = str(item.get("highlight") or "").strip()
        if title and meaning:
            narrative_stages.append(
                {
                    "stage": title,
                    "range": range_text,
                    "meaning": meaning,
                }
            )

    analytical_signals = [
        str(item).strip()
        for item in (bertopic_temporal.get("shiftSignals") or [])
        if str(item or "").strip()
    ][:4]

    peak = metrics.get("peak") if isinstance(metrics.get("peak"), dict) else {}
    peak_date = str(peak.get("date") or "").strip()
    peak_value = int(peak.get("value") or 0) if peak else 0
    mapping_rule = (
        "叙事时间用于解释传播阶段，分析时间用于提示主题切换信号；二者必须通过同一时间节点或阶段区间建立映射，"
        "不得把模型切分阶段直接当成政策周期。"
    )

    return {
        "narrative_stages": narrative_stages,
        "analytical_signals": analytical_signals,
        "anchor_node": f"{peak_date} 峰值 {peak_value}" if peak_date and peak_value else "",
        "mapping_rule": mapping_rule,
    }


def _build_indicator_relationships(
    metrics: Dict[str, Any],
    channels: List[Dict[str, Any]],
    sentiment: Dict[str, Any],
    themes: List[Dict[str, Any]],
) -> List[Dict[str, str]]:
    relationships: List[Dict[str, str]] = []

    top_channels = [item for item in channels[:2] if isinstance(item, dict) and str(item.get("name") or "").strip()]
    if len(top_channels) >= 2:
        channel_desc = "、".join(
            f"{str(item.get('name') or '').strip()}{int(item.get('value') or 0)}%"
            for item in top_channels
        )
        relationships.append(
            {
                "signal": f"渠道集中于{channel_desc}",
                "mechanism": "高占比平台决定主流分发逻辑，内容形态适配度直接影响触达效率。",
                "report_meaning": "渠道结构不是背景信息，而是后续风险判断和动作建议的前提条件。",
            }
        )

    neutral_rate = float(metrics.get("neutralRate") or 0)
    positive_rate = float(metrics.get("positiveRate") or 0)
    if neutral_rate:
        relationships.append(
            {
                "signal": f"中性情绪占比{neutral_rate:.1f}%，正面占比{positive_rate:.1f}%",
                "mechanism": "情绪表达收敛通常意味着讨论停留在信息接收或工具采纳层，未形成强价值共鸣。",
                "report_meaning": "情绪比例不能只做描述，应转译为讨论深度、转化意愿或干预难点。",
            }
        )

    if themes:
        lead_theme = themes[0]
        relationships.append(
            {
                "signal": f"主导主题为{str(lead_theme.get('name') or '').strip()}（{int(lead_theme.get('value') or 0)}）",
                "mechanism": "主题主导度变化用于解释声量波动背后的关注重心切换，而非独立指标。",
                "report_meaning": "主题指标必须与阶段变化和声量变化联动解读，避免并列罗列。",
            }
        )

    peak = metrics.get("peak") if isinstance(metrics.get("peak"), dict) else {}
    if peak and str(peak.get("date") or "").strip():
        relationships.append(
            {
                "signal": f"峰值节点为{str(peak.get('date') or '').strip()}，单日声量{int(peak.get('value') or 0)}",
                "mechanism": "峰值仅说明异常放大节点，是否构成政策触发或事件拐点，必须结合主题与阶段信息解释。",
                "report_meaning": "声量峰值是时间锚点，不等于自动成立因果结论。",
            }
        )
    return relationships


def _build_evidence_semantics(
    metrics: Dict[str, Any],
    channels: List[Dict[str, Any]],
    sentiment: Dict[str, Any],
    themes: List[Dict[str, Any]],
) -> List[Dict[str, str]]:
    evidence: List[Dict[str, str]] = []

    if channels:
        channel_text = "、".join(
            f"{str(item.get('name') or '').strip()}{int(item.get('value') or 0)}%"
            for item in channels[:3]
            if isinstance(item, dict) and str(item.get("name") or "").strip()
        )
        if channel_text:
            evidence.append(
                {
                    "judgement": "传播主阵地具有明确的平台集中性。",
                    "evidence": channel_text,
                    "source_note": "基于报告时间区间内的渠道分布统计。",
                    "boundary": "该证据可支撑平台结构判断，不自动支撑特定主体缺位或触达失效的因果结论。",
                }
            )

    if sentiment:
        evidence.append(
            {
                "judgement": "情绪表达整体收敛，讨论强度与价值对立度有限。",
                "evidence": (
                    f"中性{float(metrics.get('neutralRate') or 0):.1f}% / "
                    f"正面{float(metrics.get('positiveRate') or 0):.1f}% / "
                    f"负面{float(metrics.get('negativeRate') or 0):.1f}%"
                ),
                "source_note": "基于报告时间区间内的情绪分布统计。",
                "boundary": "该比例只能说明表达结构，不能单独推出公众态度成因。",
            }
        )

    if themes:
        top_theme = themes[0]
        evidence.append(
            {
                "judgement": "议题重心存在明确主导主题和阶段切换迹象。",
                "evidence": f"{str(top_theme.get('name') or '').strip()} {int(top_theme.get('value') or 0)}",
                "source_note": "基于主题聚类结果与时间序列映射摘要。",
                "boundary": "主题标签可用于解释关注迁移，但不能直接当作社会事实。",
            }
        )
    return evidence


def _build_subject_scope(
    *,
    topic_identifier: str,
    start: str,
    end: str,
) -> Dict[str, Any]:
    scope = summarize_source_scope(topic_identifier=topic_identifier, start=start, end=end)
    platforms = scope.get("platforms") if isinstance(scope.get("platforms"), list) else []
    authors = scope.get("authors") if isinstance(scope.get("authors"), list) else []
    coverage = scope.get("coverage") if isinstance(scope.get("coverage"), dict) else {}
    return {
        "platforms": platforms[:6],
        "authors": authors[:8],
        "coverage": coverage,
        "available_dimensions": [
            str(item).strip()
            for item in (scope.get("available_dimensions") or [])
            if str(item or "").strip()
        ][:6],
        "missing_dimensions": [
            str(item).strip()
            for item in (scope.get("missing_dimensions") or [])
            if str(item or "").strip()
        ][:6],
        "writable_subjects": [
            str(item).strip()
            for item in (scope.get("writable_subjects") or [])
            if str(item or "").strip()
        ][:6],
        "prohibited_inference": [
            str(item).strip()
            for item in (scope.get("prohibited_inference") or [])
            if str(item or "").strip()
        ][:4],
        "boundary_summary": str(scope.get("boundary_summary") or "").strip(),
    }


def _build_risk_action_map(
    deep_analysis: Dict[str, Any],
    recommendation_guardrails: Dict[str, Any],
) -> List[Dict[str, str]]:
    risks = [
        str(item).strip()
        for item in (deep_analysis.get("keyRisks") or [])
        if str(item or "").strip()
    ][:5]
    mappings: List[Dict[str, str]] = []
    for risk in risks:
        action_condition = ""
        for guardrail in recommendation_guardrails.get("action_guardrails") or []:
            subject = str(guardrail.get("subject") or "").strip()
            if any(token in subject for token in re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,8}", risk)):
                action_condition = str(guardrail.get("rule") or "").strip()
                break
        if not action_condition:
            first_action_guardrail = next(
                (
                    str(item.get("rule") or "").strip()
                    for item in (recommendation_guardrails.get("action_guardrails") or [])
                    if str(item.get("rule") or "").strip()
                ),
                "",
            )
            action_condition = first_action_guardrail
        mappings.append(
            {
                "risk": risk,
                "mechanism_bridge": "建议必须先说明该风险如何作用于传播结构、表达机制或治理触点，再进入动作设计。",
                "action_condition": action_condition or "若缺乏明确前提，应保留为待复核或条件性建议。",
            }
        )

    for guardrail in recommendation_guardrails.get("action_guardrails") or []:
        subject = str(guardrail.get("subject") or "").strip()
        if not subject:
            continue
        mappings.append(
            {
                "risk": f"{subject}相关动作存在执行前提缺口",
                "mechanism_bridge": "建议动作若依赖外部验证前提，应先闭合执行条件，再进入行动表述。",
                "action_condition": str(guardrail.get("rule") or "").strip(),
            }
        )
    return mappings[:8]


def _build_claim_candidates(
    *,
    metrics: Dict[str, Any],
    conclusion_mining: Dict[str, Any],
) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    peak = metrics.get("peak") if isinstance(metrics.get("peak"), dict) else {}
    peak_date = str(peak.get("date") or "").strip()

    if peak_date:
        candidates.append(
            {
                "claim": f"{peak_date}峰值由政策发布直接触发" if peak_date else "峰值由政策发布直接触发",
                "entities": ["政策", "通知", "条例", "发布", "控烟", "禁烟"],
                "platforms": ["新闻", "微博", "视频", "自媒体号"],
                "retrieve_mode": "event_verification",
                "claim_category": "event_causality",
            }
        )

    recommendations = conclusion_mining.get("recommendations") if isinstance(conclusion_mining.get("recommendations"), list) else []
    for item in recommendations[:4]:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        candidates.append(
            {
                "claim": text,
                "entities": _extract_guardrail_keywords(text)[:6],
                "platforms": ["视频", "自媒体号", "微博", "新闻"],
                "retrieve_mode": "action_validation",
                "claim_category": "action",
            }
        )

    for item in recommendations[:4]:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if "鲁迅" not in text and "文化符号" not in text:
            continue
        tokens = re.findall(r"[\u4e00-\u9fffA-Za-z0-9_-]{2,12}", text)
        candidates.append(
            {
                "claim": text,
                "entities": tokens[:6],
                "platforms": ["视频", "自媒体号", "微博"],
                "retrieve_mode": "narrative_verification",
                "claim_category": "attribution",
            }
        )

    deduped: List[Dict[str, Any]] = []
    seen = set()
    for item in candidates:
        claim = str(item.get("claim") or "").strip()
        if not claim:
            continue
        if claim in seen:
            continue
        seen.add(claim)
        deduped.append(item)
    return deduped[:6]


def _build_claim_verifications(
    *,
    topic_identifier: str,
    start: str,
    end: str,
    metrics: Dict[str, Any],
    conclusion_mining: Dict[str, Any],
) -> List[Dict[str, Any]]:
    verifications: List[Dict[str, Any]] = []
    candidates = _build_claim_candidates(
        metrics=metrics,
        conclusion_mining=conclusion_mining,
    )
    for candidate in candidates:
        try:
            result = verify_claim_with_records(
                topic_identifier=topic_identifier,
                start=start,
                end=end,
                claim=str(candidate.get("claim") or "").strip(),
                entities=[str(item).strip() for item in (candidate.get("entities") or []) if str(item or "").strip()],
                platforms=[str(item).strip() for item in (candidate.get("platforms") or []) if str(item or "").strip()],
                retrieve_mode=str(candidate.get("retrieve_mode") or "claim_verification").strip(),
                top_k=12,
            )
        except Exception:
            continue
        verifications.append(
            {
                "claim": result.get("claim"),
                "claim_category": str(candidate.get("claim_category") or "").strip(),
                "verification_status": result.get("verification_status"),
                "insufficient_evidence": bool(result.get("insufficient_evidence")),
                "source_distribution": result.get("source_distribution") if isinstance(result.get("source_distribution"), dict) else {},
                "representative_quotes": result.get("representative_quotes") if isinstance(result.get("representative_quotes"), list) else [],
                "supporting_items": result.get("supporting_items") if isinstance(result.get("supporting_items"), list) else [],
                "contradicting_items": result.get("contradicting_items") if isinstance(result.get("contradicting_items"), list) else [],
            }
        )
    return verifications[:6]


def _build_claim_matrix(claim_verifications: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    strength_map = {
        "supported": "factual",
        "partially_supported": "bounded",
        "unverified": "manual_review",
        "conflicting": "disputed",
    }
    matrix: List[Dict[str, Any]] = []
    for item in claim_verifications:
        if not isinstance(item, dict):
            continue
        claim = str(item.get("claim") or "").strip()
        if not claim:
            continue
        status = str(item.get("verification_status") or "").strip().lower() or "unverified"
        quotes = [
            str(entry).strip()
            for entry in (item.get("representative_quotes") or [])
            if str(entry or "").strip()
        ]
        matrix.append(
            {
                "claim": claim,
                "claim_category": str(item.get("claim_category") or "").strip(),
                "verification_status": status,
                "write_policy": strength_map.get(status, "manual_review"),
                "keywords": _extract_guardrail_keywords(claim),
                "representative_quote": quotes[0] if quotes else "",
            }
        )
    return matrix


def _build_section_evidence_packs(
    scene_profile: Dict[str, Any],
    facts: Dict[str, Any],
    claim_matrix: List[Dict[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    packs: Dict[str, List[Dict[str, Any]]] = {}
    evidence_semantics = facts.get("evidence_semantics") if isinstance(facts.get("evidence_semantics"), list) else []
    indicator_relationships = facts.get("indicator_relationships") if isinstance(facts.get("indicator_relationships"), list) else []
    time_framework = facts.get("time_framework") if isinstance(facts.get("time_framework"), dict) else {}
    risk_action_map = facts.get("risk_action_map") if isinstance(facts.get("risk_action_map"), list) else []
    module_narratives = facts.get("module_narratives") if isinstance(facts.get("module_narratives"), list) else []
    key_events = facts.get("deep_analysis", {}).get("key_events") if isinstance(facts.get("deep_analysis"), dict) else []
    themes = facts.get("themes") if isinstance(facts.get("themes"), list) else []

    def add_entry(bucket: List[Dict[str, Any]], kind: str, summary: str, *, detail: str = "", status: str = "") -> None:
        text = str(summary or "").strip()
        if not text:
            return
        key = (kind, text)
        seen = {(str(item.get("kind") or "").strip(), str(item.get("summary") or "").strip()) for item in bucket if isinstance(item, dict)}
        if key in seen:
            return
        bucket.append(
            {
                "kind": kind,
                "summary": text,
                "detail": str(detail or "").strip(),
                "status": str(status or "").strip(),
            }
        )

    for section in (scene_profile.get("section_blueprint") or []):
        if not isinstance(section, dict):
            continue
        section_id = str(section.get("id") or "").strip()
        bucket: List[Dict[str, Any]] = []

        if section_id == "summary":
            for item in evidence_semantics[:2]:
                if isinstance(item, dict):
                    add_entry(bucket, "evidence", str(item.get("judgement") or "").strip(), detail=str(item.get("evidence") or "").strip())
            for item in claim_matrix[:2]:
                if isinstance(item, dict):
                    add_entry(bucket, "claim", str(item.get("claim") or "").strip(), detail=str(item.get("representative_quote") or "").strip(), status=str(item.get("verification_status") or "").strip())

        if section_id in {"trend", "timeline", "evolution"}:
            for item in (time_framework.get("narrative_stages") or [])[:3]:
                if isinstance(item, dict):
                    add_entry(bucket, "time_stage", str(item.get("stage") or "").strip(), detail=str(item.get("meaning") or "").strip())
            for item in key_events[:3]:
                add_entry(bucket, "key_event", str(item or "").strip())
            for item in claim_matrix:
                if str(item.get("claim_category") or "").strip() == "event_causality":
                    add_entry(bucket, "claim", str(item.get("claim") or "").strip(), detail=str(item.get("representative_quote") or "").strip(), status=str(item.get("verification_status") or "").strip())

        if section_id in {"propagation", "channels", "benchmark"}:
            for item in indicator_relationships[:3]:
                if isinstance(item, dict):
                    add_entry(bucket, "indicator", str(item.get("signal") or "").strip(), detail=str(item.get("mechanism") or "").strip())
            for item in module_narratives[:2]:
                if isinstance(item, dict):
                    add_entry(bucket, "narrative", str(item.get("label") or "").strip(), detail=str(item.get("summary") or item.get("explain_text") or "").strip())

        if section_id in {"focus", "topics", "attitude", "response"}:
            for item in evidence_semantics[:3]:
                if isinstance(item, dict):
                    add_entry(bucket, "evidence", str(item.get("judgement") or "").strip(), detail=str(item.get("boundary") or "").strip())
            for item in themes[:2]:
                if isinstance(item, dict):
                    add_entry(bucket, "theme", str(item.get("name") or "").strip(), detail=str(item.get("value") or "").strip())

        if section_id in {"mechanism", "impact", "risk", "action", "response", "boundary"}:
            for item in risk_action_map[:3]:
                if isinstance(item, dict):
                    add_entry(bucket, "risk_map", str(item.get("risk") or "").strip(), detail=str(item.get("mechanism") or item.get("action_condition") or "").strip())
            for item in claim_matrix:
                if str(item.get("verification_status") or "").strip() in {"unverified", "conflicting"}:
                    add_entry(bucket, "claim_boundary", str(item.get("claim") or "").strip(), detail=str(item.get("write_policy") or "").strip(), status=str(item.get("verification_status") or "").strip())

        if not bucket:
            for item in evidence_semantics[:2]:
                if isinstance(item, dict):
                    add_entry(bucket, "evidence", str(item.get("judgement") or "").strip(), detail=str(item.get("evidence") or "").strip())
        packs[section_id] = bucket[:6]
    return packs


def _collect_claim_gate_stats(claim_matrix: List[Dict[str, Any]]) -> Dict[str, int]:
    stats = {"supported": 0, "partially_supported": 0, "unverified": 0, "conflicting": 0}
    for item in claim_matrix:
        status = str(item.get("verification_status") or "").strip().lower()
        if status in stats:
            stats[status] += 1
    return stats


def _call_evidence_analyst(
    base_facts: Dict[str, Any],
    scene_profile: Dict[str, Any],
    section_evidence_packs: Dict[str, List[Dict[str, Any]]],
    *,
    event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    prompt_facts = {
        "topic_identifier": base_facts.get("topic_identifier"),
        "topic_label": base_facts.get("topic_label"),
        "scene_profile": {
            "scene_id": scene_profile.get("scene_id"),
            "scene_label": scene_profile.get("scene_label"),
            "description": scene_profile.get("description"),
        },
        "time_range": base_facts.get("time_range"),
        "analysis_briefs": base_facts.get("analysis_briefs"),
        "claim_verifications": base_facts.get("claim_verifications"),
        "section_evidence_packs": section_evidence_packs,
    }
    runner = create_analysis_agent_runner(
        str(scene_profile.get("scene_id") or "").strip(),
        "evidence_analyst",
        {
            "topic_identifier": str(base_facts.get("topic_identifier") or "").strip(),
            "topic_label": str(base_facts.get("topic_label") or "").strip(),
            "time_range": base_facts.get("time_range") if isinstance(base_facts.get("time_range"), dict) else {},
            "scene_id": str(scene_profile.get("scene_id") or "").strip(),
            "section_id": "evidence_analyst",
            "claim_matrix": _build_claim_matrix(base_facts.get("claim_verifications") if isinstance(base_facts.get("claim_verifications"), list) else []),
            "section_evidence_pack": [],
            "style_contract": base_facts.get("style_profile") if isinstance(base_facts.get("style_profile"), dict) else {},
        },
        system_prompt="你是 evidence_analyst。你可以主动调用工具补充时间窗、原始条目和政策文本证据，最后只输出合法 JSON。",
        max_tokens=2200,
    )
    if runner is None:
        return {"evidence_semantics": [], "section_evidence_packs": section_evidence_packs, "trace": {}}
    prompt = (
        "请围绕当前报告场景补充一层更可写的证据语义，只输出 JSON。\n"
        "JSON schema:\n"
        "{\n"
        '  "evidence_semantics": [\n'
        '    {"judgement":"...", "evidence":"...", "source_note":"...", "boundary":"..."}\n'
        "  ],\n"
        '  "section_evidence_packs": {"section_id":[{"kind":"...", "summary":"...", "detail":"...", "status":"..."}]}\n'
        "}\n\n"
        f"【facts】\n{json.dumps(prompt_facts, ensure_ascii=False)}"
    )
    result = run_report_agent_step(runner, {"prompt": prompt})
    payload = _safe_json_loads_text(str(result.get("content") or ""))
    trace = result.get("trace") if isinstance(result.get("trace"), dict) else {}
    _emit_agent_trace_events(
        event_callback,
        agent="evidence_analyst",
        phase="analysis",
        trace=trace,
        tools_allowed=_tool_names_from_objects((runner.get("policy") or {}).get("allowed_tools") if isinstance(runner.get("policy"), dict) else []),
        tool_policy_mode=str((runner.get("policy") or {}).get("exploration_mode") or "analysis").strip(),
        scene_id=str(scene_profile.get("scene_id") or "").strip(),
        section_id="evidence_analyst",
        start_message="evidence_analyst 正在补充时间窗、原始条目与政策文本证据。",
        memo_title="Evidence Analyst 公开备忘录",
    )
    return {
        "evidence_semantics": payload.get("evidence_semantics") if isinstance(payload.get("evidence_semantics"), list) else [],
        "section_evidence_packs": payload.get("section_evidence_packs") if isinstance(payload.get("section_evidence_packs"), dict) else section_evidence_packs,
        "trace": trace,
    }


def _call_mechanism_analyst(
    base_facts: Dict[str, Any],
    scene_profile: Dict[str, Any],
    *,
    event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    prompt_facts = {
        "topic_identifier": base_facts.get("topic_identifier"),
        "topic_label": base_facts.get("topic_label"),
        "scene_profile": {
            "scene_id": scene_profile.get("scene_id"),
            "scene_label": scene_profile.get("scene_label"),
            "layout_focus": scene_profile.get("layout_focus"),
        },
        "deep_analysis": base_facts.get("deep_analysis"),
        "analysis_briefs": base_facts.get("analysis_briefs"),
        "evidence_semantics": base_facts.get("evidence_semantics"),
        "indicator_relationships": base_facts.get("indicator_relationships"),
        "time_framework": base_facts.get("time_framework"),
        "claim_verifications": base_facts.get("claim_verifications"),
    }
    runner = create_analysis_agent_runner(
        str(scene_profile.get("scene_id") or "").strip(),
        "mechanism_analyst",
        {
            "topic_identifier": str(base_facts.get("topic_identifier") or "").strip(),
            "topic_label": str(base_facts.get("topic_label") or "").strip(),
            "time_range": base_facts.get("time_range") if isinstance(base_facts.get("time_range"), dict) else {},
            "scene_id": str(scene_profile.get("scene_id") or "").strip(),
            "section_id": "mechanism_analyst",
            "claim_matrix": _build_claim_matrix(base_facts.get("claim_verifications") if isinstance(base_facts.get("claim_verifications"), list) else []),
            "section_evidence_pack": [],
            "style_contract": base_facts.get("style_profile") if isinstance(base_facts.get("style_profile"), dict) else {},
        },
        system_prompt="你是 mechanism_analyst。允许调用工具补充证据或理论锚点，最终必须只输出合法 JSON。",
        max_tokens=2200,
    )
    payload = {}
    trace: Dict[str, Any] = {}
    if runner is not None:
        result = run_report_agent_step(
            runner,
            {"prompt": build_full_report_mechanism_prompt(prompt_facts)},
        )
        payload = _safe_json_loads_text(str(result.get("content") or ""))
        trace = result.get("trace") if isinstance(result.get("trace"), dict) else {}
        _emit_agent_trace_events(
            event_callback,
            agent="mechanism_analyst",
            phase="analysis",
            trace=trace,
            tools_allowed=_tool_names_from_objects((runner.get("policy") or {}).get("allowed_tools") if isinstance(runner.get("policy"), dict) else []),
            tool_policy_mode=str((runner.get("policy") or {}).get("exploration_mode") or "analysis").strip(),
            scene_id=str(scene_profile.get("scene_id") or "").strip(),
            section_id="mechanism_analyst",
            start_message="mechanism_analyst 正在整理指标关系、时序映射与机制解释。",
            memo_title="Mechanism Analyst 公开备忘录",
        )
    if not payload:
        payload = _call_json_agent(build_full_report_mechanism_prompt(prompt_facts), max_tokens=2200)
    if not isinstance(payload, dict):
        return {}
    return {
        "evidence_semantics": payload.get("evidence_semantics") if isinstance(payload.get("evidence_semantics"), list) else [],
        "indicator_relationships": payload.get("indicator_relationships") if isinstance(payload.get("indicator_relationships"), list) else [],
        "time_framework": payload.get("time_framework") if isinstance(payload.get("time_framework"), dict) else {},
        "analysis_trace": {"mechanism_analyst": trace},
    }


def _call_claim_judge(
    base_facts: Dict[str, Any],
    scene_profile: Dict[str, Any],
    *,
    event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    existing_matrix = _build_claim_matrix(base_facts.get("claim_verifications") if isinstance(base_facts.get("claim_verifications"), list) else [])
    prompt_facts = {
        "topic_identifier": base_facts.get("topic_identifier"),
        "topic_label": base_facts.get("topic_label"),
        "scene_profile": {
            "scene_id": scene_profile.get("scene_id"),
            "scene_label": scene_profile.get("scene_label"),
        },
        "claim_verifications": base_facts.get("claim_verifications"),
        "existing_claim_matrix": existing_matrix,
    }
    runner = create_analysis_agent_runner(
        str(scene_profile.get("scene_id") or "").strip(),
        "claim_judge",
        {
            "topic_identifier": str(base_facts.get("topic_identifier") or "").strip(),
            "topic_label": str(base_facts.get("topic_label") or "").strip(),
            "time_range": base_facts.get("time_range") if isinstance(base_facts.get("time_range"), dict) else {},
            "scene_id": str(scene_profile.get("scene_id") or "").strip(),
            "section_id": "claim_judge",
            "claim_matrix": existing_matrix,
            "section_evidence_pack": [],
            "style_contract": base_facts.get("style_profile") if isinstance(base_facts.get("style_profile"), dict) else {},
        },
        system_prompt="你是 claim_judge。必要时调用工具补充核验，最终只输出合法 JSON。",
        max_tokens=1800,
    )
    if runner is None:
        return {"claim_matrix": existing_matrix, "trace": {}}
    prompt = (
        "请核查当前 claim matrix 是否仍有需要补充核验或降级的断言，只输出 JSON。\n"
        "JSON schema:\n"
        "{\n"
        '  "claim_matrix": [\n'
        '    {"claim":"...", "claim_category":"...", "verification_status":"supported|partially_supported|unverified|conflicting", "write_policy":"factual|bounded|manual_review|disputed", "keywords":["..."], "representative_quote":"..."}\n'
        "  ]\n"
        "}\n\n"
        f"【facts】\n{json.dumps(prompt_facts, ensure_ascii=False)}"
    )
    result = run_report_agent_step(runner, {"prompt": prompt})
    payload = _safe_json_loads_text(str(result.get("content") or ""))
    rows = payload.get("claim_matrix") if isinstance(payload, dict) and isinstance(payload.get("claim_matrix"), list) else existing_matrix
    trace = result.get("trace") if isinstance(result.get("trace"), dict) else {}
    _emit_agent_trace_events(
        event_callback,
        agent="claim_judge",
        phase="analysis",
        trace=trace,
        tools_allowed=_tool_names_from_objects((runner.get("policy") or {}).get("allowed_tools") if isinstance(runner.get("policy"), dict) else []),
        tool_policy_mode=str((runner.get("policy") or {}).get("exploration_mode") or "analysis").strip(),
        scene_id=str(scene_profile.get("scene_id") or "").strip(),
        section_id="claim_judge",
        start_message="claim_judge 正在检查哪些断言可写成事实、倾向判断或边界提示。",
        memo_title="Claim Judge 公开备忘录",
    )
    return {
        "claim_matrix": rows,
        "trace": trace,
    }


def _call_risk_mapper(base_facts: Dict[str, Any], claim_matrix: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    prompt_facts = {
        "topic_label": base_facts.get("topic_label"),
        "deep_analysis": base_facts.get("deep_analysis"),
        "claim_matrix": claim_matrix,
        "recommendation_guardrails": base_facts.get("recommendation_guardrails"),
        "risk_action_map": base_facts.get("risk_action_map"),
    }
    payload = _call_json_agent(build_full_report_risk_map_prompt(prompt_facts), max_tokens=1800)
    if not isinstance(payload, dict):
        return []
    rows = payload.get("risk_action_map")
    return rows if isinstance(rows, list) else []


def _fallback_style_review(section_body: str, prior_outputs: List[Dict[str, Any]]) -> Dict[str, Any]:
    text = str(section_body or "").strip()
    issues: List[str] = []
    patterns = [
        "并非偶然",
        "并非自然演进",
        "更值得注意的是",
        "这并非",
        "该现象并非",
        "标志着",
    ]
    hits = [pattern for pattern in patterns if pattern and pattern in text]
    if len(hits) >= 2:
        issues.append("固定转折句和大判断句过多，模板腔明显。")
    prior_text = "\n".join(str(item.get("body") or "") for item in prior_outputs if isinstance(item, dict))
    repeated = [pattern for pattern in patterns if pattern and pattern in text and pattern in prior_text]
    if repeated:
        issues.append("本节与前文共享同一组分析句法，节间同质化明显。")
    if len(text.split("。")) <= 2:
        issues.append("本节过度压缩，容易退化成统一摘要腔。")
    return {
        "pass": not issues,
        "issues": issues,
        "rewrite_instruction": "减少固定转折句和大判断句，改成先落本节独有证据，再解释机制与含义。" if issues else "",
        "style_notes": [],
    }


def _call_style_critic(
    *,
    section: Dict[str, Any],
    section_body: str,
    prior_outputs: List[Dict[str, Any]],
    facts: Dict[str, Any],
) -> Dict[str, Any]:
    prompt_facts = {
        "section": section,
        "section_body": section_body,
        "prior_sections": [
            {
                "title": str(item.get("title") or "").strip(),
                "body_preview": _truncate_text(item.get("body") or "", 240),
            }
            for item in prior_outputs[-2:]
            if isinstance(item, dict)
        ],
        "scene_profile": facts.get("scene_profile"),
        "style_profile": facts.get("style_profile"),
    }
    payload = _call_json_agent(build_full_report_style_critic_prompt(prompt_facts), max_tokens=1400)
    if not isinstance(payload, dict):
        return _fallback_style_review(section_body, prior_outputs)
    if "pass" not in payload:
        return _fallback_style_review(section_body, prior_outputs)
    return {
        "pass": bool(payload.get("pass")),
        "issues": _list_strings(payload.get("issues"), max_items=4, max_chars=120),
        "rewrite_instruction": str(payload.get("rewrite_instruction") or "").strip(),
        "style_notes": _list_strings(payload.get("style_notes"), max_items=3, max_chars=100),
    }


def _fallback_fact_review(section_body: str, facts: Dict[str, Any]) -> Dict[str, Any]:
    issues = _find_report_guardrail_violations(section_body, facts)
    claim_matrix = facts.get("claim_matrix") if isinstance(facts.get("claim_matrix"), list) else []
    text = str(section_body or "")
    for item in claim_matrix:
        if not isinstance(item, dict):
            continue
        status = str(item.get("verification_status") or "").strip()
        if status not in {"unverified", "conflicting"}:
            continue
        keywords = [str(token).strip() for token in (item.get("keywords") or []) if str(token or "").strip()]
        if keywords and any(token in text for token in keywords) and re.search(r"(引爆|导致|证明|说明|表明|确由|主动策划|算法助推)", text):
            issues.append("未通过裁决的断言被写成了确定判断。")
            break
    return {
        "pass": not issues,
        "issues": issues,
        "rewrite_instruction": "删除未获验证的因果或归因句，把该判断降级为观察线索、条件性判断或边界说明。" if issues else "",
        "guardrail_hits": issues,
    }


def _call_fact_critic(*, section: Dict[str, Any], section_body: str, facts: Dict[str, Any]) -> Dict[str, Any]:
    prompt_facts = {
        "section": section,
        "section_body": section_body,
        "claim_matrix": facts.get("claim_matrix") if isinstance(facts.get("claim_matrix"), list) else [],
        "recommendation_guardrails": facts.get("recommendation_guardrails") if isinstance(facts.get("recommendation_guardrails"), dict) else {},
    }
    payload = _call_json_agent(build_full_report_fact_critic_prompt(prompt_facts), max_tokens=1400)
    if not isinstance(payload, dict):
        return _fallback_fact_review(section_body, facts)
    if "pass" not in payload:
        return _fallback_fact_review(section_body, facts)
    return {
        "pass": bool(payload.get("pass")),
        "issues": _list_strings(payload.get("issues"), max_items=4, max_chars=120),
        "rewrite_instruction": str(payload.get("rewrite_instruction") or "").strip(),
        "guardrail_hits": _list_strings(payload.get("guardrail_hits"), max_items=4, max_chars=120),
    }


def _should_use_llm_critics(section: Dict[str, Any], current_output: Dict[str, Any], facts: Dict[str, Any]) -> bool:
    scene_id = str(((facts.get("scene_profile") or {}) if isinstance(facts.get("scene_profile"), dict) else {}).get("scene_id") or "").strip()
    section_id = str(section.get("id") or "").strip()
    source = str(current_output.get("source") or "").strip()
    return source == "langchain_agent" and (scene_id, section_id) in {
        ("policy_dynamics", "evolution"),
        ("public_hotspot", "propagation"),
        ("crisis_response", "timeline"),
        ("crisis_response", "propagation"),
    }


def _merge_analysis_outputs_into_facts(base_facts: Dict[str, Any], analysis_outputs: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base_facts or {})
    for key in (
        "evidence_semantics",
        "indicator_relationships",
        "time_framework",
        "claim_matrix",
        "risk_action_map",
        "section_evidence_packs",
        "claim_gate_stats",
    ):
        if key in analysis_outputs:
            merged[key] = analysis_outputs.get(key)
    return merged


def _run_full_report_analysis_graph(
    *,
    topic_identifier: str,
    topic_label: str,
    start: str,
    end: str,
    structured_payload: Dict[str, Any],
    knowledge_context: Dict[str, Any],
    skill_context: Dict[str, Any],
    style_profile: Dict[str, Any],
    event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    from langgraph.graph import END, StateGraph
    ensure_langchain_uuid_compat()

    def scene_router_node(state: FullReportAnalysisState) -> Dict[str, Any]:
        _emit_static_agent_activity(
            state.get("event_callback"),
            agent="scene_router",
            phase="analysis",
            message="scene_router 正在选择当前报告场景。",
            title="Scene Router 已启动",
        )
        scene_profile, scene_source = select_full_report_scene(
            state.get("structured_payload") or {},
            topic_label=str(state.get("topic_label") or "").strip(),
            skill_context=state.get("skill_context") if isinstance(state.get("skill_context"), dict) else {},
        )
        return {
            "scene_profile": scene_profile,
            "scene_source": scene_source,
            "analysis_graph_source": "scene_router",
        }

    def evidence_analyst_node(state: FullReportAnalysisState) -> Dict[str, Any]:
        scene_profile = state.get("scene_profile") if isinstance(state.get("scene_profile"), dict) else {}
        base_facts = _build_compact_report_facts(
            state.get("structured_payload") if isinstance(state.get("structured_payload"), dict) else {},
            topic_identifier=str(state.get("topic_identifier") or "").strip(),
            topic_label=str(state.get("topic_label") or "").strip(),
            start=str(state.get("start") or "").strip(),
            end=str(state.get("end") or "").strip(),
            knowledge_context=state.get("knowledge_context") if isinstance(state.get("knowledge_context"), dict) else {},
            skill_context=state.get("skill_context") if isinstance(state.get("skill_context"), dict) else {},
            style_profile=state.get("style_profile") if isinstance(state.get("style_profile"), dict) else {},
            scene_profile=scene_profile,
            layout_plan={},
            section_budget={},
        )
        claim_matrix = _build_claim_matrix(base_facts.get("claim_verifications") if isinstance(base_facts.get("claim_verifications"), list) else [])
        section_evidence_packs = _build_section_evidence_packs(scene_profile, base_facts, claim_matrix)
        evidence_result = _call_evidence_analyst(
            base_facts,
            scene_profile,
            section_evidence_packs,
            event_callback=state.get("event_callback"),
        )
        analysis_outputs = {
            "evidence_semantics": evidence_result.get("evidence_semantics") if isinstance(evidence_result.get("evidence_semantics"), list) and evidence_result.get("evidence_semantics") else (base_facts.get("evidence_semantics") if isinstance(base_facts.get("evidence_semantics"), list) else []),
            "indicator_relationships": base_facts.get("indicator_relationships") if isinstance(base_facts.get("indicator_relationships"), list) else [],
            "time_framework": base_facts.get("time_framework") if isinstance(base_facts.get("time_framework"), dict) else {},
            "claim_matrix": claim_matrix,
            "risk_action_map": base_facts.get("risk_action_map") if isinstance(base_facts.get("risk_action_map"), list) else [],
            "section_evidence_packs": evidence_result.get("section_evidence_packs") if isinstance(evidence_result.get("section_evidence_packs"), dict) else section_evidence_packs,
            "claim_gate_stats": _collect_claim_gate_stats(claim_matrix),
        }
        return {
            "base_facts": base_facts,
            "analysis_outputs": analysis_outputs,
            "analysis_trace": {"evidence_analyst": evidence_result.get("trace") if isinstance(evidence_result.get("trace"), dict) else {}},
        }

    def mechanism_analyst_node(state: FullReportAnalysisState) -> Dict[str, Any]:
        base_facts = state.get("base_facts") if isinstance(state.get("base_facts"), dict) else {}
        scene_profile = state.get("scene_profile") if isinstance(state.get("scene_profile"), dict) else {}
        refined = _call_mechanism_analyst(
            base_facts,
            scene_profile,
            event_callback=state.get("event_callback"),
        )
        outputs = dict(state.get("analysis_outputs") or {})
        if refined.get("evidence_semantics"):
            outputs["evidence_semantics"] = refined.get("evidence_semantics")
        if refined.get("indicator_relationships"):
            outputs["indicator_relationships"] = refined.get("indicator_relationships")
        if refined.get("time_framework"):
            outputs["time_framework"] = refined.get("time_framework")
        trace = dict(state.get("analysis_trace") or {})
        if isinstance(refined.get("analysis_trace"), dict):
            trace.update(refined.get("analysis_trace") or {})
        return {"analysis_outputs": outputs, "analysis_graph_source": "analysis_graph", "analysis_trace": trace}

    def claim_judge_node(state: FullReportAnalysisState) -> Dict[str, Any]:
        base_facts = state.get("base_facts") if isinstance(state.get("base_facts"), dict) else {}
        claim_judge_result = _call_claim_judge(
            base_facts,
            state.get("scene_profile") if isinstance(state.get("scene_profile"), dict) else {},
            event_callback=state.get("event_callback"),
        )
        claim_matrix = claim_judge_result.get("claim_matrix") if isinstance(claim_judge_result.get("claim_matrix"), list) else _build_claim_matrix(base_facts.get("claim_verifications") if isinstance(base_facts.get("claim_verifications"), list) else [])
        outputs = dict(state.get("analysis_outputs") or {})
        outputs["claim_matrix"] = claim_matrix
        outputs["claim_gate_stats"] = _collect_claim_gate_stats(claim_matrix)
        outputs["section_evidence_packs"] = _build_section_evidence_packs(
            state.get("scene_profile") if isinstance(state.get("scene_profile"), dict) else {},
            _merge_analysis_outputs_into_facts(base_facts, outputs),
            claim_matrix,
        )
        trace = dict(state.get("analysis_trace") or {})
        trace["claim_judge"] = claim_judge_result.get("trace") if isinstance(claim_judge_result.get("trace"), dict) else {}
        return {"analysis_outputs": outputs, "analysis_trace": trace}

    def risk_mapper_node(state: FullReportAnalysisState) -> Dict[str, Any]:
        base_facts = state.get("base_facts") if isinstance(state.get("base_facts"), dict) else {}
        claim_matrix = (state.get("analysis_outputs") or {}).get("claim_matrix") if isinstance(state.get("analysis_outputs"), dict) else []
        scene_state = state.get("scene_profile") if isinstance(state.get("scene_profile"), dict) else {}
        _emit_static_agent_activity(
            state.get("event_callback"),
            agent="risk_mapper",
            phase="analysis",
            message="risk_mapper 正在整理风险机制与动作前提。",
            title="Risk Mapper 已启动",
            scene_id=str(scene_state.get("scene_id") or "").strip(),
        )
        refined = _call_risk_mapper(base_facts, claim_matrix if isinstance(claim_matrix, list) else [])
        outputs = dict(state.get("analysis_outputs") or {})
        if refined:
            outputs["risk_action_map"] = refined
        return {"analysis_outputs": outputs}

    def analysis_supervisor_node(state: FullReportAnalysisState) -> Dict[str, Any]:
        outputs = state.get("analysis_outputs") if isinstance(state.get("analysis_outputs"), dict) else {}
        issues: List[str] = []
        if not outputs.get("evidence_semantics"):
            issues.append("缺少 evidence_semantics")
        if not outputs.get("indicator_relationships"):
            issues.append("缺少 indicator_relationships")
        if not outputs.get("claim_matrix"):
            issues.append("缺少 claim_matrix")
        packs = outputs.get("section_evidence_packs") if isinstance(outputs.get("section_evidence_packs"), dict) else {}
        if not packs or not any(isinstance(item, list) and item for item in packs.values()):
            issues.append("缺少 section_evidence_packs")
        iteration = int(state.get("analysis_iterations") or 0) + 1
        status = "retry" if issues and iteration < 2 else "approved"
        return {
            "analysis_iterations": iteration,
            "analysis_status": status,
            "analysis_issues": issues,
        }

    def analysis_router(state: FullReportAnalysisState) -> str:
        return "retry" if str(state.get("analysis_status") or "").strip() == "retry" else "end"

    graph = StateGraph(FullReportAnalysisState)
    graph.add_node("scene_router", scene_router_node)
    graph.add_node("evidence_analyst", evidence_analyst_node)
    graph.add_node("mechanism_analyst", mechanism_analyst_node)
    graph.add_node("claim_judge", claim_judge_node)
    graph.add_node("risk_mapper", risk_mapper_node)
    graph.add_node("analysis_supervisor", analysis_supervisor_node)
    graph.set_entry_point("scene_router")
    graph.add_edge("scene_router", "evidence_analyst")
    graph.add_edge("evidence_analyst", "mechanism_analyst")
    graph.add_edge("mechanism_analyst", "claim_judge")
    graph.add_edge("claim_judge", "risk_mapper")
    graph.add_edge("risk_mapper", "analysis_supervisor")
    graph.add_conditional_edges(
        "analysis_supervisor",
        analysis_router,
        {
            "retry": "evidence_analyst",
            "end": END,
        },
    )
    compiled = graph.compile()
    result = compiled.invoke(
        {
            "topic_identifier": topic_identifier,
            "topic_label": topic_label,
            "start": start,
            "end": end,
            "structured_payload": structured_payload,
            "knowledge_context": knowledge_context,
            "skill_context": skill_context,
            "style_profile": style_profile,
            "analysis_iterations": 0,
            "analysis_status": "",
            "analysis_issues": [],
            "analysis_graph_source": "analysis_graph",
            "analysis_trace": {},
            "event_callback": event_callback,
        }
    )
    return result if isinstance(result, dict) else {}


def _finalize_report_markdown(
    *,
    draft_markdown: str,
    facts: Dict[str, Any],
    brief_payload: Dict[str, Any],
    structured_payload: Dict[str, Any],
    display_name: str,
    style_profile: Dict[str, Any],
) -> Dict[str, str]:
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
        return {
            "markdown": _fallback_markdown(facts, brief_payload, style_profile),
            "revise_source": "fallback",
        }
    final_markdown = _apply_report_guardrails(final_markdown, facts)
    forbidden_hits = _find_forbidden_report_terms(final_markdown, facts)
    guardrail_violations = _find_report_guardrail_violations(final_markdown, facts)
    if forbidden_hits or guardrail_violations:
        repaired_markdown = _call_markdown_agent(
            build_full_report_revise_prompt(
                {
                    "facts": facts,
                    "brief": brief_payload,
                    "draft_markdown": final_markdown,
                    "repair_focus": {
                        "forbidden_terms": forbidden_hits,
                        "guardrail_violations": guardrail_violations,
                        "instruction": "删除内部痕迹和模板腔，严格服从 claim_matrix 与 recommendation_guardrails，不得把未验证断言写成既成事实。",
                    },
                }
            ),
            max_tokens=3400,
        )
        repaired_clean = _clean_markdown(
            repaired_markdown,
            title=structured_payload.get("title") or display_name,
        )
        if repaired_clean:
            final_markdown = _apply_report_guardrails(repaired_clean, facts)
            revise_source = "llm_repair"
    return {"markdown": final_markdown, "revise_source": revise_source}


def _run_full_report_writing_graph(
    *,
    topic_label: str,
    structured_payload: Dict[str, Any],
    skill_context: Dict[str, Any],
    style_profile: Dict[str, Any],
    scene_profile: Dict[str, Any],
    facts: Dict[str, Any],
    event_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Dict[str, Any]:
    from langgraph.graph import END, StateGraph
    ensure_langchain_uuid_compat()

    def layout_planner_node(state: FullReportWritingState) -> Dict[str, Any]:
        scene_state = state.get("scene_profile") if isinstance(state.get("scene_profile"), dict) else {}
        _emit_static_agent_activity(
            state.get("event_callback"),
            agent="layout_planner",
            phase="write",
            message="layout_planner 正在生成章节布局计划。",
            title="Layout Planner 已启动",
            scene_id=str(scene_state.get("scene_id") or "").strip(),
        )
        layout_plan, layout_source = build_full_report_layout(
            state.get("structured_payload") if isinstance(state.get("structured_payload"), dict) else {},
            topic_label=str(state.get("topic_label") or "").strip(),
            skill_context=state.get("skill_context") if isinstance(state.get("skill_context"), dict) else {},
            style_profile=state.get("style_profile") if isinstance(state.get("style_profile"), dict) else {},
            scene_profile=state.get("scene_profile") if isinstance(state.get("scene_profile"), dict) else {},
        )
        return {"layout_plan": layout_plan, "layout_source": layout_source}

    def budget_planner_node(state: FullReportWritingState) -> Dict[str, Any]:
        scene_state = state.get("scene_profile") if isinstance(state.get("scene_profile"), dict) else {}
        _emit_static_agent_activity(
            state.get("event_callback"),
            agent="budget_planner",
            phase="write",
            message="budget_planner 正在生成章节篇幅规划。",
            title="Budget Planner 已启动",
            scene_id=str(scene_state.get("scene_id") or "").strip(),
        )
        layout_plan = state.get("layout_plan") if isinstance(state.get("layout_plan"), dict) else {}
        section_budget, budget_source = build_full_report_budget(
            state.get("structured_payload") if isinstance(state.get("structured_payload"), dict) else {},
            topic_label=str(state.get("topic_label") or "").strip(),
            skill_context=state.get("skill_context") if isinstance(state.get("skill_context"), dict) else {},
            scene_profile=state.get("scene_profile") if isinstance(state.get("scene_profile"), dict) else {},
            layout_plan=layout_plan,
        )
        writing_facts = dict(state.get("facts") or {})
        writing_facts["layout_plan"] = layout_plan
        writing_facts["section_budget"] = section_budget
        brief_payload = _call_json_agent(build_full_report_brief_prompt(writing_facts), max_tokens=1800)
        brief_source = "llm" if isinstance(brief_payload, dict) else "fallback"
        if not isinstance(brief_payload, dict):
            brief_payload = _fallback_brief(
                writing_facts,
                state.get("style_profile") if isinstance(state.get("style_profile"), dict) else {},
            )
        brief_payload["sections"] = _extract_brief_sections(brief_payload)
        layout_sections = [
            {
                "id": str(item.get("id") or "").strip(),
                "title": str(item.get("title") or "").strip(),
                "goal": str(item.get("goal") or "").strip(),
                "evidence": _list_strings(item.get("evidence_focus"), max_items=4, max_chars=100),
            }
            for item in (layout_plan.get("section_plan") or [])
            if isinstance(item, dict) and str(item.get("id") or "").strip()
        ]
        extracted_sections = brief_payload.get("sections") if isinstance(brief_payload.get("sections"), list) else []
        if layout_sections and len(extracted_sections) != len(layout_sections):
            merged_sections: List[Dict[str, Any]] = []
            extracted_by_id = {
                str(item.get("id") or "").strip(): item
                for item in extracted_sections
                if isinstance(item, dict) and str(item.get("id") or "").strip()
            }
            for item in layout_sections:
                current = dict(item)
                match = extracted_by_id.get(str(item.get("id") or "").strip()) or {}
                if isinstance(match, dict):
                    current["evidence"] = _list_strings(match.get("evidence"), max_items=4, max_chars=100) or current["evidence"]
                merged_sections.append(current)
            brief_payload["sections"] = merged_sections
        return {
            "facts": writing_facts,
            "section_budget": section_budget,
            "budget_source": budget_source,
            "brief_payload": brief_payload,
            "brief_source": brief_source,
            "sections": brief_payload.get("sections") if isinstance(brief_payload.get("sections"), list) else [],
            "section_index": 0,
            "section_outputs": [],
            "section_outcomes": [],
            "section_rewrite_count": 0,
            "current_rewrite_count": 0,
            "exploration_sections": [],
            "tool_call_count_total": 0,
            "exploration_turns_total": 0,
            "section_stop_reasons": {},
        }

    def section_writer_node(state: FullReportWritingState) -> Dict[str, Any]:
        sections = state.get("sections") if isinstance(state.get("sections"), list) else []
        index = int(state.get("section_index") or 0)
        if index >= len(sections):
            return {}
        current = state.get("current_section") if isinstance(state.get("current_section"), dict) and str((state.get("current_section") or {}).get("id") or "").strip() else sections[index]
        facts_payload = state.get("facts") if isinstance(state.get("facts"), dict) else {}
        scene_state = facts_payload.get("scene_profile") if isinstance(facts_payload.get("scene_profile"), dict) else {}
        section_id = str(current.get("id") or "").strip()
        scene_id = str(scene_state.get("scene_id") or "").strip()
        result = generate_section_markdown(
            current,
            facts_payload,
            state.get("brief_payload") if isinstance(state.get("brief_payload"), dict) else {},
            state.get("section_budget") if isinstance(state.get("section_budget"), dict) else {},
        )
        exploration_trace = result.get("exploration_trace") if isinstance(result.get("exploration_trace"), dict) else {}
        writer_trace = result.get("writer_trace") if isinstance(result.get("writer_trace"), dict) else {}
        exploration_policy = result.get("exploration_policy") if isinstance(result.get("exploration_policy"), dict) else {}
        writer_policy = result.get("writer_policy") if isinstance(result.get("writer_policy"), dict) else {}
        if exploration_policy or exploration_trace:
            _emit_agent_trace_events(
                state.get("event_callback"),
                agent=f"section_exploration:{section_id}",
                phase="write",
                trace=exploration_trace,
                tools_allowed=_tool_names_from_objects(exploration_policy.get("allowed_tools") if isinstance(exploration_policy.get("allowed_tools"), list) else []),
                tool_policy_mode=str(exploration_policy.get("exploration_mode") or "off").strip(),
                scene_id=scene_id,
                section_id=section_id,
                start_message=f"{section_id} 正在展开证据探索。",
                memo_title=f"{section_id} Exploration 公开备忘录",
            )
        _emit_agent_trace_events(
            state.get("event_callback"),
            agent=f"section_writer:{section_id}",
            phase="write",
            trace=writer_trace,
            tools_allowed=_tool_names_from_objects(writer_policy.get("allowed_tools") if isinstance(writer_policy.get("allowed_tools"), list) else []),
            tool_policy_mode=str(writer_policy.get("exploration_mode") or "off").strip(),
            scene_id=scene_id,
            section_id=section_id,
            start_message=f"{section_id} 正在写作当前章节。",
            memo_title=f"{section_id} Writer 公开备忘录",
        )
        section_body = _clean_section_markdown(str(current.get("title") or "").strip(), str(result.get("markdown") or "").strip())
        current_with_runtime = dict(current)
        if isinstance(result.get("exploration_result"), dict):
            current_with_runtime["exploration_result"] = result.get("exploration_result")
        current_with_runtime["force_reexplore"] = False
        return {
            "current_section": current_with_runtime,
            "current_output": {
                "id": str(current.get("id") or "").strip(),
                "title": str(current.get("title") or "").strip(),
                "body": section_body,
                "source": str(result.get("source") or "").strip(),
                "tool_calls": result.get("tool_calls") if isinstance(result.get("tool_calls"), list) else [],
                "tool_results": result.get("tool_results") if isinstance(result.get("tool_results"), list) else [],
                "exploration_result": result.get("exploration_result") if isinstance(result.get("exploration_result"), dict) else {},
                "exploration_trace": exploration_trace,
                "writer_trace": writer_trace,
                "stop_reason": str(result.get("stop_reason") or "").strip(),
                "tool_call_count": int(result.get("tool_call_count") or 0),
                "exploration_turns": int(result.get("exploration_turns") or 0),
            },
            "writing_graph_source": "writing_graph",
        }

    def style_critic_node(state: FullReportWritingState) -> Dict[str, Any]:
        current_output = state.get("current_output") if isinstance(state.get("current_output"), dict) else {}
        section = state.get("current_section") if isinstance(state.get("current_section"), dict) else {}
        prior_outputs = state.get("section_outputs") if isinstance(state.get("section_outputs"), list) else []
        facts = state.get("facts") if isinstance(state.get("facts"), dict) else {}
        scene_state = facts.get("scene_profile") if isinstance(facts.get("scene_profile"), dict) else {}
        _emit_static_agent_activity(
            state.get("event_callback"),
            agent=f"style_critic:{str(section.get('id') or '').strip()}",
            phase="review",
            message="style_critic 正在检查模板腔和节间同质化。",
            title="Style Critic 已启动",
            section_id=str(section.get("id") or "").strip(),
            scene_id=str(scene_state.get("scene_id") or "").strip(),
        )
        section_body = str(current_output.get("body") or "").strip()
        if _should_use_llm_critics(section, current_output, facts):
            review = _call_style_critic(
                section=section,
                section_body=section_body,
                prior_outputs=prior_outputs,
                facts=facts,
            )
        else:
            review = _fallback_style_review(section_body, prior_outputs)
        return {"style_review": review}

    def fact_critic_node(state: FullReportWritingState) -> Dict[str, Any]:
        current_output = state.get("current_output") if isinstance(state.get("current_output"), dict) else {}
        section = state.get("current_section") if isinstance(state.get("current_section"), dict) else {}
        facts = state.get("facts") if isinstance(state.get("facts"), dict) else {}
        scene_state = facts.get("scene_profile") if isinstance(facts.get("scene_profile"), dict) else {}
        _emit_static_agent_activity(
            state.get("event_callback"),
            agent=f"fact_critic:{str(section.get('id') or '').strip()}",
            phase="review",
            message="fact_critic 正在检查断言强度和 claim gate 边界。",
            title="Fact Critic 已启动",
            section_id=str(section.get("id") or "").strip(),
            scene_id=str(scene_state.get("scene_id") or "").strip(),
        )
        section_body = str(current_output.get("body") or "").strip()
        if _should_use_llm_critics(section, current_output, facts):
            review = _call_fact_critic(
                section=section,
                section_body=section_body,
                facts=facts,
            )
        else:
            review = _fallback_fact_review(section_body, facts)
        return {"fact_review": review}

    def rewrite_prepare_node(state: FullReportWritingState) -> Dict[str, Any]:
        current = dict(state.get("current_section") or {})
        style_review = state.get("style_review") if isinstance(state.get("style_review"), dict) else {}
        fact_review = state.get("fact_review") if isinstance(state.get("fact_review"), dict) else {}
        instructions = [
            str(item.get("rewrite_instruction") or "").strip()
            for item in (style_review, fact_review)
            if str(item.get("rewrite_instruction") or "").strip()
        ]
        current["rewrite_instruction"] = "；".join(instructions[:2])
        evidence_issue = any("证据" in str(item).strip() for item in (fact_review.get("issues") or []))
        current["force_reexplore"] = bool(evidence_issue)
        return {
            "current_section": current,
            "current_rewrite_count": int(state.get("current_rewrite_count") or 0) + 1,
            "section_rewrite_count": int(state.get("section_rewrite_count") or 0) + 1,
        }

    def section_accept_node(state: FullReportWritingState) -> Dict[str, Any]:
        section_outputs = list(state.get("section_outputs") or [])
        current_output = state.get("current_output") if isinstance(state.get("current_output"), dict) else {}
        if current_output:
            current_output = dict(current_output)
            current_output["body"] = _apply_report_guardrails(
                _soften_template_phrases(str(current_output.get("body") or "").strip()),
                state.get("facts") if isinstance(state.get("facts"), dict) else {},
            )
            current_output["order"] = int(state.get("section_index") or 0)
            section_outputs.append(current_output)
        section_outcomes = list(state.get("section_outcomes") or [])
        exploration_sections = list(state.get("exploration_sections") or [])
        tool_call_count_total = int(state.get("tool_call_count_total") or 0)
        exploration_turns_total = int(state.get("exploration_turns_total") or 0)
        section_stop_reasons = dict(state.get("section_stop_reasons") or {})
        if int(current_output.get("tool_call_count") or 0) > 0:
            exploration_sections.append(str(current_output.get("id") or "").strip())
        tool_call_count_total += int(current_output.get("tool_call_count") or 0)
        exploration_turns_total += int(current_output.get("exploration_turns") or 0)
        section_stop_reasons[str(current_output.get("id") or "").strip()] = str(current_output.get("stop_reason") or "").strip()
        section_outcomes.append(
            {
                "id": str(current_output.get("id") or "").strip(),
                "title": str(current_output.get("title") or "").strip(),
                "rewrite_count": int(state.get("current_rewrite_count") or 0),
                "style_pass": bool((state.get("style_review") or {}).get("pass", True)),
                "fact_pass": bool((state.get("fact_review") or {}).get("pass", True)),
                "source": str(current_output.get("source") or "").strip(),
                "tool_call_count": int(current_output.get("tool_call_count") or 0),
                "exploration_turns": int(current_output.get("exploration_turns") or 0),
                "stop_reason": str(current_output.get("stop_reason") or "").strip(),
            }
        )
        return {
            "section_outputs": section_outputs,
            "section_outcomes": section_outcomes,
            "exploration_sections": exploration_sections,
            "tool_call_count_total": tool_call_count_total,
            "exploration_turns_total": exploration_turns_total,
            "section_stop_reasons": section_stop_reasons,
            "section_index": int(state.get("section_index") or 0) + 1,
            "current_section": {},
            "current_output": {},
            "current_rewrite_count": 0,
            "style_review": {},
            "fact_review": {},
        }

    def report_editor_node(state: FullReportWritingState) -> Dict[str, Any]:
        scene_state = state.get("scene_profile") if isinstance(state.get("scene_profile"), dict) else {}
        _emit_static_agent_activity(
            state.get("event_callback"),
            agent="report_editor",
            phase="review",
            message="report_editor 正在拼装全文并插入关键图示。",
            title="Report Editor 已启动",
            scene_id=str(scene_state.get("scene_id") or "").strip(),
        )
        section_outputs = state.get("section_outputs") if isinstance(state.get("section_outputs"), list) else []
        assembled_body = _compose_section_markdown(section_outputs)
        title_payload = _call_json_agent(
            build_title_subtitle_prompt(
                str(state.get("topic_label") or "").strip(),
                {
                    "facts": state.get("facts") if isinstance(state.get("facts"), dict) else {},
                    "sections": state.get("sections") if isinstance(state.get("sections"), list) else [],
                },
            ),
            max_tokens=600,
        )
        title_text = str(
            (title_payload or {}).get("title")
            or (state.get("structured_payload") or {}).get("title")
            or state.get("topic_label")
            or ""
        ).strip()
        subtitle_text = str((title_payload or {}).get("subtitle") or "").strip()
        subtitle_text = _apply_report_guardrails(_soften_template_phrases(subtitle_text), state.get("facts") if isinstance(state.get("facts"), dict) else {})
        draft_markdown = f"# {title_text}\n\n{subtitle_text}\n\n{assembled_body}".strip() if assembled_body else ""
        if not draft_markdown.strip():
            draft_markdown = _fallback_markdown(
                state.get("facts") if isinstance(state.get("facts"), dict) else {},
                state.get("brief_payload") if isinstance(state.get("brief_payload"), dict) else {},
                state.get("style_profile") if isinstance(state.get("style_profile"), dict) else {},
            )
        finalized = _finalize_report_markdown(
            draft_markdown=draft_markdown,
            facts=state.get("facts") if isinstance(state.get("facts"), dict) else {},
            brief_payload=state.get("brief_payload") if isinstance(state.get("brief_payload"), dict) else {},
            structured_payload=state.get("structured_payload") if isinstance(state.get("structured_payload"), dict) else {},
            display_name=str(state.get("topic_label") or "").strip(),
            style_profile=state.get("style_profile") if isinstance(state.get("style_profile"), dict) else {},
        )
        return {
            "final_markdown": str(finalized.get("markdown") or "").strip(),
            "revise_source": str(finalized.get("revise_source") or "").strip(),
        }

    def after_fact_router(state: FullReportWritingState) -> str:
        style_pass = bool((state.get("style_review") or {}).get("pass", True))
        fact_pass = bool((state.get("fact_review") or {}).get("pass", True))
        current_output = state.get("current_output") if isinstance(state.get("current_output"), dict) else {}
        if str(current_output.get("source") or "").strip() != "langchain_agent":
            return "accept"
        rewrite_limit = 1
        if (not style_pass or not fact_pass) and int(state.get("current_rewrite_count") or 0) < rewrite_limit:
            return "rewrite"
        return "accept"

    def after_accept_router(state: FullReportWritingState) -> str:
        sections = state.get("sections") if isinstance(state.get("sections"), list) else []
        return "next" if int(state.get("section_index") or 0) < len(sections) else "finish"

    graph = StateGraph(FullReportWritingState)
    graph.add_node("layout_planner", layout_planner_node)
    graph.add_node("budget_planner", budget_planner_node)
    graph.add_node("section_writer", section_writer_node)
    graph.add_node("style_critic", style_critic_node)
    graph.add_node("fact_critic", fact_critic_node)
    graph.add_node("rewrite_prepare", rewrite_prepare_node)
    graph.add_node("section_accept", section_accept_node)
    graph.add_node("report_editor", report_editor_node)
    graph.set_entry_point("layout_planner")
    graph.add_edge("layout_planner", "budget_planner")
    graph.add_edge("budget_planner", "section_writer")
    graph.add_edge("section_writer", "style_critic")
    graph.add_edge("style_critic", "fact_critic")
    graph.add_conditional_edges(
        "fact_critic",
        after_fact_router,
        {
            "rewrite": "rewrite_prepare",
            "accept": "section_accept",
        },
    )
    graph.add_edge("rewrite_prepare", "section_writer")
    graph.add_conditional_edges(
        "section_accept",
        after_accept_router,
        {
            "next": "section_writer",
            "finish": "report_editor",
        },
    )
    graph.add_edge("report_editor", END)
    compiled = graph.compile()
    result = compiled.invoke(
        {
            "topic_label": topic_label,
            "structured_payload": structured_payload,
            "skill_context": skill_context,
            "style_profile": style_profile,
            "scene_profile": scene_profile,
            "facts": facts,
            "event_callback": event_callback,
            "writing_graph_source": "writing_graph",
        }
    )
    return result if isinstance(result, dict) else {}


def _build_compact_report_facts(
    structured_payload: Dict[str, Any],
    *,
    topic_identifier: str,
    topic_label: str,
    start: str,
    end: str,
    knowledge_context: Dict[str, Any],
    skill_context: Dict[str, Any],
    style_profile: Dict[str, Any],
    scene_profile: Dict[str, Any],
    layout_plan: Dict[str, Any],
    section_budget: Dict[str, Any],
) -> Dict[str, Any]:
    metrics = structured_payload.get("metrics") if isinstance(structured_payload.get("metrics"), dict) else {}
    deep_analysis = structured_payload.get("deepAnalysis") if isinstance(structured_payload.get("deepAnalysis"), dict) else {}
    conclusion_mining = structured_payload.get("conclusionMining") if isinstance(structured_payload.get("conclusionMining"), dict) else {}
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

    analysis_briefs = _build_analysis_briefs(module_narratives)
    time_framework = _build_time_framework(stage_notes, bertopic_temporal, metrics)
    indicator_relationships = _build_indicator_relationships(
        structured_payload.get("metrics") if isinstance(structured_payload.get("metrics"), dict) else {},
        structured_payload.get("channels") if isinstance(structured_payload.get("channels"), list) else [],
        structured_payload.get("sentiment") if isinstance(structured_payload.get("sentiment"), dict) else {},
        structured_payload.get("themes") if isinstance(structured_payload.get("themes"), list) else [],
    )
    evidence_semantics = _build_evidence_semantics(
        structured_payload.get("metrics") if isinstance(structured_payload.get("metrics"), dict) else {},
        structured_payload.get("channels") if isinstance(structured_payload.get("channels"), list) else [],
        structured_payload.get("sentiment") if isinstance(structured_payload.get("sentiment"), dict) else {},
        structured_payload.get("themes") if isinstance(structured_payload.get("themes"), list) else [],
    )
    claim_verifications = _build_claim_verifications(
        topic_identifier=topic_identifier,
        start=start,
        end=end,
        metrics=structured_payload.get("metrics") if isinstance(structured_payload.get("metrics"), dict) else {},
        conclusion_mining=conclusion_mining,
    )
    subject_scope = _build_subject_scope(
        topic_identifier=topic_identifier,
        start=start,
        end=end,
    )
    recommendation_guardrails = _build_recommendation_guardrails(claim_verifications)
    risk_action_map = _build_risk_action_map(deep_analysis, recommendation_guardrails)

    return {
        "topic_identifier": topic_identifier,
        "topic_label": topic_label,
        "time_range": {"start": start, "end": end},
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
        "analysis_briefs": analysis_briefs[:7],
        "bertopic": {
            "insight": _truncate_text(structured_payload.get("bertopicInsight") or "", 900),
            "temporal_summary": str(bertopic_temporal.get("summary") or "").strip(),
            "shift_signals": _list_strings(bertopic_temporal.get("shiftSignals"), max_items=4, max_chars=90),
            "watchpoints": _list_strings(bertopic_temporal.get("watchpoints"), max_items=3, max_chars=90),
        },
        "evidence_semantics": evidence_semantics[:6],
        "subject_scope": subject_scope,
        "indicator_relationships": indicator_relationships[:6],
        "time_framework": time_framework,
        "risk_action_map": risk_action_map[:8],
        "claim_verifications": claim_verifications[:6],
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
        "recommendation_guardrails": recommendation_guardrails,
        "knowledge_context": {
            "summary": _truncate_text(knowledge_context.get("summary") or "", 3200),
            "theory_hints": _list_strings(knowledge_context.get("theoryHints"), max_items=6, max_chars=32),
            "dynamic_theories": _list_strings(knowledge_context.get("dynamicTheories"), max_items=6, max_chars=32),
            "reference_snippets": reference_snippets[:4],
            "expert_notes": expert_notes[:4],
        },
        "skill_context": _compact_skill_context(skill_context),
        "style_profile": style_profile,
        "scene_profile": scene_profile,
        "layout_plan": layout_plan,
        "section_budget": section_budget,
        "legacy_context": {
            "sections_count": int(legacy_context.get("sectionsCount") or 0),
            "full_text_excerpt": _truncate_text(legacy_context.get("fullText") or "", 1800),
            "manual_text_excerpt": _truncate_text(legacy_context.get("manualText") or "", 1200),
        },
    }


def _fallback_brief(facts: Dict[str, Any], style_profile: Dict[str, Any]) -> Dict[str, Any]:
    theories = facts.get("knowledge_context", {}).get("dynamic_theories") or facts.get("knowledge_context", {}).get("theory_hints") or []
    preferred_terms = [str(item).strip() for item in theories if str(item or "").strip()][:6]
    raw_sections = []
    layout_plan = facts.get("layout_plan") if isinstance(facts.get("layout_plan"), dict) else {}
    if isinstance(layout_plan.get("section_plan"), list) and layout_plan.get("section_plan"):
        raw_sections = layout_plan.get("section_plan") or []
    elif isinstance(style_profile.get("fallback_sections"), list):
        raw_sections = style_profile.get("fallback_sections") or []
    sections = []
    for item in raw_sections:
        if not isinstance(item, dict):
            continue
        section_id = str(item.get("id") or "").strip()
        title = str(item.get("title") or "").strip()
        goal = str(item.get("goal") or "").strip()
        if not (section_id and title):
            continue
        evidence = _list_strings(item.get("evidence_focus"), max_items=4, max_chars=90)
        if section_id == "summary":
            evidence = evidence or (facts.get("highlight_points") or [])
        elif section_id in {"analysis", "trend", "structure"}:
            evidence = evidence or (
                facts.get("deep_analysis", {}).get("key_events")
                or [item.get("label") for item in facts.get("module_narratives") or [] if isinstance(item, dict)]
            )
        elif section_id in {"risk", "review", "response"}:
            evidence = evidence or (facts.get("deep_analysis", {}).get("key_risks") or [
                item.get("risk")
                for item in (facts.get("risk_action_map") or [])
                if isinstance(item, dict)
            ])
        elif section_id in {"action", "recommendation"}:
            evidence = evidence or [
                item.get("action_condition")
                for item in (facts.get("risk_action_map") or [])
                if isinstance(item, dict)
            ]
        elif section_id in {"timeline", "evolution"}:
            evidence = evidence or (facts.get("deep_analysis", {}).get("key_events") or [])
        elif section_id in {"propagation", "channels"}:
            evidence = evidence or [
                item.get("signal")
                for item in (facts.get("indicator_relationships") or [])
                if isinstance(item, dict)
            ]
        elif section_id in {"focus", "topics", "response", "attitude"}:
            evidence = evidence or [
                item.get("judgement")
                for item in (facts.get("evidence_semantics") or [])
                if isinstance(item, dict)
            ]
        elif section_id in {"mechanism", "impact", "benchmark", "evidence_matrix", "sample_pack", "boundary"}:
            evidence = evidence or [
                item.get("report_meaning") or item.get("boundary")
                for item in (facts.get("indicator_relationships") or []) + (facts.get("evidence_semantics") or [])
                if isinstance(item, dict)
            ]
        else:
            evidence = evidence or (facts.get("highlight_points") or [])
        sections.append({"id": section_id, "title": title, "goal": goal, "evidence": evidence[:4]})
    if not sections:
        sections = [{"id": "summary", "title": "摘要", "goal": "概括核心判断与主要边界。", "evidence": facts.get("highlight_points") or []}]
    return {
        "core_thesis": str(facts.get("deep_analysis", {}).get("narrative_summary") or facts.get("subtitle") or "").strip(),
        "tone_notes": _list_strings(style_profile.get("fallback_tone_notes"), max_items=6, max_chars=120),
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


def _clean_section_markdown(title: str, markdown: str) -> str:
    text = _strip_code_fences(markdown)
    heading = str(title or "").strip()
    if heading:
        pattern = rf"^\s*##?\s*{re.escape(heading)}\s*\n+"
        text = re.sub(pattern, "", text, count=1, flags=re.I)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _soften_template_phrases(text: str) -> str:
    value = str(text or "")
    replacements = {
        "更值得注意的是": "同时，",
        "值得注意的是": "同时，",
        "并非偶然": "有其结构原因",
        "并非自然演进": "并非单线演进",
        "这并非": "这背后存在",
        "该现象并非": "该现象背后存在",
    }
    for source, target in replacements.items():
        value = value.replace(source, target)
    value = re.sub(r"[，,]{2,}", "，", value)
    value = re.sub(r"同时，[，,]", "同时，", value)
    return value


def _find_forbidden_report_terms(markdown: str, facts: Dict[str, Any]) -> List[str]:
    text = str(markdown or "")
    if not text:
        return []
    hits: List[str] = []
    for token in sorted(_collect_internal_identifiers(facts)):
        if re.search(rf"(?<![A-Za-z0-9_]){re.escape(token)}(?![A-Za-z0-9_])", text):
            hits.append(token)
    generic_language_leaks = [
        (r"(该|这类)?数据来自[^。；\n]{0,30}", "technical_source_note"),
        (r"(依据|根据)[^。；\n]{0,24}(字段|模块|键名)", "technical_field_reference"),
        (r"(系统|内部)[^。；\n]{0,16}(字段|模块|键名|变量)", "internal_pipeline_reference"),
    ]
    for pattern, label in generic_language_leaks:
        if re.search(pattern, text):
            hits.append(label)
    return hits


def _find_report_guardrail_violations(markdown: str, facts: Dict[str, Any]) -> List[str]:
    text = str(markdown or "")
    guardrails = facts.get("recommendation_guardrails") if isinstance(facts.get("recommendation_guardrails"), dict) else {}
    action_guardrails = guardrails.get("action_guardrails") or []
    claim_guardrails = guardrails.get("claim_guardrails") or []
    if not text:
        return []

    violations: List[str] = []
    if action_guardrails:
        immediate_block = re.search(r"可立即启动[^#]{0,800}", text, flags=re.S)
        if immediate_block:
            immediate_text = immediate_block.group(0)
            for guardrail in action_guardrails:
                keywords = [str(item).strip() for item in (guardrail.get("keywords") or []) if str(item or "").strip()]
                if any(keyword in immediate_text for keyword in keywords):
                    violations.append("需补充前提验证的动作被写成可立即启动动作")
                    break
    for guardrail in claim_guardrails:
        mode = str(guardrail.get("mode") or "").strip()
        if mode == "causal_uncertain":
            if re.search(r"(因|由于)[^。；\n]{0,40}(政策|规定|文件|通报)[^。；\n]{0,20}(发布|出台)[^。；\n]{0,20}(触发|引发|导致|引爆)", text):
                violations.append("未验证的触发因果被写成既成事实")
            if re.search(r"政策引爆于\d{1,2}月\d{1,2}日", text):
                violations.append("未验证的政策引爆判断被写成既成事实")
            if re.search(r"(政策|新规|规定)[^。；\n]{0,12}(引爆点|引爆节点)", text):
                violations.append("未验证的政策引爆判断被写成既成事实")
        elif mode == "attribution_uncertain":
            if re.search(r"(主动策划|算法助推|平台助推|平台放大)", text):
                violations.append("未验证的传播归因被写成既成事实")
    if re.search(r"政策引爆于\d{1,2}月\d{1,2}日", text):
        violations.append("未验证的政策引爆判断被写成既成事实")
    if re.search(r"(政策|新规|规定)[^。；\n]{0,12}(引爆点|引爆节点)", text):
        violations.append("未验证的政策引爆判断被写成既成事实")
    return violations


def _apply_report_guardrails(markdown: str, facts: Dict[str, Any]) -> str:
    text = str(markdown or "")
    if not text:
        return ""

    guardrails = facts.get("recommendation_guardrails") if isinstance(facts.get("recommendation_guardrails"), dict) else {}
    action_guardrails = guardrails.get("action_guardrails") or []
    claim_guardrails = guardrails.get("claim_guardrails") or []

    if action_guardrails:
        def _rewrite_short_video_line(match: re.Match[str]) -> str:
            line = str(match.group(0) or "").strip()
            if line.startswith("- 启动前需补充核验"):
                return line
            normalized = re.sub(r"^-+\s*", "", line)
            normalized = re.sub(r"^(立即启动动作包括|可立即启动动作包括|立即启动|可立即启动)[:：]?\s*", "", normalized)
            normalized = normalized.strip()
            normalized = normalized.rstrip("。；; ")
            normalized += "；相关前提仍待补充核验。"
            return f"- 启动前需补充核验：{normalized}"

        lines = text.splitlines()
        rewritten_lines: List[str] = []
        for line in lines:
            new_line = line
            for guardrail in action_guardrails:
                keywords = [str(item).strip() for item in (guardrail.get("keywords") or []) if str(item or "").strip()]
                if line.lstrip().startswith("-") and any(keyword in line for keyword in keywords):
                    new_line = _rewrite_short_video_line(re.match(r".*", line))
                    break
            rewritten_lines.append(new_line)
        text = "\n".join(rewritten_lines)

    for guardrail in claim_guardrails:
        mode = str(guardrail.get("mode") or "").strip()
        if mode == "causal_uncertain":
            text = re.sub(
                r"(因|由于)[^。；\n]{0,40}(政策|规定|文件|通报)[^。；\n]{0,20}(发布|出台)[^。；\n]{0,20}(触发|引发|导致|引爆)",
                "与相关议题升温同步，形成传播峰值",
                text,
            )
            text = re.sub(
                r"政策引爆于(\d{1,2}月\d{1,2}日)",
                r"\1形成传播峰值，并与政策议题升温同步",
                text,
            )
            text = re.sub(
                r"(政策|新规|规定)[^。；\n]{0,12}(引爆点|引爆节点)",
                "相关议题升温的关键时间锚点",
                text,
            )
        elif mode == "attribution_uncertain":
            text = re.sub(
                r"是否确由[^。；\n]{0,50}(主动策划|算法助推|平台助推|平台放大)",
                "相关传播动因仍待核验",
                text,
            )
            text = re.sub(
                r"(由|系|属于)[^。；\n]{0,20}(主动策划|算法助推|平台助推|平台放大)",
                "其传播动因仍待核验",
                text,
            )

    text = re.sub(
        r"政策引爆于(\d{1,2}月\d{1,2}日)",
        r"\1形成传播峰值，并与政策议题升温同步",
        text,
    )
    text = re.sub(
        r"(政策|新规|规定)[^。；\n]{0,12}(引爆点|引爆节点)",
        "相关议题升温的关键时间锚点",
        text,
    )
    return _soften_template_phrases(text)


def _fallback_markdown(facts: Dict[str, Any], brief: Dict[str, Any], style_profile: Dict[str, Any]) -> str:
    title = str(facts.get("title") or f"{facts.get('topic_label') or facts.get('topic_identifier') or '专题'}完整报告").strip()
    subtitle = str(facts.get("subtitle") or "").strip()
    deep_analysis = facts.get("deep_analysis") or {}
    evidence_semantics = facts.get("evidence_semantics") if isinstance(facts.get("evidence_semantics"), list) else []
    risk_action_map = facts.get("risk_action_map") if isinstance(facts.get("risk_action_map"), list) else []
    time_framework = facts.get("time_framework") if isinstance(facts.get("time_framework"), dict) else {}

    lines = [f"# {title}"]
    if subtitle:
        lines.extend(["", subtitle])
    sections = brief.get("sections") if isinstance(brief.get("sections"), list) else []
    if not sections:
        sections = style_profile.get("fallback_sections") if isinstance(style_profile.get("fallback_sections"), list) else []

    for item in sections:
        if not isinstance(item, dict):
            continue
        section_id = str(item.get("id") or "").strip()
        section_title = str(item.get("title") or "").strip() or "正文"
        lines.extend(["", f"## {section_title}"])
        if section_id == "summary":
            lines.append(str(brief.get("core_thesis") or deep_analysis.get("narrative_summary") or "当前仅完成最小可用文本汇总。").strip())
            for item in evidence_semantics[:2]:
                if isinstance(item, dict):
                    lines.append(
                        f"- {str(item.get('judgement') or '').strip()}：{str(item.get('evidence') or '').strip()}。"
                    )
            continue
        if section_id in {"analysis", "trend", "structure", "timeline", "evolution"}:
            narrative = str(deep_analysis.get("narrative_summary") or "").strip()
            if narrative:
                lines.append(narrative)
            narrative_stages = time_framework.get("narrative_stages") if isinstance(time_framework.get("narrative_stages"), list) else []
            if narrative_stages:
                for stage in narrative_stages[:3]:
                    if isinstance(stage, dict):
                        lines.append(
                            f"- {str(stage.get('stage') or '').strip()}（{str(stage.get('range') or '').strip()}）：{str(stage.get('meaning') or '').strip()}"
                        )
            evidence = item.get("evidence") if isinstance(item.get("evidence"), list) else []
            if evidence:
                lines.extend([f"- {entry}" for entry in evidence[:4] if str(entry or "").strip()])
            else:
                for semantic in evidence_semantics[:4]:
                    if isinstance(semantic, dict):
                        lines.append(
                            f"- {semantic.get('judgement')}: {semantic.get('source_note')} {semantic.get('boundary')}"
                        )
            continue
        if section_id in {"propagation", "channels"}:
            relations = facts.get("indicator_relationships") if isinstance(facts.get("indicator_relationships"), list) else []
            if relations:
                for relation in relations[:4]:
                    if isinstance(relation, dict):
                        lines.append(
                            f"- {str(relation.get('signal') or '').strip()}：{str(relation.get('mechanism') or '').strip()}"
                        )
            else:
                evidence = item.get("evidence") if isinstance(item.get("evidence"), list) else []
                lines.extend([f"- {entry}" for entry in evidence[:4] if str(entry or "").strip()])
            continue
        if section_id in {"focus", "topics", "attitude", "response", "mechanism", "impact", "benchmark"}:
            evidence = item.get("evidence") if isinstance(item.get("evidence"), list) else []
            if evidence:
                lines.extend([f"- {entry}" for entry in evidence[:4] if str(entry or "").strip()])
            else:
                for semantic in evidence_semantics[:4]:
                    if isinstance(semantic, dict):
                        lines.append(
                            f"- {str(semantic.get('judgement') or '').strip()}：{str(semantic.get('source_note') or '').strip()}"
                        )
            continue
        if section_id in {"risk", "review", "boundary"}:
            key_risks = deep_analysis.get("key_risks") or []
            if key_risks:
                lines.extend([f"- {entry}" for entry in key_risks[:5]])
            for mapping in risk_action_map[:4]:
                if isinstance(mapping, dict):
                    lines.append(
                        f"- 风险桥接：{str(mapping.get('risk') or '').strip()}；{str(mapping.get('mechanism_bridge') or '').strip()}"
                    )
            continue
        if section_id in {"action", "recommendation"}:
            for mapping in risk_action_map[:4]:
                if isinstance(mapping, dict):
                    lines.append(
                        f"- {str(mapping.get('risk') or '').strip()}：{str(mapping.get('action_condition') or '').strip()}"
                    )
            evidence = item.get("evidence") if isinstance(item.get("evidence"), list) else []
            if evidence:
                lines.extend([f"- {entry}" for entry in evidence[:4] if str(entry or "").strip()])
            continue
        if section_id in {"evidence_matrix", "sample_pack"}:
            claim_verifications = facts.get("claim_verifications") if isinstance(facts.get("claim_verifications"), list) else []
            if claim_verifications:
                for verification in claim_verifications[:4]:
                    if isinstance(verification, dict):
                        lines.append(
                            f"- {str(verification.get('claim') or '').strip()}：{str(verification.get('verification_status') or '').strip()}"
                        )
            else:
                evidence = item.get("evidence") if isinstance(item.get("evidence"), list) else []
                lines.extend([f"- {entry}" for entry in evidence[:4] if str(entry or "").strip()])
            continue
        evidence = item.get("evidence") if isinstance(item.get("evidence"), list) else []
        if evidence:
            lines.extend([f"- {entry}" for entry in evidence[:4] if str(entry or "").strip()])
        else:
            lines.append(str(brief.get("core_thesis") or deep_analysis.get("narrative_summary") or "当前仅保留最小可用说明。").strip())

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


def _get_asset_meta(style_profile: Dict[str, Any], key: str, default_title: str, default_description: str) -> Dict[str, str]:
    asset_labels = style_profile.get("asset_labels") if isinstance(style_profile.get("asset_labels"), dict) else {}
    raw = asset_labels.get(key) if isinstance(asset_labels.get(key), dict) else {}
    return {
        "title": str(raw.get("title") or default_title).strip(),
        "description": str(raw.get("description") or default_description).strip(),
    }


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


def _build_cover_asset(structured_payload: Dict[str, Any], style_profile: Dict[str, Any]) -> Optional[Dict[str, Any]]:
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

    asset_labels = style_profile.get("asset_labels") if isinstance(style_profile.get("asset_labels"), dict) else {}
    cover_meta = _get_asset_meta(style_profile, "cover", "封面摘要图", "自动摘要卡片")
    cover_metrics = asset_labels.get("cover_metrics") if isinstance(asset_labels.get("cover_metrics"), dict) else {}
    cover_badge = str((asset_labels.get("cover") or {}).get("badge") if isinstance(asset_labels.get("cover"), dict) else "").strip() or "完整稿"

    body = (
        "<rect x='76' y='82' width='1048' height='180' rx='28' fill='#0f172a'/>"
        f"<text x='112' y='148' fill='#e0f2fe' font-size='22' font-family='Segoe UI, Microsoft YaHei, sans-serif'>{_escape_xml(cover_badge)}</text>"
        f"<text x='112' y='204' fill='#ffffff' font-size='42' font-weight='700' font-family='Segoe UI, Microsoft YaHei, sans-serif'>{_escape_xml(_truncate_text(title, 28))}</text>"
        f"<text x='112' y='244' fill='#cbd5e1' font-size='20' font-family='Segoe UI, Microsoft YaHei, sans-serif'>{_escape_xml(subtitle)}</text>"
        "<rect x='76' y='298' width='324' height='128' rx='24' fill='#eff6ff' stroke='#bfdbfe'/>"
        "<rect x='438' y='298' width='324' height='128' rx='24' fill='#f0fdf4' stroke='#bbf7d0'/>"
        "<rect x='800' y='298' width='324' height='128' rx='24' fill='#fff7ed' stroke='#fed7aa'/>"
        f"<text x='108' y='336' fill='#64748b' font-size='18' font-family='Segoe UI, Microsoft YaHei, sans-serif'>{_escape_xml(str(cover_metrics.get('range') or '时间区间'))}</text>"
        f"<text x='108' y='388' fill='#0f172a' font-size='28' font-weight='700' font-family='Segoe UI, Microsoft YaHei, sans-serif'>{_escape_xml(range_text)}</text>"
        f"<text x='470' y='336' fill='#64748b' font-size='18' font-family='Segoe UI, Microsoft YaHei, sans-serif'>{_escape_xml(str(cover_metrics.get('volume') or '总声量'))}</text>"
        f"<text x='470' y='388' fill='#0f172a' font-size='28' font-weight='700' font-family='Segoe UI, Microsoft YaHei, sans-serif'>{total_volume:,}</text>"
        f"<text x='832' y='336' fill='#64748b' font-size='18' font-family='Segoe UI, Microsoft YaHei, sans-serif'>{_escape_xml(str(cover_metrics.get('peak') or '峰值节点'))}</text>"
        f"<text x='832' y='388' fill='#0f172a' font-size='24' font-weight='700' font-family='Segoe UI, Microsoft YaHei, sans-serif'>{_escape_xml(_truncate_text(peak_text, 26))}</text>"
        "<rect x='76' y='466' width='498' height='114' rx='24' fill='#f8fafc' stroke='#e2e8f0'/>"
        "<rect x='626' y='466' width='498' height='114' rx='24' fill='#f8fafc' stroke='#e2e8f0'/>"
        f"<text x='108' y='504' fill='#64748b' font-size='18' font-family='Segoe UI, Microsoft YaHei, sans-serif'>{_escape_xml(str(cover_metrics.get('stage') or '当前阶段'))}</text>"
        f"<text x='108' y='552' fill='#0f172a' font-size='30' font-weight='700' font-family='Segoe UI, Microsoft YaHei, sans-serif'>{_escape_xml(stage)}</text>"
        f"<text x='658' y='504' fill='#64748b' font-size='18' font-family='Segoe UI, Microsoft YaHei, sans-serif'>{_escape_xml(str(cover_metrics.get('event_type') or '事件类型'))}</text>"
        f"<text x='658' y='552' fill='#0f172a' font-size='30' font-weight='700' font-family='Segoe UI, Microsoft YaHei, sans-serif'>{_escape_xml(event_type)}</text>"
    )
    return {
        "key": "cover",
        "title": cover_meta["title"],
        "description": cover_meta["description"],
        "dataUrl": _svg_data_url(_wrap_svg(cover_meta["title"], body)),
    }


def _build_timeline_asset(structured_payload: Dict[str, Any], style_profile: Dict[str, Any]) -> Optional[Dict[str, Any]]:
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
    meta = _get_asset_meta(style_profile, "timeline", "时间趋势图", "时间线走势")
    body = [
        f"<text x='120' y='110' fill='#0f172a' font-size='30' font-weight='700' font-family='Segoe UI, Microsoft YaHei, sans-serif'>{_escape_xml(meta['title'])}</text>",
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
        "title": meta["title"],
        "description": meta["description"],
        "dataUrl": _svg_data_url(_wrap_svg(meta["title"], "".join(body))),
    }


def _build_sentiment_asset(structured_payload: Dict[str, Any], style_profile: Dict[str, Any]) -> Optional[Dict[str, Any]]:
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
    meta = _get_asset_meta(style_profile, "sentiment", "情绪结构图", "情绪占比")
    rects: List[str] = [
        f"<text x='120' y='110' fill='#0f172a' font-size='30' font-weight='700' font-family='Segoe UI, Microsoft YaHei, sans-serif'>{_escape_xml(meta['title'])}</text>",
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
        "title": meta["title"],
        "description": meta["description"],
        "dataUrl": _svg_data_url(_wrap_svg(meta["title"], "".join(rects))),
    }


def _build_channels_asset(structured_payload: Dict[str, Any], style_profile: Dict[str, Any]) -> Optional[Dict[str, Any]]:
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
    meta = _get_asset_meta(style_profile, "channels", "渠道分布图", "头部渠道横向对比")
    body: List[str] = [
        f"<text x='120' y='110' fill='#0f172a' font-size='30' font-weight='700' font-family='Segoe UI, Microsoft YaHei, sans-serif'>{_escape_xml(meta['title'])}</text>",
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
        "title": meta["title"],
        "description": meta["description"],
        "dataUrl": _svg_data_url(_wrap_svg(meta["title"], "".join(body))),
    }


def _build_theme_asset(structured_payload: Dict[str, Any], style_profile: Dict[str, Any]) -> Optional[Dict[str, Any]]:
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

    meta = _get_asset_meta(style_profile, "themes", "核心议题图", "主题标签插图")
    body: List[str] = [
        f"<text x='120' y='110' fill='#0f172a' font-size='30' font-weight='700' font-family='Segoe UI, Microsoft YaHei, sans-serif'>{_escape_xml(meta['title'])}</text>",
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
        "title": meta["title"],
        "description": meta["description"],
        "dataUrl": _svg_data_url(_wrap_svg(meta["title"], "".join(body))),
    }


def _build_visual_assets(structured_payload: Dict[str, Any], style_profile: Dict[str, Any]) -> List[Dict[str, Any]]:
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
            asset = builder(structured_payload, style_profile)
        except Exception:
            asset = None
        if isinstance(asset, dict) and str(asset.get("key") or "").strip():
            assets.append(asset)
    return assets


def _inject_visual_assets(markdown: str, assets: List[Dict[str, Any]], style_profile: Dict[str, Any]) -> str:
    text = str(markdown or "").strip()
    if not text or not assets:
        return text

    asset_keys = {str(item.get("key") or "").strip() for item in assets}
    if "cover" in asset_keys and "report-asset://cover" not in text:
        cover_meta = _get_asset_meta(style_profile, "cover", "封面摘要图", "自动摘要卡片")
        text = re.sub(
            r"^(# .+)$",
            rf"\1\n\n![{cover_meta['title']}](report-asset://cover)",
            text,
            count=1,
            flags=re.M,
        )

    appended_keys: List[str] = []
    asset_labels = style_profile.get("asset_labels") if isinstance(style_profile.get("asset_labels"), dict) else {}
    visual_section_title = str(asset_labels.get("visual_section_title") or "附图").strip()
    lines = [text.rstrip(), "", f"## {visual_section_title}", ""]
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
    ensure_langchain_uuid_compat()
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
    style_profile = load_full_report_style_profile(skill_context.get("documentType"))
    event_copy = style_profile.get("events") if isinstance(style_profile.get("events"), dict) else {}

    _emit_event(
        event_callback,
        {
            "type": "phase.started",
            "phase": "analysis",
            "title": str(event_copy.get("phase_write_title") or "完整文本编排"),
            "message": "正在运行 scene_router 与 analysis_graph。",
        },
    )
    analysis_state = _run_full_report_analysis_graph(
        topic_identifier=topic_identifier,
        topic_label=display_name,
        start=start_text,
        end=end_text,
        structured_payload=structured_payload,
        knowledge_context=knowledge_context,
        skill_context=skill_context,
        style_profile=style_profile,
        event_callback=event_callback,
    )
    scene_profile = analysis_state.get("scene_profile") if isinstance(analysis_state.get("scene_profile"), dict) else {}
    scene_source = str(analysis_state.get("scene_source") or "fallback").strip() or "fallback"
    base_facts = analysis_state.get("base_facts") if isinstance(analysis_state.get("base_facts"), dict) else {}
    analysis_outputs = analysis_state.get("analysis_outputs") if isinstance(analysis_state.get("analysis_outputs"), dict) else {}
    analysis_trace = analysis_state.get("analysis_trace") if isinstance(analysis_state.get("analysis_trace"), dict) else {}
    facts = _merge_analysis_outputs_into_facts(base_facts, analysis_outputs)
    facts["style_profile"] = style_profile
    facts["scene_profile"] = scene_profile
    facts["analysis_trace"] = analysis_trace

    _emit_event(
        event_callback,
        {
            "type": "agent.memo",
            "phase": "analysis",
            "agent": "analysis_graph",
            "title": "Analysis Graph 公开备忘录",
            "message": "analysis_graph 已完成证据、机制、claim gate 和风险桥接整理。",
            "delta": "analysis_graph 已完成证据、机制、claim gate 和风险桥接整理。",
            "payload": {
                **_build_agent_trace_payload(
                    agent_runtime="langgraph_graph",
                    tools_allowed=[],
                    tool_policy_mode="analysis",
                    scene_id=str(scene_profile.get("scene_id") or "").strip(),
                ),
                "scene_id": str(scene_profile.get("scene_id") or "").strip(),
                "analysis_iterations": int(analysis_state.get("analysis_iterations") or 0),
                "claim_gate_stats": facts.get("claim_gate_stats") if isinstance(facts.get("claim_gate_stats"), dict) else {},
                "analysis_issues": analysis_state.get("analysis_issues") or [],
            },
        },
    )

    _emit_event(
        event_callback,
        {
            "type": "phase.progress",
            "phase": "write",
            "title": str(event_copy.get("phase_write_title") or "完整文本编排"),
            "message": "正在运行 writing_graph。",
        },
    )
    writing_state = _run_full_report_writing_graph(
        topic_label=display_name,
        structured_payload=structured_payload,
        skill_context=skill_context,
        style_profile=style_profile,
        scene_profile=scene_profile,
        facts=facts,
        event_callback=event_callback,
    )
    layout_plan = writing_state.get("layout_plan") if isinstance(writing_state.get("layout_plan"), dict) else {}
    layout_source = str(writing_state.get("layout_source") or "fallback").strip() or "fallback"
    section_budget = writing_state.get("section_budget") if isinstance(writing_state.get("section_budget"), dict) else {}
    budget_source = str(writing_state.get("budget_source") or "fallback").strip() or "fallback"
    brief_payload = writing_state.get("brief_payload") if isinstance(writing_state.get("brief_payload"), dict) else {}
    brief_source = str(writing_state.get("brief_source") or "fallback").strip() or "fallback"
    section_outputs = writing_state.get("section_outputs") if isinstance(writing_state.get("section_outputs"), list) else []
    section_outcomes = writing_state.get("section_outcomes") if isinstance(writing_state.get("section_outcomes"), list) else []
    exploration_sections = writing_state.get("exploration_sections") if isinstance(writing_state.get("exploration_sections"), list) else []
    exploration_turns_total = int(writing_state.get("exploration_turns_total") or 0)
    tool_call_count_total = int(writing_state.get("tool_call_count_total") or 0)
    section_stop_reasons = writing_state.get("section_stop_reasons") if isinstance(writing_state.get("section_stop_reasons"), dict) else {}
    facts = writing_state.get("facts") if isinstance(writing_state.get("facts"), dict) else facts
    final_markdown = str(writing_state.get("final_markdown") or "").strip()
    revise_source = str(writing_state.get("revise_source") or "fallback").strip() or "fallback"
    draft_source = "writing_graph"

    _emit_event(
        event_callback,
        {
            "type": "agent.memo",
            "phase": "write",
            "agent": "writing_graph",
            "title": "Writing Graph 公开备忘录",
            "message": "writing_graph 已完成 section writer / critics / editor 编排。",
            "delta": "writing_graph 已完成 section writer / critics / editor 编排。",
            "payload": {
                **_build_agent_trace_payload(
                    agent_runtime="langgraph_graph",
                    tools_allowed=[],
                    tool_policy_mode="write",
                    scene_id=str(scene_profile.get("scene_id") or "").strip(),
                    tool_call_count=tool_call_count_total,
                    stop_reason="graph_completed",
                ),
                "layout_source": layout_source,
                "budget_source": budget_source,
                "brief_source": brief_source,
                "section_count": len(section_outputs),
                "section_rewrite_count": int(writing_state.get("section_rewrite_count") or 0),
                "sections": section_outcomes,
                "exploration_sections": exploration_sections,
                "tool_call_count_total": tool_call_count_total,
            },
        },
    )

    if not final_markdown:
        fallback_draft = _call_markdown_agent(
            build_full_report_markdown_prompt({"facts": facts, "brief": brief_payload}),
            max_tokens=3200,
        )
        final_markdown = fallback_draft.strip() or _fallback_markdown(facts, brief_payload, style_profile)
        draft_source = "llm_fallback" if fallback_draft.strip() else "fallback"
        finalized = _finalize_report_markdown(
            draft_markdown=final_markdown,
            facts=facts,
            brief_payload=brief_payload,
            structured_payload=structured_payload,
            display_name=display_name,
            style_profile=style_profile,
        )
        final_markdown = str(finalized.get("markdown") or "").strip()
        revise_source = str(finalized.get("revise_source") or "").strip() or revise_source

    assets = _build_visual_assets(structured_payload, style_profile)
    final_markdown = _inject_visual_assets(final_markdown, assets, style_profile)
    now_text = datetime.now().strftime("%Y-%m-%d %H:%M")

    _emit_event(
        event_callback,
        {
            "type": "agent.memo",
            "phase": "review",
            "agent": "report_editor",
            "title": str(event_copy.get("reviser_memo_title") or "Reviser 公开备忘录"),
            "message": str(event_copy.get("reviser_memo_message") or "Markdown 文本已完成 revise，并自动插入图示。"),
            "delta": str(event_copy.get("reviser_memo_message") or "Markdown 文本已完成 revise，并自动插入图示。"),
            "payload": {
                **_build_agent_trace_payload(
                    agent_runtime="langgraph_node",
                    tools_allowed=[],
                    tool_policy_mode="off",
                    scene_id=str(scene_profile.get("scene_id") or "").strip(),
                ),
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
        "meta": {
            "topic_identifier": topic_identifier,
            "topic_label": display_name,
            "cache_version": AI_FULL_REPORT_CACHE_VERSION,
            "generated_at": now_text,
            "scene_id": str(scene_profile.get("scene_id") or "").strip(),
            "scene_source": scene_source,
            "analysis_graph_source": str(analysis_state.get("analysis_graph_source") or "analysis_graph").strip(),
            "writing_graph_source": str(writing_state.get("writing_graph_source") or "writing_graph").strip(),
            "layout_source": layout_source,
            "budget_source": budget_source,
            "brief_source": brief_source,
            "draft_source": draft_source,
            "revise_source": revise_source,
            "analysis_iterations": int(analysis_state.get("analysis_iterations") or 0),
            "section_rewrite_count": int(writing_state.get("section_rewrite_count") or 0),
            "agent_runtime": next(
                (
                    str((value or {}).get("runtime") or "").strip()
                    for value in analysis_trace.values()
                    if isinstance(value, dict) and str((value or {}).get("runtime") or "").strip()
                ),
                next(
                    (
                        str(((item or {}).get("trace") or {}).get("runtime") or "").strip()
                        for item in exploration_sections
                        if isinstance(item, dict)
                        and isinstance(item.get("trace"), dict)
                        and str(((item.get("trace") or {}).get("runtime")) or "").strip()
                    ),
                    "langchain_create_agent",
                ),
            ),
            "analysis_trace": analysis_trace,
            "exploration_sections": exploration_sections,
            "exploration_turns_total": exploration_turns_total,
            "tool_call_count_total": tool_call_count_total,
            "tool_trace_summary": {
                "analysis": {
                    key: {
                        "tool_call_count": int((value or {}).get("tool_call_count") or 0),
                        "stop_reason": str((value or {}).get("stop_reason") or "").strip(),
                    }
                    for key, value in analysis_trace.items()
                    if isinstance(value, dict)
                },
                "sections": [
                    {
                        "id": str(item.get("id") or "").strip(),
                        "tool_call_count": int(item.get("tool_call_count") or 0),
                        "stop_reason": str(item.get("stop_reason") or "").strip(),
                    }
                    for item in section_outcomes
                    if isinstance(item, dict)
                ],
            },
            "section_stop_reasons": section_stop_reasons,
            "claim_gate_stats": facts.get("claim_gate_stats") if isinstance(facts.get("claim_gate_stats"), dict) else {},
            "selected_scene": scene_profile,
            "layout_plan": layout_plan,
            "budget_plan": section_budget,
            "claim_matrix": facts.get("claim_matrix") if isinstance(facts.get("claim_matrix"), list) else [],
            "section_plan": brief_payload.get("sections") if isinstance(brief_payload.get("sections"), list) else [],
            "section_outcomes": section_outcomes,
            "asset_count": len(assets),
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
            "title": str(event_copy.get("artifact_title") or "完整文本已写入"),
            "message": str(event_copy.get("artifact_message") or "Markdown 正文和自动图示已写入缓存。"),
            "payload": {
                "full_report_ready": True,
                "full_report_cache_path": str(cache_path),
                "full_report_title": str(payload.get("title") or "").strip(),
            },
        },
    )

    return payload
