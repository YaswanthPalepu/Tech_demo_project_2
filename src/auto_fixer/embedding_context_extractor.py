"""
Embedding-Enhanced Context Extractor

Hybrid approach that combines:
1. AST-based extraction (fast, precise when it works)
2. Embedding-based retrieval (robust, handles edge cases)

This provides the best of both worlds:
- Uses AST extraction as primary method
- Falls back to embedding search when AST fails
- Validates AST results with embeddings
- Handles all the edge cases AST can't

What this solves:
✓ Target function not found → embedding search finds it
✓ Wrong import paths → semantic search doesn't care
✓ Misspelled names → fuzzy matching finds them
✓ Token limit exceeded → embedding returns only relevant code
✓ Dynamic routes → HTTP endpoint search finds them
✓ Missing source files → comprehensive indexing finds them
"""

import os
from typing import Dict, List, Optional
from pathlib import Path

from .ast_context_extractor import ASTContextExtractor
from .codebase_indexer import CodebaseIndexer
from .semantic_code_retriever import SemanticCodeRetriever


class EmbeddingContextExtractor:
    """
    Hybrid context extractor using both AST and embeddings.

    Workflow:
    1. Try AST-based extraction first (fast)
    2. If AST finds nothing, use embedding search
    3. Validate AST results with embeddings
    4. Combine results intelligently
    """

    def __init__(
        self,
        project_root: str = ".",
        max_source_lines: int = 300,
        use_embeddings: bool = True,
        verbose: bool = False
    ):
        self.project_root = Path(project_root)
        self.max_source_lines = max_source_lines
        self.use_embeddings = use_embeddings
        self.verbose = verbose

        # Initialize AST extractor (always available)
        self.ast_extractor = ASTContextExtractor(
            project_root=str(project_root),
            verbose=verbose
        )

        # Initialize embedding components (lazy load)
        self._indexer = None
        self._retriever = None

        # Control flag from environment
        if os.getenv("DISABLE_EMBEDDINGS", "").lower() in ("true", "1", "yes"):
            self.use_embeddings = False
            if self.verbose:
                print("  ℹ️  Embeddings disabled via DISABLE_EMBEDDINGS env var")

    @property
    def indexer(self) -> Optional[CodebaseIndexer]:
        """Lazy-load codebase indexer."""
        if not self.use_embeddings:
            return None

        if self._indexer is None:
            try:
                self._indexer = CodebaseIndexer(
                    project_root=str(self.project_root),
                    verbose=self.verbose
                )
                # Build or load index
                self._indexer.build_index()
            except Exception as e:
                if self.verbose:
                    print(f"  ⚠️  Could not initialize indexer: {e}")
                self._indexer = None

        return self._indexer

    @property
    def retriever(self) -> Optional[SemanticCodeRetriever]:
        """Lazy-load semantic retriever."""
        if not self.use_embeddings or self.indexer is None:
            return None

        if self._retriever is None:
            self._retriever = SemanticCodeRetriever(
                indexer=self.indexer,
                verbose=self.verbose
            )

        return self._retriever

    def extract_context(
        self,
        test_file_path: str,
        test_function_name: str,
        error_message: str = ""
    ) -> Dict[str, str]:
        """
        Extract relevant source code context for a failing test.

        Hybrid approach:
        1. Try AST extraction
        2. If empty or insufficient, try embedding search
        3. Validate and combine results

        Args:
            test_file_path: Path to test file
            test_function_name: Name of failing test
            error_message: Error message with traceback

        Returns:
            Dict mapping file paths to code context
        """
        if self.verbose:
            print(f"\n  🔍 Extracting context for {test_function_name}")

        # Step 1: Try AST extraction
        ast_context = self.ast_extractor.extract_context(
            test_file_path,
            test_function_name,
            error_message
        )

        # If AST extraction succeeded and embeddings disabled, return
        if ast_context and not self.use_embeddings:
            return ast_context

        # Step 2: Use embeddings if needed
        if self.use_embeddings and self.retriever:
            # Get embedding-based context
            embedding_context = self._extract_with_embeddings(
                test_file_path,
                test_function_name,
                error_message
            )

            # Combine AST and embedding results
            combined_context = self._combine_contexts(
                ast_context,
                embedding_context
            )

            if self.verbose:
                ast_files = len(ast_context)
                embed_files = len(embedding_context)
                combined_files = len(combined_context)
                print(f"  📊 Context extraction results:")
                print(f"     AST: {ast_files} files")
                print(f"     Embeddings: {embed_files} files")
                print(f"     Combined: {combined_files} files")

            return combined_context

        # Fallback: return AST results (might be empty)
        return ast_context

    def _extract_with_embeddings(
        self,
        test_file_path: str,
        test_function_name: str,
        error_message: str
    ) -> Dict[str, str]:
        """
        Extract context using embedding-based semantic search.

        Args:
            test_file_path: Path to test file
            test_function_name: Test function name
            error_message: Error message

        Returns:
            Dict mapping file paths to code
        """
        if not self.retriever:
            return {}

        # Read test code
        try:
            with open(test_file_path, 'r') as f:
                test_content = f.read()

            # Extract the specific test function
            import ast
            tree = ast.parse(test_content)
            base_test_name = test_function_name.split('[')[0]
            test_code = ""

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.name == base_test_name:
                        test_code = ast.unparse(node)
                        break

            if not test_code:
                test_code = test_content  # Fallback

        except Exception as e:
            if self.verbose:
                print(f"    ⚠️  Could not read test file: {e}")
            test_code = ""

        # Perform semantic search
        results = self.retriever.search_by_test_failure(
            test_code=test_code,
            error_message=error_message,
            traceback=error_message,  # Traceback is part of error message
            top_k=10
        )

        if self.verbose and results:
            print(f"    🔍 Embedding search found {len(results)} matches:")
            for result in results[:3]:
                print(f"       {result.rank}. {result.code_element.name} ({result.code_element.element_type}) - score: {result.similarity_score:.3f}")

        # Build context from results
        context = {}
        current_lines = 0

        for result in results:
            elem = result.code_element
            file_path = elem.file_path

            # Check line limit
            code_lines = elem.source_code.count('\n') + 1
            if current_lines + code_lines > self.max_source_lines:
                break

            # Add to context
            if file_path not in context:
                context[file_path] = []

            context[file_path].append({
                'name': elem.name,
                'type': elem.element_type,
                'code': elem.source_code,
                'line_start': elem.line_start
            })

            current_lines += code_lines

        # Format context as strings
        formatted_context = {}
        for file_path, elements in context.items():
            # Sort by line number
            elements.sort(key=lambda x: x['line_start'])

            # Combine code
            code_parts = []
            for elem in elements:
                code_parts.append(f"# {elem['type']}: {elem['name']} (line {elem['line_start']})")
                code_parts.append(elem['code'])
                code_parts.append("")

            formatted_context[file_path] = '\n'.join(code_parts)

        return formatted_context

    def _combine_contexts(
        self,
        ast_context: Dict[str, str],
        embedding_context: Dict[str, str]
    ) -> Dict[str, str]:
        """
        Intelligently combine AST and embedding contexts.

        Strategy:
        - If AST found files, use AST (more precise)
        - Add embedding results for files AST missed
        - Prefer AST when both found same file

        Args:
            ast_context: Context from AST extraction
            embedding_context: Context from embedding search

        Returns:
            Combined context dict
        """
        combined = {}

        # Start with AST results (more precise when they work)
        combined.update(ast_context)

        # Add embedding results for files AST didn't find
        for file_path, code in embedding_context.items():
            if file_path not in combined:
                combined[file_path] = code

        return combined

    def get_full_context_string(
        self,
        test_file_path: str,
        test_function_name: str,
        error_message: str = ""
    ) -> str:
        """
        Get formatted context string for LLM.

        Args:
            test_file_path: Path to test file
            test_function_name: Test function name
            error_message: Error message

        Returns:
            Formatted context string
        """
        context = self.extract_context(
            test_file_path,
            test_function_name,
            error_message
        )

        if not context:
            return "# No relevant source code found"

        output = []
        for file_path, code in context.items():
            output.append(f"# {file_path}")
            output.append(f"```python")
            output.append(code)
            output.append(f"```")
            output.append("")

        return "\n".join(output)

    def verify_extraction_quality(
        self,
        test_file_path: str,
        test_function_name: str,
        error_message: str
    ) -> Dict[str, any]:
        """
        Verify quality of context extraction.

        Compares AST and embedding results to detect issues.

        Args:
            test_file_path: Path to test file
            test_function_name: Test function name
            error_message: Error message

        Returns:
            Dict with quality metrics
        """
        # Extract with both methods
        ast_context = self.ast_extractor.extract_context(
            test_file_path,
            test_function_name,
            error_message
        )

        embedding_context = {}
        if self.use_embeddings and self.retriever:
            embedding_context = self._extract_with_embeddings(
                test_file_path,
                test_function_name,
                error_message
            )

        # Calculate metrics
        ast_files = set(ast_context.keys())
        embedding_files = set(embedding_context.keys())

        metrics = {
            'ast_file_count': len(ast_files),
            'embedding_file_count': len(embedding_files),
            'overlap_count': len(ast_files & embedding_files),
            'ast_only': list(ast_files - embedding_files),
            'embedding_only': list(embedding_files - ast_files),
            'extraction_quality': 'good' if ast_context else 'failed'
        }

        # If AST found nothing but embeddings found something
        if not ast_context and embedding_context:
            metrics['extraction_quality'] = 'ast_failed_embedding_saved'

        # If both found different files
        if ast_files and embedding_files and not (ast_files & embedding_files):
            metrics['extraction_quality'] = 'divergent_results'

        return metrics
