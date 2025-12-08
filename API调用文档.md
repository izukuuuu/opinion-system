# OpinionSystem 基础分析页面 API 调用流程文档

## 一、整体架构概览

OpinionSystem 是一个舆情分析系统，采用前后端分离架构：
- **前端**：Vue.js + TypeScript (端口 5173)
- **后端**：Flask + Python (端口 8000)
- **���据库**：远程 MySQL 数据库（用于存储原始舆情数据）
- **本地存储**：文件系统缓存（用于存储处理后的数据和分析结果）

### 数据流转路径
```
远程数据库 → Fetch → 本地缓存 → Analyze → 结果存储 → 前端展示
```

## 二、前端页面结构

### 2.1 页面组件层级
```
/analysis/basic/run (ProjectBasicAnalysisRun.vue)
├── 专题选择器
├── 日期范围选择器
├── 分析函数选择列表
└── 执行日志面板 (AnalysisLogList.vue)
```

### 2.2 核心状态管理 (useBasicAnalysis.js)
- **topicsState**: 管理远程专题列表
- **fetchState**: 管理数据拉取状态
- **analyzeState**: 管理分析执行状态
- **selectedFunctions**: 管理选中的分析函数
- **analysisData**: 存储分析结果数据

## 三、API 调用流程详解

### 3.1 页面初始化流程

#### Step 1: 加载专题列表
```javascript
// API: POST /api/query
// 请求体：{ include_counts: false }
// 响应：{ databases: ["专题1", "专题2", ...] }

// 前端调用：
loadTopics() → callApi('/api/query') → 更新 topicsState.options
```

#### Step 2: 检查数据可用性
```javascript
// API: GET /api/fetch/availability?topic=专题名
// 响应：{ range: { start: "2024-01-01", end: "2024-12-31" } }

// 前端调用：
changeTopic() → loadAvailableRange() → 更新 availableRange
```

### 3.2 数据准备阶段（Fetch）

#### Step 3: 触发数据拉取
```javascript
// API: POST /api/fetch
// 请求体：
// {
//   topic: "专题名",
//   start: "2024-01-01",
//   end: "2024-01-31"
// }
// 响应：{ status: "ok", message: "已触发数据拉取" }

// 后端处理流程：
// 1. 验证专题和时间范围
// 2. 连接远程数据库
// 3. 按渠道提取数据（weibo, wechat, news 等）
// 4. 保存为 JSONL 格式到本地缓存
// 5. 生成合并数据（总体.jsonl）
```

#### 数据缓存结构
```
backend/data/projects/{专题}/fetch/{开始日期}_{结束日期}/
├── weibo.jsonl      # 微博数据
├── wechat.jsonl     # 微信数据
├── news.jsonl       # 新闻数据
├── app.jsonl        # APP数据
└── 总体.jsonl       # 合并后的所有数据
```

### 3.3 分析执行阶段（Analyze）

#### Step 4: 执行分析函数
```javascript
// API: POST /api/analyze
// 请求体：
// {
//   topic: "专题名",
//   start: "2024-01-01",
//   end: "2024-01-31",
//   function: "attitude"  // 或其他分析函数
// }

// 支持的分析函数：
// - attitude: 情感分析
// - classification: 话题分类
// - geography: 地域分析
// - keywords: 关键词分析
// - publishers: 发布者分析
// - trends: 趋势洞察
// - volume: 声量概览
```

#### 分析结果存储结构
```
backend/data/projects/{专题}/analyze/{开始日期}_{结束日期}/
├── attitude/
│   ├── 总体/
│   │   └── attitude.json
│   ├── weibo/
│   │   └── attitude.json
│   └── ...
├── keywords/
│   └── ...
├── ai_summary.json  # AI生成的整体摘要
└── ...
```

### 3.4 结果查询阶段

#### Step 5: 获取分析历史
```javascript
// API: GET /api/analyze/history?topic=专题名
// 响应：
// {
//   records: [
//     {
//       id: "专题:20240101_20240131",
//       topic: "专题名",
//       start: "2024-01-01",
//       end: "2024-01-31",
//       folder: "20240101_20240131",
//       updated_at: "2024-01-31 10:00:00"
//     }
//   ]
// }
```

#### Step 6: 加载分析结果
```javascript
// API: GET /api/analyze/results?topic=专题名&start=2024-01-01&end=2024-01-31
// 响应：
// {
//   topic: "专题名",
//   range: { start: "2024-01-01", end: "2024-01-31" },
//   functions: [
//     {
//       name: "attitude",
//       targets: [
//         {
//           target: "总体",
//           data: { /* 分析结果数据 */ }
//         }
//       ]
//     }
//   ],
//   ai_summary: { /* AI摘要 */ }
// }
```

## 四、数据处理细节

### 4.1 数据库查询逻辑（后端 fetch/data_fetch.py）

```python
# 核心查询逻辑
def fetch_range(topic, start_date, end_date, output_date):
    # 1. 连接远程数据库
    db_url_with_db = base_url.set(database=topic)
    engine = create_engine(db_url_with_db)

    # 2. 查询各渠道数据
    for channel in channels:
        query = """
        SELECT * FROM {table_name}
        WHERE DATE(published_at) BETWEEN :start_date AND :end_date
        ORDER BY published_at DESC
        """

    # 3. 数据清洗和保存
    # - 确保classification字段存在
    # - 保存为JSONL格式
    # - 生成渠道合并数据
```

### 4.2 分析函数执行流程（后端 analyze/runner.py）

```python
# 分析执行主流程
def run_Analyze(topic, start_date, end_date, only_function=None):
    # 1. 读取缓存数据
    fetch_dir = bucket("fetch", topic, folder_name)
    all_data = read_jsonl(fetch_dir / "总体.jsonl")

    # 2. 执行分析函数
    for function_name in functions_to_run:
        # 调用对应的分析函数
        result = analyze_function(df, all_data)

        # 3. 保存结果
        analyze_dir = bucket("analyze", topic, folder_name)
        target_dir = analyze_dir / function_name / target
        save_result(result, target_dir)

        # 4. 生成AI摘要（可选）
        if ai_client_available:
            summary = generate_ai_summary(result)
```

## 五、缓存机制说明

### 5.1 Fetch 数据缓存
- **位置**: `backend/data/projects/{专题}/fetch/`
- **命名规则**: `{开始日期}_{结束日期}/`
- **缓存策略**:
  - 如果缓存存在，直接使用
  - 如果缓存不存在，触发fetch流程
  - 支持部分日期覆盖更新

### 5.2 Analyze 结果缓存
- **位置**: `backend/data/projects/{专题}/analyze/`
- **缓存策略**:
  - 按函数分别缓存
  - 支持增量分析（只运行选中的函数）
  - 结果永久保存，除非手动删除

### 5.3 缓存管理API
```javascript
// 查看缓存状态
GET /api/projects/{name}/fetch-cache

// 清理缓存（通过删除项目存档）
DELETE /api/projects/{name}/archives/{layer}/{date}
```

## 六、错误处理和日志

### 6.1 前端错误处理
- API请求失败时显示错误信息
- 实时显示执行日志
- 支持重试机制

### 6.2 后端日志系统
- 操作日志记录在 `logs/` 目录
- 支持按专题和时间分桶存储
- 关键操作都有详细的执行日志

## 七、性能优化建议

### 7.1 数据库查询优化
- 确保 `published_at` 字段有索引
- 使用分页查询处理大数据量
- 考虑使用数据库连接池

### 7.2 缓存优化
- 大数据集考虑使用压缩存储
- 实现缓存过期机制
- 支持并行处理多个分析函数

### 7.3 前端优化
- 使用虚拟滚动处理大量数据
- 实现增量加载
- 添加请求取消机制

## 八、常见问题排查

### 8.1 数据拉取失败
1. 检查数据库连接配置
2. 验证专题名称是否正确
3. 确认时间范围内有数据
4. 检查表结构是否包含必需字段

### 8.2 分析执行失败
1. 确认fetch缓存已生成
2. 检查数据格式是否正确
3. 查看分析函数日志
4. 验证输出目录权限

### 8.3 性能问题
1. 监控数据库查询时间
2. 检查本地磁盘空间
3. 分析内存使用情况
4. 考虑数据分批处理

## 九、扩展说明

### 9.1 支持的数据渠道
- 微博 (weibo)
- 微信 (wechat)
- 新闻 (news)
- APP (app)
- 论坛 (forum)
- 其他自定义渠道

### 9.2 自定义分析函数
可以通过在 `backend/src/analyze/functions/` 目录下添加新的分析函数来扩展功能。

### 9.3 AI集成
系统支持集成通义千问等AI模型，用于生成智能摘要和分析洞察。

---

*文档更新时间：2025-12-08*
*系统版本：基于当前代码库分析*