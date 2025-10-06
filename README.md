# Opinion System 项目总览

本仓库提供一个面向“项目制”舆情流程的全栈示例，后端负责数据归档与流程记录，前端则提供项目面板、数据归档和测试页三大界面。新版实现了以下要点：

- `backend/data/`：存放项目的结构化数据（PKL、JSON 以及数据清单）。
- `backend/store/`：保存原始 Excel/CSV 表格文件，按项目分类归档。
- REST API 新增 `/api/projects/<name>/datasets` 端点，可上传表格并返回归档信息。
- 前端采用现代化双栏布局，引入 Heroicons 提供的专业级图标，并新增“项目数据”页面。

## 目录结构

```
.
├── backend/                      # Python 后端
│   ├── data/                     # 生成的 PKL/JSON 归档（版本库中以 .gitkeep 占位）
│   ├── store/                    # 原始 Excel/CSV 表格存储目录
│   ├── main.py                   # 命令行入口（Click）
│   ├── requirements.txt          # 后端依赖
│   ├── server.py                 # Flask + CORS API 服务
│   └── src/                      # 各类数据处理与项目管理模块
└── frontend/                     # Vue 3 + Vite 前端
    ├── package.json              # 已引入 @heroicons/vue、vue-router 等依赖
    ├── package-lock.json
    ├── src/
    │   ├── App.vue               # 带侧边栏的应用外壳
    │   ├── components/
    │   │   └── ProjectDashboard.vue 等业务组件
    │   ├── views/
    │   │   ├── ProjectBoardView.vue  # 项目面板
    │   │   ├── ProjectDataView.vue   # 数据归档页
    │   │   └── TestView.vue          # 测试/实验页
    │   └── router/index.js       # 前端路由配置
    └── vite.config.js
```

> 注意：`backend/data/` 与 `backend/store/` 目录会在运行时写入文件，为避免污染版本库仅保留 `.gitkeep` 占位，真实数据会按项目名称生成子目录。

## 后端使用说明

### 环境准备

```bash
cd backend
python -m venv venv           # 创建虚拟环境（可选）
source venv/bin/activate      # Linux / macOS
# .\\venv\\Scripts\\activate  # Windows
pip install -r requirements.txt
```

如需调用需要鉴权的外部服务，可将密钥写入 `backend/.env`：

```bash
DASHSCOPE_API_KEY=你的API密钥
```

### 核心命令

`main.py` 提供了统一的命令行入口，当前支持以下功能模块：

| 命令 | 作用 | 典型参数 |
| --- | --- | --- |
| `python main.py Merge` | 合并 TRS Excel 数据 | `--topic 话题 --date YYYY-MM-DD` |
| `python main.py Clean` | 清洗数据 | `--topic 话题 --date YYYY-MM-DD` |
| `python main.py Filter` | AI 相关性筛选 | `--topic 话题 --date YYYY-MM-DD` |
| `python main.py Upload` | 上传结果到数据库 | `--topic 话题 --date YYYY-MM-DD` |
| `python main.py Query` | 查询数据库中已上传的数据 | 无 |
| `python main.py Fetch` | 按时间范围提取数据 | `--topic 话题 --start YYYY-MM-DD --end YYYY-MM-DD` |
| `python main.py Analyze` | 执行数据分析，可指定分析函数 | `--topic 话题 --start YYYY-MM-DD --end YYYY-MM-DD [--func 指定函数]` |
| `python main.py DataPipeline` | 合并 → 清洗 → 筛选 → 上传的流水线 | `--topic 话题 --date YYYY-MM-DD` |
| `python main.py AnalyzePipeline` | 提数 → 分析的流水线 | `--topic 话题 --start YYYY-MM-DD --end YYYY-MM-DD` |

常用工作流示例：

```bash
cd backend
python main.py DataPipeline --topic 示例专题 --date 2025-01-01
python main.py AnalyzePipeline --topic 示例专题 --start 2025-01-01 --end 2025-01-07
```

### Web API 概览

启动 `server.py` 后将得到以下接口（默认 `http://localhost:8000/api`）：

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/projects` | 列出所有项目及其执行记录 |
| `POST` | `/api/projects` | 创建或更新项目基本信息 |
| `GET` | `/api/projects/<name>` | 查看指定项目详情 |
| `GET` | `/api/projects/<name>/datasets` | 读取项目下的归档数据清单 |
| `POST` | `/api/projects/<name>/datasets` | 上传 Excel/CSV，生成 PKL + JSON + manifest |
| `POST` | `/api/merge` / `/api/clean` / ... | 复用原有流程型接口 |

> 上传接口会自动：
> 1. 将原始表格写入 `backend/store/<项目名>/`。
> 2. 读取表格生成 `pandas.DataFrame`，输出到 `backend/data/<项目名>/<dataset_id>.pkl`。
> 3. 写入同名 JSON 元数据与 `manifest.json`，包含行数、列名、相对路径等信息。

## 前端使用说明

前端目录提供了一个现代化的 Vue 3 + Vite 开发环境，内置 Heroicons 与项目化导航。

```bash
cd frontend
npm install             # 安装依赖
npm run dev             # 启动开发服务器（默认 5173 端口）
npm run build           # 生成生产构建
npm run preview         # 预览生产构建
```

### 页面与功能

- **项目面板**：左侧列表聚合项目，右侧展示执行日志、日期范围、元信息等。
- **项目数据**：按项目上传 Excel/CSV，自动生成 PKL/JSON，并展示 manifest 列表。
- **测试页面**：集成 Heroicons 与指导提示，用于前端组件或 API 调试。

在 `.env.local` 中设置 `VITE_API_BASE_URL` 可自定义后端地址，默认为 `http://localhost:8000/api`。

## 协同开发建议

- 前后端通过 API 保持松耦合，必要时更新 README 或接口文档同步说明。
- 运行前请确认 `backend/data/` 与 `backend/store/` 具备读写权限，可在生产环境中挂载到持久磁盘。
- 若需要在 CI/CD 中复现数据生成流程，可编写脚本调用 `/api/projects/<name>/datasets` 上传并校验返回的 JSON/PKL 路径。
