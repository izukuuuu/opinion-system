# Analyze 模块调用说明

## 模块概览
`backend/src/analyze` 目录提供舆情分析的集中入口，`run_Analyze` 会读取抓取结果并调度不同的分析函数，将结果按功能与渠道写入 `analyze` 存储桶。

```
backend/src/analyze/
├── __init__.py                # 暴露 run_Analyze 作为模块入口
├── runner.py                  # 定义 run_Analyze 主流程
└── functions/                 # 各类分析逻辑
    ├── attitude.py            # 情感/态度分布
    ├── classification.py      # 分类字段统计
    ├── geography.py           # 地域分布
    ├── keywords.py            # 关键词提取
    ├── publishers.py          # 发布机构统计
    ├── trends.py              # 时间趋势
    └── volume.py              # 声量对比
```

## run_Analyze 调用流程
1. **初始化日志与配置**：根据 `settings.get_analysis_config()` 中的 `functions` 列表决定要运行的分析项。
2. **读取数据**：从 `bucket("fetch", topic, date_or_range)` 目录加载 `总体.csv` 以及同目录下的渠道 CSV。
3. **调度函数**：按照配置的 `name`（功能）与 `target`（`总体` 或 `渠道`）调用对应函数，例如 `volume`、`attitude` 等。
4. **结果落盘**：将返回的数据写入 `bucket("analyze", topic, date_or_range)/<function>/<target>/` 目录，并使用各功能约定的文件名，例如 `volume.json`。

> `only_function` 参数支持只执行单个功能（不区分大小写），`end_date` 参数允许指定日期区间以匹配抓取目录。

## 可用分析函数与输入要求
| 功能名 | 目标 | 依赖字段/说明 | 输出结构 |
| --- | --- | --- | --- |
| `volume` | 总体/渠道 | 需存在对应 CSV；总体模式读取所有渠道文件统计行数 | `{"data": [{"name": 渠道, "value": 行数}]}` |
| `attitude` | 总体/渠道 | 需要情感字段，可识别 `attitude`、`polarity`、`情感` 等列名 | `{"data": [{"name": 情感标签, "value": 数量}]}` |
| `trends` | 总体/渠道 | 需 `published_at` 列，可转为日期 | `{"data": [{"name": 日期, "value": 数量}]}` |
| `keywords` | 总体/渠道 | 需文本列（如 `content`、`正文`）；可利用停用词配置 | `{"data": [{"name": 关键词, "value": 词频}]}` |
| `geography` | 总体/渠道 | 需地域列（`region`、`省份` 等） | `{"data": [{"name": 地域, "value": 数量}]}` |
| `publishers` | 总体/渠道 | 需 `author` 列；忽略“未知” | `{"data": [{"name": 发布主体, "value": 数量}]}` |
| `classification` | 总体/渠道 | 需 `classification` 列；空值归并为“未知” | `{"data": [{"name": 分类, "value": 数量}]}` |

所有分析函数都返回一个包含 `data` 列表的字典，便于前端直接消费。如遇关键字段缺失或数据为空，函数会记录日志并返回空数据结构。

## 示例
```python
from backend.src.analyze import run_Analyze

# 以“新能源”专题 2024-06-01 的数据为例
topic = "新能源"
date = "2024-06-01"

# 执行配置中的全部功能
run_Analyze(topic, date)

# 只运行关键词分析，并指定起止日期目录
run_Analyze(topic, date, only_function="keywords", end_date="2024-06-07")
```
