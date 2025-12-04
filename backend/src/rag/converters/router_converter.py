"""RouterRAG format converter."""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import logging

from ..core.base import BaseConverter

logger = logging.getLogger(__name__)


@dataclass
class RouterRAGConfig:
    """Configuration for RouterRAG conversion."""
    topic: str = "topic"
    file_prefix: str = "doc"
    file_suffix: str = "_text1.txt"
    separator: str = "\n\n---\n\n"
    preserve_metadata: bool = True
    encoding: str = "utf-8"


class RouterConverter(BaseConverter):
    """Converter for RouterRAG format."""

    def __init__(self, config: Optional[RouterRAGConfig] = None):
        super().__init__()
        self.config = config or RouterRAGConfig()

    def convert_to_json(self,
                       input_path: Path,
                       output_path: Path,
                       **kwargs) -> None:
        """Convert RouterRAG text files to JSON format."""
        input_path = Path(input_path).resolve()
        output_path = Path(output_path).resolve()

        # Collect all text files
        texts = []
        metadata = []

        for file_path in input_path.glob("*.txt"):
            # Read the file content
            content = file_path.read_text(encoding=self.config.encoding)

            # Extract metadata from filename
            filename = file_path.stem
            parts = filename.split('_')
            doc_id = parts[0] if parts else filename
            topic = '_'.join(parts[1:-1]) if len(parts) > 2 else self.config.topic

            # Split content by separator
            parts = content.split(self.config.separator)

            for i, part in enumerate(parts):
                if part.strip():
                    texts.append(part.strip())
                    if self.config.preserve_metadata:
                        metadata.append({
                            "source_file": str(file_path),
                            "doc_id": doc_id,
                            "topic": topic,
                            "chunk_index": i,
                            "total_chunks": len(parts)
                        })

        # Create JSON output
        output_data = {
            "data": []
        }

        for i, text in enumerate(texts):
            item = {"text": text}
            if self.config.preserve_metadata and i < len(metadata):
                item.update(metadata[i])
            output_data["data"].append(item)

        # Write to JSON file
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding=self.config.encoding) as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)

        logger.info(f"Converted {len(texts)} texts to JSON: {output_path}")

    def convert_to_text(self,
                       input_path: Path,
                       output_path: Path,
                       **kwargs) -> None:
        """Convert JSON to RouterRAG text format."""
        input_path = Path(input_path).resolve()
        output_path = Path(output_path).resolve()

        # Load JSON data
        with input_path.open("r", encoding=self.config.encoding) as f:
            data = json.load(f)

        # Extract texts
        if isinstance(data, dict) and "data" in data:
            texts = [item["text"] for item in data["data"] if "text" in item]
        elif isinstance(data, list):
            texts = [item["text"] for item in data if "text" in item]
        else:
            raise ValueError("Unsupported JSON format")

        # Create output directory
        output_path.mkdir(parents=True, exist_ok=True)

        # Write texts to file
        output_file = output_path / f"{self.config.file_prefix}1_{self.config.topic}{self.config.file_suffix}"
        content = self.config.separator.join(texts)
        output_file.write_text(content, encoding=self.config.encoding)

        logger.info(f"Converted {len(texts)} texts to RouterRAG format: {output_file}")

    def convert(self,
                input_path: Path,
                output_path: Path,
                **kwargs) -> None:
        """Main conversion method."""
        input_path = Path(input_path)
        output_path = Path(output_path)

        logger.info(f"Converting {input_path} to {output_path}")

        # Determine conversion direction based on file types
        if input_path.is_dir() and output_path.suffix == ".json":
            # Convert text files to JSON
            self.convert_to_json(input_path, output_path, **kwargs)
        elif input_path.suffix == ".json" and output_path.is_dir():
            # Convert JSON to text files
            self.convert_to_text(input_path, output_path, **kwargs)
        else:
            raise ValueError(f"Unsupported conversion: {input_path} -> {output_path}")