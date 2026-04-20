---
name: subject-stance-merging
description: >
  Merge subjects, viewpoints, and conflicts into a readable stance matrix.
  Use this skill whenever the user needs to map out who holds what position
  on a contested issue — especially for policy debates, media discourse
  analysis, organizational conflicts, public affairs reporting, or academic
  argumentation. Trigger when the user mentions "各方立场""利益相关方""观点梳理"
  "冲突分析""discourse map" or asks to compare multiple actors' positions on
  a topic. This skill applies communication theory to ensure analysis is
  evidence-grounded, not emotionally labeled.
allowed_tools: extract_actor_positions
metadata:
  report:
    skillKey: subject_stance_merging
    goal: >
      输出主体列表、立场矩阵和冲突点，以传播学理论为分析框架，
      避免同义主体重复出现，避免用情绪化标签替代立场概括。
---

# Subject-Stance Merging
## 核心目标

1. **识别并统一关键主体**（避免同一行动者多种写法并列）
2. **以证据为基础聚合立场**（避免情绪化、贴标签式概括）
3. **明确冲突的结构**（谁与谁在争什么、争的是哪个层次的问题）
4. **输出可读、可引用的立场矩阵**

---

## 理论框架选用指南

分析前先判断语境，选择最适配的框架（可叠加使用）：

| 语境类型 | 优先框架 |
|---|---|
| 新闻报道 / 媒体事件 | 框架理论（Framing Theory） |
| 政策辩论 / 立法争议 | 话语联盟（Discourse Coalition） |
| 组织内部冲突 | 辩证张力理论（Dialectical Tensions） |
| 公共议题 / 舆论分析 | 议程设置 + 立场光谱分析 |
| 学术争鸣 | 哈贝马斯有效性声明分析 |

---

## Step 1 — 主体识别与去重

### 原则
- **统一命名**：同一主体只保留一种规范写法。例如"央视""中央电视台""CCTV"归并为一个条目，括号注明别称。
- **角色标注**：每个主体标注其在该议题中的**结构性角色**，而非道德评价。

### 主体类型参考（传播学视角）
| 类型 | 说明 |
|---|---|
| 信源主体（Source Actor） | 主动发出信息、构建议题框架的一方 |
| 受众主体（Audience Actor） | 接收信息、可能被动员或被影响的一方 |
| 中介主体（Intermediary） | 媒体、平台、翻译者等，立场可能隐性 |
| 权威主体（Authority Actor） | 拥有规则制定权或合法性赋予权的机构 |
| 受影响主体（Affected Party） | 议题后果的直接承担者，立场常被代言 |

> ⚠️ 注意"代言陷阱"：某主体宣称代表另一群体时，需区分**代言方的立场**与**被代言方的实际利益**，不可混同。

---

## Step 2 — 立场提取与聚合

### 立场提取的四个维度（基于 Entman 框架分析）

每个主体的立场从以下四个维度提取：

1. **问题定义**（Problem Definition）：该主体如何界定这件事是什么问题？
2. **因果归因**（Causal Attribution）：谁/什么被认为是原因？
3. **道德评价**（Moral Evaluation）：该主体持有什么规范性判断？
4. **解决方案**（Remedy/Solution）：该主体主张采取什么行动？

### 立场聚合规则
- 相同框架维度上的立场相近者，可归入同一"立场簇"（Stance Cluster）。
- 聚合时**引用原话或原文证据**，不以推断替代引述。
- 禁止使用情绪性标签（如"极端""无理""激进"），改用**描述性语言**说明立场特征（如"主张彻底废除现行制度""反对任何形式的妥协"）。

---

## Step 3 — 立场矩阵输出

输出格式如下：

```
## 主体列表

| 主体（规范名） | 别称 | 结构性角色 |
|---|---|---|
| [主体A] | ... | 信源主体 |
| [主体B] | ... | 受影响主体 |

## 立场矩阵

| 主体 | 问题定义 | 因果归因 | 道德评价 | 主张方案 | 证据来源 |
|---|---|---|---|---|---|
| [主体A] | ... | ... | ... | ... | [引述/文件] |
| [主体B] | ... | ... | ... | ... | [引述/文件] |

## 冲突点分析

### 冲突1：[议题名称]
- **冲突双方**：主体A vs 主体B
- **冲突层次**：事实争议 / 价值争议 / 利益争议（三选一或组合）
- **核心分歧**：...（一句话概括）
- **哈贝马斯有效性声明类型**：真实性主张 / 正确性主张 / 真诚性主张
```

---

## Step 4 — 冲突层次判断

传播学中区分三类冲突，分析时需准确定性，因为不同层次冲突的化解路径不同：

| 冲突层次 | 特征 | 示例 |
|---|---|---|
| **事实争议**（Factual Dispute） | 双方对"是什么"存在分歧，原则上可通过证据解决 | 数据真伪、事件经过 |
| **价值争议**（Value Dispute） | 双方对"应该怎样"存在规范性分歧，无法仅凭事实消解 | 自由与安全的优先级 |
| **利益争议**（Interest Conflict） | 双方的实质利益相冲突，立场背后是资源分配问题 | 土地权属、市场份额 |

> 引用哈贝马斯（Habermas）的沟通行动理论：真实的对话要求各方的**有效性声明**（validity claims）接受公开检验。分析中若发现某方以"声望/权威"替代论证，可标注为**策略性沟通**（strategic communication），区别于**沟通性行动**（communicative action）。

---

## Current Backend Contract

**读取（只读）：**
- `/workspace/projects/{project_identifier}/reports/{report_range}/state/normalized_task.json` → 提取顶层对象，传给 `normalized_task_json`
- `/workspace/projects/{project_identifier}/reports/{report_range}/state/evidence_cards.json` → 提取 `.result[*].evidence_id` 字符串列表，传给 `evidence_ids_json`

**写入：**
- `stance_conflict` 代理写入：`/workspace/projects/{project_identifier}/reports/{report_range}/state/actor_positions.json`
  ```json
  { "status": "ok", "result": [...actor 对象列表...] }
  ```
- `claim_actor_conflict` 代理写入：`/workspace/projects/{project_identifier}/reports/{report_range}/state/conflict_map.json`
  ```json
  { "status": "ok", "result": { "claim_nodes": [], "actor_positions": [], "conflict_edges": [], "resolution_states": [] } }
  ```

**空结果格式：**
```json
{ "status": "empty", "reason": "上游证据为空", "result": [], "skipped_due_to": ["upstream_empty"] }
```

## 约束与质量检查

完成输出后，逐项自检：

- [ ] 是否存在同一主体多种写法并列？→ 归并
- [ ] 是否存在用情绪词替代立场概括的情况？→ 替换为描述性语言
- [ ] 立场是否有证据支撑（引述、文件、行为记录）？→ 补充来源
- [ ] 冲突层次是否准确区分？→ 避免将价值争议误判为事实争议
- [ ] 是否混淆了代言方与被代言方的立场？→ 分别列出
- [ ] 中介主体（媒体/平台）的隐性框架是否被忽略？→ 补充分析

---

## 参考理论索引

| 理论 | 核心概念 | 适用场景 |
|---|---|---|
| Entman 框架理论（1993） | 问题定义、因果归因、道德评价、解决方案 | 媒体报道立场分析 |
| Habermas 沟通行动理论（1984） | 有效性声明、策略性沟通 vs 沟通性行动 | 识别伪对话与真对话 |
| Standpoint Theory（Hartsock / Collins） | 立场的社会位置性 | 分析边缘主体的视角为何被忽视 |
| 话语联盟理论（Hajer, 1995） | 共享叙事的主体聚合 | 政策领域多方博弈 |
| 辩证张力理论（Baxter & Montgomery） | 关系中不可消解的对立张力 | 组织内部长期冲突 |

