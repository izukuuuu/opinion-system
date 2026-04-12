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
from copy import deepcopy
from pathlib import Path
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
LLM_LOCAL_CONFIG_FILENAME = f"{LLM_CONFIG_NAME}.local.yaml"
_SECRET_CREDENTIAL_FIELDS = {
    "openai_api_key",
    "opinion_openai_api_key",
    "qwen_api_key",
    "dashscope_api_key",
    "report_api_key",
    "langsmith_api_key",
}


def _deep_merge_dict(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged: Dict[str, Any] = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge_dict(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


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


def _load_local_llm_config() -> Dict[str, Any]:
    """Load the local ignored LLM override file when present."""

    local_path = CONFIGS_DIR / f"{LLM_CONFIG_NAME}.local.yaml"
    if not local_path.is_file():
        return {}

    with local_path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if not isinstance(data, dict):
        return {}
    return data


def _persist_yaml_file(path: Path, data: Dict[str, Any]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(data, fh, allow_unicode=True, sort_keys=False)


def _prune_empty_dicts(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: Dict[str, Any] = {}
        for key, item in value.items():
            pruned = _prune_empty_dicts(item)
            if isinstance(pruned, dict) and not pruned:
                continue
            cleaned[key] = pruned
        return cleaned
    if isinstance(value, list):
        return [_prune_empty_dicts(item) for item in value]
    return value


def _remove_nested_value(target: Dict[str, Any], path: tuple[str, ...]) -> None:
    current: Any = target
    parents: list[tuple[Dict[str, Any], str]] = []
    for key in path[:-1]:
        if not isinstance(current, dict):
            return
        child = current.get(key)
        if not isinstance(child, dict):
            return
        parents.append((current, key))
        current = child
    if not isinstance(current, dict):
        return
    current.pop(path[-1], None)
    while parents:
        parent, key = parents.pop()
        child = parent.get(key)
        if isinstance(child, dict) and not child:
            parent.pop(key, None)
        else:
            break


def _get_nested_mapping(source: Dict[str, Any], path: tuple[str, ...]) -> Dict[str, Any]:
    current: Any = source
    for key in path:
        if not isinstance(current, dict):
            return {}
        current = current.get(key)
    return current if isinstance(current, dict) else {}


def _merge_credentials_with_local_priority(
    base_credentials: Dict[str, Any],
    override_credentials: Dict[str, Any],
) -> Dict[str, Any]:
    merged: Dict[str, Any] = deepcopy(base_credentials)
    for key, value in override_credentials.items():
        if key in _SECRET_CREDENTIAL_FIELDS:
            text = str(value).strip() if value is not None else ""
            if text:
                merged[key] = text
            elif key not in merged:
                merged[key] = ""
            continue
        if key == "openai_base_url":
            text = str(value).strip() if value is not None else ""
            if text:
                merged[key] = text
            elif key not in merged:
                merged[key] = ""
            continue
        merged[key] = deepcopy(value)
    return merged


def _sanitize_llm_config_for_persistence(config: Dict[str, Any]) -> Dict[str, Any]:
    sanitized = deepcopy(config)
    credentials = sanitized.get("credentials")
    if isinstance(credentials, dict):
        for field in _SECRET_CREDENTIAL_FIELDS:
            credentials.pop(field, None)
    _remove_nested_value(
        sanitized,
        ("langchain", "report", "runtime", "observability", "langsmith", "api_key"),
    )
    return _prune_empty_dicts(sanitized)


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


def get_active_database_connection(config: Dict[str, Any] | None = None) -> Dict[str, Any]:
    data = config if isinstance(config, dict) else load_databases_config()
    active_id = str(data.get("active") or "").strip()
    connections = data.get("connections") if isinstance(data.get("connections"), list) else []
    for connection in connections:
        if not isinstance(connection, dict):
            continue
        if str(connection.get("id") or "").strip() == active_id:
            return connection
    return {}


def persist_databases_config(config: Dict[str, Any]) -> None:
    """Persist and reload database configuration settings."""

    save_settings_config(DATABASES_CONFIG_NAME, config)
    reload_settings()


def load_llm_config() -> Dict[str, Any]:
    """Return the configured large language model presets."""

    config = load_settings_config(LLM_CONFIG_NAME)
    static_config = _deep_merge_dict(_load_static_llm_config(), _load_local_llm_config())

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

    langchain: Dict[str, Any] = {}
    static_langchain = static_config.get("langchain")
    if isinstance(static_langchain, dict):
        langchain.update(static_langchain)
    dynamic_langchain = config.get("langchain")
    if isinstance(dynamic_langchain, dict):
        langchain.update(dynamic_langchain)

    static_report_tree = static_langchain.get("report") if isinstance(static_langchain, dict) and isinstance(static_langchain.get("report"), dict) else {}
    dynamic_report_tree = dynamic_langchain.get("report") if isinstance(dynamic_langchain, dict) and isinstance(dynamic_langchain.get("report"), dict) else {}
    report_tree = _deep_merge_dict(static_report_tree, dynamic_report_tree)
    runtime_tree = report_tree.get("runtime") if isinstance(report_tree.get("runtime"), dict) else {}
    runtime_tree = deepcopy(runtime_tree)

    legacy_static_runtime = static_langchain.get("report_runtime") if isinstance(static_langchain, dict) and isinstance(static_langchain.get("report_runtime"), dict) else {}
    legacy_dynamic_runtime = dynamic_langchain.get("report_runtime") if isinstance(dynamic_langchain, dict) and isinstance(dynamic_langchain.get("report_runtime"), dict) else {}
    legacy_runtime = _deep_merge_dict(legacy_static_runtime, legacy_dynamic_runtime)
    model_tree = runtime_tree.get("model") if isinstance(runtime_tree.get("model"), dict) else {}
    runtime_tree["model"] = _deep_merge_dict(legacy_runtime, model_tree)
    report_tree["runtime"] = runtime_tree
    if report_tree:
        langchain["report"] = report_tree
    config["langchain"] = langchain

    credentials: Dict[str, Any] = {}
    static_credentials = static_config.get("credentials")
    if isinstance(static_credentials, dict):
        credentials.update(static_credentials)
    dynamic_credentials = config.get("credentials")
    if isinstance(dynamic_credentials, dict):
        credentials = _merge_credentials_with_local_priority(credentials, dynamic_credentials)
    legacy_langsmith = _get_nested_mapping(
        langchain,
        ("report", "runtime", "observability", "langsmith"),
    )
    legacy_langsmith_api_key = legacy_langsmith.get("api_key") or ""
    if isinstance(legacy_langsmith_api_key, str) and legacy_langsmith_api_key.strip():
        credentials.setdefault("langsmith_api_key", legacy_langsmith_api_key.strip())
    config["credentials"] = credentials

    return config


def persist_llm_config(config: Dict[str, Any]) -> None:
    """Persist and reload LLM configuration settings."""

    save_settings_config(LLM_CONFIG_NAME, _sanitize_llm_config_for_persistence(config))
    reload_settings()


def load_llm_local_config() -> Dict[str, Any]:
    """Return the local ignored LLM override payload."""

    return _load_local_llm_config()


def persist_llm_local_config(config: Dict[str, Any]) -> None:
    """Persist local ignored LLM overrides and refresh settings."""

    local_path = CONFIGS_DIR / LLM_LOCAL_CONFIG_FILENAME
    cleaned = _prune_empty_dicts(deepcopy(config))
    if cleaned:
        _persist_yaml_file(local_path, cleaned)
    elif local_path.exists():
        local_path.unlink()
    reload_settings()


def update_llm_local_secrets(
    *,
    credential_updates: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Update secret-only local overrides without touching tracked config."""

    local_config = load_llm_local_config()
    credentials = local_config.get("credentials")
    if not isinstance(credentials, dict):
        credentials = {}
    if isinstance(credential_updates, dict):
        for key, value in credential_updates.items():
            if key not in _SECRET_CREDENTIAL_FIELDS:
                continue
            text = str(value).strip() if value is not None else ""
            if text:
                credentials[key] = text
            else:
                credentials.pop(key, None)
    if credentials:
        local_config["credentials"] = credentials
    else:
        local_config.pop("credentials", None)
    _remove_nested_value(
        local_config,
        ("langchain", "report", "runtime", "observability", "langsmith", "api_key"),
    )

    persist_llm_local_config(local_config)
    return local_config


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
    "get_active_database_connection",
    "load_config",
    "load_databases_config",
    "load_llm_config",
    "load_llm_local_config",
    "persist_databases_config",
    "persist_llm_config",
    "persist_llm_local_config",
    "reload_settings",
    "update_llm_local_secrets",
]
