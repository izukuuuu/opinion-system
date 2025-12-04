"""Text preprocessing utilities for RAG."""

import re
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass
import unicodedata


@dataclass
class ProcessingConfig:
    """Configuration for text preprocessing."""
    lowercase: bool = False
    remove_urls: bool = True
    remove_emails: bool = True
    remove_phone_numbers: bool = False
    remove_extra_whitespace: bool = True
    remove_special_chars: bool = False
    normalize_unicode: bool = True
    min_word_length: int = 1
    stop_words: Optional[Set[str]] = None
    custom_patterns: Optional[Dict[str, str]] = None


class TextProcessor:
    """Text preprocessing utilities."""

    def __init__(self, config: Optional[ProcessingConfig] = None):
        self.config = config or ProcessingConfig()
        self._compile_patterns()

    def _compile_patterns(self):
        """Compile regex patterns for efficiency."""
        self.patterns = {
            'url': re.compile(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'),
            'email': re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
            'phone': re.compile(r'(\+?1[-.\s]?)?\(?([0-9]{3})\)?[-.\s]?([0-9]{3})[-.\s]?([0-9]{4})'),
            'extra_whitespace': re.compile(r'\s+'),
            'non_printable': re.compile(r'[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]'),
        }

        # Add custom patterns
        if self.config.custom_patterns:
            for name, pattern in self.config.custom_patterns.items():
                self.patterns[name] = re.compile(pattern)

    def clean(self, text: str) -> str:
        """Apply all cleaning operations to text."""
        if not text:
            return ""

        # Normalize Unicode
        if self.config.normalize_unicode:
            text = unicodedata.normalize('NFKC', text)

        # Remove URLs
        if self.config.remove_urls:
            text = self.patterns['url'].sub(' ', text)

        # Remove emails
        if self.config.remove_emails:
            text = self.patterns['email'].sub(' ', text)

        # Remove phone numbers
        if self.config.remove_phone_numbers:
            text = self.patterns['phone'].sub(' ', text)

        # Remove special characters
        if self.config.remove_special_chars:
            # Keep alphanumeric, punctuation, and Chinese characters
            text = re.sub(r'[^a-zA-Z0-9\s.,!?;:\'"()\[\]{}—\u4e00-\u9fff]', ' ', text)

        # Remove non-printable characters
        text = self.patterns['non_printable'].sub(' ', text)

        # Convert to lowercase
        if self.config.lowercase:
            text = text.lower()

        # Remove extra whitespace
        if self.config.remove_extra_whitespace:
            text = self.patterns['extra_whitespace'].sub(' ', text).strip()

        return text

    def tokenize(self, text: str) -> List[str]:
        """Tokenize text into words."""
        # Simple tokenization that supports English and Chinese
        tokens = re.findall(r'[a-zA-Z]+|\d+|[\u4e00-\u9fff]', text)

        # Filter by min word length
        tokens = [t for t in tokens if len(t) >= self.config.min_word_length]

        # Remove stop words
        if self.config.stop_words:
            tokens = [t for t in tokens if t not in self.config.stop_words]

        return tokens

    def extract_sentences(self, text: str) -> List[str]:
        """Extract sentences from text."""
        # Simple sentence splitting that works for English and Chinese
        sentences = re.split(r'[.!?。！？]+', text)
        return [s.strip() for s in sentences if s.strip()]

    def extract_keywords(self, text: str, top_k: int = 10) -> List[str]:
        """Extract keywords from text using simple frequency analysis."""
        tokens = self.tokenize(text)
        freq = {}

        for token in tokens:
            freq[token] = freq.get(token, 0) + 1

        # Sort by frequency and return top-k
        keywords = sorted(freq.items(), key=lambda x: x[1], reverse=True)
        return [kw for kw, _ in keywords[:top_k]]

    def process_batch(self, texts: List[str]) -> List[str]:
        """Process a batch of texts."""
        return [self.clean(text) for text in texts]

    def compute_similarity(self, text1: str, text2: str) -> float:
        """Compute simple Jaccard similarity between two texts."""
        tokens1 = set(self.tokenize(text1))
        tokens2 = set(self.tokenize(text2))

        if not tokens1 or not tokens2:
            return 0.0

        intersection = tokens1.intersection(tokens2)
        union = tokens1.union(tokens2)

        return len(intersection) / len(union)

    def filter_by_relevance(self, query: str, texts: List[str], threshold: float = 0.1) -> List[str]:
        """Filter texts by relevance to a query."""
        relevant = []

        for text in texts:
            similarity = self.compute_similarity(query, text)
            if similarity >= threshold:
                relevant.append(text)

        return relevant