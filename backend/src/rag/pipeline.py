"""Comprehensive RAG pipeline with all components integrated."""

import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Union, Tuple
import json

from .config.models import RAGConfig
from .core.base import BaseRAG
from .core.chunker import TextChunker
from .core.processor import TextProcessor
from .converters.tagrag_converter import TagRAGConverter
from .embeddings.base import BaseEmbedder
from .embeddings.huggingface_embedder import HuggingFaceEmbedder
from .retrievers.vector_retriever import VectorRetriever
from .storage.file_storage import FileStorage
from .utils.helpers import load_json, save_json, validate_rag_data

logger = logging.getLogger(__name__)


class RAGPipeline(BaseRAG):
    """Complete RAG pipeline for processing and retrieving documents."""

    def __init__(self, config: Optional[RAGConfig] = None):
        super().__init__(config.to_dict() if config else {})
        self.config = config or RAGConfig()

        # Initialize components
        self.processor = TextProcessor(self.config.processing)
        self.chunker = TextChunker(self.config.chunking)
        self.embedder = self._init_embedder()
        self.retriever = VectorRetriever(self.embedder)
        self.storage = FileStorage(self.config.storage)

        # State
        self.documents = []
        self.chunks = []
        self._initialized = False

    def _init_embedder(self) -> BaseEmbedder:
        """Initialize embedding model based on config."""
        if self.config.embedding.model_type == "huggingface":
            return HuggingFaceEmbedder(
                model_name=self.config.embedding.model_name,
                device=self.config.embedding.device
            )
        else:
            raise ValueError(f"Unsupported embedder type: {self.config.embedding.model_type}")

    def load_documents(self, input_path: Union[str, Path], format: str = "tagrag") -> None:
        """Load documents from file."""
        input_path = Path(input_path)

        if format == "tagrag":
            data = load_json(input_path)
            if isinstance(data, dict) and "data" in data:
                data = data["data"]

            # Validate data
            is_valid, issues = validate_rag_data(data)
            if not is_valid:
                logger.warning(f"Data validation issues: {issues}")

            self.documents = data
            logger.info(f"Loaded {len(self.documents)} documents from {input_path}")

        elif format == "text":
            # Load from text files
            self.documents = [{"text": text, "source": str(path)}
                             for path, text in self.storage.load_texts(input_path)]
            logger.info(f"Loaded {len(self.documents)} text files from {input_path}")

        else:
            raise ValueError(f"Unsupported format: {format}")

    def process_documents(self) -> None:
        """Process and chunk documents."""
        if not self.documents:
            raise ValueError("No documents loaded. Call load_documents() first.")

        # Extract texts
        texts = [doc.get("text", "") for doc in self.documents]
        metadata = [doc for doc in self.documents]

        # Process texts
        processed_texts = self.processor.process_batch(texts)

        # Create chunks with metadata
        self.chunks = self.chunker.chunk_with_metadata(processed_texts, metadata)
        logger.info(f"Created {len(self.chunks)} chunks from {len(texts)} documents")

    def embed_documents(self, batch_size: Optional[int] = None) -> None:
        """Generate embeddings for all chunks."""
        if not self.chunks:
            raise ValueError("No chunks created. Call process_documents() first.")

        batch_size = batch_size or self.config.embedding.batch_size
        chunk_texts = [chunk["text"] for chunk in self.chunks]

        # Generate embeddings
        logger.info(f"Generating embeddings for {len(chunk_texts)} chunks...")
        embeddings = self.embedder.embed_batch(chunk_texts, batch_size=batch_size)

        # Add embeddings to chunks
        for chunk, embedding in zip(self.chunks, embeddings):
            chunk["embedding"] = embedding.tolist()

        logger.info(f"Generated {len(embeddings)} embeddings")

    def build_index(self) -> None:
        """Build retrieval index."""
        if not self.chunks or not any("embedding" in chunk for chunk in self.chunks):
            raise ValueError("No embeddings found. Call embed_documents() first.")

        # Extract texts and embeddings
        texts = [chunk["text"] for chunk in self.chunks]
        embeddings = [chunk["embedding"] for chunk in self.chunks]
        metadata = [{k: v for k, v in chunk.items() if k != "embedding" and k != "text"}
                   for chunk in self.chunks]

        # Add to retriever
        self.retriever.add_documents(texts, metadata)

        # Set embeddings for retriever
        import numpy as np
        self.retriever.embeddings = np.array(embeddings)
        self.retriever._build_index()

        self._initialized = True
        logger.info("Built retrieval index successfully")

    def retrieve(self,
                query: str,
                top_k: Optional[int] = None,
                threshold: Optional[float] = None,
                **kwargs) -> List[Dict[str, Any]]:
        """Retrieve relevant documents for a query."""
        if not self._initialized:
            raise ValueError("Pipeline not initialized. Call build_index() first.")

        top_k = top_k or self.config.retrieval.top_k
        threshold = threshold or self.config.retrieval.threshold

        # Retrieve using vector retriever
        results = self.retriever.retrieve(query, top_k=top_k, threshold=threshold)

        # Convert to dictionary format
        return [
            {
                "text": result.text,
                "score": result.score,
                "metadata": result.metadata,
                "doc_id": result.doc_id,
                "chunk_id": result.chunk_id
            }
            for result in results
        ]

    def save(self, output_dir: Union[str, Path]) -> None:
        """Save pipeline state."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Save chunks
        save_json(self.chunks, output_dir / "chunks.json")

        # Save retriever
        self.retriever.save(output_dir / "retriever")

        # Save config
        self.config.save(output_dir / "config.json")

        logger.info(f"Saved pipeline to {output_dir}")

    def load(self, input_dir: Union[str, Path]) -> None:
        """Load pipeline state."""
        input_dir = Path(input_dir)

        # Load config
        config_path = input_dir / "config.json"
        if config_path.exists():
            self.config = RAGConfig.load(config_path)

        # Load chunks
        chunks_path = input_dir / "chunks.json"
        if chunks_path.exists():
            self.chunks = load_json(chunks_path)
            logger.info(f"Loaded {len(self.chunks)} chunks")

        # Load retriever
        retriever_path = input_dir / "retriever"
        if retriever_path.exists():
            self.retriever.load(retriever_path)
            self._initialized = True

        logger.info(f"Loaded pipeline from {input_dir}")

    def get_stats(self) -> Dict[str, Any]:
        """Get pipeline statistics."""
        stats = {
            "num_documents": len(self.documents),
            "num_chunks": len(self.chunks),
            "embedding_dimension": self.embedder.dimension,
            "pipeline_initialized": self._initialized
        }

        if self._initialized:
            stats.update(self.retriever.get_stats())

        return stats

    def process(self,
                input_path: Union[str, Path],
                output_path: Optional[Union[str, Path]] = None,
                format: str = "tagrag",
                **kwargs) -> Dict[str, Any]:
        """Run complete pipeline."""
        logger.info("Starting RAG pipeline...")

        # Load documents
        self.load_documents(input_path, format)

        # Process documents
        self.process_documents()

        # Generate embeddings
        self.embed_documents()

        # Build index
        self.build_index()

        # Save if output path provided
        if output_path:
            self.save(output_path)

        stats = self.get_stats()
        logger.info(f"Pipeline completed. Stats: {stats}")

        return stats