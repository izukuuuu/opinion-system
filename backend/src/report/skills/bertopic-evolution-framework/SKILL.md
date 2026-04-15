---
name: bertopic-evolution-framework
description: 约束报告中的 BERTopic 主题演化章节写法，聚焦主题簇、主题迁移、阶段切换和覆盖率边界。
allowed_tools: get_bertopic_snapshot build_bertopic_insight
metadata:
  report:
    skillKey: bertopic_evolution_framework
    goal: 把 BERTopic 结果组织成可读的主题演化章节，区分背景常量主题、爆发变量主题和阶段性切换主题。
---

# BERTopic 主题演化框架

该 skill 用于稳定约束“BERTopic 主题演化”章节，让主题簇、迁移路径和时序切换在报告中形成单独的深挖章节。

## Goal

把 BERTopic 结果组织成可读的主题演化章节，解释当前主线主题、阶段切换和时间维度上的迁移信号。

## Reasoning Style

- 先指出当前最主要的主题簇，再解释主题如何沿时间迁移。
- 区分背景常量主题、爆发变量主题和阶段性切换主题。
- 如果 temporal 结果缺失，只写聚类分布和覆盖边界，不推断迁移路径。

## Language Requirements

- 正文不暴露 BERTopic 文件名、内部字段名或技术实现细节。
- 主题描述必须围绕现有主题簇和关键词，不凭空补写新的主题标签。
- 如结果覆盖不足，要明确写成“当前仅能观察到主题分布”，不能上升为完整演化结论。

## Section Guidance

```json
{
  "bertopic_evolution": "聚焦主题簇、迁移节奏、时间切换和覆盖边界，不与基础分析章节混写。",
  "full_report": "该章节是平台主题能力的稳定入口，优先解释主题主线和迁移路径。"
}
```

## Current Backend Contract

**读取（只读）：**
- `/workspace/state/task_contract.json` → 提取 `.topic_identifier / .start / .end / .topic_label`，传给 `get_bertopic_snapshot`

**写入（bertopic_evolution_analyst 代理）：**
- `/workspace/state/bertopic_insight.json`，格式：
  ```json
  { "status": "ok", "result": { "topic_clusters": [], "evolution_phases": [], "background_constants": [], "burst_variables": [] } }
  ```

**空结果格式：**
```json
{ "status": "empty", "reason": "BERTopic 快照不存在或主题为空", "result": {}, "skipped_due_to": ["tool_returned_empty"] }
```

## Constraints

- 不要把主题簇描述写成抽象空话，必须回到现有主题名称和时序事实。
- 不要在缺 temporal 结果时强行解释主题迁移。
- 不要把 BERTopic 主题章节直接写成风险建议章节。
- 若 `get_bertopic_snapshot` 返回 `status='empty'`，生成标准化空结构后立即结束，禁止伪造演化趋势。
