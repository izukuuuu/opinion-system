---
name: subject-stance-merging
description: Merge subjects, viewpoints, and conflicts into a readable stance matrix without duplicating aliases or mixing actors.
metadata:
  report:
    skillKey: subject_stance_merging
    goal: 输出主体列表、立场矩阵和冲突点，并避免同义主体重复出现。
---

# Subject And Stance Merging

## Goal

- 识别关键主体及其角色。
- 把相近观点聚合为可读立场。
- 明确谁与谁存在冲突，以及冲突围绕什么。

## Constraints

- 主体名需要尽量统一，不要同一主体多种写法并列。
- 立场矩阵要基于证据，不要用情绪化标签替代观点概括。
