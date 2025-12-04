"""Vector storage for RAG embeddings."""

import numpy as np
from typing import List, Dict, Any, Optional, Union, Tuple
import logging
from pathlib import Path

from .file_storage import FileStorage
from ..core.base import BaseStorage

logger = logging.getLogger(__name__)


class VectorStorage(BaseStorage):
    """Storage optimized for vector embeddings."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.base_path = Path(config.get("path", "./data/vectors")) if config else Path("./data/vectors")
        self.index_type = config.get("index_type", "flat") if config else "flat"
        self.metric = config.get("metric", "cosine") if config else "cosine"
        self.backend = config.get("backend", "numpy") if config else "numpy"  # numpy, faiss, annoy, hnsw

        # Initialize storage
        self.file_storage = FileStorage(config)
        self.vectors = None
        self.metadata = []
        self.index = None
        self.dimension = 0

        # Initialize backend-specific storage
        if self.backend == "faiss":
            self._init_faiss()
        elif self.backend == "annoy":
            self._init_annoy()
        elif self.backend == "hnsw":
            self._init_hnsw()

    def _init_faiss(self):
        """Initialize FAISS backend."""
        try:
            import faiss
            self.faiss = faiss
        except ImportError:
            logger.warning("FAISS not installed, falling back to numpy backend")
            self.backend = "numpy"

    def _init_annoy(self):
        """Initialize Annoy backend."""
        try:
            from annoy import AnnoyIndex
            self.AnnoyIndex = AnnoyIndex
        except ImportError:
            logger.warning("Annoy not installed, falling back to numpy backend")
            self.backend = "numpy"

    def _init_hnsw(self):
        """Initialize HNSW backend."""
        try:
            import hnswlib
            self.hnswlib = hnswlib
        except ImportError:
            logger.warning("HNSWlib not installed, falling back to numpy backend")
            self.backend = "numpy"

    def _normalize_vector(self, vector: List[float]) -> List[float]:
        """Normalize vector if using cosine similarity."""
        if self.metric != "cosine":
            return vector

        vector = np.array(vector, dtype=np.float32)
        norm = np.linalg.norm(vector)
        if norm > 0:
            vector = vector / norm
        return vector.tolist()

    def store(self, data: List[Dict[str, Any]], **kwargs) -> None:
        """Store vectors with metadata."""
        if not data:
            return

        # Extract vectors and metadata
        vectors = []
        metadata = []

        for item in data:
            if "embedding" in item:
                vector = item["embedding"]
                meta = {k: v for k, v in item.items() if k != "embedding"}
            elif "vector" in item:
                vector = item["vector"]
                meta = {k: v for k, v in item.items() if k != "vector"}
            else:
                logger.warning(f"No vector found in item: {item.keys()}")
                continue

            vectors.append(self._normalize_vector(vector))
            metadata.append(meta)

        self.store_vectors(vectors, metadata, **kwargs)

    def store_vectors(self,
                     vectors: List[List[float]],
                     metadata: Optional[List[Dict[str, Any]]] = None,
                     name: str = "vectors",
                     **kwargs) -> None:
        """Store vectors with optional metadata."""
        if not vectors:
            return

        self.base_path.mkdir(parents=True, exist_ok=True)

        # Convert to numpy array
        self.vectors = np.array(vectors, dtype=np.float32)
        self.metadata = metadata or [{}] * len(vectors)
        self.dimension = self.vectors.shape[1]

        logger.info(f"Storing {len(vectors)} vectors of dimension {self.dimension}")

        # Build index
        self._build_index()

        # Save to disk
        self._save_index(name)

    def _build_index(self):
        """Build vector index based on backend."""
        if self.backend == "faiss":
            self._build_faiss_index()
        elif self.backend == "annoy":
            self._build_annoy_index()
        elif self.backend == "hnsw":
            self._build_hnsw_index()
        else:
            # Use numpy for brute-force search
            logger.info("Using numpy backend for vector search")

    def _build_faiss_index(self):
        """Build FAISS index."""
        if not hasattr(self, 'faiss'):
            return

        if self.metric == "cosine":
            # Normalize all vectors for cosine similarity
            faiss.normalize_L2(self.vectors)

        if self.index_type == "flat":
            self.index = self.faiss.IndexFlatIP(self.dimension) if self.metric == "cosine" else self.faiss.IndexFlatL2(self.dimension)
        elif self.index_type == "ivf":
            nlist = min(100, len(self.vectors) // 10)
            quantizer = self.faiss.IndexFlatL2(self.dimension)
            self.index = self.faiss.IndexIVFFlat(quantizer, self.dimension, nlist)
            self.index.train(self.vectors)
        elif self.index_type == "hnsw":
            self.index = self.faiss.IndexHNSWFlat(self.dimension, 32)
        else:
            logger.warning(f"Unsupported FAISS index type: {self.index_type}")
            self.index = self.faiss.IndexFlatL2(self.dimension)

        self.index.add(self.vectors)

    def _build_annoy_index(self):
        """Build Annoy index."""
        if not hasattr(self, 'AnnoyIndex'):
            return

        n_trees = 100
        self.index = self.AnnoyIndex(self.dimension, "angular" if self.metric == "cosine" else "euclidean")

        for i, vector in enumerate(self.vectors):
            self.index.add_item(i, vector)

        self.index.build(n_trees)

    def _build_hnsw_index(self):
        """Build HNSW index."""
        if not hasattr(self, 'hnswlib'):
            return

        max_elements = len(self.vectors)
        ef_construction = 200
        M = 16

        space = "cosine" if self.metric == "cosine" else "l2"
        self.index = self.hnswlib.Index(space=space, dim=self.dimension)
        self.index.init_index(max_elements=max_elements, ef_construction=ef_construction, M=M)

        for i, vector in enumerate(self.vectors):
            self.index.add_item(i, vector)

    def search(self,
              query_vector: List[float],
              top_k: int = 10,
              **kwargs) -> List[Dict[str, Any]]:
        """Search for similar vectors."""
        if self.vectors is None:
            return []

        query_vector = self._normalize_vector(query_vector)

        if self.backend == "faiss":
            return self._search_faiss(query_vector, top_k)
        elif self.backend == "annoy":
            return self._search_annoy(query_vector, top_k)
        elif self.backend == "hnsw":
            return self._search_hnsw(query_vector, top_k)
        else:
            return self._search_numpy(query_vector, top_k)

    def _search_numpy(self, query_vector: List[float], top_k: int) -> List[Dict[str, Any]]:
        """Brute-force search using numpy."""
        query = np.array([query_vector], dtype=np.float32)

        if self.metric == "cosine":
            # Cosine similarity
            similarities = np.dot(self.vectors, query.T).flatten()
            indices = np.argsort(-similarities)[:top_k]
            scores = similarities[indices].tolist()
        else:
            # Euclidean distance
            distances = np.linalg.norm(self.vectors - query, axis=1)
            indices = np.argsort(distances)[:top_k]
            scores = (-distances[indices]).tolist()  # Convert to similarity scores

        results = []
        for idx, score in zip(indices, scores):
            result = self.metadata[idx].copy()
            result["score"] = score
            result["id"] = result.get("id", str(idx))
            results.append(result)

        return results

    def _search_faiss(self, query_vector: List[float], top_k: int) -> List[Dict[str, Any]]:
        """Search using FAISS."""
        if self.metric == "cosine":
            query_vector = np.array([query_vector], dtype=np.float32)
            self.faiss.normalize_L2(query_vector)
            scores, indices = self.index.search(query_vector, top_k)
        else:
            query_vector = np.array([query_vector], dtype=np.float32)
            distances, indices = self.index.search(query_vector, top_k)
            scores = (-distances).flatten().tolist()

        results = []
        for idx, score in zip(indices[0], scores[0] if isinstance(scores, np.ndarray) else scores):
            if idx >= 0 and idx < len(self.metadata):
                result = self.metadata[idx].copy()
                result["score"] = float(score)
                result["id"] = result.get("id", str(idx))
                results.append(result)

        return results

    def _search_annoy(self, query_vector: List[float], top_k: int) -> List[Dict[str, Any]]:
        """Search using Annoy."""
        indices, distances = self.index.get_nns_by_vector(query_vector, top_k, include_distances=True)

        results = []
        for idx, dist in zip(indices, distances):
            if idx < len(self.metadata):
                result = self.metadata[idx].copy()
                # Convert distance to similarity score
                score = 1 - dist if self.metric != "cosine" else 1 - (dist / 2)
                result["score"] = score
                result["id"] = result.get("id", str(idx))
                results.append(result)

        return results

    def _search_hnsw(self, query_vector: List[float], top_k: int) -> List[Dict[str, Any]]:
        """Search using HNSW."""
        labels, distances = self.index.knn_query(query_vector, k=top_k)

        results = []
        for idx, dist in zip(labels, distances):
            if idx < len(self.metadata):
                result = self.metadata[idx].copy()
                # Convert distance to similarity score
                score = -dist if self.metric != "cosine" else 1 - dist
                result["score"] = score
                result["id"] = result.get("id", str(idx))
                results.append(result)

        return results

    def _save_index(self, name: str):
        """Save index to disk."""
        index_path = self.base_path / f"{name}_index.{self.backend}"
        vectors_path = self.base_path / f"{name}_vectors.npy"
        metadata_path = self.base_path / f"{name}_metadata.json"

        # Save vectors
        np.save(vectors_path, self.vectors)

        # Save metadata
        import json
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(self.metadata, f, ensure_ascii=False, indent=2)

        # Save index
        if self.backend == "faiss" and hasattr(self, 'faiss'):
            self.faiss.write_index(self.index, str(index_path))
        elif self.backend == "annoy" and hasattr(self, 'AnnoyIndex'):
            self.index.save(str(index_path))
        elif self.backend == "hnsw" and hasattr(self, 'hnswlib'):
            self.index.save_index(str(index_path))

        logger.info(f"Index saved to {index_path}")

    def load(self, name: str = "vectors", **kwargs) -> List[Dict[str, Any]]:
        """Load vectors from storage."""
        vectors_path = self.base_path / f"{name}_vectors.npy"
        metadata_path = self.base_path / f"{name}_metadata.json"
        index_path = self.base_path / f"{name}_index.{self.backend}"

        if not vectors_path.exists():
            logger.warning(f"No vectors found at {vectors_path}")
            return []

        # Load vectors
        self.vectors = np.load(vectors_path)
        self.dimension = self.vectors.shape[1]

        # Load metadata
        if metadata_path.exists():
            import json
            with open(metadata_path, "r", encoding="utf-8") as f:
                self.metadata = json.load(f)

        # Rebuild index if needed
        if index_path.exists():
            self._load_index(index_path)
        else:
            self._build_index()

        logger.info(f"Loaded {len(self.vectors)} vectors from {name}")
        return self.metadata

    def _load_index(self, path: Path):
        """Load index from disk."""
        if self.backend == "faiss" and hasattr(self, 'faiss'):
            self.index = self.faiss.read_index(str(path))
        elif self.backend == "annoy" and hasattr(self, 'AnnoyIndex'):
            self.index = self.AnnoyIndex(self.dimension, "angular" if self.metric == "cosine" else "euclidean")
            self.index.load(str(path))
        elif self.backend == "hnsw" and hasattr(self, 'hnswlib'):
            max_elements = len(self.vectors)
            space = "cosine" if self.metric == "cosine" else "l2"
            self.index = self.hnswlib.Index(space=space, dim=self.dimension)
            self.index.load_index(str(path), max_elements=max_elements)

    def get_stats(self) -> Dict[str, Any]:
        """Get storage statistics."""
        return {
            "backend": self.backend,
            "index_type": self.index_type,
            "metric": self.metric,
            "num_vectors": len(self.vectors) if self.vectors is not None else 0,
            "dimension": self.dimension,
            "size_mb": self.vectors.nbytes / (1024 * 1024) if self.vectors is not None else 0
        }