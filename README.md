# Opinion System 项目总览

本仓库提供了一个用于舆情采集、清洗、分析与数据服务的后端，以及为后续界面开发预置的 Vue 3 + Vite 前端环境。当前项目结构如下：

```
.
├── backend/           # Python 舆情处理后端
│   ├── main.py        # 命令行入口（Click）
│   ├── requirements.txt
│   └── src/           # 各类数据处理模块
└── frontend/          # Vue 3 + Vite 开发脚手架
    ├── index.html
    ├── package.json
    └── src/
```

## 后端（backend）使用说明

### 环境准备

```bash
cd backend
python -m venv venv           # 创建虚拟环境（可选）
source venv/bin/activate      # Linux / macOS
# .\\venv\\Scripts\\activate  # Windows
pip install -r requirements.txt
```

将后端配置所需的环境变量写入 `backend/.env`（示例）：

```bash
DASHSCOPE_API_KEY=你的API密钥
```

### 办案（处理）方法总览

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

### 常用工作流示例

```bash
cd backend
python main.py DataPipeline --topic 示例专题 --date 2025-01-01
python main.py AnalyzePipeline --topic 示例专题 --start 2025-01-01 --end 2025-01-07
```

## 前端（frontend）使用说明

前端目录提供了一个使用 Vue 3 与 Vite 的最小化开发环境，可直接进行页面开发或与后端 API 对接。

```bash
cd frontend
npm install
npm run dev       # 启动开发服务器（默认 5173 端口）
npm run build     # 生成生产构建
npm run preview   # 预览生产构建
```

你可以在 `frontend/src` 中新增页面、组件或接口封装，随后与后端接口联调。当前示例页面包含一个欢迎组件，方便快速验证运行环境。

## 协同开发建议

- 使用 Git 分支管理前后端改动，保持 `backend` 与 `frontend` 的接口契约清晰。
- 在前端通过环境变量（例如 `.env.local`）管理后端地址，便于部署与测试环境切换。
- 若需要共享配置，可以在项目根目录补充文档或脚本，避免前后端耦合。
