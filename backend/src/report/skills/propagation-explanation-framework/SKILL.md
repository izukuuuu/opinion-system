---
name: propagation-explanation-framework
description: Explain platform differences, diffusion rhythm, amplification nodes, and polarization patterns in a report-friendly way.
allowed_tools: compute_report_metrics build_mechanism_summary detect_risk_signals build_basic_analysis_insight
metadata:
  report:
    skillKey: propagation_explanation_framework
    goal: 把传播规模、扩散节奏、平台差异和关键节点转成可解释的传播结构结论。
---

# Propagation Explanation Framework

## Goal

- 解释传播节奏和平台差异。
- 区分“热度大”与“扩散结构重要”。
- 识别关键节点、放大因素和极化迹象。

## Current Backend Contract

**读取（只读）：**
- `/workspace/state/normalized_task.json` → 提取顶层对象，传给 `normalized_task_json`
- `/workspace/state/evidence_cards.json` → 提取 `.result[*].evidence_id` 字符串列表，传给 `evidence_ids_json`
- `/workspace/state/metrics_bundle.json` → 提取 `.result` 数组（完整指标对象列表），传给 `metric_refs_json`
- `/workspace/state/timeline_nodes.json` → 提取 `.result` 数组（完整节点对象列表），传给 `timeline_nodes_json`
- `/workspace/state/conflict_map.json` → 提取 `.result` 内层核心对象，传给 `conflict_map_json` 和 `discourse_conflict_map_json`
- `/workspace/state/actor_positions.json` → 提取 `.result` 数组（完整 actor 对象列表），传给 `actor_positions_json`

**写入（propagation_analyst 代理）：**
- `/workspace/state/mechanism_summary.json`，格式：
  ```json
  { "status": "ok", "result": { "trigger_events": [], "propagation_path": [], "phase_transitions": [], "amplification_nodes": [] } }
  ```
- `/workspace/state/risk_signals.json`，格式：
  ```json
  { "status": "ok", "result": [...风险信号对象列表...] }
  ```

**空结果格式：**
```json
{ "status": "empty", "reason": "上游依赖为空", "result": {}, "skipped_due_to": ["upstream_empty"] }
```

## Constraints

- 不要只重复声量数字。
- 平台差异必须落到内容形态、节奏或主体结构上。
- 禁止把整个 conflict_map 包装对象传给工具（只传 .result 内层核心对象）。
- 禁止把'热度大'直接等同于'扩散结构重要'。
