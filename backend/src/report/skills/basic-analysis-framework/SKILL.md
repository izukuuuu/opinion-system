---
name: basic-analysis-framework
title: 基础分析章节框架
description: 约束报告中的基础分析章节写法，聚焦量、质、人、场、效的综合判断，不把统计结果写成分散清单。
allowed_tools: get_basic_analysis_snapshot build_basic_analysis_insight
metadata:
  openclaw:
    skillKey: basic_analysis_framework
  report:
    documentType: analysis_report
    aliases:
      - basic_analysis_framework
      - basic-analysis-framework
---

# 基础分析章节框架

该 skill 用于稳定约束“基础分析洞察”章节，让平台既有的量、质、人、场、效能力在报告中形成单独章节，而不是零散分摊到各段。

## Goal

把基础分析统计结果组织成一章完整的综合判断，优先解释整体态势、结构重点和统计边界。

## Reasoning Style

- 先写总体判断，再写关键结构，不按函数名逐项罗列。
- 优先串联声量、趋势、情绪、议题、发声者和地域分布之间的关系。
- 如果多个统计维度共同指向同一主线，应合并表达，不重复描述相同事实。

## Language Requirements

- 正文不暴露内部函数名、文件名、配置名和目录结构。
- 不把图表读取结果直接写成流水账，要说明这些图表共同支持了什么判断。
- 数据缺口要清楚写出，但不能把缺图、缺模块包装成确定性结论。

## Section Guidance

```json
{
  "basic_analysis_insight": "聚焦量、质、人、场、效的综合判断，先总体后结构，再明确边界。",
  "full_report": "该章节是平台基础能力的稳定入口，不与 BERTopic 演化章节混写。"
}
```

## Constraints

- 不要按 `volume/attitude/trends/...` 逐项机械展开。
- 不要把单个统计项拔高为传播机制或治理建议。
- 如果缺少部分模块，只能写成当前覆盖有限、判断需保留边界。
