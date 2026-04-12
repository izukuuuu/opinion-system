# Method Contracts

本文件冻结四个方法对象与四个 specialist 的方法契约。目标是让下一轮 cleanup 只动实现，不再改动分析主线能力边界。

## Judgment Artifacts

### `AgendaFrameMap`

- 问题域：议题显著性、属性显著性、issue-attribute 关系、frame articulation、counter-frame、frame shift。
- 最小必填字段：
  - `issues`
  - `attributes`
  - `issue_attribute_edges`
  - `frames`
- 解释性字段：
  - `frame_carriers`
  - `frame_shifts`
  - `counter_frames`
- 允许为空：
  - `frame_shifts`
  - `counter_frames`
- 唯一上游来源：
  - router facets
  - normalized evidence units
  - typed frame articulation / synthesis
- 下游 consumer：
  - `RiskRegister`
  - `RecommendationCandidates`
  - `SectionPlan`
  - `UtilityAssessment`
- 禁止改写者：
  - compiler
  - presenter
  - frontend view model

### `ConflictMap`

- 问题域：主体围绕 target object 的命题、论证与冲突关系。
- 最小必填字段：
  - `claims`
  - `actor_positions`
  - `targets`
  - `edges`
  - `resolution_summary`
- 解释性字段：
  - `arguments`
  - `support_edges`
  - `attack_edges`
- 允许为空：
  - `support_edges`
  - `attack_edges`
- 唯一上游来源：
  - proposition extraction
  - target binding
  - argument extraction
  - support/attack relation recognition
  - resolution synthesis
- 下游 consumer：
  - `RiskRegister`
  - `RecommendationCandidates`
  - `SectionPlan`
  - `UtilityAssessment`
- 禁止改写者：
  - risk synthesis
  - recommendation compiler
  - markdown compiler

### `MechanismSummary`

- 问题域：传播为何放大、如何桥接、何时转折、由什么触发。
- 最小必填字段：
  - `amplification_paths`
  - `trigger_events`
  - `phase_shifts`
- 解释性字段：
  - `bridge_nodes`
  - `cross_platform_transfers`
  - `cause_candidates`
  - `narrative_carriers`
  - `refutation_lags`
- 允许为空：
  - `bridge_nodes`
  - `cross_platform_transfers`
  - `cause_candidates`
  - `narrative_carriers`
  - `refutation_lags`
- 唯一上游来源：
  - time slicing
  - bridge detection
  - trigger extraction
  - event-causality candidate generation
  - mechanism synthesis
- 下游 consumer：
  - `RiskRegister`
  - `RecommendationCandidates`
  - `SectionPlan`
  - `UtilityAssessment`
- 禁止改写者：
  - recommendation compiler
  - markdown compiler
  - frontend projection

### `UtilityAssessment`

- 问题域：当前 judgment objects 是否已经具备管理意义。
- 最小必填字段：
  - `decision`
  - `missing_dimensions`
  - `fallback_trace`
  - `utility_confidence`
- 解释性字段：
  - `next_action`
  - `improvement_trace`
  - `has_primary_contradiction`
  - `has_mechanism_explanation`
  - `has_issue_frame_context`
- 允许为空：
  - `next_action`
  - `improvement_trace`
- 唯一上游来源：
  - `AgendaFrameMap`
  - `ConflictMap`
  - `MechanismSummary`
  - `RiskRegister`
  - `RecommendationCandidates`
  - `UnresolvedPoints`
- 下游 consumer：
  - compiler gate
  - semantic review interrupt
  - approval lineage
- 禁止改写者：
  - compiler
  - presenter
  - frontend store

## Specialist Contracts

### `agenda_frame_builder`

- 输入 artifact：
  - normalized evidence units
  - timeline nodes
  - router facets
- 允许读取的 context：
  - retrieval router rules skill
  - task scope
  - platform/date/stage facets
- 输出 artifact：
  - `AgendaFrameMap`
- 明确禁止：
  - 输出 prose summary
  - 绕开 lineage
  - 生成新主对象
- 失败类型：
  - issue/attribute collapse
  - incomplete frame articulation
  - missing counter-frame or frame shift
- interrupt 条件：
  - 无
- 对应 skill：
  - `retrieval-router-rules`
- 对应 trace grading：
  - `frame_synthesis_fault`
  - `counter_frame_fault`
  - `frame_shift_fault`

### `claim_actor_conflict`

- 输入 artifact：
  - normalized evidence units
  - actor registry
  - agenda/frame context
- 允许读取的 context：
  - subject/stance rules
  - timeline slices
- 输出 artifact：
  - `ConflictMap`
- 明确禁止：
  - 输出 prose dispute summary
  - 绕开 lineage
  - 生成 recommendation prose
- 失败类型：
  - target binding fault
  - argument relation fault
  - actor mismatch
  - unresolved reason collapse
- interrupt 条件：
  - 无
- 对应 skill：
  - subject stance / retrieval routing related skills
- 对应 trace grading：
  - `claim_cluster_fault`
  - `target_binding_fault`
  - `argument_relation_fault`
  - `conflict_resolution_fault`

### `propagation_analyst`

- 输入 artifact：
  - normalized evidence units
  - timeline nodes
  - conflict map
  - agenda/frame context
- 允许读取的 context：
  - timeline slicing rules
  - propagation heuristics
- 输出 artifact：
  - `MechanismSummary`
- 明确禁止：
  - 输出 prose mechanism summary
  - 绕开 lineage
  - 生成新 judgment object
- 失败类型：
  - path identification fault
  - bridge node fault
  - phase shift fault
  - mechanism synthesis fault
- interrupt 条件：
  - 无
- 对应 skill：
  - timeline / router / methodology assets
- 对应 trace grading：
  - `path_identification_fault`
  - `bridge_node_fault`
  - `phase_shift_fault`
  - `mechanism_synthesis_fault`

### `decision_utility_judge`

- 输入 artifact：
  - `AgendaFrameMap`
  - `ConflictMap`
  - `MechanismSummary`
  - `RiskRegister`
  - `RecommendationCandidates`
  - `UnresolvedPoints`
- 允许读取的 context：
  - utility policy
  - approval threshold rules
- 输出 artifact：
  - `UtilityAssessment`
- 明确禁止：
  - 输出 prose advice
  - 直接写 final markdown
  - 绕过 semantic review interrupt
- 失败类型：
  - utility gate fault
  - fallback trace fault
  - review threshold fault
- interrupt 条件：
  - unresolved points 超阈值且建议强度过高
  - utility 维度缺失但仍请求正式文稿
- 对应 skill：
  - methodology / utility policy assets
- 对应 trace grading：
  - `utility_gate_fault`
  - `fallback_trace_fault`
  - `review_threshold_fault`

## Frozen Boundaries

- 不再新增第五个主 judgment artifact。
- 不再新增新的 specialist 类型，除非只是替换既有 specialist 的实现。
- compiler 只能消费 judgment artifacts，不得反写其语义。
- runtime/control surface 继续只允许 typed state、typed interrupt、typed lineage、typed approval。
- specialist 不得直接输出 prose。
