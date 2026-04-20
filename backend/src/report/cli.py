from __future__ import annotations

import argparse
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any, Dict, List, Optional, TextIO

from server_support.topic_context import TopicContext

from .api import _resolve_report_range
from .deep_report import AI_FULL_REPORT_CACHE_FILENAME, REPORT_CACHE_FILENAME, run_or_resume_deep_report_task
from .deep_report.deterministic import ensure_cache_dir_v2
from .task_queue import get_task
from .task_queue import _evaluate_resume_before_failure as evaluate_resume_before_failure

DEFAULT_EVENT_LOG_FILENAME = "report_debug_events.jsonl"
DEFAULT_DEBUG_SUMMARY_FILENAME = "report_debug_summary.json"


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return str(value)


def _safe_stream_write(stream: TextIO, text: str) -> None:
    try:
        stream.write(text)
    except UnicodeEncodeError:
        buffer = getattr(stream, "buffer", None)
        encoding = str(getattr(stream, "encoding", "") or "utf-8")
        if buffer is None:
            stream.write(text.encode(encoding, errors="backslashreplace").decode(encoding, errors="ignore"))
        else:
            buffer.write(text.encode(encoding, errors="backslashreplace"))
    stream.flush()


def _print_json(payload: Dict[str, Any], *, stream: TextIO) -> None:
    _safe_stream_write(stream, json.dumps(payload, ensure_ascii=False, default=_json_default) + "\n")


def _build_range_payload(
    topic: str,
    project: str,
    dataset_id: str,
) -> Dict[str, Any]:
    ctx, analyze_records, report_records, fetch_range = _resolve_report_range(topic, project, dataset_id)
    latest_analyze = analyze_records[0] if analyze_records else {}
    latest_report = report_records[0] if report_records else {}
    range_payload = {
        "start": str(latest_analyze.get("start") or fetch_range.get("start") or "").strip(),
        "end": str(latest_analyze.get("end") or fetch_range.get("end") or fetch_range.get("start") or "").strip(),
    }
    return {
        "context": ctx,
        "analyze_records": analyze_records,
        "report_records": report_records,
        "fetch_range": fetch_range if isinstance(fetch_range, dict) else {},
        "latest_analyze": latest_analyze,
        "latest_report": latest_report,
        "range": range_payload,
    }


def _resolve_run_context(args: argparse.Namespace) -> Dict[str, Any]:
    payload = _build_range_payload(
        topic=str(args.topic or "").strip(),
        project=str(args.project or "").strip(),
        dataset_id=str(args.dataset_id or "").strip(),
    )
    ctx = payload["context"]
    start = str(args.start or payload["range"].get("start") or "").strip()
    end = str(args.end or payload["range"].get("end") or start).strip()
    if not start or not end:
        raise ValueError("无法解析默认运行区间，请显式提供 --start 和 --end。")
    return {
        "ctx": ctx,
        "start": start,
        "end": end,
        "availability": payload,
    }


def _cache_dir_for(ctx: TopicContext, *, start: str, end: str) -> Path:
    return ensure_cache_dir_v2(
        ctx.identifier,
        start,
        end,
        project_identifier=str(getattr(ctx, "project_identifier", "") or "").strip(),
    )


class EventRecorder:
    def __init__(self, *, event_log_path: Path, emit_stdout: bool = True, stream: TextIO | None = None) -> None:
        self.event_log_path = Path(event_log_path)
        self.event_log_path.parent.mkdir(parents=True, exist_ok=True)
        self.emit_stdout = bool(emit_stdout)
        self.stream = stream or sys.stderr
        self.events: List[Dict[str, Any]] = []

    def __call__(self, event: Dict[str, Any]) -> None:
        normalized = dict(event or {})
        self.events.append(normalized)
        with self.event_log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(normalized, ensure_ascii=False, default=_json_default) + "\n")
        if self.emit_stdout:
            _print_json(normalized, stream=self.stream)


def _resolved_identity_payload(ctx: TopicContext, *, start: str, end: str, mode: str) -> Dict[str, Any]:
    return {
        "topic_identifier": str(ctx.identifier or "").strip(),
        "display_name": str(ctx.display_name or ctx.identifier or "").strip(),
        "project_identifier": str(getattr(ctx, "project_identifier", "") or "").strip(),
        "start": str(start or "").strip(),
        "end": str(end or start).strip(),
        "mode": str(mode or "fast").strip() or "fast",
    }


def _summary_from_result(
    result: Dict[str, Any],
    *,
    request_payload: Dict[str, Any],
    ctx: TopicContext,
    cache_dir: Path,
    event_log_path: Path,
) -> Dict[str, Any]:
    structured_payload = result.get("structured_payload") if isinstance(result.get("structured_payload"), dict) else {}
    full_payload = result.get("full_payload") if isinstance(result.get("full_payload"), dict) else {}
    structured_meta = structured_payload.get("metadata") if isinstance(structured_payload.get("metadata"), dict) else {}
    full_meta = full_payload.get("metadata") if isinstance(full_payload.get("metadata"), dict) else {}
    structured_meta = structured_meta or (structured_payload.get("meta") if isinstance(structured_payload.get("meta"), dict) else {})
    full_meta = full_meta or (full_payload.get("meta") if isinstance(full_payload.get("meta"), dict) else {})
    metadata = full_meta or structured_meta
    exploration_bundle = result.get("exploration_bundle") if isinstance(result.get("exploration_bundle"), dict) else {}
    degraded_sections = (
        full_payload.get("degraded_sections")
        if isinstance(full_payload.get("degraded_sections"), list)
        else metadata.get("degraded_sections")
        if isinstance(metadata.get("degraded_sections"), list)
        else []
    )
    compile_quality = str(metadata.get("compile_quality") or full_payload.get("compile_quality") or "").strip()
    if not compile_quality:
        compile_quality = "degraded" if degraded_sections or str(full_payload.get("degraded_reason") or "").strip() else "healthy"
    return {
        "request": request_payload,
        "resolved": _resolved_identity_payload(
            ctx,
            start=str(request_payload.get("start") or "").strip(),
            end=str(request_payload.get("end") or "").strip(),
            mode=str(request_payload.get("mode") or "fast").strip(),
        ),
        "status": str(result.get("status") or "").strip(),
        "message": str(result.get("message") or "").strip(),
        "thread_id": str(result.get("thread_id") or request_payload.get("thread_id") or "").strip(),
        "cache_dir": str(cache_dir),
        "structured_cache_path": str(cache_dir / REPORT_CACHE_FILENAME),
        "full_report_cache_path": str(cache_dir / AI_FULL_REPORT_CACHE_FILENAME),
        "workspace_root": str(metadata.get("workspace_root") or "").strip(),
        "state_root": str(metadata.get("state_root") or "").strip(),
        "event_log_path": str(event_log_path),
        "debug_summary_path": str(cache_dir / DEFAULT_DEBUG_SUMMARY_FILENAME),
        "gap_summary": exploration_bundle.get("gap_summary") if isinstance(exploration_bundle.get("gap_summary"), list) else [],
        "todos": (
            full_payload.get("todos")
            if isinstance(full_payload.get("todos"), list)
            else structured_meta.get("todos")
            if isinstance(structured_meta.get("todos"), list)
            else exploration_bundle.get("todos")
            if isinstance(exploration_bundle.get("todos"), list)
            else []
        ),
        "has_markdown_output": bool(full_payload.get("markdown") or result.get("markdown")),
        "compile_quality": compile_quality,
        "degraded_sections": degraded_sections,
        "section_write_receipts": (
            full_payload.get("section_write_receipts")
            if isinstance(full_payload.get("section_write_receipts"), list)
            else full_payload.get("section_generation_receipts")
            if isinstance(full_payload.get("section_generation_receipts"), list)
            else metadata.get("section_write_receipts")
            if isinstance(metadata.get("section_write_receipts"), list)
            else metadata.get("section_generation_receipts")
            if isinstance(metadata.get("section_generation_receipts"), list)
            else []
        ),
        "section_trace_annotations": full_payload.get("section_trace_annotations") if isinstance(full_payload.get("section_trace_annotations"), list) else [],
        "reused_artifacts": metadata.get("reused_artifacts") if isinstance(metadata.get("reused_artifacts"), dict) else {},
        "skipped_agents": metadata.get("skipped_agents") if isinstance(metadata.get("skipped_agents"), dict) else {},
        "execution_plan": metadata.get("execution_plan") if isinstance(metadata.get("execution_plan"), dict) else {},
        "artifact_semantic_status": (
            exploration_bundle.get("artifact_semantic_status")
            if isinstance(exploration_bundle.get("artifact_semantic_status"), dict)
            else metadata.get("artifact_semantic_status")
            if isinstance(metadata.get("artifact_semantic_status"), dict)
            else {}
        ),
        "readiness_gate_passed": bool(
            exploration_bundle.get("readiness_gate_passed")
            if "readiness_gate_passed" in exploration_bundle
            else metadata.get("readiness_gate_passed")
        ),
        "repair_attempts": int(
            exploration_bundle.get("repair_attempts")
            if "repair_attempts" in exploration_bundle
            else metadata.get("repair_attempts")
            or 0
        ),
        "repair_trace": (
            exploration_bundle.get("repair_trace")
            if isinstance(exploration_bundle.get("repair_trace"), list)
            else metadata.get("repair_trace")
            if isinstance(metadata.get("repair_trace"), list)
            else []
        ),
        "blocked_stage": str(
            exploration_bundle.get("blocked_stage")
            or metadata.get("blocked_stage")
            or ""
        ).strip(),
    }


def _write_summary(summary: Dict[str, Any], *, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")


def _emit_canonical_header(
    *,
    ctx: TopicContext,
    start: str,
    end: str,
    mode: str,
    stream: TextIO,
) -> None:
    payload = {
        "type": "cli.run.resolved",
        "topic_identifier": str(ctx.identifier or "").strip(),
        "display_name": str(ctx.display_name or ctx.identifier or "").strip(),
        "project_identifier": str(getattr(ctx, "project_identifier", "") or "").strip(),
        "start": str(start or "").strip(),
        "end": str(end or start).strip(),
        "mode": str(mode or "fast").strip() or "fast",
    }
    _print_json(payload, stream=stream)


def _run_command(args: argparse.Namespace) -> int:
    resolved = _resolve_run_context(args)
    ctx = resolved["ctx"]
    start = resolved["start"]
    end = resolved["end"]
    mode = str(args.mode or "fast").strip().lower() or "fast"
    cache_dir = _cache_dir_for(ctx, start=start, end=end)
    event_log_path = Path(str(args.event_log or "").strip()) if str(args.event_log or "").strip() else cache_dir / DEFAULT_EVENT_LOG_FILENAME
    summary_path = cache_dir / DEFAULT_DEBUG_SUMMARY_FILENAME
    recorder = EventRecorder(event_log_path=event_log_path, emit_stdout=not bool(args.quiet_events), stream=sys.stderr)
    _emit_canonical_header(ctx=ctx, start=start, end=end, mode=mode, stream=sys.stderr)
    request_payload = {
        "topic": str(args.topic or "").strip(),
        "project": str(args.project or "").strip(),
        "dataset_id": str(args.dataset_id or "").strip(),
        "topic_identifier": str(ctx.identifier or "").strip(),
        "display_name": str(ctx.display_name or ctx.identifier or "").strip(),
        "project_identifier": str(getattr(ctx, "project_identifier", "") or "").strip(),
        "start": start,
        "end": end,
        "mode": mode,
        "thread_id": str(args.thread_id or "").strip(),
        "task_id": str(args.task_id or "").strip(),
        "skip_validation": bool(args.skip_validation),
        "checkpoint_resume": bool(args.checkpoint_resume),
    }
    failure_resume_context: Dict[str, Any] | None = None
    if isinstance(getattr(args, "failure_resume_context", None), dict):
        failure_resume_context = dict(args.failure_resume_context or {})
    result = run_or_resume_deep_report_task(
        str(ctx.identifier or "").strip(),
        start,
        end,
        topic_label=str(ctx.display_name or ctx.identifier or "").strip(),
        project_identifier=str(getattr(ctx, "project_identifier", "") or "").strip(),
        mode=mode,
        thread_id=str(args.thread_id or "").strip() or None,
        task_id=str(args.task_id or "").strip(),
        checkpoint_resume=bool(args.checkpoint_resume),
        skip_validation=bool(args.skip_validation),
        failure_resume_context=failure_resume_context,
        event_callback=recorder,
    )
    summary = _summary_from_result(
        result if isinstance(result, dict) else {},
        request_payload=request_payload,
        ctx=ctx,
        cache_dir=cache_dir,
        event_log_path=event_log_path,
    )
    _write_summary(summary, output_path=summary_path)
    if bool(args.json):
        _safe_stream_write(sys.stdout, json.dumps(summary, ensure_ascii=False, indent=2, default=_json_default) + "\n")
    else:
        _print_json({"type": "cli.run.summary", **summary}, stream=sys.stdout)
    return 0 if str(summary.get("status") or "").strip() in {"completed", "completed_with_warnings"} else 1


def _availability_command(args: argparse.Namespace) -> int:
    payload = _build_range_payload(
        topic=str(args.topic or "").strip(),
        project=str(args.project or "").strip(),
        dataset_id=str(args.dataset_id or "").strip(),
    )
    ctx = payload["context"]
    output = {
        "topic_identifier": str(ctx.identifier or "").strip(),
        "display_name": str(ctx.display_name or ctx.identifier or "").strip(),
        "project_identifier": str(getattr(ctx, "project_identifier", "") or "").strip(),
        "range": payload["range"],
        "has_analyze_history": bool(payload["analyze_records"]),
        "has_report_history": bool(payload["report_records"]),
        "latest_analyze": payload["latest_analyze"],
        "latest_report": payload["latest_report"],
        "fetch_range": payload["fetch_range"],
    }
    _safe_stream_write(sys.stdout, json.dumps(output, ensure_ascii=False, indent=2, default=_json_default) + "\n")
    return 0


def _replay_task_command(args: argparse.Namespace) -> int:
    task = get_task(str(args.task_id or "").strip())
    request = task.get("request") if isinstance(task.get("request"), dict) else {}
    run_args = argparse.Namespace(
        topic=str(request.get("topic") or task.get("topic") or "").strip(),
        project=str(request.get("project") or "").strip(),
        dataset_id=str(request.get("dataset_id") or "").strip(),
        start=str(args.start or task.get("start") or request.get("start") or "").strip(),
        end=str(args.end or task.get("end") or request.get("end") or "").strip(),
        mode=str(args.mode or task.get("mode") or request.get("mode") or "fast").strip().lower() or "fast",
        skip_validation=bool(args.skip_validation or request.get("skip_validation")),
        task_id=str(args.new_task_id or "").strip(),
        thread_id=str(args.thread_id or "").strip(),
        checkpoint_resume=bool(args.checkpoint_resume),
        event_log=str(args.event_log or "").strip(),
        quiet_events=bool(args.quiet_events),
        json=bool(args.json),
        failure_resume_context=None,
    )
    if bool(args.resume_before_failure):
        evaluation = evaluate_resume_before_failure(task)
        if not bool(evaluation.get("enabled")):
            raise ValueError(str(evaluation.get("reason") or "当前任务不支持从失败前一步继续。").strip())
        run_args.failure_resume_context = {
            "source_task_id": str(task.get("id") or "").strip(),
            "source_failed_phase": str(evaluation.get("source_phase") or "").strip(),
            "source_failed_actor": str(evaluation.get("source_actor") or "").strip(),
            "source_thread_id": str(task.get("thread_id") or "").strip(),
            "structured_cache_path": str(evaluation.get("structured_cache_path") or "").strip(),
        }
    return _run_command(run_args)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Debug CLI for end-to-end report runtime.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def _add_target_arguments(target: argparse.ArgumentParser) -> None:
        target.add_argument("--topic", default="", help="Topic label or identifier")
        target.add_argument("--project", default="", help="Project name")
        target.add_argument("--dataset-id", default="", help="Dataset id")

    availability = subparsers.add_parser("availability", help="Resolve topic context and default report range")
    _add_target_arguments(availability)
    availability.set_defaults(handler=_availability_command)

    run = subparsers.add_parser("run", help="Run the real report runtime end-to-end")
    _add_target_arguments(run)
    run.add_argument("--start", default="", help="Start date (YYYY-MM-DD)")
    run.add_argument("--end", default="", help="End date (YYYY-MM-DD)")
    run.add_argument("--mode", choices=["fast", "research"], default="fast")
    run.add_argument("--skip-validation", action="store_true")
    run.add_argument("--task-id", default="", help="Optional runtime task id override")
    run.add_argument("--thread-id", default="", help="Optional runtime thread id override")
    run.add_argument("--checkpoint-resume", action="store_true", help="Resume current range from checkpoint cache when possible")
    run.add_argument("--event-log", default="", help="JSONL path for raw runtime events")
    run.add_argument("--json", action="store_true", help="Print final summary as JSON")
    run.add_argument("--quiet-events", action="store_true", help="Do not stream raw events to stderr")
    run.set_defaults(handler=_run_command)

    replay = subparsers.add_parser("replay-task", help="Replay an existing report task directly in-process")
    replay.add_argument("--task-id", required=True, help="Existing report task id")
    replay.add_argument("--new-task-id", default="", help="Optional new runtime task id for replay")
    replay.add_argument("--thread-id", default="", help="Optional runtime thread id override")
    replay.add_argument("--start", default="", help="Optional start override")
    replay.add_argument("--end", default="", help="Optional end override")
    replay.add_argument("--mode", choices=["fast", "research"], default="")
    replay.add_argument("--skip-validation", action="store_true")
    replay.add_argument("--checkpoint-resume", action="store_true")
    replay.add_argument("--resume-before-failure", action="store_true")
    replay.add_argument("--event-log", default="", help="JSONL path for raw runtime events")
    replay.add_argument("--json", action="store_true", help="Print final summary as JSON")
    replay.add_argument("--quiet-events", action="store_true", help="Do not stream raw events to stderr")
    replay.set_defaults(handler=_replay_task_command)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except Exception as exc:
        error_payload = {
            "type": "cli.error",
            "command": str(getattr(args, "command", "") or "").strip(),
            "error_type": exc.__class__.__name__,
            "message": str(exc),
        }
        with redirect_stdout(sys.stderr):
            _print_json(error_payload, stream=sys.stderr)
        return 1


__all__ = ["EventRecorder", "build_parser", "main"]


if __name__ == "__main__":
    raise SystemExit(main())
