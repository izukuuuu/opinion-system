"""
实体抽取模块：负责从文本中抽取实体、观点、框架和事件，并写入 Neo4j。
主要依赖 LLM (ContentAnalyze) 进行抽取。
"""
from __future__ import annotations

import logging
import asyncio
import hashlib
from typing import Any, Dict, List, Optional, Tuple

try:
    import jieba
    import jieba.posseg as pseg
except ImportError:
    jieba = None
    pseg = None

try:
    import nest_asyncio
except ImportError:
    nest_asyncio = None

from .neo4j_client import get_driver, get_session
from .sync_mysql_to_neo4j import _post_global_id
from ..contentanalyze.data_contentanalyze import ContentAnalyze
from ..utils.setting.paths import get_configs_root
from .source_doc import create_source_doc, link_claim_to_source

LOG = logging.getLogger(__name__)


def _generate_id(prefix: str, content: str) -> str:
    """生成基于内容的确定性 ID"""
    if not content:
        return ""
    hash_val = hashlib.md5(content.encode("utf-8")).hexdigest()
    return f"{prefix}_{hash_val}"


def _extract_entities_with_jieba(text: str) -> List[Dict]:
    """
    使用 Jieba 进行基础实体抽取 (NER 粗提)。
    提取人名 (nr), 地名 (ns), 机构名 (nt)。
    """
    if not text or not jieba or not pseg:
        return []
    
    entities = []
    seen = set()
    
    try:
        words = pseg.cut(text)
        for word, flag in words:
            if word in seen:
                continue
            
            etype = None
            if flag.startswith('nr'):
                etype = "Person"
            elif flag.startswith('ns'):
                etype = "Location"
            elif flag.startswith('nt'):
                etype = "Organization"
            
            if etype:
                entities.append({"name": word, "type": etype})
                seen.add(word)
    except Exception as e:
        LOG.warning(f"Jieba extraction failed: {e}")
        
    return entities


def write_entities_for_post(
    driver: Any,
    topic: str,
    channel: str,
    post_id_raw: str,
    entities_data: List[Dict],
) -> int:
    """
    将提取的实体写入 Neo4j 并建立 (Post)-[:MENTIONS]->(Entity) 关系。
    entities_data: [{"name": "...", "type": "..."}, ...]
    """
    if not entities_data:
        return 0

    post_global_id = _post_global_id(topic, channel, str(post_id_raw).strip())
    seen = set()
    
    with get_session() as session:
        for item in entities_data:
            name = item.get("name")
            etype = item.get("type")
            
            if not name or not str(name).strip():
                continue
                
            name = str(name).strip()
            etype = str(etype or "OTHER").strip() or "OTHER"
            
            # 去重
            key = (name, etype)
            if key in seen:
                continue
            seen.add(key)
            
            entity_id = f"{topic}_{name}_{etype}"
            
            # MERGE Entity
            session.run(
                """
                MERGE (e:Entity {id: $id})
                SET e.name = $name, e.type = $type, e.topic = $topic
                """,
                {"id": entity_id, "name": name, "type": etype, "topic": topic},
            )
            
            # MERGE Relationship
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
    注意：这是基于基础分类的 Topic。更细粒度的 Topic 由 Bertopic 模块 (topic_sync.py) 生成。
    """
    if not classification or not str(classification).strip():
        classification = "未知"
    classification = str(classification).strip()
    
    post_global_id = _post_global_id(topic, channel, str(post_id_raw).strip())
    topic_id = f"{topic}_{classification}"
    
    with get_session() as session:
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


def write_claims_for_post(
    driver: Any,
    topic: str,
    channel: str,
    post_id_raw: str,
    claims_data: List[Dict],
) -> int:
    """
    将提取的观点写入 Neo4j 并建立 (Post)-[:ASSERTS]->(Claim) 关系。
    claims_data: [{"content": "...", "evidence": "...", "source": "..."}, ...]
    """
    if not claims_data:
        return 0
        
    post_global_id = _post_global_id(topic, channel, str(post_id_raw).strip())
    count = 0
    
    with get_session() as session:
        for item in claims_data:
            # 兼容不同的键名 (content vs claim)
            claim_text = item.get("content") or item.get("claim")
            if not claim_text or not str(claim_text).strip():
                continue
                
            claim_text = str(claim_text).strip()
            claim_id = _generate_id("claim", claim_text)
            
            # MERGE Claim
            session.run(
                """
                MERGE (c:Claim {id: $id})
                SET c.content = $content, c.topic = $topic
                """,
                {"id": claim_id, "content": claim_text, "topic": topic}
            )
            
            # MERGE Relationship
            session.run(
                """
                MATCH (p:Post {id: $pid}), (c:Claim {id: $cid})
                MERGE (p)-[:ASSERTS]->(c)
                """,
                {"pid": post_global_id, "cid": claim_id}
            )
            
            # 处理 Evidence / SourceDoc
            evidence_text = item.get("evidence")
            source_info = item.get("source")
            relation_type = item.get("relation") or "SUPPORTED_BY"
            
            if evidence_text or source_info:
                doc_content = f"Evidence: {evidence_text}\nSource: {source_info}"
                doc_id = _generate_id("doc", doc_content)
                
                # 创建 SourceDoc 节点
                create_source_doc(
                    doc_id=doc_id,
                    title="Extracted Evidence",
                    content=doc_content,
                    doc_type="Evidence",
                    driver=driver # create_source_doc handles session
                )
                # 关联 Claim -> SourceDoc
                link_claim_to_source(claim_id, doc_id, relation_type=relation_type, driver=driver)
                
            count += 1
    return count


def write_frames_for_post(
    driver: Any,
    topic: str,
    channel: str,
    post_id_raw: str,
    frames_data: List[str],
) -> int:
    """
    将提取的框架写入 Neo4j 并建立 (Post)-[:HAS_FRAME]->(Frame) 关系。
    """
    if not frames_data:
        return 0
        
    post_global_id = _post_global_id(topic, channel, str(post_id_raw).strip())
    count = 0
    
    with get_session() as session:
        for frame_name in frames_data:
            if not frame_name or not str(frame_name).strip():
                continue
                
            frame_name = str(frame_name).strip()
            frame_id = f"frame_{frame_name}"
            
            session.run(
                """
                MERGE (f:Frame {id: $id})
                SET f.name = $name, f.topic = $topic
                """,
                {"id": frame_id, "name": frame_name, "topic": topic}
            )
            session.run(
                """
                MATCH (p:Post {id: $pid}), (f:Frame {id: $fid})
                MERGE (p)-[:HAS_FRAME]->(f)
                """,
                {"pid": post_global_id, "fid": frame_id}
            )
            count += 1
    return count


def write_events_for_post(
    driver: Any,
    topic: str,
    channel: str,
    post_id_raw: str,
    events_data: List[str],
) -> int:
    """
    将提取的事件写入 Neo4j 并建立 (Post)-[:PART_OF_EVENT]->(Event) 关系。
    """
    if not events_data:
        return 0
        
    post_global_id = _post_global_id(topic, channel, str(post_id_raw).strip())
    count = 0
    
    with get_session() as session:
        for event_name in events_data:
            if not event_name or not str(event_name).strip():
                continue
                
            event_name = str(event_name).strip()
            event_id = _generate_id("event", f"{topic}_{event_name}")
            
            session.run(
                """
                MERGE (e:Event {id: $id})
                SET e.name = $name, e.topic = $topic
                """,
                {"id": event_id, "name": event_name, "topic": topic}
            )
            session.run(
                """
                MATCH (p:Post {id: $pid}), (e:Event {id: $eid})
                MERGE (p)-[:PART_OF_EVENT]->(e)
                """,
                {"pid": post_global_id, "eid": event_id}
            )
            count += 1
    return count


def run_entity_extraction_for_sync(
    driver: Any,
    topic: str,
    channel: str,
    rows: List[Dict[str, Any]],
    *,
    use_llm: bool = False,
    # extract_fn 参数已移除，不再支持非 LLM 的占位符抽取
    **kwargs
) -> Tuple[int, int]:
    """
    对一批 Post 行执行：Entity/Claim/Frame/Event 提取与写入。
    策略：
    1. 基础实体（人/号/地）走 NER 粗提 (Jieba)。
    2. 若 use_llm=True (高价值样本)，走 LLM 精修 (ContentAnalyze)。
    
    Returns: (mentions_count, topics_count)
    """
    mentions = 0
    topics = 0
    
    llm_results = [None] * len(rows)
    
    # 1. 执行 LLM 抽取 (如果启用)
    if use_llm:
        try:
            texts = [row.get("contents", "") or "" for row in rows]
            
            # 加载提示词配置
            prompt_path = get_configs_root() / "prompt" / "graph_extraction" / "default.yaml"
            if not prompt_path.exists():
                LOG.error(f"提示词配置文件不存在: {prompt_path}")
            else:
                analyzer = ContentAnalyze(topic, "", "", prompt_config_path=prompt_path)
                
                # 处理异步调用
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        if nest_asyncio:
                            nest_asyncio.apply()
                            llm_results = loop.run_until_complete(analyzer.analyze_texts(texts))
                        else:
                            LOG.error("检测到运行中的事件循环，但未安装 nest_asyncio，无法执行同步调用。请运行 pip install nest_asyncio")
                    else:
                        llm_results = asyncio.run(analyzer.analyze_texts(texts))
                except RuntimeError as re:
                    # 如果没有事件循环，创建一个新的
                    llm_results = asyncio.run(analyzer.analyze_texts(texts))
                    
        except Exception as e:
            LOG.error(f"LLM 批量抽取失败: {e}")
            # 继续执行，结果为 None
    else:
        # 如果未启用 LLM，仅记录日志，不执行深度抽取
        # LOG.info("跳过 LLM 抽取 (use_llm=False)")
        pass
    
    # 2. 遍历结果写入图数据库
    for idx, row in enumerate(rows):
        post_id = row.get("id")
        contents = row.get("contents") or ""
        classification = row.get("classification") or "未知"
        
        if post_id is None or not str(post_id).strip():
            continue
            
        # --- 策略 A: NER 粗提 (总是执行) ---
        ner_entities = _extract_entities_with_jieba(contents)
        if ner_entities:
            mentions += write_entities_for_post(
                driver, topic, channel, str(post_id), ner_entities
            )

        # 获取 LLM 结果
        llm_data = llm_results[idx] if idx < len(llm_results) else None
        
        entities_data = llm_data.get("entities") if llm_data else None
        claims_data = llm_data.get("claims") if llm_data else None
        frames_data = llm_data.get("frames") if llm_data else None
        events_data = llm_data.get("events") if llm_data else None
            
        # --- 策略 B: LLM 精修 ---
        # 1. Entity (需要 LLM 结果)
        if entities_data:
            mentions += write_entities_for_post(
                driver, topic, channel, str(post_id), entities_data
            )
        
        # 2. Topic (基础分类，总是执行)
        write_topic_for_post(driver, topic, channel, str(post_id), classification)
        topics += 1
        
        # 3. Claims (需要 LLM 结果)
        if claims_data:
            write_claims_for_post(
                driver, topic, channel, str(post_id), claims_data
            )
        
        # 4. Frames (需要 LLM 结果)
        if frames_data:
            write_frames_for_post(
                driver, topic, channel, str(post_id), frames_data
            )
        
        # 5. Events (需要 LLM 结果)
        if events_data:
            write_events_for_post(
                driver, topic, channel, str(post_id), events_data
            )

    return mentions, topics
