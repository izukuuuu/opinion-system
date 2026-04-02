from __future__ import annotations

from typing import Any, Dict, List


SONA_FEATURE_ANALYSIS_TOOL_NAMES: List[str] = [
    "get_sentiment_analysis_framework",
    "get_sentiment_theories",
    "get_sentiment_case_template",
    "get_youth_sentiment_insight",
    "search_reference_insights",
    "build_event_reference_links",
    "append_expert_judgement",
]


def load_sona_feature_analysis_skill(topic: str = "") -> Dict[str, Any]:
    topic_text = str(topic or "").strip()
    return {
        "name": "sona_feature_analysis",
        "displayName": "Sona 舆情深度分析 Skill",
        "topic": topic_text,
        "goal": "将报告生成从单轮文案补全提升为带方法论约束的分段研判。",
        "reasoningStyle": [
            "先判断事件所处生命周期，再解释传播动力与风险迁移。",
            "优先识别议程设置、框架竞争、风险传播与情绪放大机制。",
            "每一段都要给出主线判断、事实依据和写作边界，不直接堆砌统计结果。",
        ],
        "sectionGuidance": {
            "deep_analysis": "聚焦事件类型、领域、阶段、关键节点、核心风险与理论锚点。",
            "bertopic_insight": "聚焦主题如何沿时间迁移，哪些主题是背景常量，哪些是爆发变量。",
            "bertopic_temporal_narrative": "聚焦切换信号、覆盖率风险、集中度变化与异常峰值提醒。",
            "stage_notes": "聚焦传播阶段划分、每一段的触发因素、节奏变化和治理重点。",
            "insights": "聚焦业务方可执行的结论压缩，避免空泛建议。",
            "title_subtitle": "聚焦整份报告的主线、态势和风险重点，表达要克制准确。",
        },
        "toolNames": SONA_FEATURE_ANALYSIS_TOOL_NAMES,
        "constraints": [
            "不得把外部检索入口或专家笔记直接写成已验证事实。",
            "不得脱离时间线、情感、主题和渠道分布进行空泛总结。",
            "结论优先服务于传播研判和处置建议，而不是单纯做数据复述。",
        ],
    }
