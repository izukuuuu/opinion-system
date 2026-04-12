from __future__ import annotations

from typing import Dict, List, Literal

from pydantic import BaseModel, Field


class AbilityEntry(BaseModel):
    ability_id: str = Field(..., description="能力唯一键")
    layer: Literal["runtime", "evidence", "semantic", "compiler", "view", "compat"]
    module: str = Field(..., description="所属模块")
    title: str = Field(..., description="能力名称")
    input_objects: List[str] = Field(default_factory=list, description="输入对象")
    output_objects: List[str] = Field(default_factory=list, description="输出对象")
    llm_tool_usage: str = Field(..., description="LLM / tool / subagent 使用情况")
    state_mutation: str = Field(..., description="是否修改 task/event/cache/artifact")
    failure_modes: List[str] = Field(default_factory=list, description="失败形态")
    quality_owner: str = Field(..., description="质量责任归属")


class AbilityLedger(BaseModel):
    version: str = Field(default="1.0")
    modules: List[str] = Field(default_factory=list)
    abilities: List[AbilityEntry] = Field(default_factory=list)


class RuntimeBoundaryAudit(BaseModel):
    version: str = Field(default="1.0")
    keep_inside_runtime: List[str] = Field(default_factory=list)
    must_snapshot: List[str] = Field(default_factory=list)
    current_boundary_risks: List[str] = Field(default_factory=list)
    rules: List[str] = Field(default_factory=list)


class FieldMappingEntry(BaseModel):
    source_field: str = Field(..., description="现有 structured field")
    target_field: str = Field(..., description="目标 ReportIR field")
    mapping_type: Literal["direct", "restructure", "projection", "drop"]
    rationale: str = Field(..., description="映射原因")


class ReportIRMapping(BaseModel):
    version: str = Field(default="1.0")
    direct: List[FieldMappingEntry] = Field(default_factory=list)
    restructure: List[FieldMappingEntry] = Field(default_factory=list)
    projection: List[FieldMappingEntry] = Field(default_factory=list)
    drop: List[FieldMappingEntry] = Field(default_factory=list)


class RefactorEntry(BaseModel):
    ability: str = Field(..., description="能力")
    current_module: str = Field(..., description="当前模块")
    target_layer: Literal["runtime", "evidence", "semantic", "compiler", "view", "compat"]
    target_shape: Literal["agent", "pass", "freeze"]
    reason: str = Field(..., description="划分原因")


class AgentPassRefactor(BaseModel):
    version: str = Field(default="1.0")
    keep_as_agent: List[RefactorEntry] = Field(default_factory=list)
    convert_to_pass: List[RefactorEntry] = Field(default_factory=list)
    freeze_as_compat: List[RefactorEntry] = Field(default_factory=list)


class SkillEvalSpec(BaseModel):
    skill_id: str = Field(..., description="技能评测唯一键")
    layer: Literal["evidence", "semantic", "compiler", "runtime", "view"]
    objective: str = Field(..., description="评测目标")
    source_of_truth: str = Field(..., description="真相源")
    assertion: str = Field(..., description="核心断言")
    failure_signal: str = Field(..., description="失败信号")


class SkillEvalPlan(BaseModel):
    version: str = Field(default="1.0")
    skill_evals: List[SkillEvalSpec] = Field(default_factory=list)
    system_regressions: List[SkillEvalSpec] = Field(default_factory=list)


class AuditBundle(BaseModel):
    ability_ledger: AbilityLedger
    runtime_boundary_audit: RuntimeBoundaryAudit
    report_ir_mapping: ReportIRMapping
    agent_pass_refactor: AgentPassRefactor
    skill_eval_plan: SkillEvalPlan
    docs: Dict[str, str] = Field(default_factory=dict)
