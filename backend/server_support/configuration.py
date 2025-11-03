"""Configuration helpers shared by the backend server endpoints."""

from __future__ import annotations

import logging
from typing import Any, Dict

import yaml

from src.utils.setting.editor import (  # type: ignore
    load_config as load_settings_config,
    save_config as save_settings_config,
)
from src.utils.setting.settings import settings  # type: ignore

from .paths import CONFIG_PATH

LOGGER = logging.getLogger(__name__)

DATABASES_CONFIG_NAME = "databases"
LLM_CONFIG_NAME = "llm"


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
    presets = config.get("presets") or []
    if not isinstance(presets, list):
        presets = []
    config["presets"] = presets
    filter_llm = config.get("filter_llm") or {}
    if not isinstance(filter_llm, dict):
        filter_llm = {}
    config["filter_llm"] = filter_llm
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
