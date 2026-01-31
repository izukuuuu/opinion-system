"""RAG configuration management for backend server."""

from __future__ import annotations

import logging
from typing import Any, Dict

from src.utils.setting.editor import (  # type: ignore
    load_config as load_settings_config,
    save_config as save_settings_config,
)
from src.utils.setting.settings import settings  # type: ignore

from .paths import CONFIGS_DIR

LOGGER = logging.getLogger(__name__)

RAG_CONFIG_NAME = "rag"


def load_rag_config() -> Dict[str, Any]:
    """Load RAG configuration from settings."""
    try:
        config = load_settings_config(RAG_CONFIG_NAME)

        # Ensure required structure exists
        if "embedding" not in config:
            config["embedding"] = {
                "model_name": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
                "model_type": "huggingface",
                "batch_size": 32,
                "normalize": True,
                "device": "auto",
                "api_key": "",
                "cache_dir": ""
            }

        if "chunking" not in config:
            config["chunking"] = {
                "strategy": "size",
                "chunk_size": 512,
                "chunk_overlap": 50,
                "separator": "\n\n",
                "respect_sentence_boundary": True,
                "strip_whitespace": True
            }

        if "retrieval" not in config:
            config["retrieval"] = {
                "top_k": 10,
                "threshold": 0.0,
                "search_type": "vector",
                "include_metadata": True,
                "score_type": "cosine",
                "rerank": False,
                "enable_query_expansion": True,
                "enable_llm_summary": True,
                "llm_summary_mode": "strict"
            }
        else:
            # Add missing fields to existing config
            ret = config["retrieval"]
            if "enable_query_expansion" not in ret: ret["enable_query_expansion"] = True
            if "enable_llm_summary" not in ret: ret["enable_llm_summary"] = True
            if "llm_summary_mode" not in ret: ret["llm_summary_mode"] = "strict"

        if "storage" not in config:
            config["storage"] = {
                "storage_type": "file",
                "path": "./data/rag",
                "index_type": "flat",
                "metric": "cosine",
                "persist_index": True
            }

        if "processing" not in config:
            config["processing"] = {
                "lowercase": False,
                "remove_urls": True,
                "remove_emails": True,
                "remove_extra_whitespace": True,
                "remove_special_chars": False,
                "normalize_unicode": True
            }

        # Ensure API keys are masked for security
        if "api_keys" not in config:
            config["api_keys"] = {
                "openai": "",
                "cohere": "",
                "huggingface": ""
            }

        return config

    except Exception as e:
        LOGGER.error(f"Failed to load RAG config: {e}")
        return _get_default_rag_config()


def _get_default_rag_config() -> Dict[str, Any]:
    """Get default RAG configuration."""
    return {
        "embedding": {
            "model_name": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
            "model_type": "huggingface",
            "batch_size": 32,
            "normalize": True,
            "device": "auto",
            "api_key": "",
            "cache_dir": ""
        },
        "chunking": {
            "strategy": "size",
            "chunk_size": 512,
            "chunk_overlap": 50,
            "separator": "\n\n",
            "respect_sentence_boundary": True,
            "strip_whitespace": True
        },
        "retrieval": {
            "top_k": 10,
            "threshold": 0.0,
            "search_type": "vector",
            "include_metadata": True,
            "score_type": "cosine",
            "rerank": False,
            "enable_query_expansion": True,
            "enable_llm_summary": True,
            "llm_summary_mode": "strict"
        },
        "storage": {
            "storage_type": "file",
            "path": "./data/rag",
            "index_type": "flat",
            "metric": "cosine",
            "persist_index": True
        },
        "processing": {
            "lowercase": False,
            "remove_urls": True,
            "remove_emails": True,
            "remove_extra_whitespace": True,
            "remove_special_chars": False,
            "normalize_unicode": True
        },
        "api_keys": {
            "openai": "",
            "cohere": "",
            "huggingface": ""
        }
    }


def get_default_rag_config() -> Dict[str, Any]:
    """Public wrapper for default RAG configuration."""
    return _get_default_rag_config()


def persist_rag_config(config: Dict[str, Any]) -> None:
    """Save RAG configuration to settings."""
    try:
        # Make a copy to avoid modifying the input
        config_to_save = config.copy()

        # Ensure API keys are properly saved (masked in response, but saved fully)
        if "api_keys" in config_to_save:
            api_keys = config_to_save["api_keys"]
            # If any key is masked (contains *), don't overwrite it
            for provider in ["openai", "cohere", "huggingface"]:
                if api_keys.get(provider, "").find("*") >= 0:
                    # Load existing config to preserve the actual key
                    existing_config = load_rag_config()
                    existing_key = existing_config.get("api_keys", {}).get(provider, "")
                    if existing_key:
                        api_keys[provider] = existing_key

        save_settings_config(RAG_CONFIG_NAME, config_to_save)

        # Reload settings to make changes effective
        reload_settings()

        LOGGER.info("RAG configuration saved successfully")

    except Exception as e:
        LOGGER.error(f"Failed to save RAG config: {e}")
        raise


def reload_settings() -> None:
    """Refresh dynamic runtime settings after persistence."""
    try:
        settings.reload()
    except Exception:
        LOGGER.warning("Failed to reload runtime settings", exc_info=True)


def mask_api_keys(config: Dict[str, Any]) -> Dict[str, Any]:
    """Return config with API keys masked for frontend display."""
    masked_config = config.copy()

    if "api_keys" in masked_config:
        masked_keys = masked_config["api_keys"].copy()
        for provider, key in masked_keys.items():
            if key and not key.startswith("*****"):
                # Mask all but first 3 and last 3 characters
                if len(key) > 6:
                    masked_keys[provider] = key[:3] + "*" * (len(key) - 6) + key[-3:]
                else:
                    masked_keys[provider] = "*" * len(key)
        masked_config["api_keys"] = masked_keys

    return masked_config


def validate_rag_config(config: Dict[str, Any]) -> tuple[bool, list[str]]:
    """Validate RAG configuration."""
    errors = []

    # Validate embedding config
    if "embedding" not in config:
        errors.append("Embedding configuration is required")
    else:
        embedding = config["embedding"]
        if not embedding.get("model_name"):
            errors.append("Embedding model name is required")

        model_type = embedding.get("model_type", "")
        if model_type == "openai" and not config.get("api_keys", {}).get("openai"):
            errors.append("OpenAI API key is required for OpenAI models")

        batch_size = embedding.get("batch_size", 32)
        if not isinstance(batch_size, int) or batch_size < 1 or batch_size > 128:
            errors.append("Batch size must be an integer between 1 and 128")

    # Validate chunking config
    if "chunking" not in config:
        errors.append("Chunking configuration is required")
    else:
        chunking = config["chunking"]
        chunk_size = chunking.get("chunk_size", 512)
        if not isinstance(chunk_size, int) or chunk_size < 50 or chunk_size > 2048:
            errors.append("Chunk size must be an integer between 50 and 2048")

        chunk_overlap = chunking.get("chunk_overlap", 50)
        if not isinstance(chunk_overlap, int) or chunk_overlap < 0:
            errors.append("Chunk overlap must be a non-negative integer")

        if chunk_overlap >= chunk_size:
            errors.append("Chunk overlap must be less than chunk size")

    # Validate retrieval config
    if "retrieval" not in config:
        errors.append("Retrieval configuration is required")
    else:
        retrieval = config["retrieval"]
        top_k = retrieval.get("top_k", 10)
        if not isinstance(top_k, int) or top_k < 1 or top_k > 100:
            errors.append("Top-K must be an integer between 1 and 100")

        threshold = retrieval.get("threshold", 0.0)
        if not isinstance(threshold, (int, float)) or threshold < 0 or threshold > 1:
            errors.append("Similarity threshold must be a number between 0 and 1")

    # Validate storage config
    if "storage" not in config:
        errors.append("Storage configuration is required")
    else:
        storage = config["storage"]
        storage_type = storage.get("storage_type", "file")
        if storage_type not in ["file", "lance", "faiss", "chroma"]:
            errors.append("Storage type must be one of: file, lance, faiss, chroma")

        if storage_type != "file" and not storage.get("path"):
            errors.append("Storage path is required for non-file storage types")

    return len(errors) == 0, errors
