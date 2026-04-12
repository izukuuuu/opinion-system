---
name: timeline-alignment-slicing
description: Build versioned timeline nodes from evidence cards, keep stage boundaries explicit, and pair timeline analysis with chart-ready temporal metrics.
allowed_tools: build_event_timeline compute_report_metrics
metadata:
  report:
    skillKey: timeline_alignment_slicing
    goal: 基于证据卡生成可回链的时间线节点与时间分布指标，确保阶段切换、证据绑定和边界说明都稳定可验证。
---

# Timeline Alignment And Slicing

## Goal

- 基于 `evidence_cards` 组织时间节点，而不是直接阅读原始命中列表。
- 生成的时间线节点必须可回链到证据卡，至少包含时间、摘要、支持证据，必要时包含冲突证据。
- 同步生成 chart-ready 的时间分布指标，供后续 `section_packet` 和报告渲染复用。

## Constraints

- 日期不明确时要显式保留边界。
- 不要把多个主体的动作混成同一个时间节点。
- 不要把“同一天讨论很多”直接写成“发生了新的事实事件”。
- 不要把相关性直接写成因果；只能写“可能触发”“与节点同步出现”“证据显示影响”。
- 不要调用或假设存在旧的时间窗/峰值类 legacy tool；默认运行时只面向 v2 tool surface。

## Current Backend Contract

- 当前 `timeline_analyst` 在后端只应读取：
  - `/workspace/state/normalized_task.json`
  - `/workspace/state/evidence_cards.json`
- 当前 `timeline_analyst` 只应产出：
  - `/workspace/state/timeline_nodes.json`
  - `/workspace/state/metrics_bundle.json`
- 后续章节写作不会直接读取你的自然语言总结，而是主要消费：
  - `/workspace/state/section_packets/timeline.json`

## Tool Surface

- 当前阶段默认只对应两类 v2 工具：
  - `build_event_timeline`
  - `compute_report_metrics`
- 不要假设还存在 `build_timeline`、`analyze_event_window` 之类旧入口。

## Expected Output Shape

- 时间线节点应尽量贴近以下语义：
  - `node_id`
  - `time_label`
  - `summary`
  - `support_evidence_ids`
  - `conflict_evidence_ids`
  - `confidence`
  - `event_type`
- 指标对象应保持 chart-ready，不写 prose，优先时间相关 family：
  - `temporal`
  - `overview`

## Decision Rules

- 如果同一天有多张近重复证据卡，优先合并成一个节点，不要机械一条卡一条节点。
- 如果同一时间点同时存在支持与反证，保留 `conflict_evidence_ids`，不要强行消解冲突。
- 如果证据只足够支持“讨论升温”，节点摘要应写传播变化，不要冒充事实更新。
- 如果证据不足以切出多个阶段，就保守输出较少节点，不要为了“完整时间线”硬切阶段。
