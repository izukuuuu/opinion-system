使用指南

### 1. 环境准备

```bash
# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
.\venv\Scripts\activate  # Windows
source venv/bin/activate  # Linux/Mac

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置

```bash
# 构造环境配置
# 创建文件 .env
# 编辑 .env 文件，填入API密钥
DASHSCOPE_API_KEY=sk-7b22413bfe8845b3bc59613d43903793
```

### 3. 操作命令

#在进行AI筛选前，可在configs/prompt/filter文件夹中，新建[话题].yaml，写入对应话题需要信息/以及分类的提示词，写好后运行下方命令

# 数据存储流水线
python main.py DataPipeline --topic 测试 --date 2025-01-01 

# 数据分析流水线
python main.py AnalyzePipeline --topic 测试 --start 2025-09-23 --end 2025-09-23



# 合并数据
python main.py Merge --topic 测试 --date 2025-01-01 

# 清洗数据
python main.py Clean --topic 测试 --date 2025-01-01

# AI筛选

#在进行AI筛选前，可在configs/prompt/filter文件夹中，新建[话题].yaml，写入对应话题需要信息/以及分类的提示词，写好后运行下方命令
python main.py Filter --topic 测试 --date 2025-01-01

# 数据上传
python main.py Upload --topic 测试 --date 2025-01-01

# 查询数据库所有数据
python main.py Query

# 提数
python main.py Fetch --topic 测试 --start 2025-09-23 --end 2025-09-23
 
# 数据分析

单功能：python main.py Analyze --topic 测试 --start 2025-09-23 --end 2025-09-23 --func attitude
联合功能：python main.py Analyze --topic 测试 --start 2025-09-23 --end 2025-09-23
