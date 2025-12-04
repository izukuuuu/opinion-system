"""Base retriever class for RAG."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union
from pathlib import Path
import logging

from ..core.base import BaseRetriever as CoreBaseRetriever

logger = logging.getLogger(__name__)


class BaseRetriever(CoreBaseRetriever):
    """Base class for retrieval systems."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.index = None
        self.documents = None
        self.embeddings = None

    @abstractmethod
    def build_index(self, documents: List[Dict[str, Any]], **kwargs) -> None:
        """Build index from documents."""
        pass

    @abstractmethod
    def save_index(self, path: Union[str, Path], **kwargs) -> None:
        """Save index to disk."""
        pass

    @abstractmethod
    def load_index(self, path: Union[str, Path], **kwargs) -> None:
        """Load index from disk."""
        pass

    def get_documents(self, ids: List[str]) -> List[Dict[str, Any]]:
        """Get documents by IDs."""
        if not self.documents:
            return []

        doc_map = {doc.get("id", i): doc for i, doc in enumerate(self.documents)}
        return [doc_map.get(doc_id) for doc_id in ids if doc_id in doc_map]

    def search_by_id(self, doc_id: str) -> Optional[Dict[str, Any]]:
        """Search for a document by ID."""
        if not self.documents:
            return None

        for doc in self.documents:
            if doc.get("id") == doc_id:
                return doc
        return None