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
from src.utils.setting.paths import bucket, ensure_bucket, get_logs_root

from .runtime import ANALYZE_FILE_MAP, collect_explain_outputs
from .deep_report import (
    AI_FULL_REPORT_CACHE_FILENAME,
    REPORT_CACHE_FILENAME,
    generate_full_report_payload,
    generate_report_payload,
)
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
REPORT_PROGRESS_FILENAME = "_progress.json"
AI_SUMMARY_FILENAME = "ai_summary.json"


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


def _report_progress_path(ctx: TopicContext, start: str, end: Optional[str], *, ensure_dir: bool = False) -> Path:
    folder = compose_folder_name(start, end)
    report_dir = ensure_bucket("reports", ctx.identifier, folder) if ensure_dir else bucket("reports", ctx.identifier, folder)
    return report_dir / REPORT_PROGRESS_FILENAME


def _load_progress_payload(ctx: TopicContext, start: str, end: Optional[str]) -> Dict[str, Any]:
    path = _report_progress_path(ctx, start, end)
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _resolve_analyze_log_path(ctx: TopicContext, start: str) -> Path:
    logs_root = get_logs_root()
    candidates: List[str] = []
    for value in [ctx.identifier, *(ctx.aliases or [])]:
        token = str(value or "").strip()
        if token and token not in candidates:
            candidates.append(token)
    for candidate in candidates:
        path = logs_root / candidate / start / f"{candidate}_{start}.log"
        if path.exists():
            return path
    return logs_root / ctx.identifier / start / f"{ctx.identifier}_{start}.log"


def _resolve_report_log_path(ctx: TopicContext, start: str, end: Optional[str]) -> Path:
    folder = compose_folder_name(start, end)
    logger_topic = f"ReportStructured_{ctx.identifier}"
    return get_logs_root() / logger_topic / folder / f"{logger_topic}_{folder}.log"


def _read_log_tail(path: Path, *, max_lines: int = 20) -> List[str]:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as fh:
            lines = [line.rstrip() for line in fh.readlines() if line.strip()]
        return lines[-max_lines:]
    except Exception:
        return []


def _summarise_log_line(line: str) -> str:
    text = str(line or "").strip()
    parts = text.split(" - ", 3)
    return parts[3].strip() if len(parts) == 4 else text


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


def _load_json_payload(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _build_task_progress_payload(task: Dict[str, Any]) -> Dict[str, Any]:
    recent_events = task.get("recent_events") if isinstance(task.get("recent_events"), list) else []
    artifacts = task.get("artifacts") if isinstance(task.get("artifacts"), dict) else {}
    trust = task.get("trust") if isinstance(task.get("trust"), dict) else {}
    run_state = task.get("run_state") if isinstance(task.get("run_state"), dict) else {}
    approvals = task.get("approvals") if isinstance(task.get("approvals"), list) else []
    todos = task.get("todos") if isinstance(task.get("todos"), list) else []
    structured_digest = task.get("structured_result_digest") if isinstance(task.get("structured_result_digest"), dict) else {}
    explain_ready = bool(artifacts.get("report_ready"))
    full_report_ready = bool(artifacts.get("full_report_ready"))
    stage = str(task.get("phase") or "").strip()
    status = str(task.get("status") or "").strip() or "queued"
    updated_at = str(task.get("updated_at") or "").strip()
    message = str(task.get("message") or "").strip()
    steps = [
        _build_step_log(
            step_id="prepare",
            label="准备数据",
            status="ok" if stage not in {"prepare", "queued"} else ("running" if status in {"queued", "running"} else status),
            message="检查基础产物与任务入队状态。",
            progress=100 if stage not in {"prepare", "queued"} else int(task.get("percentage") or 0),
            time_text=updated_at,
        ),
        _build_step_log(
            step_id="analyze",
            label="基础分析",
            status="ok" if stage not in {"prepare", "queued", "analyze"} else ("running" if stage == "analyze" and status == "running" else "queued"),
            message="必要时补跑 analyze，确保统计结果齐备。",
            progress=100 if stage not in {"prepare", "queued", "analyze"} else (int(task.get("percentage") or 0) if stage == "analyze" else 0),
            time_text=updated_at,
        ),
        _build_step_log(
            step_id="explain",
            label="总体解读",
            status="ok" if stage not in {"prepare", "queued", "analyze", "explain"} else ("running" if stage == "explain" and status == "running" else "queued"),
            message="检查或补齐总体文字解读。",
            progress=100 if stage not in {"prepare", "queued", "analyze", "explain"} else (int(task.get("percentage") or 0) if stage == "explain" else 0),
            time_text=updated_at,
        ),
        _build_step_log(
            step_id="report",
            label="报告研判",
            status="ok" if stage in {"write", "review", "persist", "completed"} else ("running" if stage == "interpret" and status == "running" else "queued"),
            message="解释与主题 agent 正在生成研判结构。",
            progress=100 if stage in {"write", "review", "persist", "completed"} else (int(task.get("percentage") or 0) if stage == "interpret" else 0),
            time_text=updated_at,
        ),
        _build_step_log(
            step_id="cache",
            label="报告缓存",
            status="ok" if status == "completed" else ("running" if stage in {"persist", "review", "write"} and status == "running" else "queued"),
            message="写入最终报告缓存并返回查看页。",
            progress=100 if status == "completed" else (int(task.get("percentage") or 0) if stage == "persist" else 0),
            time_text=updated_at,
        ),
    ]
    if status == "failed":
        for step in steps:
            if step["id"] in {"report", "cache"}:
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
        "topic": str(task.get("topic") or task.get("topic_identifier") or "").strip(),
        "topic_identifier": str(task.get("topic_identifier") or "").strip(),
        "range": _range_payload(str(task.get("start") or ""), str(task.get("end") or "")),
        "state": {
            "stage": stage,
            "status": status,
            "message": message,
            "updated_at": updated_at,
        },
        "summary": {
            "status": "running" if status in {"queued", "running", "waiting_approval"} else ("ok" if status == "completed" else "error"),
            "message": message or "当前区间暂无执行中的报告任务。",
        },
        "steps": steps,
        "task": {
            "id": str(task.get("id") or "").strip(),
            "thread_id": str(task.get("thread_id") or "").strip(),
            "status": status,
            "phase": stage,
            "percentage": int(task.get("percentage") or 0),
            "worker_pid": int(task.get("worker_pid") or 0),
            "child_pid": int(task.get("child_pid") or 0),
            "cancel_requested": bool(task.get("cancel_requested")),
            "agents": task.get("agents") or [],
            "subagents": task.get("agents") or [],
            "todos": todos,
            "approvals": approvals,
            "run_state": run_state,
            "orchestrator_state": task.get("orchestrator_state") if isinstance(task.get("orchestrator_state"), dict) else {},
            "current_actor": str(task.get("current_actor") or "").strip(),
            "current_operation": str(task.get("current_operation") or "").strip(),
            "last_diagnostic": task.get("last_diagnostic") if isinstance(task.get("last_diagnostic"), dict) else {},
            "structured_result_digest": structured_digest,
            "trust": trust,
            "recent_events": recent_events,
        },
        "explain": {
            "ready": explain_ready,
            "source": "legacy_rag" if explain_ready else "fallback",
        },
        "report": {
            "cache_exists": bool(artifacts.get("report_ready")),
            "cache_path": str(artifacts.get("report_cache_path") or "").strip(),
            "full_cache_exists": full_report_ready,
            "full_cache_path": str(artifacts.get("full_report_cache_path") or "").strip(),
        },
    }


def _collect_legacy_report_progress(ctx: TopicContext, start: str, end: Optional[str]) -> Dict[str, Any]:
    state = _load_progress_payload(ctx, start, end)
    folder = compose_folder_name(start, end)
    analyze_root = ArchiveLocator(ctx).resolve_result_dir("analyze", start, end) or bucket("analyze", ctx.identifier, folder)
    report_dir = bucket("reports", ctx.identifier, folder)
    report_cache = report_dir / REPORT_CACHE_FILENAME
    report_cache_payload = _load_report_cache_payload(report_cache)
    ai_summary_path = analyze_root / AI_SUMMARY_FILENAME
    explain_state = collect_explain_outputs(ctx, start, end)
    analyze_log_path = _resolve_analyze_log_path(ctx, start)
    report_log_path = _resolve_report_log_path(ctx, start, end)
    analyze_tail = _read_log_tail(analyze_log_path)
    report_tail = _read_log_tail(report_log_path)
    latest_analyze = _summarise_log_line(analyze_tail[-1]) if analyze_tail else ""
    latest_report = _summarise_log_line(report_tail[-1]) if report_tail else ""
    completed_functions: List[str] = []
    for func_name, filename in ANALYZE_FILE_MAP.items():
        if (analyze_root / func_name / "总体" / filename).exists():
            completed_functions.append(func_name)
    completed_count = len(completed_functions)
    total_functions = len(ANALYZE_FILE_MAP)
    ai_summary_exists = ai_summary_path.exists()
    report_cache_exists = report_cache.exists()
    report_meta = report_cache_payload.get("meta") if isinstance(report_cache_payload.get("meta"), dict) else {}
    state_stage = str(state.get("stage") or "").strip()
    state_status = str(state.get("status") or "").strip()
    state_message = str(state.get("message") or "").strip()
    updated_at = str(state.get("updated_at") or "").strip()
    explain_ready = bool(explain_state.get("ready"))
    explain_source = str(report_meta.get("explain_source") or ("legacy_rag" if explain_ready else "fallback")).strip()
    steps = [
        _build_step_log(
            step_id="analyze",
            label="基础分析",
            status="ok" if completed_count >= total_functions else ("running" if completed_count > 0 or state_stage == "analyze" else "queued"),
            message=latest_analyze or ("基础分析已完成。" if completed_count >= total_functions else "等待基础分析结果。"),
            progress=100 if completed_count >= total_functions else round(completed_count / max(1, total_functions) * 100),
            time_text=updated_at,
        ),
        _build_step_log(
            step_id="ai_summary",
            label="AI 摘要",
            status="ok" if ai_summary_exists else ("running" if completed_count >= total_functions else "queued"),
            message="ai_summary.json 已生成。" if ai_summary_exists else "等待 AI 摘要整理。",
            progress=100 if ai_summary_exists else (60 if completed_count >= total_functions else 0),
            time_text=updated_at,
        ),
        _build_step_log(
            step_id="explain",
            label="总体解读",
            status="ok" if explain_ready or report_cache_exists else ("running" if state_stage == "explain" and state_status == "running" else "queued"),
            message=state_message if state_stage == "explain" else ("总体文字解读已就绪。" if explain_ready else "等待补齐总体文字解读。"),
            progress=100 if explain_ready or report_cache_exists else round(int(explain_state.get("available_count") or 0) / max(1, int(explain_state.get("expected_count") or len(ANALYZE_FILE_MAP))) * 100),
            time_text=updated_at,
        ),
        _build_step_log(
            step_id="report",
            label="报告研判",
            status="ok" if report_cache_exists else ("running" if state_stage == "report" and state_status == "running" else "queued"),
            message=latest_report or state_message or "等待生成结构化报告。",
            progress=100 if report_cache_exists else (75 if state_stage == "report" else 0),
            time_text=updated_at,
        ),
        _build_step_log(
            step_id="cache",
            label="报告缓存",
            status="ok" if report_cache_exists else ("running" if state_stage == "report" and state_status == "running" else "queued"),
            message=f"缓存已写入 {report_cache.name}。" if report_cache_exists else "等待写入报告缓存。",
            progress=100 if report_cache_exists else 0,
            time_text=updated_at,
        ),
    ]
    return {
        "topic": ctx.display_name or ctx.identifier,
        "topic_identifier": ctx.identifier,
        "range": _range_payload(start, end),
        "state": state,
        "summary": {
            "status": "ok" if report_cache_exists else ("running" if state_status == "running" else "pending"),
            "message": state_message or ("报告已生成，可直接读取。" if report_cache_exists else "当前区间暂无执行中的报告任务。"),
        },
        "steps": steps,
        "analyze": {
            "root": str(analyze_root),
            "completed_functions": completed_functions,
            "expected_functions": list(ANALYZE_FILE_MAP.keys()),
            "completed_count": completed_count,
            "total_count": total_functions,
            "ai_summary_exists": ai_summary_exists,
            "ai_summary_path": str(ai_summary_path),
            "log_path": str(analyze_log_path),
            "log_tail": analyze_tail,
        },
        "explain": {
            "root": str(explain_state.get("root") or ""),
            "available_functions": explain_state.get("available_functions") or [],
            "available_count": int(explain_state.get("available_count") or 0),
            "expected_count": int(explain_state.get("expected_count") or len(ANALYZE_FILE_MAP)),
            "ready": explain_ready,
            "source": explain_source,
        },
        "report": {
            "cache_exists": report_cache_exists,
            "cache_path": str(report_cache),
            "log_path": str(report_log_path),
            "log_tail": report_tail,
            "progress_path": str(_report_progress_path(ctx, start, end)),
        },
    }


def _create_or_reuse_task(payload: Dict[str, Any]) -> Tuple[Dict[str, Any], bool]:
    topic_param = str(payload.get("topic") or "").strip()
    project_param = str(payload.get("project") or "").strip()
    dataset_id = str(payload.get("dataset_id") or "").strip()
    start = str(payload.get("start") or "").strip()
    end = str(payload.get("end") or "").strip() or start
    mode = str(payload.get("mode") or "fast").strip().lower() or "fast"
    if not start:
        raise ValueError("Missing required field(s): start")
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
    return success({"data": _collect_legacy_report_progress(ctx, start, end)})


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
