"""
Smart Code Chunker

Handles intelligent chunking of code context to fit within LLM token limits.
"""

from typing import List, Dict, Optional
from dataclasses import dataclass


@dataclass
class CodeChunk:
    """Represents a chunk of code context."""
    content: str
    priority: int  # Higher priority chunks are kept first
    token_estimate: int
    metadata: Dict

    def __repr__(self):
        return f"CodeChunk(priority={self.priority}, tokens={self.token_estimate})"


class CodeChunker:
    """
    Intelligently chunks code context to fit within token limits.

    Priority system:
    1. Direct matches (functions/classes mentioned in error)
    2. HTTP endpoint handlers
    3. First-level dependencies
    4. Second-level dependencies
    5. Related code in same file
    """

    def __init__(
        self,
        max_tokens: int = 6000,  # Leave room for system prompt + response
        chars_per_token: int = 4,  # Rough estimate
        verbose: bool = False
    ):
        """
        Initialize chunker.

        Args:
            max_tokens: Maximum tokens for context
            chars_per_token: Estimated characters per token
            verbose: Enable verbose logging
        """
        self.max_tokens = max_tokens
        self.chars_per_token = chars_per_token
        self.verbose = verbose

    def chunk_context(
        self,
        search_results: List,  # List of SearchResult objects
        test_code: str = "",
        error_message: str = ""
    ) -> List[CodeChunk]:
        """
        Create prioritized chunks from search results.

        Args:
            search_results: List of SearchResult objects
            test_code: The failing test code (for reference)
            error_message: Error message (for reference)

        Returns:
            List of CodeChunk objects in priority order
        """
        chunks = []

        # Chunk 1: Test code itself (ALWAYS include)
        if test_code:
            test_chunk = CodeChunk(
                content=test_code,
                priority=100,
                token_estimate=self._estimate_tokens(test_code),
                metadata={'type': 'test_code'}
            )
            chunks.append(test_chunk)

        # Chunk 2: Error message (ALWAYS include)
        if error_message:
            # Truncate very long error messages
            error_summary = error_message
            if len(error_summary) > 2000:
                error_summary = error_summary[:2000] + "\n... (truncated)"

            error_chunk = CodeChunk(
                content=error_summary,
                priority=100,
                token_estimate=self._estimate_tokens(error_summary),
                metadata={'type': 'error_message'}
            )
            chunks.append(error_chunk)

        # Chunk 3+: Source code from search results
        for result in search_results:
            # Determine priority based on similarity and type
            priority = self._calculate_priority(result)

            # Format the source code
            content = self._format_source_code(result)

            chunk = CodeChunk(
                content=content,
                priority=priority,
                token_estimate=self._estimate_tokens(content),
                metadata={
                    'type': 'source_code',
                    'element_name': result.name,
                    'element_type': result.element_type,
                    'file_path': result.file_path,
                    'similarity_score': result.similarity_score
                }
            )
            chunks.append(chunk)

        return chunks

    def select_chunks_within_limit(
        self,
        chunks: List[CodeChunk]
    ) -> List[CodeChunk]:
        """
        Select chunks that fit within token limit, prioritizing by importance.

        Args:
            chunks: List of all available chunks

        Returns:
            List of selected chunks that fit within limit
        """
        # Sort by priority (descending)
        sorted_chunks = sorted(chunks, key=lambda c: c.priority, reverse=True)

        selected = []
        current_tokens = 0

        for chunk in sorted_chunks:
            if current_tokens + chunk.token_estimate <= self.max_tokens:
                selected.append(chunk)
                current_tokens += chunk.token_estimate

                if self.verbose:
                    chunk_type = chunk.metadata.get('type', 'unknown')
                    if chunk_type == 'source_code':
                        elem_name = chunk.metadata.get('element_name', '')
                        print(f"    ✓ Including {elem_name} ({chunk.token_estimate} tokens, priority {chunk.priority})")
                    else:
                        print(f"    ✓ Including {chunk_type} ({chunk.token_estimate} tokens)")
            else:
                if self.verbose:
                    chunk_type = chunk.metadata.get('type', 'unknown')
                    if chunk_type == 'source_code':
                        elem_name = chunk.metadata.get('element_name', '')
                        print(f"    ✗ Skipping {elem_name} (would exceed token limit)")

        if self.verbose:
            print(f"  Selected {len(selected)}/{len(chunks)} chunks ({current_tokens}/{self.max_tokens} tokens)")

        return selected

    def build_final_context(
        self,
        chunks: List[CodeChunk]
    ) -> str:
        """
        Build the final context string from selected chunks.

        Args:
            chunks: Selected chunks

        Returns:
            Formatted context string
        """
        sections = []

        # Group chunks by type
        test_chunks = [c for c in chunks if c.metadata.get('type') == 'test_code']
        error_chunks = [c for c in chunks if c.metadata.get('type') == 'error_message']
        source_chunks = [c for c in chunks if c.metadata.get('type') == 'source_code']

        # Build context sections
        if test_chunks:
            sections.append("## Failing Test Code\n```python\n" + test_chunks[0].content + "\n```")

        if error_chunks:
            sections.append("## Error Information\n```\n" + error_chunks[0].content + "\n```")

        if source_chunks:
            sections.append("## Relevant Source Code")

            # Group by file
            by_file = {}
            for chunk in source_chunks:
                file_path = chunk.metadata.get('file_path', 'unknown')
                if file_path not in by_file:
                    by_file[file_path] = []
                by_file[file_path].append(chunk)

            for file_path, file_chunks in by_file.items():
                sections.append(f"\n### {file_path}")

                for chunk in file_chunks:
                    elem_name = chunk.metadata.get('element_name', '')
                    sections.append(f"\n#### {elem_name}\n```python\n{chunk.content}\n```")

        return "\n\n".join(sections)

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count for text."""
        return len(text) // self.chars_per_token

    def _calculate_priority(self, search_result) -> int:
        """
        Calculate priority for a search result.

        Priority levels:
        - 90-100: Critical (test code, errors, direct matches)
        - 70-89: High (HTTP endpoints, functions in traceback)
        - 50-69: Medium (first-level dependencies)
        - 30-49: Low (second-level dependencies)
        - 0-29: Very low (related code)
        """
        base_priority = 0

        # Similarity score contribution (0-50 points)
        similarity = search_result.similarity_score
        base_priority += int(similarity * 50)

        # Type-based bonus
        if search_result.element_type == 'http_endpoint':
            base_priority += 25
        elif search_result.element_type == 'function':
            base_priority += 20
        elif search_result.element_type == 'class':
            base_priority += 15
        elif search_result.element_type == 'method':
            base_priority += 15
        elif search_result.element_type == 'variable':
            base_priority += 10

        # Cap at 95 (reserve 100 for test/error)
        return min(base_priority, 95)

    def _format_source_code(self, search_result) -> str:
        """Format source code from a search result."""
        # Start with signature if available
        parts = []

        if search_result.signature and search_result.signature != search_result.name:
            parts.append(f"# Signature: {search_result.signature}")

        # Add the source code
        if search_result.source_code:
            parts.append(search_result.source_code)
        else:
            parts.append(f"# {search_result.name} (source code not available)")

        # Add metadata if HTTP endpoint
        if search_result.element_type == 'http_endpoint':
            method = search_result.metadata.get('http_method', '')
            route = search_result.metadata.get('http_route', '')
            parts.insert(0, f"# HTTP Endpoint: {method} {route}")

        return "\n".join(parts)

    def create_chunked_batches(
        self,
        chunks: List[CodeChunk],
        batch_token_limit: Optional[int] = None
    ) -> List[List[CodeChunk]]:
        """
        Create multiple batches if total chunks exceed single request limit.

        Useful for very large contexts that need multiple LLM calls.

        Args:
            chunks: All chunks (sorted by priority)
            batch_token_limit: Token limit per batch (defaults to self.max_tokens)

        Returns:
            List of chunk batches
        """
        if batch_token_limit is None:
            batch_token_limit = self.max_tokens

        batches = []
        current_batch = []
        current_tokens = 0

        # Always include test and error in first batch
        required_chunks = [c for c in chunks if c.priority >= 100]
        optional_chunks = [c for c in chunks if c.priority < 100]

        # Start first batch with required chunks
        for chunk in required_chunks:
            current_batch.append(chunk)
            current_tokens += chunk.token_estimate

        # Fill batches with optional chunks
        for chunk in optional_chunks:
            if current_tokens + chunk.token_estimate <= batch_token_limit:
                current_batch.append(chunk)
                current_tokens += chunk.token_estimate
            else:
                # Start new batch
                if current_batch:
                    batches.append(current_batch)

                current_batch = [chunk]
                current_tokens = chunk.token_estimate

        # Add final batch
        if current_batch:
            batches.append(current_batch)

        if self.verbose and len(batches) > 1:
            print(f"  ℹ Split context into {len(batches)} batches")

        return batches

    def get_summary(self, chunks: List[CodeChunk]) -> Dict:
        """Get summary of chunks."""
        total_tokens = sum(c.token_estimate for c in chunks)

        by_type = {}
        for chunk in chunks:
            chunk_type = chunk.metadata.get('type', 'unknown')
            by_type[chunk_type] = by_type.get(chunk_type, 0) + 1

        return {
            'total_chunks': len(chunks),
            'total_tokens': total_tokens,
            'token_limit': self.max_tokens,
            'utilization': f"{(total_tokens / self.max_tokens * 100):.1f}%",
            'by_type': by_type,
            'fits_in_single_request': total_tokens <= self.max_tokens
        }
