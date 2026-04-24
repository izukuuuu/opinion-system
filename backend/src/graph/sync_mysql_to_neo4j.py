"""
从 MySQL 增量同步到 Neo4j：Post、Account、Platform 及 POSTED、IN_PLATFORM。
与 Upload 产出对齐（同一批写入 MySQL 的数据）；幂等使用 MERGE。
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd

from ..utils.setting.paths import bucket
from ..utils.io.db import db_manager
from ..utils.logging.logging import setup_logger, log_module_start, log_success, log_error
from .config import get_graph_config, is_neo4j_configured
from .neo4j_client import get_driver, get_session
from .schema import init_schema
from . import chunk_embedding as chunk_module
from . import entity_extraction as entity_module

LOG = logging.getLogger(__name__)


def _post_global_id(topic: str, channel: str, row_id: str) -> str:
    """全局唯一 Post id，避免多专题/多表冲突。"""
    return f"{topic}_{channel}_{row_id}"


def _account_id(topic: str, author: str) -> str:
    """Account 节点唯一 id：topic + author 的稳定标识。"""
    if not author or not str(author).strip():
        author = "__unknown__"
    return f"{topic}_{author}"


def _safe_str(v: Any) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    return s if s else ""


def _safe_ts(v: Any) -> Optional[str]:
    if v is None:
        return None
    try:
        return str(v)
    except Exception:
        return None


def _extract_llm_worker(contents: str) -> Dict[str, Any]:
    """Helper for concurrent LLM extraction."""
    try:
        if not contents:
            return {}
        return entity_module.extract_with_llm(contents)
    except Exception:
        return {}

def sync_after_upload(
    topic: str,
    date: str,
    dataset_name: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
    *,
    init_schema_if_missing: bool = True,
    enable_entity_extraction: bool = False,
    enable_chunk_embedding: bool = False,
    enable_llm_extraction: bool = False,
    source_bucket: str = "filter",
) -> Dict[str, Any]:
    """
    在 Upload 成功后调用：将本批 MySQL 数据同步到 Neo4j。
    topic、date、dataset_name 与 upload_filtered_excels 一致。
    仅同步 Post、Account、Platform 及 POSTED、IN_PLATFORM；
    若 enable_entity_extraction / enable_chunk_embedding 为 True 则调用对应模块（见后续实现）。
    """
    if logger is None:
        logger = setup_logger(topic, date)
    log_module_start(logger, "GraphSync")

    if not is_neo4j_configured():
        log_error(logger, "Neo4j 未配置，跳过图同步", "GraphSync")
        return {"status": "skipped", "message": "Neo4j 未配置"}

    target_database = (dataset_name or topic).strip() or topic
    
    # Handle custom source path
    if source_bucket == "custom" and dataset_name:
        custom_path = Path(dataset_name)
        if custom_path.is_file():
            filter_dir = custom_path.parent
            # Only process this specific file
            if custom_path.suffix.lower() == '.jsonl':
                jsonl_files = [custom_path]
                csv_files = []
            elif custom_path.suffix.lower() == '.csv':
                jsonl_files = []
                csv_files = [custom_path]
            else:
                log_error(logger, f"不支持的文件类型: {custom_path}", "GraphSync")
                return {"status": "error", "message": "不支持的文件类型"}
        elif custom_path.is_dir():
            filter_dir = custom_path
            jsonl_files = list(filter_dir.glob("*.jsonl"))
            csv_files = list(filter_dir.glob("*.csv"))
        else:
             log_error(logger, f"路径不存在: {custom_path}", "GraphSync")
             return {"status": "error", "message": "路径不存在"}
    else:
        filter_dir = bucket(source_bucket, topic, date)
        jsonl_files = list(filter_dir.glob("*.jsonl")) if filter_dir.exists() else []
        csv_files = list(filter_dir.glob("*.csv")) if filter_dir.exists() else []

    if not jsonl_files and not csv_files:
        log_error(logger, f"未找到 {source_bucket} 产物 {filter_dir} (jsonl or csv)，无法确定本批表", "GraphSync")
        return {"status": "error", "message": f"未找到 {source_bucket} 产物"}

    files_to_process = []
    if jsonl_files:
        files_to_process.extend([(f, 'jsonl') for f in jsonl_files])
    # If no JSONL, try CSV (direct file mode)
    elif csv_files:
        files_to_process.extend([(f, 'csv') for f in csv_files])

    engine = None
    try:
        engine = db_manager.get_engine_for_database(target_database)
    except Exception as exc:
        if jsonl_files:
            log_error(logger, f"无法连接 MySQL 数据库 {target_database}: {exc}", "GraphSync")
            return {"status": "error", "message": str(exc)}
        else:
            LOG.warning(f"无法连接 MySQL ({exc})，将尝试直接读取 CSV 文件")

    cfg = get_graph_config()
    batch_size = int(cfg.get("sync_batch_size") or 1000)
    enable_entity = bool(cfg.get("enable_entity_extraction", False)) or enable_entity_extraction
    enable_chunk = bool(cfg.get("enable_chunk_embedding", False)) or enable_chunk_embedding

    try:
        if init_schema_if_missing:
            init_schema()
    except Exception as exc:
        log_error(logger, f"Neo4j 连接或初始化失败: {exc}", "GraphSync")
        return {"status": "error", "message": str(exc)}

    total_posts = 0
    total_chunks = 0
    total_mentions = 0
    with get_session() as session:
        for file_path, file_type in files_to_process:
            table_name = file_path.stem
            channel = table_name
            df = None
            
            try:
                if file_type == 'jsonl' and engine:
                    df = pd.read_sql(f"SELECT * FROM `{table_name}`", con=engine)
                elif file_type == 'csv':
                    df = pd.read_csv(file_path)
                    # Normalize columns if needed to match DB schema expectations
                    # Ensure 'id' exists
                    if 'id' not in df.columns and 'post_id' in df.columns:
                        df['id'] = df['post_id']
                elif file_type == 'jsonl':
                    # Fallback if engine is missing but jsonl exists (unlikely to work if data is expected in DB)
                    LOG.warning(f"Skipping {file_path} because MySQL engine is not available")
                    continue
            except Exception as exc:
                log_error(logger, f"读取数据失败 {file_path}: {exc}", "GraphSync")
                continue

            if df is None or len(df) == 0:
                continue
            
            # Ensure columns exist to avoid KeyErrors
            expected_cols = ['id', 'author', 'title', 'contents', 'platform', 'published_at', 'url', 'region', 'hit_words', 'polarity', 'classification']
            for col in expected_cols:
                if col not in df.columns:
                    df[col] = None

            total_rows = len(df)
            print(f"开始处理 {file_path.name}, 共 {total_rows} 条数据 (Start processing {total_rows} rows)...")

            # 调整 batch_size 以适应并发 (如果开启 LLM，batch 不宜过大，避免内存积压)
            process_batch_size = 20 if enable_llm_extraction else batch_size

            for start in range(0, len(df), process_batch_size):
                batch = df.iloc[start : start + process_batch_size]
                
                # Pre-fetch LLM results concurrently if enabled
                llm_results = {}
                if enable_llm_extraction:
                    with ThreadPoolExecutor(max_workers=10) as executor:
                        future_to_idx = {
                            executor.submit(_extract_llm_worker, _safe_str(row.get("contents"))): idx 
                            for idx, row in batch.iterrows()
                        }
                        for future in as_completed(future_to_idx):
                            idx = future_to_idx[future]
                            try:
                                llm_results[idx] = future.result()
                            except Exception as e:
                                LOG.warning(f"LLM extraction failed for row {idx}: {e}")

                for idx, row in batch.iterrows():
                    post_id_raw = row.get("id")
                    if post_id_raw is None or str(post_id_raw).strip() == "":
                        continue
                    post_global_id = _post_global_id(topic, channel, _safe_str(post_id_raw))
                    author = _safe_str(row.get("author"))
                    account_id = _account_id(topic, author)
                    
                    # 优先使用数据中的 platform 字段，如果为空则回退到 channel (文件名)
                    row_platform = _safe_str(row.get("platform"))
                    actual_platform = row_platform if row_platform else channel

                    # MERGE Platform
                    session.run(
                        "MERGE (p:Platform {name: $name}) SET p.name = $name",
                        {"name": actual_platform},
                    )
                    # MERGE Account
                    session.run(
                        """
                        MERGE (a:Account {id: $id})
                        SET a.topic = $topic, a.author = $author
                        """,
                        {"id": account_id, "topic": topic, "author": author or "__unknown__"},
                    )
                    # MERGE Post
                    session.run(
                        """
                        MERGE (p:Post {id: $id})
                        SET p.topic = $topic, p.channel = $channel,
                            p.title = $title, p.contents = $contents, p.platform = $platform,
                            p.author = $author, p.published_at = $published_at, p.url = $url,
                            p.region = $region, p.hit_words = $hit_words, p.polarity = $polarity,
                            p.classification = $classification
                        """,
                        {
                            "id": post_global_id,
                            "topic": topic,
                            "channel": channel,
                            "title": _safe_str(row.get("title")),
                            "contents": _safe_str(row.get("contents")),
                            "platform": actual_platform,
                            "author": author or "__unknown__",
                            "published_at": _safe_ts(row.get("published_at")),
                            "url": _safe_str(row.get("url")),
                            "region": _safe_str(row.get("region")),
                            "hit_words": _safe_str(row.get("hit_words")),
                            "polarity": _safe_str(row.get("polarity")),
                            "classification": _safe_str(row.get("classification")) or "未知",
                        },
                    )
                    # (Account)-[:POSTED]->(Post)
                    session.run(
                        """
                        MATCH (a:Account {id: $aid}), (p:Post {id: $pid})
                        MERGE (a)-[:POSTED]->(p)
                        """,
                        {"aid": account_id, "pid": post_global_id},
                    )
                    # (Post)-[:IN_PLATFORM]->(Platform)
                    session.run(
                        """
                        MATCH (p:Post {id: $pid}), (pl:Platform {name: $name})
                        MERGE (p)-[:IN_PLATFORM]->(pl)
                        """,
                        {"pid": post_global_id, "name": actual_platform},
                    )
                    total_posts += 1

                    # Chunk 与 Entity/Topic（在 Post 写入后）
                    row_dict = row.to_dict() if hasattr(row, "to_dict") else dict(row)
                    if enable_chunk:
                        try:
                            n = chunk_module.write_chunks_for_post(
                                topic, channel,
                                str(post_id_raw), _safe_str(row.get("contents")),
                            )
                            total_chunks += n
                        except Exception as e:
                            LOG.warning("Chunk for post %s failed: %s", post_global_id, e)
                        if enable_entity:
                            try:
                                # 如果开启了 LLM，直接使用预取的结果
                                pre_fetched_res = llm_results.get(idx) if enable_llm_extraction else None
                                
                                m, _ = entity_module.run_entity_extraction_for_sync(
                                    topic, channel, [row_dict], 
                                    enable_llm=enable_llm_extraction,
                                    pre_fetched_llm_result=pre_fetched_res
                                )
                                total_mentions += m
                            except Exception as e:
                                LOG.warning("Entity/Topic for post %s failed: %s", post_global_id, e)

                    if total_posts % 50 == 0:
                        print(f"  已处理 {total_posts}/{total_rows} 条 Post (Processed {total_posts}/{total_rows})...")

        log_success(logger, f"图同步完成: Post={total_posts}, Chunk={total_chunks}, MENTIONS={total_mentions} (Graph sync completed)", "GraphSync")

    engine.dispose()
    return {
        "status": "ok",
        "message": f"已同步 {total_posts} 条 Post (Synced {total_posts} posts)",
        "total_posts": total_posts,
        "total_chunks": total_chunks,
        "total_mentions": total_mentions,
    }
