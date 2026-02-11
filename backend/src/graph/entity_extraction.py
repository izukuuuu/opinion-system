"""
实体抽取：粗提 NER（可接 HanLP/BERT）+ Topic 从 MySQL classification 或 BERTopic 映射。
首期：Topic 从 classification 建节点与 (Post)-[:ABOUT_TOPIC]->(Topic)；Entity 粗提可插 NER，默认占位。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from .neo4j_client import get_driver
from .sync_mysql_to_neo4j import _post_global_id

LOG = logging.getLogger(__name__)


def extract_entities_naive(text: str) -> List[Tuple[str, str]]:
    """
    轻量级实体抽取占位：首期不依赖 HanLP/BERT，返回空列表。
    后续可接入 HanLP 或 BERT NER，返回 [(name, type), ...]，如 ("张三", "PERSON"), ("北京", "LOC")。
    """
    if not text or not str(text).strip():
        return []
    # 占位：不做 NER，避免新增依赖；后续可替换为 HanLP/BERT 调用
    return []


def write_entities_for_post(
    driver: Any,
    topic: str,
    channel: str,
    post_id_raw: str,
    contents: str,
    *,
    extract_fn: Optional[Any] = None,
) -> int:
    """
    从 Post.contents 抽取实体，MERGE Entity 节点并建立 (Post)-[:MENTIONS]->(Entity)。
    extract_fn(text) -> [(name, type), ...]；默认使用 extract_entities_naive（占位）。
    返回写入的 MENTIONS 数量。
    """
    post_global_id = _post_global_id(topic, channel, str(post_id_raw).strip())
    fn = extract_fn or extract_entities_naive
    entities = fn(str(contents or ""))
    if not entities:
        return 0
    seen: set = set()
    with driver.session() as session:
        for name, etype in entities:
            if not name or not str(name).strip():
                continue
            name = str(name).strip()
            etype = str(etype or "OTHER").strip() or "OTHER"
            key = (name, etype)
            if key in seen:
                continue
            seen.add(key)
            entity_id = f"{topic}_{name}_{etype}"
            session.run(
                """
                MERGE (e:Entity {id: $id})
                SET e.name = $name, e.type = $type, e.topic = $topic
                """,
                {"id": entity_id, "name": name, "type": etype, "topic": topic},
            )
            session.run(
                """
                MATCH (p:Post {id: $pid}), (e:Entity {id: $eid})
                MERGE (p)-[:MENTIONS]->(e)
                """,
                {"pid": post_global_id, "eid": entity_id},
            )
    return len(seen)


def write_topic_for_post(
    driver: Any,
    topic: str,
    channel: str,
    post_id_raw: str,
    classification: str,
) -> bool:
    """
    从 MySQL classification 建 Topic 节点并建立 (Post)-[:ABOUT_TOPIC]->(Topic)。
    """
    if not classification or not str(classification).strip():
        classification = "未知"
    classification = str(classification).strip()
    post_global_id = _post_global_id(topic, channel, str(post_id_raw).strip())
    topic_id = f"{topic}_{classification}"
    with driver.session() as session:
        session.run(
            """
            MERGE (t:Topic {id: $id})
            SET t.name = $name, t.topic = $topic
            """,
            {"id": topic_id, "name": classification, "topic": topic},
        )
        session.run(
            """
            MATCH (p:Post {id: $pid}), (t:Topic {id: $tid})
            MERGE (p)-[:ABOUT_TOPIC]->(t)
            """,
            {"pid": post_global_id, "tid": topic_id},
        )
    return True


def run_entity_extraction_for_sync(
    driver: Any,
    topic: str,
    channel: str,
    rows: List[Dict[str, Any]],
    *,
    extract_fn: Optional[Any] = None,
) -> Tuple[int, int]:
    """
    对一批 Post 行执行：Entity 粗提 + MENTIONS；Topic 从 classification + ABOUT_TOPIC。
    返回 (mentions_count, topics_count)。
    """
    mentions = 0
    topics = 0
    for row in rows:
        post_id = row.get("id")
        contents = row.get("contents") or ""
        classification = row.get("classification") or "未知"
        if post_id is None or not str(post_id).strip():
            continue
        mentions += write_entities_for_post(
            driver, topic, channel, str(post_id), contents, extract_fn=extract_fn
        )
        write_topic_for_post(driver, topic, channel, str(post_id), classification)
        topics += 1
    return mentions, topics
