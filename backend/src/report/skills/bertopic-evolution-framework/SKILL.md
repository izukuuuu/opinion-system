---
name: bertopic-evolution-framework
title: BERTopic 主题演化框架
description: 约束报告中的 BERTopic 主题演化章节写法，聚焦主题簇、主题迁移、阶段切换和覆盖率边界。
allowed_tools: get_bertopic_snapshot build_bertopic_insight
metadata:
  openclaw:
    skillKey: bertopic_evolution_framework
  report:
    documentType: analysis_report
    aliases:
      - bertopic_evolution_framework
      - bertopic-evolution-framework
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

## Constraints

- 不要把主题簇描述写成抽象空话，必须回到现有主题名称和时序事实。
- 不要在缺 temporal 结果时强行解释主题迁移。
- 不要把 BERTopic 主题章节直接写成风险建议章节。
