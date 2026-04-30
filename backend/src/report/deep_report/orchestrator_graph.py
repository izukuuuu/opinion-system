from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from ..runtime_infra import build_report_runnable_config, build_runtime_diagnostics, get_shared_report_checkpointer


class _OrchestratorState(TypedDict, total=False):
    request: Dict[str, Any]
    run_identity: Dict[str, Any]
    stage: str
    artifact_refs: Dict[str, Any]
    scorecard_refs: Dict[str, Any]
    approval_state: Dict[str, Any]
    retry_budget: Dict[str, Any]
    error_context: Dict[str, Any]
    exploration_bundle: Dict[str, Any]
    structured_payload: Dict[str, Any]
    full_payload: Dict[str, Any]
    approvals: List[Dict[str, Any]]
    status: str
    message: str


def _emit(event_callback: Callable[[Dict[str, Any]], None] | None, event: Dict[str, Any]) -> None:
    if callable(event_callback):
        event_callback(event)


def _now_iso() -> str:
    return datetime.now().isoformat(sep=" ")


def _sha256_file(path: Path) -> str:
    if not path.exists() or not path.is_file():
        return ""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_stage_scorecard(
    state: _OrchestratorState,
    *,
    stage: str,
    checks: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    request = state.get("request") if isinstance(state.get("request"), dict) else {}
    cache_dir_text = str(request.get("cache_dir") or "").strip()
    check_list = list(checks or [])
    failed = [item for item in check_list if item.get("status") == "fail"]
    warned = [item for item in check_list if item.get("status") == "warning"]
    status = "failed" if failed else ("warning" if warned else "passed")
    payload = {
        "type": "stage_scorecard",
        "stage": stage,
        "thread_id": str(request.get("root_thread_id") or "").strip(),
        "created_at": _now_iso(),
        "status": status,
        "checks": check_list,
        "state_keys": sorted(str(key) for key in state.keys()),
    }
    if not cache_dir_text:
        return {"stage": stage, "status": status, "payload": payload, "path": "", "sha256": "", "blocking_checks": failed, "warning_checks": warned}
    path = Path(cache_dir_text) / f"{stage}.scorecard.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return {"stage": stage, "status": status, "payload": payload, "path": str(path), "sha256": _sha256_file(path), "blocking_checks": failed, "warning_checks": warned}


def _stage_gate_node(
    stage: str,
    *,
    next_nodes: List[str],
    event_callback: Callable[[Dict[str, Any]], None] | None,
    checks_builder: Callable[[_OrchestratorState], List[Dict[str, Any]]] | None = None,
) -> Callable[[_OrchestratorState], Dict[str, Any]]:
    def _run(state: _OrchestratorState) -> Dict[str, Any]:
        request = state.get("request") if isinstance(state.get("request"), dict) else {}
        thread_id = str(request.get("root_thread_id") or "").strip()
        checks = checks_builder(state) if callable(checks_builder) else [{"name": f"{stage}_completed", "status": "pass", "reason": "stage_boundary_reached"}]
        scorecard = _write_stage_scorecard(state, stage=stage, checks=checks)
        scorecard_refs = dict(state.get("scorecard_refs") or {}) if isinstance(state.get("scorecard_refs"), dict) else {}
        scorecard_refs[stage] = {"path": scorecard.get("path", ""), "sha256": scorecard.get("sha256", ""), "status": scorecard.get("status", "")}
        payload = {
            "type": "stage_eval_gate",
            "stage": stage,
            "thread_id": thread_id,
            "checkpoint_id": "",
            "next": next_nodes,
            "scorecard_ref": str(scorecard.get("path") or ""),
            "artifact_refs": state.get("artifact_refs") if isinstance(state.get("artifact_refs"), dict) else {},
            "blocking_checks": scorecard.get("blocking_checks") if isinstance(scorecard.get("blocking_checks"), list) else [],
            "warning_checks": scorecard.get("warning_checks") if isinstance(scorecard.get("warning_checks"), list) else [],
            "allowed_decisions": ["continue", "repair", "fork", "abort"],
        }
        _emit(
            event_callback,
            {
                "type": "stage.eval_gate.ready",
                "phase": stage,
                "agent": f"eval_gate_{stage}",
                "title": f"{stage} 阶段评估完成",
                "message": f"{stage} 阶段 scorecard 已生成。",
                "payload": payload,
            },
        )
        if bool(request.get("stage_gate_enabled")):
            decision = interrupt(payload)
            decision_payload = decision if isinstance(decision, dict) else {"decision": "continue" if decision else "abort"}
        else:
            decision_payload = {"decision": "continue"}
        decision_text = str(decision_payload.get("decision") or "continue").strip().lower()
        if decision_text not in {"continue", "repair", "fork", "abort"}:
            decision_text = "continue"
        return {
            "stage": stage,
            "scorecard_refs": scorecard_refs,
            "approval_state": {"stage": stage, "decision": decision_text, "payload": decision_payload},
            "status": str(state.get("status") or "running").strip() or "running",
        }

    return _run


def _wrapped_node(
    node_name: str,
    *,
    phase: str,
    handler: Callable[[_OrchestratorState], Dict[str, Any]],
    event_callback: Callable[[Dict[str, Any]], None] | None,
) -> Callable[[_OrchestratorState], Dict[str, Any]]:
    def _run(state: _OrchestratorState) -> Dict[str, Any]:
        _emit(
            event_callback,
            {
                "type": "graph.node.started",
                "phase": phase,
                "agent": node_name,
                "title": f"{node_name} 已启动",
                "message": f"{node_name} 正在执行。",
                "payload": {"current_node": node_name},
            },
        )
        try:
            updates = handler(state) or {}
        except Exception as exc:
            _emit(
                event_callback,
                {
                    "type": "graph.node.failed",
                    "phase": phase,
                    "agent": node_name,
                    "title": f"{node_name} 失败",
                    "message": str(exc or "运行失败。").strip() or "运行失败。",
                    "payload": {"current_node": node_name, "failed_node": node_name},
                },
            )
            raise
        _emit(
            event_callback,
            {
                "type": "graph.node.completed",
                "phase": phase,
                "agent": node_name,
                "title": f"{node_name} 已完成",
                "message": f"{node_name} 已完成。",
                "payload": {"current_node": node_name},
            },
        )
        return updates

    return _run


def run_report_orchestrator_graph(
    *,
    request: Dict[str, Any],
    root_thread_id: str,
    invoke_deep_agent: Callable[[Dict[str, Any]], Dict[str, Any]],
    run_compile: Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]],
    event_callback: Callable[[Dict[str, Any]], None] | None = None,
) -> Dict[str, Any]:
    checkpointer, runtime_profile = get_shared_report_checkpointer(purpose="deep-report-root-graph")

    def resolve_scope_node(_state: _OrchestratorState) -> Dict[str, Any]:
        _emit(
            event_callback,
            {
                "type": "phase.progress",
                "phase": "resolve_scope",
                "title": "根图已启动",
                "message": "正在解析本次报告的运行范围与 checkpoint 身份。",
                "payload": {
                    "root_thread_id": root_thread_id,
                    "runtime_diagnostics": build_runtime_diagnostics(
                        purpose="deep-report-root-graph",
                        thread_id=root_thread_id,
                        task_id=str((request or {}).get("task_id") or "").strip(),
                        locator_hint=runtime_profile.checkpoint_locator,
                    ),
                },
            },
        )
        return {
            "run_identity": {
                "task_id": str((request or {}).get("task_id") or "").strip(),
                "thread_id": str((request or {}).get("thread_id") or "").strip(),
                "root_thread_id": root_thread_id,
                "topic_identifier": str((request or {}).get("topic_identifier") or "").strip(),
                "project_identifier": str((request or {}).get("project_identifier") or "").strip(),
                "start": str((request or {}).get("start") or "").strip(),
                "end": str((request or {}).get("end") or "").strip(),
                "mode": str((request or {}).get("mode") or "fast").strip() or "fast",
            },
            "artifact_refs": {},
            "scorecard_refs": {},
            "approval_state": {},
            "retry_budget": {"deep_exploration": 1, "compile": 1},
            "error_context": {},
            "stage": "resolve_scope",
            "status": "running",
            "message": "根图已启动。",
        }

    def build_retrieval_pack_node(state: _OrchestratorState) -> Dict[str, Any]:
        request_payload = state.get("request") if isinstance(state.get("request"), dict) else {}
        return {
            "stage": "build_retrieval_pack",
            "artifact_refs": {
                **(state.get("artifact_refs") if isinstance(state.get("artifact_refs"), dict) else {}),
                "retrieval_scope": {
                    "schema_version": "retrieval_scope.v1",
                    "topic_identifier": str(request_payload.get("topic_identifier") or "").strip(),
                    "project_identifier": str(request_payload.get("project_identifier") or "").strip(),
                    "start": str(request_payload.get("start") or "").strip(),
                    "end": str(request_payload.get("end") or "").strip(),
                    "producer_node": "build_retrieval_pack",
                },
            },
            "status": str(state.get("status") or "running").strip() or "running",
        }

    def deep_exploration_node(state: _OrchestratorState) -> Dict[str, Any]:
        _emit(
            event_callback,
            {
                "type": "phase.progress",
                "phase": "deep_exploration",
                "title": "进入探索子图",
                "message": "正在执行本地归档探索与结构化综合。",
                "payload": {"root_thread_id": root_thread_id},
            },
        )
        # Map parent state → deep agent input, then map output back to orchestrator state.
        # Passing state["request"] explicitly makes this node's dependency on parent state
        # visible from the function body, consistent with LangGraph subgraph wrapper convention.
        result = invoke_deep_agent(state.get("request") or {}) or {}
        return {
            "exploration_bundle": result.get("exploration_bundle") if isinstance(result.get("exploration_bundle"), dict) else {},
            "structured_payload": result.get("structured_payload") if isinstance(result.get("structured_payload"), dict) else {},
            "status": str(result.get("status") or "").strip() or "failed",
            "message": str(result.get("message") or "").strip(),
            "approvals": result.get("approvals") if isinstance(result.get("approvals"), list) else [],
            "full_payload": result.get("full_payload") if isinstance(result.get("full_payload"), dict) else {},
            "stage": "deep_exploration",
        }

    def normalize_to_ir_node(state: _OrchestratorState) -> Dict[str, Any]:
        structured_payload = state.get("structured_payload") if isinstance(state.get("structured_payload"), dict) else {}
        artifact_refs = dict(state.get("artifact_refs") or {}) if isinstance(state.get("artifact_refs"), dict) else {}
        if isinstance(structured_payload.get("report_ir"), dict):
            artifact_refs["report_ir"] = {
                "schema_version": "report_ir.v1",
                "producer_node": "normalize_to_ir",
                "status": "ready",
            }
        return {"stage": "normalize_to_ir", "artifact_refs": artifact_refs}

    def draft_sections_node(state: _OrchestratorState) -> Dict[str, Any]:
        structured_payload = state.get("structured_payload") if isinstance(state.get("structured_payload"), dict) else {}
        exploration_bundle = state.get("exploration_bundle") if isinstance(state.get("exploration_bundle"), dict) else {}
        if not structured_payload:
            return {
                "status": "failed",
                "message": "探索子图未返回结构化结果。",
                "approvals": [],
                "full_payload": {},
                "stage": "draft_sections",
                "error_context": {"stage": "draft_sections", "reason": "missing_structured_payload"},
            }
        _emit(
            event_callback,
            {
                "type": "phase.progress",
                "phase": "draft_sections",
                "title": "进入编译子图",
                "message": "正在执行正式文稿编译、校验与审批门禁。",
                "payload": {"root_thread_id": root_thread_id},
            },
        )
        result = run_compile(structured_payload, exploration_bundle) or {}
        status = str(result.get("status") or "").strip() or ("completed" if isinstance(result.get("markdown"), str) else "failed")
        message = str(result.get("message") or "").strip()
        if status == "waiting_approval":
            _emit(
                event_callback,
                {
                    "type": "phase.progress",
                    "phase": "review",
                    "title": "等待人工审批",
                    "message": message or "正式文稿触发人工审批。",
                    "payload": {"root_thread_id": root_thread_id},
                },
            )
        elif status == "completed":
            _emit(
                event_callback,
                {
                    "type": "phase.progress",
                    "phase": "persist",
                    "title": "编译子图完成",
                    "message": "正式文稿与报告缓存已写入。",
                    "payload": {"root_thread_id": root_thread_id},
                },
            )
        else:
            _emit(
                event_callback,
                {
                    "type": "phase.progress",
                    "phase": "compile",
                    "title": "编译子图未返回有效结果",
                    "message": message or "编译阶段返回了未知状态。",
                    "payload": {"root_thread_id": root_thread_id, "status": status},
                },
            )
        return {
            "status": status,
            "message": message,
            "approvals": result.get("approvals") if isinstance(result.get("approvals"), list) else [],
            "full_payload": result if isinstance(result, dict) else {},
            "stage": "draft_sections",
        }

    def validate_and_repair_node(state: _OrchestratorState) -> Dict[str, Any]:
        full_payload = state.get("full_payload") if isinstance(state.get("full_payload"), dict) else {}
        artifact_refs = dict(state.get("artifact_refs") or {}) if isinstance(state.get("artifact_refs"), dict) else {}
        if isinstance(full_payload.get("validation_result_v2"), dict):
            artifact_refs["validation_result"] = {"schema_version": "validation_result.v2", "producer_node": "validate_and_repair", "status": "ready"}
        if isinstance(full_payload.get("repair_plan_v2"), dict):
            artifact_refs["repair_plan"] = {"schema_version": "repair_plan.v2", "producer_node": "validate_and_repair", "status": "ready"}
        return {"stage": "validate_and_repair", "artifact_refs": artifact_refs}

    def render_artifacts_node(state: _OrchestratorState) -> Dict[str, Any]:
        full_payload = state.get("full_payload") if isinstance(state.get("full_payload"), dict) else {}
        artifact_refs = dict(state.get("artifact_refs") or {}) if isinstance(state.get("artifact_refs"), dict) else {}
        if full_payload:
            artifact_refs["full_payload"] = {"schema_version": "full_report_payload.v1", "producer_node": "render_artifacts", "status": str(state.get("status") or "").strip()}
        return {"stage": "render_artifacts", "artifact_refs": artifact_refs}

    def route_after_deep_exploration(state: _OrchestratorState) -> str:
        structured_payload = state.get("structured_payload") if isinstance(state.get("structured_payload"), dict) else {}
        if not structured_payload:
            return END
        return "normalize_to_ir"

    def route_after_gate(state: _OrchestratorState, next_node: str) -> str:
        approval_state = state.get("approval_state") if isinstance(state.get("approval_state"), dict) else {}
        if str(approval_state.get("decision") or "continue").strip().lower() == "abort":
            return END
        return next_node

    def _basic_stage_checks(stage: str) -> Callable[[_OrchestratorState], List[Dict[str, Any]]]:
        def _checks(state: _OrchestratorState) -> List[Dict[str, Any]]:
            if stage == "deep_exploration":
                structured_payload = state.get("structured_payload") if isinstance(state.get("structured_payload"), dict) else {}
                return [{"name": "structured_payload", "status": "pass" if structured_payload else "fail", "reason": "ready" if structured_payload else "missing"}]
            if stage == "draft_sections":
                status = str(state.get("status") or "").strip()
                return [{"name": "compile_status", "status": "pass" if status in {"completed", "waiting_approval"} else "warning", "reason": status or "unknown"}]
            return [{"name": f"{stage}_boundary", "status": "pass", "reason": "stage_boundary_reached"}]

        return _checks

    builder = StateGraph(_OrchestratorState)
    builder.add_node("resolve_scope", _wrapped_node("resolve_scope", phase="resolve_scope", handler=resolve_scope_node, event_callback=event_callback))
    builder.add_node("eval_gate_resolve_scope", _stage_gate_node("resolve_scope", next_nodes=["build_retrieval_pack"], event_callback=event_callback, checks_builder=_basic_stage_checks("resolve_scope")))
    builder.add_node(
        "build_retrieval_pack",
        _wrapped_node("build_retrieval_pack", phase="retrieval", handler=build_retrieval_pack_node, event_callback=event_callback),
    )
    builder.add_node("eval_gate_build_retrieval_pack", _stage_gate_node("build_retrieval_pack", next_nodes=["deep_exploration"], event_callback=event_callback, checks_builder=_basic_stage_checks("build_retrieval_pack")))
    builder.add_node(
        "deep_exploration",
        _wrapped_node("deep_exploration", phase="exploration", handler=deep_exploration_node, event_callback=event_callback),
    )
    builder.add_node("eval_gate_deep_exploration", _stage_gate_node("deep_exploration", next_nodes=["normalize_to_ir"], event_callback=event_callback, checks_builder=_basic_stage_checks("deep_exploration")))
    builder.add_node("normalize_to_ir", _wrapped_node("normalize_to_ir", phase="normalize", handler=normalize_to_ir_node, event_callback=event_callback))
    builder.add_node("eval_gate_normalize_to_ir", _stage_gate_node("normalize_to_ir", next_nodes=["draft_sections"], event_callback=event_callback, checks_builder=_basic_stage_checks("normalize_to_ir")))
    builder.add_node(
        "draft_sections",
        _wrapped_node("draft_sections", phase="compile", handler=draft_sections_node, event_callback=event_callback),
    )
    builder.add_node("eval_gate_draft_sections", _stage_gate_node("draft_sections", next_nodes=["validate_and_repair"], event_callback=event_callback, checks_builder=_basic_stage_checks("draft_sections")))
    builder.add_node("validate_and_repair", _wrapped_node("validate_and_repair", phase="validate", handler=validate_and_repair_node, event_callback=event_callback))
    builder.add_node("eval_gate_validate_and_repair", _stage_gate_node("validate_and_repair", next_nodes=["render_artifacts"], event_callback=event_callback, checks_builder=_basic_stage_checks("validate_and_repair")))
    builder.add_node("render_artifacts", _wrapped_node("render_artifacts", phase="render", handler=render_artifacts_node, event_callback=event_callback))
    builder.add_node("eval_gate_render_artifacts", _stage_gate_node("render_artifacts", next_nodes=[], event_callback=event_callback, checks_builder=_basic_stage_checks("render_artifacts")))
    builder.add_edge(START, "resolve_scope")
    builder.add_edge("resolve_scope", "eval_gate_resolve_scope")
    builder.add_conditional_edges("eval_gate_resolve_scope", lambda state: route_after_gate(state, "build_retrieval_pack"), {"build_retrieval_pack": "build_retrieval_pack", END: END})
    builder.add_edge("build_retrieval_pack", "eval_gate_build_retrieval_pack")
    builder.add_conditional_edges("eval_gate_build_retrieval_pack", lambda state: route_after_gate(state, "deep_exploration"), {"deep_exploration": "deep_exploration", END: END})
    builder.add_edge("deep_exploration", "eval_gate_deep_exploration")
    builder.add_conditional_edges(
        "eval_gate_deep_exploration",
        lambda state: END if str(((state.get("approval_state") if isinstance(state.get("approval_state"), dict) else {}).get("decision") or "continue")).strip().lower() == "abort" else route_after_deep_exploration(state),
        {
            "normalize_to_ir": "normalize_to_ir",
            END: END,
        },
    )
    builder.add_edge("normalize_to_ir", "eval_gate_normalize_to_ir")
    builder.add_conditional_edges("eval_gate_normalize_to_ir", lambda state: route_after_gate(state, "draft_sections"), {"draft_sections": "draft_sections", END: END})
    builder.add_edge("draft_sections", "eval_gate_draft_sections")
    builder.add_conditional_edges("eval_gate_draft_sections", lambda state: route_after_gate(state, "validate_and_repair"), {"validate_and_repair": "validate_and_repair", END: END})
    builder.add_edge("validate_and_repair", "eval_gate_validate_and_repair")
    builder.add_conditional_edges("eval_gate_validate_and_repair", lambda state: route_after_gate(state, "render_artifacts"), {"render_artifacts": "render_artifacts", END: END})
    builder.add_edge("render_artifacts", "eval_gate_render_artifacts")
    builder.add_edge("eval_gate_render_artifacts", END)

    graph = builder.compile(checkpointer=checkpointer)
    config = build_report_runnable_config(
        thread_id=root_thread_id,
        purpose="deep-report-root-graph",
        task_id=str((request or {}).get("task_id") or "").strip(),
        tags=["root_graph"],
        metadata={
            "runtime_diagnostics": build_runtime_diagnostics(
                purpose="deep-report-root-graph",
                thread_id=root_thread_id,
                task_id=str((request or {}).get("task_id") or "").strip(),
                locator_hint=runtime_profile.checkpoint_locator,
            )
        },
        locator_hint=runtime_profile.checkpoint_locator,
    )
    state: Dict[str, Any] = {}
    for chunk in graph.stream(
        {"request": request},
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
                state.update(updates)
    return {
        "status": str(state.get("status") or "").strip() or "failed",
        "message": str(state.get("message") or "").strip(),
        "approvals": state.get("approvals") if isinstance(state.get("approvals"), list) else [],
        "structured_payload": state.get("structured_payload") if isinstance(state.get("structured_payload"), dict) else {},
        "full_payload": state.get("full_payload") if isinstance(state.get("full_payload"), dict) else {},
        "exploration_bundle": state.get("exploration_bundle") if isinstance(state.get("exploration_bundle"), dict) else {},
        "thread_id": str((request.get("thread_id") if isinstance(request, dict) else "") or "").strip(),
        "root_graph_state": {
            "root_thread_id": root_thread_id,
            "status": str(state.get("status") or "").strip() or "failed",
            "stage": str(state.get("stage") or "").strip(),
            "artifact_refs": state.get("artifact_refs") if isinstance(state.get("artifact_refs"), dict) else {},
            "scorecard_refs": state.get("scorecard_refs") if isinstance(state.get("scorecard_refs"), dict) else {},
            "approval_state": state.get("approval_state") if isinstance(state.get("approval_state"), dict) else {},
            "runtime_diagnostics": build_runtime_diagnostics(
                purpose="deep-report-root-graph",
                thread_id=root_thread_id,
                task_id=str((request or {}).get("task_id") or "").strip(),
                locator_hint=runtime_profile.checkpoint_locator,
            ),
        },
    }
