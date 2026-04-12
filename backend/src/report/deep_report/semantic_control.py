from __future__ import annotations

import asyncio
import json
import re
from typing import Any, Dict, List

from ...utils.ai import call_langchain_chat
from .schemas import ConformancePolicyRegistry, FactualConformanceIssue, ReportIR, SemanticLatticeState


def _safe_async(coro: Any) -> Any:
    try:
        return asyncio.run(coro)
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(coro)
        finally:
            loop.close()


def _safe_json_dict(raw_text: Any) -> Dict[str, Any]:
    text = str(raw_text or "").strip()
    if not text:
        return {}
    try:
        value = json.loads(text)
    except Exception:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            return {}
        try:
            value = json.loads(match.group(0))
        except Exception:
            return {}
    return value if isinstance(value, dict) else {}


def _trace_context(payload: ReportIR, trace_ids: List[str]) -> Dict[str, Any]:
    claim_lookup = {claim.claim_id: claim for claim in payload.claim_set.claims}
    evidence_lookup = {entry.evidence_id: entry for entry in payload.evidence_ledger.entries}
    risk_lookup = {risk.risk_id: risk for risk in payload.risk_register.risks}
    recommendation_lookup = {item.candidate_id: item for item in payload.recommendation_candidates.items}
    unresolved_lookup = {item.item_id: item for item in payload.unresolved_points.items}
    actor_lookup = {actor.actor_id: actor for actor in payload.actor_registry.actors}
    return {
        "claims": [
            {
                "claim_id": item.claim_id,
                "text": item.text,
                "status": item.status,
                "write_policy": item.write_policy,
            }
            for trace_id in trace_ids
            for item in [claim_lookup.get(trace_id)]
            if item is not None
        ],
        "evidence": [
            {
                "evidence_id": item.evidence_id,
                "title": item.title,
                "platform": item.platform,
                "published_at": item.published_at,
                "confidence": item.confidence,
            }
            for trace_id in trace_ids
            for item in [evidence_lookup.get(trace_id)]
            if item is not None
        ],
        "risks": [
            {
                "risk_id": item.risk_id,
                "risk_type": item.risk_type,
                "severity": item.severity,
                "spread_condition": item.spread_condition,
            }
            for trace_id in trace_ids
            for item in [risk_lookup.get(trace_id)]
            if item is not None
        ],
        "recommendations": [
            {
                "candidate_id": item.candidate_id,
                "action": item.action,
                "priority": item.priority,
            }
            for trace_id in trace_ids
            for item in [recommendation_lookup.get(trace_id)]
            if item is not None
        ],
        "unresolved": [
            {
                "item_id": item.item_id,
                "statement": item.statement,
                "reason": item.reason,
            }
            for trace_id in trace_ids
            for item in [unresolved_lookup.get(trace_id)]
            if item is not None
        ],
        "actors": [
            {
                "actor_id": item.actor_id,
                "canonical_name": item.canonical_name,
                "category": item.category,
            }
            for trace_id in trace_ids
            for item in [actor_lookup.get(trace_id)]
            if item is not None
        ],
    }


def extract_semantic_state(
    payload: ReportIR,
    *,
    text: str,
    section_role: str,
    trace_ids: List[str],
    baseline: SemanticLatticeState,
    registry: ConformancePolicyRegistry,
) -> SemanticLatticeState:
    prompt = (
        "你是舆情报告语义状态抽取器。"
        "只输出 JSON，不要输出解释。"
        "请根据文本、trace 上下文与 baseline，抽取新的 SemanticLatticeState。"
        "如果文本没有足够依据上调语义，保持 baseline。"
        "JSON keys 必须为：assertion_certainty, scope_quantifier, risk_maturity, action_force, "
        "time_certainty, actor_scope, evidence_coverage, verification_status。"
    )
    raw = ""
    try:
        raw = _safe_async(
            call_langchain_chat(
                [
                    {"role": "system", "content": prompt},
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "section_role": section_role,
                                "text": str(text or "").strip(),
                                "trace_ids": trace_ids,
                                "baseline": baseline.model_dump(),
                                "policy_version": registry.policy_version,
                                "trace_context": _trace_context(payload, trace_ids),
                            },
                            ensure_ascii=False,
                        ),
                    },
                ],
                task="report",
                model_role="report",
                temperature=0.0,
                max_tokens=260,
            )
        )
    except Exception:
        raw = ""
    parsed = _safe_json_dict(raw)
    if not parsed:
        return baseline
    try:
        return SemanticLatticeState.model_validate(parsed)
    except Exception:
        return baseline


def judge_evidence_support(
    payload: ReportIR,
    *,
    section_role: str,
    trace_ids: List[str],
    baseline: SemanticLatticeState,
    actual: SemanticLatticeState,
) -> List[FactualConformanceIssue]:
    issues: List[FactualConformanceIssue] = []
    claim_lookup = {claim.claim_id: claim for claim in payload.claim_set.claims}
    risk_lookup = {risk.risk_id: risk for risk in payload.risk_register.risks}
    recommendation_lookup = {item.candidate_id: item for item in payload.recommendation_candidates.items}
    evidence_ids = {trace_id for trace_id in trace_ids if trace_id.startswith("ev-") or trace_id.startswith("evidence:")}
    for trace_id in trace_ids:
        claim = claim_lookup.get(trace_id)
        if claim is not None:
            evidence_ids.update(str(item).strip() for item in claim.support_evidence_ids if str(item or "").strip())
        risk = risk_lookup.get(trace_id)
        if risk is not None:
            evidence_ids.update(str(item).strip() for item in risk.trigger_evidence_ids if str(item or "").strip())
    risk_ids = {trace_id for trace_id in trace_ids if trace_id.startswith("risk-") or trace_id.startswith("risk:")}
    recommendation_ids = {trace_id for trace_id in trace_ids if trace_id.startswith("act-") or trace_id.startswith("candidate:")}
    for trace_id in trace_ids:
        recommendation = recommendation_lookup.get(trace_id)
        if recommendation is not None:
            recommendation_ids.add(trace_id)
    if actual.evidence_coverage == "anchored" and not evidence_ids:
        issues.append(
            FactualConformanceIssue(
                issue_id=f"support:{section_role}:evidence",
                issue_type="evidence_coverage_violation",
                message="当前语义状态要求证据锚点，但 trace 中没有 evidence 绑定。",
                section_role=section_role,
                sentence="",
                trace_ids=list(trace_ids),
                semantic_dimension="evidence_coverage",
                before_level=baseline.evidence_coverage,
                after_level=actual.evidence_coverage,
                suggested_action="请补充 evidence trace，或降低当前判断的覆盖度。",
            )
        )
    if actual.actor_scope in {"multi_actor", "public"} and len(evidence_ids) < 2:
        issues.append(
            FactualConformanceIssue(
                issue_id=f"support:{section_role}:actor_scope",
                issue_type="actor_scope_violation",
                message="主体覆盖范围被上调，但没有足够多源证据支撑。",
                section_role=section_role,
                sentence="",
                trace_ids=list(trace_ids),
                semantic_dimension="actor_scope",
                before_level=baseline.actor_scope,
                after_level=actual.actor_scope,
                suggested_action="请回退主体覆盖范围，或补充跨平台证据。",
            )
        )
    if section_role == "risks" and actual.risk_maturity in {"formed", "systemic"} and not risk_ids:
        issues.append(
            FactualConformanceIssue(
                issue_id=f"support:{section_role}:risk",
                issue_type="risk_boundary_violation",
                message="风险成熟度被上调，但没有 risk trace 支撑。",
                section_role=section_role,
                sentence="",
                trace_ids=list(trace_ids),
                semantic_dimension="risk_maturity",
                before_level=baseline.risk_maturity,
                after_level=actual.risk_maturity,
                suggested_action="请绑定已登记 risk，或降低风险成熟度。",
            )
        )
    if section_role == "recommendations" and actual.action_force in {"urgent", "mandatory"} and not recommendation_ids:
        issues.append(
            FactualConformanceIssue(
                issue_id=f"support:{section_role}:recommendation",
                issue_type="recommendation_boundary_violation",
                message="行动强制性被上调，但没有 recommendation trace 支撑。",
                section_role=section_role,
                sentence="",
                trace_ids=list(trace_ids),
                semantic_dimension="action_force",
                before_level=baseline.action_force,
                after_level=actual.action_force,
                suggested_action="请绑定 recommendation trace，或回退动作强度。",
            )
        )
    return issues
