from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field, model_validator


V2_SCHEMA_VERSION = "2.2"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class ReportTaskInfo(BaseModel):
    topic_identifier: str = Field(..., description="专题唯一标识")
    topic_label: str = Field(..., description="专题展示名称")
    start: str = Field(..., description="开始日期，YYYY-MM-DD")
    end: str = Field(..., description="结束日期，YYYY-MM-DD")
    mode: Literal["fast", "research"] = Field(default="fast", description="运行模式")
    thread_id: str = Field(..., description="本次任务的 thread_id")


class CitationRecord(BaseModel):
    citation_id: str = Field(..., description="引用索引唯一键")
    title: str = Field(default="", description="来源标题")
    url: str = Field(default="", description="来源链接")
    published_at: str = Field(default="", description="发布时间")
    platform: str = Field(default="", description="平台")
    snippet: str = Field(default="", description="摘要片段")
    source_type: str = Field(default="document", description="来源类型")
    author: str = Field(default="", description="发布者/作者")
    sentiment_label: str = Field(default="", description="情感标签(正面/负面/中性)")
    raw_content: str = Field(default="", description="完整原文(≤300字)")


class EvidenceBlock(BaseModel):
    evidence_id: str = Field(..., description="证据块唯一键")
    source_id: str = Field(default="", description="原始来源唯一键")
    finding: str = Field(..., description="证据支撑的判断")
    subject: str = Field(default="", description="涉及主体")
    stance: str = Field(default="", description="立场标签")
    time_label: str = Field(default="", description="时间标签")
    source_summary: str = Field(default="", description="来源概述")
    citation_ids: List[str] = Field(default_factory=list, description="对应引用索引")
    confidence: Literal["high", "medium", "low"] = Field(default="medium", description="证据强度")


class TimelineEvent(BaseModel):
    event_id: str = Field(..., description="时间线节点唯一键")
    date: str = Field(default="", description="日期")
    title: str = Field(..., description="事件标题")
    description: str = Field(default="", description="事件说明")
    trigger: str = Field(default="", description="触发因素")
    impact: str = Field(default="", description="影响")
    citation_ids: List[str] = Field(default_factory=list, description="关联证据引用")
    causal_links: List[str] = Field(default_factory=list, description="因果链关联节点 id")


class SubjectProfile(BaseModel):
    subject_id: str = Field(..., description="主体唯一键")
    name: str = Field(..., description="主体名称")
    category: str = Field(default="", description="主体类别")
    role: str = Field(default="", description="主体角色")
    summary: str = Field(default="", description="主体概述")
    citation_ids: List[str] = Field(default_factory=list, description="主体证据引用")


class StanceMatrixRow(BaseModel):
    subject: str = Field(..., description="主体")
    stance: str = Field(..., description="立场")
    summary: str = Field(default="", description="立场说明")
    conflict_with: List[str] = Field(default_factory=list, description="冲突主体")
    citation_ids: List[str] = Field(default_factory=list, description="支撑引用")


class ConflictPoint(BaseModel):
    conflict_id: str = Field(..., description="冲突点唯一键")
    title: str = Field(..., description="冲突标题")
    description: str = Field(default="", description="冲突说明")
    subjects: List[str] = Field(default_factory=list, description="涉及主体")
    citation_ids: List[str] = Field(default_factory=list, description="证据引用")


class PropagationFeature(BaseModel):
    feature_id: str = Field(..., description="传播特征唯一键")
    dimension: str = Field(..., description="传播维度")
    finding: str = Field(..., description="传播结论")
    explanation: str = Field(default="", description="传播解释")
    citation_ids: List[str] = Field(default_factory=list, description="支撑引用")


class RiskJudgement(BaseModel):
    risk_id: str = Field(..., description="风险点唯一键")
    label: str = Field(..., description="风险标签")
    level: Literal["high", "medium", "low"] = Field(default="medium", description="风险等级")
    summary: str = Field(default="", description="风险判断")
    citation_ids: List[str] = Field(default_factory=list, description="支撑引用")


class UnverifiedPoint(BaseModel):
    item_id: str = Field(..., description="待核验点唯一键")
    statement: str = Field(..., description="待核验陈述")
    reason: str = Field(default="", description="待核验原因")
    citation_ids: List[str] = Field(default_factory=list, description="已掌握引用")


class RecommendationItem(BaseModel):
    action_id: str = Field(..., description="建议动作唯一键")
    action: str = Field(..., description="建议动作")
    rationale: str = Field(default="", description="建议依据")
    priority: Literal["high", "medium", "low"] = Field(default="medium", description="优先级")
    citation_ids: List[str] = Field(default_factory=list, description="支撑引用")


class ReportConclusion(BaseModel):
    executive_summary: str = Field(..., description="结论摘要")
    key_findings: List[str] = Field(default_factory=list, description="核心发现")
    key_risks: List[str] = Field(default_factory=list, description="关键风险")
    confidence_label: str = Field(default="待评估", description="整体置信度标签")


class ValidationNote(BaseModel):
    note_id: str = Field(..., description="校验记录唯一键")
    category: Literal["fact", "timeline", "subject", "coverage"] = Field(..., description="问题类型")
    severity: Literal["high", "medium", "low"] = Field(default="medium", description="严重程度")
    message: str = Field(..., description="校验说明")
    related_ids: List[str] = Field(default_factory=list, description="关联对象")


class HeroMetric(BaseModel):
    metric_id: str = Field(..., description="指标唯一键")
    label: str = Field(..., description="指标名称")
    value: str = Field(default="", description="指标值")
    detail: str = Field(default="", description="指标补充说明")


class ReportHero(BaseModel):
    title: str = Field(default="", description="报告主标题")
    subtitle: str = Field(default="", description="报告副标题")
    summary: str = Field(default="", description="摘要")
    highlights: List[str] = Field(default_factory=list, description="摘要亮点")
    risks: List[str] = Field(default_factory=list, description="摘要风险")
    metrics: List[HeroMetric] = Field(default_factory=list, description="顶部指标卡")


FigureIntent = Literal["trend", "comparison", "composition", "distribution", "ranking", "network", "timeline", "geo", "none"]
FigureRenderStatus = Literal["ready", "review_required", "blocked", "degraded", "missing_data"]


class FigureIntentDecision(BaseModel):
    figure_id: str = Field(..., description="图表唯一键")
    section_role: str = Field(default="", description="挂载的标准章节角色")
    metric_id: str = Field(default="", description="主指标引用")
    function_name: str = Field(default="", description="来源分析函数")
    target: str = Field(default="", description="来源目标")
    intent: FigureIntent = Field(default="none", description="图表示意图")
    chart_type: str = Field(default="", description="目标图型")
    caption: str = Field(default="", description="图注")
    requires_review: bool = Field(default=False, description="是否需要人工审批")
    review_reasons: List[str] = Field(default_factory=list, description="审批原因")
    source_claim_ids: List[str] = Field(default_factory=list, description="来源断言")
    source_metric_ids: List[str] = Field(default_factory=list, description="来源指标")


class PlacementAnchor(BaseModel):
    figure_id: str = Field(..., description="图表唯一键")
    section_role: str = Field(default="", description="标准章节角色")
    block_id: str = Field(default="", description="语义文档中的锚点区块")
    placement_anchor: str = Field(default="", description="语义锚点")
    position: Literal["after", "before", "append"] = Field(default="after", description="插入位置")


class PlacementPlan(BaseModel):
    entries: List[PlacementAnchor] = Field(default_factory=list, description="图表插入规划")


class FigureDatasetArtifact(BaseModel):
    dataset_ref: str = Field(..., description="数据集引用键")
    dimensions: List[str] = Field(default_factory=list, description="字段维度")
    rows: List[dict] = Field(default_factory=list, description="完整数据行")
    preview_rows: List[dict] = Field(default_factory=list, description="预览行")
    digest: str = Field(default="", description="数据摘要指纹")


class ChartGrammarSpec(BaseModel):
    chart_type: str = Field(default="", description="图型")
    dataset_ref: str = Field(default="", description="数据集引用")
    option_ref: str = Field(default="", description="option 引用")
    encode: Dict[str, Any] = Field(default_factory=dict, description="编码约束")
    axes: Dict[str, Any] = Field(default_factory=dict, description="轴定义")
    series: List[Dict[str, Any]] = Field(default_factory=list, description="series 约束")
    components: Dict[str, Any] = Field(default_factory=dict, description="legend/tooltip/grid 等组件")
    degraded_from: str = Field(default="", description="降级来源图型")
    blocked_reason: str = Field(default="", description="阻断原因")


class FigureOptionArtifact(BaseModel):
    option_ref: str = Field(..., description="option 引用键")
    renderer: str = Field(default="echarts", description="渲染器")
    option: Dict[str, Any] = Field(default_factory=dict, description="受控 ECharts option")


class FigureApprovalRecord(BaseModel):
    figure_id: str = Field(..., description="图表唯一键")
    required: bool = Field(default=False, description="是否需要审批")
    status: Literal["not_required", "pending", "approved", "rejected"] = Field(default="not_required", description="审批状态")
    reason: str = Field(default="", description="审批原因")


class FigureArtifactRecord(BaseModel):
    figure_id: str = Field(..., description="图表唯一键")
    version: int = Field(default=1, description="图表版本")
    status: str = Field(default="ready", description="图表状态")
    dataset_ref: str = Field(default="", description="数据集引用")
    option_ref: str = Field(default="", description="option 引用")
    caption: str = Field(default="", description="图注")
    placement_anchor: str = Field(default="", description="图表锚点")
    source_claim_ids: List[str] = Field(default_factory=list, description="来源断言")
    source_metric_ids: List[str] = Field(default_factory=list, description="来源指标")
    policy_version: str = Field(default="figure-policy.v1", description="策略版本")
    render_status: FigureRenderStatus = Field(default="ready", description="渲染状态")
    chart_spec: ChartGrammarSpec = Field(
        default_factory=lambda: ChartGrammarSpec(chart_type="", dataset_ref="", option_ref=""),
        description="图表 grammar 规格",
    )
    dataset: FigureDatasetArtifact = Field(
        default_factory=lambda: FigureDatasetArtifact(dataset_ref="dataset:pending"),
        description="图表数据集 artifact",
    )
    option: FigureOptionArtifact = Field(
        default_factory=lambda: FigureOptionArtifact(option_ref="option:pending"),
        description="图表 option artifact",
    )
    approval_records: List[FigureApprovalRecord] = Field(default_factory=list, description="图表审批记录")


class FigureBlock(BaseModel):
    figure_id: str = Field(..., description="图表唯一键")
    intent: FigureIntent = Field(default="none", description="图表示意图")
    chart_type: str = Field(default="", description="图型")
    dataset_ref: str = Field(default="", description="数据集引用")
    option_ref: str = Field(default="", description="option 引用")
    caption: str = Field(default="", description="图注")
    placement_anchor: str = Field(default="", description="语义锚点")
    source_claim_ids: List[str] = Field(default_factory=list, description="来源断言")
    source_metric_ids: List[str] = Field(default_factory=list, description="来源指标")
    policy_version: str = Field(default="figure-policy.v1", description="策略版本")
    render_status: FigureRenderStatus = Field(default="ready", description="渲染状态")


class NarrativeBlock(BaseModel):
    type: Literal["narrative"]
    block_id: str = Field(..., description="区块唯一键")
    title: str = Field(default="", description="区块标题")
    content: str = Field(default="", description="正文内容")
    citation_ids: List[str] = Field(default_factory=list, description="引用回链")


class BulletsBlock(BaseModel):
    type: Literal["bullets"]
    block_id: str = Field(..., description="区块唯一键")
    title: str = Field(default="", description="区块标题")
    items: List[str] = Field(default_factory=list, description="要点列表")


class FigureRefBlock(BaseModel):
    type: Literal["figure_ref"]
    block_id: str = Field(..., description="区块唯一键")
    figure_id: str = Field(default="", description="图表引用")
    placement_anchor: str = Field(default="", description="语义锚点")
    render_hint: str = Field(default="", description="渲染提示")


class EvidenceListBlock(BaseModel):
    type: Literal["evidence_list"]
    block_id: str = Field(..., description="区块唯一键")
    title: str = Field(default="", description="区块标题")
    evidence_ids: List[str] = Field(default_factory=list, description="证据引用")


class TimelineListBlock(BaseModel):
    type: Literal["timeline_list"]
    block_id: str = Field(..., description="区块唯一键")
    title: str = Field(default="", description="区块标题")
    event_ids: List[str] = Field(default_factory=list, description="时间线引用")


class SubjectCardsBlock(BaseModel):
    type: Literal["subject_cards"]
    block_id: str = Field(..., description="区块唯一键")
    title: str = Field(default="", description="区块标题")
    subject_ids: List[str] = Field(default_factory=list, description="主体引用")


class StanceMatrixBlock(BaseModel):
    type: Literal["stance_matrix"]
    block_id: str = Field(..., description="区块唯一键")
    title: str = Field(default="", description="区块标题")
    subject_names: List[str] = Field(default_factory=list, description="立场矩阵主体")


class RiskListBlock(BaseModel):
    type: Literal["risk_list"]
    block_id: str = Field(..., description="区块唯一键")
    title: str = Field(default="", description="区块标题")
    risk_ids: List[str] = Field(default_factory=list, description="风险引用")


class ActionListBlock(BaseModel):
    type: Literal["action_list"]
    block_id: str = Field(..., description="区块唯一键")
    title: str = Field(default="", description="区块标题")
    action_ids: List[str] = Field(default_factory=list, description="动作引用")


class CitationRefsBlock(BaseModel):
    type: Literal["citation_refs"]
    block_id: str = Field(..., description="区块唯一键")
    title: str = Field(default="", description="区块标题")
    citation_ids: List[str] = Field(default_factory=list, description="引用索引")


class CalloutBlock(BaseModel):
    type: Literal["callout"]
    block_id: str = Field(..., description="区块唯一键")
    title: str = Field(default="", description="区块标题")
    tone: Literal["info", "warning", "danger"] = Field(default="info", description="提示语气")
    content: str = Field(default="", description="提示内容")


DocumentBlock = Annotated[
    Union[
        NarrativeBlock,
        BulletsBlock,
        FigureRefBlock,
        EvidenceListBlock,
        TimelineListBlock,
        SubjectCardsBlock,
        StanceMatrixBlock,
        RiskListBlock,
        ActionListBlock,
        CitationRefsBlock,
        CalloutBlock,
    ],
    Field(discriminator="type"),
]


class ReportSection(BaseModel):
    section_id: str = Field(..., description="章节唯一键")
    kicker: str = Field(default="", description="章节眉题")
    title: str = Field(default="", description="章节标题")
    summary: str = Field(default="", description="章节摘要")
    blocks: List[DocumentBlock] = Field(default_factory=list, description="章节区块")


class ReportAppendix(BaseModel):
    title: str = Field(default="", description="附录标题")
    blocks: List[DocumentBlock] = Field(default_factory=list, description="附录区块")


class ReportDocument(BaseModel):
    hero: ReportHero = Field(default_factory=ReportHero)
    sections: List[ReportSection] = Field(default_factory=list)
    appendix: ReportAppendix = Field(default_factory=ReportAppendix)


class ReportDataBundle(BaseModel):
    task: ReportTaskInfo
    conclusion: ReportConclusion
    timeline: List[TimelineEvent] = Field(default_factory=list)
    subjects: List[SubjectProfile] = Field(default_factory=list)
    stance_matrix: List[StanceMatrixRow] = Field(default_factory=list)
    key_evidence: List[EvidenceBlock] = Field(default_factory=list)
    conflict_points: List[ConflictPoint] = Field(default_factory=list)
    propagation_features: List[PropagationFeature] = Field(default_factory=list)
    risk_judgement: List[RiskJudgement] = Field(default_factory=list)
    unverified_points: List[UnverifiedPoint] = Field(default_factory=list)
    suggested_actions: List[RecommendationItem] = Field(default_factory=list)
    citations: List[CitationRecord] = Field(default_factory=list)
    validation_notes: List[ValidationNote] = Field(default_factory=list)
    agenda_frame_map: Optional["AgendaFrameMap"] = Field(default=None, description="议题-属性-框架图")
    conflict_map: Optional["ConflictMap"] = Field(default=None, description="断言-主体冲突图")
    mechanism_summary: Optional["MechanismSummary"] = Field(default=None, description="传播机制摘要")
    utility_assessment: Optional["UtilityAssessment"] = Field(default=None, description="决策可用性评估")
    basic_analysis_snapshot: Optional["BasicAnalysisSnapshot"] = Field(default=None, description="基础分析快照")
    basic_analysis_insight: Optional["BasicAnalysisInsight"] = Field(default=None, description="基础分析章节洞察")
    bertopic_snapshot: Optional["BertopicSnapshot"] = Field(default=None, description="BERTopic 快照")
    bertopic_insight: Optional["BertopicInsight"] = Field(default=None, description="BERTopic 章节洞察")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="文档层辅助元数据")


class StructuredReport(BaseModel):
    task: ReportTaskInfo
    conclusion: ReportConclusion
    timeline: List[TimelineEvent] = Field(default_factory=list)
    subjects: List[SubjectProfile] = Field(default_factory=list)
    stance_matrix: List[StanceMatrixRow] = Field(default_factory=list)
    key_evidence: List[EvidenceBlock] = Field(default_factory=list)
    conflict_points: List[ConflictPoint] = Field(default_factory=list)
    propagation_features: List[PropagationFeature] = Field(default_factory=list)
    risk_judgement: List[RiskJudgement] = Field(default_factory=list)
    unverified_points: List[UnverifiedPoint] = Field(default_factory=list)
    suggested_actions: List[RecommendationItem] = Field(default_factory=list)
    citations: List[CitationRecord] = Field(default_factory=list)
    validation_notes: List[ValidationNote] = Field(default_factory=list)
    agenda_frame_map: Optional["AgendaFrameMap"] = Field(default=None, description="议题-属性-框架图")
    conflict_map: Optional["ConflictMap"] = Field(default=None, description="断言-主体冲突图")
    mechanism_summary: Optional["MechanismSummary"] = Field(default=None, description="传播机制摘要")
    utility_assessment: Optional["UtilityAssessment"] = Field(default=None, description="决策可用性评估")
    report_data: Optional[ReportDataBundle] = Field(default=None, description="事实层报告数据")
    report_document: ReportDocument = Field(default_factory=ReportDocument, description="可渲染文档层")
    metadata: dict = Field(default_factory=dict)
    report_ir: Optional["ReportIR"] = Field(default=None, description="报告语义中枢对象")
    artifact_manifest: Optional["ArtifactManifest"] = Field(default=None, description="任务产物清单")
    basic_analysis_snapshot: Optional["BasicAnalysisSnapshot"] = Field(default=None, description="基础分析快照")
    basic_analysis_insight: Optional["BasicAnalysisInsight"] = Field(default=None, description="基础分析章节洞察")
    bertopic_snapshot: Optional["BertopicSnapshot"] = Field(default=None, description="BERTopic 快照")
    bertopic_insight: Optional["BertopicInsight"] = Field(default=None, description="BERTopic 章节洞察")
    metric_bundle: Optional["MetricBundle"] = Field(default=None, description="图表指标集合")
    figures: List["FigureBlock"] = Field(default_factory=list, description="图表语义真相")
    figure_artifacts: List["FigureArtifactRecord"] = Field(default_factory=list, description="图表 artifact 列表")
    placement_plan: "PlacementPlan" = Field(default_factory=lambda: PlacementPlan(entries=[]), description="图表位点规划")
    event_analysis: Dict[str, Any] = Field(
        default_factory=dict,
        description="事件分析结果（来自 event_analyst 子代理，含 platform_analysis/sentiment_summary/actor_distribution）",
    )


class StructuredReportSeed(StructuredReport):
    """Exploration/output boundary before deterministic compile and final persistence."""


class RetrievalPlan(BaseModel):
    overview: str = Field(..., description="检索策略概述")
    primary_paths: List[str] = Field(default_factory=list, description="优先检索路径")
    key_queries: List[str] = Field(default_factory=list, description="关键检索问题")
    evidence_focus: List[str] = Field(default_factory=list, description="重点证据方向")


class EvidenceBundle(BaseModel):
    summary: str = Field(..., description="证据整理摘要")
    evidence_blocks: List[EvidenceBlock] = Field(default_factory=list)
    citations: List[CitationRecord] = Field(default_factory=list)


class TimelineBundle(BaseModel):
    summary: str = Field(..., description="时间线摘要")
    events: List[TimelineEvent] = Field(default_factory=list)


class StanceBundle(BaseModel):
    summary: str = Field(..., description="立场摘要")
    subjects: List[SubjectProfile] = Field(default_factory=list)
    stance_matrix: List[StanceMatrixRow] = Field(default_factory=list)
    conflicts: List[ConflictPoint] = Field(default_factory=list)


class PropagationBundle(BaseModel):
    summary: str = Field(..., description="传播结构摘要")
    features: List[PropagationFeature] = Field(default_factory=list)
    risks: List[RiskJudgement] = Field(default_factory=list)


class DraftDocument(BaseModel):
    title: str = Field(..., description="文稿标题")
    subtitle: str = Field(default="", description="文稿副标题")
    markdown: str = Field(..., description="Markdown 正文")


class ValidationBundle(BaseModel):
    summary: str = Field(..., description="校验摘要")
    passed: bool = Field(default=True, description="是否通过")
    notes: List[ValidationNote] = Field(default_factory=list)


class ScopeTimeRange(BaseModel):
    start: str = Field(default="", description="开始日期，YYYY-MM-DD")
    end: str = Field(default="", description="结束日期，YYYY-MM-DD")


class ArtifactRecord(BaseModel):
    artifact_id: str = Field(..., description="产物唯一键")
    artifact_type: str = Field(..., description="产物类型")
    version: int = Field(default=1, description="产物版本")
    status: str = Field(default="pending", description="产物状态")
    path: str = Field(default="", description="产物路径")
    derived_from: List[str] = Field(default_factory=list, description="来源产物")
    thread_id: str = Field(default="", description="任务线程")
    task_id: str = Field(default="", description="任务 ID")
    policy_version: str = Field(default="policy.v1", description="生效策略版本")
    graph_run_id: str = Field(default="", description="图运行标识")
    parent_artifact_ids: List[str] = Field(default_factory=list, description="父产物引用")
    source_artifact_ids: List[str] = Field(default_factory=list, description="直接源产物引用")
    created_at: str = Field(default_factory=_utc_now, description="创建时间")


class ArtifactManifest(BaseModel):
    schema_version: str = Field(default="artifact-manifest.v1", description="清单 schema 版本")
    ir: ArtifactRecord = Field(default_factory=lambda: ArtifactRecord(artifact_id="ir", artifact_type="ir"))
    structured_projection: ArtifactRecord = Field(
        default_factory=lambda: ArtifactRecord(artifact_id="structured_projection", artifact_type="structured_projection")
    )
    basic_analysis_insight: ArtifactRecord = Field(
        default_factory=lambda: ArtifactRecord(artifact_id="basic_analysis_insight", artifact_type="basic_analysis_insight")
    )
    bertopic_insight: ArtifactRecord = Field(
        default_factory=lambda: ArtifactRecord(artifact_id="bertopic_insight", artifact_type="bertopic_insight")
    )
    agenda_frame_map: ArtifactRecord = Field(
        default_factory=lambda: ArtifactRecord(artifact_id="agenda_frame_map", artifact_type="agenda_frame_map")
    )
    conflict_map: ArtifactRecord = Field(
        default_factory=lambda: ArtifactRecord(artifact_id="conflict_map", artifact_type="conflict_map")
    )
    mechanism_summary: ArtifactRecord = Field(
        default_factory=lambda: ArtifactRecord(artifact_id="mechanism_summary", artifact_type="mechanism_summary")
    )
    utility_assessment: ArtifactRecord = Field(
        default_factory=lambda: ArtifactRecord(artifact_id="utility_assessment", artifact_type="utility_assessment")
    )
    draft_bundle: ArtifactRecord = Field(
        default_factory=lambda: ArtifactRecord(artifact_id="draft_bundle", artifact_type="draft_bundle")
    )
    draft_bundle_v2: ArtifactRecord = Field(
        default_factory=lambda: ArtifactRecord(artifact_id="draft_bundle_v2", artifact_type="draft_bundle_v2")
    )
    validation_result: ArtifactRecord = Field(
        default_factory=lambda: ArtifactRecord(artifact_id="validation_result", artifact_type="validation_result")
    )
    repair_plan: ArtifactRecord = Field(
        default_factory=lambda: ArtifactRecord(artifact_id="repair_plan", artifact_type="repair_plan")
    )
    graph_state: ArtifactRecord = Field(
        default_factory=lambda: ArtifactRecord(artifact_id="graph_state", artifact_type="graph_state")
    )
    full_markdown: ArtifactRecord = Field(
        default_factory=lambda: ArtifactRecord(artifact_id="full_markdown", artifact_type="full_markdown")
    )
    runtime_log: ArtifactRecord = Field(default_factory=lambda: ArtifactRecord(artifact_id="runtime_log", artifact_type="runtime_log"))
    approval_records: ArtifactRecord = Field(
        default_factory=lambda: ArtifactRecord(artifact_id="approval_records", artifact_type="approval_records")
    )
    figures: List[FigureArtifactRecord] = Field(default_factory=list, description="图表 artifact 清单")
    versions: List[ArtifactRecord] = Field(default_factory=list, description="版本列表")


class ReportIRMeta(BaseModel):
    ir_version: str = Field(default="1.0", description="IR 版本")
    topic_identifier: str = Field(default="", description="专题唯一标识")
    topic_label: str = Field(default="", description="专题展示名称")
    thread_id: str = Field(default="", description="任务线程")
    task_id: str = Field(default="", description="任务 ID")
    time_scope: ScopeTimeRange = Field(default_factory=ScopeTimeRange, description="时间范围")
    mode: str = Field(default="fast", description="运行模式")
    generated_at: str = Field(default_factory=_utc_now, description="生成时间")
    source_artifacts: List[str] = Field(default_factory=list, description="来源产物")


class ReportIRTopicScope(BaseModel):
    entities: List[str] = Field(default_factory=list, description="主体范围")
    platforms: List[str] = Field(default_factory=list, description="平台范围")
    keywords: List[str] = Field(default_factory=list, description="关键词")
    exclusions: List[str] = Field(default_factory=list, description="排除项")
    analysis_question_set: List[str] = Field(default_factory=list, description="分析问题集")


class ReportIREvent(BaseModel):
    event_id: str = Field(..., description="事件唯一键")
    time_label: str = Field(default="", description="时间标签")
    summary: str = Field(default="", description="事件摘要")
    support_evidence_ids: List[str] = Field(default_factory=list, description="支持证据")


class ReportIRTimeline(BaseModel):
    events: List[ReportIREvent] = Field(default_factory=list, description="时间线事件")


class ReportIRActor(BaseModel):
    actor_id: str = Field(..., description="主体唯一键")
    canonical_name: str = Field(default="", description="标准主体名")
    aliases: List[str] = Field(default_factory=list, description="别名")
    category: str = Field(default="", description="主体类型")


class ReportIRActorRegistry(BaseModel):
    actors: List[ReportIRActor] = Field(default_factory=list, description="主体注册表")


class ReportIRStanceRow(BaseModel):
    actor_id: str = Field(..., description="主体 ID")
    stance: str = Field(default="", description="主体立场")
    stance_shift: str = Field(default="", description="立场变化")
    conflict_actor_ids: List[str] = Field(default_factory=list, description="冲突主体")
    support_evidence_ids: List[str] = Field(default_factory=list, description="支持证据")


class ReportIRStanceMatrix(BaseModel):
    rows: List[ReportIRStanceRow] = Field(default_factory=list, description="立场矩阵")


class ReportIRClaim(BaseModel):
    claim_id: str = Field(..., description="断言唯一键")
    text: str = Field(default="", description="断言内容")
    category: str = Field(default="", description="断言类别")
    status: Literal["supported", "partially_supported", "unverified", "conflicting"] = Field(
        default="supported",
        description="断言状态",
    )
    write_policy: str = Field(default="factual", description="写作策略")
    support_evidence_ids: List[str] = Field(default_factory=list, description="支持证据")
    counter_evidence_ids: List[str] = Field(default_factory=list, description="反证")


class ReportIRClaimSet(BaseModel):
    claims: List[ReportIRClaim] = Field(default_factory=list, description="断言集合")


class ReportIREvidenceEntry(BaseModel):
    evidence_id: str = Field(..., description="证据唯一键")
    source_id: str = Field(default="", description="原始来源唯一键")
    title: str = Field(default="", description="标题")
    snippet: str = Field(default="", description="摘要")
    platform: str = Field(default="", description="平台")
    published_at: str = Field(default="", description="发布时间")
    url: str = Field(default="", description="来源链接")
    entities: List[str] = Field(default_factory=list, description="主体标签")
    confidence: str = Field(default="medium", description="证据强度")
    # BettaFish 深度引证字段（向后兼容，均有默认值）
    author: str = Field(default="", description="发布者")
    sentiment_label: str = Field(default="", description="情感标签(正面/负面/中性)")
    raw_quote: str = Field(default="", description="可引用金句(≤150字)")
    emotion_signals: List[str] = Field(default_factory=list, description="情绪关键词")
    engagement_views: int = Field(default=0, description="阅读量(若可获取)")


class ReportIREvidenceLedger(BaseModel):
    entries: List[ReportIREvidenceEntry] = Field(default_factory=list, description="证据账本")


class ReportIRRisk(BaseModel):
    risk_id: str = Field(..., description="风险唯一键")
    risk_type: str = Field(default="", description="风险类型")
    severity: str = Field(default="medium", description="风险等级")
    trigger_claim_ids: List[str] = Field(default_factory=list, description="触发断言")
    trigger_evidence_ids: List[str] = Field(default_factory=list, description="触发证据")
    spread_condition: str = Field(default="", description="扩散条件")


class ReportIRRiskRegister(BaseModel):
    risks: List[ReportIRRisk] = Field(default_factory=list, description="风险登记表")


class ReportIRUnresolvedPoint(BaseModel):
    item_id: str = Field(..., description="未解决点唯一键")
    statement: str = Field(default="", description="未解决陈述")
    reason: str = Field(default="", description="未解决原因")
    related_claim_ids: List[str] = Field(default_factory=list, description="关联断言")
    related_evidence_ids: List[str] = Field(default_factory=list, description="关联证据")


class ReportIRUnresolvedPoints(BaseModel):
    items: List[ReportIRUnresolvedPoint] = Field(default_factory=list, description="未解决问题")


class ReportIRRecommendationCandidate(BaseModel):
    candidate_id: str = Field(..., description="建议唯一键")
    action: str = Field(default="", description="建议动作")
    rationale: str = Field(default="", description="建议依据")
    preconditions: List[str] = Field(default_factory=list, description="前提条件")
    priority: str = Field(default="medium", description="优先级")
    support_claim_ids: List[str] = Field(default_factory=list, description="支持断言")


class ReportIRRecommendationCandidates(BaseModel):
    items: List[ReportIRRecommendationCandidate] = Field(default_factory=list, description="建议候选")


class IssueNode(BaseModel):
    issue_id: str = Field(..., description="议题唯一键")
    label: str = Field(default="", description="议题标签")
    salience: float = Field(default=0.0, description="议题显著性")
    time_scope: List[str] = Field(default_factory=list, description="时间窗")
    source_refs: List[str] = Field(default_factory=list, description="来源引用")


class AttributeNode(BaseModel):
    attribute_id: str = Field(..., description="属性唯一键")
    label: str = Field(default="", description="属性标签")
    attribute_type: str = Field(default="", description="属性类型")
    salience: float = Field(default=0.0, description="属性显著性")
    source_refs: List[str] = Field(default_factory=list, description="来源引用")


class IssueAttributeEdge(BaseModel):
    edge_id: str = Field(..., description="议题-属性边唯一键")
    issue_id: str = Field(default="", description="议题 ID")
    attribute_id: str = Field(default="", description="属性 ID")
    weight: float = Field(default=0.0, description="联结权重")
    time_scope: List[str] = Field(default_factory=list, description="时间窗")
    source_refs: List[str] = Field(default_factory=list, description="来源引用")


class FrameRecord(BaseModel):
    frame_id: str = Field(..., description="框架唯一键")
    problem: str = Field(default="", description="问题定义")
    cause: str = Field(default="", description="原因归因")
    judgment: str = Field(default="", description="评价判断")
    remedy: str = Field(default="", description="补救路径")
    confidence: float = Field(default=0.0, description="框架置信度")
    source_refs: List[str] = Field(default_factory=list, description="来源引用")


class FrameCarrierActor(BaseModel):
    actor_id: str = Field(..., description="主体 ID")
    frame_ids: List[str] = Field(default_factory=list, description="承载框架")
    role: str = Field(default="", description="承载角色")


class FrameShift(BaseModel):
    shift_id: str = Field(..., description="框架迁移唯一键")
    from_frame_id: str = Field(default="", description="原框架")
    to_frame_id: str = Field(default="", description="目标框架")
    time_anchor: str = Field(default="", description="时间锚点")
    trigger_refs: List[str] = Field(default_factory=list, description="触发引用")


class CounterFrame(BaseModel):
    frame_id: str = Field(..., description="反框架唯一键")
    counter_to_frame_id: str = Field(default="", description="对应主框架")
    support_refs: List[str] = Field(default_factory=list, description="支撑引用")


class AgendaFrameMap(BaseModel):
    issues: List[IssueNode] = Field(default_factory=list, description="议题节点")
    attributes: List[AttributeNode] = Field(default_factory=list, description="属性节点")
    issue_attribute_edges: List[IssueAttributeEdge] = Field(default_factory=list, description="议题-属性联结")
    frames: List[FrameRecord] = Field(default_factory=list, description="框架记录")
    frame_carriers: List[FrameCarrierActor] = Field(default_factory=list, description="框架承载主体")
    frame_shifts: List[FrameShift] = Field(default_factory=list, description="框架迁移")
    counter_frames: List[CounterFrame] = Field(default_factory=list, description="反框架")
    summary: str = Field(default="", description="议题-框架摘要")


class TargetObject(BaseModel):
    target_id: str = Field(..., description="目标对象唯一键")
    target_type: str = Field(default="", description="目标对象类型")
    label: str = Field(default="", description="目标对象标签")
    scope: str = Field(default="", description="作用范围")


class ConversationPosition(BaseModel):
    thread_scope: str = Field(default="", description="线程范围")
    reply_role: str = Field(default="", description="回复角色")
    turn_index: int = Field(default=0, description="轮次索引")


class ArgumentUnit(BaseModel):
    argument_id: str = Field(..., description="论证单元唯一键")
    claim_id: str = Field(default="", description="关联 claim")
    target_id: str = Field(default="", description="目标对象")
    argument_type: Literal["support", "attack", "context"] = Field(default="context")
    raw_span: str = Field(default="", description="原始论证片段")
    evidence_refs: List[str] = Field(default_factory=list, description="证据引用")
    evidence_type: Literal["statement", "report", "screenshot", "relay", "official_notice"] = Field(default="statement")
    conversation_position: ConversationPosition = Field(default_factory=ConversationPosition, description="对话位置")


class SupportEdge(BaseModel):
    edge_id: str = Field(..., description="支持边唯一键")
    argument_id: str = Field(default="", description="论证单元")
    target_claim_id: str = Field(default="", description="目标 claim")
    confidence: float = Field(default=0.0, description="支持置信度")


class AttackEdge(BaseModel):
    edge_id: str = Field(..., description="攻击边唯一键")
    argument_id: str = Field(default="", description="论证单元")
    target_claim_id: str = Field(default="", description="目标 claim")
    confidence: float = Field(default=0.0, description="攻击置信度")


class ClaimRecord(BaseModel):
    claim_id: str = Field(..., description="冲突图断言唯一键")
    proposition: str = Field(default="", description="命题骨架")
    proposition_slots: Dict[str, str] = Field(default_factory=dict, description="命题槽位结构")
    raw_spans: List[str] = Field(default_factory=list, description="原始表述片段")
    time_anchor: str = Field(default="", description="时间锚点")
    source_ids: List[str] = Field(default_factory=list, description="来源集合")
    verification_status: Literal["converged", "pending_verification", "sustained_conflict"] = Field(
        default="pending_verification",
        description="收敛状态",
    )
    evidence_coverage: str = Field(default="partial", description="证据覆盖度")
    source_diversity: int = Field(default=0, description="来源多样性")
    temporal_confidence: float = Field(default=0.0, description="时间锚点置信度")
    evidence_density: float = Field(default=0.0, description="证据密度")


class ConflictEdge(BaseModel):
    edge_id: str = Field(..., description="冲突边唯一键")
    claim_a_id: str = Field(default="", description="断言 A")
    claim_b_id: str = Field(default="", description="断言 B")
    conflict_type: Literal[
        "direct_contradiction",
        "evidence_conflict",
        "temporal_misalignment",
        "actor_mismatch",
        "attribution_conflict",
    ] = Field(default="evidence_conflict")
    actor_scope: List[str] = Field(default_factory=list, description="涉及主体")
    time_scope: List[str] = Field(default_factory=list, description="涉及时间窗")
    evidence_refs: List[str] = Field(default_factory=list, description="支撑证据")
    evidence_density: float = Field(default=0.0, description="冲突边证据密度")
    confidence: float = Field(default=0.0, description="冲突边判定置信度")


class ResolutionStatus(BaseModel):
    claim_id: str = Field(default="", description="对应断言")
    status: Literal["converged", "pending_verification", "sustained_conflict"] = Field(
        default="pending_verification"
    )
    reason: str = Field(default="", description="裁决原因")
    supporting_claim_ids: List[str] = Field(default_factory=list, description="支撑断言")
    unresolved_reason: str = Field(default="", description="未收敛原因")
    resolution_confidence: float = Field(default=0.0, description="收敛裁决置信度")


class ConflictMap(BaseModel):
    claims: List[ClaimRecord] = Field(default_factory=list, description="冲突图断言")
    actor_positions: List["ActorPosition"] = Field(default_factory=list, description="冲突图主体位置")
    targets: List[TargetObject] = Field(default_factory=list, description="目标对象")
    arguments: List[ArgumentUnit] = Field(default_factory=list, description="论证单元")
    support_edges: List[SupportEdge] = Field(default_factory=list, description="支持边")
    attack_edges: List[AttackEdge] = Field(default_factory=list, description="攻击边")
    edges: List[ConflictEdge] = Field(default_factory=list, description="冲突边")
    resolution_summary: List[ResolutionStatus] = Field(default_factory=list, description="收敛摘要")
    summary: str = Field(default="", description="冲突图摘要")
    evidence_density: float = Field(default=0.0, description="冲突图整体证据密度")
    source_diversity: int = Field(default=0, description="冲突图来源多样性")


class AmplificationPath(BaseModel):
    path_id: str = Field(..., description="扩散路径唯一键")
    source_actor_ids: List[str] = Field(default_factory=list, description="起始主体")
    bridge_actor_ids: List[str] = Field(default_factory=list, description="桥接主体")
    platform_sequence: List[str] = Field(default_factory=list, description="平台序列")
    linked_claim_ids: List[str] = Field(default_factory=list, description="关联断言")
    evidence_refs: List[str] = Field(default_factory=list, description="支撑证据")
    amplifier_type: str = Field(default="", description="放大器类型")
    confidence: float = Field(default=0.0, description="路径置信度")


class TriggerEvent(BaseModel):
    event_id: str = Field(..., description="触发事件唯一键")
    time_anchor: str = Field(default="", description="时间锚点")
    description: str = Field(default="", description="事件说明")
    linked_claim_ids: List[str] = Field(default_factory=list, description="关联断言")
    linked_actor_ids: List[str] = Field(default_factory=list, description="关联主体")
    evidence_refs: List[str] = Field(default_factory=list, description="支撑证据")
    confidence: float = Field(default=0.0, description="触发事件置信度")


class PhaseShift(BaseModel):
    phase_id: str = Field(..., description="阶段跃迁唯一键")
    from_phase: str = Field(default="", description="起始阶段")
    to_phase: str = Field(default="", description="目标阶段")
    reason: str = Field(default="", description="跃迁原因")
    linked_claim_ids: List[str] = Field(default_factory=list, description="关联断言")
    evidence_refs: List[str] = Field(default_factory=list, description="支撑证据")
    confidence: float = Field(default=0.0, description="阶段跃迁置信度")


class CrossPlatformBridge(BaseModel):
    bridge_id: str = Field(..., description="跨平台桥接唯一键")
    from_platform: str = Field(default="", description="源平台")
    to_platform: str = Field(default="", description="目标平台")
    bridge_actor_ids: List[str] = Field(default_factory=list, description="桥接主体")
    linked_claim_ids: List[str] = Field(default_factory=list, description="关联断言")
    evidence_refs: List[str] = Field(default_factory=list, description="支撑证据")
    confidence: float = Field(default=0.0, description="跨平台桥接置信度")


class BridgeNode(BaseModel):
    node_id: str = Field(..., description="桥接节点唯一键")
    actor_id: str = Field(default="", description="桥接主体")
    platform: str = Field(default="", description="桥接平台")
    bridge_role: str = Field(default="", description="桥接角色")
    linked_claim_ids: List[str] = Field(default_factory=list, description="关联断言")
    evidence_refs: List[str] = Field(default_factory=list, description="支撑证据")
    confidence: float = Field(default=0.0, description="桥接节点置信度")


class CauseCandidate(BaseModel):
    cause_event_id: str = Field(default="", description="原因事件")
    effect_event_id: str = Field(default="", description="结果事件")
    causality_type: str = Field(default="", description="因果类型")
    confidence: float = Field(default=0.0, description="因果置信度")
    evidence_refs: List[str] = Field(default_factory=list, description="支撑证据")


class CrossPlatformTransfer(BaseModel):
    transfer_id: str = Field(..., description="跨平台迁移唯一键")
    from_platform: str = Field(default="", description="源平台")
    to_platform: str = Field(default="", description="目标平台")
    bridge_node_ids: List[str] = Field(default_factory=list, description="桥接节点")
    evidence_refs: List[str] = Field(default_factory=list, description="支撑证据")


class NarrativeCarrier(BaseModel):
    carrier_id: str = Field(..., description="叙事载体唯一键")
    actor_id: str = Field(default="", description="主体")
    platform_id: str = Field(default="", description="平台")
    frame_ids: List[str] = Field(default_factory=list, description="承载框架")
    transport_role: str = Field(default="", description="承载角色")


class RefutationLag(BaseModel):
    refutation_id: str = Field(..., description="辟谣滞后唯一键")
    claim_id: str = Field(default="", description="关联 claim")
    refutation_event_id: str = Field(default="", description="辟谣事件")
    lag_window: str = Field(default="", description="滞后窗口")
    impact_summary: str = Field(default="", description="影响摘要")


class MechanismSummary(BaseModel):
    amplification_paths: List[AmplificationPath] = Field(default_factory=list, description="扩散路径")
    trigger_events: List[TriggerEvent] = Field(default_factory=list, description="触发事件")
    phase_shifts: List[PhaseShift] = Field(default_factory=list, description="阶段跃迁")
    cross_platform_bridges: List[CrossPlatformBridge] = Field(default_factory=list, description="跨平台桥接")
    bridge_nodes: List[BridgeNode] = Field(default_factory=list, description="桥接节点")
    cause_candidates: List[CauseCandidate] = Field(default_factory=list, description="因果候选")
    cross_platform_transfers: List[CrossPlatformTransfer] = Field(default_factory=list, description="跨平台迁移")
    narrative_carriers: List[NarrativeCarrier] = Field(default_factory=list, description="叙事载体")
    refutation_lags: List[RefutationLag] = Field(default_factory=list, description="辟谣滞后")
    confidence_summary: str = Field(default="", description="机制置信摘要")


class UtilityFailure(BaseModel):
    dimension: str = Field(default="", description="失败维度")
    reason: str = Field(default="", description="失败原因")
    suggested_pass: str = Field(default="", description="建议回退 pass")


class UtilityImprovementStep(BaseModel):
    step_id: str = Field(default="", description="改进步骤唯一键")
    triggered_by: str = Field(default="", description="触发维度")
    recompiled_pass: str = Field(default="", description="回退 pass")
    before_score: float = Field(default=0.0, description="前置评分")
    after_score: float = Field(default=0.0, description="后置评分")


class UtilityAssessment(BaseModel):
    assessment_id: str = Field(default="utility-1", description="评估唯一键")
    has_object_scope: bool = Field(default=False, description="是否明确对象")
    has_time_window: bool = Field(default=False, description="是否明确时间窗")
    has_key_actors: bool = Field(default=False, description="是否明确关键主体")
    has_primary_contradiction: bool = Field(default=False, description="是否明确主要矛盾")
    has_mechanism_explanation: bool = Field(default=False, description="是否具备机制解释")
    has_issue_frame_context: bool = Field(default=False, description="是否具备议题-框架上下文")
    has_conditional_risk: bool = Field(default=False, description="是否形成条件化风险")
    has_actionable_recommendations: bool = Field(default=False, description="是否形成可执行建议")
    has_uncertainty_boundary: bool = Field(default=False, description="是否保留不确定性边界")
    recommendation_has_object: bool = Field(default=False, description="建议是否明确对象")
    recommendation_has_time: bool = Field(default=False, description="建议是否明确时点")
    recommendation_has_action: bool = Field(default=False, description="建议是否明确动作")
    recommendation_has_preconditions: bool = Field(default=False, description="建议是否明确前提")
    recommendation_has_side_effects: bool = Field(default=False, description="建议是否明确边界或副作用")
    missing_dimensions: List[str] = Field(default_factory=list, description="缺失维度")
    fallback_trace: List[UtilityFailure] = Field(default_factory=list, description="回退轨迹")
    improvement_trace: List[UtilityImprovementStep] = Field(default_factory=list, description="改进轨迹")
    decision: Literal["pass", "fallback_recompile", "require_semantic_review"] = Field(default="fallback_recompile")
    next_action: str = Field(default="", description="下一动作")
    utility_confidence: float = Field(default=0.0, description="效用置信度")
    confidence: float = Field(default=0.0, description="决策可用性置信度")

    @model_validator(mode="before")
    @classmethod
    def _backfill_improvement_trace_step_ids(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        trace = data.get("improvement_trace")
        if not isinstance(trace, list):
            return data
        normalized_trace: List[Any] = []
        changed = False
        for index, item in enumerate(trace, start=1):
            if not isinstance(item, dict):
                normalized_trace.append(item)
                continue
            step_id = str(item.get("step_id") or "").strip()
            if step_id:
                normalized_trace.append(item)
                continue
            changed = True
            triggered_by = str(item.get("triggered_by") or "").strip()
            recompiled_pass = str(item.get("recompiled_pass") or "").strip()
            fallback_slug = "-".join(part for part in (triggered_by, recompiled_pass) if part) or "autofill"
            normalized_trace.append(
                {
                    **item,
                    "step_id": f"improve-{index}-{fallback_slug}",
                }
            )
        if not changed:
            return data
        return {**data, "improvement_trace": normalized_trace}


class ReportIRNarrativeViews(BaseModel):
    executive_summary: str = Field(default="", description="执行摘要")
    key_findings: List[str] = Field(default_factory=list, description="核心发现")
    view_models: Dict[str, Any] = Field(default_factory=dict, description="可复用叙事视图")


class ReportIRValidation(BaseModel):
    notes: List[ValidationNote] = Field(default_factory=list, description="校验记录")
    claim_coverage: Dict[str, int] = Field(default_factory=dict, description="断言覆盖统计")
    traceability_stats: Dict[str, int] = Field(default_factory=dict, description="可追溯统计")


# ---------------------------------------------------------------------------
# BettaFish 质量数据结构（深度引证用，均向后兼容）
# ---------------------------------------------------------------------------

class PlatformEmotionProfile(BaseModel):
    """各平台情绪雷达数据"""
    platform: str = Field(..., description="平台名称")
    dominant_emotion: str = Field(default="", description="主导情绪关键词")
    emotion_distribution: Dict[str, float] = Field(
        default_factory=dict,
        description="情绪分布 {'正面': 0.3, '负面': 0.5, '中性': 0.2}",
    )
    representative_quotes: List[str] = Field(
        default_factory=list,
        description="代表性评论/弹幕原文(每平台≤5条)",
    )
    discussion_style: str = Field(default="", description="讨论风格特征")
    evidence_ids: List[str] = Field(default_factory=list, description="支撑证据ID")


class EventFlashpoint(BaseModel):
    """事件全景速览爆点"""
    flashpoint_id: str = Field(..., description="爆点唯一键")
    time_label: str = Field(default="", description="时间标签")
    event_title: str = Field(default="", description="爆点事件标题")
    peak_readership: str = Field(
        default="",
        description="传播量级(字符串，如'120万'，不可用时为空)",
    )
    core_emotion_keywords: List[str] = Field(
        default_factory=list,
        description="核心情绪关键词",
    )
    support_evidence_ids: List[str] = Field(default_factory=list, description="支撑证据")


class GroupDemand(BaseModel):
    """多元群体诉求清单条目"""
    group_id: str = Field(..., description="群体唯一键")
    group_name: str = Field(default="", description="群体名称")
    high_freq_demands: List[str] = Field(default_factory=list, description="高频诉求列表")
    golden_quotes: List[str] = Field(
        default_factory=list,
        description="金句原文(来自 evidence 的原始引用)",
    )
    evidence_ids: List[str] = Field(default_factory=list, description="支撑证据")


class RiskTrafficLight(BaseModel):
    """高风险三色灯"""
    risk_id: str = Field(..., description="风险关联ID")
    light_color: Literal["red", "yellow", "green"] = Field(
        default="yellow", description="红/黄/绿灯"
    )
    flashpoint_prediction: str = Field(default="", description="爆点预测描述")
    trigger_threshold: str = Field(default="", description="触发阈值条件")
    preemptive_action: str = Field(default="", description="提前干预建议")
    support_evidence_ids: List[str] = Field(default_factory=list, description="支撑证据")


class ReportIR(BaseModel):
    meta: ReportIRMeta = Field(default_factory=ReportIRMeta)
    topic_scope: ReportIRTopicScope = Field(default_factory=ReportIRTopicScope)
    timeline: ReportIRTimeline = Field(default_factory=ReportIRTimeline)
    actor_registry: ReportIRActorRegistry = Field(default_factory=ReportIRActorRegistry)
    stance_matrix: ReportIRStanceMatrix = Field(default_factory=ReportIRStanceMatrix)
    claim_set: ReportIRClaimSet = Field(default_factory=ReportIRClaimSet)
    evidence_ledger: ReportIREvidenceLedger = Field(default_factory=ReportIREvidenceLedger)
    agenda_frame_map: AgendaFrameMap = Field(default_factory=AgendaFrameMap)
    conflict_map: ConflictMap = Field(default_factory=ConflictMap)
    mechanism_summary: MechanismSummary = Field(default_factory=MechanismSummary)
    risk_register: ReportIRRiskRegister = Field(default_factory=ReportIRRiskRegister)
    unresolved_points: ReportIRUnresolvedPoints = Field(default_factory=ReportIRUnresolvedPoints)
    recommendation_candidates: ReportIRRecommendationCandidates = Field(default_factory=ReportIRRecommendationCandidates)
    utility_assessment: UtilityAssessment = Field(default_factory=UtilityAssessment)
    narrative_views: ReportIRNarrativeViews = Field(default_factory=ReportIRNarrativeViews)
    figures: List[FigureBlock] = Field(default_factory=list, description="图表语义真相")
    placement_plan: PlacementPlan = Field(default_factory=PlacementPlan, description="图表位点规划")
    validation: ReportIRValidation = Field(default_factory=ReportIRValidation)
    # BettaFish 质量字段（向后兼容，均有默认值）
    platform_emotion_profiles: List[PlatformEmotionProfile] = Field(
        default_factory=list, description="各平台情绪雷达数据"
    )
    event_flashpoints: List[EventFlashpoint] = Field(
        default_factory=list, description="事件全景速览爆点列表"
    )
    group_demands: List[GroupDemand] = Field(
        default_factory=list, description="多元群体诉求清单"
    )
    risk_traffic_lights: List[RiskTrafficLight] = Field(
        default_factory=list, description="高风险三色灯"
    )
    emotion_conduction_formula: str = Field(
        default="", description="情绪传导公式(如'A → B → C → 标签化')"
    )
    netizen_quotes: List[str] = Field(
        default_factory=list, description="精选网民金句(跨章节可复用)"
    )


class CompilerSceneProfile(BaseModel):
    scene_id: str = Field(default="overview_brief")
    scene_label: str = Field(default="")
    focus: str = Field(default="timeline")
    guardrail_mode: str = Field(default="strict")
    render_mode: str = Field(default="claim_anchored")
    template_id: str = Field(default="", description="已选模板 ID")
    template_name: str = Field(default="", description="已选模板名称")
    template_path: str = Field(default="", description="已选模板路径")
    selection_score: float = Field(default=0.0, description="模板匹配分")
    matched_reasons: List[str] = Field(default_factory=list, description="模板命中原因")
    selection_context: Dict[str, Any] = Field(default_factory=dict, description="模板选择上下文")
    template_sections: List[Dict[str, str]] = Field(default_factory=list, description="模板章节列表")
    template_markdown: str = Field(default="", description="完整模板内容")


class CompilerStyleProfile(BaseModel):
    style_id: str = Field(default="evidence_first")
    document_tone: str = Field(default="neutral")
    heading_style: str = Field(default="analytic")
    tone_notes: List[str] = Field(default_factory=list)


class CompilerLayoutSection(BaseModel):
    section_id: str = Field(...)
    title: str = Field(default="")
    goal: str = Field(default="")
    target_words: int = Field(default=180)


class CompilerLayoutPlan(BaseModel):
    layout_summary: str = Field(default="")
    sections: List[CompilerLayoutSection] = Field(default_factory=list)


class CompilerSectionBudgetEntry(BaseModel):
    section_id: str = Field(...)
    target_words: int = Field(default=180)
    min_words: int = Field(default=120)
    max_words: int = Field(default=260)


class CompilerSectionBudget(BaseModel):
    total_words: int = Field(default=1200)
    sections: List[CompilerSectionBudgetEntry] = Field(default_factory=list)


class CompilerWriterContext(BaseModel):
    topic: str = Field(default="")
    range: ScopeTimeRange = Field(default_factory=ScopeTimeRange)
    scene_profile: CompilerSceneProfile = Field(default_factory=CompilerSceneProfile)
    style_profile: CompilerStyleProfile = Field(default_factory=CompilerStyleProfile)
    layout_plan: CompilerLayoutPlan = Field(default_factory=CompilerLayoutPlan)
    section_budget: CompilerSectionBudget = Field(default_factory=CompilerSectionBudget)
    counts: Dict[str, int] = Field(default_factory=dict)


class CompilerCriticResult(BaseModel):
    passed: bool = Field(default=True)
    issues: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CompilerSectionPlanItem(BaseModel):
    section_id: str = Field(...)
    title: str = Field(default="")
    goal: str = Field(default="")
    target_words: int = Field(default=180)
    source_groups: List[str] = Field(default_factory=list)
    template_id: str = Field(default="")
    template_title: str = Field(default="")
    template_summary: str = Field(default="")
    writing_instruction: str = Field(default="")
    selection_context: Dict[str, Any] = Field(default_factory=dict)


class SectionPlan(BaseModel):
    sections: List[CompilerSectionPlanItem] = Field(default_factory=list)


class DraftUnit(BaseModel):
    unit_id: str = Field(...)
    section_role: str = Field(default="")
    text: str = Field(default="")
    trace_ids: List[str] = Field(default_factory=list)
    claim_ids: List[str] = Field(default_factory=list)
    evidence_ids: List[str] = Field(default_factory=list)
    risk_ids: List[str] = Field(default_factory=list)
    unresolved_point_ids: List[str] = Field(default_factory=list)
    stance_row_ids: List[str] = Field(default_factory=list)
    confidence: str = Field(default="medium")
    is_unresolved: bool = Field(default=False)


class DraftBundle(BaseModel):
    source_artifact_id: str = Field(default="draft_bundle")
    policy_version: str = Field(default="policy.v1")
    units: List[DraftUnit] = Field(default_factory=list)
    section_order: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class TraceRef(BaseModel):
    trace_id: str = Field(...)
    trace_kind: Literal["evidence", "claim", "risk", "recommendation", "section_context"] = Field(default="evidence")
    support_level: Literal["structural", "direct", "aggregated", "derived"] = Field(default="direct")


class DraftUnitV2(BaseModel):
    unit_id: str = Field(...)
    section_id: str = Field(...)
    unit_type: Literal["heading", "transition", "observation", "finding", "mechanism", "risk", "recommendation", "unresolved"] = Field(default="finding")
    text: str = Field(default="")
    trace_refs: List[TraceRef] = Field(default_factory=list)
    derived_from: List[str] = Field(default_factory=list)
    support_level: Literal["structural", "direct", "aggregated", "derived"] = Field(default="direct")
    context_ref: str = Field(default="")
    render_template_id: str = Field(default="")
    validation_status: Literal["pending", "passed", "failed", "repaired"] = Field(default="pending")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DraftBundleV2(BaseModel):
    source_artifact_id: str = Field(default="draft_bundle.v2")
    policy_version: str = Field(default="policy.v2")
    schema_version: str = Field(default="draft-bundle.v2")
    units: List[DraftUnitV2] = Field(default_factory=list)
    section_order: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ValidationFailure(BaseModel):
    failure_id: str = Field(...)
    target_unit_id: str = Field(default="")
    failure_type: Literal["missing_trace", "dangling_derived_from", "unsupported_inference", "text_outside_ir", "schema_violation"] = Field(default="schema_violation")
    message: str = Field(default="")
    candidate_trace_refs: List[TraceRef] = Field(default_factory=list)
    candidate_derived_from: List[str] = Field(default_factory=list)
    patchable: bool = Field(default=False)
    patch_status: Literal["pending", "planned", "applied", "blocked"] = Field(default="pending")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RepairPatch(BaseModel):
    patch_id: str = Field(...)
    target_unit_id: str = Field(default="")
    failure_type: Literal["missing_trace", "dangling_derived_from", "unsupported_inference", "text_outside_ir", "schema_violation"] = Field(default="schema_violation")
    operation: Literal["attach_trace", "replace_unit", "downgrade_support", "mark_blocked"] = Field(default="attach_trace")
    replacement_unit: Optional[DraftUnitV2] = Field(default=None)
    candidate_trace_refs: List[TraceRef] = Field(default_factory=list)
    candidate_derived_from: List[str] = Field(default_factory=list)
    rationale: str = Field(default="")
    status: Literal["planned", "applied", "blocked"] = Field(default="planned")


class RepairPlanV2(BaseModel):
    schema_version: str = Field(default="repair-plan.v2")
    patches: List[RepairPatch] = Field(default_factory=list)
    blocked_failures: List[ValidationFailure] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ValidationResultV2(BaseModel):
    schema_version: str = Field(default="validation-result.v2")
    passed: bool = Field(default=True)
    failures: List[ValidationFailure] = Field(default_factory=list)
    patchable_failures: List[ValidationFailure] = Field(default_factory=list)
    gate: Literal["pass", "repair", "human_review", "blocked"] = Field(default="pass")
    repair_count: int = Field(default=0)
    next_node: str = Field(default="markdown_compiler")
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RewriteContract(BaseModel):
    schema_version: str = Field(default="rewrite-contract.v1")
    allowed_ops: List[str] = Field(default_factory=list)
    forbidden_ops: List[str] = Field(default_factory=list)
    offending_unit_ids: List[str] = Field(default_factory=list)
    traceable_unit_ids: List[str] = Field(default_factory=list)
    max_sentence_delta: int = Field(default=0)
    max_unit_delta: int = Field(default=0)
    must_preserve_sections: List[str] = Field(default_factory=list)
    must_preserve_trace_bindings: bool = Field(default=True)
    human_feedback: Dict[str, Any] = Field(default_factory=dict)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ReviewFeedbackContract(BaseModel):
    schema_version: str = Field(default="review-feedback.v1")
    comment: str = Field(default="")
    rewrite_focus: List[str] = Field(default_factory=list)
    must_keep: List[str] = Field(default_factory=list)
    must_remove: List[str] = Field(default_factory=list)
    tone_target: str = Field(default="")
    feedback_round: int = Field(default=0)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CommitArtifactRecord(BaseModel):
    artifact_type: str = Field(default="")
    path: str = Field(default="")
    idempotency_key: str = Field(default="")
    rewrite_round: int = Field(default=0)
    approval_round: int = Field(default=0)
    schema_version: str = Field(default="")
    payload: Dict[str, Any] = Field(default_factory=dict)


class ExplorationTaskResult(BaseModel):
    """_run_deep_report_exploration_task 的类型化返回值。"""

    status: str = Field(default="failed", description="任务状态: completed | interrupted | failed")
    message: str = Field(default="", description="任务结果说明")
    approvals: List[Dict[str, Any]] = Field(default_factory=list, description="待人工确认项")
    structured_payload: Dict[str, Any] = Field(default_factory=dict, description="结构化报告产物")
    full_payload: Dict[str, Any] = Field(default_factory=dict, description="完整报告产物")
    exploration_bundle: Dict[str, Any] = Field(default_factory=dict, description="探索阶段产物包")
    runtime_files: Dict[str, Any] = Field(default_factory=dict, description="运行时文件快照")
    thread_id: str = Field(default="", description="任务线程 ID")
    diagnostic: Dict[str, Any] = Field(default_factory=dict, description="诊断信息")


class DeepReportGraphState(BaseModel):
    schema_version: str = Field(default="deep-report-graph.v3")
    run_state_version: str = Field(default="run-state.v1", description="运行状态版本标识")
    payload: Dict[str, Any] = Field(default_factory=dict)
    report_ir: Dict[str, Any] = Field(default_factory=dict)
    policy_registry: Dict[str, Any] = Field(default_factory=dict)
    scene_profile: Dict[str, Any] = Field(default_factory=dict)
    style_profile: Dict[str, Any] = Field(default_factory=dict)
    layout_plan: Dict[str, Any] = Field(default_factory=dict)
    section_budget: Dict[str, Any] = Field(default_factory=dict)
    writer_context: Dict[str, Any] = Field(default_factory=dict)
    section_plan: Dict[str, Any] = Field(default_factory=dict)
    draft_bundle: Dict[str, Any] = Field(default_factory=dict)
    draft_bundle_v2: Dict[str, Any] = Field(default_factory=dict)
    validation_result_v2: Dict[str, Any] = Field(default_factory=dict)
    repair_plan_v2: Dict[str, Any] = Field(default_factory=dict)
    markdown: str = Field(default="")
    factual_conformance: Dict[str, Any] = Field(default_factory=dict)
    execution_phase: str = Field(default="prepare")
    rewrite_round: int = Field(default=0)
    rewrite_budget: int = Field(default=0)
    rewrite_issue_count: int = Field(default=0)
    approval_required: bool = Field(default=False)
    approval_status: str = Field(default="none")
    finalization_mode: str = Field(default="")
    commit_pending: bool = Field(default=False)
    commit_idempotency_key: str = Field(default="")
    review_required: bool = Field(default=False)
    blocked_reason: str = Field(default="")
    repair_count: int = Field(default=0)
    structured_report_current: Dict[str, Any] = Field(default_factory=dict)
    draft_bundle_current: Dict[str, Any] = Field(default_factory=dict)
    final_markdown_current: str = Field(default="")
    rewrite_contract: Dict[str, Any] = Field(default_factory=dict)
    review_feedback_contract: Dict[str, Any] = Field(default_factory=dict)
    source_checkpoint_id: str = Field(default="")
    parent_artifact_id: str = Field(default="")
    repaired_unit_ids: List[str] = Field(default_factory=list)
    dropped_unit_ids: List[str] = Field(default_factory=list)
    unchanged_unit_ids: List[str] = Field(default_factory=list)
    review_feedback_rounds: List[Dict[str, Any]] = Field(default_factory=list)
    validation_issues: List[Dict[str, Any]] = Field(default_factory=list)
    repair_history: List[Dict[str, Any]] = Field(default_factory=list)
    semantic_review_records: List[Dict[str, Any]] = Field(default_factory=list)
    progress_events: List[Dict[str, Any]] = Field(default_factory=list)
    rewrite_lineage: List[Dict[str, Any]] = Field(default_factory=list)
    commit_artifacts: List[Dict[str, Any]] = Field(default_factory=list)
    current_node: str = Field(default="")
    visited_nodes: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class RewriteDiff(BaseModel):
    before_unit_id: str = Field(default="")
    after_unit_id: str = Field(default="")
    ops: List[str] = Field(default_factory=list)
    semantic_fields_touched: List[str] = Field(default_factory=list)
    lock_bypass_attempted: bool = Field(default=False)


class SemanticLatticeState(BaseModel):
    assertion_certainty: str = Field(default="conditional")
    scope_quantifier: str = Field(default="partial")
    risk_maturity: str = Field(default="potential")
    action_force: str = Field(default="monitor")
    time_certainty: str = Field(default="uncertain")
    actor_scope: str = Field(default="specific_actor")
    evidence_coverage: str = Field(default="anchored")
    verification_status: str = Field(default="supported")


class SemanticDelta(BaseModel):
    dimension: str = Field(default="")
    before_level: str = Field(default="")
    after_level: str = Field(default="")
    direction: Literal["same", "up", "down", "unknown"] = Field(default="same")
    locked: bool = Field(default=True)


class FactualConformanceIssue(BaseModel):
    issue_id: str = Field(...)
    severity: Literal["high", "medium", "low"] = Field(default="high")
    issue_type: str = Field(default="")
    message: str = Field(default="")
    section_role: str = Field(default="")
    sentence: str = Field(default="")
    trace_ids: List[str] = Field(default_factory=list)
    semantic_dimension: str = Field(default="")
    before_level: str = Field(default="")
    after_level: str = Field(default="")
    suggested_action: str = Field(default="")


class FactualConformanceResult(BaseModel):
    passed: bool = Field(default=True)
    policy_version: str = Field(default="policy.v1")
    stage: str = Field(default="")
    can_auto_recover: bool = Field(default=True)
    requires_human_review: bool = Field(default=False)
    issues: List[FactualConformanceIssue] = Field(default_factory=list)
    semantic_deltas: List[SemanticDelta] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class StyledDraftBundle(BaseModel):
    units: List[DraftUnit] = Field(default_factory=list)
    section_order: List[str] = Field(default_factory=list)
    style_id: str = Field(default="")
    rewrite_policy: str = Field(default="presentation_only")
    policy_version: str = Field(default="policy.v1")
    rewrite_ops: List[str] = Field(default_factory=list)
    semantic_fields_locked: bool = Field(default=True)
    rewrite_diffs: List[RewriteDiff] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ConformancePolicyRegistry(BaseModel):
    policy_version: str = Field(default="policy.v1")
    claim_gate: Dict[str, str] = Field(default_factory=dict)
    risk_boundary: Dict[str, str] = Field(default_factory=dict)
    recommendation_boundary: Dict[str, str] = Field(default_factory=dict)
    strength_escalation: Dict[str, List[str]] = Field(default_factory=dict)
    time_certainty: Dict[str, List[str]] = Field(default_factory=dict)
    actor_scope: Dict[str, List[str]] = Field(default_factory=dict)
    evidence_coverage: Dict[str, List[str]] = Field(default_factory=dict)
    allowed_rewrite_ops: List[str] = Field(default_factory=list)
    disallowed_rewrite_ops: List[str] = Field(default_factory=list)
    approval_thresholds: Dict[str, str] = Field(default_factory=dict)


class ApprovalRecord(BaseModel):
    approval_id: str = Field(default="")
    interrupt_id: str = Field(default="")
    decision: str = Field(default="")
    reviewer: str = Field(default="")
    reason: str = Field(default="")
    policy_version: str = Field(default="policy.v1")
    artifact_refs: List[str] = Field(default_factory=list)
    offending_unit_ids: List[str] = Field(default_factory=list)
    approved_deltas: List[SemanticDelta] = Field(default_factory=list)
    approved_rewrite_ops: List[str] = Field(default_factory=list)
    approved_at: str = Field(default_factory=_utc_now)


class GraphApprovalRecord(BaseModel):
    approval_id: str = Field(default="")
    interrupt_id: str = Field(default="")
    decision_index: int = Field(default=0)
    tool_name: Literal["graph_interrupt"] = Field(default="graph_interrupt")
    approval_kind: Literal["graph_interrupt"] = Field(default="graph_interrupt")
    title: str = Field(default="")
    summary: str = Field(default="")
    status: Literal["pending", "resolved"] = Field(default="pending")
    allowed_decisions: List[str] = Field(default_factory=lambda: ["approve", "rewrite", "reject"])
    action: Dict[str, Any] = Field(default_factory=dict)
    requested_at: str = Field(default_factory=_utc_now)


class SemanticInterruptPayload(BaseModel):
    thread_id: str = Field(default="")
    task_id: str = Field(default="")
    policy_version: str = Field(default="policy.v1")
    artifact_ids: List[str] = Field(default_factory=list)
    offending_unit_ids: List[str] = Field(default_factory=list)
    semantic_deltas: List[SemanticDelta] = Field(default_factory=list)
    allowed_rewrite_ops: List[str] = Field(default_factory=list)
    violation_summary: List[Dict[str, Any]] = Field(default_factory=list)
    suggested_actions: List[str] = Field(default_factory=list)
    conformance: FactualConformanceResult = Field(default_factory=FactualConformanceResult)


class RouterFacet(BaseModel):
    facet_id: str = Field(default="")
    intent: str = Field(default="overview")
    platforms: List[str] = Field(default_factory=list)
    entities: List[str] = Field(default_factory=list)
    source_types: List[str] = Field(default_factory=list)
    time_start: str = Field(default="")
    time_end: str = Field(default="")
    event_stage: str = Field(default="")
    source_credibility: str = Field(default="balanced")
    risk_sensitivity: str = Field(default="moderate")
    task_goal: str = Field(default="")
    output_goal: str = Field(default="evidence")


class RouterDispatch(BaseModel):
    facet_id: str = Field(default="")
    specialist_target: str = Field(default="archive_evidence_organizer")
    aggregation_strategy: str = Field(default="merge_by_trace")
    lineage_tags: List[str] = Field(default_factory=list)
    expected_artifacts: List[str] = Field(default_factory=list)
    contribution_weight: float = Field(default=0.0)


class ExplorationArtifactStatus(BaseModel):
    path: str = Field(default="")
    owner: str = Field(default="")
    status: Literal["ready", "missing", "degraded"] = Field(default="ready")
    summary: str = Field(default="")


class ExplorationBundle(BaseModel):
    root_thread_id: str = Field(default="")
    exploration_thread_id: str = Field(default="")
    compile_thread_id: str = Field(default="")
    todos: List[Dict[str, Any]] = Field(default_factory=list)
    gap_summary: List[str] = Field(default_factory=list)
    exploration_manifest: Dict[str, ExplorationArtifactStatus] = Field(default_factory=dict)
    exploration_graph_state: Dict[str, Any] = Field(default_factory=dict)


class DispatchQualityEntry(BaseModel):
    facet_id: str = Field(default="")
    specialist_target: str = Field(default="")
    expected_artifacts: List[str] = Field(default_factory=list)
    actual_artifacts: List[str] = Field(default_factory=list)
    contributed_artifacts: List[str] = Field(default_factory=list)
    contribution_status: Literal["planned", "partial", "contributed", "no_signal"] = Field(default="planned")


class RouterDispatchPlan(BaseModel):
    router_version: str = Field(default="router.v1")
    policy_version: str = Field(default="policy.v1")
    facets: List[RouterFacet] = Field(default_factory=list)
    dispatches: List[RouterDispatch] = Field(default_factory=list)
    quality_ledger: List[DispatchQualityEntry] = Field(default_factory=list)


class AppliedScope(BaseModel):
    topic: str = Field(default="", description="专题或任务主题")
    time_range: ScopeTimeRange = Field(default_factory=ScopeTimeRange, description="应用到当前结果的时间范围")
    platforms: List[str] = Field(default_factory=list, description="平台范围")
    entities: List[str] = Field(default_factory=list, description="主体范围")
    report_type: str = Field(default="", description="报告类型")
    mode: str = Field(default="fast", description="检索或分析模式")


class CoverageSnapshot(BaseModel):
    matched_count: int = Field(default=0, description="命中记录数")
    sampled_count: int = Field(default=0, description="采样或返回记录数")
    raw_matched_count: int = Field(default=0, description="原始命中记录数（多轮 query 合并前）")
    deduped_candidate_count: int = Field(default=0, description="去重后的候选数")
    returned_card_count: int = Field(default=0, description="最终返回的证据卡数")
    platform_counts: Dict[str, int] = Field(default_factory=dict, description="平台分布")
    date_span: Dict[str, str] = Field(default_factory=dict, description="实际日期覆盖")
    source_resolution: str = Field(default="", description="原始语料命中来源类型")
    resolved_fetch_range: Dict[str, str] = Field(default_factory=dict, description="实际命中的 fetch 区间")
    resolved_source_files: List[str] = Field(default_factory=list, description="实际命中的源文件")
    requested_time_range: Dict[str, str] = Field(default_factory=dict, description="请求时间范围")
    effective_time_range: Dict[str, str] = Field(default_factory=dict, description="实际执行时间范围")
    contract_topic_identifier: str = Field(default="", description="运行时合同中的专题标识")
    effective_topic_identifier: str = Field(default="", description="当前工具执行使用的专题标识")
    contract_mismatch: bool = Field(default=False, description="是否出现任务边界改写")
    field_gaps: List[str] = Field(default_factory=list, description="字段缺口")
    missing_sources: List[str] = Field(default_factory=list, description="缺失来源")
    source_quality_flags: List[str] = Field(default_factory=list, description="来源质量提示")
    readiness_flags: List[str] = Field(default_factory=list, description="可用性标记")


class ResultTrace(BaseModel):
    source_ids: List[str] = Field(default_factory=list, description="来源索引")
    dedupe_keys: List[str] = Field(default_factory=list, description="去重键")
    truncated: bool = Field(default=False, description="是否已截断")
    next_cursor: str = Field(default="", description="下一页游标")
    retrieval_strategy: str = Field(default="", description="检索策略标签")
    rewrite_queries: List[str] = Field(default_factory=list, description="查询改写后的候选表达")
    compression_applied: bool = Field(default=False, description="是否应用了压缩/多样化裁剪")
    contract_id: str = Field(default="", description="执行时绑定的 contract 标识")
    derivation_id: str = Field(default="", description="执行时绑定的 derivation 标识")
    requested_scope: Dict[str, Any] = Field(default_factory=dict, description="请求的检索 scope")
    effective_scope: Dict[str, Any] = Field(default_factory=dict, description="系统生效的检索 scope")
    display_label: str = Field(default="", description="展示层标签")
    evidence_need: str = Field(default="", description="编排层需求键")
    compiled_tool_intents: List[str] = Field(default_factory=list, description="编译后的工具 intent 列表")
    requested_intent: str = Field(default="", description="原始工具 intent 输入")
    allowed_intents: List[str] = Field(default_factory=list, description="工具层允许的 intent 枚举")
    rerank_policy: str = Field(default="", description="最终采用的重排策略")
    dominant_signals: List[str] = Field(default_factory=list, description="主导当前结果的重排信号")


class CapabilityTrace(BaseModel):
    topic_identifier: str = Field(default="", description="专题唯一标识")
    time_range: ScopeTimeRange = Field(default_factory=ScopeTimeRange, description="时间范围")
    source_paths: List[str] = Field(default_factory=list, description="命中的归档路径")
    hit_files: List[str] = Field(default_factory=list, description="命中的文件")
    missing_files: List[str] = Field(default_factory=list, description="缺失文件")
    availability_flags: List[str] = Field(default_factory=list, description="能力可用性标记")


class BasicAnalysisSnapshot(BaseModel):
    snapshot_id: str = Field(default="")
    topic_identifier: str = Field(default="")
    topic_label: str = Field(default="")
    time_range: ScopeTimeRange = Field(default_factory=ScopeTimeRange)
    available: bool = Field(default=False)
    source_root: str = Field(default="")
    available_functions: List[str] = Field(default_factory=list)
    missing_functions: List[str] = Field(default_factory=list)
    overview: Dict[str, Any] = Field(default_factory=dict)
    functions: List[Dict[str, Any]] = Field(default_factory=list)
    trace: CapabilityTrace = Field(default_factory=CapabilityTrace)


class BasicAnalysisInsight(BaseModel):
    section_id: str = Field(default="basic-analysis-insight")
    section_title: str = Field(default="基础分析洞察")
    summary: str = Field(default="")
    key_findings: List[str] = Field(default_factory=list)
    chart_refs: List[str] = Field(default_factory=list)
    evidence_refs: List[str] = Field(default_factory=list)
    uncertainty_notes: List[str] = Field(default_factory=list)
    trace: CapabilityTrace = Field(default_factory=CapabilityTrace)


class BertopicSnapshot(BaseModel):
    snapshot_id: str = Field(default="")
    topic_identifier: str = Field(default="")
    topic_label: str = Field(default="")
    time_range: ScopeTimeRange = Field(default_factory=ScopeTimeRange)
    available: bool = Field(default=False)
    source_root: str = Field(default="")
    available_files: List[str] = Field(default_factory=list)
    raw_topics: List[Dict[str, Any]] = Field(default_factory=list)
    llm_clusters: List[Dict[str, Any]] = Field(default_factory=list)
    temporal_points: List[Dict[str, Any]] = Field(default_factory=list)
    trace: CapabilityTrace = Field(default_factory=CapabilityTrace)


class BertopicInsight(BaseModel):
    section_id: str = Field(default="bertopic-evolution")
    section_title: str = Field(default="BERTopic 主题演化")
    summary: str = Field(default="")
    key_findings: List[str] = Field(default_factory=list)
    chart_refs: List[str] = Field(default_factory=list)
    evidence_refs: List[str] = Field(default_factory=list)
    uncertainty_notes: List[str] = Field(default_factory=list)
    trace: CapabilityTrace = Field(default_factory=CapabilityTrace)


class TaskContract(BaseModel):
    contract_id: str = Field(..., description="运行时任务合同唯一键")
    topic_identifier: str = Field(default="", description="专题唯一标识")
    topic_label: str = Field(default="", description="专题展示名称")
    start: str = Field(default="", description="开始日期")
    end: str = Field(default="", description="结束日期")
    mode: str = Field(default="fast", description="运行模式")
    thread_id: str = Field(default="", description="线程唯一键")


# ========== Semantic Constraint Types for Task Derivation ==========

class SemanticEntity(BaseModel):
    """领域实体 - 必须是名词短语，非句子片段"""
    name: str = Field(
        ...,
        min_length=2,
        max_length=20,
        description="实体名称，必须是简短的名词短语（如政策、组织、事件）",
        examples=["控烟政策", "电子烟监管", "青少年控烟", "无烟环境"]
    )
    category: Literal["policy", "organization", "event", "concept", "location", "person", "other"] = Field(
        default="other",
        description="实体类别"
    )


class SemanticKeyword(BaseModel):
    """检索关键词 - 必须是单个词汇，不含标点和空格"""
    term: str = Field(
        ...,
        min_length=1,
        max_length=10,
        description="检索关键词，必须是单个词汇或短语，不含标点和空格",
        examples=["控烟", "禁烟", "二手烟", "戒烟"]
    )
    relevance: Literal["primary", "secondary", "contextual"] = Field(
        default="primary",
        description="关键词相关性级别"
    )


class TopicLabel(BaseModel):
    """专题标签 - 简短展示名称"""
    label: str = Field(
        ...,
        min_length=2,
        max_length=30,
        description="专题简短标签，用于展示和引用，不超过30字符",
        examples=["2025控烟舆情", "食品安全事件", "教育政策分析"]
    )
    full_description: str = Field(
        default="",
        max_length=200,
        description="完整描述，包含分析目标和维度说明"
    )


class TaskDerivation(BaseModel):
    derivation_id: str = Field(..., description="语义派生对象唯一键")
    topic: str = Field(
        default="",
        max_length=200,
        description="任务主题完整描述",
        examples=["2025控烟舆情分析：监测和分析2025年度控烟相关舆情动态"]
    )
    topic_identifier: str = Field(
        default="",
        min_length=4,
        max_length=40,
        description="专题唯一标识符，格式为时间戳+主题缩写",
        examples=["20260304-091855-2025控烟舆情"]
    )
    topic_label: TopicLabel = Field(
        default_factory=lambda: TopicLabel(label="待确定"),
        description="专题展示标签（结构化）"
    )
    topic_aliases: List[str] = Field(
        default_factory=list,
        max_length=5,
        description="语义别名列表，不超过5个",
        examples=[["控烟舆情", "烟草控制分析"]]
    )
    entities: List[SemanticEntity] = Field(
        default_factory=list,
        max_length=20,
        description="领域实体列表（结构化），每个实体必须是名词短语而非句子片段",
        json_schema_extra={
            "constraint_note": "禁止将句子片段作为实体，如'监测和分析2025年度控烟舆情'是错误示例",
            "expected_format": "简短名词短语，如'控烟政策'、'电子烟监管'"
        }
    )
    keywords: List[SemanticKeyword] = Field(
        default_factory=list,
        max_length=30,
        description="检索关键词列表（结构化），每个关键词必须是单个词汇",
        json_schema_extra={
            "constraint_note": "禁止句子片段作为关键词，必须是可用于检索的单一词汇",
            "expected_format": "如'控烟'、'禁烟'、'二手烟'"
        }
    )
    platform_scope: List[str] = Field(
        default_factory=list,
        description="平台范围",
        examples=[["微博", "自媒体号", "视频", "论坛"]]
    )
    report_type: Literal["propagation", "analysis", "risk", "comprehensive"] = Field(
        default="analysis",
        description="报告类型：propagation(传播分析)、analysis(综合分析)、risk(风险评估)、comprehensive(全维度)"
    )
    mandatory_sections: List[str] = Field(
        default_factory=list,
        description="必备章节列表",
        examples=[["overview", "timeline", "actors", "propagation", "risk"]]
    )
    risk_policy: List[str] = Field(
        default_factory=list,
        description="风险表述策略",
        examples=[["evidence_first", "prefer_counterevidence", "keep_uncertainty_visible"]]
    )
    analysis_question_set: List[str] = Field(
        default_factory=list,
        description="固定分析问题集",
        examples=[["传播演化", "主体立场", "争议焦点", "风险信号"]]
    )
    coverage_expectation: List[str] = Field(
        default_factory=list,
        description="理论上应覆盖的数据维度",
        examples=[["raw_posts", "media_reports", "platform_distribution"]]
    )
    inference_policy: List[str] = Field(
        default_factory=list,
        description="推断与证据约束",
        examples=[["risk_trend_can_be_weak_inference", "actor_shift_requires_multi_period_evidence"]]
    )
    attempted_overrides: Dict[str, str] = Field(default_factory=dict, description="agent 试图写入但无权生效的执行字段")
    contract_overrides_applied: List[str] = Field(default_factory=list, description="被运行时忽略或覆盖的执行字段")

    @model_validator(mode="after")
    def validate_semantic_quality(self) -> "TaskDerivation":
        """校验语义质量：确保 entities 和 keywords 不是句子片段"""
        # 检查 entities
        for entity in self.entities:
            name = entity.name
            # 禁止包含动词短语特征
            if any(marker in name for marker in ["监测", "分析", "包括", "维度", "动态", "解读"]):
                if len(name) > 15:  # 允许复合名词，但禁止句子片段
                    raise ValueError(
                        f"entity '{name}' 看起来像句子片段而非领域实体。"
                        f"实体应该是简短名词短语，如'控烟政策'、'电子烟监管'"
                    )
        # 检查 keywords
        for kw in self.keywords:
            term = kw.term
            if len(term) > 10:
                raise ValueError(
                    f"keyword '{term}' 过长。关键词应该是单一词汇，如'控烟'、'禁烟'"
                )
        return self


class NormalizedTask(BaseModel):
    """规范化任务 - 最终执行定义"""
    task_id: str = Field(..., description="任务唯一键")
    contract_id: str = Field(default="", description="合约唯一键")
    topic: str = Field(
        default="",
        max_length=200,
        description="任务主题完整描述",
        examples=["2025控烟舆情分析：监测和分析2025年度控烟相关舆情动态"]
    )
    topic_identifier: str = Field(
        default="",
        min_length=4,
        max_length=40,
        description="专题唯一标识符",
        examples=["20260304-091855-2025控烟舆情"]
    )
    topic_label: str = Field(
        default="",
        max_length=30,
        description="专题简短展示标签",
        examples=["2025控烟舆情"]
    )
    topic_aliases: List[str] = Field(
        default_factory=list,
        max_length=5,
        description="语义别名列表"
    )
    task_contract: Dict[str, str] = Field(default_factory=dict, description="运行时冻结的任务边界")
    entities: List[str] = Field(
        default_factory=list,
        max_length=20,
        description="领域实体列表（简短名词短语）",
        examples=["控烟政策", "电子烟监管", "青少年控烟"],
        json_schema_extra={
            "constraint_note": "必须是简短名词短语，禁止句子片段如'监测和分析2025年度控烟舆情'"
        }
    )
    keywords: List[str] = Field(
        default_factory=list,
        max_length=30,
        description="检索关键词列表（单一词汇）",
        examples=["控烟", "禁烟", "二手烟", "戒烟"],
        json_schema_extra={
            "constraint_note": "必须是单一词汇，禁止句子片段"
        }
    )
    time_range: ScopeTimeRange = Field(default_factory=ScopeTimeRange, description="时间范围")
    platform_scope: List[str] = Field(
        default_factory=list,
        description="平台范围",
        examples=[["微博", "自媒体号", "视频", "论坛"]]
    )
    report_type: Literal["propagation", "analysis", "risk", "comprehensive"] = Field(
        default="analysis",
        description="报告类型"
    )
    mandatory_sections: List[str] = Field(
        default_factory=list,
        description="必备章节列表",
        examples=[["overview", "timeline", "actors", "propagation", "risk"]]
    )
    risk_policy: List[str] = Field(
        default_factory=list,
        description="风险表述策略",
        examples=[["evidence_first", "prefer_counterevidence", "keep_uncertainty_visible"]]
    )
    mode: Literal["fast", "research"] = Field(default="fast", description="运行模式")
    analysis_question_set: List[str] = Field(
        default_factory=list,
        description="固定分析问题集",
        examples=[["传播演化", "主体立场", "争议焦点", "风险信号"]]
    )
    coverage_expectation: List[str] = Field(
        default_factory=list,
        description="理论上应覆盖的数据维度",
        examples=[["raw_posts", "media_reports", "platform_distribution"]]
    )
    inference_policy: List[str] = Field(
        default_factory=list,
        description="推断与证据约束",
        examples=[["risk_trend_can_be_weak_inference", "actor_shift_requires_multi_period_evidence"]]
    )
    contract_overrides_applied: List[str] = Field(default_factory=list, description="由运行时合同强制纠正的字段")
    schema_version: str = Field(default=V2_SCHEMA_VERSION, description="schema版本")
    generated_at: str = Field(default_factory=_utc_now, description="生成时间")


class EvidenceCard(BaseModel):
    evidence_id: str = Field(..., description="证据卡唯一键")
    source_id: str = Field(default="", description="来源唯一键")
    platform: str = Field(default="", description="平台")
    published_at: str = Field(default="", description="发布时间")
    author: str = Field(default="", description="发布者名称")
    author_type: str = Field(default="", description="作者类型")
    entity_tags: List[str] = Field(default_factory=list, description="主体标签")
    topic_cluster: str = Field(default="", description="主题簇")
    title: str = Field(default="", description="标题")
    snippet: str = Field(default="", description="片段摘要")
    content: str = Field(default="", description="原文完整内容（用于引证）")
    raw_contents: str = Field(default="", description="原始 contents 字段")
    raw_polarity: str = Field(default="", description="原始 polarity 字段")
    region: str = Field(default="", description="地域字段")
    matched_terms: List[str] = Field(default_factory=list, description="检索命中的关键词")
    sentiment_label: str = Field(default="", description="情感标签")
    keywords: List[str] = Field(default_factory=list, description="关键词列表")
    engagement: Dict[str, Any] = Field(default_factory=dict, description="互动指标")
    relevance: float = Field(default=0.0, description="相关度")
    confidence: float = Field(default=0.0, description="证据置信度")
    dedupe_key: str = Field(default="", description="去重键")
    url: str = Field(default="", description="来源链接")
    stance_hint: str = Field(default="", description="轻量立场提示")
    claimability: List[str] = Field(default_factory=list, description="更适合支撑的断言类型")
    novelty_score: float = Field(default=0.0, description="信息增量分数")
    contradiction_signal: float = Field(default=0.0, description="与主叙事冲突的概率提示")
    content_quality_hint: str = Field(default="", description="contents 字段质量提示")
    official_source_hint: str = Field(default="", description="是否像官方/媒体源的轻量提示")
    source_kind_hint: str = Field(default="", description="来源类型轻量提示")
    actor_salience_score: float = Field(default=0.0, description="主体显著性分数")
    eventness_score: float = Field(default=0.0, description="事件性分数")
    risk_salience_score: float = Field(default=0.0, description="风险显著性分数")
    risk_facets: List[str] = Field(default_factory=list, description="命中的风险侧面标签")


class TimelineNode(BaseModel):
    node_id: str = Field(..., description="时间线节点唯一键")
    time_label: str = Field(default="", description="时间标签")
    summary: str = Field(default="", description="节点摘要")
    support_evidence_ids: List[str] = Field(default_factory=list, description="支持证据")
    conflict_evidence_ids: List[str] = Field(default_factory=list, description="反证")
    confidence: float = Field(default=0.0, description="节点置信度")
    event_type: str = Field(default="event", description="事件类型")


class MetricRecord(BaseModel):
    metric_id: str = Field(..., description="指标唯一键")
    label: str = Field(default="", description="指标名称")
    value: float = Field(default=0.0, description="指标值")
    dimension: str = Field(default="", description="指标维度")
    detail: str = Field(default="", description="指标说明")
    metric_family: Literal["volume", "platform", "temporal", "overview"] = Field(default="overview", description="指标族")


class FigureMetricSource(BaseModel):
    metric_id: str = Field(..., description="指标唯一键")
    function_name: str = Field(default="", description="来源分析函数")
    target: str = Field(default="", description="来源目标")
    label: str = Field(default="", description="展示名称")
    metric_family: str = Field(default="", description="指标族")
    rows: List[Dict[str, Any]] = Field(default_factory=list, description="预览行")
    all_rows: List[Dict[str, Any]] = Field(default_factory=list, description="完整数据行")
    meta: Dict[str, Any] = Field(default_factory=dict, description="扩展元数据")


class MetricBundle(BaseModel):
    policy_version: str = Field(default="figure-policy.v1", description="指标策略版本")
    metrics: List[MetricRecord] = Field(default_factory=list, description="指标列表")
    sources: List[FigureMetricSource] = Field(default_factory=list, description="图表可消费的数据源")


class ActorPosition(BaseModel):
    actor_id: str = Field(..., description="主体唯一键")
    name: str = Field(default="", description="主体名称")
    aliases: List[str] = Field(default_factory=list, description="别名集合")
    role_type: str = Field(default="", description="主体角色类型")
    organization_type: str = Field(default="", description="组织类型")
    speaker_role: str = Field(default="", description="发声角色")
    relay_role: str = Field(default="", description="转述角色")
    account_tier: str = Field(default="", description="账号层级")
    is_official: bool = Field(default=False, description="是否官方主体")
    stance: str = Field(default="", description="主体立场")
    stance_shift: str = Field(default="", description="立场变化")
    claim_ids: List[str] = Field(default_factory=list, description="关联断言")
    representative_evidence_ids: List[str] = Field(default_factory=list, description="代表性证据")
    conflict_actor_ids: List[str] = Field(default_factory=list, description="冲突主体")
    confidence: float = Field(default=0.0, description="主体立场置信度")


class RiskSignal(BaseModel):
    risk_id: str = Field(..., description="风险唯一键")
    risk_type: str = Field(default="", description="风险类型")
    trigger_evidence_ids: List[str] = Field(default_factory=list, description="触发证据")
    spread_condition: str = Field(default="", description="扩散条件")
    severity: str = Field(default="medium", description="风险等级")
    confidence: float = Field(default=0.0, description="风险置信度")
    time_sensitivity: str = Field(default="", description="时间敏感性")


class ClaimVerificationRecord(BaseModel):
    claim_id: str = Field(..., description="断言唯一键")
    claim_text: str = Field(default="", description="断言原文")
    status: Literal["supported", "partially_supported", "unsupported", "contradicted"] = Field(
        default="unsupported",
        description="核验状态",
    )
    support_ids: List[str] = Field(default_factory=list, description="支持证据")
    contradict_ids: List[str] = Field(default_factory=list, description="反证")
    gap_note: str = Field(default="", description="证据缺口说明")
    confidence: float = Field(default=0.0, description="核验置信度")


class SectionPacket(BaseModel):
    section_id: str = Field(..., description="章节唯一键")
    section_goal: str = Field(default="", description="章节目标")
    claim_candidates: List[str] = Field(default_factory=list, description="候选断言")
    verified_claims: List[ClaimVerificationRecord] = Field(default_factory=list, description="已核验断言")
    key_metrics: List[MetricRecord] = Field(default_factory=list, description="关键指标")
    evidence_cards: List[EvidenceCard] = Field(default_factory=list, description="证据卡")
    counterevidence: List[EvidenceCard] = Field(default_factory=list, description="反证卡")
    uncertainty_notes: List[str] = Field(default_factory=list, description="不确定性说明")
    chart_data_refs: List[Dict[str, Any]] = Field(default_factory=list, description="图表引用")


class ConflictAxis(BaseModel):
    axis_id: str = Field(..., description="争议轴唯一键")
    title: str = Field(default="", description="争议轴标题")
    opposing_sides: List[str] = Field(default_factory=list, description="对立主体")
    focus_shift_path: List[str] = Field(default_factory=list, description="焦点迁移路径")
    intensity: float = Field(default=0.0, description="冲突强度")
    trigger_evidence_ids: List[str] = Field(default_factory=list, description="升级触发证据")


class DiscourseConflictMap(BaseModel):
    axes: List[ConflictAxis] = Field(default_factory=list, description="主争议轴")
    summary: str = Field(default="", description="冲突结构摘要")


class NormalizedTaskResult(BaseModel):
    schema_version: str = Field(default=V2_SCHEMA_VERSION)
    tool_name: str = Field(default="normalize_task")
    generated_at: str = Field(default_factory=_utc_now)
    task_contract: TaskContract = Field(default_factory=lambda: TaskContract(contract_id=""))
    task_derivation: TaskDerivation = Field(default_factory=lambda: TaskDerivation(derivation_id=""))
    proposal_snapshot: Dict[str, Any] = Field(default_factory=dict)
    normalized_task: NormalizedTask = Field(default_factory=lambda: NormalizedTask(task_id=""))
    result: NormalizedTask = Field(default_factory=lambda: NormalizedTask(task_id=""))
    applied_scope: AppliedScope = Field(default_factory=AppliedScope)
    coverage: CoverageSnapshot = Field(default_factory=CoverageSnapshot)
    counterevidence: List[Dict[str, Any]] = Field(default_factory=list)
    confidence: float = Field(default=0.0)
    trace: ResultTrace = Field(default_factory=ResultTrace)
    error_hint: Optional[str] = Field(default=None)


class CorpusCoverageResult(BaseModel):
    schema_version: str = Field(default=V2_SCHEMA_VERSION)
    tool_name: str = Field(default="get_corpus_coverage")
    generated_at: str = Field(default_factory=_utc_now)
    result: Dict[str, Any] = Field(default_factory=dict)
    applied_scope: AppliedScope = Field(default_factory=AppliedScope)
    coverage: CoverageSnapshot = Field(default_factory=CoverageSnapshot)
    counterevidence: List[Dict[str, Any]] = Field(default_factory=list)
    confidence: float = Field(default=0.0)
    trace: ResultTrace = Field(default_factory=ResultTrace)
    error_hint: Optional[str] = Field(default=None)


class EvidenceCardPage(BaseModel):
    schema_version: str = Field(default=V2_SCHEMA_VERSION)
    tool_name: str = Field(default="retrieve_evidence_cards")
    generated_at: str = Field(default_factory=_utc_now)
    result: List[EvidenceCard] = Field(default_factory=list)
    counterevidence: List[EvidenceCard] = Field(default_factory=list)
    applied_scope: AppliedScope = Field(default_factory=AppliedScope)
    coverage: CoverageSnapshot = Field(default_factory=CoverageSnapshot)
    confidence: float = Field(default=0.0)
    trace: ResultTrace = Field(default_factory=ResultTrace)
    error_hint: Optional[str] = Field(default=None)


class TimelineBuildResult(BaseModel):
    schema_version: str = Field(default=V2_SCHEMA_VERSION)
    tool_name: str = Field(default="build_event_timeline")
    generated_at: str = Field(default_factory=_utc_now)
    result: List[TimelineNode] = Field(default_factory=list)
    counterevidence: List[EvidenceCard] = Field(default_factory=list)
    applied_scope: AppliedScope = Field(default_factory=AppliedScope)
    coverage: CoverageSnapshot = Field(default_factory=CoverageSnapshot)
    confidence: float = Field(default=0.0)
    trace: ResultTrace = Field(default_factory=ResultTrace)
    error_hint: Optional[str] = Field(default=None)


class MetricBundleResult(BaseModel):
    schema_version: str = Field(default=V2_SCHEMA_VERSION)
    tool_name: str = Field(default="compute_report_metrics")
    generated_at: str = Field(default_factory=_utc_now)
    result: List[MetricRecord] = Field(default_factory=list)
    metric_scope: Literal["volume", "platform", "temporal", "overview"] = Field(default="overview")
    chart_data_refs: List[Dict[str, Any]] = Field(default_factory=list)
    counterevidence: List[EvidenceCard] = Field(default_factory=list)
    applied_scope: AppliedScope = Field(default_factory=AppliedScope)
    coverage: CoverageSnapshot = Field(default_factory=CoverageSnapshot)
    confidence: float = Field(default=0.0)
    trace: ResultTrace = Field(default_factory=ResultTrace)
    error_hint: Optional[str] = Field(default=None)


class ActorPositionResult(BaseModel):
    schema_version: str = Field(default=V2_SCHEMA_VERSION)
    tool_name: str = Field(default="extract_actor_positions")
    generated_at: str = Field(default_factory=_utc_now)
    actors: List[ActorPosition] = Field(default_factory=list)
    result: List[ActorPosition] = Field(default_factory=list)
    counterevidence: List[EvidenceCard] = Field(default_factory=list)
    applied_scope: AppliedScope = Field(default_factory=AppliedScope)
    coverage: CoverageSnapshot = Field(default_factory=CoverageSnapshot)
    confidence: float = Field(default=0.0)
    trace: ResultTrace = Field(default_factory=ResultTrace)
    error_hint: Optional[str] = Field(default=None)


class RiskSignalResult(BaseModel):
    schema_version: str = Field(default=V2_SCHEMA_VERSION)
    tool_name: str = Field(default="detect_risk_signals")
    generated_at: str = Field(default_factory=_utc_now)
    risks: List[RiskSignal] = Field(default_factory=list)
    discourse_conflict_map: DiscourseConflictMap = Field(default_factory=DiscourseConflictMap)
    result: List[RiskSignal] = Field(default_factory=list)
    counterevidence: List[EvidenceCard] = Field(default_factory=list)
    applied_scope: AppliedScope = Field(default_factory=AppliedScope)
    coverage: CoverageSnapshot = Field(default_factory=CoverageSnapshot)
    confidence: float = Field(default=0.0)
    trace: ResultTrace = Field(default_factory=ResultTrace)
    error_hint: Optional[str] = Field(default=None)


class ClaimVerificationPage(BaseModel):
    schema_version: str = Field(default=V2_SCHEMA_VERSION)
    tool_name: str = Field(default="verify_claim_v2")
    generated_at: str = Field(default_factory=_utc_now)
    claims: List[ClaimVerificationRecord] = Field(default_factory=list)
    result: List[ClaimVerificationRecord] = Field(default_factory=list)
    counterevidence: List[EvidenceCard] = Field(default_factory=list)
    applied_scope: AppliedScope = Field(default_factory=AppliedScope)
    coverage: CoverageSnapshot = Field(default_factory=CoverageSnapshot)
    confidence: float = Field(default=0.0)
    trace: ResultTrace = Field(default_factory=ResultTrace)
    error_hint: Optional[str] = Field(default=None)


class ClaimActorConflictResult(BaseModel):
    schema_version: str = Field(default=V2_SCHEMA_VERSION)
    tool_name: str = Field(default="build_claim_actor_conflict")
    generated_at: str = Field(default_factory=_utc_now)
    conflict_map: ConflictMap = Field(default_factory=ConflictMap)
    result: ConflictMap = Field(default_factory=ConflictMap)
    counterevidence: List[EvidenceCard] = Field(default_factory=list)
    applied_scope: AppliedScope = Field(default_factory=AppliedScope)
    coverage: CoverageSnapshot = Field(default_factory=CoverageSnapshot)
    confidence: float = Field(default=0.0)
    trace: ResultTrace = Field(default_factory=ResultTrace)
    error_hint: Optional[str] = Field(default=None)


class AgendaFrameMapResult(BaseModel):
    schema_version: str = Field(default=V2_SCHEMA_VERSION)
    tool_name: str = Field(default="build_agenda_frame_map")
    generated_at: str = Field(default_factory=_utc_now)
    agenda_frame_map: AgendaFrameMap = Field(default_factory=AgendaFrameMap)
    result: AgendaFrameMap = Field(default_factory=AgendaFrameMap)
    counterevidence: List[EvidenceCard] = Field(default_factory=list)
    applied_scope: AppliedScope = Field(default_factory=AppliedScope)
    coverage: CoverageSnapshot = Field(default_factory=CoverageSnapshot)
    confidence: float = Field(default=0.0)
    trace: ResultTrace = Field(default_factory=ResultTrace)
    error_hint: Optional[str] = Field(default=None)


class MechanismSummaryResult(BaseModel):
    schema_version: str = Field(default=V2_SCHEMA_VERSION)
    tool_name: str = Field(default="build_mechanism_summary")
    generated_at: str = Field(default_factory=_utc_now)
    mechanism_summary: MechanismSummary = Field(default_factory=MechanismSummary)
    result: MechanismSummary = Field(default_factory=MechanismSummary)
    counterevidence: List[EvidenceCard] = Field(default_factory=list)
    applied_scope: AppliedScope = Field(default_factory=AppliedScope)
    coverage: CoverageSnapshot = Field(default_factory=CoverageSnapshot)
    confidence: float = Field(default=0.0)
    trace: ResultTrace = Field(default_factory=ResultTrace)
    error_hint: Optional[str] = Field(default=None)


class UtilityAssessmentResult(BaseModel):
    schema_version: str = Field(default=V2_SCHEMA_VERSION)
    tool_name: str = Field(default="judge_decision_utility")
    generated_at: str = Field(default_factory=_utc_now)
    utility_assessment: UtilityAssessment = Field(default_factory=UtilityAssessment)
    result: UtilityAssessment = Field(default_factory=UtilityAssessment)
    counterevidence: List[EvidenceCard] = Field(default_factory=list)
    applied_scope: AppliedScope = Field(default_factory=AppliedScope)
    coverage: CoverageSnapshot = Field(default_factory=CoverageSnapshot)
    confidence: float = Field(default=0.0)
    trace: ResultTrace = Field(default_factory=ResultTrace)
    error_hint: Optional[str] = Field(default=None)


class SectionPacketResult(BaseModel):
    schema_version: str = Field(default=V2_SCHEMA_VERSION)
    tool_name: str = Field(default="build_section_packet")
    generated_at: str = Field(default_factory=_utc_now)
    section_packet: SectionPacket = Field(default_factory=lambda: SectionPacket(section_id=""))
    result: SectionPacket = Field(default_factory=lambda: SectionPacket(section_id=""))
    counterevidence: List[EvidenceCard] = Field(default_factory=list)
    applied_scope: AppliedScope = Field(default_factory=AppliedScope)
    coverage: CoverageSnapshot = Field(default_factory=CoverageSnapshot)
    confidence: float = Field(default=0.0)
    trace: ResultTrace = Field(default_factory=ResultTrace)
    error_hint: Optional[str] = Field(default=None)


class BasicAnalysisSnapshotResult(BaseModel):
    schema_version: str = Field(default=V2_SCHEMA_VERSION)
    tool_name: str = Field(default="get_basic_analysis_snapshot")
    generated_at: str = Field(default_factory=_utc_now)
    snapshot: BasicAnalysisSnapshot = Field(default_factory=BasicAnalysisSnapshot)
    result: BasicAnalysisSnapshot = Field(default_factory=BasicAnalysisSnapshot)
    trace: CapabilityTrace = Field(default_factory=CapabilityTrace)
    error_hint: Optional[str] = Field(default=None)


class BasicAnalysisInsightResult(BaseModel):
    schema_version: str = Field(default=V2_SCHEMA_VERSION)
    tool_name: str = Field(default="build_basic_analysis_insight")
    generated_at: str = Field(default_factory=_utc_now)
    insight: BasicAnalysisInsight = Field(default_factory=BasicAnalysisInsight)
    result: BasicAnalysisInsight = Field(default_factory=BasicAnalysisInsight)
    trace: CapabilityTrace = Field(default_factory=CapabilityTrace)
    error_hint: Optional[str] = Field(default=None)


class BertopicSnapshotResult(BaseModel):
    schema_version: str = Field(default=V2_SCHEMA_VERSION)
    tool_name: str = Field(default="get_bertopic_snapshot")
    generated_at: str = Field(default_factory=_utc_now)
    snapshot: BertopicSnapshot = Field(default_factory=BertopicSnapshot)
    result: BertopicSnapshot = Field(default_factory=BertopicSnapshot)
    trace: CapabilityTrace = Field(default_factory=CapabilityTrace)
    error_hint: Optional[str] = Field(default=None)


class BertopicInsightResult(BaseModel):
    schema_version: str = Field(default=V2_SCHEMA_VERSION)
    tool_name: str = Field(default="build_bertopic_insight")
    generated_at: str = Field(default_factory=_utc_now)
    insight: BertopicInsight = Field(default_factory=BertopicInsight)
    result: BertopicInsight = Field(default_factory=BertopicInsight)
    trace: CapabilityTrace = Field(default_factory=CapabilityTrace)
    error_hint: Optional[str] = Field(default=None)


class DocumentComposerOutput(BaseModel):
    """AI 文档编排代理的输出：章节与附录结构，仅负责文本与结构块编排。"""

    sections: List[ReportSection] = Field(
        default_factory=list,
        description="报告章节列表。图表位点由后续 typed workflow 注入，不在此处定义。",
    )
    appendix: Optional[ReportAppendix] = Field(
        default=None,
        description="可选附录，通常包含 citation_refs 和 callout。",
    )


ConflictMap.model_rebuild()
ReportDataBundle.model_rebuild()
StructuredReport.model_rebuild()
ReportIR.model_rebuild()
