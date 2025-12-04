"""HuggingFace embedding model."""

from typing import List, Union, Dict, Any, Optional
import logging
import numpy as np
from pathlib import Path

from .base import BaseEmbedder

logger = logging.getLogger(__name__)


class HuggingFaceEmbedder(BaseEmbedder):
    """HuggingFace sentence-transformers embedding model."""

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2", config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.model_name = model_name
        self.model = None
        self.device = config.get("device", "auto") if config else "auto"
        self.cache_dir = config.get("cache_dir") if config else None

    def _initialize_model(self):
        """Initialize the HuggingFace model."""
        if self.model is None:
            try:
                from sentence_transformers import SentenceTransformer

                # Determine device
                if self.device == "auto":
                    import torch
                    self.device = "cuda" if torch.cuda.is_available() else "cpu"

                # Load model
                self.model = SentenceTransformer(
                    self.model_name,
                    device=self.device,
                    cache_folder=self.cache_dir
                )
                logger.info(f"Loaded model {self.model_name} on {self.device}")

            except ImportError:
                raise ImportError("sentence-transformers library not installed. Install with: pip install sentence-transformers torch")

    def embed(self, texts: Union[str, List[str]], **kwargs) -> Union[List[float], List[List[float]]]:
        """Generate embeddings for texts."""
        self._initialize_model()

        # Handle single text input
        if isinstance(texts, str):
            texts = [texts]

        try:
            embeddings = self.model.encode(
                texts,
                batch_size=kwargs.get("batch_size", 32),
                normalize_embeddings=kwargs.get("normalize", True),
                convert_to_numpy=True
            )

            # Convert to lists
            if isinstance(embeddings, np.ndarray):
                embeddings = embeddings.tolist()

            # Return single embedding for single input
            return embeddings[0] if len(embeddings) == 1 else embeddings

        except Exception as e:
            logger.error(f"Failed to generate embeddings: {e}")
            raise

    def embed_batch(self, texts: List[str], batch_size: int = 32, **kwargs) -> List[List[float]]:
        """Generate embeddings for a batch of texts."""
        self._initialize_model()

        try:
            embeddings = self.model.encode(
                texts,
                batch_size=batch_size,
                normalize_embeddings=kwargs.get("normalize", True),
                convert_to_numpy=True,
                show_progress_bar=kwargs.get("show_progress", True)
            )

            return embeddings.tolist()

        except Exception as e:
            logger.error(f"Failed to generate batch embeddings: {e}")
            raise

    def get_dimension(self) -> int:
        """Get embedding dimension."""
        self._initialize_model()
        return self.model.get_sentence_embedding_dimension()

    def save_model(self, path: Union[str, Path]):
        """Save the model to disk."""
        self._initialize_model()
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)
        self.model.save(str(path))
        logger.info(f"Model saved to {path}")

    def load_model(self, path: Union[str, Path]):
        """Load the model from disk."""
        try:
            from sentence_transformers import SentenceTransformer
            self.model = SentenceTransformer(str(path))
            logger.info(f"Model loaded from {path}")
        except ImportError:
            raise ImportError("sentence-transformers library not installed")