"""Runtime configuration helpers for the NetInsight integration."""
from __future__ import annotations

import os
from copy import deepcopy
from typing import Any, Dict

from ..utils.setting.editor import load_config as load_settings_config
from ..utils.setting.editor import save_config as save_settings_config
from ..utils.setting.settings import settings

CONFIG_NAME = "netinsight"

DEFAULT_CONFIG: Dict[str, Any] = {
    "credentials": {
        "user": "",
        "pass": "",
    },
    "runtime": {
        "headless": False,
        "no_proxy": False,
        "login_timeout_ms": 120000,
        "worker_idle_seconds": 90,
        "page_size": 50,
        "sort": "comments_desc",
        "info_type": "2",
        "browser_channel": "",
    },
    "planner": {
        "default_days": 30,
        "default_total_limit": 500,
        "default_platforms": ["微博"],
        "default_allocate_by_platform": False,
    },
}


def _merge_dict(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dict(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_netinsight_config() -> Dict[str, Any]:
    raw = load_settings_config(CONFIG_NAME)
    if not isinstance(raw, dict):
        raw = {}

    config = _merge_dict(DEFAULT_CONFIG, raw)

    credentials = config.get("credentials")
    if not isinstance(credentials, dict):
        credentials = {}
    credentials["user"] = str(
        os.getenv("NETINSIGHT_USER") or credentials.get("user") or ""
    ).strip()
    credentials["pass"] = str(
        os.getenv("NETINSIGHT_PASS") or credentials.get("pass") or ""
    ).strip()
    config["credentials"] = credentials

    runtime = config.get("runtime")
    if not isinstance(runtime, dict):
        runtime = {}
    runtime["headless"] = _safe_bool(runtime.get("headless", False))
    runtime["no_proxy"] = _safe_bool(runtime.get("no_proxy", False))
    runtime["login_timeout_ms"] = _safe_int(runtime.get("login_timeout_ms"), 120000, minimum=10000)
    runtime["worker_idle_seconds"] = _safe_int(runtime.get("worker_idle_seconds"), 90, minimum=15)
    runtime["page_size"] = _safe_int(runtime.get("page_size"), 50, minimum=10)
    runtime["sort"] = str(runtime.get("sort") or "comments_desc").strip() or "comments_desc"
    runtime["info_type"] = str(runtime.get("info_type") or "2").strip() or "2"
    runtime["browser_channel"] = str(runtime.get("browser_channel") or "").strip()
    config["runtime"] = runtime

    planner = config.get("planner")
    if not isinstance(planner, dict):
        planner = {}
    planner["default_days"] = _safe_int(planner.get("default_days"), 30, minimum=1)
    planner["default_total_limit"] = _safe_int(planner.get("default_total_limit"), 500, minimum=1)
    planner["default_allocate_by_platform"] = _safe_bool(planner.get("default_allocate_by_platform", False))
    default_platforms = planner.get("default_platforms")
    if not isinstance(default_platforms, list):
        default_platforms = ["微博"]
    planner["default_platforms"] = [
        str(item).strip() for item in default_platforms if str(item).strip()
    ] or ["微博"]
    config["planner"] = planner

    return config


def persist_netinsight_config(config: Dict[str, Any]) -> None:
    save_settings_config(CONFIG_NAME, config)
    try:
        settings.reload()
    except Exception:
        pass


def resolve_netinsight_credentials() -> Dict[str, str]:
    credentials = load_netinsight_config().get("credentials", {})
    if not isinstance(credentials, dict):
        credentials = {}
    return {
        "user": str(credentials.get("user") or "").strip(),
        "pass": str(credentials.get("pass") or "").strip(),
    }


def summarise_netinsight_credentials() -> Dict[str, Any]:
    credentials = resolve_netinsight_credentials()
    user = credentials.get("user") or ""
    return {
        "configured": bool(user and credentials.get("pass")),
        "user": user,
        "masked_user": mask_user(user),
        "password_configured": bool(credentials.get("pass")),
    }


def mask_user(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= 2:
        return "*" * len(text)
    if len(text) <= 6:
        return f"{text[:1]}***{text[-1:]}"
    return f"{text[:2]}***{text[-2:]}"


def _safe_int(value: Any, default: int, *, minimum: int = 0) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, parsed)


def _safe_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


__all__ = [
    "CONFIG_NAME",
    "DEFAULT_CONFIG",
    "load_netinsight_config",
    "mask_user",
    "persist_netinsight_config",
    "resolve_netinsight_credentials",
    "summarise_netinsight_credentials",
]
