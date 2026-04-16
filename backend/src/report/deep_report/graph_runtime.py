from __future__ import annotations

import copy
import operator
import re
import uuid
from pathlib import Path
from typing import Annotated, Any, Callable, Dict, List, Optional, TypedDict

from langgraph.errors import GraphInterrupt
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, Send, interrupt

from ..agent_runtime import ensure_langchain_uuid_compat
from ..runtime_infra import build_report_runnable_config, open_report_checkpointer
from .compiler import (
    apply_guardrails,
    assemble_writer_context,
    build_conformance_policy_registry,
    build_layout_plan,
    build_section_budget,
    build_section_plan,
    run_factual_conformance,
    sanitize_public_markdown,
    select_scene_profile,
    resolve_style_profile,
)
from .schemas import (
    CommitArtifactRecord,
    DeepReportGraphState,
    DraftBundle,
    DraftBundleV2,
    DraftUnit,
    DraftUnitV2,
    FactualConformanceIssue,
    FactualConformanceResult,
    RepairPatch,
    RepairPlanV2,
    ReviewFeedbackContract,
    RewriteContract,
    TraceRef,
    ValidationFailure,
    ValidationResultV2,
)


def _accumulate_or_reset(existing: List, update: Optional[List]) -> List:
    """LangGraph 自定义 reducer：update=None 时重置为空列表，否则追加。

    标准 operator.add 无法将列表清空（existing + [] == existing），
    finalize 节点需要通过返回 None 而非 [] 来触发重置。
    """
    if update is None:
        return []
    return (existing or []) + update


class _GraphState(TypedDict, total=False):
    payload: Dict[str, Any]
    report_ir: Dict[str, Any]
    task: Dict[str, Any]
    utility_assessment: Dict[str, Any]
    policy_registry: Dict[str, Any]
    scene_profile: Dict[str, Any]
    style_profile: Dict[str, Any]
    layout_plan: Dict[str, Any]
    section_budget: Dict[str, Any]
    writer_context: Dict[str, Any]
    section_plan: Dict[str, Any]
    draft_bundle: Dict[str, Any]
    draft_bundle_v2: Dict[str, Any]
    validation_result_v2: Dict[str, Any]
    repair_plan_v2: Dict[str, Any]
    graph_state_v2: Dict[str, Any]
    markdown: str
    execution_phase: str
    rewrite_round: int
    rewrite_budget: int
    rewrite_issue_count: int
    approval_required: bool
    approval_status: str
    finalization_mode: str
    commit_pending: bool
    commit_idempotency_key: str
    review_required: bool
    blocked_reason: str
    repair_count: int
    structured_report_current: Dict[str, Any]
    draft_bundle_current: Dict[str, Any]
    final_markdown_current: str
    rewrite_contract: Dict[str, Any]
    review_feedback_contract: Dict[str, Any]
    source_checkpoint_id: str
    parent_artifact_id: str
    repaired_unit_ids: List[str]
    dropped_unit_ids: List[str]
    unchanged_unit_ids: List[str]
    review_feedback_rounds: Annotated[List[Dict[str, Any]], operator.add]
    validation_issues: Annotated[List[Dict[str, Any]], operator.add]
    repair_history: Annotated[List[Dict[str, Any]], operator.add]
    semantic_review_records: Annotated[List[Dict[str, Any]], operator.add]
    progress_events: Annotated[List[Dict[str, Any]], operator.add]
    rewrite_lineage: Annotated[List[Dict[str, Any]], operator.add]
    commit_artifacts: Annotated[List[Dict[str, Any]], operator.add]
    visited_nodes: List[str]
    current_node: str
    planner_slots: List[Dict[str, Any]]
    planner_slot: Dict[str, Any]
    section_batches: Annotated[List[Dict[str, Any]], _accumulate_or_reset]
    repair_patch: Dict[str, Any]
    repair_batches: Annotated[List[Dict[str, Any]], _accumulate_or_reset]
    final_output: Dict[str, Any]


_TRACEABLE_UNIT_TYPES = {"observation", "finding", "mechanism", "risk", "recommendation", "unresolved"}

_DEFAULT_ALLOWED_REWRITE_OPS = ["downtone", "delete_untraced", "move_to_unverified", "rephrase"]
_DEFAULT_FORBIDDEN_REWRITE_OPS = ["add_fact", "add_actor", "add_risk", "add_recommendation", "expand_scope"]


def compile_draft_units(report_ir: Dict[str, Any], section_plan: Dict[str, Any], scene_profile: Any) -> DraftBundleV2:
    from .deep_writer import compile_draft_units_with_llm

    result = compile_draft_units_with_llm(report_ir, section_plan, scene_profile)
    if isinstance(result, DraftBundle):
        return upgrade_draft_bundle_to_v2(report_ir, result)
    if isinstance(result, dict) and result.get("units") is not None and result.get("schema_version") != "draft-bundle.v2":
        return upgrade_draft_bundle_to_v2(report_ir, result)
    return result if isinstance(result, DraftBundleV2) else DraftBundleV2.model_validate(result)


def _payload_from_state(state: _GraphState) -> Dict[str, Any]:
    payload = state.get("payload") if isinstance(state.get("payload"), dict) else {}
    if payload:
        return payload
    report_ir = state.get("report_ir") if isinstance(state.get("report_ir"), dict) else {}
    task = state.get("task") if isinstance(state.get("task"), dict) else {}
    return {
        "report_ir": report_ir,
        "task": task,
    }


def _emit(event_callback: Callable[[Dict[str, Any]], None] | None, event: Dict[str, Any]) -> None:
    if callable(event_callback):
        event_callback(event)


def _emit_graph_event(
    event_callback: Callable[[Dict[str, Any]], None] | None,
    *,
    event_type: str,
    node_name: str,
    phase: str,
    title: str,
    message: str,
    payload: Dict[str, Any] | None = None,
) -> None:
    _emit(
        event_callback,
        {
            "type": event_type,
            "phase": phase,
            "agent": node_name,
            "title": title,
            "message": message,
            "payload": payload or {},
        },
    )


def _state_progress_event(*, event_type: str, node_name: str, phase: str, message: str, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
    return {
        "event_type": event_type,
        "node_name": node_name,
        "phase": phase,
        "message": message,
        "payload": payload or {},
    }


def _json_dumpable(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump()
    return value


def _safe_sentence_limit(text: str, *, limit: int) -> str:
    cleaned = str(text or "").strip()
    if not cleaned:
        return ""
    sentences = re.split(r"(?<=[。！？!?])\s*", cleaned)
    return " ".join([item for item in sentences if item][:limit]).strip() or cleaned


def _build_commit_idempotency_key(*, task_id: str, artifact_type: str, rewrite_round: int, schema_version: str) -> str:
    return "::".join(
        [
            str(task_id or "").strip() or "missing-task",
            str(artifact_type or "").strip() or "artifact",
            str(int(rewrite_round or 0)),
            str(schema_version or "").strip() or "schema",
        ]
    )


def _upsert_json_artifact(path_text: str, payload: Dict[str, Any]) -> None:
    path = Path(str(path_text or "").strip())
    if not str(path):
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(__import__("json").dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _artifact_paths_from_task(task: Dict[str, Any]) -> Dict[str, str]:
    raw = task.get("artifact_paths") if isinstance(task.get("artifact_paths"), dict) else {}
    return {str(key).strip(): str(value).strip() for key, value in raw.items() if str(key).strip() and str(value).strip()}


def _node_phase(node_name: str) -> str:
    if node_name in {
        "unit_validator",
        "repair_patch_planner",
        "repair_worker",
        "repair_finalize",
        "repairer_agent",
        "semantic_gate_router",
        "rewrite_contract_builder",
        "auto_rewrite_agent",
        "semantic_review_interrupt",
    }:
        return "review"
    if node_name == "markdown_compiler":
        return "write"
    if node_name in {"finalize_artifacts", "commit_artifacts", "artifact_renderer"}:
        return "persist"
    if node_name in {"section_realizer_agent", "section_realizer_worker", "section_realizer_finalize"}:
        return "write"
    return "write"


def _known_id_buckets(report_ir: Dict[str, Any]) -> Dict[str, set[str]]:
    payload = report_ir if isinstance(report_ir, dict) else {}
    return {
        "claim": {str(item.get("claim_id") or "").strip() for item in ((payload.get("claim_set") or {}).get("claims") or []) if str(item.get("claim_id") or "").strip()},
        "evidence": {str(item.get("evidence_id") or "").strip() for item in ((payload.get("evidence_ledger") or {}).get("entries") or []) if str(item.get("evidence_id") or "").strip()},
        "risk": {str(item.get("risk_id") or "").strip() for item in ((payload.get("risk_register") or {}).get("risks") or []) if str(item.get("risk_id") or "").strip()},
        "recommendation": {str(item.get("candidate_id") or "").strip() for item in ((payload.get("recommendation_candidates") or {}).get("items") or []) if str(item.get("candidate_id") or "").strip()},
        "section_context": {str(item.get("section_id") or "").strip() for item in ((payload.get("placement_plan") or {}).get("entries") or []) if str(item.get("section_id") or "").strip()},
    }


def _trace_kind_for_id(trace_id: str, buckets: Dict[str, set[str]]) -> str:
    text = str(trace_id or "").strip()
    for kind in ("evidence", "claim", "risk", "recommendation"):
        if text in buckets.get(kind, set()):
            return kind
    return "section_context"


def _support_level_for_unit(unit_type: str) -> str:
    if unit_type in {"heading", "transition"}:
        return "structural"
    if unit_type == "observation":
        return "direct"
    if unit_type == "finding":
        return "aggregated"
    if unit_type in {"mechanism", "risk", "recommendation"}:
        return "derived"
    return "aggregated"


def _dedupe_texts(items: List[str]) -> List[str]:
    deduped: List[str] = []
    for item in items:
        text = str(item or "").strip()
        if text and text not in deduped:
            deduped.append(text)
    return deduped


def _section_context_ref(section_id: str, *, support_level: str) -> TraceRef:
    return TraceRef(
        trace_id=str(section_id or "").strip() or "claims",
        trace_kind="section_context",
        support_level=support_level,  # type: ignore[arg-type]
    )


def _repair_candidate_derived_from(unit: DraftUnitV2, failure: ValidationFailure) -> List[str]:
    metadata = unit.metadata if isinstance(unit.metadata, dict) else {}
    candidate_ids: List[str] = []
    candidate_ids.extend([str(item).strip() for item in failure.candidate_derived_from if str(item or "").strip()])
    candidate_ids.extend([str(item).strip() for item in unit.derived_from if str(item or "").strip()])
    candidate_ids.extend([str(item).strip() for item in metadata.get("legacy_claim_ids") or [] if str(item or "").strip()])
    candidate_ids.extend([str(item).strip() for item in metadata.get("legacy_evidence_ids") or [] if str(item or "").strip()])
    candidate_ids.extend([str(item).strip() for item in metadata.get("legacy_risk_ids") or [] if str(item or "").strip()])
    candidate_ids.extend([str(item).strip() for item in metadata.get("legacy_unresolved_ids") or [] if str(item or "").strip()])
    if not candidate_ids:
        candidate_ids.extend(
            [
                str(item.trace_id).strip()
                for item in failure.candidate_trace_refs
                if str(item.trace_id or "").strip() and item.trace_kind != "section_context"
            ]
        )
    return _dedupe_texts(candidate_ids)


def _repair_candidate_evidence_refs(unit: DraftUnitV2, failure: ValidationFailure) -> List[TraceRef]:
    metadata = unit.metadata if isinstance(unit.metadata, dict) else {}
    evidence_ids: List[str] = []
    evidence_ids.extend(
        [
            str(item.trace_id).strip()
            for item in failure.candidate_trace_refs
            if str(item.trace_id or "").strip() and item.trace_kind == "evidence"
        ]
    )
    evidence_ids.extend([str(item).strip() for item in metadata.get("legacy_evidence_ids") or [] if str(item or "").strip()])
    return [
        TraceRef(trace_id=trace_id, trace_kind="evidence", support_level="direct")
        for trace_id in _dedupe_texts(evidence_ids)
    ]


def _infer_unit_type(unit: DraftUnit) -> str:
    unit_id = str(unit.unit_id or "").strip()
    section_role = str(unit.section_role or "").strip()
    text = str(unit.text or "").strip()
    if unit_id.startswith("heading:") or text.startswith("## "):
        return "heading"
    if unit_id.startswith("transition:"):
        return "transition"
    if section_role == "timeline" or unit_id.startswith("unit:ledger:"):
        return "observation"
    if section_role == "mechanism":
        return "mechanism"
    if section_role == "risks":
        return "risk"
    if section_role == "recommendations":
        return "recommendation"
    if section_role == "unresolved" or unit.is_unresolved:
        return "unresolved"
    return "finding"


def _candidate_trace_refs_from_legacy(unit: DraftUnit, report_ir: Dict[str, Any], unit_type: str) -> List[TraceRef]:
    buckets = _known_id_buckets(report_ir)
    refs: List[TraceRef] = []
    seen: set[str] = set()
    candidate_ids = (
        list(unit.evidence_ids)
        + list(unit.claim_ids)
        + list(unit.risk_ids)
        + list(unit.trace_ids)
        + list(unit.stance_row_ids)
        + list(unit.unresolved_point_ids)
    )
    for trace_id in candidate_ids:
        text = str(trace_id or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        refs.append(
            TraceRef(
                trace_id=text,
                trace_kind=_trace_kind_for_id(text, buckets),
                support_level=_support_level_for_unit(unit_type),
            )
        )
    if not refs and str(unit.section_role or "").strip():
        refs.append(
            TraceRef(
                trace_id=str(unit.section_role or "").strip(),
                trace_kind="section_context",
                support_level="structural" if unit_type in {"heading", "transition"} else _support_level_for_unit(unit_type),
            )
        )
    return refs


def upgrade_draft_bundle_to_v2(report_ir: Dict[str, Any], draft_bundle: DraftBundle | Dict[str, Any]) -> DraftBundleV2:
    bundle = draft_bundle if isinstance(draft_bundle, DraftBundle) else DraftBundle.model_validate(draft_bundle or {})
    units: List[DraftUnitV2] = []
    for unit in bundle.units:
        unit_type = _infer_unit_type(unit)
        trace_refs = _candidate_trace_refs_from_legacy(unit, report_ir, unit_type)
        derived_from: List[str] = []
        if unit_type in {"finding", "mechanism", "risk", "recommendation", "unresolved"}:
            derived_from.extend([str(item).strip() for item in unit.claim_ids if str(item or "").strip()])
            if unit_type in {"mechanism", "risk", "recommendation"} and not derived_from:
                derived_from.extend([str(item).strip() for item in unit.evidence_ids if str(item or "").strip()])
        if unit_type == "unresolved" and not derived_from:
            derived_from.extend([str(item).strip() for item in unit.unresolved_point_ids if str(item or "").strip()])
        units.append(
            DraftUnitV2(
                unit_id=unit.unit_id,
                section_id=str(unit.section_role or "").strip() or "claims",
                unit_type=unit_type,
                text=str(unit.text or "").strip(),
                trace_refs=trace_refs,
                derived_from=list(dict.fromkeys([item for item in derived_from if item])),
                support_level=_support_level_for_unit(unit_type),
                context_ref=str(unit.section_role or "").strip() or "claims",
                render_template_id=f"{str(unit.section_role or '').strip() or 'claims'}:{unit_type}",
                validation_status="pending",
                metadata={
                    "legacy_trace_ids": list(unit.trace_ids),
                    "legacy_claim_ids": list(unit.claim_ids),
                    "legacy_evidence_ids": list(unit.evidence_ids),
                    "legacy_risk_ids": list(unit.risk_ids),
                    "legacy_unresolved_ids": list(unit.unresolved_point_ids),
                    "legacy_stance_row_ids": list(unit.stance_row_ids),
                },
            )
        )
    return DraftBundleV2(
        source_artifact_id="draft_bundle.v2",
        policy_version="policy.v2",
        units=units,
        section_order=list(bundle.section_order),
        metadata={
            **dict(bundle.metadata or {}),
            "upgraded_from": "draft_bundle",
            "unit_count": len(units),
        },
    )


def _validation_failure(
    *,
    failure_id: str,
    unit: DraftUnitV2,
    failure_type: str,
    message: str,
    patchable: bool,
) -> ValidationFailure:
    return ValidationFailure(
        failure_id=failure_id,
        target_unit_id=unit.unit_id,
        failure_type=failure_type,
        message=message,
        candidate_trace_refs=list(unit.trace_refs),
        candidate_derived_from=list(unit.derived_from),
        patchable=patchable,
        patch_status="pending" if patchable else "blocked",
        metadata={
            "section_id": unit.section_id,
            "unit_type": unit.unit_type,
            "support_level": unit.support_level,
        },
    )


def validate_draft_bundle_v2(
    report_ir: Dict[str, Any],
    draft_bundle_v2: DraftBundleV2 | Dict[str, Any],
    *,
    repair_count: int = 0,
    max_repairs: int = 2,
) -> ValidationResultV2:
    bundle = draft_bundle_v2 if isinstance(draft_bundle_v2, DraftBundleV2) else DraftBundleV2.model_validate(draft_bundle_v2 or {})
    buckets = _known_id_buckets(report_ir)
    known_ids = set().union(*buckets.values()) if buckets else set()
    prior_patch_count = int((bundle.metadata or {}).get("repair_patch_count") or 0)
    failures: List[ValidationFailure] = []
    for index, unit in enumerate(bundle.units, start=1):
        if not str(unit.text or "").strip():
            failures.append(
                _validation_failure(
                    failure_id=f"schema_violation:{index}",
                    unit=unit,
                    failure_type="schema_violation",
                    message="文本单元为空，不能进入正式编译。",
                    patchable=False,
                )
            )
            continue
        trace_ids = [str(item.trace_id or "").strip() for item in unit.trace_refs if str(item.trace_id or "").strip()]
        unknown_trace_ids = [
            str(item.trace_id or "").strip()
            for item in unit.trace_refs
            if str(item.trace_id or "").strip()
            and item.trace_kind != "section_context"
            and str(item.trace_id or "").strip() not in known_ids
            and str(item.trace_id or "").strip() != unit.section_id
        ]
        if unknown_trace_ids:
            failures.append(
                _validation_failure(
                    failure_id=f"schema_violation:{index}",
                    unit=unit,
                    failure_type="schema_violation",
                    message=f"存在未登记 trace：{','.join(unknown_trace_ids[:3])}",
                    patchable=False,
                )
            )
            continue
        if unit.unit_type in {"heading", "transition"}:
            if unit.support_level != "structural":
                failures.append(
                    _validation_failure(
                        failure_id=f"unsupported_inference:{index}",
                        unit=unit,
                        failure_type="unsupported_inference",
                        message="结构或过渡单元只能使用 structural support。",
                        patchable=True,
                    )
                )
            continue
        if unit.unit_type in _TRACEABLE_UNIT_TYPES and not trace_ids:
            failures.append(
                _validation_failure(
                    failure_id=f"missing_trace:{index}",
                    unit=unit,
                    failure_type="missing_trace",
                    message="该单元缺少 trace 绑定。",
                    patchable=bool(unit.metadata.get("legacy_evidence_ids") or unit.metadata.get("legacy_claim_ids") or unit.metadata.get("legacy_risk_ids")),
                )
            )
            continue
        if unit.unit_type == "observation":
            has_evidence = any(item.trace_kind == "evidence" for item in unit.trace_refs)
            if unit.support_level != "direct" or not has_evidence:
                failures.append(
                    _validation_failure(
                        failure_id=f"unsupported_inference:{index}",
                        unit=unit,
                        failure_type="unsupported_inference",
                        message="观察句必须直连 evidence 且使用 direct support。",
                        patchable=True,
                    )
                )
        elif unit.unit_type == "finding":
            has_support = any(item.trace_kind in {"claim", "evidence"} for item in unit.trace_refs) or bool(unit.derived_from)
            if unit.support_level != "aggregated" or not has_support:
                failures.append(
                    _validation_failure(
                        failure_id=f"unsupported_inference:{index}",
                        unit=unit,
                        failure_type="unsupported_inference",
                        message="归纳判断句必须至少绑定 claim、evidence 或 derived_from。",
                        patchable=True,
                    )
                )
        elif unit.unit_type in {"mechanism", "risk", "recommendation"}:
            if unit.support_level != "derived" or not unit.derived_from:
                failures.append(
                    _validation_failure(
                        failure_id=f"dangling_derived_from:{index}",
                        unit=unit,
                        failure_type="dangling_derived_from",
                        message="分析型单元必须携带 derived_from 追溯链。",
                        patchable=True,
                    )
                )
        elif unit.unit_type == "unresolved":
            if not (trace_ids or unit.derived_from):
                failures.append(
                    _validation_failure(
                        failure_id=f"text_outside_ir:{index}",
                        unit=unit,
                        failure_type="text_outside_ir",
                        message="未决问题缺少可回链的 IR 引用。",
                        patchable=True,
                    )
                )
    patchable = [item for item in failures if item.patchable]
    if not failures:
        gate = "pass"
        next_node = "markdown_compiler"
    elif repair_count > 0 and prior_patch_count <= 0:
        gate = "human_review"
        next_node = "compile_blocked"
    elif patchable and repair_count < max(int(max_repairs or 0), 0):
        gate = "repair"
        next_node = "repair_patch_planner"
    else:
        gate = "human_review"
        next_node = "compile_blocked"
    return ValidationResultV2(
        passed=not failures,
        failures=failures,
        patchable_failures=patchable,
        gate=gate,
        repair_count=int(repair_count or 0),
        next_node=next_node,
        metadata={
            "failure_count": len(failures),
            "patchable_count": len(patchable),
            "max_repairs": int(max_repairs or 0),
        },
    )


def build_repair_plan_v2(report_ir: Dict[str, Any], draft_bundle_v2: DraftBundleV2 | Dict[str, Any], validation_result_v2: ValidationResultV2 | Dict[str, Any]) -> RepairPlanV2:
    bundle = draft_bundle_v2 if isinstance(draft_bundle_v2, DraftBundleV2) else DraftBundleV2.model_validate(draft_bundle_v2 or {})
    validation = validation_result_v2 if isinstance(validation_result_v2, ValidationResultV2) else ValidationResultV2.model_validate(validation_result_v2 or {})
    units = {unit.unit_id: unit for unit in bundle.units}
    patches: List[RepairPatch] = []
    blocked: List[ValidationFailure] = []
    for index, failure in enumerate(validation.failures, start=1):
        unit = units.get(failure.target_unit_id)
        if unit is None or not failure.patchable:
            blocked.append(failure)
            continue
        replacement = copy.deepcopy(unit)
        operation = "attach_trace"
        if failure.failure_type == "missing_trace":
            candidate_refs = list(replacement.trace_refs)
            if not candidate_refs:
                candidate_refs = _candidate_trace_refs_from_legacy(
                    DraftUnit(
                        unit_id=replacement.unit_id,
                        section_role=replacement.section_id,
                        text=replacement.text,
                        trace_ids=list(replacement.metadata.get("legacy_trace_ids") or []),
                        claim_ids=list(replacement.metadata.get("legacy_claim_ids") or []),
                        evidence_ids=list(replacement.metadata.get("legacy_evidence_ids") or []),
                        risk_ids=list(replacement.metadata.get("legacy_risk_ids") or []),
                        unresolved_point_ids=list(replacement.metadata.get("legacy_unresolved_ids") or []),
                        stance_row_ids=list(replacement.metadata.get("legacy_stance_row_ids") or []),
                    ),
                    report_ir,
                    replacement.unit_type,
                )
            replacement.trace_refs = candidate_refs
        elif failure.failure_type == "unsupported_inference":
            if replacement.unit_type == "observation":
                evidence_refs = _repair_candidate_evidence_refs(replacement, failure)
                if evidence_refs:
                    replacement.trace_refs = evidence_refs
                    replacement.support_level = "direct"
                    operation = "attach_trace"
                else:
                    replacement.unit_type = "transition"
                    replacement.support_level = "structural"
                    replacement.trace_refs = [
                        ref.model_copy(update={"support_level": "structural"})
                        for ref in (replacement.trace_refs or failure.candidate_trace_refs)
                    ] or [_section_context_ref(replacement.section_id, support_level="structural")]
                    replacement.derived_from = []
                    replacement.render_template_id = f"{replacement.section_id}:transition"
                    operation = "replace_unit"
            else:
                replacement.support_level = _support_level_for_unit(replacement.unit_type)  # type: ignore[assignment]
                if replacement.unit_type == "finding" and not replacement.derived_from:
                    replacement.derived_from = _repair_candidate_derived_from(replacement, failure)
                operation = "downgrade_support"
        elif failure.failure_type in {"dangling_derived_from", "text_outside_ir"}:
            replacement.derived_from = _repair_candidate_derived_from(replacement, failure)
            operation = "replace_unit"
        replacement.validation_status = "repaired"
        if replacement.model_dump() == unit.model_dump():
            blocked.append(failure.model_copy(update={"patch_status": "blocked"}))
            continue
        patches.append(
            RepairPatch(
                patch_id=f"patch-{index}",
                target_unit_id=failure.target_unit_id,
                failure_type=failure.failure_type,
                operation=operation,
                replacement_unit=replacement,
                candidate_trace_refs=list(failure.candidate_trace_refs),
                candidate_derived_from=list(failure.candidate_derived_from),
                rationale=failure.message,
                status="planned",
            )
        )
    return RepairPlanV2(
        patches=patches,
        blocked_failures=blocked,
        metadata={
            "patch_count": len(patches),
            "blocked_count": len(blocked),
        },
    )


def _draft_bundle_v2_from_any(report_ir: Dict[str, Any], draft_bundle: DraftBundleV2 | DraftBundle | Dict[str, Any]) -> DraftBundleV2:
    if isinstance(draft_bundle, DraftBundleV2):
        return draft_bundle
    if isinstance(draft_bundle, DraftBundle):
        return upgrade_draft_bundle_to_v2(report_ir, draft_bundle)
    candidate = draft_bundle if isinstance(draft_bundle, dict) else {}
    if candidate.get("units") and candidate.get("schema_version") != "draft-bundle.v2":
        return upgrade_draft_bundle_to_v2(report_ir, candidate)
    return DraftBundleV2.model_validate(candidate or {})


def apply_repair_plan_v2(draft_bundle_v2: DraftBundleV2 | Dict[str, Any], repair_plan_v2: RepairPlanV2 | Dict[str, Any]) -> DraftBundleV2:
    bundle = draft_bundle_v2 if isinstance(draft_bundle_v2, DraftBundleV2) else DraftBundleV2.model_validate(draft_bundle_v2 or {})
    plan = repair_plan_v2 if isinstance(repair_plan_v2, RepairPlanV2) else RepairPlanV2.model_validate(repair_plan_v2 or {})
    units = {unit.unit_id: unit for unit in bundle.units}
    for patch in plan.patches:
        if patch.replacement_unit is None:
            continue
        units[patch.target_unit_id] = patch.replacement_unit
    return DraftBundleV2(
        source_artifact_id=bundle.source_artifact_id,
        policy_version=bundle.policy_version,
        schema_version=bundle.schema_version,
        section_order=list(bundle.section_order),
        units=[units[unit.unit_id] for unit in bundle.units if unit.unit_id in units],
        metadata={
            **dict(bundle.metadata or {}),
            "repair_patch_count": len(plan.patches),
        },
    )


def _legacy_draft_bundle_from_v2(draft_bundle_v2: DraftBundleV2 | Dict[str, Any]) -> DraftBundle:
    if isinstance(draft_bundle_v2, DraftBundle):
        return draft_bundle_v2
    bundle = draft_bundle_v2 if isinstance(draft_bundle_v2, DraftBundleV2) else DraftBundleV2.model_validate(draft_bundle_v2 or {})
    legacy_units: List[DraftUnit] = []
    for unit in bundle.units:
        claim_ids = [item.trace_id for item in unit.trace_refs if item.trace_kind == "claim"]
        evidence_ids = [item.trace_id for item in unit.trace_refs if item.trace_kind == "evidence"]
        risk_ids = [item.trace_id for item in unit.trace_refs if item.trace_kind == "risk"]
        trace_ids = [item.trace_id for item in unit.trace_refs if item.trace_kind in {"recommendation", "section_context"}]
        derived_from = [item for item in unit.derived_from if item not in claim_ids]
        legacy_units.append(
            DraftUnit(
                unit_id=unit.unit_id,
                section_role=unit.section_id,
                text=unit.text,
                trace_ids=list(dict.fromkeys(trace_ids + derived_from)),
                claim_ids=list(dict.fromkeys(claim_ids)),
                evidence_ids=list(dict.fromkeys(evidence_ids)),
                risk_ids=list(dict.fromkeys(risk_ids)),
                unresolved_point_ids=[],
                stance_row_ids=[],
                confidence="high" if unit.validation_status in {"passed", "repaired"} else "medium",
                is_unresolved=unit.unit_type == "unresolved",
            )
        )
    return DraftBundle(
        source_artifact_id="draft_bundle",
        policy_version="policy.v2",
        units=legacy_units,
        section_order=list(bundle.section_order),
        metadata=dict(bundle.metadata or {}),
    )


def _trace_ids_from_v2(unit: DraftUnitV2) -> List[str]:
    ids = [str(item.trace_id or "").strip() for item in unit.trace_refs if str(item.trace_id or "").strip()]
    ids.extend([str(item or "").strip() for item in unit.derived_from if str(item or "").strip()])
    deduped: List[str] = []
    for item in ids:
        if item and item not in deduped:
            deduped.append(item)
    return deduped


def render_markdown_from_v2(report_ir: Dict[str, Any], draft_bundle_v2: DraftBundleV2 | Dict[str, Any], *, title: str = "") -> str:
    bundle = draft_bundle_v2 if isinstance(draft_bundle_v2, DraftBundleV2) else DraftBundleV2.model_validate(draft_bundle_v2 or {})
    payload = report_ir if isinstance(report_ir, dict) else {}
    placement_entries = ((payload.get("placement_plan") or {}).get("entries")) or []
    section_figures: Dict[str, List[str]] = {}
    for entry in placement_entries:
        if not isinstance(entry, dict):
            continue
        section_figures.setdefault(str(entry.get("section_role") or "").strip() or "claims", []).append(str(entry.get("figure_id") or "").strip())
    safe_title = str(title or ((payload.get("meta") or {}).get("topic_label")) or ((payload.get("meta") or {}).get("topic_identifier")) or "专题报告").strip() or "专题报告"
    lines: List[str] = [f"# {safe_title}", ""]
    time_scope = (payload.get("meta") or {}).get("time_scope") if isinstance((payload.get("meta") or {}).get("time_scope"), dict) else {}
    if time_scope.get("start") or time_scope.get("end"):
        lines.extend([f"> 区间：{time_scope.get('start', '')} -> {time_scope.get('end', time_scope.get('start', ''))} | 模式：{(payload.get('meta') or {}).get('mode', '')}", ""])
    rendered_sections: set[str] = set()
    for unit in bundle.units:
        text = str(unit.text or "").rstrip()
        if not text:
            continue
        trace_ids = _trace_ids_from_v2(unit)
        if unit.unit_type != "heading" and trace_ids and not text.startswith("## ") and not re.match(r"^\s*[-*]\s*\[[^\]]+\]", text) and not re.match(r"^\[[^\]]+\]", text):
            if text.startswith("- "):
                text = f"- [{trace_ids[0]}] {text[2:].lstrip()}"
            else:
                text = f"[{trace_ids[0]}] {text}"
        lines.append(text)
        if unit.section_id and unit.section_id not in rendered_sections and unit.section_id in section_figures:
            rendered_sections.add(unit.section_id)
            lines.extend(["", *[f'::figure{{ref="{figure_id}"}}' for figure_id in section_figures.get(unit.section_id, []) if figure_id], ""])
    markdown = "\n".join(lines).strip()
    markdown = re.sub(r"\n{3,}", "\n\n", markdown)
    markdown = apply_guardrails(markdown, payload)
    markdown = sanitize_public_markdown(markdown)
    return markdown.strip()


def _translate_validation_to_conformance(validation: ValidationResultV2) -> FactualConformanceResult:
    issues = [
        FactualConformanceIssue(
            issue_id=item.failure_id,
            issue_type=item.failure_type,
            message=item.message,
            section_role=str(item.metadata.get("section_id") or "").strip(),
            sentence=item.target_unit_id,
            trace_ids=[trace.trace_id for trace in item.candidate_trace_refs],
            suggested_action=item.patch_status,
        )
        for item in validation.failures
    ]
    return FactualConformanceResult(
        passed=validation.passed,
        policy_version="policy.v2",
        stage="draft_bundle_v2",
        can_auto_recover=validation.gate == "repair",
        requires_human_review=validation.gate == "human_review",
        issues=issues,
        metadata=dict(validation.metadata or {}),
    )


def _stream_graph_events(
    graph: Any,
    input_or_command: Any,
    config: Dict[str, Any],
    event_callback: Optional[Callable[[Dict[str, Any]], None]],
) -> Dict[str, Any]:
    """用 LangGraph 原生 stream(mode='updates') 替代 graph.invoke()。
    将 node 更新事件翻译成现有 graph.node.update 事件格式。
    event_callback 为 None 时 fallback 到直接 invoke。"""
    def _normalize_invoke_result(result: Any) -> Dict[str, Any]:
        payload = result if isinstance(result, dict) else getattr(result, "value", result)
        state = dict(payload) if isinstance(payload, dict) else {"value": payload}
        interrupts = getattr(result, "interrupts", None)
        if isinstance(interrupts, (list, tuple)) and interrupts:
            state["__interrupt__"] = list(interrupts)
        elif isinstance(state.get("__interrupt__"), tuple) and state.get("__interrupt__"):
            state["__interrupt__"] = list(state.get("__interrupt__") or ())
        return state

    if not callable(event_callback):
        try:
            result = graph.invoke(input_or_command, config=config, version="v2")
        except TypeError:
            # Older LangGraph builds may not support invoke(version="v2") yet.
            result = graph.invoke(input_or_command, config=config)
        return _normalize_invoke_result(result)

    last_state: Dict[str, Any] = {}
    for chunk in graph.stream(input_or_command, config=config, stream_mode="updates", version="v2"):
        if not isinstance(chunk, dict):
            continue
        data = chunk.get("data") if chunk.get("type") == "updates" else None
        if not isinstance(data, dict):
            continue
        for node_name, updates in data.items():
            if node_name == "__interrupt__":
                # graph.stream() yields interrupt as a tuple; normalize to list
                # to match the shape that graph.invoke() returns
                last_state["__interrupt__"] = (
                    list(updates)
                    if isinstance(updates, (tuple, list))
                    else [updates]
                )
                continue
            if isinstance(updates, dict):
                last_state.update(updates)
            _emit_graph_event(
                event_callback,
                event_type="graph.node.update",
                node_name=str(node_name),
                phase=_node_phase(str(node_name)),
                title=f"{node_name} 更新",
                message=f"{node_name} 已产出中间更新。",
                payload={"node_name": node_name},
            )
    return last_state


def run_report_compilation_graph(
    payload: Dict[str, Any],
    *,
    event_callback: Callable[[Dict[str, Any]], None] | None = None,
    max_repairs: int = 2,
    checkpointer_path: str = "",
    graph_thread_id: str = "",
    review_decision: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    if not isinstance(payload, dict) or not isinstance(payload.get("report_ir"), dict):
        raise ValueError("run_report_compilation_graph requires payload carrying ReportIR.")
    ensure_langchain_uuid_compat()
    checkpoint_hint = str(checkpointer_path or "").strip()
    compile_thread_id = str(graph_thread_id or ((payload.get("task") or {}).get("thread_id")) or "deep-report-compile").strip() or "deep-report-compile"
    is_resume_invocation = isinstance(review_decision, dict)

    def _node(node_name: str, handler: Callable[[_GraphState], Dict[str, Any]], *, mutate_state: bool = True):
        def _wrapped(state: _GraphState) -> Dict[str, Any]:
            phase = _node_phase(node_name)
            visited = list(state.get("visited_nodes") or [])
            visited.append(node_name)
            _emit_graph_event(
                event_callback,
                event_type="graph.node.started",
                node_name=node_name,
                phase=phase,
                title=f"{node_name} 已启动",
                message=f"{node_name} 正在处理当前阶段。",
                payload={"current_node": node_name, "visited_nodes": visited},
            )
            try:
                updates = handler(state) or {}
                if mutate_state:
                    updates["current_node"] = node_name
                    updates["visited_nodes"] = visited
                _emit_graph_event(
                    event_callback,
                    event_type="graph.node.completed",
                    node_name=node_name,
                    phase=phase,
                    title=f"{node_name} 已完成",
                    message=f"{node_name} 已完成当前阶段。",
                    payload={"current_node": node_name, "visited_nodes": visited},
                )
                return updates
            except GraphInterrupt:
                raise
            except Exception as exc:
                _emit_graph_event(
                    event_callback,
                    event_type="graph.node.failed",
                    node_name=node_name,
                    phase=phase,
                    title=f"{node_name} 失败",
                    message=str(exc or "图节点执行失败。").strip() or "图节点执行失败。",
                    payload={"current_node": node_name, "failed_node": node_name},
                )
                raise

        return _wrapped

    def load_context(state: _GraphState) -> Dict[str, Any]:
        payload = _payload_from_state(state)
        report_ir = payload.get("report_ir") if isinstance(payload.get("report_ir"), dict) else {}
        task = payload.get("task") if isinstance(payload.get("task"), dict) else {}
        utility = report_ir.get("utility_assessment") if isinstance(report_ir.get("utility_assessment"), dict) else {}
        skip_validation = bool(task.get("skip_validation"))
        configured_budget = task.get("rewrite_budget")
        default_rewrite_budget = 0 if skip_validation else 1
        try:
            rewrite_budget = max(0, int(configured_budget if configured_budget is not None else default_rewrite_budget))
        except (TypeError, ValueError):
            rewrite_budget = default_rewrite_budget
        policy_registry = build_conformance_policy_registry()
        scene_profile = select_scene_profile(report_ir)
        style_profile = resolve_style_profile(report_ir, scene_profile)
        layout_plan = build_layout_plan(report_ir, scene_profile, style_profile)
        section_budget = build_section_budget(report_ir, scene_profile, layout_plan)
        writer_context = assemble_writer_context(report_ir, scene_profile, style_profile, layout_plan, section_budget)
        section_plan = build_section_plan(report_ir, layout_plan, section_budget, scene_profile)
        return {
            "payload": payload,
            "report_ir": report_ir,
            "task": task,
            "utility_assessment": utility,
            "policy_registry": policy_registry.model_dump(),
            "scene_profile": scene_profile.model_dump(),
            "style_profile": style_profile.model_dump(),
            "layout_plan": layout_plan.model_dump(),
            "section_budget": section_budget.model_dump(),
            "writer_context": writer_context.model_dump(),
            "section_plan": section_plan.model_dump(),
            "execution_phase": "prepare",
            "rewrite_round": 0,
            "rewrite_budget": rewrite_budget,
            "rewrite_issue_count": 0,
            "approval_required": False,
            "approval_status": "approved" if skip_validation else "none",
            "finalization_mode": "",
            "commit_pending": False,
            "commit_idempotency_key": "",
            "structured_report_current": payload,
            "draft_bundle_current": {},
            "final_markdown_current": "",
            "rewrite_contract": {},
            "source_checkpoint_id": "",
            "parent_artifact_id": "structured_projection",
            "repaired_unit_ids": [],
            "dropped_unit_ids": [],
            "unchanged_unit_ids": [],
            "validation_issues": [],
            "repair_history": [],
            "semantic_review_records": [],
            "progress_events": [
                _state_progress_event(
                    event_type="compile.prepare.started",
                    node_name="load_context",
                    phase="prepare",
                    message="编译图已初始化。",
                    payload={"rewrite_budget": rewrite_budget, "skip_validation": skip_validation},
                )
            ],
            "commit_artifacts": [],
        }

    def planner_agent(state: _GraphState) -> Dict[str, Any]:
        section_plan = state.get("section_plan") if isinstance(state.get("section_plan"), dict) else {}
        sections = section_plan.get("sections") if isinstance(section_plan.get("sections"), list) else []
        planner_slots = [
            {
                "section_id": str(item.get("section_id") or "").strip(),
                "analysis_goal": str(item.get("goal") or "").strip(),
                "coverage_need": list(item.get("source_groups") or []),
            }
            for item in sections
            if isinstance(item, dict) and str(item.get("section_id") or "").strip()
        ]
        return {
            "section_plan": {
                **section_plan,
                "planner_slots": planner_slots,
            },
            "planner_slots": planner_slots,
        }

    def existing_analysis_workers_subgraph(state: _GraphState) -> Dict[str, Any]:
        report_ir = state.get("report_ir") if isinstance(state.get("report_ir"), dict) else {}
        return {"report_ir": report_ir}

    def ir_merge(state: _GraphState) -> Dict[str, Any]:
        return {"report_ir": state.get("report_ir") or {}}

    def trace_binder(state: _GraphState) -> Dict[str, Any]:
        # 正式文稿统一走模板驱动写作，确定性拼接仅保留历史兼容函数。
        scene_profile = state.get("scene_profile") or {}
        from .schemas import CompilerSceneProfile

        scene = CompilerSceneProfile.model_validate(scene_profile)
        draft_bundle_v2 = compile_draft_units(
            state["report_ir"],
            state["section_plan"],
            scene,
        )
        draft_bundle = _legacy_draft_bundle_from_v2(draft_bundle_v2)
        return {
            "draft_bundle": draft_bundle.model_dump(),
            "draft_bundle_v2": draft_bundle_v2.model_dump(),
        }

    def section_realizer_worker(state: _GraphState) -> Dict[str, Any]:
        bundle = _draft_bundle_v2_from_any(state.get("report_ir") or {}, state.get("draft_bundle_v2") or {})
        slot = state.get("planner_slot") if isinstance(state.get("planner_slot"), dict) else {}
        section_id = str(slot.get("section_id") or "").strip()
        units = [
            unit.model_copy(
                update={
                    "validation_status": "pending",
                    "metadata": {
                        **dict(unit.metadata or {}),
                        "planner_slot": slot,
                    },
                }
            ).model_dump()
            for unit in bundle.units
            if str(unit.section_id or "").strip() == section_id
        ]
        return {"section_batches": [{"section_id": section_id, "units": units}]}

    def section_realizer_finalize(state: _GraphState) -> Dict[str, Any]:
        bundle = _draft_bundle_v2_from_any(state.get("report_ir") or {}, state.get("draft_bundle_v2") or {})
        section_batches = state.get("section_batches") if isinstance(state.get("section_batches"), list) else []
        realized_by_section = {
            str(item.get("section_id") or "").strip(): [
                DraftUnitV2.model_validate(unit)
                for unit in (item.get("units") or [])
                if isinstance(unit, dict)
            ]
            for item in section_batches
            if isinstance(item, dict) and str(item.get("section_id") or "").strip()
        }
        realized_units: List[DraftUnitV2] = []
        for unit in bundle.units:
            section_id = str(unit.section_id or "").strip()
            candidates = realized_by_section.get(section_id) or []
            if candidates:
                realized_units.append(candidates.pop(0))
            else:
                realized_units.append(unit.model_copy(update={"validation_status": "pending"}))
        realized = bundle.model_copy(update={"units": realized_units})
        return {"draft_bundle_v2": realized.model_dump(), "section_batches": None}

    def unit_validator(state: _GraphState) -> Dict[str, Any]:
        validation = validate_draft_bundle_v2(
            state["report_ir"],
            state["draft_bundle_v2"],
            repair_count=int(state.get("repair_count") or 0),
            max_repairs=max_repairs,
        )
        if not validation.passed:
            _emit_graph_event(
                event_callback,
                event_type="validation.failed",
                node_name="unit_validator",
                phase="review",
                title="验证失败",
                message=f"验证失败：{len(validation.failures)} 个单元需要修复或人工复核。",
                payload={"validation_result_v2": validation.model_dump(), "failure_count": len(validation.failures), "repair_count": int(state.get("repair_count") or 0)},
            )
        return {
            "validation_result_v2": validation.model_dump(),
            "validation_issues": [
                {
                    "stage": "unit_validation",
                    "repair_count": int(state.get("repair_count") or 0),
                    "failures": [item.model_dump() for item in validation.failures],
                    "gate": validation.gate,
                }
            ],
            "execution_phase": "review" if not validation.passed else "compile",
            "draft_bundle_current": state.get("draft_bundle_v2") or {},
            "progress_events": [
                _state_progress_event(
                    event_type="compile.validation.completed",
                    node_name="unit_validator",
                    phase="review" if not validation.passed else "compile",
                    message="结构验证已完成。",
                    payload={"passed": validation.passed, "gate": validation.gate, "failure_count": len(validation.failures)},
                )
            ],
        }

    def repair_patch_planner(state: _GraphState) -> Dict[str, Any]:
        plan = build_repair_plan_v2(state["report_ir"], state["draft_bundle_v2"], state["validation_result_v2"])
        _emit_graph_event(
            event_callback,
            event_type="repair.loop.started",
            node_name="repair_patch_planner",
            phase="review",
            title="开始修复不可追溯单元",
            message=f"准备执行第 {int(state.get('repair_count') or 0) + 1} 轮修复。",
            payload={"repair_count": int(state.get('repair_count') or 0) + 1, "repair_plan_v2": plan.model_dump()},
        )
        return {
            "repair_plan_v2": plan.model_dump(),
            "repair_history": [
                {
                    "kind": "draft_repair_plan",
                    "repair_round": int(state.get("repair_count") or 0) + 1,
                    "patch_count": len(plan.patches),
                    "blocked_failure_count": len(plan.blocked_failures),
                }
            ],
            "progress_events": [
                _state_progress_event(
                    event_type="compile.repair.plan",
                    node_name="repair_patch_planner",
                    phase="review",
                    message="结构修复计划已生成。",
                    payload={"repair_round": int(state.get("repair_count") or 0) + 1, "patch_count": len(plan.patches)},
                )
            ],
        }

    def repair_worker(state: _GraphState) -> Dict[str, Any]:
        patch = state.get("repair_patch") if isinstance(state.get("repair_patch"), dict) else {}
        if not patch:
            return {"repair_batches": []}
        current_patch = RepairPatch.model_validate(patch)
        applied_patch = current_patch.model_copy(update={"status": "applied"})
        return {"repair_batches": [applied_patch.model_dump()]}

    def repair_finalize(state: _GraphState) -> Dict[str, Any]:
        plan = RepairPlanV2.model_validate(state.get("repair_plan_v2") or {})
        batch_items = state.get("repair_batches") if isinstance(state.get("repair_batches"), list) else []
        applied_by_id = {
            str(item.get("patch_id") or "").strip(): RepairPatch.model_validate(item)
            for item in batch_items
            if isinstance(item, dict) and str(item.get("patch_id") or "").strip()
        }
        applied_patches = [applied_by_id.get(patch.patch_id, patch) for patch in plan.patches]
        applied_plan = plan.model_copy(update={"patches": applied_patches})
        repaired = apply_repair_plan_v2(state["draft_bundle_v2"], applied_plan)
        repair_count = int(state.get("repair_count") or 0) + 1
        _emit_graph_event(
            event_callback,
            event_type="repair.loop.completed",
            node_name="repair_finalize",
            phase="review",
            title="修复已完成",
            message=f"第 {repair_count} 轮修复已完成，正在重新验证。",
            payload={"repair_count": repair_count, "repair_plan_v2": applied_plan.model_dump()},
        )
        return {
            "draft_bundle_v2": repaired.model_dump(),
            "repair_plan_v2": applied_plan.model_dump(),
            "repair_batches": None,
            "repair_count": repair_count,
            "draft_bundle_current": repaired.model_dump(),
            "repair_history": [
                {
                    "kind": "draft_repair_applied",
                    "repair_round": repair_count,
                    "patch_count": len(applied_plan.patches),
                    "patched_unit_ids": [str(item.target_unit_id or "").strip() for item in applied_plan.patches if str(item.target_unit_id or "").strip()],
                }
            ],
            "progress_events": [
                _state_progress_event(
                    event_type="compile.repair.completed",
                    node_name="repair_finalize",
                    phase="review",
                    message="结构修复已应用。",
                    payload={"repair_round": repair_count, "patch_count": len(applied_plan.patches)},
                )
            ],
        }

    def markdown_compiler(state: _GraphState) -> Dict[str, Any]:
        bundle_v2 = _draft_bundle_v2_from_any(state.get("report_ir") or {}, state["draft_bundle_v2"])
        validation = ValidationResultV2.model_validate(state["validation_result_v2"])
        if not validation.passed:
            raise ValueError("markdown_compiler requires a validated DraftBundleV2.")
        title = str(((state.get("task") or {}).get("topic_label")) or "").strip()
        _emit_graph_event(
            event_callback,
            event_type="compile.started",
            node_name="markdown_compiler",
            phase="write",
            title="开始正式编译",
            message="正在把 validated bundle 渲染为正式 Markdown。",
            payload={"validated_unit_count": len(bundle_v2.units)},
        )
        markdown = render_markdown_from_v2(state["report_ir"], bundle_v2, title=title)
        factual = run_factual_conformance(state["report_ir"], markdown)
        _emit_graph_event(
            event_callback,
            event_type="compile.completed",
            node_name="markdown_compiler",
            phase="write",
            title="正式编译完成",
            message="validated bundle 已成功编译为正式 Markdown。",
            payload={"unit_count": len(bundle_v2.units), "markdown_issue_count": len(factual.issues)},
        )
        return {
            "markdown": markdown,
            "final_markdown_current": markdown,
            "factual_conformance": factual.model_dump(),
            "review_required": bool(factual.requires_human_review),
            "rewrite_issue_count": len(factual.issues),
            "draft_bundle_current": bundle_v2.model_dump(),
            "execution_phase": "compile",
            "validation_issues": [
                {
                    "stage": "semantic_conformance",
                    "repair_count": int(state.get("repair_count") or 0),
                    "rewrite_round": int(state.get("rewrite_round") or 0),
                    "issues": [item.model_dump() for item in factual.issues],
                    "requires_human_review": bool(factual.requires_human_review),
                }
            ],
            "progress_events": [
                _state_progress_event(
                    event_type="compile.markdown.completed",
                    node_name="markdown_compiler",
                    phase="write",
                    message="正式文稿已完成一次编译。",
                    payload={"issue_count": len(factual.issues), "requires_human_review": bool(factual.requires_human_review)},
                )
            ],
        }

    def semantic_gate_router(state: _GraphState) -> Dict[str, Any]:
        factual = FactualConformanceResult.model_validate(state.get("factual_conformance") or {})
        utility = state.get("utility_assessment") if isinstance(state.get("utility_assessment"), dict) else {}
        utility_decision = str(utility.get("decision") or "pass").strip() or "pass"
        rewrite_round = int(state.get("rewrite_round") or 0)
        rewrite_budget = int(state.get("rewrite_budget") or 0)
        skip_validation = bool(((state.get("task") or {}).get("skip_validation")))
        issue_count = len(factual.issues)
        can_rewrite = (not skip_validation) and rewrite_round < rewrite_budget and bool(issue_count)
        requires_review = (not skip_validation) and (bool(factual.requires_human_review) or utility_decision == "require_semantic_review")
        if factual.passed and issue_count == 0 and utility_decision == "pass":
            next_phase = "finalize"
            finalization_mode = "direct"
        elif can_rewrite:
            next_phase = "auto_rewrite"
            finalization_mode = "auto_rewritten"
        elif requires_review or issue_count:
            next_phase = "human_review"
            finalization_mode = "approval_required"
        else:
            next_phase = "finalize"
            finalization_mode = "direct"
        return {
            "execution_phase": next_phase,
            "approval_required": next_phase == "human_review",
            "review_required": next_phase == "human_review",
            "finalization_mode": finalization_mode,
            "rewrite_issue_count": issue_count,
            "progress_events": [
                _state_progress_event(
                    event_type="compile.semantic_gate.routed",
                    node_name="semantic_gate_router",
                    phase="review" if next_phase in {"auto_rewrite", "human_review"} else "persist",
                    message="语义门禁已完成路由。",
                    payload={"next_phase": next_phase, "issue_count": issue_count, "rewrite_round": rewrite_round, "rewrite_budget": rewrite_budget},
                )
            ],
        }

    def rewrite_contract_builder(state: _GraphState) -> Dict[str, Any]:
        factual = FactualConformanceResult.model_validate(state.get("factual_conformance") or {})
        bundle_v2 = _draft_bundle_v2_from_any(state.get("report_ir") or {}, state.get("draft_bundle_v2") or {})
        feedback = ReviewFeedbackContract.model_validate(state.get("review_feedback_contract") or {})
        issue_targets = [str(item.sentence or "").strip() for item in factual.issues if str(item.sentence or "").strip()]
        offending_unit_ids: List[str] = []
        dropped_unit_ids: List[str] = []
        for unit in bundle_v2.units:
            if unit.text and any(target in unit.text for target in issue_targets):
                offending_unit_ids.append(str(unit.unit_id or "").strip())
        for issue in factual.issues:
            if str(issue.issue_id or "").startswith("markdown_untraceable:") and issue.sentence:
                dropped_unit_ids.extend([str(unit.unit_id or "").strip() for unit in bundle_v2.units if unit.text == issue.sentence])
        traceable_unit_ids = [str(unit.unit_id or "").strip() for unit in bundle_v2.units if str(unit.unit_id or "").strip()]
        contract = RewriteContract(
            allowed_ops=list(_DEFAULT_ALLOWED_REWRITE_OPS),
            forbidden_ops=list(_DEFAULT_FORBIDDEN_REWRITE_OPS),
            offending_unit_ids=list(dict.fromkeys(offending_unit_ids)),
            traceable_unit_ids=traceable_unit_ids,
            max_sentence_delta=max(1, len(factual.issues)),
            max_unit_delta=max(1, len(offending_unit_ids) or len(factual.issues)),
            must_preserve_sections=list(bundle_v2.section_order),
            must_preserve_trace_bindings=True,
            human_feedback=feedback.model_dump(exclude_none=True),
            metadata={
                "issue_count": len(factual.issues),
                "semantic_delta_count": len(factual.semantic_deltas),
                "feedback_round": int(feedback.feedback_round or 0),
            },
        )
        forbidden_ops = list(contract.forbidden_ops)
        if feedback.must_keep:
            forbidden_ops.append("remove_must_keep")
        if feedback.must_remove:
            contract.allowed_ops = list(dict.fromkeys(list(contract.allowed_ops) + ["delete_untraced"]))
        contract.forbidden_ops = list(dict.fromkeys(forbidden_ops))
        return {
            "rewrite_contract": contract.model_dump(),
            "dropped_unit_ids": list(dict.fromkeys(dropped_unit_ids)),
            "unchanged_unit_ids": [item for item in traceable_unit_ids if item not in offending_unit_ids],
            "progress_events": [
                _state_progress_event(
                    event_type="compile.auto_rewrite.contract_ready",
                    node_name="rewrite_contract_builder",
                    phase="review",
                    message="自动重写契约已生成。",
                    payload={
                        "offending_unit_count": len(contract.offending_unit_ids),
                        "max_sentence_delta": contract.max_sentence_delta,
                        "feedback_round": int(feedback.feedback_round or 0),
                    },
                )
            ],
        }

    def auto_rewrite_agent(state: _GraphState) -> Dict[str, Any]:
        markdown = str(state.get("final_markdown_current") or state.get("markdown") or "").strip()
        factual = FactualConformanceResult.model_validate(state.get("factual_conformance") or {})
        contract = RewriteContract.model_validate(state.get("rewrite_contract") or {})
        if not markdown:
            return {"execution_phase": "human_review", "finalization_mode": "approval_required"}
        rewritten = markdown
        removed_lines: List[str] = []
        feedback = contract.human_feedback if isinstance(contract.human_feedback, dict) else {}
        must_keep = [str(item).strip() for item in (feedback.get("must_keep") or []) if str(item or "").strip()]
        must_remove = [str(item).strip() for item in (feedback.get("must_remove") or []) if str(item or "").strip()]
        rewrite_focus = [str(item).strip() for item in (feedback.get("rewrite_focus") or []) if str(item or "").strip()]
        tone_target = str(feedback.get("tone_target") or "").strip().lower()
        for issue in factual.issues:
            sentence = str(issue.sentence or "").strip()
            if sentence and sentence in rewritten and sentence not in must_keep and "delete_untraced" in contract.allowed_ops:
                rewritten = "\n".join(line for line in rewritten.splitlines() if line.strip() != sentence.strip())
                removed_lines.append(sentence)
        for sentence in must_remove:
            if sentence and sentence in rewritten and sentence not in must_keep:
                rewritten = "\n".join(line for line in rewritten.splitlines() if sentence not in line)
                removed_lines.append(sentence)
        for before, after in [
            ("已经证实", "现有材料显示"),
            ("必然", "可能"),
            ("全面", "较广范围"),
            ("必须", "建议优先"),
            ("紧急", "应尽快"),
            ("公众一致", "部分公众观点"),
        ]:
            rewritten = rewritten.replace(before, after)
        if tone_target in {"conservative", "cautious", "审慎"}:
            for before, after in [("判断为", "倾向于认为"), ("说明了", "可能说明"), ("导致", "可能带来")]:
                rewritten = rewritten.replace(before, after)
        if rewrite_focus:
            for focus in rewrite_focus:
                if focus in {"delete_untraced", "remove_unverified"}:
                    rewritten = "\n".join(
                        line for line in rewritten.splitlines() if "未经证实" not in line and "无法回溯" not in line
                    )
        rewritten = sanitize_public_markdown(rewritten)
        rewritten = _safe_sentence_limit(rewritten, limit=max(3, 24 + int(contract.max_sentence_delta or 0)))
        rewritten_factual = run_factual_conformance(state["report_ir"], rewritten)
        rewrite_round = int(state.get("rewrite_round") or 0) + 1
        review_feedback_rounds = list(state.get("review_feedback_rounds") or [])
        rewrite_lineage_entry = {
            "rewrite_round": rewrite_round,
            "source_checkpoint_id": str(state.get("source_checkpoint_id") or ""),
            "parent_artifact_id": str(state.get("parent_artifact_id") or ""),
            "repaired_unit_ids": list(contract.offending_unit_ids or []),
            "dropped_unit_ids": list(dict.fromkeys(list(state.get("dropped_unit_ids") or []) + removed_lines)),
            "unchanged_unit_ids": list(state.get("unchanged_unit_ids") or []),
            "human_feedback": feedback,
        }
        return {
            "markdown": rewritten,
            "final_markdown_current": rewritten,
            "factual_conformance": rewritten_factual.model_dump(),
            "review_required": bool(rewritten_factual.requires_human_review),
            "rewrite_round": rewrite_round,
            "rewrite_issue_count": len(rewritten_factual.issues),
            "repaired_unit_ids": list(dict.fromkeys(list(state.get("repaired_unit_ids") or []) + list(contract.offending_unit_ids or []))),
            "dropped_unit_ids": list(dict.fromkeys(list(state.get("dropped_unit_ids") or []) + removed_lines)),
            "execution_phase": "review",
            "approval_status": "rewritten" if feedback else str(state.get("approval_status") or "none"),
            "review_feedback_rounds": review_feedback_rounds if not feedback else review_feedback_rounds,
            "repair_history": [
                {
                    "kind": "auto_rewrite",
                    "rewrite_round": rewrite_round,
                    "allowed_ops": list(contract.allowed_ops),
                    "removed_sentence_count": len(removed_lines),
                    "remaining_issue_count": len(rewritten_factual.issues),
                    "feedback_round": int(feedback.get("feedback_round") or 0) if feedback else 0,
                }
            ],
            "rewrite_lineage": [rewrite_lineage_entry],
            "review_feedback_contract": {},
            "progress_events": [
                _state_progress_event(
                    event_type="compile.auto_rewrite.completed",
                    node_name="auto_rewrite_agent",
                    phase="review",
                    message="自动重写已完成，并重新执行语义校验。",
                    payload={
                        "rewrite_round": rewrite_round,
                        "remaining_issue_count": len(rewritten_factual.issues),
                        "feedback_round": int(feedback.get("feedback_round") or 0) if feedback else 0,
                    },
                )
            ],
        }

    def semantic_review_interrupt(state: _GraphState) -> Dict[str, Any]:
        factual = FactualConformanceResult.model_validate(state.get("factual_conformance") or {})
        validation = ValidationResultV2.model_validate(state.get("validation_result_v2") or {})
        markdown_preview = str(state.get("final_markdown_current") or state.get("markdown") or "").strip()
        if not markdown_preview and state.get("draft_bundle_v2"):
            title = str(((state.get("task") or {}).get("topic_label")) or "").strip()
            markdown_preview = render_markdown_from_v2(
                state.get("report_ir") or {},
                _draft_bundle_v2_from_any(state.get("report_ir") or {}, state.get("draft_bundle_v2") or {}),
                title=title,
            )
        interrupt_event_key = f"{compile_thread_id}:semantic_review:{int(state.get('rewrite_round') or 0)}"
        interrupt_payload = {
            "protocol_version": "semantic-review.v1",
            "review_kind": "semantic_review",
            "title": "语义边界确认",
            "summary": (
                f"正式文稿仍有 {len(factual.issues)} 个语义/事实边界问题，"
                f"rewrite round={int(state.get('rewrite_round') or 0)}，需要人工确认。"
            ),
            "allowed_decisions": ["approve", "rewrite", "reject"],
            "event_key": interrupt_event_key,
            "review_mode": "annotation",
            "review_prompt": "文稿预览保持只读。可确认放行、要求最小改写，或拒绝本轮写入；如需重写，请补充人工审核批注与结构化反馈。",
            "review_placeholder": "请输入审核批注，说明需保留、需移除、语气调整或重写重点",
            "markdown_preview": markdown_preview,
            "validation_result_v2": validation.model_dump(),
            "repair_plan_v2": state.get("repair_plan_v2") or {},
            "factual_conformance": factual.model_dump(),
            "rewrite_contract": state.get("rewrite_contract") or {},
            "rewrite_round": int(state.get("rewrite_round") or 0),
            "approval_round": len(state.get("semantic_review_records") or []) + 1,
            "review_payload_schema": {
                "comment": "string",
                "rewrite_focus": ["string"],
                "must_keep": ["string"],
                "must_remove": ["string"],
                "tone_target": "string",
            },
        }
        if not is_resume_invocation:
            _emit_graph_event(
                event_callback,
                event_type="compile.human_review.required",
                node_name="semantic_review_interrupt",
                phase="review",
                title="等待人工复核",
                message=interrupt_payload["summary"],
                payload=interrupt_payload,
            )
        decision = interrupt(interrupt_payload)
        resolved = decision if isinstance(decision, dict) else {"decision": "approve" if decision else "reject"}
        decision_text = str(resolved.get("decision") or "").strip().lower() or "approve"
        review_payload = resolved.get("review_payload") if isinstance(resolved.get("review_payload"), dict) else {}
        review_comment = str(review_payload.get("comment") or "").strip()
        feedback_contract = ReviewFeedbackContract(
            comment=review_comment,
            rewrite_focus=[str(item).strip() for item in (review_payload.get("rewrite_focus") or []) if str(item or "").strip()],
            must_keep=[str(item).strip() for item in (review_payload.get("must_keep") or []) if str(item or "").strip()],
            must_remove=[str(item).strip() for item in (review_payload.get("must_remove") or []) if str(item or "").strip()],
            tone_target=str(review_payload.get("tone_target") or "").strip(),
            feedback_round=int(state.get("rewrite_round") or 0) + 1,
            metadata={"interrupt_id": interrupt_event_key},
        )
        review_feedback_rounds = list(state.get("review_feedback_rounds") or [])
        if decision_text == "rewrite":
            review_feedback_rounds = review_feedback_rounds + [feedback_contract.model_dump()]
        return {
            "markdown": markdown_preview,
            "final_markdown_current": markdown_preview,
            "approval_required": False,
            "approval_status": "approved" if decision_text == "approve" else "rewrite_requested" if decision_text == "rewrite" else "rejected",
            "review_required": decision_text != "approve",
            "blocked_reason": "" if decision_text == "approve" else "rewrite_requested" if decision_text == "rewrite" else "rejected_by_human_review",
            "execution_phase": "finalize" if decision_text == "approve" else "auto_rewrite" if decision_text == "rewrite" else "failed",
            "finalization_mode": "approved_after_review" if decision_text == "approve" else "rewrite_requested" if decision_text == "rewrite" else "failed",
            "review_feedback_contract": feedback_contract.model_dump() if decision_text == "rewrite" else {},
            "review_feedback_rounds": review_feedback_rounds,
            "semantic_review_records": [
                {
                    "interrupt_id": interrupt_event_key,
                    "decision": decision_text,
                    "review_payload": review_payload,
                    "review_comment": review_comment,
                    "rewrite_round": int(state.get("rewrite_round") or 0),
                }
            ],
            "progress_events": [
                _state_progress_event(
                    event_type="compile.human_review.resolved",
                    node_name="semantic_review_interrupt",
                    phase="review",
                    message="人工复核结果已写回图状态。",
                    payload={
                        "decision": decision_text,
                        "rewrite_round": int(state.get("rewrite_round") or 0),
                        "feedback_round": feedback_contract.feedback_round if decision_text == "rewrite" else 0,
                    },
                )
            ],
        }

    def finalize_artifacts(state: _GraphState) -> Dict[str, Any]:
        validation = ValidationResultV2.model_validate(state.get("validation_result_v2") or {})
        draft_bundle_v2 = _draft_bundle_v2_from_any(state.get("report_ir") or {}, state.get("draft_bundle_v2") or {})
        legacy_bundle = _legacy_draft_bundle_from_v2(draft_bundle_v2)
        draft_conformance = _translate_validation_to_conformance(validation)
        factual_dump = state.get("factual_conformance") if isinstance(state.get("factual_conformance"), dict) else FactualConformanceResult(
            passed=not state.get("review_required"),
            policy_version="policy.v2",
            stage="final_markdown",
            can_auto_recover=False,
            requires_human_review=bool(state.get("review_required")),
            issues=[],
            metadata={},
        ).model_dump()
        graph_state = DeepReportGraphState(
            payload=state.get("payload") or {},
            report_ir=state.get("report_ir") or {},
            policy_registry=state.get("policy_registry") or {},
            scene_profile=state.get("scene_profile") or {},
            style_profile=state.get("style_profile") or {},
            layout_plan=state.get("layout_plan") or {},
            section_budget=state.get("section_budget") or {},
            writer_context=state.get("writer_context") or {},
            section_plan=state.get("section_plan") or {},
            structured_report_current=state.get("structured_report_current") or {},
            draft_bundle_current=state.get("draft_bundle_current") or draft_bundle_v2.model_dump(),
            final_markdown_current=str(state.get("final_markdown_current") or state.get("markdown") or "").strip(),
            execution_phase=str(state.get("execution_phase") or "finalize"),
            rewrite_round=int(state.get("rewrite_round") or 0),
            rewrite_budget=int(state.get("rewrite_budget") or 0),
            rewrite_issue_count=int(state.get("rewrite_issue_count") or 0),
            approval_required=bool(state.get("approval_required")),
            approval_status=str(state.get("approval_status") or "none"),
            finalization_mode=str(state.get("finalization_mode") or ""),
            commit_pending=bool(state.get("commit_pending")),
            commit_idempotency_key=str(state.get("commit_idempotency_key") or ""),
            draft_bundle=legacy_bundle.model_dump(),
            draft_bundle_v2=draft_bundle_v2.model_dump(),
            validation_result_v2=validation.model_dump(),
            repair_plan_v2=state.get("repair_plan_v2") or {},
            markdown=str(state.get("markdown") or "").strip(),
            factual_conformance=factual_dump,
            review_required=bool(state.get("review_required")),
            blocked_reason=str(state.get("blocked_reason") or "").strip(),
            repair_count=int(state.get("repair_count") or 0),
            rewrite_contract=state.get("rewrite_contract") or {},
            review_feedback_contract=state.get("review_feedback_contract") or {},
            source_checkpoint_id=str(state.get("source_checkpoint_id") or ""),
            parent_artifact_id=str(state.get("parent_artifact_id") or ""),
            repaired_unit_ids=list(state.get("repaired_unit_ids") or []),
            dropped_unit_ids=list(state.get("dropped_unit_ids") or []),
            unchanged_unit_ids=list(state.get("unchanged_unit_ids") or []),
            review_feedback_rounds=list(state.get("review_feedback_rounds") or []),
            validation_issues=list(state.get("validation_issues") or []),
            repair_history=list(state.get("repair_history") or []),
            semantic_review_records=list(state.get("semantic_review_records") or []),
            progress_events=list(state.get("progress_events") or []),
            rewrite_lineage=list(state.get("rewrite_lineage") or []),
            commit_artifacts=list(state.get("commit_artifacts") or []),
            current_node="finalize_artifacts",
            visited_nodes=list(state.get("visited_nodes") or []),
            metadata={"max_repairs": max_repairs},
        )
        return {
            "commit_pending": True,
            "graph_state_v2": graph_state.model_dump(),
            "progress_events": [
                _state_progress_event(
                    event_type="compile.finalize.ready",
                    node_name="finalize_artifacts",
                    phase="persist",
                    message="最终产物已整理，等待提交。",
                    payload={"finalization_mode": str(state.get("finalization_mode") or ""), "review_required": bool(state.get("review_required"))},
                )
            ],
        }

    def commit_artifacts(state: _GraphState) -> Dict[str, Any]:
        validation = ValidationResultV2.model_validate(state.get("validation_result_v2") or {})
        draft_bundle_v2 = _draft_bundle_v2_from_any(state.get("report_ir") or {}, state.get("draft_bundle_v2") or {})
        legacy_bundle = _legacy_draft_bundle_from_v2(draft_bundle_v2)
        draft_conformance = _translate_validation_to_conformance(validation)
        factual_dump = state.get("factual_conformance") if isinstance(state.get("factual_conformance"), dict) else {}
        task = state.get("task") if isinstance(state.get("task"), dict) else {}
        graph_state_v2 = state.get("graph_state_v2") if isinstance(state.get("graph_state_v2"), dict) else {}
        artifact_paths = _artifact_paths_from_task(task)
        task_id = str(task.get("runtime_task_id") or task.get("task_id") or compile_thread_id).strip()
        rewrite_round = int(state.get("rewrite_round") or 0)
        artifact_payloads = {
            "draft_bundle": legacy_bundle.model_dump(),
            "draft_bundle_v2": draft_bundle_v2.model_dump(),
            "validation_result_v2": validation.model_dump(),
            "repair_plan_v2": state.get("repair_plan_v2") or {},
            "graph_state_v2": graph_state_v2,
            "approval_records": {
                "semantic_review_records": list(state.get("semantic_review_records") or []),
                "review_feedback_rounds": list(state.get("review_feedback_rounds") or []),
                "rewrite_lineage": list(state.get("rewrite_lineage") or []),
            },
            "full_markdown": {
                "markdown": str(state.get("final_markdown_current") or state.get("markdown") or "").strip(),
                "rewrite_round": rewrite_round,
                "finalization_mode": str(state.get("finalization_mode") or ""),
            },
        }
        schema_versions = {
            "draft_bundle": "draft-bundle.v1",
            "draft_bundle_v2": "draft-bundle.v2",
            "validation_result_v2": "validation-result.v2",
            "repair_plan_v2": "repair-plan.v2",
            "graph_state_v2": str(graph_state_v2.get("schema_version") or "deep-report-graph.v3"),
            "approval_records": "approval-records.v1",
            "full_markdown": "full-markdown.v1",
        }
        records: List[CommitArtifactRecord] = []
        for artifact_type, payload_value in artifact_payloads.items():
            approval_round = len(state.get("semantic_review_records") or []) if artifact_type == "approval_records" else 0
            record = CommitArtifactRecord(
                artifact_type=artifact_type,
                path=artifact_paths.get(artifact_type, ""),
                idempotency_key=_build_commit_idempotency_key(
                    task_id=task_id,
                    artifact_type=artifact_type,
                    rewrite_round=rewrite_round,
                    schema_version=schema_versions[artifact_type],
                ),
                rewrite_round=rewrite_round,
                approval_round=approval_round,
                schema_version=schema_versions[artifact_type],
                payload=payload_value if isinstance(payload_value, dict) else {},
            )
            records.append(record)
            if record.path and isinstance(record.payload, dict):
                _upsert_json_artifact(record.path, record.payload)
        final_output = {
            "status": "completed" if not state.get("review_required") else "failed",
            "policy_registry": state.get("policy_registry") or {},
            "scene_profile": state.get("scene_profile") or {},
            "style_profile": state.get("style_profile") or {},
            "layout_plan": state.get("layout_plan") or {},
            "section_budget": state.get("section_budget") or {},
            "writer_context": state.get("writer_context") or {},
            "section_plan": state.get("section_plan") or {},
            "draft_bundle": legacy_bundle.model_dump(),
            "draft_bundle_v2": draft_bundle_v2.model_dump(),
            "styled_draft_bundle": legacy_bundle.model_dump(),
            "validation_result_v2": validation.model_dump(),
            "repair_plan_v2": state.get("repair_plan_v2") or {},
            "graph_state_v2": graph_state_v2,
            "factual_conformance": factual_dump,
            "draft_conformance": draft_conformance.model_dump(),
            "style_conformance": draft_conformance.model_dump(),
            "utility_assessment": state.get("utility_assessment") or {},
            "review_required": bool(state.get("review_required")),
            "approval_required": bool(state.get("approval_required")),
            "approval_status": str(state.get("approval_status") or "none"),
            "blocked_reason": str(state.get("blocked_reason") or "").strip(),
            "markdown": str(state.get("final_markdown_current") or state.get("markdown") or "").strip(),
            "selected_template": (
                draft_bundle_v2.metadata.get("selected_template")
                if isinstance(draft_bundle_v2.metadata, dict)
                else {}
            ),
            "section_generation_receipts": (
                draft_bundle_v2.metadata.get("section_generation_receipts")
                if isinstance(draft_bundle_v2.metadata, dict)
                else []
            ),
            "degraded_sections": (
                draft_bundle_v2.metadata.get("degraded_sections")
                if isinstance(draft_bundle_v2.metadata, dict)
                else []
            ),
            "execution_phase": str(state.get("execution_phase") or "completed"),
            "rewrite_round": rewrite_round,
            "rewrite_budget": int(state.get("rewrite_budget") or 0),
            "finalization_mode": str(state.get("finalization_mode") or ""),
            "auto_rewrite_attempted": rewrite_round > 0,
            "auto_rewrite_succeeded": rewrite_round > 0 and not bool(state.get("review_required")),
            "rewrite_issue_count": int(state.get("rewrite_issue_count") or 0),
            "source_checkpoint_id": str(state.get("source_checkpoint_id") or ""),
            "parent_artifact_id": str(state.get("parent_artifact_id") or ""),
            "repaired_unit_ids": list(state.get("repaired_unit_ids") or []),
            "dropped_unit_ids": list(state.get("dropped_unit_ids") or []),
            "unchanged_unit_ids": list(state.get("unchanged_unit_ids") or []),
            "review_feedback_rounds": list(state.get("review_feedback_rounds") or []),
            "rewrite_contract": state.get("rewrite_contract") or {},
            "repair_history": list(state.get("repair_history") or []),
            "semantic_review_records": list(state.get("semantic_review_records") or []),
            "progress_events": list(state.get("progress_events") or []),
            "rewrite_lineage": list(state.get("rewrite_lineage") or []),
            "commit_artifacts": [record.model_dump() for record in records],
        }
        return {
            "commit_pending": False,
            "commit_idempotency_key": _build_commit_idempotency_key(
                task_id=task_id,
                artifact_type="graph_commit",
                rewrite_round=rewrite_round,
                schema_version="commit.v1",
            ),
            "commit_artifacts": [record.model_dump() for record in records],
            "final_output": final_output,
            "progress_events": [
                _state_progress_event(
                    event_type="compile.commit.completed",
                    node_name="commit_artifacts",
                    phase="persist",
                    message="编译图提交阶段已完成。",
                    payload={"artifact_count": len(records), "finalization_mode": str(state.get("finalization_mode") or "")},
                )
            ],
        }

    def route_after_validation(state: _GraphState) -> str:
        validation = ValidationResultV2.model_validate(state.get("validation_result_v2") or {})
        if validation.passed:
            return "markdown_compiler"
        if validation.gate == "repair":
            return "repair_patch_planner"
        return "semantic_review_interrupt"

    def route_after_semantic_gate(state: _GraphState) -> str:
        phase = str(state.get("execution_phase") or "").strip()
        if phase == "auto_rewrite":
            return "rewrite_contract_builder"
        if phase == "human_review":
            return "semantic_review_interrupt"
        return "finalize_artifacts"

    def route_after_human_review(state: _GraphState) -> str:
        phase = str(state.get("execution_phase") or "").strip()
        if phase == "auto_rewrite":
            return "rewrite_contract_builder"
        return "finalize_artifacts"

    def route_section_workers(state: _GraphState):
        slots = state.get("planner_slots") if isinstance(state.get("planner_slots"), list) else []
        if not slots:
            return "section_realizer_finalize"
        sends = [Send("section_realizer_worker", {"draft_bundle_v2": state.get("draft_bundle_v2") or {}, "planner_slot": slot}) for slot in slots if isinstance(slot, dict)]
        return sends or "section_realizer_finalize"

    def route_repair_workers(state: _GraphState):
        plan = RepairPlanV2.model_validate(state.get("repair_plan_v2") or {})
        if not plan.patches:
            return "repair_finalize"
        sends = [Send("repair_worker", {"repair_patch": patch.model_dump()}) for patch in plan.patches]
        return sends or "repair_finalize"

    builder = StateGraph(_GraphState)
    builder.add_node("load_context", _node("load_context", load_context))
    builder.add_node("planner_agent", _node("planner_agent", planner_agent))
    builder.add_node("existing_analysis_workers_subgraph", _node("existing_analysis_workers_subgraph", existing_analysis_workers_subgraph))
    builder.add_node("ir_merge", _node("ir_merge", ir_merge))
    builder.add_node("trace_binder", _node("trace_binder", trace_binder))
    builder.add_node("section_realizer_worker", _node("section_realizer_worker", section_realizer_worker, mutate_state=False))
    builder.add_node("section_realizer_finalize", _node("section_realizer_finalize", section_realizer_finalize))
    builder.add_node("unit_validator", _node("unit_validator", unit_validator))
    builder.add_node("repair_patch_planner", _node("repair_patch_planner", repair_patch_planner))
    builder.add_node("repair_worker", _node("repair_worker", repair_worker, mutate_state=False))
    builder.add_node("repair_finalize", _node("repair_finalize", repair_finalize))
    builder.add_node("markdown_compiler", _node("markdown_compiler", markdown_compiler))
    builder.add_node("semantic_gate_router", _node("semantic_gate_router", semantic_gate_router))
    builder.add_node("rewrite_contract_builder", _node("rewrite_contract_builder", rewrite_contract_builder))
    builder.add_node("auto_rewrite_agent", _node("auto_rewrite_agent", auto_rewrite_agent))
    builder.add_node("semantic_review_interrupt", _node("semantic_review_interrupt", semantic_review_interrupt))
    builder.add_node("finalize_artifacts", _node("finalize_artifacts", finalize_artifacts))
    builder.add_node("commit_artifacts", _node("commit_artifacts", commit_artifacts))
    builder.add_edge(START, "load_context")
    builder.add_edge("load_context", "planner_agent")
    builder.add_edge("planner_agent", "existing_analysis_workers_subgraph")
    builder.add_edge("existing_analysis_workers_subgraph", "ir_merge")
    builder.add_edge("ir_merge", "trace_binder")
    builder.add_conditional_edges(
        "trace_binder",
        route_section_workers,
        {
            "section_realizer_finalize": "section_realizer_finalize",
            "section_realizer_worker": "section_realizer_worker",
        },
    )
    builder.add_edge("section_realizer_worker", "section_realizer_finalize")
    builder.add_edge("section_realizer_finalize", "unit_validator")
    builder.add_conditional_edges(
        "unit_validator",
        route_after_validation,
        {
            "repair_patch_planner": "repair_patch_planner",
            "markdown_compiler": "markdown_compiler",
            "semantic_review_interrupt": "semantic_review_interrupt",
        },
    )
    builder.add_conditional_edges(
        "repair_patch_planner",
        route_repair_workers,
        {
            "repair_finalize": "repair_finalize",
            "repair_worker": "repair_worker",
        },
    )
    builder.add_edge("repair_worker", "repair_finalize")
    builder.add_edge("repair_finalize", "unit_validator")
    builder.add_edge("markdown_compiler", "semantic_gate_router")
    builder.add_conditional_edges(
        "semantic_gate_router",
        route_after_semantic_gate,
        {
            "rewrite_contract_builder": "rewrite_contract_builder",
            "semantic_review_interrupt": "semantic_review_interrupt",
            "finalize_artifacts": "finalize_artifacts",
        },
    )
    builder.add_edge("rewrite_contract_builder", "auto_rewrite_agent")
    builder.add_edge("auto_rewrite_agent", "semantic_gate_router")
    builder.add_conditional_edges(
        "semantic_review_interrupt",
        route_after_human_review,
        {
            "rewrite_contract_builder": "rewrite_contract_builder",
            "finalize_artifacts": "finalize_artifacts",
        },
    )
    builder.add_edge("finalize_artifacts", "commit_artifacts")
    builder.add_edge("commit_artifacts", END)

    initial_state = {
        "payload": payload,
        "report_ir": payload.get("report_ir") if isinstance(payload.get("report_ir"), dict) else {},
        "task": payload.get("task") if isinstance(payload.get("task"), dict) else {},
        "repair_count": 0,
        "rewrite_round": 0,
        "rewrite_budget": 0,
        "rewrite_issue_count": 0,
        "approval_required": False,
        "approval_status": "none",
        "finalization_mode": "",
        "commit_pending": False,
        "commit_idempotency_key": "",
        "visited_nodes": [],
        "planner_slots": [],
        "section_batches": [],
        "repair_batches": [],
        "review_feedback_contract": {},
        "review_feedback_rounds": [],
        "validation_issues": [],
        "repair_history": [],
        "semantic_review_records": [],
        "progress_events": [],
        "rewrite_lineage": [],
        "commit_artifacts": [],
    }
    config = build_report_runnable_config(
        thread_id=compile_thread_id,
        purpose="deep-report-compile",
        task_id=str(((payload.get("task") or {}).get("runtime_task_id")) or "").strip(),
        tags=["compile_graph"],
        metadata={"graph_thread_id": compile_thread_id},
        locator_hint=checkpoint_hint,
    )
    _invoke_input = Command(resume=review_decision) if isinstance(review_decision, dict) else initial_state
    with open_report_checkpointer(purpose="deep-report-compile", locator_hint=checkpoint_hint) as (checkpointer, runtime_profile):
        graph = builder.compile(checkpointer=checkpointer)
        state = _stream_graph_events(graph, _invoke_input, config, event_callback)
    if isinstance(state, dict) and isinstance(state.get("__interrupt__"), list) and state.get("__interrupt__"):
        interrupts = []
        for item in state.get("__interrupt__") or []:
            value = getattr(item, "value", None)
            interrupts.append(
                {
                    "interrupt_id": str(getattr(item, "id", "") or "").strip(),
                    "value": value if isinstance(value, dict) else {"value": value},
                }
            )
        primary = interrupts[0]["value"] if interrupts else {}
        graph_state = DeepReportGraphState(
            payload=payload,
            report_ir=state.get("report_ir") or payload.get("report_ir") or {},
            policy_registry=state.get("policy_registry") or {},
            scene_profile=state.get("scene_profile") or {},
            style_profile=state.get("style_profile") or {},
            layout_plan=state.get("layout_plan") or {},
            section_budget=state.get("section_budget") or {},
            writer_context=state.get("writer_context") or {},
            section_plan=state.get("section_plan") or {},
            structured_report_current=state.get("structured_report_current") or payload,
            draft_bundle_current=state.get("draft_bundle_current") or state.get("draft_bundle_v2") or {},
            final_markdown_current=str(primary.get("markdown_preview") or state.get("final_markdown_current") or "").strip(),
            execution_phase="human_review",
            rewrite_round=int(primary.get("rewrite_round") or state.get("rewrite_round") or 0),
            rewrite_budget=int(state.get("rewrite_budget") or 0),
            rewrite_issue_count=int(state.get("rewrite_issue_count") or 0),
            approval_required=True,
            approval_status=str(state.get("approval_status") or "pending"),
            finalization_mode="approval_required",
            commit_pending=False,
            commit_idempotency_key=str(state.get("commit_idempotency_key") or ""),
            draft_bundle=state.get("draft_bundle") or {},
            draft_bundle_v2=state.get("draft_bundle_v2") or {},
            validation_result_v2=primary.get("validation_result_v2") or state.get("validation_result_v2") or {},
            repair_plan_v2=primary.get("repair_plan_v2") or state.get("repair_plan_v2") or {},
            markdown=str(primary.get("markdown_preview") or "").strip(),
            factual_conformance=primary.get("factual_conformance") or state.get("factual_conformance") or {},
            review_required=True,
            blocked_reason="semantic_review_pending",
            repair_count=int(primary.get("repair_count") or state.get("repair_count") or 0),
            rewrite_contract=primary.get("rewrite_contract") or state.get("rewrite_contract") or {},
            review_feedback_contract=state.get("review_feedback_contract") or {},
            source_checkpoint_id=str(runtime_profile.checkpoint_locator or ""),
            parent_artifact_id=str(state.get("parent_artifact_id") or "structured_projection"),
            repaired_unit_ids=list(state.get("repaired_unit_ids") or []),
            dropped_unit_ids=list(state.get("dropped_unit_ids") or []),
            unchanged_unit_ids=list(state.get("unchanged_unit_ids") or []),
            review_feedback_rounds=list(state.get("review_feedback_rounds") or []),
            validation_issues=list(state.get("validation_issues") or []),
            repair_history=list(state.get("repair_history") or []),
            semantic_review_records=list(state.get("semantic_review_records") or []),
            progress_events=list(state.get("progress_events") or []),
            rewrite_lineage=list(state.get("rewrite_lineage") or []),
            commit_artifacts=list(state.get("commit_artifacts") or []),
            current_node="semantic_review_interrupt",
            visited_nodes=list(state.get("visited_nodes") or []),
            metadata={
                "max_repairs": max_repairs,
                "checkpoint_path": runtime_profile.checkpoint_path,
                "checkpoint_backend": runtime_profile.checkpointer_backend,
                "checkpoint_locator": runtime_profile.checkpoint_locator,
                "graph_thread_id": compile_thread_id,
                "interrupted": True,
            },
        )
        return {
            "status": "interrupted",
            "review_required": True,
            "approval_required": True,
            "approval_status": "pending",
            "interrupts": interrupts,
            "draft_bundle": state.get("draft_bundle") or {},
            "draft_bundle_v2": state.get("draft_bundle_v2") or {},
            "styled_draft_bundle": state.get("draft_bundle") or {},
            "validation_result_v2": primary.get("validation_result_v2") or state.get("validation_result_v2") or {},
            "repair_plan_v2": primary.get("repair_plan_v2") or state.get("repair_plan_v2") or {},
            "graph_state_v2": graph_state.model_dump(),
            "markdown": str(primary.get("markdown_preview") or "").strip(),
            "factual_conformance": primary.get("factual_conformance") or {
                "passed": False,
                "policy_version": "policy.v2",
                "stage": "final_markdown",
                "can_auto_recover": False,
                "requires_human_review": True,
                "issues": [],
                "semantic_deltas": [],
                "metadata": {"interrupted": True},
            },
            "utility_assessment": state.get("utility_assessment") or {},
            "policy_registry": state.get("policy_registry") or {},
            "scene_profile": state.get("scene_profile") or {},
            "style_profile": state.get("style_profile") or {},
            "layout_plan": state.get("layout_plan") or {},
            "section_budget": state.get("section_budget") or {},
            "writer_context": state.get("writer_context") or {},
            "section_plan": state.get("section_plan") or {},
            "blocked_reason": "semantic_review_pending",
            "execution_phase": "human_review",
            "finalization_mode": "approval_required",
            "rewrite_round": int(primary.get("rewrite_round") or state.get("rewrite_round") or 0),
            "rewrite_budget": int(state.get("rewrite_budget") or 0),
            "rewrite_issue_count": int(state.get("rewrite_issue_count") or 0),
            "rewrite_contract": primary.get("rewrite_contract") or state.get("rewrite_contract") or {},
            "review_feedback_rounds": list(state.get("review_feedback_rounds") or []),
            "rewrite_lineage": list(state.get("rewrite_lineage") or []),
            "checkpoint_path": runtime_profile.checkpoint_path,
            "checkpoint_backend": runtime_profile.checkpointer_backend,
            "checkpoint_locator": runtime_profile.checkpoint_locator,
            "graph_thread_id": compile_thread_id,
        }
    final_output = state.get("final_output") if isinstance(state, dict) and isinstance(state.get("final_output"), dict) else {}
    if not final_output:
        raise ValueError("report compilation graph did not produce a final output.")
    graph_state_v2 = final_output.get("graph_state_v2") if isinstance(final_output.get("graph_state_v2"), dict) else {}
    if graph_state_v2:
        metadata = graph_state_v2.get("metadata") if isinstance(graph_state_v2.get("metadata"), dict) else {}
        final_output["graph_state_v2"] = {
            **graph_state_v2,
            "metadata": {
                **metadata,
                "checkpoint_path": runtime_profile.checkpoint_path,
                "checkpoint_backend": runtime_profile.checkpointer_backend,
                "checkpoint_locator": runtime_profile.checkpoint_locator,
                "graph_thread_id": compile_thread_id,
            },
        }
    final_output["checkpoint_path"] = runtime_profile.checkpoint_path
    final_output["checkpoint_backend"] = runtime_profile.checkpointer_backend
    final_output["checkpoint_locator"] = runtime_profile.checkpoint_locator
    return final_output
