from __future__ import annotations

from typing import Annotated, List, Literal, Optional, Union

from pydantic import BaseModel, Field


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


class EvidenceBlock(BaseModel):
    evidence_id: str = Field(..., description="证据块唯一键")
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


class ChartCatalogItem(BaseModel):
    chart_id: str = Field(..., description="图表唯一键")
    function_name: str = Field(default="", description="所属分析函数")
    target: str = Field(default="", description="所属目标")
    title: str = Field(default="", description="图表标题")
    subtitle: str = Field(default="", description="图表说明")
    option: dict = Field(default_factory=dict, description="ECharts option")
    rows: List[dict] = Field(default_factory=list, description="预览行")
    all_rows: List[dict] = Field(default_factory=list, description="完整行")
    has_data: bool = Field(default=False, description="是否有图表数据")
    empty_message: str = Field(default="暂无可视化数据", description="空态文案")


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


class ChartSlotBlock(BaseModel):
    type: Literal["chart_slot"]
    block_id: str = Field(..., description="区块唯一键")
    title: str = Field(default="", description="区块标题")
    description: str = Field(default="", description="区块说明")
    chart_ids: List[str] = Field(default_factory=list, description="图表引用")
    chart_ids_missing: List[str] = Field(default_factory=list, description="缺失图表引用")


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
        ChartSlotBlock,
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
    chart_catalog_version: int = Field(default=1, description="图表目录版本")


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
    report_data: Optional[ReportDataBundle] = Field(default=None, description="事实层报告数据")
    report_document: ReportDocument = Field(default_factory=ReportDocument, description="可渲染文档层")
    chart_catalog: List[ChartCatalogItem] = Field(default_factory=list, description="图表目录")
    metadata: dict = Field(default_factory=dict)


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


class DocumentComposerOutput(BaseModel):
    """AI 文档编排代理的输出：章节与附录结构，AI 决定哪个章节放哪些图表、写什么解释。"""

    sections: List[ReportSection] = Field(
        default_factory=list,
        description="报告章节列表。每章含若干 block，block 的 chart_ids 必须来自传入的图表目录。",
    )
    appendix: Optional[ReportAppendix] = Field(
        default=None,
        description="可选附录，通常包含 citation_refs 和 callout。",
    )
