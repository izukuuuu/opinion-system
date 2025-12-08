#!/usr/bin/env python3
"""
测试BERTopic新实现的导入
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
backend_dir = Path(__file__).parent
project_root = backend_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

print(f"Project root: {project_root}")
print(f"Backend dir: {backend_dir}")
print(f"Python path: {sys.path[:3]}")

try:
    print("\n测试导入 fetch.data_fetch...")
    from src.fetch.data_fetch import get_topic_available_date_range
    print("✅ src.fetch.data_fetch 导入成功")

    # 测试函数是否存在
    if callable(get_topic_available_date_range):
        print("✅ get_topic_available_date_range 函数可用")
    else:
        print("❌ get_topic_available_date_range 不可调用")

except ImportError as e:
    print(f"❌ 导入 src.fetch.data_fetch 失败: {e}")
    print("\n尝试其他导入路径...")

    try:
        from backend.src.fetch.data_fetch import get_topic_available_date_range
        print("✅ backend.src.fetch.data_fetch 导入成功")
    except ImportError as e2:
        print(f"❌ 尝试 backend.src.fetch.data_fetch 也失败: {e2}")

try:
    print("\n测试导入 topic.data_bertopic_qwen_v2...")
    from src.topic.data_bertopic_qwen_v2 import run_topic_bertopic
    print("✅ src.topic.data_bertopic_qwen_v2 导入成功")

    # 测���函数是否存在
    if callable(run_topic_bertopic):
        print("✅ run_topic_bertopic 函数可用")
    else:
        print("❌ run_topic_bertopic 不可调用")

except ImportError as e:
    print(f"❌ 导入 src.topic.data_bertopic_qwen_v2 失败: {e}")
    print(f"错误详情: {type(e).__name__}: {e}")

    # 打印更详细的错误信息
    import traceback
    traceback.print_exc()

# 检查目录结构
print("\n检查目录结构:")
src_dir = project_root / "src" / "fetch"
if src_dir.exists():
    print(f"✅ src/fetch 目录存在: {src_dir}")
    init_file = src_dir / "__init__.py"
    if init_file.exists():
        print("✅ src/fetch/__init__.py 存在")
    else:
        print("❌ src/fetch/__init__.py 不存在")

    data_fetch_file = src_dir / "data_fetch.py"
    if data_fetch_file.exists():
        print("✅ src/fetch/data_fetch.py 存在")
    else:
        print("❌ src/fetch/data_fetch.py 不存在")
else:
    print(f"❌ src/fetch 目录不存在")

topic_dir = project_root / "src" / "topic"
if topic_dir.exists():
    print(f"✅ src/topic 目录存在: {topic_dir}")

    bertopic_file = topic_dir / "data_bertopic_qwen_v2.py"
    if bertopic_file.exists():
        print("✅ src/topic/data_bertopic_qwen_v2.py 存在")
    else:
        print("❌ src/topic/data_bertopic_qwen_v2.py 不存在")
else:
    print(f"❌ src/topic 目录不存在")