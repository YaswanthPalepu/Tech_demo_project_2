"""
Semantic code search using embeddings.
"""

import logging
from typing import Any, Dict, List, Optional

from .chroma_client import ChromaClient
from .embedder import Embedder
from . import config

logger = logging.getLogger(__name__)


class SemanticSearch:
    """
    Semantic search for code entities, bug patterns, and context retrieval.
    """

    def __init__(
        self,
        chroma_client: Optional[ChromaClient] = None,
        embedder: Optional[Embedder] = None,
    ):
        """
        Initialize semantic search.

        Args:
            chroma_client: ChromaDB client
            embedder: Embedder instance
        """
        self.chroma_client = chroma_client or ChromaClient()
        self.embedder = embedder or Embedder()

        logger.info("SemanticSearch initialized")

    def search_code(
        self,
        query: str,
        n_results: int = 10,
        filters: Optional[Dict[str, Any]] = None,
        include_covered: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Search for similar code entities.

        Args:
            query: Natural language or code query
            n_results: Number of results to return
            filters: Optional metadata filters (e.g., {"entity_type": "function"})
            include_covered: Whether to include covered code

        Returns:
            List of matching code entities with similarity scores
        """
        where = filters or {}

        # Filter by coverage if needed
        if not include_covered:
            where["is_covered"] = False

        results = self.chroma_client.query(
            config.COLLECTION_CODE_ENTITIES,
            query_texts=[query],
            n_results=n_results,
            where=where if where else None,
        )

        matches = []
        for doc, metadata, distance in zip(
            results.get('documents', [[]])[0],
            results.get('metadatas', [[]])[0],
            results.get('distances', [[]])[0],
        ):
            similarity = 1 - distance
            matches.append({
                "entity_name": metadata.get('name'),
                "entity_type": metadata.get('entity_type'),
                "file_path": metadata.get('file_path'),
                "line_start": metadata.get('line_start'),
                "line_end": metadata.get('line_end'),
                "similarity": round(similarity, 3),
                "is_covered": metadata.get('is_covered', True),
                "coverage_pct": metadata.get('coverage_pct', 100.0),
            })

        return matches

    def find_similar_entities(
        self,
        entity_name: str,
        file_path: str,
        n_results: int = 10,
        exclude_self: bool = True,
    ) -> List[Dict[str, Any]]:
        """
        Find code entities similar to a given entity.

        Args:
            entity_name: Name of the entity
            file_path: File path of the entity
            n_results: Number of results to return
            exclude_self: Whether to exclude the entity itself

        Returns:
            List of similar entities
        """
        # Get the entity
        entity_results = self.chroma_client.search_by_metadata(
            config.COLLECTION_CODE_ENTITIES,
            where={
                "name": entity_name,
                "file_path": file_path,
            },
            limit=1,
        )

        if not entity_results.get('documents'):
            logger.warning(f"Entity {entity_name} not found in {file_path}")
            return []

        # Get embedding
        entity_doc = entity_results['documents'][0]
        entity_embedding = self.embedder.embed(entity_doc)

        # Find similar
        where = None
        if exclude_self:
            where = {
                "$or": [
                    {"name": {"$ne": entity_name}},
                    {"file_path": {"$ne": file_path}},
                ]
            }

        results = self.chroma_client.query(
            config.COLLECTION_CODE_ENTITIES,
            query_embeddings=[entity_embedding],
            n_results=n_results + (1 if not exclude_self else 0),
            where=where,
        )

        matches = []
        for doc, metadata, distance in zip(
            results.get('documents', [[]])[0],
            results.get('metadatas', [[]])[0],
            results.get('distances', [[]])[0],
        ):
            # Skip self if not excluded by filter
            if metadata.get('name') == entity_name and metadata.get('file_path') == file_path:
                continue

            similarity = 1 - distance
            matches.append({
                "entity_name": metadata.get('name'),
                "entity_type": metadata.get('entity_type'),
                "file_path": metadata.get('file_path'),
                "line_start": metadata.get('line_start'),
                "line_end": metadata.get('line_end'),
                "similarity": round(similarity, 3),
            })

        return matches

    def get_relevant_context(
        self,
        target_code: str,
        max_results: int = None,
        exclude_file: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Get most relevant code context for a target entity.

        Useful for test generation - retrieves related code instead
        of just truncating to token limits.

        Args:
            target_code: Target code entity
            max_results: Maximum number of context chunks
            exclude_file: Optional file to exclude (e.g., the target file)

        Returns:
            List of relevant code entities
        """
        max_results = max_results or config.MAX_CONTEXT_CHUNKS

        where = None
        if exclude_file:
            where = {"file_path": {"$ne": exclude_file}}

        results = self.chroma_client.query(
            config.COLLECTION_CODE_ENTITIES,
            query_texts=[target_code],
            n_results=max_results,
            where=where,
        )

        context_chunks = []
        for doc, metadata, distance in zip(
            results.get('documents', [[]])[0],
            results.get('metadatas', [[]])[0],
            results.get('distances', [[]])[0],
        ):
            similarity = 1 - distance

            # Only include relevant chunks (>0.5 similarity)
            if similarity >= 0.5:
                context_chunks.append({
                    "entity_name": metadata.get('name'),
                    "entity_type": metadata.get('entity_type'),
                    "file_path": metadata.get('file_path'),
                    "line_start": metadata.get('line_start'),
                    "line_end": metadata.get('line_end'),
                    "similarity": round(similarity, 3),
                    "content": doc,
                })

        return context_chunks

    def find_uncovered_similar_to(
        self,
        covered_entity: str,
        n_results: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Find uncovered code similar to a covered entity.

        Useful for prioritizing what to test next.

        Args:
            covered_entity: Code from a covered entity
            n_results: Number of results

        Returns:
            List of similar uncovered entities
        """
        results = self.chroma_client.query(
            config.COLLECTION_CODE_ENTITIES,
            query_texts=[covered_entity],
            n_results=n_results * 2,  # Get more, filter later
            where={"is_covered": False},
        )

        matches = []
        for doc, metadata, distance in zip(
            results.get('documents', [[]])[0],
            results.get('metadatas', [[]])[0],
            results.get('distances', [[]])[0],
        ):
            similarity = 1 - distance

            if similarity >= config.SIMILARITY_THRESHOLD_CODE:
                matches.append({
                    "entity_name": metadata.get('name'),
                    "entity_type": metadata.get('entity_type'),
                    "file_path": metadata.get('file_path'),
                    "line_start": metadata.get('line_start'),
                    "line_end": metadata.get('line_end'),
                    "similarity": round(similarity, 3),
                    "coverage_pct": metadata.get('coverage_pct', 0.0),
                })

        return matches[:n_results]

    def search_by_description(
        self,
        description: str,
        entity_type: Optional[str] = None,
        n_results: int = 5,
    ) -> List[Dict[str, Any]]:
        """
        Search code by natural language description.

        Args:
            description: Natural language description
            entity_type: Optional filter by type (function, class, etc.)
            n_results: Number of results

        Returns:
            List of matching entities
        """
        where = None
        if entity_type:
            where = {"entity_type": entity_type}

        results = self.chroma_client.query(
            config.COLLECTION_CODE_ENTITIES,
            query_texts=[description],
            n_results=n_results,
            where=where,
        )

        matches = []
        for doc, metadata, distance in zip(
            results.get('documents', [[]])[0],
            results.get('metadatas', [[]])[0],
            results.get('distances', [[]])[0],
        ):
            similarity = 1 - distance
            matches.append({
                "entity_name": metadata.get('name'),
                "entity_type": metadata.get('entity_type'),
                "file_path": metadata.get('file_path'),
                "line_start": metadata.get('line_start'),
                "line_end": metadata.get('line_end'),
                "similarity": round(similarity, 3),
                "content_preview": doc[:200] + "..." if len(doc) > 200 else doc,
            })

        return matches

    def cluster_uncovered_code(
        self,
        min_similarity: float = 0.75,
    ) -> List[Dict[str, Any]]:
        """
        Group uncovered code into semantic clusters.

        Useful for batching test generation.

        Args:
            min_similarity: Minimum similarity for clustering

        Returns:
            List of clusters with similar uncovered entities
        """
        # Get all uncovered entities
        uncovered = self.chroma_client.search_by_metadata(
            config.COLLECTION_CODE_ENTITIES,
            where={"is_covered": False},
        )

        if not uncovered.get('documents'):
            return []

        # Simple greedy clustering
        clusters = []
        processed = set()

        for i, (doc, metadata) in enumerate(zip(uncovered['documents'], uncovered['metadatas'])):
            entity_id = f"{metadata.get('file_path')}:{metadata.get('name')}"

            if entity_id in processed:
                continue

            # Find similar entities
            embedding = self.embedder.embed(doc)
            similar = self.chroma_client.query(
                config.COLLECTION_CODE_ENTITIES,
                query_embeddings=[embedding],
                n_results=20,
                where={"is_covered": False},
            )

            cluster_members = []
            for s_doc, s_metadata, s_distance in zip(
                similar.get('documents', [[]])[0],
                similar.get('metadatas', [[]])[0],
                similar.get('distances', [[]])[0],
            ):
                s_similarity = 1 - s_distance
                s_entity_id = f"{s_metadata.get('file_path')}:{s_metadata.get('name')}"

                if s_similarity >= min_similarity and s_entity_id not in processed:
                    cluster_members.append({
                        "entity_name": s_metadata.get('name'),
                        "file_path": s_metadata.get('file_path'),
                        "similarity_to_anchor": round(s_similarity, 3),
                    })
                    processed.add(s_entity_id)

            if cluster_members:
                clusters.append({
                    "anchor_entity": metadata.get('name'),
                    "anchor_file": metadata.get('file_path'),
                    "cluster_size": len(cluster_members),
                    "members": cluster_members,
                })

        logger.info(f"Created {len(clusters)} semantic clusters from uncovered code")
        return clusters
