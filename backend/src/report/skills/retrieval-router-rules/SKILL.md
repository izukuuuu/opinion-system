---
name: retrieval-router-rules
description: Freeze task scope, build a retrieval plan, and decide which v2 report-object tools should run first without falling back to legacy raw-hit tools.
allowed_tools: normalize_task get_corpus_coverage
metadata:
  report:
    skillKey: retrieval_router_rules
    goal: 为报告任务先冻结 scope、生成 retrieval plan 和 coverage 判断，再把后续问题分发给议题/框架、冲突、机制与风险工具。
---

# Retrieval Router Rules

## Goal

- 先冻结任务边界，再决定后续应该优先走哪些中间对象工具。
- 先产出 `/workspace/state/normalized_task.json`、`/workspace/state/retrieval_plan.json`、`/workspace/state/corpus_coverage.json`。
- 检索路径只服务于当前任务，不追求“能查的都查”。

## Reasoning Style

- 先识别问题类型，再明确 `analysis_question_set`、`coverage_expectation`、`inference_policy`。
- 先把问题拆成 retrieval intent，例如 `overview / agenda_frame / timeline / actors / conflict / mechanism / risk / claim_support / claim_counter`，不要维持一个笼统 query。
- retrieval plan 里要体现时间、平台、主体、阶段这些硬约束，而不是只写关键词。
- retrieval plan 除了 `router_facets` 和 `dispatch_plan`，还要保留 `dispatch_quality_ledger` 的 planned surface，方便后续 trace grading。
- dispatch plan 应当优先服务 typed judgment artifacts：`AgendaFrameMap`、`ConflictMap`、`MechanismSummary`、`UtilityAssessment`。
- 如果 coverage 已经显示存在明显缺口，要先把“无数据”和“无发现”区分开，再决定是否继续扩检。
- 默认使用 tool surface：`normalize_task`、`get_corpus_coverage`，并为后续 `retrieve_evidence_cards` 提供 query rewrite 思路。

## Constraints

- 不要把工具清单直接复述给用户。
- 不要把“多查一点”当作默认最优策略。
- legacy raw-hit 工具已经从默认 tool surface 中移除；不要再假设存在 `query_documents`、`build_timeline`、`build_entity_graph` 这类入口。
- 不要让 writer 直接接触原始检索命中；writer 只应消费 `/workspace/state/section_packets/*.json`。
- 不要让 router 用 prose token fallback 决定 specialist；派工依据必须能回放为 typed facets 与 dispatch reason。

## Expected Output

- 一个简短总结，说明：
  - 当前 scope 是否稳定
  - coverage 是否满足最低要求
  - 后续应优先支撑哪些 judgment artifacts
  - 是否需要扩大时间窗、增加平台或补充反证检索
- 同时把 retrieval plan 写入 `/workspace/state/retrieval_plan.json`，至少包含：
  - `intent`
  - `query_variants`
  - `filters`
  - `retrieval_strategy`
  - `rerank_policy`
  - `compression_policy`
  - `router_facets`
  - `dispatch_plan`
  - `dispatch_quality_ledger`
