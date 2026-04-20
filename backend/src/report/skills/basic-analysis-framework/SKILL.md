---
name: basic-analysis-framework
description: 约束报告中的基础分析章节写法，聚焦量、质、人、场、效的综合判断，不把统计结果写成分散清单。
allowed_tools: get_basic_analysis_snapshot build_basic_analysis_insight
metadata:
  report:
    skillKey: basic_analysis_framework
    goal: 把基础分析统计结果组织成综合判断章节，优先解释整体态势、结构重点和统计边界。
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
- 情感段首句必须先写清正向、负向、中性三类数量或占比，不得跳过基本结构直接写抽象判断。
- 若没有按情感分层的代表性评论样本，就不要替正向、负向、中性各自“脑补”评论立场，只能停留在数量结构层。
- 若已通过证据召回拿到带 `sentiment` 标签的证据卡或评论片段，可在数量结构之后补一句“高频表达主要集中在什么问题”，但必须带引摘或可回链样本。

## Section Guidance

- “基础分析洞察”按固定顺序写：先给出总体现象判断，再插入情感分析总体图，再解释图所反映的结构，然后插入词云图，最后补边界说明。
- 这一节是基础分析能力在报告中的稳定入口，放在报告前部，不与 BERTopic 主题演化混写。

## Fixed Chart Template

- 本章节最多固定插入 2 张图，不由模型自由选择图型。
- 图 1：情感分析总体图
- 图 2：词云图
- 图注统一由系统生成，表现为“图 x 图注”，居中、小字号。
- 图表只服务正文判断，不要把图表描述写成技术说明或字段说明。

## Current Backend Contract

**读取（只读）：**
- `/workspace/projects/{project_identifier}/reports/{report_range}/state/task_contract.json` → 提取 `.topic_identifier / .start / .end / .topic_label`，传给 `get_basic_analysis_snapshot`

**工具调用规范（coordinator 和 archive_evidence_organizer 使用）：**
- `get_basic_analysis_snapshot(topic_identifier=..., start=..., end=..., topic_label=...)` — 参数严格取自 task_contract
- `build_basic_analysis_insight(snapshot_json=...)` — snapshot_json 传 get_basic_analysis_snapshot 的完整返回值 JSON 字符串

**空结果格式：**
```json
{ "status": "empty", "reason": "基础分析快照不存在", "result": {}, "skipped_due_to": ["tool_returned_empty"] }
```

## Constraints

- 不要按 `volume/attitude/trends/...` 逐项机械展开。
- 不要把单个统计项拔高为传播机制或治理建议。
- 如果缺少部分模块，只能写成当前覆盖有限、判断需保留边界。
- 快照不存在时生成标准化空结构，禁止伪造基础分析数据。
- 不要把“情感分析总体图”“词云图”写成后端产物说明或工具调用记录。
- 不要用“这张图提示的重点不是……而是……”这类辩护句替代情感结构说明。
- 若正文需要解释正向、负向、中性分别在说什么，应先通过证据召回拿到可引用样本；没有样本时，不写评论类型解释。

