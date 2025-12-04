"""Vector-based retrieval system using embeddings."""

import numpy as np
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import pickle
from pathlib import Path

from ..embeddings.base import BaseEmbedder
from ..core.base import BaseRetriever


@dataclass
class RetrievalResult:
    """Result from a retrieval operation."""
    text: str
    score: float
    metadata: Dict[str, Any]
    doc_id: Optional[str] = None
    chunk_id: Optional[int] = None


class VectorRetriever(BaseRetriever):
    """Vector-based retriever using embeddings."""

    def __init__(self,
                 embedder: BaseEmbedder,
                 index_path: Optional[Path] = None,
                 use_faiss: bool = False):
        super().__init__()
        self.embedder = embedder
        self.index_path = index_path
        self.use_faiss = use_faiss
        self.texts = []
        self.embeddings = None
        self.metadata = []
        self._index = None

    def add_documents(self,
                     texts: List[str],
                     metadata: Optional[List[Dict[str, Any]]] = None,
                     batch_size: int = 32) -> None:
        """Add documents to the retriever."""
        # Store texts and metadata
        self.texts.extend(texts)

        if metadata is None:
            metadata = [{}] * len(texts)
        self.metadata.extend(metadata)

        # Generate embeddings
        new_embeddings = self.embedder.embed_batch(texts, batch_size=batch_size)
        new_embeddings = np.array(new_embeddings)

        # Combine with existing embeddings
        if self.embeddings is None:
            self.embeddings = new_embeddings
        else:
            self.embeddings = np.vstack([self.embeddings, new_embeddings])

        # Build/update index
        self._build_index()

    def _build_index(self) -> None:
        """Build the search index."""
        if self.use_faiss:
            self._build_faiss_index()
        else:
            # Simple numpy-based search
            self._index = self.embedder.normalize(self.embeddings)

    def _build_faiss_index(self) -> None:
        """Build FAISS index for faster search."""
        try:
            import faiss
        except ImportError:
            raise ImportError("FAISS not installed. Install with: pip install faiss-cpu")

        dimension = self.embeddings.shape[1]
        self._index = faiss.IndexFlatIP(dimension)

        # Normalize embeddings for cosine similarity
        normalized_embeddings = self.embedder.normalize(self.embeddings)
        self._index.add(normalized_embeddings.astype('float32'))

    def retrieve(self,
                query: str,
                top_k: int = 10,
                threshold: float = 0.0,
                **kwargs) -> List[RetrievalResult]:
        """Retrieve most similar documents."""
        if self._index is None:
            return []

        # Embed query
        query_embedding = self.embedder.embed(query)
        if isinstance(query_embedding, list):
            query_embedding = np.array(query_embedding)
        query_embedding = query_embedding.reshape(1, -1)
        query_embedding = self.embedder.normalize(query_embedding)

        # Search
        if self.use_faiss:
            scores, indices = self._search_faiss(query_embedding, top_k)
        else:
            scores, indices = self._search_numpy(query_embedding, top_k)

        # Filter by threshold and create results
        results = []
        for score, idx in zip(scores, indices):
            if score >= threshold and idx < len(self.texts):
                result = RetrievalResult(
                    text=self.texts[idx],
                    score=float(score),
                    metadata=self.metadata[idx] if idx < len(self.metadata) else {},
                    doc_id=str(idx)
                )
                results.append(result)

        return results

    def _search_faiss(self, query_embedding: np.ndarray, top_k: int) -> Tuple[np.ndarray, np.ndarray]:
        """Search using FAISS index."""
        import faiss
        scores, indices = self._index.search(
            query_embedding.astype('float32'),
            min(top_k, len(self.texts))
        )
        return scores[0], indices[0]

    def _search_numpy(self, query_embedding: np.ndarray, top_k: int) -> Tuple[np.ndarray, np.ndarray]:
        """Search using numpy dot product."""
        similarities = np.dot(self._index, query_embedding.T).flatten()
        top_indices = np.argsort(similarities)[::-1][:top_k]
        return similarities[top_indices], top_indices

    def save(self, path: Path) -> None:
        """Save the retriever to disk."""
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)

        data = {
            'texts': self.texts,
            'embeddings': self.embeddings,
            'metadata': self.metadata
        }

        # Save data
        with open(path / 'retriever_data.pkl', 'wb') as f:
            pickle.dump(data, f)

        # Save index if using FAISS
        if self.use_faiss and self._index:
            import faiss
            faiss.write_index(self._index, str(path / 'retriever_index.faiss'))

    def load(self, path: Path) -> None:
        """Load the retriever from disk."""
        path = Path(path)

        # Load data
        with open(path / 'retriever_data.pkl', 'rb') as f:
            data = pickle.load(f)

        self.texts = data['texts']
        self.embeddings = data['embeddings']
        self.metadata = data['metadata']

        # Load index if using FAISS
        if self.use_faiss and (path / 'retriever_index.faiss').exists():
            import faiss
            self._index = faiss.read_index(str(path / 'retriever_index.faiss'))
        else:
            self._build_index()

    def get_stats(self) -> Dict[str, Any]:
        """Get retrieval statistics."""
        return {
            'num_documents': len(self.texts),
            'embedding_dimension': self.embeddings.shape[1] if self.embeddings is not None else None,
            'index_type': 'faiss' if self.use_faiss else 'numpy'
        }