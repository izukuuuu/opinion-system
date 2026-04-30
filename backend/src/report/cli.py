from __future__ import annotations

import argparse
import hashlib
import operator
import json
import sys
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Annotated, Any, Dict, List, Optional, TextIO, TypedDict

from langchain_core.messages import HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from server_support.topic_context import TopicContext

from .api import _resolve_report_range
from .deep_report import AI_FULL_REPORT_CACHE_FILENAME, AI_FULL_REPORT_HTML_FILENAME, REPORT_CACHE_FILENAME, run_or_resume_deep_report_task
from .deep_report.deterministic import ensure_cache_dir_v2
from .deep_report.html_report_renderer import build_html_report_artifact
from .runtime_infra import build_report_runnable_config, build_runtime_diagnostics, get_shared_report_checkpointer
from .task_queue import get_task
from .task_queue import _evaluate_resume_before_failure as evaluate_resume_before_failure
from ..utils.ai import build_langchain_chat_model

DEFAULT_EVENT_LOG_FILENAME = "report_debug_events.jsonl"
DEFAULT_DEBUG_SUMMARY_FILENAME = "report_debug_summary.json"
DEFAULT_HARNESS_TRACE_FILENAME = "report_runtime_harness_trace.json"
DEFAULT_HARNESS_SCORECARD_FILENAME = "report_runtime_harness_scorecard.json"
DEFAULT_HTML_RENDER_FIXTURE_PATH = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "report_html_2025_tobacco.json"
DEFAULT_HTML_LLM_PROBE_TRACE_FILENAME = "report_html_llm_probe_trace.json"
HTML_LLM_PROBE_PURPOSE = "html-llm-probe"
ROOT_GRAPH_PURPOSE = "deep-report-root-graph"


class _HtmlLlmProbeState(TypedDict, total=False):
    run_identity: Dict[str, Any]
    stage: str
    artifact_refs: Dict[str, Any]
    scorecard_refs: Dict[str, Any]
    approval_state: Dict[str, Any]
    retry_budget: Dict[str, Any]
    error_context: Dict[str, Any]
    runtime_state: Dict[str, Any]
    exploration_overlay: Dict[str, Any]
    html_artifact: Dict[str, Any]
    scorecard: Dict[str, Any]
    model_config: Dict[str, Any]
    probe_status: str
    probe_error: str
    raw_response_preview: str
    output_path: str
    trace: Annotated[List[Dict[str, Any]], operator.add]


class _RuntimeInspectionState(TypedDict, total=False):
    run_identity: Dict[str, Any]
    stage: str
    artifact_refs: Dict[str, Any]
    scorecard_refs: Dict[str, Any]
    approval_state: Dict[str, Any]
    retry_budget: Dict[str, Any]
    error_context: Dict[str, Any]
    request: Dict[str, Any]
    exploration_bundle: Dict[str, Any]
    structured_payload: Dict[str, Any]
    full_payload: Dict[str, Any]
    approvals: List[Dict[str, Any]]
    status: str
    message: str


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


def _default_probe_thread_id(cache_dir: Path) -> str:
    digest = hashlib.sha1(str(cache_dir.resolve()).encode("utf-8", errors="ignore")).hexdigest()[:12]
    return f"probe-html-llm:{cache_dir.name}:{digest}"


def _checkpoint_id_from_config(config: Any) -> str:
    if not isinstance(config, dict):
        return ""
    configurable = config.get("configurable") if isinstance(config.get("configurable"), dict) else {}
    return str(configurable.get("checkpoint_id") or "").strip()


def _snapshot_to_dict(snapshot: Any) -> Dict[str, Any]:
    if snapshot is None:
        return {}

    def _task_to_dict(task: Any) -> Dict[str, Any]:
        interrupts = getattr(task, "interrupts", None)
        if isinstance(interrupts, tuple):
            interrupts_payload = [_interrupt_to_dict(item) for item in interrupts]
        elif isinstance(interrupts, list):
            interrupts_payload = [_interrupt_to_dict(item) for item in interrupts]
        else:
            interrupts_payload = []
        return {
            "id": str(getattr(task, "id", "") or "").strip(),
            "name": str(getattr(task, "name", "") or "").strip(),
            "error": str(getattr(task, "error", "") or "").strip(),
            "interrupts": interrupts_payload,
            "state": _jsonable(getattr(task, "state", None)),
        }

    return {
        "values": _jsonable(getattr(snapshot, "values", {})),
        "next": list(getattr(snapshot, "next", ()) or ()),
        "config": _jsonable(getattr(snapshot, "config", {})),
        "metadata": _jsonable(getattr(snapshot, "metadata", {})),
        "created_at": str(getattr(snapshot, "created_at", "") or "").strip(),
        "parent_config": _jsonable(getattr(snapshot, "parent_config", {})),
        "tasks": [_task_to_dict(item) for item in (getattr(snapshot, "tasks", ()) or ())],
        "interrupts": [_interrupt_to_dict(item) for item in (getattr(snapshot, "interrupts", ()) or ())],
        "checkpoint_id": _checkpoint_id_from_config(getattr(snapshot, "config", {})),
    }


def _jsonable(value: Any) -> Any:
    try:
        json.dumps(value, ensure_ascii=False, default=_json_default)
        return value
    except Exception:
        if isinstance(value, dict):
            return {str(key): _jsonable(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [_jsonable(item) for item in value]
        return _json_default(value)


def _interrupt_to_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return _jsonable(value)
    return {
        "id": str(getattr(value, "id", "") or "").strip(),
        "value": _jsonable(getattr(value, "value", {})),
    }


def _runtime_purpose(runtime: str) -> str:
    runtime_text = str(runtime or "probe").strip().lower()
    if runtime_text in {"root", "report", "root-graph"}:
        return ROOT_GRAPH_PURPOSE
    return HTML_LLM_PROBE_PURPOSE


def _runtime_config(*, thread_id: str, purpose: str, checkpoint_id: str = "", task_id: str = "", locator_hint: str = "") -> Dict[str, Any]:
    config = build_report_runnable_config(
        thread_id=thread_id,
        purpose=purpose,
        task_id=task_id,
        tags=["cli_stage_runtime"],
        metadata={},
        locator_hint=locator_hint,
    )
    if checkpoint_id:
        config.setdefault("configurable", {})["checkpoint_id"] = checkpoint_id
    return config


def _build_runtime_inspection_graph(*, purpose: str, locator_hint: str = "") -> Any:
    checkpointer, _runtime_profile = get_shared_report_checkpointer(purpose=purpose, locator_hint=locator_hint)

    def _noop(state: Dict[str, Any]) -> Dict[str, Any]:
        return {}

    graph = StateGraph(_RuntimeInspectionState)
    graph.add_node("noop", _noop)
    graph.add_edge(START, "noop")
    graph.add_edge("noop", END)
    return graph.compile(checkpointer=checkpointer)


def _stage_artifact_ref(path: Path, *, schema_version: str, producer_node: str) -> Dict[str, Any]:
    return {
        "path": str(path),
        "schema_version": schema_version,
        "sha256": _sha256_file(path),
        "producer_node": producer_node,
    }


def _write_stage_scorecard(
    cache_dir: Path,
    *,
    stage: str,
    thread_id: str,
    state: Dict[str, Any],
    checks: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    cache_dir.mkdir(parents=True, exist_ok=True)
    check_list = list(checks or [])
    failed = [item for item in check_list if item.get("status") == "fail"]
    warned = [item for item in check_list if item.get("status") == "warning"]
    status = "failed" if failed else ("warning" if warned else "passed")
    output_path = cache_dir / f"{stage}.scorecard.json"
    payload = {
        "type": "stage_scorecard",
        "stage": stage,
        "thread_id": thread_id,
        "created_at": _now_iso(),
        "status": status,
        "checks": check_list,
        "state_keys": sorted(str(key) for key in state.keys()),
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
    return {
        "stage": stage,
        "status": status,
        "path": str(output_path),
        "sha256": _sha256_file(output_path),
        "blocking_checks": [item for item in check_list if item.get("status") == "fail"],
        "warning_checks": [item for item in check_list if item.get("status") == "warning"],
    }


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


@dataclass
class ReportCliHarness:
    """Report runtime harness adapted from the template evaluation workflow."""

    cache_dir: Path
    request_payload: Dict[str, Any]
    event_log_path: Path
    events: List[Dict[str, Any]] = field(default_factory=list)

    def record_runtime_event(self, event: Dict[str, Any]) -> None:
        normalized = dict(event or {})
        self.events.append(
            {
                "ts": _now_iso(),
                "event_type": str(normalized.get("type") or "").strip() or "runtime.event",
                "phase": str(normalized.get("phase") or "").strip(),
                "agent": str(normalized.get("agent") or normalized.get("actor") or "").strip(),
                "message": str(normalized.get("message") or "").strip(),
                "payload": normalized.get("payload") if isinstance(normalized.get("payload"), dict) else {},
            }
        )

    def _score_event_coverage(self) -> Dict[str, Any]:
        phases = {str(event.get("phase") or "").strip() for event in self.events if str(event.get("phase") or "").strip()}
        if not self.events:
            return {"name": "runtime_event_coverage", "status": "warning", "reason": "no_runtime_events"}
        expected = {"prepare", "interpret", "persist"}
        covered = sorted(phases & expected)
        if "persist" not in phases and "completed" not in phases:
            return {
                "name": "runtime_event_coverage",
                "status": "warning",
                "reason": "persist_phase_not_observed",
                "covered_phases": covered,
                "observed_phases": sorted(phases),
            }
        return {
            "name": "runtime_event_coverage",
            "status": "pass",
            "reason": "runtime_events_observed",
            "covered_phases": covered,
            "observed_phases": sorted(phases),
        }

    def _score_artifact_outputs(self, summary: Dict[str, Any]) -> Dict[str, Any]:
        markdown_path = Path(str(summary.get("full_report_cache_path") or ""))
        html_path = Path(str(summary.get("full_html_cache_path") or ""))
        missing: List[str] = []
        if not bool(summary.get("has_markdown_output")) and not markdown_path.exists():
            missing.append("full_markdown")
        if not html_path.exists():
            missing.append("full_html")
        if missing:
            status = "fail" if str(summary.get("status") or "").strip() in {"completed", "completed_with_warnings"} else "warning"
            return {
                "name": "artifact_outputs",
                "status": status,
                "reason": "missing_artifacts",
                "missing": missing,
                "full_markdown": str(markdown_path),
                "full_html": str(html_path),
            }
        return {
            "name": "artifact_outputs",
            "status": "pass",
            "reason": "expected_artifacts_ready",
            "full_markdown": str(markdown_path),
            "full_html": str(html_path),
        }

    def _score_breakpoint_state(self, result: Dict[str, Any]) -> Dict[str, Any]:
        approvals = result.get("approvals") if isinstance(result.get("approvals"), list) else []
        unresolved = [
            item
            for item in approvals
            if isinstance(item, dict) and str(item.get("status") or "pending").strip() not in {"resolved", "approved", "rejected"}
        ]
        status = str(result.get("status") or "").strip()
        if status == "waiting_approval" or unresolved:
            return {
                "name": "breakpoint_state",
                "status": "warning",
                "reason": "human_review_breakpoint_pending",
                "approval_count": len(approvals),
                "pending_count": len(unresolved) or len(approvals),
            }
        return {
            "name": "breakpoint_state",
            "status": "pass",
            "reason": "no_pending_human_review_breakpoint",
            "approval_count": len(approvals),
        }

    def _score_retrieval_lineage(self, summary: Dict[str, Any]) -> Dict[str, Any]:
        artifact_status = summary.get("artifact_semantic_status") if isinstance(summary.get("artifact_semantic_status"), dict) else {}
        evidence_status = ""
        evidence_record = artifact_status.get("evidence_cards.json") if isinstance(artifact_status.get("evidence_cards.json"), dict) else {}
        if evidence_record:
            evidence_status = str(evidence_record.get("status") or "").strip()
        retrieval_counts: Dict[str, Any] = {}
        retrieval_success = False
        for event in self.events:
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            tool_name = str(payload.get("tool_name") or "").strip()
            counts = payload.get("counts") if isinstance(payload.get("counts"), dict) else {}
            if tool_name == "retrieve_evidence_cards" or str(event.get("agent") or "").strip() == "archive_evidence_organizer":
                cards_count = int(counts.get("cards_count") or 0) if isinstance(counts, dict) else 0
                sampled_count = int(counts.get("sampled_count") or 0) if isinstance(counts, dict) else 0
                if cards_count > 0 or sampled_count > 0:
                    retrieval_success = True
                    retrieval_counts = dict(counts)
        if retrieval_success and evidence_status not in {"ready"}:
            return {
                "name": "retrieval_lineage",
                "status": "fail",
                "reason": "retrieval_result_not_persisted",
                "evidence_cards_status": evidence_status or "missing",
                "retrieval_counts": retrieval_counts,
            }
        if evidence_status == "ready":
            return {
                "name": "retrieval_lineage",
                "status": "pass",
                "reason": "evidence_cards_ready",
                "evidence_cards_status": evidence_status,
                "retrieval_counts": retrieval_counts,
            }
        if evidence_status in {"empty", "failed", "stale"}:
            return {
                "name": "retrieval_lineage",
                "status": "warning",
                "reason": "evidence_cards_not_ready",
                "evidence_cards_status": evidence_status,
            }
        return {"name": "retrieval_lineage", "status": "warning", "reason": "retrieval_not_observed"}

    def _score_compile_health(self, summary: Dict[str, Any]) -> Dict[str, Any]:
        status = str(summary.get("status") or "").strip()
        compile_quality = str(summary.get("compile_quality") or "").strip()
        degraded = summary.get("degraded_sections") if isinstance(summary.get("degraded_sections"), list) else []
        if status not in {"completed", "completed_with_warnings"}:
            return {"name": "compile_health", "status": "fail", "reason": status or "runtime_not_completed"}
        if degraded or compile_quality == "degraded":
            return {
                "name": "compile_health",
                "status": "warning",
                "reason": "compile_completed_with_degradation",
                "compile_quality": compile_quality,
                "degraded_sections": degraded,
            }
        return {"name": "compile_health", "status": "pass", "reason": "compile_completed", "compile_quality": compile_quality}

    def finalize(self, *, result: Dict[str, Any], summary: Dict[str, Any]) -> Dict[str, Any]:
        checks = [
            self._score_event_coverage(),
            self._score_artifact_outputs(summary),
            self._score_retrieval_lineage(summary),
            self._score_breakpoint_state(result),
            self._score_compile_health(summary),
        ]
        failed = [item for item in checks if item.get("status") == "fail"]
        warned = [item for item in checks if item.get("status") == "warning"]
        status = "failed" if failed else ("warning" if warned else "passed")
        trace_path = self.cache_dir / DEFAULT_HARNESS_TRACE_FILENAME
        scorecard_path = self.cache_dir / DEFAULT_HARNESS_SCORECARD_FILENAME
        payload = {
            "task_id": str(self.request_payload.get("task_id") or "").strip(),
            "thread_id": str(summary.get("thread_id") or "").strip(),
            "created_at": _now_iso(),
            "status": status,
            "checks": checks,
            "event_count": len(self.events),
            "event_log_path": str(self.event_log_path),
            "trace_path": str(trace_path),
            "scorecard_path": str(scorecard_path),
        }
        trace_path.write_text(
            json.dumps({"request": self.request_payload, "events": self.events}, ensure_ascii=False, indent=2, default=_json_default),
            encoding="utf-8",
        )
        scorecard_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
        return payload


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
        "full_html_cache_path": str(cache_dir / AI_FULL_REPORT_HTML_FILENAME),
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


def _score_html_render_artifact(artifact: Dict[str, Any]) -> Dict[str, Any]:
    html_text = str(artifact.get("html") or "")
    summary = artifact.get("report_data_summary") if isinstance(artifact.get("report_data_summary"), dict) else {}
    checks = [
        {
            "name": "html_non_empty",
            "status": "pass" if len(html_text.encode("utf-8")) >= 12000 else "fail",
            "byte_length": len(html_text.encode("utf-8")),
        },
        {
            "name": "template_placeholders_removed",
            "status": "fail" if "__REPORT_JSON_DATA__" in html_text or "{{REPORT_TITLE}}" in html_text else "pass",
        },
        {
            "name": "echarts_contract",
            "status": "pass" if all(token in html_text for token in ["echarts.init", "setOption", "keywordCloud", "timelineList"]) else "fail",
        },
        {
            "name": "chart_data_coverage",
            "status": "pass"
            if int(summary.get("keyword_count") or 0) >= 6 and int(summary.get("timeline_count") or 0) >= 2
            else "warning",
            "summary": summary,
        },
        {
            "name": "no_data_placeholder_leak",
            "status": "fail"
            if "证据不足" in html_text
            and (
                int(summary.get("sentiment_count") or 0) > 1
                or int(summary.get("volume_points") or 0) > 1
                or int(summary.get("keyword_count") or 0) > 3
                or int(summary.get("timeline_count") or 0) > 1
            )
            else "pass",
        },
        {
            "name": "lineage_recorded",
            "status": "pass" if artifact.get("input_digests") and artifact.get("source_artifact_ids") else "fail",
            "source_artifact_ids": artifact.get("source_artifact_ids") if isinstance(artifact.get("source_artifact_ids"), list) else [],
            "input_digests": artifact.get("input_digests") if isinstance(artifact.get("input_digests"), dict) else {},
        },
    ]
    failed = [item for item in checks if item.get("status") == "fail"]
    warned = [item for item in checks if item.get("status") == "warning"]
    return {
        "status": "failed" if failed else ("warning" if warned else "passed"),
        "checks": checks,
    }


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
    harness = ReportCliHarness(cache_dir=cache_dir, request_payload=request_payload, event_log_path=event_log_path)

    def _record_event(event: Dict[str, Any]) -> None:
        recorder(event)
        harness.record_runtime_event(event)

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
        event_callback=_record_event,
    )
    summary = _summary_from_result(
        result if isinstance(result, dict) else {},
        request_payload=request_payload,
        ctx=ctx,
        cache_dir=cache_dir,
        event_log_path=event_log_path,
    )
    harness_scorecard = harness.finalize(result=result if isinstance(result, dict) else {}, summary=summary)
    summary["harness_scorecard"] = harness_scorecard
    summary["harness_trace_path"] = harness_scorecard.get("trace_path", "")
    summary["harness_scorecard_path"] = harness_scorecard.get("scorecard_path", "")
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


def _render_html_fixture_command(args: argparse.Namespace) -> int:
    fixture_path = Path(str(args.fixture or DEFAULT_HTML_RENDER_FIXTURE_PATH)).resolve()
    if not fixture_path.exists():
        raise FileNotFoundError(f"HTML render fixture not found: {fixture_path}")
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    state = fixture.get("state") if isinstance(fixture.get("state"), dict) else fixture
    if not isinstance(state, dict):
        raise ValueError("HTML render fixture must be a JSON object or contain a state object.")
    artifact = build_html_report_artifact(state)
    output_path = Path(str(args.output or "").strip()).resolve() if str(args.output or "").strip() else fixture_path.with_suffix(".html")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(str(artifact.get("html") or ""), encoding="utf-8")
    scorecard = _score_html_render_artifact(artifact)
    summary = {
        "type": "cli.render_html_fixture.summary",
        "fixture_path": str(fixture_path),
        "output_path": str(output_path),
        "renderer_version": str(artifact.get("renderer_version") or ""),
        "template": str(artifact.get("template") or ""),
        "narrative_source": str(artifact.get("narrative_source") or ""),
        "byte_length": int(artifact.get("byte_length") or 0),
        "warnings": list(artifact.get("warnings") or []),
        "report_data_summary": artifact.get("report_data_summary") if isinstance(artifact.get("report_data_summary"), dict) else {},
        "scorecard": scorecard,
    }
    _safe_stream_write(sys.stdout, json.dumps(summary, ensure_ascii=False, indent=2 if bool(args.json) else None, default=_json_default) + "\n")
    return 0 if scorecard.get("status") in {"passed", "warning"} else 1


def _read_json_if_exists(path: Path) -> Dict[str, Any]:
    if not path.exists() or not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def _iter_dict_values(value: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            out.append(current)
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
    return out


def _safe_analysis_json(path_text: str) -> Dict[str, Any]:
    path = Path(str(path_text or "").strip())
    if not str(path):
        return {}
    try:
        resolved = path.resolve()
        data_root = (Path(__file__).resolve().parents[2] / "data").resolve()
        if data_root not in resolved.parents or resolved.suffix.lower() != ".json" or not resolved.exists():
            return {}
        return _read_json_if_exists(resolved)
    except Exception:
        return {}


def _attach_analysis_outputs(payload: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(payload or {})
    name_map = {
        "attitude": "analysis_attitude",
        "sentiment": "analysis_attitude",
        "trends": "analysis_trends",
        "geography": "analysis_geography",
        "publishers": "analysis_publishers",
        "keywords": "analysis_keywords",
    }
    for candidate in _iter_dict_values(payload):
        functions = candidate.get("functions")
        if not isinstance(functions, list):
            continue
        for item in functions:
            if not isinstance(item, dict):
                continue
            target_key = name_map.get(str(item.get("name") or "").strip())
            if not target_key or target_key in out:
                continue
            loaded = _safe_analysis_json(str(item.get("path") or ""))
            if loaded:
                out[target_key] = loaded
            elif isinstance(item.get("top_items"), list):
                out[target_key] = {"data": item.get("top_items")}
    return out


def _load_exploration_overlay(path_text: str) -> Dict[str, Any]:
    path = Path(str(path_text or "").strip())
    if not str(path):
        return {}
    resolved = path.resolve()
    if not resolved.exists() or resolved.suffix.lower() != ".json":
        raise FileNotFoundError(f"Exploration overlay not found: {resolved}")
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Exploration overlay must be a JSON object.")
    return payload.get("state") if isinstance(payload.get("state"), dict) else payload


def _merge_exploration_overlay(state: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    if not overlay:
        return state
    merged = dict(state or {})
    payload = dict(merged.get("payload") if isinstance(merged.get("payload"), dict) else {})
    overlay_payload = overlay.get("payload") if isinstance(overlay.get("payload"), dict) else {}
    for key in [
        "evidence_cards",
        "timeline_nodes",
        "metrics_bundle",
        "actor_positions",
        "event_analysis",
        "normalized_task",
        "analysis_attitude",
        "analysis_trends",
        "analysis_geography",
        "analysis_publishers",
        "analysis_keywords",
    ]:
        if key in overlay_payload:
            payload[key] = overlay_payload[key]
        elif key in overlay:
            payload[key] = overlay[key]
    for key in [
        "report_ir",
        "draft_bundle_v2",
        "validation_result_v2",
        "repair_plan_v2",
        "graph_state_v2",
        "section_markdown_manifest",
        "section_trace_annotations",
    ]:
        if isinstance(overlay.get(key), dict):
            merged[key] = overlay[key]
    for key in ["markdown", "final_markdown_current"]:
        if str(overlay.get(key) or "").strip():
            merged[key] = str(overlay.get(key) or "")
    task = overlay.get("task")
    if isinstance(task, dict):
        merged["task"] = {**(merged.get("task") if isinstance(merged.get("task"), dict) else {}), **task}
    merged["payload"] = payload
    return merged


def _state_from_cache_dir(cache_dir: Path, *, exploration_overlay_path: str = "") -> Dict[str, Any]:
    full_payload = _read_json_if_exists(cache_dir / AI_FULL_REPORT_CACHE_FILENAME)
    report_payload = _read_json_if_exists(cache_dir / REPORT_CACHE_FILENAME)
    payload = _attach_analysis_outputs({**report_payload, **full_payload})
    report_ir = _read_json_if_exists(cache_dir / "report_ir.json")
    if not report_ir and isinstance(full_payload.get("report_ir"), dict):
        report_ir = full_payload.get("report_ir") or {}
    state = {
        "task": full_payload.get("task") if isinstance(full_payload.get("task"), dict) else report_payload.get("task") if isinstance(report_payload.get("task"), dict) else {},
        "markdown": str(full_payload.get("markdown") or ""),
        "final_markdown_current": str(full_payload.get("markdown") or ""),
        "payload": payload,
        "report_ir": report_ir,
        "draft_bundle_v2": _read_json_if_exists(cache_dir / "draft_bundle.v2.json"),
        "validation_result_v2": _read_json_if_exists(cache_dir / "validation_result.v2.json"),
        "repair_plan_v2": _read_json_if_exists(cache_dir / "repair_plan.v2.json"),
        "graph_state_v2": _read_json_if_exists(cache_dir / "graph_state.v2.json"),
        "section_markdown_manifest": _read_json_if_exists(cache_dir / "section_markdown_manifest.json"),
        "section_trace_annotations": _read_json_if_exists(cache_dir / "section_trace_annotations.json"),
    }
    if isinstance(full_payload.get("timeline"), list):
        state["payload"]["timeline_nodes"] = full_payload.get("timeline")
    if isinstance(full_payload.get("citations"), list):
        state["payload"]["evidence_cards"] = full_payload.get("citations")
    overlay = _load_exploration_overlay(exploration_overlay_path) if str(exploration_overlay_path or "").strip() else {}
    return _merge_exploration_overlay(state, overlay)


def _render_html_cache_command(args: argparse.Namespace) -> int:
    cache_dir = Path(str(args.cache_dir or "").strip()).resolve()
    if not cache_dir.exists() or not cache_dir.is_dir():
        raise FileNotFoundError(f"Report cache directory not found: {cache_dir}")
    state = _state_from_cache_dir(cache_dir, exploration_overlay_path=str(getattr(args, "exploration_overlay", "") or ""))
    artifact = build_html_report_artifact(state)
    output_path = Path(str(args.output or "").strip()).resolve() if str(args.output or "").strip() else cache_dir / AI_FULL_REPORT_HTML_FILENAME
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(str(artifact.get("html") or ""), encoding="utf-8")
    scorecard = _score_html_render_artifact(artifact)
    summary = {
        "type": "cli.render_html_cache.summary",
        "cache_dir": str(cache_dir),
        "exploration_overlay": str(getattr(args, "exploration_overlay", "") or "").strip(),
        "output_path": str(output_path),
        "renderer_version": str(artifact.get("renderer_version") or ""),
        "byte_length": int(artifact.get("byte_length") or 0),
        "warnings": list(artifact.get("warnings") or []),
        "report_data_summary": artifact.get("report_data_summary") if isinstance(artifact.get("report_data_summary"), dict) else {},
        "scorecard": scorecard,
    }
    _safe_stream_write(sys.stdout, json.dumps(summary, ensure_ascii=False, indent=2 if bool(args.json) else None, default=_json_default) + "\n")
    return 0 if scorecard.get("status") in {"passed", "warning"} else 1


def _parse_json_object(text: str) -> Dict[str, Any]:
    raw = str(text or "").strip()
    raw = raw.removeprefix("```json").removeprefix("```").strip()
    raw = raw.removesuffix("```").strip()
    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        parsed = json.loads(raw[start : end + 1])
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _compact_probe_context(state: Dict[str, Any], *, max_chars: int = 12000) -> str:
    payload = state.get("payload") if isinstance(state.get("payload"), dict) else {}
    report_ir = state.get("report_ir") if isinstance(state.get("report_ir"), dict) else {}
    context = {
        "task": state.get("task") if isinstance(state.get("task"), dict) else {},
        "markdown_excerpt": str(state.get("final_markdown_current") or state.get("markdown") or "")[:5000],
        "timeline": report_ir.get("timeline") if isinstance(report_ir.get("timeline"), dict) else report_ir.get("timeline"),
        "topic_scope": report_ir.get("topic_scope") if isinstance(report_ir.get("topic_scope"), dict) else {},
        "analysis_attitude": payload.get("analysis_attitude"),
        "analysis_trends": {"sample": (payload.get("analysis_trends") or {}).get("data", [])[:12]} if isinstance(payload.get("analysis_trends"), dict) else {},
        "analysis_geography": payload.get("analysis_geography"),
        "analysis_keywords": payload.get("analysis_keywords"),
        "analysis_publishers": payload.get("analysis_publishers"),
    }
    return json.dumps(context, ensure_ascii=False, default=_json_default)[:max_chars]


def _probe_stage_gate(
    *,
    cache_dir: Path,
    stage: str,
    next_nodes: List[str],
    thread_id: str,
    artifact_ref_builder: Any,
) -> Any:
    def _gate(state: Dict[str, Any]) -> Dict[str, Any]:
        checks = []
        if stage == "llm_exploration":
            if str(state.get("probe_status") or "").strip() == "failed":
                checks.append({"name": "llm_exploration_status", "status": "fail", "reason": str(state.get("probe_error") or "failed")})
            elif not isinstance(state.get("exploration_overlay"), dict) or not state.get("exploration_overlay"):
                checks.append({"name": "exploration_overlay", "status": "fail", "reason": "missing_overlay"})
            else:
                checks.append({"name": "exploration_overlay", "status": "pass", "reason": "overlay_ready"})
        elif stage == "render_html":
            scorecard = state.get("scorecard") if isinstance(state.get("scorecard"), dict) else {}
            render_status = str(scorecard.get("status") or "").strip()
            checks.append(
                {
                    "name": "html_render_contract",
                    "status": "pass" if render_status in {"passed", "warning"} else "fail",
                    "reason": render_status or "missing_render_scorecard",
                }
            )

        scorecard = _write_stage_scorecard(cache_dir, stage=stage, thread_id=thread_id, state=state, checks=checks)
        scorecard_refs = dict(state.get("scorecard_refs") or {}) if isinstance(state.get("scorecard_refs"), dict) else {}
        scorecard_refs[stage] = {"path": scorecard["path"], "sha256": scorecard["sha256"], "status": scorecard["status"]}
        artifact_refs = dict(state.get("artifact_refs") or {}) if isinstance(state.get("artifact_refs"), dict) else {}
        artifact_refs.update(artifact_ref_builder(state))
        payload = {
            "type": "stage_eval_gate",
            "stage": stage,
            "thread_id": thread_id,
            "checkpoint_id": "",
            "next": next_nodes,
            "scorecard_ref": scorecard["path"],
            "artifact_refs": artifact_refs,
            "blocking_checks": scorecard["blocking_checks"],
            "warning_checks": scorecard["warning_checks"],
            "allowed_decisions": ["continue", "repair", "fork", "abort"],
        }
        decision = interrupt(payload)
        decision_payload = decision if isinstance(decision, dict) else {"decision": "continue" if decision else "abort"}
        decision_text = str(decision_payload.get("decision") or "continue").strip().lower()
        if decision_text not in {"continue", "repair", "fork", "abort"}:
            decision_text = "continue"
        return {
            "stage": stage,
            "artifact_refs": artifact_refs,
            "scorecard_refs": scorecard_refs,
            "approval_state": {"stage": stage, "decision": decision_text, "payload": decision_payload},
            "trace": [{"node": f"eval_gate_{stage}", "status": "completed", "decision": decision_text, "scorecard_ref": scorecard["path"]}],
        }

    return _gate


def _build_html_llm_probe_graph(*, cache_dir: Path, output_path: Path, thread_id: str) -> Any:
    def load_cache(state: Dict[str, Any]) -> Dict[str, Any]:
        runtime_state = _state_from_cache_dir(cache_dir)
        return {
            "run_identity": {
                "thread_id": thread_id,
                "cache_dir": str(cache_dir),
                "output_path": str(output_path),
                "contract_id": "html-llm-probe.v1",
            },
            "stage": "load_cache",
            "artifact_refs": {},
            "scorecard_refs": {},
            "approval_state": {},
            "retry_budget": {"llm_exploration": 1, "render_html": 1},
            "error_context": {},
            "runtime_state": runtime_state,
            "trace": [
                {
                    "node": "load_cache",
                    "status": "completed",
                    "cache_dir": str(cache_dir),
                    "has_markdown": bool(str(runtime_state.get("final_markdown_current") or runtime_state.get("markdown") or "").strip()),
                }
            ],
        }

    def llm_exploration(state: Dict[str, Any]) -> Dict[str, Any]:
        runtime_state = state.get("runtime_state") if isinstance(state.get("runtime_state"), dict) else {}
        llm, client_cfg = build_langchain_chat_model(task="report", model_role="report", temperature=0.1, max_tokens=2600, timeout=180, max_retries=1)
        safe_cfg = {
            "provider": str((client_cfg or {}).get("provider") or "").strip(),
            "model": str((client_cfg or {}).get("model") or "").strip(),
            "base_url": str((client_cfg or {}).get("base_url") or "").strip(),
            "model_role": str((client_cfg or {}).get("model_role") or "").strip(),
        } if isinstance(client_cfg, dict) else {}
        if llm is None:
            return {
                "probe_status": "failed",
                "probe_error": "report_llm_unavailable",
                "model_config": safe_cfg,
                "stage": "llm_exploration",
                "error_context": {"stage": "llm_exploration", "reason": "report_llm_unavailable"},
                "trace": [{"node": "llm_exploration", "status": "failed", "reason": "report_llm_unavailable", "model_config": safe_cfg}],
            }
        prompt = (
            "请基于输入的舆情报告缓存上下文，生成一个可被 HTML renderer 消费的探索插片 JSON。\n"
            "只输出 JSON 对象，不要解释。结构必须为：\n"
            "{ \"payload\": { \"evidence_cards\": {\"status\":\"ready\",\"result\":[...]}, "
            "\"timeline_nodes\": {\"status\":\"ready\",\"result\":[...]}, "
            "\"metrics_bundle\": {\"status\":\"ready\",\"result\":[...]}, "
            "\"actor_positions\": {\"status\":\"ready\",\"result\":[...]}, "
            "\"event_analysis\": {\"status\":\"ready\",\"result\":{\"summary\":\"...\",\"sentiment_summary\":{\"negative\":0,\"neutral\":0,\"positive\":0},\"keywords\":[...]}} } }\n"
            "要求：证据卡和时间线必须来自输入上下文，不要编造外部新闻；优先聚焦高铁站台控烟、站台禁烟、规则适用差异、公众投诉和部门解释一致性。"
        )
        try:
            response = llm.invoke(
                [
                    SystemMessage(content="你是舆情报告探索子图的中间产物生成节点，只输出严格 JSON。"),
                    HumanMessage(content=prompt + "\n\n输入上下文：\n" + _compact_probe_context(runtime_state)),
                ]
            )
            content = str(getattr(response, "content", response) or "")
            overlay = _parse_json_object(content)
            if not overlay:
                return {
                    "probe_status": "failed",
                    "probe_error": "llm_returned_non_json",
                    "model_config": safe_cfg,
                    "raw_response_preview": content[:1200],
                    "stage": "llm_exploration",
                    "error_context": {"stage": "llm_exploration", "reason": "llm_returned_non_json"},
                    "trace": [{"node": "llm_exploration", "status": "failed", "reason": "llm_returned_non_json", "model_config": safe_cfg}],
                }
            return {
                "exploration_overlay": overlay,
                "probe_status": "exploration_ready",
                "model_config": safe_cfg,
                "stage": "llm_exploration",
                "trace": [{"node": "llm_exploration", "status": "completed", "model_config": safe_cfg}],
            }
        except Exception as exc:
            return {
                "probe_status": "failed",
                "probe_error": f"{type(exc).__name__}: {exc}",
                "model_config": safe_cfg,
                "stage": "llm_exploration",
                "error_context": {"stage": "llm_exploration", "reason": type(exc).__name__, "message": str(exc)},
                "trace": [{"node": "llm_exploration", "status": "failed", "reason": type(exc).__name__, "model_config": safe_cfg}],
            }

    def render_html(state: Dict[str, Any]) -> Dict[str, Any]:
        if str(state.get("probe_status") or "").strip() == "failed":
            return {"trace": [{"node": "render_html", "status": "skipped", "reason": "probe_failed"}]}
        runtime_state = state.get("runtime_state") if isinstance(state.get("runtime_state"), dict) else {}
        overlay = state.get("exploration_overlay") if isinstance(state.get("exploration_overlay"), dict) else {}
        merged_state = _merge_exploration_overlay(runtime_state, overlay)
        artifact = build_html_report_artifact(merged_state)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(str(artifact.get("html") or ""), encoding="utf-8")
        return {
            "html_artifact": {key: value for key, value in artifact.items() if key != "html"},
            "output_path": str(output_path),
            "scorecard": _score_html_render_artifact(artifact),
            "probe_status": "completed",
            "stage": "render_html",
            "model_config": state.get("model_config") if isinstance(state.get("model_config"), dict) else {},
            "trace": [{"node": "render_html", "status": "completed", "output_path": str(output_path)}],
        }

    def _route_after_llm_gate(state: Dict[str, Any]) -> str:
        approval_state = state.get("approval_state") if isinstance(state.get("approval_state"), dict) else {}
        decision = str(approval_state.get("decision") or "continue").strip().lower()
        if decision == "abort" or str(state.get("probe_status") or "").strip() == "failed":
            return END
        return "render_html"

    def _llm_artifact_refs(state: Dict[str, Any]) -> Dict[str, Any]:
        overlay_path = cache_dir / "html_llm_probe_overlay.json"
        overlay = state.get("exploration_overlay") if isinstance(state.get("exploration_overlay"), dict) else {}
        if overlay:
            overlay_path.write_text(json.dumps(overlay, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
            return {
                "exploration_overlay": _stage_artifact_ref(
                    overlay_path,
                    schema_version="html_llm_probe_overlay.v1",
                    producer_node="llm_exploration",
                )
            }
        return {}

    def _render_artifact_refs(state: Dict[str, Any]) -> Dict[str, Any]:
        refs = {}
        if output_path.exists():
            refs["html"] = _stage_artifact_ref(output_path, schema_version="html-report.v1", producer_node="render_html")
        return refs

    graph = StateGraph(_HtmlLlmProbeState)
    graph.add_node("load_cache", load_cache)
    graph.add_node("llm_exploration", llm_exploration)
    graph.add_node(
        "eval_gate_after_llm",
        _probe_stage_gate(
            cache_dir=cache_dir,
            stage="llm_exploration",
            next_nodes=["render_html"],
            thread_id=thread_id,
            artifact_ref_builder=_llm_artifact_refs,
        ),
    )
    graph.add_node("render_html", render_html)
    graph.add_node(
        "eval_gate_after_render",
        _probe_stage_gate(
            cache_dir=cache_dir,
            stage="render_html",
            next_nodes=[],
            thread_id=thread_id,
            artifact_ref_builder=_render_artifact_refs,
        ),
    )
    graph.add_edge(START, "load_cache")
    graph.add_edge("load_cache", "llm_exploration")
    graph.add_edge("llm_exploration", "eval_gate_after_llm")
    graph.add_conditional_edges("eval_gate_after_llm", _route_after_llm_gate, {"render_html": "render_html", END: END})
    graph.add_edge("render_html", "eval_gate_after_render")
    graph.add_edge("eval_gate_after_render", END)
    checkpointer, _runtime_profile = get_shared_report_checkpointer(purpose=HTML_LLM_PROBE_PURPOSE)
    return graph.compile(checkpointer=checkpointer)


def _probe_html_llm_graph_command(args: argparse.Namespace) -> int:
    cache_dir = Path(str(args.cache_dir or "").strip()).resolve()
    if not cache_dir.exists() or not cache_dir.is_dir():
        raise FileNotFoundError(f"Report cache directory not found: {cache_dir}")
    output_path = Path(str(args.output or "").strip()).resolve() if str(args.output or "").strip() else cache_dir / "ai_full_report_llm_probe.html"
    thread_id = str(getattr(args, "thread_id", "") or "").strip() or _default_probe_thread_id(cache_dir)
    graph = _build_html_llm_probe_graph(cache_dir=cache_dir, output_path=output_path, thread_id=thread_id)
    config = _runtime_config(thread_id=thread_id, purpose=HTML_LLM_PROBE_PURPOSE)
    result = graph.invoke({}, config)
    snapshot = graph.get_state(config)
    snapshot_payload = _snapshot_to_dict(snapshot)
    interrupts = snapshot_payload.get("interrupts") if isinstance(snapshot_payload.get("interrupts"), list) else []
    status = str(result.get("probe_status") or "").strip() if isinstance(result, dict) else ""
    if interrupts or snapshot_payload.get("next"):
        status = "interrupted"
    trace_path = cache_dir / DEFAULT_HTML_LLM_PROBE_TRACE_FILENAME
    trace_path.write_text(
        json.dumps({"result": result, "snapshot": snapshot_payload}, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    summary = {
        "type": "cli.probe_html_llm_graph.summary",
        "thread_id": thread_id,
        "cache_dir": str(cache_dir),
        "output_path": str(result.get("output_path") or output_path),
        "trace_path": str(trace_path),
        "status": status or "failed",
        "checkpoint_id": str(snapshot_payload.get("checkpoint_id") or "").strip(),
        "next": snapshot_payload.get("next") if isinstance(snapshot_payload.get("next"), list) else [],
        "interrupts": interrupts,
        "model_config": result.get("model_config") if isinstance(result.get("model_config"), dict) else {},
        "probe_error": str(result.get("probe_error") or "").strip(),
        "scorecard": result.get("scorecard") if isinstance(result.get("scorecard"), dict) else {},
        "html_artifact": result.get("html_artifact") if isinstance(result.get("html_artifact"), dict) else {},
        "artifact_refs": result.get("artifact_refs") if isinstance(result.get("artifact_refs"), dict) else {},
        "scorecard_refs": result.get("scorecard_refs") if isinstance(result.get("scorecard_refs"), dict) else {},
        "trace": result.get("trace") if isinstance(result.get("trace"), list) else [],
        "runtime_diagnostics": build_runtime_diagnostics(purpose=HTML_LLM_PROBE_PURPOSE, thread_id=thread_id),
    }
    _safe_stream_write(sys.stdout, json.dumps(summary, ensure_ascii=False, indent=2 if bool(args.json) else None, default=_json_default) + "\n")
    return 0 if summary["status"] in {"completed", "interrupted"} else 1


def _state_runtime_command(args: argparse.Namespace) -> int:
    thread_id = str(args.thread_id or "").strip()
    if not thread_id:
        raise ValueError("--thread-id is required")
    purpose = _runtime_purpose(str(getattr(args, "runtime", "") or "probe"))
    checkpointer, runtime_profile = get_shared_report_checkpointer(purpose=purpose, locator_hint=str(getattr(args, "checkpoint_locator", "") or "").strip())
    del checkpointer
    config = _runtime_config(
        thread_id=thread_id,
        purpose=purpose,
        checkpoint_id=str(getattr(args, "checkpoint_id", "") or "").strip(),
        locator_hint=runtime_profile.checkpoint_locator,
    )
    if purpose == HTML_LLM_PROBE_PURPOSE:
        cache_dir = Path(str(getattr(args, "cache_dir", "") or ".").strip()).resolve()
        output_path = Path(str(getattr(args, "output", "") or "").strip()).resolve() if str(getattr(args, "output", "") or "").strip() else cache_dir / "ai_full_report_llm_probe.html"
        graph = _build_html_llm_probe_graph(cache_dir=cache_dir, output_path=output_path, thread_id=thread_id)
    else:
        graph = _build_runtime_inspection_graph(purpose=purpose, locator_hint=runtime_profile.checkpoint_locator)
    snapshot = graph.get_state(config)
    payload = {
        "type": "cli.inspect_state.summary",
        "runtime": "probe" if purpose == HTML_LLM_PROBE_PURPOSE else "root",
        "thread_id": thread_id,
        "runtime_diagnostics": build_runtime_diagnostics(purpose=purpose, thread_id=thread_id, locator_hint=runtime_profile.checkpoint_locator),
        "snapshot": _snapshot_to_dict(snapshot),
    }
    _safe_stream_write(sys.stdout, json.dumps(payload, ensure_ascii=False, indent=2 if bool(args.json) else None, default=_json_default) + "\n")
    return 0


def _history_runtime_command(args: argparse.Namespace) -> int:
    thread_id = str(args.thread_id or "").strip()
    if not thread_id:
        raise ValueError("--thread-id is required")
    purpose = _runtime_purpose(str(getattr(args, "runtime", "") or "probe"))
    locator_hint = str(getattr(args, "checkpoint_locator", "") or "").strip()
    graph = _build_runtime_inspection_graph(purpose=purpose, locator_hint=locator_hint)
    config = _runtime_config(thread_id=thread_id, purpose=purpose, locator_hint=locator_hint)
    history = [_snapshot_to_dict(snapshot) for snapshot in graph.get_state_history(config)]
    payload = {
        "type": "cli.history.summary",
        "runtime": "probe" if purpose == HTML_LLM_PROBE_PURPOSE else "root",
        "thread_id": thread_id,
        "count": len(history),
        "history": history,
    }
    _safe_stream_write(sys.stdout, json.dumps(payload, ensure_ascii=False, indent=2 if bool(args.json) else None, default=_json_default) + "\n")
    return 0


def _resume_runtime_command(args: argparse.Namespace) -> int:
    runtime = str(getattr(args, "runtime", "") or "probe").strip().lower()
    if runtime not in {"probe", "html-llm-probe"}:
        raise ValueError("resume currently supports --runtime probe.")
    thread_id = str(args.thread_id or "").strip()
    if not thread_id:
        raise ValueError("--thread-id is required")
    cache_dir = Path(str(args.cache_dir or "").strip()).resolve()
    if not cache_dir.exists() or not cache_dir.is_dir():
        raise FileNotFoundError(f"Report cache directory not found: {cache_dir}")
    output_path = Path(str(getattr(args, "output", "") or "").strip()).resolve() if str(getattr(args, "output", "") or "").strip() else cache_dir / "ai_full_report_llm_probe.html"
    graph = _build_html_llm_probe_graph(cache_dir=cache_dir, output_path=output_path, thread_id=thread_id)
    decision = str(getattr(args, "decision", "") or "continue").strip().lower() or "continue"
    config = _runtime_config(thread_id=thread_id, purpose=HTML_LLM_PROBE_PURPOSE)
    result = graph.invoke(Command(resume={"decision": decision}), config)
    snapshot_payload = _snapshot_to_dict(graph.get_state(config))
    interrupts = snapshot_payload.get("interrupts") if isinstance(snapshot_payload.get("interrupts"), list) else []
    status = str(result.get("probe_status") or "").strip() if isinstance(result, dict) else ""
    if interrupts or snapshot_payload.get("next"):
        status = "interrupted"
    payload = {
        "type": "cli.resume.summary",
        "runtime": "probe",
        "thread_id": thread_id,
        "decision": decision,
        "status": status or "failed",
        "checkpoint_id": str(snapshot_payload.get("checkpoint_id") or "").strip(),
        "next": snapshot_payload.get("next") if isinstance(snapshot_payload.get("next"), list) else [],
        "interrupts": interrupts,
        "result": result,
    }
    _safe_stream_write(sys.stdout, json.dumps(payload, ensure_ascii=False, indent=2 if bool(args.json) else None, default=_json_default) + "\n")
    return 0 if payload["status"] in {"completed", "interrupted"} else 1


def _eval_stage_command(args: argparse.Namespace) -> int:
    cache_dir = Path(str(args.cache_dir or "").strip()).resolve()
    stage = str(args.stage or "").strip()
    if not stage:
        raise ValueError("--stage is required")
    scorecard_path = cache_dir / f"{stage}.scorecard.json"
    scorecard = _read_json_if_exists(scorecard_path)
    payload = {
        "type": "cli.eval_stage.summary",
        "runtime": str(getattr(args, "runtime", "") or "probe").strip().lower() or "probe",
        "thread_id": str(getattr(args, "thread_id", "") or "").strip(),
        "stage": stage,
        "scorecard_ref": str(scorecard_path),
        "scorecard": scorecard,
        "status": str(scorecard.get("status") or "missing").strip() if isinstance(scorecard, dict) else "missing",
    }
    _safe_stream_write(sys.stdout, json.dumps(payload, ensure_ascii=False, indent=2 if bool(args.json) else None, default=_json_default) + "\n")
    return 0 if payload["status"] in {"passed", "warning"} else 1


def _replay_from_command(args: argparse.Namespace) -> int:
    thread_id = str(args.thread_id or "").strip()
    checkpoint_id = str(args.checkpoint_id or "").strip()
    if not thread_id or not checkpoint_id:
        raise ValueError("--thread-id and --checkpoint-id are required")
    cache_dir = Path(str(args.cache_dir or "").strip()).resolve()
    if not cache_dir.exists() or not cache_dir.is_dir():
        raise FileNotFoundError(f"Report cache directory not found: {cache_dir}")
    output_path = Path(str(getattr(args, "output", "") or "").strip()).resolve() if str(getattr(args, "output", "") or "").strip() else cache_dir / "ai_full_report_llm_probe.html"
    graph = _build_html_llm_probe_graph(cache_dir=cache_dir, output_path=output_path, thread_id=thread_id)
    config = _runtime_config(thread_id=thread_id, purpose=HTML_LLM_PROBE_PURPOSE, checkpoint_id=checkpoint_id)
    result = graph.invoke(None, config)
    snapshot_payload = _snapshot_to_dict(graph.get_state(_runtime_config(thread_id=thread_id, purpose=HTML_LLM_PROBE_PURPOSE)))
    payload = {
        "type": "cli.replay_from.summary",
        "runtime": "probe",
        "thread_id": thread_id,
        "source_checkpoint_id": checkpoint_id,
        "latest_checkpoint_id": str(snapshot_payload.get("checkpoint_id") or "").strip(),
        "next": snapshot_payload.get("next") if isinstance(snapshot_payload.get("next"), list) else [],
        "result": result,
    }
    _safe_stream_write(sys.stdout, json.dumps(payload, ensure_ascii=False, indent=2 if bool(args.json) else None, default=_json_default) + "\n")
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

    render_html = subparsers.add_parser("render-html-fixture", help="Render HTML report from a replay fixture")
    render_html.add_argument("--fixture", default=str(DEFAULT_HTML_RENDER_FIXTURE_PATH), help="Fixture JSON path")
    render_html.add_argument("--output", default="", help="Output HTML path")
    render_html.add_argument("--json", action="store_true", help="Pretty-print summary JSON")
    render_html.set_defaults(handler=_render_html_fixture_command)

    render_html_cache = subparsers.add_parser("render-html-cache", help="Render HTML report from an existing report cache directory")
    render_html_cache.add_argument("--cache-dir", required=True, help="Report cache directory")
    render_html_cache.add_argument("--exploration-overlay", default="", help="Optional exploration artifact JSON overlay")
    render_html_cache.add_argument("--output", default="", help="Output HTML path")
    render_html_cache.add_argument("--json", action="store_true", help="Pretty-print summary JSON")
    render_html_cache.set_defaults(handler=_render_html_cache_command)

    probe_html_llm = subparsers.add_parser("probe-html-llm-graph", help="Run a LangGraph + LangChain exploration probe and render HTML")
    probe_html_llm.add_argument("--cache-dir", required=True, help="Report cache directory")
    probe_html_llm.add_argument("--output", default="", help="Output HTML path")
    probe_html_llm.add_argument("--thread-id", default="", help="Persistent LangGraph thread id for checkpointed probe")
    probe_html_llm.add_argument("--json", action="store_true", help="Pretty-print summary JSON")
    probe_html_llm.set_defaults(handler=_probe_html_llm_graph_command)

    inspect_state = subparsers.add_parser("inspect-state", help="Inspect latest checkpoint StateSnapshot for a runtime thread")
    inspect_state.add_argument("--runtime", choices=["probe", "root"], default="probe")
    inspect_state.add_argument("--thread-id", required=True)
    inspect_state.add_argument("--checkpoint-id", default="")
    inspect_state.add_argument("--checkpoint-locator", default="")
    inspect_state.add_argument("--cache-dir", default=".", help="Probe cache directory, required for probe graph reconstruction")
    inspect_state.add_argument("--output", default="", help="Probe output path")
    inspect_state.add_argument("--json", action="store_true")
    inspect_state.set_defaults(handler=_state_runtime_command)

    history = subparsers.add_parser("history", help="List checkpoint StateSnapshot history for a runtime thread")
    history.add_argument("--runtime", choices=["probe", "root"], default="probe")
    history.add_argument("--thread-id", required=True)
    history.add_argument("--checkpoint-locator", default="")
    history.add_argument("--cache-dir", default=".", help="Probe cache directory, required for probe graph reconstruction")
    history.add_argument("--output", default="", help="Probe output path")
    history.add_argument("--json", action="store_true")
    history.set_defaults(handler=_history_runtime_command)

    resume = subparsers.add_parser("resume", help="Resume an interrupted checkpointed runtime")
    resume.add_argument("--runtime", choices=["probe", "root"], default="probe")
    resume.add_argument("--thread-id", required=True)
    resume.add_argument("--decision", choices=["continue", "repair", "fork", "abort"], default="continue")
    resume.add_argument("--cache-dir", required=True, help="Probe cache directory")
    resume.add_argument("--output", default="", help="Probe output path")
    resume.add_argument("--json", action="store_true")
    resume.set_defaults(handler=_resume_runtime_command)

    continue_runtime = subparsers.add_parser("continue", help="Continue an interrupted checkpointed runtime")
    continue_runtime.add_argument("--runtime", choices=["probe", "root"], default="probe")
    continue_runtime.add_argument("--thread-id", required=True)
    continue_runtime.add_argument("--cache-dir", required=True, help="Probe cache directory")
    continue_runtime.add_argument("--output", default="", help="Probe output path")
    continue_runtime.add_argument("--json", action="store_true")
    continue_runtime.set_defaults(
        handler=lambda args: _resume_runtime_command(argparse.Namespace(**{**vars(args), "decision": "continue"}))
    )

    eval_stage = subparsers.add_parser("eval-stage", help="Read a stage scorecard without invoking LLM/runtime work")
    eval_stage.add_argument("--runtime", choices=["probe", "root"], default="probe")
    eval_stage.add_argument("--thread-id", default="")
    eval_stage.add_argument("--cache-dir", required=True)
    eval_stage.add_argument("--stage", required=True)
    eval_stage.add_argument("--json", action="store_true")
    eval_stage.set_defaults(handler=_eval_stage_command)

    replay_from = subparsers.add_parser("replay-from", help="Replay probe runtime from a historical checkpoint id")
    replay_from.add_argument("--runtime", choices=["probe"], default="probe")
    replay_from.add_argument("--thread-id", required=True)
    replay_from.add_argument("--checkpoint-id", required=True)
    replay_from.add_argument("--cache-dir", required=True)
    replay_from.add_argument("--output", default="")
    replay_from.add_argument("--json", action="store_true")
    replay_from.set_defaults(handler=_replay_from_command)

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

    start = subparsers.add_parser("start", help="Start the real report runtime end-to-end")
    _add_target_arguments(start)
    start.add_argument("--start", default="", help="Start date (YYYY-MM-DD)")
    start.add_argument("--end", default="", help="End date (YYYY-MM-DD)")
    start.add_argument("--mode", choices=["fast", "research"], default="fast")
    start.add_argument("--skip-validation", action="store_true")
    start.add_argument("--task-id", default="", help="Optional runtime task id override")
    start.add_argument("--thread-id", default="", help="Optional runtime thread id override")
    start.add_argument("--checkpoint-resume", action="store_true", help="Resume current range from checkpoint cache when possible")
    start.add_argument("--event-log", default="", help="JSONL path for raw runtime events")
    start.add_argument("--json", action="store_true", help="Print final summary as JSON")
    start.add_argument("--quiet-events", action="store_true", help="Do not stream raw events to stderr")
    start.set_defaults(handler=_run_command)

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
