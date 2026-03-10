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

DEFAULT_BERTOPIC_CONFIG = {
    "embedding": {
        "model_name": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        "device": "cpu",
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
