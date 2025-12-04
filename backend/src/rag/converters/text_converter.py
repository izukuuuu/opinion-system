"""Text format converter."""

from pathlib import Path
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass
import logging

from ..core.base import BaseConverter

logger = logging.getLogger(__name__)


@dataclass
class TextConfig:
    """Configuration for text conversion."""
    encoding: str = "utf-8"
    separator: str = "\n\n---\n\n"
    preserve_metadata: bool = True
    chunk_size: int = 1000
    overlap: int = 100


class TextConverter(BaseConverter):
    """Converter for text formats."""

    def __init__(self, config: Optional[TextConfig] = None):
        super().__init__()
        self.config = config or TextConfig()

    def read_text_file(self, input_path: Path) -> str:
        """Read text from file."""
        return input_path.read_text(encoding=self.config.encoding)

    def chunk_text(self, text: str) -> List[str]:
        """Split text into chunks."""
        chunks = []
        start = 0

        while start < len(text):
            end = start + self.config.chunk_size

            # Try to split at separator if possible
            if end < len(text):
                # Find the last separator before the end
                sep_pos = text.rfind(self.config.separator, start, end)
                if sep_pos > start:
                    end = sep_pos + len(self.config.separator)

            chunk = text[start:end]
            chunks.append(chunk.strip())

            # Move start position with overlap
            start = max(start + 1, end - self.config.overlap)

        # Filter out empty chunks
        return [chunk for chunk in chunks if chunk]

    def convert_to_json(self,
                       input_path: Path,
                       output_path: Path,
                       **kwargs) -> None:
        """Convert text to JSON format."""
        text = self.read_text_file(input_path)
        chunks = self.chunk_text(text)

        output_data = {
            "data": []
        }

        for i, chunk in enumerate(chunks):
            item = {"text": chunk}
            if self.config.preserve_metadata:
                item.update({
                    "meta_source_file": str(input_path),
                    "meta_chunk_index": i,
                    "meta_total_chunks": len(chunks)
                })
            output_data["data"].append(item)

        # Write JSON output
        output_path.parent.mkdir(parents=True, exist_ok=True)
        import json
        with output_path.open("w", encoding=self.config.encoding) as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)

        logger.info(f"Converted {len(chunks)} chunks to JSON: {output_path}")

    def convert_to_jsonl(self,
                        input_path: Path,
                        output_path: Path,
                        **kwargs) -> None:
        """Convert text to JSONL format."""
        text = self.read_text_file(input_path)
        chunks = self.chunk_text(text)

        output_path.parent.mkdir(parents=True, exist_ok=True)

        import json
        with output_path.open("w", encoding=self.config.encoding) as f:
            for i, chunk in enumerate(chunks):
                item = {"text": chunk}
                if self.config.preserve_metadata:
                    item.update({
                        "meta_source_file": str(input_path),
                        "meta_chunk_index": i,
                        "meta_total_chunks": len(chunks)
                    })
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

        logger.info(f"Converted {len(chunks)} chunks to JSONL: {output_path}")

    def convert_from_json(self,
                         input_path: Path,
                         output_path: Path,
                         **kwargs) -> None:
        """Convert JSON to text format."""
        import json

        with input_path.open("r", encoding=self.config.encoding) as f:
            data = json.load(f)

        # Extract texts
        texts = []
        if isinstance(data, dict) and "data" in data:
            texts = [item["text"] for item in data["data"] if "text" in item]
        elif isinstance(data, list):
            texts = [item["text"] for item in data if "text" in item]

        # Combine texts with separator
        combined_text = self.config.separator.join(texts)

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(combined_text, encoding=self.config.encoding)

        logger.info(f"Converted {len(texts)} texts to single text file: {output_path}")

    def convert(self,
                input_path: Path,
                output_path: Path,
                **kwargs) -> None:
        """Main conversion method."""
        input_path = Path(input_path).resolve()
        output_path = Path(output_path).resolve()

        logger.info(f"Converting {input_path} to {output_path}")

        # Determine conversion direction
        if input_path.suffix in ['.txt', '.md'] and output_path.suffix in ['.json', '.jsonl']:
            if output_path.suffix == ".jsonl":
                self.convert_to_jsonl(input_path, output_path, **kwargs)
            else:
                self.convert_to_json(input_path, output_path, **kwargs)
        elif input_path.suffix in ['.json', '.jsonl'] and output_path.suffix in ['.txt', '.md']:
            self.convert_from_json(input_path, output_path, **kwargs)
        else:
            raise ValueError(f"Unsupported conversion: {input_path} -> {output_path}")

    def batch_convert(self,
                     input_dir: Path,
                     output_dir: Path,
                     pattern: str = "*.txt",
                     **kwargs) -> None:
        """Convert multiple files in a directory."""
        input_dir = Path(input_dir).resolve()
        output_dir = Path(output_dir).resolve()

        output_dir.mkdir(parents=True, exist_ok=True)

        for input_path in input_dir.glob(pattern):
            if input_path.is_file():
                # Generate output path
                if output_path.suffix in ['.json', '.jsonl']:
                    output_path = output_dir / f"{input_path.stem}.json"
                else:
                    output_path = output_dir / f"{input_path.stem}.txt"

                try:
                    self.convert(input_path, output_path, **kwargs)
                except Exception as e:
                    logger.error(f"Failed to convert {input_path}: {e}")

        logger.info(f"Batch conversion completed")