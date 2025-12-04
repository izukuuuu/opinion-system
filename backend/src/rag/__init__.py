"""
RAG (Retrieval-Augmented Generation) module for the opinion system.

This module provides comprehensive functionality for:
- Converting between different RAG formats (TagRAG, RouterRAG)
- Text chunking and preprocessing
- Vector embeddings and similarity search
- Data storage and retrieval
- CLI utilities for RAG operations
"""

__version__ = "1.0.0"
__author__ = "RAG Team"

from .core import *
from .converters import *
from .embeddings import *
from .retrievers import *
from .storage import *