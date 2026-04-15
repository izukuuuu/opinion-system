# LangGraph + DeepAgents 调试指南

本文档说明如何在本地高效调试深度报告系统，避免生产环境浪费 token。

## 调试工具概览

| 工具 | 用途 | 何时使用 |
|------|------|----------|
| **单元测试** | 测试单个节点逻辑 | 开发新节点、修改现有逻辑 |
| **静态检查** | 发现常见错误 | 提交代码前 |
| **调试脚本** | 快速测试图执行 | 验证图结构、状态传递 |
| **调试日志** | 记录执行轨迹 | 排查复杂问题、分析性能 |
| **LangGraph Studio** | 可视化调试 | 理解图流程、时间旅行调试 |

---

## 1. 静态检查（最快）

**在运行前发现问题，零成本。**

```bash
# 检查所有图文件
uv run --no-sync python backend/scripts/check_graph.py
```

**检查内容：**
- 状态 schema 定义是否正确
- 节点函数是否有返回值
- Reducer 是否处理 None
- 中断是否有异常处理
- Send 并发使用是否合理

**示例输出：**
```
检查文件: orchestrator_graph.py
------------------------------------------------------------
✅ 未发现问题

检查文件: graph_runtime.py
------------------------------------------------------------
⚠️  行 54: [WARNING] 状态 schema _GraphState 建议使用 total=False
ℹ️  行 234: [INFO] Send 通常在循环中使用以实现 fan-out
```

---

## 2. 单元测试（最可靠）

**测试单个节点逻辑，不依赖 LLM。**

```bash
# 运行所有深度报告测试
uv run --no-sync python -m pytest backend/tests/test_deep_report*.py -v

# 只测试图运行时
uv run --no-sync python -m pytest backend/tests/test_deep_report_graph_runtime.py -v

# 测试特定函数
uv run --no-sync python -m pytest backend/tests/test_deep_report_graph_runtime.py::DeepReportGraphRuntimeTests::test_build_repair_plan_v2_recovers_missing_derived_from -v
```

**编写测试的最佳实践：**

```python
# ✅ 好的测试：隔离节点逻辑
def test_repair_plan_recovers_derived_from():
    bundle = DraftBundleV2(units=[...])
    validation = ValidationResultV2(failures=[...])
    
    plan = build_repair_plan_v2(report_ir, bundle, validation)
    
    assert plan.patches[0].replacement_unit.derived_from == ["action-001"]

# ❌ 坏的测试：依赖真实 LLM
def test_full_pipeline():
    result = run_full_report(topic="测试")  # 会调用 LLM，浪费 token
    assert result["status"] == "completed"
```

---

## 3. 调试脚本（最直观）

**快速测试图执行，使用 mock 数据。**

```bash
# 启用调试模式
export DEEP_REPORT_DEBUG=1  # Linux/Mac
set DEEP_REPORT_DEBUG=1     # Windows CMD
$env:DEEP_REPORT_DEBUG="1"  # Windows PowerShell

# 运行调试脚本
uv run --no-sync python backend/scripts/debug_graph.py
```

**交互式菜单：**
```
选择调试目标:
1. 根编排图 (orchestrator)
2. 编译图 (compilation)
3. 分析已有日志

输入选项 (1/2/3): 2
```

**输出示例：**
```
✅ 编译图执行成功
状态: completed
修复次数: 1
事件数: 23

修复事件 (4):
  - repair_patch_planner: 修复规划已启动
  - repair_worker: 修复工作节点已启动
  - repair_finalize: 修复合并已启动
  - validator: 单元验证器已启动
```

**调试日志位置：**
```
backend/data/_debug/
├── compilation_debug-session_20260414_153022.jsonl
└── orchestrator_debug-session_20260414_152845.jsonl
```

---

## 4. 调试日志分析

**分析执行轨迹，找出性能瓶颈和错误。**

```bash
# 分析最新日志
uv run --no-sync python backend/scripts/debug_graph.py
# 选择选项 3

# 或直接分析
uv run --no-sync python -c "
from scripts.debug_graph import analyze_debug_logs
from pathlib import Path
analyze_debug_logs(Path('backend/data/_debug/compilation_xxx.jsonl'))
"
```

**分析输出：**
```
📊 分析日志: compilation_debug-session_20260414_153022.jsonl
总事件数: 156

节点执行统计:
  validator: 12 次
  repair_worker: 8 次
  section_realizer_worker: 6 次
  repair_finalize: 4 次

LLM 调用统计:
  调用次数: 23
  Prompt tokens: 45,230
  Completion tokens: 12,450
  总 tokens: 57,680

❌ 发现 2 个错误:
  repair_worker: 缺少 derived_from 字段
  validator: 验证失败次数超过阈值
```

---

## 5. LangGraph Studio（最强大）

**可视化调试，支持时间旅行和状态检查。**

### 安装

1. 下载 LangGraph Studio Desktop：https://studio.langchain.com/
2. 安装并启动

### 使用步骤

**步骤 1：启动 Studio**
```bash
cd F:\opinion-system\backend
# Studio 会自动检测 langgraph.json
```

**步骤 2：在 Studio 中打开项目**
- File → Open Project
- 选择 `F:\opinion-system\backend`
- Studio 会加载 `langgraph.json` 中定义的图

**步骤 3：选择要调试的图**
- 左侧面板选择 `orchestrator` 或 `compilation`
- 可视化显示图结构

**步骤 4：运行图**
- 点击 "New Thread" 创建新会话
- 输入测试数据（JSON 格式）：
  ```json
  {
    "request": {
      "task_id": "test-001",
      "topic_identifier": "demo",
      "topic_label": "测试专题",
      "start_text": "2025-01-01",
      "end_text": "2025-01-31",
      "mode": "fast"
    }
  }
  ```
- 点击 "Run" 执行

**步骤 5：调试功能**

| 功能 | 说明 |
|------|------|
| **节点高亮** | 当前执行的节点会高亮显示 |
| **状态检查** | 点击节点查看输入/输出状态 |
| **时间旅行** | 拖动时间轴回到任意执行点 |
| **断点** | 在节点上设置断点暂停执行 |
| **状态编辑** | 手动修改状态后继续执行 |
| **中断处理** | 可视化显示中断点，手动恢复 |

### Studio 调试场景

**场景 1：验证图结构**
- 问题：不确定边的连接是否正确
- 方法：在 Studio 中查看可视化图，检查节点连接

**场景 2：排查状态传递问题**
- 问题：某个节点收到的状态不对
- 方法：点击节点查看输入状态，对比上游节点输出

**场景 3：调试修复循环**
- 问题：修复循环没有正确终止
- 方法：
  1. 运行图直到进入修复循环
  2. 查看 `repair_count` 状态
  3. 检查条件边逻辑
  4. 手动修改 `repair_count` 测试终止条件

**场景 4：测试中断恢复**
- 问题：中断后恢复状态丢失
- 方法：
  1. 运行到中断点
  2. 查看 checkpointer 中保存的状态
  3. 手动恢复，检查状态完整性

---

## 6. 集成到开发流程

### 提交前检查清单

```bash
# 1. 静态检查
uv run --no-sync python backend/scripts/check_graph.py

# 2. 运行单元测试
uv run --no-sync python -m pytest backend/tests/test_deep_report*.py

# 3. 快速冒烟测试
export DEEP_REPORT_DEBUG=1
uv run --no-sync python backend/scripts/debug_graph.py
# 选择选项 1 和 2，确保都能成功执行
```

### 排查生产问题

**步骤 1：复现问题**
```python
# 从生产日志提取失败的 payload
payload = {...}  # 从数据库或日志获取

# 本地运行
from src.report.deep_report.service import run_deep_report_exploration_task
result = run_deep_report_exploration_task(payload)
```

**步骤 2：启用调试日志**
```bash
export DEEP_REPORT_DEBUG=1
# 重新运行，查看详细日志
```

**步骤 3：在 Studio 中单步调试**
- 将 payload 输入 Studio
- 单步执行，找到失败节点
- 检查该节点的输入状态

---

## 7. 性能优化建议

### 减少 LLM 调用

**问题：修复循环调用 LLM 次数过多**

```python
# ❌ 每次修复都调用 LLM
def repair_worker(state):
    llm_result = call_llm(state)  # 昂贵
    return {"patch": llm_result}

# ✅ 优先使用确定性修复
def repair_worker(state):
    failure = state["failure"]
    if failure["type"] == "missing_derived_from":
        # 确定性修复，不调用 LLM
        return {"patch": deterministic_fix(failure)}
    else:
        # 只在必要时调用 LLM
        return {"patch": call_llm(state)}
```

### 并行化节点

**问题：section 串行执行太慢**

```python
# ❌ 串行执行
graph.add_edge("planner", "section_worker_1")
graph.add_edge("section_worker_1", "section_worker_2")

# ✅ 并行执行（使用 Send）
def planner(state):
    slots = state["planner_slots"]
    return [Send("section_worker", {"slot": s}) for s in slots]

graph.add_conditional_edges("planner", planner)
```

### 缓存中间结果

**问题：重复计算相同内容**

```python
# ✅ 使用 checkpointer 缓存
# 如果 thread_id 相同，LangGraph 会自动恢复状态
result = graph.invoke(
    input_data,
    config={"configurable": {"thread_id": "cache-key"}}
)
```

---

## 8. 常见问题

### Q1: 图执行卡住不动

**可能原因：**
- 节点函数没有返回值
- 条件边逻辑错误，进入死循环
- 等待中断但没有恢复

**排查方法：**
```bash
# 1. 检查日志
tail -f backend/data/_debug/*.jsonl

# 2. 在 Studio 中查看当前节点
# 3. 检查该节点的返回值
```

### Q2: 状态更新不生效

**可能原因：**
- 节点返回了空字典 `{}`
- Reducer 配置错误
- 状态 key 拼写错误

**排查方法：**
```python
# 在节点中打印返回值
def my_node(state):
    updates = {"key": "value"}
    print(f"Node returning: {updates}")  # 调试输出
    return updates
```

### Q3: 修复循环不终止

**可能原因：**
- `repair_count` 没有递增
- 条件边判断逻辑错误
- 验证器总是返回失败

**排查方法：**
```python
# 在 Studio 中查看 repair_count
# 或在条件边中打印
def should_continue_repair(state):
    count = state.get("repair_count", 0)
    print(f"Repair count: {count}")  # 调试输出
    return "validator" if count < 3 else "markdown_compiler"
```

### Q4: 中断恢复后状态丢失

**可能原因：**
- Checkpointer 没有正确配置
- 恢复时 thread_id 不一致
- 状态包含不可序列化对象

**排查方法：**
```python
# 检查 checkpointer 配置
checkpointer, profile = get_shared_report_checkpointer(purpose="test")
print(f"Checkpointer: {profile.checkpoint_locator}")

# 确保 thread_id 一致
config = {"configurable": {"thread_id": "same-id"}}
graph.invoke(input1, config=config)  # 第一次
graph.invoke(None, config=config)    # 恢复，使用相同 thread_id
```

---

## 9. 总结

**调试优先级：**

1. **开发新功能时**：单元测试 → 调试脚本 → Studio
2. **提交代码前**：静态检查 → 单元测试
3. **排查生产问题**：调试日志 → 本地复现 → Studio 单步调试
4. **性能优化**：调试日志分析 → 识别瓶颈 → 优化代码

**节省 token 的关键：**
- ✅ 本地使用 mock 数据测试图结构
- ✅ 单元测试覆盖所有确定性逻辑
- ✅ 只在必要时调用真实 LLM
- ✅ 使用 checkpointer 缓存中间结果
- ❌ 不要在生产环境反复试错
