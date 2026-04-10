"""Background worker subprocess for report queue execution."""
from __future__ import annotations

import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict

BACKEND_DIR = Path(__file__).resolve().parents[2]
SRC_DIR = BACKEND_DIR / "src"
for path in (BACKEND_DIR, SRC_DIR):
    path_text = str(path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)

from server_support.archive_locator import compose_folder_name  # type: ignore
from server_support.topic_context import TopicContext  # type: ignore
from src.report.deep_report import (  # type: ignore
    AI_FULL_REPORT_CACHE_FILENAME,
    REPORT_CACHE_FILENAME,
    ReportRuntimeFailure,
    run_or_resume_deep_report_task,
)
from src.report.deep_report.assets import build_artifacts_root  # type: ignore
from src.report.runtime import ensure_analyze_results, ensure_explain_results  # type: ignore
from src.report.task_queue import (  # type: ignore
    append_agent_memo,
    append_event,
    get_task,
    mark_approval_required,
    mark_agent_started,
    mark_artifact_ready,
    mark_task_cancelled,
    mark_task_completed,
    mark_task_failed,
    mark_task_progress,
    set_structured_result_digest,
    reserve_next_task,
    set_worker_pid,
    should_cancel,
    update_task_trust,
    update_todos,
    write_worker_status,
)
from src.utils.setting.paths import get_data_root  # type: ignore
from src.utils.setting.paths import bucket  # type: ignore

LOGGER = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s | %(message)s",
)
PHASE_PERCENTAGE = {
    "prepare": 5,
    "analyze": 18,
    "explain": 32,
    "interpret": 58,
    "write": 82,
    "review": 93,
    "persist": 98,
}


class TaskCancelled(RuntimeError):
    """Raised when the queue item was cancelled by the user."""


def main() -> None:
    started_at = _utc_now()
    idle_seconds = 90
    last_active_at = time.monotonic()
    write_worker_status(
        {
            "pid": os.getpid(),
            "status": "idle",
            "running": True,
            "current_task_id": "",
            "last_heartbeat": _utc_now(),
            "started_at": started_at,
        }
    )
    try:
        while True:
            task = reserve_next_task()
            if not task:
                write_worker_status(
                    {
                        "pid": os.getpid(),
                        "status": "idle",
                        "running": True,
                        "current_task_id": "",
                        "last_heartbeat": _utc_now(),
                        "started_at": started_at,
                    }
                )
                if time.monotonic() - last_active_at >= idle_seconds:
                    write_worker_status(
                        {
                            "pid": os.getpid(),
                            "status": "stopped",
                            "running": False,
                            "current_task_id": "",
                            "last_heartbeat": _utc_now(),
                            "started_at": started_at,
                        }
                    )
                    return
                time.sleep(2.0)
                continue

            last_active_at = time.monotonic()
            task_id = str(task.get("id") or "")
            set_worker_pid(task_id, os.getpid())
            write_worker_status(
                {
                    "pid": os.getpid(),
                    "status": "running",
                    "running": True,
                    "current_task_id": task_id,
                    "last_heartbeat": _utc_now(),
                    "started_at": started_at,
                }
            )
            try:
                _run_task(task_id)
            except TaskCancelled as exc:
                mark_task_cancelled(task_id, str(exc))
            except Exception as exc:
                LOGGER.exception("Report worker failed | task=%s", task_id)
                diagnostic = _build_failure_diagnostic(task_id, exc)
                mark_task_failed(task_id, _failure_message(exc, diagnostic), payload=diagnostic)
    finally:
        write_worker_status(
            {
                "pid": os.getpid(),
                "status": "stopped",
                "running": False,
                "current_task_id": "",
                "last_heartbeat": _utc_now(),
                "started_at": started_at,
            }
        )


def _run_task(task_id: str) -> None:
    task = get_task(task_id)
    request = dict(task.get("request") or {})
    topic_identifier = str(request.get("topic_identifier") or task.get("topic_identifier") or "").strip()
    topic_label = str(request.get("topic") or task.get("topic") or topic_identifier).strip() or topic_identifier
    start = str(request.get("start") or task.get("start") or "").strip()
    end = str(request.get("end") or task.get("end") or start).strip() or start
    mode = str(request.get("mode") or task.get("mode") or "fast").strip().lower() or "fast"
    aliases = [
        str(item).strip()
        for item in (request.get("aliases") or [])
        if str(item or "").strip()
    ]
    ctx = TopicContext(identifier=topic_identifier, display_name=topic_label, aliases=aliases)
    folder = compose_folder_name(start, end)
    cache_path = bucket("reports", topic_identifier, folder) / REPORT_CACHE_FILENAME
    full_cache_path = bucket("reports", topic_identifier, folder) / AI_FULL_REPORT_CACHE_FILENAME
    LOGGER.warning(
        "report worker | task start | task=%s topic=%s start=%s end=%s mode=%s",
        task_id,
        topic_identifier,
        start,
        end,
        mode,
    )

    stop_event = threading.Event()
    heartbeat = threading.Thread(
        target=_heartbeat_loop,
        args=(task_id, stop_event, task.get("started_at") or _utc_now()),
        daemon=True,
    )
    heartbeat.start()
    try:
        _raise_if_cancelled(task_id)
        mark_agent_started(
            task_id,
            agent="researcher",
            phase="prepare",
            message="Researcher 正在检查专题数据和历史产物。",
        )
        mark_task_progress(task_id, phase="prepare", percentage=PHASE_PERCENTAGE["prepare"], message="正在检查基础数据是否完备。")
        mark_task_progress(task_id, phase="analyze", percentage=PHASE_PERCENTAGE["analyze"], message="Researcher 正在确认基础分析结果。")

        analyze_prepare = ensure_analyze_results(
            topic_identifier,
            start=start,
            end=end,
            ctx=ctx,
        )
        LOGGER.warning(
            "report worker | analyze ready | task=%s prepared=%s root=%s",
            task_id,
            bool(analyze_prepare.get("prepared")),
            analyze_prepare.get("analyze_root"),
        )
        append_agent_memo(
            task_id,
            agent="researcher",
            phase="analyze",
            message=analyze_prepare.get("message") or "基础分析结果已就绪。",
            delta=str(analyze_prepare.get("message") or "基础分析结果已就绪。"),
            payload=analyze_prepare,
        )
        _raise_if_cancelled(task_id)

        mark_task_progress(task_id, phase="explain", percentage=PHASE_PERCENTAGE["explain"], message="Researcher 正在补齐总体文字解读。")
        explain_prepare = ensure_explain_results(
            topic_identifier,
            start=start,
            end=end,
            ctx=ctx,
        )
        if not bool(explain_prepare.get("ready")):
            LOGGER.warning(
                "report worker | explain still incomplete | task=%s source=%s smart_fill=%s available=%s/%s",
                task_id,
                explain_prepare.get("source"),
                explain_prepare.get("smart_fill"),
                explain_prepare.get("available_count"),
                explain_prepare.get("expected_count"),
            )
        else:
            LOGGER.warning(
                "report worker | explain ready | task=%s source=%s generated=%s",
                task_id,
                explain_prepare.get("source"),
                (explain_prepare.get("smart_fill") or {}).get("generated_functions"),
            )
        append_agent_memo(
            task_id,
            agent="researcher",
            phase="explain",
            message=explain_prepare.get("message") or "总体文字解读检查完成。",
            delta=str(explain_prepare.get("message") or "总体文字解读检查完成。"),
            payload=explain_prepare,
        )
        if mode == "research":
            append_agent_memo(
                task_id,
                agent="researcher",
                phase="explain",
                message="当前任务使用 research 模式，会保留更完整的调研轨迹。",
                delta="当前任务使用 research 模式，会保留更完整的调研轨迹。",
            )
        _raise_if_cancelled(task_id)
        _maybe_update_fallback_todos(
            task_id,
            stage="interpret",
            phase="interpret",
            message="总控代理开始协调检索、证据整理和结构分析。",
        )
        if _has_rejected_approval(task):
            raise TaskCancelled("审批已拒绝，本次报告未继续写入正式结果。")

        resume_payload = _build_resume_payload_from_task(task)
        if resume_payload is None:
            mark_task_progress(task_id, phase="interpret", percentage=PHASE_PERCENTAGE["interpret"], message="总控代理正在调度子代理并生成结构化结果。")
        else:
            mark_task_progress(task_id, phase="persist", percentage=PHASE_PERCENTAGE["persist"], message="审批已处理，正在恢复正式写入流程。")

        runtime_result = run_or_resume_deep_report_task(
            topic_identifier,
            start,
            end,
            topic_label=topic_label,
            mode=mode,
            thread_id=str(task.get("thread_id") or request.get("thread_id") or "").strip(),
            task_id=task_id,
            resume_payload=resume_payload,
            event_callback=lambda event: _handle_report_event(task_id, event),
        )
        if str(runtime_result.get("status") or "").strip() == "failed":
            diagnostic = runtime_result.get("diagnostic") if isinstance(runtime_result.get("diagnostic"), dict) else {}
            raise ReportRuntimeFailure(
                str(runtime_result.get("message") or "深度代理执行失败。").strip() or "深度代理执行失败。",
                diagnostic,
            )
        report_payload = runtime_result.get("structured_payload") if isinstance(runtime_result.get("structured_payload"), dict) else {}
        full_report_payload = runtime_result.get("full_payload") if isinstance(runtime_result.get("full_payload"), dict) else {}
        if report_payload:
            LOGGER.warning(
                "report worker | structured payload ready | task=%s title=%s",
                task_id,
                str(((report_payload.get("task") or {}).get("topic_label")) or "").strip(),
            )
            set_structured_result_digest(
                task_id,
                digest=_structured_digest_from_payload(report_payload),
                path=str(cache_path),
            )
            update_task_trust(
                task_id,
                trust=_trust_from_payload(report_payload),
                phase="write",
                message="已根据结构化结果更新置信信息。",
            )
            _maybe_update_fallback_todos(
                task_id,
                stage="review",
                phase="write",
                message="结构化结果已生成，正在准备正式文稿。",
            )
        _raise_if_cancelled(task_id)

        if str(runtime_result.get("status") or "").strip() == "interrupted":
            approval_items = runtime_result.get("approvals") if isinstance(runtime_result.get("approvals"), list) else []
            mark_task_progress(task_id, phase="review", percentage=PHASE_PERCENTAGE["review"], message="文稿写入前需要人工确认。")
            _maybe_update_fallback_todos(
                task_id,
                stage="persist",
                phase="persist",
                message="正式写入前等待人工确认。",
            )
            mark_approval_required(
                task_id,
                approvals=approval_items,
                phase="persist",
                message=str(runtime_result.get("message") or "文稿写入前需要人工确认。").strip() or "文稿写入前需要人工确认。",
            )
            LOGGER.warning("report worker | task interrupted for approval | task=%s approvals=%s", task_id, len(approval_items))
            return
        if not report_payload:
            raise RuntimeError("深度代理未产出结构化报告缓存。")
        if not full_report_payload:
            raise RuntimeError("深度代理未产出完整文稿缓存。")

        mark_task_progress(task_id, phase="persist", percentage=PHASE_PERCENTAGE["persist"], message="正在整理最终报告产物。")
        _maybe_update_fallback_todos(
            task_id,
            stage="completed",
            phase="persist",
            message="结构化结果、正式文稿和校验结果均已完成。",
        )
        mark_artifact_ready(
            task_id,
            message="结构化报告与 AI 完整报告缓存已写入。",
            payload={
                "report_ready": True,
                "report_cache_path": str(cache_path),
                "report_title": str(((report_payload.get("task") or {}).get("topic_label")) or topic_label).strip(),
                "full_report_ready": True,
                "full_report_cache_path": str(full_cache_path),
                "full_report_title": str(full_report_payload.get("title") or "").strip(),
                "report_runtime_artifact": str(build_artifacts_root(task_id, get_data_root()) / "report.md"),
                "view": {
                    "topic": topic_label,
                    "topic_identifier": topic_identifier,
                    "start": start,
                    "end": end,
                },
            },
        )
        mark_task_completed(
            task_id,
            message="报告已生成。",
            payload={
                "report_ready": True,
                "report_cache_path": str(cache_path),
                "report_title": str(((report_payload.get("task") or {}).get("topic_label")) or topic_label).strip(),
                "full_report_ready": True,
                "full_report_cache_path": str(full_cache_path),
                "full_report_title": str(full_report_payload.get("title") or "").strip(),
            },
        )
        LOGGER.warning(
            "report worker | task completed | task=%s cache=%s full_cache=%s",
            task_id,
            cache_path,
            full_cache_path,
        )
    finally:
        stop_event.set()
        heartbeat.join(timeout=1.0)


def _heartbeat_loop(task_id: str, stop_event: threading.Event, started_at: str) -> None:
    while not stop_event.wait(12.0):
        try:
            task = get_task(task_id)
            write_worker_status(
                {
                    "pid": os.getpid(),
                    "status": "running",
                    "running": True,
                    "current_task_id": task_id,
                    "last_heartbeat": _utc_now(),
                    "started_at": started_at,
                }
            )
        except Exception:
            continue


def _handle_report_event(task_id: str, event: Dict[str, Any]) -> None:
    _raise_if_cancelled(task_id)
    if not isinstance(event, dict):
        return
    event_type = str(event.get("type") or "").strip()
    phase = str(event.get("phase") or "").strip() or "interpret"
    title = str(event.get("title") or "").strip()
    message = str(event.get("message") or "").strip()
    agent = str(event.get("agent") or "").strip()
    payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
    if event_type == "task.failed":
        LOGGER.warning(
            "report worker | callback event | task=%s type=%s phase=%s message=%s payload=%s",
            task_id,
            event_type,
            phase,
            message,
            payload,
        )
    if event_type == "phase.started":
        mark_task_progress(task_id, phase=phase, percentage=PHASE_PERCENTAGE.get(phase, 60), message=message or title or "阶段已开始。")
        if payload:
            append_event(
                task_id,
                event_type="phase.context",
                phase=phase,
                agent=agent,
                title=title,
                message=message,
                payload=payload,
            )
        return
    if event_type == "phase.progress":
        mark_task_progress(task_id, phase=phase, percentage=PHASE_PERCENTAGE.get(phase, 60), message=message or title or "阶段执行中。")
        if payload:
            append_event(
                task_id,
                event_type="phase.context",
                phase=phase,
                agent=agent,
                title=title,
                message=message,
                payload=payload,
            )
        return
    if event_type == "agent.started":
        mark_agent_started(
            task_id,
            agent=agent or "runtime",
            phase=phase,
            message=message or title or "Agent 已启动。",
            title=title,
            payload=payload,
        )
        return
    if event_type == "subagent.started":
        mark_agent_started(
            task_id,
            agent=agent or "runtime",
            phase=phase,
            message=message or title or "子代理已启动。",
            title=title,
            payload=payload,
        )
        return
    if event_type == "subagent.completed":
        from src.report.task_queue import mark_agent_completed  # type: ignore

        mark_agent_completed(
            task_id,
            agent=agent or "runtime",
            phase=phase,
            message=message or title or "子代理已完成。",
            title=title,
            payload=payload,
        )
        return
    if event_type == "agent.memo":
        append_agent_memo(
            task_id,
            agent=agent or "runtime",
            phase=phase,
            message=message or title or "Agent 已输出公开备忘录。",
            title=title,
            delta=str(event.get("delta") or "").strip(),
            payload=payload,
        )
        return
    if event_type == "todo.updated":
        update_todos(
            task_id,
            todos=payload.get("todos") if isinstance(payload.get("todos"), list) else [],
            phase=phase,
            message=message or title or "任务清单已更新。",
        )
        return
    if event_type == "tool.called":
        from src.report.task_queue import record_tool_call  # type: ignore

        record_tool_call(
            task_id,
            agent=agent or "runtime",
            phase=phase,
            title=title or "工具调用",
            message=message or "Agent 正在调用工具。",
            payload=payload,
        )
        return
    if event_type == "tool.result":
        from src.report.task_queue import record_tool_result  # type: ignore

        record_tool_result(
            task_id,
            agent=agent or "runtime",
            phase=phase,
            title=title or "工具回执",
            message=message or "Agent 已拿到工具结果。",
            payload=payload,
        )
        return
    if event_type == "artifact.ready":
        mark_artifact_ready(task_id, message=message or "报告产物已写入。", payload=payload)
        return
    append_event(
        task_id,
        event_type=event_type or "phase.progress",
        phase=phase,
        agent=agent,
        title=title,
        message=message,
        delta=str(event.get("delta") or "").strip(),
        payload=payload,
    )


def _failure_message(exc: Exception, diagnostic: Dict[str, Any]) -> str:
    category = str(diagnostic.get("category") or "").strip()
    if category == "model_connection":
        return "模型连接失败：当前环境无法访问上游模型服务。"
    closure_stage = str(diagnostic.get("closure_stage") or "").strip()
    if closure_stage == "fallback_synthesis_failed":
        return "总控未保存结构化结果，服务端补写失败。"
    if closure_stage == "structured_validation_failed":
        return "结构化结果已生成，但字段校验未通过。"
    if closure_stage == "agent_save_missing":
        return "总控未调用结构化保存，系统已尝试自动补写。"
    if closure_stage == "tool_round_limit_reached":
        return "任务达到工具回合上限，建议提高总控或子代理回合数后重试。"
    text = str(exc or "").strip()
    return text or "报告任务执行失败。"


def _build_failure_diagnostic(task_id: str, exc: Exception) -> Dict[str, Any]:
    task = get_task(task_id)
    cause = exc.__cause__ or exc.__context__
    extra = getattr(exc, "task_diagnostic", None)
    diagnostic: Dict[str, Any] = {
        "error_type": type(exc).__name__,
        "error_message": str(exc or "").strip(),
        "failed_phase": str(task.get("phase") or "").strip() or "prepare",
        "failed_actor": str(task.get("current_actor") or "").strip() or "report_coordinator",
        "current_operation": str(task.get("current_operation") or "").strip(),
    }
    if isinstance(extra, dict) and extra:
        diagnostic.update(extra)
    if cause is not None:
        diagnostic["root_cause_type"] = type(cause).__name__
        diagnostic["root_cause_message"] = str(cause or "").strip()

    combined_text = " ".join(
        part for part in [
            diagnostic.get("error_type"),
            diagnostic.get("error_message"),
            diagnostic.get("root_cause_type"),
            diagnostic.get("root_cause_message"),
        ]
        if str(part or "").strip()
    ).lower()
    if "apiconnectionerror" in combined_text or "connecterror" in combined_text or "winerror 10013" in combined_text:
        diagnostic.update(
            {
                "category": "model_connection",
                "retryable": True,
                "hint": "请检查当前机器到模型服务的网络连通性、代理配置、防火墙或安全软件拦截。",
            }
        )
    return diagnostic


def _raise_if_cancelled(task_id: str) -> None:
    if should_cancel(task_id):
        raise TaskCancelled("任务已按请求取消。")


def _structured_digest_from_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    task = payload.get("task") if isinstance(payload.get("task"), dict) else {}
    conclusion = payload.get("conclusion") if isinstance(payload.get("conclusion"), dict) else {}
    return {
        "topic": str(task.get("topic_label") or task.get("topic_identifier") or "").strip(),
        "range": {
            "start": str(task.get("start") or "").strip(),
            "end": str(task.get("end") or "").strip(),
        },
        "summary": str(conclusion.get("executive_summary") or "").strip(),
        "key_findings": [str(item).strip() for item in (conclusion.get("key_findings") or []) if str(item or "").strip()][:6],
        "key_risks": [str(item).strip() for item in (conclusion.get("key_risks") or []) if str(item or "").strip()][:6],
        "counts": {
            "timeline": len(payload.get("timeline") or []),
            "subjects": len(payload.get("subjects") or []),
            "evidence": len(payload.get("key_evidence") or []),
            "conflicts": len(payload.get("conflict_points") or []),
            "propagation": len(payload.get("propagation_features") or []),
            "risks": len(payload.get("risk_judgement") or []),
            "actions": len(payload.get("suggested_actions") or []),
            "citations": len(payload.get("citations") or []),
        },
    }


def _trust_from_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    conclusion = payload.get("conclusion") if isinstance(payload.get("conclusion"), dict) else {}
    evidence_blocks = payload.get("key_evidence") if isinstance(payload.get("key_evidence"), list) else []
    citations = payload.get("citations") if isinstance(payload.get("citations"), list) else []
    validation_notes = payload.get("validation_notes") if isinstance(payload.get("validation_notes"), list) else []

    unique_citation_ids = set()
    corroborated_blocks = 0
    confidence_values = []
    for item in evidence_blocks:
        if not isinstance(item, dict):
            continue
        citation_ids = {
            str(citation_id).strip()
            for citation_id in (item.get("citation_ids") or [])
            if str(citation_id or "").strip()
        }
        unique_citation_ids.update(citation_ids)
        if len(citation_ids) >= 2:
            corroborated_blocks += 1
        confidence = str(item.get("confidence") or "").strip().lower()
        confidence_values.append({"high": 1.0, "medium": 0.65, "low": 0.35}.get(confidence, 0.5))

    official_sources = 0
    for citation in citations:
        if not isinstance(citation, dict):
            continue
        source_type = str(citation.get("source_type") or "").strip().lower()
        if source_type in {"official", "government", "gov", "media_official", "official_media"}:
            official_sources += 1

    coverage_penalty = sum(
        1
        for note in validation_notes
        if isinstance(note, dict)
        and str(note.get("category") or "").strip().lower() == "coverage"
        and str(note.get("severity") or "").strip().lower() in {"high", "medium"}
    )

    total_citations = max(len(citations), 1)
    total_evidence = max(len(evidence_blocks), 1)
    evidence_coverage = min(len(unique_citation_ids) / total_citations, 1.0)
    if coverage_penalty:
        evidence_coverage = max(0.0, evidence_coverage - 0.15 * coverage_penalty)

    return {
        "status": "ready",
        "confidence_label": str(conclusion.get("confidence_label") or "").strip() or "待评估",
        "evidence_coverage": round(evidence_coverage, 4),
        "corroborated_coverage": round(corroborated_blocks / total_evidence, 4),
        "official_source_coverage": round(official_sources / total_citations, 4),
        "avg_signal": round(sum(confidence_values) / max(len(confidence_values), 1), 4),
    }


def _deep_todos_snapshot(stage: str) -> list[Dict[str, Any]]:
    order = ["scope", "retrieval", "evidence", "structure", "writing", "validation", "persist"]
    labels = {
        "scope": "范围确认",
        "retrieval": "检索路由",
        "evidence": "证据整理",
        "structure": "结构分析",
        "writing": "文稿生成",
        "validation": "质量校验",
        "persist": "审批与存储",
    }
    progress_map = {
        "interpret": {"scope": "completed", "retrieval": "running", "evidence": "pending", "structure": "pending", "writing": "pending", "validation": "pending", "persist": "pending"},
        "review": {"scope": "completed", "retrieval": "completed", "evidence": "completed", "structure": "completed", "writing": "running", "validation": "pending", "persist": "pending"},
        "persist": {"scope": "completed", "retrieval": "completed", "evidence": "completed", "structure": "completed", "writing": "completed", "validation": "completed", "persist": "running"},
        "completed": {"scope": "completed", "retrieval": "completed", "evidence": "completed", "structure": "completed", "writing": "completed", "validation": "completed", "persist": "completed"},
    }
    selected = progress_map.get(stage, progress_map["interpret"])
    return [{"id": item, "label": labels[item], "status": selected[item]} for item in order]


def _maybe_update_fallback_todos(task_id: str, *, stage: str, phase: str, message: str) -> None:
    task = get_task(task_id)
    todos = task.get("todos") if isinstance(task.get("todos"), list) else []
    if todos:
        return
    update_todos(
        task_id,
        todos=_deep_todos_snapshot(stage),
        phase=phase,
        message=message,
    )


def _has_rejected_approval(task: Dict[str, Any]) -> bool:
    approvals = task.get("approvals") if isinstance(task.get("approvals"), list) else []
    return any(
        isinstance(item, dict)
        and str(item.get("status") or "").strip() == "resolved"
        and str(item.get("decision") or "").strip().lower() == "reject"
        for item in approvals
    )


def _build_resume_payload_from_task(task: Dict[str, Any]) -> Any:
    approvals = task.get("approvals") if isinstance(task.get("approvals"), list) else []
    resolved = [item for item in approvals if isinstance(item, dict) and str(item.get("status") or "").strip() == "resolved"]
    if not resolved:
        return None
    grouped: Dict[str, Dict[int, Dict[str, Any]]] = {}
    for item in resolved:
        interrupt_id = str(item.get("interrupt_id") or "").strip()
        if not interrupt_id:
            continue
        decision_index = int(item.get("decision_index") or 0)
        tool_name = str(item.get("tool_name") or "").strip()
        action = item.get("action") if isinstance(item.get("action"), dict) else {}
        original_args = action.get("tool_args") if isinstance(action.get("tool_args"), dict) else {}
        decision_type = str(item.get("decision") or "").strip().lower()
        if decision_type == "edit":
            edited = item.get("edited_action") if isinstance(item.get("edited_action"), dict) else {}
            grouped.setdefault(interrupt_id, {})[decision_index] = {
                "type": "edit",
                "edited_action": {
                    "name": tool_name,
                    "args": {**original_args, **edited},
                },
            }
        elif decision_type == "reject":
            grouped.setdefault(interrupt_id, {})[decision_index] = {
                "type": "reject",
                "message": "人工审批拒绝了该动作。",
            }
        else:
            grouped.setdefault(interrupt_id, {})[decision_index] = {"type": "approve"}
    if not grouped:
        return None
    ordered = {
        interrupt_id: {"decisions": [entries[index] for index in sorted(entries.keys())]}
        for interrupt_id, entries in grouped.items()
    }
    if len(ordered) == 1:
        return next(iter(ordered.values()))
    return ordered


def _utc_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


if __name__ == "__main__":
    main()
