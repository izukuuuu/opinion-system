from __future__ import annotations

from typing import Any, Callable, Dict

from .graph_runtime import run_report_compilation_graph
from .schemas import FactualConformanceIssue
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
    utility_decision = str(utility_assessment.get("decision") or "pass").strip() or "pass"
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
    if (
        utility_decision == "pass"
        and not (markdown_conformance.get("issues") or [])
        and not (markdown_conformance.get("semantic_deltas") or [])
    ):
        markdown_conformance = {
            **markdown_conformance,
            "passed": True,
            "can_auto_recover": False,
            "requires_human_review": False,
        }
    if utility_decision != "pass":
        issues = markdown_conformance.get("issues") if isinstance(markdown_conformance.get("issues"), list) else []
        issues.append(
            FactualConformanceIssue(
                issue_id="utility-gate",
                issue_type="utility_gate_violation",
                message="当前 judgment object 尚未满足进入正式文稿的决策可用性门禁。",
                section_role="utility",
                sentence=str(utility_assessment.get("next_action") or "").strip(),
                trace_ids=[],
                suggested_action=str(utility_assessment.get("next_action") or "").strip(),
            ).model_dump()
        )
        markdown_conformance = {
            **markdown_conformance,
            "issues": issues,
            "passed": False,
            "can_auto_recover": utility_decision == "fallback_recompile",
            "requires_human_review": utility_decision == "require_semantic_review" and not human_override_accepted,
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
    # fallback_recompile 允许继续编译流程（can_auto_recover=True 表示可自动恢复）
    # require_semantic_review 需要人工审核，由 allow_review_pending 控制
    if not markdown_conformance.get("passed") and not allow_review_pending and not human_override_accepted:
        raise ValueError("compile_markdown_artifacts aborted: final markdown requires review or contains novel claims.")
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


def build_full_payload(
    structured_payload: Dict[str, Any],
    markdown: str,
    *,
    cache_version: int,
    draft_bundle: Dict[str, Any] | None = None,
    styled_draft_bundle: Dict[str, Any] | None = None,
    factual_conformance: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    source = _report_source(structured_payload)
    task = source.get("task") if isinstance(source.get("task"), dict) else {}
    title = str(task.get("topic_label") or task.get("topic_identifier") or "AI 完整报告").strip() or "AI 完整报告"
    report_ir = structured_payload.get("report_ir") if isinstance(structured_payload.get("report_ir"), dict) else {}
    artifact_manifest = structured_payload.get("artifact_manifest") if isinstance(structured_payload.get("artifact_manifest"), dict) else {}
    utility_assessment = report_ir.get("utility_assessment") if isinstance(report_ir.get("utility_assessment"), dict) else {}
    full_payload = {
        **structured_payload,
        "title": title,
        "rangeText": f"{str(task.get('start') or '').strip()} -> {str(task.get('end') or '').strip()}",
        "markdown": str(markdown or "").strip(),
        "draft_bundle": draft_bundle if isinstance(draft_bundle, dict) else {},
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
