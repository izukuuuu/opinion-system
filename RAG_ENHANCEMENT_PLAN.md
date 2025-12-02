# RAG 增强与舆情分析集成优化方案

## 执行摘要

本方案旨在系统性地提升现有RAG（检索增强生成）模块的性能与可靠性，并将其深度集成至舆情分析业务流程中。当前，Explain（解读）与Report（报告）模块的洞察生成缺乏可追溯的客观依据，输出质量存在波动。通过构建评估体系、优化检索技术、规范输出格式，我们将打通“数据检索 → 业务解读 → 报告生成”的全链路，使分析结论更具可信度与可操作性，降低误判风险，提升团队效率。

## 1. 项目背景与目标

### 1.1 现状与挑战
当前系统已具备基础的RAG能力（GraphRAG, NormalRAG, TagRAG），但在实际业务应用中暴露出以下问题：
- **缺乏评估标准**：没有用于衡量检索结果质量的黄金数据集与评估脚本，优化方向不明确。
- **检索精度待提升**：未使用重排序（Reranker）与混合检索等技术，对复杂查询的命中率有提升空间。
- **输出不可追溯**：LLM生成的洞察未强制关联原文证据，导致报告中的观点缺乏可信支撑。
- **集成度不足**：RAG能力未在Explain、Report、Filter/Query等模块形成标准化、可观测的闭环。

### 1.2 核心目标
1.  **建立质量基线**：创建评估数据集与脚本，量化RAG各环节性能。
2.  **提升检索效果**：引入先进检索技术，显著提升关键信息的召回率与准确率。
3.  **确保输出可审计**：规范Prompt，使所有业务洞察都能关联回原始证据。
4.  **实现深度集成**：将优化后的RAG能力无缝嵌入现有舆情分析流水线，提升整体产品价值。

## 2. 现有架构概览

### 2.1 技术栈与核心组件

| 组件类型 | 实现位置 | 技术方案 | 核心功能 |
|---------|----------|----------|----------|
| **向量数据库** | `backend/src/utils/rag/*/vector_db/` | LanceDB | 存储各类向量数据，支持高效相似性检索 |
| **嵌入模型** | `backend/src/utils/rag/tagrag/tag_retrieve_data.py:130` | Qwen text-embedding-v4 | 将文本转换为1024维向量表示 |
| **TagRAG系统** | `backend/src/utils/rag/tagrag/` | 向量检索+拼音表名映射 | 基于语义标签的结构化检索 |
| **多策略RAG** | `backend/src/utils/rag/ragrouter/` | GraphRAG+NormalRAG+TagRAG | 实体关系图检索+句子向量检索+标签检索 |
| **智能检索器** | `backend/src/utils/rag/ragrouter/router_retrieve_data.py` | `AdvancedRAGSearcher` | 时间智能过滤+多路检索+LLM结果汇总 |
| **业务集成** | `backend/src/explain/functions/base.py:653` | `generate_rag_enhanced_explanation` | 二次RAG增强解读生成 |

### 2.2 数据准备流程
- **TagRAG向量化**：将专题的结构化标签数据（`tagrag/format_db/<topic>.json`）通过千问嵌入模型转换为向量，存储于LanceDB中。
  - 表名通过拼音转换（`to_pinyin`函数）解决中文命名问题
  - 支持标签向量（`tag_vec`）和文本向量（`text_vec`）双列检索
- **多路向量化**：通过`RouterVectorize`将原始项目数据加工为四套向量数据：
    - `graphrag_entities`（实体向量）- 识别文本中人、事、物
    - `graphrag_relationships`（关系向量）- 建立实体间关联
    - `graphrag_texts`（文本块向量）- 长文本切分后的检索单元
    - `normalrag`（常规句子向量）- 句子级别的语义检索

### 2.3 检索与业务应用

#### 2.3.1 智能检索系统 (`AdvancedRAGSearcher`)
- **时间智能过滤**：自动识别查询中的时间约束，精准匹配相关时段文档
- **多策略检索**：支持`mixed`/`graphrag`/`normalrag`/`tagrag`四种检索模式
- **可配置参数**：
  - `topk_graphrag`：实体检索数量（默认3个核心实体）
  - `topk_normalrag`：句子检索数量（默认5条）
  - `topk_tagrag`：标签检索数量（默认5条）
  - `llm_summary_mode`：`strict`（严格模式）/`supplement`（补充模式）
- **LLM结果汇总**：通过`llm_summary`字段提供结构化的检索材料整合

#### 2.3.2 业务集成点
- **Explain模块**（`backend/src/explain/runner.py:23`）：
  1. 各分析函数（volume/attitude/trends等）生成初步解读
  2. 调用`generate_rag_enhanced_explanation`进行RAG二次增强
  3. 基于检索到的证据材料生成深度解读（`*_rag_enhanced.json`）
- **Report模块**：解析RAG增强解读文件，自动生成带引用附录的Word/PDF报告

## 3. 核心优化方案

### 3.1 第一阶段：建立评估体系与质量基线
**目标**：改变"凭感觉优化"的现状，实现数据驱动的迭代。

#### 3.1.1 黄金标准集构建
- **数据源**：从历史专题的`analyze`与`explain`结果中精选典型案例
- **标注结构**：
  ```json
  {
    "query_id": "unique_id",
    "topic": "专题名称",
    "function": "volume|attitude|trends等",
    "query": "用户查询/分析问题",
    "golden_answer": "标准答案描述",
    "evidence_docs": ["doc_id_1", "doc_id_2"],
    "evidence_snippets": ["关键证据片段1", "关键证据片段2"],
    "difficulty": "easy|medium|hard",
    "created_by": "标注人员",
    "created_at": "2024-01-01"
  }
  ```
- **标注工具**：开发简单的标注界面（`frontend/src/views/admin/AnnotationView.vue`）
- **存储位置**：`backend/data/evaluation/golden_dataset.json`

#### 3.1.2 自动化评估框架
**目录结构**：
```
backend/src/utils/rag/eval/
├── __init__.py
├── evaluator.py          # 主评估器
├── metrics.py           # 评估指标计算
├── dataset_loader.py    # 数据集加载器
├── report_generator.py  # 报告生成器
└── configs/
    └── eval_config.yaml  # 评估配置
```

**核心评估指标**：
- **Context Precision**：检索结果的相关性（基于与golden答案的余弦相似度）
- **Answer Relevancy**：生成答案与查询的语义相关性
- **Faithfulness**：答案与检索证据的一致性（使用LLM判断）
- **Retrieval Recall**： golden证据文档的召回率
- **Response Time**：端到端响应时间

#### 3.1.3 评估报告系统
**报告位置**：`backend/logs/rag_eval/eval_report_YYYYMMDD_HHMMSS.json`
**报告内容**：
```json
{
  "eval_id": "unique_eval_id",
  "timestamp": "2024-01-01 10:00:00",
  "model_version": "v1.2.0",
  "dataset_stats": {
    "total_queries": 100,
    "by_difficulty": {"easy": 30, "medium": 50, "hard": 20},
    "by_function": {"volume": 20, "attitude": 20, "trends": 15, ...}
  },
  "overall_metrics": {
    "context_precision": 0.85,
    "answer_relevancy": 0.82,
    "faithfulness": 0.88,
    "retrieval_recall": 0.75,
    "avg_response_time": 2.3
  },
  "detailed_results": [
    {
      "query_id": "q001",
      "metrics": {...},
      "retrieved_docs": [...],
      "generated_answer": "...",
      "analysis": "检索到3/5个golden文档，答案质量良好"
    }
  ],
  "recommendations": [
    "提升hard难度查询的检索效果",
    "优化attitude分析的提示词模板"
  ]
}
```

#### 3.1.4 实施步骤
1. **Week 1**：
   - 设计标注规范和工具
   - 从3个核心专题标注50个查询案例
   - 完成评估框架基础代码

2. **Week 2**：
   - 完善评估指标计算逻辑
   - 生成首份基准评估报告
   - 建立持续评估流程

### 3.2 第二阶段：检索核心能力升级
**目标**：实质性提升信息检索的准确性与覆盖率。

#### 3.2.1 重排序模型集成
**技术选型**：
- **主模型**：BGE-Reranker-Large（`BAAI/bge-reranker-large`）
- **备选模型**：Cohere Rerank v3.5（商业方案，效果更佳）
- **部署方案**：本地部署 + API调用结合

**实现位置**：`backend/src/utils/rag/reranker/`
```python
# bge_reranker.py
class BGEReranker:
    def __init__(self, model_path: str, device: str = "cuda"):
        from FlagEmbedding import FlagReranker
        self.reranker = FlagReranker(model_path, use_fp16=True)

    def rerank(self, query: str, passages: List[str], top_k: int = 10) -> List[Dict]:
        scores = self.reranker.compute_score([[query, passage] for passage in passages])
        results = sorted(zip(passages, scores), key=lambda x: x[1], reverse=True)
        return [{"passage": passage, "score": score} for passage, score in results[:top_k]]
```

#### 3.2.2 混合检索实现
**目标**：结合向量检索的语义理解能力和BM25的关键词精确匹配能力

**核心实现**：
- 使用jieba分词构建中文BM25索引
- 采用Reciprocal Rank Fusion (RRF)算法融合向量检索和BM25结果
- 在`AdvancedRAGSearcher`中集成混合检索流程

#### 3.2.3 元数据增强与过滤
**扩展元数据字段**：
```python
class DocumentMetadata:
    channel: str           # 渠道（微信、微博、新闻等）
    sentiment: str         # 情感（正面、负面、中性）
    influence_score: float # 影响力评分
    topic_tags: List[str]  # 话题标签
    key_entities: List[str] # 关键实体
    publish_time: str      # 发布时间
    author_type: str       # 作者类型（KOL、官媒、个人等）
```

**智能过滤器**：支持按渠道、情感、影响力、时间范围等多维度过滤

#### 3.2.4 嵌入模型升级评估
**候选模型对比**：
| 模型 | 向量维度 | 中文支持 | 性能评分 | 部署复杂度 |
|------|----------|----------|----------|------------|
| text-embedding-v4 | 1024 | ★★★★★ | 8.5 | 低（现有） |
| BGE-M3 | 1024 | ★★★★★ | 9.2 | 中 |
| jina-embeddings-v3 | 1024 | ★★★★☆ | 9.0 | 中 |
| text-embedding-3-large | 3072 | ★★★★☆ | 9.1 | 低（API） |

#### 3.2.5 阶段实施计划
**Week 3**：重排序模型集成 + BM25索引构建
**Week 4**：混合检索算法实现 + 元数据增强
**Week 5**：嵌入模型评估 + 性能优化 + 集成测试

### 3.3 第三阶段：生成模块标准化与集成
**目标**：确保业务输出格式统一、证据可追溯，并提升用户体验。

#### 3.3.1 标准化输出格式规范

**增强解读文件结构**（`*_rag_enhanced.json`）：
```json
{
  "version": "2.0",
  "generated_at": "2024-01-01 10:00:00",
  "topic": "控烟",
  "function": "volume",
  "analysis_range": {
    "start_date": "2023-12-01",
    "end_date": "2023-12-31"
  },
  "model_config": {
    "rag_mode": "mixed",
    "embedding_model": "text-embedding-v4",
    "reranker_enabled": true
  },
  "insights": [
    {
      "id": "insight_001",
      "type": "key_finding",
      "content": "抖音平台声量显著高于其他渠道，主要集中在政策讨论相关内容",
      "confidence": 0.92,
      "impact_level": "high",
      "evidence_chain": [
        {
          "doc_id": "doc_12345",
          "text": "抖音相关话题播放量超过1000万次，用户讨论热烈...",
          "channel": "抖音",
          "timestamp": "2023-12-25 14:30:00",
          "relevance_score": 0.89,
          "sentiment": "neutral",
          "key_entities": ["抖音", "政策", "控烟"]
        },
        {
          "doc_id": "doc_12348",
          "text": "短视频平台成为政策宣传的重要渠道...",
          "channel": "微博",
          "timestamp": "2023-12-26 09:15:00",
          "relevance_score": 0.85,
          "sentiment": "positive",
          "key_entities": ["短视频", "政策宣传"]
        }
      ],
      "supporting_data": {
        "volume_stats": {
          "douyin": 1500000,
          "weibo": 450000,
          "wechat": 320000
        }
      }
    }
  ],
  "summary": "整体声量分析表明抖音平台主导了政策相关讨论...",
  "methodology": {
    "retrieval_strategy": "mixed",
    "total_candidates_retrieved": 50,
    "after_reranking": 8,
    "llm_summary_mode": "supplement"
  }
}
```

**Prompt模板标准化**（`configs/prompt/explain_rag/结构化输出.yaml`）：
```yaml
prompts:
  rag_explain:
    system: |
      你是专业的舆情分析专家。基于提供的分析数据和RAG检索材料，生成深度解读。

      输出要求：
      1. 每个洞察必须包含具体的证据支持
      2. 证据必须包含文档ID、原文片段、来源渠道
      3. 提供置信度评估（0-1）
      4. 标注影响程度（high/medium/low）

      输出格式：
      {
        "insights": [
          {
            "id": "insight_XXX",
            "content": "具体洞察内容",
            "confidence": 0.85,
            "impact_level": "high",
            "evidence_chain": [...]
          }
        ]
      }

    user: |
      初步分析结果：{first_explanation}

      RAG检索材料：{rag_materials}

      原始分析数据：{analysis_data}

      请基于上述信息生成结构化解读，确保每个结论都有证据支持。
```

#### 3.3.2 报告生成系统增强

**新增组件**：`backend/src/report/evidence_citation.py`
```python
class EvidenceCitationGenerator:
    def __init__(self):
        self.citation_style = "APA"  # 可配置引用格式

    def generate_citation_section(self, enhanced_explanations: List[Dict]) -> Dict:
        """生成引用附录"""
        citations = []
        evidence_map = {}

        # 收集所有证据
        for explanation in enhanced_explanations:
            for insight in explanation.get('insights', []):
                for evidence in insight.get('evidence_chain', []):
                    doc_id = evidence['doc_id']
                    if doc_id not in evidence_map:
                        evidence_map[doc_id] = {
                            'doc_id': doc_id,
                            'text': evidence['text'],
                            'channel': evidence['channel'],
                            'timestamp': evidence['timestamp'],
                            'referenced_by': []
                        }
                    evidence_map[doc_id]['referenced_by'].append({
                        'insight_id': insight['id'],
                        'content_snippet': insight['content'][:100]
                    })

        # 生成引用列表
        for doc_id, evidence in evidence_map.items():
            citations.append({
                'citation_id': f"[{doc_id}]",
                'source': f"{evidence['channel']} - {evidence['timestamp']}",
                'content': evidence['text'][:200] + "..." if len(evidence['text']) > 200 else evidence['text'],
                'referenced_insights': len(evidence['referenced_by'])
            })

        return {
            "total_evidence": len(citations),
            "citations": citations,
            "evidence_index": evidence_map
        }

    def embed_citations_in_content(self, content: str, evidence_chain: List[Dict]) -> str:
        """在正文中嵌入引用标记"""
        for i, evidence in enumerate(evidence_chain):
            citation_marker = f"[{evidence['doc_id']}]"
            # 智能插入引用标记，避免破坏语句流畅性
            content = self._smart_insert_citation(content, citation_marker, i)
        return content
```

**报告模板更新**（`backend/src/report/templates/分析报告模板.docx`）：
- 新增"证据引用附录"章节
- 在正文中添加超链接，点击可跳转到对应证据
- 支持证据的展开/折叠显示

#### 3.3.3 可观测性与监控系统

**RAG状态监控API**（`backend/server.py`新增）：
```python
@app.route('/api/rag/status', methods=['GET'])
def rag_status():
    """获取RAG系统状态"""
    try:
        status_data = {
            "system_health": "healthy",
            "vector_databases": {},
            "model_status": {},
            "performance_metrics": {},
            "active_topics": []
        }

        # 检查各专题向量库状态
        for topic in get_all_topics():
            db_status = check_vector_db_status(topic)
            status_data["vector_databases"][topic] = {
                "status": db_status["status"],
                "document_count": db_status["doc_count"],
                "last_updated": db_status["last_updated"],
                "size_mb": db_status["size_mb"]
            }

            if db_status["status"] == "active":
                status_data["active_topics"].append(topic)

        # 模型状态检查
        status_data["model_status"] = {
            "embedding_model": check_model_health("text-embedding-v4"),
            "reranker": check_model_health("bge-reranker"),
            "llm": check_model_health("qwen-plus")
        }

        # 性能指标
        status_data["performance_metrics"] = {
            "avg_search_time": get_avg_search_time(),
            "success_rate": get_success_rate(),
            "daily_requests": get_daily_request_count()
        }

        return jsonify({"status": "success", "data": status_data})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/rag/metrics', methods=['GET'])
def rag_metrics():
    """获取RAG性能指标详情"""
    return jsonify(get_detailed_metrics())
```

**统一日志格式**（`backend/src/utils/logging/rag_logger.py`）：
```python
class RAGLogger:
    def __init__(self, component: str):
        self.component = component
        self.logger = setup_logger(f"RAG_{component}", "rag")

    def log_search_request(self, topic: str, query: str, params: Dict):
        """记录检索请求"""
        self.logger.info(json.dumps({
            "event_type": "search_request",
            "component": self.component,
            "topic": topic,
            "query_hash": hashlib.md5(query.encode()).hexdigest()[:8],
            "params": params,
            "timestamp": datetime.now().isoformat()
        }))

    def log_search_result(self, request_id: str, results: List[Dict], duration: float):
        """记录检索结果"""
        self.logger.info(json.dumps({
            "event_type": "search_result",
            "request_id": request_id,
            "result_count": len(results),
            "duration_ms": duration * 1000,
            "top_score": results[0].get('similarity', 0) if results else 0,
            "timestamp": datetime.now().isoformat()
        }))
```

**通知机制**（`backend/src/utils/rag/notifications.py`）：
```python
class RAGNotificationSystem:
    def __init__(self):
        self.channels = ["webhook", "email", "slack"]

    def notify_vectorization_complete(self, topic: str, stats: Dict):
        """向量化完成通知"""
        message = f"专题 {topic} 向量化完成\n文档数量：{stats['doc_count']}\n耗时：{stats['duration']}"
        self._send_notification("vectorization_complete", message, {"topic": topic})

    def notify_performance_degradation(self, metric: str, current_value: float, threshold: float):
        """性能下降告警"""
        message = f"RAG性能告警：{metric} 当前值 {current_value} 低于阈值 {threshold}"
        self._send_notification("performance_alert", message, {"metric": metric})
```

#### 3.3.4 阶段实施计划
**Week 6**：输出格式标准化 + Prompt模板优化
**Week 7**：报告生成增强 + 引用系统实现
**Week 8**：监控系统开发 + 通知机制集成 + 文档完善

## 4. 业务集成与价值体现

### 4.1 TagRAG：舆情“特征放大器”
- **价值**：将非结构化文本转化为“事件类型”、“风险等级”、“参与主体”等语义标签，实现基于特征的智能筛选与案例召回。
- **业务场景**：
    - 在分析某产品投诉事件时，快速召回历史上所有“同类产品投诉”案例，供对比分析。
    - 在初筛阶段，过滤掉与“政策发布”无关的噪音信息，让分析师聚焦于“企业危机”类内容。
- **预期成效**：将人工筛选工作量降低30%-50%，高风险舆情漏报率低于10%。

### 4.2 GraphRAG：舆情“关系透视镜”
- **价值**：自动构建“人物-事件-话题”关系图谱，揭示传播路径与关键影响者。
- **业务场景**：
    - 自动识别在负面事件中频繁出现、关联度高的账号或媒体，作为关键传播节点上报。
    - 在趋势分析中，明确指出声量峰值是由图谱中的哪个具体子事件引爆。
- **预期成效**：系统自动识别的关键影响者与人工判断重合度达70%以上，传播路径分析报告的自动化生成率达80%。

### 4.3 对现有分析功能的增强
- **声量分析 (`volume`)**：不仅报告“声量高”，更能通过GraphRAG解释是“哪个子事件”导致声量攀升。
- **情感分析 (`attitude`)**：结合TagRAG标签，区分是“产品质量”引发的负面情绪，还是“售后服务”引发的不满。
- **趋势分析 (`trends`)**：利用事件图谱，清晰展示话题演变链条，而不仅仅是时间序列上的波动。

## 5. 实施路线图与成功标准

| 阶段 | 时间 | 主要交付物 | 成功标准 |
| :--- | :--- | :--- | :--- |
| **第一阶段** | 第1-2周 | 1. 黄金评估数据集<br>2. 自动化评估脚本<br>3. 首份性能基准报告 | 1. 覆盖至少3个专题的5个功能<br>2. 团队可自行运行评估并解读报告 |
| **第二阶段** | 第3-5周 | 1. Reranker集成代码<br>2. 混合检索验证结果<br>3. 元数据字段扩展 | 1. 在评估集上，答案相关性指标提升10%<br>2. 关键词检索召回率显著改善 |
| **第三阶段** | 第6-7周 | 1. 标准化Prompt模板<br>2. 带证据追溯的报告样例<br>3. 系统状态监控API | 1. 所有RAG增强解读均包含证据ID<br>2. 报告可自动生成引用附录<br>3. 运维可通过API查看系统健康度 |
| **收尾与文档** | 第8周 | 1. 完整的项目文档 (`backend/docs/rag.md`)<br>2. 团队培训与SOP | 1. 文档清晰，新成员可据此维护RAG模块<br>2. 优化流程纳入常规开发周期 |

## 6. 资源与风险

- **所需资源**：需要算法工程师重点投入检索优化与评估体系建设；需要标注人员协助构建黄金数据集；需关注GPU资源（用于Reranker等模型）。
- **潜在风险**：
    - 新引入的Reranker模型可能增加单次检索延迟，需通过缓存、异步等方式优化。
    - 向量数据库随数据量增长，需制定存储扩容与归档策略。
- **应对措施**：采用分阶段上线、A/B测试对比效果、建立性能监控告警机制。

## 7. 技术实施详细方案

### 7.1 核心代码修改清单

#### 7.1.1 现有代码增强点

**1. AdvancedRAGSearcher性能优化**（`router_retrieve_data.py`）
```python
# 需要修改的方法
class AdvancedRAGSearcher:
    async def search(self, params: SearchParams) -> Dict:
        # 添加并行检索支持
        # 集成重排序逻辑
        # 增强错误处理
        # 添加性能监控
        pass

    def _apply_reranking(self, query: str, candidates: List[Dict]) -> List[Dict]:
        # 新增：重排序逻辑
        pass

    def _hybrid_search(self, query: str, params: SearchParams) -> List[Dict]:
        # 新增：混合检索（向量+BM25）
        pass

    def _metadata_filter(self, results: List[Dict], filters: Dict) -> List[Dict]:
        # 新增：元数据过滤
        pass
```

**2. ExplainBase功能扩展**（`explain/functions/base.py:653`）
```python
# 需要增强的方法
class ExplainBase:
    async def generate_rag_enhanced_explanation(
        self, func_name: str, first_explanation: Dict,
        data: Dict, target: str, channel_name: str = None
    ) -> Optional[Dict]:
        # 添加证据链追踪
        # 增强输出格式
        # 添加置信度评估
        # 集成重排序结果
        pass

    def _format_enhanced_output(
        self, insights: List[Dict], evidence_chain: List[Dict]
    ) -> Dict:
        # 新增：标准化输出格式
        pass
```

#### 7.1.2 新增代码模块

**1. 评估框架**（`backend/src/utils/rag/eval/`）
```
backend/src/utils/rag/eval/
├── __init__.py
├── evaluator.py          # 主评估器
├── metrics.py           # 评估指标实现
├── dataset_loader.py    # 黄金数据集加载
├── visualization.py     # 评估结果可视化
└── configs/
    └── eval_config.yaml  # 评估配置
```

**2. 重排序系统**（`backend/src/utils/rag/reranker/`）
```
backend/src/utils/rag/reranker/
├── __init__.py
├── bge_reranker.py      # BGE重排序实现
├── cohere_reranker.py   # Cohere重排序实现
├── base_interface.py    # 统一接口定义
└── model_loader.py      # 模型加载器
```

**3. 监控系统**（`backend/src/monitoring/`）
```
backend/src/monitoring/
├── __init__.py
├── rag_monitor.py       # RAG性能监控
├── metrics_collector.py # 指标收集器
├── alerting.py          # 告警系统
└── dashboard.py         # 监控面板
```

### 7.2 配置文件扩展

#### 7.2.1 RAG配置增强（`configs/llm.yaml`）
```yaml
rag:
  # 现有配置
  embedding_model: "text-embedding-v4"
  llm_model: "qwen-max"

  # 新增配置
  reranker:
    enabled: true
    model: "BAAI/bge-reranker-large"
    device: "cuda"
    top_k: 5
    threshold: 0.5

  hybrid_search:
    enabled: true
    bm25_weight: 0.3
    vector_weight: 0.7
    fusion_method: "rrf"  # rrf, weighted_avg, rank_fusion

  metadata:
    enabled: true
    fields: ["channel", "sentiment", "influence_score", "publish_time"]

  performance:
    cache_enabled: true
    cache_ttl: 3600
    batch_size: 32
    max_concurrent: 10

evaluation:
  dataset_path: "backend/data/evaluation/golden_dataset.json"
  metrics: ["context_precision", "answer_relevancy", "faithfulness", "retrieval_recall"]
  report_path: "backend/logs/rag_eval/"
  auto_schedule: "0 2 * * 1"  # 每周一凌晨2点自动评估

monitoring:
  enabled: true
  alert_thresholds:
    avg_response_time: 3.0  # 秒
    success_rate: 0.95      # 95%
    memory_usage: 0.8       # 80%
  notification_channels: ["webhook", "email"]
```

### 7.3 API接口设计

#### 7.3.1 RAG查询接口增强
```python
# backend/server.py 新增接口

@app.route('/api/projects/<topic>/rag_search', methods=['POST'])
@validate_rag_request
async def rag_search(topic: str):
    """
    智能检索接口
    支持重排序、混合检索、元数据过滤
    """
    pass

@app.route('/api/rag/status', methods=['GET'])
def rag_status():
    """获取RAG系统状态和性能指标"""
    pass
```

### 7.4 前端界面增强

#### 7.4.1 RAG管理界面（`frontend/src/views/rag/RagManagementView.vue`）
```vue
<template>
  <div class="rag-management">
    <!-- 向量库状态监控 -->
    <VectorDBStatus :topics="topics" />

    <!-- 智能搜索测试 -->
    <RAGSearchTest @search="handleSearch" />

    <!-- 评估结果展示 -->
    <EvaluationDashboard :metrics="evaluationMetrics" />

    <!-- 配置管理 -->
    <RAGConfiguration :config="ragConfig" @update="updateConfig" />
  </div>
</template>
```

## 8. 结论与建议

### 8.1 方案总结
本方案遵循"先测量，后优化"的原则，通过系统性的三步走策略，旨在将RAG从一项实验性技术转化为支撑舆情分析核心业务流程的可靠基础设施。

### 8.2 核心优势
1. **技术先进性**：集成最新的重排序、混合检索技术
2. **评估驱动**：建立完整的评估体系，确保优化方向正确
3. **业务深度集成**：与现有分析流程无缝结合
4. **可观测性**：完善的监控和告警机制
5. **标准化输出**：统一的证据追溯格式

### 8.3 实施建议
**立即启动第一阶段工作**：
- 快速建立客观的质量评估基线
- 为后续的技术选型与优化决策提供坚实依据
- 预计2周内可完成初步评估框架

**资源需求**：
- 算法工程师：1-2人，重点投入检索优化
- 标注人员：1人，协助构建黄金数据集
- GPU资源：用于重排序模型训练和推理

**预期成果**：
- 整个计划在2个月内完成
- 分析可靠性提升30%以上
- 人工筛选工作量降低40%-60%
- 高风险舆情漏报率低于10%

**风险管控**：
- 采用分阶段上线策略
- 建立A/B测试对比机制
- 设置性能监控告警
- 准备回滚方案

---

**附件**：
- [现有RAG模块核心代码路径说明]
- [初步评估数据集构建指南]
- [Reranker模型性能对比测试计划]
- [监控系统部署指南]
- [前端界面原型设计]