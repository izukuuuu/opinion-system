"""
内容分析提示词管理辅助模块

用于读取/保存 contentanalysis 提示词 YAML，便于前端配置。
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import yaml

from .paths import CONTENT_PROMPT_DIR


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def content_prompt_path(topic: str) -> Path:
    """Return the YAML path for a topic-specific contentanalysis prompt."""

    safe_topic = str(topic or "").strip()
    if not safe_topic:
        raise ValueError("Missing topic identifier")
    normalised = safe_topic.replace("/", "_").replace("\\", "_")
    CONTENT_PROMPT_DIR.mkdir(parents=True, exist_ok=True)
    return CONTENT_PROMPT_DIR / f"{normalised}.yaml"


def load_content_prompt_config(topic: str) -> Dict[str, Any]:
    """Load contentanalysis prompt config for a topic."""

    path = content_prompt_path(topic)
    if not path.exists():
        return {
            "topic": topic,
            "exists": False,
            "system_prompt": "",
            "analysis_prompt": "",
            "path": str(path),
        }

    try:
        with path.open("r", encoding="utf-8") as fh:
            payload = yaml.safe_load(fh) or {}
    except Exception as exc:  # pragma: no cover - defensive for malformed YAML
        raise ValueError(f"读取提示词配置失败: {exc}") from exc

    system_prompt = str(payload.get("system_prompt") or "")
    analysis_prompt = str(payload.get("analysis_prompt") or "")
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}

    return {
        "topic": topic,
        "exists": True,
        "system_prompt": system_prompt,
        "analysis_prompt": analysis_prompt,
        "metadata": metadata,
        "path": str(path),
    }


def persist_content_prompt_config(topic: str, system_prompt: str, analysis_prompt: str) -> Dict[str, Any]:
    """Persist system/analysis prompts for contentanalysis."""

    path = content_prompt_path(topic)
    if not system_prompt.strip() and not analysis_prompt.strip():
        raise ValueError("system_prompt 与 analysis_prompt 不能同时为空")

    payload: Dict[str, Any] = {
        "system_prompt": str(system_prompt or "").rstrip(),
        "analysis_prompt": str(analysis_prompt or "").rstrip(),
        "metadata": {
            "updated_at": _utc_now(),
            "version": 1,
        },
    }

    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(payload, fh, allow_unicode=True, sort_keys=False)

    return load_content_prompt_config(topic)


__all__ = [
    "content_prompt_path",
    "load_content_prompt_config",
    "persist_content_prompt_config",
]
