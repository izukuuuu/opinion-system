"""
Report-scoped LangChain tools.

These tools are intentionally narrower than Sona's full agent toolbox. The goal
is to give the structured report pipeline a controlled set of high-value helper
tools without converting the whole report service into an open-ended agent.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List

from langchain_core.tools import tool

from ..knowledge_loader import (
    build_report_reference_links,
    get_dynamic_theories,
    load_report_expert_notes,
    load_report_knowledge,
    search_report_reference_insights,
)


def _safe_json_loads(raw: str) -> Dict[str, Any]:
    try:
        value = json.loads(str(raw or ""))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _safe_json_loads_list(raw: str) -> List[Any]:
    try:
        value = json.loads(str(raw or ""))
    except Exception:
        return []
    return value if isinstance(value, list) else []


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except Exception:
        return default


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

    reasons: List[str] = []
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
def risk_assessment_tool(
    topic: str,
    metrics_json: str,
    timeline_json: str,
    sentiment_json: str,
    content_split_json: str,
) -> str:
    """
    基于结构化统计结果输出风险评估摘要。
    适合在深度分析前先快速形成风险排序。
    """
    metrics = _safe_json_loads(metrics_json)
    sentiment = _safe_json_loads(sentiment_json)
    content_split = _safe_json_loads(content_split_json)
    timeline = _safe_json_loads_list(timeline_json)

    total_sentiment = max(
        1,
        _as_int(sentiment.get("positive")) + _as_int(sentiment.get("neutral")) + _as_int(sentiment.get("negative")),
    )
    negative_rate = _as_int(sentiment.get("negative")) / total_sentiment
    content_total = max(1, _as_int(content_split.get("factual")) + _as_int(content_split.get("opinion")))
    opinion_ratio = _as_int(content_split.get("opinion")) / content_total
    total_volume = _as_int(metrics.get("totalVolume"))
    peak_value = _as_int((metrics.get("peak") or {}).get("value") if isinstance(metrics.get("peak"), dict) else 0)

    risks: List[Dict[str, Any]] = []
    if negative_rate >= 0.35:
        risks.append(
            {
                "risk": "情绪对立升级",
                "level": "high",
                "reason": f"负向占比约 {round(negative_rate * 100, 1)}%，已具备显著对立情绪扩散条件。",
            }
        )
    if opinion_ratio >= 0.45:
        risks.append(
            {
                "risk": "议题泛化",
                "level": "high" if opinion_ratio >= 0.6 else "medium",
                "reason": f"观点类内容占比约 {round(opinion_ratio * 100, 1)}%，讨论可能从事实层转向立场竞争。",
            }
        )
    if total_volume > 0 and peak_value > 0 and peak_value / max(1, total_volume) >= 0.35:
        risks.append(
            {
                "risk": "单点爆发依赖",
                "level": "medium",
                "reason": "峰值声量集中在少数节点，舆论对关键事件触发高度敏感。",
            }
        )
    if isinstance(timeline, list) and len(timeline) >= 3:
        first_value = _as_int((timeline[0] or {}).get("value") if isinstance(timeline[0], dict) else 0)
        last_value = _as_int((timeline[-1] or {}).get("value") if isinstance(timeline[-1], dict) else 0)
        if first_value > 0 and last_value >= first_value * 1.5:
            risks.append(
                {
                    "risk": "扩散未收敛",
                    "level": "medium",
                    "reason": "尾部声量仍高于起始水平，说明讨论尚未真正回落。",
                }
            )
    if not risks:
        risks.append(
            {
                "risk": "长尾外溢",
                "level": "medium",
                "reason": "当前显性指标未极端恶化，但仍需关注次生议题和观点扩散。",
            }
        )

    payload = {
        "topic": str(topic or "").strip(),
        "risks": risks[:4],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


@tool
def recommendation_tool(topic: str, risks_json: str, stage: str = "", event_type: str = "") -> str:
    """
    根据风险评估结果生成操作性建议。
    适合在结论卡片和建议部分引用。
    """
    risks_payload = _safe_json_loads(risks_json)
    risks = risks_payload.get("risks") if isinstance(risks_payload.get("risks"), list) else []
    actions: List[str] = []

    for item in risks[:4]:
        if not isinstance(item, dict):
            continue
        risk_name = str(item.get("risk") or "").strip()
        if "情绪对立" in risk_name:
            actions.append("优先统一口径并缩短回应周期，避免情绪主导议程。")
        elif "议题泛化" in risk_name:
            actions.append("围绕核心争议建立问答与澄清素材，压缩次生议题扩散空间。")
        elif "扩散未收敛" in risk_name:
            actions.append("持续监测头部平台和高频词簇，避免误判为已回落。")
        else:
            actions.append("针对高互动样本补充证据链，增强回应与复盘的可信度。")

    if str(stage or "").strip():
        actions.append(f"当前处于{str(stage).strip()}，建议按阶段设置差异化沟通策略。")
    if "危机" in str(event_type or "").strip():
        actions.append("建议同步准备责任回应、事实澄清和后续修复三条线。")
    if not actions:
        actions.append("建议围绕渠道、情绪和主题迁移建立分层响应机制。")

    payload = {
        "topic": str(topic or "").strip(),
        "recommendations": actions[:5],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2)


REPORT_ANALYSIS_TOOLS = [
    reference_search_tool,
    theory_matcher_tool,
    risk_assessment_tool,
    recommendation_tool,
]
