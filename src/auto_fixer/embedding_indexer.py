"""
Embedding-Based Code Indexer

Builds a semantic index of the entire codebase including:
- Functions and their signatures
- Classes and methods
- HTTP endpoints (FastAPI, Flask, Django)
- Variables and constants
- Imports and dependencies
"""

import ast
import os
import json
import hashlib
from typing import Dict, List, Optional, Tuple, Set
from pathlib import Path
from dataclasses import dataclass, asdict
import re

try:
    from openai import AzureOpenAI
except ImportError:
    AzureOpenAI = None


@dataclass
class CodeElement:
    """Represents a code element to be indexed."""
    id: str
    type: str  # 'function', 'class', 'method', 'variable', 'http_endpoint'
    name: str
    file_path: str
    line_start: int
    line_end: int
    signature: str
    docstring: str
    source_code: str
    dependencies: List[str]  # Names of functions/vars this element depends on
    metadata: Dict  # Additional metadata (HTTP method, route, decorators, etc.)

    def to_embedding_text(self) -> str:
        """Convert to text representation for embedding."""
        parts = [
            f"Type: {self.type}",
            f"Name: {self.name}",
            f"File: {self.file_path}",
        ]

        if self.signature:
            parts.append(f"Signature: {self.signature}")

        if self.docstring:
            parts.append(f"Documentation: {self.docstring}")

        # Add HTTP endpoint info if applicable
        if self.type == 'http_endpoint':
            method = self.metadata.get('http_method', '')
            route = self.metadata.get('http_route', '')
            parts.append(f"HTTP: {method} {route}")

        # Add source code (truncated if too long)
        if self.source_code:
            code = self.source_code
            if len(code) > 500:
                code = code[:500] + "\n... (truncated)"
            parts.append(f"Code:\n{code}")

        return "\n".join(parts)


class EmbeddingIndexer:
    """
    Builds a semantic embedding index of the codebase.

    Workflow:
    1. Walk through all Python files
    2. Extract code elements (functions, classes, endpoints)
    3. Generate embeddings for each element
    4. Store in a searchable index
    """

    def __init__(
        self,
        project_root: str = ".",
        cache_dir: str = ".auto_fixer_cache",
        embedding_model: str = "text-embedding-3-small",
        verbose: bool = False
    ):
        """
        Initialize the indexer.

        Args:
            project_root: Root directory of the project
            cache_dir: Directory to store the index cache
            embedding_model: OpenAI embedding model to use
            verbose: Enable verbose logging
        """
        self.project_root = Path(project_root)
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.embedding_model = embedding_model
        self.verbose = verbose

        # Will store all code elements
        self.elements: List[CodeElement] = []

        # Index file path
        self.index_file = self.cache_dir / "code_index.json"
        self.embeddings_file = self.cache_dir / "embeddings.json"

        # OpenAI client (lazy init)
        self._client: Optional[AzureOpenAI] = None

    def get_openai_client(self) -> AzureOpenAI:
        """Get or create OpenAI client."""
        if self._client is None:
            if AzureOpenAI is None:
                raise ImportError("openai package not installed")

            # Import from existing openai_client module
            import sys
            sys.path.insert(0, str(self.project_root / "src"))
            from gen.openai_client import create_client
            self._client = create_client()

        return self._client

    def build_index(
        self,
        exclude_patterns: Optional[List[str]] = None,
        force_rebuild: bool = False
    ) -> Dict:
        """
        Build the embedding index for the entire codebase.

        Args:
            exclude_patterns: List of glob patterns to exclude (e.g., ["tests/*", "*.pyc"])
            force_rebuild: Force rebuild even if cache exists

        Returns:
            Dict with index statistics
        """
        if exclude_patterns is None:
            exclude_patterns = [
                "tests/*",
                "test_*",
                "*_test.py",
                "*.pyc",
                "__pycache__/*",
                ".git/*",
                ".venv/*",
                "venv/*",
                "env/*",
                ".auto_fixer_cache/*"
            ]

        # Check if we can use cached index
        if not force_rebuild and self.index_file.exists():
            if self.verbose:
                print(f"✓ Loading cached index from {self.index_file}")
            self._load_cached_index()
            return {
                'elements': len(self.elements),
                'cached': True
            }

        if self.verbose:
            print(f"🔨 Building code index for {self.project_root}...")

        # Step 1: Walk through all Python files
        python_files = self._find_python_files(exclude_patterns)

        if self.verbose:
            print(f"  Found {len(python_files)} Python files to index")

        # Step 2: Extract code elements from each file
        for file_path in python_files:
            self._extract_elements_from_file(file_path)

        if self.verbose:
            print(f"  Extracted {len(self.elements)} code elements")

        # Step 3: Generate embeddings (with batching for efficiency)
        self._generate_embeddings_batch()

        # Step 4: Save index to disk
        self._save_index()

        if self.verbose:
            print(f"✓ Index built successfully: {len(self.elements)} elements indexed")

        return {
            'elements': len(self.elements),
            'files': len(python_files),
            'cached': False
        }

    def _find_python_files(self, exclude_patterns: List[str]) -> List[Path]:
        """Find all Python files in the project."""
        python_files = []

        for py_file in self.project_root.rglob("*.py"):
            # Check exclusions
            relative_path = py_file.relative_to(self.project_root)
            excluded = False

            for pattern in exclude_patterns:
                if relative_path.match(pattern):
                    excluded = True
                    break

            if not excluded:
                python_files.append(py_file)

        return python_files

    def _extract_elements_from_file(self, file_path: Path):
        """Extract all code elements from a single file."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except (UnicodeDecodeError, IOError) as e:
            if self.verbose:
                print(f"  ⚠ Could not read {file_path}: {e}")
            return

        try:
            tree = ast.parse(content)
        except SyntaxError as e:
            if self.verbose:
                print(f"  ⚠ Syntax error in {file_path}: {e}")
            return

        relative_path = str(file_path.relative_to(self.project_root))

        # Extract top-level elements
        for node in tree.body:
            self._extract_element(node, relative_path, content)

    def _extract_element(self, node: ast.AST, file_path: str, file_content: str):
        """Extract a single code element from an AST node."""
        element_type = None
        name = None
        signature = ""
        docstring = ""
        dependencies = []
        metadata = {}

        # Function definitions
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            element_type = 'function'
            name = node.name
            signature = self._get_function_signature(node)
            docstring = ast.get_docstring(node) or ""
            dependencies = self._extract_dependencies(node)

            # Check for HTTP endpoint decorators
            http_info = self._extract_http_endpoint_info(node)
            if http_info:
                element_type = 'http_endpoint'
                metadata['http_method'] = http_info[0]
                metadata['http_route'] = http_info[1]
                metadata['handler_function'] = name

        # Class definitions
        elif isinstance(node, ast.ClassDef):
            element_type = 'class'
            name = node.name
            signature = f"class {name}"
            docstring = ast.get_docstring(node) or ""

            # Also extract methods from the class
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    method_name = f"{name}.{item.name}"
                    method_sig = self._get_function_signature(item)
                    method_doc = ast.get_docstring(item) or ""
                    method_deps = self._extract_dependencies(item)

                    try:
                        method_code = ast.unparse(item)
                    except:
                        method_code = ""

                    method_element = CodeElement(
                        id=self._generate_id(file_path, method_name),
                        type='method',
                        name=method_name,
                        file_path=file_path,
                        line_start=getattr(item, 'lineno', 0),
                        line_end=getattr(item, 'end_lineno', 0),
                        signature=method_sig,
                        docstring=method_doc,
                        source_code=method_code,
                        dependencies=method_deps,
                        metadata={'class': name}
                    )
                    self.elements.append(method_element)

        # Variable assignments (constants, configurations)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    element_type = 'variable'
                    name = target.id
                    # Only index UPPERCASE variables (constants)
                    if not name.isupper():
                        continue
                    signature = f"{name} = ..."
                    dependencies = self._extract_dependencies(node)

        # Import statements
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            # We'll track imports but not create separate elements
            # Instead, include them in file-level metadata
            return

        if name and element_type:
            # Get source code
            try:
                source_code = ast.unparse(node)
            except:
                source_code = ""

            element = CodeElement(
                id=self._generate_id(file_path, name),
                type=element_type,
                name=name,
                file_path=file_path,
                line_start=getattr(node, 'lineno', 0),
                line_end=getattr(node, 'end_lineno', 0),
                signature=signature,
                docstring=docstring,
                source_code=source_code,
                dependencies=dependencies,
                metadata=metadata
            )

            self.elements.append(element)

    def _get_function_signature(self, node: ast.FunctionDef) -> str:
        """Extract function signature."""
        args = []

        # Regular args
        for arg in node.args.args:
            arg_str = arg.arg
            if arg.annotation:
                try:
                    arg_str += f": {ast.unparse(arg.annotation)}"
                except:
                    pass
            args.append(arg_str)

        # Return annotation
        returns = ""
        if node.returns:
            try:
                returns = f" -> {ast.unparse(node.returns)}"
            except:
                pass

        async_prefix = "async " if isinstance(node, ast.AsyncFunctionDef) else ""
        return f"{async_prefix}def {node.name}({', '.join(args)}){returns}"

    def _extract_dependencies(self, node: ast.AST) -> List[str]:
        """Extract function/variable names that this node depends on."""
        dependencies = []

        for child in ast.walk(node):
            # Function calls
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name):
                    dependencies.append(child.func.id)
                elif isinstance(child.func, ast.Attribute):
                    # obj.method() -> include obj
                    if isinstance(child.func.value, ast.Name):
                        dependencies.append(child.func.value.id)

            # Variable references
            elif isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
                dependencies.append(child.id)

        return list(set(dependencies))  # Remove duplicates

    def _extract_http_endpoint_info(self, node: ast.FunctionDef) -> Optional[Tuple[str, str]]:
        """
        Extract HTTP endpoint info from decorators.

        Returns:
            (method, route) tuple or None
        """
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue

            if not isinstance(decorator.func, ast.Attribute):
                continue

            # Get method name (get, post, put, delete, etc.)
            method_name = decorator.func.attr.lower()
            http_methods = ['get', 'post', 'put', 'delete', 'patch', 'head', 'options']

            if method_name not in http_methods:
                continue

            # Get route path (first argument)
            if not decorator.args:
                continue

            first_arg = decorator.args[0]
            route = None

            if isinstance(first_arg, ast.Constant):
                route = first_arg.value
            elif isinstance(first_arg, ast.Str):
                route = first_arg.s

            if route and isinstance(route, str):
                return (method_name.upper(), route)

        return None

    def _generate_id(self, file_path: str, name: str) -> str:
        """Generate a unique ID for a code element."""
        unique_str = f"{file_path}::{name}"
        return hashlib.md5(unique_str.encode()).hexdigest()[:16]

    def _generate_embeddings_batch(self, batch_size: int = 100):
        """Generate embeddings for all elements in batches."""
        if not self.elements:
            return

        if self.verbose:
            print(f"  Generating embeddings for {len(self.elements)} elements...")

        try:
            client = self.get_openai_client()
        except Exception as e:
            if self.verbose:
                print(f"  ⚠ Could not initialize OpenAI client: {e}")
                print(f"  Indexing without embeddings (will use text-based search)")
            return

        # Process in batches
        for i in range(0, len(self.elements), batch_size):
            batch = self.elements[i:i + batch_size]
            texts = [elem.to_embedding_text() for elem in batch]

            try:
                # Get embeddings from OpenAI
                response = client.embeddings.create(
                    input=texts,
                    model=self.embedding_model
                )

                # Store embeddings in metadata
                for j, embedding_obj in enumerate(response.data):
                    batch[j].metadata['embedding'] = embedding_obj.embedding

                if self.verbose and i % 100 == 0:
                    print(f"    Processed {i + len(batch)}/{len(self.elements)} elements")

            except Exception as e:
                if self.verbose:
                    print(f"  ⚠ Error generating embeddings for batch {i}: {e}")
                # Continue without embeddings for this batch

    def _save_index(self):
        """Save the index to disk."""
        # Convert elements to JSON-serializable format
        elements_data = []
        embeddings_data = []

        for elem in self.elements:
            elem_dict = asdict(elem)

            # Extract embedding separately
            embedding = elem_dict['metadata'].pop('embedding', None)

            elements_data.append(elem_dict)

            if embedding:
                embeddings_data.append({
                    'id': elem.id,
                    'embedding': embedding
                })

        # Save elements
        with open(self.index_file, 'w') as f:
            json.dump({
                'version': '1.0',
                'elements': elements_data
            }, f, indent=2)

        # Save embeddings separately (they're large)
        if embeddings_data:
            with open(self.embeddings_file, 'w') as f:
                json.dump({
                    'version': '1.0',
                    'embeddings': embeddings_data
                }, f)

        if self.verbose:
            print(f"  ✓ Saved index to {self.index_file}")
            if embeddings_data:
                print(f"  ✓ Saved {len(embeddings_data)} embeddings to {self.embeddings_file}")

    def _load_cached_index(self):
        """Load index from cache."""
        try:
            # Load elements
            with open(self.index_file, 'r') as f:
                data = json.load(f)

            # Load embeddings if they exist
            embeddings_map = {}
            if self.embeddings_file.exists():
                with open(self.embeddings_file, 'r') as f:
                    emb_data = json.load(f)
                    for item in emb_data.get('embeddings', []):
                        embeddings_map[item['id']] = item['embedding']

            # Reconstruct elements
            self.elements = []
            for elem_dict in data.get('elements', []):
                # Restore embedding if available
                if elem_dict['id'] in embeddings_map:
                    elem_dict['metadata']['embedding'] = embeddings_map[elem_dict['id']]

                self.elements.append(CodeElement(**elem_dict))

            if self.verbose:
                print(f"  Loaded {len(self.elements)} elements from cache")

        except Exception as e:
            if self.verbose:
                print(f"  ⚠ Could not load cached index: {e}")
            self.elements = []

    def get_statistics(self) -> Dict:
        """Get statistics about the indexed code."""
        stats = {
            'total_elements': len(self.elements),
            'by_type': {},
            'files': set(),
            'http_endpoints': []
        }

        for elem in self.elements:
            stats['by_type'][elem.type] = stats['by_type'].get(elem.type, 0) + 1
            stats['files'].add(elem.file_path)

            if elem.type == 'http_endpoint':
                method = elem.metadata.get('http_method', '')
                route = elem.metadata.get('http_route', '')
                stats['http_endpoints'].append(f"{method} {route}")

        stats['files'] = len(stats['files'])

        return stats
