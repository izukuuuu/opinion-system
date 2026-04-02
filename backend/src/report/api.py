"""
报告生成 API。
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from flask import Blueprint, jsonify, request

from server_support import error, resolve_topic_identifier, success
from server_support.topic_context import resolve_context, TopicContext
from server_support.archive_locator import ArchiveLocator, compose_folder_name
from src.fetch.data_fetch import get_topic_available_date_range
from src.project import get_project_manager
from src.analyze import run_Analyze
from src.utils.setting.paths import bucket, ensure_bucket, get_logs_root

from .structured_service import generate_report_payload


PROJECT_MANAGER = get_project_manager()
report_bp = Blueprint("report", __name__)
REPORT_PROGRESS_FILENAME = "_progress.json"
AI_SUMMARY_FILENAME = "ai_summary.json"
REPORT_CACHE_FILENAME = "report_payload.json"
ANALYZE_FILE_MAP: Dict[str, str] = {
    "volume": "volume.json",
    "attitude": "attitude.json",
    "trends": "trends.json",
    "geography": "geography.json",
    "publishers": "publishers.json",
    "keywords": "keywords.json",
    "classification": "classification.json",
}


def _resolve_topic(topic_param: str, project_param: str, dataset_id: str) -> Tuple[str, str]:
    if not topic_param and not project_param:
        raise ValueError("Missing required field(s): topic or project")

    payload = {}
    if topic_param:
        payload["topic"] = topic_param
    if project_param:
        payload["project"] = project_param
    if dataset_id:
        payload["dataset_id"] = dataset_id

    topic_identifier, display_name, _, _ = resolve_topic_identifier(payload, PROJECT_MANAGER)
    return topic_identifier, display_name


def _build_topic_context(topic_param: str, project_param: str, dataset_id: str) -> TopicContext:
    payload = {}
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
    return {
        "start": start_text,
        "end": end_text,
    }


def _report_progress_path(ctx: TopicContext, start: str, end: Optional[str], *, ensure_dir: bool = False) -> Path:
    folder = compose_folder_name(start, end)
    if ensure_dir:
        report_dir = ensure_bucket("reports", ctx.identifier, folder)
    else:
        report_dir = bucket("reports", ctx.identifier, folder)
    return report_dir / REPORT_PROGRESS_FILENAME


def _load_progress_payload(ctx: TopicContext, start: str, end: Optional[str]) -> Dict[str, Any]:
    progress_path = _report_progress_path(ctx, start, end)
    if not progress_path.exists():
        return {}
    try:
        with progress_path.open("r", encoding="utf-8") as fh:
            payload = json.load(fh)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _write_progress_payload(
    ctx: TopicContext,
    start: str,
    end: Optional[str],
    *,
    stage: str,
    status: str,
    message: str,
    extra_meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    progress_path = _report_progress_path(ctx, start, end, ensure_dir=True)
    previous = _load_progress_payload(ctx, start, end)
    now_text = _utc_now_text()
    meta = previous.get("meta") if isinstance(previous.get("meta"), dict) else {}
    if extra_meta:
        meta.update(extra_meta)

    payload: Dict[str, Any] = {
        "topic": ctx.display_name or ctx.identifier,
        "topic_identifier": ctx.identifier,
        "range": _range_payload(start, end),
        "stage": str(stage or "").strip() or "prepare",
        "status": str(status or "").strip() or "pending",
        "message": str(message or "").strip(),
        "started_at": previous.get("started_at") or now_text,
        "updated_at": now_text,
    }
    if meta:
        payload["meta"] = meta
    if payload["status"] in {"ok", "error"}:
        payload["finished_at"] = now_text

    with progress_path.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
    return payload


def _resolve_analyze_log_path(ctx: TopicContext, start: str) -> Path:
    logs_root = get_logs_root()
    candidates = []
    for value in [ctx.identifier, *(ctx.aliases or [])]:
        token = str(value or "").strip()
        if token and token not in candidates:
            candidates.append(token)

    for candidate in candidates:
        log_path = logs_root / candidate / start / f"{candidate}_{start}.log"
        if log_path.exists():
            return log_path
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
    if not text:
        return ""
    parts = text.split(" - ", 3)
    if len(parts) == 4:
        return parts[3].strip()
    return text


def _build_step_log(
    *,
    step_id: str,
    label: str,
    status: str,
    message: str,
    progress: int,
    time: str = "",
) -> Dict[str, Any]:
    value = max(0, min(100, int(progress)))
    return {
        "id": step_id,
        "label": label,
        "status": status,
        "message": message,
        "progress": value,
        "time": time,
    }


def _collect_report_progress(ctx: TopicContext, start: str, end: Optional[str]) -> Dict[str, Any]:
    state = _load_progress_payload(ctx, start, end)
    folder = compose_folder_name(start, end)
    analyze_root = ArchiveLocator(ctx).resolve_result_dir("analyze", start, end)
    if analyze_root is None:
        analyze_root = bucket("analyze", ctx.identifier, folder)

    report_dir = bucket("reports", ctx.identifier, folder)
    report_cache = report_dir / REPORT_CACHE_FILENAME
    ai_summary_path = analyze_root / AI_SUMMARY_FILENAME
    analyze_log_path = _resolve_analyze_log_path(ctx, start)
    report_log_path = _resolve_report_log_path(ctx, start, end)
    analyze_tail = _read_log_tail(analyze_log_path)
    report_tail = _read_log_tail(report_log_path)
    latest_analyze_line = _summarise_log_line(analyze_tail[-1]) if analyze_tail else ""
    latest_report_line = _summarise_log_line(report_tail[-1]) if report_tail else ""

    completed_functions: List[str] = []
    for func_name, filename in ANALYZE_FILE_MAP.items():
        overall_file = analyze_root / func_name / "总体" / filename
        if overall_file.exists():
            completed_functions.append(func_name)

    completed_count = len(completed_functions)
    total_functions = len(ANALYZE_FILE_MAP)
    ai_summary_exists = ai_summary_path.exists()
    report_cache_exists = report_cache.exists()
    state_stage = str(state.get("stage") or "").strip()
    state_status = str(state.get("status") or "").strip()
    state_message = str(state.get("message") or "").strip()
    updated_at = str(state.get("updated_at") or "").strip()
    error_stage = state_stage if state_status == "error" else ""

    analyze_status = "queued"
    analyze_message = "等待基础分析结果。"
    analyze_progress = 0
    if error_stage == "analyze":
        analyze_status = "error"
        analyze_message = state_message or "基础分析执行失败。"
        analyze_progress = max(1, round(completed_count / max(1, total_functions) * 100))
    elif completed_count >= total_functions:
        analyze_status = "ok"
        analyze_message = latest_analyze_line or f"基础分析已完成，共 {completed_count}/{total_functions} 个维度。"
        analyze_progress = 100
    elif state_stage == "analyze" and state_status == "running":
        analyze_status = "running"
        analyze_message = latest_analyze_line or state_message or "正在自动补跑 analyze。"
        analyze_progress = max(5, round(completed_count / max(1, total_functions) * 100))
    elif completed_count > 0:
        analyze_status = "running"
        analyze_message = latest_analyze_line or f"基础分析已完成 {completed_count}/{total_functions} 个维度。"
        analyze_progress = max(5, round(completed_count / max(1, total_functions) * 100))

    ai_summary_status = "queued"
    ai_summary_message = "等待 AI 摘要整理。"
    ai_summary_progress = 0
    if error_stage == "analyze" and not ai_summary_exists:
        ai_summary_status = "error"
        ai_summary_message = state_message or "AI 摘要未生成。"
        ai_summary_progress = 100
    elif ai_summary_exists:
        ai_summary_status = "ok"
        ai_summary_message = "ai_summary.json 已生成。"
        ai_summary_progress = 100
    elif completed_count >= total_functions or (state_stage == "analyze" and state_status == "running"):
        ai_summary_status = "running"
        ai_summary_message = latest_analyze_line or "基础分析产物已就绪，正在整理 AI 摘要。"
        ai_summary_progress = 60 if completed_count >= total_functions else 20

    report_status = "queued"
    report_message = "等待报告生成。"
    report_progress = 0
    if report_cache_exists:
        report_status = "ok"
        report_message = latest_report_line or "结构化报告已生成。"
        report_progress = 100
    elif error_stage == "report":
        report_status = "error"
        report_message = state_message or "报告生成失败。"
        report_progress = 100
    elif state_stage == "report" and state_status == "running":
        report_status = "running"
        report_message = latest_report_line or state_message or "正在生成结构化报告。"
        report_progress = 75
    elif ai_summary_exists or completed_count >= total_functions:
        report_status = "queued"
        report_message = "基础分析已准备完成，等待生成报告。"
        report_progress = 0

    cache_status = "queued"
    cache_message = "等待写入报告缓存。"
    cache_progress = 0
    if report_cache_exists:
        cache_status = "ok"
        cache_message = f"缓存已写入 {report_cache.name}。"
        cache_progress = 100
    elif error_stage in {"report", "cache"}:
        cache_status = "error"
        cache_message = state_message or "报告缓存未写入。"
        cache_progress = 100
    elif state_stage == "report" and state_status == "running":
        cache_status = "running"
        cache_message = "报告内容生成中，等待写入缓存。"
        cache_progress = 20

    steps = [
        _build_step_log(
            step_id="analyze",
            label="基础分析",
            status=analyze_status,
            message=analyze_message,
            progress=analyze_progress,
            time=updated_at,
        ),
        _build_step_log(
            step_id="ai_summary",
            label="AI 摘要",
            status=ai_summary_status,
            message=ai_summary_message,
            progress=ai_summary_progress,
            time=updated_at,
        ),
        _build_step_log(
            step_id="report",
            label="报告研判",
            status=report_status,
            message=report_message,
            progress=report_progress,
            time=updated_at,
        ),
        _build_step_log(
            step_id="cache",
            label="报告缓存",
            status=cache_status,
            message=cache_message,
            progress=cache_progress,
            time=updated_at,
        ),
    ]

    summary_status = "pending"
    summary_message = "当前区间暂无执行中的报告任务。"
    if report_cache_exists:
        summary_status = "ok"
        summary_message = "报告已生成，可直接读取。"
    elif state_status == "error":
        summary_status = "error"
        summary_message = state_message or "最近一次报告生成失败。"
    elif state_status == "running" and state_stage == "report":
        summary_status = "running"
        summary_message = "基础分析已就绪，正在生成报告。"
    elif state_status == "running" and state_stage == "analyze":
        summary_status = "running"
        summary_message = f"正在自动补跑 analyze，已完成 {completed_count}/{total_functions} 个维度。"
    elif ai_summary_exists or completed_count >= total_functions:
        summary_status = "queued"
        summary_message = "基础分析已完成，等待生成报告。"
    elif completed_count > 0:
        summary_status = "running"
        summary_message = f"基础分析执行中，已完成 {completed_count}/{total_functions} 个维度。"

    return {
        "topic": ctx.display_name or ctx.identifier,
        "topic_identifier": ctx.identifier,
        "range": _range_payload(start, end),
        "state": state,
        "summary": {
            "status": summary_status,
            "message": summary_message,
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
        "report": {
            "cache_exists": report_cache_exists,
            "cache_path": str(report_cache),
            "log_path": str(report_log_path),
            "log_tail": report_tail,
            "progress_path": str(_report_progress_path(ctx, start, end)),
        },
    }


def _ensure_analyze_results(
    topic_identifier: str,
    *,
    start: str,
    end: Optional[str],
    ctx: TopicContext,
) -> Dict[str, Any]:
    locator = ArchiveLocator(ctx)
    existing_root = locator.resolve_result_dir("analyze", start, end)
    if existing_root:
        return {
            "prepared": False,
            "analyze_root": str(existing_root),
            "message": "",
        }

    ok = run_Analyze(topic_identifier, start, end_date=end)
    if not ok:
        raise ValueError("当前专题缺少基础分析结果，且自动补跑 analyze 失败")

    analyze_root = locator.resolve_result_dir("analyze", start, end)
    if not analyze_root:
        raise ValueError("analyze 已执行，但未生成可供报告读取的分析目录")

    return {
        "prepared": True,
        "analyze_root": str(analyze_root),
        "message": "已自动补跑 analyze 并生成报告输入数据。",
    }


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
    except ValueError as exc:
        return error(str(exc))

    try:
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
        if range_payload["start"]:
            message = "当前专题暂无基础分析结果，点击“生成”时会先自动补跑 analyze。"
        else:
            message = "当前专题暂无可用数据区间，无法生成报告。"

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
    raw_topic = str(request.args.get("topic") or "").strip()
    raw_project = str(request.args.get("project") or "").strip()
    raw_dataset_id = str(request.args.get("dataset_id") or "").strip()

    payload = {}
    if raw_topic:
        payload["topic"] = raw_topic
    if raw_project:
        payload["project"] = raw_project
    if raw_dataset_id:
        payload["dataset_id"] = raw_dataset_id

    try:
        ctx = resolve_context(payload, PROJECT_MANAGER)
    except ValueError:
        if not raw_topic:
            return error("Missing required field(s): topic or project")
        ctx = TopicContext(
            identifier=raw_topic,
            display_name=raw_topic,
            aliases=[a for a in (raw_topic, raw_project) if a],
        )

    locator = ArchiveLocator(ctx)
    records = locator.list_history("reports")
    return success(
        {
            "records": records,
            "topic": ctx.display_name,
            "topic_identifier": ctx.identifier,
        }
    )


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

    return success({"data": _collect_report_progress(ctx, start, end)})


@report_bp.post("/regenerate")
def regenerate_report_payload():
    payload = request.get_json(silent=True) or {}
    topic_param = str(payload.get("topic") or "").strip()
    project_param = str(payload.get("project") or "").strip()
    dataset_id = str(payload.get("dataset_id") or "").strip()
    start = str(payload.get("start") or "").strip()
    end = str(payload.get("end") or "").strip() or None

    if not start:
        return jsonify({"status": "error", "message": "Missing required field(s): start"}), 400

    try:
        topic_identifier, display_name = _resolve_topic(topic_param, project_param, dataset_id)
        ctx = _build_topic_context(topic_param, project_param, dataset_id)
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    _write_progress_payload(
        ctx,
        start,
        end,
        stage="prepare",
        status="running",
        message="正在检查基础分析结果。",
    )

    try:
        _write_progress_payload(
            ctx,
            start,
            end,
            stage="analyze",
            status="running",
            message="正在确认基础分析结果，必要时自动补跑 analyze。",
        )
        analyze_prepare = _ensure_analyze_results(
            topic_identifier,
            start=start,
            end=end,
            ctx=ctx,
        )
        _write_progress_payload(
            ctx,
            start,
            end,
            stage="report",
            status="running",
            message="基础分析已就绪，正在生成结构化报告。",
            extra_meta={"analyze_prepare": analyze_prepare},
        )
        report_payload = generate_report_payload(
            topic_identifier,
            start,
            end,
            topic_label=display_name,
            regenerate=True,
        )
        _write_progress_payload(
            ctx,
            start,
            end,
            stage="completed",
            status="ok",
            message="报告生成完成。",
            extra_meta={
                "analyze_prepare": analyze_prepare,
                "report_cache": str(bucket("reports", ctx.identifier, compose_folder_name(start, end)) / REPORT_CACHE_FILENAME),
            },
        )
    except ValueError as exc:
        _write_progress_payload(
            ctx,
            start,
            end,
            stage="report" if "报告" in str(exc) else "analyze",
            status="error",
            message=str(exc),
        )
        return jsonify({"status": "error", "message": str(exc)}), 404
    except Exception as exc:
        _write_progress_payload(
            ctx,
            start,
            end,
            stage="report",
            status="error",
            message=f"报告重生成失败: {str(exc)}",
        )
        return jsonify({"status": "error", "message": f"报告重生成失败: {str(exc)}"}), 500

    return jsonify({"status": "ok", "data": report_payload, "meta": {"analyze_prepare": analyze_prepare}})
