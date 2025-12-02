# Analyze 模块调用说明

> 下面的表格与示例覆盖 `backend/src/analyze` 目录内所有可调用函数，前端或自动化脚本可以直接据此对接。

```
backend/src/analyze/
├── __init__.py                # 暴露 run_Analyze
├── runner.py                  # 主调度器
└── functions/                 # 具体分析实现
    ├── attitude.py            # 态度分布
    ├── classification.py      # 分类统计
    ├── geography.py           # 地域分布
    ├── keywords.py            # 关键词
    ├── publishers.py          # 发布主体
    ├── trends.py              # 时间趋势
    └── volume.py              # 声量对比
```

## 入口调用

```python
from backend.src.analyze import run_Analyze

run_Analyze(
    topic="新能源",
    date="2024-06-01",
    only_function=None,   # 可选：仅运行某个功能
    end_date=None,        # 可选：与 fetch 模块使用同样的起止目录
)
```

- `topic`：专题名称，会成为 `bucket("fetch", topic, date_or_range)` 与 `bucket("analyze", topic, date_or_range)` 的子目录。
- `date`：抓取日期（`YYYY-MM-DD`）。若配合 `end_date` 使用，落盘目录为 `YYYY-MM-DD_YYYY-MM-DD`。
- `only_function`：大小写不敏感，匹配 `settings.get_analysis_config()["functions"][].name`。
- `end_date`：存在时，runner 会在 `fetch/topic/{date}_{end_date}` 目录读取/写入。
- 返回值：`bool`，表示是否至少有一个分析项成功。

## 数据流概览
1. `runner.py` 读取 `settings.get_analysis_config()` 中的 `functions` 数组，成员结构：
   ```json
   {"name": "volume", "target": "总体"}  # target ∈ {"总体","渠道"}
   ```
2. 读取 `bucket("fetch", topic, date_or_range)` 下的 `总体.jsonl` 及同级其它渠道 JSONL。
3. 根据配置调度对应函数，传入所需的 DataFrame 及辅助参数。
4. 结果写入 `bucket("analyze", topic, date_or_range)/{function}/{target}/`，文件名遵循 `{function}.json`（或 `result.json`）。

## 函数清单（快速对照）

| 名称 | 作用范围 | 关键字段 | 输出文件 | 返回示例 |
| --- | --- | --- | --- | --- |
| `analyze_volume_overall` / `analyze_volume_by_channel` | 总体/渠道 | fetch 目录内 JSONL 文件本身 | `volume.json` | `{"data":[{"name":"微博","value":1200}]}` |
| `analyze_attitude_overall` / `analyze_attitude_by_channel` | 总体/渠道 | 任意情感列（`attitude`,`polarity`,`情感`,`label` 等） | `attitude.json` | `{"data":[{"name":"positive","value":321}]}` |
| `analyze_trends_overall` / `analyze_trends_by_channel` | 总体/渠道 | `published_at`（可被 `pd.to_datetime` 解析） | `trends.json` | `{"data":[{"name":"2024-06-01","value":88}]}` |
| `analyze_keywords_overall` / `analyze_keywords_by_channel` | 总体/渠道 | 需至少一个正文列（`content`,`正文`,`segment` 等） | `keywords.json` | `{"data":[{"name":"新能源","value":56}]}` |
| `analyze_geography_overall` / `analyze_geography_by_channel` | 总体/渠道 | `region`,`省份`,`location_province` 等地域列 | `geography.json` | `{"data":[{"name":"北京","value":43}]}` |
| `analyze_publishers_overall` / `analyze_publishers_by_channel` | 总体/渠道 | `author`（会过滤掉“未知”） | `publishers.json` | `{"data":[{"name":"新华社","value":12}]}` |
| `analyze_classification_overall` / `analyze_classification_by_channel` | 总体/渠道 | `classification`（空值归并为“未知”） | `classification.json` | `{"data":[{"name":"政策解读","value":40}]}` |

所有函数都返回 `{"data": [...], "echarts": {...}}` 的结构，`echarts` 字段是预置好的 ECharts Option（若数据为空则不返回）。若缺少必需列或数据为空，则返回 `{"data": []}` 并在日志中记录原因。

## 函数细节与调用要点

### 1. Volume（声量）
- **总体**：遍历 `fetch/topic/date_or_range` 下除 `总体.jsonl` 外的每个渠道 JSONL，统计行数。
- **渠道**：只读取单个 `{channel}.jsonl` 并统计行数。
- **失败场景**：找不到目录/文件或 JSONL 解析失败，日志中会给出具体文件名。

### 2. Attitude（态度）
- `_normalize_attitude_column` 会自动兼容多种列名并将数值/中文映射到 `positive | negative | neutral | unknown`。
- 如果完全找不到可用列，则新增 `attitude='unknown'`，因此永远有数据返回。

### 3. Trends（趋势）
- 需要 `published_at` 列，函数内会复制 DataFrame 并调用 `pd.to_datetime`.
- 过滤掉解析失败的行后，按 `date` 维度统计；空结果会返回 `[]`。

### 4. Keywords（关键词）
- 自动探测包含 `content`/`正文`/`ocr`/`segment` 等字样的列。
- 使用 `configs/stopwords.txt`（或 `OPINION_CONFIG_DIR` 环境变量指向的目录）作为停用词。
- 如果安装了 `jieba`，使用词性过滤（名词/动词/形容词等）；否则 fallback 到简单英文/中文拆分。
- 默认只取 top 20 词频。

### 5. Geography（地域）
- `_detect_region_col` 依次尝试 `region`,`地区`,`省份`,`province`,`location_province`。
- 找不到列时返回空 dict，前端可直接渲染为空图。

### 6. Publishers（发布主体）
- 必须存在 `author` 列；空值和“未知”都会被丢弃。
- 结果按出现次数排序，默认返回前 20 项。

### 7. Classification（分类）
- 强制将空白、`nan`、`None`、`null` 视为“未知”。
- 会记录 `classification_percentages`（目前仅内部使用），最终对外只暴露数量。

## 输出目录示例
```
bucket("analyze", topic, date_or_range)/
└── keywords/
    ├── 总体/keywords.json
    ├── 微博/keywords.json
    └── 小红书/keywords.json
```

- 每个 JSON 文件内容形式一致，可直接由前端请求后渲染。
- 若需要新增分析，只需在 `settings.analysis.functions` 中添加配置并实现对应函数即可自动落盘。

## 日志与错误处理
- 日志入口统一来自 `setup_logger(topic, date)`。
- `log_success`：模块或函数执行成功。
- `log_error`：字段缺失、文件不存在、解析失败等都会记录详细信息，便于排查。
- `log_skip`：当 DataFrame 为空时，会提示已跳过（例如分类分析）。

前端集成时，可以据 `bucket/analyze/...` 目录结构拉取 JSON，或根据日志定位缺失字段/数据问题。
