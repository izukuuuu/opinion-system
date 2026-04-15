from __future__ import annotations

import json
from pathlib import Path

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
    intent: str = Field(
        default="",
        description="检索意图描述，用于指导排序和筛选策略"
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
        description="来自 normalize_task 的标准化任务 JSON，包含主题标识和时间范围"
    )
    evidence_ids_json: str = Field(
        default="[]",
        description="证据卡 ID 列表的 JSON 字符串，用于支撑时间线节点"
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
        description="来自 normalize_task 的标准化任务 JSON"
    )
    metric_scope: str = Field(
        default="overview",
        description="指标范围: 'overview' 全览, 'sentiment' 情感, 'source' 来源分布"
    )
    evidence_ids_json: str = Field(
        default="[]",
        description="证据卡 ID 列表 JSON，用于限定指标计算范围"
    )


class ExtractActorPositionsInput(BaseModel):
    normalized_task_json: str = Field(
        ...,
        description="来自 normalize_task 的标准化任务 JSON"
    )
    evidence_ids_json: str = Field(
        default="[]",
        description="证据卡 ID 列表 JSON，用于抽取主体立场"
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
        description="来自 normalize_task 的标准化任务 JSON"
    )
    evidence_ids_json: str = Field(
        default="[]",
        description="证据卡 ID 列表 JSON"
    )
    actor_positions_json: str = Field(
        default="[]",
        description="来自 extract_actor_positions 的主体立场 JSON"
    )
    conflict_map_json: str = Field(
        default="{}",
        description="来自 build_claim_actor_conflict 的冲突图 JSON"
    )
    timeline_nodes_json: str = Field(
        default="[]",
        description="来自 build_event_timeline 的时间线节点 JSON"
    )


class BuildClaimActorConflictInput(BaseModel):
    normalized_task_json: str = Field(
        ...,
        description="来自 normalize_task 的标准化任务 JSON，包含主题标识和时间范围"
    )
    evidence_ids_json: str = Field(
        default="[]",
        description="证据卡 ID 列表的 JSON 字符串，用于支撑分析"
    )
    actor_positions_json: str = Field(
        default="[]",
        description="来自 extract_actor_positions 的主体立场 JSON"
    )
    timeline_nodes_json: str = Field(
        default="[]",
        description="来自 build_event_timeline 的时间线节点 JSON"
    )


class BuildMechanismSummaryInput(BaseModel):
    normalized_task_json: str = Field(
        ...,
        description="来自 normalize_task 的标准化任务 JSON"
    )
    evidence_ids_json: str = Field(
        default="[]",
        description="证据卡 ID 列表 JSON"
    )
    timeline_nodes_json: str = Field(
        default="[]",
        description="来自 build_event_timeline 的时间线节点 JSON"
    )
    conflict_map_json: str = Field(
        default="{}",
        description="来自 build_claim_actor_conflict 的冲突图 JSON"
    )
    metric_refs_json: str = Field(
        default="[]",
        description="来自 compute_report_metrics 的指标引用 JSON"
    )


class DetectRiskSignalsInput(BaseModel):
    normalized_task_json: str = Field(
        ...,
        description="来自 normalize_task 的标准化任务 JSON"
    )
    evidence_ids_json: str = Field(
        default="[]",
        description="证据卡 ID 列表 JSON"
    )
    metric_refs_json: str = Field(
        default="[]",
        description="来自 compute_report_metrics 的指标引用 JSON"
    )
    discourse_conflict_map_json: str = Field(
        default="",
        description="话语冲突图 JSON，用于识别争议焦点"
    )
    actor_positions_json: str = Field(
        default="[]",
        description="来自 extract_actor_positions 的主体立场 JSON"
    )


class JudgeDecisionUtilityInput(BaseModel):
    normalized_task_json: str = Field(
        ...,
        description="来自 normalize_task 的标准化任务 JSON"
    )
    risk_signals_json: str = Field(
        default="[]",
        description="来自 detect_risk_signals 的风险信号 JSON"
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
        description="来自 build_agenda_frame_map 的议题框架图 JSON"
    )
    conflict_map_json: str = Field(
        default="{}",
        description="来自 build_claim_actor_conflict 的冲突图 JSON"
    )
    mechanism_summary_json: str = Field(
        default="{}",
        description="来自 build_mechanism_summary 的机制摘要 JSON"
    )
    actor_positions_json: str = Field(
        default="[]",
        description="来自 extract_actor_positions 的主体立场 JSON"
    )


class VerifyClaimV2Input(BaseModel):
    normalized_task_json: str = Field(
        ...,
        description="来自 normalize_task 的标准化任务 JSON"
    )
    claims_json: str = Field(
        ...,
        description="待校验的断言列表 JSON，每个断言包含文本和来源"
    )
    evidence_ids_json: str = Field(
        default="[]",
        description="用于校验的证据卡 ID 列表 JSON"
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
        description="来自 normalize_task 的标准化任务 JSON"
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
        description="章节引用的证据卡 ID 列表 JSON"
    )
    metric_refs_json: str = Field(
        default="[]",
        description="章节引用的指标 JSON"
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
    intent: str = "",
    filters_json: str = "{}",
    sort_by: str = "relevance",
    limit: int = 12,
    cursor: str = "",
) -> str:
    """按意图返回分页证据卡。

    证据卡包含文档元数据、关键片段和情感标签。
    专题身份固定由 contract_id 解析，时间范围通过 retrieval_scope 做受控裁剪。
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