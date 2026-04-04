from __future__ import annotations

import json
from typing import Any, Dict, List

from langchain.tools import tool

from .common import as_int, safe_json_loads, safe_json_loads_list


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
    metrics = safe_json_loads(metrics_json)
    sentiment = safe_json_loads(sentiment_json)
    content_split = safe_json_loads(content_split_json)
    timeline = safe_json_loads_list(timeline_json)

    total_sentiment = max(
        1,
        as_int(sentiment.get("positive")) + as_int(sentiment.get("neutral")) + as_int(sentiment.get("negative")),
    )
    negative_rate = as_int(sentiment.get("negative")) / total_sentiment
    content_total = max(1, as_int(content_split.get("factual")) + as_int(content_split.get("opinion")))
    opinion_ratio = as_int(content_split.get("opinion")) / content_total
    total_volume = as_int(metrics.get("totalVolume"))
    peak_value = as_int((metrics.get("peak") or {}).get("value") if isinstance(metrics.get("peak"), dict) else 0)

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
        first_value = as_int((timeline[0] or {}).get("value") if isinstance(timeline[0], dict) else 0)
        last_value = as_int((timeline[-1] or {}).get("value") if isinstance(timeline[-1], dict) else 0)
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
    risks_payload = safe_json_loads(risks_json)
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
