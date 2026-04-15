from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from langchain.tools import tool
from pydantic import BaseModel, Field

from .payloads import (
    build_basic_analysis_insight_payload,
    build_bertopic_insight_payload,
    build_agenda_frame_map_payload,
    build_claim_actor_conflict_payload,
    build_event_timeline_payload,
    build_mechanism_summary_payload,
    build_section_packet_payload,
    compute_report_metrics_payload,
    detect_risk_signals_payload,
    extract_actor_positions_payload,
    get_basic_analysis_snapshot_payload,
    get_corpus_coverage_payload,
    get_bertopic_snapshot_payload,
    judge_decision_utility_payload,
    normalize_task_payload,
    retrieve_evidence_cards_payload,
    verify_claim_payload,
)

# 模板目录
TEMPLATE_DIR = Path(__file__).parent.parent / "templates" / "full_report"


# ========== Input Schemas ==========

class NormalizeTaskInput(BaseModel):
    task_text: str = Field(
        ...,
        description="用户原始任务描述文本，定义分析目标和研究范围"
    )
    topic_identifier: str = Field(
        ...,
        description="专题唯一标识符，用于绑定 corpus 和后续检索"
    )
    start: str = Field(
        ...,
        description="时间窗口起始日期，格式 YYYY-MM-DD"
    )
    end: str = Field(
        ...,
        description="时间窗口结束日期，格式 YYYY-MM-DD"
    )
    mode: str = Field(
        default="fast",
        description="执行模式: 'fast' 快速模式或 'full' 完整深度分析"
    )
    hints_json: str = Field(
        default="{}",
        description="可选提示参数 JSON，用于微调分析策略"
    )


class GetCorpusCoverageInput(BaseModel):
    contract_id: str = Field(
        ...,
        description="来自 normalize_task 的 contract ID，用于解析专题身份"
    )
    retrieval_scope_json: str = Field(
        default="{}",
        description="检索范围参数 JSON，用于受控裁剪时间/来源范围"
    )
    filters_json: str = Field(
        default="{}",
        description="额外过滤条件 JSON，如来源类型、情感倾向等"
    )
    include_samples: bool = Field(
        default=False,
        description="是否在结果中包含样本文档内容"
    )
    limit: int = Field(
        default=20,
        ge=1,
        le=30,
        description="返回结果数量上限，范围 1-30"
    )


class RetrieveEvidenceCardsInput(BaseModel):
    contract_id: str = Field(
        ...,
        description="来自 normalize_task 的 contract ID，用于解析专题身份"
    )
    retrieval_scope_json: str = Field(
        default="{}",
        description="检索范围参数 JSON，用于受控裁剪时间/来源范围"
    )
    intent: Literal["overview", "timeline", "actors", "risk", "claim_support", "claim_counter"] = Field(
        default="overview",
        description=(
            "检索意图，控制排序与筛选策略。必须从以下枚举值中选取：\n"
            "  overview      — 综合全览（默认）\n"
            "  timeline      — 时间线与演化事件\n"
            "  actors        — 主体与立场\n"
            "  risk          — 风险信号\n"
            "  claim_support — 断言/论点的支持证据\n"
            "  claim_counter — 断言/论点的反证\n"
            "中文语义词映射：传播总览→overview，时间线/演化→timeline，主体立场→actors，"
            "风险信号→risk，争议焦点支持→claim_support，争议焦点反证→claim_counter。"
            "禁止直接传中文词或超出枚举范围的自造值。"
        )
    )
    filters_json: str = Field(
        default="{}",
        description="额外过滤条件 JSON"
    )
    sort_by: str = Field(
        default="relevance",
        description="排序方式: 'relevance' 相关性, 'time' 时间, 'sentiment' 情感"
    )
    limit: int = Field(
        default=12,
        ge=1,
        le=20,
        description="每页返回数量上限，范围 1-20"
    )
    cursor: str = Field(
        default="",
        description="分页游标，用于获取下一页结果"
    )


class BuildEventTimelineInput(BaseModel):
    normalized_task_json: str = Field(
        ...,
        description=(
            "来自 normalize_task 工具的返回值，或读取 /workspace/state/normalized_task.json 的完整内容（JSON 字符串）。"
            "工具内部只提取 contract_id、topic_identifier、start、end、mode 字段，可传顶层对象或 result 子字段。"
        )
    )
    evidence_ids_json: str = Field(
        default="[]",
        description=(
            "证据卡 ID 字符串列表的 JSON，格式为 [\"ev-001\", \"ev-002\", ...]。"
            "必须从 evidence_cards.json 的 .result[*].evidence_id 字段提取，"
            "禁止传整个 evidence_cards 对象或 result 中的完整证据卡对象。"
        )
    )
    max_nodes: int = Field(
        default=8,
        ge=1,
        le=12,
        description="时间线节点数量上限，范围 1-12"
    )


class ComputeReportMetricsInput(BaseModel):
    normalized_task_json: str = Field(
        ...,
        description=(
            "来自 normalize_task 工具的返回值，或读取 /workspace/state/normalized_task.json 的完整内容（JSON 字符串）。"
            "工具内部只提取 contract_id、topic_identifier、start、end、mode 字段，可传顶层对象或 result 子字段。"
        )
    )
    metric_scope: str = Field(
        default="overview",
        description="指标范围: 'overview' 全览, 'sentiment' 情感, 'source' 来源分布"
    )
    evidence_ids_json: str = Field(
        default="[]",
        description=(
            "证据卡 ID 字符串列表的 JSON，格式为 [\"ev-001\", \"ev-002\", ...]。"
            "必须从 evidence_cards.json 的 .result[*].evidence_id 字段提取，"
            "禁止传整个 evidence_cards 对象或 result 中的完整证据卡对象。"
        )
    )


class ExtractActorPositionsInput(BaseModel):
    normalized_task_json: str = Field(
        ...,
        description=(
            "来自 normalize_task 工具的返回值，或读取 /workspace/state/normalized_task.json 的完整内容（JSON 字符串）。"
            "工具内部只提取 contract_id、topic_identifier、start、end、mode 字段，可传顶层对象或 result 子字段。"
        )
    )
    evidence_ids_json: str = Field(
        default="[]",
        description=(
            "证据卡 ID 字符串列表的 JSON，格式为 [\"ev-001\", \"ev-002\", ...]。"
            "必须从 evidence_cards.json 的 .result[*].evidence_id 字段提取，"
            "禁止传整个 evidence_cards 对象或 result 中的完整证据卡对象。"
        )
    )
    actor_limit: int = Field(
        default=10,
        ge=1,
        le=16,
        description="主体数量上限，范围 1-16"
    )


class BuildAgendaFrameMapInput(BaseModel):
    normalized_task_json: str = Field(
        ...,
        description=(
            "来自 normalize_task 工具的返回值，或读取 /workspace/state/normalized_task.json 的完整内容（JSON 字符串）。"
            "工具内部只提取 contract_id、topic_identifier、start、end、mode 字段，可传顶层对象或 result 子字段。"
        )
    )
    evidence_ids_json: str = Field(
        default="[]",
        description=(
            "证据卡 ID 字符串列表的 JSON，格式为 [\"ev-001\", \"ev-002\", ...]。"
            "必须从 evidence_cards.json 的 .result[*].evidence_id 字段提取，禁止传整个对象。"
        )
    )
    actor_positions_json: str = Field(
        default="[]",
        description=(
            "主体立场完整对象列表的 JSON。"
            "必须从 actor_positions.json 的 .result 数组提取（完整 actor 对象，而非仅 ID）。"
            "禁止传整个 actor_positions 包装对象。"
        )
    )
    conflict_map_json: str = Field(
        default="{}",
        description=(
            "冲突图核心对象的 JSON。"
            "必须从 conflict_map.json 的 .result 字段提取（内层核心对象，而非整个包装对象）。"
        )
    )
    timeline_nodes_json: str = Field(
        default="[]",
        description=(
            "时间线节点完整对象列表的 JSON。"
            "必须从 timeline_nodes.json 的 .result 数组提取（完整节点对象，而非仅 ID）。"
            "禁止传整个 timeline_nodes 包装对象。"
        )
    )


class BuildClaimActorConflictInput(BaseModel):
    normalized_task_json: str = Field(
        ...,
        description=(
            "来自 normalize_task 工具的返回值，或读取 /workspace/state/normalized_task.json 的完整内容（JSON 字符串）。"
            "工具内部只提取 contract_id、topic_identifier、start、end、mode 字段，可传顶层对象或 result 子字段。"
        )
    )
    evidence_ids_json: str = Field(
        default="[]",
        description=(
            "证据卡 ID 字符串列表的 JSON，格式为 [\"ev-001\", \"ev-002\", ...]。"
            "必须从 evidence_cards.json 的 .result[*].evidence_id 字段提取，禁止传整个对象。"
        )
    )
    actor_positions_json: str = Field(
        default="[]",
        description=(
            "主体立场完整对象列表的 JSON。"
            "必须从 actor_positions.json 的 .result 数组提取（完整 actor 对象，而非仅 ID）。"
            "禁止传整个 actor_positions 包装对象。"
        )
    )
    timeline_nodes_json: str = Field(
        default="[]",
        description=(
            "时间线节点完整对象列表的 JSON。"
            "必须从 timeline_nodes.json 的 .result 数组提取（完整节点对象，而非仅 ID）。"
            "禁止传整个 timeline_nodes 包装对象。"
        )
    )


class BuildMechanismSummaryInput(BaseModel):
    normalized_task_json: str = Field(
        ...,
        description=(
            "来自 normalize_task 工具的返回值，或读取 /workspace/state/normalized_task.json 的完整内容（JSON 字符串）。"
            "工具内部只提取 contract_id、topic_identifier、start、end、mode 字段，可传顶层对象或 result 子字段。"
        )
    )
    evidence_ids_json: str = Field(
        default="[]",
        description=(
            "证据卡 ID 字符串列表的 JSON，格式为 [\"ev-001\", \"ev-002\", ...]。"
            "必须从 evidence_cards.json 的 .result[*].evidence_id 字段提取，禁止传整个对象。"
        )
    )
    timeline_nodes_json: str = Field(
        default="[]",
        description=(
            "时间线节点完整对象列表的 JSON。"
            "必须从 timeline_nodes.json 的 .result 数组提取（完整节点对象，而非仅 ID）。"
            "禁止传整个 timeline_nodes 包装对象。"
        )
    )
    conflict_map_json: str = Field(
        default="{}",
        description=(
            "冲突图核心对象的 JSON。"
            "必须从 conflict_map.json 的 .result 字段提取（内层核心对象，而非整个包装对象）。"
        )
    )
    metric_refs_json: str = Field(
        default="[]",
        description=(
            "指标对象列表的 JSON。"
            "必须从 metrics_bundle.json 的 .result 数组提取（完整指标对象，而非仅引用 ID）。"
            "禁止传整个 metrics_bundle 包装对象。"
        )
    )


class DetectRiskSignalsInput(BaseModel):
    normalized_task_json: str = Field(
        ...,
        description=(
            "来自 normalize_task 工具的返回值，或读取 /workspace/state/normalized_task.json 的完整内容（JSON 字符串）。"
            "工具内部只提取 contract_id、topic_identifier、start、end、mode 字段，可传顶层对象或 result 子字段。"
        )
    )
    evidence_ids_json: str = Field(
        default="[]",
        description=(
            "证据卡 ID 字符串列表的 JSON，格式为 [\"ev-001\", \"ev-002\", ...]。"
            "必须从 evidence_cards.json 的 .result[*].evidence_id 字段提取，禁止传整个对象。"
        )
    )
    metric_refs_json: str = Field(
        default="[]",
        description=(
            "指标对象列表的 JSON。"
            "必须从 metrics_bundle.json 的 .result 数组提取（完整指标对象，而非仅引用 ID）。"
        )
    )
    discourse_conflict_map_json: str = Field(
        default="",
        description=(
            "话语冲突图核心对象的 JSON，用于识别争议焦点。"
            "必须从 conflict_map.json 的 .result 字段提取（内层核心对象，而非整个包装对象）。"
            "若 conflict_map.json 不存在或为空，传空字符串 ''。"
        )
    )
    actor_positions_json: str = Field(
        default="[]",
        description=(
            "主体立场完整对象列表的 JSON。"
            "必须从 actor_positions.json 的 .result 数组提取（完整 actor 对象，而非仅 ID）。"
            "禁止传整个 actor_positions 包装对象。"
        )
    )


class JudgeDecisionUtilityInput(BaseModel):
    normalized_task_json: str = Field(
        ...,
        description=(
            "来自 normalize_task 工具的返回值，或读取 /workspace/state/normalized_task.json 的完整内容（JSON 字符串）。"
            "工具内部只提取 contract_id、topic_identifier、start、end、mode 字段，可传顶层对象或 result 子字段。"
        )
    )
    risk_signals_json: str = Field(
        default="[]",
        description=(
            "风险信号列表的 JSON。"
            "必须从 risk_signals.json 的 .result 数组提取（完整风险信号对象列表）。"
            "禁止传整个 risk_signals 包装对象。"
        )
    )
    recommendation_candidates_json: str = Field(
        default="[]",
        description="候选建议列表 JSON"
    )
    unresolved_points_json: str = Field(
        default="[]",
        description="未解决争议点列表 JSON"
    )
    agenda_frame_map_json: str = Field(
        default="{}",
        description=(
            "议题框架图核心对象的 JSON。"
            "必须从 agenda_frame_map.json 的 .result 字段提取（内层核心对象，而非整个包装对象）。"
        )
    )
    conflict_map_json: str = Field(
        default="{}",
        description=(
            "冲突图核心对象的 JSON。"
            "必须从 conflict_map.json 的 .result 字段提取（内层核心对象，而非整个包装对象）。"
        )
    )
    mechanism_summary_json: str = Field(
        default="{}",
        description=(
            "传播机制摘要核心对象的 JSON。"
            "必须从 mechanism_summary.json 的 .result 字段提取（内层核心对象，而非整个包装对象）。"
        )
    )
    actor_positions_json: str = Field(
        default="[]",
        description=(
            "主体立场完整对象列表的 JSON。"
            "必须从 actor_positions.json 的 .result 数组提取（完整 actor 对象，而非仅 ID）。"
            "禁止传整个 actor_positions 包装对象。"
        )
    )


class VerifyClaimV2Input(BaseModel):
    normalized_task_json: str = Field(
        ...,
        description=(
            "来自 normalize_task 工具的返回值，或读取 /workspace/state/normalized_task.json 的完整内容（JSON 字符串）。"
            "工具内部只提取 contract_id、topic_identifier、start、end、mode 字段，可传顶层对象或 result 子字段。"
        )
    )
    claims_json: str = Field(
        ...,
        description="待校验的断言列表 JSON，每个断言包含文本和来源"
    )
    evidence_ids_json: str = Field(
        default="[]",
        description=(
            "证据卡 ID 字符串列表的 JSON，格式为 [\"ev-001\", \"ev-002\", ...]。"
            "必须从 evidence_cards.json 的 .result[*].evidence_id 字段提取，禁止传整个对象。"
        )
    )
    strictness: str = Field(
        default="balanced",
        description="校验严格度: 'strict' 严格, 'balanced' 平衡, 'loose'宽松"
    )


class GetBasicAnalysisSnapshotInput(BaseModel):
    topic_identifier: str = Field(
        ...,
        description="专题唯一标识符"
    )
    start: str = Field(
        ...,
        description="时间窗口起始日期，格式 YYYY-MM-DD"
    )
    end: str = Field(
        default="",
        description="时间窗口结束日期，默认等于 start"
    )
    topic_label: str = Field(
        default="",
        description="专题显示名称，可选"
    )


class BuildBasicAnalysisInsightInput(BaseModel):
    snapshot_json: str = Field(
        ...,
        description="来自 get_basic_analysis_snapshot 的快照 JSON"
    )


class GetBertopicSnapshotInput(BaseModel):
    topic_identifier: str = Field(
        ...,
        description="专题唯一标识符"
    )
    start: str = Field(
        ...,
        description="时间窗口起始日期，格式 YYYY-MM-DD"
    )
    end: str = Field(
        default="",
        description="时间窗口结束日期，默认等于 start"
    )
    topic_label: str = Field(
        default="",
        description="专题显示名称，可选"
    )


class BuildBertopicInsightInput(BaseModel):
    snapshot_json: str = Field(
        ...,
        description="来自 get_bertopic_snapshot 的快照 JSON"
    )


class BuildSectionPacketInput(BaseModel):
    normalized_task_json: str = Field(
        ...,
        description=(
            "来自 normalize_task 工具的返回值，或读取 /workspace/state/normalized_task.json 的完整内容（JSON 字符串）。"
            "工具内部只提取 contract_id、topic_identifier、start、end、mode 字段，可传顶层对象或 result 子字段。"
        )
    )
    section_id: str = Field(
        ...,
        description="章节唯一标识符，如 'overview', 'timeline', 'conclusion'"
    )
    section_goal: str = Field(
        default="",
        description="章节写作目标描述"
    )
    evidence_ids_json: str = Field(
        default="[]",
        description=(
            "章节引用的证据卡 ID 字符串列表的 JSON，格式为 [\"ev-001\", \"ev-002\", ...]。"
            "从 evidence_cards.json 的 .result[*].evidence_id 字段提取。"
        )
    )
    metric_refs_json: str = Field(
        default="[]",
        description=(
            "章节引用的指标对象列表的 JSON。"
            "从 metrics_bundle.json 的 .result 数组提取（完整指标对象）。"
        )
    )
    claim_ids_json: str = Field(
        default="[]",
        description="章节引用的断言 ID 列表 JSON"
    )


# ========== Tool Definitions ==========

@tool(args_schema=NormalizeTaskInput)
def normalize_task(
    task_text: str,
    topic_identifier: str,
    start: str,
    end: str,
    mode: str = "fast",
    hints_json: str = "{}",
) -> str:
    """冻结任务边界并生成可复用的 task contract，不执行原始文档检索。

    返回标准化任务 JSON，包含 contract_id、topic_identifier、时间范围和执行模式。
    后续所有工具调用都依赖此 contract 进行专题绑定和范围控制。

    Returns:
        JSON 对象，顶层字段：
          status: str          — "ok"
          contract_id: str     — 任务合约唯一标识，后续所有工具必须使用此 ID
          topic_identifier: str
          start: str           — YYYY-MM-DD
          end: str             — YYYY-MM-DD
          mode: str            — "fast" | "full"
          result: dict         — 完整归一化任务对象（可整体传给 normalized_task_json 参数）

        下游传参约定：
          normalized_task_json → 传本工具返回值的完整 JSON 字符串，或 result 子字段的 JSON 字符串
          contract_id          → 直接取顶层 contract_id 字段
    """
    return json.dumps(
        normalize_task_payload(
            task_text=str(task_text or "").strip(),
            topic_identifier=str(topic_identifier or "").strip(),
            start=str(start or "").strip(),
            end=str(end or "").strip(),
            mode=str(mode or "fast").strip().lower() or "fast",
            hints_json=str(hints_json or "{}"),
        ),
        ensure_ascii=False,
        indent=2,
    )


@tool(args_schema=GetCorpusCoverageInput)
def get_corpus_coverage(
    contract_id: str,
    retrieval_scope_json: str = "{}",
    filters_json: str = "{}",
    include_samples: bool = False,
    limit: int = 20,
) -> str:
    """诊断 contract 绑定专题在当前 scope 下的覆盖与缺口。

    返回覆盖统计、缺口分析和可选样本文档。
    专题身份固定由 contract_id 解析，时间窗口只作为受控 scope 参数。

    Returns:
        JSON 对象，顶层字段：
          status: str                 — "ok" | "empty"
          coverage: dict              — 覆盖信息对象
            .total_records: int       — 语料总条数
            .readiness_flags: list    — 可能含 "no_records_in_scope"、"partial_coverage"
            .time_distribution: dict  — 时间分布统计
          samples: list               — 样本文档列表（仅 include_samples=True 时有内容）

        下游传参约定：
          coverage.readiness_flags 若含 "no_records_in_scope" → 后续分析应生成空结果
          coverage.readiness_flags 若含 "partial_coverage"    → 可考虑扩大时间窗后重试一次
    """
    return json.dumps(
        get_corpus_coverage_payload(
            contract_id=str(contract_id or "").strip(),
            retrieval_scope_json=str(retrieval_scope_json or "{}"),
            filters_json=str(filters_json or "{}"),
            include_samples=bool(include_samples),
            limit=max(1, min(int(limit or 20), 30)),
        ),
        ensure_ascii=False,
        indent=2,
    )


@tool(args_schema=RetrieveEvidenceCardsInput)
def retrieve_evidence_cards(
    contract_id: str,
    retrieval_scope_json: str = "{}",
    intent: str = "overview",
    filters_json: str = "{}",
    sort_by: str = "relevance",
    limit: int = 12,
    cursor: str = "",
) -> str:
    """按意图返回分页证据卡。

    证据卡包含文档元数据、关键片段和情感标签。
    专题身份固定由 contract_id 解析，时间范围通过 retrieval_scope 做受控裁剪。

    Returns:
        JSON 对象，顶层字段：
          status: str            — "ok" | "empty"
          result: list[dict]     — 证据卡列表，每条包含：
            .evidence_id: str    — 证据唯一 ID（用于传给 evidence_ids_json 参数）
            .snippet: str        — 关键文本片段（引用原文来源）
            .content: str        — 完整内容
            .source: str         — 来源平台
            .sentiment: str      — 情感标签
            .publish_time: str   — 发布时间
          coverage: dict         — 含 readiness_flags 列表
          cursor_next: str       — 下一页游标，空字符串表示无更多

        下游传参约定：
          evidence_ids_json      → 提取 result[*].evidence_id 组成字符串列表，格式 ["ev-001", "ev-002", ...]
          分页策略：若 cursor_next 非空且当前证据数 < 20，可追加一次调用传入 cursor=cursor_next
    """
    return json.dumps(
        retrieve_evidence_cards_payload(
            contract_id=str(contract_id or "").strip(),
            retrieval_scope_json=str(retrieval_scope_json or "{}"),
            intent=str(intent or "").strip(),
            filters_json=str(filters_json or "{}"),
            sort_by=str(sort_by or "relevance").strip(),
            limit=max(1, min(int(limit or 12), 20)),
            cursor=str(cursor or "").strip(),
        ),
        ensure_ascii=False,
        indent=2,
    )


@tool(args_schema=BuildEventTimelineInput)
def build_event_timeline(
    normalized_task_json: str,
    evidence_ids_json: str = "[]",
    max_nodes: int = 8,
) -> str:
    """将证据卡压缩成时间线节点，节点必须带支持或冲突证据。

    返回按时间排序的事件节点列表，每个节点包含日期、事件描述、相关主体和证据引用。

    Returns:
        JSON 对象，顶层字段：
          status: str                      — "ok" | "empty"
          result: list[dict]               — 时间线节点列表，写入 timeline_nodes.json
            .node_id: str
            .time_label: str               — 时间标签
            .summary: str                  — 节点摘要
            .support_evidence_ids: list    — 支持证据 ID 列表
            .conflict_evidence_ids: list   — 反证 ID 列表（可为空）
            .confidence: str
            .event_type: str

        下游传参约定：
          timeline_nodes_json → 传 result 数组（完整节点对象列表，非仅 ID）
    """
    return json.dumps(
        build_event_timeline_payload(
            normalized_task_json=str(normalized_task_json or "{}"),
            evidence_ids_json=str(evidence_ids_json or "[]"),
            max_nodes=max(1, min(int(max_nodes or 8), 12)),
        ),
        ensure_ascii=False,
        indent=2,
    )


@tool(args_schema=ComputeReportMetricsInput)
def compute_report_metrics(
    normalized_task_json: str,
    metric_scope: str = "overview",
    evidence_ids_json: str = "[]",
) -> str:
    """生成强分类、chart-ready 的指标对象，不直接输出自然语言结论。

    返回结构化指标数据，包括数量统计、情感分布、来源分布等，可直接用于图表渲染。

    Returns:
        JSON 对象，顶层字段：
          status: str          — "ok" | "empty"
          result: list[dict]   — 指标对象列表，写入 metrics_bundle.json
            每个指标含 family（"temporal"|"overview"|"sentiment"|"source"）、
            metric_id、label、value、chart_type 等字段

        下游传参约定：
          metric_refs_json → 传 result 数组（完整指标对象列表，非仅 ID）
    """
    return json.dumps(
        compute_report_metrics_payload(
            normalized_task_json=str(normalized_task_json or "{}"),
            metric_scope=str(metric_scope or "overview").strip(),
            evidence_ids_json=str(evidence_ids_json or "[]"),
        ),
        ensure_ascii=False,
        indent=2,
    )


@tool(args_schema=ExtractActorPositionsInput)
def extract_actor_positions(
    normalized_task_json: str,
    evidence_ids_json: str = "[]",
    actor_limit: int = 10,
) -> str:
    """抽取主体、立场、冲突关系，不负责最终 prose 写作。

    返回主体列表，每个主体包含名称、角色类型、立场倾向和关键表态证据。

    Returns:
        JSON 对象，顶层字段：
          status: str           — "ok" | "empty"
          result: list[dict]    — 主体立场列表，写入 actor_positions.json
            .actor_id: str
            .name: str
            .type: str          — 主体类型（媒体/政府/企业/KOL/普通用户等）
            .stance: str        — 立场倾向
            .evidence_ids: list — 支撑证据 ID 列表
            .key_statements: list — 关键表态原文列表

        下游传参约定：
          actor_positions_json → 传 result 数组（完整 actor 对象列表，非仅 ID）
    """
    return json.dumps(
        extract_actor_positions_payload(
            normalized_task_json=str(normalized_task_json or "{}"),
            evidence_ids_json=str(evidence_ids_json or "[]"),
            actor_limit=max(1, min(int(actor_limit or 10), 16)),
        ),
        ensure_ascii=False,
        indent=2,
    )


@tool(args_schema=BuildAgendaFrameMapInput)
def build_agenda_frame_map(
    normalized_task_json: str,
    evidence_ids_json: str = "[]",
    actor_positions_json: str = "[]",
    conflict_map_json: str = "{}",
    timeline_nodes_json: str = "[]",
) -> str:
    """构建议题-属性-框架图，只输出 typed analysis artifact。

    返回议题框架分析结果，包含核心议题、争议焦点和各主体框架倾向。

    Returns:
        JSON 对象，顶层字段：
          status: str           — "ok" | "empty"
          result: dict          — 议题框架图核心对象，写入 agenda_frame_map.json
            .issue_nodes: list  — 议题节点列表（含时间戳和证据支撑）
            .frame_records: list — 框架记录（主体 × 框架 × 时间）
            .frame_shifts: list  — 框架转换事件
            .counter_frames: list — 反框架列表

        下游传参约定：
          agenda_frame_map_json → 传 result 字段内容（内层核心对象，非整个包装对象）
    """
    return json.dumps(
        build_agenda_frame_map_payload(
            normalized_task_json=str(normalized_task_json or "{}"),
            evidence_ids_json=str(evidence_ids_json or "[]"),
            actor_positions_json=str(actor_positions_json or "[]"),
            conflict_map_json=str(conflict_map_json or "{}"),
            timeline_nodes_json=str(timeline_nodes_json or "[]"),
        ),
        ensure_ascii=False,
        indent=2,
    )


@tool(args_schema=BuildClaimActorConflictInput)
def build_claim_actor_conflict(
    normalized_task_json: str,
    evidence_ids_json: str = "[]",
    actor_positions_json: str = "[]",
    timeline_nodes_json: str = "[]",
) -> str:
    """构建断言-主体冲突图，只输出 typed judgment objects。

    返回冲突关系图，包含关键断言、支持/反对主体、冲突强度和证据支撑。

    Returns:
        JSON 对象，顶层字段：
          status: str              — "ok" | "empty"
          result: dict             — 冲突图核心对象，写入 conflict_map.json
            .claim_nodes: list     — 断言节点列表（含证据 ID）
            .actor_positions: list — 主体立场摘要
            .conflict_edges: list  — 冲突边（主体 × 断言 × 立场）
            .resolution_states: list — 冲突解决状态

        下游传参约定：
          conflict_map_json → 传 result 字段内容（内层核心对象，非整个包装对象）
    """
    return json.dumps(
        build_claim_actor_conflict_payload(
            normalized_task_json=str(normalized_task_json or "{}"),
            evidence_ids_json=str(evidence_ids_json or "[]"),
            actor_positions_json=str(actor_positions_json or "[]"),
            timeline_nodes_json=str(timeline_nodes_json or "[]"),
        ),
        ensure_ascii=False,
        indent=2,
    )


@tool(args_schema=BuildMechanismSummaryInput)
def build_mechanism_summary(
    normalized_task_json: str,
    evidence_ids_json: str = "[]",
    timeline_nodes_json: str = "[]",
    conflict_map_json: str = "{}",
    metric_refs_json: str = "[]",
) -> str:
    """提炼传播路径、触发事件与阶段跃迁，不直接输出 prose。

    返回传播机制分析结果，包含关键节点、传播路径、触发因素和阶段划分。

    Returns:
        JSON 对象，顶层字段：
          status: str               — "ok" | "empty"
          result: dict              — 传播机制摘要核心对象，写入 mechanism_summary.json
            .trigger_events: list   — 触发事件列表
            .propagation_path: list — 传播路径节点
            .phase_transitions: list — 阶段跃迁说明
            .amplification_nodes: list — 热度放大节点

        下游传参约定：
          mechanism_summary_json → 传 result 字段内容（内层核心对象，非整个包装对象）
    """
    return json.dumps(
        build_mechanism_summary_payload(
            normalized_task_json=str(normalized_task_json or "{}"),
            evidence_ids_json=str(evidence_ids_json or "[]"),
            timeline_nodes_json=str(timeline_nodes_json or "[]"),
            conflict_map_json=str(conflict_map_json or "{}"),
            metric_refs_json=str(metric_refs_json or "[]"),
        ),
        ensure_ascii=False,
        indent=2,
    )


@tool(args_schema=DetectRiskSignalsInput)
def detect_risk_signals(
    normalized_task_json: str,
    evidence_ids_json: str = "[]",
    metric_refs_json: str = "[]",
    discourse_conflict_map_json: str = "",
    actor_positions_json: str = "[]",
) -> str:
    """输出风险项对象，优先基于 evidence/metrics/conflict map，而不是直接写建议。

    返回风险信号列表，包含风险类型、严重程度、影响范围和缓解建议方向。

    Returns:
        JSON 对象，顶层字段：
          status: str             — "ok" | "empty"
          result: list[dict]      — 风险信号列表，写入 risk_signals.json
            .signal_id: str
            .risk_type: str       — 风险类型
            .severity: str        — 严重程度
            .trigger_condition: str — 触发条件
            .impact_scope: str    — 影响范围
            .evidence_ids: list   — 支撑证据 ID 列表

        下游传参约定：
          risk_signals_json → 传 result 数组（完整风险信号对象列表，非仅 ID）
    """
    return json.dumps(
        detect_risk_signals_payload(
            normalized_task_json=str(normalized_task_json or "{}"),
            evidence_ids_json=str(evidence_ids_json or "[]"),
            metric_refs_json=str(metric_refs_json or "[]"),
            discourse_conflict_map_json=str(discourse_conflict_map_json or ""),
            actor_positions_json=str(actor_positions_json or "[]"),
        ),
        ensure_ascii=False,
        indent=2,
    )


@tool(args_schema=JudgeDecisionUtilityInput)
def judge_decision_utility(
    normalized_task_json: str,
    risk_signals_json: str = "[]",
    recommendation_candidates_json: str = "[]",
    unresolved_points_json: str = "[]",
    agenda_frame_map_json: str = "{}",
    conflict_map_json: str = "{}",
    mechanism_summary_json: str = "{}",
    actor_positions_json: str = "[]",
) -> str:
    """评估当前判断对象是否已具备进入正式文稿的决策可用性。

    返回决策可用性评估结果，包含完整性评分、缺口分析和是否可进入写作阶段。

    Returns:
        JSON 对象，顶层字段：
          status: str               — "ok"
          result: dict              — 裁决对象，写入 utility_assessment.json
            .decision: str          — "pass" | "fallback_recompile" | "block"
            .completeness_score: float
            .missing_dimensions: list  — 缺失维度列表（若上游为 empty，必须记录原因）
            .unverified_points: list   — 未验证关键点
            .can_proceed_to_writing: bool

        下游传参约定：
          utility_assessment.result.decision 为 "pass" 或 "fallback_recompile" 时才能进入 writer 阶段
    """
    return json.dumps(
        judge_decision_utility_payload(
            normalized_task_json=str(normalized_task_json or "{}"),
            risk_signals_json=str(risk_signals_json or "[]"),
            recommendation_candidates_json=str(recommendation_candidates_json or "[]"),
            unresolved_points_json=str(unresolved_points_json or "[]"),
            agenda_frame_map_json=str(agenda_frame_map_json or "{}"),
            conflict_map_json=str(conflict_map_json or "{}"),
            mechanism_summary_json=str(mechanism_summary_json or "{}"),
            actor_positions_json=str(actor_positions_json or "[]"),
        ),
        ensure_ascii=False,
        indent=2,
    )


@tool(args_schema=VerifyClaimV2Input)
def verify_claim_v2(
    normalized_task_json: str,
    claims_json: str,
    evidence_ids_json: str = "[]",
    strictness: str = "balanced",
) -> str:
    """对句级断言做回链校验，返回支持、反证和缺口。

    返回校验结果，包含每个断言的支持证据、反证证据和验证状态。
    """
    return json.dumps(
        verify_claim_payload(
            normalized_task_json=str(normalized_task_json or "{}"),
            claims_json=str(claims_json or "[]"),
            evidence_ids_json=str(evidence_ids_json or "[]"),
            strictness=str(strictness or "balanced").strip(),
        ),
        ensure_ascii=False,
        indent=2,
    )


@tool(args_schema=GetBasicAnalysisSnapshotInput)
def get_basic_analysis_snapshot(
    topic_identifier: str,
    start: str,
    end: str = "",
    topic_label: str = "",
) -> str:
    """读取基础分析归档快照，只做能力诊断和归档读取。

    返回基础分析结果快照，包含数量统计、情感分布、关键主题等。

    Returns:
        JSON 对象，顶层字段：
          status: str        — "ok" | "empty"（快照不存在时为 empty）
          result: dict       — 快照内容（传给 build_basic_analysis_insight 的 snapshot_json 参数）

        下游传参约定：
          snapshot_json → 传本工具返回值的完整 JSON 字符串（或其 result 子字段的 JSON 字符串）
    """
    return json.dumps(
        get_basic_analysis_snapshot_payload(
            topic_identifier=str(topic_identifier or "").strip(),
            start=str(start or "").strip(),
            end=str(end or "").strip() or str(start or "").strip(),
            topic_label=str(topic_label or "").strip(),
        ),
        ensure_ascii=False,
        indent=2,
    )


@tool(args_schema=BuildBasicAnalysisInsightInput)
def build_basic_analysis_insight(snapshot_json: str) -> str:
    """把基础分析快照转换成报告可消费的章节洞察对象。

    返回结构化洞察结果，可直接作为报告章节内容引用。

    Returns:
        JSON 对象，顶层字段：
          status: str       — "ok" | "empty"
          result: dict      — 章节洞察对象（含量化数据和关键发现列表）
    """
    return json.dumps(
        build_basic_analysis_insight_payload(snapshot_json=str(snapshot_json or "{}")),
        ensure_ascii=False,
        indent=2,
    )


@tool(args_schema=GetBertopicSnapshotInput)
def get_bertopic_snapshot(
    topic_identifier: str,
    start: str,
    end: str = "",
    topic_label: str = "",
) -> str:
    """读取 BERTopic 归档快照，只做能力诊断和归档读取。

    返回 BERTopic 主题演化分析结果，包含主题聚类、演化轨迹等。

    Returns:
        JSON 对象，顶层字段：
          status: str        — "ok" | "empty"（快照不存在或主题为空时为 empty）
          result: dict       — 快照内容（传给 build_bertopic_insight 的 snapshot_json 参数）

        下游传参约定：
          snapshot_json → 传本工具返回值的完整 JSON 字符串（或其 result 子字段的 JSON 字符串）
    """
    return json.dumps(
        get_bertopic_snapshot_payload(
            topic_identifier=str(topic_identifier or "").strip(),
            start=str(start or "").strip(),
            end=str(end or "").strip() or str(start or "").strip(),
            topic_label=str(topic_label or "").strip(),
        ),
        ensure_ascii=False,
        indent=2,
    )


@tool(args_schema=BuildBertopicInsightInput)
def build_bertopic_insight(snapshot_json: str) -> str:
    """把 BERTopic 快照转换成报告可消费的主题演化章节洞察对象。

    返回结构化主题演化洞察，可直接作为报告章节内容引用。

    Returns:
        JSON 对象，顶层字段：
          status: str       — "ok" | "empty"
          result: dict      — 主题演化洞察对象（含主题聚类、演化阶段、背景常量与爆发变量）
    """
    return json.dumps(
        build_bertopic_insight_payload(snapshot_json=str(snapshot_json or "{}")),
        ensure_ascii=False,
        indent=2,
    )


@tool(args_schema=BuildSectionPacketInput)
def build_section_packet(
    normalized_task_json: str,
    section_id: str,
    section_goal: str = "",
    evidence_ids_json: str = "[]",
    metric_refs_json: str = "[]",
    claim_ids_json: str = "[]",
) -> str:
    """组装章节材料包，作为 writer 的直接输入。

    返回章节材料包，包含章节目标、引用素材和写作指导。

    Returns:
        JSON 对象，顶层字段：
          status: str          — "ok" | "empty"
          result: dict         — 章节材料包
            .section_id: str
            .section_goal: str
            .evidence_cards: list  — 完整证据卡对象列表（含 snippet/content）
            .metrics: list         — 完整指标对象列表
            .writing_hints: list   — 写作提示
    """
    return json.dumps(
        build_section_packet_payload(
            normalized_task_json=str(normalized_task_json or "{}"),
            section_id=str(section_id or "").strip(),
            section_goal=str(section_goal or "").strip(),
            evidence_ids_json=str(evidence_ids_json or "[]"),
            metric_refs_json=str(metric_refs_json or "[]"),
            claim_ids_json=str(claim_ids_json or "[]"),
        ),
        ensure_ascii=False,
        indent=2,
    )


# ========== Report Template Tool ==========

class GetReportTemplateInput(BaseModel):
    mode: str = Field(
        ...,
        description="报告模式，决定使用哪个模板。可选值：'public_hotspot'（公共热点）、'crisis_response'（危机响应）、'policy_dynamics'（政策动态）"
    )


@tool(args_schema=GetReportTemplateInput)
def get_report_template(mode: str) -> str:
    """读取指定模式的报告模板内容。

    返回模板全文，包含各章节的写作要求、结构指导和内容密度要求。
    writer 子代理应使用此工具获取模板，按模板要求组织章节。

    Args:
        mode: 报告模式，可选 'public_hotspot'、'crisis_response'、'policy_dynamics'

    Returns:
        模板全文（Markdown格式）
    """
    mode_clean = str(mode or "").strip().lower()
    template_file = {
        "public_hotspot": "public_hotspot.md",
        "crisis_response": "crisis_response.md",
        "policy_dynamics": "policy_dynamics.md",
    }.get(mode_clean)

    if not template_file:
        return json.dumps(
            {
                "error": f"未知的报告模式: {mode}",
                "available_modes": ["public_hotspot", "crisis_response", "policy_dynamics"],
                "hint": "请使用上述可用模式之一。",
            },
            ensure_ascii=False,
            indent=2,
        )

    template_path = TEMPLATE_DIR / template_file
    if not template_path.exists():
        return json.dumps(
            {
                "error": f"模板文件不存在: {template_path}",
                "hint": "请检查模板目录是否正确配置。",
            },
            ensure_ascii=False,
            indent=2,
        )

    template_content = template_path.read_text(encoding="utf-8")
    return json.dumps(
        {
            "mode": mode_clean,
            "template_file": template_file,
            "template_content": template_content,
            "usage_hint": "请按模板各章节要求进行写作，特别注意：1) 监测口径与样本说明要界定结论适用范围；2) 事件演变要围绕节点-转折-再定义展开；3) 每章节要有足够内容密度，不能只堆砌数据。",
        },
        ensure_ascii=False,
        indent=2,
    )