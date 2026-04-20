from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List


SCENE_PROFILES: Dict[str, Dict[str, Any]] = {
    "routine_monitoring": {
        "scene_id": "routine_monitoring",
        "scene_label": "日常监测场景",
        "reference_template_name": "日常或定期舆情监测报告模板",
        "reference_template": "日常或定期舆情监测报告模板",
        "description": "适合周报、月报和持续跟踪型任务，重点是异常点、趋势变化、渠道表现与后续关注项。",
        "supported_document_types": ["analysis_report", "monitor_brief"],
        "selection_hints": ["监测", "周报", "月报", "周期", "跟踪", "简报", "波动", "预警"],
        "keyword_hints": ["监测", "周报", "月报", "周期", "跟踪", "简报", "波动", "预警"],
        "layout_focus": [
            "先概览，再展开趋势、节点和待跟进事项。",
            "优先保留异常波动、平台迁移和新增话题。",
            "建议只保留监测和跟进动作，不主动拔高为强处置方案。",
        ],
        "hero_focus": ["本期核心变化", "异常节点", "后续关注点"],
        "recommendation_policy": "仅允许跟进和监测类建议，不主动扩写重处置方案。",
        "analysis_path": ["scene_router", "evidence_analyst", "mechanism_analyst", "claim_judge", "risk_mapper", "analysis_supervisor"],
        "writing_path": ["layout_planner", "budget_planner", "section_writer", "style_critic", "fact_critic", "report_editor"],
        "default_total_words": 1800,
        "budget_weights": {
            "summary": 0.16,
            "trend": 0.2,
            "timeline": 0.16,
            "topics": 0.16,
            "channels": 0.14,
            "risk": 0.18,
        },
        "section_blueprint": [
            {"id": "summary", "title": "本期摘要", "goal": "概括本期最重要的变化、异常点和整体边界。"},
            {"id": "trend", "title": "趋势变化", "goal": "说明声量、情绪和节奏变化，不做流水账。"},
            {"id": "timeline", "title": "关键节点", "goal": "提炼阶段节点与异常时段的传播线索。"},
            {"id": "topics", "title": "热点话题", "goal": "交代核心话题、新增话题与关注迁移。"},
            {"id": "channels", "title": "渠道表现", "goal": "说明平台分布、传播阵地与内容形态变化。"},
            {"id": "risk", "title": "风险与跟进", "goal": "列出风险点和下一周期需要继续观察的问题。"},
        ],
    },
    "public_hotspot": {
        "scene_id": "public_hotspot",
        "scene_label": "公共热点场景",
        "reference_template_name": "社会公共热点事件分析报告模板",
        "reference_template": "社会公共热点事件分析报告模板",
        "description": "适合社会热点、公共议题和讨论扩散类任务，重点是演变脉络、传播链、观点分化与社会情绪。",
        "supported_document_types": ["analysis_report", "monitor_brief"],
        "selection_hints": ["热点", "公共", "社会", "争议", "讨论", "舆论", "话题", "事件"],
        "keyword_hints": ["热点", "公共", "社会", "争议", "讨论", "舆论", "话题", "事件"],
        "layout_focus": [
            "开头先定性当前热点的矛盾点和传播状态。",
            "中段重点写传播路径、核心议题与情绪分化。",
            "结尾回到影响判断和条件性动作，不直接写成固定治理方案。",
        ],
        "hero_focus": ["事件定性", "核心转折", "传播路径"],
        "recommendation_policy": "允许输出条件性影响判断和动作建议，但需区分已验证风险与待观察风险。",
        "analysis_path": ["scene_router", "evidence_analyst", "mechanism_analyst", "claim_judge", "risk_mapper", "analysis_supervisor"],
        "writing_path": ["layout_planner", "budget_planner", "section_writer", "style_critic", "fact_critic", "report_editor"],
        "default_total_words": 2600,
        "budget_weights": {
            "summary": 0.12,
            "evolution": 0.18,
            "propagation": 0.18,
            "focus": 0.18,
            "mechanism": 0.18,
            "action": 0.16,
        },
        "section_blueprint": [
            {"id": "summary", "title": "摘要", "goal": "概括事件定性、关键判断与主要边界。"},
            {"id": "evolution", "title": "事件演变", "goal": "说明背景、发酵脉络与当前态势。"},
            {"id": "propagation", "title": "传播路径", "goal": "分析传播链条、引爆节点与关键主体。"},
            {"id": "focus", "title": "核心焦点与情绪", "goal": "拆解议题重心、多方观点与情绪结构。"},
            {"id": "mechanism", "title": "深层动因", "goal": "解释传播动力、结构失衡与价值冲突。"},
            {"id": "action", "title": "影响与动作", "goal": "给出风险影响与有条件的动作建议。"},
        ],
    },
    "policy_dynamics": {
        "scene_id": "policy_dynamics",
        "scene_label": "政策行业场景",
        "reference_template_name": "特定政策或行业动态舆情分析报告模板",
        "reference_template": "特定政策或行业动态舆情分析报告模板",
        "description": "适合政策发布、监管动态、行业趋势变动类任务，重点是按时间节点梳理讨论对象如何迁移，再展开传播演变、舆论反应与影响传导。",
        "supported_document_types": ["analysis_report", "monitor_brief"],
        "selection_hints": ["政策", "新规", "规定", "条例", "通知", "行业", "监管", "发布"],
        "keyword_hints": ["政策", "新规", "规定", "条例", "通知", "行业", "监管", "发布"],
        "layout_focus": [
            "摘要采用“总判断句 + 演化句”结构，不承担样本边界、风险分项和对策建议。",
            "摘要主轴最多三个且必须同层，事件锚点按月份单向推进，不超过四个。",
            "事件脉络与传播演变必须从时间节点直接起笔，不写“先校正时间锚点”或泛背景说明。",
            "每一段只回答这个节点把讨论对象从哪里推到了哪里，不把多个判断挤在同一段。",
            "禁止把下一年度的通过、施行、结果性事实倒灌到当前年度脉络中。",
            "传播分析要区分媒体解读、用户实操讨论与场景化冲突。",
            "影响判断应区分已验证影响、预期影响和待观察影响。",
        ],
        "hero_focus": ["核心影响", "舆论反应", "趋势预判"],
        "recommendation_policy": "允许趋势和应对建议，但必须区分已验证影响、预期影响和待观察影响。",
        "analysis_path": ["scene_router", "evidence_analyst", "mechanism_analyst", "claim_judge", "risk_mapper", "analysis_supervisor"],
        "writing_path": ["layout_planner", "budget_planner", "section_writer", "style_critic", "fact_critic", "report_editor"],
        "default_total_words": 2500,
        "budget_weights": {
            "summary": 0.12,
            "evolution": 0.21,
            "response": 0.17,
            "impact": 0.19,
            "benchmark": 0.14,
            "action": 0.17,
        },
        "section_blueprint": [
            {"id": "summary", "title": "摘要", "goal": "概括政策或动态的核心影响与舆论反应。"},
            {"id": "evolution", "title": "事件脉络与传播演变", "goal": "按时间节点写清关键事件如何推动讨论对象迁移，并保持年度事实边界不串层。"},
            {"id": "response", "title": "公众态度与议题反应", "goal": "拆解舆论焦点、情绪结构与讨论方向。"},
            {"id": "impact", "title": "潜在影响", "goal": "区分结构性影响、机遇挑战与边界条件。"},
            {"id": "benchmark", "title": "行业对照", "goal": "说明行业主体、标杆案例或关联方反应。"},
            {"id": "action", "title": "趋势与应对", "goal": "输出趋势研判和条件闭合后的动作建议。"},
        ],
    },
    "crisis_response": {
        "scene_id": "crisis_response",
        "scene_label": "突发危机场景",
        "reference_template_name": "突发事件与危机公关舆情报告模板",
        "reference_template": "突发事件与危机公关舆情报告模板",
        "description": "适合事故、危机、公关风波和突发舆情任务，重点是首发、扩散、风险层级与响应窗口。",
        "supported_document_types": ["analysis_report", "monitor_brief"],
        "selection_hints": ["危机", "突发", "事故", "风波", "应急", "公关", "爆雷", "投诉"],
        "keyword_hints": ["危机", "突发", "事故", "风波", "应急", "公关", "爆雷", "投诉"],
        "layout_focus": [
            "开头先交代事件状态和风险级别，不绕背景。",
            "中段重点写时间线、传播节点和情绪压力点。",
            "建议应贴近处置窗口、事实说明与后续行动，不写泛化动作。",
        ],
        "hero_focus": ["事件定性", "关键时间线", "风险等级"],
        "recommendation_policy": "建议可覆盖处置窗口、解释框架与后续动作，但不得脱离证据写成强结论。",
        "analysis_path": ["scene_router", "evidence_analyst", "mechanism_analyst", "claim_judge", "risk_mapper", "analysis_supervisor"],
        "writing_path": ["layout_planner", "budget_planner", "section_writer", "style_critic", "fact_critic", "report_editor"],
        "default_total_words": 2400,
        "budget_weights": {
            "summary": 0.12,
            "timeline": 0.18,
            "propagation": 0.18,
            "attitude": 0.16,
            "risk": 0.18,
            "response": 0.18,
        },
        "section_blueprint": [
            {"id": "summary", "title": "摘要", "goal": "概括事件定性、核心结论与响应重点。"},
            {"id": "timeline", "title": "事件脉络", "goal": "说明首发、关键发展和当前态势。"},
            {"id": "propagation", "title": "传播分析", "goal": "拆解传播声量、渠道和关键传播节点。"},
            {"id": "attitude", "title": "舆论焦点与态度", "goal": "说明舆论焦点、情绪结构和主要观点。"},
            {"id": "risk", "title": "风险研判", "goal": "区分短期、长期和次生风险。"},
            {"id": "response", "title": "响应策略", "goal": "聚焦处置窗口、解释框架与后续行动。"},
        ],
    },
    "evidence_dossier": {
        "scene_id": "evidence_dossier",
        "scene_label": "证据汇编场景",
        "reference_template_name": "证据汇编自定义场景",
        "reference_template": "证据汇编自定义场景",
        "description": "适合附录、审查底稿和人工复核界面，重点是证据整理、样本展示与边界说明。",
        "supported_document_types": ["evidence_digest"],
        "selection_hints": ["证据", "汇编", "样本", "附录", "底稿", "核查", "条目"],
        "keyword_hints": ["证据", "汇编", "样本", "附录", "底稿", "核查", "条目"],
        "layout_focus": [
            "不主动扩写强判断，优先组织证据组和统计口径。",
            "每一节都要能回到样本或原始条目语义。",
            "边界和不确定性应单独成节，而不是夹在正文里。",
        ],
        "hero_focus": ["证据概览", "代表样本", "证据边界"],
        "recommendation_policy": "不主动生成动作建议，重点是证据整理、边界说明和回溯线索。",
        "analysis_path": ["scene_router", "evidence_analyst", "mechanism_analyst", "claim_judge", "risk_mapper", "analysis_supervisor"],
        "writing_path": ["layout_planner", "budget_planner", "section_writer", "style_critic", "fact_critic", "report_editor"],
        "default_total_words": 1800,
        "budget_weights": {
            "summary": 0.18,
            "evidence_matrix": 0.28,
            "sample_pack": 0.28,
            "boundary": 0.26,
        },
        "section_blueprint": [
            {"id": "summary", "title": "证据概览", "goal": "概括当前证据可支撑的判断范围。"},
            {"id": "evidence_matrix", "title": "证据矩阵", "goal": "按主题、阶段或主体整理核心证据组。"},
            {"id": "sample_pack", "title": "代表样本", "goal": "呈现最有代表性的条目语义与样本特征。"},
            {"id": "boundary", "title": "边界说明", "goal": "说明证据缺口、冲突点与尚不能下结论之处。"},
        ],
    },
}


def load_full_report_scene_catalog(document_type: str | None = None) -> List[Dict[str, Any]]:
    key = str(document_type or "").strip() or "analysis_report"
    results: List[Dict[str, Any]] = []
    for profile in SCENE_PROFILES.values():
        supported = profile.get("supported_document_types") or []
        if supported and key not in supported:
            continue
        results.append(deepcopy(profile))
    if results:
        return results
    return [deepcopy(SCENE_PROFILES["public_hotspot"])]


def load_full_report_scene_profile(scene_id: str | None = None) -> Dict[str, Any]:
    key = str(scene_id or "").strip()
    profile = SCENE_PROFILES.get(key) or SCENE_PROFILES["public_hotspot"]
    return deepcopy(profile)


def fallback_select_full_report_scene(
    document_type: str | None,
    *,
    topic_label: str = "",
    title: str = "",
    subtitle: str = "",
    event_type: str = "",
    domain: str = "",
    stage: str = "",
) -> Dict[str, Any]:
    doc_type = str(document_type or "").strip() or "analysis_report"
    if doc_type == "evidence_digest":
        return load_full_report_scene_profile("evidence_dossier")
    if doc_type == "monitor_brief":
        return load_full_report_scene_profile("routine_monitoring")

    haystack = " ".join(
        [
            str(topic_label or "").strip(),
            str(title or "").strip(),
            str(subtitle or "").strip(),
            str(event_type or "").strip(),
            str(domain or "").strip(),
            str(stage or "").strip(),
        ]
    )
    for scene_id in ("crisis_response", "policy_dynamics", "routine_monitoring"):
        profile = SCENE_PROFILES.get(scene_id) or {}
        raw_hints = profile.get("selection_hints") or profile.get("keyword_hints") or []
        hints = [str(item).strip() for item in raw_hints if str(item or "").strip()]
        if any(hint and hint in haystack for hint in hints):
            return deepcopy(profile)
    return load_full_report_scene_profile("public_hotspot")
