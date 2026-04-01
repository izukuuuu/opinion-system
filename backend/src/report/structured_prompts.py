"""
结构化报告提示词模板。

所有提示词均用于 ``call_langchain_chat(task="report")``，
并要求模型返回严格 JSON 结果，便于后端解析与校验。
"""
from __future__ import annotations

import json
from typing import Any, Dict, List


REPORT_SYSTEM_PROMPT = (
    "你是一名资深舆情分析报告编辑。"
    "请仅基于输入的事实数据进行归纳，不得编造数字或事件。"
    "必须输出合法 JSON，禁止输出 Markdown、解释文字或代码块。"
)


def _json_block(data: Dict[str, Any]) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def build_title_subtitle_prompt(topic: str, facts: Dict[str, Any]) -> str:
    schema = {
        "title": f"{topic}舆情分析报告",
        "subtitle": "一句话总结报告主旨，控制在40字以内",
    }
    return (
        "请基于事实生成报告标题与副标题。\n"
        "要求：\n"
        "1) title 使用正式报告名称；\n"
        "2) subtitle 需覆盖传播节奏或舆情态势；\n"
        "3) 如事实中包含 deep_analysis / methodology_context / reference_snippets / dynamic_theories，可用于增强表达；\n"
        "4) 如事实中包含 legacy_rag_sections 或 legacy_report_text，可用于增强表达；\n"
        "5) 仅输出 JSON。\n\n"
        f"【输出 JSON Schema】\n{_json_block(schema)}\n\n"
        f"【事实数据】\n{_json_block(facts)}"
    )


def build_stage_notes_prompt(facts: Dict[str, Any]) -> str:
    schema = {
        "stageNotes": [
            {
                "title": "阶段名称",
                "range": "起止日期描述",
                "delta": "变化幅度描述",
                "highlight": "2-3句阶段解读，不少于40字",
                "badge": "P1",
            }
        ]
    }
    return (
        "请根据时间趋势生成三段“传播节奏”阶段说明。\n"
        "要求：\n"
        "1) 按时间先后输出 stageNotes；\n"
        "2) badge 固定为 P1/P2/P3；\n"
        "3) 不得杜撰输入中不存在的具体数值；\n"
        "4) 可结合 deep_analysis.keyEvents / deep_analysis.stage / theory_hints 强化阶段解读；\n"
        "5) 可结合 legacy_rag_sections / legacy_report_text 强化阶段解读；\n"
        "6) 仅输出 JSON。\n\n"
        f"【输出 JSON Schema】\n{_json_block(schema)}\n\n"
        f"【事实数据】\n{_json_block(facts)}"
    )


def build_insights_prompt(facts: Dict[str, Any]) -> str:
    fixed_titles: List[str] = ["声量", "趋势", "态度", "关键词", "主题", "建议"]
    schema = {
        "highlight_points": ["洞察亮点1", "洞察亮点2", "洞察亮点3", "洞察亮点4"],
        "insights": [
            {
                "title": fixed_titles[0],
                "headline": "一句话小结",
                "points": ["要点1", "要点2", "要点3"],
            }
        ],
    }
    return (
        "请根据事实输出“洞察亮点”和“重点结论卡片”。\n"
        "要求：\n"
        "1) insights 必须包含且仅包含 6 张卡片，title 固定为："
        + "、".join(fixed_titles)
        + "；\n"
        "2) 每张卡片 points 建议 3-5 条；\n"
        "3) 建议类内容应可执行且避免空话；\n"
        "4) deep_analysis / methodology_context / reference_snippets / expert_notes 可作为研判背景；\n"
        "5) legacy_rag_sections / legacy_report_text 可作为证据性背景；\n"
        "6) 仅输出 JSON。\n\n"
        f"【输出 JSON Schema】\n{_json_block(schema)}\n\n"
        f"【事实数据】\n{_json_block(facts)}"
    )


def build_bertopic_insight_prompt(facts: Dict[str, Any]) -> str:
    schema = {
        "insight_markdown": "面向业务方的BERTopic主题演化解读，使用2-4段中文Markdown，允许使用小标题与加粗。",
    }
    return (
        "请基于 BERTopic 时间线事实生成“核心关注点随时间的变化”解读。\n"
        "要求：\n"
        "1) 明确描述关注焦点如何迁移，不要逐日流水账；\n"
        "2) 点出长期主题与爆发主题，并结合时间节点解释原因；\n"
        "3) 仅基于输入事实，不得编造日期、数量或事件；\n"
        "4) deep_analysis 与 theory_hints 可作为背景，但仍要以 BERTopic 时序事实为核心；\n"
        "5) 输出语言口语化但专业，避免空话；\n"
        "6) 只输出 JSON。\n\n"
        f"【输出 JSON Schema】\n{_json_block(schema)}\n\n"
        f"【事实数据】\n{_json_block(facts)}"
    )


def build_bertopic_temporal_narrative_prompt(facts: Dict[str, Any]) -> str:
    schema = {
        "summary": "1段中文摘要，80-140字，说明主题焦点如何沿时间迁移。",
        "shiftSignals": ["迁移信号1", "迁移信号2", "迁移信号3"],
        "watchpoints": ["提醒1", "提醒2"],
    }
    return (
        "请基于 BERTopic 时序事实生成一层更结构化的报告解读。\n"
        "要求：\n"
        "1) summary 要概括时间主线、主导主题与变化方式；\n"
        "2) shiftSignals 聚焦“何时发生切换、由什么主题切到什么主题、强度如何”；\n"
        "3) watchpoints 聚焦覆盖范围、主题集中度、异常峰值等提醒；\n"
        "4) 可吸收 deep_analysis / methodology_context 的风险视角，但不得脱离 BERTopic 事实；\n"
        "5) 不得编造输入中不存在的日期、数量或事件；\n"
        "6) 仅输出 JSON。\n\n"
        f"【输出 JSON Schema】\n{_json_block(schema)}\n\n"
        f"【事实数据】\n{_json_block(facts)}"
    )


def build_interpretation_prompt(facts: Dict[str, Any]) -> str:
    schema = {
        "narrativeSummary": "100-220字，概括事件如何演变、关键转折点、整体舆论态势。",
        "keyEvents": ["最多5条，提炼阶段性节点或关键进展。"],
        "keyRisks": ["最多5条，提炼传播风险、治理风险或声誉风险。"],
        "eventType": "事件类型，例如品牌危机/突发事故/公共政策/社会事件等。",
        "domain": "所属领域，例如教育/汽车/餐饮/互联网/民生等。",
        "stage": "当前舆情阶段，例如爆发期/扩散期/对抗期/回落期。",
        "indicatorDimensions": ["建议 4-6 条，如 count/sentiment/channel/theme/timeline/actor。"],
        "theoryNames": ["最多3条，优先从 methodology_context 或 theory_hints 中选择。"],
    }
    return (
        "请基于事实与方法论上下文，生成一份结构化“解释与研判”JSON。\n"
        "要求：\n"
        "1) narrativeSummary 要形成完整叙事骨架，不得只罗列数据；\n"
        "2) keyEvents 与 keyRisks 必须与 metrics / timeline / sentiment / themes 一致；\n"
        "3) eventType / domain / stage 可以谨慎归纳，但不得脱离 topic 与事实；\n"
        "4) indicatorDimensions 至少给出 4 条，体现后续应持续观察的分析维度；\n"
        "5) theoryNames 优先使用 methodology_context、dynamic_theories、theory_hints、reference_snippets 中真实可映射的理论；\n"
        "6) 如参考资料中存在 expert_notes，可吸收其中的研判视角，但不得把外部线索当成事实本身；\n"
        "7) 如存在 reference_links，只能把它们视为进一步核验入口，不得凭链接内容编造新事实；\n"
        "8) 仅输出 JSON。\n\n"
        f"【输出 JSON Schema】\n{_json_block(schema)}\n\n"
        f"【事实与上下文】\n{_json_block(facts)}"
    )
