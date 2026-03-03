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
        "3) 如事实中包含 legacy_rag_sections 或 legacy_report_text，可用于增强表达；\n"
        "4) 仅输出 JSON。\n\n"
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
        "4) 可结合 legacy_rag_sections / legacy_report_text 强化阶段解读；\n"
        "5) 仅输出 JSON。\n\n"
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
        "4) legacy_rag_sections / legacy_report_text 可作为证据性背景；\n"
        "5) 仅输出 JSON。\n\n"
        f"【输出 JSON Schema】\n{_json_block(schema)}\n\n"
        f"【事实数据】\n{_json_block(facts)}"
    )
