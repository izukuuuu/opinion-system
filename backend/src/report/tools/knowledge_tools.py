from __future__ import annotations

import json

from langchain.tools import tool

from ..knowledge_loader import (
    build_report_reference_links,
    load_report_expert_notes,
    load_report_knowledge,
    search_report_reference_insights,
)
from .common import as_float, as_int, to_clean_list


@tool
def reference_search_tool(query: str, limit: int = 6) -> str:
    """
    搜索 Sona 舆情智库中的事件定向参考片段、外部检索链接与专家笔记。
    适用于需要补充案例、评论、理论片段或人工研判时。
    """
    safe_limit = max(1, min(int(limit or 6), 8))
    refs = search_report_reference_insights(query, limit=safe_limit)
    links = build_report_reference_links(query)
    expert_notes = load_report_expert_notes(query, limit=4)
    payload = {
        "query": str(query or "").strip(),
        "reference_snippets": refs[:safe_limit],
        "reference_links": links[:4],
        "expert_notes": expert_notes[:4],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


@tool
def theory_matcher_tool(topic: str, event_type: str = "", stage: str = "") -> str:
    """
    根据专题、事件类型和阶段匹配更合适的舆情理论锚点。
    返回理论名称与匹配原因，用于增强解释与研判。
    """
    topic_text = str(topic or "").strip()
    knowledge = load_report_knowledge(topic_text)
    theory_names = [
        str(item).strip()
        for item in (knowledge.get("dynamicTheories") or knowledge.get("theoryHints") or [])
        if str(item or "").strip()
    ]

    reasons = []
    if str(stage or "").strip():
        reasons.append(f"当前阶段为 {str(stage).strip()}，优先关注生命周期与阶段转换。")
    if "危机" in str(event_type or "") or "事故" in str(event_type or ""):
        reasons.append("事件具备风险扩散特征，优先关注风险传播与框架竞争。")
    if not reasons:
        reasons.append("理论基于专题关键词与舆情智库动态匹配。")

    payload = {
        "topic": topic_text,
        "event_type": str(event_type or "").strip(),
        "stage": str(stage or "").strip(),
        "theory_names": theory_names[:4],
        "reasoning": reasons,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


@tool
def policy_document_lookup_tool(
    topic: str,
    document_query: str = "",
    entity_terms_json: str = "[]",
    limit: int = 6,
) -> str:
    """
    检索政策文本、法规名称、发布主体及外部核验入口。
    适合核查“某通知/条例是否存在、是否被持续解读、是否能追溯到公开来源”。
    """
    safe_limit = max(1, min(as_int(limit, 6), 8))
    topic_text = str(topic or "").strip()
    query_terms = to_clean_list(entity_terms_json, max_items=10)
    search_query = " ".join(
        item
        for item in [str(document_query or "").strip(), topic_text, *query_terms]
        if str(item or "").strip()
    ).strip() or topic_text
    refs = search_report_reference_insights(search_query, limit=safe_limit)
    links = build_report_reference_links(search_query)
    documents = []
    for item in refs[:safe_limit]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        snippet = str(item.get("snippet") or "").strip()
        source = str(item.get("source") or "").strip()
        if not (title or snippet):
            continue
        documents.append(
            {
                "title": title,
                "source": source,
                "snippet": snippet,
                "score": as_float(item.get("score"), 0.0),
            }
        )
    verification_status = "supported" if documents else "unverified"
    payload = {
        "topic": topic_text,
        "search_query": search_query,
        "entity_terms": query_terms,
        "documents": documents,
        "reference_links": links[:4],
        "verification_status": verification_status,
        "missing_fields": [] if documents else ["official_document"],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)
