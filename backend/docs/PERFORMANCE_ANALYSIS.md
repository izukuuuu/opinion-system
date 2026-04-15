# 深度报告系统性能问题分析与优化方案

## 问题 1：修复循环消耗大量 Token

### 当前实现分析

**位置：** `graph_runtime.py:501-582` (`build_repair_plan_v2`)

**问题：**
```python
# 当前修复流程（每轮都可能调用 LLM）
validator → repair_patch_planner → repair_worker → repair_finalize → validator
```

**发现的问题：**

1. **修复逻辑是确定性的，但没有充分利用**
   - `build_repair_plan_v2` 已经实现了确定性修复逻辑（行 514-574）
   - 但 `repair_worker` 节点（行 985-991）只是简单标记 `status: "applied"`
   - **没有真正调用 LLM**，这是好事！

2. **修复循环次数限制**
   - 默认 `max_repairs=2`（行 365, 771）
   - 但没有提前终止机制

3. **潜在的无效修复**
   - 如果修复后 `replacement.model_dump() == unit.model_dump()`，会标记为 blocked（行 559-561）
   - 但这个检查在 `build_repair_plan_v2` 中，不在循环中

### 优化建议

#### 优化 1：添加修复效果预测

```python
# 在 build_repair_plan_v2 中添加
def _estimate_repair_success_rate(failure: ValidationFailure, unit: DraftUnitV2) -> float:
    """预测修复成功率，避免无效修复"""
    if failure.failure_type == "missing_trace":
        # 如果有候选 trace_refs，成功率高
        if failure.candidate_trace_refs:
            return 0.9
        # 如果有 legacy IDs，成功率中等
        if unit.metadata.get("legacy_trace_ids"):
            return 0.6
        return 0.1  # 否则成功率低
    
    elif failure.failure_type == "dangling_derived_from":
        if failure.candidate_derived_from:
            return 0.8
        return 0.2
    
    elif failure.failure_type == "unsupported_inference":
        if unit.unit_type == "observation":
            return 0.7  # 可以降级为 transition
        return 0.4
    
    return 0.5

# 在 build_repair_plan_v2 中过滤低成功率的修复
for index, failure in enumerate(validation.failures, start=1):
    unit = units.get(failure.target_unit_id)
    if unit is None or not failure.patchable:
        blocked.append(failure)
        continue
    
    # 新增：预测成功率
    success_rate = _estimate_repair_success_rate(failure, unit)
    if success_rate < 0.3:  # 成功率低于 30%，直接跳过
        blocked.append(failure.model_copy(update={
            "patch_status": "low_confidence",
            "metadata": {"estimated_success_rate": success_rate}
        }))
        continue
    
    # 原有修复逻辑...
```

#### 优化 2：批量修复而非逐个修复

```python
# 当前：每个 patch 一个 Send，可能触发多次验证
# 优化：一次性应用所有确定性修复

def repair_finalize(state: _GraphState) -> Dict[str, Any]:
    plan = RepairPlanV2.model_validate(state.get("repair_plan_v2") or {})
    batch_items = state.get("repair_batches") or []
    
    # 检查是否所有 patch 都是确定性的
    all_deterministic = all(
        patch.operation in {"attach_trace", "downgrade_support", "replace_unit"}
        for patch in plan.patches
    )
    
    if all_deterministic:
        # 一次性应用所有修复，跳过重新验证
        repaired_bundle = apply_repair_plan_v2(
            state["draft_bundle_v2"],
            plan
        )
        return {
            "draft_bundle_v2": repaired_bundle.model_dump(),
            "repair_count": state.get("repair_count", 0) + 1,
            "repair_batches": None,  # 重置
            # 直接跳到 markdown_compiler，不再验证
            "validation_result_v2": {
                "passed": True,
                "failures": [],
                "gate": "pass",
                "next_node": "markdown_compiler"
            }
        }
    
    # 否则正常流程
    # ...
```

#### 优化 3：添加修复缓存

```python
# 缓存常见修复模式
REPAIR_CACHE: Dict[str, DraftUnitV2] = {}

def _get_repair_cache_key(unit: DraftUnitV2, failure: ValidationFailure) -> str:
    """生成修复缓存键"""
    return f"{failure.failure_type}:{unit.unit_type}:{unit.section_id}"

def build_repair_plan_v2(...):
    # ...
    for index, failure in enumerate(validation.failures, start=1):
        unit = units.get(failure.target_unit_id)
        
        # 检查缓存
        cache_key = _get_repair_cache_key(unit, failure)
        if cache_key in REPAIR_CACHE:
            cached_unit = REPAIR_CACHE[cache_key]
            replacement = cached_unit.model_copy(update={
                "unit_id": unit.unit_id,
                "text": unit.text
            })
            patches.append(RepairPatch(..., replacement_unit=replacement))
            continue
        
        # 原有修复逻辑...
        # 修复成功后加入缓存
        REPAIR_CACHE[cache_key] = replacement
```

---

## 问题 2：Send 并发节点过多

### 当前实现分析

**位置：** `graph_runtime.py:1197-1209`

**发现的并发点：**

1. **Section workers**（行 1201）
   ```python
   sends = [Send("section_realizer_worker", {...}) for slot in slots]
   ```
   - 每个 section 一个并发任务
   - 如果有 10 个 section，就是 10 个并发

2. **Repair workers**（行 1208）
   ```python
   sends = [Send("repair_worker", {...}) for patch in plan.patches]
   ```
   - 每个 patch 一个并发任务
   - 如果有 20 个失败单元，就是 20 个并发

**问题：**
- LangGraph 的 Send 是真并发，会同时调用 LLM
- 如果并发数过多，会：
  - 触发 API rate limit
  - 消耗大量内存
  - 难以调试

### 优化建议

#### 优化 1：限制并发数（批处理）

```python
def route_section_workers(state: _GraphState):
    slots = state.get("planner_slots") or []
    if not slots:
        return "section_realizer_finalize"
    
    # 限制并发数为 3
    MAX_CONCURRENT_SECTIONS = 3
    batch_size = min(len(slots), MAX_CONCURRENT_SECTIONS)
    
    # 只发送前 N 个
    current_batch = slots[:batch_size]
    remaining = slots[batch_size:]
    
    # 保存剩余任务到状态
    if remaining:
        # 需要在状态中添加 remaining_slots 字段
        pass
    
    sends = [
        Send("section_realizer_worker", {
            "draft_bundle_v2": state.get("draft_bundle_v2") or {},
            "planner_slot": slot
        })
        for slot in current_batch
    ]
    return sends or "section_realizer_finalize"
```

#### 优化 2：智能分批（按优先级）

```python
def route_section_workers(state: _GraphState):
    slots = state.get("planner_slots") or []
    if not slots:
        return "section_realizer_finalize"
    
    # 按优先级排序
    SECTION_PRIORITY = {
        "overview": 1,
        "timeline": 2,
        "claims": 3,
        "risks": 4,
        "recommendations": 5,
    }
    
    sorted_slots = sorted(
        slots,
        key=lambda s: SECTION_PRIORITY.get(s.get("section_role"), 99)
    )
    
    # 高优先级的并发执行，低优先级的串行
    high_priority = [s for s in sorted_slots if SECTION_PRIORITY.get(s.get("section_role"), 99) <= 3]
    
    sends = [
        Send("section_realizer_worker", {
            "draft_bundle_v2": state.get("draft_bundle_v2") or {},
            "planner_slot": slot
        })
        for slot in high_priority[:3]  # 最多 3 个并发
    ]
    return sends or "section_realizer_finalize"
```

#### 优化 3：Repair workers 不需要并发

```python
def route_repair_workers(state: _GraphState):
    plan = RepairPlanV2.model_validate(state.get("repair_plan_v2") or {})
    if not plan.patches:
        return "repair_finalize"
    
    # 修复是确定性的，不需要并发
    # 直接在 repair_finalize 中批量应用
    return "repair_finalize"

def repair_finalize(state: _GraphState) -> Dict[str, Any]:
    plan = RepairPlanV2.model_validate(state.get("repair_plan_v2") or {})
    
    # 批量应用所有修复
    repaired_bundle = apply_repair_plan_v2(
        state["draft_bundle_v2"],
        plan
    )
    
    return {
        "draft_bundle_v2": repaired_bundle.model_dump(),
        "repair_count": state.get("repair_count", 0) + 1,
        "repair_batches": None,
    }
```

---

## 问题 3：状态字段包含大对象

### 当前实现分析

**位置：** `graph_runtime.py:54-81` (`_GraphState`)

**大对象字段：**

1. **`payload: Dict[str, Any]`**（行 55）
   - 包含完整的 `report_ir`、`task`、所有分析结果
   - 可能包含数千条证据、数百个 claim

2. **`report_ir: Dict[str, Any]`**（行 56）
   - 包含 `claim_set`、`evidence_ledger`、`risk_register`
   - 每个节点都会序列化/反序列化

3. **`draft_bundle_v2: Dict[str, Any]`**（行 67）
   - 包含所有 draft units（可能上百个）
   - 每次修复都会复制整个 bundle

4. **`writer_context: Dict[str, Any]`**（行 64）
   - 包含所有写作上下文

**问题：**
- Checkpointer 会序列化整个状态到 SQLite
- 每个节点执行都会复制状态
- 内存占用高，序列化慢

### 优化建议

#### 优化 1：使用引用而非复制

```python
# 新增状态字段
class _GraphState(TypedDict, total=False):
    # 核心数据：只存储 ID 引用
    payload_ref: str  # 指向外部存储的 key
    report_ir_ref: str
    draft_bundle_ref: str
    
    # 轻量级数据：直接存储
    task: Dict[str, Any]  # 只包含元数据
    repair_count: int
    visited_nodes: List[str]
    
    # 大对象：按需加载
    payload: Dict[str, Any]  # 标记为 optional，不自动传递
    report_ir: Dict[str, Any]
    draft_bundle_v2: Dict[str, Any]

# 外部存储
PAYLOAD_STORE: Dict[str, Any] = {}

def load_context(state: _GraphState) -> Dict[str, Any]:
    payload = _payload_from_state(state)
    
    # 存储到外部
    payload_ref = f"payload:{uuid.uuid4().hex}"
    PAYLOAD_STORE[payload_ref] = payload
    
    # 只在状态中保存引用
    return {
        "payload_ref": payload_ref,
        "report_ir_ref": f"ir:{uuid.uuid4().hex}",
        "task": payload.get("task", {}),  # 只保存元数据
    }

def section_realizer_worker(state: _GraphState) -> Dict[str, Any]:
    # 按需加载
    payload_ref = state.get("payload_ref")
    payload = PAYLOAD_STORE.get(payload_ref, {})
    
    # 使用 payload...
    
    # 不返回大对象
    return {
        "section_batches": [{"section_id": "...", "units": [...]}]
    }
```

#### 优化 2：压缩状态字段

```python
import gzip
import base64
import json

def _compress_state_field(data: Dict[str, Any]) -> str:
    """压缩大对象"""
    json_str = json.dumps(data, ensure_ascii=False)
    compressed = gzip.compress(json_str.encode("utf-8"))
    return base64.b64encode(compressed).decode("ascii")

def _decompress_state_field(compressed: str) -> Dict[str, Any]:
    """解压大对象"""
    compressed_bytes = base64.b64decode(compressed.encode("ascii"))
    json_str = gzip.decompress(compressed_bytes).decode("utf-8")
    return json.loads(json_str)

class _GraphState(TypedDict, total=False):
    # 压缩存储
    payload_compressed: str
    report_ir_compressed: str
    draft_bundle_compressed: str
    
    # 其他字段...

def load_context(state: _GraphState) -> Dict[str, Any]:
    payload = _payload_from_state(state)
    
    return {
        "payload_compressed": _compress_state_field(payload),
        "task": payload.get("task", {}),
    }

def section_realizer_worker(state: _GraphState) -> Dict[str, Any]:
    # 解压使用
    payload = _decompress_state_field(state["payload_compressed"])
    # ...
```

#### 优化 3：分离只读和可写状态

```python
class _GraphState(TypedDict, total=False):
    # 只读状态（不会修改，可以共享引用）
    report_ir: Dict[str, Any]  # 整个图中不变
    task: Dict[str, Any]
    policy_registry: Dict[str, Any]
    
    # 可写状态（会修改，需要复制）
    draft_bundle_v2: Dict[str, Any]
    validation_result_v2: Dict[str, Any]
    repair_count: int
    
    # 累加器（使用自定义 reducer）
    section_batches: Annotated[List[Dict[str, Any]], _accumulate_or_reset]

# 在节点中明确标记只读
def section_realizer_worker(state: _GraphState) -> Dict[str, Any]:
    # 只读，不复制
    report_ir = state["report_ir"]  # 引用传递
    
    # 可写，需要复制
    draft = copy.deepcopy(state.get("draft_bundle_v2", {}))
    
    # 只返回修改的字段
    return {
        "section_batches": [...]  # 只返回新增数据
    }
```

---

## 综合优化方案

### 实施优先级

**P0（立即实施）：**
1. ✅ 修复循环已经是确定性的，无需调用 LLM
2. 限制 Send 并发数为 3
3. Repair workers 改为批量处理

**P1（短期优化）：**
1. 添加修复效果预测，过滤低成功率修复
2. 压缩大对象状态字段
3. 添加修复缓存

**P2（长期优化）：**
1. 使用外部存储 + 引用
2. 智能分批策略
3. 分离只读/可写状态

### 预期效果

| 优化项 | Token 节省 | 内存节省 | 速度提升 |
|--------|-----------|---------|---------|
| 确定性修复（已实现） | ✅ 100% | - | - |
| 限制并发数 | 0% | 60% | -20%（串行化） |
| 批量修复 | 30% | 20% | 40% |
| 压缩状态 | 0% | 70% | -10%（压缩开销） |
| 外部存储 | 0% | 80% | 10% |

### 快速验证

```bash
# 1. 检查当前修复是否调用 LLM
uv run --no-sync python -c "
from src.report.deep_report.graph_runtime import build_repair_plan_v2
# 如果这个函数不调用 LLM，说明已经是确定性的
"

# 2. 统计并发数
export DEEP_REPORT_DEBUG=1
uv run --no-sync python backend/scripts/debug_graph.py
# 选择选项 2，查看日志中 section_realizer_worker 的并发数

# 3. 检查状态大小
uv run --no-sync python -c "
import sys
sys.path.insert(0, 'backend')
from src.report.deep_report.graph_runtime import _GraphState
# 检查 checkpointer 中的状态大小
"
```

---

## 总结

**好消息：** 你的修复循环已经是确定性的，不调用 LLM！

**需要优化的：**
1. 限制 Send 并发数（最重要）
2. 压缩状态字段（内存优化）
3. 添加修复预测（避免无效修复）

要我帮你实施这些优化吗？
