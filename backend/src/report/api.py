"""Report generation API."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from flask import Blueprint, Response, jsonify, request, stream_with_context

from server_support import error, resolve_topic_identifier, success
from server_support.archive_locator import ArchiveLocator, compose_folder_name
from server_support.topic_context import TopicContext, resolve_context
from src.fetch.data_fetch import get_topic_available_date_range
from src.project import get_project_manager
from src.utils.setting.paths import bucket

from .deep_report import AI_FULL_REPORT_CACHE_FILENAME, REPORT_CACHE_FILENAME, generate_full_report_payload, generate_report_payload
from .runtime_infra import resolve_runtime_profile
from .task_queue import (
    cancel_task,
    create_task,
    ensure_worker_running,
    find_existing_task,
    find_latest_task,
    get_task,
    list_tasks,
    load_events_since,
    resolve_approval,
    retry_task,
)

PROJECT_MANAGER = get_project_manager()
report_bp = Blueprint("report", __name__)


def _resolve_topic(topic_param: str, project_param: str, dataset_id: str) -> Tuple[str, str]:
    if not topic_param and not project_param:
        raise ValueError("Missing required field(s): topic or project")
    payload: Dict[str, Any] = {}
    if topic_param:
        payload["topic"] = topic_param
    if project_param:
        payload["project"] = project_param
    if dataset_id:
        payload["dataset_id"] = dataset_id
    topic_identifier, display_name, _, _ = resolve_topic_identifier(payload, PROJECT_MANAGER)
    return topic_identifier, display_name


def _build_topic_context(topic_param: str, project_param: str, dataset_id: str) -> TopicContext:
    payload: Dict[str, Any] = {}
    if topic_param:
        payload["topic"] = topic_param
    if project_param:
        payload["project"] = project_param
    if dataset_id:
        payload["dataset_id"] = dataset_id
    return resolve_context(payload, PROJECT_MANAGER)


def _resolve_report_range(
    topic_param: str,
    project_param: str,
    dataset_id: str,
) -> Tuple[TopicContext, List[Dict[str, Any]], List[Dict[str, Any]], Dict[str, Any]]:
    ctx = _build_topic_context(topic_param, project_param, dataset_id)
    locator = ArchiveLocator(ctx)
    analyze_records = locator.list_history("analyze")
    report_records = locator.list_history("reports")
    fetch_range = get_topic_available_date_range(topic_param or ctx.display_name or ctx.identifier)
    return ctx, analyze_records, report_records, fetch_range if isinstance(fetch_range, dict) else {}


def _utc_now_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def _range_payload(start: str, end: Optional[str]) -> Dict[str, str]:
    start_text = str(start or "").strip()
    end_text = str(end or "").strip() or start_text
    return {"start": start_text, "end": end_text}


def _build_step_log(*, step_id: str, label: str, status: str, message: str, progress: int, time_text: str = "") -> Dict[str, Any]:
    value = max(0, min(100, int(progress)))
    return {
        "id": step_id,
        "label": label,
        "status": status,
        "message": message,
        "progress": value,
        "time": time_text,
    }


def _load_report_cache_payload(report_cache: Path) -> Dict[str, Any]:
    if not report_cache.exists():
        return {}
    try:
        with report_cache.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _artifact_status(manifest: Dict[str, Any], artifact_key: str) -> str:
    record = manifest.get(artifact_key)
    if not isinstance(record, dict):
        return ""
    return str(record.get("status") or "").strip()


def _artifact_ready(manifest: Dict[str, Any], artifact_key: str) -> bool:
    return _artifact_status(manifest, artifact_key) == "ready"


def _task_summary_payload(
    *,
    topic: str,
    topic_identifier: str,
    start: str,
    end: Optional[str],
    stage: str,
    status: str,
    message: str,
    updated_at: str,
    artifact_manifest: Dict[str, Any],
    report_ir_summary: Dict[str, Any],
    structured_result_digest: Dict[str, Any],
    approvals: List[Dict[str, Any]],
    recent_events: List[Dict[str, Any]],
    task_details: Optional[Dict[str, Any]] = None,
    cache_paths: Optional[Dict[str, str]] = None,
    worker_details: Optional[Dict[str, Any]] = None,
    todos: Optional[List[Dict[str, Any]]] = None,
    agents: Optional[List[Dict[str, Any]]] = None,
    trust: Optional[Dict[str, Any]] = None,
    run_state: Optional[Dict[str, Any]] = None,
    orchestrator_state: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    structured_ready = _artifact_ready(artifact_manifest, "structured_projection")
    full_ready = _artifact_ready(artifact_manifest, "full_markdown")
    percentage = int((task_details or {}).get("percentage") or 0)
    stage_normalized = {
        "prepare": "planning",
        "analyze": "planning",
        "explain": "planning",
        "interpret": "exploration",
        "write": "structure",
    }.get(stage, stage)
    planning_status = "ok" if structured_ready or full_ready or stage_normalized not in {"planning"} else ("running" if stage_normalized == "planning" and status == "running" else "queued")
    exploration_status = "ok" if structured_ready or full_ready or stage_normalized not in {"planning", "exploration"} else ("running" if stage_normalized == "exploration" and status == "running" else "queued")
    structure_status = "ok" if structured_ready or full_ready or stage_normalized not in {"planning", "exploration", "structure"} else ("running" if stage_normalized == "structure" and status == "running" else "queued")
    report_status = "ok" if structured_ready or full_ready else ("running" if stage_normalized in {"compile", "review"} and status in {"running", "waiting_approval"} else "queued")
    cache_status = "ok" if full_ready else ("running" if stage == "persist" and status in {"running", "waiting_approval"} else "queued")
    steps = [
        _build_step_log(
            step_id="planning",
            label="任务规划",
            status=planning_status,
            message="建立根图、任务边界与执行清单。",
            progress=100 if planning_status == "ok" else (percentage if planning_status == "running" else 0),
            time_text=updated_at,
        ),
        _build_step_log(
            step_id="exploration",
            label="本地探索",
            status=exploration_status,
            message="围绕本地归档、基础分析和专题资料完成探索。",
            progress=100 if exploration_status == "ok" else (percentage if exploration_status == "running" else 0),
            time_text=updated_at,
        ),
        _build_step_log(
            step_id="structure",
            label="结构综合",
            status=structure_status,
            message="汇总探索产物并形成结构化报告种子。",
            progress=100 if structure_status == "ok" else (percentage if structure_status == "running" else 0),
            time_text=updated_at,
        ),
        _build_step_log(
            step_id="compile",
            label="正式编译",
            status=report_status,
            message="执行正式文稿编译、验证和语义门禁。",
            progress=100 if report_status == "ok" else (percentage if report_status == "running" else 0),
            time_text=updated_at,
        ),
        _build_step_log(
            step_id="persist",
            label="写入结果",
            status=cache_status,
            message="写入最终报告缓存并返回查看页。",
            progress=100 if cache_status == "ok" else (percentage if cache_status == "running" else 0),
            time_text=updated_at,
        ),
    ]
    if status == "failed":
        for step in steps:
            if step["id"] in {"structure", "compile", "persist"}:
                step["status"] = "error"
                step["message"] = message or "任务执行失败。"
                break
    if status == "cancelled":
        for step in steps:
            if step["status"] == "running":
                step["status"] = "error"
                step["message"] = "任务已取消。"
                break
    return {
        "topic": topic,
        "topic_identifier": topic_identifier,
        "range": _range_payload(start, end),
        "state": {
            "stage": stage_normalized,
            "status": status,
            "message": message,
            "updated_at": updated_at,
        },
        "summary": {
            "status": (
                "running"
                if status in {"queued", "running", "waiting_approval"}
                else ("ok" if status == "completed" else ("pending" if status in {"pending", "idle", ""} else "error"))
            ),
            "message": message or ("已找到历史结果，可直接查看。" if structured_ready or full_ready else "当前区间暂无执行中的报告任务。"),
        },
        "steps": steps,
        "task": {
            "id": str((task_details or {}).get("id") or "").strip(),
            "thread_id": str((task_details or {}).get("thread_id") or "").strip(),
            "status": status,
            "phase": stage_normalized,
            "percentage": percentage,
            "worker_pid": int((worker_details or {}).get("worker_pid") or 0),
            "child_pid": int((worker_details or {}).get("child_pid") or 0),
            "cancel_requested": bool((task_details or {}).get("cancel_requested")),
            "agents": agents or [],
            "subagents": agents or [],
            "todos": todos or [],
            "approvals": approvals,
            "run_state": run_state or {},
            "orchestrator_state": orchestrator_state or {},
            "current_actor": str((worker_details or {}).get("current_actor") or "").strip(),
            "current_operation": str((worker_details or {}).get("current_operation") or "").strip(),
            "last_diagnostic": (worker_details or {}).get("last_diagnostic") if isinstance((worker_details or {}).get("last_diagnostic"), dict) else {},
            "structured_result_digest": structured_result_digest,
            "report_ir_summary": report_ir_summary,
            "artifact_manifest": artifact_manifest,
            "trust": trust or {},
            "recent_events": recent_events,
        },
        "explain": {
            "ready": structured_ready or full_ready,
            "source": "structured_projection" if structured_ready or full_ready else "pending",
        },
        "report": {
            "cache_exists": structured_ready,
            "cache_path": str((cache_paths or {}).get("report_cache_path") or "").strip(),
            "full_cache_exists": full_ready,
            "full_cache_path": str((cache_paths or {}).get("full_report_cache_path") or "").strip(),
            "artifact_manifest": artifact_manifest,
        },
    }


def _extract_cache_meta(payload: Dict[str, Any]) -> Dict[str, Any]:
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    if metadata:
        return metadata
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    return meta if isinstance(meta, dict) else {}


def _build_historical_progress_payload(ctx: TopicContext, start: str, end: Optional[str]) -> Dict[str, Any]:
    folder = compose_folder_name(start, end)
    report_dir = bucket("reports", ctx.identifier, folder)
    report_cache = report_dir / REPORT_CACHE_FILENAME
    full_cache = report_dir / AI_FULL_REPORT_CACHE_FILENAME
    structured_payload = _load_report_cache_payload(report_cache)
    full_payload = _load_report_cache_payload(full_cache)
    structured_meta = _extract_cache_meta(structured_payload)
    full_meta = _extract_cache_meta(full_payload)
    artifact_manifest = {}
    for candidate in (
        structured_meta.get("artifact_manifest"),
        structured_payload.get("artifact_manifest"),
        full_meta.get("artifact_manifest"),
        full_payload.get("artifact_manifest"),
    ):
        if isinstance(candidate, dict) and candidate:
            artifact_manifest = candidate
            break
    report_ir_summary = {}
    for candidate in (
        structured_meta.get("report_ir_summary"),
        structured_payload.get("report_ir_summary"),
        full_meta.get("report_ir_summary"),
        full_payload.get("report_ir_summary"),
    ):
        if isinstance(candidate, dict) and candidate:
            report_ir_summary = candidate
            break
    has_history = bool(structured_payload or full_payload or artifact_manifest)
    stage = "completed" if has_history else ""
    status = "completed" if has_history else "pending"
    message = "已找到历史结果，可直接查看。" if has_history else "当前区间暂无执行中的报告任务。"
    updated_at = str(
        (full_meta.get("generated_at") or full_meta.get("updated_at") or structured_meta.get("generated_at") or structured_meta.get("updated_at") or "")
    ).strip()
    structured_result_digest = {
        "summary": str(report_ir_summary.get("summary") or "").strip(),
        "counts": report_ir_summary.get("counts") if isinstance(report_ir_summary.get("counts"), dict) else {},
        "utility_assessment": report_ir_summary.get("utility_assessment") if isinstance(report_ir_summary.get("utility_assessment"), dict) else {},
        "fallback_trace_count": (
            (report_ir_summary.get("utility_assessment") or {}).get("fallback_trace_count")
            if isinstance(report_ir_summary.get("utility_assessment"), dict)
            else 0
        ),
        "source": "historical_cache" if has_history else "empty",
    }
    return _task_summary_payload(
        topic=ctx.display_name or ctx.identifier,
        topic_identifier=ctx.identifier,
        start=start,
        end=end,
        stage=stage,
        status=status,
        message=message,
        updated_at=updated_at,
        artifact_manifest=artifact_manifest,
        report_ir_summary=report_ir_summary,
        structured_result_digest=structured_result_digest,
        approvals=[],
        recent_events=[],
        cache_paths={
            "report_cache_path": str(report_cache) if structured_payload else "",
            "full_report_cache_path": str(full_cache) if full_payload else "",
        },
    )


def _build_task_progress_payload(task: Dict[str, Any]) -> Dict[str, Any]:
    recent_events = task.get("recent_events") if isinstance(task.get("recent_events"), list) else []
    artifacts = task.get("artifacts") if isinstance(task.get("artifacts"), dict) else {}
    trust = task.get("trust") if isinstance(task.get("trust"), dict) else {}
    run_state = task.get("run_state") if isinstance(task.get("run_state"), dict) else {}
    approvals = task.get("approvals") if isinstance(task.get("approvals"), list) else []
    todos = task.get("todos") if isinstance(task.get("todos"), list) else []
    structured_digest = task.get("structured_result_digest") if isinstance(task.get("structured_result_digest"), dict) else {}
    report_ir_summary = task.get("report_ir_summary") if isinstance(task.get("report_ir_summary"), dict) else {}
    artifact_manifest = task.get("artifact_manifest") if isinstance(task.get("artifact_manifest"), dict) else {}
    return _task_summary_payload(
        topic=str(task.get("topic") or task.get("topic_identifier") or "").strip(),
        topic_identifier=str(task.get("topic_identifier") or "").strip(),
        start=str(task.get("start") or ""),
        end=str(task.get("end") or ""),
        stage=str(task.get("phase") or "").strip(),
        status=str(task.get("status") or "").strip() or "queued",
        message=str(task.get("message") or "").strip(),
        updated_at=str(task.get("updated_at") or "").strip(),
        artifact_manifest=artifact_manifest,
        report_ir_summary=report_ir_summary,
        structured_result_digest=structured_digest,
        approvals=approvals,
        recent_events=recent_events,
        task_details=task,
        cache_paths={
            "report_cache_path": str(artifacts.get("report_cache_path") or "").strip(),
            "full_report_cache_path": str(artifacts.get("full_report_cache_path") or "").strip(),
        },
        worker_details={
            "worker_pid": task.get("worker_pid"),
            "child_pid": task.get("child_pid"),
            "current_actor": task.get("current_actor"),
            "current_operation": task.get("current_operation"),
            "last_diagnostic": task.get("last_diagnostic"),
        },
        todos=todos,
        agents=task.get("agents") or [],
        trust=trust,
        run_state=run_state,
        orchestrator_state=task.get("orchestrator_state") if isinstance(task.get("orchestrator_state"), dict) else {},
    )


def _create_or_reuse_task(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    topic_param = str(payload.get("topic") or "").strip()
    project_param = str(payload.get("project") or "").strip()
    dataset_id = str(payload.get("dataset_id") or "").strip()
    start = str(payload.get("start") or "").strip()
    end = str(payload.get("end") or "").strip() or start
    mode = str(payload.get("mode") or "fast").strip().lower() or "fast"
    if not start:
        raise ValueError("Missing required field(s): start")
    resolve_runtime_profile(purpose="report-api")
    ctx = _build_topic_context(topic_param, project_param, dataset_id)
    existing = find_existing_task(
        topic_identifier=ctx.identifier,
        start=start,
        end=end,
        mode=mode,
        statuses=["queued", "running", "waiting_approval"],
    )
    if existing:
        return existing, True
    created = create_task(
        {
            "topic": ctx.display_name or ctx.identifier,
            "topic_identifier": ctx.identifier,
            "start": start,
            "end": end,
            "mode": mode,
            "project": project_param,
            "dataset_id": dataset_id,
            "aliases": ctx.aliases or [],
        }
    )
    return created, False


@report_bp.get("")
def get_report_payload():
    topic_param = str(request.args.get("topic") or "").strip()
    project_param = str(request.args.get("project") or "").strip()
    dataset_id = str(request.args.get("dataset_id") or "").strip()
    start = str(request.args.get("start") or "").strip()
    end = str(request.args.get("end") or "").strip() or None
    if not start:
        return error("Missing required field(s): start")
    try:
        topic_identifier, display_name = _resolve_topic(topic_param, project_param, dataset_id)
        payload = generate_report_payload(
            topic_identifier,
            start,
            end,
            topic_label=display_name,
            regenerate=False,
        )
    except ValueError as exc:
        return error(str(exc), status_code=404)
    except Exception as exc:
        return error(f"报告生成失败: {str(exc)}", status_code=500)
    return success({"data": payload})


@report_bp.get("/full")
def get_full_report_payload():
    topic_param = str(request.args.get("topic") or "").strip()
    project_param = str(request.args.get("project") or "").strip()
    dataset_id = str(request.args.get("dataset_id") or "").strip()
    start = str(request.args.get("start") or "").strip()
    end = str(request.args.get("end") or "").strip() or None
    regenerate_raw = str(request.args.get("regenerate") or "").strip().lower()
    regenerate = regenerate_raw in {"1", "true", "yes", "on"}
    if not start:
        return error("Missing required field(s): start")
    try:
        topic_identifier, display_name = _resolve_topic(topic_param, project_param, dataset_id)
        payload = generate_full_report_payload(
            topic_identifier,
            start,
            end,
            topic_label=display_name,
            regenerate=regenerate,
        )
    except ValueError as exc:
        return error(str(exc), status_code=404)
    except Exception as exc:
        return error(f"AI 完整报告生成失败: {str(exc)}", status_code=500)
    return success({"data": payload})


@report_bp.get("/availability")
def get_report_availability():
    topic_param = str(request.args.get("topic") or "").strip()
    project_param = str(request.args.get("project") or "").strip()
    dataset_id = str(request.args.get("dataset_id") or "").strip()
    if not topic_param and not project_param:
        return error("Missing required field(s): topic or project")
    try:
        ctx, analyze_records, report_records, fetch_range = _resolve_report_range(topic_param, project_param, dataset_id)
    except ValueError as exc:
        return error(str(exc))
    latest_analyze = analyze_records[0] if analyze_records else {}
    latest_report = report_records[0] if report_records else {}
    range_payload = {
        "start": str(latest_analyze.get("start") or fetch_range.get("start") or "").strip(),
        "end": str(latest_analyze.get("end") or fetch_range.get("end") or fetch_range.get("start") or "").strip(),
    }
    has_analyze = bool(analyze_records)
    message = ""
    if not has_analyze:
        message = "当前专题暂无基础分析结果，点击“生成”时会先自动补跑 analyze。" if range_payload["start"] else "当前专题暂无可用数据区间，无法生成报告。"
    return success(
        {
            "data": {
                "topic": ctx.display_name,
                "topic_identifier": ctx.identifier,
                "range": range_payload,
                "has_analyze_history": has_analyze,
                "has_report_history": bool(report_records),
                "latest_analyze": latest_analyze,
                "latest_report": latest_report,
                "fetch_range": fetch_range,
                "message": message,
            }
        }
    )


@report_bp.get("/history")
def get_report_history():
    topic_param = str(request.args.get("topic") or "").strip()
    project_param = str(request.args.get("project") or "").strip()
    dataset_id = str(request.args.get("dataset_id") or "").strip()
    payload: Dict[str, Any] = {}
    if topic_param:
        payload["topic"] = topic_param
    if project_param:
        payload["project"] = project_param
    if dataset_id:
        payload["dataset_id"] = dataset_id
    try:
        ctx = resolve_context(payload, PROJECT_MANAGER)
    except ValueError:
        if not topic_param:
            return error("Missing required field(s): topic or project")
        ctx = TopicContext(identifier=topic_param, display_name=topic_param, aliases=[value for value in [topic_param, project_param] if value])
    locator = ArchiveLocator(ctx)
    return success({"records": locator.list_history("reports"), "topic": ctx.display_name, "topic_identifier": ctx.identifier})


@report_bp.get("/progress")
def get_report_progress():
    topic_param = str(request.args.get("topic") or "").strip()
    project_param = str(request.args.get("project") or "").strip()
    dataset_id = str(request.args.get("dataset_id") or "").strip()
    start = str(request.args.get("start") or "").strip()
    end = str(request.args.get("end") or "").strip() or None
    if not start:
        return error("Missing required field(s): start")
    try:
        ctx = _build_topic_context(topic_param, project_param, dataset_id)
    except ValueError as exc:
        return error(str(exc))
    task = find_latest_task(
        topic_identifier=ctx.identifier,
        start=start,
        end=str(end or start),
        statuses=["queued", "running", "waiting_approval", "completed", "failed", "cancelled"],
    )
    if task:
        return success({"data": _build_task_progress_payload(task)})
    return success({"data": _build_historical_progress_payload(ctx, start, end)})


@report_bp.post("/regenerate")
def regenerate_report_payload():
    payload = request.get_json(silent=True) or {}
    try:
        task, reused = _create_or_reuse_task(payload)
        worker = ensure_worker_running()
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400
    except Exception as exc:
        return jsonify({"status": "error", "message": f"报告任务提交失败: {str(exc)}"}), 500
    return jsonify({"status": "accepted", "reused": reused, "task": task, "worker": worker}), 200


@report_bp.post("/tasks")
def create_report_task():
    payload = request.get_json(silent=True) or {}
    try:
        task, reused = _create_or_reuse_task(payload)
        worker = ensure_worker_running()
    except ValueError as exc:
        return error(str(exc), 400)
    except Exception as exc:
        return error(f"报告任务创建失败: {str(exc)}", 500)
    return success(
        {
            "task": task,
            "task_id": str(task.get("id") or "").strip(),
            "thread_id": str(task.get("thread_id") or "").strip(),
            "run_state": task.get("run_state") if isinstance(task.get("run_state"), dict) else {},
            "worker": worker,
            "reused": reused,
        }
    )


@report_bp.get("/tasks")
def get_report_tasks():
    topic = str(request.args.get("topic") or "").strip()
    status = str(request.args.get("status") or "").strip()
    try:
        payload = list_tasks(topic=topic, status=status, limit=int(request.args.get("limit") or 50))
    except Exception as exc:
        return error(f"读取报告任务失败: {str(exc)}", 500)
    return success(payload)


@report_bp.get("/tasks/<task_id>")
def get_report_task(task_id: str):
    try:
        return success({"task": get_task(task_id)})
    except LookupError as exc:
        return error(str(exc), 404)


@report_bp.post("/tasks/<task_id>/cancel")
def cancel_report_task(task_id: str):
    try:
        task = cancel_task(task_id)
    except LookupError as exc:
        return error(str(exc), 404)
    except ValueError as exc:
        return error(str(exc), 400)
    return success({"task": task})


@report_bp.post("/tasks/<task_id>/retry")
def retry_report_task(task_id: str):
    try:
        task = retry_task(task_id)
        worker = ensure_worker_running()
    except LookupError as exc:
        return error(str(exc), 404)
    except ValueError as exc:
        return error(str(exc), 400)
    return success({"task": task, "worker": worker})


@report_bp.post("/tasks/<task_id>/approvals/<approval_id>")
def resolve_report_approval(task_id: str, approval_id: str):
    payload = request.get_json(silent=True) or {}
    try:
        task = resolve_approval(
            task_id,
            approval_id=approval_id,
            decision=str(payload.get("decision") or "").strip(),
            edited_action=payload.get("edited_action") if isinstance(payload.get("edited_action"), dict) else None,
        )
        worker = ensure_worker_running()
    except LookupError as exc:
        return error(str(exc), 404)
    except ValueError as exc:
        return error(str(exc), 400)
    return success({"task": task, "worker": worker})


@report_bp.get("/tasks/<task_id>/stream")
def stream_report_task(task_id: str):
    try:
        get_task(task_id)
    except LookupError as exc:
        return error(str(exc), 404)
    since_raw = str(request.args.get("since_id") or request.headers.get("Last-Event-ID") or "").strip()
    try:
        since_id = int(since_raw) if since_raw else 0
    except ValueError:
        since_id = 0

    def _format_event(event_name: str, data: Dict[str, Any], event_id: Optional[int] = None) -> str:
        parts: List[str] = []
        if event_id is not None:
            parts.append(f"id: {event_id}")
        parts.append(f"event: {event_name}")
        parts.append(f"data: {json.dumps(data, ensure_ascii=False)}")
        return "\n".join(parts) + "\n\n"

    def _stream():
        last_id = since_id
        heartbeat_at = time.time()
        yield "retry: 2500\n\n"
        while True:
            try:
                events = load_events_since(task_id, last_id)
                current_task = get_task(task_id)
            except LookupError:
                break
            for item in events:
                event_id = int(item.get("event_id") or 0)
                if event_id > last_id:
                    last_id = event_id
                yield _format_event(str(item.get("type") or "message"), item, event_id=event_id)
            if time.time() - heartbeat_at >= 12:
                heartbeat_at = time.time()
                yield _format_event(
                    "heartbeat",
                    {
                        "task_id": task_id,
                        "ts": _utc_now_text(),
                        "phase": current_task.get("phase"),
                        "status": current_task.get("status"),
                        "message": current_task.get("message"),
                        "event_id": last_id,
                    },
                    event_id=None,
                )
            if str(current_task.get("status") or "") in {"completed", "failed", "cancelled"} and not events:
                yield _format_event(
                    "done",
                    {
                        "task_id": task_id,
                        "status": current_task.get("status"),
                        "event_id": last_id,
                    },
                )
                break
            time.sleep(1.0)

    response = Response(stream_with_context(_stream()), mimetype="text/event-stream")
    response.headers["Cache-Control"] = "no-cache"
    response.headers["X-Accel-Buffering"] = "no"
    return response
