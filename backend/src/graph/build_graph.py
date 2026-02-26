import logging
import sys
import os
import shutil
import pandas as pd
from pathlib import Path

# Add project root to sys.path to allow imports
current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from src.graph.sync_mysql_to_neo4j import sync_after_upload
from src.graph.topic_sync import sync_bertopic_results
from src.graph.event_clustering import cluster_and_link_events
from src.graph.neo4j_client import get_driver, get_session
from src.topic.data_bertopic_qwen_v2 import run_topic_bertopic
from src.utils.setting.paths import bucket
from src.utils.logging.logging import setup_logger

def clear_graph_data(topic: str, clear_all: bool = False):
    """
    清空图谱数据。
    Args:
        topic: 专题名称 (用于删除特定专题的数据)
        clear_all: 是否清空整个数据库 (慎用)
    """
    with get_session() as session:
        if clear_all:
            print("正在清空 Neo4j 中的所有数据 (Clearing ALL data in Neo4j)...")
            session.run("MATCH (n) DETACH DELETE n")
        else:
            print(f"正在清空专题 {topic} 的数据 (Clearing data for topic: {topic})...")
            # 删除带有 topic 属性的节点
            session.run("MATCH (n) WHERE n.topic = $topic DETACH DELETE n", {"topic": topic})
            # 删除 Topic 节点 (可能属性是 project)
            session.run("MATCH (t:Topic) WHERE t.project = $topic DETACH DELETE t", {"topic": topic})
            # 注意: Platform 等共享节点通常保留
            # Chunk 节点通常通过 Post 删除级联删除，或者需要额外清理
            # 暂时假设 Chunk 通过 Post 关联被清理 (如果 Post 删除，Chunk 变成孤儿，这里没删孤儿)
            # 补充删除孤儿 Chunk (可选)
            # session.run("MATCH (c:Chunk) WHERE NOT (c)<-[:HAS_CHUNK]-() DETACH DELETE c")

def rebuild_graph(topic: str, date_range: str, use_llm: bool = False, clear_topics: bool = False, clear_graph: bool = False, clear_all_db: bool = False, source_bucket: str = "filter", skip_step1: bool = False):
    """
    全量重建知识图谱流程：
    1. (可选) 清空旧数据
    2. 同步 MySQL/Jsonl 数据 -> Neo4j (Post, Account, Platform)
    3. 执行实体/观点/事件抽取 -> Neo4j (Entity, Claim, Event, Frame)
    4. 执行文本切片 -> Neo4j (Chunk)
    5. 同步 BERTopic 结果 -> Neo4j (Topic)
    """
    logger = setup_logger(topic, date_range)
    # Initialize dataset_name_arg early to avoid UnboundLocalError
    dataset_name_arg = None
    
    print(f"开始重建图谱，专题: {topic}, 日期范围: {date_range} (Start rebuilding graph for project: {topic}, date: {date_range})")

    if clear_all_db:
        print("!!! 警告: 正在清空整个 Neo4j 数据库 (!!! WARNING: Clearing ENTIRE Neo4j database !!!)")
        clear_graph_data(topic, clear_all=True)
    elif clear_graph:
        clear_graph_data(topic, clear_all=False) # 默认只清空当前专题

    # Step 1: Base Sync + Extraction + Chunking
    # sync_after_upload 内部已经集成了 entity_extraction 和 chunk_embedding 的调用
    
    # 检查 source_bucket 是否为完整路径
    dataset_name_arg = None
    if os.path.exists(source_bucket) or "/" in source_bucket or "\\" in source_bucket:
         dataset_name_arg = source_bucket
         source_bucket = "custom" # 只是个标记，sync_after_upload 会优先使用 dataset_name_arg

    if not skip_step1:
        print("\n[Step 1] 同步基础数据 (Post/Account/Platform) + 实体抽取 + 文本切片 (Syncing Base Data + Extraction + Chunking)...")
        
        try:
            base_res = sync_after_upload(
                topic=topic,
                date=date_range,
                dataset_name=dataset_name_arg, # Use custom path if provided
                logger=logger,
                init_schema_if_missing=True,
                enable_entity_extraction=True,    # 总是启用抽取模块 (Tier 1 is mandatory)
                enable_llm_extraction=use_llm,    # 控制 Tier 2
                enable_chunk_embedding=True,      # 总是启用切片
                source_bucket=source_bucket       # 指定数据来源 (filter, clean, merge)
            )
            print(f"Step 1 结果: {base_res}")
        except Exception as e:
            print(f"Step 1 失败: {e}")
            return
    else:
        print("\n[Step 1] 跳过 (Skipped)")

    # Step 2: Run BERTopic Analysis (if needed)
    print("\n[Step 2] 检查并运行 BERTopic 分析 (Running BERTopic Analysis)...")
    topic_output_dir = bucket("topic", topic, date_range)
    
    # Prepare data for BERTopic if using custom source
    if dataset_name_arg and os.path.exists(dataset_name_arg):
        fetch_dir = bucket("fetch", topic, date_range)
        fetch_dir.mkdir(parents=True, exist_ok=True)
        target_file = fetch_dir / "总体.jsonl"
        
        if not target_file.exists():
            print(f"Converting custom source {dataset_name_arg} to {target_file} for BERTopic...")
            try:
                source_path = Path(dataset_name_arg)
                if source_path.suffix.lower() == '.csv':
                    # Force read id as string to avoid scientific notation or float conversion
                    df = pd.read_csv(source_path, dtype={'id': str, 'post_id': str})
                    # Ensure content column exists (BERTopic needs it)
                    if 'contents' not in df.columns:
                        for col in ['content', 'text', 'body', '正文']:
                            if col in df.columns:
                                df.rename(columns={col: 'contents'}, inplace=True)
                                break
                    
                    # Add channel column (filename without extension)
                    channel_name = source_path.stem
                    if 'channel' not in df.columns:
                        df['channel'] = channel_name
                        
                    df.to_json(target_file, orient='records', lines=True, force_ascii=False)
                    print(f"Conversion successful. Saved to {target_file}")
                elif source_path.suffix.lower() == '.jsonl':
                     shutil.copy2(source_path, target_file)
                     print(f"Copied jsonl to {target_file}")
            except Exception as e:
                print(f"Warning: Failed to prepare data for BERTopic: {e}")

    # Check if BERTopic results actually exist (not just the directory)
    expected_result_file = topic_output_dir / "1主题统计结果.json"
    if not topic_output_dir.exists() or not expected_result_file.exists():
        print(f"BERTopic results not found (or incomplete), running analysis now...")
        
        # Parse date range
        if "_" in date_range:
            parts = date_range.split("_")
            start_date = parts[0]
            end_date = parts[1] if len(parts) > 1 else None
        else:
            start_date = date_range
            end_date = None
            
        try:
            success = run_topic_bertopic(
                topic=topic,
                start_date=start_date,
                end_date=end_date
            )
            if not success:
                print("Step 2 Failed: BERTopic analysis returned False.")
                return
            print("Step 2: BERTopic analysis completed successfully.")
        except Exception as e:
            print(f"Step 2 Error: {e}")
            return
    else:
        print(f"Step 2 Skipped: BERTopic results already exist at {topic_output_dir}")

    # Step 3: Topic Sync (BERTopic Results -> Neo4j)
    print("\n[Step 3] Syncing BERTopic Results to Neo4j...")
    
    if topic_output_dir.exists():
        try:
            success = sync_bertopic_results(
                project_topic=topic,
                output_dir=topic_output_dir,
                clear_existing=clear_topics
            )
            if success:
                print("Step 3: BERTopic sync completed successfully.")
            else:
                print("Step 3: BERTopic sync failed (check logs).")
        except Exception as e:
            print(f"Step 3 Error: {e}")
    else:
        print(f"Step 3 Skipped: BERTopic output directory still not found: {topic_output_dir}")

    # Step 4: Event Clustering
    print("\n[Step 4] Clustering Posts into Events...")
    try:
        # Default time gap is 24 hours
        event_count = cluster_and_link_events(topic, time_threshold_hours=24)
        print(f"Step 4: Event clustering completed. Created {event_count} events.")
    except Exception as e:
        print(f"Step 4 Failed: {e}")

    print("\nGraph reconstruction process finished.")

if __name__ == "__main__":
    # 示例运行
    # python -m src.graph.rebuild_graph
    # 实际使用时请修改参数
    # rebuild_graph("新建专题", "2025-09-23_2025-09-23", use_llm=True, clear_topics=True, clear_graph=True)
    import argparse
    parser = argparse.ArgumentParser(description="Rebuild Knowledge Graph")
    parser.add_argument("--topic", type=str, required=True, help="Project/Topic name")
    parser.add_argument("--date", type=str, required=True, help="Date range (e.g. 2025-11-08)")
    parser.add_argument("--use-llm", action="store_true", help="Enable LLM extraction (Tier 2)")
    parser.add_argument("--clear-graph", action="store_true", help="Clear graph data for this topic before syncing")
    parser.add_argument("--skip-step1", action="store_true", help="Skip Step 1 (Sync Base Data)")
    parser.add_argument("--force-clear-all", action="store_true", help="DANGER: Clear ENTIRE Neo4j database")
    parser.add_argument("--source", type=str, default="filter", help="Source bucket name (filter, clean, merge) OR full directory path")
    
    args = parser.parse_args()
    
    rebuild_graph(args.topic, args.date, use_llm=args.use_llm, clear_topics=True, clear_graph=args.clear_graph, clear_all_db=args.force_clear_all, source_bucket=args.source, skip_step1=args.skip_step1)
