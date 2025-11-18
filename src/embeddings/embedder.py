"""
Embedding generation using OpenAI API with caching and batching.
"""

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Dict, List, Optional, Union

try:
    import tiktoken
except ImportError:
    tiktoken = None

from ..gen.openai_client import call_openai_chat_api, get_openai_client
from . import config

logger = logging.getLogger(__name__)


class Embedder:
    """
    Generate embeddings using OpenAI API with caching and batching support.
    """

    def __init__(
        self,
        model: str = None,
        cache_dir: Optional[str] = None,
        enable_cache: bool = None,
        batch_size: int = None,
    ):
        """
        Initialize embedder.

        Args:
            model: OpenAI embedding model (default: config.EMBEDDING_MODEL)
            cache_dir: Directory for caching embeddings (default: config.CACHE_DIR)
            enable_cache: Whether to use caching (default: config.ENABLE_EMBEDDING_CACHE)
            batch_size: Batch size for embedding generation (default: config.EMBEDDING_BATCH_SIZE)
        """
        self.model = model or config.EMBEDDING_MODEL
        self.dimensions = config.get_embedding_dimensions(self.model)
        self.enable_cache = enable_cache if enable_cache is not None else config.ENABLE_EMBEDDING_CACHE
        self.batch_size = batch_size or config.EMBEDDING_BATCH_SIZE

        # Initialize cache
        if self.enable_cache:
            self.cache_dir = Path(cache_dir or config.CACHE_DIR)
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self.cache_file = self.cache_dir / f"embeddings_{self.model.replace('/', '_')}.json"
            self.cache = self._load_cache()
        else:
            self.cache = {}

        # Initialize OpenAI client
        self.client = get_openai_client()

        # Initialize tokenizer for counting
        if tiktoken:
            try:
                self.tokenizer = tiktoken.encoding_for_model(self.model)
            except Exception:
                logger.warning(f"Could not load tokenizer for {self.model}, using cl100k_base")
                self.tokenizer = tiktoken.get_encoding("cl100k_base")
        else:
            self.tokenizer = None
            logger.warning("tiktoken not installed, token counting disabled")

        # Statistics
        self.stats = {
            "total_calls": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "total_tokens": 0,
            "total_time": 0.0,
        }

        logger.info(f"Embedder initialized with model={self.model}, dimensions={self.dimensions}")

    def _load_cache(self) -> Dict[str, List[float]]:
        """Load embedding cache from disk."""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r') as f:
                    cache = json.load(f)
                logger.info(f"Loaded {len(cache)} cached embeddings from {self.cache_file}")
                return cache
            except Exception as e:
                logger.warning(f"Failed to load cache: {e}")
                return {}
        return {}

    def _save_cache(self):
        """Save embedding cache to disk."""
        if not self.enable_cache:
            return

        try:
            with open(self.cache_file, 'w') as f:
                json.dump(self.cache, f)
            logger.debug(f"Saved {len(self.cache)} embeddings to cache")
        except Exception as e:
            logger.warning(f"Failed to save cache: {e}")

    def _get_cache_key(self, text: str) -> str:
        """Generate cache key for text."""
        return hashlib.sha256(f"{self.model}:{text}".encode()).hexdigest()

    def count_tokens(self, text: str) -> int:
        """
        Count tokens in text.

        Args:
            text: Input text

        Returns:
            Number of tokens (approximate if tokenizer not available)
        """
        if self.tokenizer:
            return len(self.tokenizer.encode(text))
        else:
            # Rough approximation: ~4 chars per token
            return len(text) // 4

    def embed(self, text: str, use_cache: bool = True) -> List[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Input text to embed
            use_cache: Whether to use cache (default: True)

        Returns:
            Embedding vector
        """
        if not text or not text.strip():
            logger.warning("Empty text provided for embedding")
            return [0.0] * self.dimensions

        # Check cache
        cache_key = self._get_cache_key(text)
        if use_cache and self.enable_cache and cache_key in self.cache:
            self.stats["cache_hits"] += 1
            return self.cache[cache_key]

        # Generate embedding
        start_time = time.time()
        try:
            response = self.client.embeddings.create(
                model=self.model,
                input=text,
            )

            embedding = response.data[0].embedding

            # Update cache
            if self.enable_cache:
                self.cache[cache_key] = embedding
                self.stats["cache_misses"] += 1

            # Update stats
            self.stats["total_calls"] += 1
            self.stats["total_tokens"] += response.usage.total_tokens
            self.stats["total_time"] += time.time() - start_time

            return embedding

        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            raise

    def embed_batch(
        self,
        texts: List[str],
        use_cache: bool = True,
        show_progress: bool = False,
    ) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in batches.

        Args:
            texts: List of input texts
            use_cache: Whether to use cache (default: True)
            show_progress: Whether to show progress (default: False)

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        embeddings = []
        texts_to_embed = []
        text_indices = []

        # Check cache for each text
        for i, text in enumerate(texts):
            if not text or not text.strip():
                embeddings.append([0.0] * self.dimensions)
                continue

            cache_key = self._get_cache_key(text)
            if use_cache and self.enable_cache and cache_key in self.cache:
                embeddings.append(self.cache[cache_key])
                self.stats["cache_hits"] += 1
            else:
                embeddings.append(None)  # Placeholder
                texts_to_embed.append(text)
                text_indices.append(i)

        # Generate embeddings for uncached texts in batches
        if texts_to_embed:
            if show_progress:
                logger.info(f"Generating embeddings for {len(texts_to_embed)} texts in batches of {self.batch_size}")

            for batch_start in range(0, len(texts_to_embed), self.batch_size):
                batch_end = min(batch_start + self.batch_size, len(texts_to_embed))
                batch_texts = texts_to_embed[batch_start:batch_end]
                batch_indices = text_indices[batch_start:batch_end]

                if show_progress:
                    logger.info(f"Processing batch {batch_start // self.batch_size + 1}/{(len(texts_to_embed) + self.batch_size - 1) // self.batch_size}")

                start_time = time.time()
                try:
                    response = self.client.embeddings.create(
                        model=self.model,
                        input=batch_texts,
                    )

                    # Update embeddings and cache
                    for i, data in enumerate(response.data):
                        embedding = data.embedding
                        original_idx = batch_indices[i]
                        embeddings[original_idx] = embedding

                        # Update cache
                        if self.enable_cache:
                            cache_key = self._get_cache_key(batch_texts[i])
                            self.cache[cache_key] = embedding

                    # Update stats
                    self.stats["total_calls"] += 1
                    self.stats["cache_misses"] += len(batch_texts)
                    self.stats["total_tokens"] += response.usage.total_tokens
                    self.stats["total_time"] += time.time() - start_time

                except Exception as e:
                    logger.error(f"Batch embedding failed: {e}")
                    # Fill with zero vectors as fallback
                    for idx in batch_indices:
                        if embeddings[idx] is None:
                            embeddings[idx] = [0.0] * self.dimensions

        # Save cache periodically
        if self.enable_cache and len(texts_to_embed) > 0:
            self._save_cache()

        return embeddings

    def embed_documents(
        self,
        documents: List[Dict[str, str]],
        text_key: str = "content",
        use_cache: bool = True,
        show_progress: bool = False,
    ) -> List[List[float]]:
        """
        Generate embeddings for documents.

        Args:
            documents: List of document dicts
            text_key: Key containing text to embed (default: "content")
            use_cache: Whether to use cache
            show_progress: Whether to show progress

        Returns:
            List of embedding vectors
        """
        texts = [doc.get(text_key, "") for doc in documents]
        return self.embed_batch(texts, use_cache=use_cache, show_progress=show_progress)

    def get_stats(self) -> Dict[str, Union[int, float]]:
        """
        Get embedding statistics.

        Returns:
            Dictionary with statistics
        """
        cache_hit_rate = 0.0
        if self.stats["cache_hits"] + self.stats["cache_misses"] > 0:
            cache_hit_rate = self.stats["cache_hits"] / (self.stats["cache_hits"] + self.stats["cache_misses"])

        avg_time_per_call = 0.0
        if self.stats["total_calls"] > 0:
            avg_time_per_call = self.stats["total_time"] / self.stats["total_calls"]

        return {
            **self.stats,
            "cache_hit_rate": cache_hit_rate,
            "avg_time_per_call": avg_time_per_call,
            "cache_size": len(self.cache),
        }

    def reset_stats(self):
        """Reset statistics."""
        self.stats = {
            "total_calls": 0,
            "cache_hits": 0,
            "cache_misses": 0,
            "total_tokens": 0,
            "total_time": 0.0,
        }

    def clear_cache(self):
        """Clear embedding cache."""
        self.cache = {}
        if self.enable_cache and self.cache_file.exists():
            self.cache_file.unlink()
        logger.info("Embedding cache cleared")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if self.enable_cache:
            self._save_cache()

        if config.LOG_EMBEDDING_STATS:
            stats = self.get_stats()
            logger.info(f"Embedding stats: {stats}")
