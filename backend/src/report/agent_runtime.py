from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional, TypedDict

from langchain.agents import create_agent
from langchain.agents.middleware import (
    ModelCallLimitMiddleware,
    ToolCallLimitMiddleware,
    ToolRetryMiddleware,
    dynamic_prompt,
    wrap_model_call,
    wrap_tool_call,
)
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver

from ..utils.ai import build_langchain_chat_model
from .tools import ensure_langchain_toolset_valid, get_report_tool_bundle


class ToolPolicy(TypedDict, total=False):
    allowed_tools: List[Any]
    required_tools: List[str]
    max_exploration_turns: int
    tool_choice_policy: str
    parallel_tool_calls: bool
    stop_conditions: List[str]
    escalation_conditions: List[str]
    exploration_mode: str
    scope_id: str


class ReportAgentContext(TypedDict, total=False):
    topic_identifier: str
    topic_label: str
    time_range: Dict[str, str]
    scene_id: str
    section_id: str
    claim_matrix: List[Dict[str, Any]]
    section_evidence_pack: List[Dict[str, Any]]
    style_contract: Dict[str, Any]
    tool_policy: ToolPolicy


class ExplorationTrace(TypedDict, total=False):
    tool_calls: List[Dict[str, Any]]
    tool_results: List[Dict[str, Any]]
    stop_reason: str
    evidence_summary: List[str]
    unresolved_questions: List[str]
    tool_call_count: int
    exploration_turns: int


def ensure_langchain_uuid_compat() -> None:
    try:
        import langchain_core.utils.uuid as lc_uuid
    except Exception:
        return
    try:
        lc_uuid._uuid_utils_uuid7()  # type: ignore[attr-defined]
    except Exception:
        lc_uuid._uuid_utils_uuid7 = lambda timestamp=None, nanos=None: uuid.uuid4()  # type: ignore[attr-defined]


def _extract_json_text(raw_text: str) -> str:
    text = str(raw_text or "").strip()
    if not text:
        return ""
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1].strip()
    return ""


def _safe_json_loads(raw_text: str) -> Dict[str, Any]:
    candidate = _extract_json_text(raw_text)
    if not candidate:
        return {}
    try:
        value = json.loads(candidate)
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def build_section_tool_policy(scene_id: str, section_id: str) -> ToolPolicy:
    tools = get_report_tool_bundle(scene_id, section_id)
    deep_sections = {
        ("policy_dynamics", "evolution"),
        ("public_hotspot", "propagation"),
        ("crisis_response", "timeline"),
        ("crisis_response", "propagation"),
    }
    action_sections = {
        ("policy_dynamics", "action"),
        ("public_hotspot", "action"),
        ("crisis_response", "response"),
        ("routine_monitoring", "risk"),
    }
    pair = (str(scene_id or "").strip(), str(section_id or "").strip())
    required_tools: List[str] = []
    tool_choice_policy = "auto"
    if pair in deep_sections:
        required_tools = [str(getattr(tool, "name", "") or "").strip() for tool in tools[:2] if str(getattr(tool, "name", "") or "").strip()]
        tool_choice_policy = "required_any"
    if pair in action_sections:
        required_tools = ["claim_verifier_tool"]
    exploration_mode = "deep" if pair in deep_sections and tools else "off"
    return {
        "allowed_tools": tools,
        "required_tools": required_tools,
        "max_exploration_turns": 4 if pair in deep_sections else 2,
        "tool_choice_policy": tool_choice_policy,
        "parallel_tool_calls": pair in deep_sections,
        "stop_conditions": [
            "已获得至少一组可写证据和一条边界说明时停止探索。",
            "达到工具调用上限后必须收束，不得无边界继续扩展。",
        ],
        "escalation_conditions": [
            "若 required_tools 未命中，应在正文中降级判断强度。",
            "若 claim_matrix 存在 unverified/conflicting，必须保留边界说明。",
        ],
        "exploration_mode": exploration_mode,
        "scope_id": f"{str(scene_id or '').strip()}::{str(section_id or '').strip()}",
    }


def _build_analysis_tool_policy(scene_id: str, agent_name: str) -> ToolPolicy:
    pair = (str(scene_id or "").strip(), str(agent_name or "").strip())
    scope_map = {
        ("policy_dynamics", "evidence_analyst"): ["raw_item_search_tool", "temporal_event_window_tool", "content_focus_compare_tool"],
        ("public_hotspot", "evidence_analyst"): ["raw_item_search_tool", "temporal_event_window_tool", "content_focus_compare_tool"],
        ("crisis_response", "evidence_analyst"): ["raw_item_search_tool", "temporal_event_window_tool", "content_focus_compare_tool"],
        ("policy_dynamics", "mechanism_analyst"): ["theory_matcher_tool", "reference_search_tool"],
        ("public_hotspot", "mechanism_analyst"): ["theory_matcher_tool", "reference_search_tool"],
        ("crisis_response", "mechanism_analyst"): ["theory_matcher_tool", "reference_search_tool"],
        ("policy_dynamics", "claim_judge"): ["claim_verifier_tool"],
        ("public_hotspot", "claim_judge"): ["claim_verifier_tool"],
        ("crisis_response", "claim_judge"): ["claim_verifier_tool"],
    }
    available = (
        get_report_tool_bundle(scene_id, "evolution")
        + get_report_tool_bundle(scene_id, "response")
        + get_report_tool_bundle(scene_id, "impact")
    )
    by_name = {str(getattr(tool, "name", "") or "").strip(): tool for tool in available if str(getattr(tool, "name", "") or "").strip()}
    selected = [by_name[name] for name in scope_map.get(pair, []) if name in by_name]
    max_turns = 2 if str(agent_name or "").strip() == "evidence_analyst" else 1
    return {
        "allowed_tools": selected,
        "required_tools": [name for name in scope_map.get(pair, [])[:1]] if str(agent_name or "").strip() == "evidence_analyst" else [],
        "max_exploration_turns": max_turns,
        "tool_choice_policy": "required_any" if selected and str(agent_name or "").strip() == "evidence_analyst" else "auto",
        "parallel_tool_calls": False,
        "stop_conditions": ["完成核心证据检索后停止。"],
        "escalation_conditions": ["若缺少直接证据，必须保留不确定性。"],
        "exploration_mode": "analysis",
        "scope_id": f"{str(scene_id or '').strip()}::{str(agent_name or '').strip()}",
    }


def _build_thread_id(context: ReportAgentContext, suffix: str) -> str:
    topic_identifier = str(context.get("topic_identifier") or "report").strip()
    scene_id = str(context.get("scene_id") or "scene").strip()
    section_id = str(context.get("section_id") or context.get("tool_policy", {}).get("scope_id") or "scope").strip()
    return f"{topic_identifier}:{scene_id}:{section_id}:{suffix}"


def create_report_agent_runner(
    policy: ToolPolicy,
    context: ReportAgentContext,
    *,
    task: str = "report",
    model_role: str = "report",
    system_prompt: str,
    max_tokens: int = 2200,
    temperature: float = 0.2,
    name: str = "report_agent",
) -> Optional[Dict[str, Any]]:
    ensure_langchain_uuid_compat()
    llm, client_cfg = build_langchain_chat_model(
        task=task,
        model_role=model_role,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    if llm is None or client_cfg is None:
        return None

    allowed_tools = policy.get("allowed_tools") or []
    ensure_langchain_toolset_valid(list(allowed_tools))
    required_tools = [str(item).strip() for item in (policy.get("required_tools") or []) if str(item or "").strip()]
    max_turns = max(1, int(policy.get("max_exploration_turns") or 4))
    parallel_tool_calls = bool(policy.get("parallel_tool_calls"))
    runtime_context = dict(context or {})
    runtime_context["tool_policy"] = policy

    @dynamic_prompt
    def _runtime_prompt(request: Any) -> str:
        runtime_context = request.runtime.context or {}
        tool_policy = runtime_context.get("tool_policy") if isinstance(runtime_context, dict) and isinstance(runtime_context.get("tool_policy"), dict) else {}
        tool_names = [
            str(getattr(tool, "name", "") or "").strip()
            for tool in (tool_policy.get("allowed_tools") or [])
            if str(getattr(tool, "name", "") or "").strip()
        ]
        required = [str(item).strip() for item in (tool_policy.get("required_tools") or []) if str(item or "").strip()]
        stop_conditions = tool_policy.get("stop_conditions") if isinstance(tool_policy, dict) else []
        escalation_conditions = tool_policy.get("escalation_conditions") if isinstance(tool_policy, dict) else []
        return (
            f"{system_prompt}\n\n"
            f"当前 scene: {str(runtime_context.get('scene_id') or '').strip()}\n"
            f"当前 section: {str(runtime_context.get('section_id') or '').strip()}\n"
            f"允许工具: {', '.join(tool_names) if tool_names else '无'}\n"
            f"必需优先命中的工具: {', '.join(required) if required else '无'}\n"
            f"停止条件: {'；'.join(str(item).strip() for item in stop_conditions if str(item or '').strip()) or '得到足够证据后停止'}\n"
            f"升级条件: {'；'.join(str(item).strip() for item in escalation_conditions if str(item or '').strip()) or '证据不足时降低判断强度'}\n"
            "如果能通过工具补证，请先补证；如果证据仍不足，必须明确保留边界。"
        )

    @wrap_model_call
    def _model_policy(request: Any, handler: Any) -> Any:
        request.model_settings = {**(request.model_settings or {}), "parallel_tool_calls": parallel_tool_calls}
        return handler(request)

    @wrap_tool_call
    def _tool_policy(request: Any, handler: Any) -> Any:
        return handler(request)

    middleware: List[Any] = [
        _runtime_prompt,
        _model_policy,
        _tool_policy,
        ModelCallLimitMiddleware(run_limit=max_turns + (2 if allowed_tools else 1), exit_behavior="end"),
        ToolCallLimitMiddleware(run_limit=max_turns, exit_behavior="end"),
        ToolRetryMiddleware(max_retries=1, on_failure="return_message"),
    ]
    agent = create_agent(
        model=llm,
        tools=allowed_tools,
        middleware=middleware,
        checkpointer=InMemorySaver(),
        name=name,
        debug=False,
    )
    return {
        "agent": agent,
        "client_cfg": client_cfg,
        "context": runtime_context,
        "policy": policy,
        "thread_id": _build_thread_id(context, name),
    }


def _extract_agent_trace(messages: List[Any], policy: ToolPolicy) -> ExplorationTrace:
    tool_calls: List[Dict[str, Any]] = []
    tool_results: List[Dict[str, Any]] = []
    evidence_summary: List[str] = []
    for message in messages:
        if isinstance(message, AIMessage):
            for tool_call in message.tool_calls or []:
                tool_calls.append(
                    {
                        "name": str(tool_call.get("name") or "").strip(),
                        "args": tool_call.get("args") or {},
                        "id": str(tool_call.get("id") or "").strip(),
                    }
                )
        elif isinstance(message, ToolMessage):
            output = str(message.content or "").strip()
            tool_results.append(
                {
                    "name": str(getattr(message, "name", "") or "").strip(),
                    "tool_call_id": str(getattr(message, "tool_call_id", "") or "").strip(),
                    "output": output,
                }
            )
            if output:
                evidence_summary.append(output[:180])
    called_names = {str(item.get("name") or "").strip() for item in tool_calls if str(item.get("name") or "").strip()}
    required = {str(item).strip() for item in (policy.get("required_tools") or []) if str(item or "").strip()}
    if required and not (called_names & required):
        stop_reason = "missing_required_tools"
    elif tool_calls and len(tool_calls) >= int(policy.get("max_exploration_turns") or 4):
        stop_reason = "tool_call_limit"
    elif tool_calls:
        stop_reason = "model_stopped"
    else:
        stop_reason = "no_tool_call"
    return {
        "tool_calls": tool_calls,
        "tool_results": tool_results,
        "stop_reason": stop_reason,
        "evidence_summary": evidence_summary[:6],
        "unresolved_questions": [],
        "tool_call_count": len(tool_calls),
        "exploration_turns": len(tool_calls),
    }


def run_report_agent_step(
    agent_runner: Dict[str, Any],
    input_state: Dict[str, Any],
) -> Dict[str, Any]:
    agent = agent_runner.get("agent")
    if agent is None:
        return {"content": "", "messages": [], "trace": {}}
    user_prompt = str(input_state.get("prompt") or "").strip()
    if not user_prompt:
        return {"content": "", "messages": [], "trace": {}}
    result = agent.invoke(
        {"messages": [{"role": "user", "content": user_prompt}]},
        config={"configurable": {"thread_id": str(agent_runner.get("thread_id") or "report_agent")}},
        context=agent_runner.get("context") or {},
    )
    messages = result.get("messages") if isinstance(result, dict) and isinstance(result.get("messages"), list) else []
    final_content = ""
    for message in reversed(messages):
        if isinstance(message, AIMessage) and not (message.tool_calls or []):
            final_content = str(message.content or "").strip()
            break
    trace = _extract_agent_trace(messages, agent_runner.get("policy") or {})
    return {"content": final_content, "messages": messages, "trace": trace}


def create_analysis_agent_runner(scene_id: str, agent_name: str, context: ReportAgentContext, *, system_prompt: str, max_tokens: int = 2000) -> Optional[Dict[str, Any]]:
    policy = _build_analysis_tool_policy(scene_id, agent_name)
    return create_report_agent_runner(
        policy,
        context,
        system_prompt=system_prompt,
        max_tokens=max_tokens,
        temperature=0.15,
        name=agent_name,
    )


def run_section_exploration(section_context: Dict[str, Any], tool_policy: ToolPolicy) -> Dict[str, Any]:
    scene_profile = section_context.get("scene_profile") if isinstance(section_context.get("scene_profile"), dict) else {}
    section = section_context.get("section") if isinstance(section_context.get("section"), dict) else {}
    context: ReportAgentContext = {
        "topic_identifier": str(section_context.get("topic_identifier") or "").strip(),
        "topic_label": str(section_context.get("topic_label") or "").strip(),
        "time_range": section_context.get("time_range") if isinstance(section_context.get("time_range"), dict) else {},
        "scene_id": str(scene_profile.get("scene_id") or "").strip(),
        "section_id": str(section.get("id") or "").strip(),
        "claim_matrix": section_context.get("claim_matrix") if isinstance(section_context.get("claim_matrix"), list) else [],
        "section_evidence_pack": section_context.get("section_evidence_pack") if isinstance(section_context.get("section_evidence_pack"), list) else [],
        "style_contract": section_context.get("style_profile") if isinstance(section_context.get("style_profile"), dict) else {},
        "tool_policy": tool_policy,
    }
    runner = create_report_agent_runner(
        tool_policy,
        context,
        system_prompt="你是报告 section 的 exploration analyst。先主动调用工具补证，再只输出合法 JSON。",
        max_tokens=1800,
        temperature=0.1,
        name="section_exploration",
    )
    if runner is None:
        return {
            "status": "fallback",
            "evidence_summary": [],
            "unresolved_questions": [],
            "trace": {"tool_calls": [], "tool_results": [], "stop_reason": "runner_unavailable", "tool_call_count": 0, "exploration_turns": 0},
        }
    prompt = (
        "请先用可用工具补充该节最关键的证据，再输出 JSON。\n"
        "JSON schema:\n"
        "{\n"
        '  "status": "ok",\n'
        '  "evidence_summary": ["最多6条，可直接给 writer 使用的证据结论"],\n'
        '  "unresolved_questions": ["最多4条，尚未证成的问题"],\n'
        '  "boundary": ["最多4条，本节不能越过的证据边界"]\n'
        "}\n\n"
        f"【section_context】\n{json.dumps(section_context, ensure_ascii=False)}"
    )
    result = run_report_agent_step(runner, {"prompt": prompt})
    payload = _safe_json_loads(str(result.get("content") or ""))
    if not payload:
        payload = {
            "status": "partial",
            "evidence_summary": (result.get("trace") or {}).get("evidence_summary") or [],
            "unresolved_questions": [],
            "boundary": [],
        }
    payload["policy"] = tool_policy
    payload["trace"] = result.get("trace") or {}
    payload["_agent_runner"] = runner
    return payload


def run_section_writer_agent(section_context: Dict[str, Any], exploration_result: Dict[str, Any]) -> Dict[str, Any]:
    scene_profile = section_context.get("scene_profile") if isinstance(section_context.get("scene_profile"), dict) else {}
    section = section_context.get("section") if isinstance(section_context.get("section"), dict) else {}
    tool_policy = build_section_tool_policy(
        str(scene_profile.get("scene_id") or "").strip(),
        str(section.get("id") or "").strip(),
    )
    writer_policy = dict(tool_policy)
    if exploration_result.get("evidence_summary") or exploration_result.get("boundary"):
        writer_policy["allowed_tools"] = []
        writer_policy["required_tools"] = []
        writer_policy["max_exploration_turns"] = 1
        writer_policy["parallel_tool_calls"] = False
    else:
        writer_policy["max_exploration_turns"] = min(2, int(tool_policy.get("max_exploration_turns") or 2))
    context: ReportAgentContext = {
        "topic_identifier": str(section_context.get("topic_identifier") or "").strip(),
        "topic_label": str(section_context.get("topic_label") or "").strip(),
        "time_range": section_context.get("time_range") if isinstance(section_context.get("time_range"), dict) else {},
        "scene_id": str(scene_profile.get("scene_id") or "").strip(),
        "section_id": str(section.get("id") or "").strip(),
        "claim_matrix": section_context.get("claim_matrix") if isinstance(section_context.get("claim_matrix"), list) else [],
        "section_evidence_pack": section_context.get("section_evidence_pack") if isinstance(section_context.get("section_evidence_pack"), list) else [],
        "style_contract": section_context.get("style_profile") if isinstance(section_context.get("style_profile"), dict) else {},
        "tool_policy": writer_policy,
    }
    runner = create_report_agent_runner(
        writer_policy,
        context,
        system_prompt="你是报告 section writer。优先复用 exploration_result 的证据写作；只有在证据明显不足时才继续补查。只输出 Markdown 正文。",
        max_tokens=2200,
        temperature=0.2,
        name="section_writer",
    )
    if runner is None:
        return {"markdown": "", "trace": {"tool_calls": [], "tool_results": [], "stop_reason": "runner_unavailable", "tool_call_count": 0, "exploration_turns": 0}}
    prompt = (
        "请基于 section_context 与 exploration_result 撰写该节 Markdown 正文。\n"
        "要求：只输出正文，不要 H1/H2，不要 JSON，不要暴露工具或字段名。\n"
        "如已有 exploration_result，就优先复用已有证据；只有在证据不足时才继续补查。\n\n"
        f"【section_context】\n{json.dumps(section_context, ensure_ascii=False)}\n\n"
        f"【exploration_result】\n{json.dumps({k: v for k, v in exploration_result.items() if not str(k).startswith('_')}, ensure_ascii=False)}"
    )
    result = run_report_agent_step(runner, {"prompt": prompt})
    return {
        "markdown": str(result.get("content") or "").strip(),
        "trace": result.get("trace") or {},
        "policy": writer_policy,
        "_agent_runner": runner,
    }
