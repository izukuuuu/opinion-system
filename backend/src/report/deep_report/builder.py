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
from ..configs import get_subagent_skill_keys, get_coordinator_skill_keys


# ---------------------------------------------------------------------------
# 每个 subagent 的 preferred_skill_keys（从 YAML 配置文件加载）
# ---------------------------------------------------------------------------
def _get_subagent_skill_keys(agent_name: str) -> List[str]:
    """获取子代理的 skill_keys（从 YAML 配置加载）。"""
    return get_subagent_skill_keys(agent_name)


def _get_coordinator_skill_keys() -> List[str]:
    """获取 coordinator 的 skill_keys（从 YAML 配置加载）。"""
    return get_coordinator_skill_keys()


# 保留旧常量作为 fallback（兼容旧代码）
_SUBAGENT_SKILL_KEYS: Dict[str, List[str]] = {
    "retrieval_router": ["retrieval-router-rules"],
    "archive_evidence_organizer": ["evidence-source-credibility"],
    "timeline_analyst": ["timeline-alignment-slicing"],
    "stance_conflict": ["subject-stance-merging"],
    "event_analyst": ["sentiment-analysis-methodology", "propagation-explanation-framework"],
    "claim_actor_conflict": ["subject-stance-merging"],
    "propagation_analyst": ["propagation-explanation-framework", "chart-interpretation-guidelines"],
    "bertopic_evolution_analyst": ["bertopic-evolution-framework"],
    "decision_utility_judge": ["quality-validation-backlink"],
    "agenda_frame_builder": [],
    "validator": ["quality-validation-backlink"],
    "writer": [
        "report-writing-framework",
        "sentiment-analysis-methodology",
        "chart-interpretation-guidelines",
        "propagation-explanation-framework",
    ],
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
        # 从 YAML 配置加载 skill_keys，fallback 到旧常量
        preferred = _get_subagent_skill_keys(agent_name)
        if not preferred:
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
    event_analysis_tools = _tools_for("event_analyst")  # 新增
    conflict_tools = _tools_for("claim_actor_conflict")
    propagation_tools = _tools_for("propagation_analyst")
    bertopic_tools = _tools_for("bertopic_evolution_analyst")
    utility_tools = _tools_for("decision_utility_judge")
    writer_tools = _tools_for("writer")

    return [
        {
            "name": "retrieval_router",
            "description": "负责冻结任务边界、生成 task derivation / retrieval plan / dispatch quality，并诊断语料覆盖。task_contract 是唯一执行锚点，normalized_task 只保留为兼容视图。写入 /workspace/state/task_derivation.json、/workspace/state/task_derivation_proposal.json、/workspace/state/normalized_task.json、/workspace/state/retrieval_plan.json、/workspace/state/dispatch_quality.json 和 /workspace/state/corpus_coverage.json。",
            "system_prompt": (
                "你是任务规范化与覆盖诊断代理。\n\n"
                "## 输入来源\n"
                "读取 /workspace/base_context.json，提取以下字段（**只读，禁止改写**）：\n"
                "  → task_contract.topic_identifier  用于 normalize_task 的 topic_identifier 参数\n"
                "  → task_contract.start             用于 normalize_task 的 start 参数\n"
                "  → task_contract.end               用于 normalize_task 的 end 参数\n"
                "  → task_contract.contract_id       用于 get_corpus_coverage 的 contract_id 参数\n"
                "  → task_contract.mode              用于 normalize_task 的 mode 参数\n"
                "如果 task_contract 与 base_context 字段不一致，必须立即终止并报错，禁止自动覆盖。\n\n"
                "## 工具调用规范\n"
                "1. 调用 normalize_task 时：\n"
                "   - topic_identifier / start / end / contract_id / mode 必须严格原样取自 base_context.task_contract，禁止自行生成\n"
                "   - 只在 hints_json 中补充 topic / entities / keywords / platform_scope / mandatory_sections 等语义字段\n"
                "2. 调用 get_corpus_coverage 时：\n"
                "   - contract_id = base_context.task_contract.contract_id（严格原样，禁止生成新值）\n"
                "   - 若返回的 coverage.readiness_flags 含 'partial_coverage'，扩大 retrieval_scope_json 时间窗后再调用一次，最多扩展一次\n"
                "   - 明确区分'没有数据（no_records_in_scope）'与'没有发现（分析层面为空）'\n\n"
                "## 输出目标\n"
                "依次写入以下文件（若已存在先 read_file 再 edit_file 更新，禁止直接 write_file 覆盖）：\n"
                "  /workspace/state/task_derivation.json         — 任务推导\n"
                "  /workspace/state/task_derivation_proposal.json — 推导提案\n"
                "  /workspace/state/normalized_task.json         — 标准化任务（normalize_task 返回值）\n"
                "  /workspace/state/retrieval_plan.json          — 检索计划（含 router_facets / dispatch_plan / dispatch_quality_ledger）\n"
                "  /workspace/state/dispatch_quality.json        — 派发质量\n"
                "  /workspace/state/corpus_coverage.json         — 语料覆盖（get_corpus_coverage 返回值）\n\n"
                "## 空结果/降级处理\n"
                "若 coverage.readiness_flags 包含 'no_records_in_scope'，在 corpus_coverage.json 中记录此状态，"
                "并在 dispatch_quality.json 中标注 status='no_data'，然后结束，不要继续扩检。\n\n"
                "## 禁止行为\n"
                "- 禁止自行生成 topic_identifier / start / end / contract_id / mode\n"
                "- 禁止调用 query_documents / build_timeline / build_entity_graph 等已废弃工具\n"
                "- 禁止把 writer 直接连接到原始检索命中（writer 只消费 section_packets）\n"
                "- 默认策略：少调用、重研判，不要把'多查一点'当作最优策略\n"
            ),
            "tools": retrieval_tools,
            "middleware": middleware_factory("retrieval_router"),
            "skills": _skills_for("retrieval_router", retrieval_tools),
        },
        {
            "name": "archive_evidence_organizer",
            "description": "负责按任务意图召回证据卡，并写入 /workspace/state/evidence_cards.json。",
            “system_prompt”: (
                “你是证据卡整理代理。\n\n”
                “## 输入来源\n”
                “读取以下文件，按标注提取字段：\n”
                “  /workspace/state/task_contract.json    → 提取 .contract_id（唯一执行锚点，用于所有 retrieve_evidence_cards 调用）\n”
                “  /workspace/state/corpus_coverage.json  → 检查 .coverage.readiness_flags 列表\n”
                “  /workspace/state/task_derivation.json  → 参考检索意图和过滤条件（只读）\n”
                “  normalized_task.json 仅供调试参考，不作为执行依据。\n\n”
                “## 工具调用规范\n”
                “调用 retrieve_evidence_cards 时：\n”
                “  - contract_id = task_contract.contract_id（严格原样）\n”
                “  - intent 必须从以下枚举中选取（禁止传中文词或自造值）：\n”
                “      overview（传播总览）、timeline（时间线/演化）、actors（主体立场）、\n”
                “      risk（风险信号）、claim_support（争议焦点支持方）、claim_counter（争议焦点反对方）\n”
                “  - 分页策略：若返回的 cursor_next 非空且当前 intent 证据数 < 20，追加一次调用传入 cursor=cursor_next，每个 intent 最多调用 2 次\n”
                “  - 最低证据数要求：6 个 intent 合计至少召回 15 条非空证据卡；若不足，在摘要中写明缺口\n\n”
                “## 输出目标\n”
                “把聚合后的所有证据卡写入 /workspace/state/evidence_cards.json，格式：\n”
                “  { 'status': 'ok', 'result': [...所有证据卡...], 'coverage': {...} }\n”
                “若文件已存在，先 read_file 再 edit_file 更新，禁止 write_file 覆盖。\n\n”
                “## 空结果/降级处理\n”
                “若 corpus_coverage.coverage.readiness_flags 包含 'no_records_in_scope'，\n”
                “生成以下标准化空结构后立即结束，禁止继续换 intent 重试：\n”
                '  { “status”: “empty”, “reason”: “corpus 无数据”, “result”: [], “skipped_due_to”: [“no_records_in_scope”] }\n\n'
                “## 禁止行为\n”
                “- 禁止直接传中文 intent 值（如'关键事件''主体立场''争议焦点'）\n”
                “- 禁止把长段原文或数据库字段直接写入输出\n”
                “- 禁止在数据缺失时继续重试超过规定次数\n”
            ),
            "tools": evidence_tools,
            "middleware": middleware_factory("archive_evidence_organizer"),
            "skills": _skills_for("archive_evidence_organizer", evidence_tools),
        },
        {
            "name": "timeline_analyst",
            "description": "负责构建时间线节点和图表就绪指标，写入 /workspace/state/timeline_nodes.json 与 /workspace/state/metrics_bundle.json。",
            "system_prompt": (
                "你是时间线分析代理。\n\n"
                "## 输入来源\n"
                "读取以下文件，按标注提取字段：\n"
                "  /workspace/state/normalized_task.json  → 读取完整内容（JSON 字符串），用于 normalized_task_json 参数\n"
                "  /workspace/state/evidence_cards.json   → 提取 .result[*].evidence_id 组成字符串列表，用于 evidence_ids_json 参数\n"
                "                                           同时检查 .coverage.readiness_flags 列表\n\n"
                "## 工具调用规范\n"
                "调用 build_event_timeline 时（必须显式传参，禁止依赖默认值）：\n"
                "  - normalized_task_json = normalized_task.json 的完整 JSON 字符串（顶层对象）\n"
                "  - evidence_ids_json = evidence_cards.result[*].evidence_id 的字符串列表，格式 [\"ev-001\", ...]（仅 ID，禁止传完整证据卡对象或整个包装对象）\n"
                "调用 compute_report_metrics 时：\n"
                "  - normalized_task_json = normalized_task.json 的完整 JSON 字符串\n"
                "  - evidence_ids_json = 同上的 ID 字符串列表\n\n"
                "## 输出目标\n"
                "  /workspace/state/timeline_nodes.json   — build_event_timeline 结果（含 result 数组）\n"
                "  /workspace/state/metrics_bundle.json   — compute_report_metrics 结果（含 result 数组）\n"
                "若文件已存在，先 read_file 再 edit_file 更新，禁止 write_file 覆盖。\n\n"
                "## 空结果/降级处理\n"
                "若 evidence_cards.coverage.readiness_flags 包含 'no_cards' 或 evidence_cards.result 为空列表，\n"
                "生成以下标准化空结构后立即结束，禁止继续尝试深描：\n"
                '  { "status": "empty", "reason": "上游证据为空", "result": [], "skipped_due_to": ["upstream_empty"] }\n\n'
                "## 禁止行为\n"
                "- 禁止把整个 evidence_cards 对象传给 evidence_ids_json（只传 ID 字符串列表）\n"
                "- 禁止在证据不足时硬切阶段（节点数不够就少输出节点）\n"
                "- 禁止把相关性直接写成因果\n"
            ),
            "tools": timeline_tools,
            "middleware": middleware_factory("timeline_analyst"),
            "skills": _skills_for("timeline_analyst", timeline_tools),
        },
        {
            "name": "stance_conflict",
            "description": "负责识别主体与立场关系，写入 /workspace/state/actor_positions.json。",
            "system_prompt": (
                "你是主体立场代理。\n\n"
                "## 输入来源\n"
                "读取以下文件，按标注提取字段：\n"
                "  /workspace/state/normalized_task.json  → 读取完整内容（JSON 字符串），用于 normalized_task_json 参数\n"
                "  /workspace/state/evidence_cards.json   → 提取 .result[*].evidence_id 组成字符串列表，用于 evidence_ids_json 参数\n"
                "                                           同时检查 .result 是否为空\n\n"
                "## 工具调用规范\n"
                "调用 extract_actor_positions 时（必须显式传参，禁止依赖默认值）：\n"
                "  - normalized_task_json = normalized_task.json 的完整 JSON 字符串（顶层对象）\n"
                "  - evidence_ids_json = evidence_cards.result[*].evidence_id 的字符串列表，格式 [\"ev-001\", ...]（仅 ID，禁止传整个包装对象）\n"
                "禁止依赖工具自行 fallback 重召回证据。\n\n"
                "## 输出目标\n"
                "把结果写入 /workspace/state/actor_positions.json，格式：\n"
                "  { 'status': 'ok', 'result': [...actor 对象列表...] }\n"
                "若文件已存在，先 read_file 再 edit_file 更新，禁止 write_file 覆盖。\n\n"
                "## 空结果/降级处理\n"
                "若 evidence_cards.result 为空列表，生成以下标准化空结构后立即结束：\n"
                '  { "status": "empty", "reason": "上游证据为空", "result": [], "skipped_due_to": ["upstream_empty"] }\n\n'
                "## 禁止行为\n"
                "- 禁止把整个 evidence_cards 对象传给 evidence_ids_json（只传 ID 字符串列表）\n"
                "- 禁止在没有证据支撑时推断主体立场\n"
            ),
            "tools": stance_tools,
            "middleware": middleware_factory("stance_conflict"),
            "skills": _skills_for("stance_conflict", stance_tools),
        },
        {
            "name": "event_analyst",
            "description": "负责通用事件分析，拆解引发点、讨论演化、主体分布、平台差异、关键词和情感倾向，写入 /workspace/state/event_analysis.json。",
            "system_prompt": (
                "你是事件结构分析代理。\n\n"
                "## 输入来源\n"
                "读取以下文件，按标注提取字段：\n"
                "  /workspace/state/evidence_cards.json   → 读取完整内容，用于引用 snippet/content 原文；提取 .result[*].evidence_id\n"
                "  /workspace/state/timeline_nodes.json   → 直接读取已计算的时间线节点（不要重新调用 build_event_timeline）\n"
                "  /workspace/state/metrics_bundle.json   → 直接读取已计算的指标数据（不要重新调用 compute_report_metrics）\n"
                "  /workspace/state/task_derivation.json  → 参考分析问题集（只读）\n"
                "若 timeline_nodes.json 或 metrics_bundle.json 不存在，才允许调用对应工具补充计算。\n\n"
                "## 工具调用规范\n"
                "调用 build_basic_analysis_insight 时（补充基础数据）：\n"
                "  - snapshot_json = get_basic_analysis_snapshot 工具的完整返回值 JSON 字符串\n"
                "若需补充调用 build_event_timeline 或 compute_report_metrics（文件不存在时）：\n"
                "  - normalized_task_json = normalized_task.json 的完整 JSON 字符串\n"
                "  - evidence_ids_json = evidence_cards.result[*].evidence_id 的字符串列表（仅 ID）\n\n"
                "## 输出目标\n"
                "把以下 6 个结构组合写入 /workspace/state/event_analysis.json：\n"
                "  event_trigger / discussion_evolution / actor_distribution / platform_analysis / keywords / sentiment_summary\n"
                "每个结构必须有 evidence_ids 字段，指向 evidence_cards.result 中的具体 evidence_id。\n"
                "key_statements 必须引用 evidence_cards 中的 snippet/content 原文（≤80字/条），禁止写'网友认为'无具体发言者。\n"
                "若文件已存在，先 read_file 再 edit_file 更新，禁止 write_file 覆盖。\n\n"
                "## 空结果/降级处理\n"
                "若 evidence_cards.result 为空，生成包含 6 个空结构的标准化结果后立即结束：\n"
                '  { "status": "empty", "reason": "上游证据为空", "result": { "event_trigger": {}, "discussion_evolution": {}, '
                '"actor_distribution": {}, "platform_analysis": {}, "keywords": {}, "sentiment_summary": {} }, '
                '"skipped_due_to": ["upstream_empty"] }\n\n'
                "## 禁止行为\n"
                "- 禁止在 timeline_nodes.json 已存在时重新调用 build_event_timeline（避免重复计算）\n"
                "- 禁止写无具体发言者的'网友认为'\n"
                "- 禁止超出证据支撑范围下结论\n"
            ),
            "tools": event_analysis_tools,
            "middleware": middleware_factory("event_analyst"),
            "skills": _skills_for("event_analyst", event_analysis_tools),
        },
        {
            "name": "claim_actor_conflict",
            "description": "负责构建断言-主体冲突图，写入 /workspace/state/conflict_map.json。",
            "system_prompt": (
                "你是断言冲突构建代理。\n\n"
                "## 输入来源\n"
                "读取以下文件，按标注提取字段：\n"
                "  /workspace/state/normalized_task.json  → 读取完整内容（JSON 字符串），用于 normalized_task_json 参数\n"
                "  /workspace/state/evidence_cards.json   → 提取 .result[*].evidence_id 字符串列表，用于 evidence_ids_json 参数\n"
                "                                           同时检查 .coverage.readiness_flags\n"
                "  /workspace/state/actor_positions.json  → 提取 .result 数组（完整 actor 对象列表），用于 actor_positions_json 参数\n"
                "  /workspace/state/timeline_nodes.json   → 提取 .result 数组（完整节点对象列表），用于 timeline_nodes_json 参数\n\n"
                "## 工具调用规范\n"
                "调用 build_claim_actor_conflict 时（必须显式传参，禁止依赖默认值）：\n"
                "  - normalized_task_json = normalized_task.json 的完整 JSON 字符串\n"
                "  - evidence_ids_json    = evidence_cards.result[*].evidence_id 的字符串列表，格式 [\"ev-001\", ...]（仅 ID）\n"
                "  - actor_positions_json = actor_positions.result 数组（完整 actor 对象列表，非仅 ID）\n"
                "  - timeline_nodes_json  = timeline_nodes.result 数组（完整节点对象列表，非仅 ID）\n"
                "禁止把整个包装对象直接传给任何参数。\n\n"
                "## 输出目标\n"
                "把结果写入 /workspace/state/conflict_map.json，格式：\n"
                "  { 'status': 'ok', 'result': { claim_nodes, actor_positions, conflict_edges, resolution_states } }\n"
                "若文件已存在，先 read_file 再 edit_file 更新，禁止 write_file 覆盖。\n\n"
                "## 空结果/降级处理\n"
                "若 evidence_cards.coverage.readiness_flags 包含 'no_cards'，或 actor_positions.result 为空，或 timeline_nodes.result 为空，\n"
                "生成以下标准化空结构后立即结束，禁止重试：\n"
                '  { "status": "empty", "reason": "上游依赖为空", "result": { "claim_nodes": [], "actor_positions": [], "conflict_edges": [], "resolution_states": [] }, "skipped_due_to": ["upstream_empty"] }\n\n'
                "## 禁止行为\n"
                "- 禁止输出 prose 结论\n"
                "- 禁止默认把冲突写成已收敛\n"
                "- 禁止把整个包装对象传给工具参数\n"
            ),
            "tools": conflict_tools,
            "middleware": middleware_factory("claim_actor_conflict"),
            "skills": _skills_for("claim_actor_conflict", conflict_tools),
        },
        {
            "name": "agenda_frame_builder",
            "description": "负责构建议题-属性-框架图，写入 /workspace/state/agenda_frame_map.json。",
            "system_prompt": (
                "你是议题与框架构建代理。\n\n"
                "## 输入来源\n"
                "读取以下文件，按标注提取字段：\n"
                "  /workspace/state/normalized_task.json  → 读取完整内容（JSON 字符串），用于 normalized_task_json 参数\n"
                "  /workspace/state/evidence_cards.json   → 提取 .result[*].evidence_id 字符串列表，用于 evidence_ids_json 参数\n"
                "  /workspace/state/actor_positions.json  → 提取 .result 数组（完整 actor 对象列表），用于 actor_positions_json 参数\n"
                "  /workspace/state/conflict_map.json     → 提取 .result 字段（内层核心对象），用于 conflict_map_json 参数\n"
                "  /workspace/state/timeline_nodes.json   → 提取 .result 数组（完整节点对象列表），用于 timeline_nodes_json 参数\n\n"
                "## 工具调用规范\n"
                "调用 build_agenda_frame_map 时（必须显式传参，禁止依赖默认值）：\n"
                "  - normalized_task_json = normalized_task.json 的完整 JSON 字符串\n"
                "  - evidence_ids_json    = evidence_cards.result[*].evidence_id 字符串列表（仅 ID）\n"
                "  - actor_positions_json = actor_positions.result 数组（完整 actor 对象列表，非仅 ID）\n"
                "  - conflict_map_json    = conflict_map.result 内层核心对象（禁止传整个包装对象）\n"
                "  - timeline_nodes_json  = timeline_nodes.result 数组（完整节点对象列表，非仅 ID）\n\n"
                "## 输出目标\n"
                "把结果写入 /workspace/state/agenda_frame_map.json，格式：\n"
                "  { 'status': 'ok', 'result': { issue_nodes, frame_records, frame_shifts, counter_frames } }\n"
                "若文件已存在，先 read_file 再 edit_file 更新，禁止 write_file 覆盖。\n\n"
                "## 空结果/降级处理\n"
                "若任一依赖文件不存在或 status='empty'，生成以下标准化空结构后立即结束：\n"
                '  { "status": "empty", "reason": "上游依赖为空", "result": { "issue_nodes": [], "frame_records": [], "frame_shifts": [], "counter_frames": [] }, "skipped_due_to": ["upstream_empty"] }\n\n'
                "## 禁止行为\n"
                "- 禁止输出 prose 结论或普通摘要（只输出结构化框架对象）\n"
                "- 禁止把整个包装对象传给 conflict_map_json（只传 .result 内层对象）\n"
                "- 禁止把'各方说法不同'直接等同于'框架冲突'（框架差异必须有跨主体的证据支撑）\n"
            ),
            "tools": agenda_tools,
            "middleware": middleware_factory("agenda_frame_builder"),
            "skills": _skills_for("agenda_frame_builder", agenda_tools),
        },
        {
            "name": "propagation_analyst",
            "description": "负责解释传播指标、机制摘要与风险信号，写入 /workspace/state/mechanism_summary.json 与 /workspace/state/risk_signals.json。",
            "system_prompt": (
                "你是传播与风险代理。\n\n"
                "## 输入来源\n"
                "读取以下文件，按标注提取字段：\n"
                "  /workspace/state/normalized_task.json  → 读取完整内容（JSON 字符串），用于 normalized_task_json 参数\n"
                "  /workspace/state/evidence_cards.json   → 提取 .result[*].evidence_id 字符串列表，用于 evidence_ids_json 参数\n"
                "                                           同时检查 .coverage.readiness_flags\n"
                "  /workspace/state/timeline_nodes.json   → 提取 .result 数组（完整节点对象列表），用于 timeline_nodes_json 参数\n"
                "  /workspace/state/conflict_map.json     → 提取 .result 字段（内层核心对象），用于 conflict_map_json 和 discourse_conflict_map_json 参数\n"
                "  /workspace/state/metrics_bundle.json   → 提取 .result 数组（完整指标对象列表），用于 metric_refs_json 参数\n"
                "                                           若文件不存在，先调用 compute_report_metrics 补充计算\n"
                "  /workspace/state/actor_positions.json  → 提取 .result 数组（完整 actor 对象列表），用于 actor_positions_json 参数\n\n"
                "## 工具调用规范\n"
                "调用 build_mechanism_summary 时（必须显式传参，禁止依赖默认值）：\n"
                "  - normalized_task_json = normalized_task.json 的完整 JSON 字符串\n"
                "  - evidence_ids_json    = evidence_cards.result[*].evidence_id 字符串列表（仅 ID）\n"
                "  - timeline_nodes_json  = timeline_nodes.result 数组（完整节点对象列表）\n"
                "  - conflict_map_json    = conflict_map.result 内层核心对象（禁止传整个包装对象）\n"
                "  - metric_refs_json     = metrics_bundle.result 数组（完整指标对象列表）\n"
                "调用 detect_risk_signals 时（必须显式传参）：\n"
                "  - normalized_task_json       = normalized_task.json 的完整 JSON 字符串\n"
                "  - evidence_ids_json          = evidence_cards.result[*].evidence_id 字符串列表（仅 ID）\n"
                "  - metric_refs_json           = metrics_bundle.result 数组\n"
                "  - discourse_conflict_map_json = conflict_map.result 内层核心对象\n"
                "  - actor_positions_json        = actor_positions.result 数组（完整 actor 对象列表）\n\n"
                "## 输出目标\n"
                "  /workspace/state/mechanism_summary.json — build_mechanism_summary 结果\n"
                "  /workspace/state/risk_signals.json      — detect_risk_signals 结果\n"
                "若文件已存在，先 read_file 再 edit_file 更新，禁止 write_file 覆盖。\n\n"
                "## 空结果/降级处理\n"
                "若 evidence_cards.coverage.readiness_flags 包含 'no_cards'，或 conflict_map.result 为空，\n"
                "分别生成以下标准化空结构后立即结束：\n"
                '  mechanism_summary: { "status": "empty", "reason": "上游依赖为空", "result": {}, "skipped_due_to": ["upstream_empty"] }\n'
                '  risk_signals:      { "status": "empty", "reason": "上游依赖为空", "result": [], "skipped_due_to": ["upstream_empty"] }\n\n'
                "## 禁止行为\n"
                "- 禁止把整个包装对象传给 conflict_map_json（只传 .result 内层对象）\n"
                "- 禁止把'热度大'直接等同于'扩散结构重要'\n"
                "- 禁止在没有证据时生成风险判断\n"
            ),
            "tools": propagation_tools,
            "middleware": middleware_factory("propagation_analyst"),
            "skills": _skills_for("propagation_analyst", propagation_tools),
        },
        {
            "name": "bertopic_evolution_analyst",
            "description": "负责读取 BERTopic 快照并生成主题演化洞察，写入 /workspace/state/bertopic_insight.json。",
            "system_prompt": (
                "你是 BERTopic 主题演化代理。\n\n"
                "## 输入来源\n"
                "读取以下文件，按标注提取字段：\n"
                "  /workspace/state/task_contract.json    → 提取 .topic_identifier、.start、.end、.topic_label\n\n"
                "## 工具调用规范\n"
                "1. 调用 get_bertopic_snapshot 时：\n"
                "   - topic_identifier = task_contract.topic_identifier\n"
                "   - start = task_contract.start\n"
                "   - end   = task_contract.end\n"
                "   - topic_label = task_contract.topic_label（可为空）\n"
                "2. 调用 build_bertopic_insight 时：\n"
                "   - snapshot_json = get_bertopic_snapshot 工具的完整返回值 JSON 字符串\n\n"
                "## 输出目标\n"
                "把结果写入 /workspace/state/bertopic_insight.json。\n"
                "若文件已存在，先 read_file 再 edit_file 更新，禁止 write_file 覆盖。\n\n"
                "## 空结果/降级处理\n"
                "若 get_bertopic_snapshot 返回 status='empty' 或主题为空，\n"
                "生成以下标准化空结构后立即结束，禁止伪造演化趋势：\n"
                '  { "status": "empty", "reason": "BERTopic 快照不存在或主题为空", "result": {}, "skipped_due_to": ["tool_returned_empty"] }\n\n'
                "## 禁止行为\n"
                "- 禁止在没有 temporal 数据时推断主题迁移\n"
                "- 禁止伪造演化趋势或凭空生成主题\n"
            ),
            "tools": bertopic_tools,
            "middleware": middleware_factory("bertopic_evolution_analyst"),
            "skills": _skills_for("bertopic_evolution_analyst", bertopic_tools),
        },
        {
            "name": "decision_utility_judge",
            "description": "负责裁决当前判断对象是否具备进入正式文稿的决策可用性，写入 /workspace/state/utility_assessment.json。",
            "system_prompt": (
                "你是决策可用性裁决代理。\n\n"
                "## 输入来源\n"
                "读取以下文件，按标注提取字段：\n"
                "  /workspace/state/normalized_task.json    → 读取完整内容（JSON 字符串），用于 normalized_task_json 参数\n"
                "  /workspace/state/risk_signals.json       → 提取 .result 数组（完整风险信号对象列表），用于 risk_signals_json 参数\n"
                "  /workspace/state/actor_positions.json    → 提取 .result 数组（完整 actor 对象列表），用于 actor_positions_json 参数\n"
                "  /workspace/state/agenda_frame_map.json   → 提取 .result 字段（内层核心对象），用于 agenda_frame_map_json 参数\n"
                "  /workspace/state/conflict_map.json       → 提取 .result 字段（内层核心对象），用于 conflict_map_json 参数\n"
                "  /workspace/state/mechanism_summary.json  → 提取 .result 字段（内层核心对象），用于 mechanism_summary_json 参数\n"
                "  其余文件（corpus_coverage / evidence_cards / task_derivation）只读，用于判断上游空状态\n\n"
                "## 工具调用规范\n"
                "调用 judge_decision_utility 时（必须显式传参，禁止依赖默认值）：\n"
                "  - normalized_task_json    = normalized_task.json 的完整 JSON 字符串\n"
                "  - risk_signals_json       = risk_signals.result 数组（完整对象列表，禁止传整个包装对象）\n"
                "  - actor_positions_json    = actor_positions.result 数组（完整对象列表，禁止传整个包装对象）\n"
                "  - agenda_frame_map_json   = agenda_frame_map.result 内层核心对象（禁止传整个包装对象）\n"
                "  - conflict_map_json       = conflict_map.result 内层核心对象（禁止传整个包装对象）\n"
                "  - mechanism_summary_json  = mechanism_summary.result 内层核心对象（禁止传整个包装对象）\n\n"
                "## 输出目标\n"
                "把结果写入 /workspace/state/utility_assessment.json，格式：\n"
                "  { 'status': 'ok', 'result': { decision, completeness_score, missing_dimensions, unverified_points, can_proceed_to_writing } }\n"
                "若文件已存在，先 read_file 再 edit_file 更新，禁止 write_file 覆盖。\n\n"
                "## 空结果/降级处理\n"
                "若任一上游文件的 status='empty' 或 skipped_due_to 非空，\n"
                "必须把对应的 skipped_due_to 值写入 result.missing_dimensions，并将 decision 设为 'fallback_recompile' 或 'block'。\n"
                "禁止在上游明确为空时仍输出 decision='pass'。\n\n"
                "## 禁止行为\n"
                "- 禁止直接写正文或用 prose 代替结构化裁决\n"
                "- 禁止把整个包装对象传给工具参数（只传 .result 内层内容）\n"
                "- 禁止在上游空状态时绕过限制放行写作\n"
            ),
            "tools": utility_tools,
            "middleware": middleware_factory("decision_utility_judge"),
            "skills": _skills_for("decision_utility_judge", utility_tools),
        },
        {
            "name": "writer",
            "description": "负责按模板章节进行深度舆情报告写作，产出带证据引证的正式文稿。读取分析结果、证据卡、模板要求，使用 skills 指导写作方法，产出有传播结构分析、因果解释、证据回链的报告正文。",
            "system_prompt": (
                "你是舆情报告深度写作代理。你的职责是按模板章节产出正式报告正文，不是数据拼接。\n\n"
                "## 输入来源\n"
                "必须读取以下文件（按顺序）：\n"
                "  /workspace/state/task_contract.json      → 取 .mode 用于选择模板\n"
                "  /workspace/state/utility_assessment.json → 确认 .result.decision 为 'pass' 或 'fallback_recompile' 后才能开始写作\n"
                "  /workspace/state/event_analysis.json     → 直接引用 .result.actor_distribution.actors[*].key_statements 作为原文引用（禁止重新从 evidence_cards 手动拼装）\n"
                "  /workspace/state/evidence_cards.json     → 完整证据卡（含 snippet/content 字段），用于补充引用\n"
                "  /workspace/state/timeline_nodes.json     → 时间线节点（用于时间线章节）\n"
                "  /workspace/state/actor_positions.json    → 主体立场（用于立场章节）\n"
                "  /workspace/state/conflict_map.json       → 冲突图（用于争议章节）\n"
                "  /workspace/state/mechanism_summary.json  → 传播机制（用于传播章节）\n"
                "  /workspace/state/risk_signals.json       → 风险信号（用于风险章节）\n"
                "  /workspace/state/bertopic_insight.json   → 主题演化（用于主题章节）\n\n"
                "## 工具调用规范\n"
                "1. 首先调用 get_report_template(mode=task_contract.mode) 获取模板：\n"
                "   - mode 必须是 'public_hotspot' / 'crisis_response' / 'policy_dynamics' 之一\n"
                "   - task_contract.mode 若为 'fast'/'full' 则需要映射到模板类型（从 task_derivation.json 读取 report_type 字段）\n"
                "2. 调用 retrieve_evidence_cards 补充章节证据时：\n"
                "   - intent 必须从枚举值中选取（与章节目标匹配）\n"
                "   - 每章至少调用 1 次；若首次证据不足（< 5 条），可追加 1 次分页调用（传 cursor=cursor_next）\n"
                "   - contract_id = task_contract.contract_id\n"
                "3. 调用 build_section_packet 时：\n"
                "   - evidence_ids_json = 该章节引用的 evidence_cards.result[*].evidence_id 字符串列表\n"
                "   - metric_refs_json  = metrics_bundle.result 数组\n\n"
                "## 输出目标\n"
                "每章节使用 edit_file 写入 /workspace/state/section_drafts/{section_id}.json，格式：\n"
                "  { section_id, title, content（完整段落 Markdown），evidence_refs, claim_refs }\n"
                "若文件已存在，先 read_file 再 edit_file 更新，禁止 write_file 覆盖。\n\n"
                "## 内容密度要求\n"
                "- 每章节正文 ≥ 800 字\n"
                "- 每 100 字至少包含 1-2 个具体数据点或原文引用\n"
                "- 每章节至少引用 8-12 条具体用户原文（使用引用格式）\n"
                "- 段落组织：锚定现象 → 交代机制 → 点出含义\n"
                "- 情感强度必须匹配证据确定性（不确定时用审慎语气）\n\n"
                "## 引用格式示例\n"
                "> \"官方回应太慢了，等了14小时才发通报\" —— 贴吧用户（热度：89）\n\n"
                "## 禁止行为\n"
                "- 禁止只写'网友认为'，必须写出具体发言者和原文内容\n"
                "- 禁止暴露系统字段名、工具名、模块名\n"
                "- 禁止使用'舆情爆炸''彻底翻车'等情绪修辞\n"
                "- 禁止在没有证据支撑的情况下下结论\n"
                "- 禁止在 utility_assessment.decision='block' 时开始写作\n"
            ),
            "tools": writer_tools,
            "middleware": middleware_factory("writer"),
            "skills": _skills_for("writer", writer_tools),
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
    coordinator_skill_keys = _get_coordinator_skill_keys()
    if not coordinator_skill_keys:
        coordinator_skill_keys = _COORDINATOR_SKILL_KEYS
    coordinator_skills = select_report_skill_sources(
        skill_assets,
        available_tool_ids=[t.name for t in core_tools if str(getattr(t, "name", "") or "").strip()],
        preferred_skill_keys=coordinator_skill_keys,
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
        "请先使用 write_todos 建立总计划，再严格按以下流程执行，不要跳步，也不要在未调用工具的情况下直接结束：\n\n"
        "1. 使用 task 工具按 Tier 顺序委派子代理：\n"
        "   Tier 0: retrieval_router\n"
        "   Tier 1: archive_evidence_organizer、bertopic_evolution_analyst（并行）\n"
        "   Tier 2: timeline_analyst、stance_conflict（并行）\n"
        "   Tier 3: event_analyst、claim_actor_conflict（并行）\n"
        "   Tier 4: agenda_frame_builder、propagation_analyst（并行）\n"
        "   Tier 5: decision_utility_judge\n\n"
        "2. 每个 Tier 完成后，检查 /workspace/state/ 下对应文件是否已生成且 status 不为 'error'。\n"
        "   若某个文件不存在或 status='error'（而非 'empty'），重新委派该子代理一次。\n"
        "   status='empty' 是合法的降级状态，不需要重试。\n"
        "   必须生成的文件：task_contract、task_derivation、task_derivation_proposal、normalized_task、\n"
        "   retrieval_plan、dispatch_quality、corpus_coverage、evidence_cards、timeline_nodes、\n"
        "   metrics_bundle、actor_positions、event_analysis、conflict_map、agenda_frame_map、\n"
        "   mechanism_summary、risk_signals、bertopic_insight、utility_assessment。\n\n"
        "3. 在 utility_assessment.result.decision 为 'pass' 或 'fallback_recompile' 时，\n"
        "   使用 task 工具委派 writer 子代理进行深度报告写作。\n"
        "   若 decision='block'，在 save_structured_report 中记录 block 原因，直接进入步骤 5。\n\n"
        "4. writer 完成后，读取 /workspace/state/section_drafts/*.json，汇总成完整结构化报告对象。\n\n"
        "5. 调用 save_structured_report 保存结构化对象。\n"
        "   优先直接传 payload 对象，不要把整个结构化 JSON 再包成字符串。\n"
        "   先整理好完整对象，再一次性提交，不要连续试探多个版本。\n"
        "   对象必须包含：task、conclusion、timeline、subjects、stance_matrix、\n"
        "   key_evidence、conflict_points、conflict_map、propagation_features、mechanism_summary、\n"
        "   risk_judgement、unverified_points、suggested_actions、utility_assessment、\n"
        "   citations、validation_notes、section_drafts、event_analysis。\n\n"
        "6. 保存成功后立即结束本轮。禁止再生成 report_draft.md / claim_checks.json / validation_notes.md 等旧中间态。\n\n"
        "默认风格：单次回复尽量研判深刻，不必节省 token，但要尽量减少调用次数。\n"
        "所有关键判断都要尽量带 citation_ids；如果证据不足，请进入 unverified_points。\n"
        f"本次总控最大工具回合：{int(coordinator_tool_round_limit) if coordinator_tool_round_limit is not None else '不限制'}；"
        f"子代理最大工具回合：{int(subagent_tool_round_limit) if subagent_tool_round_limit is not None else '不限制'}。"
    )

    return {
        "agent": agent,
        "coordinator_checkpointer": coordinator_checkpointer,
        "coordinator_runtime_profile": coordinator_runtime_profile,
        "prompt": prompt,
    }


__all__ = ["ReportCoordinatorContext", "build_report_deep_agent"]
