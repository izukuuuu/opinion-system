"""
从 MySQL 增量同步到 Neo4j：Post、Account、Platform 及 POSTED、IN_PLATFORM。
与 Upload 产出对齐（同一批写入 MySQL 的数据）；幂等使用 MERGE。
"""
from __future__ import annotations

import logging
from pathlib import Path
import concurrent.futures
from typing import Any, Dict, List, Optional

import pandas as pd

from ..utils.setting.paths import bucket
from ..utils.io.db import db_manager
from ..utils.logging.logging import setup_logger, log_module_start, log_success, log_error
from .config import get_graph_config, is_neo4j_configured
from .neo4j_client import get_driver, get_session
from .schema import init_schema

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


def sync_after_upload(
    topic: str,
    date: str,
    dataset_name: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
    *,
    init_schema_if_missing: bool = True,
    enable_entity_extraction: bool = False,
    enable_llm_extraction: bool = False,
    enable_chunk_embedding: bool = False,
    source_bucket: str = "filter",
) -> Dict[str, Any]:
    """
    在 Upload 成功后调用：将本批 MySQL 数据同步到 Neo4j。
    topic、date、dataset_name 与 upload_filtered_excels 一致。
    source_bucket: 指定同步的数据来源，默认为 "filter"（AI筛选后的数据），可选 "clean"（清洗后的全量数据）。
    仅同步 Post、Account、Platform 及 POSTED、IN_PLATFORM；
    若 enable_entity_extraction / enable_chunk_embedding 为 True 则调用对应模块（见后续实现）。
    """
    if logger is None:
        logger = setup_logger(topic, date)
    log_module_start(logger, "GraphSync")

    cfg = get_graph_config()
    neo4j_db_name = cfg.get("database", "neo4j")
    log_success(logger, f"Neo4j 目标数据库: {neo4j_db_name}", "GraphSync")

    if not is_neo4j_configured():
        log_error(logger, "Neo4j 未配置，跳过图同步", "GraphSync")
        return {"status": "skipped", "message": "Neo4j 未配置"}

    # [Mod] 支持直接传入文件路径作为 data_dir
    # 如果 dataset_name 是一个存在的目录路径，则直接使用它
    custom_path = Path(dataset_name) if dataset_name else None
    if custom_path and custom_path.exists() and custom_path.is_dir():
        data_dir = custom_path
        target_database = topic # 只是个标识
        use_file_source = True
        log_success(logger, f"使用自定义数据目录: {data_dir}", "GraphSync")
    else:
        target_database = (dataset_name or topic).strip() or topic
        data_dir = bucket(source_bucket, topic, date)
        
        # 如果指定的目录不存在，尝试回退
        if not data_dir.exists() and source_bucket == "filter":
            logger.warning(f"未找到 filter 目录，尝试使用 clean 目录")
            data_dir = bucket("clean", topic, date)
            source_bucket = "clean"
        
        use_file_source = (source_bucket == "filter" or source_bucket == "merge")

    jsonl_files = list(data_dir.glob("*.jsonl")) if data_dir.exists() else []

    if not jsonl_files:
        log_error(logger, f"未找到数据产物 {data_dir}，无法确定本批表", "GraphSync")
        return {"status": "error", "message": f"未找到 {source_bucket} 产物"}

    table_names = [f.stem for f in jsonl_files]
    
    # [Mod] 如果是 filter/merge 模式，我们直接从 jsonl 文件读取数据进行同步，而不是从数据库
    # 因为数据库可能只存了部分数据，或者用户希望直接用文件作为源
    # use_file_source 已经在上面设置了
    
    try:
        if not use_file_source:
            engine = db_manager.get_engine_for_database(target_database)
        else:
            engine = None
    except Exception as exc:
        log_error(logger, f"无法连接 MySQL 数据库 {target_database}: {exc}", "GraphSync")
        return {"status": "error", "message": str(exc)}

    cfg = get_graph_config()
    batch_size = int(cfg.get("sync_batch_size") or 1000)
    # enable_entity controls whether to run extraction AT ALL (including NER)
    enable_entity = bool(cfg.get("enable_entity_extraction", False)) or enable_entity_extraction
    # enable_llm controls whether to upgrade to Tier 2 (LLM extraction)
    # Default to False unless explicitly enabled in config or passed as argument
    enable_llm = bool(cfg.get("enable_llm_extraction", False)) or enable_llm_extraction
    enable_chunk = bool(cfg.get("enable_chunk_embedding", False)) or enable_chunk_embedding

    # Avoid circular imports by importing optional modules lazily.
    chunk_module = None
    entity_module = None
    if enable_chunk:
        from . import chunk_embedding as chunk_module  # type: ignore[redefined-outer-name]
    if enable_entity:
        from . import entity_extraction as entity_module  # type: ignore[redefined-outer-name]

    try:
        driver = get_driver()
        if init_schema_if_missing:
            init_schema(driver)
    except Exception as exc:
        log_error(logger, f"Neo4j 连接或初始化失败: {exc}", "GraphSync")
        return {"status": "error", "message": str(exc)}

    total_posts = 0
    total_chunks = 0
    total_mentions = 0
    # dialect_name = engine.dialect.name if engine else "unknown"

    # 记录本次将要处理的渠道表，便于在日志中观察整体进度
    try:
        source_desc = f"文件目录 {data_dir}" if use_file_source else f"数据库 {target_database}"
        log_success(
            logger,
            f"准备从 {source_desc} 同步 {len(table_names)} 个渠道表: {', '.join(table_names)}",
            "GraphSync",
        )
    except Exception:
        # 日志失败不影响主流程
        pass

    from ..utils.io.excel import read_jsonl  # lazy import
    
    # 初始化线程池
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=8)

    with get_session() as session:
        for table_name in table_names:
            channel = table_name
            try:
                if use_file_source:
                    # 直接从 jsonl 读取
                    jsonl_path = data_dir / f"{table_name}.jsonl"
                    if not jsonl_path.exists():
                        log_error(logger, f"文件 {jsonl_path} 不存在", "GraphSync")
                        continue
                    df = read_jsonl(jsonl_path)
                else:
                    # 从数据库读取
                    dialect_name = engine.dialect.name
                    if dialect_name == "mysql":
                        query = f"SELECT * FROM `{table_name}`"
                    else:
                        query = f'SELECT * FROM "{table_name}"'
                    df = pd.read_sql(query, con=engine)
            except Exception as exc:
                log_error(logger, f"读取 {source_desc} 的表/文件 {table_name} 失败: {exc}", "GraphSync")
                continue
            if df is None or len(df) == 0:
                log_success(logger, f"表 {target_database}.{table_name} 无数据，跳过", "GraphSync")
                continue

            total_rows = len(df)
            log_success(
                logger,
                f"开始处理 {table_name}，共 {total_rows} 行（batch_size={batch_size}）",
                "GraphSync",
            )

            processed_in_table = 0
            for start in range(0, len(df), batch_size):
                batch = df.iloc[start : start + batch_size]
                processed_in_table += len(batch)
                
                batch_rows = []
                batch_params = []

                for _, row in batch.iterrows():
                    post_id_raw = row.get("id")
                    if post_id_raw is None or str(post_id_raw).strip() == "":
                        continue
                    
                    # 准备数据对象
                    row_dict = row.to_dict() if hasattr(row, "to_dict") else dict(row)
                    batch_rows.append(row_dict)
                    
                    # 准备 Cypher 参数
                    post_global_id = _post_global_id(topic, channel, _safe_str(post_id_raw))
                    author = _safe_str(row.get("author"))
                    account_id = _account_id(topic, author)
                    
                    batch_params.append({
                        "post_id": post_global_id,
                        "account_id": account_id,
                        "topic": topic,
                        "channel": channel,
                        "title": _safe_str(row.get("title")),
                        "contents": _safe_str(row.get("contents")),
                        "platform": _safe_str(row.get("platform")) or channel,
                        "author": author or "__unknown__",
                        "published_at": _safe_ts(row.get("published_at")),
                        "url": _safe_str(row.get("url")),
                        "region": _safe_str(row.get("region")),
                        "hit_words": _safe_str(row.get("hit_words")),
                        "polarity": _safe_str(row.get("polarity")),
                        "classification": _safe_str(row.get("classification")) or "未知",
                    })

                if not batch_params:
                    continue

                # 1. 批量写入 Post/Account/Platform (UNWIND)
                try:
                    session.run(
                        """
                        UNWIND $batch AS row
                        MERGE (p:Platform {name: row.channel})
                        
                        MERGE (a:Account {id: row.account_id})
                        SET a.topic = row.topic, a.author = row.author
                        
                        MERGE (post:Post {id: row.post_id})
                        SET post.topic = row.topic, 
                            post.channel = row.channel,
                            post.title = row.title, 
                            post.contents = row.contents, 
                            post.platform = row.platform,
                            post.author = row.author, 
                            post.published_at = row.published_at, 
                            post.url = row.url,
                            post.region = row.region, 
                            post.hit_words = row.hit_words, 
                            post.polarity = row.polarity,
                            post.classification = row.classification
                        
                        MERGE (a)-[:POSTED]->(post)
                        MERGE (post)-[:IN_PLATFORM]->(p)
                        """,
                        {"batch": batch_params}
                    )
                    total_posts += len(batch_params)
                except Exception as e:
                    LOG.error(f"Batch write failed for {table_name}: {e}")
                
                # 2. 并发执行 Chunk 和 Entity Extraction
                futures = []
                
                # Chunking (per post)
                if enable_chunk:
                    for row in batch_rows:
                        post_id_raw = row.get("id")
                        contents = _safe_str(row.get("contents"))
                        if post_id_raw and contents:
                            futures.append(
                                executor.submit(
                                    chunk_module.write_chunks_for_post,
                                    driver, topic, channel,
                                    str(post_id_raw), contents
                                )
                            )

                # Entity Extraction (batch)
                if enable_entity:
                    # 将整个 batch 作为一个任务提交
                    futures.append(
                        executor.submit(
                            entity_module.run_entity_extraction_for_sync,
                            driver, topic, channel, batch_rows, use_llm=enable_llm
                        )
                    )

                # 等待当前批次的所有辅助任务完成
                # 这样做可以控制内存占用，避免一次性提交过多任务
                for f in concurrent.futures.as_completed(futures):
                    try:
                        res = f.result()
                        if isinstance(res, tuple): # entity extraction returns (mentions, claims)
                            total_mentions += res[0]
                        elif isinstance(res, int): # chunking returns count
                            total_chunks += res
                    except Exception as e:
                        LOG.warning(f"Async task failed: {e}")

                # 每处理若干批输出一次表级进度（避免日志过于频繁）
                current_batch_index = start // batch_size
                if current_batch_index % 10 == 0 or processed_in_table >= total_rows:
                    log_success(
                        logger,
                        f"表 {target_database}.{table_name} 进度: 已处理 {processed_in_table}/{total_rows} 行",
                        "GraphSync",
                    )
    
    # 关闭线程池
    executor.shutdown(wait=True)

    log_success(logger, f"图同步完成: Post={total_posts}, Chunk={total_chunks}, MENTIONS={total_mentions}", "GraphSync")

    # engine.dispose()
    if engine:
        engine.dispose()
    return {
        "status": "ok",
        "message": f"已同步 {total_posts} 条 Post",
        "total_posts": total_posts,
        "total_chunks": total_chunks,
        "total_mentions": total_mentions,
    }
