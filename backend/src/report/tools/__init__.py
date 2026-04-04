"""
Lazy exports for report tools.

Keeping this package lazy avoids circular imports between ``knowledge_loader``
and the tool modules that consume it.
"""
from __future__ import annotations

from importlib import import_module
from typing import Any, Dict, Tuple


_EXPORT_MAP: Dict[str, Tuple[str, str]] = {
    "REPORT_ANALYSIS_TOOLS": (".registry", "REPORT_ANALYSIS_TOOLS"),
    "get_report_tool_bundle": (".registry", "get_report_tool_bundle"),
    "get_report_tool_rounds": (".registry", "get_report_tool_rounds"),
    "ensure_langchain_toolset_valid": (".validation", "ensure_langchain_toolset_valid"),
    "validate_langchain_toolset": (".validation", "validate_langchain_toolset"),
    "recommendation_tool": (".decision_tools", "recommendation_tool"),
    "risk_assessment_tool": (".decision_tools", "risk_assessment_tool"),
    "policy_document_lookup_tool": (".knowledge_tools", "policy_document_lookup_tool"),
    "reference_search_tool": (".knowledge_tools", "reference_search_tool"),
    "theory_matcher_tool": (".knowledge_tools", "theory_matcher_tool"),
    "claim_verifier_tool": (".retrieval_tools", "claim_verifier_tool"),
    "content_focus_compare_tool": (".retrieval_tools", "content_focus_compare_tool"),
    "raw_item_search_tool": (".retrieval_tools", "raw_item_search_tool"),
    "temporal_event_window_tool": (".retrieval_tools", "temporal_event_window_tool"),
    "append_expert_judgement": (".knowledge_base_tools", "append_expert_judgement"),
    "build_event_reference_links": (".knowledge_base_tools", "build_event_reference_links"),
    "get_sentiment_analysis_framework": (".knowledge_base_tools", "get_sentiment_analysis_framework"),
    "get_sentiment_case_template": (".knowledge_base_tools", "get_sentiment_case_template"),
    "get_sentiment_theories": (".knowledge_base_tools", "get_sentiment_theories"),
    "get_youth_sentiment_insight": (".knowledge_base_tools", "get_youth_sentiment_insight"),
    "load_sentiment_knowledge": (".knowledge_base_tools", "load_sentiment_knowledge"),
    "search_reference_insights": (".knowledge_base_tools", "search_reference_insights"),
}

__all__ = sorted(_EXPORT_MAP)


def __getattr__(name: str) -> Any:
    target = _EXPORT_MAP.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = target
    module = import_module(module_name, __name__)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value

