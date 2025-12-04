# RAG (Retrieval-Augmented Generation) Module

A comprehensive, modular RAG system for the opinion system with support for multiple embedding models, retrieval strategies, and data formats.

## Features

- **Multiple Data Formats**: Support for TagRAG, RouterRAG, JSON, and text formats
- **Advanced Text Processing**: Chunking, cleaning, and preprocessing utilities
- **Flexible Embeddings**: Support for HuggingFace, OpenAI, and custom embedding models
- **Efficient Retrieval**: Vector search, hybrid retrieval, and BM25 support
- **Storage Backends**: File-based, Lance, FAISS, and database storage options
- **CLI Tools**: Command-line utilities for data conversion and processing
- **Configurable**: Comprehensive configuration system for all components

## Quick Start

### Installation

```bash
pip install -e .
```

### Basic Usage

```python
from rag import RAGPipeline, RAGConfig

# Create pipeline with default config
pipeline = RAGPipeline()

# Process TagRAG data
stats = pipeline.process(
    input_path="data/tagrag/smoking.json",
    output_path="output/rag_index",
    format="tagrag"
)

# Retrieve documents
results = pipeline.retrieve("smoking health risks", top_k=5)
```

### Using CLI Tools

#### Convert TagRAG to RouterRAG format

```bash
python -m rag.cli.export_tagrag \
    --input data/smoking.json \
    --output output/text_db \
    --topic smoking \
    --chunk-size 3
```

#### Batch process multiple files

```bash
python -m rag.cli.export_tagrag \
    --input-dir ./input_files \
    --output-dir ./output_files \
    --chunk-size 5 \
    --preserve-metadata
```

## Module Structure

```
rag/
├── core/           # Core functionality and base classes
│   ├── base.py     # Abstract base classes
│   ├── chunker.py  # Text chunking utilities
│   └── processor.py # Text preprocessing
├── converters/     # Data format converters
│   ├── tagrag_converter.py
│   ├── router_converter.py
│   └── json_converter.py
├── embeddings/     # Embedding models
│   ├── base.py
│   ├── huggingface_embedder.py
│   └── openai_embedder.py
├── retrievers/     # Retrieval systems
│   ├── base.py
│   ├── vector_retriever.py
│   └── hybrid_retriever.py
├── storage/        # Storage backends
│   ├── file_storage.py
│   ├── lance_storage.py
│   └── router_retrieve_data.py
├── config/         # Configuration management
│   ├── models.py
│   └── settings.py
├── utils/          # Utility functions
│   ├── helpers.py
│   └── data_utils.py
├── cli/            # Command-line tools
│   ├── export_tagrag.py
│   └── batch_convert.py
└── pipeline.py     # Complete RAG pipeline
```

## Configuration

### Using Configuration Files

```python
from rag import RAGConfig, RAGPipeline

# Load config from file
config = RAGConfig.load("config/rag_config.json")

# Create pipeline with config
pipeline = RAGPipeline(config)
```

### Custom Configuration

```python
from rag.config.models import RAGConfig, EmbeddingConfig

config = RAGConfig(
    embedding=EmbeddingConfig(
        model_name="sentence-transformers/all-MiniLM-L6-v2",
        batch_size=64
    ),
    retrieval=RetrievalConfig(
        top_k=20,
        threshold=0.5
    )
)
```

## Advanced Usage

### Custom Embedding Model

```python
from rag.embeddings import HuggingFaceEmbedder

embedder = HuggingFaceEmbedder(
    model_name="bert-base-chinese",
    device="cuda"
)

# Use with retriever
retriever = VectorRetriever(embedder)
```

### Custom Chunking Strategy

```python
from rag.core import TextChunker, ChunkConfig

chunker = TextChunker(ChunkConfig(
    chunk_size=1000,
    chunk_overlap=100,
    respect_sentence_boundary=True
))
```

### Hybrid Retrieval

```python
from rag.retrievers import HybridRetriever

retriever = HybridRetriever(
    vector_retriever=vector_retriever,
    bm25_retriever=bm25_retriever,
    alpha=0.7  # Weight for vector search
)
```

## CLI Reference

### export_tagrag

Convert TagRAG JSON to RouterRAG text chunks.

```bash
python -m rag.cli.export_tagrag [OPTIONS]

Options:
  --input TEXT              Input JSON file path
  --input-dir TEXT          Input directory with JSON files
  --output TEXT             Output directory path
  --topic TEXT              Topic name for files
  --chunk-size INTEGER      Number of entries per file
  --chunk-strategy [count|size]  Chunking strategy
  --preserve-metadata       Preserve source metadata
  --text-field TEXT         Field name for text content
  --id-field TEXT           Field name for document ID
  --verbose                 Enable verbose logging
  --dry-run                 Show what would be done
```

## API Reference

### RAGPipeline

Main pipeline class that orchestrates all RAG components.

#### Methods

- `load_documents(path, format)`: Load documents from file
- `process_documents()`: Process and chunk documents
- `embed_documents()`: Generate embeddings
- `build_index()`: Build retrieval index
- `retrieve(query, top_k, threshold)`: Retrieve relevant documents
- `save(output_dir)`: Save pipeline state
- `load(input_dir)`: Load pipeline state

### TextChunker

Advanced text chunking with multiple strategies.

```python
chunker = TextChunker(config)
chunks = chunker.chunk_by_size(text)
chunks = chunker.chunk_with_metadata(texts, metadata)
```

### TextProcessor

Text preprocessing and cleaning utilities.

```python
processor = TextProcessor(config)
clean_text = processor.clean(raw_text)
tokens = processor.tokenize(text)
```

## Best Practices

1. **Data Quality**: Always validate your input data before processing
2. **Chunking**: Choose appropriate chunk size based on your content and use case
3. **Embeddings**: Select embedding models trained on your domain's language
4. **Caching**: Enable embedding caching to avoid recomputation
5. **Storage**: Use appropriate storage backend for your scale requirements

## Troubleshooting

### Common Issues

1. **Memory Issues**: Reduce batch size or use streaming processing
2. **Slow Retrieval**: Consider using FAISS or Lance for large datasets
3. **Poor Results**: Adjust chunking parameters and retrieval threshold
4. **Encoding Issues**: Ensure all text files are UTF-8 encoded

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## License

This module is part of the opinion system project.