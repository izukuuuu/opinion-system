from __future__ import annotations

from .decision_tools import recommendation_tool, risk_assessment_tool
from .knowledge_tools import policy_document_lookup_tool, reference_search_tool, theory_matcher_tool
from .retrieval_tools import (
    claim_verifier_tool,
    content_focus_compare_tool,
    raw_item_search_tool,
    temporal_event_window_tool,
)


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
]

TOOL_BY_NAME = {
    str(getattr(tool, "name", "") or "").strip(): tool
    for tool in REPORT_ANALYSIS_TOOLS
    if str(getattr(tool, "name", "") or "").strip()
}

DEFAULT_TOOL_NAMES = [
    "reference_search_tool",
    "theory_matcher_tool",
    "claim_verifier_tool",
]

SECTION_TOOL_NAME_MAP = {
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


def get_report_tool_bundle(scene_id: str, section_id: str):
    scene_key = str(scene_id or "").strip()
    section_key = str(section_id or "").strip()
    names = SECTION_TOOL_NAME_MAP.get((scene_key, section_key)) or (DEFAULT_TOOL_NAMES if section_key else [])
    return [tool for name in names if name in TOOL_BY_NAME for tool in [TOOL_BY_NAME[name]]]


def get_report_tool_rounds(scene_id: str, section_id: str) -> int:
    scene_key = str(scene_id or "").strip()
    section_key = str(section_id or "").strip()
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
