"""Base classes for RAG components."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union
from pathlib import Path


class BaseRAG(ABC):
    """Base class for all RAG implementations."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}

    @abstractmethod
    def process(self, *args, **kwargs) -> Any:
        """Process the input and return results."""
        pass


class BaseConverter(BaseRAG):
    """Base class for data converters."""

    @abstractmethod
    def convert(self, input_path: Path, output_path: Path, **kwargs) -> None:
        """Convert data from one format to another."""
        pass


class BaseRetriever(BaseRAG):
    """Base class for retrieval systems."""

    @abstractmethod
    def retrieve(self, query: str, top_k: int = 10, **kwargs) -> List[Dict[str, Any]]:
        """Retrieve relevant documents for a query."""
        pass


class BaseEmbedder(BaseRAG):
    """Base class for text embedding models."""

    @abstractmethod
    def embed(self, texts: Union[str, List[str]], **kwargs) -> Union[List[float], List[List[float]]]:
        """Generate embeddings for texts."""
        pass


class BaseStorage(BaseRAG):
    """Base class for storage backends."""

    @abstractmethod
    def store(self, data: List[Dict[str, Any]], **kwargs) -> None:
        """Store data in the backend."""
        pass

    @abstractmethod
    def load(self, **kwargs) -> List[Dict[str, Any]]:
        """Load data from the backend."""
        pass