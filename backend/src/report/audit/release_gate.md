# Release Gate

本文件定义“下一轮只做 cleanup”之前必须满足的冻结条件。未满足以下 gate，不允许进入目录重组、命名统一、dead code 删除和 legacy 清理阶段。

## Gate 1: Object Completeness

以下四个方法对象必须全部冻结：

- `AgendaFrameMap`
- `ConflictMap`
- `MechanismSummary`
- `UtilityAssessment`

冻结标准：

- 具备最小字段集
- 已进入 `ReportIR`
- 已进入 `ArtifactManifest`
- 具备 consumer mapping
- 具备 `policy_version`
- 具备 lineage / approval compatibility

## Gate 2: Specialist Quality

以下 specialist 必须全部冻结：

- `agenda_frame_builder`
- `claim_actor_conflict`
- `propagation_analyst`
- `decision_utility_judge`

冻结标准：

- 输入 artifact 固定
- 输出 artifact 固定
- 不得直接输出 prose
- 失败类型固定
- interrupt 条件固定
- trace grading 维度固定

## Gate 3: Utility / Review

冻结标准：

- `UtilityAssessment` 是进入 final markdown 的唯一 gate
- fallback / review / approval 的路径可完整回放
- typed review 决策能在 lineage 中复原

## Runtime Freeze Rules

继续强制保持 typed surface：

- graph state
- interrupt payload
- approval queue item
- approval record
- artifact manifest
- report IR summary
- dispatch plan
- dispatch quality ledger

## Explicit Prohibitions

cleanup 开始前后都禁止：

- 新增 lexical fallback
- 新增 contains / regex / tag-based routing or guard
- 新增直接写 prose 的 specialist / critic
- 新增绕开 lineage 的 artifact 生产者
- 新增“service helper 里再塞一个兜底 prompt”
- 新增新的主 judgment artifact

## Allowed Next-Round Work

满足本文件所有 gate 后，下一轮只允许：

- 目录重组
- 命名统一
- import 收口
- dead code 删除
- legacy 清理

不允许：

- 改动四个方法对象的语义边界
- 改动 specialist 契约
- 改动运行时 typed surface 约束
- 改动 trace / eval 主维度
