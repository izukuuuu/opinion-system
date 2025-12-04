"""OpenAI embedding model."""

from typing import List, Union, Dict, Any, Optional
import logging
import numpy as np

from .base import BaseEmbedder

logger = logging.getLogger(__name__)


class OpenAIEmbedder(BaseEmbedder):
    """OpenAI API-based embedding model."""

    def __init__(self, model_name: str = "text-embedding-ada-002", config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.model_name = model_name
        self.api_key = config.get("api_key") if config else None
        self.client = None

    def _initialize_client(self):
        """Initialize OpenAI client."""
        try:
            import openai
            self.client = openai.Client(api_key=self.api_key)
        except ImportError:
            raise ImportError("OpenAI library not installed. Install with: pip install openai")

    def embed(self, texts: Union[str, List[str]], **kwargs) -> Union[List[float], List[List[float]]]:
        """Generate embeddings for texts."""
        if not self.client:
            self._initialize_client()

        # Handle single text input
        if isinstance(texts, str):
            texts = [texts]

        try:
            response = self.client.embeddings.create(
                model=self.model_name,
                input=texts
            )
            embeddings = [item.embedding for item in response.data]

            # Return single embedding for single input
            return embeddings[0] if len(embeddings) == 1 else embeddings

        except Exception as e:
            logger.error(f"Failed to generate embeddings: {e}")
            raise

    def embed_batch(self, texts: List[str], batch_size: int = 100, **kwargs) -> List[List[float]]:
        """Generate embeddings for a batch of texts."""
        embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            batch_embeddings = self.embed(batch, **kwargs)
            if isinstance(batch_embeddings[0], list):
                embeddings.extend(batch_embeddings)
            else:
                embeddings.append(batch_embeddings)

        return embeddings

    def get_dimension(self) -> int:
        """Get embedding dimension."""
        # Common dimensions for OpenAI models
        if "ada-002" in self.model_name:
            return 1536
        elif "3-small" in self.model_name:
            return 1536
        elif "3-large" in self.model_name:
            return 3072
        else:
            return 1536  # Default