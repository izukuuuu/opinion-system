"""BM25 retriever for keyword search."""

from typing import List, Dict, Any, Optional, Union
import logging
import math
import json
from pathlib import Path
from collections import defaultdict, Counter

from .base import BaseRetriever

logger = logging.getLogger(__name__)


class BM25Retriever(BaseRetriever):
    """BM25 retriever for keyword-based search."""

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)

        # BM25 parameters
        self.k1 = config.get("k1", 1.2) if config else 1.2
        self.b = config.get("b", 0.75) if config else 0.75
        self.epsilon = config.get("epsilon", 0.25) if config else 0.25

        # Index data
        self.doc_freqs = []
        self.idf = {}
        self.doc_lengths = []
        self.avgdl = 0
        self.corpus_size = 0
        self.vocabulary = set()

    def _tokenize(self, text: str) -> List[str]:
        """Simple tokenization."""
        # In a real implementation, you might want more sophisticated tokenization
        import re
        # Remove punctuation and split on whitespace
        text = re.sub(r'[^\w\s]', '', text.lower())
        return text.split()

    def build_index(self, documents: List[Dict[str, Any]], **kwargs) -> None:
        """Build BM25 index from documents."""
        logger.info("Building BM25 index...")

        self.documents = documents
        self.corpus_size = len(documents)

        # Extract texts from documents
        texts = []
        for doc in documents:
            # Try to get text field
            text = doc.get("text", "")
            if not text:
                # Fall back to concatenating other string fields
                text = " ".join([str(v) for v in doc.values() if isinstance(v, str)])
            texts.append(text)

        # Calculate document frequencies
        self.doc_freqs = []
        self.doc_lengths = []
        total_length = 0
        term_doc_freq = defaultdict(int)

        for text in texts:
            tokens = self._tokenize(text)
            self.doc_lengths.append(len(tokens))
            total_length += len(tokens)

            # Count token frequencies in document
            token_counts = Counter(tokens)
            self.doc_freqs.append(token_counts)

            # Update document frequencies
            for token in set(tokens):
                term_doc_freq[token] += 1
                self.vocabulary.add(token)

        # Calculate average document length
        self.avgdl = total_length / self.corpus_size if self.corpus_size > 0 else 0

        # Calculate IDF scores
        self.idf = {}
        for term in self.vocabulary:
            idf = math.log((self.corpus_size - term_doc_freq[term] + 0.5) / (term_doc_freq[term] + 0.5))
            self.idf[term] = idf if idf > 0 else self.epsilon

        logger.info(f"BM25 index built for {self.corpus_size} documents with {len(self.vocabulary)} unique terms")

    def retrieve(self, query: str, top_k: int = 10, **kwargs) -> List[Dict[str, Any]]:
        """Retrieve documents using BM25 scoring."""
        if not self.documents:
            return []

        # Tokenize query
        query_tokens = self._tokenize(query)

        # Calculate BM25 scores for each document
        scores = []
        for doc_idx, doc_freqs in enumerate(self.doc_freqs):
            score = 0
            for token in query_tokens:
                if token in doc_freqs and token in self.idf:
                    # BM25 formula
                    tf = doc_freqs[token]
                    idf = self.idf[token]
                    doc_len = self.doc_lengths[doc_idx]

                    # Normalized term frequency
                    normalized_tf = tf * (self.k1 + 1) / (tf + self.k1 * (1 - self.b + self.b * doc_len / self.avgdl))

                    score += idf * normalized_tf

            scores.append((doc_idx, score))

        # Sort by score (descending)
        scores.sort(key=lambda x: x[1], reverse=True)

        # Return top_k results
        results = []
        for doc_idx, score in scores[:top_k]:
            if score > 0:  # Only return documents with positive scores
                doc = self.documents[doc_idx].copy()
                doc["score"] = score
                doc["retrieval_type"] = "bm25"
                doc["id"] = doc.get("id", str(doc_idx))
                results.append(doc)

        return results

    def save_index(self, path: Union[str, Path], **kwargs) -> None:
        """Save BM25 index to disk."""
        path = Path(path)
        path.mkdir(parents=True, exist_ok=True)

        # Save index data
        index_data = {
            "k1": self.k1,
            "b": self.b,
            "epsilon": self.epsilon,
            "doc_freqs": self.doc_freqs,
            "idf": dict(self.idf),
            "doc_lengths": self.doc_lengths,
            "avgdl": self.avgdl,
            "corpus_size": self.corpus_size,
            "vocabulary": list(self.vocabulary)
        }

        index_path = path / "bm25_index.json"
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(index_data, f, indent=2)

        # Save documents
        docs_path = path / "documents.json"
        with open(docs_path, "w", encoding="utf-8") as f:
            json.dump(self.documents, f, ensure_ascii=False, indent=2)

        logger.info(f"BM25 index saved to {path}")

    def load_index(self, path: Union[str, Path], **kwargs) -> None:
        """Load BM25 index from disk."""
        path = Path(path)

        # Load index data
        index_path = path / "bm25_index.json"
        if index_path.exists():
            with open(index_path, "r", encoding="utf-8") as f:
                index_data = json.load(f)

            self.k1 = index_data.get("k1", 1.2)
            self.b = index_data.get("b", 0.75)
            self.epsilon = index_data.get("epsilon", 0.25)
            self.doc_freqs = index_data.get("doc_freqs", [])
            self.idf = index_data.get("idf", {})
            self.doc_lengths = index_data.get("doc_lengths", [])
            self.avgdl = index_data.get("avgdl", 0)
            self.corpus_size = index_data.get("corpus_size", 0)
            self.vocabulary = set(index_data.get("vocabulary", []))

        # Load documents
        docs_path = path / "documents.json"
        if docs_path.exists():
            with open(docs_path, "r", encoding="utf-8") as f:
                self.documents = json.load(f)

        logger.info(f"BM25 index loaded from {path}")

    def get_stats(self) -> Dict[str, Any]:
        """Get retriever statistics."""
        return {
            "type": "bm25",
            "k1": self.k1,
            "b": self.b,
            "epsilon": self.epsilon,
            "num_documents": self.corpus_size,
            "vocabulary_size": len(self.vocabulary),
            "avg_doc_length": self.avgdl
        }