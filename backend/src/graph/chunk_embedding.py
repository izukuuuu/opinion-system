"""
文本切块与 Neo4j Chunk 节点：对 Post.contents 切分，写 Chunk 节点及 (Post)-[:HAS_CHUNK]->(Chunk)。
与 RAG chunker 策略对齐；向量仍写入现有 LanceDB，本模块只写图结构。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from ..rag.core.chunker import ChunkConfig, TextChunker
from .neo4j_client import get_driver, get_session
from .sync_mysql_to_neo4j import _post_global_id

LOG = logging.getLogger(__name__)


def _chunk_text(text: str, chunk_size: int = 512, chunk_overlap: int = 50) -> List[Tuple[str, int]]:
    """按字符切块，与 RAG chunker 对齐。返回 [(chunk_text, chunk_index), ...]。"""
    if not text or not str(text).strip():
        return []
    config = ChunkConfig(chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    chunker = TextChunker(config=config)
    return chunker.chunk_by_size(str(text).strip())


def write_chunks_for_post(
    driver: Any,
    topic: str,
    channel: str,
    post_id_raw: str,
    contents: str,
    *,
    chunk_size: int = 512,
    chunk_overlap: int = 50,
) -> int:
    """
    对一条 Post 的 contents 切块，在 Neo4j 中创建 Chunk 节点及 (Post)-[:HAS_CHUNK]->(Chunk)。
    返回写入的 Chunk 数量。
    """
    post_global_id = _post_global_id(topic, channel, str(post_id_raw).strip())
    chunks = _chunk_text(contents, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    if not chunks:
        return 0
    
    # 使用 get_session() 确保连接到配置的数据库
    with get_session() as session:
        for chunk_text, chunk_index in chunks:
            chunk_id = f"{post_global_id}_chunk_{chunk_index}"
            session.run(
                """
                MERGE (c:Chunk {id: $id})
                SET c.post_id = $post_id, c.chunk_index = $chunk_index, c.text = $text
                """,
                {"id": chunk_id, "post_id": post_global_id, "chunk_index": chunk_index, "text": chunk_text},
            )
            session.run(
                """
                MATCH (p:Post {id: $pid}), (c:Chunk {id: $cid})
                MERGE (p)-[:HAS_CHUNK]->(c)
                """,
                {"pid": post_global_id, "cid": chunk_id},
            )
    return len(chunks)


def run_chunk_embedding_for_sync(
    driver: Any,
    topic: str,
    channel: str,
    rows: List[Dict[str, Any]],
    *,
    chunk_size: int = 512,
    chunk_overlap: int = 50,
) -> int:
    """
    对一批 Post 行（含 id、contents）执行切块并写 Chunk 与 HAS_CHUNK。
    返回写入的 Chunk 总数。
    """
    total = 0
    for row in rows:
        post_id = row.get("id")
        contents = row.get("contents") or ""
        if post_id is None or not str(post_id).strip():
            continue
        n = write_chunks_for_post(
            driver, topic, channel, str(post_id), contents,
            chunk_size=chunk_size, chunk_overlap=chunk_overlap,
        )
        total += n
    return total
