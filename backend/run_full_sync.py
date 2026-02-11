import sys
import os
import shutil
import asyncio
from pathlib import Path

# 将 backend 目录加入 Python 路径，确保可以导入 src 模块
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.clean.data_clean import run_clean
from src.filter.data_filter import run_filter_async
from src.graph.sync_mysql_to_neo4j import sync_after_upload
from src.utils.setting.paths import bucket

# 项目配置
TOPIC = "20251103-130902-新建专题"
DATE = "2025-09-23_2025-09-23"

def fix_merge_directory():
    """
    修复 Merge 目录结构：
    如果 JSONL 文件直接位于 merge/ 根目录下，将它们移动到 merge/<DATE>/ 子目录，
    以便 data_clean.py 能正确找到它们。
    """
    target_dir = bucket("merge", TOPIC, DATE)
    merge_root = target_dir.parent  # .../projects/.../merge
    
    if not merge_root.exists():
        print(f"Merge root {merge_root} does not exist.")
        return

    # 检查 merge 根目录下是否有 jsonl 文件
    jsonl_files = list(merge_root.glob("*.jsonl"))
    if jsonl_files:
        print(f"Found {len(jsonl_files)} JSONL files in {merge_root}, moving to {target_dir}")
        target_dir.mkdir(parents=True, exist_ok=True)
        for f in jsonl_files:
            try:
                shutil.move(str(f), str(target_dir / f.name))
                print(f"  Moved: {f.name}")
            except Exception as e:
                print(f"  Failed to move {f.name}: {e}")
    else:
        print(f"No misplaced JSONL files found in {merge_root}.")

async def main():
    print(f"=== 开始执行全流程: Topic={TOPIC}, Date={DATE} ===")
    
    # 1. 目录结构预处理
    print("\n--- Step 1: 检查并修复目录结构 ---")
    fix_merge_directory()
    
    # 2. 数据清洗 (Merge -> Clean)
    print("\n--- Step 2: 运行数据清洗 (Clean) ---")
    # 清洗模块会读取 merge/<date>/ 下的数据，输出到 clean/<date>/
    success = run_clean(TOPIC, DATE)
    if not success:
        print("❌ Data Clean failed. Aborting.")
        return
    print("✅ Data Clean completed.")

    # 3. AI 筛选 (Clean -> Filter)
    print("\n--- Step 3: 运行 AI 筛选 (Filter) ---")
    # 筛选模块读取 clean/<date>/，调用 LLM 判断相关性，输出到 filter/<date>/
    # 这一步需要确保 backend/configs/prompt/filter/ 下有对应的配置文件
    success = await run_filter_async(TOPIC, DATE)
    if not success:
        print("❌ Data Filter failed. Aborting.")
        return
    print("✅ Data Filter completed.")

    # 4. 构建知识图谱 (Filter -> Neo4j)
    print("\n--- Step 4: 构建知识图谱 (Graph Sync) ---")
    # 使用我们修改过的 sync_mysql_to_neo4j.py
    # source_bucket="filter" 指示它直接读取 filter 目录的 JSONL 文件，不查数据库
    # enable_entity_extraction=True 会触发实体抽取
    result = sync_after_upload(
        topic=TOPIC,
        date=DATE,
        dataset_name=TOPIC,
        init_schema_if_missing=True,
        enable_entity_extraction=True,
        enable_chunk_embedding=True, # 如果配置了 Embedding 模型，这里会生成向量
        source_bucket="filter"
    )
    
    print(f"\n图谱构建结果: {result}")
    if result.get("status") == "ok":
        print("✅ 全流程执行成功！知识图谱骨架已构建。")
    else:
        print(f"❌ 图谱构建遇到问题: {result.get('message')}")

if __name__ == "__main__":
    asyncio.run(main())