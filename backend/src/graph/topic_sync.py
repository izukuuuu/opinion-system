"""
BERTopic 结果同步到 Neo4j。
读取 data_bertopic_qwen_v2.py 生成的 JSON 文件，构建 Topic 及其与 Post 的关系。
遵循严格的节点约束：只使用 Topic 节点，不创建 TopicCluster/Keyword 节点。
宏观话题作为高层级 Topic 存在。
"""
import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional

from .neo4j_client import get_driver, get_session

LOG = logging.getLogger(__name__)


def _generate_topic_global_id(project_topic: str, topic_id: int) -> str:
    """生成 Topic 节点的全局唯一 ID"""
    return f"{project_topic}_topic_{topic_id}"

def _generate_cluster_global_id(project_topic: str, cluster_name: str) -> str:
    """生成宏观 Topic (Cluster) 的全局唯一 ID"""
    # 简单的哈希或编码，确保唯一性
    import hashlib
    h = hashlib.md5(cluster_name.encode("utf-8")).hexdigest()
    return f"{project_topic}_cluster_{h}"

def _generate_post_global_id(project_topic: str, channel: str, raw_id: str) -> str:
    """生成 Post 节点的全局唯一 ID (需与 entity_extraction.py 保持一致)"""
    return f"{project_topic}_{channel}_{raw_id}"

def sync_bertopic_results(
    project_topic: str,
    output_dir: Path,
    clear_existing: bool = False
) -> bool:
    """
    同步 BERTopic 分析结果到 Neo4j。
    
    Args:
        project_topic: 专题名称 (用于 ID 命名空间)
        output_dir: BERTopic 结果输出目录 (包含 1~5 号 JSON 文件)
        clear_existing: 是否先清除该专题下的旧 Topic 数据 (慎用)
    """
    if not output_dir.exists():
        LOG.error(f"BERTopic output directory not found: {output_dir}")
        return False

    driver = get_driver()
    
    # 1. 读取所有必要文件
    try:
        # 文件 1: 统计结果 (ID <-> Name)
        with open(output_dir / "1主题统计结果.json", 'r', encoding='utf-8') as f:
            stats_data = json.load(f)
            if "topics" in stats_data and isinstance(stats_data["topics"], list):
                topic_stats = stats_data["topics"]
            elif "主题文档统计" in stats_data:
                topic_stats = []
                for k, v in stats_data["主题文档统计"].items():
                    try:
                        tid = int(k.replace("主题", ""))
                        topic_stats.append({
                            "topic_id": tid,
                            "topic_name": k,
                            "count": v.get("文档数", 0),
                            "frequency": 0.0
                        })
                    except ValueError:
                        pass
            else:
                topic_stats = []

        # 文件 2: 主题关键词
        keywords_path = output_dir / "2主题关键词.json"
        topic_keywords = {}
        if keywords_path.exists():
            with open(keywords_path, 'r', encoding='utf-8') as f:
                topic_keywords = json.load(f)

        # 文件 3: 文档坐标 (Post <-> Topic)
        coords_path = output_dir / "3文档2D坐标.json"
        doc_coords = []
        if coords_path.exists():
            with open(coords_path, 'r', encoding='utf-8') as f:
                raw_coords = json.load(f)
                if isinstance(raw_coords, dict):
                    doc_coords = raw_coords.get("documents", [])
                elif isinstance(raw_coords, list):
                    doc_coords = raw_coords

        # 文件 4: 聚类结果 (Cluster <-> Topic Name)
        clusters_path = output_dir / "4大模型再聚类结果.json"
        clusters_data = []
        if clusters_path.exists():
            with open(clusters_path, 'r', encoding='utf-8') as f:
                raw_clusters = json.load(f)
                if isinstance(raw_clusters, dict) and "clusters" in raw_clusters:
                    clusters_data = raw_clusters.get("clusters", [])
                elif isinstance(raw_clusters, dict):
                    for k, v in raw_clusters.items():
                        clusters_data.append({
                            "cluster_name": k,
                            "name": v.get("主题命名", k),
                            "description": v.get("主题描述", ""),
                            "topics": v.get("原始主题集合", [])
                        })
                elif isinstance(raw_clusters, list):
                    clusters_data = raw_clusters

        # 文件 5: 聚类关键词
        cluster_keywords_path = output_dir / "5大模型主题关键词.json"
        cluster_keywords = {}
        if cluster_keywords_path.exists():
            with open(cluster_keywords_path, 'r', encoding='utf-8') as f:
                cluster_keywords = json.load(f)
                
    except Exception as e:
        LOG.error(f"Failed to read BERTopic result files: {e}")
        return False

    with driver.session() as session:
        # 0. 清理旧数据 (可选)
        if clear_existing:
            LOG.info(f"Clearing existing topics for project: {project_topic}")
            session.run(
                """
                MATCH (t:Topic {project: $project})
                DETACH DELETE t
                """, {"project": project_topic}
            )

        # 1. 创建微观 Topic 节点
        LOG.info(f"Syncing {len(topic_stats)} topics...")
        topic_name_to_id = {} # Name -> Global ID mapping for clustering
        
        for t in topic_stats:
            tid = t["topic_id"]
            name = t["topic_name"]
            count = t["count"]
            freq = t["frequency"]
            
            global_id = _generate_topic_global_id(project_topic, tid)
            topic_name_to_id[name] = global_id
            
            # 获取关键词
            k_key = f"Topic_{tid}"
            raw_kw = topic_keywords.get(k_key, [])
            keywords_list = []
            
            # 提取纯文本关键词，扁平化处理以存入 Neo4j
            target_list = raw_kw
            if isinstance(raw_kw, dict):
                target_list = raw_kw.get("关键词", [])
            
            if isinstance(target_list, list):
                # 处理 [[word, score], ...] 或 [word, ...]
                keywords_list = [str(x[0]) if isinstance(x, list) else str(x) for x in target_list]
            
            session.run(
                """
                MERGE (t:Topic {id: $id})
                SET t.name = $name,
                    t.count = $count,
                    t.frequency = $freq,
                    t.project = $project,
                    t.source = 'BERTopic',
                    t.level = 'micro',
                    t.keywords = $keywords
                """,
                {
                    "id": global_id,
                    "name": name,
                    "count": count,
                    "freq": freq,
                    "project": project_topic,
                    "keywords": keywords_list
                }
            )

        # 2. 创建宏观 Topic 节点 (原 TopicCluster)
        LOG.info(f"Syncing {len(clusters_data)} macro topics...")
        for c in clusters_data:
            c_id_key = c.get("cluster_name")
            c_name = c.get("name", c_id_key)
            c_desc = c.get("description", "")
            sub_topic_names = c.get("topics", [])
            
            cluster_id = _generate_cluster_global_id(project_topic, c_id_key)
            
            # 获取聚类关键词
            raw_ckw = cluster_keywords.get(c_id_key, [])
            c_keywords = []
            
            target_clist = raw_ckw
            if isinstance(raw_ckw, dict):
                target_clist = raw_ckw.get("关键词", [])
            
            if isinstance(target_clist, list):
                c_keywords = [str(x[0]) if isinstance(x, list) else str(x) for x in target_clist]
            
            # Create Macro Topic Node
            session.run(
                """
                MERGE (t:Topic {id: $id})
                SET t.name = $name,
                    t.description = $desc,
                    t.project = $project,
                    t.source = 'LLM_Cluster',
                    t.level = 'macro',
                    t.keywords = $keywords
                """,
                {
                    "id": cluster_id,
                    "name": c_name,
                    "desc": c_desc,
                    "project": project_topic,
                    "keywords": c_keywords
                }
            )
            
            # Link Micro Topics to Macro Topic (Hierarchy)
            # 关系: (MicroTopic)-[:SUB_TOPIC_OF]->(MacroTopic)
            for sub_name in sub_topic_names:
                if sub_name in topic_name_to_id:
                    sub_id = topic_name_to_id[sub_name]
                    session.run(
                        """
                        MATCH (sub:Topic {id: $sub_id})
                        MATCH (parent:Topic {id: $parent_id})
                        MERGE (sub)-[:SUB_TOPIC_OF]->(parent)
                        """,
                        {"sub_id": sub_id, "parent_id": cluster_id}
                    )

        # 3. 建立 Post -> Topic 关系
        LOG.info(f"Syncing {len(doc_coords)} post-topic relationships...")
        # 批量处理以提高性能
        batch_size = 1000
        batch = []
        
        for doc in doc_coords:
            post_raw_id = doc.get("post_id")
            channel = doc.get("channel")
            topic_id_int = doc.get("topic_id")
            
            if post_raw_id and channel and topic_id_int is not None and topic_id_int != -1:
                post_global_id = _generate_post_global_id(project_topic, channel, str(post_raw_id))
                topic_global_id = _generate_topic_global_id(project_topic, topic_id_int)
                batch.append({"pid": post_global_id, "tid": topic_global_id})
            
            if len(batch) >= batch_size:
                session.run(
                    """
                    UNWIND $batch as row
                    MATCH (p:Post {id: row.pid})
                    MATCH (t:Topic {id: row.tid})
                    MERGE (p)-[:ABOUT_TOPIC]->(t)
                    """,
                    {"batch": batch}
                )
                batch = []
        
        # 处理剩余 batch
        if batch:
            session.run(
                """
                UNWIND $batch as row
                MATCH (p:Post {id: row.pid})
                MATCH (t:Topic {id: row.tid})
                MERGE (p)-[:ABOUT_TOPIC]->(t)
                """,
                {"batch": batch}
            )

    LOG.info("BERTopic sync completed successfully.")
    return True
