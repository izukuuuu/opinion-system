"""BERTopic global configuration management.

This module handles the loading and saving of global BERTopic settings,
including embedding model configuration and global custom filters.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from ..utils.setting.paths import get_configs_root

CONFIG_FILE = get_configs_root() / "bertopic.json"
STOPWORDS_FILE = get_configs_root() / "stopwords.txt"

DEFAULT_BERTOPIC_CONFIG = {
    "embedding": {
        "model_name": "moka-ai/m3e-base",
        "device": "auto",
        "batch_size": 32
    },
    "custom_filters": [
        {"category": "明星八卦", "description": "包含明星、网红、娱乐圈等与专题无关的八卦内容"},
        {"category": "广告推广", "description": "包含广告、营销推广、品牌植入等商业推广内容"},
    ]
}


def load_bertopic_config() -> Dict[str, Any]:
    """Load global BERTopic configuration."""
    if not CONFIG_FILE.exists():
        return DEFAULT_BERTOPIC_CONFIG.copy()

    try:
        with CONFIG_FILE.open("r", encoding="utf-8") as f:
            config = json.load(f)

        # Ensure structure matches defaults
        if "embedding" not in config:
            config["embedding"] = DEFAULT_BERTOPIC_CONFIG["embedding"].copy()
        if "custom_filters" not in config:
            config["custom_filters"] = list(DEFAULT_BERTOPIC_CONFIG["custom_filters"])

        return config
    except Exception:
        return DEFAULT_BERTOPIC_CONFIG.copy()


def save_bertopic_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Save global BERTopic configuration."""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)

    with CONFIG_FILE.open("w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

    return load_bertopic_config()


def _normalize_stopwords_content(content: Any) -> str:
    text = str(content or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = []
    seen = set()
    for raw in text.split("\n"):
        value = str(raw or "").strip().lstrip("\ufeff")
        if not value or value in seen:
            continue
        seen.add(value)
        lines.append(value)
    if not lines:
        return ""
    return "\n".join(lines) + "\n"


def load_bertopic_stopwords() -> Dict[str, Any]:
    """Load BERTopic stopwords file content and metadata."""
    if not STOPWORDS_FILE.exists():
        return {
            "path": str(STOPWORDS_FILE),
            "content": "",
            "line_count": 0,
        }

    try:
        content = STOPWORDS_FILE.read_text(encoding="utf-8")
    except Exception:
        content = ""

    normalized = _normalize_stopwords_content(content)
    line_count = len([line for line in normalized.splitlines() if line.strip()])
    return {
        "path": str(STOPWORDS_FILE),
        "content": normalized,
        "line_count": line_count,
    }


def save_bertopic_stopwords(content: Any) -> Dict[str, Any]:
    """Save BERTopic stopwords file and return refreshed payload."""
    STOPWORDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    normalized = _normalize_stopwords_content(content)
    STOPWORDS_FILE.write_text(normalized, encoding="utf-8")
    return load_bertopic_stopwords()
