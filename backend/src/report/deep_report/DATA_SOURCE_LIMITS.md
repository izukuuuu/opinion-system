# 数据源字段与报告模块依赖

## 状态标记

- ✅ 可直接实现
- ⚠️ 需推断/降级实现
- ❌ 数据源缺失，无法实现

---

## 字段可用性原则

系统采用**动态字段检测**，不硬编码数据源类型。所有字段提取遵循：

```python
# 运行时动态检查，优先中文字段名，fallback英文字段名
value = row.get("点赞数") or row.get("like_count") or row.get("likes") or None
```

**核心原则**：
- 不假设数据来自"NetInsight"或"Project"
- 每条记录独立检查字段存在性
- 有字段则使用，无字段则留空/默认值
- 不在输出中区分数据源类型

---

## 可用字段清单（动态检测）

| 字段 | 检测路径 | 默认值 | 备注 |
|------|----------|--------|------|
| `点赞数`/`likes` | `row.get("点赞数") or row.get("like_count") or row.get("likes")` | 0 | 互动数据，无则留空 |
| `评论数`/`comments` | `row.get("评论数") or row.get("comment_count") or row.get("comments")` | 0 | 互动数据 |
| `转发数`/`shares` | `row.get("转发数") or row.get("share_count") or row.get("shares") or row.get("转发")` | 0 | 互动数据 |
| `播放量`/`views` | `row.get("播放量") or row.get("view_count") or row.get("views") or row.get("阅读量")` | 0 | 浏览数据 |
| `情感`/`sentiment` | `row.get("情感") or row.get("sentiment") or row.get("sentiment_label") or row.get("polarity")` | "" | 情感标签 |
| `热度`/`hotness` | `row.get("热度") or row.get("hotness_score")` → fallback 到 `relevance` | 0 | 热度评分 |
| `title` | `row.get("title")` | "" | 必有 |
| `contents` | `row.get("contents")` | "" | 内容 |
| `platform` | `row.get("platform")` | "" | 平台 |
| `author` | `row.get("author")` | "" | 作者 |
| `published_at` | `row.get("published_at") or row.get("publish_time") or row.get("date")` | "" | 时间 |

---

## 基础字段（几乎必有）

| 字段 | 示例值 | 状态 | 备注 |
|------|--------|------|------|
| `id` | 202603065552 | ✅ | 直接作为 source_id |
| `title` | "发布了头条文章..." | ✅ | 用于标题、snippet 截取 |
| `contents` | 同 title | ✅ | 用于内容分析 |
| `platform` | "微博" | ✅ | 平台统计、跨平台分析 |
| `author` | "人神共奋的李刚" | ✅ | actor推断来源 |
| `published_at` | "2025-09-02T20:47:00.000" | ✅ | 时间线构建核心字段 |
| `url` | https://weibo.com/... | ✅ | 引用链接 |
| `region` | "上海市" | ⚠️ | 地域分布（非核心） |
| `hit_words` | "控烟" | ✅ | 关键词提取来源 |
| `polarity` | "正面"/"中性"/"负面" | ⚠️ | stance_hint 推断辅助，部分数据源有 `情感` 字段更精确 |
| `classification` | "未筛选" | ⚠️ | 价值较低 |

---

## 计算字段（非原始数据）

| 字段 | 计算方式 | 备注 |
|------|----------|------|
| `hotness_score` | 优先 `row.get("热度")`，无则 fallback 到检索相关性 `relevance` | 非原始数据，动态计算 |
| `time_label` | 格式化 `published_at` 为 `%Y-%m-%d %H:%M` | 用于引用时的时间标注 |
| `stance_hint` | 基于 title/snippet 关键词推断 | `_STANCE_REFUTE_HINTS` 等关键词匹配 |
| `confidence` | `min(1.0, max(0.05, relevance / 10.0))` | 从相关性得分派生 |

---

## 各模块实现状态

### mechanism_summary 模块

| 输出字段 | 状态 | 实现方式 |
|----------|------|----------|
| `amplification_paths` | ⚠️ 动态 | 有 engagement 数据时识别放大节点，无则只用 platform_sequence |
| `trigger_events` | ✅ | 从 timeline_nodes 构建 |
| `phase_shifts` | ✅ | 从 published_at 时间密度变化计算 |
| `cross_platform_bridges` | ⚠️ 降级 | 无 event_id，用时间窗口+标题相似度推断 |
| `bridge_nodes` | ⚠️ 动态 | 有 engagement 可识别关键转发节点，无则降级 |
| `cause_candidates` | ✅ | 从标题关键词推断 |
| `narrative_carriers` | ⚠️ 动态 | 有 engagement 可计算，无则输出空数组 |
| `refutation_lags` | ⚠️ 降级 | 用"辟谣"关键词识别，精度有限 |

### risk_signals 模块

| 检测类型 | 状态 | 实现方式 |
|----------|------|----------|
| `rumor_conflict` | ✅ | 基于 `contradiction_signal >= 0.7`（关键词推断） |
| `platform_concentration` | ✅ | 基于 platform 计数统计 |
| `attention_watch` | ✅ | 基于证据卡数量 |

### event_analysis 模块

| 输出字段 | 状态 | 实现方式 |
|----------|------|----------|
| `event_trigger` | ✅ | 从 timeline + evidence_cards 提取首发信源 |
| `discussion_evolution` | ✅ | 从 timeline_nodes 按时间分段 |
| `actor_distribution` | ✅ | 从 actor_positions + evidence_cards |
| `platform_analysis` | ⚠️ 动态 | 有 sentiment 字段可统计情感分布，无则从 polarity 推断 |
| `keywords` | ✅ | 从 evidence_cards.keywords + hit_words |
| `sentiment_summary` | ⚠️ 动态 | 有 `情感` 字段直接统计，无则从 polarity 推断 |

---

## AI 输出行为约束

**原则**：当数据不足以支撑某分析时，工具输出应：
1. 输出空数组/空对象（而非抛错或警告）
2. 不在 `error_hint` 中写"缺少xx数据需警惕"
3. 在 `readiness_flags` 中标记对应状态（如 `narrative_carriers_disabled`）

**禁止行为**：
- ❌ 输出"缺少互动数据，无法识别叙事载体，请补充数据"
- ❌ 输出"数据源不完整，风险分析可信度降低"
- ❌ 在 prose 中写"因数据缺失，以下分析仅供参考"

**正确行为**：
- ✅ `narrative_carriers: []` + `readiness_flags: ["narrative_carriers_disabled"]`
- ✅ 简短或跳过相关章节，不强调数据问题

---

## 数据管道修复记录

### 2026-04-14: Engagement字段动态传递

**问题**: 原始数据行可能包含 `点赞数`、`评论数`、`转发数`、`情感` 等字段，但 `evidence_retriever.py` 的 `_retrieve_candidates` 函数在构建候选时只传递了 `title`、`snippet`、`url` 等有限字段，导致存在的互动数据在管道中途丢失。

**修复**:
1. `evidence_retriever.py:740-775` - 运行时动态提取 `engagement_likes`、`engagement_comments`、`engagement_shares`、`engagement_views`、`sentiment_raw`、`hotness_raw`（有则传递，无则 None）
2. `payloads.py:1265-1299` - `_map_item_to_card` 优先读取传递的字段，fallback 到原始字段名

**效果**: 有 engagement 数据的记录现可完整流入 evidence_cards，支持：
- 具体引用时标注互动数据（如"点赞数：1234"）
- 识别高互动节点作为放大节点
- 情感分布统计

**注意**: 不假设数据源类型，每条记录独立检测字段存在性。

---

## 后续数据源改进建议

如需完整实现传播分析能力，建议在数据采集阶段补充：

1. **互动指标**：`likes`、`shares`、`comments`、`views`（或中文名 `点赞数`、`评论数`、`转发数`）
2. **账号类型**：`author_type` (official/media/personal/org)
3. **事件标签**：`event_cluster_id` 或 `topic_hash` 用于跨平台关联
4. **转发链**：`parent_post_id` 用于构建传播树
5. **情感标签**：`情感` 或 `sentiment` 字段（比 polarity 更精确）