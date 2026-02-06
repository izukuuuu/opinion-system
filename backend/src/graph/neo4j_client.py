"""
Neo4j 连接与会话管理。
"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Generator, Optional

from .config import get_graph_config, is_neo4j_configured

LOG = logging.getLogger(__name__)
_driver: Any = None


def get_driver():
    """创建或返回已存在的 Neo4j Driver。未配置或连接失败时抛出异常。"""
    global _driver
    if not is_neo4j_configured():
        raise RuntimeError("Neo4j 未配置：请设置 configs/neo4j.yaml 或环境变量 NEO4J_URI / NEO4J_PASSWORD")
    if _driver is None:
        try:
            from neo4j import GraphDatabase
        except ImportError as e:
            raise RuntimeError("请安装 neo4j 驱动: pip install neo4j") from e
        cfg = get_graph_config()
        uri = cfg.get("uri", "bolt://localhost:7687")
        user = cfg.get("user", "neo4j")
        password = cfg.get("password", "")
        _driver = GraphDatabase.driver(uri, auth=(user, password))
        try:
            _driver.verify_connectivity()
        except Exception as e:
            LOG.exception("Neo4j 连接验证失败")
            _driver.close()
            _driver = None
            raise RuntimeError(f"Neo4j 连接失败: {e}") from e
    return _driver


@contextmanager
def get_session() -> Generator[Any, None, None]:
    """Context manager 返回 Neo4j 会话。"""
    driver = get_driver()
    session = driver.session()
    try:
        yield session
    finally:
        session.close()


def close_driver() -> None:
    """关闭全局 Driver。"""
    global _driver
    if _driver is not None:
        try:
            _driver.close()
        except Exception:
            pass
        _driver = None
