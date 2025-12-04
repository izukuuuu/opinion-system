"""Hybrid retriever combining vector and keyword search."""

from typing import List, Dict, Any, Optional, Union
import logging
import numpy as np
from pathlib import Path

from .base import BaseRetriever
from .vector_retriever import VectorRetriever
from .bm25_retriever import BM25Retriever

logger = logging.getLogger(__name__)


class HybridRetriever(BaseRetriever):
    """Hybrid retriever that combines vector and BM25 search."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)

        # Initialize sub-retrievers
        self.vector_retriever = VectorRetriever(config)
        self.bm25_retriever = BM25Retriever(config)

        # Hybrid search parameters
        self.vector_weight = config.get("vector_weight", 0.5) if config else 0.5
        self.bm25_weight = config.get("bm25_weight", 0.5) if config else 0.5
        self.rerank = config.get("rerank", True) if config else True

    def build_index(self, documents: List[Dict[str, Any]], **kwargs) -> None:
        """Build both vector and BM25 indexes."""
        logger.info("Building hybrid index...")

        # Store documents
        self.documents = documents

        # Build vector index
        self.vector_retriever.build_index(documents, **kwargs)

        # Build BM25 index
        self.bm25_retriever.build_index(documents, **kwargs)

        logger.info(f"Hybrid index built for {len(documents)} documents")

    def retrieve(self, query: str, top_k: int = 10, **kwargs) -> List[Dict[str, Any]]:
        """Retrieve documents using hybrid search."""
        if not self.documents:
            return []

        # Get more results from each retriever for better fusion
        vector_results = self.vector_retriever.retrieve(query, top_k * 2, **kwargs)
        bm25_results = self.bm25_retriever.retrieve(query, top_k * 2, **kwargs)

        # Score fusion
        fused_results = self._fuse_results(vector_results, bm25_results, query)

        # Return top_k results
        return fused_results[:top_k]

    def _fuse_results(self,
                     vector_results: List[Dict[str, Any]],
                     bm25_results: List[Dict[str, Any]],
                     query: str) -> List[Dict[str, Any]]:
        """Fuse results from vector and BM25 retrievers."""
        # Create document score maps
        doc_scores = {}
        doc_results = {}

        # Process vector results
        for result in vector_results:
            doc_id = result.get("id", "")
            score = result.get("score", 0.0)
            doc_scores[doc_id] = doc_scores.get(doc_id, 0) + self.vector_weight * score
            doc_results[doc_id] = result

        # Process BM25 results
        for result in bm25_results:
            doc_id = result.get("id", "")
            score = result.get("score", 0.0)
            doc_scores[doc_id] = doc_scores.get(doc_id, 0) + self.bm25_weight * score
            if doc_id not in doc_results:
                doc_results[doc_id] = result

        # Sort by combined score
        sorted_docs = sorted(doc_scores.items(), key=lambda x: x[1], reverse=True)

        # Build final results
        fused_results = []
        for doc_id, score in sorted_docs:
            result = doc_results[doc_id].copy()
            result["score"] = score
            result["retrieval_type"] = "hybrid"
            fused_results.append(result)

        return fused_results

    def save_index(self, path: Union[str, Path], **kwargs) -> None:
        """Save hybrid index to disk."""
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)

        # Save vector index
        vector_path = path / "vector"
        self.vector_retriever.save_index(vector_path, **kwargs)

        # Save BM25 index
        bm25_path = path / "bm25"
        self.bm25_retriever.save_index(bm25_path, **kwargs)

        # Save hybrid config
        import json
        config_path = path / "hybrid_config.json"
        config = {
            "vector_weight": self.vector_weight,
            "bm25_weight": self.bm25_weight,
            "rerank": self.rerank
        }
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)

        logger.info(f"Hybrid index saved to {path}")

    def load_index(self, path: Union[str, Path], **kwargs) -> None:
        """Load hybrid index from disk."""
        path = Path(path)

        # Load vector index
        vector_path = path / "vector"
        if vector_path.exists():
            self.vector_retriever.load_index(vector_path, **kwargs)

        # Load BM25 index
        bm25_path = path / "bm25"
        if bm25_path.exists():
            self.bm25_retriever.load_index(bm25_path, **kwargs)

        # Load hybrid config
        config_path = path / "hybrid_config.json"
        if config_path.exists():
            import json
            with open(config_path, "r") as f:
                config = json.load(f)
            self.vector_weight = config.get("vector_weight", 0.5)
            self.bm25_weight = config.get("bm25_weight", 0.5)
            self.rerank = config.get("rerank", True)

        logger.info(f"Hybrid index loaded from {path}")

    def set_weights(self, vector_weight: float, bm25_weight: float):
        """Set weights for vector and BM25 search."""
        total = vector_weight + bm25_weight
        if total == 0:
            raise ValueError("Weights cannot both be zero")

        self.vector_weight = vector_weight / total
        self.bm25_weight = bm25_weight / total

    def get_stats(self) -> Dict[str, Any]:
        """Get retrieval statistics."""
        stats = {
            "type": "hybrid",
            "vector_weight": self.vector_weight,
            "bm25_weight": self.bm25_weight,
            "rerank": self.rerank,
            "num_documents": len(self.documents) if self.documents else 0
        }

        # Add sub-retriever stats
        if hasattr(self.vector_retriever, 'get_stats'):
            stats["vector_stats"] = self.vector_retriever.get_stats()
        if hasattr(self.bm25_retriever, 'get_stats'):
            stats["bm25_stats"] = self.bm25_retriever.get_stats()

        return stats