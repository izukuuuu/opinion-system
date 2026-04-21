# -*- coding: utf-8 -*-
"""
deep_report/exploration_deterministic_graph.py
===============================================

确定性子代理调度图：将子代理委派从 LLM-driven coordinator 改为确定性 LangGraph 流程。
"""
from __future__ import annotations

import fnmatch
import json
from dataclasses import dataclass
from typing import Annotated, Any, Callable, Dict, List, Optional, Tuple, TypedDict

from deepagents import create_deep_agent
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from ..runtime_infra import build_report_runnable_config, get_shared_report_checkpointer
from .assets import RUNTIME_STORE
from .builder import ReportCoordinatorContext, _build_subagent_specs
from .deterministic import build_runtime_workspace_layout
from .subagent_registry import (
    build_tier_todo_specs,
    get_subagent_metadata_by_name,
    get_subagent_node_name,
    get_tier_groups,
)

_TIER_PHASES: Dict[int, str] = {
    0: "interpret",
    1: "interpret",
    2: "interpret",
    3: "interpret",
    4: "interpret",
    5: "interpret",
    6: "write",
}

_TIER_NODE_AGENTS: Dict[int, List[Tuple[str, str]]] = {
    tier: [(get_subagent_node_name(agent_name), agent_name) for agent_name in agent_names]
    for tier, agent_names in get_tier_groups().items()
    if 1 <= int(tier) <= 4
}

_TIER_TODO_SPECS: Dict[int, Dict[str, Any]] = build_tier_todo_specs()


def _merge_files(existing: Dict[str, Any], update: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if update is None:
        return existing or {}
    merged = dict(existing or {})
    merged.update(update)
    return merged


def _merge_dicts(existing: Optional[Dict[str, Any]], update: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    merged = dict(existing or {})
    merged.update(update or {})
    return merged


def _merge_unique_strings(existing: Optional[List[str]], update: Optional[List[str]]) -> List[str]:
    output: List[str] = []
    for item in [*(existing or []), *(update or [])]:
        value = str(item or "").strip()
        if value and value not in output:
            output.append(value)
    return output


def _dedupe_gaps(existing: Optional[List[Dict[str, Any]]], update: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    output: List[Dict[str, Any]] = []
    seen: set[Tuple[str, str, str, int]] = set()
    for item in [*(existing or []), *(update or [])]:
        if not isinstance(item, dict):
            continue
        normalized = {
            "agent": str(item.get("agent") or "").strip(),
            "file": str(item.get("file") or "").strip(),
            "reason": str(item.get("reason") or "").strip(),
            "tier": int(item.get("tier") or 0),
        }
        key = (
            normalized["agent"],
            normalized["file"],
            normalized["reason"],
            normalized["tier"],
        )
        if key in seen:
            continue
        seen.add(key)
        output.append(normalized)
    return output


class ExplorationDeterministicState(TypedDict, total=False):
    files: Annotated[Dict[str, Dict[str, Any]], _merge_files]
    task_id: str
    thread_id: str
    topic_identifier: str
    project_identifier: str
    topic_label: str
    start: str
    end: str
    mode: str
    status: str
    message: str
    gaps: Annotated[List[Dict[str, Any]], _dedupe_gaps]
    structured_payload: Dict[str, Any]
    current_agent: str
    agent_attempts: Annotated[Dict[str, int], _merge_dicts]
    agent_statuses: Annotated[Dict[str, str], _merge_dicts]
    agent_messages: Annotated[Dict[str, str], _merge_dicts]
    agent_results: Annotated[Dict[str, Dict[str, Any]], _merge_dicts]
    tier_results: Annotated[Dict[str, Dict[str, Any]], _merge_dicts]
    section_draft_paths: Annotated[List[str], _merge_unique_strings]
    reuse_plan: Annotated[Dict[str, Any], _merge_dicts]
    execution_plan: Annotated[Dict[str, Any], _merge_dicts]
    reused_artifacts: Annotated[Dict[str, Any], _merge_dicts]
    supplement_candidates: Annotated[Dict[str, Any], _merge_dicts]
    skipped_agents: Annotated[Dict[str, Any], _merge_dicts]
    repair_context: Annotated[Dict[str, Any], _merge_dicts]


@dataclass(frozen=True)
class _ExplorationRuntimeDeps:
    skill_assets: Dict[str, Any]
    middleware_factory: Callable[[str], List[Any]]
    event_callback: Callable[[Dict[str, Any]], None] | None
    llm: Any
    runtime_backend: Any = None
    common_context: Dict[str, Any] | None = None
    subagent_specs: Dict[str, Dict[str, Any]] | None = None
    lifecycle_tracker: Dict[str, Any] | None = None


def _path_tokens(common_context: Dict[str, Any] | None) -> Dict[str, str]:
    context = common_context if isinstance(common_context, dict) else {}
    configured = context.get("workspace_path_tokens") if isinstance(context.get("workspace_path_tokens"), dict) else {}
    if configured:
        return {str(key): str(value) for key, value in configured.items()}
    layout = build_runtime_workspace_layout(
        project_identifier=str(context.get("project_identifier") or "").strip(),
        topic_identifier=str(context.get("topic_identifier") or "").strip(),
        start=str(context.get("start") or "").strip(),
        end=str(context.get("end") or "").strip(),
    )
    return {
        "project_identifier": layout.project_component,
        "report_range": layout.range_component,
        "workspace_root": layout.workspace_root,
        "state_root": layout.state_root,
    }


def _state_path(relative_path: str, common_context: Dict[str, Any] | None) -> str:
    tokens = _path_tokens(common_context)
    return f"{tokens['state_root']}/{str(relative_path or '').strip().lstrip('/')}"


def _emit_event(event_callback: Callable[[Dict[str, Any]], None] | None, event: Dict[str, Any]) -> None:
    if callable(event_callback):
        event_callback(event)


def _tier_status_from_result(result: Dict[str, Any]) -> str:
    normalized = str(result.get("status") or "").strip()
    if normalized == "failed":
        return "failed"
    if normalized in {"completed", "partial"}:
        return "completed"
    return "pending"


def _base_tier_todos() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for tier in sorted(_TIER_TODO_SPECS.keys()):
        spec = _TIER_TODO_SPECS[tier]
        rows.append(
            {
                "id": spec["id"],
                "label": spec["label"],
                "status": "pending",
                "detail": spec["detail"],
                "agents": list(spec["agents"]),
                "tier": tier,
            }
        )
    return rows


def _build_tier_todos(
    state: Optional[ExplorationDeterministicState] = None,
    *,
    tier_overrides: Optional[Dict[int, Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    output = _base_tier_todos()
    tier_results = state.get("tier_results") if isinstance(state, dict) and isinstance(state.get("tier_results"), dict) else {}
    for row in output:
        tier = int(row["tier"])
        result = tier_results.get(f"tier_{tier}") if isinstance(tier_results, dict) else None
        if isinstance(result, dict):
            row["status"] = _tier_status_from_result(result)
            detail = str(result.get("detail") or "").strip()
            if detail:
                row["detail"] = detail
            agents = result.get("agents")
            if isinstance(agents, list) and agents:
                row["agents"] = [str(item).strip() for item in agents if str(item or "").strip()]
    for tier, patch in (tier_overrides or {}).items():
        for row in output:
            if int(row["tier"]) != int(tier):
                continue
            row.update({key: value for key, value in dict(patch or {}).items() if key != "tier"})
            break
    return output


def _emit_todo_update(
    event_callback: Callable[[Dict[str, Any]], None] | None,
    *,
    state: Optional[ExplorationDeterministicState],
    phase: str,
    title: str,
    message: str,
    tier_overrides: Optional[Dict[int, Dict[str, Any]]] = None,
    agent: str = "exploration_subgraph",
) -> None:
    todos = _build_tier_todos(state, tier_overrides=tier_overrides)
    _emit_event(
        event_callback,
        {
            "type": "todo.updated",
            "phase": phase,
            "agent": agent,
            "title": title,
            "message": message,
            "payload": {"todos": todos},
        },
    )


def _merge_stream_update(existing: Dict[str, Any], update: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(existing or {})
    for key, value in dict(update or {}).items():
        if key == "files":
            merged[key] = _merge_files(merged.get(key) if isinstance(merged.get(key), dict) else {}, value if isinstance(value, dict) else {})
        elif key == "gaps":
            merged[key] = _dedupe_gaps(merged.get(key) if isinstance(merged.get(key), list) else [], value if isinstance(value, list) else [])
        elif key in {"agent_attempts", "agent_statuses", "agent_messages", "agent_results", "tier_results", "reused_artifacts", "supplement_candidates", "skipped_agents"}:
            merged[key] = _merge_dicts(merged.get(key) if isinstance(merged.get(key), dict) else {}, value if isinstance(value, dict) else {})
        elif key in {"section_draft_paths"}:
            merged[key] = _merge_unique_strings(merged.get(key) if isinstance(merged.get(key), list) else [], value if isinstance(value, list) else [])
        else:
            merged[key] = value
    return merged


def _read_runtime_file(files: Dict[str, Dict[str, Any]], path: str) -> str:
    payload = files.get(str(path or "").strip())
    if not isinstance(payload, dict):
        return ""
    content = payload.get("content")
    if isinstance(content, list):
        return "\n".join(str(line) for line in content)
    return str(content or "")


def _read_runtime_json_file(files: Dict[str, Dict[str, Any]], path: str) -> Dict[str, Any]:
    raw = _read_runtime_file(files, path).strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except Exception:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _state_path_from_state(relative_path: str, state: ExplorationDeterministicState) -> str:
    return _state_path(
        relative_path,
        {
            "project_identifier": str(state.get("project_identifier") or "").strip(),
            "topic_identifier": str(state.get("topic_identifier") or "").strip(),
            "start": str(state.get("start") or "").strip(),
            "end": str(state.get("end") or "").strip(),
        },
    )


def _execution_plan_nodes(state: ExplorationDeterministicState) -> Dict[str, Dict[str, Any]]:
    plan = state.get("execution_plan") if isinstance(state.get("execution_plan"), dict) else {}
    nodes = plan.get("nodes") if isinstance(plan.get("nodes"), dict) else {}
    return nodes if isinstance(nodes, dict) else {}


def _plan_for_agent(state: ExplorationDeterministicState, agent_name: str) -> Dict[str, Any]:
    node = _execution_plan_nodes(state).get(agent_name)
    return dict(node) if isinstance(node, dict) else {}


def _is_skipped_by_reuse(state: ExplorationDeterministicState, agent_name: str) -> bool:
    return bool(_plan_for_agent(state, agent_name).get("skip"))


def _skip_payload_for_agent(state: ExplorationDeterministicState, agent_name: str, tier: int) -> Dict[str, Any]:
    plan = _plan_for_agent(state, agent_name)
    artifact_keys = [str(item).strip() for item in (plan.get("artifact_keys") or []) if str(item or "").strip()]
    source_ranges = [str(item).strip() for item in (plan.get("source_report_ranges") or []) if str(item or "").strip()]
    message = "已复用历史产物，当前节点跳过执行。"
    if artifact_keys:
        message = f"已复用历史产物：{', '.join(artifact_keys)}。"
    return {
        "status": "skipped",
        "attempts": 0,
        "message": message,
        "gaps": [],
        "reason": "reused_from_history",
        "artifact_keys": artifact_keys,
        "source_report_ranges": source_ranges,
        "tier": tier,
    }


def _result_payload(result: Any) -> Dict[str, Any]:
    if isinstance(result, dict):
        return result
    value = getattr(result, "value", None)
    return value if isinstance(value, dict) else {}


def _result_summary(result: Any) -> str:
    def _flatten_content(value: Any) -> str:
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, list):
            parts: List[str] = []
            for item in value:
                if isinstance(item, dict):
                    text = str(item.get("text") or item.get("thinking") or "").strip()
                    if text:
                        parts.append(text)
                else:
                    text = str(getattr(item, "text", "") or getattr(item, "content", "") or "").strip()
                    if text:
                        parts.append(text)
            return "\n".join(part for part in parts if part).strip()
        if isinstance(value, dict):
            return str(value.get("text") or value.get("thinking") or value.get("content") or "").strip()
        return str(value or "").strip()

    payload = _result_payload(result)
    message = str(payload.get("message") or "").strip()
    if message:
        return message
    messages = payload.get("messages") if isinstance(payload.get("messages"), list) else []
    for item in reversed(messages):
        if isinstance(item, dict):
            content = _flatten_content(item.get("content"))
        else:
            content = _flatten_content(getattr(item, "content", ""))
        if content:
            return content[:240]
    return ""


def _required_paths_for_agent(agent_name: str, tier: int, common_context: Dict[str, Any] | None) -> List[str]:
    metadata = get_subagent_metadata_by_name(agent_name)
    return [
        str(item).format(**_path_tokens(common_context))
        for item in (metadata.get("output_files") or [])
        if str(item or "").strip()
    ]


def _output_globs_for_agent(agent_name: str, common_context: Dict[str, Any] | None) -> List[str]:
    metadata = get_subagent_metadata_by_name(agent_name)
    return [
        str(item).format(**_path_tokens(common_context))
        for item in (metadata.get("output_globs") or [])
        if str(item or "").strip()
    ]


def _output_state(content: Dict[str, Any]) -> str:
    if not isinstance(content, dict):
        return "missing"
    status = str(content.get("status") or "").strip().lower()
    skipped_due_to = content.get("skipped_due_to") if isinstance(content.get("skipped_due_to"), list) else []
    coverage = content.get("coverage") if isinstance(content.get("coverage"), dict) else {}
    readiness_flags = coverage.get("readiness_flags") if isinstance(coverage.get("readiness_flags"), list) else []
    if status == "error":
        return "error"
    if status == "empty" or skipped_due_to:
        return "empty"
    if any(str(item or "").strip() in {"no_cards", "no_records_in_scope", "upstream_empty"} for item in readiness_flags):
        return "empty"
    return "ready"


def _is_provider_throttling_error(message: str) -> bool:
    text = str(message or "").strip().lower()
    if not text:
        return False
    markers = [
        "error code: 429",
        "week allocated quota exceeded",
        "throttling",
        "rate limit",
        "ratelimit",
        "quota exceeded",
    ]
    return any(marker in text for marker in markers)


def _check_required_files(
    files: Dict[str, Dict[str, Any]],
    *,
    agent_name: str,
    tier: int,
    required_paths: List[str],
) -> List[Dict[str, Any]]:
    from .service import _runtime_file_content

    gaps: List[Dict[str, Any]] = []
    for path in required_paths:
        raw = _runtime_file_content(files, path).strip()
        if not raw:
            gaps.append({"agent": agent_name, "file": path, "reason": "missing", "tier": tier})
            continue
        try:
            parsed = json.loads(raw)
        except Exception:
            gaps.append({"agent": agent_name, "file": path, "reason": "invalid_json", "tier": tier})
            continue
        if isinstance(parsed, dict):
            semantic_state = _output_state(parsed)
            if semantic_state == "error":
                gaps.append({"agent": agent_name, "file": path, "reason": "error", "tier": tier})
            elif semantic_state == "empty":
                gaps.append({"agent": agent_name, "file": path, "reason": "empty", "tier": tier})
    return gaps


def _validate_output_globs(
    files: Dict[str, Dict[str, Any]],
    *,
    agent_name: str,
    tier: int,
    output_globs: List[str],
) -> Tuple[List[str], List[Dict[str, Any]]]:
    matched_paths: List[str] = []
    gaps: List[Dict[str, Any]] = []
    for pattern in output_globs:
        current = sorted(path for path in files.keys() if fnmatch.fnmatch(str(path or "").strip(), pattern))
        if not current:
            gaps.append({"agent": agent_name, "file": pattern, "reason": "missing", "tier": tier})
            continue
        for path in current:
            raw = _read_runtime_file(files, path).strip()
            if not raw:
                gaps.append({"agent": agent_name, "file": path, "reason": "empty", "tier": tier})
                continue
            try:
                parsed = json.loads(raw)
            except Exception:
                gaps.append({"agent": agent_name, "file": path, "reason": "invalid_json", "tier": tier})
                continue
            if not isinstance(parsed, dict):
                gaps.append({"agent": agent_name, "file": path, "reason": "invalid_shape", "tier": tier})
                continue
            matched_paths.append(path)
    return matched_paths, gaps


def _subagent_prompt(
    agent_name: str,
    state: ExplorationDeterministicState,
    runtime_deps: _ExplorationRuntimeDeps,
    *,
    tier: int,
) -> str:
    required_paths = _required_paths_for_agent(agent_name, tier, runtime_deps.common_context)
    output_globs = _output_globs_for_agent(agent_name, runtime_deps.common_context)
    lines = [
        f"当前专题：{str(state.get('topic_label') or state.get('topic_identifier') or '').strip()}",
        f"时间范围：{str(state.get('start') or '').strip()} 至 {str(state.get('end') or '').strip()}",
        f"当前子代理：{agent_name}",
        "请在一次运行内完成你的职责，自主读取 /workspace 中所需输入文件，并把结果写回工作区。",
    ]
    if required_paths:
        lines.append("必须产出的固定文件：")
        lines.extend(f"- {path}" for path in required_paths)
    if output_globs:
        lines.append("必须命中的输出模式：")
        lines.extend(f"- {pattern}" for pattern in output_globs)
    node_plan = _plan_for_agent(state, agent_name)
    if bool(node_plan.get("supplement")):
        lines.append("本轮要求补跑并参考历史候选，不允许直接复用旧结果。")
        for artifact_key, artifact_payload in (state.get("supplement_candidates") or {}).items():
            if not isinstance(artifact_payload, dict):
                continue
            if str((artifact_payload.get("target_agent") or "")).strip() != agent_name:
                continue
            source_range = str(artifact_payload.get("source_report_range") or "").strip()
            runtime_path = str(artifact_payload.get("runtime_path") or "").strip()
            lines.append(
                f"- supplement artifact={artifact_key} source_report_range={source_range or 'unknown'} runtime_path={runtime_path or 'unknown'}"
            )
    repair_context = state.get("repair_context") if isinstance(state.get("repair_context"), dict) else {}
    if repair_context and str(repair_context.get("target_agent") or "").strip() == agent_name:
        lines.append("本次调用是 compile 前的受限补救重跑，只允许补齐指定产物。")
        lines.append(
            f"- target_artifact={str(repair_context.get('target_artifact') or '').strip() or 'unknown'}"
        )
        lines.append(
            f"- reason={str(repair_context.get('reason') or '').strip() or 'artifact_not_ready'}"
        )
        expected_paths = [
            str(item).strip()
            for item in (repair_context.get("expected_output_paths") or [])
            if str(item or "").strip()
        ]
        if expected_paths:
            lines.append("- expected_output_paths:")
            lines.extend(f"  - {path}" for path in expected_paths)
        upstream_paths = [
            str(item).strip()
            for item in (repair_context.get("ready_input_paths") or [])
            if str(item or "").strip()
        ]
        if upstream_paths:
            lines.append("- ready_inputs:")
            lines.extend(f"  - {path}" for path in upstream_paths)
        lines.append("禁止扩写任务范围、禁止顺手重跑其他代理、禁止写非 canonical workspace 路径。")
    lines.extend(
        [
            "如果上游为空或工具明确返回 empty/skipped_due_to，可输出合法降级结果，但不要省略目标文件。",
            "完成后只返回简短总结，不要再要求人工确认。",
        ]
    )
    return "\n".join(lines)


def _build_subagent_spec_map(
    *,
    skill_assets: Dict[str, Any],
    middleware_factory: Callable[[str], List[Any]],
) -> Dict[str, Dict[str, Any]]:
    specs = _build_subagent_specs(
        skill_assets=skill_assets,
        middleware_factory=middleware_factory,
    )
    output: Dict[str, Dict[str, Any]] = {}
    for spec in specs:
        if not isinstance(spec, dict):
            continue
        name = str(spec.get("name") or "").strip()
        if name:
            output[name] = dict(spec)
    return output


def _invoke_subagent_once(
    agent_name: str,
    state: ExplorationDeterministicState,
    runtime_deps: _ExplorationRuntimeDeps,
    *,
    tier: int,
) -> Dict[str, Any]:
    from .service import _runtime_thread_id, _seed_invoke_payload

    spec = dict((runtime_deps.subagent_specs or {}).get(agent_name) or {})
    if not spec:
        raise ValueError(f"Unknown deterministic exploration subagent: {agent_name}")
    if isinstance(runtime_deps.lifecycle_tracker, dict):
        runtime_deps.lifecycle_tracker["runtime_files"] = (
            state.get("files") if isinstance(state.get("files"), dict) else {}
        )

    purpose = f"deep-report-subagent-{agent_name}"
    checkpointer, runtime_profile = get_shared_report_checkpointer(purpose=purpose)
    agent = create_deep_agent(
        model=runtime_deps.llm,
        tools=spec.get("tools") or [],
        system_prompt=str(spec.get("system_prompt") or "").strip(),
        middleware=list(runtime_deps.middleware_factory(agent_name) or []),
        skills=spec.get("skills") or None,
        context_schema=ReportCoordinatorContext,
        checkpointer=checkpointer,
        store=RUNTIME_STORE,
        backend=runtime_deps.runtime_backend,
        debug=False,
        name=f"deep-report-{agent_name}",
    )
    thread_id = _runtime_thread_id(task_id=str(state.get("task_id") or "").strip(), role=agent_name)
    result = agent.invoke(
        _seed_invoke_payload(
            state.get("files") if isinstance(state.get("files"), dict) else {},
            _subagent_prompt(agent_name, state, runtime_deps, tier=tier),
        ),
        config=build_report_runnable_config(
            thread_id=thread_id,
            purpose=purpose,
            task_id=str(state.get("task_id") or "").strip(),
            tags=["deterministic", "exploration", agent_name],
            metadata={
                "topic_identifier": str(state.get("topic_identifier") or "").strip(),
                "subagent": agent_name,
            },
            locator_hint=runtime_profile.checkpoint_locator,
        ),
        context=runtime_deps.common_context or {},
        version="v2",
    )
    payload = _result_payload(result)
    updated_files = payload.get("files") if isinstance(payload.get("files"), dict) else {}
    tracker_files = {}
    if isinstance(runtime_deps.lifecycle_tracker, dict):
        tracker_candidate = runtime_deps.lifecycle_tracker.get("runtime_files")
        if isinstance(tracker_candidate, dict):
            tracker_files = tracker_candidate
    return {
        "payload": payload,
        "files": _merge_files(
            _merge_files(state.get("files") if isinstance(state.get("files"), dict) else {}, tracker_files),
            updated_files,
        ),
        "message": _result_summary(result),
    }


def _run_subagent_node(
    state: ExplorationDeterministicState,
    runtime_deps: _ExplorationRuntimeDeps,
    *,
    agent_name: str,
    tier: int,
    phase: str,
) -> Dict[str, Any]:
    required_paths = _required_paths_for_agent(agent_name, tier, runtime_deps.common_context)
    output_globs = _output_globs_for_agent(agent_name, runtime_deps.common_context)
    if _is_skipped_by_reuse(state, agent_name):
        skip_payload = _skip_payload_for_agent(state, agent_name, tier)
        _emit_event(
            runtime_deps.event_callback,
            {
                "type": "graph.node.skipped",
                "phase": phase,
                "agent": agent_name,
                "title": f"{agent_name} 已复用跳过",
                "message": skip_payload["message"],
                "payload": {
                    "reason": "reused_from_history",
                    "artifact_keys": skip_payload["artifact_keys"],
                    "source_report_ranges": skip_payload["source_report_ranges"],
                },
            },
        )
        if tier in {0, 5, 6}:
            _emit_todo_update(
                runtime_deps.event_callback,
                state=state,
                phase=phase,
                title=f"{_TIER_TODO_SPECS[tier]['label']} 已复用",
                message=skip_payload["message"],
                tier_overrides={
                    tier: {
                        "status": "completed",
                        "detail": "已复用历史产物。",
                        "agents": [agent_name],
                    }
                },
                agent=agent_name,
            )
        return {
            "gaps": [],
            "agent_attempts": {agent_name: 0},
            "agent_statuses": {agent_name: "skipped"},
            "agent_messages": {agent_name: str(skip_payload["message"])},
            "agent_results": {agent_name: skip_payload},
            "skipped_agents": {
                agent_name: {
                    "reason": "reused_from_history",
                    "artifact_keys": skip_payload["artifact_keys"],
                    "source_report_ranges": skip_payload["source_report_ranges"],
                }
            },
            "tier_results": {
                f"tier_{tier}": {
                    "tier": tier,
                    "agents": [agent_name],
                    "status": "completed",
                    "detail": "已复用历史产物。",
                    "gaps": [],
                    "failed_agents": [],
                    "skipped_agents": [agent_name],
                }
            } if tier in {0, 5, 6} else {},
        }
    if tier in {0, 5, 6}:
        _emit_todo_update(
            runtime_deps.event_callback,
            state=state,
            phase=phase,
            title=f"{_TIER_TODO_SPECS[tier]['label']} 已启动",
            message=f"{_TIER_TODO_SPECS[tier]['label']} 正在执行。",
            tier_overrides={
                tier: {
                    "status": "running",
                    "detail": f"{_TIER_TODO_SPECS[tier]['label']} 正在执行。",
                }
            },
            agent=agent_name,
        )
    _emit_event(
        runtime_deps.event_callback,
        {
            "type": "graph.node.started",
            "phase": phase,
            "agent": agent_name,
            "title": f"{agent_name} 已启动",
            "message": f"{agent_name} 正在执行。",
        },
    )

    latest_files = state.get("files") if isinstance(state.get("files"), dict) else {}
    latest_message = ""
    latest_gaps: List[Dict[str, Any]] = []
    section_paths: List[str] = []

    for attempt in range(1, 3):
        if attempt > 1:
            _emit_event(
                runtime_deps.event_callback,
                {
                    "type": "agent.memo",
                    "phase": phase,
                    "agent": agent_name,
                    "title": f"{agent_name} 重试",
                    "message": f"{agent_name} 正在进行第 {attempt} 次尝试。",
                    "payload": {"attempt": attempt},
                },
            )
        try:
            result = _invoke_subagent_once(agent_name, {**state, "files": latest_files}, runtime_deps, tier=tier)
            latest_files = result.get("files") if isinstance(result.get("files"), dict) else latest_files
            latest_message = str(result.get("message") or "").strip()
        except Exception as exc:
            latest_message = str(exc or "子代理执行失败。").strip() or "子代理执行失败。"
            latest_gaps = [{"agent": agent_name, "file": "__runtime__", "reason": "exception", "tier": tier}]
            if attempt < 2 and not _is_provider_throttling_error(latest_message):
                continue
            _emit_event(
                runtime_deps.event_callback,
                {
                    "type": "graph.node.failed",
                    "phase": phase,
                    "agent": agent_name,
                    "title": f"{agent_name} 失败",
                    "message": latest_message,
                    "payload": {"failed_node": agent_name, "attempts": attempt},
                },
            )
            if tier in {0, 5, 6}:
                _emit_todo_update(
                    runtime_deps.event_callback,
                    state=state,
                    phase=phase,
                    title=f"{_TIER_TODO_SPECS[tier]['label']} 失败",
                    message=latest_message,
                    tier_overrides={
                        tier: {
                            "status": "failed",
                            "detail": latest_message,
                            "agents": [agent_name],
                        }
                    },
                    agent=agent_name,
                )
            return {
                "files": latest_files,
                "gaps": latest_gaps,
                "agent_attempts": {agent_name: attempt},
                "agent_statuses": {agent_name: "failed"},
                "agent_messages": {agent_name: latest_message},
                "agent_results": {
                    agent_name: {
                        "status": "failed",
                        "attempts": attempt,
                        "message": latest_message,
                        "gaps": latest_gaps,
                    }
                },
                "tier_results": {
                    f"tier_{tier}": {
                        "tier": tier,
                        "agents": [agent_name],
                        "status": "failed",
                        "detail": latest_message,
                        "gaps": latest_gaps,
                        "failed_agents": [agent_name],
                    }
                } if tier in {0, 5, 6} else {},
            }

        latest_gaps = _check_required_files(
            latest_files,
            agent_name=agent_name,
            tier=tier,
            required_paths=required_paths,
        )
        if output_globs:
            section_paths, glob_gaps = _validate_output_globs(
                latest_files,
                agent_name=agent_name,
                tier=tier,
                output_globs=output_globs,
            )
            latest_gaps = _dedupe_gaps(latest_gaps, glob_gaps)
        if not latest_gaps:
            _emit_event(
                runtime_deps.event_callback,
                {
                    "type": "graph.node.completed",
                    "phase": phase,
                    "agent": agent_name,
                    "title": f"{agent_name} 已完成",
                    "message": latest_message or f"{agent_name} 已完成。",
                    "payload": {"attempts": attempt},
                },
            )
            if tier in {0, 5, 6}:
                _emit_todo_update(
                    runtime_deps.event_callback,
                    state=state,
                    phase=phase,
                    title=f"{_TIER_TODO_SPECS[tier]['label']} 已完成",
                    message=latest_message or f"{agent_name} 已完成。",
                    tier_overrides={
                        tier: {
                            "status": "completed",
                            "detail": latest_message or f"{agent_name} 已完成。",
                            "agents": [agent_name],
                        }
                    },
                    agent=agent_name,
                )
            return {
                "files": latest_files,
                "gaps": [],
                "section_draft_paths": section_paths,
                "agent_attempts": {agent_name: attempt},
                "agent_statuses": {agent_name: "completed"},
                "agent_messages": {agent_name: latest_message or f"{agent_name} 已完成。"},
                "agent_results": {
                    agent_name: {
                        "status": "completed",
                        "attempts": attempt,
                        "message": latest_message or f"{agent_name} 已完成。",
                        "gaps": [],
                        "section_draft_paths": section_paths,
                    }
                },
                "tier_results": {
                    f"tier_{tier}": {
                        "tier": tier,
                        "agents": [agent_name],
                        "status": "completed",
                        "detail": latest_message or f"{agent_name} 已完成。",
                        "gaps": [],
                        "failed_agents": [],
                    }
                } if tier in {0, 5, 6} else {},
            }

    _emit_event(
        runtime_deps.event_callback,
        {
            "type": "graph.node.failed",
            "phase": phase,
            "agent": agent_name,
            "title": f"{agent_name} 失败",
            "message": latest_message or f"{agent_name} 缺少必需产物。",
            "payload": {"failed_node": agent_name, "gaps": latest_gaps},
        },
    )
    if tier in {0, 5, 6}:
        _emit_todo_update(
            runtime_deps.event_callback,
            state=state,
            phase=phase,
            title=f"{_TIER_TODO_SPECS[tier]['label']} 失败",
            message=latest_message or f"{agent_name} 缺少必需产物。",
            tier_overrides={
                tier: {
                    "status": "failed",
                    "detail": latest_message or f"{agent_name} 缺少必需产物。",
                    "agents": [agent_name],
                }
            },
            agent=agent_name,
        )
    return {
        "files": latest_files,
        "gaps": latest_gaps,
        "section_draft_paths": section_paths,
        "agent_attempts": {agent_name: 2},
        "agent_statuses": {agent_name: "failed"},
        "agent_messages": {agent_name: latest_message or f"{agent_name} 缺少必需产物。"},
        "agent_results": {
            agent_name: {
                "status": "failed",
                "attempts": 2,
                "message": latest_message or f"{agent_name} 缺少必需产物。",
                "gaps": latest_gaps,
                "section_draft_paths": section_paths,
            }
        },
        "tier_results": {
            f"tier_{tier}": {
                "tier": tier,
                "agents": [agent_name],
                "status": "failed",
                "detail": latest_message or f"{agent_name} 缺少必需产物。",
                "gaps": latest_gaps,
                "failed_agents": [agent_name],
            }
        } if tier in {0, 5, 6} else {},
    }


def _make_agent_node(
    runtime_deps: _ExplorationRuntimeDeps,
    *,
    agent_name: str,
    tier: int,
    phase: str,
) -> Callable[[ExplorationDeterministicState], Dict[str, Any]]:
    def _run(state: ExplorationDeterministicState) -> Dict[str, Any]:
        return _run_subagent_node(
            state,
            runtime_deps,
            agent_name=agent_name,
            tier=tier,
            phase=phase,
        )

    return _run


def _collect_tier_gaps(
    state: ExplorationDeterministicState,
    *,
    tier: int,
    agent_names: List[str],
    common_context: Dict[str, Any] | None,
) -> Tuple[List[Dict[str, Any]], List[str]]:
    files = state.get("files") if isinstance(state.get("files"), dict) else {}
    tier_gaps: List[Dict[str, Any]] = []
    tier_paths: List[str] = []
    for agent_name in agent_names:
        if _is_skipped_by_reuse(state, agent_name):
            continue
        tier_gaps = _dedupe_gaps(
            tier_gaps,
            _check_required_files(
                files,
                agent_name=agent_name,
                tier=tier,
                required_paths=_required_paths_for_agent(agent_name, tier, common_context),
            ),
        )
        output_globs = _output_globs_for_agent(agent_name, common_context)
        if output_globs:
            matched_paths, glob_gaps = _validate_output_globs(
                files,
                agent_name=agent_name,
                tier=tier,
                output_globs=output_globs,
            )
            tier_paths = _merge_unique_strings(tier_paths, matched_paths)
            tier_gaps = _dedupe_gaps(tier_gaps, glob_gaps)
    return tier_gaps, tier_paths


def _make_gather_node(
    runtime_deps: _ExplorationRuntimeDeps,
    *,
    tier: int,
    phase: str,
    agent_names: List[str],
) -> Callable[[ExplorationDeterministicState], Dict[str, Any]]:
    tier_key = f"tier_{tier}"

    def _run(state: ExplorationDeterministicState) -> Dict[str, Any]:
        tier_gaps, tier_paths = _collect_tier_gaps(
            state,
            tier=tier,
            agent_names=agent_names,
            common_context=runtime_deps.common_context,
        )
        failed_agents = [
            agent_name
            for agent_name in agent_names
            if str((state.get("agent_statuses") or {}).get(agent_name) or "").strip() == "failed"
        ]
        skipped_agents = [
            agent_name
            for agent_name in agent_names
            if str((state.get("agent_statuses") or {}).get(agent_name) or "").strip() == "skipped"
        ]
        message = f"Tier {tier} 完成。"
        if tier_gaps:
            message = f"Tier {tier} 完成，但仍有 {len(tier_gaps)} 项产物缺口。"
        elif failed_agents:
            message = f"Tier {tier} 已结束，{len(failed_agents)} 个子代理降级返回。"
        elif skipped_agents and len(skipped_agents) == len(agent_names):
            message = f"Tier {tier} 已复用历史产物。"
        todo_status = "failed" if failed_agents else "completed"
        todo_detail = "带缺口完成。" if tier_gaps and not failed_agents else message
        if failed_agents:
            todo_detail = f"有 {len(failed_agents)} 个子代理失败。"
        elif skipped_agents and len(skipped_agents) == len(agent_names):
            todo_detail = "已复用历史产物。"
        _emit_todo_update(
            runtime_deps.event_callback,
            state=state,
            phase=phase,
            title=f"{_TIER_TODO_SPECS[tier]['label']} 已完成",
            message=message,
            tier_overrides={
                tier: {
                    "status": todo_status,
                    "detail": todo_detail,
                    "agents": agent_names,
                }
            },
        )
        _emit_event(
            runtime_deps.event_callback,
            {
                "type": "phase.progress",
                "phase": phase,
                "title": f"Tier {tier} 完成",
                "message": message,
                "payload": {
                    "tier": tier,
                    "agents": agent_names,
                    "gaps": tier_gaps,
                    "failed_agents": failed_agents,
                    "skipped_agents": skipped_agents,
                },
            },
        )
        return {
            "gaps": tier_gaps,
            "section_draft_paths": tier_paths,
            "tier_results": {
                tier_key: {
                    "tier": tier,
                    "agents": agent_names,
                    "status": "partial" if tier_gaps or failed_agents else "completed",
                    "detail": todo_detail,
                    "gaps": tier_gaps,
                    "failed_agents": failed_agents,
                    "skipped_agents": skipped_agents,
                }
            },
        }

    return _run


def _make_tier_start_node(
    runtime_deps: _ExplorationRuntimeDeps,
    *,
    tier: int,
    phase: str,
) -> Callable[[ExplorationDeterministicState], Dict[str, Any]]:
    label = str(_TIER_TODO_SPECS[tier]["label"]).strip()

    def _run(state: ExplorationDeterministicState) -> Dict[str, Any]:
        _emit_todo_update(
            runtime_deps.event_callback,
            state=state,
            phase=phase,
            title=f"{label} 已启动",
            message=f"{label} 正在执行。",
            tier_overrides={
                tier: {
                    "status": "running",
                    "detail": f"{label} 正在执行。",
                }
            },
        )
        _emit_event(
            runtime_deps.event_callback,
            {
                "type": "phase.progress",
                "phase": phase,
                "title": f"Tier {tier} 启动",
                "message": f"{label} 正在执行。",
                "payload": {"tier": tier, "agents": list(_TIER_TODO_SPECS[tier]["agents"])},
            },
        )
        return {}

    return _run


def dispatch_tier1(state: ExplorationDeterministicState) -> List[Send]:
    return [Send(node_name, {}) for node_name, _agent_name in _TIER_NODE_AGENTS[1]]


def dispatch_tier2(state: ExplorationDeterministicState) -> List[Send]:
    return [Send(node_name, {}) for node_name, _agent_name in _TIER_NODE_AGENTS[2]]


def dispatch_tier3(state: ExplorationDeterministicState) -> List[Send]:
    return [Send(node_name, {}) for node_name, _agent_name in _TIER_NODE_AGENTS[3]]


def dispatch_tier4(state: ExplorationDeterministicState) -> List[Send]:
    return [Send(node_name, {}) for node_name, _agent_name in _TIER_NODE_AGENTS[4]]


def route_after_utility(state: ExplorationDeterministicState) -> str:
    utility = _read_runtime_json_file(
        state.get("files") if isinstance(state.get("files"), dict) else {},
        _state_path_from_state("utility_assessment.json", state),
    )
    decision = str(utility.get("decision") or "").strip()
    if not decision:
        nested = utility.get("result") if isinstance(utility.get("result"), dict) else {}
        decision = str(nested.get("decision") or "").strip()
    if decision in {"pass", "fallback_recompile"}:
        return "writer_node"
    return "finalize_node"


def finalize_node(
    state: ExplorationDeterministicState,
    runtime_deps: _ExplorationRuntimeDeps,
) -> Dict[str, Any]:
    from .service import (
        _build_structured_seed_payload,
        _finalize_structured_payload,
        _merge_structured_payload,
        _synthesize_structured_report_from_files,
        _upsert_runtime_json_file,
    )

    files = dict(state.get("files") or {}) if isinstance(state.get("files"), dict) else {}
    seed_payload = _build_structured_seed_payload(
        topic_identifier=str(state.get("topic_identifier") or "").strip(),
        topic_label=str(state.get("topic_label") or state.get("topic_identifier") or "").strip(),
        start_text=str(state.get("start") or "").strip(),
        end_text=str(state.get("end") or state.get("start") or "").strip(),
        mode=str(state.get("mode") or "fast").strip() or "fast",
        thread_id=str(state.get("thread_id") or "").strip(),
    )

    structured_report_path = _state_path_from_state("structured_report.json", state)
    preferred = _read_runtime_json_file(files, structured_report_path)
    synthesis_error = ""
    if not preferred:
        try:
            preferred = _synthesize_structured_report_from_files(
                files=files,
                topic_identifier=str(state.get("topic_identifier") or "").strip(),
                topic_label=str(state.get("topic_label") or state.get("topic_identifier") or "").strip(),
                start_text=str(state.get("start") or "").strip(),
                end_text=str(state.get("end") or state.get("start") or "").strip(),
                mode=str(state.get("mode") or "fast").strip() or "fast",
                thread_id=str(state.get("thread_id") or "").strip(),
            )
        except Exception as exc:
            synthesis_error = str(exc or "").strip()
            preferred = {}

    structured_payload = _finalize_structured_payload(
        _merge_structured_payload(seed_payload, preferred if isinstance(preferred, dict) else {})
    )
    _upsert_runtime_json_file(files, structured_report_path, structured_payload)

    gaps = state.get("gaps") if isinstance(state.get("gaps"), list) else []
    failed_agents = [
        agent_name
        for agent_name, status in (state.get("agent_statuses") or {}).items()
        if str(status or "").strip() == "failed"
    ] if isinstance(state.get("agent_statuses"), dict) else []
    partial = bool(gaps or failed_agents or synthesis_error)
    status = "partial" if partial else "completed"
    message = "确定性探索图已完成，并生成了结构化结果。"
    if partial:
        message = "确定性探索图已带缺口完成，并生成了可继续编译的结构化结果。"
    if synthesis_error:
        message = "探索图已生成兜底结构化结果，但自动综合阶段出现降级。"
    tier_six_detail = "结构化结果已准备好。"
    if state.get("tier_results") and isinstance((state.get("tier_results") or {}).get("tier_6"), dict):
        tier_six_detail = str(((state.get("tier_results") or {}).get("tier_6") or {}).get("detail") or tier_six_detail).strip() or tier_six_detail
    elif not _read_runtime_json_file(files, _state_path_from_state("utility_assessment.json", state)).get("decision"):
        tier_six_detail = "文稿节点未执行，已直接交付结构化结果。"
    todos = _build_tier_todos(
        state,
        tier_overrides={
            6: {
                "status": "failed" if status == "failed" else "completed",
                "detail": tier_six_detail if status == "completed" else message,
            }
        },
    )
    structured_payload.setdefault("metadata", {})
    structured_payload["metadata"]["todos"] = todos
    structured_payload["meta"] = {
        **(structured_payload.get("meta") if isinstance(structured_payload.get("meta"), dict) else {}),
        "todos": todos,
    }
    _emit_todo_update(
        runtime_deps.event_callback,
        state=state,
        phase="persist",
        title="探索阶段清单已更新",
        message=message,
        tier_overrides={
            6: {
                "status": "completed",
                "detail": tier_six_detail,
            }
        },
    )

    _emit_event(
        runtime_deps.event_callback,
        {
            "type": "phase.progress",
            "phase": "persist",
            "title": "探索阶段完成",
            "message": message,
            "payload": {
                "status": status,
                "gap_count": len(gaps),
                "failed_agents": failed_agents,
                "structured_ready": bool(structured_payload),
                "synthesis_error": synthesis_error,
            },
        },
    )

    return {
        "files": files,
        "status": status,
        "message": message,
        "structured_payload": structured_payload,
        "todos": todos,
        "tier_results": {
            "tier_6": {
                "tier": 6,
                "agents": ["writer"],
                "status": "partial" if partial else "completed",
                "detail": tier_six_detail,
                "gaps": gaps,
                "failed_agents": [agent for agent in failed_agents if agent == "writer"],
            },
            "finalize": {
                "status": status,
                "gap_count": len(gaps),
                "failed_agents": failed_agents,
                "structured_ready": bool(structured_payload),
                "synthesis_error": synthesis_error,
            }
        },
    }


def build_exploration_deterministic_graph(
    runtime_deps: Optional[_ExplorationRuntimeDeps] = None,
) -> StateGraph:
    deps = runtime_deps or _ExplorationRuntimeDeps(
        skill_assets={},
        middleware_factory=lambda _name: [],
        event_callback=None,
        llm=None,
        runtime_backend=None,
        common_context={},
        subagent_specs={},
    )

    builder = StateGraph(ExplorationDeterministicState)
    builder.add_node(get_subagent_node_name("retrieval_router"), _make_agent_node(deps, agent_name="retrieval_router", tier=0, phase=_TIER_PHASES[0]))
    for tier in sorted(_TIER_NODE_AGENTS.keys()):
        builder.add_node(f"start_tier{tier}", _make_tier_start_node(deps, tier=tier, phase=_TIER_PHASES[tier]))
        for node_name, agent_name in _TIER_NODE_AGENTS[tier]:
            builder.add_node(node_name, _make_agent_node(deps, agent_name=agent_name, tier=tier, phase=_TIER_PHASES[tier]))
        builder.add_node(
            f"gather_tier{tier}",
            _make_gather_node(
                deps,
                tier=tier,
                phase=_TIER_PHASES[tier],
                agent_names=[agent_name for _, agent_name in _TIER_NODE_AGENTS[tier]],
            ),
        )
    builder.add_node(
        get_subagent_node_name("decision_utility_judge"),
        _make_agent_node(deps, agent_name="decision_utility_judge", tier=5, phase=_TIER_PHASES[5]),
    )
    builder.add_node(
        get_subagent_node_name("writer"),
        _make_agent_node(deps, agent_name="writer", tier=6, phase=_TIER_PHASES[6]),
    )
    builder.add_node("finalize_node", lambda state: finalize_node(state, deps))

    builder.add_edge(START, get_subagent_node_name("retrieval_router"))
    previous = get_subagent_node_name("retrieval_router")
    for tier in sorted(_TIER_NODE_AGENTS.keys()):
        start_node = f"start_tier{tier}"
        gather_node = f"gather_tier{tier}"
        builder.add_edge(previous, start_node)
        builder.add_conditional_edges(
            start_node,
            (dispatch_tier1 if tier == 1 else dispatch_tier2 if tier == 2 else dispatch_tier3 if tier == 3 else dispatch_tier4),
        )
        for node_name, _agent_name in _TIER_NODE_AGENTS[tier]:
            builder.add_edge(node_name, gather_node)
        previous = gather_node
    builder.add_edge(previous, get_subagent_node_name("decision_utility_judge"))
    builder.add_conditional_edges(
        get_subagent_node_name("decision_utility_judge"),
        route_after_utility,
        {
            "writer_node": "writer_node",
            "finalize_node": "finalize_node",
        },
    )
    builder.add_edge(get_subagent_node_name("writer"), "finalize_node")
    builder.add_edge("finalize_node", END)
    return builder


def run_exploration_deterministic_graph(
    *,
    request: Dict[str, Any],
    skill_assets: Dict[str, Any],
    middleware_factory: Callable[[str], List[Any]],
    event_callback: Callable[[Dict[str, Any]], None] | None = None,
    llm: Any,
    initial_files: Dict[str, Dict[str, Any]],
    runtime_backend: Any = None,
    common_context: Optional[Dict[str, Any]] = None,
    lifecycle_tracker: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    runtime_deps = _ExplorationRuntimeDeps(
        skill_assets=skill_assets if isinstance(skill_assets, dict) else {},
        middleware_factory=middleware_factory,
        event_callback=event_callback,
        llm=llm,
        runtime_backend=runtime_backend,
        common_context=common_context if isinstance(common_context, dict) else {},
        lifecycle_tracker=lifecycle_tracker if isinstance(lifecycle_tracker, dict) else None,
        subagent_specs=_build_subagent_spec_map(
            skill_assets=skill_assets if isinstance(skill_assets, dict) else {},
            middleware_factory=middleware_factory,
        ),
    )

    builder = build_exploration_deterministic_graph(runtime_deps)
    checkpointer, runtime_profile = get_shared_report_checkpointer(purpose="exploration-deterministic-graph")
    graph = builder.compile(checkpointer=checkpointer)

    thread_id = str(request.get("thread_id") or "").strip()
    task_id = str(request.get("task_id") or "").strip()
    config = build_report_runnable_config(
        thread_id=thread_id,
        purpose="exploration-deterministic-graph",
        task_id=task_id,
        tags=["deterministic", "exploration"],
        metadata={"topic_identifier": str(request.get("topic_identifier") or "").strip()},
        locator_hint=runtime_profile.checkpoint_locator,
    )

    initial_state: ExplorationDeterministicState = {
        "files": initial_files if isinstance(initial_files, dict) else {},
        "task_id": task_id,
        "thread_id": thread_id,
        "topic_identifier": str(request.get("topic_identifier") or "").strip(),
        "project_identifier": str((common_context or {}).get("project_identifier") or request.get("project_identifier") or "").strip(),
        "topic_label": str(request.get("topic_label") or "").strip(),
        "start": str(request.get("start") or "").strip(),
        "end": str(request.get("end") or "").strip(),
        "mode": str(request.get("mode") or "fast").strip() or "fast",
        "status": "running",
        "message": "",
        "gaps": [],
        "structured_payload": {},
        "agent_attempts": {},
        "agent_statuses": {},
        "agent_messages": {},
        "agent_results": {},
        "tier_results": {},
        "section_draft_paths": [],
        "reuse_plan": (common_context or {}).get("reuse_decision") if isinstance((common_context or {}).get("reuse_decision"), dict) else {},
        "execution_plan": (common_context or {}).get("execution_plan") if isinstance((common_context or {}).get("execution_plan"), dict) else {},
        "reused_artifacts": (common_context or {}).get("reused_artifacts") if isinstance((common_context or {}).get("reused_artifacts"), dict) else {},
        "supplement_candidates": (common_context or {}).get("supplement_candidates") if isinstance((common_context or {}).get("supplement_candidates"), dict) else {},
        "skipped_agents": {},
    }
    _emit_todo_update(
        event_callback,
        state=initial_state,
        phase="prepare",
        title="探索阶段清单已创建",
        message="已建立 Tier 0-6 执行清单。",
    )

    final_state: Dict[str, Any] = {}
    for chunk in graph.stream(
        initial_state,
        config=config,
        stream_mode="updates",
        version="v2",
    ):
        if not isinstance(chunk, dict):
            continue
        data = chunk.get("data") if chunk.get("type") == "updates" else None
        if not isinstance(data, dict):
            continue
        for updates in data.values():
            if isinstance(updates, dict):
                final_state = _merge_stream_update(final_state, updates)

    return {
        "files": final_state.get("files") if isinstance(final_state.get("files"), dict) else {},
        "gaps": final_state.get("gaps") if isinstance(final_state.get("gaps"), list) else [],
        "structured_payload": final_state.get("structured_payload") if isinstance(final_state.get("structured_payload"), dict) else {},
        "status": str(final_state.get("status") or "").strip() or "failed",
        "message": str(final_state.get("message") or "").strip(),
        "agent_statuses": final_state.get("agent_statuses") if isinstance(final_state.get("agent_statuses"), dict) else {},
        "tier_results": final_state.get("tier_results") if isinstance(final_state.get("tier_results"), dict) else {},
        "section_draft_paths": final_state.get("section_draft_paths") if isinstance(final_state.get("section_draft_paths"), list) else [],
        "execution_plan": final_state.get("execution_plan") if isinstance(final_state.get("execution_plan"), dict) else initial_state.get("execution_plan") or {},
        "reused_artifacts": final_state.get("reused_artifacts") if isinstance(final_state.get("reused_artifacts"), dict) else initial_state.get("reused_artifacts") or {},
        "skipped_agents": final_state.get("skipped_agents") if isinstance(final_state.get("skipped_agents"), dict) else {},
        "todos": final_state.get("todos") if isinstance(final_state.get("todos"), list) else _build_tier_todos(initial_state),
    }


__all__ = [
    "ExplorationDeterministicState",
    "build_exploration_deterministic_graph",
    "finalize_node",
    "route_after_utility",
    "run_exploration_deterministic_graph",
]
