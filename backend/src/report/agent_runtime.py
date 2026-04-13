from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional, TypedDict

from langchain.agents import create_agent
from langchain.agents.middleware import (
    ModelCallLimitMiddleware,
    ToolCallLimitMiddleware,
    ToolRetryMiddleware,
    wrap_model_call,
    wrap_tool_call,
)
from langchain_core.messages import AIMessage, ToolMessage

from ..utils.ai import build_langchain_chat_model
from .deepagents_backends import build_state_backend
from .runtime_infra import build_report_runnable_config, build_runtime_diagnostics, get_shared_report_checkpointer
from .skills import (
    build_report_skill_runtime_assets,
    discover_report_skills,
    read_report_skill_resource,
    resolve_report_skill,
    select_report_skill_sources,
)
from .tools import ensure_langchain_toolset_valid, select_report_tools
from .tools.registry import READ_ONLY, get_report_tool_spec


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
    runtime: str


_ALLOWED_RUNTIME_BUILTIN_TOOLS = frozenset(
    {
        "write_todos",
        "ls",
        "read_file",
        "glob",
        "grep",
        "compact_conversation",
    }
)


def _json_safe_runtime_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {
            str(key): _json_safe_runtime_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_json_safe_runtime_value(item) for item in value]
    tool_name = str(getattr(value, "name", "") or getattr(value, "__name__", "") or "").strip()
    if tool_name:
        return tool_name
    return str(value)


def snapshot_tool_policy(policy: ToolPolicy) -> Dict[str, Any]:
    payload = policy if isinstance(policy, dict) else {}
    return {
        "allowed_tools": [
            str(getattr(tool, "name", "") or getattr(tool, "__name__", "") or "").strip()
            for tool in (payload.get("allowed_tools") or [])
            if str(getattr(tool, "name", "") or getattr(tool, "__name__", "") or "").strip()
        ],
        "required_tools": [
            str(item).strip()
            for item in (payload.get("required_tools") or [])
            if str(item or "").strip()
        ],
        "max_exploration_turns": int(payload.get("max_exploration_turns") or 0),
        "tool_choice_policy": str(payload.get("tool_choice_policy") or "").strip(),
        "parallel_tool_calls": bool(payload.get("parallel_tool_calls")),
        "stop_conditions": [
            str(item).strip()
            for item in (payload.get("stop_conditions") or [])
            if str(item or "").strip()
        ],
        "escalation_conditions": [
            str(item).strip()
            for item in (payload.get("escalation_conditions") or [])
            if str(item or "").strip()
        ],
        "exploration_mode": str(payload.get("exploration_mode") or "").strip(),
        "scope_id": str(payload.get("scope_id") or "").strip(),
    }


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


def _build_skill_catalog_prompt(topic: str) -> str:
    catalog = discover_report_skills(topic)
    if not catalog:
        return "当前未注册可用 skills。"
    lines = [
        "当前可用 skills catalog：",
    ]
    for item in catalog:
        skill_key = str(item.get("skill_key") or item.get("name") or "").strip()
        agent_skill_name = str(item.get("agentSkillName") or "").strip()
        description = str(item.get("description") or "").strip()
        document_type = str(item.get("documentType") or "").strip()
        source_scope = str(item.get("sourceScope") or "").strip()
        target = agent_skill_name or skill_key or "unknown-skill"
        lines.append(
            f"- {target}: {description or '无描述'}"
            f"{f' | documentType={document_type}' if document_type else ''}"
            f"{f' | source={source_scope}' if source_scope else ''}"
        )
    lines.append("如果当前任务明显匹配某个 skill，请先调用 load_skill 读取完整说明。")
    return "\n".join(lines)


def _compose_runtime_system_prompt(
    *,
    base_prompt: str,
    context: ReportAgentContext,
    policy: ToolPolicy,
    include_plain_skill_catalog: bool,
    topic: str,
) -> str:
    tool_names = [
        str(getattr(tool, "name", "") or "").strip()
        for tool in (policy.get("allowed_tools") or [])
        if str(getattr(tool, "name", "") or "").strip()
    ]
    required = [str(item).strip() for item in (policy.get("required_tools") or []) if str(item or "").strip()]
    stop_conditions = policy.get("stop_conditions") if isinstance(policy, dict) and isinstance(policy.get("stop_conditions"), list) else []
    escalation_conditions = (
        policy.get("escalation_conditions")
        if isinstance(policy, dict) and isinstance(policy.get("escalation_conditions"), list)
        else []
    )
    skill_section = ""
    if include_plain_skill_catalog:
        skill_section = f"\n\n{_build_skill_catalog_prompt(topic)}"
    return (
        f"{base_prompt}{skill_section}\n\n"
        f"当前 scene: {str(context.get('scene_id') or '').strip()}\n"
        f"当前 section: {str(context.get('section_id') or '').strip()}\n"
        f"允许工具: {', '.join(tool_names) if tool_names else '无'}\n"
        f"必需优先命中的工具: {', '.join(required) if required else '无'}\n"
        f"停止条件: {'；'.join(str(item).strip() for item in stop_conditions if str(item or '').strip()) or '得到足够证据后停止'}\n"
        f"升级条件: {'；'.join(str(item).strip() for item in escalation_conditions if str(item or '').strip()) or '证据不足时降低判断强度'}\n"
        "如果能通过工具补证，请先补证；如果证据仍不足，必须明确保留边界。"
    )


def _build_plain_load_skill_tool(topic: str) -> Any:
    from langchain_core.tools import tool

    @tool("load_skill")
    def load_skill(skill_name: str) -> str:
        """Load the full instructions for a report skill by name or alias."""
        resolved = resolve_report_skill(skill_name, topic=topic)
        resource_contents: Dict[str, str] = {}
        for item in resolved.get("resourceIndex") or []:
            relative_path = str(item.get("path") or "").strip()
            if not relative_path:
                continue
            if str(item.get("kind") or "") not in {"references", "root"}:
                continue
            if not bool(item.get("staged")):
                continue
            try:
                resource_contents[relative_path] = read_report_skill_resource(
                    str(resolved.get("skill_key") or resolved.get("name") or skill_name),
                    relative_path,
                    topic=topic,
                )[:6000]
            except Exception:
                continue
            if len(resource_contents) >= 3:
                break
        payload = {
            "skill_key": resolved.get("skill_key") or resolved.get("name"),
            "agent_skill_name": resolved.get("agentSkillName"),
            "display_name": resolved.get("displayName"),
            "description": resolved.get("description"),
            "document_type": resolved.get("documentType"),
            "instructions_markdown": resolved.get("instructionsMarkdown"),
            "sections": resolved.get("sections") if isinstance(resolved.get("sections"), dict) else {},
            "resource_index": resolved.get("resourceIndex") if isinstance(resolved.get("resourceIndex"), list) else [],
            "resource_contents": resource_contents,
        }
        return json.dumps(payload, ensure_ascii=False)

    return load_skill


def _build_runtime_middleware(
    *,
    policy: ToolPolicy,
) -> List[Any]:
    allowed_tool_names = {
        str(getattr(tool, "name", "") or "").strip()
        for tool in (policy.get("allowed_tools") or [])
        if str(getattr(tool, "name", "") or "").strip()
    }
    required_tools = [str(item).strip() for item in (policy.get("required_tools") or []) if str(item or "").strip()]
    max_turns = max(1, int(policy.get("max_exploration_turns") or 4))
    tool_choice_policy = str(policy.get("tool_choice_policy") or "").strip() or "auto"
    parallel_tool_calls = bool(policy.get("parallel_tool_calls"))
    tool_limit_exit_behavior = "continue" if parallel_tool_calls else "end"

    def _required_tools_already_hit(messages: List[Any]) -> bool:
        required = set(required_tools)
        if not required:
            return True
        for message in messages:
            if isinstance(message, ToolMessage):
                tool_name = str(getattr(message, "name", "") or "").strip()
                if tool_name in required:
                    return True
        return False

    @wrap_model_call(name="ReportRuntimePolicyMiddleware")
    def _model_policy(request: Any, handler: Any) -> Any:
        request = request.override(
            model_settings={**(request.model_settings or {}), "parallel_tool_calls": parallel_tool_calls}
        )
        if tool_choice_policy == "required_any" and required_tools:
            messages = request.state.get("messages", []) if isinstance(request.state, dict) else []
            if not _required_tools_already_hit(messages if isinstance(messages, list) else []):
                required_toolset = [
                    tool
                    for tool in request.tools
                    if str(getattr(tool, "name", "") or "").strip() in required_tools
                ]
                if required_toolset:
                    request = request.override(tools=required_toolset, tool_choice="any")
        return handler(request)

    @wrap_tool_call
    def _tool_policy(request: Any, handler: Any) -> Any:
        tool_call = request.tool_call if isinstance(request.tool_call, dict) else {}
        tool_name = str(tool_call.get("name") or "").strip()
        if tool_name and tool_name not in allowed_tool_names and tool_name not in _ALLOWED_RUNTIME_BUILTIN_TOOLS:
            allowed_names = sorted({*allowed_tool_names, *_ALLOWED_RUNTIME_BUILTIN_TOOLS})
            return ToolMessage(
                content=(
                    f"Tool '{tool_name}' is not allowed in this report runtime step. "
                    f"Allowed tools: {', '.join(allowed_names)}."
                ),
                tool_call_id=str(tool_call.get("id") or "").strip() or None,
                name=tool_name,
                status="error",
            )
        return handler(request)

    return [
        _model_policy,
        _tool_policy,
        ModelCallLimitMiddleware(run_limit=max_turns + (2 if required_tools else 1), exit_behavior="end"),
        ToolCallLimitMiddleware(run_limit=max_turns, exit_behavior=tool_limit_exit_behavior),
        ToolRetryMiddleware(max_retries=1, on_failure="continue"),
    ]


def build_section_tool_policy(scene_id: str, section_id: str) -> ToolPolicy:
    tools = select_report_tools(runtime_target="agent_runtime_section", scene_id=scene_id, section_id=section_id)
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
    selected = select_report_tools(runtime_target="agent_runtime_analysis", scene_id=scene_id, agent_name=agent_name)
    selected_names = [str(getattr(tool, "name", "") or "").strip() for tool in selected if str(getattr(tool, "name", "") or "").strip()]
    max_turns = 2 if str(agent_name or "").strip() == "evidence_analyst" else 1
    return {
        "allowed_tools": selected,
        "required_tools": selected_names[:1] if pair[1] == "evidence_analyst" else [],
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


def _build_interrupt_on(tools: List[Any]) -> Dict[str, Any]:
    mapping: Dict[str, Any] = {}
    for tool in tools:
        tool_name = str(getattr(tool, "name", "") or "").strip()
        if not tool_name:
            continue
        try:
            spec = get_report_tool_spec(tool_name)
        except Exception:
            continue
        if spec.mutability != READ_ONLY:
            mapping[tool_name] = True
    return mapping


def _agent_result_payload(result: Any) -> Any:
    return result if isinstance(result, dict) else getattr(result, "value", result)


def create_report_deep_agent(
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
    try:
        from deepagents import create_deep_agent
    except Exception:
        return None

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
    runtime_context = dict(context or {})
    runtime_context["tool_policy"] = policy
    topic = str(runtime_context.get("topic_label") or runtime_context.get("topic_identifier") or "").strip()
    runtime_system_prompt = _compose_runtime_system_prompt(
        base_prompt=system_prompt,
        context=runtime_context,
        policy=policy,
        include_plain_skill_catalog=False,
        topic=topic,
    )
    skill_assets = build_report_skill_runtime_assets(topic)
    skill_sources = select_report_skill_sources(
        skill_assets,
        available_tool_ids=[tool.name for tool in allowed_tools if str(getattr(tool, "name", "") or "").strip()],
        runtime_target="agent_runtime",
    )
    middleware = _build_runtime_middleware(
        policy=policy,
    )
    thread_id = _build_thread_id(context, name)
    checkpointer, runtime_profile = get_shared_report_checkpointer(purpose=f"agent-runtime:{name}")

    agent = create_deep_agent(
        model=llm,
        tools=allowed_tools,
        system_prompt=runtime_system_prompt,
        middleware=middleware,
        skills=skill_sources or None,
        context_schema=ReportAgentContext,
        checkpointer=checkpointer,
        backend=build_state_backend(),
        interrupt_on=_build_interrupt_on(list(allowed_tools)),
        name=name,
        debug=False,
    )
    seed_state = {"files": skill_assets.get("files") or {}} if skill_assets.get("files") else {}
    diagnostics = build_runtime_diagnostics(
        purpose=f"agent-runtime:{name}",
        thread_id=thread_id,
        locator_hint=runtime_profile.checkpoint_locator,
    )
    diagnostics["agent_harness"] = "deepagents"
    return {
        "agent": agent,
        "client_cfg": client_cfg,
        "context": runtime_context,
        "policy": policy,
        "thread_id": thread_id,
        "runtime": "deepagents",
        "seed_state": seed_state,
        "skill_sources": skill_sources,
        "skill_catalog": skill_assets.get("catalog") or [],
        "runtime_diagnostics": diagnostics,
    }


def _create_plain_report_agent_runner(
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
    runtime_context = dict(context or {})
    runtime_context["tool_policy"] = policy
    topic = str(runtime_context.get("topic_label") or runtime_context.get("topic_identifier") or "").strip()
    runtime_system_prompt = _compose_runtime_system_prompt(
        base_prompt=system_prompt,
        context=runtime_context,
        policy=policy,
        include_plain_skill_catalog=True,
        topic=topic,
    )
    middleware = _build_runtime_middleware(
        policy=policy,
    )
    compatibility_tools = [_build_plain_load_skill_tool(topic)]
    thread_id = _build_thread_id(context, name)
    checkpointer, runtime_profile = get_shared_report_checkpointer(purpose=f"agent-runtime:{name}:plain")
    agent = create_agent(
        model=llm,
        system_prompt=runtime_system_prompt,
        tools=[*allowed_tools, *compatibility_tools],
        middleware=middleware,
        checkpointer=checkpointer,
        context_schema=ReportAgentContext,
        name=name,
        debug=False,
    )
    return {
        "agent": agent,
        "client_cfg": client_cfg,
        "context": runtime_context,
        "policy": policy,
        "thread_id": thread_id,
        "runtime": "plain",
        "runtime_diagnostics": build_runtime_diagnostics(
            purpose=f"agent-runtime:{name}:plain",
            thread_id=thread_id,
            locator_hint=runtime_profile.checkpoint_locator,
        ),
    }


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
    force_plain: bool = False,
) -> Optional[Dict[str, Any]]:
    """Create a report agent runner.

    By default always returns a Deep Agents runner.  Pass ``force_plain=True``
    only for explicit debug/test purposes — plain runtime is not a regular
    production path.
    """
    if not force_plain:
        runner = create_report_deep_agent(
            policy,
            context,
            task=task,
            model_role=model_role,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
            name=name,
        )
        # Do NOT silently fall back to plain when deepagents fails — return
        # None so callers can detect the failure explicitly.
        return runner
    return _create_plain_report_agent_runner(
        policy,
        context,
        task=task,
        model_role=model_role,
        system_prompt=system_prompt,
        max_tokens=max_tokens,
        temperature=temperature,
        name=name,
    )


def _extract_agent_trace(messages: List[Any], policy: ToolPolicy, runtime: str) -> ExplorationTrace:
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
        "runtime": runtime,
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
    payload = {
        **(agent_runner.get("seed_state") if isinstance(agent_runner.get("seed_state"), dict) else {}),
        "messages": [{"role": "user", "content": user_prompt}],
    }
    thread_id = str(agent_runner.get("thread_id") or "report_agent").strip()
    runtime_name = str(agent_runner.get("runtime") or "plain").strip() or "plain"
    runtime_diagnostics = agent_runner.get("runtime_diagnostics") if isinstance(agent_runner.get("runtime_diagnostics"), dict) else {}
    result = agent.invoke(
        payload,
        config=build_report_runnable_config(
            thread_id=thread_id,
            purpose=f"agent-step:{runtime_name}",
            tags=[runtime_name, str(agent_runner.get("context", {}).get("scene_id") or "").strip()],
            metadata={"runtime_diagnostics": runtime_diagnostics},
            locator_hint=str(runtime_diagnostics.get("checkpoint_locator") or "").strip(),
        ),
        context=agent_runner.get("context") or {},
        version="v2",
    )
    result_payload = _agent_result_payload(result)
    messages = result_payload.get("messages") if isinstance(result_payload, dict) and isinstance(result_payload.get("messages"), list) else []
    final_content = ""
    for message in reversed(messages):
        if isinstance(message, AIMessage) and not (message.tool_calls or []):
            final_content = str(message.content or "").strip()
            break
    trace = _extract_agent_trace(messages, agent_runner.get("policy") or {}, str(agent_runner.get("runtime") or "plain"))
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
            "trace": {"tool_calls": [], "tool_results": [], "stop_reason": "runner_unavailable", "tool_call_count": 0, "exploration_turns": 0, "runtime": "none"},
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
    payload["policy"] = snapshot_tool_policy(tool_policy)
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
        return {"markdown": "", "trace": {"tool_calls": [], "tool_results": [], "stop_reason": "runner_unavailable", "tool_call_count": 0, "exploration_turns": 0, "runtime": "none"}}
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
        "policy": snapshot_tool_policy(writer_policy),
        "_agent_runner": runner,
    }
