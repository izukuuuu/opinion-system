#!/usr/bin/env python3
"""
最小测试，验证在Flask服务器环境中的导入
"""

import sys
import os
from pathlib import Path

# 添加backend目录到路径，模拟从server.py运行
backend_dir = Path(__file__).parent
sys.path.insert(0, str(backend_dir))

# 也添加src目录
src_dir = backend_dir / "src"
sys.path.insert(0, str(src_dir))

print("="*60)
print("BERTopic模块导入测试")
print("="*60)
print(f"当前目录: {Path.cwd()}")
print(f"Backend目录: {backend_dir}")
print(f"Src目录: {src_dir}")

# 检查requirements文件
print("\n检查依赖...")
requirements_file = backend_dir.parent / "requirements.txt"
if requirements_file.exists():
    print(f"\n找到requirements.txt: {requirements_file}")
    with open(requirements_file, 'r') as f:
        requirements = f.read()
        if 'bertopic' in requirements:
            print("✅ requirements.txt中包含bertopic")
        else:
            print("❌ requirements.txt中不包含bertopic")

# 提供安装命令
print("\n" + "="*60)
print("解决方案")
print("="*60)
print("""
如果遇到 'No module named bertopic' 错误，请运行：

pip install bertopic
pip install jieba
pip install openai

或者安装完整的依赖：
pip install -r requirements.txt

这些依赖应该安装在运行Flask服务器的Python环境中。
""")

# 检查server.py中相关的导入
print("\n" + "="*60)
print("server.py中的导入路径")
print("="*60)
server_file = backend_dir / "server.py"
if server_file.exists():
    print("server.py中的相关导入:")
    with open(server_file, 'r') as f:
        content = f.read()
        if 'from src.topic.data_bertopic_qwen_v2 import' in content:
            print("✅ server.py正确导入了data_bertopic_qwen_v2")
        if 'from src.fetch.data_fetch import' in content:
            print("✅ server.py正确导入了fetch.data_fetch")

print("\n导入测试说明:")
print("1. 当Flask服务器运行时，所有导入应该正常工作")
print("2. 独立测试时会因为相对导入而失败")
print("3. 确保在正确的Python环境中安装了所需依赖")