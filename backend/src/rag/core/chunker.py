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
        """
        Chunk text by character count with overlap, optimized for Chinese.
        Returns [(chunk_text, chunk_index), ...]
        """
        if not text:
            return []

        text = text.strip()
        if not text:
            return []

        chunks = []
        start = 0
        chunk_id = 1
        n = len(text)
        
        # Punctuation marks to split on (Chinese & English)
        separators = ["\n\n", "\n", "。", "！", "？", ".", "!", "?"]

        while start < n:
            # Target end position
            end = min(start + self.config.chunk_size, n)
            
            # If we reached the end of text, just take it
            if end == n:
                chunk_text = text[start:end]
                chunks.append((chunk_text, chunk_id))
                break

            # Try to find a separator to break cleanly
            best_split = -1
            
            # Look for separators in reverse order from end
            # Search buffer: from (end - overlap) to end
            search_start = max(start + self.config.min_chunk_size, end - 50) 
            
            if search_start < end:
                sub_text = text[search_start:end]
                for sep in separators:
                    pos = sub_text.rfind(sep)
                    if pos != -1:
                        # Found a separator, split after it
                        best_split = search_start + pos + len(sep)
                        break
            
            if best_split != -1:
                end = best_split
            else:
                # No separator found, force split at chunk_size
                pass

            chunk_text = text[start:end].strip()
            if chunk_text:
                chunks.append((chunk_text, chunk_id))
                chunk_id += 1
            
            # Calculate next start
            # If we found a separator, next start is strictly after it (no overlap needed if semantic split?)
            # But usually we want some overlap to keep context.
            # Let's enforce overlap: move start to (end - overlap)
            
            next_start = end - self.config.chunk_overlap
            
            # Prevent infinite loop or backward movement
            if next_start <= start:
                next_start = start + max(1, len(chunk_text) // 2) # Force forward
            
            start = next_start
            
            # Correction: if next_start is beyond current end (shouldn't happen with correct overlap)
            if start >= n:
                break

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