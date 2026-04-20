---
name: chart-interpretation-guidelines
description: Translate chart and metric outputs into concise analytical statements without reading them as proof of unsupported causal claims.
allowed_tools: compute_report_metrics build_basic_analysis_insight
metadata:
  report:
    skillKey: chart_interpretation_guidelines
    goal: 把基础分析图表读成结论线索，而不是直接当成因果证明。
agent_families:
  - propagation_analyst
  - document_composer
runtime_surfaces:
  - deep_report_subagent
  - plain_compat
---

# Chart Interpretation Guidelines

## Goal

- 用图表说明结构变化、峰值位置和相对差异。
- 指标解释要回到任务问题本身。

## Current Backend Contract

**读取（只读）：**
- `/workspace/projects/{project_identifier}/reports/{report_range}/state/metrics_bundle.json` → 读取 `.result` 数组（完整指标对象列表）
- `/workspace/projects/{project_identifier}/reports/{report_range}/state/event_analysis.json` → 读取 `.result.platform_analysis` 用于跨平台差异说明

**注意：**
- 图表数据来自 `metrics_bundle.result`，不要直接从 `evidence_cards` 自行汇总统计数字
- 指标解释必须回到任务问题本身，不脱离 `normalized_task.json` 的分析问题集

## Constraints

- 不要把单一指标直接提升为综合结论。
- 不要把图表标签当成现实世界的确定事实。
- 平台差异必须落到内容形态、节奏或主体结构上，而非只引用数量对比。

