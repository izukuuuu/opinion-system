"""
deep_report/builder.py
======================
Deep Agents coordinator + subagents 配置的唯一 builder。

职责边界
--------
- 集中定义 coordinator 和所有 custom subagents 的 tools / skills / middleware / interrupt_on。
- subagent skills 通过显式 _SUBAGENT_SKILL_KEYS 映射附加，不再依赖 capability_manifest 的
  运行时投影（select_runtime_skill_ids / select_runtime_capability_ids）。
- coordinator skills 通过显式 preferred_skill_keys 列表附加。
- 不参与 LangGraph 拓扑决策；不包含任何 orchestrator_graph 的 state 类型。
- 闭包工具（save_structured_report / write_final_report / overwrite_report_cache）由
  service.py 构造后作为 extra_coordinator_tools 传入。
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, TypedDict

from deepagents import create_deep_agent

from ..capability_manifest import RUNTIME_COORDINATOR, RUNTIME_SUBAGENT
from ..runtime_infra import get_shared_report_checkpointer
from ..skills import select_report_skill_sources
from ..tools import select_report_tools
from ..tools.registry import READ_ONLY, get_report_tool_spec
from .assets import RUNTIME_STORE


# ---------------------------------------------------------------------------
# 每个 subagent 的 preferred_skill_keys（从 skill contracts 派生，硬编码在此）
# ---------------------------------------------------------------------------
_SUBAGENT_SKILL_KEYS: Dict[str, List[str]] = {
    "retrieval_router": ["retrieval-router-rules"],
    "archive_evidence_organizer": ["evidence-source-credibility"],
    "timeline_analyst": ["timeline-alignment-slicing"],
    "stance_conflict": ["subject-stance-merging"],
    "claim_actor_conflict": ["subject-stance-merging"],
    "propagation_analyst": ["propagation-explanation-framework", "chart-interpretation-guidelines"],
    "bertopic_evolution_analyst": ["bertopic-evolution-framework"],
    "decision_utility_judge": ["quality-validation-backlink"],
    "agenda_frame_builder": [],
    "validator": ["quality-validation-backlink"],
    "writer": [],
}

# coordinator 的 preferred_skill_keys
_COORDINATOR_SKILL_KEYS: List[str] = ["basic-analysis-framework", "sentiment-analysis-methodology"]


class ReportCoordinatorContext(TypedDict, total=False):
    topic_identifier: str
    topic_label: str
    start: str
    end: str
    mode: str
    thread_id: str
    task_id: str
    runtime_contract_version: str
    base_context_path: str
    task_contract: Dict[str, Any]


def _interrupt_on_for_coordinator_tools(tools: List[Any]) -> Dict[str, Any]:
    """为 coordinator tools 构建 interrupt_on 映射（写入类工具需要人工确认）。"""
    mapping: Dict[str, Any] = {}
    for tool in tools:
        tool_name = str(getattr(tool, "name", "") or "").strip()
        if not tool_name:
            continue
        if tool_name in {"write_final_report", "overwrite_report_cache"}:
            mapping[tool_name] = True
            continue
        try:
            spec = get_report_tool_spec(tool_name)
        except Exception:
            continue
        if spec.mutability != READ_ONLY:
            mapping[tool_name] = True
    return mapping


def _build_subagent_specs(
    *,
    skill_assets: Dict[str, Any],
    middleware_factory: Callable[[str], List[Any]],
) -> List[Dict[str, Any]]:
    """
    构建所有 custom subagent 规范列表（Deep Agents 官方 spec 格式）。

    每个 subagent 的 tools 来自 SUBAGENT_TOOL_ID_MAP（静态常量，已在 registry.py 中硬编码），
    每个 subagent 的 skills 来自 _SUBAGENT_SKILL_KEYS（显式映射，不经过 capability_manifest 投影）。
    """

    def _tools_for(agent_name: str) -> List[Any]:
        return select_report_tools(runtime_target=RUNTIME_SUBAGENT, agent_name=agent_name)

    def _skills_for(agent_name: str, toolset: List[Any]) -> List[str]:
        preferred = _SUBAGENT_SKILL_KEYS.get(agent_name, [])
        if not preferred:
            return []
        return select_report_skill_sources(
            skill_assets,
            available_tool_ids=[t.name for t in toolset if str(getattr(t, "name", "") or "").strip()],
            preferred_skill_keys=preferred,
            runtime_target=RUNTIME_SUBAGENT,
            agent_name=agent_name,
        )

    retrieval_tools = _tools_for("retrieval_router")
    evidence_tools = _tools_for("archive_evidence_organizer")
    agenda_tools = _tools_for("agenda_frame_builder")
    timeline_tools = _tools_for("timeline_analyst")
    stance_tools = _tools_for("stance_conflict")
    conflict_tools = _tools_for("claim_actor_conflict")
    propagation_tools = _tools_for("propagation_analyst")
    bertopic_tools = _tools_for("bertopic_evolution_analyst")
    utility_tools = _tools_for("decision_utility_judge")

    return [
        {
            "name": "retrieval_router",
            "description": "负责冻结任务边界、生成 task derivation / retrieval plan / dispatch quality，并诊断语料覆盖。task_contract 是唯一执行锚点，normalized_task 只保留为兼容视图。写入 /workspace/state/task_derivation.json、/workspace/state/task_derivation_proposal.json、/workspace/state/normalized_task.json、/workspace/state/retrieval_plan.json、/workspace/state/dispatch_quality.json 和 /workspace/state/corpus_coverage.json。",
            "system_prompt": (
                "你是任务规范化与覆盖诊断代理。先读取 /workspace/base_context.json，"
                "必须严格沿用其中 task_contract.topic_identifier / start / end / mode，禁止自行改写专题标识、时间窗或模式。"
                "调用 normalize_task 生成 task_derivation，只补充 topic / entities / keywords / platform_scope / mandatory_sections 等语义字段，"
                "再基于 analysis_question_set、coverage_expectation 与 inference_policy 归纳 retrieval plan，"
                "最后从 /workspace/state/task_contract.json 读取 contract_id，并调用 get_corpus_coverage(contract_id=..., retrieval_scope_json=..., filters_json=...) 区分'没有数据'与'没有发现'。"
                "把结果分别写入 /workspace/state/task_derivation.json、/workspace/state/task_derivation_proposal.json、/workspace/state/normalized_task.json、/workspace/state/retrieval_plan.json、/workspace/state/dispatch_quality.json 和 /workspace/state/corpus_coverage.json，"
                "并返回简短总结。默认策略是少调用、重研判。"
                "若目标文件已存在，先读取再使用 edit_file 更新，不要直接用 write_file 覆盖。"
            ),
            "tools": retrieval_tools,
            "middleware": middleware_factory("retrieval_router"),
            "skills": _skills_for("retrieval_router", retrieval_tools),
        },
        {
            "name": "archive_evidence_organizer",
            "description": "负责按任务意图召回证据卡，并写入 /workspace/state/evidence_cards.json。",
            "system_prompt": (
                "你是证据卡整理代理。请读取 /workspace/state/task_contract.json、/workspace/state/task_derivation.json、/workspace/state/normalized_task.json 和 /workspace/state/corpus_coverage.json。"
                "其中 task_contract 是唯一执行 authority，normalized_task 只用于调试和兼容展示。"
                "从 /workspace/state/task_contract.json 提取 contract_id，只使用 retrieve_evidence_cards(contract_id=..., retrieval_scope_json=..., filters_json=..., intent=...) 产出分页证据卡与反证卡。"
                "如果 corpus_coverage.coverage.readiness_flags 包含 no_records_in_scope，"
                "只允许生成一次空 evidence_cards.json，随后立即结束，不要继续换 intent 重试。"
                "把聚合后的结果写入 /workspace/state/evidence_cards.json，并返回摘要。"
                "不要回写长段原文，不要把数据库字段直接搬进文稿。"
                "若目标文件已存在，先读取再使用 edit_file 更新，不要直接用 write_file 覆盖。"
            ),
            "tools": evidence_tools,
            "middleware": middleware_factory("archive_evidence_organizer"),
            "skills": _skills_for("archive_evidence_organizer", evidence_tools),
        },
        {
            "name": "agenda_frame_builder",
            "description": "负责构建议题-属性-框架图，写入 /workspace/state/agenda_frame_map.json。",
            "system_prompt": (
                "你是议题与框架构建代理。请读取 /workspace/state/task_contract.json、/workspace/state/task_derivation.json、/workspace/state/normalized_task.json、/workspace/state/evidence_cards.json、"
                "/workspace/state/actor_positions.json、/workspace/state/conflict_map.json 与 /workspace/state/timeline_nodes.json，"
                "使用 build_agenda_frame_map 生成 issue nodes、attribute nodes、frame records、frame shifts 与 counter-frames。"
                "把结果写入 /workspace/state/agenda_frame_map.json，并返回简短总结。"
                "不要输出 prose 结论，不要把框架写成普通摘要。"
                "若目标文件已存在，先读取再使用 edit_file 更新，不要直接用 write_file 覆盖。"
            ),
            "tools": agenda_tools,
            "middleware": middleware_factory("agenda_frame_builder"),
            "skills": _skills_for("agenda_frame_builder", agenda_tools),
        },
        {
            "name": "timeline_analyst",
            "description": "负责构建时间线节点和图表就绪指标，写入 /workspace/state/timeline_nodes.json 与 /workspace/state/metrics_bundle.json。",
            "system_prompt": (
                "你是时间线分析代理。请读取 /workspace/state/task_contract.json、/workspace/state/task_derivation.json、/workspace/state/normalized_task.json 与 /workspace/state/evidence_cards.json，"
                "如果 evidence_cards.coverage.readiness_flags 包含 no_cards，则只生成结构化空结果并附带跳过原因，不要继续尝试深描。"
                "使用 build_event_timeline 生成带 support_evidence_ids 的时间线节点，"
                "再用 compute_report_metrics 输出 chart-ready 指标。"
                "结果写入 /workspace/state/timeline_nodes.json 和 /workspace/state/metrics_bundle.json，并返回简短总结。"
                "若目标文件已存在，先读取再使用 edit_file 更新，不要直接用 write_file 覆盖。"
            ),
            "tools": timeline_tools,
            "middleware": middleware_factory("timeline_analyst"),
            "skills": _skills_for("timeline_analyst", timeline_tools),
        },
        {
            "name": "stance_conflict",
            "description": "负责识别主体与立场关系，写入 /workspace/state/actor_positions.json。",
            "system_prompt": (
                "你是主体立场代理。请读取 /workspace/state/task_contract.json、/workspace/state/task_derivation.json、/workspace/state/normalized_task.json 与 /workspace/state/evidence_cards.json，"
                "只使用 extract_actor_positions 输出主体、立场变化、冲突关系。"
                "把结果写入 /workspace/state/actor_positions.json，并返回简短总结。"
                "若目标文件已存在，先读取再使用 edit_file 更新，不要直接用 write_file 覆盖。"
            ),
            "tools": stance_tools,
            "middleware": middleware_factory("stance_conflict"),
            "skills": _skills_for("stance_conflict", stance_tools),
        },
        {
            "name": "claim_actor_conflict",
            "description": "负责构建断言-主体冲突图，写入 /workspace/state/conflict_map.json。",
            "system_prompt": (
                "你是断言冲突构建代理。请读取 /workspace/state/task_contract.json、/workspace/state/task_derivation.json、/workspace/state/normalized_task.json、/workspace/state/evidence_cards.json、"
                "/workspace/state/actor_positions.json 和 /workspace/state/timeline_nodes.json，"
                "如果 evidence_cards.coverage.readiness_flags 包含 no_cards，或 actor_positions / timeline_nodes 明显为空，"
                "只生成结构化空图谱并说明 skip reason，不要反复重试。"
                "使用 build_claim_actor_conflict 生成 claim graph、actor positions、conflict edges 与 resolution states。"
                "把结果写入 /workspace/state/conflict_map.json，并返回简短总结。"
                "不要输出 prose 结论，不要默认把冲突写成已收敛。"
                "若目标文件已存在，先读取再使用 edit_file 更新，不要直接用 write_file 覆盖。"
            ),
            "tools": conflict_tools,
            "middleware": middleware_factory("claim_actor_conflict"),
            "skills": _skills_for("claim_actor_conflict", conflict_tools),
        },
        {
            "name": "propagation_analyst",
            "description": "负责解释传播指标、机制摘要与风险信号，写入 /workspace/state/mechanism_summary.json 与 /workspace/state/risk_signals.json。",
            "system_prompt": (
                "你是传播与风险代理。请读取 /workspace/state/task_contract.json、/workspace/state/task_derivation.json、/workspace/state/normalized_task.json、/workspace/state/evidence_cards.json、"
                "/workspace/state/metrics_bundle.json、/workspace/state/timeline_nodes.json 与 /workspace/state/conflict_map.json，"
                "如果 evidence_cards.coverage.readiness_flags 包含 no_cards，或 conflict_map / timeline_nodes 为空，"
                "只生成结构化空机制与空风险对象，并明确写出 skip reason。"
                "必要时补做 compute_report_metrics，使用 build_mechanism_summary 生成传播机制对象，再使用 detect_risk_signals 输出风险对象。"
                "把结果写入 /workspace/state/mechanism_summary.json 与 /workspace/state/risk_signals.json，并返回简短总结。"
                "若目标文件已存在，先读取再使用 edit_file 更新，不要直接用 write_file 覆盖。"
            ),
            "tools": propagation_tools,
            "middleware": middleware_factory("propagation_analyst"),
            "skills": _skills_for("propagation_analyst", propagation_tools),
        },
        {
            "name": "bertopic_evolution_analyst",
            "description": "负责读取 BERTopic 快照并生成主题演化洞察，写入 /workspace/state/bertopic_insight.json。",
            "system_prompt": (
                "你是 BERTopic 主题演化代理。请读取 /workspace/state/task_contract.json、/workspace/state/task_derivation.json 与 /workspace/state/normalized_task.json，"
                "先使用 get_bertopic_snapshot 读取当前专题在本地归档中的 BERTopic 结果，再使用 build_bertopic_insight 输出主题演化章节洞察。"
                "若快照不存在或可用主题为空，写出结构化空洞察并注明 skip reason，不要伪造演化趋势。"
                "把结果写入 /workspace/state/bertopic_insight.json，并返回简短总结。"
                "若目标文件已存在，先读取再使用 edit_file 更新，不要直接用 write_file 覆盖。"
            ),
            "tools": bertopic_tools,
            "middleware": middleware_factory("bertopic_evolution_analyst"),
            "skills": _skills_for("bertopic_evolution_analyst", bertopic_tools),
        },
        {
            "name": "decision_utility_judge",
            "description": "负责裁决当前判断对象是否具备进入正式文稿的决策可用性，写入 /workspace/state/utility_assessment.json。",
            "system_prompt": (
                "你是决策可用性裁决代理。请读取 /workspace/state/task_contract.json、/workspace/state/task_derivation.json、/workspace/state/normalized_task.json、/workspace/state/corpus_coverage.json、"
                "/workspace/state/evidence_cards.json、/workspace/state/conflict_map.json、/workspace/state/mechanism_summary.json、"
                "/workspace/state/agenda_frame_map.json、/workspace/state/risk_signals.json 与 /workspace/state/actor_positions.json，"
                "如果上游已经进入 empty_corpus / empty_evidence / insufficient_structure，"
                "必须把这些原因写入 utility assessment 的 missing_dimensions 或 fallback reason，不要假装仍可正常放行。"
                "使用 judge_decision_utility 产出 typed utility assessment。"
                "把结果写入 /workspace/state/utility_assessment.json，并返回简短总结。"
                "不要直接写正文，不要用 prose 代替结构化裁决。"
                "若目标文件已存在，先读取再使用 edit_file 更新，不要直接用 write_file 覆盖。"
            ),
            "tools": utility_tools,
            "middleware": middleware_factory("decision_utility_judge"),
            "skills": _skills_for("decision_utility_judge", utility_tools),
        },
    ]


def build_report_deep_agent(
    *,
    llm: Any,
    topic_identifier: str,
    topic_label: str,
    start_text: str,
    end_text: str,
    mode: str,
    thread_id: str,
    task_id: str,
    skill_assets: Dict[str, Any],
    memory_paths: Optional[List[str]] = None,
    runtime_backend: Any,
    extra_coordinator_tools: Optional[List[Any]] = None,
    middleware_factory: Callable[[str], List[Any]],
    coordinator_tool_round_limit: Optional[int] = None,
    subagent_tool_round_limit: Optional[int] = None,
    lifecycle_tracker: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    构建并返回 Deep Agents 总控代理（coordinator）及相关 runtime 资产。

    Parameters
    ----------
    llm
        LangChain 语言模型实例。
    topic_identifier / topic_label / start_text / end_text / mode
        报告任务元数据。
    thread_id / task_id
        运行时标识符。
    skill_assets
        由 build_report_skill_runtime_assets() 生成的完整 skill 资产包。
    memory_paths
        Deep Agents memory 路径列表（可为 None）。
    runtime_backend
        Deep Agents runtime backend 实例。
    extra_coordinator_tools
        由 service.py 构造的闭包工具列表（save_structured_report 等），因为这些工具
        close over 本地变量，必须由 service.py 传入。
    middleware_factory
        接受 agent_name: str，返回 middleware 列表的工厂函数。
        由 service.py 通过 _build_lifecycle_middleware 构建。
    coordinator_tool_round_limit / subagent_tool_round_limit
        工具回合上限（None = 不限制）。
    lifecycle_tracker
        可变的 tracker dict（由 service.py 构造后传入；builder 不创建新 tracker）。

    Returns
    -------
    dict with keys:
        agent                   — compiled deep agent coordinator
        coordinator_checkpointer — coordinator 的 checkpointer
        coordinator_runtime_profile — coordinator 的 runtime profile（用于构建 runnable config）
        prompt                  — 初始 user prompt 字符串
    """
    # --- coordinator tools ---------------------------------------------------
    core_tools = select_report_tools(runtime_target=RUNTIME_COORDINATOR)
    agent_tools = [*core_tools, *(extra_coordinator_tools or [])]

    # --- coordinator skills --------------------------------------------------
    coordinator_skills = select_report_skill_sources(
        skill_assets,
        available_tool_ids=[t.name for t in core_tools if str(getattr(t, "name", "") or "").strip()],
        preferred_skill_keys=_COORDINATOR_SKILL_KEYS,
        runtime_target=RUNTIME_COORDINATOR,
    ) or None

    # --- subagents -----------------------------------------------------------
    subagents = _build_subagent_specs(
        skill_assets=skill_assets,
        middleware_factory=middleware_factory,
    )

    # --- round limit text for prompts ----------------------------------------
    coordinator_limit_text = (
        f"本次总控允许的最大工具回合为 {int(coordinator_tool_round_limit)}，请把调用压缩在这个范围内。"
        if coordinator_tool_round_limit is not None
        else "本次总控默认不限制工具回合，但仍应尽量减少无效调用。"
    )
    subagent_limit_text = (
        f"各子代理默认工具回合上限为 {int(subagent_tool_round_limit)}。"
        if subagent_tool_round_limit is not None
        else "各子代理默认不限制工具回合，但仍应优先少调用、深研判。"
    )

    # --- checkpointer --------------------------------------------------------
    coordinator_checkpointer, coordinator_runtime_profile = get_shared_report_checkpointer(
        purpose="deep-report-coordinator"
    )

    # --- create coordinator agent --------------------------------------------
    agent = create_deep_agent(
        model=llm,
        tools=agent_tools,
        system_prompt=(
            "你是舆情报告总控代理。你的职责是规划任务、调用合适的子代理，并整理出完整结构化结果。"
            "你不能跳过证据回链，也不能在没有结构化对象的情况下声称任务完成。"
            "你必须优先使用 task 工具委派给专业子代理，而不是自己直接完成所有分析。"
            "默认策略是少调用、重研判：不必节省 token，但要控制调用次数，优先在单次回复里完成更深、更完整的归纳和判断。"
            "完成必要取证后，尽量减少碎片化 read_file / 重复小调用，优先一次性收口成完整结构化对象。"
            "调用 save_structured_report 前，先在单次回复里把对象整理完整；不要连续提交多个试探版本。"
            "本轮职责止于保存结构化对象。正式文稿编译、trace 校验、repair loop、语义审批和缓存写入由外层确定性图负责。"
            f"{coordinator_limit_text}"
            f"{subagent_limit_text}"
            "完成结构化保存后即可结束本轮，不要再额外调用最终写入类工具。"
        ),
        middleware=middleware_factory("report_coordinator"),
        subagents=subagents,
        skills=coordinator_skills,
        memory=memory_paths or None,
        context_schema=ReportCoordinatorContext,
        checkpointer=coordinator_checkpointer,
        store=RUNTIME_STORE,
        backend=runtime_backend,
        interrupt_on=_interrupt_on_for_coordinator_tools(agent_tools),
        debug=False,
        name="deep-report-coordinator",
    )

    # --- initial prompt ------------------------------------------------------
    prompt = (
        "请先使用 write_todos 建立总计划，再严格按以下流程执行，不要跳步，也不要在未调用工具的情况下直接结束：\n"
        "1. 使用 task 工具依次委派 retrieval_router、archive_evidence_organizer、"
        "agenda_frame_builder、timeline_analyst、stance_conflict、claim_actor_conflict、"
        "propagation_analyst、bertopic_evolution_analyst、decision_utility_judge。\n"
        "2. 确认 /workspace/state/ 下至少生成 task_contract、task_derivation、task_derivation_proposal、normalized_task、retrieval_plan、dispatch_quality、corpus_coverage、evidence_cards、timeline_nodes、metrics_bundle、actor_positions、conflict_map、mechanism_summary、risk_signals、bertopic_insight、utility_assessment。\n"
        "3. 先调用 build_section_packet 生成至少 overview、timeline、risk 三个章节材料包，并写入 /workspace/state/section_packets/*.json。\n"
        "4. 读取这些中间对象，汇总成完整结构化报告对象。\n"
        "5. 调用 save_structured_report 保存结构化对象。优先直接传 payload 对象，不要把整个结构化 JSON 再包成字符串。先整理好完整对象，再一次性提交，不要连续试探多个版本。对象必须包含：task、conclusion、timeline、subjects、stance_matrix、"
        "key_evidence、conflict_points、conflict_map、propagation_features、mechanism_summary、risk_judgement、unverified_points、suggested_actions、utility_assessment、citations、validation_notes。\n"
        "6. 保存成功后立即结束本轮。不要再生成 /workspace/state/report_draft.md、/workspace/state/claim_checks.json 或 /workspace/state/validation_notes.md；这些旧中间态已经被外层 graph compile 路径替代。\n"
        "默认风格：单次回复尽量研判深刻，不必节省 token，但要尽量减少调用次数。"
        f"本次总控最大工具回合：{int(coordinator_tool_round_limit) if coordinator_tool_round_limit is not None else '不限制'}；"
        f"子代理最大工具回合：{int(subagent_tool_round_limit) if subagent_tool_round_limit is not None else '不限制'}。"
        "完成必要读取后，优先一次性输出更完整的分析和结构，不要拆成很多次浅层补充。"
        "所有关键判断都要尽量带 citation_ids；如果证据不足，请进入 unverified_points。"
    )

    return {
        "agent": agent,
        "coordinator_checkpointer": coordinator_checkpointer,
        "coordinator_runtime_profile": coordinator_runtime_profile,
        "prompt": prompt,
    }


__all__ = ["ReportCoordinatorContext", "build_report_deep_agent"]
