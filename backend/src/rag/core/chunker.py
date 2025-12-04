"""Text chunking utilities for RAG."""

from typing import List, Tuple, Optional, Generator
import re
from dataclasses import dataclass


@dataclass
class ChunkConfig:
    """Configuration for text chunking."""
    chunk_size: int = 512
    chunk_overlap: int = 50
    separator: str = "\n\n"
    min_chunk_size: int = 50
    max_chunk_size: int = 2048
    respect_sentence_boundary: bool = True
    strip_whitespace: bool = True


class TextChunker:
    """Advanced text chunker with multiple strategies."""

    def __init__(self, config: Optional[ChunkConfig] = None):
        self.config = config or ChunkConfig()

    def chunk_by_size(self, text: str) -> List[Tuple[str, int]]:
        """Chunk text by character count with overlap."""
        if not text:
            return []

        chunks = []
        start = 0
        chunk_id = 1

        while start < len(text):
            # Calculate end position
            end = min(start + self.config.chunk_size, len(text))

            # If not the last chunk, try to find a good break point
            if end < len(text):
                # Look for sentence boundary
                if self.config.respect_sentence_boundary:
                    sentence_end = text.rfind('.', start, end)
                    if sentence_end > start + self.config.min_chunk_size:
                        end = sentence_end + 1
                    else:
                        # Try paragraph break
                        para_end = text.rfind(self.config.separator, start, end)
                        if para_end > start + self.config.min_chunk_size:
                            end = para_end + len(self.config.separator)

            chunk = text[start:end]
            if self.config.strip_whitespace:
                chunk = chunk.strip()

            if chunk:
                chunks.append((chunk, chunk_id))
                chunk_id += 1

            # Calculate next start position with overlap
            start = max(start + 1, end - self.config.chunk_overlap)

        return chunks

    def chunk_by_separator(self, text: str, separator: Optional[str] = None) -> List[Tuple[str, int]]:
        """Chunk text by separator (e.g., paragraphs)."""
        sep = separator or self.config.separator

        # Split by separator
        parts = re.split(sep, text)
        parts = [p.strip() for p in parts if p.strip()]

        # Group parts into chunks
        chunks = []
        current_chunk = []
        current_length = 0
        chunk_id = 1

        for part in parts:
            if current_length + len(part) > self.config.chunk_size and current_chunk:
                # Save current chunk
                chunk_text = sep.join(current_chunk)
                chunks.append((chunk_text, chunk_id))
                chunk_id += 1

                # Start new chunk
                current_chunk = [part]
                current_length = len(part)
            else:
                current_chunk.append(part)
                current_length += len(part) + len(sep)

        # Add final chunk
        if current_chunk:
            chunk_text = sep.join(current_chunk)
            chunks.append((chunk_text, chunk_id))

        return chunks

    def chunk_with_metadata(self, texts: List[str], metadata: Optional[List[dict]] = None) -> List[dict]:
        """Chunk texts and preserve metadata."""
        results = []

        for i, text in enumerate(texts):
            chunks = self.chunk_by_size(text)

            for chunk_text, chunk_id in chunks:
                chunk_data = {
                    "text": chunk_text,
                    "chunk_id": chunk_id,
                    "source_doc_id": i + 1,
                    "chunk_index": chunk_id - 1
                }

                # Add metadata if available
                if metadata and i < len(metadata):
                    chunk_data.update(metadata[i])

                results.append(chunk_data)

        return results

    def merge_chunks(self, chunks: List[str], separators: Optional[str] = None) -> str:
        """Merge chunks back into a single text."""
        if not chunks:
            return ""

        sep = separators or self.config.separator
        return sep.join(chunks)

    def validate_chunk(self, chunk: str) -> bool:
        """Validate if a chunk meets quality criteria."""
        if not chunk:
            return False

        if len(chunk) < self.config.min_chunk_size:
            return False

        if len(chunk) > self.config.max_chunk_size:
            return False

        # Check if chunk has meaningful content
        if not re.search(r'[a-zA-Z\u4e00-\u9fff]', chunk):
            return False

        return True