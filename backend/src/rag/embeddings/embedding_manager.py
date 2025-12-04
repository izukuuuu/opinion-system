"""Embedding manager for handling multiple embedding models."""

from typing import Dict, Any, Optional, List, Union
import logging
from pathlib import Path

from .base import BaseEmbedder
from .huggingface_embedder import HuggingFaceEmbedder
from .openai_embedder import OpenAIEmbedder
from .cache_embedder import CachedEmbedder

logger = logging.getLogger(__name__)


class EmbeddingManager:
    """Manager for multiple embedding models with automatic selection."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.embedders: Dict[str, BaseEmbedder] = {}
        self.default_model = None
        self._initialize_embedders()

    def _initialize_embedders(self):
        """Initialize available embedding models."""
        # Initialize HuggingFace embedder
        try:
            hf_config = self.config.get("huggingface", {})
            hf_embedder = HuggingFaceEmbedder(
                model_name=hf_config.get("model_name", "sentence-transformers/all-MiniLM-L6-v2"),
                config=hf_config
            )
            self.embedders["huggingface"] = hf_embedder
            if self.default_model is None:
                self.default_model = "huggingface"
        except Exception as e:
            logger.warning(f"Failed to initialize HuggingFace embedder: {e}")

        # Initialize OpenAI embedder if API key is provided
        if self.config.get("openai", {}).get("api_key"):
            try:
                openai_config = self.config.get("openai", {})
                openai_embedder = OpenAIEmbedder(
                    model_name=openai_config.get("model_name", "text-embedding-ada-002"),
                    config=openai_config
                )
                self.embedders["openai"] = openai_embedder
                if self.default_model is None:
                    self.default_model = "openai"
            except Exception as e:
                logger.warning(f"Failed to initialize OpenAI embedder: {e}")

        # Wrap embedders with cache if enabled
        if self.config.get("cache", {}).get("enabled", True):
            cache_config = self.config.get("cache", {})
            for name, embedder in list(self.embedders.items()):
                cached_embedder = CachedEmbedder(
                    embedder=embedder,
                    cache_dir=cache_config.get("dir"),
                    config=cache_config
                )
                self.embedders[f"{name}_cached"] = cached_embedder
                # Make cached version default if caching is enabled
                if name == self.default_model:
                    self.default_model = f"{name}_cached"

    def get_embedder(self, model_name: Optional[str] = None) -> BaseEmbedder:
        """Get an embedding model by name."""
        if model_name is None:
            model_name = self.default_model

        if model_name not in self.embedders:
            raise ValueError(f"Embedding model '{model_name}' not available. Available models: {list(self.embedders.keys())}")

        return self.embedders[model_name]

    def embed(self,
              texts: Union[str, List[str]],
              model_name: Optional[str] = None,
              **kwargs) -> Union[List[float], List[List[float]]]:
        """Generate embeddings using the specified model."""
        embedder = self.get_embedder(model_name)
        return embedder.embed(texts, **kwargs)

    def get_available_models(self) -> List[str]:
        """Get list of available embedding models."""
        return list(self.embedders.keys())

    def get_model_info(self, model_name: Optional[str] = None) -> Dict[str, Any]:
        """Get information about a model."""
        embedder = self.get_embedder(model_name)
        info = {
            "type": type(embedder).__name__,
            "config": embedder.config
        }

        # Add model-specific info
        if hasattr(embedder, 'model_name'):
            info["model_name"] = embedder.model_name
        if hasattr(embedder, 'get_dimension'):
            info["dimension"] = embedder.get_dimension()

        # Add cache info if it's a cached embedder
        if isinstance(embedder, CachedEmbedder):
            info.update(embedder.get_cache_stats())

        return info

    def preload_model(self, model_name: str):
        """Preload a model into memory."""
        embedder = self.get_embedder(model_name)
        # Trigger model initialization by embedding a sample text
        embedder.embed("preload sample")
        logger.info(f"Preloaded model: {model_name}")

    def unload_model(self, model_name: str):
        """Unload a model from memory (if supported)."""
        # Most embedders don't support explicit unloading
        # This is a placeholder for future implementation
        logger.info(f"Model unloading not implemented for: {model_name}")

    def clear_cache(self, model_name: Optional[str] = None):
        """Clear cache for a model or all models."""
        if model_name:
            embedder = self.get_embedder(model_name)
            if isinstance(embedder, CachedEmbedder):
                embedder.clear_cache()
        else:
            # Clear cache for all cached embedders
            for name, embedder in self.embedders.items():
                if isinstance(embedder, CachedEmbedder):
                    embedder.clear_cache()

    def save_config(self, path: Union[str, Path]):
        """Save the embedding manager configuration."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        import json
        with open(path, 'w') as f:
            json.dump(self.config, f, indent=2)
        logger.info(f"Configuration saved to {path}")

    @classmethod
    def load_config(cls, path: Union[str, Path]) -> 'EmbeddingManager':
        """Load embedding manager from configuration file."""
        path = Path(path)
        import json
        with open(path, 'r') as f:
            config = json.load(f)
        return cls(config)