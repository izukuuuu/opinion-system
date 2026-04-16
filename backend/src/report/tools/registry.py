from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Tuple

from langchain.tools import BaseTool

from ..capability_manifest import (
    RUNTIME_AGENT,
    RUNTIME_COORDINATOR,
    RUNTIME_MANUAL_ONLY,
    RUNTIME_SUBAGENT,
)
from ..deep_report.agent_tools import (
    build_agenda_frame_map,
    build_basic_analysis_insight,
    build_bertopic_insight,
    build_claim_actor_conflict,
    build_event_timeline,
    build_mechanism_summary,
    build_section_packet,
    compute_report_metrics,
    detect_risk_signals,
    extract_actor_positions,
    get_basic_analysis_snapshot,
    get_bertopic_snapshot,
    get_corpus_coverage,
    get_report_template,
    judge_decision_utility,
    normalize_task,
    retrieve_evidence_cards,
    verify_claim_v2,
)
from .decision_tools import recommendation_tool, risk_assessment_tool
from .knowledge_base_tools import (
    append_expert_judgement,
    build_event_reference_links,
    get_sentiment_analysis_framework,
    get_sentiment_case_template,
    get_sentiment_theories,
    get_youth_sentiment_insight,
    search_reference_insights,
)
from .knowledge_tools import policy_document_lookup_tool, reference_search_tool, theory_matcher_tool
from .retrieval_tools import (
    claim_verifier_tool,
    content_focus_compare_tool,
    raw_item_search_tool,
    temporal_event_window_tool,
)
from .media_tools import media_coverage_summary_tool
from .validation import validate_langchain_toolset


READ_ONLY = "read_only"
STATE_MUTATING = "state_mutating"
RUNTIME_SKILL_ONLY = "skill_only"

READ_TOOL = "read"
SYNTHESIS_TOOL = "synthesis"
STATE_MUTATING_TOOL = "state_mutating"
MANUAL_TOOL = "manual"


@dataclass(frozen=True)
class ReportToolSpec:
    tool_id: str
    tool: BaseTool
    capability_tags: Tuple[str, ...]
    runtime_tags: Tuple[str, ...]
    tool_class: str
    mutability: str = READ_ONLY


def _spec(
    tool: BaseTool,
    *,
    capability_tags: Sequence[str],
    runtime_tags: Sequence[str],
    tool_class: str,
    mutability: str = READ_ONLY,
) -> ReportToolSpec:
    tool_id = str(getattr(tool, "name", "") or "").strip()
    if not tool_id:
        raise ValueError("Report tool is missing a canonical name.")
    return ReportToolSpec(
        tool_id=tool_id,
        tool=tool,
        capability_tags=tuple(dict.fromkeys(str(item).strip() for item in capability_tags if str(item or "").strip())),
        runtime_tags=tuple(dict.fromkeys(str(item).strip() for item in runtime_tags if str(item or "").strip())),
        tool_class=str(tool_class or READ_TOOL).strip() or READ_TOOL,
        mutability=STATE_MUTATING if str(mutability or "").strip() == STATE_MUTATING else READ_ONLY,
    )


_TOOL_SPECS: Tuple[ReportToolSpec, ...] = (
    _spec(
        reference_search_tool,
        capability_tags=("knowledge", "analysis"),
        runtime_tags=(RUNTIME_AGENT,),
        tool_class=READ_TOOL,
    ),
    _spec(
        raw_item_search_tool,
        capability_tags=("retrieval", "analysis"),
        runtime_tags=(RUNTIME_AGENT,),
        tool_class=READ_TOOL,
    ),
    _spec(
        temporal_event_window_tool,
        capability_tags=("retrieval", "analysis", "timeline"),
        runtime_tags=(RUNTIME_AGENT,),
        tool_class=READ_TOOL,
    ),
    _spec(
        theory_matcher_tool,
        capability_tags=("knowledge", "analysis"),
        runtime_tags=(RUNTIME_AGENT,),
        tool_class=READ_TOOL,
    ),
    _spec(
        policy_document_lookup_tool,
        capability_tags=("knowledge", "analysis"),
        runtime_tags=(RUNTIME_AGENT,),
        tool_class=READ_TOOL,
    ),
    _spec(
        risk_assessment_tool,
        capability_tags=("analysis", "risk"),
        runtime_tags=(RUNTIME_AGENT,),
        tool_class=SYNTHESIS_TOOL,
    ),
    _spec(
        content_focus_compare_tool,
        capability_tags=("retrieval", "analysis"),
        runtime_tags=(RUNTIME_AGENT,),
        tool_class=READ_TOOL,
    ),
    _spec(
        recommendation_tool,
        capability_tags=("analysis", "decision"),
        runtime_tags=(RUNTIME_AGENT,),
        tool_class=SYNTHESIS_TOOL,
    ),
    _spec(
        claim_verifier_tool,
        capability_tags=("validation", "analysis"),
        runtime_tags=(RUNTIME_AGENT,),
        tool_class=SYNTHESIS_TOOL,
    ),
    _spec(
        normalize_task,
        capability_tags=("retrieval", "analysis"),
        runtime_tags=(RUNTIME_COORDINATOR, RUNTIME_SUBAGENT),
        tool_class=SYNTHESIS_TOOL,
    ),
    _spec(
        get_corpus_coverage,
        capability_tags=("retrieval", "analysis"),
        runtime_tags=(RUNTIME_COORDINATOR, RUNTIME_SUBAGENT),
        tool_class=READ_TOOL,
    ),
    _spec(
        retrieve_evidence_cards,
        capability_tags=("retrieval", "analysis", "evidence"),
        runtime_tags=(RUNTIME_COORDINATOR, RUNTIME_SUBAGENT),
        tool_class=READ_TOOL,
    ),
    _spec(
        get_basic_analysis_snapshot,
        capability_tags=("analysis", "knowledge"),
        runtime_tags=(RUNTIME_COORDINATOR, RUNTIME_SUBAGENT),
        tool_class=READ_TOOL,
    ),
    _spec(
        build_basic_analysis_insight,
        capability_tags=("analysis", "writer_support"),
        runtime_tags=(RUNTIME_COORDINATOR, RUNTIME_SUBAGENT),
        tool_class=SYNTHESIS_TOOL,
    ),
    _spec(
        get_bertopic_snapshot,
        capability_tags=("analysis", "knowledge"),
        runtime_tags=(RUNTIME_COORDINATOR, RUNTIME_SUBAGENT),
        tool_class=READ_TOOL,
    ),
    _spec(
        build_bertopic_insight,
        capability_tags=("analysis", "writer_support"),
        runtime_tags=(RUNTIME_COORDINATOR, RUNTIME_SUBAGENT),
        tool_class=SYNTHESIS_TOOL,
    ),
    _spec(
        build_event_timeline,
        capability_tags=("analysis", "timeline"),
        runtime_tags=(RUNTIME_COORDINATOR, RUNTIME_SUBAGENT),
        tool_class=SYNTHESIS_TOOL,
    ),
    _spec(
        compute_report_metrics,
        capability_tags=("analysis", "metrics"),
        runtime_tags=(RUNTIME_COORDINATOR, RUNTIME_SUBAGENT),
        tool_class=SYNTHESIS_TOOL,
    ),
    _spec(
        extract_actor_positions,
        capability_tags=("analysis", "subjects"),
        runtime_tags=(RUNTIME_COORDINATOR, RUNTIME_SUBAGENT),
        tool_class=SYNTHESIS_TOOL,
    ),
    _spec(
        build_agenda_frame_map,
        capability_tags=("analysis", "agenda"),
        runtime_tags=(RUNTIME_COORDINATOR, RUNTIME_SUBAGENT),
        tool_class=SYNTHESIS_TOOL,
    ),
    _spec(
        build_claim_actor_conflict,
        capability_tags=("analysis", "conflict"),
        runtime_tags=(RUNTIME_COORDINATOR, RUNTIME_SUBAGENT),
        tool_class=SYNTHESIS_TOOL,
    ),
    _spec(
        build_mechanism_summary,
        capability_tags=("analysis", "mechanism"),
        runtime_tags=(RUNTIME_COORDINATOR, RUNTIME_SUBAGENT),
        tool_class=SYNTHESIS_TOOL,
    ),
    _spec(
        detect_risk_signals,
        capability_tags=("analysis", "risk"),
        runtime_tags=(RUNTIME_COORDINATOR, RUNTIME_SUBAGENT),
        tool_class=SYNTHESIS_TOOL,
    ),
    _spec(
        judge_decision_utility,
        capability_tags=("analysis", "decision", "validation"),
        runtime_tags=(RUNTIME_COORDINATOR, RUNTIME_SUBAGENT),
        tool_class=SYNTHESIS_TOOL,
    ),
    _spec(
        verify_claim_v2,
        capability_tags=("validation", "analysis"),
        runtime_tags=(RUNTIME_COORDINATOR, RUNTIME_SUBAGENT),
        tool_class=SYNTHESIS_TOOL,
    ),
    _spec(
        build_section_packet,
        capability_tags=("analysis", "writer_support"),
        runtime_tags=(RUNTIME_COORDINATOR,),
        tool_class=SYNTHESIS_TOOL,
    ),
    _spec(
        get_report_template,
        capability_tags=("knowledge", "writer_support"),
        runtime_tags=(RUNTIME_COORDINATOR, RUNTIME_SUBAGENT),
        tool_class=READ_TOOL,
    ),
    _spec(
        get_sentiment_analysis_framework,
        capability_tags=("knowledge", "methodology"),
        runtime_tags=(RUNTIME_COORDINATOR, RUNTIME_SKILL_ONLY),
        tool_class=READ_TOOL,
    ),
    _spec(
        get_sentiment_theories,
        capability_tags=("knowledge", "methodology"),
        runtime_tags=(RUNTIME_COORDINATOR, RUNTIME_SKILL_ONLY),
        tool_class=READ_TOOL,
    ),
    _spec(
        get_sentiment_case_template,
        capability_tags=("knowledge", "writer_support", "methodology"),
        runtime_tags=(RUNTIME_COORDINATOR, RUNTIME_SKILL_ONLY),
        tool_class=READ_TOOL,
    ),
    _spec(
        get_youth_sentiment_insight,
        capability_tags=("knowledge", "methodology"),
        runtime_tags=(RUNTIME_COORDINATOR, RUNTIME_SKILL_ONLY),
        tool_class=READ_TOOL,
    ),
    _spec(
        search_reference_insights,
        capability_tags=("knowledge", "retrieval", "methodology"),
        runtime_tags=(RUNTIME_COORDINATOR, RUNTIME_SKILL_ONLY),
        tool_class=READ_TOOL,
    ),
    _spec(
        build_event_reference_links,
        capability_tags=("knowledge", "methodology"),
        runtime_tags=(RUNTIME_COORDINATOR, RUNTIME_SKILL_ONLY),
        tool_class=READ_TOOL,
    ),
    _spec(
        append_expert_judgement,
        capability_tags=("knowledge", "methodology"),
        runtime_tags=(RUNTIME_SKILL_ONLY, RUNTIME_MANUAL_ONLY),
        tool_class=MANUAL_TOOL,
        mutability=STATE_MUTATING,
    ),
    _spec(
        media_coverage_summary_tool,
        capability_tags=("media_analysis", "source_credibility", "analysis"),
        runtime_tags=(RUNTIME_COORDINATOR, RUNTIME_SUBAGENT),
        tool_class=READ_TOOL,
    ),
)

_TOOL_SPEC_BY_ID: Dict[str, ReportToolSpec] = {}
for _spec_item in _TOOL_SPECS:
    if _spec_item.tool_id in _TOOL_SPEC_BY_ID:
        raise ValueError(f"Duplicate report tool id: {_spec_item.tool_id}")
    _TOOL_SPEC_BY_ID[_spec_item.tool_id] = _spec_item


REPORT_ANALYSIS_TOOLS = [
    reference_search_tool,
    raw_item_search_tool,
    temporal_event_window_tool,
    theory_matcher_tool,
    policy_document_lookup_tool,
    risk_assessment_tool,
    content_focus_compare_tool,
    recommendation_tool,
    claim_verifier_tool,
    media_coverage_summary_tool,
]

DEFAULT_TOOL_NAMES = [
    "reference_search_tool",
    "theory_matcher_tool",
    "claim_verifier_tool",
]

SECTION_TOOL_NAME_MAP: Mapping[Tuple[str, str], Sequence[str]] = {
    ("policy_dynamics", "evolution"): [
        "raw_item_search_tool",
        "temporal_event_window_tool",
        "content_focus_compare_tool",
        "claim_verifier_tool",
        "reference_search_tool",
        "theory_matcher_tool",
    ],
    ("policy_dynamics", "response"): [
        "raw_item_search_tool",
        "content_focus_compare_tool",
        "claim_verifier_tool",
        "reference_search_tool",
        "theory_matcher_tool",
    ],
    ("policy_dynamics", "impact"): [
        "raw_item_search_tool",
        "content_focus_compare_tool",
        "risk_assessment_tool",
        "claim_verifier_tool",
        "reference_search_tool",
        "theory_matcher_tool",
    ],
    ("policy_dynamics", "benchmark"): [
        "raw_item_search_tool",
        "content_focus_compare_tool",
        "reference_search_tool",
        "claim_verifier_tool",
    ],
    ("policy_dynamics", "action"): [
        "risk_assessment_tool",
        "recommendation_tool",
        "claim_verifier_tool",
        "reference_search_tool",
    ],
    ("public_hotspot", "propagation"): [
        "raw_item_search_tool",
        "temporal_event_window_tool",
        "claim_verifier_tool",
        "reference_search_tool",
    ],
    ("public_hotspot", "focus"): [
        "raw_item_search_tool",
        "content_focus_compare_tool",
        "claim_verifier_tool",
        "reference_search_tool",
    ],
    ("public_hotspot", "mechanism"): [
        "raw_item_search_tool",
        "content_focus_compare_tool",
        "theory_matcher_tool",
        "claim_verifier_tool",
        "reference_search_tool",
    ],
    ("public_hotspot", "action"): [
        "risk_assessment_tool",
        "recommendation_tool",
        "claim_verifier_tool",
        "reference_search_tool",
    ],
    ("crisis_response", "timeline"): [
        "raw_item_search_tool",
        "temporal_event_window_tool",
        "claim_verifier_tool",
        "reference_search_tool",
    ],
    ("crisis_response", "propagation"): [
        "raw_item_search_tool",
        "temporal_event_window_tool",
        "content_focus_compare_tool",
        "claim_verifier_tool",
        "reference_search_tool",
    ],
    ("crisis_response", "risk"): [
        "risk_assessment_tool",
        "raw_item_search_tool",
        "claim_verifier_tool",
        "reference_search_tool",
    ],
    ("crisis_response", "response"): [
        "risk_assessment_tool",
        "recommendation_tool",
        "claim_verifier_tool",
        "reference_search_tool",
    ],
    ("routine_monitoring", "trend"): [
        "raw_item_search_tool",
        "temporal_event_window_tool",
        "reference_search_tool",
    ],
    ("routine_monitoring", "timeline"): [
        "raw_item_search_tool",
        "temporal_event_window_tool",
        "claim_verifier_tool",
    ],
    ("routine_monitoring", "topics"): [
        "raw_item_search_tool",
        "content_focus_compare_tool",
        "reference_search_tool",
    ],
    ("routine_monitoring", "risk"): [
        "risk_assessment_tool",
        "recommendation_tool",
        "claim_verifier_tool",
    ],
    ("evidence_dossier", "evidence_matrix"): [
        "raw_item_search_tool",
        "claim_verifier_tool",
        "reference_search_tool",
    ],
    ("evidence_dossier", "sample_pack"): [
        "raw_item_search_tool",
        "claim_verifier_tool",
        "reference_search_tool",
    ],
    ("evidence_dossier", "boundary"): [
        "claim_verifier_tool",
        "reference_search_tool",
        "theory_matcher_tool",
    ],
}

# Explicit static tool ID lists — derived from capability_manifest entrypoint_tool_ids projection.
# These replace the former module-load-time select_runtime_tool_ids() calls so that
# capability_manifest is not invoked on the runtime hot path.
DEEP_REPORT_COORDINATOR_TOOL_IDS: Sequence[str] = (
    "normalize_task",
    "get_corpus_coverage",
    "retrieve_evidence_cards",
    "verify_claim_v2",
    "get_basic_analysis_snapshot",
    "build_agenda_frame_map",
    "extract_actor_positions",
    "build_claim_actor_conflict",
    "build_event_timeline",
    "compute_report_metrics",
    "build_mechanism_summary",
    "detect_risk_signals",
    "build_basic_analysis_insight",
    "judge_decision_utility",
    "get_bertopic_snapshot",
    "build_bertopic_insight",
    "build_section_packet",
    "get_sentiment_analysis_framework",
    "get_sentiment_theories",
    "get_sentiment_case_template",
    "get_youth_sentiment_insight",
    "search_reference_insights",
    "build_event_reference_links",
)

SUBAGENT_TOOL_ID_MAP: Mapping[str, Sequence[str]] = {
    "retrieval_router": ("normalize_task", "get_corpus_coverage"),
    "archive_evidence_organizer": ("retrieve_evidence_cards", "get_basic_analysis_snapshot"),
    "timeline_analyst": ("build_event_timeline", "compute_report_metrics"),
    "stance_conflict": ("extract_actor_positions", "media_coverage_summary_tool"),
    "event_analyst": (
        "retrieve_evidence_cards",
        "build_event_timeline",
        "compute_report_metrics",
        "get_basic_analysis_snapshot",
        "build_basic_analysis_insight",
    ),
    "agenda_frame_builder": ("build_agenda_frame_map",),
    "claim_actor_conflict": ("extract_actor_positions", "build_claim_actor_conflict"),
    "propagation_analyst": (
        "compute_report_metrics",
        "build_mechanism_summary",
        "detect_risk_signals",
        "build_basic_analysis_insight",
        "media_coverage_summary_tool",
    ),
    "bertopic_evolution_analyst": ("get_bertopic_snapshot", "build_bertopic_insight"),
    "decision_utility_judge": ("judge_decision_utility",),
    "validator": ("verify_claim_v2",),
    "writer": (
        "get_sentiment_analysis_framework",
        "get_sentiment_theories",
        "get_sentiment_case_template",
        "search_reference_insights",
        "build_section_packet",
        "build_basic_analysis_insight",
        "build_bertopic_insight",
        "retrieve_evidence_cards",
        "get_report_template",  # 新增：模板读取工具
    ),
}

ANALYSIS_AGENT_TOOL_ID_MAP: Mapping[Tuple[str, str], Sequence[str]] = {
    ("policy_dynamics", "evidence_analyst"): [
        "raw_item_search_tool",
        "temporal_event_window_tool",
        "content_focus_compare_tool",
    ],
    ("public_hotspot", "evidence_analyst"): [
        "raw_item_search_tool",
        "temporal_event_window_tool",
        "content_focus_compare_tool",
    ],
    ("crisis_response", "evidence_analyst"): [
        "raw_item_search_tool",
        "temporal_event_window_tool",
        "content_focus_compare_tool",
    ],
    ("policy_dynamics", "mechanism_analyst"): ["theory_matcher_tool", "reference_search_tool"],
    ("public_hotspot", "mechanism_analyst"): ["theory_matcher_tool", "reference_search_tool"],
    ("crisis_response", "mechanism_analyst"): ["theory_matcher_tool", "reference_search_tool"],
    ("policy_dynamics", "claim_judge"): ["claim_verifier_tool"],
    ("public_hotspot", "claim_judge"): ["claim_verifier_tool"],
    ("crisis_response", "claim_judge"): ["claim_verifier_tool"],
}


def get_report_tool_catalog() -> List[ReportToolSpec]:
    return list(_TOOL_SPECS)


def get_report_tool(tool_id: str) -> BaseTool:
    key = str(tool_id or "").strip()
    if not key or key not in _TOOL_SPEC_BY_ID:
        raise KeyError(f"Unknown report tool id: {tool_id}")
    return _TOOL_SPEC_BY_ID[key].tool


def get_report_tool_spec(tool_id: str) -> ReportToolSpec:
    key = str(tool_id or "").strip()
    if not key or key not in _TOOL_SPEC_BY_ID:
        raise KeyError(f"Unknown report tool id: {tool_id}")
    return _TOOL_SPEC_BY_ID[key]


def iter_report_tool_ids(*, runtime_tag: str = "") -> Iterable[str]:
    tag = str(runtime_tag or "").strip()
    for item in _TOOL_SPECS:
        if tag and tag not in item.runtime_tags:
            continue
        yield item.tool_id


def validate_report_toolset(tools: List[Any]) -> Dict[str, Any]:
    return validate_langchain_toolset(tools)


def validate_skill_tool_ids(
    tool_ids: Sequence[str] | str,
    *,
    available_tool_ids: Sequence[str] | None = None,
    allow_manual: bool = False,
) -> List[str]:
    items = (
        [token for token in str(tool_ids or "").split()]
        if isinstance(tool_ids, str)
        else [str(item or "").strip() for item in (tool_ids or [])]
    )
    normalized: List[str] = []
    seen = set()
    allowed = {str(item or "").strip() for item in (available_tool_ids or []) if str(item or "").strip()}
    for raw in items:
        tool_id = str(raw or "").strip()
        if not tool_id:
            continue
        if tool_id in seen:
            raise ValueError(f"Duplicate skill tool id: {tool_id}")
        if tool_id not in _TOOL_SPEC_BY_ID:
            raise ValueError(f"Unknown skill tool id: {tool_id}")
        spec = _TOOL_SPEC_BY_ID[tool_id]
        if not allow_manual and (spec.mutability != READ_ONLY or RUNTIME_MANUAL_ONLY in spec.runtime_tags):
            raise ValueError(f"Skill tool id is not allowed for autonomous runtime: {tool_id}")
        if allowed and tool_id not in allowed:
            raise ValueError(f"Skill tool id is not available in the target runtime surface: {tool_id}")
        seen.add(tool_id)
        normalized.append(tool_id)
    return normalized


def _resolve_tools(tool_ids: Sequence[str], *, include_manual: bool = False) -> List[BaseTool]:
    selected: List[BaseTool] = []
    for tool_id in tool_ids:
        spec = get_report_tool_spec(tool_id)
        if not include_manual and (spec.mutability != READ_ONLY or RUNTIME_MANUAL_ONLY in spec.runtime_tags):
            continue
        selected.append(spec.tool)
    return selected


def _normalize_template_section_scope(scene_id: str, section_id: str) -> str:
    scene_key = str(scene_id or "").strip()
    section_key = str(section_id or "").strip().lower()
    if not section_key:
        return ""
    if (scene_key, section_key) in SECTION_TOOL_NAME_MAP:
        return section_key
    if scene_key == "policy_dynamics":
        if any(token in section_key for token in ("演变", "脉络", "timeline", "节点")):
            return "evolution"
        if any(token in section_key for token in ("态度", "反应", "焦点", "情绪", "response")):
            return "response"
        if any(token in section_key for token in ("影响", "impact")):
            return "impact"
        if any(token in section_key for token in ("对照", "benchmark")):
            return "benchmark"
        if any(token in section_key for token in ("动作", "应对", "建议", "action")):
            return "action"
    if scene_key == "public_hotspot":
        if any(token in section_key for token in ("传播", "演变", "路径", "脉络", "propagation")):
            return "propagation"
        if any(token in section_key for token in ("焦点", "情绪", "立场", "focus")):
            return "focus"
        if any(token in section_key for token in ("动因", "机制", "mechanism")):
            return "mechanism"
        if any(token in section_key for token in ("动作", "影响", "建议", "action")):
            return "action"
    if scene_key == "crisis_response":
        if any(token in section_key for token in ("事件", "脉络", "timeline", "节点")):
            return "timeline"
        if any(token in section_key for token in ("传播", "扩散", "propagation")):
            return "propagation"
        if any(token in section_key for token in ("风险", "risk")):
            return "risk"
        if any(token in section_key for token in ("响应", "应对", "策略", "action", "response")):
            return "response"
    return section_key


def select_report_tools(
    *,
    runtime_target: str,
    scene_id: str = "",
    section_id: str = "",
    agent_name: str = "",
    include_manual: bool = False,
) -> List[BaseTool]:
    target = str(runtime_target or "").strip()
    if target == "agent_runtime_section":
        section_key = _normalize_template_section_scope(scene_id, section_id)
        scene_key = str(scene_id or "").strip()
        tool_ids = SECTION_TOOL_NAME_MAP.get((scene_key, section_key)) or (DEFAULT_TOOL_NAMES if section_key else [])
        return _resolve_tools(tool_ids, include_manual=include_manual)
    if target == "agent_runtime_analysis":
        pair = (str(scene_id or "").strip(), str(agent_name or "").strip())
        return _resolve_tools(ANALYSIS_AGENT_TOOL_ID_MAP.get(pair, ()), include_manual=include_manual)
    if target == RUNTIME_COORDINATOR:
        return _resolve_tools(DEEP_REPORT_COORDINATOR_TOOL_IDS, include_manual=include_manual)
    if target == RUNTIME_SUBAGENT:
        agent_key = str(agent_name or "").strip()
        return _resolve_tools(SUBAGENT_TOOL_ID_MAP.get(agent_key, ()), include_manual=include_manual)
    if target == RUNTIME_AGENT:
        agent_tool_ids = [s.tool_id for s in _TOOL_SPECS if RUNTIME_AGENT in s.runtime_tags]
        return _resolve_tools(agent_tool_ids, include_manual=include_manual)
    raise ValueError(f"Unsupported report runtime target: {runtime_target}")


def get_report_tool_bundle(scene_id: str, section_id: str) -> List[BaseTool]:
    return select_report_tools(runtime_target="agent_runtime_section", scene_id=scene_id, section_id=section_id)


def get_report_tool_rounds(scene_id: str, section_id: str) -> int:
    scene_key = str(scene_id or "").strip()
    section_key = _normalize_template_section_scope(scene_id, section_id)
    if (scene_key, section_key) in {
        ("policy_dynamics", "evolution"),
        ("public_hotspot", "propagation"),
        ("crisis_response", "timeline"),
        ("crisis_response", "propagation"),
    }:
        return 4
    if (scene_key, section_key) in {
        ("policy_dynamics", "impact"),
        ("policy_dynamics", "action"),
        ("public_hotspot", "mechanism"),
        ("crisis_response", "response"),
    }:
        return 3
    return 2


__all__ = [
    "ANALYSIS_AGENT_TOOL_ID_MAP",
    "DEEP_REPORT_COORDINATOR_TOOL_IDS",
    "DEFAULT_TOOL_NAMES",
    "MANUAL_TOOL",
    "READ_TOOL",
    "READ_ONLY",
    "REPORT_ANALYSIS_TOOLS",
    "RUNTIME_AGENT",
    "RUNTIME_COORDINATOR",
    "RUNTIME_MANUAL_ONLY",
    "RUNTIME_SKILL_ONLY",
    "RUNTIME_SUBAGENT",
    "ReportToolSpec",
    "SECTION_TOOL_NAME_MAP",
    "STATE_MUTATING_TOOL",
    "STATE_MUTATING",
    "SUBAGENT_TOOL_ID_MAP",
    "SYNTHESIS_TOOL",
    "get_report_tool",
    "get_report_tool_bundle",
    "get_report_tool_catalog",
    "get_report_tool_rounds",
    "get_report_tool_spec",
    "iter_report_tool_ids",
    "select_report_tools",
    "validate_report_toolset",
    "validate_skill_tool_ids",
]
