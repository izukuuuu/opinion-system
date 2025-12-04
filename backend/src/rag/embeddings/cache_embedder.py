"""Cached embedding wrapper."""

from typing import List, Union, Dict, Any, Optional
import logging
import hashlib
import json
import pickle
from pathlib import Path

from .base import BaseEmbedder

logger = logging.getLogger(__name__)


class CachedEmbedder(BaseEmbedder):
    """Wrapper that caches embeddings to avoid recomputation."""

    def __init__(self, embedder: BaseEmbedder, cache_dir: Optional[Union[str, Path]] = None, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.embedder = embedder
        self.cache_dir = Path(cache_dir) if cache_dir else Path("./cache/embeddings")
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.memory_cache = {}
        self.use_memory_cache = config.get("use_memory_cache", True) if config else True

    def _get_cache_key(self, text: str) -> str:
        """Generate cache key for text."""
        # Include model info if available
        model_info = ""
        if hasattr(self.embedder, 'model_name'):
            model_info = self.embedder.model_name
        elif hasattr(self.embedder, 'model'):
            model_info = str(self.embedder.model)

        content = f"{model_info}:{text}"
        return hashlib.md5(content.encode('utf-8')).hexdigest()

    def _get_cache_path(self, cache_key: str) -> Path:
        """Get cache file path for key."""
        return self.cache_dir / f"{cache_key}.pkl"

    def _load_from_disk(self, cache_key: str) -> Optional[List[float]]:
        """Load embedding from disk cache."""
        cache_path = self._get_cache_path(cache_key)
        if cache_path.exists():
            try:
                with open(cache_path, 'rb') as f:
                    return pickle.load(f)
            except Exception as e:
                logger.warning(f"Failed to load cache for {cache_key}: {e}")
        return None

    def _save_to_disk(self, cache_key: str, embedding: List[float]):
        """Save embedding to disk cache."""
        cache_path = self._get_cache_path(cache_key)
        try:
            with open(cache_path, 'wb') as f:
                pickle.dump(embedding, f)
        except Exception as e:
            logger.warning(f"Failed to save cache for {cache_key}: {e}")

    def embed(self, texts: Union[str, List[str]], **kwargs) -> Union[List[float], List[List[float]]]:
        """Generate embeddings with caching."""
        # Handle single text input
        single_input = isinstance(texts, str)
        if single_input:
            texts = [texts]

        embeddings = []
        uncached_texts = []
        uncached_indices = []

        # Check cache for each text
        for i, text in enumerate(texts):
            cache_key = self._get_cache_key(text)

            # Check memory cache first
            if self.use_memory_cache and cache_key in self.memory_cache:
                embeddings.append(self.memory_cache[cache_key])
                continue

            # Check disk cache
            embedding = self._load_from_disk(cache_key)
            if embedding is not None:
                embeddings.append(embedding)
                # Store in memory cache
                if self.use_memory_cache:
                    self.memory_cache[cache_key] = embedding
            else:
                embeddings.append(None)
                uncached_texts.append(text)
                uncached_indices.append(i)

        # Generate embeddings for uncached texts
        if uncached_texts:
            try:
                new_embeddings = self.embedder.embed(uncached_texts, **kwargs)

                # Update cache and results
                for text, idx, embedding in zip(uncached_texts, uncached_indices, new_embeddings):
                    cache_key = self._get_cache_key(text)
                    embeddings[idx] = embedding

                    # Save to caches
                    if self.use_memory_cache:
                        self.memory_cache[cache_key] = embedding
                    self._save_to_disk(cache_key, embedding)

            except Exception as e:
                logger.error(f"Failed to generate embeddings: {e}")
                # Fill with None for failed embeddings
                for idx in uncached_indices:
                    embeddings[idx] = None

        # Return single embedding for single input
        return embeddings[0] if single_input else embeddings

    def get_dimension(self) -> int:
        """Get embedding dimension."""
        if hasattr(self.embedder, 'get_dimension'):
            return self.embedder.get_dimension()
        else:
            # Try to infer by embedding a sample text
            try:
                sample = self.embed("sample")
                return len(sample)
            except:
                raise ValueError("Cannot determine embedding dimension")

    def clear_cache(self):
        """Clear all caches."""
        self.memory_cache.clear()
        # Clear disk cache
        for cache_file in self.cache_dir.glob("*.pkl"):
            cache_file.unlink()
        logger.info("Cleared all caches")

    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        disk_cache_files = list(self.cache_dir.glob("*.pkl"))
        return {
            "memory_cache_size": len(self.memory_cache),
            "disk_cache_size": len(disk_cache_files),
            "disk_cache_dir": str(self.cache_dir)
        }