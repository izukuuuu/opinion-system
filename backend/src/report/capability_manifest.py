from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple

from .audit.loader import load_ability_ledger


FRAMEWORK_LAYER_TOOL = "tool"
FRAMEWORK_LAYER_WORKFLOW = "workflow"
FRAMEWORK_LAYER_SUBAGENT = "subagent"
FRAMEWORK_LAYER_COMPILER = "compiler"
FRAMEWORK_LAYER_VIEW = "view"

RUNTIME_AGENT = "agent_runtime"
RUNTIME_COORDINATOR = "deep_report_coordinator"
RUNTIME_SUBAGENT = "deep_report_subagent"
RUNTIME_PLAIN_COMPAT = "plain_compat"
RUNTIME_MANUAL_ONLY = "manual_only"

SKILL_MODE_METHOD = "method_binding"
SKILL_MODE_GUIDANCE = "guidance_only"


@dataclass(frozen=True)
class ReportCapabilitySpec:
    ability_id: str
    audit_layer: str
    framework_layer: str
    module: str
    title: str
    input_objects: Tuple[str, ...]
    output_objects: Tuple[str, ...]
    owned_artifacts: Tuple[str, ...]
    runtime_surfaces: Tuple[str, ...]
    tool_ids: Tuple[str, ...]
    skill_ids: Tuple[str, ...]
    entrypoints: Tuple[str, ...]
    entrypoint_tool_ids: Mapping[str, Tuple[str, ...]]
    backlog_status: str


@dataclass(frozen=True)
class ReportSkillContract:
    skill_id: str
    capability_ids: Tuple[str, ...]
    runtime_surfaces: Tuple[str, ...]
    agent_families: Tuple[str, ...]
    binding_mode: str = SKILL_MODE_METHOD


_ABILITY_LEDGER = load_ability_ledger()
_ABILITY_BY_ID = {entry.ability_id: entry for entry in _ABILITY_LEDGER.abilities}


def _tuple(values: Sequence[str] | None) -> Tuple[str, ...]:
    ordered: List[str] = []
    seen = set()
    for item in values or ():
        token = str(item or "").strip()
        if not token or token in seen:
            continue
        seen.add(token)
        ordered.append(token)
    return tuple(ordered)


def _projection_map(**entries: Sequence[str]) -> Mapping[str, Tuple[str, ...]]:
    return {str(key): _tuple(value) for key, value in entries.items() if _tuple(value)}


def _capability(
    ability_id: str,
    *,
    framework_layer: str,
    owned_artifacts: Sequence[str] = (),
    runtime_surfaces: Sequence[str] = (),
    tool_ids: Sequence[str] = (),
    skill_ids: Sequence[str] = (),
    entrypoints: Sequence[str] = (),
    entrypoint_tool_ids: Mapping[str, Sequence[str]] | None = None,
    backlog_status: str = "aligned",
) -> ReportCapabilitySpec:
    ledger_entry = _ABILITY_BY_ID.get(str(ability_id or "").strip())
    if ledger_entry is None:
        raise ValueError(f"Capability manifest references unknown audit ability: {ability_id}")
    projection = {
        key: _tuple(value)
        for key, value in (entrypoint_tool_ids or {}).items()
        if _tuple(value)
    }
    return ReportCapabilitySpec(
        ability_id=ledger_entry.ability_id,
        audit_layer=ledger_entry.layer,
        framework_layer=str(framework_layer or "").strip(),
        module=ledger_entry.module,
        title=ledger_entry.title,
        input_objects=_tuple(ledger_entry.input_objects),
        output_objects=_tuple(ledger_entry.output_objects),
        owned_artifacts=_tuple(owned_artifacts),
        runtime_surfaces=_tuple(runtime_surfaces),
        tool_ids=_tuple(tool_ids),
        skill_ids=_tuple(skill_ids),
        entrypoints=_tuple(entrypoints),
        entrypoint_tool_ids=projection,
        backlog_status=str(backlog_status or "aligned").strip() or "aligned",
    )


_CAPABILITY_SPECS: Tuple[ReportCapabilitySpec, ...] = (
    _capability(
        "runtime.task_orchestration",
        framework_layer=FRAMEWORK_LAYER_WORKFLOW,
        owned_artifacts=("structured_payload", "interrupt payload", "runtime diagnostic"),
        runtime_surfaces=(RUNTIME_COORDINATOR,),
        skill_ids=("sentiment-analysis-methodology",),
        entrypoints=("report_coordinator",),
        backlog_status="aligned",
    ),
    _capability(
        "evidence.normalize_retrieve_verify",
        framework_layer=FRAMEWORK_LAYER_WORKFLOW,
        owned_artifacts=("NormalizedTaskResult", "EvidenceCardPage", "CorpusCoverageResult", "ClaimVerificationPage"),
        runtime_surfaces=(RUNTIME_COORDINATOR, RUNTIME_SUBAGENT),
        tool_ids=(
            "normalize_task",
            "get_corpus_coverage",
            "retrieve_evidence_cards",
            "verify_claim_v2",
            "get_basic_analysis_snapshot",
        ),
        skill_ids=("retrieval-router-rules", "evidence-source-credibility"),
        entrypoints=("report_coordinator", "retrieval_router", "archive_evidence_organizer", "validator"),
        entrypoint_tool_ids=_projection_map(
            report_coordinator=(
                "normalize_task",
                "get_corpus_coverage",
                "retrieve_evidence_cards",
                "verify_claim_v2",
                "get_basic_analysis_snapshot",
            ),
            retrieval_router=("normalize_task", "get_corpus_coverage"),
            archive_evidence_organizer=("retrieve_evidence_cards", "get_basic_analysis_snapshot"),
            validator=("verify_claim_v2",),
        ),
        backlog_status="aligned",
    ),
    _capability(
        "semantic.report_ir_assembly",
        framework_layer=FRAMEWORK_LAYER_WORKFLOW,
        owned_artifacts=("ReportIR", "ArtifactManifest", "report_ir_summary"),
        runtime_surfaces=(RUNTIME_COORDINATOR,),
        entrypoints=("report_coordinator",),
        backlog_status="aligned",
    ),
    _capability(
        "semantic.agenda_frame_builder",
        framework_layer=FRAMEWORK_LAYER_SUBAGENT,
        owned_artifacts=("AgendaFrameMap",),
        runtime_surfaces=(RUNTIME_COORDINATOR, RUNTIME_SUBAGENT),
        tool_ids=("build_agenda_frame_map",),
        skill_ids=(),
        entrypoints=("report_coordinator", "agenda_frame_builder"),
        entrypoint_tool_ids=_projection_map(
            report_coordinator=("build_agenda_frame_map",),
            agenda_frame_builder=("build_agenda_frame_map",),
        ),
        backlog_status="partially_aligned",
    ),
    _capability(
        "semantic.conflict_map_builder",
        framework_layer=FRAMEWORK_LAYER_SUBAGENT,
        owned_artifacts=("ConflictMap",),
        runtime_surfaces=(RUNTIME_COORDINATOR, RUNTIME_SUBAGENT),
        tool_ids=("extract_actor_positions", "build_claim_actor_conflict"),
        skill_ids=("subject-stance-merging",),
        entrypoints=("report_coordinator", "stance_conflict", "claim_actor_conflict"),
        entrypoint_tool_ids=_projection_map(
            report_coordinator=("extract_actor_positions", "build_claim_actor_conflict"),
            stance_conflict=("extract_actor_positions",),
            claim_actor_conflict=("extract_actor_positions", "build_claim_actor_conflict"),
        ),
        backlog_status="aligned",
    ),
    _capability(
        "semantic.mechanism_builder",
        framework_layer=FRAMEWORK_LAYER_SUBAGENT,
        owned_artifacts=("MechanismSummary", "RiskSignalResult"),
        runtime_surfaces=(RUNTIME_COORDINATOR, RUNTIME_SUBAGENT),
        tool_ids=(
            "build_event_timeline",
            "compute_report_metrics",
            "build_mechanism_summary",
            "detect_risk_signals",
            "build_basic_analysis_insight",
        ),
        skill_ids=("timeline-alignment-slicing", "propagation-explanation-framework", "chart-interpretation-guidelines"),
        entrypoints=("report_coordinator", "timeline_analyst", "propagation_analyst"),
        entrypoint_tool_ids=_projection_map(
            report_coordinator=(
                "build_event_timeline",
                "compute_report_metrics",
                "build_mechanism_summary",
                "detect_risk_signals",
                "build_basic_analysis_insight",
            ),
            timeline_analyst=("build_event_timeline", "compute_report_metrics"),
            propagation_analyst=(
                "compute_report_metrics",
                "build_mechanism_summary",
                "detect_risk_signals",
                "build_basic_analysis_insight",
            ),
        ),
        backlog_status="aligned",
    ),
    _capability(
        "semantic.utility_gate",
        framework_layer=FRAMEWORK_LAYER_SUBAGENT,
        owned_artifacts=("UtilityAssessment",),
        runtime_surfaces=(RUNTIME_COORDINATOR, RUNTIME_SUBAGENT),
        tool_ids=("judge_decision_utility",),
        skill_ids=("quality-validation-backlink",),
        entrypoints=("report_coordinator", "decision_utility_judge"),
        entrypoint_tool_ids=_projection_map(
            report_coordinator=("judge_decision_utility",),
            decision_utility_judge=("judge_decision_utility",),
        ),
        backlog_status="aligned",
    ),
    _capability(
        "compiler.full_markdown_compile",
        framework_layer=FRAMEWORK_LAYER_COMPILER,
        owned_artifacts=("markdown", "full payload"),
        runtime_surfaces=(RUNTIME_PLAIN_COMPAT,),
        skill_ids=("report-writing-framework", "chart-interpretation-guidelines"),
        entrypoints=("document_composer",),
        backlog_status="partially_aligned",
    ),
    _capability(
        "compiler.scene_layout_critic_graph",
        framework_layer=FRAMEWORK_LAYER_COMPILER,
        owned_artifacts=("layout plan", "section budgets", "section markdown", "final markdown"),
        runtime_surfaces=(RUNTIME_PLAIN_COMPAT,),
        skill_ids=("report-writing-framework",),
        entrypoints=("document_composer",),
        backlog_status="partially_aligned",
    ),
    _capability(
        "semantic.evidence_semantic_enrichment",
        framework_layer=FRAMEWORK_LAYER_WORKFLOW,
        owned_artifacts=("subject scope", "risk action map", "claim matrix", "section evidence packs"),
        runtime_surfaces=(RUNTIME_COORDINATOR, RUNTIME_SUBAGENT),
        tool_ids=(
            "get_basic_analysis_snapshot",
            "build_basic_analysis_insight",
            "get_bertopic_snapshot",
            "build_bertopic_insight",
            "build_section_packet",
            "get_sentiment_analysis_framework",
            "get_sentiment_theories",
            "get_sentiment_case_template",
            "get_youth_sentiment_insight",
            "search_reference_insights",
            "build_event_reference_links",
        ),
        skill_ids=("basic-analysis-framework", "bertopic-evolution-framework", "sentiment-analysis-methodology"),
        entrypoints=("report_coordinator", "bertopic_evolution_analyst"),
        entrypoint_tool_ids=_projection_map(
            report_coordinator=(
                "get_basic_analysis_snapshot",
                "build_basic_analysis_insight",
                "get_bertopic_snapshot",
                "build_bertopic_insight",
                "build_section_packet",
                "get_sentiment_analysis_framework",
                "get_sentiment_theories",
                "get_sentiment_case_template",
                "get_youth_sentiment_insight",
                "search_reference_insights",
                "build_event_reference_links",
            ),
            bertopic_evolution_analyst=("get_bertopic_snapshot", "build_bertopic_insight"),
        ),
        backlog_status="partially_aligned",
    ),
    _capability(
        "compat.structured_generation",
        framework_layer=FRAMEWORK_LAYER_WORKFLOW,
        owned_artifacts=("legacy structured payload", "report cache"),
        runtime_surfaces=(RUNTIME_AGENT,),
        tool_ids=(
            "reference_search_tool",
            "raw_item_search_tool",
            "temporal_event_window_tool",
            "theory_matcher_tool",
            "policy_document_lookup_tool",
            "risk_assessment_tool",
            "content_focus_compare_tool",
            "recommendation_tool",
            "claim_verifier_tool",
        ),
        entrypoints=("report_agent", "evidence_analyst", "mechanism_analyst", "claim_judge"),
        backlog_status="aligned",
    ),
    _capability(
        "view.route_projection",
        framework_layer=FRAMEWORK_LAYER_VIEW,
        runtime_surfaces=(),
        backlog_status="aligned",
    ),
    _capability(
        "view.queue_execution_bridge",
        framework_layer=FRAMEWORK_LAYER_VIEW,
        runtime_surfaces=(),
        backlog_status="aligned",
    ),
    _capability(
        "view.frontend_workspace_projection",
        framework_layer=FRAMEWORK_LAYER_VIEW,
        runtime_surfaces=(),
        backlog_status="aligned",
    ),
)

_CAPABILITY_BY_ID: Dict[str, ReportCapabilitySpec] = {}
for _spec in _CAPABILITY_SPECS:
    if _spec.ability_id in _CAPABILITY_BY_ID:
        raise ValueError(f"Duplicate capability manifest entry: {_spec.ability_id}")
    _CAPABILITY_BY_ID[_spec.ability_id] = _spec


_SKILL_CONTRACTS: Tuple[ReportSkillContract, ...] = (
    ReportSkillContract(
        skill_id="retrieval-router-rules",
        capability_ids=("evidence.normalize_retrieve_verify",),
        runtime_surfaces=(RUNTIME_SUBAGENT,),
        agent_families=("retrieval_router",),
        binding_mode=SKILL_MODE_METHOD,
    ),
    ReportSkillContract(
        skill_id="evidence-source-credibility",
        capability_ids=("evidence.normalize_retrieve_verify",),
        runtime_surfaces=(RUNTIME_SUBAGENT,),
        agent_families=("archive_evidence_organizer",),
        binding_mode=SKILL_MODE_METHOD,
    ),
    ReportSkillContract(
        skill_id="timeline-alignment-slicing",
        capability_ids=("semantic.mechanism_builder",),
        runtime_surfaces=(RUNTIME_SUBAGENT,),
        agent_families=("timeline_analyst",),
        binding_mode=SKILL_MODE_METHOD,
    ),
    ReportSkillContract(
        skill_id="subject-stance-merging",
        capability_ids=("semantic.conflict_map_builder",),
        runtime_surfaces=(RUNTIME_SUBAGENT,),
        agent_families=("stance_conflict", "claim_actor_conflict"),
        binding_mode=SKILL_MODE_METHOD,
    ),
    ReportSkillContract(
        skill_id="propagation-explanation-framework",
        capability_ids=("semantic.mechanism_builder",),
        runtime_surfaces=(RUNTIME_SUBAGENT,),
        agent_families=("propagation_analyst",),
        binding_mode=SKILL_MODE_METHOD,
    ),
    ReportSkillContract(
        skill_id="chart-interpretation-guidelines",
        capability_ids=("semantic.mechanism_builder", "compiler.full_markdown_compile"),
        runtime_surfaces=(RUNTIME_SUBAGENT, RUNTIME_PLAIN_COMPAT),
        agent_families=("propagation_analyst", "document_composer"),
        binding_mode=SKILL_MODE_GUIDANCE,
    ),
    ReportSkillContract(
        skill_id="bertopic-evolution-framework",
        capability_ids=("semantic.evidence_semantic_enrichment",),
        runtime_surfaces=(RUNTIME_COORDINATOR, RUNTIME_SUBAGENT),
        agent_families=("bertopic_evolution_analyst",),
        binding_mode=SKILL_MODE_METHOD,
    ),
    ReportSkillContract(
        skill_id="basic-analysis-framework",
        capability_ids=("semantic.evidence_semantic_enrichment",),
        runtime_surfaces=(RUNTIME_COORDINATOR,),
        agent_families=(),
        binding_mode=SKILL_MODE_METHOD,
    ),
    ReportSkillContract(
        skill_id="sentiment-analysis-methodology",
        capability_ids=("semantic.evidence_semantic_enrichment",),
        runtime_surfaces=(RUNTIME_COORDINATOR,),
        agent_families=("report_coordinator",),
        binding_mode=SKILL_MODE_METHOD,
    ),
    ReportSkillContract(
        skill_id="quality-validation-backlink",
        capability_ids=("semantic.utility_gate", "evidence.normalize_retrieve_verify"),
        runtime_surfaces=(RUNTIME_SUBAGENT,),
        agent_families=("decision_utility_judge", "validator"),
        binding_mode=SKILL_MODE_GUIDANCE,
    ),
    ReportSkillContract(
        skill_id="report-writing-framework",
        capability_ids=("compiler.full_markdown_compile", "compiler.scene_layout_critic_graph"),
        runtime_surfaces=(RUNTIME_PLAIN_COMPAT,),
        agent_families=("document_composer",),
        binding_mode=SKILL_MODE_GUIDANCE,
    ),
)

_SKILL_CONTRACT_BY_ID: Dict[str, ReportSkillContract] = {}
for _contract in _SKILL_CONTRACTS:
    if _contract.skill_id in _SKILL_CONTRACT_BY_ID:
        raise ValueError(f"Duplicate skill contract entry: {_contract.skill_id}")
    validate_ids = [capability_id for capability_id in _contract.capability_ids if capability_id not in _CAPABILITY_BY_ID]
    if validate_ids:
        raise ValueError(f"Skill contract references unknown capabilities: {_contract.skill_id} -> {validate_ids}")
    _SKILL_CONTRACT_BY_ID[_contract.skill_id] = _contract

_SKILL_CONTRACT_ALIAS_MAP: Dict[str, ReportSkillContract] = {}
for _skill_id, _contract in _SKILL_CONTRACT_BY_ID.items():
    for _alias in {
        _skill_id,
        _skill_id.replace("-", "_"),
        _skill_id.replace("_", "-"),
    }:
        _SKILL_CONTRACT_ALIAS_MAP[str(_alias or "").strip()] = _contract


_SUBAGENT_CAPABILITY_MAP: Mapping[str, Tuple[str, ...]] = {
    "retrieval_router": ("evidence.normalize_retrieve_verify",),
    "archive_evidence_organizer": ("evidence.normalize_retrieve_verify",),
    "timeline_analyst": ("semantic.mechanism_builder",),
    "stance_conflict": ("semantic.conflict_map_builder",),
    "agenda_frame_builder": ("semantic.agenda_frame_builder",),
    "claim_actor_conflict": ("semantic.conflict_map_builder",),
    "propagation_analyst": ("semantic.mechanism_builder",),
    "bertopic_evolution_analyst": ("semantic.evidence_semantic_enrichment",),
    "decision_utility_judge": ("semantic.utility_gate",),
    "validator": ("evidence.normalize_retrieve_verify",),
    "writer": (),
}

_COORDINATOR_CAPABILITY_IDS: Tuple[str, ...] = (
    "runtime.task_orchestration",
    "evidence.normalize_retrieve_verify",
    "semantic.report_ir_assembly",
    "semantic.agenda_frame_builder",
    "semantic.conflict_map_builder",
    "semantic.mechanism_builder",
    "semantic.utility_gate",
    "semantic.evidence_semantic_enrichment",
)

_AGENT_RUNTIME_CAPABILITY_IDS: Tuple[str, ...] = ("compat.structured_generation",)


def get_report_capability_catalog() -> List[ReportCapabilitySpec]:
    return list(_CAPABILITY_SPECS)


def get_report_capability(ability_id: str) -> ReportCapabilitySpec:
    key = str(ability_id or "").strip()
    if not key or key not in _CAPABILITY_BY_ID:
        raise KeyError(f"Unknown report capability id: {ability_id}")
    return _CAPABILITY_BY_ID[key]


def validate_report_capability_ids(capability_ids: Sequence[str] | str) -> List[str]:
    items = (
        [token for token in str(capability_ids or "").split()]
        if isinstance(capability_ids, str)
        else [str(item or "").strip() for item in (capability_ids or [])]
    )
    normalized: List[str] = []
    seen = set()
    for raw in items:
        ability_id = str(raw or "").strip()
        if not ability_id:
            continue
        if ability_id in seen:
            raise ValueError(f"Duplicate report capability id: {ability_id}")
        if ability_id not in _CAPABILITY_BY_ID:
            raise ValueError(f"Unknown report capability id: {ability_id}")
        seen.add(ability_id)
        normalized.append(ability_id)
    return normalized


def get_report_skill_contract(skill_id: str) -> ReportSkillContract | None:
    return _SKILL_CONTRACT_ALIAS_MAP.get(str(skill_id or "").strip())


def get_report_skill_contract_catalog() -> List[ReportSkillContract]:
    return list(_SKILL_CONTRACTS)


def select_runtime_capability_ids(*, runtime_target: str, agent_name: str = "") -> List[str]:
    target = str(runtime_target or "").strip()
    if target == RUNTIME_COORDINATOR:
        return list(_COORDINATOR_CAPABILITY_IDS)
    if target == RUNTIME_SUBAGENT:
        return list(_SUBAGENT_CAPABILITY_MAP.get(str(agent_name or "").strip(), ()))
    if target in {RUNTIME_AGENT, "agent_runtime_section", "agent_runtime_analysis"}:
        return list(_AGENT_RUNTIME_CAPABILITY_IDS)
    if target == RUNTIME_PLAIN_COMPAT:
        return ["compiler.full_markdown_compile", "compiler.scene_layout_critic_graph"]
    return []


def select_runtime_tool_ids(*, runtime_target: str, agent_name: str = "") -> List[str]:
    selected: List[str] = []
    seen = set()
    entrypoint = "report_coordinator" if runtime_target == RUNTIME_COORDINATOR else str(agent_name or "").strip()
    for ability_id in select_runtime_capability_ids(runtime_target=runtime_target, agent_name=agent_name):
        spec = get_report_capability(ability_id)
        projected = spec.entrypoint_tool_ids.get(entrypoint) or spec.tool_ids
        for tool_id in projected:
            token = str(tool_id or "").strip()
            if not token or token in seen:
                continue
            seen.add(token)
            selected.append(token)
    return selected


def select_runtime_skill_ids(*, runtime_target: str, agent_name: str = "") -> List[str]:
    selected: List[str] = []
    seen = set()
    capability_ids = set(select_runtime_capability_ids(runtime_target=runtime_target, agent_name=agent_name))
    for contract in _SKILL_CONTRACTS:
        if runtime_target and runtime_target not in contract.runtime_surfaces:
            continue
        if agent_name and contract.agent_families and str(agent_name or "").strip() not in contract.agent_families:
            continue
        if capability_ids and not capability_ids.intersection(contract.capability_ids):
            continue
        if contract.skill_id in seen:
            continue
        seen.add(contract.skill_id)
        selected.append(contract.skill_id)
    return selected


def get_skill_capability_ids(skill_id: str) -> List[str]:
    contract = get_report_skill_contract(skill_id)
    return list(contract.capability_ids) if contract else []


def get_skill_runtime_surfaces(skill_id: str) -> List[str]:
    contract = get_report_skill_contract(skill_id)
    return list(contract.runtime_surfaces) if contract else []


def get_skill_agent_families(skill_id: str) -> List[str]:
    contract = get_report_skill_contract(skill_id)
    return list(contract.agent_families) if contract else []


def is_guidance_only_skill(skill_id: str) -> bool:
    contract = get_report_skill_contract(skill_id)
    return bool(contract and contract.binding_mode == SKILL_MODE_GUIDANCE)


@lru_cache(maxsize=1)
def load_capability_map_snapshot() -> Dict[str, Dict[str, object]]:
    snapshot: Dict[str, Dict[str, object]] = {}
    for spec in _CAPABILITY_SPECS:
        snapshot[spec.ability_id] = {
            "framework_layer": spec.framework_layer,
            "runtime_surfaces": list(spec.runtime_surfaces),
            "owned_artifacts": list(spec.owned_artifacts),
            "tool_ids": list(spec.tool_ids),
            "skill_ids": list(spec.skill_ids),
            "entrypoints": list(spec.entrypoints),
            "backlog_status": spec.backlog_status,
        }
    return snapshot


__all__ = [
    "FRAMEWORK_LAYER_COMPILER",
    "FRAMEWORK_LAYER_SUBAGENT",
    "FRAMEWORK_LAYER_TOOL",
    "FRAMEWORK_LAYER_VIEW",
    "FRAMEWORK_LAYER_WORKFLOW",
    "RUNTIME_AGENT",
    "RUNTIME_COORDINATOR",
    "RUNTIME_MANUAL_ONLY",
    "RUNTIME_PLAIN_COMPAT",
    "RUNTIME_SUBAGENT",
    "ReportCapabilitySpec",
    "ReportSkillContract",
    "SKILL_MODE_GUIDANCE",
    "SKILL_MODE_METHOD",
    "get_report_capability",
    "get_report_capability_catalog",
    "get_report_skill_contract",
    "get_report_skill_contract_catalog",
    "get_skill_agent_families",
    "get_skill_capability_ids",
    "get_skill_runtime_surfaces",
    "is_guidance_only_skill",
    "load_capability_map_snapshot",
    "select_runtime_capability_ids",
    "select_runtime_skill_ids",
    "select_runtime_tool_ids",
    "validate_report_capability_ids",
]
