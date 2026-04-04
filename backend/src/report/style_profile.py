from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict


STYLE_PROFILES: Dict[str, Dict[str, Any]] = {
    "analysis_report": {
        "name": "analysis_report",
        "document_label": "分析报告",
        "system_prompt_hint": "文书体裁、章节组织、图示标题与语气以 style_profile 为准，不预设唯一文书类型。",
        "fallback_tone_notes": [
            "事实先行，判断克制，解释充分，表达可读。",
            "一段只承担一种主要功能，避免把走势、原因、风险和建议堆进同一段。",
            "证据不足时保留不确定性，不用流畅措辞掩盖事实空缺。",
        ],
        "fallback_sections": [
            {"id": "summary", "title": "摘要", "goal": "概括核心判断与主要边界。"},
            {"id": "analysis", "title": "分析正文", "goal": "展开机制、结构与阶段变化。"},
            {"id": "risk", "title": "风险与边界", "goal": "说明风险项、证据边界与待核验点。"},
            {"id": "action", "title": "建议与条件", "goal": "提出动作建议并交代执行条件。"},
        ],
        "asset_labels": {
            "visual_section_title": "附图",
            "cover": {"title": "封面摘要图", "description": "自动摘要卡片", "badge": "完整稿"},
            "timeline": {"title": "时间趋势图", "description": "时间线走势"},
            "sentiment": {"title": "情绪结构图", "description": "情绪占比"},
            "channels": {"title": "渠道分布图", "description": "头部渠道横向对比"},
            "themes": {"title": "核心议题图", "description": "主题标签插图"},
            "cover_metrics": {
                "range": "时间区间",
                "volume": "总声量",
                "peak": "峰值节点",
                "stage": "当前阶段",
                "event_type": "事件类型",
            },
        },
        "events": {
            "phase_write_title": "完整文本编排",
            "phase_write_message": "正在整合结构化结果、方法论上下文与证据边界。",
            "integrator_started_title": "Integrator 已启动",
            "integrator_started_message": "正在组装完整文本写作 brief。",
            "integrator_memo_title": "Integrator 公开备忘录",
            "integrator_memo_message": "写作 brief 已生成，开始进入正文草拟。",
            "phase_review_title": "完整文本修订",
            "phase_review_message": "正在压缩重复表述并强化证据边界。",
            "writer_started_title": "Writer 已启动",
            "writer_started_message": "正在生成 Markdown 正文草稿。",
            "writer_memo_title": "Writer 公开备忘录",
            "writer_memo_message": "正文草稿已生成，开始进行 revise 收口。",
            "reviser_started_title": "Reviser 已启动",
            "reviser_started_message": "正在对 Markdown 文本进行 revise。",
            "reviser_memo_title": "Reviser 公开备忘录",
            "reviser_memo_message": "Markdown 文本已完成 revise，并自动插入图示。",
            "artifact_title": "完整文本已写入",
            "artifact_message": "Markdown 正文和自动图示已写入缓存。",
        },
    },
    "monitor_brief": {
        "name": "monitor_brief",
        "document_label": "监测简报",
        "system_prompt_hint": "文书应偏向简报体，突出异常、节点与待跟进事项。",
        "fallback_tone_notes": [
            "优先呈现异常点、关键转折和待跟进事项。",
            "篇幅紧凑，不展开过多理论解释。",
            "结论强度服从证据强度，不预设治理建议。",
        ],
        "fallback_sections": [
            {"id": "summary", "title": "简报摘要", "goal": "概括本期最重要变化。"},
            {"id": "analysis", "title": "监测发现", "goal": "说明关键节点、结构变化与异常项。"},
            {"id": "risk", "title": "待跟进事项", "goal": "列出风险与需继续观测的问题。"},
        ],
    },
    "evidence_digest": {
        "name": "evidence_digest",
        "document_label": "证据汇编",
        "system_prompt_hint": "文书应偏向证据整理，不主动扩写强判断或处置建议。",
        "fallback_tone_notes": [
            "以证据归纳和边界说明为主，不主动拔高判断强度。",
            "优先保留统计口径、样本范围和代表性条目语义。",
            "避免把相关性材料直接上升为因果结论。",
        ],
        "fallback_sections": [
            {"id": "summary", "title": "证据概览", "goal": "概括当前证据可支撑的判断。"},
            {"id": "analysis", "title": "证据整理", "goal": "按主题、阶段或主体整理关键材料。"},
            {"id": "risk", "title": "证据边界", "goal": "说明证据不足与待核验点。"},
        ],
    },
}


def load_full_report_style_profile(document_type: str | None = None) -> Dict[str, Any]:
    key = str(document_type or "").strip() or "analysis_report"
    profile = STYLE_PROFILES.get(key) or STYLE_PROFILES["analysis_report"]
    return deepcopy(profile)
