"""
SourceDoc (来源文档) 节点管理。
用于存储权威信源、政策文件、专家报告等，作为 Claim 的佐证 (Evidence)。
"""
from typing import Any, List, Optional
from .neo4j_client import get_driver, get_session

def create_source_doc(
    doc_id: str,
    title: str,
    content: str,
    url: str = "",
    author: str = "",
    publish_date: str = "",
    doc_type: str = "Report",
    driver: Any = None
) -> bool:
    """
    创建或更新 SourceDoc 节点。
    doc_id: 唯一标识 (如 DOI, URL hash, 或内部编号)
    """
    if not doc_id:
        return False
        
    with get_session() as session:
        session.run(
            """
            MERGE (s:SourceDoc {id: $id})
            SET s.title = $title,
                s.content = $content,
                s.url = $url,
                s.author = $author,
                s.publish_date = $publish_date,
                s.type = $type
            """,
            {
                "id": doc_id,
                "title": title,
                "content": content,
                "url": url,
                "author": author,
                "publish_date": publish_date,
                "type": doc_type
            }
        )
    return True

def link_claim_to_source(claim_id: str, source_doc_id: str, relation_type: str = "SUPPORTED_BY", driver: Any = None) -> bool:
    """
    建立 (Claim)-[relation]->(SourceDoc) 关系。
    relation_type: SUPPORTED_BY 或 REFUTED_BY
    """
    if not claim_id or not source_doc_id:
        return False
        
    valid_relations = {"SUPPORTED_BY", "REFUTED_BY"}
    if relation_type not in valid_relations:
        relation_type = "SUPPORTED_BY"

    with get_session() as session:
        # 使用 f-string 注入关系类型 (关系类型不能作为参数传递)
        query = f"""
            MATCH (c:Claim {{id: $cid}})
            MATCH (s:SourceDoc {{id: $sid}})
            MERGE (c)-[:{relation_type}]->(s)
            RETURN count(c) as cnt
        """
        result = session.run(
            query,
            {"cid": claim_id, "sid": source_doc_id}
        )
        record = result.single()
        return record["cnt"] > 0 if record else False
