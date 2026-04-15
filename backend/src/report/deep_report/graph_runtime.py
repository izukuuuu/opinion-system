from __future__ import annotations

import copy
import operator
import re
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
    compile_draft_units,
    run_factual_conformance,
    sanitize_public_markdown,
    select_scene_profile,
    resolve_style_profile,
)
from .schemas import (
    DeepReportGraphState,
    DraftBundle,
    DraftBundleV2,
    DraftUnit,
    DraftUnitV2,
    FactualConformanceIssue,
    FactualConformanceResult,
    RepairPatch,
    RepairPlanV2,
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
    markdown: str
    review_required: bool
    blocked_reason: str
    repair_count: int
    visited_nodes: List[str]
    current_node: str
    planner_slots: List[Dict[str, Any]]
    planner_slot: Dict[str, Any]
    section_batches: Annotated[List[Dict[str, Any]], _accumulate_or_reset]
    repair_patch: Dict[str, Any]
    repair_batches: Annotated[List[Dict[str, Any]], _accumulate_or_reset]
    final_output: Dict[str, Any]


_TRACEABLE_UNIT_TYPES = {"observation", "finding", "mechanism", "risk", "recommendation", "unresolved"}


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


def _node_phase(node_name: str) -> str:
    if node_name in {
        "unit_validator",
        "repair_patch_planner",
        "repair_worker",
        "repair_finalize",
        "repairer_agent",
        "compile_blocked",
    }:
        return "review"
    if node_name == "markdown_compiler":
        return "write"
    if node_name in {"artifact_renderer"}:
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
        # 根据render_mode选择编译方式
        scene_profile = state.get("scene_profile") or {}
        render_mode = str(scene_profile.get("render_mode", "") or "").strip()

        if render_mode == "template_driven":
            # 使用LLM深度写作（复刻BettaFish能力）
            from .deep_writer import compile_draft_units_with_llm
            from .schemas import CompilerSceneProfile
            scene = CompilerSceneProfile.model_validate(scene_profile)
            draft_bundle_v2 = compile_draft_units_with_llm(
                state["report_ir"],
                state["section_plan"],
                scene,
            )
            # 同时生成legacy draft_bundle用于兼容
            draft_bundle = compile_draft_units(state["report_ir"], state["section_plan"])
            return {
                "draft_bundle": draft_bundle.model_dump(),
                "draft_bundle_v2": draft_bundle_v2.model_dump(),
            }
        else:
            # 使用确定性拼接（claim_anchored模式）
            draft_bundle = compile_draft_units(state["report_ir"], state["section_plan"])
            draft_bundle_v2 = upgrade_draft_bundle_to_v2(state["report_ir"], draft_bundle)
            return {
                "draft_bundle": draft_bundle.model_dump(),
                "draft_bundle_v2": draft_bundle_v2.model_dump(),
            }

    def section_realizer_worker(state: _GraphState) -> Dict[str, Any]:
        bundle = DraftBundleV2.model_validate(state.get("draft_bundle_v2") or {})
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
        bundle = DraftBundleV2.model_validate(state.get("draft_bundle_v2") or {})
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
        return {"validation_result_v2": validation.model_dump()}

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
        return {"repair_plan_v2": plan.model_dump()}

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
        }

    def compile_blocked(state: _GraphState) -> Dict[str, Any]:
        validation = ValidationResultV2.model_validate(state.get("validation_result_v2") or {})
        bundle_v2 = DraftBundleV2.model_validate(state.get("draft_bundle_v2") or {})
        title = str(((state.get("task") or {}).get("topic_label")) or "").strip()
        markdown_preview = render_markdown_from_v2(state["report_ir"], bundle_v2, title=title)
        interrupt_event_key = f"{compile_thread_id}:compile_blocked:{int(state.get('repair_count') or 0)}"
        interrupt_payload = {
            "review_kind": "compile_blocked",
            "title": "语义边界确认",
            "summary": f"验证仍未通过，当前停在人工复核前置门禁。失败单元 {len(validation.failures)} 个。",
            "allowed_decisions": ["approve", "reject"],
            "event_key": interrupt_event_key,
            "review_mode": "annotation",
            "review_prompt": "文稿预览保持只读。如需继续写入，请补充人工审核批注，说明边界判断或后续写作调整要求。",
            "review_placeholder": "请输入审核批注、边界说明或需保留的写作调整意见",
            "markdown_preview": markdown_preview,
            "validation_result_v2": validation.model_dump(),
            "repair_plan_v2": state.get("repair_plan_v2") or {},
            "repair_count": int(state.get("repair_count") or 0),
        }
        if not is_resume_invocation:
            _emit_graph_event(
                event_callback,
                event_type="compile.blocked",
                node_name="compile_blocked",
                phase="review",
                title="正式编译已阻止",
                message=interrupt_payload["summary"],
                payload={**interrupt_payload, "event_key": f"{interrupt_event_key}:compile.blocked"},
            )
            _emit_graph_event(
                event_callback,
                event_type="interrupt.human_review",
                node_name="compile_blocked",
                phase="review",
                title="等待人工复核",
                message="修复回路未能自动闭合，当前需要人工复核。",
                payload={**interrupt_payload, "event_key": f"{interrupt_event_key}:interrupt.human_review"},
            )
        decision = interrupt(interrupt_payload)
        resolved = decision if isinstance(decision, dict) else {"decision": "approve" if decision else "reject"}
        decision_text = str(resolved.get("decision") or "").strip().lower() or "approve"
        review_payload = resolved.get("review_payload") if isinstance(resolved.get("review_payload"), dict) else {}
        review_comment = str(review_payload.get("comment") or "").strip()
        approved_markdown = markdown_preview
        factual = FactualConformanceResult(
            passed=False,
            policy_version="policy.v2",
            stage="final_markdown",
            can_auto_recover=False,
            requires_human_review=decision_text != "approve",
            issues=[
                FactualConformanceIssue(
                    issue_id="human-review-gate",
                    issue_type="human_review_required",
                    message="该文稿在自动 repair 后仍需人工确认。",
                    section_role="review",
                    sentence=validation.failures[0].target_unit_id if validation.failures else "",
                    trace_ids=[],
                    suggested_action=decision_text,
                )
            ],
            metadata={
                "decision": decision_text,
                "review_decision": decision_text,
                "review_mode": "annotation",
                "review_payload": review_payload,
                "review_comment": review_comment,
                "repair_count": int(state.get("repair_count") or 0),
            },
        )
        return {
            "markdown": approved_markdown,
            "review_required": decision_text != "approve",
            "blocked_reason": "" if decision_text == "approve" else "rejected_by_human_review",
            "factual_conformance": factual.model_dump(),
        }

    def markdown_compiler(state: _GraphState) -> Dict[str, Any]:
        bundle_v2 = DraftBundleV2.model_validate(state["draft_bundle_v2"])
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
        return {"markdown": markdown, "factual_conformance": factual.model_dump(), "review_required": bool(factual.requires_human_review)}

    def artifact_renderer(state: _GraphState) -> Dict[str, Any]:
        validation = ValidationResultV2.model_validate(state.get("validation_result_v2") or {})
        draft_bundle_v2 = DraftBundleV2.model_validate(state.get("draft_bundle_v2") or {})
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
            draft_bundle=legacy_bundle.model_dump(),
            draft_bundle_v2=draft_bundle_v2.model_dump(),
            validation_result_v2=validation.model_dump(),
            repair_plan_v2=state.get("repair_plan_v2") or {},
            markdown=str(state.get("markdown") or "").strip(),
            factual_conformance=factual_dump,
            review_required=bool(state.get("review_required")),
            blocked_reason=str(state.get("blocked_reason") or "").strip(),
            repair_count=int(state.get("repair_count") or 0),
            current_node="artifact_renderer",
            visited_nodes=list(state.get("visited_nodes") or []),
            metadata={"max_repairs": max_repairs},
        )
        return {
            "final_output": {
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
                "graph_state_v2": graph_state.model_dump(),
                "factual_conformance": factual_dump,
                "draft_conformance": draft_conformance.model_dump(),
                "style_conformance": draft_conformance.model_dump(),
                "utility_assessment": state.get("utility_assessment") or {},
                "review_required": bool(state.get("review_required")),
                "blocked_reason": str(state.get("blocked_reason") or "").strip(),
                "markdown": str(state.get("markdown") or "").strip(),
            }
        }

    def route_after_validation(state: _GraphState) -> str:
        validation = ValidationResultV2.model_validate(state.get("validation_result_v2") or {})
        if validation.passed:
            return "markdown_compiler"
        if validation.gate == "repair":
            return "repair_patch_planner"
        return "compile_blocked"

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
    builder.add_node("compile_blocked", _node("compile_blocked", compile_blocked))
    builder.add_node("markdown_compiler", _node("markdown_compiler", markdown_compiler))
    builder.add_node("artifact_renderer", _node("artifact_renderer", artifact_renderer))
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
            "compile_blocked": "compile_blocked",
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
    builder.add_edge("compile_blocked", "artifact_renderer")
    builder.add_edge("markdown_compiler", "artifact_renderer")
    builder.add_edge("artifact_renderer", END)

    initial_state = {
        "payload": payload,
        "report_ir": payload.get("report_ir") if isinstance(payload.get("report_ir"), dict) else {},
        "task": payload.get("task") if isinstance(payload.get("task"), dict) else {},
        "repair_count": 0,
        "visited_nodes": [],
        "planner_slots": [],
        "section_batches": [],
        "repair_batches": [],
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
            draft_bundle=state.get("draft_bundle") or {},
            draft_bundle_v2=state.get("draft_bundle_v2") or {},
            validation_result_v2=primary.get("validation_result_v2") or state.get("validation_result_v2") or {},
            repair_plan_v2=primary.get("repair_plan_v2") or state.get("repair_plan_v2") or {},
            markdown=str(primary.get("markdown_preview") or "").strip(),
            factual_conformance={},
            review_required=True,
            blocked_reason="validation_failed_after_repair",
            repair_count=int(primary.get("repair_count") or state.get("repair_count") or 0),
            current_node="compile_blocked",
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
            "interrupts": interrupts,
            "draft_bundle": state.get("draft_bundle") or {},
            "draft_bundle_v2": state.get("draft_bundle_v2") or {},
            "styled_draft_bundle": state.get("draft_bundle") or {},
            "validation_result_v2": primary.get("validation_result_v2") or state.get("validation_result_v2") or {},
            "repair_plan_v2": primary.get("repair_plan_v2") or state.get("repair_plan_v2") or {},
            "graph_state_v2": graph_state.model_dump(),
            "markdown": str(primary.get("markdown_preview") or "").strip(),
            "factual_conformance": {
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
            "blocked_reason": "validation_failed_after_repair",
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
