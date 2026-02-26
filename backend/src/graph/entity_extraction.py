"""
实体抽取：粗提 NER（可接 HanLP/BERT）+ Topic 从 MySQL classification 或 BERTopic 映射。
首期：Topic 从 classification 建节点与 (Post)-[:ABOUT_TOPIC]->(Topic)；Entity 粗提可插 NER，默认占位。
"""
from __future__ import annotations

import logging
import json
from typing import Any, Dict, List, Optional, Tuple

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

from ..utils.setting.env_loader import get_api_key
from .neo4j_client import get_driver, get_session

LOG = logging.getLogger(__name__)


def _post_global_id(topic: str, channel: str, row_id: str) -> str:
    """Duplicate of sync_mysql_to_neo4j._post_global_id to avoid circular import."""
    return f"{topic}_{channel}_{row_id}"


def extract_with_llm(text: str) -> Dict[str, Any]:
    """
    使用 LLM 提取实体和观点。
    返回: {"entities": [(name, type), ...], "claims": [claim_text, ...]}
    """
    if not text or not str(text).strip():
        return {"entities": [], "claims": []}

    api_key = get_api_key()
    if not api_key or OpenAI is None:
        LOG.warning("LLM API Key not found or OpenAI package missing, skipping LLM extraction.")
        return {"entities": [], "claims": []}

    try:
        client = OpenAI(
            api_key=api_key,
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1"
        )

        prompt = f"""
请分析以下文本，提取其中的关键实体和核心观点。

文本内容：
{text[:3000]}

请严格按照以下 JSON 格式输出：
{{
    "entities": [["实体名称", "实体类型(如: 人物, 地点, 组织, 事件, 产品, 其他)"], ...],
    "claims": ["观点1", "观点2", ...]
}}
注意：
1. 实体类型请尽量规范。
2. 观点应简洁明了，概括文本中的主要论断或意见。
3. 仅输出 JSON，不要包含其他解释。
"""

        completion = client.chat.completions.create(
            model="qwen-plus",
            messages=[
                {'role': 'system', 'content': '你是一个专业的信息抽取助手，擅长从文本中提取实体和观点。'},
                {'role': 'user', 'content': prompt}
            ],
            response_format={"type": "json_object"}
        )
        content = completion.choices[0].message.content
        data = json.loads(content)
        
        raw_entities = data.get("entities", [])
        entities = []
        for e in raw_entities:
            if isinstance(e, list) and len(e) >= 2:
                entities.append((str(e[0]), str(e[1])))
        
        claims = [str(c) for c in data.get("claims", []) if c]
        
        return {"entities": entities, "claims": claims}

    except Exception as e:
        LOG.error(f"LLM extraction failed: {e}")
        return {"entities": [], "claims": []}


def extract_entities_naive(text: str) -> List[Tuple[str, str]]:
    """
    轻量级实体抽取占位：首期不依赖 HanLP/BERT，返回空列表。
    后续可接入 HanLP 或 BERT NER，返回 [(name, type), ...]，如 ("张三", "PERSON"), ("北京", "LOC")。
    """
    if not text or not str(text).strip():
        return []
    # 占位：不做 NER，避免新增依赖；后续可替换为 HanLP/BERT 调用
    return []


def _write_entities(
    topic: str,
    channel: str,
    post_id_raw: str,
    entities: List[Tuple[str, str]],
) -> int:
    """
    Internal helper to write entities to Neo4j.
    """
    if not entities:
        return 0
    
    post_global_id = _post_global_id(topic, channel, str(post_id_raw).strip())
    seen: set = set()
    
    with get_session() as session:
        # 使用 Transaction 处理一批实体，减少死锁概率
        with session.begin_transaction() as tx:
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
                
                # MERGE Entity
                tx.run(
                    """
                    MERGE (e:Entity {id: $id})
                    SET e.name = $name, e.type = $type, e.topic = $topic
                    """,
                    {"id": entity_id, "name": name, "type": etype, "topic": topic},
                )
                # MERGE Relationship
                tx.run(
                    """
                    MATCH (p:Post {id: $pid}), (e:Entity {id: $eid})
                    MERGE (p)-[:MENTIONS]->(e)
                    """,
                    {"pid": post_global_id, "eid": entity_id},
                )
    return len(seen)


def write_entities_for_post(
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
    fn = extract_fn or extract_entities_naive
    entities = fn(str(contents or ""))
    return _write_entities(topic, channel, post_id_raw, entities)


def write_claims_for_post(
    topic: str,
    channel: str,
    post_id_raw: str,
    claims: List[str],
) -> int:
    """
    将提取的观点写入 Neo4j，建立 (Post)-[:HAS_CLAIM]->(Claim)。
    """
    if not claims:
        return 0

    post_global_id = _post_global_id(topic, channel, str(post_id_raw).strip())
    count = 0
    
    with get_session() as session:
        with session.begin_transaction() as tx:
            for claim_text in claims:
                if not claim_text or not str(claim_text).strip():
                    continue
                
                # 使用简单的 hash 作为 ID，或者 topic + hash
                import hashlib
                claim_hash = hashlib.md5(claim_text.encode("utf-8")).hexdigest()
                claim_id = f"{topic}_claim_{claim_hash}"
                
                try:
                    tx.run(
                        """
                        MERGE (c:Claim {id: $id})
                        SET c.content = $content, c.topic = $topic
                        """,
                        {"id": claim_id, "content": claim_text, "topic": topic}
                    )
                    tx.run(
                        """
                        MATCH (p:Post {id: $pid}), (c:Claim {id: $cid})
                        MERGE (p)-[:HAS_CLAIM]->(c)
                        """,
                        {"pid": post_global_id, "cid": claim_id}
                    )
                    count += 1
                except Exception as e:
                    LOG.warning(f"Failed to write claim: {e}")
                
    return count


def run_entity_extraction_for_sync(
    topic: str,
    channel: str,
    rows: List[Dict[str, Any]],
    *,
    extract_fn: Optional[Any] = None,
    enable_llm: bool = False,
    pre_fetched_llm_result: Optional[Dict[str, Any]] = None,
) -> Tuple[int, int]:
    """
    对一批 Post 行执行：Entity 粗提 + MENTIONS；
    不再创建基于 classification 的 Topic 节点（classification 已作为 Post 属性）。
    pre_fetched_llm_result: 可选，预先获取的 LLM 结果（用于并发优化）
    返回 (mentions_count, topics_count)。topics_count 始终为 0。
    """
    mentions = 0
    topics = 0
    for row in rows:
        post_id = row.get("id")
        contents = row.get("contents") or ""
        # classification = row.get("classification") or "未知" # 已作为 Post 属性，不再需要独立节点
        if post_id is None or not str(post_id).strip():
            continue
            
        if enable_llm:
            try:
                # LLM 抽取实体和观点
                if pre_fetched_llm_result is not None:
                    res = pre_fetched_llm_result
                else:
                    res = extract_with_llm(contents)
                
                ents = res.get("entities", [])
                claims = res.get("claims", [])
                
                # 写入实体
                mentions += _write_entities(topic, channel, str(post_id), ents)
                
                # 写入观点
                write_claims_for_post(topic, channel, str(post_id), claims)
            except Exception as e:
                LOG.warning(f"LLM extraction failed for post {post_id}: {e}")
        else:
            # 默认粗提取
            mentions += write_entities_for_post(
                topic, channel, str(post_id), contents, extract_fn=extract_fn
            )
            
        # 不再创建 Topic 节点
        # write_topic_for_post(topic, channel, str(post_id), classification)
        # topics += 1
    return mentions, topics
