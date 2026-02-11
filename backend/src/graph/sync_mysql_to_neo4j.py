"""
从 MySQL 增量同步到 Neo4j：Post、Account、Platform 及 POSTED、IN_PLATFORM。
与 Upload 产出对齐（同一批写入 MySQL 的数据）；幂等使用 MERGE。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import pandas as pd

from ..utils.setting.paths import bucket
from ..utils.io.db import db_manager
from ..utils.logging.logging import setup_logger, log_module_start, log_success, log_error
from .config import get_graph_config, is_neo4j_configured
from .neo4j_client import get_driver
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


def sync_after_upload(
    topic: str,
    date: str,
    dataset_name: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
    *,
    init_schema_if_missing: bool = True,
    enable_entity_extraction: bool = False,
    enable_chunk_embedding: bool = False,
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
    filter_dir = bucket("filter", topic, date)
    jsonl_files = list(filter_dir.glob("*.jsonl")) if filter_dir.exists() else []

    if not jsonl_files:
        log_error(logger, f"未找到 filter 产物 {filter_dir}，无法确定本批表", "GraphSync")
        return {"status": "error", "message": "未找到 filter 产物"}

    table_names = [f.stem for f in jsonl_files]
    try:
        engine = db_manager.get_engine_for_database(target_database)
    except Exception as exc:
        log_error(logger, f"无法连接 MySQL 数据库 {target_database}: {exc}", "GraphSync")
        return {"status": "error", "message": str(exc)}

    cfg = get_graph_config()
    batch_size = int(cfg.get("sync_batch_size") or 1000)
    enable_entity = bool(cfg.get("enable_entity_extraction", False)) or enable_entity_extraction
    enable_chunk = bool(cfg.get("enable_chunk_embedding", False)) or enable_chunk_embedding

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
    with driver.session() as session:
        for table_name in table_names:
            channel = table_name
            try:
                df = pd.read_sql(
                    f"SELECT * FROM `{table_name}`",
                    con=engine,
                )
            except Exception as exc:
                log_error(logger, f"读取表 {target_database}.{table_name} 失败: {exc}", "GraphSync")
                continue
            if df is None or len(df) == 0:
                continue
            for start in range(0, len(df), batch_size):
                batch = df.iloc[start : start + batch_size]
                for _, row in batch.iterrows():
                    post_id_raw = row.get("id")
                    if post_id_raw is None or str(post_id_raw).strip() == "":
                        continue
                    post_global_id = _post_global_id(topic, channel, _safe_str(post_id_raw))
                    author = _safe_str(row.get("author"))
                    account_id = _account_id(topic, author)

                    # MERGE Platform
                    session.run(
                        "MERGE (p:Platform {name: $name}) SET p.name = $name",
                        {"name": channel},
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
                            "platform": _safe_str(row.get("platform")) or channel,
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
                        {"pid": post_global_id, "name": channel},
                    )
                    total_posts += 1

                    # Chunk 与 Entity/Topic（在 Post 写入后）
                    row_dict = row.to_dict() if hasattr(row, "to_dict") else dict(row)
                    if enable_chunk:
                        try:
                            n = chunk_module.write_chunks_for_post(
                                driver, topic, channel,
                                str(post_id_raw), _safe_str(row.get("contents")),
                            )
                            total_chunks += n
                        except Exception as e:
                            LOG.warning("Chunk for post %s failed: %s", post_global_id, e)
                    if enable_entity:
                        try:
                            m, _ = entity_module.run_entity_extraction_for_sync(
                                driver, topic, channel, [row_dict],
                            )
                            total_mentions += m
                        except Exception as e:
                            LOG.warning("Entity/Topic for post %s failed: %s", post_global_id, e)

        log_success(logger, f"图同步完成: Post={total_posts}, Chunk={total_chunks}, MENTIONS={total_mentions}", "GraphSync")

    engine.dispose()
    return {
        "status": "ok",
        "message": f"已同步 {total_posts} 条 Post",
        "total_posts": total_posts,
        "total_chunks": total_chunks,
        "total_mentions": total_mentions,
    }
