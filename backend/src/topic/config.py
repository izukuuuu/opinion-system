"""BERTopic global configuration management.

This module handles the loading and saving of global BERTopic settings,
specifically for embedding model configuration.
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
    }
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
            
        return config
    except Exception:
        return DEFAULT_BERTOPIC_CONFIG.copy()


def save_bertopic_config(config: Dict[str, Any]) -> Dict[str, Any]:
    """Save global BERTopic configuration."""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    with CONFIG_FILE.open("w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
        
    return load_bertopic_config()
