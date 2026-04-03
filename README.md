> ⚠️ **UNDER CONSTRUCTION** ⚠️ 不可用状态

## 最近更新日志

<p>
  <a href="./CHANGELOG.md">
    <img alt="查看所有更新日志" src="https://img.shields.io/badge/查看所有更新日志-0F172A?style=for-the-badge&logo=bookstack&logoColor=white">
  </a>
</p>

### 2026/4/3 更新日志

**数据集成部分：**

- [x] **交互界面开发：** 构建“下载队列”管理页，包含新建任务弹窗（支持关键词与参数配置）及任务列表状态监控。

**数据清洗：**

- [x] **完善专题关键词过滤机制：** 为解决 AI 筛选耗费 Token 的问题，新增了不依赖分词的规则匹配功能。现已实现入库前的“预清洗”和针对数据库噪声的“后清洗”双流程，命中自定义排除词（如特定无关实体）的条目将被直接丢弃。
- [x] **前端弹窗交互优化：** 优化排除词交互与 Modal 布局。排除词高亮标红、Heroicons 移除图标替换，修复弹窗滚动条溢出导致的圆角遮挡问题。

**基础流程分析完善：**

- [x] **标签映射：** 在前端集成图表配置层，将原始数据标签统一映射为中文展示。
- [x] **动态占比分析：** 新增“时间流动占比”分析模块，计算各舆情维度随时间演变的权重分布。

**报告生成部分：**

运行部分

- [x] **独立 worker + heartbeat 模式**

完善分析质量

- [x] **优化报告基础分析部分逻辑：** 强化“基础分析层”到“报告生成”的衔接，增加对各子项分析结果的文本解读深度；将基础分析的各大子项图表完整集成至 Web 版报告生成界面。
- [x] **Bertopic 时序分析模块化封装：** 将 BERTopic 时序挖掘功能独立为标准模块，统一时序分析与报告输出的格式；明确 BERTopic 的更新点，同步修正报告生成模块中的相关调用与引用路径；在报告生成环节接入 LangChain 文本解读层，实现对时序动态的自动化叙述。
- [x] **完善分析逻辑：** 将“舆情智库”与“深度分析”转化为系统内标准化的 **Skill** 与 **Tools**；引入多维提示词工程（Prompt Engineering）与分析链路，提升报告生成模块的逻辑推导能力与文本产出深度。


# OpinionSystem - 舆情分析系统

基于AI的智能舆情数据采集、分析与检索系统

---

## 🚀 快速开始：环境配置与运行

本项目包含前端（Vue3）和后端（Python Flask）两部分。推荐优先使用根目录快速启动文件，它们已经统一封装了依赖检查、占位文件创建、服务启动和浏览器打开流程。

### 1. 推荐方式：根目录快速启动

#### 1.1 先准备本地数据库

本项目**不会自动安装数据库服务**，请先自行在本机准备并启动关系型数据库。

- 推荐使用 **PostgreSQL**
- 默认本地开发建议使用 `localhost:5432`
- 启动前请自行编辑 `backend/configs/databases.yaml`
- 根目录 `run.py` 只会检查数据库配置和连通性，不会代替你安装数据库

#### 1.2 安装 `uv` 与 Node.js（如未安装）

```bash
# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

请另外安装：

- Node.js 18+
- 本地 PostgreSQL（推荐）

#### 1.3 运行快速启动文件

Windows：

```bat
start_win.bat
```

macOS / Linux：

```bash
./start_mac.sh
```

通用方式：

```bash
python run.py
```

这些快速启动文件会自动：

- 检查 `uv pip`、`npm` 和 `backend/configs/databases.yaml` 当前激活数据库连接是否可达
- 缺失时创建 `backend/.env`、`frontend/.env.local`、`backend/configs/databases.yaml` 等本地占位文件
- 安装前后端依赖，并按主机环境自动选择 PyTorch 方案
- macOS 自动使用标准 PyTorch；Apple Silicon 可走 MPS，Intel Mac 走 CPU
- Windows 没有 NVIDIA / CUDA 时自动切到 CPU 版 PyTorch
- Windows 检测到 NVIDIA GPU 但系统没有 CUDA 时会直接退出，并提示先安装 CUDA 11.8+
- 启动 `backend/server.py` 与前端 Vite 开发服务
- 服务就绪后自动打开浏览器

启动成功后，默认访问：

- 前端：`http://127.0.0.1:5173`
- 后端状态：`http://127.0.0.1:8000/api/status`

---

### 2. 手动方式（备选）

#### 2.1 后端环境配置

后端基于 Python 3.11，使用 Flask 作为服务器框架。请使用项目虚拟环境解释器，不要依赖系统 Python。

#### 2.1.1 安装后端依赖

Windows：

```powershell
uv pip install --python .venv\Scripts\python.exe -r backend\requirements.txt
```

macOS / Linux：

```bash
uv pip install --python .venv/bin/python -r backend/requirements.txt
```

#### 2.1.2 安装 PyTorch（按主机环境选择）

macOS：

```bash
uv pip install --python .venv/bin/python torch torchvision torchaudio
```

Windows，无 NVIDIA GPU / 不准备使用 CUDA：

```powershell
uv pip install --python .venv\Scripts\python.exe --index-url https://download.pytorch.org/whl/cpu torch torchvision torchaudio
```

Windows，已安装 NVIDIA GPU 且系统已装 CUDA 11.8+：

```powershell
uv pip install --python .venv\Scripts\python.exe --index-url https://download.pytorch.org/whl/cu118 torch torchvision torchaudio
```

如果是 Windows 且检测到 NVIDIA GPU，但系统还没有 CUDA，请先安装 CUDA，再继续后端环境安装。

#### 2.1.3 配置后端环境变量

`backend/.env` 在缺失时会由 `run.py` 自动创建；如果你手动启动，也可以自己补充 API 密钥：

```env
DASHSCOPE_API_KEY=your_api_key_here
```

> 💡 如需使用阿里云通义千问等大模型服务，请在此处填写对应的 API Key。

#### 2.1.4 启动后端服务

Windows：

```powershell
.venv\Scripts\python.exe backend\server.py
```

macOS / Linux：

```bash
.venv/bin/python backend/server.py
```

后端默认运行在 `http://127.0.0.1:8000`。

---

### 2.2 前端环境配置

前端基于 Vue3 + Vite + TailwindCSS 构建，位于 `frontend/` 目录。需要 Node.js 环境（推荐 v18+）。

#### 2.2.1 安装前端依赖

```bash
cd frontend
npm install
```

#### 2.2.2 配置前端环境变量

前端环境变量文件为 `frontend/.env.local`。该文件在缺失时会由 `run.py` 自动创建；如果你手动启动，可写入后端 API 地址：

```env
VITE_API_BASE_URL=http://127.0.0.1:8000/api
```

> 💡 如后端运行在其他地址，请相应修改此配置。

#### 2.2.3 启动前端开发服务器

```bash
cd frontend
npm run dev
```

前端默认运行在 `http://localhost:5173`，浏览器访问即可使用系统。

---

### 3. 手动完整启动流程

```bash
# 终端 1：启动后端
.venv\Scripts\python.exe backend\server.py

# 终端 2：启动前端
cd frontend
npm run dev
```

启动成功后，访问 `http://localhost:5173` 即可使用舆情分析系统。

---

### 4. 技术栈概览

| 模块 | 技术 |
|------|------|
| 前端框架 | Vue 3 + Vite |
| 前端样式 | TailwindCSS |
| 图表 | ECharts |
| 后端框架 | Flask |
| AI 模型 | 阿里云通义千问 (Qwen) |
| 向量数据库 | LanceDB |
| 关系数据库 | PostgreSQL |

---

## 📋 目录

- [最近更新日志](#最近更新日志)
- [系统简介](#系统简介)
- [核心功能](#核心功能)
- [技术架构](#技术架构)
- [快速开始](#快速开始)
- [数据处理流水线](#数据处理流水线)
- [数据分析功能](#数据分析功能)
- [内容分析功能](#内容分析功能)
- [数据解读功能](#数据解读功能)
- [RAG检索系统](#rag检索系统)
- [项目结构](#项目结构)
- [配置说明](#配置说明)
- [日志管理](#日志管理)

---

## 系统简介

OpinionSystem 是一个完整的舆情分析解决方案，集成了数据采集、清洗、AI筛选、多维度分析和智能检索功能。

### 主要特性

- 🔄 **自动化数据流水线**: 从原始数据到数据库存储的全流程自动化
- 🤖 **AI智能筛选**: 基于大语言模型的相关性筛选和分类
- 📊 **多维度分析**: 情感、地域、趋势、关键词等7大维度分析
- 🧠 **智能解读**: 基于AI的舆情分析结果深度解读
- 🔍 **智能检索系统**: 支持GraphRAG和传统向量检索的混合检索
- 📈 **可视化报告**: 自动生成多渠道、多维度的分析报告
- 🎯 **多专题管理**: 支持多专题并行处理和独立管理

---

## 核心功能

### 1. 数据处理模块
- **数据合并**: 整合TRS系统导出的多渠道Excel数据
- **数据清洗**: 去重、格式标准化、字段补全
- **AI筛选**: 基于自定义规则的智能相关性筛选
- **数据存储**: 自动上传到数据库并建立索引

### 2. 数据分析模块
- **情感分析** (attitude): 正面/中性/负面情感倾向分析
- **话题分类** (classification): 多级话题分类体系
- **地域分析** (geography): 省市级地域分布统计
- **关键词分析** (keywords): 高频词提取和词云生成
- **发布者分析** (publishers): 发布账号Top排行
- **趋势分析** (trends): 时间序列变化趋势
- **声量分析** (volume): 各渠道声量统计

### 3. 内容分析模块
- **内容编码分析**: 基于AI的新闻内容深度编码分析
- **动态字段适配**: 自动识别不同专题的JSON字段结构
- **智能编码**: 支持信息类别、议题编码、信源编码等多维度分析
- **批量处理**: 高并发批量分析，支持自定义QPS控制

### 4. 数据解读模块
- **智能解读**: 基于AI的舆情分析结果深度解读
- **TagRAG集成**: 自动召回相关背景文段提供上下文
- **多维度解读**: 支持情感、关键词、趋势等8大维度解读
- **高并发处理**: 50并发处理渠道解读任务
- **数据检查**: 自动检查分析结果有效性，跳过无效数据

### 5. RAG检索系统
- **TagRAG**: 基于标签的快速检索系统
- **RouterRAG**: 集成GraphRAG、NormalRAG、TagRAG的混合检索
  - GraphRAG: 知识图谱实体关系检索
  - NormalRAG: 传统语义向量检索
  - TagRAG: 标签向量检索
- **时间智能过滤**: 自动识别查询时间并过滤文档
- **LLM整理**: 将检索结果智能整理为结构化资料

---

## 技术架构

```
OpinionSystem
├── 数据层
│   ├── TRS原始数据 (Excel)
│   ├── PostgreSQL数据库
│   └── LanceDB向量数据库
├── 处理层
│   ├── 数据合并引擎
│   ├── 数据清洗引擎
│   ├── AI筛选引擎 (Qwen)
│   └── 向量化引擎
├── 分析层
│   ├── 情感分析
│   ├── 话题分类
│   ├── 地域分析
│   ├── 关键词提取
│   ├── 趋势分析
│   └── 内容编码分析
├── 解读层
│   ├── 智能解读引擎
│   ├── TagRAG集成
│   └── 多维度解读
└── 检索层
    ├── TagRAG检索
    └── RouterRAG检索
        ├── GraphRAG (知识图谱)
        ├── NormalRAG (语义向量)
        └── TagRAG (标签向量)
```

### 核心技术栈
- **AI模型**: 阿里云通义千问 (Qwen-Plus, Qwen-Max)
- **向量数据库**: LanceDB
- **关系数据库**: PostgreSQL
- **数据处理**: Pandas, openpyxl
- **词云生成**: wordcloud, jieba
- **日志系统**: 彩色日志 + 文件持久化

---

## 快速开始

### 1. 环境准备

```bash
# 克隆项目
git clone <repository-url>
cd OpinionSystem
```

请先准备：

- Python 3.11+
- `uv`
- Node.js 18+
- 本地 PostgreSQL（推荐）

### 2. 配置数据库

数据库需要**自行在本机安装和配置**，推荐使用 **PostgreSQL**。  
项目不会自动创建数据库服务，只会读取你的本地配置并尝试连接。

编辑 `backend/configs/databases.yaml`：

```yaml
db_url: postgresql+psycopg2://postgres:your_password@localhost:5432/postgres
connections:
  - id: primary
    name: 本地PostgreSQL
    engine: postgresql
    url: postgresql+psycopg2://postgres:your_password@localhost:5432/postgres
    description: 本地开发数据库
active: primary
```

### 3. 推荐启动方式

Windows：

```bat
start_win.bat
```

macOS / Linux：

```bash
./start_mac.sh
```

通用方式：

```bash
python run.py
```

脚本会在启动前检查 `uv pip`、`npm`、当前激活数据库连接以及当前主机对应的 PyTorch/CUDA 方案；如果本地数据库未安装、未启动，或 `backend/configs/databases.yaml` 配置错误，会直接提示你先处理。
如果是 Windows 且检测到 NVIDIA GPU，但系统没有 CUDA，脚本会直接退出并提示先安装 CUDA 11.8+。

### 4. 手动方式（备选）

Windows，无 NVIDIA GPU / 不准备使用 CUDA：

```powershell
uv pip install --python .venv\Scripts\python.exe -r backend\requirements.txt
uv pip install --python .venv\Scripts\python.exe --index-url https://download.pytorch.org/whl/cpu torch torchvision torchaudio
.venv\Scripts\python.exe backend\server.py
```

Windows，已安装 NVIDIA GPU 且系统已装 CUDA 11.8+：

```powershell
uv pip install --python .venv\Scripts\python.exe -r backend\requirements.txt
uv pip install --python .venv\Scripts\python.exe --index-url https://download.pytorch.org/whl/cu118 torch torchvision torchaudio
.venv\Scripts\python.exe backend\server.py
```

macOS：

```bash
uv pip install --python .venv/bin/python -r backend/requirements.txt
uv pip install --python .venv/bin/python torch torchvision torchaudio
.venv/bin/python backend/server.py
```

```bash
cd frontend
npm install
npm run dev
```

### 5. 准备数据

将TRS导出的Excel文件放入：
```
data/raw/{专题名称}/{日期}/
```

---

## 数据处理流水线

### 完整流水线

一键完成从原始数据到数据库存储的全流程：

```bash
python main.py DataPipeline --topic 控烟 --date 2025-01-15
```

**流程说明**:
1. 合并TRS多渠道Excel → `data/merge/`
2. 数据清洗去重 → `data/clean/`
3. AI相关性筛选 → `data/filter/`
4. 上传到数据库

### 单独步骤

#### 1. 合并数据
```bash
python main.py Merge --topic 控烟 --date 2025-01-15
```
输出: `data/merge/{专题}/{日期}/各渠道.xlsx`

#### 2. 清洗数据
```bash
python main.py Clean --topic 控烟 --date 2025-01-15
```
输出: `data/clean/{专题}/{日期}/各渠道.xlsx`

#### 3. AI筛选

**准备筛选规则**: 在 `configs/prompt/filter/` 创建 `{专题}.yaml`

```yaml
# configs/prompt/filter/控烟.yaml
system_prompt: "你是一个专业的舆情分析师"
filter_prompt: |
  请判断以下内容是否与控烟话题相关...
  
classification_prompt: |
  请对内容进行分类...
```

**执行筛选**:
```bash
python main.py Filter --topic 控烟 --date 2025-01-15
```
输出: `data/filter/{专题}/{日期}/各渠道.xlsx`

#### 4. 上传数据库
```bash
python main.py Upload --topic 控烟 --date 2025-01-15
```

#### 5. 查询数据库
```bash
python main.py Query
```
**可选参数**:
- `--json` 输出完整JSON详情
- `--save result.json` 将结果写入指定文件

---

## 数据分析功能

### 分析流水线

自动完成提数和分析的完整流程：

```bash
python main.py AnalyzePipeline --topic 控烟 --start 2025-01-01 --end 2025-01-31
```

**流程说明**:
1. 从数据库提取数据 → `data/fetch/`
2. 运行7大分析功能 → `data/analyze/`

### 单独操作

#### 1. 从数据库提数
```bash
python main.py Fetch --topic 控烟 --start 2025-01-01 --end 2025-01-31
```
输出: `data/fetch/{专题}/{时间范围}/各渠道.csv`

#### 1.1 查询可用日期区间
在提数前可以先确认数据库中每个渠道/专题的可用时间范围，避免输入无数据的区间。

```bash
# 查询整个专题的可用区间
python main.py FetchAvailability --topic 控烟

# 仅查看单个渠道表
python main.py FetchAvailability --topic 控烟 --table 新闻
```
**可选参数**:
- `--json` 输出JSON格式的区间明细

#### 2. 数据分析

**运行全部分析**:
```bash
python main.py Analyze --topic 控烟 --start 2025-01-01 --end 2025-01-31
```

**运行单个分析**:
```bash
# 情感分析
python main.py Analyze --topic 控烟 --start 2025-01-01 --end 2025-01-31 --func attitude

# 话题分类
python main.py Analyze --topic 控烟 --start 2025-01-01 --end 2025-01-31 --func classification

# 地域分析
python main.py Analyze --topic 控烟 --start 2025-01-01 --end 2025-01-31 --func geography

# 关键词分析
python main.py Analyze --topic 控烟 --start 2025-01-01 --end 2025-01-31 --func keywords

# 发布者分析
python main.py Analyze --topic 控烟 --start 2025-01-01 --end 2025-01-31 --func publishers

# 趋势分析
python main.py Analyze --topic 控烟 --start 2025-01-01 --end 2025-01-31 --func trends

# 声量分析
python main.py Analyze --topic 控烟 --start 2025-01-01 --end 2025-01-31 --func volume
```

输出结构:
```
data/analyze/{专题}/{时间范围}/
├── attitude/        # 情感分析
├── classification/  # 话题分类
├── geography/       # 地域分析
├── keywords/        # 关键词分析
├── publishers/      # 发布者分析
├── trends/          # 趋势分析
└── volume/          # 声量分析
    ├── 微信/
    ├── 微博/
    ├── 新闻/
    ├── 视频/
    ├── 论坛/
    ├── 自媒体号/
    └── 总体/
```

---

## 内容分析功能

### 内容编码分析

基于AI的新闻内容深度编码分析，支持自定义分析维度和动态字段适配。

#### 功能特性

- **动态字段适配**: 自动识别不同专题的JSON字段结构
- **智能编码**: 基于Qwen-Plus的精准内容编码
- **批量处理**: 支持高并发批量分析（50 QPS）
- **多格式输出**: 同时生成Excel详细结果和JSON统计

#### 分析维度

**控烟专题示例**:
- **信息类别**: 控烟立场/烟草立场/其他
- **议题编码**: 1-1烟草与健康、1-2无烟立法、2-1社会公益等
- **信源编码**: 卫生部门、媒体自采、意见领袖等
- **报道体裁**: 事实性报道、观点性报道、深度综合等
- **诉求方式**: 恐怖诉求、人性诉求、行动呼吁等

#### 使用方法

**运行内容分析**:
```bash
python main.py ContentAnalyze --topic 控烟 --start 2025-01-01 --end 2025-01-31
```

**输出结果**:
```
data/contentanalyze/{专题}/{时间范围}/
├── contentanalysis.xlsx  # 详细分析结果
└── contentanalysis.json  # 字段统计分布
```

#### 配置提示词

为每个专题创建分析规则配置文件：

**文件位置**: `configs/prompt/contentanalysis/{专题}.yaml`

**配置示例**:
```yaml
# 内容分析提示词配置
system_prompt: |
  You are a strict content-coding engine. Your only job is to return a valid JSON with five fields:
  {"信息类别": "1|2|3","议题编码": ["...", "..."],"信源编码": ["...", "..."],"报道体裁": "1|2|3|4|5","诉求方式": ["...", "..."]}

analysis_prompt: |
  Coding rules (must be followed exactly, no new codes allowed）
  # ... 详细编码规则
```

#### 技术特点

- **并发控制**: 50 QPS，32条/批次
- **错误处理**: 完善的异常捕获和日志记录
- **路径管理**: 统一的相对路径管理
- **字段统计**: 自动生成多选/单选字段分布统计

---

## 数据解读功能

### 智能解读系统

基于AI的舆情分析结果智能解读，结合TagRAG背景知识，生成专业的解读报告。

#### 功能特性

- **智能解读**: 基于Qwen-Plus的深度解读分析
- **TagRAG集成**: 自动召回相关背景文段提供上下文
- **高并发处理**: 50并发处理渠道解读任务
- **数据检查**: 自动检查分析结果有效性，跳过无效数据
- **详细日志**: 完整的步骤跟踪和错误报告

#### 解读维度

**支持的分析类型**:
- **情感分析** (attitude): 情感倾向解读
- **话题分类** (classification): 内容分类解读
- **地域分析** (geography): 地域分布解读
- **关键词分析** (keywords): 关键词热点解读
- **发布者分析** (publishers): 发布机构解读
- **趋势分析** (trends): 时间趋势解读
- **声量分析** (volume): 声量分布解读
- **内容分析** (contentanalyze): 内容编码解读

#### 使用方法

**运行完整解读**:
```bash
python main.py Explain --topic 控烟 --start 2025-01-01 --end 2025-01-31
```

**运行单个解读**:
```bash
# 声量分析解读
python main.py Explain --topic 控烟 --start 2025-01-01 --end 2025-01-31 --func volume

# 情感态度解读
python main.py Explain --topic 控烟 --start 2025-01-01 --end 2025-01-31 --func attitude

# 趋势分析解读
python main.py Explain --topic 控烟 --start 2025-01-01 --end 2025-01-31 --func trends

# 关键词分析解读
python main.py Explain --topic 控烟 --start 2025-01-01 --end 2025-01-31 --func keywords

# 地域分析解读
python main.py Explain --topic 控烟 --start 2025-01-01 --end 2025-01-31 --func geography

# 发布者分析解读
python main.py Explain --topic 控烟 --start 2025-01-01 --end 2025-01-31 --func publishers

# 话题分类解读
python main.py Explain --topic 控烟 --start 2025-01-01 --end 2025-01-31 --func classification

# 内容分析解读
python main.py Explain --topic 控烟 --start 2025-01-01 --end 2025-01-31 --func contentanalyze
```

**输出结果**:
```
data/explain/{专题}/{时间范围}/
├── volume/          # 声量分析解读
│   ├── 总体/volume.json
│   ├── 微信/volume.json
│   ├── 微博/volume.json
│   └── ...
├── attitude/        # 情感态度解读
│   ├── 总体/attitude.json
│   ├── 微信/attitude.json
│   ├── 微博/attitude.json
│   └── ...
├── trends/          # 趋势分析解读
│   ├── 总体/trends.json
│   ├── 微信/trends.json
│   └── ...
├── keywords/        # 关键词分析解读
│   ├── 总体/keywords.json
│   ├── 微信/keywords.json
│   └── ...
├── geography/       # 地域分析解读
│   ├── 总体/geography.json
│   └── ...
├── publishers/      # 发布者分析解读
│   ├── 总体/publishers.json
│   └── ...
├── classification/  # 话题分类解读
│   ├── 总体/classification.json
│   └── ...
└── contentanalyze/  # 内容分析解读
    ├── 微信/contentanalyze.json
    └── ...
```

#### 配置解读提示词

为每个专题创建解读规则配置文件：

**文件位置**: `configs/prompt/explain/{专题}.yaml`

**配置示例**:
```yaml
# 解读提示词配置
prompts:
  attitude:
    system: |
      你是一个专业的舆情分析师，专门负责解读情感态度分析数据。请根据提供的情感数据，生成专业、客观、有洞察力的解读报告。
    user: |
      请分析以下情感态度数据，生成专业的解读报告：
      
      数据：{data}
      
      要求：
      1. 分析情感分布的整体态势
      2. 识别情感倾向的主要特征
      3. 分析情感分布的原因和影响
      4. 提供情感管理的建议
      5. 输出格式为JSON，包含title、summary、insights、recommendations字段

  keywords:
    system: |
      你是一个专业的舆情分析师，专门负责解读关键词分析数据。请根据提供的关键词数据，生成专业、客观、有洞察力的解读报告。
    user: |
      请分析以下关键词数据，生成专业的解读报告：
      
      数据：{data}
      
      要求：
      1. 分析关键词的分布特征
      2. 识别核心关注点和热点话题
      3. 分析关键词背后的社会心理
      4. 提供话题引导建议
      5. 输出格式为JSON，包含title、summary、insights、recommendations字段
```

#### 解读流程

1. **数据检查**: 检查分析结果JSON文件是否存在且有效
2. **TagRAG召回**: 根据专题和功能召回相关背景文段
3. **提示词构建**: 结合分析数据和背景信息构建完整提示词
4. **AI解读**: 使用Qwen-Plus生成专业解读报告
5. **结果保存**: 保存为JSON格式的解读结果

#### 技术特点

- **智能检查**: 自动检查分析结果有效性，跳过无效数据
- **TagRAG集成**: 每个解读都会召回相关背景文段
- **配置驱动**: 使用llm.yaml中的explain_llm配置
- **高并发**: 50并发处理渠道解读任务
- **详细日志**: 完整的步骤跟踪和错误报告
- **错误容错**: 单个解读失败不影响其他解读继续执行

#### 解读输出格式

```json
{
  "title": "情感态度解读",
  "summary": "整体情感分布呈现中性为主的特征...",
  "insights": [
    "中性情感占主导地位，说明公众对话题保持理性态度",
    "负面情感占比较低，表明话题争议性不强"
  ],
  "recommendations": [
    "继续保持中性传播策略",
    "关注负面情感的具体原因"
  ]
}
```

---

## RAG检索系统

### TagRAG - 标签检索系统

适用于简单、快速的标签匹配检索。

#### 向量化
```bash
python main.py TagVectorize --topic 控烟
```

#### 检索
```bash
python main.py TagRetrieve \
  --query "控烟政策的实施效果" \
  --topic 控烟 \
  --top-k 5
```

**参数说明**:
- `--query`: 查询语句
- `--topic`: 主题名称
- `--search-column`: 搜索列 (tag_vec 或 text_vec)
- `--top-k`: 返回结果数量
- `--return-columns`: 返回字段 (如: id,text,tag)

---

### RouterRAG - 混合检索系统

集成GraphRAG、NormalRAG、TagRAG的高级检索系统。

#### 1. 准备文本数据

在主题数据库目录下创建文本文件：

```
src/utils/rag/ragrouter/{主题}数据库/normal_db/text_db/
├── doc1_{文档名}_text1.txt
├── doc1_{文档名}_text2.txt
├── doc2_{文档名}_text1.txt
└── ...
```

**文件命名规范**:
- 格式: `doc{编号}_{文档名}_text{编号}.txt`
- 例如: `doc1_2024年控烟报告_text1.txt`

#### 2. 配置提示词

创建 `configs/prompt/router_vec/{主题}.yaml`:

```yaml
# 实体关系提取提示词
entity_relation_extraction:
  prompt: |
    请从以下文本中提取实体和关系...

# 文本标签生成提示词  
text_tagging:
  prompt: |
    请为以下文本生成简洁的标签...
```

创建 `configs/prompt/router_retrieve/{主题}.yaml`:

```yaml
# 时间提取提示词
time_extraction:
  prompt: |
    请从查询中提取时间信息...

# 时间匹配提示词
time_matching:
  prompt: |
    请判断查询时间与文档时间的匹配关系...

# 结果整理提示词（严格模式）
result_summary_strict:
  prompt: |
    根据检索到的资料回答问题...

# 结果整理提示词（补充模式）
result_summary_supplement:
  prompt: |
    结合资料和知识库回答问题...
```

#### 3. 向量化处理

```bash
python main.py RouterVectorize --topic 控烟
```

**处理流程**:
1. 文本处理: 清洗、合并、切句
2. 实体关系提取: 使用Qwen-Plus提取知识图谱
3. 向量生成: 生成实体、关系、句子、标签向量
4. 数据去重: 实体和关系的智能去重
5. 存储: 保存到LanceDB向量数据库

**输出结构**:
```
src/utils/rag/ragrouter/{主题}数据库/
├── normal_db/
│   ├── text_db/          # 原始文本
│   ├── doc_db/           # 文档级文本
│   ├── sentence_db/      # 句子级文本
│   ├── entities_db/      # 提取的实体
│   ├── relationships_db/ # 提取的关系
│   └── log_db/          # 映射和日志
│       └── data_mapping.json
└── vector_db/           # LanceDB向量数据库
    ├── normalrag        # 句子向量表
    ├── graphrag_entities      # 实体向量表
    ├── graphrag_relationships # 关系向量表
    └── graphrag_texts         # 文本标签向量表
```

#### 4. 检索查询

**基础检索**:
```bash
python main.py RouterRetrieve \
  --topic 控烟 \
  --query "2024年控烟政策的实施效果如何？"
```

**完整参数示例**:
```bash
python main.py RouterRetrieve \
  --topic 控烟 \
  --query "分析青少年控烟传播策略的效果" \
  --mode mixed \
  --topk-graphrag 3 \
  --topk-normalrag 10 \
  --topk-tagrag 3 \
  --llm-summary-mode supplement \
  --return-format both
```

**参数说明**:

| 参数 | 说明 | 可选值 | 默认值 |
|------|------|--------|--------|
| `--topic` | 检索主题 | 任意字符串 | 必填 |
| `--query` | 查询语句 | 任意字符串 | 必填 |
| `--mode` | 检索模式 | mixed/graphrag/normalrag/tagrag | mixed |
| `--topk-graphrag` | GraphRAG核心实体数 | 整数 | 3 |
| `--topk-normalrag` | NormalRAG句子数 | 整数 | 10 |
| `--topk-tagrag` | TagRAG文本块数 | 整数 | 3 |
| `--no-llm-summary` | 禁用LLM整理 | 标志 | false |
| `--llm-summary-mode` | LLM整理模式 | strict/supplement | supplement |
| `--return-format` | 返回格式 | both/llm_only/index_only | both |

**检索模式说明**:

1. **mixed** (混合模式): 同时使用三种检索策略
   - GraphRAG: 提取核心实体及其关系网络
   - NormalRAG: 检索语义相关的句子
   - TagRAG: 检索相关的文本块

2. **graphrag** (知识图谱模式): 仅使用GraphRAG
   - 适用于: 实体关系查询、多跳推理

3. **normalrag** (语义检索模式): 仅使用NormalRAG
   - 适用于: 精确语义匹配

4. **tagrag** (标签检索模式): 仅使用TagRAG
   - 适用于: 快速话题匹配

**返回格式说明**:

1. **both**: 返回索引结果 + LLM整理结果
2. **llm_only**: 仅返回LLM整理的结构化资料
3. **index_only**: 仅返回原始检索结果

**检索输出示例**:

```json
{
  "query_topic": "控烟",
  "query_text": "2024年控烟政策的实施效果如何？",
  "search_mode": "mixed",
  "time_filter": {
    "has_time": true,
    "time_text": "2024年",
    "matched_docs": ["1", "5", "8"]
  },
  "graphrag": {
    "entities": {
      "core": [...],      // 核心实体
      "extended": [...]   // 扩展实体
    },
    "relationships": {
      "all": [...],       // 所有关系
      "top3": [...]       // Top3关键关系
    }
  },
  "normalrag": {
    "sentences": [...]    // 相关句子
  },
  "tagrag": {
    "text_blocks": [...]  // 相关文本块
  },
  "llm_summary": "..."    // LLM整理的结构化资料
}
```

---

## 项目结构

```
OpinionSystem/
├── run.py                      # 跨平台快速启动与环境检查
├── start_win.bat              # Windows 快速启动入口
├── start_mac.sh               # macOS / Linux 快速启动入口
├── config.yaml                # 前后端基础运行地址配置
├── backend/
│   ├── server.py              # Web 服务入口
│   ├── main.py                # CLI 流水线入口
│   ├── requirements.txt       # 后端依赖列表
│   ├── configs/               # 后端配置文件
│   │   ├── analysis.yaml      # 分析功能配置
│   │   ├── channels.yaml      # 渠道映射配置
│   │   ├── databases.yaml     # 数据库配置
│   │   ├── explain.yaml       # 解读功能配置
│   │   ├── llm.yaml           # LLM模型配置
│   │   └── prompt/            # 提示词模板
│   ├── data/                  # 项目数据与运行产物
│   ├── logs/                  # 日志目录
│   ├── server_support/        # 服务辅助模块
│   └── src/                   # 后端核心模块
├── frontend/
│   ├── package.json           # 前端依赖与脚本
│   ├── vite.config.js         # Vite 配置
│   └── src/                   # Vue 前端源码
└── README.md                  # 项目文档
```

---

## 配置说明

### 1. LLM配置 (`backend/configs/llm.yaml`)

```yaml
# 数据筛选使用的模型
filter_llm:
  model: qwen-plus
  max_tokens: 2000

# 数据分析使用的模型
analyze_llm:
  model: qwen-max
  max_tokens: 16000

# 向量化使用的模型
vectorize_llm:
  model: qwen-plus
  max_tokens: 4000

# Router检索使用的模型
router_retrieve_llm:
  model: qwen-plus
  max_tokens: 3000

# 数据解读使用的模型
explain_llm:
  provider: qwen
  model: qwen-plus
  qps: 50
  batch_size: 32
  max_tokens: 2000

# 向量模型
embedding_llm:
  model: text-embedding-v4
```

### 2. 分析配置 (`backend/configs/analysis.yaml`)

```yaml
# 可用的分析功能列表
available_functions:
  - attitude      # 情感分析
  - classification # 话题分类
  - geography     # 地域分析
  - keywords      # 关键词分析
  - publishers    # 发布者分析
  - trends        # 趋势分析
  - volume        # 声量分析

# 关键词分析配置
keywords:
  top_k: 20       # 提取Top20关键词
  min_freq: 2     # 最小词频
```

### 3. 解读配置 (`backend/configs/explain.yaml`)

```yaml
# 解读函数配置
functions:
  # 总体解读函数
  - name: volume
    target: 总体
  - name: attitude
    target: 总体
  - name: trends
    target: 总体
  - name: keywords
    target: 总体
  - name: geography
    target: 总体
  - name: publishers
    target: 总体
  - name: classification
    target: 总体

  # 渠道解读函数
  - name: attitude
    target: 渠道
  - name: trends
    target: 渠道
  - name: keywords
    target: 渠道
  - name: geography
    target: 渠道
  - name: publishers
    target: 渠道
  - name: classification
    target: 渠道
  - name: contentanalyze
    target: 渠道
```

### 4. 渠道配置 (`backend/configs/channels.yaml`)

```yaml
channels:
  微信: wechat
  微博: weibo
  新闻app: news_app
  新闻网站: news_web
  电子报: epaper
  视频: video
  论坛: forum
  自媒体号: self_media
```

---

## 日志管理

### 日志特性

- ✅ **彩色输出**: 成功(绿色)、失败(红色)
- ✅ **文件持久化**: 按主题和日期归档
- ✅ **统一格式**: `[模块]-success|fail 简洁描述`
- ✅ **详细追踪**: 包含时间戳、日志级别、详细信息

### 日志位置

```
logs/
├── RouterVectorize_{主题}/
│   └── {日期}/
│       └── RouterVectorize_{主题}_{日期}.log
└── RagRouter_{主题}/
    └── {日期}/
        └── RagRouter_{主题}_{日期}.log
```

### 日志示例

```
[RouterVectorize]-success 载入表: normalrag (1250条)
[RouterRetrieve]-success [GraphRAG]召回: 实体数-15 | 关系数-28
[RouterRetrieve]-success [NormalRAG]召回: 句子数-10
[RouterRetrieve]-success [TagRAG]召回: 文本块数-3
[RouterRetrieve]-success 资料整理完成：共 (2847字)
```

---

## 常见问题

### Q: 向量化时提示"数据库不存在"
**A**: 需要先创建主题数据库目录和文本文件：
```bash
mkdir -p src/utils/rag/ragrouter/{主题}数据库/normal_db/text_db
# 然后将文本文件放入text_db目录
```

### Q: 检索时返回空结果
**A**: 检查以下几点：
1. 是否已完成向量化处理
2. 向量数据库是否存在
3. 提示词配置是否正确
4. 查询语句是否合理

### Q: LLM整理超时
**A**: 减少topk参数或使用 `--no-llm-summary` 跳过LLM整理

### Q: 如何更新已有的向量数据库
**A**: RouterRAG支持增量更新，直接在text_db添加新文件后重新向量化即可

---

## 开发规范

### 代码风格
- 遵循PEP 257文档字符串规范
- 每个模块开头包含三引号说明
- 使用类型注解
- 统一使用logger系统输出日志

### 日志规范
```python
from src.utils.logging.logging import setup_logger, log_success, log_error

logger = setup_logger("模块名", "日期")
log_success(logger, "操作成功描述", "模块")
log_error(logger, "错误描述", "模块")
```

---

## 许可证

本项目仅供内部使用。

---

## 联系方式

如有问题或建议，请联系项目维护团队。

---

**最后更新**: 2025-01-12
