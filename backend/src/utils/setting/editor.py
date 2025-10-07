"""Utility helpers for loading and persisting YAML-based project settings."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import yaml

from .paths import get_configs_root


def _ensure_config_dir() -> Path:
    config_dir = get_configs_root()
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_config_path(name: str) -> Path:
    """Return the absolute path for a named configuration file."""
    config_dir = _ensure_config_dir()
    filename = f"{name}.yaml" if not name.endswith(".yaml") else name
    return config_dir / filename


def load_config(name: str) -> Dict[str, Any]:
    """Load a configuration file and return its contents as a dictionary."""
    path = get_config_path(name)
    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8") as stream:
        data = yaml.safe_load(stream) or {}
    if not isinstance(data, dict):
        return {}
    return data


def save_config(name: str, data: Dict[str, Any]) -> None:
    """Persist a configuration dictionary to disk as YAML."""
    path = get_config_path(name)
    with path.open("w", encoding="utf-8") as stream:
        yaml.safe_dump(data, stream, allow_unicode=True, sort_keys=False)
