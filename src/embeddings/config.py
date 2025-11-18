"""
Configuration for embedding and ChromaDB integration.
"""

import os
from pathlib import Path

# ChromaDB Configuration
CHROMA_DB_PATH = os.getenv(
    "CHROMA_DB_PATH",
    str(Path(__file__).parent.parent.parent / "chroma_db")
)

# Collection Names
COLLECTION_CODE_ENTITIES = "code_entities"
COLLECTION_BUG_PATTERNS = "bug_patterns"
COLLECTION_SECURITY_PATTERNS = "security_patterns"
COLLECTION_CODE_SMELLS = "code_smells"
COLLECTION_TEST_PATTERNS = "test_patterns"

# Embedding Configuration
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
EMBEDDING_DIMENSIONS = {
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}

# Similarity Thresholds
SIMILARITY_THRESHOLD_BUG = float(os.getenv("SIMILARITY_THRESHOLD_BUG", "0.80"))
SIMILARITY_THRESHOLD_CODE = float(os.getenv("SIMILARITY_THRESHOLD_CODE", "0.75"))
SIMILARITY_THRESHOLD_SECURITY = float(os.getenv("SIMILARITY_THRESHOLD_SECURITY", "0.85"))
SIMILARITY_THRESHOLD_DUPLICATE = float(os.getenv("SIMILARITY_THRESHOLD_DUPLICATE", "0.90"))

# Context Retrieval
MAX_CONTEXT_TOKENS = int(os.getenv("MAX_CONTEXT_TOKENS", "10000"))
MAX_CONTEXT_CHUNKS = int(os.getenv("MAX_CONTEXT_CHUNKS", "50"))

# Batch Processing
EMBEDDING_BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "100"))
INDEXING_BATCH_SIZE = int(os.getenv("INDEXING_BATCH_SIZE", "500"))

# Distance Metric
DISTANCE_METRIC = os.getenv("DISTANCE_METRIC", "cosine")  # cosine, l2, ip

# Bug Classification
BUG_CONFIDENCE_HIGH = 0.85
BUG_CONFIDENCE_MEDIUM = 0.70
BUG_CONFIDENCE_LOW = 0.50

# Error Types
TEST_ERROR_TYPES = {
    "ImportError",
    "ModuleNotFoundError",
    "AttributeError",
    "NameError",
    "FixtureNotFoundError",
    "pytest.UsageError",
}

REAL_BUG_ERROR_TYPES = {
    "AssertionError",
    "ValueError",
    "TypeError",
    "KeyError",
    "IndexError",
    "ZeroDivisionError",
    "RuntimeError",
}

SECURITY_ERROR_TYPES = {
    "SecurityError",
    "PermissionError",
    "AuthenticationError",
    "ValidationError",
}

# Code Entity Types
ENTITY_TYPES = [
    "function",
    "class",
    "method",
    "route",
    "model",
    "view",
    "serializer",
    "form",
    "admin",
]

# Chunk Size Configuration
MAX_CHUNK_SIZE = int(os.getenv("MAX_CHUNK_SIZE", "2000"))  # characters
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "200"))  # characters

# Cache Configuration
ENABLE_EMBEDDING_CACHE = os.getenv("ENABLE_EMBEDDING_CACHE", "true").lower() == "true"
CACHE_DIR = os.getenv("CACHE_DIR", str(Path(__file__).parent.parent.parent / ".embedding_cache"))

# Incremental Update Configuration
ENABLE_INCREMENTAL_UPDATE = os.getenv("ENABLE_INCREMENTAL_UPDATE", "true").lower() == "true"
HASH_ALGORITHM = "sha256"

# Performance Tuning
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "4"))  # Parallel embedding workers
QUERY_TIMEOUT = int(os.getenv("QUERY_TIMEOUT", "30"))  # seconds

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_EMBEDDING_STATS = os.getenv("LOG_EMBEDDING_STATS", "true").lower() == "true"


def get_embedding_dimensions(model: str = None) -> int:
    """Get embedding dimensions for the specified model."""
    model = model or EMBEDDING_MODEL
    return EMBEDDING_DIMENSIONS.get(model, 1536)


def validate_config():
    """Validate configuration settings."""
    errors = []

    if SIMILARITY_THRESHOLD_BUG < 0 or SIMILARITY_THRESHOLD_BUG > 1:
        errors.append("SIMILARITY_THRESHOLD_BUG must be between 0 and 1")

    if SIMILARITY_THRESHOLD_CODE < 0 or SIMILARITY_THRESHOLD_CODE > 1:
        errors.append("SIMILARITY_THRESHOLD_CODE must be between 0 and 1")

    if DISTANCE_METRIC not in ["cosine", "l2", "ip"]:
        errors.append(f"Invalid DISTANCE_METRIC: {DISTANCE_METRIC}")

    if EMBEDDING_MODEL not in EMBEDDING_DIMENSIONS:
        errors.append(f"Unknown EMBEDDING_MODEL: {EMBEDDING_MODEL}")

    if errors:
        raise ValueError(f"Configuration errors: {', '.join(errors)}")

    return True
