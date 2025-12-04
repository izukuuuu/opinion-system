"""Database storage for RAG."""

from typing import List, Dict, Any, Optional, Union
import logging
from pathlib import Path
import json
import uuid
from datetime import datetime

from ..core.base import BaseStorage

logger = logging.getLogger(__name__)


class DatabaseStorage(BaseStorage):
    """Database storage backend supporting multiple databases."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.db_type = config.get("db_type", "sqlite") if config else "sqlite"
        self.connection_string = config.get("connection_string", "sqlite:///./data/rag.db") if config else "sqlite:///./data/rag.db"
        self.table_name = config.get("table_name", "embeddings") if config else "embeddings"
        self.vector_column = config.get("vector_column", "embedding") if config else "embedding"

        self.engine = None
        self.session = None
        self._init_db()

    def _init_db(self):
        """Initialize database connection."""
        if self.db_type == "sqlite":
            self._init_sqlite()
        elif self.db_type == "postgresql":
            self._init_postgresql()
        elif self.db_type == "mysql":
            self._init_mysql()
        else:
            raise ValueError(f"Unsupported database type: {self.db_type}")

    def _init_sqlite(self):
        """Initialize SQLite connection."""
        try:
            from sqlalchemy import create_engine, Column, String, Text, Float, DateTime, JSON
            from sqlalchemy.ext.declarative import declarative_base
            from sqlalchemy.orm import sessionmaker
            import sqlite3

            # Create directory if needed
            if self.connection_string.startswith("sqlite:///"):
                db_path = self.connection_string.replace("sqlite:///", "")
                Path(db_path).parent.mkdir(parents=True, exist_ok=True)

            # Create engine
            self.engine = create_engine(self.connection_string)

            # Create session
            self.Session = sessionmaker(bind=self.engine)
            self.session = self.Session()

            # Create table if not exists
            Base = declarative_base()

            class Embedding(Base):
                __tablename__ = self.table_name

                id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
                text = Column(Text)
                embedding = Column(JSON)  # Store as JSON
                metadata = Column(JSON)
                score = Column(Float)
                created_at = Column(DateTime, default=datetime.utcnow)

            self.Embedding = Embedding
            Base.metadata.create_all(self.engine)

        except ImportError:
            raise ImportError("SQLAlchemy not installed. Install with: pip install sqlalchemy")

    def _init_postgresql(self):
        """Initialize PostgreSQL connection."""
        try:
            from sqlalchemy import create_engine, Column, String, Text, Float, DateTime, JSON
            from sqlalchemy.ext.declarative import declarative_base
            from sqlalchemy.orm import sessionmaker

            # Create engine
            self.engine = create_engine(self.connection_string)

            # Create session
            self.Session = sessionmaker(bind=self.engine)
            self.session = self.Session()

            # Create table if not exists
            Base = declarative_base()

            class Embedding(Base):
                __tablename__ = self.table_name

                id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
                text = Column(Text)
                embedding = Column(JSON)
                metadata = Column(JSON)
                score = Column(Float)
                created_at = Column(DateTime, default=datetime.utcnow)

            self.Embedding = Embedding
            Base.metadata.create_all(self.engine)

        except ImportError:
            raise ImportError("SQLAlchemy and psycopg2 required. Install with: pip install sqlalchemy psycopg2-binary")

    def _init_mysql(self):
        """Initialize MySQL connection."""
        try:
            from sqlalchemy import create_engine, Column, String, Text, Float, DateTime, JSON
            from sqlalchemy.ext.declarative import declarative_base
            from sqlalchemy.orm import sessionmaker

            # Create engine
            self.engine = create_engine(self.connection_string)

            # Create session
            self.Session = sessionmaker(bind=self.engine)
            self.session = self.Session()

            # Create table if not exists
            Base = declarative_base()

            class Embedding(Base):
                __tablename__ = self.table_name

                id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
                text = Column(Text)
                embedding = Column(JSON)
                metadata = Column(JSON)
                score = Column(Float)
                created_at = Column(DateTime, default=datetime.utcnow)

            self.Embedding = Embedding
            Base.metadata.create_all(self.engine)

        except ImportError:
            raise ImportError("SQLAlchemy and PyMySQL required. Install with: pip install sqlalchemy pymysql")

    def store(self, data: List[Dict[str, Any]], **kwargs) -> None:
        """Store data in database."""
        if not data:
            return

        try:
            # Create embedding objects
            embeddings = []
            for item in data:
                embedding_obj = self.Embedding()

                # Handle different field names
                if "text" in item:
                    embedding_obj.text = item["text"]
                elif "content" in item:
                    embedding_obj.text = item["content"]

                if "embedding" in item:
                    embedding_obj.embedding = item["embedding"]
                elif "vector" in item:
                    embedding_obj.embedding = item["vector"]

                # Store metadata
                metadata = {k: v for k, v in item.items()
                           if k not in ["text", "content", "embedding", "vector"]}
                if metadata:
                    embedding_obj.metadata = metadata

                if "score" in item:
                    embedding_obj.score = item["score"]

                embeddings.append(embedding_obj)

            # Bulk insert
            self.session.bulk_save_objects(embeddings)
            self.session.commit()

            logger.info(f"Stored {len(embeddings)} items in database")

        except Exception as e:
            self.session.rollback()
            logger.error(f"Failed to store data: {e}")
            raise

    def load(self, name: Optional[str] = None, **kwargs) -> List[Dict[str, Any]]:
        """Load data from database."""
        table_name = name or self.table_name

        try:
            # Query all items
            query = self.session.query(self.Embedding)

            # Convert to list of dicts
            results = []
            for item in query.all():
                result = {
                    "id": item.id,
                    "text": item.text,
                    "embedding": item.embedding,
                    "score": item.score
                }

                if item.metadata:
                    result.update(item.metadata)

                results.append(result)

            logger.info(f"Loaded {len(results)} items from database")
            return results

        except Exception as e:
            logger.error(f"Failed to load data: {e}")
            return []

    def search(self,
              query_vector: List[float],
              top_k: int = 10,
              threshold: float = 0.0,
              **kwargs) -> List[Dict[str, Any]]:
        """Search for similar vectors."""
        # This is a simplified implementation
        # In production, you'd use vector extensions like pgvector for PostgreSQL

        try:
            # Load all embeddings (not efficient for large datasets)
            all_data = self.load()

            # Calculate similarities
            import numpy as np
            query = np.array(query_vector)
            results = []

            for item in all_data:
                if item.get("embedding"):
                    vec = np.array(item["embedding"])
                    # Cosine similarity
                    similarity = np.dot(query, vec) / (np.linalg.norm(query) * np.linalg.norm(vec))
                    if similarity >= threshold:
                        item["score"] = float(similarity)
                        results.append(item)

            # Sort by score and return top_k
            results.sort(key=lambda x: x["score"], reverse=True)
            return results[:top_k]

        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

    def delete(self, filter_expr: Optional[str] = None, id: Optional[str] = None, **kwargs) -> bool:
        """Delete data from database."""
        try:
            query = self.session.query(self.Embedding)

            if id:
                query = query.filter_by(id=id)
            elif filter_expr:
                # Simple filter implementation
                # In production, you'd want more sophisticated filtering
                pass

            deleted = query.delete()
            self.session.commit()

            logger.info(f"Deleted {deleted} items")
            return True

        except Exception as e:
            self.session.rollback()
            logger.error(f"Delete failed: {e}")
            return False

    def update(self, id: str, data: Dict[str, Any], **kwargs) -> bool:
        """Update data in database."""
        try:
            query = self.session.query(self.Embedding).filter_by(id=id)
            item = query.first()

            if not item:
                return False

            # Update fields
            if "text" in data or "content" in data:
                item.text = data.get("text") or data.get("content")

            if "embedding" in data or "vector" in data:
                item.embedding = data.get("embedding") or data.get("vector")

            if "score" in data:
                item.score = data["score"]

            # Update metadata
            metadata = {k: v for k, v in data.items()
                       if k not in ["text", "content", "embedding", "vector", "score"]}
            if metadata:
                item.metadata = metadata

            self.session.commit()
            logger.info(f"Updated item {id}")
            return True

        except Exception as e:
            self.session.rollback()
            logger.error(f"Update failed: {e}")
            return False

    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics."""
        try:
            count = self.session.query(self.Embedding).count()
            return {
                "db_type": self.db_type,
                "table_name": self.table_name,
                "connection_string": self.connection_string,
                "num_items": count
            }
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {}

    def close(self):
        """Close database connection."""
        if self.session:
            self.session.close()
            logger.info("Database connection closed")