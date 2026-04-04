---
name: retrieval-router-rules
description: Decide whether a report question should first use structured analysis, raw documents, timeline aggregation, or entity graph retrieval.
metadata:
  report:
    skillKey: retrieval_router_rules
    goal: 为报告任务优先选择正确的检索路径和关键问题，避免一开始就盲目扩展检索范围。
---

# Retrieval Router Rules

## Goal

- 先判断当前问题更适合走基础分析快照、原始条目回查、时间线聚合还是主体图谱提取。
- 检索路径只服务于当前任务，不追求“能查的都查”。

## Reasoning Style

- 先识别问题类型，再给出优先路径。
- 如果已有基础分析足以回答，就不要先下沉到原始条目。
- 只有当结论需要直接证据、引用索引或主体判断时，再优先原始条目回查。

## Constraints

- 不要把工具清单直接复述给用户。
- 不要把“多查一点”当作默认最优策略。
