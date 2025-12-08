# BERTopic 数据流集成方案文档

## 概述

本文档描述了BERTopic主题分析模块与现有数据流集成的改造方案，使其能够从远程数据库获取数据，而不是简单地读取本地文件。

## 一、改造目标

1. **复用Fetch流程**：使用与基础分析相同的fetch机制从远程数据库获取数据
2. **缓存机制**：支持fetch缓存，避免重复拉取数据
3. **统一接口**：前端调用方式与基础分析保持一致的用户体验
4. **独立存储层**：保持topic作为一个独立的分析层，结果存储在`data/topic/`下

## 二、架构设计

### 2.1 数据流程图

```
远程数据库 → Fetch API → 本地缓存(fetch目录) → BERTopic分析 → 结果存储(topic目录) → 前端展示
```

### 2.2 目录结构

```
backend/data/projects/{专题}/
├── fetch/                          # 数据缓存（与基础分析共享）
│   ├── {开始日期}_{结束日期}/       # 按日期范围分桶
│   │   ├── 总体.jsonl             # 合并后的所有数据
│   │   ├── weibo.jsonl            # 各渠道数据
│   │   ├── wechat.jsonl
│   │   └── ...
└── topic/                          # BERTopic分析结果
    └── {开始日期}_{结束日期}/       # 与fetch目录日期范围对应
        ├── 1主题统计结果.json      # 主题统计
        ├── 2主题关键词.json         # 主题关键词
        ├── 3文档2D坐标.json         # 文档坐标（可视化）
        ├── 4大模型再聚类结果.json    # AI聚类结果
        └── 5大模型主题关键词.json     # AI生成关键词
```

## 三、后端改造

### 3.1 新增核心文件

1. **`backend/src/topic/data_bertopic_qwen_v2.py`**
   - 集成了fetch流程的新BERTopic实现
   - 自动检查缓存，如不存在则触发fetch
   - 处理JSONL格式的数据输入
   - 保持原有的分析逻辑和输出格式

2. **主要改动**
   ```python
   # 自动确保数据可用
   def _ensure_fetch_data(topic: str, start_date: str, end_date: str, logger) -> bool:
       # 检查缓存
       if fetch_dir.exists() and (fetch_dir / "总体.jsonl").exists():
           return True

       # 检查数据可用性
       avail_start, avail_end = get_topic_available_date_range(topic)

       # 执行fetch
       success = fetch_range(topic, start_date, end_date, output_date, logger)
       return success
   ```

### 3.2 API接口改造

#### 1. 运行BERTopic分析
```http
POST /api/analysis/topic/bertopic/run
```

**请求体：**
```json
{
  "topic": "专题名称",
  "start_date": "2024-01-01",
  "end_date": "2024-01-31",
  "fetch_dir": "",        // 可选：自定义fetch目录
  "userdict": "",         // 可选：自定义词典
  "stopwords": ""         // 可选：自定义停用词
}
```

**响应：**
```json
{
  "status": "ok",
  "operation": "topic-bertopic",
  "data": {
    "topic": "专题名称",
    "start_date": "2024-01-01",
    "end_date": "2024-01-31",
    "folder": "20240101_20240131",
    "message": "BERTopic分析完成，结果已保存"
  }
}
```

#### 2. 获取专题列表（新增数据源检查）
```http
GET /api/analysis/topic/bertopic/topics?only_with_data=true
```

**查询参数：**
- `only_with_results`: 只返回有BERTopic结果的专题
- `only_with_data`: 只返回有可用数据的专题（新增）

**响应：**
```json
{
  "status": "ok",
  "data": {
    "topics": [
      {
        "bucket": "专题名称",
        "name": "专题名称",
        "display_name": "显示名称",
        "has_bertopic_results": false,
        "source": "database"  // "database"或"local"
      }
    ],
    "source": "database"  // 数据来源
  }
}
```

#### 3. 检查数据可用性（新增）
```http
GET /api/analysis/topic/bertopic/availability?topic=专题名称
```

**响应：**
```json
{
  "status": "ok",
  "data": {
    "topic": "专题名称",
    "topic_identifier": "专题标识",
    "database_range": {
      "start": "2024-01-01",
      "end": "2024-12-31"
    },
    "local_caches": [
      {
        "folder": "20240101_20240131",
        "start": "20240101",
        "end": "20240131",
        "has_data": true,
        "path": "projects/专题/fetch/20240101_20240131"
      }
    ],
    "has_cache": true
  }
}
```

## 四、前端改造

### 4.1 新增Composable

**`frontend/src/composables/useTopicBertopicAnalysisV2.js`**
- 复用与基础分析相似的状态管理模式
- 自动加载数据可用性
- 集成日志显示
- 支持缓存提示

### 4.2 页面改造要点

1. **专题选择**
   - 从远程数据库获取专题列表
   - 默认只显示有数据的专题
   - 支持刷新功能

2. **日期选择**
   - 自动检查数据可用范围
   - 显示数据可用性提示
   - 自动填充最近的缓存范围

3. **执行流程**
   - 自动触发fetch（如需要）
   - 实时显示执行日志
   - 支持进度追踪

4. **结果展示**
   - 保持原有的结果展示方式
   - 显示文件生成位置
   - 支持查看历史记录

## 五、关键改动说明

### 5.1 数据格式处理

新实现读取JSONL格式而非CSV：
```python
# 优先读取总体.jsonl
overall_file = fetch_dir / "总体.jsonl"
df = read_jsonl(overall_file)

# 确保有contents字段
if 'content' in df.columns:
    df = df.rename(columns={'content': 'contents'})
```

### 5.2 缓存机制

- 与基础分析共享fetch缓存
- 自动检查缓存存在性
- 支持增量分析

### 5.3 错误处理

- 数据范围验证
- 缓存不存在时的自动处理
- 详细的错误日志

## 六、部署说明

### 6.1 文件部署

1. 将新的`data_bertopic_qwen_v2.py`放入`backend/src/topic/`
2. 更新`server.py`中的API接口（已包含）
3. 将`useTopicBertopicAnalysisV2.js`放入`frontend/src/composables/`
4. 更新`TopicBertopicRun.vue`（已包含）

### 6.2 兼容性

- 保留原有`data_bertopic_qwen.py`作为fallback
- 支持新旧两种数据格式（JSONL/CSV）
- API向后兼容

### 6.3 配置要求

- 确保数据库配置正确
- 检查fetch权限
- 验证主题分析配置（userdict/stopwords）

## 七、测试建议

### 7.1 功能测试

1. **专题列表加载**
   - 验证从数据库获取专题列表
   - 测试刷新功能
   - 检查空数据处理

2. **数据可用性检查**
   - 验证日期范围检查
   - 测试缓存提示
   - 检查错误处理

3. **分析执行**
   - 测试自动fetch
   - 验证日志显示
   - 检查结果生成

### 7.2 性能测试

- 大数据集的fetch性能
- BERTopic分析耗时
- 缓存命中效果

## 八、常见问题

### Q1: 如何处理已有数据？
A: 系统会自动检测已有的fetch缓存，如果存在则直接使用，无需重新拉取。

### Q2: 可以使用自定义fetch目录吗？
A: 是的，通过`fetch_dir`参数可以指定自定义的fetch目录。

### Q3: 如何切换回旧版本？
A: 删除或重命名`data_bertopic_qwen_v2.py`，系统会自动回退到`data_bertopic_qwen.py`。

### Q4: 支持哪些数据格式？
A: 新版本主要支持JSONL格式（与基础分析一致），同时保持对CSV的兼容性。

---

*文档更新时间：2025-12-08*
*版本：1.0*