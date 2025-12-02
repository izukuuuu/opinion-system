"""
后端服务配置辅助模块

为舆情分析系统后端接口提供统一的配置加载、保存与刷新工具，支持静态配置文件与动态运行时配置的读写，主要功能包括：

1. 加载/保存数据库连接配置（支持多数据库连接结构）。
2. 加载/保存大语言模型（LLM）相关配置，包括模型预设、过滤模型、助手模型、API凭证等。
3. 支持静态配置（如 configs/llm.yaml）与动态配置（如 settings/）的合并与优先级处理。
4. 提供配置热加载能力，保证运行时配置变更后即时生效。
5. 提供过滤AI（filter_llm）当前配置的简要概览，便于前端展示。
6. 兼容异常处理，保证接口健壮性。

主要导出函数：
- load_config/load_databases_config/load_llm_config：加载各类配置
- persist_databases_config/persist_llm_config：保存并刷新配置
- reload_settings：刷新运行时配置
- filter_ai_overview：获取过滤AI配置摘要

适用场景：
- 后端接口配置管理
- 管理后台配置编辑
- 动态参数热加载
"""

from __future__ import annotations

import logging
from typing import Any, Dict

import yaml

from src.utils.setting.editor import (  # type: ignore
    load_config as load_settings_config,
    save_config as save_settings_config,
)
from src.utils.setting.settings import settings  # type: ignore

from .paths import CONFIG_PATH, CONFIGS_DIR

LOGGER = logging.getLogger(__name__)

DATABASES_CONFIG_NAME = "databases"
LLM_CONFIG_NAME = "llm"


def _load_static_llm_config() -> Dict[str, Any]:
    """Load the default LLM configuration bundled with the backend."""

    static_path = CONFIGS_DIR / f"{LLM_CONFIG_NAME}.yaml"
    if not static_path.is_file():
        return {}

    with static_path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        return {}
    return data


def load_config() -> Dict[str, Any]:
    """Load the static backend configuration file."""

    if CONFIG_PATH.is_file():
        with CONFIG_PATH.open("r", encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    LOGGER.warning("Configuration file %s not found, using defaults", CONFIG_PATH)
    return {}


def reload_settings() -> None:
    """Refresh dynamic runtime settings after persistence."""

    try:
        settings.reload()
    except Exception:  # pragma: no cover - reload failures should not crash endpoints
        LOGGER.warning("Failed to reload runtime settings", exc_info=True)


def load_databases_config() -> Dict[str, Any]:
    """Return the structured settings payload for database connections."""

    config = load_settings_config(DATABASES_CONFIG_NAME)
    connections = config.get("connections") or []
    if not isinstance(connections, list):
        connections = []
    config["connections"] = connections
    return config


def persist_databases_config(config: Dict[str, Any]) -> None:
    """Persist and reload database configuration settings."""

    save_settings_config(DATABASES_CONFIG_NAME, config)
    reload_settings()


def load_llm_config() -> Dict[str, Any]:
    """Return the configured large language model presets."""

    config = load_settings_config(LLM_CONFIG_NAME)
    static_config = _load_static_llm_config()

    presets = config.get("presets")
    if not isinstance(presets, list) or any(not isinstance(item, dict) for item in presets):
        presets = static_config.get("presets") if isinstance(static_config.get("presets"), list) else []
    config["presets"] = presets or []

    filter_llm: Dict[str, Any] = {}
    static_filter = static_config.get("filter_llm")
    if isinstance(static_filter, dict):
        filter_llm.update(static_filter)
    dynamic_filter = config.get("filter_llm")
    if isinstance(dynamic_filter, dict):
        filter_llm.update(dynamic_filter)
    config["filter_llm"] = filter_llm

    assistant: Dict[str, Any] = {}
    static_assistant = static_config.get("assistant")
    if isinstance(static_assistant, dict):
        assistant.update(static_assistant)
    dynamic_assistant = config.get("assistant")
    if isinstance(dynamic_assistant, dict):
        assistant.update(dynamic_assistant)
    config["assistant"] = assistant

    embedding_llm: Dict[str, Any] = {}
    static_embedding = static_config.get("embedding_llm")
    if isinstance(static_embedding, dict):
        embedding_llm.update(static_embedding)
    dynamic_embedding = config.get("embedding_llm")
    if isinstance(dynamic_embedding, dict):
        embedding_llm.update(dynamic_embedding)
    config["embedding_llm"] = embedding_llm

    credentials = config.get("credentials")
    if not isinstance(credentials, dict):
        credentials = {}
    config["credentials"] = credentials

    return config


def persist_llm_config(config: Dict[str, Any]) -> None:
    """Persist and reload LLM configuration settings."""

    save_settings_config(LLM_CONFIG_NAME, config)
    reload_settings()


def filter_ai_overview() -> Dict[str, Any]:
    """Return the active configuration summary for the filter LLM."""

    cfg = load_llm_config().get("filter_llm", {})
    if not isinstance(cfg, dict):
        cfg = {}
    return {
        "provider": str(cfg.get("provider") or "").strip() or "qwen",
        "model": str(cfg.get("model") or "").strip(),
        "qps": cfg.get("qps"),
        "batch_size": cfg.get("batch_size"),
        "truncation": cfg.get("truncation"),
    }


__all__ = [
    "DATABASES_CONFIG_NAME",
    "LLM_CONFIG_NAME",
    "filter_ai_overview",
    "load_config",
    "load_databases_config",
    "load_llm_config",
    "persist_databases_config",
    "persist_llm_config",
    "reload_settings",
]
