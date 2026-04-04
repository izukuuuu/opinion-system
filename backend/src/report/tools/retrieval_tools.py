from __future__ import annotations

import json

from langchain.tools import tool

from ..evidence_retriever import (
    analyze_temporal_event_window,
    compare_content_focus,
    search_raw_records,
    verify_claim_with_records,
)
from .common import as_int, safe_json_loads_list, to_clean_list


@tool
def raw_item_search_tool(
    topic_identifier: str,
    start: str,
    end: str,
    query: str,
    entities_json: str = "[]",
    platforms_json: str = "[]",
    time_start: str = "",
    time_end: str = "",
    top_k: int = 12,
) -> str:
    """
    按时间窗、平台和查询词回查原始舆情条目。
    适合围绕某个事件、场景或传播表达抓取代表性样本。
    """
    payload = search_raw_records(
        topic_identifier=str(topic_identifier or "").strip(),
        start=str(start or "").strip(),
        end=str(end or "").strip(),
        query=str(query or "").strip(),
        entities=to_clean_list(entities_json),
        platforms=to_clean_list(platforms_json),
        time_start=str(time_start or "").strip(),
        time_end=str(time_end or "").strip(),
        top_k=as_int(top_k, 12),
    )
    return json.dumps(payload, ensure_ascii=False, indent=2)


@tool
def temporal_event_window_tool(
    topic_identifier: str,
    start: str,
    end: str,
    anchor_date: str,
    query: str = "",
    entities_json: str = "[]",
    platforms_json: str = "[]",
    window_days: int = 7,
    top_k: int = 6,
) -> str:
    """
    围绕时间锚点比较前后窗口的传播内容与强度变化。
    适合核查峰值、引爆点和主题切换是否存在同步关系。
    """
    payload = analyze_temporal_event_window(
        topic_identifier=str(topic_identifier or "").strip(),
        start=str(start or "").strip(),
        end=str(end or "").strip(),
        anchor_date=str(anchor_date or "").strip(),
        query=str(query or "").strip(),
        entities=to_clean_list(entities_json),
        platforms=to_clean_list(platforms_json),
        window_days=as_int(window_days, 7),
        top_k=as_int(top_k, 6),
    )
    return json.dumps(payload, ensure_ascii=False, indent=2)


@tool
def content_focus_compare_tool(
    topic_identifier: str,
    start: str,
    end: str,
    bucket_a_label: str,
    bucket_a_terms_json: str,
    bucket_b_label: str,
    bucket_b_terms_json: str,
    query: str = "",
    entities_json: str = "[]",
    platforms_json: str = "[]",
    time_start: str = "",
    time_end: str = "",
    top_k: int = 8,
) -> str:
    """
    比较两组语义焦点在当前样本中的占优程度。
    适合判断讨论是更偏场景冲突、制度条文、生活实操还是其他内容桶。
    """
    payload = compare_content_focus(
        topic_identifier=str(topic_identifier or "").strip(),
        start=str(start or "").strip(),
        end=str(end or "").strip(),
        bucket_a_terms=to_clean_list(bucket_a_terms_json, max_items=14),
        bucket_b_terms=to_clean_list(bucket_b_terms_json, max_items=14),
        query=str(query or "").strip(),
        entities=to_clean_list(entities_json, max_items=10),
        platforms=to_clean_list(platforms_json, max_items=10),
        time_start=str(time_start or "").strip(),
        time_end=str(time_end or "").strip(),
        top_k=as_int(top_k, 8),
    )
    payload["bucket_a"]["label"] = str(bucket_a_label or "bucket_a").strip() or "bucket_a"
    payload["bucket_b"]["label"] = str(bucket_b_label or "bucket_b").strip() or "bucket_b"
    return json.dumps(payload, ensure_ascii=False, indent=2)


@tool
def claim_verifier_tool(
    topic_identifier: str,
    start: str,
    end: str,
    claim: str,
    entities_json: str = "[]",
    platforms_json: str = "[]",
    retrieve_mode: str = "claim_verification",
    top_k: int = 20,
) -> str:
    """
    面向报告验证的条目级证据检索工具。
    用于针对结构化断言回查原始条目，输出支持项、冲突项、代表性片段和验证状态。
    """
    entities = safe_json_loads_list(entities_json)
    platforms = safe_json_loads_list(platforms_json)
    payload = verify_claim_with_records(
        topic_identifier=str(topic_identifier or "").strip(),
        start=str(start or "").strip(),
        end=str(end or "").strip(),
        claim=str(claim or "").strip(),
        entities=[str(item).strip() for item in entities if str(item or "").strip()],
        platforms=[str(item).strip() for item in platforms if str(item or "").strip()],
        retrieve_mode=str(retrieve_mode or "claim_verification").strip(),
        top_k=as_int(top_k, 20),
    )
    return json.dumps(payload, ensure_ascii=False, indent=2)
