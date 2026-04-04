from __future__ import annotations

from typing import List, Literal

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
