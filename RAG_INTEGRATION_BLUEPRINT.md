# RAG深度集成技术方案

## 一、项目概述

### 1.1 项目背景
当前舆情分析系统中，Explain（解读）和Report（报告）模块的结论生成主要依赖统计结果和人工经验，缺乏可追溯的客观依据。为解决这一问题，我们计划将RAG（检索增强生成）技术深度集成到"分析→解读→报告"全链路中，确保每个洞察都有据可查。

### 1.2 核心价值
- **提升结论可信度**：为分析观点提供原文证据支持
- **提高分析效率**：自动化信息检索与整合，减少人工查找时间
- **增强报告可追溯性**：建立完整的"观点-证据"映射关系
- **降低误判风险**：基于事实数据的客观分析，减少主观偏差

### 1.3 预期成果
- 构建完整的RAG增强分析流水线
- 实现可演示的智能问答功能
- 生成带证据链的标准化报告
- 建立RAG性能评估体系

## 二、系统现状与架构

### 2.1 现有技术能力概览

| 模块 | 功能描述 | 技术实现 | 输出产物 |
|------|----------|----------|----------|
| **项目管理** | 统一管理专题数据 | `ProjectManager`类 | `backend/data/projects/<topic>/`目录结构 |
| **数据获取** | 采集原始舆情数据 | `run_fetch`函数 | 原始数据文件 |
| **数据分析** | 基础统计分析 | `run_Analyze`调用各分析函数 | 结构化JSON结果 |
| **RAG向量化** | 构建检索索引 | TagRAG/Router向量化脚本 | LanceDB向量数据库 |
| **智能检索** | 多策略信息检索 | `AdvancedRAGSearcher`类 | 检索结果+LLM汇总 |
| **解读增强** | RAG增强解读生成 | `generate_rag_enhanced_explanation` | `*_rag_enhanced.json`文件 |
| **报告生成** | 文档自动生成 | `data_report.py`模块 | Word/PDF报告 |

### 2.2 核心RAG组件详解

#### 2.2.1 TagRAG系统
- **数据源**：`tagrag/format_db/<topic>.json`（结构化标签数据）
- **向量化**：使用千问`text-embedding-v4`模型生成向量
- **存储**：LanceDB向量数据库，表名通过拼音转换
- **检索器**：`tag_retrieve_data.Retriever`提供标签/段落级召回

#### 2.2.2 Router多路RAG系统
- **数据处理**：`router_vec_data.py`负责：
  - 实体抽取：识别文本中的人、事、物
  - 关系构建：建立实体间关联关系
  - 文本分块：将长文本切分为检索单元
- **向量存储**：生成四类向量表：
  - `graphrag_entities`（实体向量）
  - `graphrag_relationships`（关系向量）
  - `graphrag_texts`（文本块向量）
  - `normalrag`（常规句子向量）
- **智能检索器**：`AdvancedRAGSearcher`提供：
  - 时间智能过滤：自动识别时间约束
  - 多策略检索：支持Graph/Normal/Tag混合检索
  - LLM结果汇总：生成结构化`llm_summary`

### 2.3 当前数据流分析

```
原始数据 → 预处理 → 向量化 → 存储 → 检索 → 汇总 → 应用
    ↓        ↓        ↓       ↓       ↓       ↓       ↓
   Fetch → Clean → Vectorize → LanceDB → Search → LLM → Explain/Report
```

## 三、详细实施方案

### 3.1 阶段A：打通核心链路

#### 任务A1：开发RAG查询API
```python
# 实现位置：backend/server.py
@app.route('/api/projects/<topic>/rag_search', methods=['POST'])
def rag_search(topic):
    """
    智能检索接口
    参数：
        topic: 专题名称
        query: 查询语句
        mode: 检索模式（mixed/graphrag/normalrag/tagrag）
        topk_normal: NormalRAG返回数量
        topk_graph: GraphRAG返回数量
        llm_summary_mode: 汇总模式
    返回：
        {
            "status": "success",
            "search_results": { ... },
            "llm_summary": "汇总文本",
            "evidences": [{"doc_id": "...", "text": "...", "channel": "..."}]
        }
    """
```

#### 任务A2：前端集成
- 在现有分析界面添加"智能问答"模块
- 设计简洁的查询输入和结果展示界面
- 支持结果中证据来源的点击查看

#### 任务A3：独立RAG触发命令
```bash
# 新增CLI选项，支持不运行完整分析流程，直接进行RAG增强
python backend/main.py Explain --topic=控烟 --date=20240101 --func=volume --rag-only
```

### 3.2 阶段B：标准化输出与报告集成

#### 任务B1：统一输出格式规范
```json
{
  "version": "1.0",
  "generated_at": "2024-01-01 10:00:00",
  "topic": "控烟",
  "function": "volume",
  "points": [
    {
      "id": "point_001",
      "content": "抖音平台声量显著高于其他渠道",
      "confidence": 0.92,
      "evidences": [
        {
          "doc_id": "doc_12345",
          "text": "抖音相关话题播放量超过1000万次...",
          "channel": "抖音",
          "timestamp": "2023-12-25 14:30:00"
        }
      ]
    }
  ],
  "summary": "整体声量分析表明...",
  "metadata": {
    "rag_mode": "mixed",
    "search_params": { ... }
  }
}
```

#### 任务B2：报告自动引用生成
- 修改`data_report.py`，自动解析RAG增强文件
- 在报告中增加"证据引用"章节
- 支持点击引用跳转到原文

#### 任务B3：证据材料归档
- 生成独立的`rag_materials.json`文件
- 包含所有引用的原文片段
- 支持批量导出和下载

### 3.3 阶段C：评估优化与文档化

#### 任务C1：建立评估体系
```python
# 评估脚本框架
class RAGEvaluator:
    def evaluate(self, topic, query_file):
        """
        评估RAG性能
        指标：
        - Context Precision: 检索结果的相关性
        - Answer Relevancy: 答案与问题的相关度
        - Faithfulness: 答案与证据的一致性
        """
```

#### 任务C2：引入高级检索技术
- **Reranker重排序**：使用BGE-Reranker等模型提升精度
- **混合检索**：融合向量检索与关键词检索
- **查询重写**：优化复杂查询的检索效果

#### 任务C3：团队文档与SOP
- 编写《RAG系统操作手册》
- 建立最佳实践指南
- 创建故障排查文档

## 四、技术实现细节

### 4.1 核心类结构

```python
# AdvancedRAGSearcher 增强说明
class AdvancedRAGSearcher:
    def __init__(self, topic, config):
        self.topic = topic
        self.config = config
        self.llm_helper = LLMHelper()
        
    def search(self, query, params):
        # 1. 时间过滤处理
        time_filter = self._process_time_filter(query)
        
        # 2. 多路检索
        results = {}
        if params.mode in ['mixed', 'graphrag']:
            results['graphrag'] = self._graphrag_search(query, time_filter)
        if params.mode in ['mixed', 'normalrag']:
            results['normalrag'] = self._normalrag_search(query, time_filter)
        if params.mode in ['mixed', 'tagrag']:
            results['tagrag'] = self._tagrag_search(query, time_filter)
            
        # 3. LLM汇总
        summary = self.llm_helper.summarize_results(results, query)
        
        return {
            'raw_results': results,
            'llm_summary': summary,
            'evidences': self._extract_evidences(results)
        }
```

### 4.2 数据库Schema设计

```sql
-- GraphRAG实体表
CREATE TABLE graphrag_entities (
    id TEXT PRIMARY KEY,
    entity_name TEXT,
    entity_type TEXT,
    embedding VECTOR(1024),
    doc_id TEXT,
    created_at TIMESTAMP
);

-- 文本块表
CREATE TABLE graphrag_texts (
    id TEXT PRIMARY KEY,
    text_content TEXT,
    embedding VECTOR(1024),
    doc_id TEXT,
    channel TEXT,
    timestamp TIMESTAMP,
    tags JSON
);
```

## 五、风险评估与应对策略

### 5.1 技术风险

| 风险项 | 影响程度 | 概率 | 缓解措施 |
|--------|----------|------|----------|
| 向量数据库性能瓶颈 | 高 | 中 | 1. 定期索引优化<br>2. 分级存储策略<br>3. 查询缓存机制 |
| LLM API调用超时 | 中 | 高 | 1. 超时重试机制<br>2. 本地模型备选<br>3. 异步调用设计 |
| 数据不一致性 | 高 | 低 | 1. 数据版本控制<br>2. 完整性校验<br>3. 异常自动修复 |

### 5.2 业务风险

| 风险项 | 影响程度 | 概率 | 缓解措施 |
|--------|----------|------|----------|
| 分析师接受度低 | 中 | 中 | 1. 渐进式培训<br>2. 成功案例展示<br>3. 用户反馈闭环 |
| 报告格式不适应 | 低 | 高 | 1. 灵活模板配置<br>2. 自定义导出选项<br>3. 格式兼容转换 |

## 六、成功标准与验收指标

### 6.1 技术验收标准

| 指标 | 目标值 | 测量方法 |
|------|--------|----------|
| 检索响应时间 | < 3秒 | 性能测试脚本 |
| 检索准确率 | > 85% | 评估数据集 |
| 系统可用性 | > 99.5% | 监控系统记录 |
| 证据可追溯率 | 100% | 抽样检查 |

### 6.2 业务验收标准

| 指标 | 目标值 | 测量方法 |
|------|--------|----------|
| 分析师使用率 | > 70% | 系统日志分析 |
| 报告生成时间 | 减少30% | 任务耗时统计 |
| 用户满意度 | > 4.0/5.0 | 用户调研问卷 |
| 误判减少率 | > 20% | 历史对比分析 |

## 七、附录

### 附录A：技术术语对照表

| 术语 | 中文解释 | 业务含义 |
|------|----------|----------|
| RAG | 检索增强生成 | 先检索后生成的技术框架 |
| GraphRAG | 图检索增强生成 | 基于知识图谱的检索 |
| TagRAG | 标签检索增强生成 | 基于语义标签的检索 |
| LanceDB | 向量数据库 | 存储向量数据的专业数据库 |
| Embedding | 向量嵌入 | 将文本转换为数学向量的过程 |
| LLM | 大语言模型 | 能够理解和生成自然语言的AI模型 |

### 附录B：现有系统详细调用关系

```
# 完整分析流水线调用关系
main.py:run_pipeline()
    ├── run_fetch()  # 数据获取
    ├── run_Analyze()  # 基础分析
    │   ├── volume_analysis()
    │   ├── sentiment_analysis()
    │   └── keyword_analysis()
    ├── run_Explain()  # 解读生成
    │   ├── generate_base_explanation()
    │   └── generate_rag_enhanced_explanation()  # RAG增强
    │       ├── AdvancedRAGSearcher.search()
    │       └── LLMHelper.summarize()
    └── run_Report()  # 报告生成
        └── data_report.generate()
```

### 附录C：配置文件说明

```yaml
# backend/configs/llm.yaml 示例
rag:
  embedding_model: "text-embedding-v4"
  reranker_model: "bge-reranker-large"
  llm_model: "qwen-max"
  search:
    normal_topk: 10
    graph_topk: 5
    tag_topk: 8
    use_reranker: true
    rerank_topn: 3
```

### 附录D：部署与运维说明

1. **环境要求**
   - Python 3.9+
   - 至少16GB内存
   - GPU（可选，用于加速推理）

2. **部署步骤**
   ```bash
   # 1. 环境准备
   pip install -r requirements.txt
   
   # 2. 数据向量化
   python backend/main.py RouterVectorize --topic=控烟
   
   # 3. 服务启动
   python backend/server.py --port=8000
   ```

3. **监控建议**
   - 设置向量数据库大小监控
   - 配置LLM API调用频率告警
   - 定期备份RAG索引数据

### 附录E：常见问题与解决方案

| 问题 | 可能原因 | 解决方案 |
|------|----------|----------|
| 检索结果为空 | 未生成向量库 | 运行Vectorize命令 |
| 检索速度慢 | 索引未优化 | 重建向量索引 |
| 结果不准确 | 模型版本过旧 | 更新嵌入模型 |
| 内存占用高 | 数据量过大 | 启用分级存储 |