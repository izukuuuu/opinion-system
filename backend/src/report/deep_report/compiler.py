from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Sequence

from .semantic_control import extract_semantic_state, judge_evidence_support
from .schemas import (
    CompilerCriticResult,
    CompilerLayoutPlan,
    CompilerLayoutSection,
    CompilerSceneProfile,
    CompilerSectionBudget,
    CompilerSectionBudgetEntry,
    CompilerSectionPlanItem,
    CompilerStyleProfile,
    CompilerWriterContext,
    ConformancePolicyRegistry,
    DraftBundle,
    DraftUnit,
    FactualConformanceIssue,
    FactualConformanceResult,
    ReportIR,
    RewriteDiff,
    SemanticDelta,
    SemanticLatticeState,
    SectionPlan,
    StyledDraftBundle,
)


POLICY_VERSION = "policy.v2"
SEMANTIC_DIMENSIONS = (
    "assertion_certainty",
    "scope_quantifier",
    "risk_maturity",
    "action_force",
    "time_certainty",
    "actor_scope",
    "evidence_coverage",
    "verification_status",
)
ALLOWED_REWRITE_OPS = {
    "compress",
    "reorder",
    "merge_adjacent",
    "heading_normalize",
    "remove_redundancy",
    "lexical_soften",
    "list_to_paragraph",
    "paragraph_to_list",
    "transition_bridge",
}


def _ensure_ir(ir: ReportIR | Dict[str, Any]) -> ReportIR:
    return ir if isinstance(ir, ReportIR) else ReportIR.model_validate(ir if isinstance(ir, dict) else {})


def build_conformance_policy_registry() -> ConformancePolicyRegistry:
    return ConformancePolicyRegistry(
        policy_version=POLICY_VERSION,
        claim_gate={
            "supported": "indicated",
            "partially_supported": "conditional",
            "unverified": "observed",
            "conflicting": "observed",
        },
        risk_boundary={
            "low": "potential",
            "medium": "elevated",
            "high": "formed",
        },
        recommendation_boundary={
            "low": "monitor",
            "medium": "recommend",
            "high": "urgent",
        },
        strength_escalation={
            "assertion_certainty": ["observed", "conditional", "indicated", "confirmed"],
            "scope_quantifier": ["partial", "broad", "universal"],
            "risk_maturity": ["potential", "elevated", "formed", "systemic"],
            "action_force": ["monitor", "recommend", "urgent", "mandatory"],
            "time_certainty": ["uncertain", "windowed", "confirmed"],
            "actor_scope": ["specific_actor", "multi_actor", "public"],
            "evidence_coverage": ["unanchored", "anchored"],
            "verification_status": ["unverified", "partial", "supported", "conflicting"],
        },
        time_certainty={
            "uncertain": ["可能", "或", "待核验", "尚待"],
            "confirmed": ["已经", "已于", "确定", "证实"],
        },
        actor_scope={
            "public": ["舆论普遍", "社会普遍", "公众一致", "全面"],
            "multi_actor": ["多平台", "多主体", "多方"],
        },
        evidence_coverage={
            "unanchored": ["据称", "有观点认为", "有声音称"],
            "anchored": ["根据", "证据显示", "材料显示", "台账显示"],
        },
        allowed_rewrite_ops=sorted(ALLOWED_REWRITE_OPS),
        disallowed_rewrite_ops=[
            "infer_implication",
            "upgrade_risk",
            "generalize_public_opinion",
            "fill_missing_cause",
            "add_subject_relation",
            "add_new_recommendation",
        ],
        approval_thresholds={
            "strength_escalation": "human_review",
            "risk_boundary_violation": "human_review",
            "recommendation_boundary_violation": "human_review",
            "claim_gate_violation": "auto_recover",
        },
    )


def _level_index(registry: ConformancePolicyRegistry, dimension: str, level: str) -> int:
    values = registry.strength_escalation.get(dimension) or []
    try:
        return values.index(level)
    except ValueError:
        return -1


def _semantic_state_from_levels(levels: Dict[str, str]) -> SemanticLatticeState:
    return SemanticLatticeState.model_validate(levels)


def _semantic_deltas(
    registry: ConformancePolicyRegistry,
    *,
    baseline: SemanticLatticeState,
    actual: SemanticLatticeState,
) -> List[SemanticDelta]:
    deltas: List[SemanticDelta] = []
    for dimension in SEMANTIC_DIMENSIONS:
        before_level = getattr(baseline, dimension, "")
        after_level = getattr(actual, dimension, "")
        if not before_level or not after_level:
            direction = "unknown"
        else:
            before_index = _level_index(registry, dimension, before_level)
            after_index = _level_index(registry, dimension, after_level)
            if before_index < 0 or after_index < 0:
                direction = "unknown"
            elif after_index > before_index:
                direction = "up"
            elif after_index < before_index:
                direction = "down"
            else:
                direction = "same"
        deltas.append(
            SemanticDelta(
                dimension=dimension,
                before_level=before_level,
                after_level=after_level,
                direction=direction,
                locked=True,
            )
        )
    return deltas


def _collect_trace_ids_from_unit(unit: DraftUnit) -> List[str]:
    return list(
        dict.fromkeys(
            unit.trace_ids + unit.claim_ids + unit.evidence_ids + unit.risk_ids + unit.unresolved_point_ids + unit.stance_row_ids
        )
    )


def _extract_leading_trace_ids(line: str) -> List[str]:
    text = str(line or "")
    if not text.strip():
        return []
    match = re.match(r"^\s*(?:[-*]\s*)?(?P<prefix>(?:\[[^\]]+\]\s*)+)", text)
    if not match:
        return []
    prefix = str(match.group("prefix") or "")
    return [item.strip() for item in re.findall(r"\[([^\]]+)\]", prefix) if str(item or "").strip()]


def _semantic_signature(text: str, *, section_role: str, trace_ids: List[str], payload: ReportIR, registry: ConformancePolicyRegistry) -> Dict[str, str]:
    baseline = _semantic_state_from_levels(
        _baseline_signature(payload, section_role=section_role, trace_ids=trace_ids, registry=registry)
    )
    return extract_semantic_state(
        payload,
        text=str(text or "").strip(),
        section_role=section_role,
        trace_ids=trace_ids,
        baseline=baseline,
        registry=registry,
    ).model_dump()


def _baseline_signature(
    payload: ReportIR,
    *,
    section_role: str,
    trace_ids: List[str],
    registry: ConformancePolicyRegistry,
) -> Dict[str, str]:
    baseline = {
        "assertion_certainty": "conditional",
        "scope_quantifier": "partial",
        "risk_maturity": "potential",
        "action_force": "monitor",
        "time_certainty": "windowed",
        "actor_scope": "specific_actor",
        "evidence_coverage": "unanchored",
        "verification_status": "supported",
    }
    claim_lookup = {claim.claim_id: claim for claim in payload.claim_set.claims}
    risk_lookup = {risk.risk_id: risk for risk in payload.risk_register.risks}
    recommendation_lookup = {item.candidate_id: item for item in payload.recommendation_candidates.items}

    for trace_id in trace_ids:
        claim = claim_lookup.get(trace_id)
        if claim is not None:
            baseline["assertion_certainty"] = max(
                baseline["assertion_certainty"],
                registry.claim_gate.get(claim.status, "conditional"),
                key=lambda value: _level_index(registry, "assertion_certainty", value),
            )
            if claim.status in {"unverified", "conflicting"}:
                baseline["time_certainty"] = "uncertain"
            baseline["verification_status"] = (
                "unverified"
                if claim.status == "unverified"
                else "conflicting"
                if claim.status == "conflicting"
                else "partial"
                if claim.status == "partially_supported"
                else baseline["verification_status"]
            )
        risk = risk_lookup.get(trace_id)
        if risk is not None:
            baseline["risk_maturity"] = max(
                baseline["risk_maturity"],
                registry.risk_boundary.get(risk.severity, "potential"),
                key=lambda value: _level_index(registry, "risk_maturity", value),
            )
            if risk.trigger_evidence_ids:
                baseline["evidence_coverage"] = "anchored"
        recommendation = recommendation_lookup.get(trace_id)
        if recommendation is not None:
            priority = str(recommendation.priority or "").strip().lower()
            baseline["action_force"] = max(
                baseline["action_force"],
                registry.recommendation_boundary.get(priority or "medium", "recommend"),
                key=lambda value: _level_index(registry, "action_force", value),
            )
        if trace_id.startswith("sub-") or trace_id.startswith("actor:"):
            baseline["actor_scope"] = "specific_actor"
        if trace_id.startswith("ev-") or trace_id.startswith("evidence:"):
            baseline["time_certainty"] = max(
                baseline["time_certainty"],
                "windowed",
                key=lambda value: _level_index(registry, "time_certainty", value),
            )
            baseline["evidence_coverage"] = "anchored"
        elif claim is not None and claim.support_evidence_ids:
            baseline["evidence_coverage"] = "anchored"
    if section_role == "recommendations":
        baseline["action_force"] = max(
            baseline["action_force"],
            "recommend",
            key=lambda value: _level_index(registry, "action_force", value),
        )
    return baseline


def _build_escalation_issues(
    *,
    registry: ConformancePolicyRegistry,
    baseline: SemanticLatticeState,
    actual: SemanticLatticeState,
    line: str,
    section_role: str,
    trace_ids: List[str],
    issue_prefix: str,
    start_index: int,
) -> tuple[List[FactualConformanceIssue], List[SemanticDelta], int]:
    issues: List[FactualConformanceIssue] = []
    deltas = _semantic_deltas(registry, baseline=baseline, actual=actual)
    issue_index = int(start_index)
    for delta in deltas:
        before_level = delta.before_level
        after_level = delta.after_level
        if delta.direction != "up" or not before_level or not after_level:
            continue
        issue_index += 1
        issue_type = "strength_escalation"
        if delta.dimension == "risk_maturity":
            issue_type = "risk_boundary_violation"
        elif delta.dimension == "action_force" and section_role == "recommendations":
            issue_type = "recommendation_boundary_violation"
        issues.append(
            FactualConformanceIssue(
                issue_id=f"{issue_prefix}_{delta.dimension}:{issue_index}",
                issue_type=issue_type,
                message="文本在语义格上超过了已登记边界。",
                section_role=section_role,
                sentence=line,
                trace_ids=list(trace_ids),
                semantic_dimension=delta.dimension,
                before_level=before_level,
                after_level=after_level,
                suggested_action="请降级表述或回退到上游 DraftUnit。",
            )
        )
    return issues, deltas, issue_index

def _section(section_id: str, title: str, goal: str, target_words: int) -> CompilerLayoutSection:
    return CompilerLayoutSection(section_id=section_id, title=title, goal=goal, target_words=target_words)


def select_scene_profile(ir: ReportIR | Dict[str, Any]) -> CompilerSceneProfile:
    """根据报告内容选择最相近模板，并返回对应 scene/profile。"""
    payload = _ensure_ir(ir)
    from ..full_report_templates import choose_best_template
    from ..scene_profile import load_full_report_scene_profile

    template_data = choose_best_template(
        topic_label=str(payload.meta.topic_label or payload.meta.topic_identifier or "").strip(),
        title=str(payload.meta.topic_label or "").strip(),
        subtitle="",
        mode=str(payload.meta.mode or "").strip(),
        report_ir=payload.model_dump(),
    )
    scene_id = str(template_data.get("scene_id") or template_data.get("template_id") or "public_hotspot").strip() or "public_hotspot"
    scene_profile = load_full_report_scene_profile(scene_id)
    scene_label = str(scene_profile.get("scene_label") or template_data.get("scene_label") or "").strip()

    # 正式文稿统一使用模板驱动写作，避免固定 section_id 分支退化成骨架。
    render_mode = "template_driven"
    focus = (
        "risk"
        if scene_id == "crisis_response"
        else "risk"
        if scene_id == "policy_dynamics"
        else "timeline"
    )
    unresolved_count = len(payload.unresolved_points.items)

    return CompilerSceneProfile(
        scene_id=scene_id,
        scene_label=scene_label,
        focus=focus,
        guardrail_mode="bounded_claims" if unresolved_count else "strict",
        render_mode=render_mode,
        template_id=str(template_data.get("template_id") or "").strip(),
        template_name=str(template_data.get("template_name") or "").strip(),
        template_path=str(template_data.get("template_path") or "").strip(),
        selection_score=float(template_data.get("score") or 0.0),
        matched_reasons=[
            str(item).strip()
            for item in (template_data.get("matched_reasons") or [])
            if str(item or "").strip()
        ],
        selection_context=template_data.get("selection_context") if isinstance(template_data.get("selection_context"), dict) else {},
        template_sections=template_data.get("template_sections", []),
        template_markdown=template_data.get("template_markdown", ""),
    )


def resolve_style_profile(
    ir: ReportIR | Dict[str, Any],
    scene_profile: CompilerSceneProfile | Dict[str, Any],
) -> CompilerStyleProfile:
    payload = _ensure_ir(ir)
    scene = scene_profile if isinstance(scene_profile, CompilerSceneProfile) else CompilerSceneProfile.model_validate(scene_profile or {})
    tone = "cautious" if payload.unresolved_points.items else "neutral"
    notes = ["结论必须回链到 claim 或 evidence。", "不允许引入 ReportIR 中不存在的新事实。"]
    if scene.focus == "risk":
        notes.append("风险与建议先写边界，再写判断。")
    return CompilerStyleProfile(
        style_id="evidence_first",
        document_tone=tone,
        heading_style="analytic",
        tone_notes=notes,
    )


def build_layout_plan(
    ir: ReportIR | Dict[str, Any],
    scene_profile: CompilerSceneProfile | Dict[str, Any],
    style_profile: CompilerStyleProfile | Dict[str, Any],
) -> CompilerLayoutPlan:
    payload = _ensure_ir(ir)
    _ = style_profile if isinstance(style_profile, CompilerStyleProfile) else CompilerStyleProfile.model_validate(style_profile or {})
    scene = scene_profile if isinstance(scene_profile, CompilerSceneProfile) else CompilerSceneProfile.model_validate(scene_profile or {})
    sections: List[CompilerLayoutSection] = [
        _section("executive_summary", "执行摘要", "概括核心判断与边界。", 180),
        _section("claims", "事实断言", "只输出已冻结的 claim 与证据锚点。", 320),
    ]
    if payload.agenda_frame_map.issues or payload.agenda_frame_map.frames:
        sections.append(_section("agenda", "议题与框架", "说明议题显著性、属性联结与问题定义方式。", 240))
    if payload.timeline.events:
        sections.append(_section("timeline", "时间线", "交代事件演化与关键节点。", 240))
    if payload.stance_matrix.rows:
        sections.append(_section("actors", "主体与立场", "说明主体关系、分歧与支持证据。", 240))
    if payload.conflict_map.claims or payload.conflict_map.edges:
        sections.append(_section("conflicts", "冲突与收敛", "说明断言、主体和冲突边的收敛状态。", 240))
    if payload.mechanism_summary.amplification_paths or payload.mechanism_summary.phase_shifts or payload.mechanism_summary.trigger_events:
        sections.append(_section("mechanism", "传播机制", "交代扩散路径、触发事件与阶段转折。", 240))
    if payload.risk_register.risks:
        sections.append(_section("risks", "风险登记", "说明风险项、触发链和边界。", 280 if scene.focus == "risk" else 220))
    if payload.recommendation_candidates.items:
        sections.append(_section("recommendations", "建议动作", "只写带 claim 绑定的建议。", 200))
    if payload.unresolved_points.items:
        sections.append(_section("unresolved", "待核验点", "说明仍未冻结的边界。", 180))
    if payload.evidence_ledger.entries:
        sections.append(_section("ledger", "证据账本", "保留主要证据索引。", 160))
    return CompilerLayoutPlan(
        layout_summary=f"采用 {scene.scene_label} 编排，围绕 {scene.focus} 组织章节。",
        sections=sections,
    )


def build_section_budget(
    ir: ReportIR | Dict[str, Any],
    scene_profile: CompilerSceneProfile | Dict[str, Any],
    layout_plan: CompilerLayoutPlan | Dict[str, Any],
) -> CompilerSectionBudget:
    payload = _ensure_ir(ir)
    _ = scene_profile if isinstance(scene_profile, CompilerSceneProfile) else CompilerSceneProfile.model_validate(scene_profile or {})
    layout = layout_plan if isinstance(layout_plan, CompilerLayoutPlan) else CompilerLayoutPlan.model_validate(layout_plan or {})
    base_words = 900 + min(700, len(payload.claim_set.claims) * 45)
    entries: List[CompilerSectionBudgetEntry] = []
    for section in layout.sections:
        target = max(120, int(section.target_words))
        entries.append(
            CompilerSectionBudgetEntry(
                section_id=section.section_id,
                target_words=target,
                min_words=max(90, int(target * 0.75)),
                max_words=max(target + 40, int(target * 1.35)),
            )
        )
    total_words = sum(item.target_words for item in entries) or base_words
    return CompilerSectionBudget(total_words=total_words, sections=entries)


def assemble_writer_context(
    ir: ReportIR | Dict[str, Any],
    scene_profile: CompilerSceneProfile | Dict[str, Any],
    style_profile: CompilerStyleProfile | Dict[str, Any] | None = None,
    layout_plan: CompilerLayoutPlan | Dict[str, Any] | None = None,
    section_budget: CompilerSectionBudget | Dict[str, Any] | None = None,
) -> CompilerWriterContext:
    payload = _ensure_ir(ir)
    scene = scene_profile if isinstance(scene_profile, CompilerSceneProfile) else CompilerSceneProfile.model_validate(scene_profile or {})
    style = style_profile if isinstance(style_profile, CompilerStyleProfile) else CompilerStyleProfile.model_validate(style_profile or {})
    layout = layout_plan if isinstance(layout_plan, CompilerLayoutPlan) else CompilerLayoutPlan.model_validate(layout_plan or {})
    budget = section_budget if isinstance(section_budget, CompilerSectionBudget) else CompilerSectionBudget.model_validate(section_budget or {})
    return CompilerWriterContext(
        topic=payload.meta.topic_label or payload.meta.topic_identifier,
        range=payload.meta.time_scope,
        scene_profile=scene,
        style_profile=style,
        layout_plan=layout,
        section_budget=budget,
        counts={
            "claims": len(payload.claim_set.claims),
            "evidence": len(payload.evidence_ledger.entries),
            "agenda_issues": len(payload.agenda_frame_map.issues),
            "agenda_frames": len(payload.agenda_frame_map.frames),
            "actors": len(payload.actor_registry.actors),
            "conflict_edges": len(payload.conflict_map.edges),
            "mechanism_paths": len(payload.mechanism_summary.amplification_paths),
            "risks": len(payload.risk_register.risks),
            "unresolved": len(payload.unresolved_points.items),
        },
    )


# BettaFish 质量写作目标 —— 强制表格结构和原文引用
_BETTAFISH_SECTION_GOALS: Dict[str, str] = {
    "监测口径与样本说明": (
        "必须输出表格：平台 | 样本量 | 时间范围 | 覆盖局限。"
        "交代结论适用范围，注明未覆盖的平台或场景。"
    ),
    "摘要": (
        "先概括态势，再指出分歧，再给出趋势判断。"
        "禁止口号式结论。必须包含：事件当前阶段、核心争议点、舆论走向。"
    ),
    "事件演变": (
        "必须输出事件全景速览表格：时间 | 爆点事件 | 传播量级 | 核心情绪关键词。"
        "围绕'节点—转折—再定义'展开，每个节点：发生了什么 / 为什么改变讨论结构 / 由谁推动。"
        "必须嵌入具体网民金句作为情绪锚点（使用 > '原文' —— 来源 格式）。"
    ),
    "传播路径": (
        "必须输出平台情绪雷达表格：平台 | 主导情绪 | 代表性评论（引用原文） | 传播角色。"
        "区分首发源/搬运节点/情绪放大节点/权威纠偏节点，写出接力关系而非并列。"
        "必须输出情绪传导公式：A → B → C → 标签化。"
    ),
    "舆论立场与结构": (
        "必须输出多元群体诉求清单表格：群体 | 高频诉求 | 金句（引用原文）。"
        "至少区分：当事方/官方机构/传统媒体/垂类博主/普通用户/利益相关群体。"
        "每类主体：核心立场 + 表达强度 + 影响范围 + 互动关系。"
    ),
    "核心焦点与情绪": (
        "情绪必须附着在具体议题上，不能单独列'愤怒/质疑'标签。"
        "每个焦点簇：核心问题 / 主导情绪 / 典型观点 / 聚集原因。"
        "必须引用具体网民原文（使用 > '原文' —— 平台/作者 格式）。"
    ),
    "深层动因": (
        "从四层展开：现实结构利益冲突 / 认知信息不对称 / 平台推荐机制 / 价值符号冲突。"
        "说明本次事件哪层起主导作用，以及各层如何叠加。"
        "禁止'社会关注度高''平台传播快'等表层描述。"
    ),
    "影响与动作": (
        "必须输出高风险三色灯表格：🔴/🟡/🟢 | 风险描述 | 爆点预测 | 触发阈值 | 提前干预动作。"
        "先写影响传导（舆情→组织/政策/行业层面），再写动作建议。"
        "建议必须与风险和传播机制一一对应，禁止空泛建议。"
    ),
    "附录": (
        "输出证据台账表格：来源 | 平台 | 发布时间 | 可信度 | 内容摘要。"
        "列出代表性信息源与高传播表达，为报告关键判断提供锚点。"
    ),
}


def build_section_plan(
    ir: ReportIR | Dict[str, Any],
    layout_plan: CompilerLayoutPlan | Dict[str, Any],
    section_budget: CompilerSectionBudget | Dict[str, Any],
    scene_profile: CompilerSceneProfile | Dict[str, Any] | None = None,
) -> SectionPlan:
    """构建章节规划，优先使用模板章节，fallback 到布局规划章节."""
    _ = _ensure_ir(ir)
    layout = layout_plan if isinstance(layout_plan, CompilerLayoutPlan) else CompilerLayoutPlan.model_validate(layout_plan or {})
    budget = section_budget if isinstance(section_budget, CompilerSectionBudget) else CompilerSectionBudget.model_validate(section_budget or {})
    budget_map = {item.section_id: item.target_words for item in budget.sections}

    # 章节与数据源的映射
    group_map = {
        "executive_summary": ["narrative_views", "claim_set", "risk_register", "unresolved_points"],
        "监测口径与样本说明": ["meta", "evidence_ledger"],
        "摘要": ["narrative_views", "claim_set", "risk_register"],
        "事件演变": ["timeline", "evidence_ledger", "claim_set"],
        "传播路径": ["mechanism_summary", "timeline", "evidence_ledger"],
        "舆论立场与结构": ["stance_matrix", "actor_registry", "conflict_map", "evidence_ledger"],
        "核心焦点与情绪": ["agenda_frame_map", "claim_set", "evidence_ledger"],
        "深层动因": ["mechanism_summary", "agenda_frame_map", "conflict_map"],
        "影响与动作": ["risk_register", "recommendation_candidates", "utility_assessment"],
        "附录": ["evidence_ledger", "citations"],
        # fallback IDs
        "claims": ["claim_set", "evidence_ledger"],
        "agenda": ["agenda_frame_map", "evidence_ledger", "actor_registry"],
        "timeline": ["timeline", "evidence_ledger"],
        "actors": ["stance_matrix", "actor_registry", "evidence_ledger"],
        "conflicts": ["conflict_map", "claim_set", "actor_registry"],
        "mechanism": ["mechanism_summary", "timeline", "agenda_frame_map", "evidence_ledger"],
        "risks": ["risk_register", "claim_set", "evidence_ledger", "agenda_frame_map", "conflict_map", "mechanism_summary"],
        "recommendations": ["recommendation_candidates", "claim_set", "agenda_frame_map", "utility_assessment", "risk_register"],
        "unresolved": ["unresolved_points", "claim_set"],
        "ledger": ["evidence_ledger"],
    }

    # 章节ID标准化函数
    def _section_id_from_title(title: str) -> str:
        normalized = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "_", str(title or "").strip().lower()).strip("_")
        return normalized or "section"

    # 优先使用模板章节
    scene = scene_profile if isinstance(scene_profile, CompilerSceneProfile) else None
    template_sections = scene.template_sections if scene and scene.template_sections else []

    if template_sections:
        # 使用模板章节构建规划，合并 BettaFish 强制结构要求
        sections_list = []
        for s in template_sections:
            title_key = str(s.get("title", "")).strip()
            if not title_key:
                continue
            base_goal = str(s.get("summary", "")).strip()
            extra_instruction = str(s.get("writing_instruction", "")).strip()
            bettafish_goal = _BETTAFISH_SECTION_GOALS.get(title_key, "")
            # BettaFish 结构要求在前，模板指导在后
            merged_goal = f"{bettafish_goal}\n\n{base_goal}".strip() if bettafish_goal else base_goal
            if extra_instruction:
                merged_goal = f"{merged_goal}\n\n补充要求：{extra_instruction}".strip()
            # BettaFish 章节字数更高（表格+叙事）
            default_section_id = _section_id_from_title(title_key)
            section_id = str(s.get("section_id", "")).strip() or default_section_id
            base_words = int(budget_map.get(section_id, budget_map.get(default_section_id, 280)))
            target_words = max(base_words, 400) if bettafish_goal else base_words
            sections_list.append(
                CompilerSectionPlanItem(
                    section_id=section_id,
                    title=title_key,
                    goal=merged_goal,
                    target_words=target_words,
                    source_groups=group_map.get(section_id, group_map.get(default_section_id, [])),
                    template_id=str(scene.template_id or "").strip(),
                    template_title=title_key,
                    template_summary=base_goal,
                    writing_instruction=extra_instruction,
                    selection_context={
                        "scene_id": str(scene.scene_id or "").strip(),
                        "template_id": str(scene.template_id or "").strip(),
                        "template_name": str(scene.template_name or "").strip(),
                        "template_path": str(scene.template_path or "").strip(),
                        "template_score": float(scene.selection_score or 0.0),
                        "matched_reasons": list(scene.matched_reasons or []),
                    },
                )
            )
        sections = sections_list
    else:
        # fallback 到布局规划章节
        sections = [
            CompilerSectionPlanItem(
                section_id=section.section_id,
                title=section.title,
                goal=section.goal,
                target_words=int(budget_map.get(section.section_id, section.target_words)),
                source_groups=group_map.get(section.section_id, []),
            )
            for section in layout.sections
        ]

    return SectionPlan(sections=sections)


def _bounded(items: Sequence[Any], limit: int) -> List[Any]:
    return list(items[: max(0, limit)])


def _join_ids(values: Iterable[str], limit: int = 4) -> str:
    picked = [str(value).strip() for value in values if str(value or "").strip()][:limit]
    return ",".join(picked) if picked else "none"


def _claim_map(payload: ReportIR) -> Dict[str, Any]:
    return {claim.claim_id: claim for claim in payload.claim_set.claims}


def _build_summary_units(payload: ReportIR) -> List[DraftUnit]:
    units: List[DraftUnit] = []
    if payload.narrative_views.executive_summary:
        claim_ids = [claim.claim_id for claim in _bounded(payload.claim_set.claims, 3)]
        evidence_ids: List[str] = []
        for claim in _bounded(payload.claim_set.claims, 3):
            evidence_ids.extend(claim.support_evidence_ids[:2])
        risk_ids = [risk.risk_id for risk in _bounded(payload.risk_register.risks, 2)]
        unresolved_ids = [item.item_id for item in _bounded(payload.unresolved_points.items, 2)]
        units.append(
            DraftUnit(
                unit_id="unit:executive_summary:summary",
                section_role="executive_summary",
                text=payload.narrative_views.executive_summary,
                claim_ids=claim_ids,
                evidence_ids=list(dict.fromkeys(evidence_ids)),
                risk_ids=risk_ids,
                unresolved_point_ids=unresolved_ids,
                confidence="medium" if unresolved_ids else "high",
                is_unresolved=bool(unresolved_ids),
            )
        )
    for index, finding in enumerate(_bounded(payload.narrative_views.key_findings, 4), start=1):
        matched_claims = [claim.claim_id for claim in payload.claim_set.claims if finding and finding in claim.text][:2]
        if not matched_claims and payload.claim_set.claims:
            matched_claims = [payload.claim_set.claims[min(index - 1, len(payload.claim_set.claims) - 1)].claim_id]
        evidence_ids: List[str] = []
        for claim_id in matched_claims:
            claim = _claim_map(payload).get(claim_id)
            if claim is not None:
                evidence_ids.extend(claim.support_evidence_ids[:2])
        units.append(
            DraftUnit(
                unit_id=f"unit:executive_summary:finding:{index}",
                section_role="executive_summary",
                text=str(finding).strip(),
                claim_ids=matched_claims,
                evidence_ids=list(dict.fromkeys(evidence_ids)),
                confidence="high" if evidence_ids else "medium",
            )
        )
    return units


def _build_claim_units(payload: ReportIR, limit: int) -> List[DraftUnit]:
    units: List[DraftUnit] = []
    for claim in _bounded(payload.claim_set.claims, limit):
        support = _join_ids(claim.support_evidence_ids, 3)
        counter = _join_ids(claim.counter_evidence_ids, 2)
        text = f"[{claim.claim_id}] {claim.text}（status={claim.status}; support={support}; counter={counter}）"
        units.append(
            DraftUnit(
                unit_id=f"unit:claims:{claim.claim_id}",
                section_role="claims",
                text=text,
                claim_ids=[claim.claim_id],
                evidence_ids=list(claim.support_evidence_ids),
                confidence="high" if claim.support_evidence_ids else "medium",
                is_unresolved=claim.status in {"unverified", "conflicting"},
            )
        )
    return units


def _build_timeline_units(payload: ReportIR, limit: int) -> List[DraftUnit]:
    units: List[DraftUnit] = []
    for event in _bounded(payload.timeline.events, limit):
        text = f"[{event.event_id}] {event.time_label} {event.summary}（support={_join_ids(event.support_evidence_ids, 3)}）"
        units.append(
            DraftUnit(
                unit_id=f"unit:timeline:{event.event_id}",
                section_role="timeline",
                text=text,
                trace_ids=[event.event_id] if event.event_id else [],
                evidence_ids=list(event.support_evidence_ids),
                confidence="high" if event.support_evidence_ids else "medium",
            )
        )
    return units


def _build_agenda_units(payload: ReportIR, limit: int) -> List[DraftUnit]:
    units: List[DraftUnit] = []
    for issue in _bounded(payload.agenda_frame_map.issues, max(1, limit // 3)):
        units.append(
            DraftUnit(
                unit_id=f"unit:agenda:issue:{issue.issue_id}",
                section_role="agenda",
                text=f"[{issue.issue_id}] 议题 {issue.label}（salience={issue.salience}; sources={_join_ids(issue.source_refs, 3)}）",
                trace_ids=[issue.issue_id] if issue.issue_id else [],
                evidence_ids=list(issue.source_refs),
                confidence="medium",
            )
        )
    for frame in _bounded(payload.agenda_frame_map.frames, max(1, limit // 3)):
        units.append(
            DraftUnit(
                unit_id=f"unit:agenda:frame:{frame.frame_id}",
                section_role="agenda",
                text=f"[{frame.frame_id}] problem={frame.problem}；cause={frame.cause}；remedy={frame.remedy}",
                trace_ids=[frame.frame_id] if frame.frame_id else [],
                evidence_ids=list(frame.source_refs),
                confidence="medium",
            )
        )
    for shift in _bounded(payload.agenda_frame_map.frame_shifts, max(1, limit // 4)):
        units.append(
            DraftUnit(
                unit_id=f"unit:agenda:shift:{shift.shift_id}",
                section_role="agenda",
                text=f"[{shift.shift_id}] {shift.from_frame_id} -> {shift.to_frame_id}",
                trace_ids=[shift.shift_id] if shift.shift_id else [],
                evidence_ids=list(shift.trigger_refs),
                confidence="medium",
            )
        )
    return units


def _build_actor_units(payload: ReportIR, limit: int) -> List[DraftUnit]:
    units: List[DraftUnit] = []
    for row in _bounded(payload.stance_matrix.rows, limit):
        text = f"[{row.actor_id}] {row.stance}：{row.stance_shift}（support={_join_ids(row.support_evidence_ids, 3)}）"
        units.append(
            DraftUnit(
                unit_id=f"unit:actors:{row.actor_id}",
                section_role="actors",
                text=text,
                evidence_ids=list(row.support_evidence_ids),
                stance_row_ids=[row.actor_id],
                confidence="high" if row.support_evidence_ids else "medium",
            )
        )
    return units


def _build_conflict_units(payload: ReportIR, limit: int) -> List[DraftUnit]:
    units: List[DraftUnit] = []
    for edge in _bounded(payload.conflict_map.edges, limit):
        claim_ids = [edge.claim_a_id, edge.claim_b_id]
        text = (
            f"[{edge.edge_id}] {edge.conflict_type}"
            f"（claims={_join_ids(claim_ids, 3)}; actors={_join_ids(edge.actor_scope, 3)}; evidence={_join_ids(edge.evidence_refs, 3)}）"
        )
        units.append(
            DraftUnit(
                unit_id=f"unit:conflicts:{edge.edge_id}",
                section_role="conflicts",
                text=text,
                claim_ids=[item for item in claim_ids if item],
                evidence_ids=list(edge.evidence_refs),
                confidence="medium",
                is_unresolved=True,
            )
        )
    for item in _bounded(payload.conflict_map.resolution_summary, max(1, limit // 2)):
        text = f"[{item.claim_id}] {item.status}：{item.reason or item.unresolved_reason}"
        units.append(
            DraftUnit(
                unit_id=f"unit:conflicts:resolution:{item.claim_id}",
                section_role="conflicts",
                text=text,
                claim_ids=[item.claim_id] if item.claim_id else [],
                confidence="medium" if item.status == "converged" else "low",
                is_unresolved=item.status != "converged",
            )
        )
    return units


def _build_mechanism_units(payload: ReportIR, limit: int) -> List[DraftUnit]:
    units: List[DraftUnit] = []
    for path in _bounded(payload.mechanism_summary.amplification_paths, max(1, limit // 2)):
        text = (
            f"[{path.path_id}] 扩散路径：platforms={_join_ids(path.platform_sequence, 4)}"
            f"；bridges={_join_ids(path.bridge_actor_ids, 3)}；evidence={_join_ids(path.evidence_refs, 3)}"
        )
        units.append(
            DraftUnit(
                unit_id=f"unit:mechanism:{path.path_id}",
                section_role="mechanism",
                text=text,
                trace_ids=[path.path_id] if path.path_id else [],
                evidence_ids=list(path.evidence_refs),
                confidence="medium",
            )
        )
    for event in _bounded(payload.mechanism_summary.trigger_events, max(1, limit // 3)):
        units.append(
            DraftUnit(
                unit_id=f"unit:mechanism:trigger:{event.event_id}",
                section_role="mechanism",
                text=f"[{event.event_id}] {event.time_anchor} {event.description}",
                trace_ids=[event.event_id] if event.event_id else [],
                claim_ids=list(event.linked_claim_ids),
                evidence_ids=list(event.evidence_refs),
                confidence="medium",
            )
        )
    for shift in _bounded(payload.mechanism_summary.phase_shifts, max(1, limit // 3)):
        units.append(
            DraftUnit(
                unit_id=f"unit:mechanism:shift:{shift.phase_id}",
                section_role="mechanism",
                text=f"[{shift.phase_id}] {shift.from_phase} -> {shift.to_phase}：{shift.reason}",
                trace_ids=[shift.phase_id] if shift.phase_id else [],
                evidence_ids=list(shift.evidence_refs),
                confidence="medium",
            )
        )
    for bridge in _bounded(payload.mechanism_summary.bridge_nodes, max(1, limit // 4)):
        units.append(
            DraftUnit(
                unit_id=f"unit:mechanism:bridge:{bridge.node_id}",
                section_role="mechanism",
                text=f"[{bridge.node_id}] 桥接节点 {bridge.actor_id} @ {bridge.platform}：{bridge.bridge_role}",
                trace_ids=[bridge.node_id] if bridge.node_id else [],
                claim_ids=list(bridge.linked_claim_ids),
                evidence_ids=list(bridge.evidence_refs),
                confidence="medium",
            )
        )
    return units


def _build_risk_units(payload: ReportIR, limit: int) -> List[DraftUnit]:
    units: List[DraftUnit] = []
    for risk in _bounded(payload.risk_register.risks, limit):
        text = (
            f"[{risk.risk_id}] {risk.risk_type}（{risk.severity}）：{risk.spread_condition}"
            f"（claims={_join_ids(risk.trigger_claim_ids, 3)}; evidence={_join_ids(risk.trigger_evidence_ids, 3)}）"
        )
        units.append(
            DraftUnit(
                unit_id=f"unit:risks:{risk.risk_id}",
                section_role="risks",
                text=text,
                claim_ids=list(risk.trigger_claim_ids),
                evidence_ids=list(risk.trigger_evidence_ids),
                risk_ids=[risk.risk_id],
                confidence="high" if (risk.trigger_claim_ids or risk.trigger_evidence_ids) else "medium",
            )
        )
    return units


def _build_recommendation_units(payload: ReportIR, limit: int) -> List[DraftUnit]:
    units: List[DraftUnit] = []
    claim_lookup = _claim_map(payload)
    for item in _bounded(payload.recommendation_candidates.items, limit):
        evidence_ids: List[str] = []
        for claim_id in item.support_claim_ids:
            claim = claim_lookup.get(claim_id)
            if claim is not None:
                evidence_ids.extend(claim.support_evidence_ids[:2])
        text = f"[{item.candidate_id}] {item.action}：{item.rationale}（claims={_join_ids(item.support_claim_ids, 3)}）"
        units.append(
            DraftUnit(
                unit_id=f"unit:recommendations:{item.candidate_id}",
                section_role="recommendations",
                text=text,
                trace_ids=[item.candidate_id] if item.candidate_id else [],
                claim_ids=list(item.support_claim_ids),
                evidence_ids=list(dict.fromkeys(evidence_ids)),
                confidence="medium",
            )
        )
    return units


def _build_unresolved_units(payload: ReportIR, limit: int) -> List[DraftUnit]:
    units: List[DraftUnit] = []
    for item in _bounded(payload.unresolved_points.items, limit):
        text = f"[{item.item_id}] {item.statement}：{item.reason}（claims={_join_ids(item.related_claim_ids, 3)}; evidence={_join_ids(item.related_evidence_ids, 3)}）"
        units.append(
            DraftUnit(
                unit_id=f"unit:unresolved:{item.item_id}",
                section_role="unresolved",
                text=text,
                claim_ids=list(item.related_claim_ids),
                evidence_ids=list(item.related_evidence_ids),
                unresolved_point_ids=[item.item_id],
                confidence="low",
                is_unresolved=True,
            )
        )
    return units


def _build_ledger_units(payload: ReportIR, limit: int) -> List[DraftUnit]:
    units: List[DraftUnit] = []
    for entry in _bounded(payload.evidence_ledger.entries, limit):
        text = f"[{entry.evidence_id}] {entry.title}{f' ({entry.url})' if entry.url else ''}"
        units.append(
            DraftUnit(
                unit_id=f"unit:ledger:{entry.evidence_id}",
                section_role="ledger",
                text=text,
                evidence_ids=[entry.evidence_id],
                confidence=str(entry.confidence or "medium").strip() or "medium",
            )
        )
        if entry.snippet:
            units.append(
                DraftUnit(
                    unit_id=f"unit:ledger:{entry.evidence_id}:snippet",
                    section_role="ledger",
                    text=str(entry.snippet).strip(),
                    evidence_ids=[entry.evidence_id],
                    confidence=str(entry.confidence or "medium").strip() or "medium",
                )
            )
    return units


def compile_heading_units(plan_item: CompilerSectionPlanItem) -> List[DraftUnit]:
    return [
        DraftUnit(
            unit_id=f"heading:{plan_item.section_id}",
            section_role=plan_item.section_id,
            text=f"## {plan_item.title}",
            confidence="high",
        )
    ]


def compile_summary_units(payload: ReportIR, plan_item: CompilerSectionPlanItem) -> List[DraftUnit]:
    _ = plan_item
    return _build_summary_units(payload)


def compile_transition_units(payload: ReportIR, plan_item: CompilerSectionPlanItem) -> List[DraftUnit]:
    if plan_item.section_id == "timeline" and payload.timeline.events:
        return [
            DraftUnit(
                unit_id="transition:timeline",
                section_role="timeline",
                text=f"{payload.meta.time_scope.start or '本周期'} 至 {payload.meta.time_scope.end or payload.meta.time_scope.start or '当前'} 的关键节点如下。",
                trace_ids=[payload.timeline.events[0].event_id] if payload.timeline.events[0].event_id else [],
                evidence_ids=list(payload.timeline.events[0].support_evidence_ids[:1]),
                confidence="medium",
            )
        ]
    if plan_item.section_id == "agenda" and payload.agenda_frame_map.frames:
        frame = payload.agenda_frame_map.frames[0]
        return [
            DraftUnit(
                unit_id="transition:agenda",
                section_role="agenda",
                text="以下议题与框架对象只描述问题界定、责任归因与补救路径，不扩展到未登记解释。",
                trace_ids=[frame.frame_id] if frame.frame_id else [],
                evidence_ids=list(frame.source_refs[:1]),
                confidence="medium",
            )
        ]
    if plan_item.section_id == "actors" and payload.stance_matrix.rows:
        row = payload.stance_matrix.rows[0]
        return [
            DraftUnit(
                unit_id="transition:actors",
                section_role="actors",
                text="以下主体判断仅覆盖已登记主体与证据绑定，不扩展到未登记群体。",
                stance_row_ids=[row.actor_id],
                evidence_ids=list(row.support_evidence_ids[:1]),
                confidence="medium",
            )
        ]
    if plan_item.section_id == "risks" and payload.risk_register.risks:
        risk = payload.risk_register.risks[0]
        return [
            DraftUnit(
                unit_id="transition:risks",
                section_role="risks",
                text="风险判断先列触发链，再说明仍受哪些边界约束。",
                risk_ids=[risk.risk_id],
                claim_ids=list(risk.trigger_claim_ids[:1]),
                evidence_ids=list(risk.trigger_evidence_ids[:1]),
                confidence="medium",
            )
        ]
    return []


def compile_evidence_anchor_units(payload: ReportIR, plan_item: CompilerSectionPlanItem) -> List[DraftUnit]:
    if plan_item.section_id == "claims":
        return _build_claim_units(payload, max(6, min(12, plan_item.target_words // 40)))
    if plan_item.section_id == "agenda":
        return _build_agenda_units(payload, max(4, min(10, plan_item.target_words // 45)))
    if plan_item.section_id == "timeline":
        return _build_timeline_units(payload, max(4, min(10, plan_item.target_words // 45)))
    if plan_item.section_id == "actors":
        return _build_actor_units(payload, max(4, min(10, plan_item.target_words // 45)))
    if plan_item.section_id == "conflicts":
        return _build_conflict_units(payload, max(4, min(10, plan_item.target_words // 45)))
    if plan_item.section_id == "mechanism":
        return _build_mechanism_units(payload, max(4, min(10, plan_item.target_words // 45)))
    if plan_item.section_id == "ledger":
        return _build_ledger_units(payload, 10)
    return []


def compile_risk_statement_units(payload: ReportIR, plan_item: CompilerSectionPlanItem) -> List[DraftUnit]:
    if plan_item.section_id != "risks":
        return []
    return _build_risk_units(payload, max(4, min(8, plan_item.target_words // 45)))


def compile_recommendation_units(payload: ReportIR, plan_item: CompilerSectionPlanItem) -> List[DraftUnit]:
    if plan_item.section_id != "recommendations":
        return []
    return _build_recommendation_units(payload, 6)


def compile_closing_units(payload: ReportIR, plan_item: CompilerSectionPlanItem) -> List[DraftUnit]:
    if plan_item.section_id == "unresolved":
        return _build_unresolved_units(payload, 8)
    return []


def compile_section_draft_units(
    ir: ReportIR | Dict[str, Any],
    section: CompilerSectionPlanItem | Dict[str, Any],
) -> List[DraftUnit]:
    payload = _ensure_ir(ir)
    plan_item = section if isinstance(section, CompilerSectionPlanItem) else CompilerSectionPlanItem.model_validate(section or {})
    heading_units = compile_heading_units(plan_item)
    transition_units = compile_transition_units(payload, plan_item)
    summary_units = compile_summary_units(payload, plan_item) if plan_item.section_id == "executive_summary" else []
    evidence_units = compile_evidence_anchor_units(payload, plan_item)
    risk_units = compile_risk_statement_units(payload, plan_item)
    recommendation_units = compile_recommendation_units(payload, plan_item)
    closing_units = compile_closing_units(payload, plan_item)
    units: List[DraftUnit] = [
        *heading_units,
        *transition_units,
        *summary_units,
        *evidence_units,
        *risk_units,
        *recommendation_units,
        *closing_units,
    ]
    return units


def compile_draft_units(
    ir: ReportIR | Dict[str, Any],
    section_plan: SectionPlan | Dict[str, Any],
) -> DraftBundle:
    payload = _ensure_ir(ir)
    plan = section_plan if isinstance(section_plan, SectionPlan) else SectionPlan.model_validate(section_plan or {})
    units: List[DraftUnit] = []
    for section in plan.sections:
        units.extend(compile_section_draft_units(payload, section))
    return DraftBundle(
        policy_version=POLICY_VERSION,
        units=units,
        section_order=[section.section_id for section in plan.sections],
        metadata={
            "claim_count": len(payload.claim_set.claims),
            "evidence_count": len(payload.evidence_ledger.entries),
            "agenda_issue_count": len(payload.agenda_frame_map.issues),
            "agenda_frame_count": len(payload.agenda_frame_map.frames),
            "conflict_edge_count": len(payload.conflict_map.edges),
            "mechanism_path_count": len(payload.mechanism_summary.amplification_paths),
            "risk_count": len(payload.risk_register.risks),
            "utility_decision": str(payload.utility_assessment.decision or "").strip(),
            "policy_version": POLICY_VERSION,
        },
    )


def _bundle_from_any(value: Any) -> DraftBundle | StyledDraftBundle:
    if isinstance(value, (DraftBundle, StyledDraftBundle)):
        return value
    if isinstance(value, dict) and "style_id" in value:
        return StyledDraftBundle.model_validate(value)
    return DraftBundle.model_validate(value or {})


def _known_trace_ids(payload: ReportIR) -> set[str]:
    ids = set()
    ids.update(claim.claim_id for claim in payload.claim_set.claims)
    ids.update(issue.issue_id for issue in payload.agenda_frame_map.issues)
    ids.update(attribute.attribute_id for attribute in payload.agenda_frame_map.attributes)
    ids.update(edge.edge_id for edge in payload.agenda_frame_map.issue_attribute_edges)
    ids.update(frame.frame_id for frame in payload.agenda_frame_map.frames)
    ids.update(shift.shift_id for shift in payload.agenda_frame_map.frame_shifts)
    ids.update(claim.claim_id for claim in payload.conflict_map.claims)
    ids.update(target.target_id for target in payload.conflict_map.targets)
    ids.update(argument.argument_id for argument in payload.conflict_map.arguments)
    ids.update(edge.edge_id for edge in payload.conflict_map.support_edges)
    ids.update(edge.edge_id for edge in payload.conflict_map.attack_edges)
    ids.update(edge.edge_id for edge in payload.conflict_map.edges)
    ids.update(entry.evidence_id for entry in payload.evidence_ledger.entries)
    ids.update(risk.risk_id for risk in payload.risk_register.risks)
    ids.update(item.item_id for item in payload.unresolved_points.items)
    ids.update(item.candidate_id for item in payload.recommendation_candidates.items)
    ids.update(row.actor_id for row in payload.stance_matrix.rows)
    ids.update(actor.actor_id for actor in payload.conflict_map.actor_positions)
    ids.update(event.event_id for event in payload.timeline.events)
    ids.update(path.path_id for path in payload.mechanism_summary.amplification_paths)
    ids.update(event.event_id for event in payload.mechanism_summary.trigger_events)
    ids.update(shift.phase_id for shift in payload.mechanism_summary.phase_shifts)
    ids.update(bridge.bridge_id for bridge in payload.mechanism_summary.cross_platform_bridges)
    ids.update(node.node_id for node in payload.mechanism_summary.bridge_nodes)
    ids.update(candidate.cause_event_id for candidate in payload.mechanism_summary.cause_candidates if candidate.cause_event_id)
    ids.update(candidate.effect_event_id for candidate in payload.mechanism_summary.cause_candidates if candidate.effect_event_id)
    ids.update(transfer.transfer_id for transfer in payload.mechanism_summary.cross_platform_transfers)
    ids.update(carrier.carrier_id for carrier in payload.mechanism_summary.narrative_carriers)
    ids.update(lag.refutation_id for lag in payload.mechanism_summary.refutation_lags)
    return ids


class ConformanceExecutor:
    def __init__(self, payload: ReportIR, registry: ConformancePolicyRegistry) -> None:
        self.payload = payload
        self.registry = registry
        self.claim_lookup = {claim.claim_id: claim for claim in payload.claim_set.claims}
        self.risk_lookup = {risk.risk_id: risk for risk in payload.risk_register.risks}
        self.recommendation_lookup = {item.candidate_id: item for item in payload.recommendation_candidates.items}

    def check_trace_projection(
        self,
        *,
        line: str,
        section_role: str,
        trace_ids: List[str],
        known_ids: set[str],
        issue_prefix: str,
        start_index: int,
    ) -> tuple[List[FactualConformanceIssue], int]:
        issues: List[FactualConformanceIssue] = []
        issue_index = int(start_index)
        unknown_ids = [item for item in trace_ids if item not in known_ids]
        if unknown_ids:
            issue_index += 1
            issues.append(
                FactualConformanceIssue(
                    issue_id=f"{issue_prefix}_unknown_trace:{issue_index}",
                    issue_type="unknown_trace",
                    message="当前内容包含 ReportIR 之外的 trace id。",
                    section_role=section_role,
                    sentence=line,
                    trace_ids=unknown_ids,
                    suggested_action="请删除未知 trace 或回退到已登记 source。",
                )
            )
        return issues, issue_index

    def check_claim_gate_boundary(
        self,
        *,
        line: str,
        section_role: str,
        trace_ids: List[str],
        issue_prefix: str,
        start_index: int,
    ) -> tuple[List[FactualConformanceIssue], int]:
        issues: List[FactualConformanceIssue] = []
        issue_index = int(start_index)
        for trace_id in trace_ids:
            claim = self.claim_lookup.get(trace_id)
            if claim is None:
                continue
            if claim.status in {"unverified", "conflicting", "partially_supported"}:
                baseline = _baseline_signature(self.payload, section_role=section_role, trace_ids=[trace_id], registry=self.registry)
                actual = _semantic_signature(line, section_role=section_role, trace_ids=[trace_id], payload=self.payload, registry=self.registry)
                if _level_index(self.registry, "assertion_certainty", actual["assertion_certainty"]) > _level_index(self.registry, "assertion_certainty", baseline["assertion_certainty"]):
                    issue_index += 1
                    issues.append(
                        FactualConformanceIssue(
                            issue_id=f"{issue_prefix}_claim_gate:{issue_index}",
                            issue_type="claim_gate_violation",
                            message="未完全冻结的 claim 被写成了确定判断。",
                            section_role=section_role,
                            sentence=line,
                            trace_ids=[trace_id],
                            semantic_dimension="assertion_certainty",
                            before_level=baseline["assertion_certainty"],
                            after_level=actual["assertion_certainty"],
                            suggested_action="请把确定判断降级为观察、线索或条件性表达。",
                        )
                    )
                    break
        return issues, issue_index

    def check_risk_and_recommendation_bounds(
        self,
        *,
        line: str,
        section_role: str,
        trace_ids: List[str],
        issue_prefix: str,
        start_index: int,
    ) -> tuple[List[FactualConformanceIssue], int]:
        issues: List[FactualConformanceIssue] = []
        issue_index = int(start_index)
        risk_ids = set(self.risk_lookup)
        recommendation_ids = set(self.recommendation_lookup)
        if section_role == "risks" and not any(item in risk_ids for item in trace_ids):
            baseline = _baseline_signature(self.payload, section_role=section_role, trace_ids=trace_ids, registry=self.registry)
            actual = _semantic_signature(line, section_role=section_role, trace_ids=trace_ids, payload=self.payload, registry=self.registry)
            if _level_index(self.registry, "risk_maturity", actual["risk_maturity"]) > _level_index(self.registry, "risk_maturity", baseline["risk_maturity"]):
                issue_index += 1
                issues.append(
                    FactualConformanceIssue(
                        issue_id=f"{issue_prefix}_risk:{issue_index}",
                        issue_type="risk_boundary_violation",
                        message="风险表述越过了已登记 risk 边界。",
                        section_role=section_role,
                        sentence=line,
                        trace_ids=list(trace_ids),
                        semantic_dimension="risk_maturity",
                        before_level=baseline["risk_maturity"],
                        after_level=actual["risk_maturity"],
                        suggested_action="请降低风险成熟度，或补充已登记 risk 绑定。",
                    )
                )
        if section_role == "recommendations":
            if not trace_ids:
                issue_index += 1
                issues.append(
                    FactualConformanceIssue(
                        issue_id=f"{issue_prefix}_recommendation:{issue_index}",
                        issue_type="recommendation_boundary_violation",
                        message="建议表达缺少任何 support trace。",
                        section_role=section_role,
                        sentence=line,
                        trace_ids=[],
                        semantic_dimension="action_force",
                        before_level="monitor",
                        after_level="recommend",
                        suggested_action="请绑定 recommendation 或 claim trace。",
                    )
                )
            elif not any(item in recommendation_ids for item in trace_ids):
                baseline = _baseline_signature(self.payload, section_role=section_role, trace_ids=trace_ids, registry=self.registry)
                actual = _semantic_signature(line, section_role=section_role, trace_ids=trace_ids, payload=self.payload, registry=self.registry)
                if _level_index(self.registry, "action_force", actual["action_force"]) > _level_index(self.registry, "action_force", baseline["action_force"]):
                    issue_index += 1
                    issues.append(
                        FactualConformanceIssue(
                            issue_id=f"{issue_prefix}_recommendation:{issue_index}",
                            issue_type="recommendation_boundary_violation",
                            message="建议表达越过了已登记 recommendation 边界。",
                            section_role=section_role,
                            sentence=line,
                            trace_ids=list(trace_ids),
                            semantic_dimension="action_force",
                            before_level=baseline["action_force"],
                            after_level=actual["action_force"],
                            suggested_action="请降低动作强制性，或绑定已登记 recommendation。",
                        )
                    )
        return issues, issue_index

    def check_strength_lattice(
        self,
        *,
        line: str,
        section_role: str,
        trace_ids: List[str],
        issue_prefix: str,
        start_index: int,
    ) -> tuple[List[FactualConformanceIssue], List[SemanticDelta], int]:
        baseline = _semantic_state_from_levels(
            _baseline_signature(self.payload, section_role=section_role, trace_ids=trace_ids, registry=self.registry)
        )
        actual = _semantic_state_from_levels(
            _semantic_signature(line, section_role=section_role, trace_ids=trace_ids, payload=self.payload, registry=self.registry)
        )
        issues, deltas, next_index = _build_escalation_issues(
            registry=self.registry,
            baseline=baseline,
            actual=actual,
            line=line,
            section_role=section_role,
            trace_ids=trace_ids,
            issue_prefix=issue_prefix,
            start_index=start_index,
        )
        support_issues = judge_evidence_support(
            self.payload,
            section_role=section_role,
            trace_ids=trace_ids,
            baseline=baseline,
            actual=actual,
        )
        if support_issues:
            next_index = max(next_index, start_index)
            for item in support_issues:
                next_index += 1
                issues.append(item.model_copy(update={"issue_id": f"{issue_prefix}_support:{next_index}"}))
        return issues, deltas, next_index


def run_factual_conformance(
    ir: ReportIR | Dict[str, Any],
    draft_or_markdown: DraftBundle | StyledDraftBundle | Dict[str, Any] | str,
) -> FactualConformanceResult:
    payload = _ensure_ir(ir)
    registry = build_conformance_policy_registry()
    executor = ConformanceExecutor(payload, registry)
    issues: List[FactualConformanceIssue] = []
    semantic_deltas: List[SemanticDelta] = []
    known_ids = _known_trace_ids(payload)
    if isinstance(draft_or_markdown, str):
        heading_set = {"执行摘要", "事实断言", "时间线", "主体与立场", "冲突与收敛", "传播机制", "风险登记", "建议动作", "待核验点", "证据账本", "编译备注"}
        heading_role_map = {
            "执行摘要": "executive_summary",
            "事实断言": "claims",
            "时间线": "timeline",
            "主体与立场": "actors",
            "冲突与收敛": "conflicts",
            "传播机制": "mechanism",
            "风险登记": "risks",
            "建议动作": "recommendations",
            "待核验点": "unresolved",
            "证据账本": "ledger",
            "编译备注": "markdown",
        }
        lines = [line.strip() for line in str(draft_or_markdown or "").splitlines() if line.strip()]
        issue_index = 0
        current_section_role = "markdown"
        for line in lines:
            if line.startswith("## "):
                heading = line.lstrip("#").strip()
                current_section_role = heading_role_map.get(heading, "markdown")
                continue
            if line.startswith("#"):
                continue
            if line.startswith("::figure{"):
                continue
            trace_ids = _extract_leading_trace_ids(line)
            trace_ids = [item for item in trace_ids if item not in heading_set]
            text_without_prefix = re.sub(r"^\s*[-*]\s*", "", line)
            if text_without_prefix.startswith("部分断言缺少证据绑定") or text_without_prefix.startswith("部分风险缺少断言或证据引用"):
                continue
            if trace_ids:
                extra_issues, issue_index = executor.check_trace_projection(
                    line=line,
                    section_role=current_section_role,
                    trace_ids=trace_ids,
                    known_ids=known_ids,
                    issue_prefix="markdown",
                    start_index=issue_index,
                )
                issues.extend(extra_issues)
                extra_issues, issue_index = executor.check_claim_gate_boundary(
                    line=line,
                    section_role=current_section_role,
                    trace_ids=trace_ids,
                    issue_prefix="markdown",
                    start_index=issue_index,
                )
                issues.extend(extra_issues)
                extra_issues, issue_index = executor.check_risk_and_recommendation_bounds(
                    line=line,
                    section_role=current_section_role,
                    trace_ids=trace_ids,
                    issue_prefix="markdown",
                    start_index=issue_index,
                )
                issues.extend(extra_issues)
                extra_issues, deltas, issue_index = executor.check_strength_lattice(
                    line=line,
                    section_role=current_section_role,
                    trace_ids=trace_ids,
                    issue_prefix="markdown",
                    start_index=issue_index,
                )
                issues.extend(extra_issues)
                semantic_deltas.extend(deltas)
            elif not line.startswith(">") and not line.startswith("当前"):
                issue_index += 1
                issues.append(
                    FactualConformanceIssue(
                        issue_id=f"markdown_untraceable:{issue_index}",
                        issue_type="untraceable_sentence",
                        message="Markdown 存在无法回投到 ReportIR 的句子。",
                        sentence=line,
                    )
                )
        return FactualConformanceResult(
            passed=not issues,
            policy_version=registry.policy_version,
            stage="final_markdown",
            can_auto_recover=not any(item.severity == "high" for item in issues),
            requires_human_review=any(item.issue_type in {"strength_escalation", "risk_boundary_violation", "recommendation_boundary_violation"} for item in issues),
            issues=issues,
            semantic_deltas=semantic_deltas,
            metadata={
                "mode": "markdown",
                "line_count": len(lines),
                "novel_sentence_count": len([item for item in issues if item.issue_type == "untraceable_sentence"]),
            },
        )

    bundle = _bundle_from_any(draft_or_markdown)
    issue_index = 0
    for unit in bundle.units:
        if unit.text.startswith("## "):
            continue
        trace_ids = _collect_trace_ids_from_unit(unit)
        if not trace_ids:
            issue_index += 1
            issues.append(
                FactualConformanceIssue(
                    issue_id=f"unit_missing_trace:{issue_index}",
                    issue_type="missing_trace",
                    message="DraftUnit 缺少 trace 绑定。",
                    section_role=unit.section_role,
                    sentence=unit.text,
                )
            )
            continue
        extra_issues, issue_index = executor.check_trace_projection(
            line=unit.text,
            section_role=unit.section_role,
            trace_ids=trace_ids,
            known_ids=known_ids,
            issue_prefix="unit",
            start_index=issue_index,
        )
        issues.extend(extra_issues)
        extra_issues, issue_index = executor.check_claim_gate_boundary(
            line=unit.text,
            section_role=unit.section_role,
            trace_ids=trace_ids,
            issue_prefix="unit",
            start_index=issue_index,
        )
        issues.extend(extra_issues)
        extra_issues, issue_index = executor.check_risk_and_recommendation_bounds(
            line=unit.text,
            section_role=unit.section_role,
            trace_ids=trace_ids,
            issue_prefix="unit",
            start_index=issue_index,
        )
        issues.extend(extra_issues)
        extra_issues, deltas, issue_index = executor.check_strength_lattice(
            line=unit.text,
            section_role=unit.section_role,
            trace_ids=trace_ids,
            issue_prefix="unit",
            start_index=issue_index,
        )
        issues.extend(extra_issues)
        semantic_deltas.extend(deltas)
    return FactualConformanceResult(
        passed=not issues,
        policy_version=registry.policy_version,
        stage="styled_draft" if isinstance(bundle, StyledDraftBundle) else "draft_bundle",
        can_auto_recover=not any(item.severity == "high" for item in issues),
        requires_human_review=any(item.issue_type in {"strength_escalation", "risk_boundary_violation", "recommendation_boundary_violation"} for item in issues),
        issues=issues,
        semantic_deltas=semantic_deltas,
        metadata={
            "mode": "styled_draft" if isinstance(bundle, StyledDraftBundle) else "draft_bundle",
            "unit_count": len(bundle.units),
            "issue_count": len(issues),
            "issue_types": [item.issue_type for item in issues],
        },
    )


def run_stylistic_rewrite(
    ir: ReportIR | Dict[str, Any],
    draft_bundle: DraftBundle | Dict[str, Any],
    style_context: CompilerWriterContext | Dict[str, Any],
) -> StyledDraftBundle:
    _ = _ensure_ir(ir)
    bundle = draft_bundle if isinstance(draft_bundle, DraftBundle) else DraftBundle.model_validate(draft_bundle or {})
    context = style_context if isinstance(style_context, CompilerWriterContext) else CompilerWriterContext.model_validate(style_context or {})
    registry = build_conformance_policy_registry()
    rewritten_units: List[DraftUnit] = []
    rewrite_ops: List[str] = []
    rewrite_diffs: List[RewriteDiff] = []
    for unit in bundle.units:
        original_text = str(unit.text or "").strip()
        text = original_text
        raw_ops: List[str] = []
        if text.startswith("## "):
            rewritten_units.append(unit)
            continue
        text = re.sub(r"\s+", " ", text).strip()
        if text != original_text:
            raw_ops.append("compress")
        if unit.section_role == "executive_summary" and not text.startswith("- "):
            text = f"- {text}"
            raw_ops.append("paragraph_to_list")
        elif unit.section_role in {"claims", "timeline", "actors", "risks", "recommendations", "unresolved", "ledger"} and not text.startswith("- "):
            text = f"- {text}"
            raw_ops.append("paragraph_to_list")
        unit_ops = [op for op in raw_ops if op in registry.allowed_rewrite_ops]
        rewrite_ops.extend(unit_ops)
        rewritten_units.append(unit.model_copy(update={"text": text}))
        if text != original_text or unit_ops:
            rewrite_diffs.append(
                RewriteDiff(
                    before_unit_id=unit.unit_id,
                    after_unit_id=unit.unit_id,
                    ops=list(dict.fromkeys(unit_ops)),
                    semantic_fields_touched=["presentation_only"] if unit_ops else [],
                    lock_bypass_attempted=any(op in registry.disallowed_rewrite_ops or op not in registry.allowed_rewrite_ops for op in raw_ops),
                )
            )
    return StyledDraftBundle(
        units=rewritten_units,
        section_order=list(bundle.section_order),
        style_id=context.style_profile.style_id,
        rewrite_policy="presentation_only",
        policy_version=POLICY_VERSION,
        rewrite_ops=list(dict.fromkeys(rewrite_ops)),
        semantic_fields_locked=True,
        rewrite_diffs=rewrite_diffs,
        metadata={
            **dict(bundle.metadata or {}),
            "document_tone": context.style_profile.document_tone,
            "rewrite_policy": "presentation_only",
            "policy_version": POLICY_VERSION,
            "rewrite_ops": list(dict.fromkeys(rewrite_ops)),
            "rewrite_algebra": "presentation_only",
            "semantic_fields_locked": True,
        },
    )


def render_final_markdown(
    ir: ReportIR | Dict[str, Any],
    styled_bundle: StyledDraftBundle | Dict[str, Any],
    layout_plan: CompilerLayoutPlan | Dict[str, Any],
    *,
    title: str = "",
) -> str:
    payload = _ensure_ir(ir)
    bundle = styled_bundle if isinstance(styled_bundle, StyledDraftBundle) else StyledDraftBundle.model_validate(styled_bundle or {})
    _ = layout_plan if isinstance(layout_plan, CompilerLayoutPlan) else CompilerLayoutPlan.model_validate(layout_plan or {})
    safe_title = str(title or payload.meta.topic_label or payload.meta.topic_identifier or "专题报告").strip() or "专题报告"
    section_figures: Dict[str, List[str]] = {}
    for entry in payload.placement_plan.entries:
        section_figures.setdefault(str(entry.section_role or "").strip() or "claims", []).append(str(entry.figure_id or "").strip())
    lines: List[str] = [f"# {safe_title}", ""]
    if payload.meta.time_scope.start or payload.meta.time_scope.end:
        lines.extend([f"> 区间：{payload.meta.time_scope.start} -> {payload.meta.time_scope.end} | 模式：{payload.meta.mode}", ""])
    rendered_sections: set[str] = set()
    for unit in bundle.units:
        text = str(unit.text or "").rstrip()
        if not text:
            continue
        if not text.startswith("## "):
            trace_ids = _collect_trace_ids_from_unit(unit)
            if trace_ids and not re.match(r"^\s*[-*]\s*\[[^\]]+\]", text) and not re.match(r"^\[[^\]]+\]", text):
                if text.startswith("- "):
                    text = f"- [{trace_ids[0]}] {text[2:].lstrip()}"
                else:
                    text = f"[{trace_ids[0]}] {text}"
        lines.append(text)
        section_role = str(unit.section_role or "").strip()
        if section_role and section_role not in rendered_sections and section_role in section_figures:
            rendered_sections.add(section_role)
            lines.extend(["", *[f'::figure{{ref="{figure_id}"}}' for figure_id in section_figures.get(section_role, [])], ""])
    cleaned = "\n".join(lines).strip()
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    cleaned = apply_guardrails(cleaned, payload)
    cleaned = sanitize_public_markdown(cleaned)
    return cleaned.strip()


def compile_claim_draft(ir: ReportIR | Dict[str, Any], writer_context: CompilerWriterContext | Dict[str, Any]) -> str:
    payload = _ensure_ir(ir)
    context = writer_context if isinstance(writer_context, CompilerWriterContext) else CompilerWriterContext.model_validate(writer_context or {})
    section_plan = build_section_plan(payload, context.layout_plan, context.section_budget)
    draft_bundle = compile_draft_units(payload, section_plan)
    styled_bundle = run_stylistic_rewrite(payload, draft_bundle, context)
    return render_final_markdown(payload, styled_bundle, context.layout_plan, title=context.topic)


def run_factual_critic(ir: ReportIR | Dict[str, Any], draft: str) -> CompilerCriticResult:
    payload = _ensure_ir(ir)
    conformance = run_factual_conformance(payload, draft)
    missing_support_claims = [
        claim.claim_id for claim in payload.claim_set.claims if claim.status == "supported" and not claim.support_evidence_ids
    ]
    missing_risk_refs = [
        risk.risk_id for risk in payload.risk_register.risks if not risk.trigger_claim_ids and not risk.trigger_evidence_ids
    ]
    issues = list(conformance.issues)
    issue_names = [f"{item.issue_type}:{item.issue_id}" for item in issues]
    issue_names.extend([f"missing_support:{claim_id}" for claim_id in missing_support_claims])
    issue_names.extend([f"missing_risk_ref:{risk_id}" for risk_id in missing_risk_refs])
    return CompilerCriticResult(
        passed=not issue_names,
        issues=issue_names,
        metadata={
            "missing_support_claims": missing_support_claims,
            "missing_risk_refs": missing_risk_refs,
            "conformance_issues": [item.model_dump() for item in issues],
        },
    )


def run_style_critic(ir: ReportIR | Dict[str, Any], draft: str) -> CompilerCriticResult:
    payload = _ensure_ir(ir)
    headings = [line for line in str(draft or "").splitlines() if line.startswith("## ")]
    required_sections = ["## 执行摘要", "## 事实断言"]
    if payload.risk_register.risks:
        required_sections.append("## 风险登记")
    missing_sections = [section for section in required_sections if section not in headings]
    return CompilerCriticResult(
        passed=not missing_sections,
        issues=[f"missing_section:{section}" for section in missing_sections],
        metadata={
            "missing_sections": missing_sections,
            "topic": payload.meta.topic_label or payload.meta.topic_identifier,
        },
    )


def _strip_code_fences(markdown: str) -> str:
    text = str(markdown or "").strip()
    if not text:
        return ""
    fenced = re.match(r"```(?:markdown|md)?\s*(.*?)\s*```$", text, flags=re.S)
    return fenced.group(1).strip() if fenced else text


def sanitize_public_markdown(markdown: str) -> str:
    text = str(markdown or "").strip()
    if not text:
        return ""
    hidden_heading_patterns = [
        re.compile(r"^\s{0,3}#{2,6}\s*(待核验提醒|待核验点|待核验事项)\s*$"),
        re.compile(r"^\s{0,3}#{2,6}\s*(证据边界|边界说明|校验记录)\s*$"),
    ]
    lines = text.splitlines()
    sanitized: List[str] = []
    skipping_hidden_section = False
    for line in lines:
        stripped = str(line or "").strip()
        if any(pattern.match(stripped) for pattern in hidden_heading_patterns):
            skipping_hidden_section = True
            continue
        if skipping_hidden_section and stripped.startswith("#"):
            skipping_hidden_section = False
        if skipping_hidden_section:
            continue
        if re.search(r"(待核验提醒|待核验点|待核验事项|当前结果没有单独列出待核验点)", stripped):
            continue
        sanitized.append(line)
    text = "\n".join(sanitized)
    replacements = {
        "相关传播动因仍待核验": "相关传播动因暂不作确定判断",
        "其传播动因仍待核验": "其传播动因暂不作确定判断",
        "启动前需补充核验：": "当前不建议直接启动：",
        "相关前提仍待补充核验。": "",
        "仍待核验": "暂不作确定判断",
        "待核验": "暂不作确定判断",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)
    text = re.sub(r"[；;]\s*(?=[。.!！?？]|$)", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


def apply_guardrails(markdown: str, ir: ReportIR | Dict[str, Any]) -> str:
    payload = _ensure_ir(ir)
    text = str(markdown or "")
    if payload.unresolved_points.items:
        text = re.sub(r"(因此|所以|由此可见)([^。；\n]{0,32})待核验", r"\1\2暂不作确定判断", text)
    if re.search(r"(政策|新规|规定)[^。；\n]{0,12}(引爆点|引爆节点)", text):
        text = re.sub(r"(政策|新规|规定)([^。；\n]{0,12})(引爆点|引爆节点)", r"\1\2关键节点", text)
    return text


def sanitize_and_finalize(
    ir: ReportIR | Dict[str, Any],
    draft: str,
    critic_outputs: Dict[str, CompilerCriticResult | Dict[str, Any]],
) -> str:
    _ = _ensure_ir(ir)
    lines = [line.rstrip() for line in str(draft or "").splitlines()]
    cleaned = "\n".join(lines).strip()
    factual = critic_outputs.get("factual")
    style = critic_outputs.get("style")
    factual_result = factual if isinstance(factual, CompilerCriticResult) else CompilerCriticResult.model_validate(factual or {})
    style_result = style if isinstance(style, CompilerCriticResult) else CompilerCriticResult.model_validate(style or {})
    notes: List[str] = []
    for issue in factual_result.issues[:5]:
        if issue.startswith("missing_support:"):
            notes.append(f"部分断言缺少证据绑定：{issue.split(':', 1)[1]}")
        elif issue.startswith("missing_risk_ref:"):
            notes.append(f"部分风险缺少断言或证据引用：{issue.split(':', 1)[1]}")
    for issue in style_result.issues[:5]:
        if issue.startswith("missing_section:"):
            notes.append(f"文稿自动补齐仍缺章节：{issue.split(':', 1)[1]}")
    if notes:
        cleaned = "\n".join([cleaned, "", "## 编译备注", *[f"- {note}" for note in notes]]).strip()
    return cleaned


def finalize_markdown(
    ir: ReportIR | Dict[str, Any],
    draft: str,
    critic_outputs: Dict[str, CompilerCriticResult | Dict[str, Any]],
    *,
    title: str = "",
) -> str:
    payload = _ensure_ir(ir)
    cleaned = sanitize_and_finalize(payload, draft, critic_outputs)
    cleaned = _strip_code_fences(cleaned)
    cleaned = re.sub(r"<\s*(script|style|iframe|object|embed)[^>]*>.*?<\s*/\s*\1\s*>", "", cleaned, flags=re.I | re.S)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    if cleaned and not re.search(r"^\s*#\s+", cleaned, flags=re.M):
        safe_title = str(title or payload.meta.topic_label or payload.meta.topic_identifier or "专题报告").strip() or "专题报告"
        cleaned = f"# {safe_title}\n\n{cleaned}"
    cleaned = apply_guardrails(cleaned, payload)
    cleaned = sanitize_public_markdown(cleaned)
    return cleaned.strip()
