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
- 正文必须解释“这些主题分别在讨论什么”，不能只对着图说热度涨跌。
- 至少交代 2-3 个头部主题簇的主题含义、关键词指向和代表性阶段，不能只写“主题线交替抬升”。
- 若已有峰值周或主导阶段信息，应明确写出“哪一周 / 哪一阶段由哪个主题主导”，避免把时间演化写成泛泛总结。

## Section Guidance

- “BERTopic 主题演化”按固定顺序写：先给出主题主线判断，再插入主题演变图，再解释演变过程和阶段切换，最后补覆盖边界。
- 这一节固定放在“基础分析洞察”之后，用来承接前面的总体统计判断，不单独扩写成风险建议章节。
- 图前正文要先解释主题主线与头部主题簇的含义；图后正文要解释峰值周、切换周和稳定阶段分别说明了什么。
- 优先使用工具结果里已给出的主题画像、峰值周和阶段信息，不要把这一节写成“图显示有多个波段，因此议题反复被激活”的空泛复述。

## Fixed Chart Template

- 本章节固定最多 1 张图，不由模型自由决定图型。
- 图 3：主题演变图
- 图注统一由系统生成，表现为“图 x 图注”，居中、小字号。
- 图表是正文论证的辅助，不要把章节写成技术说明、模型流程说明或主题编号清单。

## Current Backend Contract

**读取（只读）：**
- `/workspace/projects/{project_identifier}/reports/{report_range}/state/task_contract.json` → 提取 `.topic_identifier / .start / .end / .topic_label`，传给 `get_bertopic_snapshot`

**写入（bertopic_evolution_analyst 代理）：**
- `/workspace/projects/{project_identifier}/reports/{report_range}/state/bertopic_insight.json`，格式：
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
- 不要把“主题演变图”写成字段解释或后端产物说明。
- 若工具结果已提供主题描述、关键词、峰值周或阶段信息，正文必须显式吸收，不要遗漏成“只有图、没有主题解释”。

