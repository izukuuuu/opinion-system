"""Base embedding classes."""

from abc import ABC, abstractmethod
from typing import List, Union, Optional, Dict, Any
import numpy as np


class BaseEmbedder(ABC):
    """Base class for text embedding models."""

    def __init__(self, model_name: str = None, dimension: int = None):
        self.model_name = model_name or "default"
        self.dimension = dimension
        self._is_initialized = False

    @abstractmethod
    def embed(self, texts: Union[str, List[str]], **kwargs) -> Union[np.ndarray, List[np.ndarray]]:
        """Generate embeddings for texts."""
        pass

    @abstractmethod
    def initialize(self, **kwargs) -> None:
        """Initialize the embedding model."""
        pass

    def embed_single(self, text: str, **kwargs) -> np.ndarray:
        """Embed a single text."""
        return self.embed(text, **kwargs)[0]

    def embed_batch(self, texts: List[str], batch_size: int = 32, **kwargs) -> List[np.ndarray]:
        """Embed texts in batches."""
        embeddings = []
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            batch_embeddings = self.embed(batch, **kwargs)
            if isinstance(batch_embeddings, np.ndarray) and batch_embeddings.ndim == 2:
                embeddings.extend(batch_embeddings)
            else:
                embeddings.extend(batch_embeddings)
        return embeddings

    def normalize(self, embeddings: np.ndarray) -> np.ndarray:
        """Normalize embeddings to unit vectors."""
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        return embeddings / (norms + 1e-8)

    def compute_similarity(self, embedding1: np.ndarray, embedding2: np.ndarray) -> float:
        """Compute cosine similarity between embeddings."""
        return float(np.dot(embedding1, embedding2))

    def compute_similarity_matrix(self, embeddings: np.ndarray) -> np.ndarray:
        """Compute pairwise similarity matrix."""
        normalized = self.normalize(embeddings)
        return np.dot(normalized, normalized.T)