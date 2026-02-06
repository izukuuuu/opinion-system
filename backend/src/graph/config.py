"""
图模块配置：Neo4j 连接与同步选项。
从 configs/neo4j.yaml 读取，密码可通过环境变量 NEO4J_PASSWORD 注入。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict

try:
    import yaml
except ImportError:
    yaml = None


def _get_configs_root() -> Path:
    try:
        from ..utils.setting.paths import get_configs_root
        return get_configs_root()
    except Exception:
        return Path(__file__).resolve().parents[2] / "configs"


def get_graph_config() -> Dict[str, Any]:
    """
    读取 Neo4j 与图同步配置。
    返回 dict：uri, user, password, sync_batch_size, enable_entity_extraction, enable_chunk_embedding 等。
    密码优先从环境变量 NEO4J_PASSWORD 读取。
    """
    root = _get_configs_root()
    path = root / "neo4j.yaml"
    cfg: Dict[str, Any] = {
        "uri": os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
        "user": os.environ.get("NEO4J_USER", "neo4j"),
        "password": os.environ.get("NEO4J_PASSWORD", ""),
        "sync_batch_size": 1000,
        "enable_entity_extraction": True,
        "enable_chunk_embedding": True,
    }
    if path.exists() and yaml is not None:
        try:
            with open(path, "r", encoding="utf-8") as f:
                file_cfg = yaml.safe_load(f) or {}
            cfg.update(file_cfg)
        except Exception:
            pass
    if not cfg.get("password") and os.environ.get("NEO4J_PASSWORD"):
        cfg["password"] = os.environ.get("NEO4J_PASSWORD")
    return cfg


def is_neo4j_configured() -> bool:
    """判断 Neo4j 是否已配置（uri 非空且 password 非空或允许无密码）。"""
    c = get_graph_config()
    uri = (c.get("uri") or "").strip()
    if not uri:
        return False
    # 本地开发可能无密码
    return True
