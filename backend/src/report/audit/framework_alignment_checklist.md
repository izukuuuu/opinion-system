# Framework Capability Alignment Checklist

本文件对照 LangGraph / Deep Agents 官方能力定义，逐项评定当前 report 主链的对齐状态。
评定时间：2026-04-12。评定依据：代码实证（不依赖文档自述）。

状态标记：
- **已对齐** — 代码行为与官方能力语义一致，无明显漂移风险
- **部分对齐** — 核心路径已对齐，但存在遗留入口、缺失保障或潜在退化点
- **未对齐** — 官方能力在当前系统中尚未落地

---

## 一、审批恢复契约（Approval Resume Contract）

**评定：已对齐**

### 已对齐的部分

- `_build_resume_payload_from_task`（worker.py:864-903）完全以 `interrupt_id` 为主键构造 resume payload；
  无 `interrupt_id` 的 approval 项被静默跳过，不会产生格式退化的恢复调用。
- `service.py` 的 `generate_full_report_payload` 所有分支均硬编码 `tool_name: "graph_interrupt"` 和 `approval_kind: "graph_interrupt"`。
- worker 侧 `_resolved_graph_review()` 仅接受 `graph_interrupt`；
  旧 `semantic_review_markdown` 不再是合法审批名。
- 前端 ReportGenerationRun 只按 `graph_interrupt` 渲染与编辑审批，不再保留并列旧名入口。

---

## 二、副作用幂等边界（Durable Execution Side-Effect Boundary）

**评定：已对齐**

### 已对齐的部分

- `compile_blocked` 节点在调用 `interrupt()` 前**无任何 file/DB 写**：
  无 `open()` / `json.dump()` / `artifact_manifest` 更新 / `task_queue.patch()` 调用。
- `markdown_compiler`、`artifact_renderer` 等节点同样无预先副作用。
- `compile_blocked` 在 `is_resume_invocation` 下不再重复发 `compile.blocked / interrupt.human_review`。
- task queue 对 runtime event 还额外提供 `event_key` 去重，SSE 面不会因 replay 产生重复业务事件。

---

## 三、状态层与表示层混放（State / Presentation Coupling）

**评定：已对齐**

### 现状

- `StyledDraftBundle` 是结构化 Pydantic model（含 `units`、`rewrite_diffs`、`semantic_fields_locked` 等），
  **不是格式化展示文本**。
- 仅在终态节点 `artifact_renderer`（graph_runtime.py:981）写入 `state["final_output"]["styled_draft_bundle"]`，
  不在中间 pipeline 节点存入状态。
- 中间节点（section_realizer、unit_validator、repair）只在函数调用链内传递结构化对象，不向状态写展示字符串。

### 潜在注意点

若后续 `rewrite_ops` / `rewrite_diffs` 字段开始包含 HTML/CSS 样式片段，应重新评估是否存在展示层渗入。

---

## 四、Subgraph 持久化命名空间（Subgraph Persistence Namespace）

**评定：已对齐（风险暂不适用）**

### 现状

- 代码中名为 `existing_analysis_workers_subgraph` 的是一个普通 Python 函数节点（graph_runtime.py:716），
  **不是 compiled LangGraph subgraph**，不存在 checkpoint namespace 冲突问题。
- 主图的 `SqliteSaver` 是 per-invocation 上下文管理器（graph_runtime.py:1082），每次调用独立实例化。
- `compile_thread_id` 来自任务元数据，同一任务 resume 时复用相同 thread_id，不同任务使用不同值。

### 潜在注意点

一旦 `section_realizer_worker` 或 repair 节点被抽成真正的 compiled subgraph 并在同一 thread 下多次复用，
需要显式选择 per-invocation 持久化模式，否则会出现 checkpoint namespace 冲突。
**在实施 subgraph 重构前需重新评估此项。**

---

## 五、可观测性与前端事件流（Observability / Frontend Event Stream）

**评定：部分对齐**

### 已对齐的部分

- 后端通过 `event_callback` 注入机制，在所有主要 graph 节点边界发出事件：
  `graph.node.started/completed/failed`、`validation.failed`、`repair.loop.*`、
  `compile.blocked/started/completed`、`interrupt.human_review`。
- 所有事件写入 JSONL（task_events_path），通过 SSE 端点（api.py:645-709）流向前端。
- 前端 `useReportGeneration.js:146-177` 订阅了上述所有事件类型，通过 `taskState.mergeEvents()` 聚合。
- root orchestrator graph 与 compile graph 已切到 `graph.stream(...)` 路径执行；
  当前 SSE 面消费的是 graph-native 执行结果加 typed event adapter。
- `runtime_infra.py` 已提供 LangSmith 开关与 project 配置，trace metadata 会随 runnable config 注入。

### 尚未对齐的部分

- Deep Agents coordinator / subagent 面仍主要通过 typed callback adapter 出事件，
  不是完整的 LangGraph subgraph 原生 stream surface。
- 尚未把 `subgraphs=True` 引入到真正 compiled subgraph 场景，因此后续若继续拆图，需要再补子图透传策略。

### 修复建议

若后续引入真正 compiled subgraph，统一切到 `stream_mode + subgraphs=True`，
把子图事件也纳入同一 typed observability surface。

---

## 六、Deep Agents 上下文治理能力（Context Governance）

**评定：部分对齐**

### 现状

当前已落地的 Deep Agents 能力：

| 能力 | 状态 |
|------|------|
| `write_todos` 任务分解 | 已使用 |
| `task` 子代理委派 | 已使用 |
| Skills / context engineering | 已使用 |
| tool-level `interrupt_on` | 已使用 |
| backend / store 接线 | 已使用 |

当前尚未完全拉满的能力：

| 能力 | 状态 |
|------|------|
| 大结果自动 offloading | 未使用 |
| 长会话上下文摘要压缩 | 未使用 |
| 文件上下文后端策略统一化 | 部分使用 |
| 内置 HITL interrupt（高风险工具全量覆盖） | 部分使用 |

### 当前定位评估

当前系统定位准确描述为：
**LangGraph-native 确定性编排 + Deep Agents harness 负责总控 planning、skills、subagents 与 tool-level HITL。**

这与官方对"custom workflow"路径的定义一致，不需要强行对齐 Deep Agents harness。

### 若后续引入 Deep Agents 的合理切入点

1. `section_realizer_worker` — 高不确定性、输入大，适合子代理隔离 + 上下文卸载。
2. `trace_binder` — 证据检索链路长，适合 Deep Agents 的上下文摘要压缩。
3. 多 section 并发 drafting — 适合 SubAgentMiddleware + TodoList 任务分解。

---

## 优先修复顺序

| 优先级 | 项 | 操作 |
|--------|---|------|
| P1 | 可观测性 | 引入 compiled subgraph 时同步迁移到 `subgraphs=True` 的原生 streaming |
| P2 | Deep Agents 上下文治理 | 继续补 memory/filesystem/offloading 的生产级策略 |
| — | 状态/表示混放 | 无需立即操作，保持现状并持续观察 |
| — | Subgraph 命名空间 | 无需立即操作，重构 subgraph 前重新评估 |
