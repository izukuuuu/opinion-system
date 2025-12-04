"""JSON format converter."""

import json
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass
import logging

from ..core.base import BaseConverter

logger = logging.getLogger(__name__)


@dataclass
class JSONConfig:
    """Configuration for JSON conversion."""
    text_field: str = "text"
    id_field: Optional[str] = None
    encoding: str = "utf-8"
    preserve_metadata: bool = True
    output_format: str = "jsonl"  # "json", "jsonl", or "ndjson"


class JSONConverter(BaseConverter):
    """Converter for JSON formats."""

    def __init__(self, config: Optional[JSONConfig] = None):
        super().__init__()
        self.config = config or JSONConfig()

    def load_json(self, input_path: Path) -> List[Dict[str, Any]]:
        """Load and validate JSON input."""
        with input_path.open("r", encoding=self.config.encoding) as f:
            raw = json.load(f)

        # Handle different JSON structures
        if isinstance(raw, dict) and "data" in raw:
            data = raw["data"]
        elif isinstance(raw, list):
            data = raw
        elif isinstance(raw, dict) and "items" in raw:
            data = raw["items"]
        elif isinstance(raw, dict):
            # Single item
            data = [raw]
        else:
            raise ValueError(
                f"Unsupported JSON format in {input_path}. "
                "Expected list or object with 'data' or 'items' field."
            )

        if not isinstance(data, list):
            raise ValueError("Data must be a list of items.")

        logger.info(f"Loaded {len(data)} items from {input_path}")
        return data

    def extract_text(self, item: Dict[str, Any]) -> str:
        """Extract text from a single item."""
        if self.config.text_field not in item:
            logger.warning(f"Item missing '{self.config.text_field}' field: {item.keys()}")
            return ""

        text = item[self.config.text_field]
        if isinstance(text, str):
            return text.strip()
        else:
            return str(text).strip()

    def extract_metadata(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Extract metadata from a single item."""
        metadata = {}

        # Include ID if available
        if self.config.id_field and self.config.id_field in item:
            metadata["source_id"] = item[self.config.id_field]
        elif "id" in item:
            metadata["source_id"] = item["id"]

        # Include all non-text fields as metadata
        if self.config.preserve_metadata:
            for key, value in item.items():
                if key != self.config.text_field and not key.startswith("_"):
                    metadata[f"meta_{key}"] = value

        return metadata

    def convert_to_jsonl(self,
                        input_path: Path,
                        output_path: Path,
                        **kwargs) -> None:
        """Convert JSON to JSONL format."""
        data = self.load_json(input_path)

        output_path.parent.mkdir(parents=True, exist_ok=True)

        with output_path.open("w", encoding=self.config.encoding) as f:
            for item in data:
                text = self.extract_text(item)
                if text:
                    output_item = {"text": text}
                    if self.config.preserve_metadata:
                        metadata = self.extract_metadata(item)
                        output_item.update(metadata)
                    f.write(json.dumps(output_item, ensure_ascii=False) + "\n")

        logger.info(f"Converted to JSONL: {output_path}")

    def convert_to_json(self,
                       input_path: Path,
                       output_path: Path,
                       **kwargs) -> None:
        """Convert between JSON formats."""
        data = self.load_json(input_path)

        output_data = {
            "data": []
        }

        for item in data:
            text = self.extract_text(item)
            if text:
                output_item = {"text": text}
                if self.config.preserve_metadata:
                    metadata = self.extract_metadata(item)
                    output_item.update(metadata)
                output_data["data"].append(output_item)

        output_path.parent.mkdir(parents=True, exist_ok=True)

        with output_path.open("w", encoding=self.config.encoding) as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)

        logger.info(f"Converted to JSON: {output_path}")

    def convert(self,
                input_path: Path,
                output_path: Path,
                **kwargs) -> None:
        """Main conversion method."""
        input_path = Path(input_path).resolve()
        output_path = Path(output_path).resolve()

        logger.info(f"Converting {input_path} to {output_path}")

        # Determine output format based on file extension
        if output_path.suffix == ".jsonl" or self.config.output_format == "jsonl":
            self.convert_to_jsonl(input_path, output_path, **kwargs)
        elif output_path.suffix == ".json":
            self.convert_to_json(input_path, output_path, **kwargs)
        else:
            raise ValueError(f"Unsupported output format: {output_path.suffix}")

    def validate_format(self, data: List[Dict[str, Any]]) -> bool:
        """Validate JSON format."""
        if not isinstance(data, list):
            return False

        for item in data:
            if not isinstance(item, dict):
                return False
            if self.config.text_field not in item:
                logger.warning(f"Item missing '{self.config.text_field}' field")

        return True