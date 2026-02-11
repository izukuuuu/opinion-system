"""
将 BERTopic 分析结果同步到 Neo4j 知识图谱。
"""
import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional

from ..utils.setting.paths import bucket
from ..utils.logging.logging import setup_logger, log_success, log_error
from .neo4j_client import get_driver
from .sync_mysql_to_neo4j import _post_global_id

def load_json(path: Path) -> Any:
    if not path.exists():
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def sync_bertopic_results(
    topic: str,
    start_date: str,
    end_date: str = None,
    logger = None
) -> bool:
    """
    读取 BERTopic 分析结果并写入 Neo4j。
    
    Args:
        topic: 专题名称
        start_date: 开始日期
        end_date: 结束日期
        logger: 日志记录器
        
    Returns:
        bool: 是否成功
    """
    if not logger:
        logger = setup_logger("sync_bertopic")
        
    folder_name = f"{start_date}_{end_date}" if end_date else start_date
    output_dir = bucket("topic", topic, folder_name)
    
    if not output_dir.exists():
        log_error(logger, f"分析结果目录不存在: {output_dir}", "SyncBertopic")
        return False
        
    # 1. 读取分析结果
    stats_path = output_dir / "1主题统计结果.json"
    coords_path = output_dir / "3文档2D坐标.json"
    clusters_path = output_dir / "4大模型再聚类结果.json"
    cluster_keywords_path = output_dir / "5大模型主题关键词.json"
    
    stats_data = load_json(stats_path)
    coords_data = load_json(coords_path)
    clusters_data = load_json(clusters_path)
    cluster_keywords = load_json(cluster_keywords_path) or {}
    
    if not stats_data or not coords_data:
        log_error(logger, "缺少必要的主题统计或文档坐标文件", "SyncBertopic")
        return False
        
    # 建立映射
    # topic_id -> topic_name (Original BERTopic)
    tid_to_name = {}
    for t in stats_data.get("topics", []):
        tid_to_name[t["topic_id"]] = t["topic_name"]
        
    # topic_name -> cluster_name (LLM Cluster)
    tname_to_cluster = {}
    cluster_info = {} # name -> {description, keywords}
    
    if clusters_data:
        for cluster in clusters_data.get("clusters", []):
            c_name = cluster["cluster_name"]
            c_desc = cluster.get("description", "")
            c_topics = cluster.get("topics", [])
            
            cluster_info[c_name] = {
                "description": c_desc,
                "keywords": cluster_keywords.get(c_name, [])
            }
            
            for t_name in c_topics:
                tname_to_cluster[t_name] = c_name
                
    driver = get_driver()
    
    log_success(logger, f"开始同步 BERTopic 结果到 Neo4j: {topic}", "SyncBertopic")
    
    with driver.session() as session:
        # 2. 创建 Cluster Topic 节点 (大模型聚类)
        for c_name, info in cluster_info.items():
            cid = f"{topic}_Cluster_{c_name}"
            session.run(
                """
                MERGE (t:Topic {id: $id})
                SET t.name = $name, 
                    t.type = 'Cluster',
                    t.description = $desc,
                    t.keywords = $keywords,
                    t.topic_scope = $topic_scope
                """,
                {
                    "id": cid, 
                    "name": c_name, 
                    "desc": info["description"],
                    "keywords": info["keywords"],
                    "topic_scope": topic
                }
            )
            
        # 3. 创建 SubTopic 节点 (原始 BERTopic)
        # 并建立 (SubTopic)-[:BELONGS_TO]->(Topic)
        for tid, tname in tid_to_name.items():
            sid = f"{topic}_Sub_{tid}"
            # 查找所属 Cluster
            c_name = tname_to_cluster.get(tname)
            
            session.run(
                """
                MERGE (st:Topic {id: $id})
                SET st.name = $name,
                    st.type = 'SubTopic',
                    st.original_id = $tid,
                    st.topic_scope = $topic_scope
                """,
                {
                    "id": sid,
                    "name": tname,
                    "tid": tid,
                    "topic_scope": topic
                }
            )
            
            if c_name:
                cid = f"{topic}_Cluster_{c_name}"
                session.run(
                    """
                    MATCH (st:Topic {id: $sid}), (t:Topic {id: $cid})
                    MERGE (st)-[:BELONGS_TO]->(t)
                    """,
                    {"sid": sid, "cid": cid}
                )

        # 4. 建立 (Post)-[:ABOUT_TOPIC]->(SubTopic)
        # 从文档坐标中获取 Post ID
        processed_count = 0
        
        # 为了提高性能，可以使用 UNWIND 批量插入，但这里先逐个插入或小批量
        # 这里数据量可能较大，建议批量
        
        batch_size = 1000
        batch_params = []
        
        documents = coords_data.get("documents", [])
        
        for doc in documents:
            post_id_raw = doc.get("post_id")
            channel = doc.get("channel")
            topic_id = doc.get("topic_id")
            
            if not post_id_raw or not channel or topic_id is None:
                continue
                
            post_global_id = _post_global_id(topic, channel, str(post_id_raw).strip())
            sid = f"{topic}_Sub_{topic_id}"
            
            batch_params.append({
                "pid": post_global_id,
                "sid": sid
            })
            
            if len(batch_params) >= batch_size:
                session.run(
                    """
                    UNWIND $batch as row
                    MATCH (p:Post {id: row.pid})
                    MATCH (t:Topic {id: row.sid})
                    MERGE (p)-[:ABOUT_TOPIC]->(t)
                    """,
                    {"batch": batch_params}
                )
                processed_count += len(batch_params)
                batch_params = []
                
        # 处理剩余的
        if batch_params:
            session.run(
                """
                UNWIND $batch as row
                MATCH (p:Post {id: row.pid})
                MATCH (t:Topic {id: row.sid})
                MERGE (p)-[:ABOUT_TOPIC]->(t)
                """,
                {"batch": batch_params}
            )
            processed_count += len(batch_params)
            
    log_success(logger, f"同步完成，关联了 {processed_count} 个 Post 到 Topic", "SyncBertopic")
    return True
