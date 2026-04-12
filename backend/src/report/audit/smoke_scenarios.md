# Runtime Smoke Scenarios

本文件冻结当前主链必须稳定通过的四条运行级 smoke 场景。

执行说明：

- smoke 不是补充性单测，而是 cleanup 前的最小运行 gate。
- 每条 smoke 都必须同时校验 `thread_id`、`artifact_manifest`、`approval_records/fallback_trace` 的可回放性。
- Windows 前端测试若在受限执行环境中出现 `spawn EPERM`，按环境噪声记录，不作为产品 contract 缺陷处理。

## Scenario 1: Happy Path E2E

输入条件：

- 创建真实 report task
- 正常生成 structured payload 和 final markdown

必出现的 artifact / interrupt：

- 生成 `dispatch plan`
- 四个 judgment artifacts 落盘
- `UtilityAssessment` 放行
- `artifact_manifest` 单调追加
- final markdown 可回投到同一 `thread_id`
- 对应 trace 能定位到 dispatch -> artifact build -> utility gate -> finalize

失败时先看：

- `artifact_manifest` 是否追加了 `structured_projection` 和 `full_markdown`
- 同一 `thread_id` 下是否还有连续的 `recent_events`
- 若主链入口被误改，先检查 contract guard 和 import topology

## Scenario 2: Semantic Review Path

输入条件：

- 构造会触发 semantic review 的正式文稿生成

必出现的 artifact / interrupt：

- 发出 `graph_interrupt`（`tool_name: "graph_interrupt"`，`approval_kind: "graph_interrupt"`）
- approval queue 写入，`approvals[].status = "pending"`
- `approval.required` 出现在同一 thread 的 event stream 中
- approval 后恢复执行
- `approval_records` 回写到同一 lineage
- 前端仍绑定原 `thread_id`，不会跳转到新的结果上下文

Resume 关键输入（缺一不可）：

- `interrupt_id`：来自 `approvals[].interrupt_id`（格式 `"graph-interrupt:{task_id}:{index}"`）
- `checkpoint_locator`：来自 `approvals[].action.tool_args.checkpoint_locator`，是恢复事实源
- `graph_thread_id`：来自 `approvals[].action.tool_args.graph_thread_id`，LangGraph compile 层 thread ID
- resume payload 封装为 `Command(resume={interrupt_id: {decisions: [{type: "approve"|"edit"|"reject"}]}})`
- 同一 `thread_id` 可累积多个 interrupt，各由独立 `interrupt_id` 标识，按 `decision_index` 区分

失败时先看：

- `approvals` 和 `approval_records` 是否仍落在同一 `thread_id`
- `checkpoint_backend/checkpoint_locator` 是否与运行时配置一致、`graph_thread_id` 是否与发出 interrupt 时一致
- `artifact_manifest` 是否缺失 review 后的新版本
- 若中断后无法恢复，先看 resume 路径和 queue state

## Scenario 3: Fallback Recompile Path

输入条件：

- 构造 utility 不足但无需人工审批的 case

必出现的 artifact / interrupt：

- 触发 `fallback_recompile`
- 新 draft/full artifact 追加到同一 lineage
- 前端继续读取最新 artifact，而不是旧结果
- fallback 原因能从 `UtilityAssessment.fallback_trace` 回放

失败时先看：

- `fallback_trace` 是否仍写入 `UtilityAssessment`
- `artifact_manifest` 是否单调追加而不是覆盖
- 若页面展示旧结果，先查前端是否仍只读最新 lineage

## Scenario 4: Resume After Failure Path

输入条件：

- 中途失败后重试/恢复同一任务链

必出现的 artifact / interrupt：

- 能从已有 artifact surface 或 typed resume payload 继续
- 不覆盖旧 lineage
- 不丢 approval queue item
- 最终结果仍关联回原 `thread_id`
- 恢复后 trace 中仍能定位到故障前后的同一任务链
- 若开启 LangSmith，root graph / deep coordinator / compile graph trace 都应能通过同一 thread 关联

失败时先看：

- `thread_id` 是否被错误重置
- `artifact_manifest` 是否追加而不是重写
- `approvals` / `approval_records` 是否在恢复后丢失
