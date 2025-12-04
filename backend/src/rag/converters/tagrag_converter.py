"""Enhanced TagRAG format converter with improved functionality."""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Union, Tuple
from dataclasses import dataclass
import logging

from ..core.base import BaseConverter
from ..core.chunker import TextChunker, ChunkConfig
from ..core.processor import TextProcessor, ProcessingConfig

logger = logging.getLogger(__name__)


@dataclass
class TagRAGConfig:
    """Configuration for TagRAG conversion."""
    chunk_size: int = 3
    chunk_strategy: str = "count"  # "count" or "size"
    max_chunk_chars: int = 2000
    topic: str = "topic"
    file_prefix: str = "doc"
    file_suffix: str = "_text1.txt"
    separator: str = "\n\n---\n\n"
    preserve_metadata: bool = True
    text_field: str = "text"
    id_field: Optional[str] = None
    output_format: str = "router"  # "router" or "tagrag"


class TagRAGConverter(BaseConverter):
    """Enhanced converter for TagRAG format with advanced features."""

    def __init__(self, config: Optional[TagRAGConfig] = None):
        super().__init__()
        self.config = config or TagRAGConfig()
        self.chunker = TextChunker()
        self.processor = TextProcessor()

    def load_json(self, input_path: Path) -> List[Dict[str, Any]]:
        """Load and validate JSON input."""
        with input_path.open("r", encoding="utf-8") as f:
            raw = json.load(f)

        # Handle different JSON structures
        if isinstance(raw, dict) and "data" in raw:
            data = raw["data"]
        elif isinstance(raw, list):
            data = raw
        elif isinstance(raw, dict) and "items" in raw:
            data = raw["items"]
        else:
            raise ValueError(
                f"Unsupported JSON format in {input_path}. "
                "Expected list or object with 'data' or 'items' field."
            )

        if not isinstance(data, list):
            raise ValueError("Data must be a list of items.")

        logger.info(f"Loaded {len(data)} items from {input_path}")
        return data

    def extract_texts(self, data: List[Dict[str, Any]]) -> List[str]:
        """Extract text from data items."""
        texts = []
        missing_count = 0

        for item in data:
            text = item.get(self.config.text_field, "").strip()
            if text:
                texts.append(text)
            else:
                missing_count += 1

        if missing_count > 0:
            logger.warning(f"Found {missing_count} items without text field")

        if not texts:
            raise ValueError("No valid text found in the input data")

        return texts

    def extract_metadata(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extract metadata from data items."""
        metadata = []

        for item in data:
            meta = {}

            # Include ID if available
            if self.config.id_field and self.config.id_field in item:
                meta["source_id"] = item[self.config.id_field]
            elif "id" in item:
                meta["source_id"] = item["id"]

            # Include all non-text fields as metadata
            for key, value in item.items():
                if key != self.config.text_field and not key.startswith("_"):
                    meta[f"meta_{key}"] = value

            metadata.append(meta)

        return metadata

    def chunk_by_count(self, texts: List[str]) -> List[Tuple[List[str], int]]:
        """Chunk texts by count."""
        chunks = []
        for i in range(0, len(texts), self.config.chunk_size):
            chunk = texts[i:i + self.config.chunk_size]
            chunks.append((chunk, (i // self.config.chunk_size) + 1))
        return chunks

    def chunk_by_size(self, texts: List[str]) -> List[Tuple[List[str], int]]:
        """Chunk texts by character count."""
        chunks = []
        current_chunk = []
        current_size = 0
        chunk_id = 1

        for text in texts:
            # Check if adding this text would exceed the limit
            if current_size + len(text) > self.config.max_chunk_chars and current_chunk:
                chunks.append((current_chunk, chunk_id))
                chunk_id += 1
                current_chunk = [text]
                current_size = len(text)
            else:
                current_chunk.append(text)
                current_size += len(text)

        # Add final chunk
        if current_chunk:
            chunks.append((current_chunk, chunk_id))

        return chunks

    def convert_to_router(self,
                         input_path: Path,
                         output_path: Path,
                         **kwargs) -> None:
        """Convert TagRAG JSON to RouterRAG format."""
        # Load and validate data
        data = self.load_json(input_path)
        texts = self.extract_texts(data)
        metadata = self.extract_metadata(data) if self.config.preserve_metadata else None

        # Create output directory
        output_path.mkdir(parents=True, exist_ok=True)

        # Choose chunking strategy
        if self.config.chunk_strategy == "size":
            chunks = self.chunk_by_size(texts)
        else:
            chunks = self.chunk_by_count(texts)

        # Write chunks to files
        for chunk_texts, chunk_id in chunks:
            doc_id = f"{self.config.file_prefix}{chunk_id}"
            file_name = f"{doc_id}_{self.config.topic}{self.config.file_suffix}"
            file_path = output_path / file_name

            # Combine texts with separator
            content = self.config.separator.join(chunk_texts)

            # Write to file
            file_path.write_text(content, encoding="utf-8")

            # Log metadata if available
            if metadata and chunk_id <= len(metadata):
                logger.debug(f"Written {file_name} with metadata: {metadata[chunk_id-1]}")
            else:
                logger.info(f"Written {file_name} with {len(chunk_texts)} texts")

        logger.info(f"Successfully converted {len(texts)} texts to {len(chunks)} chunks")

    def convert_to_tagrag(self,
                         input_path: Path,
                         output_path: Path,
                         **kwargs) -> None:
        """Convert RouterRAG format back to TagRAG JSON."""
        # Read all text files
        texts = []
        for file_path in output_path.glob("*.txt"):
            text = file_path.read_text(encoding="utf-8")
            # Split by separator to get individual texts
            parts = text.split(self.config.separator)
            texts.extend(parts)

        # Create TagRAG format
        output_data = {
            "data": [
                {"text": text.strip()}
                for text in texts
                if text.strip()
            ]
        }

        # Write to JSON file
        output_file = output_path.parent / f"{output_path.name}.json"
        with output_file.open("w", encoding="utf-8") as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)

        logger.info(f"Converted {len(texts)} texts to TagRAG format: {output_file}")

    def process_texts(self, texts: List[str]) -> List[str]:
        """Optional: Process texts before conversion."""
        processed = []
        for text in texts:
            # Clean and process text
            cleaned = self.processor.clean(text)
            if cleaned:
                processed.append(cleaned)
        return processed

    def convert(self,
                input_path: Path,
                output_path: Path,
                **kwargs) -> None:
        """Main conversion method."""
        input_path = Path(input_path).resolve()
        output_path = Path(output_path).resolve()

        logger.info(f"Converting {input_path} to {output_path}")

        if self.config.output_format == "router":
            self.convert_to_router(input_path, output_path, **kwargs)
        else:
            self.convert_to_tagrag(input_path, output_path, **kwargs)