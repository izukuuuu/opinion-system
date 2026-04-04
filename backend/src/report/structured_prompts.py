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


def build_section_agent_system_prompt(section_name: str, focus: str = "") -> str:
    focus_text = str(focus or "").strip()
    prompt = (
        f"{REPORT_SYSTEM_PROMPT}"
        f"你当前负责报告中的“{section_name}”部分。"
        "请先完成本段内部研判，再输出可直接写入报告的最终 JSON。"
        "你可以吸收上游 deep_analysis、section_agent_analysis、方法论和参考材料中的判断，"
        "但不得把推测、外部线索或常识脑补写成事实。"
    )
    if focus_text:
        prompt += f"本段职责：{focus_text}"
    return prompt


def build_section_agent_analysis_prompt(section_name: str, section_goal: str, facts: Dict[str, Any]) -> str:
    schema = {
        "judgement": "80-160字，说明这一部分最值得强调的主线判断。",
        "evidence": ["最多4条，概括支撑该判断的事实依据或已知线索。"],
        "watchpoints": ["最多3条，指出本段撰写时需要规避的误读、风险或边界。"],
        "angle": "一句话，说明这一部分最终输出应采用的叙述角度。",
    }
    return (
        f"请先作为“{section_name}”分段研判 agent，基于事实生成一份内部分析备忘录。\n"
        "要求：\n"
        "1) judgement 必须是可复用的段落主线，不得空泛；\n"
        "2) evidence 只能来自输入事实、已知方法论、参考资料或上游结构化研判；\n"
        "3) watchpoints 要指出写作边界、潜在偏差或需要重点提醒的风险；\n"
        "4) angle 要给出最终段落的叙述角度，例如“强调传播节奏”“突出风险迁移”“压缩成编辑摘要”；\n"
        f"5) section_goal: {section_goal or '围绕本部分目标做事实归纳与表达设计'}；\n"
        "6) 仅输出 JSON。\n\n"
        f"【输出 JSON Schema】\n{_json_block(schema)}\n\n"
        f"【事实数据】\n{_json_block(facts)}"
    )


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
        "3) 如事实中包含 section_agent_analysis，可优先吸收其中的主线判断与叙述角度；\n"
        "4) 如事实中包含 skill_context，可吸收其中的标题写作约束与全篇主线要求；\n"
        "5) 如事实中包含 deep_analysis / methodology_context / reference_snippets / dynamic_theories，可用于增强表达；\n"
        "6) 如事实中包含 legacy_rag_sections 或 legacy_report_text，可用于增强表达；\n"
        "7) 仅输出 JSON。\n\n"
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
        "4) 可结合 section_agent_analysis 的 judgement / evidence / angle 强化阶段划分；\n"
        "5) 如事实中包含 skill_context，可吸收其中对传播阶段划分的偏好与边界；\n"
        "6) 可结合 deep_analysis.keyEvents / deep_analysis.stage / theory_hints 强化阶段解读；\n"
        "7) 可结合 legacy_rag_sections / legacy_report_text 强化阶段解读；\n"
        "8) 仅输出 JSON。\n\n"
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
        "4) 可吸收 section_agent_analysis 的 judgement / watchpoints，使卡片更有主线和边界感；\n"
        "5) 如事实中包含 skill_context，可吸收其中的结论压缩方式和建议表达约束；\n"
        "6) deep_analysis / methodology_context / reference_snippets / expert_notes 可作为研判背景；\n"
        "7) legacy_rag_sections / legacy_report_text 可作为证据性背景；\n"
        "8) 仅输出 JSON。\n\n"
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
        "4) 可吸收 section_agent_analysis 中对主题迁移主线的判断，但仍要以 BERTopic 时序事实为核心；\n"
        "5) 如事实中包含 skill_context，可吸收其中对主题迁移解读的偏好；\n"
        "6) deep_analysis 与 theory_hints 可作为背景；\n"
        "7) 输出语言口语化但专业，避免空话；\n"
        "8) 只输出 JSON。\n\n"
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
        "3) watchpoints 聚焦主题集中度、异常峰值与解读边界等提醒，不讨论覆盖率或子集构成；\n"
        "4) 可吸收 section_agent_analysis 中的迁移判断与风险边界；\n"
        "5) 如事实中包含 skill_context，可吸收其中关于切换信号和监测提醒的写作取向；\n"
        "6) 可吸收 deep_analysis / methodology_context 的风险视角，但不得脱离 BERTopic 事实；\n"
        "7) 不得编造输入中不存在的日期、数量或事件；\n"
        "8) 仅输出 JSON。\n\n"
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
        "5) 如存在 section_agent_analysis，可吸收其中的 judgement / evidence / watchpoints，但仍需回到事实本身；\n"
        "6) 如存在 skill_context，可吸收其中对研判结构、分段重点和方法论使用方式的约束；\n"
        "7) theoryNames 优先使用 methodology_context、dynamic_theories、theory_hints、reference_snippets 中真实可映射的理论；\n"
        "8) 如参考资料中存在 expert_notes，可吸收其中的研判视角，但不得把外部线索当成事实本身；\n"
        "9) 如存在 reference_links，只能把它们视为进一步核验入口，不得凭链接内容编造新事实；\n"
        "10) 仅输出 JSON。\n\n"
        f"【输出 JSON Schema】\n{_json_block(schema)}\n\n"
        f"【事实与上下文】\n{_json_block(facts)}"
    )


def build_full_report_scene_prompt(facts: Dict[str, Any]) -> str:
    schema = {
        "scene_id": "public_hotspot",
        "scene_reason": "60-120字，说明为什么当前任务更适合这一 scene。",
        "must_cover": ["最多4条，指出该 scene 下正文必须回答的问题。"],
        "writing_risks": ["最多3条，指出最容易写偏的地方。"],
    }
    return (
        "请作为 report template selector，在给定 scene_catalog 中选择当前最合适的报告场景。\n"
        "要求：\n"
        "1) 只能从 scene_catalog 中选择 1 个 scene_id；\n"
        "2) 选择依据应综合 document_type、主题类型、事件形态、风险结构和传播阶段，而不是只看标题表面词；\n"
        "3) scene_reason 要说明为何当前任务更适合该场景，而不是复述 scene 名称；\n"
        "4) must_cover 要指出正文必须回答的核心问题，writing_risks 要指出最容易写偏的方向；\n"
        "5) 若 document_type 为 monitor_brief，应优先保留简报属性；若为 evidence_digest，应优先保留证据汇编属性；\n"
        "6) 仅输出 JSON。\n\n"
        f"【输出 JSON Schema】\n{_json_block(schema)}\n\n"
        f"【事实数据】\n{_json_block(facts)}"
    )


def build_full_report_layout_prompt(facts: Dict[str, Any]) -> str:
    schema = {
        "layout_summary": "60-120字，概括这份完整报告的结构组织思路。",
        "hero_focus": ["最多4条，首页或摘要区最该突出的信息焦点。"],
        "writing_guidelines": ["最多5条，场景化的写作执行要求。"],
        "section_plan": [
            {
                "id": "summary",
                "title": "章节标题",
                "goal": "本节要回答什么问题",
                "priority": "high",
                "evidence_focus": ["最多4条，本节应优先吸收的事实或证据类型。"],
                "target_words": 260,
            }
        ],
    }
    return (
        "请作为 report layout designer，根据已选 scene_profile 与 style_profile 生成轻量布局计划。\n"
        "要求：\n"
        "1) section_plan 的顺序应体现当前文书体裁和 scene 的章节推进关系；\n"
        "2) section_plan.id 优先沿用 scene_profile.section_blueprint 中已有 id，不随意新造；\n"
        "3) target_words 只作为篇幅引导，应与文书类型匹配，monitor_brief 更紧凑，analysis_report 更完整；\n"
        "4) evidence_focus 只能引用输入事实里的证据类型、结构变量或已验证断言，不得凭空新增事实；\n"
        "5) writing_guidelines 要具体到本场景下的组织方式，而不是泛化的“语言要专业”；\n"
        "6) 仅输出 JSON。\n\n"
        f"【输出 JSON Schema】\n{_json_block(schema)}\n\n"
        f"【事实数据】\n{_json_block(facts)}"
    )


def build_full_report_budget_prompt(facts: Dict[str, Any]) -> str:
    schema = {
        "total_words": 2400,
        "global_guidelines": ["最多5条，说明全篇篇幅分配与详略原则。"],
        "sections": [
            {
                "id": "summary",
                "target_words": 260,
                "min_words": 180,
                "max_words": 320,
                "priority": "high",
                "focus": "该节应重点展开什么",
            }
        ],
    }
    return (
        "请作为 report budget planner，根据已选 scene_profile 和 layout_plan 生成章节篇幅规划。\n"
        "要求：\n"
        "1) sections 只能覆盖 layout_plan.section_plan 中已有的章节 id，顺序保持一致；\n"
        "2) total_words 要与文书类型和场景匹配，monitor_brief 偏紧凑，analysis_report 可以更完整；\n"
        "3) 每节必须给出 target_words / min_words / max_words，且三者关系必须合理；\n"
        "4) priority 只允许 high / medium / low；\n"
        "5) focus 应说明该节为什么值得展开，而不是重复标题；\n"
        "6) global_guidelines 重点说明详略关系、压缩原则和避免模板化铺陈的方法；\n"
        "7) 仅输出 JSON。\n\n"
        f"【输出 JSON Schema】\n{_json_block(schema)}\n\n"
        f"【事实数据】\n{_json_block(facts)}"
    )


def build_full_report_mechanism_prompt(facts: Dict[str, Any]) -> str:
    schema = {
        "evidence_semantics": [
            {
                "judgement": "一句可验证判断",
                "evidence": "支撑该判断的统计或样本语义",
                "source_note": "证据语义说明",
                "boundary": "该证据不能直接支撑什么结论",
            }
        ],
        "indicator_relationships": [
            {
                "signal": "一个关键指标或结构信号",
                "mechanism": "该信号如何作用于传播结构或讨论路径",
                "report_meaning": "它在报告中意味着什么",
            }
        ],
        "time_framework": {
            "narrative_stages": [
                {"stage": "阶段名", "range": "时间区间", "meaning": "阶段含义"}
            ],
            "analytical_signals": ["主题或结构切换信号"],
            "anchor_node": "关键时间锚点",
            "mapping_rule": "叙事时间与分析时间的映射规则",
        },
    }
    return (
        "请作为 mechanism_analyst，基于结构化结果与条目级证据，输出报告可直接消费的机制分析产物。\n"
        "要求：\n"
        "1) evidence_semantics 必须把统计结果改写为“判断+证据+边界”，不得保留中间层字段口吻；\n"
        "2) indicator_relationships 必须解释指标之间如何相互约束，不接受并列统计；\n"
        "3) time_framework 必须区分叙事时间与分析时间，并建立映射；\n"
        "4) 不能把相关性直接写成因果，也不能把聚类标签直接写成社会事实；\n"
        "5) 仅输出 JSON。\n\n"
        f"【输出 JSON Schema】\n{_json_block(schema)}\n\n"
        f"【事实数据】\n{_json_block(facts)}"
    )


def build_full_report_risk_map_prompt(facts: Dict[str, Any]) -> str:
    schema = {
        "risk_action_map": [
            {
                "risk": "风险项",
                "mechanism": "风险为何形成",
                "action_condition": "什么条件下才可动作",
                "action": "条件闭合后的动作",
                "boundary": "不能越过的证据边界",
            }
        ]
    }
    return (
        "请作为 risk_mapper，把风险判断改写成可执行的“风险-机制-条件-动作”映射。\n"
        "要求：\n"
        "1) 每条 risk_action_map 都必须先写风险机制，再写执行条件和动作；\n"
        "2) 对 evidence 不足或 claim_verifications 未通过的动作，只能写成条件未闭合，不得写成可立即启动；\n"
        "3) action_condition 必须具体，不能只写“需进一步观察”；\n"
        "4) 仅输出 JSON。\n\n"
        f"【输出 JSON Schema】\n{_json_block(schema)}\n\n"
        f"【事实数据】\n{_json_block(facts)}"
    )


def build_full_report_brief_prompt(facts: Dict[str, Any]) -> str:
    schema = {
        "core_thesis": "80-160字，说明完整报告最核心的主线判断。",
        "tone_notes": ["最多4条，说明行文口径、边界与应保持的表达克制。"],
        "preferred_terms": ["最多8条，优先沿用方法论/知识库中的术语。"],
        "sections": [
            {
                "id": "summary",
                "title": "章节标题",
                "goal": "这一节要回答什么问题",
                "evidence": ["最多4条，应引用哪些事实或已知方法论"],
            }
        ],
    }
    return (
        "请作为 report integrator，把结构化报告、知识库方法论和 skill 约束整合成一份写作 brief。\n"
        "要求：\n"
        "1) core_thesis 必须形成完整主线，不得只是标题复述；\n"
        "2) tone_notes 要强调证据边界、表达克制和适合当前文书类型的语气；\n"
        "3) preferred_terms 优先吸收 methodology_context / theory_hints / dynamic_theories / skill_context 中的术语；\n"
        "4) sections 的数量、顺序和命名应优先服从 layout_plan 和 section_budget，其次服从 scene_profile.section_blueprint 和 style_profile；\n"
        "5) sections.evidence 只能来自输入事实、方法论、旧报告上下文或已验证的证据约束；\n"
        "6) brief 必须明确要求正文避免技术审计口吻，不出现内部字段名、模块名、英文键名或“该数据来自……”式脚注表达；\n"
        "7) 如果输入中存在 style_profile、scene_profile、layout_plan、section_budget、language_requirements、language_contract 或 style_language_requirements，必须把它们视为写作契约，而不是可选偏好；\n"
        "8) 如果输入中存在 evidence_semantics / indicator_relationships / time_framework / risk_action_map / claim_verifications，应优先据此组织章节主线，而不是直接复述中间层字段；\n"
        "9) 仅输出 JSON。\n\n"
        f"【输出 JSON Schema】\n{_json_block(schema)}\n\n"
        f"【事实数据】\n{_json_block(facts)}"
    )


def build_full_report_section_prompt(facts: Dict[str, Any]) -> str:
    section = facts.get("section") if isinstance(facts.get("section"), dict) else {}
    title = str(section.get("title") or "正文").strip()
    target_words = int(section.get("target_words") or 0)
    section_hint = f"建议正文长度约 {target_words} 字。" if target_words > 0 else "建议篇幅适中。"
    rewrite_instruction = str(section.get("rewrite_instruction") or "").strip()
    rewrite_hint = f"10) 本轮重写重点：{rewrite_instruction}\n" if rewrite_instruction else ""
    return (
        f"请撰写完整报告中的“{title}”这一节，输出该节专属 Markdown 正文。\n"
        "要求：\n"
        "1) 只输出该节正文，不要重复输出本节 H2 标题，不要输出 H1，不要输出 JSON，不要输出代码块；\n"
        f"2) {section_hint}\n"
        "3) 该节必须服从 section.goal / section.focus / section.evidence_focus / scene_profile / style_profile / section_budget 的约束；\n"
        "4) 若当前节涉及风险、建议、归因或政策触发，必须优先服从 claim_verifications 和 recommendation_guardrails；\n"
        "5) 如输入提供了 tooling_context，应把它视为本节的工具调用策略，优先按 tool_focus 调用最合适的工具，而不是盲目少量检索；\n"
        "6) 如有必要，可调用工具补充参考证据、理论锚点、时间窗比较、政策文核查或条目级验证，但不得把工具输出以技术痕迹形式暴露在正文；\n"
        "7) 正文应以分析语言完成“证据→结构→机制→结论”的转译，不得写成模块结果拼接；\n"
        "8) 不得编造新的数字、日期、机构、政策名称或传播链路；\n"
        "9) 不得出现内部字段名、模块名、英文键名、工具名或“该数据来自……”类脚注表达；\n"
        "10) 节内如需补充层级，只允许少量 H3，不要再输出本节同名 H2。\n"
        f"{rewrite_hint}\n"
        f"【事实数据】\n{_json_block(facts)}"
    )


def build_full_report_style_critic_prompt(facts: Dict[str, Any]) -> str:
    schema = {
        "pass": True,
        "issues": ["最多4条，指出模板腔、重复句法或节间同质化问题"],
        "rewrite_instruction": "一句可直接交给 section_writer 的重写指令",
        "style_notes": ["最多3条，本节应如何与其他章节拉开语言功能"],
    }
    return (
        "请作为 style_critic，对单节报告语言做风格审校。\n"
        "要求：\n"
        "1) 重点检查模板腔、重复句法、节间同质化、技术口吻残留；\n"
        "2) 若发现问题，rewrite_instruction 必须具体到怎么改，不接受空泛评价；\n"
        "3) 如果当前节已经具备独立功能和语言差异，可 pass=true；\n"
        "4) 仅输出 JSON。\n\n"
        f"【输出 JSON Schema】\n{_json_block(schema)}\n\n"
        f"【事实数据】\n{_json_block(facts)}"
    )


def build_full_report_fact_critic_prompt(facts: Dict[str, Any]) -> str:
    schema = {
        "pass": True,
        "issues": ["最多4条，指出断言越级、因果跳跃、建议脱离条件等问题"],
        "rewrite_instruction": "一句可直接交给 section_writer 的重写指令",
        "guardrail_hits": ["命中的 claim / recommendation guardrail"],
    }
    return (
        "请作为 fact_critic，对单节报告做事实与结论强度审校。\n"
        "要求：\n"
        "1) 重点检查 claim_matrix、claim_verifications 和 recommendation_guardrails 是否被正确执行；\n"
        "2) unverified/conflicting 不得写成事实，动作条件不闭合不得写成既定动作；\n"
        "3) 若发现问题，rewrite_instruction 必须能直接指导重写；\n"
        "4) 仅输出 JSON。\n\n"
        f"【输出 JSON Schema】\n{_json_block(schema)}\n\n"
        f"【事实数据】\n{_json_block(facts)}"
    )


def build_full_report_markdown_prompt(facts: Dict[str, Any]) -> str:
    return (
        "请基于写作 brief 和结构化事实，输出一份完整中文 Markdown 报告。\n"
        "要求：\n"
        "1) 只输出 Markdown，禁止输出 JSON、解释文字或代码块；\n"
        "2) 必须包含 1 个 H1 标题，H2 章节数量与 layout_plan.section_plan 保持一致；若无 layout_plan，至少输出 3 个 H2 章节；\n"
        "3) 优先沿用 brief.preferred_terms、skill_context.reasoningStyle、skill_context.language_requirements、skill_context.language_contract、skill_context.style_language_requirements、style_profile、scene_profile、layout_plan、section_budget 和 methodology_context 中的约束；\n"
        "4) 不得编造新的数字、日期、机构表态或事件细节；\n"
        "5) 文书体裁、结构密度、章节推进、详略分配、语气与建议强度由 style_profile、scene_profile、layout_plan 和 section_budget 共同决定，不得把所有任务都写成同一种固定报告；\n"
        "6) 正文禁止出现输入数据结构名、内部模块名或英文键名，例如各类 snake_case / camelCase 标识、技术模块名或工具名；\n"
        "7) 禁止使用“该数据来自……模块”“依据某字段”“前提核验要求明确指出……”这类技术注释式表达；如需提示边界，要改写成业务语言，例如“该建议启动前仍需补充核验……”。\n"
        "8) 若输入中存在 evidence_semantics，正文应优先执行“证据→结构→机制→结论”的转译，不得停留在并列统计或模块结果拼接；\n"
        "9) 若输入中存在 subject_scope，主体、平台、机构和来源相关判断必须服从其 available_dimensions / missing_dimensions / prohibited_inference，不得超出原始数据源可支撑的主体范围；\n"
        "10) 若输入中存在 indicator_relationships，必须显式解释指标之间的约束关系，例如主导主题变化如何解释声量波动、渠道结构如何影响触达效率；\n"
        "11) 若输入中存在 time_framework，必须区分叙事时间与分析时间，并通过时间节点或阶段区间建立映射，不得混用；\n"
        "12) 若输入中存在 risk_action_map，建议部分必须先写风险作用机制，再写执行条件与动作，不得从风险直接跳到建议；\n"
        "13) 若输入中存在 claim_verifications，关键断言必须服从其 verification_status：supported 才可写成明确判断，partially_supported 只能写成倾向性判断，unverified 必须写成待核验线索，conflicting 必须写成存在分歧；\n"
        "14) 结构拆解章节不要把声量、主题、情绪、主体写成互不相干的数据清单，应写出结构失衡如何形成、如何相互强化、最终带来什么传播或治理后果；\n"
        "15) 建议部分必须区分“可立即启动”和“前提未满足、暂不启动”，未经验证的假设不得写成既定动作；如 recommendation_guardrails 提供了动作或判断护栏，必须严格执行；\n"
        "16) 不要输出目录，不要输出图片占位符，图片会由系统后处理插入。\n\n"
        f"【事实数据】\n{_json_block(facts)}"
    )


def build_full_report_revise_prompt(facts: Dict[str, Any]) -> str:
    return (
        "请作为 report reviser，对现有 Markdown 报告做最后一轮修订。\n"
        "要求：\n"
        "1) 只输出修订后的 Markdown，禁止输出解释文字；\n"
        "2) 优先修正过度推断、口号化表达、重复段落和证据链不清的问题；\n"
        "3) 保留原有章节结构，但可以重写句子和段落；\n"
        "4) 必须更充分地吸收 knowledge_context / skill_context / style_profile / scene_profile / layout_plan / section_budget 的术语、体裁约束、语言合同和分析视角；\n"
        "5) 必须清除技术审计口吻、字段说明口吻和系统内部痕迹，正文不得出现内部字段名、模块名、键名或工具名，也不得出现“该数据来自……”类脚注表达；\n"
        "6) 若输入中存在 evidence_semantics / indicator_relationships / time_framework / risk_action_map / claim_verifications，必须检查正文是否已完成对应的报告化转译，而不是保留分析中间层；\n"
        "7) claim_verifications 中 verification_status 为 unverified 或 conflicting 的断言不得在正文中写成确定事实；\n"
        "8) 若输入中存在 repair_focus / forbidden_terms / writing_guardrails / recommendation_guardrails，必须逐项消除对应问题并改写成正式业务语言；\n"
        "9) 不能新增输入中不存在的事实。\n\n"
        f"【事实数据】\n{_json_block(facts)}"
    )
