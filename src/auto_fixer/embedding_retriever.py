"""
Embedding-Based Code Retriever

Performs semantic search on the code index to find relevant code elements.
"""

import os
import numpy as np
from typing import List, Dict, Optional, Set, Tuple
from dataclasses import dataclass

try:
    from openai import AzureOpenAI
except ImportError:
    AzureOpenAI = None


@dataclass
class SearchResult:
    """Represents a search result with similarity score."""
    element_id: str
    element_type: str
    name: str
    file_path: str
    line_start: int
    line_end: int
    signature: str
    source_code: str
    similarity_score: float
    dependencies: List[str]
    metadata: Dict

    def __repr__(self):
        return f"SearchResult(name={self.name}, type={self.element_type}, score={self.similarity_score:.3f})"


class EmbeddingRetriever:
    """
    Retrieves relevant code elements using semantic search.

    Key features:
    - Semantic similarity search
    - Fallback to text-based search when embeddings unavailable
    - Recursive dependency resolution
    - HTTP endpoint to handler mapping
    - "Target not found" and "Source not found" detection
    """

    def __init__(
        self,
        indexer,  # EmbeddingIndexer instance
        embedding_model: str = "text-embedding-3-small",
        verbose: bool = False
    ):
        """
        Initialize retriever.

        Args:
            indexer: EmbeddingIndexer instance with built index
            embedding_model: OpenAI embedding model to use
            verbose: Enable verbose logging
        """
        self.indexer = indexer
        self.embedding_model = embedding_model
        self.verbose = verbose

        # OpenAI client (lazy init)
        self._client: Optional[AzureOpenAI] = None

    def get_openai_client(self) -> AzureOpenAI:
        """Get or create OpenAI client."""
        if self._client is None:
            self._client = self.indexer.get_openai_client()
        return self._client

    def search(
        self,
        query: str,
        top_k: int = 10,
        filters: Optional[Dict] = None,
        min_similarity: float = 0.5
    ) -> List[SearchResult]:
        """
        Search for relevant code elements.

        Args:
            query: Search query (e.g., "POST /predict", "function that validates input")
            top_k: Number of results to return
            filters: Optional filters (e.g., {'type': 'function', 'file_path': 'app/main.py'})
            min_similarity: Minimum similarity threshold

        Returns:
            List of SearchResult objects ranked by relevance
        """
        if not self.indexer.elements:
            if self.verbose:
                print("⚠ Index is empty. Build index first.")
            return []

        # Check if we have embeddings
        has_embeddings = any(
            'embedding' in elem.metadata
            for elem in self.indexer.elements
        )

        if has_embeddings:
            results = self._search_with_embeddings(query, top_k, filters, min_similarity)
        else:
            if self.verbose:
                print("ℹ Using text-based search (no embeddings available)")
            results = self._search_text_based(query, top_k, filters)

        return results

    def _search_with_embeddings(
        self,
        query: str,
        top_k: int,
        filters: Optional[Dict],
        min_similarity: float
    ) -> List[SearchResult]:
        """Perform embedding-based semantic search."""
        try:
            # Generate query embedding
            client = self.get_openai_client()
            response = client.embeddings.create(
                input=[query],
                model=self.embedding_model
            )
            query_embedding = response.data[0].embedding

        except Exception as e:
            if self.verbose:
                print(f"⚠ Error generating query embedding: {e}")
                print("  Falling back to text-based search")
            return self._search_text_based(query, top_k, filters)

        # Compute similarities
        results = []

        for elem in self.indexer.elements:
            # Apply filters
            if filters:
                skip = False
                for key, value in filters.items():
                    if key == 'type' and elem.type != value:
                        skip = True
                        break
                    elif key == 'file_path' and value not in elem.file_path:
                        skip = True
                        break
                if skip:
                    continue

            # Get element embedding
            elem_embedding = elem.metadata.get('embedding')
            if not elem_embedding:
                continue

            # Compute cosine similarity
            similarity = self._cosine_similarity(query_embedding, elem_embedding)

            if similarity >= min_similarity:
                result = SearchResult(
                    element_id=elem.id,
                    element_type=elem.type,
                    name=elem.name,
                    file_path=elem.file_path,
                    line_start=elem.line_start,
                    line_end=elem.line_end,
                    signature=elem.signature,
                    source_code=elem.source_code,
                    similarity_score=similarity,
                    dependencies=elem.dependencies,
                    metadata=elem.metadata
                )
                results.append(result)

        # Sort by similarity (descending)
        results.sort(key=lambda r: r.similarity_score, reverse=True)

        return results[:top_k]

    def _search_text_based(
        self,
        query: str,
        top_k: int,
        filters: Optional[Dict]
    ) -> List[SearchResult]:
        """Fallback text-based search using keyword matching."""
        query_lower = query.lower()
        results = []

        for elem in self.indexer.elements:
            # Apply filters
            if filters:
                skip = False
                for key, value in filters.items():
                    if key == 'type' and elem.type != value:
                        skip = True
                        break
                    elif key == 'file_path' and value not in elem.file_path:
                        skip = True
                        break
                if skip:
                    continue

            # Compute text-based score
            score = 0.0
            searchable_text = f"{elem.name} {elem.signature} {elem.docstring} {elem.source_code}".lower()

            # Exact name match
            if query_lower in elem.name.lower():
                score += 1.0

            # Signature match
            if query_lower in elem.signature.lower():
                score += 0.7

            # HTTP endpoint match (for queries like "POST /predict")
            if elem.type == 'http_endpoint':
                method = elem.metadata.get('http_method', '').lower()
                route = elem.metadata.get('http_route', '').lower()
                endpoint_str = f"{method} {route}"

                if query_lower in endpoint_str:
                    score += 1.5

            # General text match
            query_words = query_lower.split()
            matched_words = sum(1 for word in query_words if word in searchable_text)
            score += (matched_words / len(query_words)) * 0.5

            if score > 0:
                result = SearchResult(
                    element_id=elem.id,
                    element_type=elem.type,
                    name=elem.name,
                    file_path=elem.file_path,
                    line_start=elem.line_start,
                    line_end=elem.line_end,
                    signature=elem.signature,
                    source_code=elem.source_code,
                    similarity_score=score,
                    dependencies=elem.dependencies,
                    metadata=elem.metadata
                )
                results.append(result)

        # Sort by score (descending)
        results.sort(key=lambda r: r.similarity_score, reverse=True)

        return results[:top_k]

    @staticmethod
    def _cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
        """Compute cosine similarity between two vectors."""
        v1 = np.array(vec1)
        v2 = np.array(vec2)

        dot_product = np.dot(v1, v2)
        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)

        if norm1 == 0 or norm2 == 0:
            return 0.0

        return float(dot_product / (norm1 * norm2))

    def search_by_http_endpoint(
        self,
        method: str,
        route: str
    ) -> Optional[SearchResult]:
        """
        Find the handler for a specific HTTP endpoint.

        Args:
            method: HTTP method (GET, POST, etc.)
            route: Route path (/predict, /health, etc.)

        Returns:
            SearchResult for the handler or None
        """
        query = f"{method.upper()} {route}"

        results = self.search(
            query=query,
            top_k=5,
            filters={'type': 'http_endpoint'},
            min_similarity=0.6
        )

        # Return the best match
        if results:
            if self.verbose:
                print(f"  ✓ Found handler for {method} {route}: {results[0].name}")
            return results[0]

        if self.verbose:
            print(f"  ✗ No handler found for {method} {route}")
        return None

    def search_by_error_traceback(
        self,
        error_message: str,
        file_path: Optional[str] = None
    ) -> List[SearchResult]:
        """
        Find relevant code based on error traceback.

        Args:
            error_message: Full error message with traceback
            file_path: Optional file path to filter results

        Returns:
            List of relevant SearchResult objects
        """
        # Extract function names from traceback
        import re
        pattern = r'in (\w+)'
        function_names = re.findall(pattern, error_message)

        # Extract file paths from traceback
        file_pattern = r'File "([^"]+)"'
        file_paths = re.findall(file_pattern, error_message)

        # Build query from error context
        query_parts = []

        if function_names:
            query_parts.append(' '.join(function_names[:3]))

        # Add error type/message context
        error_lines = error_message.split('\n')
        if error_lines:
            last_line = error_lines[-1].strip()
            if last_line:
                query_parts.append(last_line)

        query = ' '.join(query_parts)

        # Search
        filters = None
        if file_path:
            filters = {'file_path': file_path}

        results = self.search(
            query=query,
            top_k=10,
            filters=filters,
            min_similarity=0.5
        )

        # Boost results that match function names in traceback
        for result in results:
            if result.name in function_names:
                result.similarity_score += 0.3

        # Re-sort
        results.sort(key=lambda r: r.similarity_score, reverse=True)

        return results

    def resolve_dependencies_recursive(
        self,
        element_names: List[str],
        max_depth: int = 3,
        visited: Optional[Set[str]] = None
    ) -> List[SearchResult]:
        """
        Recursively resolve dependencies of given elements.

        Args:
            element_names: Names of elements to resolve
            max_depth: Maximum recursion depth
            visited: Set of already visited element names (for cycle detection)

        Returns:
            List of all dependencies (including transitive)
        """
        if visited is None:
            visited = set()

        if max_depth <= 0:
            return []

        all_dependencies = []

        for name in element_names:
            if name in visited:
                continue

            visited.add(name)

            # Find the element
            matching_elements = [
                elem for elem in self.indexer.elements
                if elem.name == name
            ]

            if not matching_elements:
                continue

            element = matching_elements[0]

            # Add the element itself
            result = SearchResult(
                element_id=element.id,
                element_type=element.type,
                name=element.name,
                file_path=element.file_path,
                line_start=element.line_start,
                line_end=element.line_end,
                signature=element.signature,
                source_code=element.source_code,
                similarity_score=1.0,
                dependencies=element.dependencies,
                metadata=element.metadata
            )
            all_dependencies.append(result)

            # Recursively resolve dependencies
            if element.dependencies:
                dep_results = self.resolve_dependencies_recursive(
                    element.dependencies,
                    max_depth - 1,
                    visited
                )
                all_dependencies.extend(dep_results)

        return all_dependencies

    def detect_missing_target(
        self,
        target_name: str,
        context: str = ""
    ) -> Tuple[bool, Optional[str]]:
        """
        Detect if a target function/class doesn't exist in the codebase.

        Args:
            target_name: Name of the target to find
            context: Additional context (error message, test code)

        Returns:
            (is_missing, suggestion) tuple
            - is_missing: True if target not found
            - suggestion: Suggested alternative if available
        """
        query = f"{target_name} {context}"

        results = self.search(
            query=query,
            top_k=5,
            min_similarity=0.5
        )

        if not results:
            if self.verbose:
                print(f"  ❌ Target '{target_name}' not found in codebase")
            return True, None

        # Check if top result is a good match
        top_result = results[0]

        if top_result.similarity_score > 0.75:
            if self.verbose:
                print(f"  ✓ Found target '{target_name}': {top_result.name}")
            return False, None

        # Low similarity - might be a typo
        if self.verbose:
            print(f"  ⚠ Target '{target_name}' not found, but similar: {top_result.name}")

        return True, top_result.name

    def get_statistics(self) -> Dict:
        """Get retrieval statistics."""
        total_with_embeddings = sum(
            1 for elem in self.indexer.elements
            if 'embedding' in elem.metadata
        )

        return {
            'total_elements': len(self.indexer.elements),
            'elements_with_embeddings': total_with_embeddings,
            'coverage': f"{(total_with_embeddings / len(self.indexer.elements) * 100):.1f}%" if self.indexer.elements else "0%"
        }
