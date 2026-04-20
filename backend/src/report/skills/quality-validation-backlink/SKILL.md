---
name: quality-validation-backlink
description: Validate a report for unsupported claims, time misalignment, and subject confusion, then push issues back to the right stage.
allowed_tools: judge_decision_utility
metadata:
  report:
    skillKey: quality_validation_backlink
    goal: 对结构化结果做事实一致性、时间一致性和主体边界校验，产出 typed utility assessment。
agent_families:
  - decision_utility_judge
  - validator
runtime_surfaces:
  - deep_report_subagent
---

# Quality Validation And Backlink

## Goal

- 检查三类问题：无证据判断、时间错位、跨主体混淆。
- 问题要给出 severity、message 和 related_ids。
- 校验说明要能直接回推到该补哪一类材料。

## Current Backend Contract

**读取（只读，全部上游文件）：**
- `/workspace/projects/{project_identifier}/reports/{report_range}/state/normalized_task.json` → 提取顶层对象，传给 `normalized_task_json`
- `/workspace/projects/{project_identifier}/reports/{report_range}/state/risk_signals.json` → 提取 `.result` 数组，传给 `risk_signals_json`
- `/workspace/projects/{project_identifier}/reports/{report_range}/state/actor_positions.json` → 提取 `.result` 数组，传给 `actor_positions_json`
- `/workspace/projects/{project_identifier}/reports/{report_range}/state/agenda_frame_map.json` → 提取 `.result` 内层核心对象，传给 `agenda_frame_map_json`
- `/workspace/projects/{project_identifier}/reports/{report_range}/state/conflict_map.json` → 提取 `.result` 内层核心对象，传给 `conflict_map_json`
- `/workspace/projects/{project_identifier}/reports/{report_range}/state/mechanism_summary.json` → 提取 `.result` 内层核心对象，传给 `mechanism_summary_json`
- 其余文件（corpus_coverage / evidence_cards / task_derivation）只读，用于检测上游空状态

**写入：**
- `/workspace/projects/{project_identifier}/reports/{report_range}/state/utility_assessment.json`，格式：
  ```json
  {
    "status": "ok",
    "result": {
      "decision": "pass | fallback_recompile | block",
      "completeness_score": 0.0,
      "missing_dimensions": [],
      "unverified_points": [],
      "can_proceed_to_writing": true
    }
  }
  ```

**空状态处理规则：**
- 若任一上游文件 `status='empty'` 或含 `skipped_due_to`，必须将该字段的值写入 `missing_dimensions`
- 禁止在上游明确为空时输出 `decision='pass'`

**标准化空结果格式（skipped_due_to 枚举值）：**
- `no_records_in_scope` — corpus_coverage 确认无数据
- `upstream_empty` — 上游依赖文件为空结构
- `insufficient_evidence` — 证据不足以支撑分析
- `tool_returned_empty` — 工具调用返回空结果

## Constraints

- 不把文风问题伪装成事实问题。
- 没有明确问题时要说明通过理由，而不是空输出。
- 禁止把整个包装对象传给工具参数（只传 .result 内层内容）。

