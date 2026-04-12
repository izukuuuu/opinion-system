from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..deep_report import REPORT_CACHE_FILENAME, generate_report_payload
from ..deep_report.payloads import (
    get_corpus_coverage_payload,
    normalize_task_payload,
    retrieve_evidence_cards_payload,
)
from ..deep_report.compiler import (
    assemble_writer_context,
    build_layout_plan,
    build_section_budget,
    build_section_plan,
    compile_draft_units,
    resolve_style_profile,
    run_factual_conformance,
    run_stylistic_rewrite,
    select_scene_profile,
)
from ..deep_report.deterministic import ensure_cache_dir
from ..deep_report.presenter import compile_markdown_artifacts
from ..deep_report.report_ir import attach_report_ir, build_artifact_manifest, summarize_report_ir
from ..deep_report.schemas import CorpusCoverageResult, EvidenceCardPage
from ...utils.ai.langchain_client import build_langchain_chat_model


def _load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    return value if isinstance(value, dict) else {}


def _task_path(task_id: str) -> Path:
    return Path(__file__).resolve().parents[3] / "data" / "_report" / "tasks" / f"{task_id}.json"


def _issue_dump(issue: Any) -> Dict[str, Any]:
    if hasattr(issue, "model_dump"):
        return issue.model_dump()
    return dict(issue) if isinstance(issue, dict) else {"value": str(issue)}


def _bundle_issue_summary(draft_bundle: Any, conformance: Any) -> Dict[str, Any]:
    issues = list(getattr(conformance, "issues", []) or [])
    failing_units: List[Dict[str, Any]] = []
    issue_by_trace = {}
    for issue in issues:
        for trace_id in getattr(issue, "trace_ids", []) or []:
            issue_by_trace.setdefault(str(trace_id), []).append(issue)
    for unit in getattr(draft_bundle, "units", []) or []:
        trace_ids = list(dict.fromkeys(list(getattr(unit, "trace_ids", []) or []) + list(getattr(unit, "claim_ids", []) or []) + list(getattr(unit, "evidence_ids", []) or []) + list(getattr(unit, "risk_ids", []) or []) + list(getattr(unit, "unresolved_point_ids", []) or []) + list(getattr(unit, "stance_row_ids", []) or [])))
        related = []
        for trace_id in trace_ids:
            related.extend(issue_by_trace.get(str(trace_id), []))
        if not trace_ids and any(getattr(item, "sentence", "") == getattr(unit, "text", "") for item in issues):
            related = [item for item in issues if getattr(item, "sentence", "") == getattr(unit, "text", "")]
        if not related:
            continue
        failing_units.append(
            {
                "unit_id": str(getattr(unit, "unit_id", "") or "").strip(),
                "section_role": str(getattr(unit, "section_role", "") or "").strip(),
                "text": str(getattr(unit, "text", "") or "").strip()[:240],
                "trace_ids": trace_ids,
                "issues": [_issue_dump(item) for item in related[:4]],
            }
        )
    return {
        "passed": bool(getattr(conformance, "passed", False)),
        "issue_count": len(issues),
        "issues": [_issue_dump(item) for item in issues[:20]],
        "failing_units": failing_units[:20],
        "metadata": dict(getattr(conformance, "metadata", {}) or {}),
    }


def _ensure_report_ir(payload: Dict[str, Any], *, topic_identifier: str, start: str, end: str, task_id: str) -> Dict[str, Any]:
    if isinstance(payload.get("report_ir"), dict):
        return payload
    cache_dir = ensure_cache_dir(topic_identifier, start, end)
    manifest = build_artifact_manifest(
        topic_identifier=topic_identifier,
        thread_id=str(((payload.get("task") or {}) if isinstance(payload.get("task"), dict) else {}).get("thread_id") or "").strip(),
        task_id=task_id,
        structured_path=str(cache_dir / REPORT_CACHE_FILENAME),
        agenda_path=str(cache_dir / "agenda_frame_map.json"),
        conflict_path=str(cache_dir / "conflict_map.json"),
        mechanism_path=str(cache_dir / "mechanism_summary.json"),
        utility_path=str(cache_dir / "utility_assessment.json"),
        ir_path=str(cache_dir / "report_ir.json"),
        previous_manifest=payload.get("artifact_manifest") if isinstance(payload.get("artifact_manifest"), dict) else None,
    )
    return attach_report_ir(payload, artifact_manifest=manifest, task_id=task_id)


def _split_source_id(source_id: str) -> tuple[str, str]:
    source_text = str(source_id or "").strip()
    if not source_text:
        return "", ""
    source_file, sep, row_index = source_text.rpartition(":")
    if not sep:
        return "", source_text
    return source_file, row_index


def _build_raw_evidence_audit(
    *,
    task_id: str,
    task: Dict[str, Any],
    structured: Dict[str, Any],
) -> Dict[str, Any]:
    topic_identifier = str(task.get("topic_identifier") or "").strip()
    topic_label = str(task.get("topic") or task.get("topic_label") or topic_identifier).strip() or topic_identifier
    start = str(task.get("start") or "").strip()
    end = str(task.get("end") or start).strip() or start
    mode = str(task.get("mode") or "fast").strip() or "fast"
    normalized = normalize_task_payload(
        task_text=f"{topic_label} {mode} 舆情分析",
        topic_identifier=topic_identifier,
        start=start,
        end=end,
        mode=mode,
        hints_json=json.dumps({"topic": topic_label}, ensure_ascii=False),
    )
    coverage = CorpusCoverageResult.model_validate(
        get_corpus_coverage_payload(
            normalized_task_json=json.dumps(normalized.get("result") or {}, ensure_ascii=False),
            include_samples=True,
            limit=12,
        )
    )
    evidence_page = EvidenceCardPage.model_validate(
        retrieve_evidence_cards_payload(
            normalized_task_json=json.dumps(normalized.get("result") or {}, ensure_ascii=False),
            intent="overview",
            limit=12,
        )
    )
    cards = list(evidence_page.result or [])
    trace_source_ids = [str(path).strip() for path in (evidence_page.trace.source_ids or []) if str(path or "").strip()]
    source_files = []
    for source_id in trace_source_ids:
        source_file, _row_index = _split_source_id(source_id)
        if source_file and source_file not in source_files:
            source_files.append(source_file)
    existing_source_files = [path for path in source_files if Path(path).exists()]
    cards_with_source_id = [card for card in cards if str(card.source_id or "").strip()]
    resolved_card_sources = []
    unresolved_card_sources = []
    for card in cards_with_source_id:
        source_file, row_index = _split_source_id(card.source_id)
        if source_file and Path(source_file).exists():
            resolved_card_sources.append(
                {
                    "evidence_id": card.evidence_id,
                    "source_id": card.source_id,
                    "source_file": source_file,
                    "row_index": row_index,
                }
            )
        else:
            unresolved_card_sources.append(
                {
                    "evidence_id": card.evidence_id,
                    "source_id": card.source_id,
                    "source_file": source_file,
                    "row_index": row_index,
                }
            )
    structured_key_evidence = structured.get("key_evidence") if isinstance(structured.get("key_evidence"), list) else []
    explicit_structured_refs = [
        item
        for item in structured_key_evidence
        if isinstance(item, dict) and any(str(item.get(field) or "").strip() for field in ("source_id", "source_file", "dataset_id"))
    ]
    report_ir = structured.get("report_ir") if isinstance(structured.get("report_ir"), dict) else {}
    evidence_ledger = ((report_ir.get("evidence_ledger") or {}) if isinstance(report_ir.get("evidence_ledger"), dict) else {})
    ledger_entries = evidence_ledger.get("entries") if isinstance(evidence_ledger.get("entries"), list) else []
    explicit_ledger_refs = [
        item
        for item in ledger_entries
        if isinstance(item, dict) and any(str(item.get(field) or "").strip() for field in ("source_id", "source_file", "dataset_id"))
    ]
    request_payload = task.get("request") if isinstance(task.get("request"), dict) else {}
    dataset_id = str(request_payload.get("dataset_id") or "").strip()
    return {
        "task_id": task_id,
        "dataset_binding": {
            "request_dataset_id": dataset_id,
            "status": "explicit_dataset" if dataset_id else "topic_archive_only",
        },
        "coverage": {
            "matched_count": int(coverage.coverage.matched_count or 0),
            "readiness_flags": list(coverage.coverage.readiness_flags or []),
            "platform_counts": dict(coverage.coverage.platform_counts or {}),
        },
        "evidence_cards": {
            "count": len(cards),
            "cards_with_source_id": len(cards_with_source_id),
            "cards_with_existing_source_file": len(resolved_card_sources),
            "cards_with_url": len([card for card in cards if str(card.url or "").strip()]),
            "trace_source_file_count": len(source_files),
            "trace_source_file_existing_count": len(existing_source_files),
            "trace_source_id_count": len(trace_source_ids),
            "sample_resolved_sources": resolved_card_sources[:5],
            "sample_unresolved_sources": unresolved_card_sources[:5],
        },
        "cache_projection": {
            "structured_key_evidence_count": len(structured_key_evidence),
            "structured_key_evidence_with_explicit_source_ref": len(explicit_structured_refs),
            "report_ir_evidence_entry_count": len(ledger_entries),
            "report_ir_evidence_with_explicit_source_ref": len(explicit_ledger_refs),
        },
    }


def _build_model_audit() -> Dict[str, Any]:
    _llm, client_cfg = build_langchain_chat_model(task="report", model_role="report", temperature=0.15, max_tokens=4200)
    safe_cfg = {}
    if isinstance(client_cfg, dict):
        safe_cfg = {
            "provider": str(client_cfg.get("provider") or "").strip(),
            "model": str(client_cfg.get("model") or "").strip(),
            "base_url": str(client_cfg.get("base_url") or "").strip(),
            "model_role": str(client_cfg.get("model_role") or "").strip(),
            "temperature": client_cfg.get("temperature"),
            "max_tokens": client_cfg.get("max_tokens"),
            "timeout": client_cfg.get("timeout"),
            "max_retries": client_cfg.get("max_retries"),
        }
    return {
        "replay_pipeline": "generate_report_payload + draft/styled/final compiler",
        "uses_report_runtime_model": False,
        "reason": "该 replay 直接调用 generate_report_payload() 与 compile_markdown_artifacts()，不会进入 run_or_resume_deep_report_task() 的 report runtime agent。",
        "configured_report_runtime_model": safe_cfg,
    }


def build_real_report_diagnostic(
    *,
    task_id: str,
    source_mode: str = "cache",
) -> Dict[str, Any]:
    task = _load_json(_task_path(task_id))
    topic_identifier = str(task.get("topic_identifier") or "").strip()
    topic_label = str(task.get("topic") or task.get("topic_label") or topic_identifier).strip() or topic_identifier
    start = str(task.get("start") or "").strip()
    end = str(task.get("end") or start).strip() or start
    cache_dir = ensure_cache_dir(topic_identifier, start, end)

    if source_mode == "regenerate":
        structured = generate_report_payload(
            topic_identifier,
            start,
            end,
            topic_label=topic_label,
            regenerate=True,
            mode=str(task.get("mode") or "fast").strip() or "fast",
            thread_id=str(task.get("thread_id") or "").strip(),
            task_id=task_id,
        )
        source_path = str(cache_dir / REPORT_CACHE_FILENAME)
    else:
        source_path = str(cache_dir / REPORT_CACHE_FILENAME)
        structured = _load_json(Path(source_path))

    structured = _ensure_report_ir(structured, topic_identifier=topic_identifier, start=start, end=end, task_id=task_id)
    report_ir = structured.get("report_ir") if isinstance(structured.get("report_ir"), dict) else {}

    scene = select_scene_profile(report_ir)
    style = resolve_style_profile(report_ir, scene)
    layout = build_layout_plan(report_ir, scene, style)
    budget = build_section_budget(report_ir, scene, layout)
    section_plan = build_section_plan(report_ir, layout, budget)
    draft_bundle = compile_draft_units(report_ir, section_plan)
    draft_conformance = run_factual_conformance(report_ir, draft_bundle)
    writer_context = assemble_writer_context(report_ir, scene, style, layout, budget)
    styled_bundle = run_stylistic_rewrite(report_ir, draft_bundle, writer_context)
    style_conformance = run_factual_conformance(report_ir, styled_bundle)

    compile_result: Dict[str, Any]
    try:
        compiled = compile_markdown_artifacts(structured, allow_review_pending=True)
        compile_result = {
            "ok": True,
            "markdown_length": len(str(compiled.get("markdown") or "").strip()),
            "review_required": bool(compiled.get("review_required")),
            "factual_conformance": compiled.get("factual_conformance") if isinstance(compiled.get("factual_conformance"), dict) else {},
        }
    except Exception as exc:
        compile_result = {
            "ok": False,
            "error_type": exc.__class__.__name__,
            "error_message": str(exc),
        }

    return {
        "task": {
            "task_id": task_id,
            "topic_identifier": topic_identifier,
            "topic_label": topic_label,
            "start": start,
            "end": end,
            "mode": str(task.get("mode") or "fast").strip() or "fast",
            "thread_id": str(task.get("thread_id") or "").strip(),
            "source_mode": source_mode,
        },
        "paths": {
            "task_json": str(_task_path(task_id)),
            "cache_dir": str(cache_dir),
            "structured_cache": source_path,
        },
        "raw_evidence_audit": _build_raw_evidence_audit(task_id=task_id, task=task, structured=structured),
        "model_audit": _build_model_audit(),
        "structured": {
            "has_report_ir": bool(report_ir),
            "report_ir_summary": summarize_report_ir(report_ir) if report_ir else {},
            "utility_decision": str((report_ir.get("utility_assessment") or {}).get("decision") or "").strip() if report_ir else "",
        },
        "draft_bundle": {
            "unit_count": len(getattr(draft_bundle, "units", []) or []),
            "section_order": list(getattr(draft_bundle, "section_order", []) or []),
            "conformance": _bundle_issue_summary(draft_bundle, draft_conformance),
        },
        "styled_bundle": {
            "unit_count": len(getattr(styled_bundle, "units", []) or []),
            "rewrite_ops": list(getattr(styled_bundle, "rewrite_ops", []) or []),
            "conformance": _bundle_issue_summary(styled_bundle, style_conformance),
        },
        "final_compile": compile_result,
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Replay a real report task and inspect structured -> draft -> markdown compilation.")
    parser.add_argument("--task-id", required=True, help="Report task id, e.g. rp-20260411-121934-d70c11")
    parser.add_argument("--source-mode", choices=["cache", "regenerate"], default="cache")
    parser.add_argument("--output", default="", help="Optional JSON output path")
    args = parser.parse_args(argv)

    diagnostic = build_real_report_diagnostic(task_id=str(args.task_id).strip(), source_mode=str(args.source_mode).strip())
    output_path = Path(str(args.output).strip()) if str(args.output).strip() else None
    if output_path is not None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(diagnostic, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        print(json.dumps(diagnostic, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
