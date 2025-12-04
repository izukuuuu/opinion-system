"""Configuration models for RAG components."""

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List
from pathlib import Path


@dataclass
class EmbeddingConfig:
    """Configuration for embedding models."""
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2"
    model_type: str = "huggingface"  # "huggingface", "openai", "cohere"
    dimension: Optional[int] = None
    batch_size: int = 32
    normalize: bool = True
    cache_embeddings: bool = True
    cache_dir: Optional[Path] = None
    device: str = "auto"  # "cpu", "cuda", "auto"
    api_key: Optional[str] = None
    api_base: Optional[str] = None


@dataclass
class ChunkingConfig:
    """Configuration for text chunking."""
    strategy: str = "size"  # "size", "count", "semantic"
    chunk_size: int = 512
    chunk_overlap: int = 50
    separator: str = "\n\n"
    min_chunk_size: int = 50
    max_chunk_size: int = 2048
    respect_sentence_boundary: bool = True
    strip_whitespace: bool = True


@dataclass
class RetrievalConfig:
    """Configuration for retrieval."""
    top_k: int = 10
    threshold: float = 0.0
    search_type: str = "vector"  # "vector", "hybrid", "bm25"
    rerank: bool = False
    reranker_model: Optional[str] = None
    include_metadata: bool = True
    score_type: str = "cosine"  # "cosine", "dot", "euclidean"


@dataclass
class StorageConfig:
    """Configuration for storage backends."""
    storage_type: str = "file"  # "file", "lance", "faiss", "chroma", "database"
    path: Optional[Path] = None
    connection_string: Optional[str] = None
    index_type: str = "flat"  # "flat", "ivf", "hnsw"
    metric: str = "cosine"  # "cosine", "l2", "ip"
    create_if_not_exists: bool = True
    persist_index: bool = True


@dataclass
class ProcessingConfig:
    """Configuration for text preprocessing."""
    lowercase: bool = False
    remove_urls: bool = True
    remove_emails: bool = True
    remove_extra_whitespace: bool = True
    remove_special_chars: bool = False
    normalize_unicode: bool = True
    min_word_length: int = 1
    stop_words: List[str] = field(default_factory=list)


@dataclass
class RAGConfig:
    """Complete configuration for RAG pipeline."""
    # Component configurations
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    processing: ProcessingConfig = field(default_factory=ProcessingConfig)

    # Pipeline settings
    pipeline_name: str = "default"
    enable_caching: bool = True
    cache_dir: Optional[Path] = None
    log_level: str = "INFO"

    # Additional settings
    custom_settings: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary."""
        return {
            "pipeline_name": self.pipeline_name,
            "enable_caching": self.enable_caching,
            "cache_dir": str(self.cache_dir) if self.cache_dir else None,
            "log_level": self.log_level,
            "embedding": self.embedding.__dict__,
            "chunking": self.chunking.__dict__,
            "retrieval": self.retrieval.__dict__,
            "storage": self.storage.__dict__,
            "processing": self.processing.__dict__,
            "custom_settings": self.custom_settings
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RAGConfig":
        """Create config from dictionary."""
        config = cls()

        # Update pipeline settings
        config.pipeline_name = data.get("pipeline_name", "default")
        config.enable_caching = data.get("enable_caching", True)
        config.cache_dir = Path(data["cache_dir"]) if data.get("cache_dir") else None
        config.log_level = data.get("log_level", "INFO")

        # Update component configs
        if "embedding" in data:
            config.embedding = EmbeddingConfig(**data["embedding"])
        if "chunking" in data:
            config.chunking = ChunkingConfig(**data["chunking"])
        if "retrieval" in data:
            config.retrieval = RetrievalConfig(**data["retrieval"])
        if "storage" in data:
            config.storage = StorageConfig(**data["storage"])
        if "processing" in data:
            config.processing = ProcessingConfig(**data["processing"])

        config.custom_settings = data.get("custom_settings", {})

        return config

    def save(self, path: Path) -> None:
        """Save configuration to file."""
        import json
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def load(cls, path: Path) -> "RAGConfig":
        """Load configuration from file."""
        import json
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return cls.from_dict(data)