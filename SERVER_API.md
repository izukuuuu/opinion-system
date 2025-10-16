# Server API 使用手册

所有接口均返回 JSON；若 `status: "ok"` 则表示成功，`status: "error"` 时需查看 `message` 与 `data` 中的上下文信息。

---

## 1. 基础信息

### `GET /api/status`
- **说明**：健康检查，返回后端运行状态与部分配置。
- **响应示例**：
  ```json
  {
    "status": "ok",
    "message": "OpinionSystem backend is running",
    "config": {
      "backend": {
        "host": "127.0.0.1",
        "port": 8000
      }
    }
  }
  ```

### `GET /api/config`
- **说明**：返回 `config.yaml` 中加载的整体配置，用于前端初始化。
- **响应**：`config.yaml` 的 JSON 化对象。

### `GET /`
- **说明**：根路径，返回一个包含常用端点的简要列表，便于快速验证服务可用。

---

## 2. 数据库连接管理

所有接口由 `backend/server.py` 内部的 `_load_databases_config` / `_persist_databases_config` 读写 `configs/settings/databases.yaml`。

### `GET /api/settings/databases`
- **说明**：列出已配置的数据库连接以及当前激活的连接 ID。
- **响应示例**：
  ```json
  {
    "status": "ok",
    "data": {
      "connections": [
        { "id": "primary", "name": "Prod MySQL", "engine": "mysql", "url": "mysql+pymysql://..." }
      ],
      "active": "primary"
    }
  }
  ```

### `POST /api/settings/databases`
- **说明**：创建新的连接配置，可通过 `set_active: true` 同时激活。
- **请求体**：
  ```json
  {
    "id": "primary",
    "name": "Prod MySQL",
    "engine": "mysql",
    "url": "mysql+pymysql://user:pass@host/db",
    "description": "生产库",
    "set_active": true
  }
  ```
- **返回**：新建的连接对象；若 ID 已存在则返回 409。

### `PUT /api/settings/databases/<connection_id>`
- **说明**：更新已存在的连接（不可修改 ID）。设置 `set_active: true` 可切换当前激活连接。
- **请求体**：任意需更新字段。

### `DELETE /api/settings/databases/<connection_id>`
- **说明**：删除连接，若目标为当前激活连接则返回 409。

### `POST /api/settings/databases/<connection_id>/activate`
- **说明**：显式将指定连接设为当前激活连接。

---

## 3. LLM 设置管理

数据存储于 `configs/settings/llm.yaml`。

### `GET /api/settings/llm`
- **说明**：返回完整的 LLM 配置（包含 `filter_llm`、`presets` 等）。

### `PUT /api/settings/llm/filter`
- **说明**：更新筛选模型的核心参数。
- **可选字段**：`provider`、`model`（字符串），`qps`、`batch_size`、`truncation`（整数）。
- **返回**：更新后的 `filter_llm` 对象。

### `POST /api/settings/llm/presets`
- **说明**：新增模型预设，字段 `id`、`name`、`provider`、`model` 必填。
- **返回**：新预设，ID 冲突会返回 409。

### `PUT /api/settings/llm/presets/<preset_id>`
- **说明**：更新指定预设的 `name`、`provider`、`model`、`description`。

### `DELETE /api/settings/llm/presets/<preset_id>`
- **说明**：删除指定预设；若不存在返回 404。

---

## 4. 数据入库流水线

### `POST /api/pipeline`
- **说明**：串行执行 Merge → Clean → Filter → Upload。
- **请求体**：
  ```json
  { "topic": "campaign_x", "date": "2024-04-01" }
  ```
- **成功响应**：
  ```json
  {
    "status": "ok",
    "operation": "pipeline",
    "data": {
      "status": "ok",
      "steps": [
        { "operation": "merge", "success": true, "result": true },
        { "operation": "clean", "success": true, "result": true },
        { "operation": "filter", "success": true, "result": true },
        { "operation": "upload", "success": true, "result": true }
      ]
    }
  }
  ```
- **失败响应**：`data.status = "error"`，`message` 指出失败步骤，`steps` 中对应 `success=false`。
- **推荐用法**：前端调用时展示 per-step 状态，失败后可引导用户查看日志或改用单步接口。

### 单步接口（可调试或按需重跑）
所有接口共用请求体 `{ "topic": string, "date": "YYYY-MM-DD" }`。

| 接口 | 说明 | 成功返回 |
| ---- | ---- | -------- |
| `POST /api/merge` | 合并 `data/raw/<topic>/<date>` 下多渠道 Excel，结果写入 `data/merge/<topic>/<date>` | `{"status":"ok","operation":"merge","data":true}` |
| `POST /api/clean` | 标准化列名/文本/时间并重排 `id`，输出 `data/clean/<topic>/<date>` | 同上 |
| `POST /api/filter` | 调用千问模型筛选高相关内容，输出 `data/filter/<topic>/<date>` | 同上，失败时可能返回模型错误信息 |
| `POST /api/upload` | 确保数据库及表结构存在，将筛选结果写入 `{topic}` 数据库 | 同上 |

---

## 5. 数据查询与分析

### `POST /api/query`
- **说明**：执行后端定义的查询调试逻辑（`src/query/run_query`），无请求体。
- **返回**：封装后的查询结果结构，具体取决于实现。

### `POST /api/fetch`
- **说明**：从数据库提取指定日期范围的数据并落盘。
- **请求体**：
  ```json
  {
    "topic": "campaign_x",
    "start": "2024-04-01",
    "end": "2024-04-07"
  }
  ```
- **返回**：`run_fetch` 的序列化结果。

### `POST /api/analyze`
- **说明**：对提取好的数据执行分析，可指定分析函数。
- **请求体**：
  ```json
  {
    "topic": "campaign_x",
    "start": "2024-04-01",
    "end": "2024-04-07",
    "function": "volume"   // 可选
  }
  ```
- **返回**：`run_Analyze` 的结果。

### `GET /api/analyze/results`
- **说明**：读取分析产出的 JSON 文件。
- **查询参数**：
  - `topic` (必填)
  - `start` (必填)
  - `end` (可选，缺省时等于 `start`)
  - `function` (可选，指定分析函数名)
  - `target` (可选，筛选下钻目标)
- **返回**：
  ```json
  {
    "status": "ok",
    "topic": "campaign_x",
    "range": { "start": "2024-04-01", "end": "2024-04-07" },
    "functions": [
      {
        "name": "volume",
        "targets": [
          {
            "target": "default",
            "file": "result.json",
            "data": { "...": "..." }
          }
        ]
      }
    ]
  }
  ```
- **错误码**：目录不存在或文件缺失时返回 404。

---

## 6. 项目管理与数据集

### `GET /api/projects`
- **说明**：列出所有项目及其元信息。

### `GET /api/projects/<name>`
- **说明**：获取指定项目的详情；不存在返回 404。

### `POST /api/projects`
- **请求体**：
  ```json
  {
    "name": "campaign_x",
    "description": "专题描述",
    "metadata": { "owner": "ops-team" }
  }
  ```
- **说明**：创建或更新项目，元数据为可选字典。

### `DELETE /api/projects/<name>`
- **说明**：删除项目；若不存在返回 404。

### `GET /api/projects/<name>/datasets`
- **说明**：列出项目下的本地数据集清单；异常时返回 500 并附错误提示。

### `POST /api/projects/<name>/datasets`
- **说明**：通过 multipart form 上传文件，并写入项目数据仓库。
- **请求体**：`form-data`，字段名为 `file`，值为 Excel 或 CSV 文件。
- **成功返回**：
  ```json
  {
    "status": "ok",
    "dataset": {
      "id": "...",
      "display_name": "dataset.xlsx",
      "rows": 120,
      "column_count": 12
    }
  }
  ```
- **注意**：接口内部会记录操作日志，失败时返回 400 / 500 具体原因。

---

## 7. 额外说明

- 所有修改配置类接口都会调用 `_reload_settings()` 以使变更即时生效。
- 数据入库/分析类接口（Merge/Clean/Filter/Upload/Fetch/Analyze）均在成功后记录项目操作日志，可在 `/api/projects/<name>` 中查看最近操作状态。
- 若需要自定义前端轮询逻辑，可关注返回体中的 `operation` 字段与 `steps` 结构，便于关联日志与 UI 展示。
