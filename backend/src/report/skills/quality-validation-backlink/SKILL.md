---
name: quality-validation-backlink
description: Validate a report for unsupported claims, time misalignment, and subject confusion, then push issues back to the right stage.
capability_ids:
  - semantic.utility_gate
  - evidence.normalize_retrieve_verify
runtime_surfaces:
  - deep_report_subagent
agent_families:
  - decision_utility_judge
  - validator
guidance_only: true
metadata:
  report:
    skillKey: quality_validation_backlink
    goal: 对结构化结果做事实一致性、时间一致性和主体边界校验。
---

# Quality Validation And Backlink

## Goal

- 检查三类问题：无证据判断、时间错位、跨主体混淆。
- 问题要给出 severity、message 和 related_ids。
- 校验说明要能直接回推到该补哪一类材料。

## Constraints

- 不把文风问题伪装成事实问题。
- 没有明确问题时要说明通过理由，而不是空输出。
