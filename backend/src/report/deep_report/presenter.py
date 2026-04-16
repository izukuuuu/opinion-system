from __future__ import annotations

from typing import Any, Callable, Dict

from .graph_runtime import run_report_compilation_graph
from .report_ir import summarize_report_ir


def _report_source(payload: Dict[str, Any]) -> Dict[str, Any]:
    report_data = payload.get("report_data")
    if isinstance(report_data, dict):
        return report_data
    return payload


def render_markdown(payload: Dict[str, Any]) -> str:
    compiled = compile_markdown_artifacts(payload)
    return str(compiled.get("markdown") or "").strip()


def compile_markdown_artifacts(
    payload: Dict[str, Any],
    *,
    allow_review_pending: bool = False,
    event_callback: Callable[[Dict[str, Any]], None] | None = None,
    checkpointer_path: str = "",
    graph_thread_id: str = "",
    review_decision: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    report_ir = payload.get("report_ir") if isinstance(payload.get("report_ir"), dict) else {}
    if not report_ir:
        raise ValueError("render_markdown requires ReportIR and no longer accepts raw structured payload compilation.")
    utility_assessment = report_ir.get("utility_assessment") if isinstance(report_ir.get("utility_assessment"), dict) else {}
    review_decision_text = str((review_decision or {}).get("decision") or "").strip().lower()
    compiled = run_report_compilation_graph(
        payload,
        event_callback=event_callback,
        checkpointer_path=checkpointer_path,
        graph_thread_id=graph_thread_id,
        review_decision=review_decision,
    )
    if str(compiled.get("status") or "").strip() == "interrupted":
        return compiled
    markdown_conformance = compiled.get("factual_conformance") if isinstance(compiled.get("factual_conformance"), dict) else {}
    graph_review_metadata = markdown_conformance.get("metadata") if isinstance(markdown_conformance.get("metadata"), dict) else {}
    graph_review_decision_text = str(
        graph_review_metadata.get("review_decision")
        or graph_review_metadata.get("decision")
        or ""
    ).strip().lower()
    effective_review_decision_text = review_decision_text or graph_review_decision_text
    human_override_accepted = effective_review_decision_text in {"approve", "edit"}
    markdown_conformance = {
        **markdown_conformance,
        "metadata": {
            **dict(markdown_conformance.get("metadata") or {}),
            "utility_assessment": utility_assessment,
            "human_override_accepted": human_override_accepted,
            "review_decision": effective_review_decision_text,
        },
    }
    compiled["factual_conformance"] = markdown_conformance
    compiled["utility_assessment"] = utility_assessment
    compiled["review_required"] = bool(markdown_conformance.get("requires_human_review") or compiled.get("review_required"))
    return compiled


def build_structured_digest(payload: Dict[str, Any]) -> Dict[str, Any]:
    report_ir = payload.get("report_ir") if isinstance(payload.get("report_ir"), dict) else {}
    if report_ir:
        return summarize_report_ir(report_ir)
    source = _report_source(payload)
    task = source.get("task") if isinstance(source.get("task"), dict) else {}
    conclusion = source.get("conclusion") if isinstance(source.get("conclusion"), dict) else {}
    report_document = payload.get("report_document") if isinstance(payload.get("report_document"), dict) else {}
    report_ir = payload.get("report_ir") if isinstance(payload.get("report_ir"), dict) else {}
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
            "timeline": len(source.get("timeline") or []),
            "subjects": len(source.get("subjects") or []),
            "evidence": len(source.get("key_evidence") or []),
            "conflicts": len(source.get("conflict_points") or []),
            "propagation": len(source.get("propagation_features") or []),
            "risks": len(source.get("risk_judgement") or []),
            "actions": len(source.get("suggested_actions") or []),
            "citations": len(source.get("citations") or []),
            "sections": len(report_document.get("sections") or []),
            "figures": len(report_ir.get("figures") or payload.get("figures") or []),
        },
    }


def _evaluate_markdown_health(markdown: str) -> Dict[str, Any]:
    text = str(markdown or "").strip()
    if not text:
        return {
            "is_healthy": False,
            "degraded_reason": "empty_markdown",
            "heading_count": 0,
            "body_line_count": 0,
        }
    lines = [line.rstrip() for line in text.splitlines()]
    heading_count = len([line for line in lines if line.lstrip().startswith("## ")])
    body_lines = [
        line.strip()
        for line in lines
        if line.strip()
        and not line.lstrip().startswith("#")
        and not line.lstrip().startswith(">")
        and line.strip() != "---"
    ]
    non_heading_chars = sum(len(line) for line in body_lines)
    only_headings = bool(heading_count) and not body_lines
    too_sparse = non_heading_chars < 120
    degraded_reason = ""
    if only_headings:
        degraded_reason = "heading_only_skeleton"
    elif too_sparse:
        degraded_reason = "markdown_body_too_sparse"
    return {
        "is_healthy": not bool(degraded_reason),
        "degraded_reason": degraded_reason,
        "heading_count": heading_count,
        "body_line_count": len(body_lines),
        "non_heading_char_count": non_heading_chars,
    }


def build_full_payload(
    structured_payload: Dict[str, Any],
    markdown: str,
    *,
    cache_version: int,
    draft_bundle: Dict[str, Any] | None = None,
    draft_bundle_v2: Dict[str, Any] | None = None,
    styled_draft_bundle: Dict[str, Any] | None = None,
    factual_conformance: Dict[str, Any] | None = None,
    scene_profile: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    source = _report_source(structured_payload)
    task = source.get("task") if isinstance(source.get("task"), dict) else {}
    title = str(task.get("topic_label") or task.get("topic_identifier") or "AI 完整报告").strip() or "AI 完整报告"
    report_ir = structured_payload.get("report_ir") if isinstance(structured_payload.get("report_ir"), dict) else {}
    artifact_manifest = structured_payload.get("artifact_manifest") if isinstance(structured_payload.get("artifact_manifest"), dict) else {}
    utility_assessment = report_ir.get("utility_assessment") if isinstance(report_ir.get("utility_assessment"), dict) else {}
    markdown_text = str(markdown or "").strip()
    markdown_health = _evaluate_markdown_health(markdown_text)
    degraded_reason = str(markdown_health.get("degraded_reason") or "").strip()
    draft_bundle_v2_payload = draft_bundle_v2 if isinstance(draft_bundle_v2, dict) else {}
    draft_bundle_v2_meta = draft_bundle_v2_payload.get("metadata") if isinstance(draft_bundle_v2_payload.get("metadata"), dict) else {}
    scene_payload = scene_profile if isinstance(scene_profile, dict) else {}
    selected_template = (
        draft_bundle_v2_meta.get("selected_template")
        if isinstance(draft_bundle_v2_meta.get("selected_template"), dict)
        else {
            "template_id": str(scene_payload.get("template_id") or "").strip(),
            "template_name": str(scene_payload.get("template_name") or "").strip(),
            "template_path": str(scene_payload.get("template_path") or "").strip(),
            "scene_id": str(scene_payload.get("scene_id") or "").strip(),
            "scene_label": str(scene_payload.get("scene_label") or "").strip(),
            "score": float(scene_payload.get("selection_score") or 0.0),
            "matched_reasons": list(scene_payload.get("matched_reasons") or []),
        }
    )
    section_generation_receipts = (
        draft_bundle_v2_meta.get("section_generation_receipts")
        if isinstance(draft_bundle_v2_meta.get("section_generation_receipts"), list)
        else []
    )
    degraded_sections = (
        draft_bundle_v2_meta.get("degraded_sections")
        if isinstance(draft_bundle_v2_meta.get("degraded_sections"), list)
        else []
    )
    full_payload = {
        **structured_payload,
        "title": title,
        "rangeText": f"{str(task.get('start') or '').strip()} -> {str(task.get('end') or '').strip()}",
        "markdown": markdown_text,
        "degraded_reason": degraded_reason,
        "selected_template": selected_template,
        "template_match_reasons": list(selected_template.get("matched_reasons") or []) if isinstance(selected_template, dict) else [],
        "section_generation_receipts": section_generation_receipts,
        "degraded_sections": degraded_sections,
        "draft_bundle": draft_bundle if isinstance(draft_bundle, dict) else {},
        "draft_bundle_v2": draft_bundle_v2_payload,
        "styled_draft_bundle": styled_draft_bundle if isinstance(styled_draft_bundle, dict) else {},
        "report_ir_summary": summarize_report_ir(report_ir) if report_ir else {},
        "meta": {
            "cache_version": int(cache_version),
            "thread_id": str(task.get("thread_id") or "").strip(),
            "structured_digest": build_structured_digest(structured_payload),
            "report_ir_summary": summarize_report_ir(report_ir) if report_ir else {},
            "artifact_manifest": artifact_manifest,
            "figure_ids": [str(item.get("figure_id") or "").strip() for item in (report_ir.get("figures") or []) if isinstance(item, dict)],
            "figure_policy_version": str((((report_ir.get("figures") or [{}])[0] if isinstance(report_ir.get("figures"), list) and report_ir.get("figures") else {}).get("policy_version")) or "figure-policy.v1"),
            "draft_trace_summary": {
                "unit_count": len(((draft_bundle or {}).get("units")) or []),
                "section_order": list(((draft_bundle or {}).get("section_order")) or []),
            },
            "style_trace_summary": {
                "unit_count": len(((styled_draft_bundle or {}).get("units")) or []),
                "rewrite_ops": list(((styled_draft_bundle or {}).get("rewrite_ops")) or []),
                "policy_version": str((styled_draft_bundle or {}).get("policy_version") or ""),
            },
            "factual_conformance": factual_conformance if isinstance(factual_conformance, dict) else {},
            "markdown_health": markdown_health,
            "selected_template": selected_template,
            "template_match_reasons": list(selected_template.get("matched_reasons") or []) if isinstance(selected_template, dict) else [],
            "section_generation_receipts": section_generation_receipts,
            "degraded_sections": degraded_sections,
            "utility_assessment": utility_assessment,
            "utility_gate_trace": {
                "decision": str(utility_assessment.get("decision") or "").strip(),
                "missing_dimensions": list(utility_assessment.get("missing_dimensions") or []),
                "fallback_trace": list(utility_assessment.get("fallback_trace") or []),
                "improvement_trace": list(utility_assessment.get("improvement_trace") or []),
            },
        },
    }
    if isinstance(structured_payload.get("meta"), dict):
        full_payload["meta"] = {**structured_payload.get("meta"), **full_payload["meta"]}
    return full_payload
