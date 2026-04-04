---
name: timeline-alignment-slicing
description: Build event timelines by aligning dates, separating stages, and explaining likely triggers without overstating causality.
metadata:
  report:
    skillKey: timeline_alignment_slicing
    goal: 生成清晰的事件序列，并在证据允许范围内解释阶段切换与触发因素。
---

# Timeline Alignment And Slicing

## Goal

- 以时间先后组织关键节点。
- 将事件分成阶段，解释每个阶段为何变化。
- 因果链只写“可能触发”和“证据支持的影响”，不要把相关性直接写成因果。

## Constraints

- 日期不明确时要显式保留边界。
- 不要把多个主体的动作混成同一个时间节点。
