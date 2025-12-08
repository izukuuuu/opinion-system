#!/usr/bin/env python3
"""
模拟server.py的导入方式测试BERTopic
"""

import sys
import os
from pathlib import Path

# 模拟server.py的路径设置
backend_dir = Path(__file__).parent
SRC_DIR = backend_dir / "src"

if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

print(f"SRC_DIR: {SRC_DIR}")
print(f"Python path includes: {SRC_DIR}")

# 测试导入
try:
    print("\n1. 测试导入 fetch.data_fetch...")
    from fetch.data_fetch import get_topic_available_date_range
    print("✅ 成功导入 fetch.data_fetch")
except ImportError as e:
    print(f"❌ 导入失败: {e}")

# 检查BERTopic是否安装
print("\n2. 检查BERTopic依赖...")
try:
    import bertopic
    print("✅ bertopic 已安装")
except ImportError:
    print("❌ bertopic 未安装，需要运行:")
    print("   pip install bertopic")

print("\n3. 测试导入 topic.data_bertopic_qwen_v2（跳过bertopic依赖）...")
try:
    # 先尝试直接导入，看看具体的错误
    import importlib.util

    # 检查文件是否存在
    bertopic_file = SRC_DIR / "topic" / "data_bertopic_qwen_v2.py"
    print(f"文件路径: {bertopic_file}")
    print(f"文件存在: {bertopic_file.exists()}")

    if bertopic_file.exists():
        print("\n文件存在，检查前几行是否有语法错误...")
        with open(bertopic_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()[:50]  # 读取前50行
            for i, line in enumerate(lines, 1):
                if "import" in line and ("bertopic" in line.lower() or "jieba" in line.lower()):
                    print(f"第{i}行: {line.strip()}")

except Exception as e:
    print(f"检查时出错: {e}")

# 检查fetch模块
print("\n4. 检查fetch模块...")
fetch_dir = SRC_DIR / "fetch"
print(f"fetch目录: {fetch_dir}")
print(f"fetch目录存在: {fetch_dir.exists()}")

if fetch_dir.exists():
    files = list(fetch_dir.glob("*.py"))
    print(f"fetch目录中的Python文件: {[f.name for f in files]}")

# 检查topic模块
print("\n5. 检查topic模块...")
topic_dir = SRC_DIR / "topic"
print(f"topic目录: {topic_dir}")
print(f"topic目录存在: {topic_dir.exists()}")

if topic_dir.exists():
    files = list(topic_dir.glob("*.py"))
    print(f"topic目录中的Python文件: {[f.name for f in files]}")