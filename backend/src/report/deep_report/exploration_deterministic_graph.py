# -*- coding: utf-8 -*-
"""
deep_report/exploration_deterministic_graph.py
===============================================

确定性子代理调度图：将子代理委派从 LLM-driven coordinator 改为确定性 LangGraph 流程。

每个节点内部仍使用 LangChain agent（保留 skills/tools），但调度顺序由图结构决定，
而非依赖 LLM 的 prompt 理解。

执行层级：
  Tier 0: retrieval_router（无依赖）
      ↓
  Tier 1: [并行] archive_evidence_organizer + bertopic_evolution_analyst
      ↓
  Tier 2: [并行] timeline_analyst + stance_conflict
      ↓
  Tier 3: [并行] event_analyst + claim_actor_conflict
      ↓
  Tier 4: [并行] agenda_frame_builder + propagation_analyst
      ↓
  Tier 5: decision_utility_judge
      ↓
  Tier 6: writer（条件执行）
      ↓
  Tier 7: finalize（汇总 + 保存）
"""
from __future__ import annotations

import operator
from typing import Annotated, Any, Callable, Dict, List, Optional, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from ..capability_manifest import RUNTIME_SUBAGENT
from ..runtime_infra import get_shared_report_checkpointer, build_report_runnable_config
from ..tools import select_report_tools
from ..skills import select_report_skill_sources
from ..configs import get_subagent_skill_keys, get_subagent_output_files, get_subagents_by_tier


# ---------------------------------------------------------------------------
# State Schema
# ---------------------------------------------------------------------------

def _merge_files(existing: Dict[str, Any], update: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """合并 files 字典（用于 state reducer）。"""
    if update is None:
        return existing or {}
    merged = dict(existing or {})
    merged.update(update)
    return merged


def _accumulate_gaps(existing: List, update: Optional[List]) -> List:
    """累积 gaps 列表。"""
    if update is None:
        return existing or []
    return (existing or []) + update


class ExplorationDeterministicState(TypedDict, total=False):
    """确定性调度图的状态 schema。"""

    # 运行时文件系统（虚拟 workspace）
    files: Annotated[Dict[str, Dict[str, Any]], _merge_files]

    # 任务元数据
    task_id: str
    thread_id: str
    topic_identifier: str
    topic_label: str
    start: str
    end: str
    mode: str

    # 执行状态
    status: str  # running | completed | failed | partial
    message: str

    # 缺失记录
    gaps: Annotated[List[Dict[str, Any]], _accumulate_gaps]

    # 结构化结果
    structured_payload: Dict[str, Any]

    # 运行时资产（传入）
    skill_assets: Dict[str, Any]
    middleware_factory: Callable[[str], List[Any]]
    event_callback: Callable[[Dict[str, Any]], None]
    llm: Any

    # 当前执行的子代理名称（用于并行分支）
    current_agent: str


# ---------------------------------------------------------------------------
# 文件完整性检查
# ---------------------------------------------------------------------------

_TIER_REQUIRED_FILES: Dict[int, List[str]] = {
    0: [
        "/workspace/state/task_contract.json",  # 已存在
        "/workspace/state/task_derivation.json",
        "/workspace/state/task_derivation_proposal.json",
        "/workspace/state/normalized_task.json",
        "/workspace/state/retrieval_plan.json",
        "/workspace/state/dispatch_quality.json",
        "/workspace/state/corpus_coverage.json",
    ],
    1: [
        "/workspace/state/evidence_cards.json",
        "/workspace/state/bertopic_insight.json",
    ],
    2: [
        "/workspace/state/timeline_nodes.json",
        "/workspace/state/metrics_bundle.json",
        "/workspace/state/actor_positions.json",
    ],
    3: [
        "/workspace/state/event_analysis.json",
        "/workspace/state/conflict_map.json",
    ],
    4: [
        "/workspace/state/agenda_frame_map.json",
        "/workspace/state/mechanism_summary.json",
        "/workspace/state/risk_signals.json",
    ],
    5: [
        "/workspace/state/utility_assessment.json",
    ],
    6: [
        # writer 输出 section_drafts，可选检查
    ],
}


def _get_tier_required_files_from_config(tier: int) -> List[str]:
    """从 YAML 配置获取指定 tier 的必需输出文件。"""
    subagents_in_tier = get_subagents_by_tier(tier)
    all_files: List[str] = []
    for agent_name in subagents_in_tier:
        agent_files = get_subagent_output_files(agent_name)
        all_files.extend(agent_files)
    # Fallback to hardcoded if config returns empty
    if not all_files:
        all_files = _TIER_REQUIRED_FILES.get(tier, [])
    return all_files


def _is_empty_result(content: Dict[str, Any]) -> bool:
    """检查是否为结构化空结果。"""
    if not isinstance(content, dict):
        return True
    result = content.get("result")
    if isinstance(result, list) and len(result) == 0:
        # 检查是否有明确的空标记
        coverage = content.get("coverage", {})
        flags = coverage.get("readiness_flags", [])
        if "no_cards" in flags or "no_records_in_scope" in flags:
            return True
        # 有 coverage 但 result 为空，可能是合法空结果
        return False
    return False


def _check_files(
    files: Dict[str, Dict[str, Any]],
    required_paths: List[str],
    agent: str = "",
    tier: int = 0,
) -> List[Dict[str, Any]]:
    """检查必需文件是否存在，返回缺失列表。"""
    gaps: List[Dict[str, Any]] = []
    for path in required_paths:
        content = files.get(path)
        if not content:
            gaps.append({
                "agent": agent,
                "file": path,
                "reason": "missing",
                "tier": tier,
            })
        elif _is_empty_result(content):
            gaps.append({
                "agent": agent,
                "file": path,
                "reason": "empty_result",
                "tier": tier,
            })
    return gaps


def _read_file(files: Dict[str, Dict[str, Any]], path: str) -> Dict[str, Any]:
    """从 files 字典读取文件内容。"""
    content = files.get(path)
    return content if isinstance(content, dict) else {}


# ---------------------------------------------------------------------------
# 子代理调用工厂
# ---------------------------------------------------------------------------

# 子代理 system_prompt 配置（从 builder.py 复制）
_SUBAGENT_SYSTEM_PROMPTS: Dict[str, str] = {
    "retrieval_router": (
        "你是任务规范化与覆盖诊断代理。先读取 /workspace/base_context.json，"
        "**绝对禁止**自行生成、改写或覆盖以下字段：\n"
        "- topic_identifier（必须严格沿用 base_context.task_contract.topic_identifier）\n"
        "- start / end 时间窗口（必须严格沿用 base_context.task_contract.start/end）\n"
        "- contract_id（必须严格沿用 base_context.task_contract.contract_id）\n"
        "- mode 执行模式（必须严格沿用 base_context.task_contract.mode）\n"
        "如果发现 task_contract 与 base_context 不一致，必须立即终止并报错，不允许自动覆盖。\n\n"
        "调用 normalize_task 时，必须传入 base_context 中已有的 topic_identifier、start、end、mode 作为参数，"
        "只补充 topic / entities / keywords / platform_scope / mandatory_sections 等语义字段，"
        "再基于 analysis_question_set、coverage_expectation 与 inference_policy 归纳 retrieval plan，"
        "最后从 /workspace/state/task_contract.json 读取 contract_id，并调用 get_corpus_coverage(contract_id=..., retrieval_scope_json=..., filters_json=...) 区分'没有数据'与'没有发现'。"
        "把结果分别写入 /workspace/state/task_derivation.json、/workspace/state/task_derivation_proposal.json、/workspace/state/normalized_task.json、/workspace/state/retrieval_plan.json、/workspace/state/dispatch_quality.json 和 /workspace/state/corpus_coverage.json，"
        "并返回简短总结。默认策略是少调用、重研判。"
        "若目标文件已存在，先读取再使用 edit_file 更新，不要直接用 write_file 覆盖。"
    ),
    "archive_evidence_organizer": """
        你是证据卡整理代理。请读取 /workspace/state/task_contract.json、/workspace/state/task_derivation.json、/workspace/state/normalized_task.json 和 /workspace/state/corpus_coverage.json。
        其中 task_contract 是唯一执行 authority，normalized_task 只用于调试和兼容展示。
        从 /workspace/state/task_contract.json 提取 contract_id，只使用 retrieve_evidence_cards(contract_id=..., retrieval_scope_json=..., filters_json=..., intent=...) 产出分页证据卡与反证卡。
        intent 只允许使用以下 ABI 白名单：overview、timeline、actors、risk、claim_support、claim_counter。
        不要直接传中文语义词或自造值；例如 "传播总览" 必须映射为 overview，"传播演化"/"时间线" 映射为 timeline，"主体立场" 映射为 actors，"风险信号" 映射为 risk，"争议焦点" 必须拆成 claim_support 和 claim_counter，禁止直接传 "关键事件"、"主体立场"、"争议焦点"、"风险信号" 等中文 intent。
        如果 corpus_coverage.coverage.readiness_flags 包含 no_records_in_scope，
        只允许生成一次空 evidence_cards.json，随后立即结束，不要继续换 intent 重试。
        把聚合后的结果写入 /workspace/state/evidence_cards.json，并返回摘要。
        不要回写长段原文，不要把数据库字段直接搬进文稿。
        若目标文件已存在，先读取再使用 edit_file 更新，不要直接用 write_file 覆盖。
        """,
    "bertopic_evolution_analyst": (
        "你是 BERTopic 主题演化代理。请读取 /workspace/state/task_contract.json、/workspace/state/task_derivation.json 与 /workspace/state/normalized_task.json，"
        "先使用 get_bertopic_snapshot 读取当前专题在本地归档中的 BERTopic 结果，再使用 build_bertopic_insight 输出主题演化章节洞察。"
        "若快照不存在或可用主题为空，写出结构化空洞察，不输出警告性提示，不要伪造演化趋势。"
        "把结果写入 /workspace/state/bertopic_insight.json，并返回简短总结。"
        "若目标文件已存在，先读取再使用 edit_file 更新，不要直接用 write_file 覆盖。"
    ),
    "timeline_analyst": (
        "你是时间线分析代理。请读取 /workspace/state/task_contract.json、/workspace/state/task_derivation.json、/workspace/state/normalized_task.json 与 /workspace/state/evidence_cards.json，"
        "如果 evidence_cards.coverage.readiness_flags 包含 no_cards，则只生成结构化空结果并附带跳过原因，不要继续尝试深描。"
        "使用 build_event_timeline 生成带 support_evidence_ids 的时间线节点，再用 compute_report_metrics 输出 chart-ready 指标。\n\n"
        "**关键传参约束**:\n"
        "调用 build_event_timeline 时必须显式传参：\n"
        "- normalized_task_json 必须传 normalized_task.json 的完整内容（可以是顶层对象或其 normalized_task/result 子字段）\n"
        "- evidence_ids_json 必须传 evidence_cards.json 中的 result 数组（而非整个包装对象），不能为空或默认值\n"
        "不要只读取文件不传参，也不要把整个包装对象直接传给工具。\n\n"
        "只有在 evidence_cards.result 明确为空时，才允许返回空时间线结果。\n\n"
        "结果写入 /workspace/state/timeline_nodes.json 和 /workspace/state/metrics_bundle.json，并返回简短总结。"
        "若目标文件已存在，先读取再使用 edit_file 更新，不要直接用 write_file 覆盖。"
    ),
    "stance_conflict": (
        "你是主体立场代理。请读取 /workspace/state/task_contract.json、/workspace/state/task_derivation.json、/workspace/state/normalized_task.json 与 /workspace/state/evidence_cards.json，"
        "只使用 extract_actor_positions 输出主体、立场变化、冲突关系。"
        "调用时必须把 evidence_cards.json 中的 result 数组原样作为 evidence_ids_json 传入，不要只读取文件不传参，也不要把整个包装对象直接传给工具。"
        "只有在 evidence_cards.result 明确为空时，才允许返回空主体结果；不要依赖工具自行 fallback 重召回。"
        "把结果写入 /workspace/state/actor_positions.json，并返回简短总结。"
        "若目标文件已存在，先读取再使用 edit_file 更新，不要直接用 write_file 覆盖。"
    ),
    "event_analyst": (
        "你是事件结构分析代理。请读取 /workspace/state/task_contract.json、/workspace/state/task_derivation.json、"
        "/workspace/state/evidence_cards.json、/workspace/state/timeline_nodes.json 和 /workspace/state/metrics_bundle.json。\n\n"
        "**必须输出的结构**:\n"
        "1. event_trigger: {\n"
        "   'trigger_point': '事件触发点描述',\n"
        "   'first_source': '首发信源（平台/账号）',\n"
        "   'first_platform': '首发平台',\n"
        "   'trigger_time': '首发时间',\n"
        "   'trigger_content': '首发内容摘要（必须引用原文）'\n"
        "}\n"
        "2. discussion_evolution: {\n"
        "   'phases': [{'phase': '阶段名', 'focus': '焦点', 'mechanism': '机制', 'evidence_ids': ['ev-xxx']}],\n"
        "   'frame_shifts': ['框架转换描述'],\n"
        "   'key_nodes': ['关键转折节点']\n"
        "}\n"
        "3. actor_distribution: {\n"
        "   'actors': [{\n"
        "     'name': '主体名', 'type': '类型', 'stance': '立场', 'influence': '影响力',\n"
        "     'key_statements': ['具体发言（必须引用原文，≤80字/条）'],\n"
        "     'evidence_ids': ['ev-xxx']  # 对应 evidence_cards 中的 evidence_id\n"
        "   }],\n"
        "   'stance_summary': '整体立场结构摘要'\n"
        "}\n"
        "4. platform_analysis: {\n"
        "   'platforms': [{\n"
        "     'platform': '平台名',\n"
        "     'discussion_style': '讨论特征（如：情绪宣泄型/理性分析型/娱乐化解构型）',\n"
        "     'emotion_dist': {'positive': X, 'negative': Y, 'neutral': Z},\n"
        "     'dominant_emotion': '主导情绪关键词（如：愤怒/焦虑/讽刺/同情）',\n"
        "     'representative_quotes': ['原文引用1（≤80字，来自该平台的 evidence_cards）', '原文引用2'],\n"
        "     'key_users': ['关键用户'],\n"
        "     'evidence_ids': ['ev-xxx']  # 该平台的支撑证据ID\n"
        "   }],\n"
        "   'cross_platform_diff': '跨平台差异分析'\n"
        "}\n"
        "5. keywords: {\n"
        "   'top_keywords': ['关键词1', '关键词2', ...],\n"
        "   'keyword_semantics': {'关键词': '语义含义'}\n"
        "}\n"
        "6. sentiment_summary: {\n"
        "   'overall_emotion': '整体情感倾向',\n"
        "   'emotion_by_platform': {'平台': '情感描述'},\n"
        "   'emotion_drivers': ['情感驱动因素']\n"
        "}\n\n"
        "**关键约束**:\n"
        "- 每个判断必须有evidence_id支撑\n"
        "- key_statements必须引用evidence_cards中的snippet/content原文\n"
        "- 不能写'网友认为'，必须写具体发言者和原文\n"
        "- 使用 build_basic_analysis_insight 获取基础数据支撑\n\n"
        "结果写入 /workspace/state/event_analysis.json，并返回简短总结。"
    ),
    "claim_actor_conflict": (
        "你是断言冲突构建代理。请读取 /workspace/state/task_contract.json、/workspace/state/task_derivation.json、/workspace/state/normalized_task.json、/workspace/state/evidence_cards.json、"
        "/workspace/state/actor_positions.json 和 /workspace/state/timeline_nodes.json，"
        "如果 evidence_cards.coverage.readiness_flags 包含 no_cards，或 actor_positions / timeline_nodes 明显为空，"
        "只生成结构化空图谱，不输出警告性提示，不要反复重试。"
        "使用 build_claim_actor_conflict 生成 claim graph、actor positions、conflict edges 与 resolution states。"
        "调用时必须把 evidence_cards.json 中的 result 数组作为 evidence_ids_json，把 actor_positions.json 中的 result 数组作为 actor_positions_json，把 timeline_nodes.json 中的 result 数组作为 timeline_nodes_json。"
        "不要只读取这些文件而不传给工具，也不要把整个包装对象直接传给工具。"
        "把结果写入 /workspace/state/conflict_map.json，并返回简短总结。"
        "不要输出 prose 结论，不要默认把冲突写成已收敛。"
        "若目标文件已存在，先读取再使用 edit_file 更新，不要直接用 write_file 覆盖。"
    ),
    "agenda_frame_builder": (
        "你是议题与框架构建代理。请读取 /workspace/state/task_contract.json、/workspace/state/task_derivation.json、/workspace/state/normalized_task.json、/workspace/state/evidence_cards.json、"
        "/workspace/state/actor_positions.json、/workspace/state/conflict_map.json 与 /workspace/state/timeline_nodes.json，"
        "使用 build_agenda_frame_map 生成 issue nodes、attribute nodes、frame records、frame shifts 与 counter-frames。"
        "调用工具时必须显式传参："
        "normalized_task_json 从 normalized_task.json 提取，"
        "evidence_ids_json 必须传 evidence_cards.json 的 result 数组（而非整个包装对象），"
        "actor_positions_json 必须传 actor_positions.json 的 result 数组，"
        "timeline_nodes_json 必须传 timeline_nodes.json 的 result 数组，"
        "conflict_map_json 必须传 conflict_map.json 的核心对象内容。"
        "如果依赖文件不存在或为空，只生成结构化空结果，不输出警告性提示。"
        "把结果写入 /workspace/state/agenda_frame_map.json，并返回简短总结。"
        "不要输出 prose 结论，不要把框架写成普通摘要。"
        "若目标文件已存在，先读取再使用 edit_file 更新，不要直接用 write_file 覆盖。"
    ),
    "propagation_analyst": (
        "你是传播与风险代理。请读取 /workspace/state/task_contract.json、/workspace/state/task_derivation.json、/workspace/state/normalized_task.json、/workspace/state/evidence_cards.json、"
        "/workspace/state/metrics_bundle.json、/workspace/state/timeline_nodes.json 与 /workspace/state/conflict_map.json，"
        "如果 evidence_cards.coverage.readiness_flags 包含 no_cards，或 conflict_map / timeline_nodes 为空，"
        "只生成结构化空机制与空风险对象，不输出警告性提示。"
        "必要时补做 compute_report_metrics，使用 build_mechanism_summary 生成传播机制对象，再使用 detect_risk_signals 输出风险对象。\n\n"
        "**关键传参约束**:\n"
        "调用 build_mechanism_summary 时必须显式传参：\n"
        "- normalized_task_json 必须传 normalized_task.json 的完整内容\n"
        "- evidence_ids_json 必须传 evidence_cards.json 的 result 数组\n"
        "- timeline_nodes_json 必须传 timeline_nodes.json 的 result 数组\n"
        "- conflict_map_json 必须传 conflict_map.json 的核心对象（可传 result 内层或整个对象）\n"
        "不要只读取文件不传参，不要把包装对象直接传给工具，不要传空值。\n\n"
        "调用 detect_risk_signals 时同样必须显式传参：\n"
        "- evidence_ids_json 必须传 evidence_cards.json 的 result 数组\n\n"
        "把结果写入 /workspace/state/mechanism_summary.json 与 /workspace/state/risk_signals.json，并返回简短总结。"
        "若目标文件已存在，先读取再使用 edit_file 更新，不要直接用 write_file 覆盖。"
    ),
    "decision_utility_judge": (
        "你是决策可用性裁决代理。请读取 /workspace/state/task_contract.json、/workspace/state/task_derivation.json、/workspace/state/normalized_task.json、/workspace/state/corpus_coverage.json、"
        "/workspace/state/evidence_cards.json、/workspace/state/conflict_map.json、/workspace/state/mechanism_summary.json、"
        "/workspace/state/agenda_frame_map.json、/workspace/state/risk_signals.json 与 /workspace/state/actor_positions.json，"
        "如果上游已经进入 empty_corpus / empty_evidence / insufficient_structure，"
        "必须把这些原因写入 utility assessment 的 missing_dimensions 或 fallback reason，不要假装仍可正常放行。"
        "使用 judge_decision_utility 产出 typed utility assessment。"
        "调用时必须显式传参，不要只读取文件。"
        "risk_signals_json 必须传 risk_signals.json 的 result 数组；actor_positions_json 必须传 actor_positions.json 的 result 数组。"
        "agenda_frame_map_json、conflict_map_json、mechanism_summary_json 必须传各自的核心对象内容，可传 result 内层对象，也可传已展开的对象本身，但不要传空壳或只传文件元信息。"
        "把结果写入 /workspace/state/utility_assessment.json，并返回简短总结。"
        "不要直接写正文，不要用 prose 代替结构化裁决。"
        "若目标文件已存在，先读取再使用 edit_file 更新，不要直接用 write_file 覆盖。"
    ),
    "writer": (
        "你是舆情报告深度写作代理。你的职责是按模板章节产出正式报告正文，不是数据拼接。\n\n"
        "**核心要求（最高优先级）**：\n"
        "1. 每个判断必须有证据支撑，必须引用具体原文（使用 snippet/content 字段）\n"
        "2. 绝对不能只写'网友认为'，必须写出具体发言者和原文内容\n"
        "3. 每章节至少引用5条具体原文（使用引用格式）\n"
        "4. 段落组织遵循：锚定现象 → 交代机制 → 点出含义\n"
        "5. 情感强度必须匹配证据确定性\n\n"
        "**引用格式示例**：\n"
        "> \"武大这次真的让人心疼，校友群里都在讨论\" —— 微博用户@xxx（点赞数：1234）\n"
        "> \"我觉得问题不在个人，整个审核流程都有漏洞\" —— 知乎回答（评论数：567）\n"
        "> \"官方回应太慢了，等了14小时才发通报\" —— 贴吧用户（热度：89）\n\n"
        "**必须读取的文件**：\n"
        "/workspace/state/task_contract.json、/workspace/state/task_derivation.json、\n"
        "/workspace/state/event_analysis.json  # 事件分析结果（新增，必须读取）\n"
        "/workspace/state/evidence_cards.json  # 证据卡（含完整snippet/content）\n"
        "/workspace/state/timeline_nodes.json、/workspace/state/actor_positions.json、\n"
        "/workspace/state/conflict_map.json、/workspace/state/mechanism_summary.json、\n"
        "/workspace/state/risk_signals.json、/workspace/state/bertopic_insight.json、\n"
        "/workspace/state/utility_assessment.json。\n\n"
        "**模板使用**：\n"
        "先调用 get_report_template(mode=...) 获取模板内容。\n"
        "根据 task_contract.mode 选择模板：\n"
        "- 'public_hotspot' → 公共热点模板\n"
        "- 'crisis_response' → 危机响应模板\n"
        "- 'policy_dynamics' → 政策动态模板\n"
        "按模板各章节要求写作，特别注意：\n"
        "- 监测口径与样本说明：界定结论适用范围\n"
        "- 事件演变：围绕节点-转折-再定义展开\n"
        "- 传播路径：区分首发源、搬运节点、情绪放大节点\n"
        "- 舆论立场：区分主体类型，不能混写'公众反应'\n\n"
        "**内容密度要求**：\n"
        "- 每章节正文≥800字\n"
        "- 每100字至少包含1-2个具体数据点或引用\n"
        "- 每章节至少包含8-12条用户评论引用\n\n"
        "**使用工具**：\n"
        "- get_report_template(mode=...) 获取模板\n"
        "- retrieve_evidence_cards(intent=...) 获取补充证据\n"
        "- build_section_packet 构建章节材料包\n"
        "- get_sentiment_analysis_framework 获取方法论支撑\n\n"
        "**输出格式**：\n"
        "每章节使用 edit_file 写入 /workspace/state/section_drafts/{section_id}.json，\n"
        "包含 section_id、title、content（完整段落）、evidence_refs、claim_refs。\n"
        "完成后返回简短总结。若目标文件已存在，先读取再更新。\n\n"
        "**禁止事项**：\n"
        "- 禁止暴露系统字段名、工具名、模块名\n"
        "- 禁止使用'舆情爆炸''彻底翻车'等修辞\n"
        "- 禁止在没有证据支撑的情况下下结论"
    ),
}


def _get_subagent_system_prompt(agent_name: str) -> str:
    """获取子代理的 system_prompt。"""
    return _SUBAGENT_SYSTEM_PROMPTS.get(agent_name, "")


def _emit_event(
    event_callback: Callable[[Dict[str, Any]], None] | None,
    event: Dict[str, Any],
) -> None:
    """发送事件。"""
    if callable(event_callback):
        event_callback(event)


# ---------------------------------------------------------------------------
# 节点实现
# ---------------------------------------------------------------------------

def _invoke_subagent(
    agent_name: str,
    state: ExplorationDeterministicState,
) -> Dict[str, Any]:
    """
    调用单个子代理并返回结果。

    注意：这是一个简化实现，实际调用 LangChain agent 需要：
    1. 构建 agent（使用 create_agent）
    2. 配置 tools、skills、middleware
    3. 调用 agent.invoke()
    4. 从结果中提取 files 更新

    当前实现返回占位结果，后续需要与 builder.py 中的 subagent spec 整合。
    """
    # 占位实现：返回空结果
    # 实际实现需要：
    #   llm = state.get("llm")
    #   tools = select_report_tools(runtime_target=RUNTIME_SUBAGENT, agent_name=agent_name)
    #   skill_keys = _SUBAGENT_SKILL_KEYS.get(agent_name, [])
    #   skills = select_report_skill_sources(state.get("skill_assets"), ...)
    #   middleware = state.get("middleware_factory")(agent_name)
    #   agent = create_agent(model=llm, system_prompt=_get_subagent_system_prompt(agent_name), ...)
    #   result = agent.invoke({"prompt": "执行任务..."})
    #   return {"files": result.files, "status": "completed"}

    _emit_event(
        state.get("event_callback"),
        {
            "type": "graph.node.started",
            "phase": "interpret",
            "agent": agent_name,
            "title": f"{agent_name} 已启动",
            "message": f"{agent_name} 正在执行。",
        },
    )

    # TODO: 实际调用子代理
    return {
        "files": {},
        "status": "running",
        "gaps": [],
    }


# Tier 0: retrieval_router
def retrieval_router_node(state: ExplorationDeterministicState) -> Dict[str, Any]:
    """执行 retrieval_router 子代理。"""
    result = _invoke_subagent("retrieval_router", state)

    # 检查必需文件
    gaps = _check_files(
        result.get("files", {}),
        _TIER_REQUIRED_FILES.get(0, []),
        agent="retrieval_router",
        tier=0,
    )

    _emit_event(
        state.get("event_callback"),
        {
            "type": "graph.node.completed",
            "phase": "interpret",
            "agent": "retrieval_router",
            "title": "retrieval_router 已完成",
            "message": f"retrieval_router 完成，缺失文件：{len(gaps)}",
        },
    )

    return {
        "files": result.get("files", {}),
        "gaps": gaps,
        "status": "running",
    }


# Tier 1: 并行节点
def dispatch_tier1(state: ExplorationDeterministicState) -> List[Send]:
    """分发 Tier 1 并行任务。"""
    return [
        Send("archive_evidence_node", {"current_agent": "archive_evidence_organizer"}),
        Send("bertopic_node", {"current_agent": "bertopic_evolution_analyst"}),
    ]


def archive_evidence_node(state: ExplorationDeterministicState) -> Dict[str, Any]:
    """执行 archive_evidence_organizer 子代理。"""
    result = _invoke_subagent("archive_evidence_organizer", state)
    return {
        "files": result.get("files", {}),
    }


def bertopic_node(state: ExplorationDeterministicState) -> Dict[str, Any]:
    """执行 bertopic_evolution_analyst 子代理。"""
    result = _invoke_subagent("bertopic_evolution_analyst", state)
    return {
        "files": result.get("files", {}),
    }


def gather_tier1(state: ExplorationDeterministicState) -> Dict[str, Any]:
    """收集 Tier 1 结果并检查文件完整性。"""
    gaps = _check_files(
        state.get("files", {}),
        _TIER_REQUIRED_FILES.get(1, []),
        tier=1,
    )

    _emit_event(
        state.get("event_callback"),
        {
            "type": "phase.progress",
            "phase": "interpret",
            "title": "Tier 1 完成",
            "message": f"Tier 1 并行节点完成，缺失文件：{len(gaps)}",
        },
    )

    return {
        "gaps": gaps,
        "status": "running",
    }


# Tier 2: 并行节点
def dispatch_tier2(state: ExplorationDeterministicState) -> List[Send]:
    """分发 Tier 2 并行任务。"""
    return [
        Send("timeline_node", {"current_agent": "timeline_analyst"}),
        Send("stance_node", {"current_agent": "stance_conflict"}),
    ]


def timeline_node(state: ExplorationDeterministicState) -> Dict[str, Any]:
    """执行 timeline_analyst 子代理。"""
    result = _invoke_subagent("timeline_analyst", state)
    return {
        "files": result.get("files", {}),
    }


def stance_node(state: ExplorationDeterministicState) -> Dict[str, Any]:
    """执行 stance_conflict 子代理。"""
    result = _invoke_subagent("stance_conflict", state)
    return {
        "files": result.get("files", {}),
    }


def gather_tier2(state: ExplorationDeterministicState) -> Dict[str, Any]:
    """收集 Tier 2 结果并检查文件完整性。"""
    gaps = _check_files(
        state.get("files", {}),
        _TIER_REQUIRED_FILES.get(2, []),
        tier=2,
    )

    _emit_event(
        state.get("event_callback"),
        {
            "type": "phase.progress",
            "phase": "interpret",
            "title": "Tier 2 完成",
            "message": f"Tier 2 并行节点完成，缺失文件：{len(gaps)}",
        },
    )

    return {
        "gaps": gaps,
        "status": "running",
    }


# Tier 3: 并行节点
def dispatch_tier3(state: ExplorationDeterministicState) -> List[Send]:
    """分发 Tier 3 并行任务。"""
    return [
        Send("event_analyst_node", {"current_agent": "event_analyst"}),
        Send("conflict_node", {"current_agent": "claim_actor_conflict"}),
    ]


def event_analyst_node(state: ExplorationDeterministicState) -> Dict[str, Any]:
    """执行 event_analyst 子代理。"""
    result = _invoke_subagent("event_analyst", state)
    return {
        "files": result.get("files", {}),
    }


def conflict_node(state: ExplorationDeterministicState) -> Dict[str, Any]:
    """执行 claim_actor_conflict 子代理。"""
    result = _invoke_subagent("claim_actor_conflict", state)
    return {
        "files": result.get("files", {}),
    }


def gather_tier3(state: ExplorationDeterministicState) -> Dict[str, Any]:
    """收集 Tier 3 结果并检查文件完整性。"""
    gaps = _check_files(
        state.get("files", {}),
        _TIER_REQUIRED_FILES.get(3, []),
        tier=3,
    )

    _emit_event(
        state.get("event_callback"),
        {
            "type": "phase.progress",
            "phase": "interpret",
            "title": "Tier 3 完成",
            "message": f"Tier 3 并行节点完成，缺失文件：{len(gaps)}",
        },
    )

    return {
        "gaps": gaps,
        "status": "running",
    }


# Tier 4: 并行节点
def dispatch_tier4(state: ExplorationDeterministicState) -> List[Send]:
    """分发 Tier 4 并行任务。"""
    return [
        Send("agenda_node", {"current_agent": "agenda_frame_builder"}),
        Send("propagation_node", {"current_agent": "propagation_analyst"}),
    ]


def agenda_node(state: ExplorationDeterministicState) -> Dict[str, Any]:
    """执行 agenda_frame_builder 子代理。"""
    result = _invoke_subagent("agenda_frame_builder", state)
    return {
        "files": result.get("files", {}),
    }


def propagation_node(state: ExplorationDeterministicState) -> Dict[str, Any]:
    """执行 propagation_analyst 子代理。"""
    result = _invoke_subagent("propagation_analyst", state)
    return {
        "files": result.get("files", {}),
    }


def gather_tier4(state: ExplorationDeterministicState) -> Dict[str, Any]:
    """收集 Tier 4 结果并检查文件完整性。"""
    gaps = _check_files(
        state.get("files", {}),
        _TIER_REQUIRED_FILES.get(4, []),
        tier=4,
    )

    _emit_event(
        state.get("event_callback"),
        {
            "type": "phase.progress",
            "phase": "interpret",
            "title": "Tier 4 完成",
            "message": f"Tier 4 并行节点完成，缺失文件：{len(gaps)}",
        },
    )

    return {
        "gaps": gaps,
        "status": "running",
    }


# Tier 5: utility_node
def utility_node(state: ExplorationDeterministicState) -> Dict[str, Any]:
    """执行 decision_utility_judge 子代理。"""
    result = _invoke_subagent("decision_utility_judge", state)

    # 检查必需文件
    gaps = _check_files(
        state.get("files", {}),
        _TIER_REQUIRED_FILES.get(5, []),
        agent="decision_utility_judge",
        tier=5,
    )

    _emit_event(
        state.get("event_callback"),
        {
            "type": "graph.node.completed",
            "phase": "interpret",
            "agent": "decision_utility_judge",
            "title": "decision_utility_judge 已完成",
            "message": f"决策可用性裁决完成，缺失文件：{len(gaps)}",
        },
    )

    return {
        "files": result.get("files", {}),
        "gaps": gaps,
        "status": "running",
    }


def route_after_utility(state: ExplorationDeterministicState) -> str:
    """根据 utility_assessment.decision 决定是否执行 writer。"""
    utility = _read_file(state.get("files", {}), "/workspace/state/utility_assessment.json")
    decision = str(utility.get("decision") or "").strip()

    if decision in ("pass", "fallback_recompile"):
        return "writer_node"
    return "finalize_node"


# Tier 6: writer_node
def writer_node(state: ExplorationDeterministicState) -> Dict[str, Any]:
    """执行 writer 子代理。"""
    result = _invoke_subagent("writer", state)

    _emit_event(
        state.get("event_callback"),
        {
            "type": "graph.node.completed",
            "phase": "write",
            "agent": "writer",
            "title": "writer 已完成",
            "message": "深度报告写作完成。",
        },
    )

    return {
        "files": result.get("files", {}),
        "status": "running",
    }


# Tier 7: finalize_node
def finalize_node(state: ExplorationDeterministicState) -> Dict[str, Any]:
    """汇总结果并生成结构化报告。"""
    # TODO: 实现结构化汇总逻辑
    # 1. 从 files 中读取所有中间结果
    # 2. 合并成 structured_payload
    # 3. 调用 save_structured_report

    gaps = state.get("gaps", [])
    status = "completed" if not gaps else "partial"

    _emit_event(
        state.get("event_callback"),
        {
            "type": "phase.progress",
            "phase": "persist",
            "title": "探索阶段完成",
            "message": f"确定性调度完成。缺失项：{len(gaps)}",
            "payload": {
                "gaps": gaps,
                "status": status,
            },
        },
    )

    return {
        "status": status,
        "message": f"确定性调度完成。缺失项：{len(gaps)}",
        "structured_payload": {},  # TODO: 实际汇总
    }


# ---------------------------------------------------------------------------
# 图构建
# ---------------------------------------------------------------------------

def build_exploration_deterministic_graph() -> StateGraph:
    """构建确定性调度图。"""
    builder = StateGraph(ExplorationDeterministicState)

    # Tier 0
    builder.add_node("retrieval_router_node", retrieval_router_node)
    builder.add_edge(START, "retrieval_router_node")

    # Tier 1: 并行
    builder.add_node("archive_evidence_node", archive_evidence_node)
    builder.add_node("bertopic_node", bertopic_node)
    builder.add_node("gather_tier1", gather_tier1)
    builder.add_conditional_edges("retrieval_router_node", dispatch_tier1)
    builder.add_edge("archive_evidence_node", "gather_tier1")
    builder.add_edge("bertopic_node", "gather_tier1")

    # Tier 2: 并行
    builder.add_node("timeline_node", timeline_node)
    builder.add_node("stance_node", stance_node)
    builder.add_node("gather_tier2", gather_tier2)
    builder.add_conditional_edges("gather_tier1", dispatch_tier2)
    builder.add_edge("timeline_node", "gather_tier2")
    builder.add_edge("stance_node", "gather_tier2")

    # Tier 3: 并行
    builder.add_node("event_analyst_node", event_analyst_node)
    builder.add_node("conflict_node", conflict_node)
    builder.add_node("gather_tier3", gather_tier3)
    builder.add_conditional_edges("gather_tier2", dispatch_tier3)
    builder.add_edge("event_analyst_node", "gather_tier3")
    builder.add_edge("conflict_node", "gather_tier3")

    # Tier 4: 并行
    builder.add_node("agenda_node", agenda_node)
    builder.add_node("propagation_node", propagation_node)
    builder.add_node("gather_tier4", gather_tier4)
    builder.add_conditional_edges("gather_tier3", dispatch_tier4)
    builder.add_edge("agenda_node", "gather_tier4")
    builder.add_edge("propagation_node", "gather_tier4")

    # Tier 5: utility
    builder.add_node("utility_node", utility_node)
    builder.add_edge("gather_tier4", "utility_node")

    # Tier 6: writer（条件执行）
    builder.add_node("writer_node", writer_node)
    builder.add_conditional_edges(
        "utility_node",
        route_after_utility,
        {
            "writer_node": "writer_node",
            "finalize_node": "finalize_node",
        },
    )

    # Tier 7: finalize
    builder.add_node("finalize_node", finalize_node)
    builder.add_edge("writer_node", "finalize_node")
    builder.add_edge("finalize_node", END)

    return builder


def run_exploration_deterministic_graph(
    *,
    request: Dict[str, Any],
    skill_assets: Dict[str, Any],
    middleware_factory: Callable[[str], List[Any]],
    event_callback: Callable[[Dict[str, Any]], None] | None = None,
    llm: Any,
    initial_files: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    """
    执行确定性调度图。

    Parameters
    ----------
    request : Dict[str, Any]
        任务请求，包含 topic_identifier、start、end、mode 等。
    skill_assets : Dict[str, Any]
        技能资产包。
    middleware_factory : Callable[[str], List[Any]]
        中间件工厂函数。
    event_callback : Callable[[Dict], None] | None
        事件回调函数。
    llm : Any
        LangChain 语言模型实例。
    initial_files : Dict[str, Dict[str, Any]]
        初始文件内容（如 base_context.json）。

    Returns
    -------
    Dict[str, Any]
        包含 files、gaps、structured_payload、status 的结果字典。
    """
    builder = build_exploration_deterministic_graph()
    checkpointer, runtime_profile = get_shared_report_checkpointer(
        purpose="exploration-deterministic-graph"
    )
    graph = builder.compile(checkpointer=checkpointer)

    thread_id = str(request.get("thread_id") or "").strip()
    task_id = str(request.get("task_id") or "").strip()

    config = build_report_runnable_config(
        thread_id=thread_id,
        purpose="exploration-deterministic-graph",
        task_id=task_id,
        tags=["deterministic", "exploration"],
        metadata={
            "topic_identifier": str(request.get("topic_identifier") or "").strip(),
        },
        locator_hint=runtime_profile.checkpoint_locator,
    )

    initial_state: ExplorationDeterministicState = {
        "files": initial_files,
        "task_id": task_id,
        "thread_id": thread_id,
        "topic_identifier": str(request.get("topic_identifier") or "").strip(),
        "topic_label": str(request.get("topic_label") or "").strip(),
        "start": str(request.get("start") or "").strip(),
        "end": str(request.get("end") or "").strip(),
        "mode": str(request.get("mode") or "fast").strip(),
        "status": "running",
        "message": "",
        "gaps": [],
        "structured_payload": {},
        "skill_assets": skill_assets,
        "middleware_factory": middleware_factory,
        "event_callback": event_callback or (lambda _: None),
        "llm": llm,
    }

    # 执行图
    final_state: Dict[str, Any] = {}
    for chunk in graph.stream(
        initial_state,
        config=config,
        stream_mode="updates",
        version="v2",
    ):
        if not isinstance(chunk, dict):
            continue
        data = chunk.get("data") if chunk.get("type") == "updates" else None
        if not isinstance(data, dict):
            continue
        for updates in data.values():
            if isinstance(updates, dict):
                final_state.update(updates)

    return {
        "files": final_state.get("files", {}),
        "gaps": final_state.get("gaps", []),
        "structured_payload": final_state.get("structured_payload", {}),
        "status": str(final_state.get("status") or "").strip() or "failed",
        "message": str(final_state.get("message") or "").strip(),
    }


__all__ = [
    "ExplorationDeterministicState",
    "build_exploration_deterministic_graph",
    "run_exploration_deterministic_graph",
]