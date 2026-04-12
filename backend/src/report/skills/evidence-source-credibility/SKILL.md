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

## Constraints

- 证据块只能写“能支持什么”，不能替证据做超额推断。
- 证据不足时，宁可保留低置信度，也不要凑成强判断。
- 引用索引必须能回到具体来源。
