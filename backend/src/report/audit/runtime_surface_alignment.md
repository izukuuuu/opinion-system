# Runtime Surface Alignment

本文件记录当前前后端运行面约束。目标是让 API、worker、task queue 与前端运行台围绕同一套 typed runtime surface 工作。

## Canonical Runtime Surface

主链路统一消费以下字段：

- `task.id`
- `thread_id`
- `status`
- `phase`
- `percentage`
- `run_state`
- `orchestrator_state`
- `approvals`
- `artifact_manifest`
- `report_ir_summary`
- `structured_result_digest`
- `recent_events`

兼容字段可以保留，但只允许作为派生 surface，不允许继续承担事实源职责。

## Backend Alignment

- `task_queue` 负责持久化 canonical task snapshot 与 event log。
- `api.py` 只投影 canonical surface，不再发明额外 runtime truth。
- `worker.py` 只通过 `thread_id + artifact_manifest + approvals + run_state` 恢复与推进任务。
- analyze/explain bootstrap 主链实现位于 `runtime_bootstrap.py`；旧 `runtime.py` bridge 已退役，不允许以任何形式回流。

## Frontend Alignment

- `useReportGeneration.js` 的 `activeTask` 必须保留 canonical surface 的前端映射。
- 运行页、语义报告页、正式文稿页只依赖：
  - `threadId`
  - `artifactManifest`
  - `approvals`
  - `runState`
- operator 诊断面额外读取：
  - `runState.runtime_mode`
  - `runState.checkpoint_backend`
  - `runState.checkpoint_locator`
  - `runState.langsmith_enabled`
  - `runState.langsmith_project`
- topic/date 只能用于创建任务、读取历史记录，不能用于推断当前结果。

## Approval / Interrupt 字段结构

当前主链的审批机制已全部转为 `graph_interrupt`，不再使用旧的 `semantic_review_markdown` 路径。`approvals` 数组中每一项的关键字段：

```
approvals[].tool_name                            = "graph_interrupt"
approvals[].approval_kind                        = "graph_interrupt"
approvals[].interrupt_id                         = "graph-interrupt:{runtime_task_id}:{index}"
approvals[].status                               = "pending" | "resolved"
approvals[].decision                             = "approve" | "edit" | "reject"（resolved 后写入）
approvals[].action.tool_args.graph_thread_id     = LangGraph compile 层的 thread ID
approvals[].action.tool_args.checkpoint_backend  = "sqlite" | "postgres"
approvals[].action.tool_args.checkpoint_locator  = durable checkpoint 定位信息（恢复事实源）
approvals[].action.tool_args.checkpoint_path     = sqlite 开发态下的本地 checkpoint 文件路径
approvals[].action.graph_interrupt.interrupt_id  = 与外层 interrupt_id 对应
approvals[].action.graph_interrupt.value         = 原始 interrupt payload
```

Resume 时三个字段缺一不可：`interrupt_id + checkpoint_locator + graph_thread_id`。  
同一 `thread_id` 下可累积多个 interrupt，按 `decision_index` 区分；  
resume payload 封装为 `Command(resume={interrupt_id: {decisions: [...]}})` 并由统一 runtime checkpointer 恢复状态。

## Exit Conditions

- 创建任务后运行页立即绑定同一 `thread_id`
- graph_interrupt / approval resolve / resume 不丢 `thread_id`
- operator 面可稳定看到 `runtime_mode + checkpoint_backend + checkpoint_locator + latest_interrupt_id`
- 刷新与断线重连后仍能恢复同一 lineage 链上的最新 artifact
- final markdown 的可达性只由 `artifact_manifest.full_markdown.status` 决定
