from __future__ import annotations

from typing import Any, Callable, Dict, List, TypedDict

from langgraph.graph import END, START, StateGraph

from ..runtime_infra import build_report_runnable_config, build_runtime_diagnostics, get_shared_report_checkpointer


class _OrchestratorState(TypedDict, total=False):
    request: Dict[str, Any]
    exploration_bundle: Dict[str, Any]
    structured_payload: Dict[str, Any]
    full_payload: Dict[str, Any]
    approvals: List[Dict[str, Any]]
    status: str
    message: str


def _emit(event_callback: Callable[[Dict[str, Any]], None] | None, event: Dict[str, Any]) -> None:
    if callable(event_callback):
        event_callback(event)


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
    run_exploration: Callable[[], Dict[str, Any]],
    run_compile: Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]],
    event_callback: Callable[[Dict[str, Any]], None] | None = None,
) -> Dict[str, Any]:
    checkpointer, runtime_profile = get_shared_report_checkpointer(purpose="deep-report-root-graph")

    def planning_node(_state: _OrchestratorState) -> Dict[str, Any]:
        _emit(
            event_callback,
            {
                "type": "phase.progress",
                "phase": "planning",
                "title": "根图已启动",
                "message": "正在建立本次报告的根编排图。",
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
        return {"status": "running", "message": "根图已启动。"}

    def exploration_node(_state: _OrchestratorState) -> Dict[str, Any]:
        _emit(
            event_callback,
            {
                "type": "phase.progress",
                "phase": "exploration",
                "title": "进入探索子图",
                "message": "正在执行本地归档探索与结构化综合。",
                "payload": {"root_thread_id": root_thread_id},
            },
        )
        result = run_exploration() or {}
        return {
            "exploration_bundle": result.get("exploration_bundle") if isinstance(result.get("exploration_bundle"), dict) else {},
            "structured_payload": result.get("structured_payload") if isinstance(result.get("structured_payload"), dict) else {},
            "status": str(result.get("status") or "").strip() or "failed",
            "message": str(result.get("message") or "").strip(),
            "approvals": result.get("approvals") if isinstance(result.get("approvals"), list) else [],
            "full_payload": result.get("full_payload") if isinstance(result.get("full_payload"), dict) else {},
        }

    def compile_node(state: _OrchestratorState) -> Dict[str, Any]:
        structured_payload = state.get("structured_payload") if isinstance(state.get("structured_payload"), dict) else {}
        exploration_bundle = state.get("exploration_bundle") if isinstance(state.get("exploration_bundle"), dict) else {}
        if not structured_payload:
            return {
                "status": "failed",
                "message": "探索子图未返回结构化结果。",
                "approvals": [],
                "full_payload": {},
            }
        _emit(
            event_callback,
            {
                "type": "phase.progress",
                "phase": "compile",
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
        return {
            "status": status,
            "message": message,
            "approvals": result.get("approvals") if isinstance(result.get("approvals"), list) else [],
            "full_payload": result if isinstance(result, dict) else {},
        }

    def route_after_exploration(state: _OrchestratorState) -> str:
        status = str(state.get("status") or "").strip()
        structured_payload = state.get("structured_payload") if isinstance(state.get("structured_payload"), dict) else {}
        if status == "failed" or not structured_payload:
            return END
        return "compile_subgraph"

    builder = StateGraph(_OrchestratorState)
    builder.add_node("planning", _wrapped_node("planning", phase="planning", handler=planning_node, event_callback=event_callback))
    builder.add_node(
        "exploration_subgraph",
        _wrapped_node("exploration_subgraph", phase="exploration", handler=exploration_node, event_callback=event_callback),
    )
    builder.add_node(
        "compile_subgraph",
        _wrapped_node("compile_subgraph", phase="compile", handler=compile_node, event_callback=event_callback),
    )
    builder.add_edge(START, "planning")
    builder.add_edge("planning", "exploration_subgraph")
    builder.add_conditional_edges(
        "exploration_subgraph",
        route_after_exploration,
        {
            "compile_subgraph": "compile_subgraph",
            END: END,
        },
    )
    builder.add_edge("compile_subgraph", END)

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
    ):
        if not isinstance(chunk, dict):
            continue
        for updates in chunk.values():
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
            "runtime_diagnostics": build_runtime_diagnostics(
                purpose="deep-report-root-graph",
                thread_id=root_thread_id,
                task_id=str((request or {}).get("task_id") or "").strip(),
                locator_hint=runtime_profile.checkpoint_locator,
            ),
        },
    }
