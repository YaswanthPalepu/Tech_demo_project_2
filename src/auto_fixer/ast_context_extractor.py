"""
AST Context Extractor

Extracts relevant source code context based on test imports.
"""

import ast
import os
from typing import Dict, List, Set, Optional
from pathlib import Path


class ASTContextExtractor:
    """
    Extracts relevant source code based on test file imports.

    Analyzes test imports and extracts:
    - Classes
    - Functions
    - Routes
    - Models
    - Utils
    """

    def __init__(self, project_root: str = "."):
        self.project_root = Path(project_root)

    def extract_context(
        self,
        test_file_path: str,
        test_function_name: str
    ) -> Dict[str, str]:
        """
        Extract relevant source code context for a failing test.

        Args:
            test_file_path: Path to the test file
            test_function_name: Name of the failing test function

        Returns:
            Dictionary mapping source file paths to their relevant code
        """
        # Read test file
        try:
            with open(test_file_path, 'r') as f:
                test_content = f.read()
        except FileNotFoundError:
            return {}

        # Parse test file AST
        try:
            tree = ast.parse(test_content)
        except SyntaxError:
            return {}

        # Extract imports from test file
        imports = self._extract_imports(tree)

        # Extract the specific test function code
        test_func_code = self._extract_test_function(tree, test_function_name)

        # Analyze imports used in the test function
        test_imports = self._get_function_imports(test_func_code, imports)

        # Resolve import paths to actual files
        source_files = self._resolve_imports_to_files(test_imports)

        # Extract relevant code from each source file
        context = {}
        for source_file in source_files:
            code = self._extract_relevant_code(source_file, test_imports)
            if code:
                context[source_file] = code

        return context

    def _extract_imports(self, tree: ast.AST) -> Dict[str, str]:
        """
        Extract all imports from the AST.

        Args:
            tree: AST tree

        Returns:
            Dictionary mapping import names to module paths
        """
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
        """
        Extract the source code of a specific test function.

        Args:
            tree: AST tree
            func_name: Function name to extract (may include parameters like "test_foo[param]")

        Returns:
            Source code of the function
        """
        # Strip parameter suffix for parameterized tests
        # e.g., "test_foo[param]" → "test_foo"
        base_func_name = func_name.split('[')[0] if '[' in func_name else func_name

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == base_func_name:
                return ast.unparse(node)

        return ""

    def _get_function_imports(
        self,
        function_code: str,
        all_imports: Dict[str, str]
    ) -> Set[str]:
        """
        Identify which imports are used in a specific function.

        Args:
            function_code: Source code of the function
            all_imports: All available imports

        Returns:
            Set of module paths used in the function
        """
        used_imports = set()

        for name, module_path in all_imports.items():
            # Check if the import name is used in the function code
            if name in function_code:
                used_imports.add(module_path)

        return used_imports

    def _resolve_imports_to_files(self, imports: Set[str]) -> List[str]:
        """
        Resolve import module paths to actual file paths.

        Args:
            imports: Set of module paths

        Returns:
            List of resolved file paths
        """
        files = []

        for import_path in imports:
            # Skip standard library and third-party imports
            if self._is_stdlib_or_third_party(import_path):
                continue

            # Convert module path to file path
            file_path = self._module_to_file(import_path)

            if file_path and os.path.exists(file_path):
                files.append(file_path)

        return files

    def _is_stdlib_or_third_party(self, module_path: str) -> bool:
        """
        Check if a module is from stdlib or third-party.

        Args:
            module_path: Module path (e.g., "os.path" or "django.db")

        Returns:
            True if stdlib or third-party
        """
        # Common stdlib modules
        stdlib_modules = {
            'os', 'sys', 'json', 'ast', 're', 'typing', 'pathlib',
            'collections', 'itertools', 'functools', 'datetime',
            'unittest', 'pytest', 'asyncio'
        }

        # Common third-party frameworks
        third_party_prefixes = [
            'django', 'flask', 'fastapi', 'pydantic', 'sqlalchemy',
            'requests', 'httpx', 'pytest', 'unittest', 'mock'
        ]

        # Check top-level module
        top_level = module_path.split('.')[0]

        if top_level in stdlib_modules:
            return True

        for prefix in third_party_prefixes:
            if module_path.startswith(prefix):
                return True

        return False

    def _module_to_file(self, module_path: str) -> Optional[str]:
        """
        Convert module path to file path.

        Args:
            module_path: Module path (e.g., "src.models.user")

        Returns:
            File path or None
        """
        # Try different variations
        variations = [
            # Direct path: src.models.user -> src/models/user.py
            module_path.replace('.', '/') + '.py',
            # Package path: src.models.user -> src/models/user/__init__.py
            module_path.replace('.', '/') + '/__init__.py',
            # Without first component: models.user -> models/user.py
            '/'.join(module_path.split('.')[1:]) + '.py',
        ]

        for var in variations:
            full_path = self.project_root / var
            if full_path.exists():
                return str(full_path)

        return None

    def _extract_relevant_code(
        self,
        source_file: str,
        imports: Set[str]
    ) -> str:
        """
        Extract relevant code elements from a source file.

        Args:
            source_file: Path to source file
            imports: Import paths that reference this file

        Returns:
            Concatenated relevant code
        """
        try:
            with open(source_file, 'r') as f:
                content = f.read()
        except (FileNotFoundError, IOError):
            return ""

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return content  # Return raw content if parsing fails

        # Extract all top-level definitions
        relevant_code = []

        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Include function definitions
                relevant_code.append(ast.unparse(node))

            elif isinstance(node, ast.ClassDef):
                # Include class definitions
                relevant_code.append(ast.unparse(node))

            elif isinstance(node, ast.Assign):
                # Include important assignments (constants, configs)
                relevant_code.append(ast.unparse(node))

        return "\n\n".join(relevant_code) if relevant_code else content

    def get_full_context_string(
        self,
        test_file_path: str,
        test_function_name: str
    ) -> str:
        """
        Get a formatted string with all relevant context.

        Args:
            test_file_path: Path to test file
            test_function_name: Name of failing test

        Returns:
            Formatted context string
        """
        context = self.extract_context(test_file_path, test_function_name)

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
