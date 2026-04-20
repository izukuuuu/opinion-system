---
name: evidence-source-credibility
description: Normalize raw retrieval hits into evidence blocks, deduplicate overlaps, and keep source credibility and citation boundaries explicit.
allowed_tools: retrieve_evidence_cards get_basic_analysis_snapshot
metadata:
  report:
    skillKey: evidence_source_credibility
    goal: 将原始命中结果压缩成可引用、可去重、可回链的证据块。
---

# Evidence Source Credibility

## Goal

- 把原始条目整理成统一证据块。
- 统一时间、来源、主体、立场和 citation_ids。
- 同义复述、重复转载、同一事件的转述片段要合并描述。

## Current Backend Contract

**读取（只读）：**
- `/workspace/projects/{project_identifier}/reports/{report_range}/state/task_contract.json` → 提取 `.contract_id`，用于所有 `retrieve_evidence_cards` 调用
- `/workspace/projects/{project_identifier}/reports/{report_range}/state/corpus_coverage.json` → 检查 `.coverage.readiness_flags`

**写入：**
- `/workspace/projects/{project_identifier}/reports/{report_range}/state/evidence_cards.json`，格式：
  ```json
  { “status”: “ok”, “result”: [...证据卡对象列表...], “coverage”: {...} }
  ```

**分页策略：**
- 每个 intent 首次调用 `limit=12`；若 `cursor_next` 非空且证据数 < 20，追加一次调用，最多 2 次/intent
- 6 个 intent 合计至少召回 15 条非空证据卡；若不足，在摘要中写明缺口

**空结果格式：**
```json
{
  “status”: “empty”,
  “reason”: “corpus 无数据”,
  “result”: [],
  “skipped_due_to”: [“no_records_in_scope”]
}
```

## Constraints

- 证据块只能写”能支持什么”，不能替证据做超额推断。
- 证据不足时，宁可保留低置信度，也不要凑成强判断。
- 引用索引必须能回到具体来源。
- intent 必须从枚举白名单选取：`overview / timeline / actors / risk / claim_support / claim_counter`，禁止直接传中文词。

