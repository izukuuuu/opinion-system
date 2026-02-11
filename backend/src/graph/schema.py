"""
Neo4j 图结构定义：约束、索引与初始化。
与 3.1.1 节点/关系一致，不写业务数据，只写结构。
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional

LOG = logging.getLogger(__name__)

# 默认 8 个渠道（平台），与文档一致；可在 neo4j.yaml 中覆盖
DEFAULT_PLATFORMS = [
    "微信", "微博", "新闻APP", "新闻网站", "电子报", "视频", "论坛", "自媒体",
]


def _run(driver: Any, queries: List[str], description: str = "") -> None:
    with driver.session() as session:
        for q in queries:
            try:
                session.run(q)
            except Exception as e:
                if "EquivalentSchemaRuleAlreadyExists" in str(e) or "already exists" in str(e).lower():
                    pass
                else:
                    LOG.warning("Schema statement failed (%s): %s", description, e)


def init_vector_indexes(driver: Any) -> None:
    """初始化向量索引 (Neo4j 5.x+)"""
    # 注意：Neo4j 向量索引创建通常是 idempotent 的，但最好检查是否存在
    # 这里假设使用 1024 维 (bge-large-zh-v1.5) 和 cosine 相似度
    # 索引名: chunk_embedding_vec
    queries = [
        """
        CREATE VECTOR INDEX chunk_embedding_vec IF NOT EXISTS
        FOR (c:Chunk) ON (c.embedding)
        OPTIONS {indexConfig: {
            `vector.dimensions`: 1024,
            `vector.similarity_function`: 'cosine'
        }}
        """
    ]
    _run(driver, queries, "vector_indexes")


def init_fulltext_indexes(driver: Any) -> None:
    """初始化全文索引"""
    # 索引名: ft_content
    queries = [
        """
        CREATE FULLTEXT INDEX ft_content IF NOT EXISTS
        FOR (p:Post) ON EACH [p.title, p.contents]
        """
    ]
    _run(driver, queries, "fulltext_indexes")


def init_schema(driver: Any, seed_platforms: Optional[List[str]] = None) -> None:
    """
    初始化图结构：约束、索引；可选预置 Platform 节点。
    seed_platforms: 若提供则 MERGE 这些平台名称；None 则使用 DEFAULT_PLATFORMS。
    """
    # 唯一性约束（Neo4j 5.x 用 CREATE CONSTRAINT ... FOR ... REQUIRE ... UNIQUE）
    constraints = [
        "CREATE CONSTRAINT post_id IF NOT EXISTS FOR (p:Post) REQUIRE p.id IS UNIQUE",
        "CREATE CONSTRAINT platform_name IF NOT EXISTS FOR (p:Platform) REQUIRE p.name IS UNIQUE",
        "CREATE CONSTRAINT account_id IF NOT EXISTS FOR (a:Account) REQUIRE a.id IS UNIQUE",
        "CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE",
        "CREATE CONSTRAINT chunk_id IF NOT EXISTS FOR (c:Chunk) REQUIRE c.id IS UNIQUE",
        "CREATE CONSTRAINT topic_id IF NOT EXISTS FOR (t:Topic) REQUIRE t.id IS UNIQUE",
        # 新增 GraphRAG 核心节点约束
        "CREATE CONSTRAINT claim_id IF NOT EXISTS FOR (c:Claim) REQUIRE c.id IS UNIQUE",
        "CREATE CONSTRAINT frame_id IF NOT EXISTS FOR (f:Frame) REQUIRE f.id IS UNIQUE",
        "CREATE CONSTRAINT event_id IF NOT EXISTS FOR (e:Event) REQUIRE e.id IS UNIQUE",
        "CREATE CONSTRAINT source_doc_id IF NOT EXISTS FOR (s:SourceDoc) REQUIRE s.id IS UNIQUE",
        "CREATE CONSTRAINT forecast_stage_id IF NOT EXISTS FOR (f:ForecastStage) REQUIRE f.id IS UNIQUE",
    ]
    _run(driver, constraints, "constraints")

    # 索引（若无唯一约束的查询字段）
    indexes = [
        "CREATE INDEX post_topic IF NOT EXISTS FOR (p:Post) ON (p.topic)",
        "CREATE INDEX post_channel IF NOT EXISTS FOR (p:Post) ON (p.channel)",
        "CREATE INDEX post_published_at IF NOT EXISTS FOR (p:Post) ON (p.published_at)",
        "CREATE INDEX chunk_post_id IF NOT EXISTS FOR (c:Chunk) ON (c.post_id)",
        "CREATE INDEX entity_name IF NOT EXISTS FOR (e:Entity) ON (e.name)",
        "CREATE INDEX entity_type IF NOT EXISTS FOR (e:Entity) ON (e.type)",
        # 新增节点索引
        "CREATE INDEX topic_name IF NOT EXISTS FOR (t:Topic) ON (t.name)",
        "CREATE INDEX event_name IF NOT EXISTS FOR (e:Event) ON (e.name)",
        "CREATE INDEX claim_content IF NOT EXISTS FOR (c:Claim) ON (c.content)",
    ]
    _run(driver, indexes, "indexes")

    # 初始化向量索引和全文索引
    init_vector_indexes(driver)
    init_fulltext_indexes(driver)

    # 预置 Platform 节点
    platforms = seed_platforms if seed_platforms is not None else DEFAULT_PLATFORMS
    with driver.session() as session:
        for name in platforms:
            if not (name and str(name).strip()):
                continue
            try:
                session.run(
                    "MERGE (p:Platform {name: $name}) SET p.name = $name",
                    {"name": str(name).strip()},
                )
            except Exception as e:
                LOG.warning("Seed Platform %s failed: %s", name, e)
