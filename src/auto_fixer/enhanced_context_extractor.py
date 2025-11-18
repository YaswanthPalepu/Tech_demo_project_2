"""
Enhanced Context Extractor with Embedding Support

Combines AST-based analysis with embedding-based semantic search
to provide the best of both worlds:
- AST: Precise, fast, no API calls
- Embeddings: Semantic understanding, handles misspellings, finds "hidden" code
"""

import ast
import os
import re
from typing import Dict, List, Set, Optional, Tuple
from pathlib import Path

from .embedding_indexer import EmbeddingIndexer
from .embedding_retriever import EmbeddingRetriever, SearchResult
from .code_chunker import CodeChunker


class EnhancedContextExtractor:
    """
    Extracts relevant source code context using hybrid approach:
    1. Try AST-based extraction first (fast, precise)
    2. Fall back to embedding search when AST fails
    3. Use embeddings to find "hidden" dependencies
    4. Recursively resolve dependencies
    5. Smart chunking to fit token limits
    """

    def __init__(
        self,
        project_root: str = ".",
        max_context_tokens: int = 6000,
        use_embeddings: bool = True,
        verbose: bool = False
    ):
        """
        Initialize enhanced extractor.

        Args:
            project_root: Root directory of the project
            max_context_tokens: Maximum tokens for context
            use_embeddings: Enable embedding-based search
            verbose: Enable verbose logging
        """
        self.project_root = Path(project_root)
        self.max_context_tokens = max_context_tokens
        self.use_embeddings = use_embeddings
        self.verbose = verbose

        # Initialize components
        self.indexer: Optional[EmbeddingIndexer] = None
        self.retriever: Optional[EmbeddingRetriever] = None
        self.chunker = CodeChunker(
            max_tokens=max_context_tokens,
            verbose=verbose
        )

        # Initialize embedding index if enabled
        if use_embeddings:
            self._initialize_embedding_index()

    def _initialize_embedding_index(self):
        """Initialize the embedding index (lazy loading)."""
        try:
            if self.verbose:
                print("🔍 Initializing embedding index...")

            self.indexer = EmbeddingIndexer(
                project_root=str(self.project_root),
                verbose=self.verbose
            )

            # Build or load index
            stats = self.indexer.build_index(force_rebuild=False)

            if self.verbose:
                if stats.get('cached'):
                    print(f"  ✓ Loaded cached index: {stats['elements']} elements")
                else:
                    print(f"  ✓ Built new index: {stats['elements']} elements from {stats.get('files', 0)} files")

            # Initialize retriever
            self.retriever = EmbeddingRetriever(
                indexer=self.indexer,
                verbose=self.verbose
            )

        except Exception as e:
            if self.verbose:
                print(f"  ⚠ Could not initialize embeddings: {e}")
                print(f"  Will use AST-only extraction")
            self.use_embeddings = False

    def extract_context(
        self,
        test_file_path: str,
        test_function_name: str,
        error_message: str = "",
        test_code: str = ""
    ) -> Tuple[str, Dict]:
        """
        Extract relevant source code context for a failing test.

        Args:
            test_file_path: Path to the test file
            test_function_name: Name of the failing test function
            error_message: Error message with traceback
            test_code: The failing test code

        Returns:
            Tuple of (context_string, metadata)
        """
        if self.verbose:
            print(f"\n🔎 Extracting context for {test_function_name}...")

        # Step 1: Try AST-based extraction
        ast_results = self._extract_using_ast(
            test_file_path,
            test_function_name,
            error_message
        )

        # Step 2: Try embedding-based extraction
        embedding_results = []
        if self.use_embeddings and self.retriever:
            embedding_results = self._extract_using_embeddings(
                test_file_path,
                test_function_name,
                error_message,
                test_code
            )

        # Step 3: Merge results
        all_results = self._merge_results(ast_results, embedding_results)

        # Step 4: Resolve dependencies recursively
        if self.use_embeddings and self.retriever and all_results:
            all_results = self._resolve_dependencies(all_results)

        # Step 5: Create chunks
        chunks = self.chunker.chunk_context(
            search_results=all_results,
            test_code=test_code,
            error_message=error_message
        )

        # Step 6: Select chunks within limit
        selected_chunks = self.chunker.select_chunks_within_limit(chunks)

        # Step 7: Build final context
        context_string = self.chunker.build_final_context(selected_chunks)

        # Metadata
        metadata = {
            'method': 'hybrid' if (ast_results and embedding_results) else ('ast' if ast_results else 'embedding'),
            'total_results': len(all_results),
            'selected_chunks': len(selected_chunks),
            'chunk_summary': self.chunker.get_summary(selected_chunks)
        }

        if self.verbose:
            print(f"  ✓ Extracted context: {len(all_results)} elements, {len(selected_chunks)} chunks")
            print(f"  Method: {metadata['method']}")

        return context_string, metadata

    def _extract_using_ast(
        self,
        test_file_path: str,
        test_function_name: str,
        error_message: str
    ) -> List[SearchResult]:
        """
        Extract context using AST analysis.

        Returns:
            List of SearchResult objects (converted from AST findings)
        """
        results = []

        try:
            # Read test file
            with open(test_file_path, 'r') as f:
                test_content = f.read()
                tree = ast.parse(test_content)

            # Extract imports
            imports = self._extract_imports(tree)

            # Find test function
            test_func_code = self._extract_test_function(tree, test_function_name)

            # Determine which imports are used in test
            used_imports = self._get_used_imports(test_func_code, imports)

            # Resolve imports to files
            source_files = self._resolve_imports_to_files(used_imports)

            if self.verbose and source_files:
                print(f"  AST: Found {len(source_files)} source file(s)")

            # Extract code from each source file
            for source_file in source_files:
                file_results = self._extract_from_file(source_file)
                results.extend(file_results)

        except Exception as e:
            if self.verbose:
                print(f"  ⚠ AST extraction failed: {e}")

        return results

    def _extract_using_embeddings(
        self,
        test_file_path: str,
        test_function_name: str,
        error_message: str,
        test_code: str
    ) -> List[SearchResult]:
        """Extract context using embedding-based search."""
        if not self.retriever:
            return []

        results = []

        try:
            # Strategy 1: Search by error traceback
            if error_message:
                traceback_results = self.retriever.search_by_error_traceback(
                    error_message=error_message
                )
                results.extend(traceback_results)

                if self.verbose and traceback_results:
                    print(f"  Embeddings (traceback): Found {len(traceback_results)} element(s)")

            # Strategy 2: Search by HTTP endpoints (if test makes HTTP calls)
            http_endpoints = self._extract_http_calls(test_code)
            for method, route in http_endpoints:
                endpoint_result = self.retriever.search_by_http_endpoint(method, route)
                if endpoint_result:
                    results.append(endpoint_result)

            if self.verbose and http_endpoints:
                print(f"  Embeddings (HTTP): Found {len([r for r in results if r.element_type == 'http_endpoint'])} endpoint(s)")

            # Strategy 3: General semantic search
            if test_code:
                # Build query from test code
                query = self._build_search_query(test_code, error_message)
                general_results = self.retriever.search(
                    query=query,
                    top_k=10,
                    min_similarity=0.6
                )
                results.extend(general_results)

                if self.verbose and general_results:
                    print(f"  Embeddings (semantic): Found {len(general_results)} element(s)")

        except Exception as e:
            if self.verbose:
                print(f"  ⚠ Embedding extraction failed: {e}")

        return results

    def _merge_results(
        self,
        ast_results: List[SearchResult],
        embedding_results: List[SearchResult]
    ) -> List[SearchResult]:
        """
        Merge AST and embedding results, removing duplicates.

        Prioritize AST results (they're more precise).
        """
        # Index by name to detect duplicates
        seen = {}

        for result in ast_results:
            seen[result.name] = result

        for result in embedding_results:
            if result.name not in seen:
                seen[result.name] = result

        return list(seen.values())

    def _resolve_dependencies(
        self,
        results: List[SearchResult],
        max_depth: int = 2
    ) -> List[SearchResult]:
        """Recursively resolve dependencies of found elements."""
        if not self.retriever:
            return results

        # Extract all element names
        element_names = [r.name for r in results]

        # Resolve dependencies
        dep_results = self.retriever.resolve_dependencies_recursive(
            element_names=element_names,
            max_depth=max_depth
        )

        # Merge
        all_results = self._merge_results(results, dep_results)

        if self.verbose and len(dep_results) > len(results):
            print(f"  Dependencies: Added {len(dep_results) - len(results)} transitive dependencies")

        return all_results

    def _extract_imports(self, tree: ast.AST) -> Dict[str, str]:
        """Extract imports from AST."""
        imports = {}

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.asname or alias.name
                    imports[name] = alias.name

            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    name = alias.asname or alias.name
                    full_path = f"{module}.{alias.name}" if module else alias.name
                    imports[name] = full_path

        return imports

    def _extract_test_function(self, tree: ast.AST, func_name: str) -> str:
        """Extract test function code."""
        base_func_name = func_name.split('[')[0] if '[' in func_name else func_name

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == base_func_name:
                try:
                    return ast.unparse(node)
                except:
                    return ""

        return ""

    def _get_used_imports(self, function_code: str, all_imports: Dict[str, str]) -> Set[str]:
        """Identify which imports are used in function."""
        used = set()

        for name, module_path in all_imports.items():
            if name in function_code:
                used.add(module_path)

        return used

    def _resolve_imports_to_files(self, imports: Set[str]) -> List[str]:
        """Resolve import paths to actual files."""
        files = []

        for import_path in imports:
            # Skip stdlib and third-party
            if self._is_stdlib_or_third_party(import_path):
                continue

            file_path = self._module_to_file(import_path)
            if file_path and os.path.exists(file_path):
                files.append(file_path)

        return files

    def _is_stdlib_or_third_party(self, module_path: str) -> bool:
        """Check if module is stdlib or third-party."""
        stdlib = {'os', 'sys', 'json', 'ast', 're', 'typing', 'pathlib', 'unittest', 'pytest'}
        third_party = ['django', 'flask', 'fastapi', 'pydantic', 'requests', 'httpx']

        top_level = module_path.split('.')[0]

        if top_level in stdlib:
            return True

        for prefix in third_party:
            if module_path.startswith(prefix):
                return True

        return False

    def _module_to_file(self, module_path: str) -> Optional[str]:
        """Convert module path to file path."""
        variations = [
            module_path.replace('.', '/') + '.py',
            module_path.replace('.', '/') + '/__init__.py',
        ]

        for var in variations:
            full_path = self.project_root / var
            if full_path.exists():
                return str(full_path)

        return None

    def _extract_from_file(self, file_path: str) -> List[SearchResult]:
        """Extract code elements from a file (AST-based)."""
        results = []

        try:
            with open(file_path, 'r') as f:
                content = f.read()
                tree = ast.parse(content)

            for node in tree.body:
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    try:
                        source_code = ast.unparse(node)
                        signature = self._get_signature(node)

                        result = SearchResult(
                            element_id=f"{file_path}::{node.name}",
                            element_type='function' if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else 'class',
                            name=node.name,
                            file_path=file_path,
                            line_start=getattr(node, 'lineno', 0),
                            line_end=getattr(node, 'end_lineno', 0),
                            signature=signature,
                            source_code=source_code,
                            similarity_score=0.8,  # AST results get high score
                            dependencies=[],
                            metadata={}
                        )
                        results.append(result)

                    except:
                        continue

        except:
            pass

        return results

    def _get_signature(self, node: ast.AST) -> str:
        """Get signature of function/class."""
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            args = ', '.join(arg.arg for arg in node.args.args)
            async_prefix = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
            return f"{async_prefix}def {node.name}({args})"
        elif isinstance(node, ast.ClassDef):
            return f"class {node.name}"
        return ""

    def _extract_http_calls(self, test_code: str) -> List[Tuple[str, str]]:
        """Extract HTTP calls from test code."""
        endpoints = []
        http_methods = ['get', 'post', 'put', 'delete', 'patch']

        for method in http_methods:
            pattern = rf'client\.{method}\s*\(\s*["\']([^"\']+)["\']'
            matches = re.findall(pattern, test_code, re.IGNORECASE)

            for endpoint in matches:
                endpoints.append((method.upper(), endpoint))

        return endpoints

    def _build_search_query(self, test_code: str, error_message: str) -> str:
        """Build semantic search query from test code and error."""
        # Extract key terms from test code
        test_words = re.findall(r'\w+', test_code.lower())

        # Extract function names (likely relevant)
        func_pattern = r'def (test_\w+)'
        func_names = re.findall(func_pattern, test_code)

        # Extract error type
        error_type = ""
        if error_message:
            error_lines = error_message.split('\n')
            if error_lines:
                last_line = error_lines[-1]
                error_type = last_line.split(':')[0] if ':' in last_line else ""

        # Build query
        query_parts = []

        if func_names:
            query_parts.append(func_names[0].replace('test_', ''))

        if error_type:
            query_parts.append(error_type)

        # Add some frequent words (excluding common ones)
        common_words = {'test', 'assert', 'import', 'from', 'def', 'return', 'true', 'false', 'none'}
        frequent = [w for w in set(test_words) if w not in common_words and len(w) > 3]

        query_parts.extend(frequent[:5])

        return ' '.join(query_parts)

    def detect_source_not_found(
        self,
        test_file_path: str,
        test_code: str,
        error_message: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Detect if source code could not be found.

        Returns:
            (is_not_found, reason) tuple
        """
        # Try extraction
        context, metadata = self.extract_context(
            test_file_path=test_file_path,
            test_function_name="temp",
            error_message=error_message,
            test_code=test_code
        )

        # Check if we got meaningful results
        total_results = metadata.get('total_results', 0)

        if total_results == 0:
            return True, "No source code found matching test imports or error traceback"

        if metadata.get('method') == 'embedding' and total_results < 3:
            return True, "Very few source elements found (AST failed, embeddings found minimal matches)"

        return False, None

    def get_statistics(self) -> Dict:
        """Get statistics about the extractor."""
        stats = {
            'embeddings_enabled': self.use_embeddings,
            'max_context_tokens': self.max_context_tokens,
        }

        if self.use_embeddings and self.indexer:
            stats['index_stats'] = self.indexer.get_statistics()

        if self.retriever:
            stats['retrieval_stats'] = self.retriever.get_statistics()

        return stats
