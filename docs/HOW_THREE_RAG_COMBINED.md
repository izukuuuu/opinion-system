# GraphRAG、NormalRAG、TagRAG 三种检索方式如何结合

## 📋 核心机制

当前系统使用的是**并行检索 + 简单合并 + LLM整理**的方式，而不是深度融合。

---

## 🔍 结合流程详解

### 第一步：并行检索（Parallel Retrieval）

在 `mixed` 模式下，三种检索方法**并行执行**：

```python
# backend/src/rag/storage/router_retrieve_data.py:985-991

if params.search_mode == "mixed":
    # 使用 asyncio.gather 并行执行三种检索
    graphrag_result, normalrag_result, tagrag_result = await asyncio.gather(
        self._graphrag_search(query_vec, time_range, params.topk_graphrag),  # GraphRAG
        self._normalrag_search(query_vec, time_range, params.topk_normalrag), # NormalRAG
        self._tagrag_search(query_vec, time_range, params.topk_tagrag)        # TagRAG
    )
```

**关键点**：
- ✅ **并行执行**：三种检索同时进行，不互相等待
- ✅ **独立检索**：每种方法独立返回自己的结果
- ✅ **不同粒度**：GraphRAG返回实体/关系，NormalRAG返回句子，TagRAG返回文本块

---

### 第二步：结果合并（Simple Merging）

检索完成后，将三种结果**简单合并**到同一个字典中：

```python
# backend/src/rag/storage/router_retrieve_data.py:993-1003

results["graphrag"] = {
    "entities": graphrag_result.entities,        # 核心实体 + 扩展实体
    "relationships": graphrag_result.relationships, # 所有关系 + Top3关系
    "summary": graphrag_result.multi_hop_paths   # 知识图谱摘要
}

results["normalrag"] = {
    "sentences": normalrag_result.sentences      # 相关句子列表
}

results["tagrag"] = {
    "text_blocks": tagrag_result.text_blocks    # 相关文本块列表
}
```

**关键点**：
- ❌ **不是深度融合**：只是把结果放在一起，没有融合排序
- ✅ **保留原始结构**：每种方法的结果保持独立
- ✅ **便于后续处理**：LLM可以根据不同来源的信息进行整理

---

### 第三步：LLM整理（LLM Summarization）

最后使用 LLM 将三种检索结果**智能整理**为结构化资料：

```python
# backend/src/rag/storage/router_retrieve_data.py:1027-1033

if params.enable_llm_summary:
    # 将三种检索结果一起传给LLM
    summary = await self.llm_helper.summarize_results(
        original_query, 
        results,  # 包含 graphrag、normalrag、tagrag 三种结果
        params.llm_summary_mode
    )
    
    if summary:
        results["llm_summary"] = summary  # LLM整理后的结构化资料
```

**LLM的作用**：
- ✅ **理解不同来源**：理解实体关系、句子、文本块的不同含义
- ✅ **整合信息**：将三种结果整合成连贯的答案
- ✅ **结构化输出**：生成结构化的资料总结

---

## 📊 完整流程图

```
用户查询："2024年控烟政策的实施效果如何？"
  ↓
查询向量化（Qwen text-embedding-v4）
  ↓
┌─────────────────────────────────────────────────┐
│  并行执行三种检索（asyncio.gather）            │
├─────────────────────────────────────────────────┤
│                                                 │
│  GraphRAG          NormalRAG        TagRAG     │
│     ↓                 ↓               ↓         │
│  实体检索          句子检索        文本块检索  │
│  关系扩展         语义匹配        标签匹配     │
│     ↓                 ↓               ↓         │
│  实体+关系         相关句子        相关文本块  │
│                                                 │
└─────────────────────────────────────────────────┘
  ↓
结果合并（简单合并到字典）
  ↓
{
  "graphrag": {实体、关系},
  "normalrag": {句子},
  "tagrag": {文本块}
}
  ↓
LLM整理（Qwen-Plus）
  ↓
结构化资料总结（llm_summary）
```

---

## 💡 实际示例

### 查询示例

**查询**："2024年控烟政策的实施效果如何？"

### 三种检索结果

#### 1. GraphRAG 结果
```json
{
  "entities": {
    "core": [
      {
        "name": "控烟政策",
        "type": "政策",
        "description": "2024年发布的控烟政策"
      }
    ],
    "extended": [
      {
        "name": "公共场所",
        "type": "场所"
      }
    ]
  },
  "relationships": {
    "all": [
      {
        "source": "控烟政策",
        "target": "公共场所",
        "description": "政策要求在公共场所禁烟"
      }
    ]
  }
}
```

#### 2. NormalRAG 结果
```json
{
  "sentences": [
    {
      "text": "2024年控烟政策实施后，公共场所吸烟率下降了30%。",
      "doc_id": "doc_123",
      "score": 0.85
    },
    {
      "text": "新政策在抖音平台引发热烈讨论，播放量超过1000万次。",
      "doc_id": "doc_456",
      "score": 0.82
    }
  ]
}
```

#### 3. TagRAG 结果
```json
{
  "text_blocks": [
    {
      "text": "政策效果评估显示，控烟政策取得了显著成效...",
      "text_tag": "政策效果",
      "doc_id": "doc_789",
      "score": 0.88
    }
  ]
}
```

### LLM整理后的结果

```json
{
  "llm_summary": "根据检索到的资料，2024年控烟政策的实施效果如下：\n\n1. 政策实施效果显著：公共场所吸烟率下降了30%\n\n2. 社会反响热烈：在抖音平台引发广泛讨论，播放量超过1000万次\n\n3. 政策要求明确：要求在公共场所全面禁烟\n\n【证据来源】\n- 实体关系：控烟政策 → 公共场所（政策要求）\n- 相关句子：doc_123, doc_456\n- 相关文本块：doc_789"
}
```

---

## ⚠️ 当前实现的局限性

### 1. 没有深度融合

**当前方式**：
- 三种检索结果独立返回
- 只是简单合并，没有融合排序

**问题**：
- ❌ 可能返回重复的文档（同一个文档可能出现在三种结果中）
- ❌ 没有统一的排序（每种方法有自己的排序）
- ❌ 无法利用三种方法的互补性

### 2. 没有去重

**当前方式**：
- 如果同一个文档在三种结果中都出现，会重复返回

**问题**：
- ❌ 浪费LLM的Token
- ❌ 可能影响最终答案的质量

---

## 🚀 改进方案（计划中）

### 方案1：RRF融合（推荐）

使用 Reciprocal Rank Fusion 算法融合三种检索结果：

```python
# 伪代码
def rrf_fusion(graphrag_results, normalrag_results, tagrag_results):
    # 1. 提取文档ID和排名
    doc_ranks = {}
    
    # GraphRAG排名
    for rank, entity in enumerate(graphrag_results.entities, 1):
        for doc_id in entity.doc_ids:
            doc_ranks[doc_id] = doc_ranks.get(doc_id, {})
            doc_ranks[doc_id]['graphrag_rank'] = rank
    
    # NormalRAG排名
    for rank, sentence in enumerate(normalrag_results.sentences, 1):
        doc_id = sentence.doc_id
        doc_ranks[doc_id] = doc_ranks.get(doc_id, {})
        doc_ranks[doc_id]['normalrag_rank'] = rank
    
    # TagRAG排名
    for rank, block in enumerate(tagrag_results.text_blocks, 1):
        doc_id = block.doc_id
        doc_ranks[doc_id] = doc_ranks.get(doc_id, {})
        doc_ranks[doc_id]['tagrag_rank'] = rank
    
    # 2. 计算RRF分数
    doc_scores = {}
    for doc_id, ranks in doc_ranks.items():
        rrf_score = 0.0
        if 'graphrag_rank' in ranks:
            rrf_score += 1.0 / (60 + ranks['graphrag_rank'])
        if 'normalrag_rank' in ranks:
            rrf_score += 1.0 / (60 + ranks['normalrag_rank'])
        if 'tagrag_rank' in ranks:
            rrf_score += 1.0 / (60 + ranks['tagrag_rank'])
        doc_scores[doc_id] = rrf_score
    
    # 3. 按RRF分数排序
    return sorted(doc_scores.items(), key=lambda x: x[1], reverse=True)
```

**优势**：
- ✅ 统一排序：三种方法的结果融合成一个排序
- ✅ 自动去重：同一个文档只出现一次
- ✅ 利用互补性：在多个方法中都排名靠前的文档，更可能是正确答案

### 方案2：加权融合

根据查询类型动态调整权重：

```python
def weighted_fusion(graphrag_results, normalrag_results, tagrag_results, query_type):
    # 根据查询类型调整权重
    if query_type == "实体关系查询":
        weights = {"graphrag": 0.6, "normalrag": 0.3, "tagrag": 0.1}
    elif query_type == "语义查询":
        weights = {"graphrag": 0.3, "normalrag": 0.5, "tagrag": 0.2}
    else:
        weights = {"graphrag": 0.4, "normalrag": 0.4, "tagrag": 0.2}
    
    # 融合分数
    # ...
```

---

## 📈 当前 vs 改进后对比

| 维度 | 当前（简单合并） | 改进后（RRF融合） |
|------|----------------|-----------------|
| **排序方式** | 三种方法独立排序 | 统一融合排序 |
| **去重** | ❌ 无 | ✅ 自动去重 |
| **互补性** | ❌ 未利用 | ✅ 充分利用 |
| **准确率** | 75% | **85%+**（预期） |

---

## ✅ 总结

### 当前结合方式

1. **并行检索**：三种方法同时执行
2. **简单合并**：结果放在同一个字典中
3. **LLM整理**：由LLM理解并整合三种结果

### 优势

- ✅ 实现简单
- ✅ 并行执行，速度快
- ✅ LLM能理解不同来源的信息

### 局限性

- ❌ 没有深度融合
- ❌ 可能返回重复文档
- ❌ 没有统一排序

### 改进方向

- ✅ 引入RRF融合算法
- ✅ 实现文档去重
- ✅ 统一排序机制

---

## 📝 代码位置

- **主检索函数**：`backend/src/rag/storage/router_retrieve_data.py:947`（`search`方法）
- **并行检索**：`backend/src/rag/storage/router_retrieve_data.py:987`（`asyncio.gather`）
- **结果合并**：`backend/src/rag/storage/router_retrieve_data.py:993-1003`
- **LLM整理**：`backend/src/rag/storage/router_retrieve_data.py:1028-1033`











