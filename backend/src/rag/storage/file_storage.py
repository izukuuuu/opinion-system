"""File-based storage for RAG."""

import json
import pickle
from pathlib import Path
from typing import List, Dict, Any, Optional, Union
import logging
import shutil

from ..core.base import BaseStorage

logger = logging.getLogger(__name__)


class FileStorage(BaseStorage):
    """Simple file-based storage backend."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.base_path = Path(config.get("path", "./data/rag")) if config else Path("./data/rag")
        self.format = config.get("format", "json") if config else "json"  # json, pickle, or parquet
        self.compression = config.get("compression", None) if config else None  # gzip, bz2

    def _get_file_path(self, name: str) -> Path:
        """Get file path for a given name."""
        suffix = f".{self.format}"
        if self.compression:
            suffix = f".{self.compression}{suffix}"

        return self.base_path / f"{name}{suffix}"

    def _open_file(self, path: Path, mode: str = "r"):
        """Open file with appropriate compression."""
        if self.compression == "gzip":
            import gzip
            return gzip.open(path, mode=mode.replace("t", ""), encoding=mode.replace("b", "") if "t" in mode else None)
        elif self.compression == "bz2":
            import bz2
            return bz2.open(path, mode=mode.replace("t", ""), encoding=mode.replace("b", "") if "t" in mode else None)
        else:
            return open(path, mode=mode)

    def store(self, data: List[Dict[str, Any]], name: str = "data", **kwargs) -> None:
        """Store data to file."""
        path = self._get_file_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)

        logger.info(f"Storing {len(data)} items to {path}")

        if self.format == "json":
            with self._open_file(path, "wt") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

        elif self.format == "pickle":
            with self._open_file(path, "wb") as f:
                pickle.dump(data, f)

        elif self.format == "parquet":
            try:
                import pandas as pd
                df = pd.DataFrame(data)
                if self.compression:
                    path = path.with_suffix(".parquet")
                df.to_parquet(path, compression=self.compression)
            except ImportError:
                raise ImportError("pandas and pyarrow required for parquet storage")

        else:
            raise ValueError(f"Unsupported format: {self.format}")

    def load(self, name: str = "data", **kwargs) -> List[Dict[str, Any]]:
        """Load data from file."""
        path = self._get_file_path(name)

        if not path.exists():
            logger.warning(f"File not found: {path}")
            return []

        logger.info(f"Loading data from {path}")

        if self.format == "json":
            with self._open_file(path, "rt") as f:
                return json.load(f)

        elif self.format == "pickle":
            with self._open_file(path, "rb") as f:
                return pickle.load(f)

        elif self.format == "parquet":
            try:
                import pandas as pd
                path = path.with_suffix(".parquet")
                df = pd.read_parquet(path)
                return df.to_dict("records")
            except ImportError:
                raise ImportError("pandas and pyarrow required for parquet storage")

        else:
            raise ValueError(f"Unsupported format: {self.format}")

    def store_embeddings(self,
                        embeddings: List[List[float]],
                        metadata: Optional[List[Dict[str, Any]]] = None,
                        name: str = "embeddings",
                        **kwargs) -> None:
        """Store embeddings with optional metadata."""
        data = {
            "embeddings": embeddings,
            "metadata": metadata or []
        }
        self.store(data, name, **kwargs)

    def load_embeddings(self,
                       name: str = "embeddings",
                       **kwargs) -> tuple[List[List[float]], List[Dict[str, Any]]]:
        """Load embeddings with metadata."""
        data = self.load(name, **kwargs)
        embeddings = data.get("embeddings", [])
        metadata = data.get("metadata", [])
        return embeddings, metadata

    def append(self, item: Dict[str, Any], name: str = "data", **kwargs) -> None:
        """Append item to existing data."""
        data = self.load(name, **kwargs)
        data.append(item)
        self.store(data, name, **kwargs)

    def delete(self, name: str = "data", **kwargs) -> bool:
        """Delete stored data."""
        path = self._get_file_path(name)
        if path.exists():
            path.unlink()
            logger.info(f"Deleted {path}")
            return True
        return False

    def exists(self, name: str = "data", **kwargs) -> bool:
        """Check if data exists."""
        path = self._get_file_path(name)
        return path.exists()

    def list(self, pattern: str = "*", **kwargs) -> List[str]:
        """List all stored data names."""
        pattern = f"*.{self.format}"
        if self.compression:
            pattern = f".{self.compression}{pattern}"

        files = list(self.base_path.glob(pattern))
        names = [f.stem for f in files]
        return names

    def clear(self, **kwargs) -> None:
        """Clear all stored data."""
        if self.base_path.exists():
            shutil.rmtree(self.base_path)
            logger.info(f"Cleared storage directory: {self.base_path}")

    def get_size(self, name: str = "data", **kwargs) -> int:
        """Get size of stored data in bytes."""
        path = self._get_file_path(name)
        if path.exists():
            return path.stat().st_size
        return 0

    def get_info(self, name: str = "data", **kwargs) -> Dict[str, Any]:
        """Get information about stored data."""
        path = self._get_file_path(name)
        if not path.exists():
            return {}

        stat = path.stat()
        return {
            "name": name,
            "path": str(path),
            "size": stat.st_size,
            "format": self.format,
            "compression": self.compression,
            "modified": stat.st_mtime,
            "created": stat.st_ctime
        }