"""
Embedding-based bug detection and semantic code search module.

This module provides:
- ChromaDB integration for vector storage
- OpenAI embedding generation
- Code entity indexing
- Bug pattern matching
- Semantic search capabilities
- Error classification (real bugs vs test mistakes)
"""

from .chroma_client import ChromaClient
from .embedder import Embedder
from .code_indexer import CodeIndexer
from .bug_detector import BugDetector
from .error_classifier import ErrorClassifier
from .semantic_search import SemanticSearch

__all__ = [
    'ChromaClient',
    'Embedder',
    'CodeIndexer',
    'BugDetector',
    'ErrorClassifier',
    'SemanticSearch',
]
