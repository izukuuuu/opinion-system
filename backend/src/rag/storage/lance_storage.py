"""LanceDB storage for RAG."""

from typing import List, Dict, Any, Optional, Union
import logging
from pathlib import Path
import numpy as np

from ..core.base import BaseStorage

logger = logging.getLogger(__name__)


class LanceStorage(BaseStorage):
    """LanceDB storage backend for vector search."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.uri = config.get("uri", "./data/lancedb") if config else "./data/lancedb"
        self.table_name = config.get("table_name", "embeddings") if config else "embeddings"
        self.vector_column = config.get("vector_column", "vector") if config else "vector"
        self.metric = config.get("metric", "cosine") if config else "cosine"

        self.db = None
        self.table = None

    def _init_db(self):
        """Initialize LanceDB connection."""
        try:
            import lancedb
            self.db = lancedb.connect(self.uri)
        except ImportError:
            raise ImportError("LanceDB not installed. Install with: pip install lancedb")

    def _create_table(self, data: List[Dict[str, Any]], vector_dimension: int):
        """Create table with data."""
        import pyarrow as pa

        # Prepare schema
        schema = self._infer_schema(data, vector_dimension)

        # Create table
        self.table = self.db.create_table(self.table_name, data=data, schema=schema)

    def _infer_schema(self, data: List[Dict[str, Any]], vector_dimension: int):
        """Infer Arrow schema from data."""
        import pyarrow as pa

        fields = []

        # Add vector field
        fields.append(pa.field(self.vector_column, pa.list_(pa.float32(), vector_dimension)))

        # Infer fields from first few items
        for item in data[:10]:
            for key, value in item.items():
                if key == self.vector_column or key == "embedding":
                    continue

                # Determine Arrow type
                if isinstance(value, str):
                    dtype = pa.string()
                elif isinstance(value, int):
                    dtype = pa.int64()
                elif isinstance(value, float):
                    dtype = pa.float64()
                elif isinstance(value, bool):
                    dtype = pa.bool_()
                elif isinstance(value, list):
                    dtype = pa.list_(pa.string())
                elif isinstance(value, dict):
                    dtype = pa.struct([])
                else:
                    dtype = pa.string()

                # Check if field already exists
                field_exists = False
                for field in fields:
                    if field.name == key:
                        field_exists = True
                        break

                if not field_exists:
                    fields.append(pa.field(key, dtype))

        return pa.schema(fields)

    def _prepare_data(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Prepare data for LanceDB."""
        prepared = []

        for item in data:
            prepared_item = {}

            # Handle vector/embedding field
            if "embedding" in item:
                prepared_item[self.vector_column] = item["embedding"]
            elif "vector" in item:
                prepared_item[self.vector_column] = item["vector"]
            else:
                logger.warning(f"No vector found in item: {item}")
                continue

            # Copy other fields
            for key, value in item.items():
                if key not in ["embedding", "vector"]:
                    prepared_item[key] = value

            prepared.append(prepared_item)

        return prepared

    def store(self, data: List[Dict[str, Any]], **kwargs) -> None:
        """Store data in LanceDB."""
        if not data:
            return

        if not self.db:
            self._init_db()

        # Prepare data
        prepared_data = self._prepare_data(data)

        if not prepared_data:
            logger.warning("No valid data to store")
            return

        # Determine vector dimension
        vector_dimension = len(prepared_data[0][self.vector_column])

        try:
            # Try to open existing table
            self.table = self.db.open_table(self.table_name)

            # Add data to existing table
            self.table.add(prepared_data)

        except Exception:
            # Table doesn't exist, create it
            self._create_table(prepared_data, vector_dimension)

        logger.info(f"Stored {len(prepared_data)} items in LanceDB table '{self.table_name}'")

    def load(self, name: Optional[str] = None, **kwargs) -> List[Dict[str, Any]]:
        """Load data from LanceDB."""
        table_name = name or self.table_name

        if not self.db:
            self._init_db()

        try:
            self.table = self.db.open_table(table_name)

            # Load all data
            data = self.table.to_arrow().to_pylist()

            # Convert vector field back to "embedding" for consistency
            for item in data:
                if self.vector_column in item:
                    item["embedding"] = item.pop(self.vector_column)

            logger.info(f"Loaded {len(data)} items from LanceDB table '{table_name}'")
            return data

        except Exception as e:
            logger.warning(f"Failed to load table '{table_name}': {e}")
            return []

    def search(self,
              query_vector: List[float],
              top_k: int = 10,
              filter_expr: Optional[str] = None,
              **kwargs) -> List[Dict[str, Any]]:
        """Search for similar vectors."""
        if not self.table:
            self.load()

        if not self.table:
            return []

        try:
            # Perform search
            results = self.table.search(query_vector).limit(top_k)

            # Apply filter if provided
            if filter_expr:
                results = results.where(filter_expr)

            # Convert to list
            results_list = results.to_arrow().to_pylist()

            # Add scores and normalize
            for i, item in enumerate(results_list):
                item["score"] = float(item.get("_score", 0.0))
                if self.vector_column in item:
                    item["embedding"] = item.pop(self.vector_column)
                item["id"] = item.get("id", str(i))

            return results_list

        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

    def delete(self, filter_expr: str, **kwargs) -> bool:
        """Delete data from table."""
        if not self.table:
            return False

        try:
            self.table.delete(filter_expr)
            logger.info(f"Deleted items matching: {filter_expr}")
            return True
        except Exception as e:
            logger.error(f"Delete failed: {e}")
            return False

    def update(self, values: Dict[str, Any], filter_expr: Optional[str] = None, **kwargs) -> bool:
        """Update data in table."""
        if not self.table:
            return False

        try:
            # LanceDB doesn't have direct update, use delete + add
            if filter_expr:
                # Delete matching items first
                self.delete(filter_expr)

            # Add updated items
            self.store([values])

            logger.info(f"Updated item(s)")
            return True

        except Exception as e:
            logger.error(f"Update failed: {e}")
            return False

    def create_index(self,
                    column: str = None,
                    index_type: str = "ivf_pq",
                    **kwargs) -> bool:
        """Create index for faster search."""
        if not self.table:
            return False

        column = column or self.vector_column

        try:
            # Create vector index
            self.table.create_index(
                column,
                index_type=index_type,
                metric=self.metric,
                **kwargs
            )
            logger.info(f"Created {index_type} index on column '{column}'")
            return True
        except Exception as e:
            logger.error(f"Index creation failed: {e}")
            return False

    def get_schema(self) -> Dict[str, Any]:
        """Get table schema."""
        if not self.table:
            return {}

        return self.table.schema.to_arrow_schema().to_pydict()

    def get_stats(self) -> Dict[str, Any]:
        """Get table statistics."""
        if not self.table:
            return {}

        try:
            # Count rows
            count = self.table.count_rows()

            return {
                "uri": self.uri,
                "table_name": self.table_name,
                "num_rows": count,
                "vector_column": self.vector_column,
                "metric": self.metric,
                "schema": self.get_schema()
            }
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {}