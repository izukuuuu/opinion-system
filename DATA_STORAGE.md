# 数据存储规范

本文档约定 `backend/data/projects/` 目录下的文件层级、命名规范与格式，便于前后端、运维及数据团队协同。

```
backend/data/projects/
└── <topic>/                      # 项目/专题名称（保持原文）
    ├── raw/                      # 外部采集的原始文件（仍为 Excel）
    │   └── <date>/               # YYYY-MM-DD
    │       └── *.xlsx            # TRS / 手工上传的来源文件
    ├── merge/                    # Merge 步骤输出
    │   └── <date>/<channel>.jsonl
    ├── clean/                    # Clean 步骤输出
    │   └── <date>/<channel>.jsonl
    ├── filter/                   # Filter 步骤输出（高相关）
    │   └── <date>/<channel>.jsonl
    ├── fetch/                    # Fetch 步骤输出（日期范围）
    │   └── <start>_<end>/        # YYYY-MM-DD_YYYY-MM-DD
    │       ├── <channel>.jsonl   # 各渠道数据
    │       ├── <merge>.jsonl     # 配置中要求的合并渠道
    │       └── 总体.jsonl        # 汇总全量数据
    ├── analyze/                  # Analyze 结果（保持原有 JSON 命名）
    │   └── <range>/<func>/<target>/<file>.json
    └── uploads/                  # 项目数据上传归档
        ├── original/             # 原始上传文件
        ├── jsonl/                # 转换后的标准 JSONL
        ├── cache/                # DataFrame pickle 缓存
        ├── meta/                 # 单个数据集元信息（*.json）
        └── manifest.json         # 数据集清单
```

## 文件格式

- **原始层 (`raw/`)**：沿用采集系统生成的 Excel（`.xlsx`/`.xls`）。后续流程只读取不改写。
- **中间层 (`merge/`、`clean/`、`filter/`、`fetch/`)**：统一使用 UTF-8 JSON Lines（`.jsonl`），每行一条记录，便于增量处理与流式读取。
- **分析层 (`analyze/`)**：保持既有 JSON 结构（`volume.json`、`trends.json` 等），不作变更。
- **上传归档 (`uploads/`)**：
  - `original/`：保留原始上传文件副本；
  - `jsonl/`：同一数据的标准 JSONL 版本；
  - `cache/`：`pandas.DataFrame.to_pickle()` 输出，供后端快速读取；
  - `meta/`：包含行数、列名、原始/JSONL 路径等元数据；
  - `manifest.json`：汇总 `meta/` 下所有条目，供 `/api/projects/<name>/datasets` 返回。

## 命名约定

- `<topic>`：专题或项目名称，原样使用；若包含空格/特殊字符，代码会在写盘前自动 slug 化（如 `新能源 项目` → `新能源-项目`）。
- `<date>`：单日流程使用 `YYYY-MM-DD`。
- `<start>_<end>`：跨日期范围使用 `YYYY-MM-DD_YYYY-MM-DD`。
- `<channel>`：渠道或合并结果名称，来自 `channels.yaml.keep` 或 `merge_for_analysis`。
- `<func>` / `<target>`：分析函数名与目标（`总体` 或渠道名），沿用配置。
- 上传数据的 `dataset_id`：格式 `YYYYMMDDTHHMMSS-<8位随机>`，确保可排序与去重。

## 读写接口与约定

- **路径解析**：使用 `src/utils/setting/paths.py` 中的 `bucket/ensure_bucket`，自动定位 `backend/data/projects/<topic>/<layer>/<date_or_range>`。
- **JSONL 读写**：统一调用 `src/utils/io/excel.py` 内的 `read_jsonl` / `write_jsonl`，确保 `orient=records`、`lines=true`、`force_ascii=false`。
- **数据库上传**：`src/update/data_update.py` 读取 `filter/<date>/*.jsonl`，去重后写入数据库；若无 JSONL，直接退出并记录错误。
- **Fetch/Analyze**：Fetch 写入 JSONL 后，Analyze 使用 `read_jsonl` 读取 `总体.jsonl` + 渠道 JSONL，兼容所有下游分析函数。
- **项目数据上传**：`src/project/storage.py` 会在 `uploads/` 目录内同时生成 `original`, `jsonl`, `cache`, `meta`, `manifest` 五套文件，前端调用 `/api/projects/<name>/datasets` 即可获取。

## 使用建议

- 在部署或本地调试前，确保运行用户对 `backend/data/projects/` 拥有读写权限。
- 若需要清理数据，可按项目目录整体归档/备份，避免跨项目混淆。
- 当新增流程节点时，请更新本说明和 `src/utils/setting/paths.py` 的 `LAYERS` 枚举，并统一输出 JSONL。
