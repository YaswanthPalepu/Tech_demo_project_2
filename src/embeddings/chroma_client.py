"""
ChromaDB client wrapper for vector storage and retrieval.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

try:
    import chromadb
    from chromadb.config import Settings
    from chromadb.utils import embedding_functions
except ImportError:
    raise ImportError(
        "ChromaDB not installed. Install with: pip install chromadb"
    )

from . import config

logger = logging.getLogger(__name__)


class ChromaClient:
    """
    Wrapper for ChromaDB client with predefined collections
    for code entities, bug patterns, and semantic search.
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        embedding_function: Optional[Any] = None,
        reset: bool = False,
    ):
        """
        Initialize ChromaDB client.

        Args:
            db_path: Path to ChromaDB storage (default: config.CHROMA_DB_PATH)
            embedding_function: Custom embedding function (default: None, uses embedder)
            reset: Whether to reset/clear all collections (default: False)
        """
        self.db_path = Path(db_path or config.CHROMA_DB_PATH)
        self.db_path.mkdir(parents=True, exist_ok=True)

        # Initialize ChromaDB client
        self.client = chromadb.PersistentClient(
            path=str(self.db_path),
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True,
            ),
        )

        self.embedding_function = embedding_function
        self.collections = {}

        if reset:
            logger.warning("Resetting ChromaDB - all data will be deleted!")
            self.client.reset()

        # Initialize collections
        self._init_collections()

        logger.info(f"ChromaDB initialized at {self.db_path}")

    def _init_collections(self):
        """Initialize predefined collections."""
        collection_configs = {
            config.COLLECTION_CODE_ENTITIES: {
                "metadata": {
                    "hnsw:space": config.DISTANCE_METRIC,
                    "description": "Code entities with embeddings",
                }
            },
            config.COLLECTION_BUG_PATTERNS: {
                "metadata": {
                    "hnsw:space": config.DISTANCE_METRIC,
                    "description": "Historical bug patterns",
                }
            },
            config.COLLECTION_SECURITY_PATTERNS: {
                "metadata": {
                    "hnsw:space": config.DISTANCE_METRIC,
                    "description": "Security vulnerability patterns",
                }
            },
            config.COLLECTION_CODE_SMELLS: {
                "metadata": {
                    "hnsw:space": config.DISTANCE_METRIC,
                    "description": "Code smell and anti-pattern examples",
                }
            },
            config.COLLECTION_TEST_PATTERNS: {
                "metadata": {
                    "hnsw:space": config.DISTANCE_METRIC,
                    "description": "Common test patterns and scenarios",
                }
            },
        }

        for name, cfg in collection_configs.items():
            try:
                collection = self.client.get_or_create_collection(
                    name=name,
                    metadata=cfg["metadata"],
                    embedding_function=self.embedding_function,
                )
                self.collections[name] = collection
                logger.info(f"Collection '{name}' ready ({collection.count()} items)")
            except Exception as e:
                logger.error(f"Failed to initialize collection '{name}': {e}")
                raise

    def add_documents(
        self,
        collection_name: str,
        documents: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None,
        embeddings: Optional[List[List[float]]] = None,
    ) -> None:
        """
        Add documents to a collection.

        Args:
            collection_name: Name of the collection
            documents: List of document texts
            metadatas: Optional list of metadata dicts
            ids: Optional list of document IDs (auto-generated if None)
            embeddings: Optional pre-computed embeddings
        """
        collection = self.collections.get(collection_name)
        if not collection:
            raise ValueError(f"Collection '{collection_name}' not found")

        if ids is None:
            # Generate IDs
            existing_count = collection.count()
            ids = [f"{collection_name}_{existing_count + i}" for i in range(len(documents))]

        try:
            if embeddings:
                # Use provided embeddings
                collection.add(
                    documents=documents,
                    metadatas=metadatas,
                    ids=ids,
                    embeddings=embeddings,
                )
            else:
                # Let ChromaDB handle embedding (if embedding_function is set)
                collection.add(
                    documents=documents,
                    metadatas=metadatas,
                    ids=ids,
                )

            logger.debug(f"Added {len(documents)} documents to '{collection_name}'")

        except Exception as e:
            logger.error(f"Failed to add documents to '{collection_name}': {e}")
            raise

    def query(
        self,
        collection_name: str,
        query_texts: Optional[List[str]] = None,
        query_embeddings: Optional[List[List[float]]] = None,
        n_results: int = 10,
        where: Optional[Dict[str, Any]] = None,
        where_document: Optional[Dict[str, Any]] = None,
        include: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Query a collection for similar documents.

        Args:
            collection_name: Name of the collection
            query_texts: List of query texts (will be embedded)
            query_embeddings: Pre-computed query embeddings
            n_results: Number of results to return
            where: Metadata filters
            where_document: Document content filters
            include: Fields to include in results

        Returns:
            Query results with documents, metadatas, distances
        """
        collection = self.collections.get(collection_name)
        if not collection:
            raise ValueError(f"Collection '{collection_name}' not found")

        if not query_texts and not query_embeddings:
            raise ValueError("Must provide either query_texts or query_embeddings")

        include = include or ["documents", "metadatas", "distances"]

        try:
            results = collection.query(
                query_texts=query_texts,
                query_embeddings=query_embeddings,
                n_results=n_results,
                where=where,
                where_document=where_document,
                include=include,
            )
            return results

        except Exception as e:
            logger.error(f"Query failed for collection '{collection_name}': {e}")
            raise

    def update_documents(
        self,
        collection_name: str,
        ids: List[str],
        documents: Optional[List[str]] = None,
        metadatas: Optional[List[Dict[str, Any]]] = None,
        embeddings: Optional[List[List[float]]] = None,
    ) -> None:
        """
        Update existing documents in a collection.

        Args:
            collection_name: Name of the collection
            ids: List of document IDs to update
            documents: Updated document texts
            metadatas: Updated metadata
            embeddings: Updated embeddings
        """
        collection = self.collections.get(collection_name)
        if not collection:
            raise ValueError(f"Collection '{collection_name}' not found")

        try:
            collection.update(
                ids=ids,
                documents=documents,
                metadatas=metadatas,
                embeddings=embeddings,
            )
            logger.debug(f"Updated {len(ids)} documents in '{collection_name}'")

        except Exception as e:
            logger.error(f"Failed to update documents in '{collection_name}': {e}")
            raise

    def delete_documents(
        self,
        collection_name: str,
        ids: Optional[List[str]] = None,
        where: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Delete documents from a collection.

        Args:
            collection_name: Name of the collection
            ids: List of document IDs to delete
            where: Metadata filter for deletion
        """
        collection = self.collections.get(collection_name)
        if not collection:
            raise ValueError(f"Collection '{collection_name}' not found")

        try:
            collection.delete(ids=ids, where=where)
            logger.debug(f"Deleted documents from '{collection_name}'")

        except Exception as e:
            logger.error(f"Failed to delete documents from '{collection_name}': {e}")
            raise

    def get_collection_stats(self, collection_name: str) -> Dict[str, Any]:
        """
        Get statistics about a collection.

        Args:
            collection_name: Name of the collection

        Returns:
            Dictionary with collection statistics
        """
        collection = self.collections.get(collection_name)
        if not collection:
            raise ValueError(f"Collection '{collection_name}' not found")

        return {
            "name": collection_name,
            "count": collection.count(),
            "metadata": collection.metadata,
        }

    def search_by_metadata(
        self,
        collection_name: str,
        where: Dict[str, Any],
        limit: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Search documents by metadata filter only.

        Args:
            collection_name: Name of the collection
            where: Metadata filter
            limit: Maximum number of results

        Returns:
            Matching documents with metadata
        """
        collection = self.collections.get(collection_name)
        if not collection:
            raise ValueError(f"Collection '{collection_name}' not found")

        try:
            results = collection.get(
                where=where,
                limit=limit,
                include=["documents", "metadatas"],
            )
            return results

        except Exception as e:
            logger.error(f"Metadata search failed for '{collection_name}': {e}")
            raise

    def clear_collection(self, collection_name: str) -> None:
        """
        Clear all documents from a collection.

        Args:
            collection_name: Name of the collection
        """
        collection = self.collections.get(collection_name)
        if not collection:
            raise ValueError(f"Collection '{collection_name}' not found")

        try:
            # Get all IDs and delete them
            all_data = collection.get()
            if all_data["ids"]:
                collection.delete(ids=all_data["ids"])
                logger.info(f"Cleared {len(all_data['ids'])} documents from '{collection_name}'")

        except Exception as e:
            logger.error(f"Failed to clear collection '{collection_name}': {e}")
            raise

    def list_collections(self) -> List[str]:
        """
        List all collection names.

        Returns:
            List of collection names
        """
        return list(self.collections.keys())

    def close(self):
        """Close the ChromaDB client."""
        # ChromaDB automatically persists data
        logger.info("ChromaDB client closed")

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
