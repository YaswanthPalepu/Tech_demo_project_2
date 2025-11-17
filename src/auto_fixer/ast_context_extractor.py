"""
AST Context Extractor

Extracts relevant source code context based on test imports.
"""

import ast
import os
import re
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

    Advanced features:
    - Targeted extraction (finds functions at any line number)
    - Recursive dependency resolution
    - Error traceback parsing
    - Smart caching for performance
    """

    def __init__(self, project_root: str = ".", verbose: bool = False):
        self.project_root = Path(project_root)
        self.verbose = verbose
        # Max lines to extract from a single source file (prevent token overflow)
        # REDUCED from 300 to 200 to prevent token overflow with error messages
        self.max_source_lines = 200
        # Cache for source maps (performance optimization)
        self._source_map_cache = {}

    def extract_context(
        self,
        test_file_path: str,
        test_function_name: str,
        error_message: str = ""
    ) -> Dict[str, str]:
        """
        Extract relevant source code context for a failing test.

        Args:
            test_file_path: Path to the test file
            test_function_name: Name of the failing test function
            error_message: Error message with traceback (for targeted extraction)

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
            # Use targeted extraction if error message provided, otherwise fallback
            if error_message:
                code = self._extract_relevant_code_targeted(
                    source_file=source_file,
                    test_file=test_file_path,
                    error_message=error_message,
                    max_lines=self.max_source_lines
                )
            else:
                code = self._extract_relevant_code(source_file, test_imports)

            if code:
                context[source_file] = code

        if self.verbose:
            if context:
                print(f"  ✓ Extracted context from {len(context)} source file(s)")
            else:
                print(f"  ⚠ No source code context found")
                print(f"    Imports detected: {list(imports.keys())[:5]}")
                print(f"    Used in test: {list(test_imports)[:5]}")

        return context

    def _extract_imports(self, tree: ast.AST) -> Dict[str, str]:
        """
        Extract all imports from the AST, including string-based references in patch/monkeypatch.

        Args:
            tree: AST tree

        Returns:
            Dictionary mapping import names to module paths
        """
        imports = {}

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    # import app.main as app_main
                    name = alias.asname or alias.name
                    imports[name] = alias.name

                    # Also add the base module path for matching
                    # e.g., "app.main" should match both "app_main" and "app.main"
                    if alias.asname and '.' in alias.name:
                        # Add intermediate paths for multi-part imports
                        parts = alias.name.split('.')
                        for i in range(len(parts)):
                            partial = '.'.join(parts[:i+1])
                            imports[partial] = partial

            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for alias in node.names:
                    name = alias.asname or alias.name
                    full_path = f"{module}.{alias.name}" if module else alias.name
                    imports[name] = full_path

                    # Also add the module itself
                    if module:
                        imports[module] = module

            # NEW: Detect string-based imports in patch() and monkeypatch calls
            elif isinstance(node, ast.Call):
                # Check for unittest.mock.patch('app.main.model')
                if isinstance(node.func, ast.Attribute) and node.func.attr == 'patch':
                    if node.args and isinstance(node.args[0], (ast.Constant, ast.Str)):
                        # Extract the string argument
                        patch_target = node.args[0].value if isinstance(node.args[0], ast.Constant) else node.args[0].s
                        if isinstance(patch_target, str) and '.' in patch_target:
                            # 'app.main.model' -> extract 'app.main'
                            parts = patch_target.split('.')
                            # Add the module path (everything except the last part)
                            if len(parts) >= 2:
                                module = '.'.join(parts[:-1])
                                imports[module] = module
                                if self.verbose:
                                    print(f"    Detected patch target: '{patch_target}' → importing '{module}'")

                # Check for monkeypatch.setattr('app.main.model', ...)
                elif isinstance(node.func, ast.Attribute) and node.func.attr == 'setattr':
                    if node.args and isinstance(node.args[0], (ast.Constant, ast.Str)):
                        # Extract the string argument
                        setattr_target = node.args[0].value if isinstance(node.args[0], ast.Constant) else node.args[0].s
                        if isinstance(setattr_target, str) and '.' in setattr_target:
                            # 'app.main.model' -> extract 'app.main'
                            parts = setattr_target.split('.')
                            if len(parts) >= 2:
                                module = '.'.join(parts[:-1])
                                imports[module] = module
                                if self.verbose:
                                    print(f"    Detected monkeypatch target: '{setattr_target}' → importing '{module}'")

                # Check for dynamic import helpers: pytest.importorskip("app.main"), safe_import("app.main"), try_import("app.main")
                elif isinstance(node.func, ast.Attribute):
                    # pytest.importorskip("app.main")
                    if node.func.attr == 'importorskip':
                        if node.args and isinstance(node.args[0], (ast.Constant, ast.Str)):
                            module_path = node.args[0].value if isinstance(node.args[0], ast.Constant) else node.args[0].s
                            if isinstance(module_path, str):
                                imports[module_path] = module_path
                                if self.verbose:
                                    print(f"    Detected pytest.importorskip('{module_path}') → importing '{module_path}'")

                # Check for function-based dynamic imports: safe_import("app.main"), try_import("app.main")
                elif isinstance(node.func, ast.Name):
                    if node.func.id in ('safe_import', 'try_import', 'importorskip'):
                        if node.args and isinstance(node.args[0], (ast.Constant, ast.Str)):
                            module_path = node.args[0].value if isinstance(node.args[0], ast.Constant) else node.args[0].s
                            if isinstance(module_path, str):
                                imports[module_path] = module_path
                                if self.verbose:
                                    print(f"    Detected {node.func.id}('{module_path}') → importing '{module_path}'")

            # Also check for patch() used as decorator
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Call):
                        # @patch('app.main.model')
                        if isinstance(decorator.func, ast.Name) and decorator.func.id == 'patch':
                            if decorator.args and isinstance(decorator.args[0], (ast.Constant, ast.Str)):
                                patch_target = decorator.args[0].value if isinstance(decorator.args[0], ast.Constant) else decorator.args[0].s
                                if isinstance(patch_target, str) and '.' in patch_target:
                                    parts = patch_target.split('.')
                                    if len(parts) >= 2:
                                        module = '.'.join(parts[:-1])
                                        imports[module] = module
                                        if self.verbose:
                                            print(f"    Detected patch decorator: '@patch({patch_target})' → importing '{module}'")

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
        parts = module_path.split('.')

        # Try different variations
        variations = []

        # 1. Direct path: src.models.user -> src/models/user.py
        variations.append(module_path.replace('.', '/') + '.py')

        # 2. Package path: src.models.user -> src/models/user/__init__.py
        variations.append(module_path.replace('.', '/') + '/__init__.py')

        # 3. Without first component: models.user -> models/user.py
        if len(parts) > 1:
            variations.append('/'.join(parts[1:]) + '.py')

        # 4. Single file at root: app.main -> main.py or app.py
        if len(parts) >= 2:
            variations.append(parts[-1] + '.py')  # Last component
            variations.append(parts[0] + '.py')   # First component
        elif len(parts) == 1:
            variations.append(parts[0] + '.py')

        # 5. Common Python app structures
        if len(parts) >= 2:
            # app.something -> app/something.py
            variations.append(f"{parts[0]}/{'/'.join(parts[1:])}.py")
            # something.else -> src/something/else.py
            variations.append(f"src/{module_path.replace('.', '/')}.py")

        # 6. Single file patterns for common entry points
        common_files = ['main.py', 'app.py', 'server.py', 'api.py', '__init__.py']
        variations.extend(common_files)
        variations.extend([f"app/{f}" for f in common_files])
        variations.extend([f"src/{f}" for f in common_files])

        if self.verbose:
            print(f"    Trying to resolve module '{module_path}'...")

        # Try each variation
        for var in variations:
            full_path = self.project_root / var
            if full_path.exists():
                if self.verbose:
                    print(f"      ✓ Found: {full_path}")
                return str(full_path)

        if self.verbose:
            print(f"      ✗ Not found (tried {len(variations)} variations)")

        return None

    def _extract_relevant_code(
        self,
        source_file: str,
        imports: Set[str]
    ) -> str:
        """
        Extract relevant code elements from a source file.

        Intelligently limits extraction to avoid token overflow.

        Args:
            source_file: Path to source file
            imports: Import paths that reference this file

        Returns:
            Concatenated relevant code (limited to max_source_lines)
        """
        try:
            with open(source_file, 'r') as f:
                content = f.read()
        except (FileNotFoundError, IOError):
            return ""

        lines = content.split('\n')

        # If file is small enough, return all content
        if len(lines) <= self.max_source_lines:
            return content

        # File too large - extract intelligently
        if self.verbose:
            print(f"    ⚠ File too large ({len(lines)} lines), extracting relevant parts only...")

        try:
            tree = ast.parse(content)
        except SyntaxError:
            # If parsing fails, return truncated raw content
            truncated = '\n'.join(lines[:self.max_source_lines])
            return truncated + f"\n\n# ... (file truncated: {len(lines)} total lines)"

        # Extract definitions with size tracking
        extracted_items = []
        current_lines = 0

        # Priority 1: Extract imports and constants (usually at top)
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom, ast.Assign)):
                code = ast.unparse(node)
                item_lines = len(code.split('\n'))
                if current_lines + item_lines <= self.max_source_lines:
                    extracted_items.append(code)
                    current_lines += item_lines

        # Priority 2: Extract functions and classes (up to limit)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                code = ast.unparse(node)
                item_lines = len(code.split('\n'))

                # If adding this would exceed limit, skip
                if current_lines + item_lines > self.max_source_lines:
                    continue

                extracted_items.append(code)
                current_lines += item_lines

        result = "\n\n".join(extracted_items) if extracted_items else ""

        # Add truncation notice
        if current_lines < len(lines):
            result += f"\n\n# ... (extracted {current_lines}/{len(lines)} lines to fit token limit)"

            if self.verbose:
                print(f"      → Extracted {current_lines}/{len(lines)} lines")

        return result if result else content[:self.max_source_lines * 80]  # Fallback

    # ========================================================================
    # ADVANCED TARGETED EXTRACTION COMPONENTS
    # ========================================================================

    def _parse_test_imports_detailed(self, test_file: str) -> Dict[str, Set[str]]:
        """
        Parse test file to find what it imports from each module (detailed version).

        Args:
            test_file: Path to test file

        Returns:
            Dict mapping module paths to imported names
            Example: {
                'app.main': {'predict_batch', 'validate_sentence'},
                'app.utils': {'sanitize_input'}
            }
        """
        try:
            with open(test_file, 'r') as f:
                tree = ast.parse(f.read())
        except (FileNotFoundError, SyntaxError):
            return {}

        imports = {}  # module_path -> set of imported names

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                # import app.main as app_main
                for alias in node.names:
                    module_path = alias.name  # 'app.main'
                    import_name = alias.asname or alias.name  # 'app_main'

                    if module_path not in imports:
                        imports[module_path] = set()
                    imports[module_path].add(import_name)

            elif isinstance(node, ast.ImportFrom):
                # from app.main import predict_batch, validate_sentence
                module_path = node.module or ""

                if module_path not in imports:
                    imports[module_path] = set()

                for alias in node.names:
                    import_name = alias.name  # 'predict_batch'
                    imports[module_path].add(import_name)

        if self.verbose and imports:
            print(f"  📥 Parsed test imports:")
            for module, names in list(imports.items())[:3]:  # Show first 3
                names_str = ', '.join(list(names)[:5])
                if len(names) > 5:
                    names_str += f', ... ({len(names)} total)'
                print(f"      {module}: {names_str}")

        return imports

    def _build_source_map(self, source_file: str) -> Dict[str, Dict]:
        """
        Build an index of all definitions in the source file.

        Args:
            source_file: Path to source file

        Returns:
            Dict mapping names to definition info
            Format: {
                'function_name': {
                    'node': ast.FunctionDef,
                    'line_start': int,
                    'line_end': int,
                    'code': str
                }
            }
        """
        # Check cache first
        if source_file in self._source_map_cache:
            return self._source_map_cache[source_file]

        try:
            with open(source_file, 'r') as f:
                content = f.read()
        except (FileNotFoundError, IOError):
            return {}

        try:
            tree = ast.parse(content)
        except SyntaxError:
            return {}

        source_map = {}

        # Walk through all top-level definitions
        for node in tree.body:
            name = None

            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Function definitions
                name = node.name

            elif isinstance(node, ast.ClassDef):
                # Class definitions
                name = node.name

            elif isinstance(node, ast.Assign):
                # Variable assignments (constants)
                # MODEL = None
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        name = target.id
                        break

            if name:
                # Store definition info
                try:
                    code = ast.unparse(node)
                except:
                    code = ""  # Fallback if unparsing fails

                source_map[name] = {
                    'node': node,
                    'line_start': node.lineno if hasattr(node, 'lineno') else 0,
                    'line_end': node.end_lineno if hasattr(node, 'end_lineno') else 0,
                    'code': code
                }

        # Cache the result
        self._source_map_cache[source_file] = source_map

        if self.verbose and source_map:
            print(f"  🗺️  Built source map: {len(source_map)} definitions found")

        return source_map

    def _parse_error_traceback(
        self,
        error_message: str,
        source_file: str
    ) -> Set[str]:
        """
        Extract function names from error traceback.

        Args:
            error_message: The full error message with traceback
            source_file: Path to source file (to filter relevant entries)

        Returns:
            Set of function names that appear in the traceback
        """
        functions = set()

        if not error_message:
            return functions

        # Normalize paths for comparison
        try:
            source_file_normalized = os.path.abspath(source_file)
            source_file_name = os.path.basename(source_file)
        except:
            return functions

        # Pattern: File "path/to/file.py", line 123, in function_name
        # Matches both:
        #   File "/home/user/app/main.py", line 520, in predict_batch
        #   File "app/main.py", line 520, in predict_batch
        pattern = r'File\s+"([^"]+)",\s+line\s+(\d+),\s+in\s+(\w+)'

        for match in re.finditer(pattern, error_message):
            file_path = match.group(1)
            line_number = int(match.group(2))
            function_name = match.group(3)

            # Check if this traceback entry is from our source file
            # Match by filename or full path
            try:
                file_path_normalized = os.path.abspath(file_path)
                file_name = os.path.basename(file_path)

                if (file_path_normalized == source_file_normalized or
                    file_name == source_file_name):
                    functions.add(function_name)

                    if self.verbose:
                        print(f"      📍 Found in traceback: {function_name} (line {line_number})")
            except:
                # If path normalization fails, try basic string matching
                if source_file_name in file_path:
                    functions.add(function_name)

        return functions

    def _find_dependencies(
        self,
        node: ast.AST,
        source_map: Dict[str, Dict],
        max_depth: int = 3,
        visited: Optional[Set[str]] = None
    ) -> Set[str]:
        """
        Find all functions/variables that a node depends on (recursive).

        Args:
            node: AST node to analyze
            source_map: Map of all available definitions
            max_depth: Maximum recursion depth (prevent infinite loops)
            visited: Set of already visited names (for cycle detection)

        Returns:
            Set of dependency names
        """
        if visited is None:
            visited = set()

        if max_depth <= 0:
            return set()

        dependencies = set()

        # Walk through the function/class body
        for child in ast.walk(node):
            # Find Name nodes (variable/function references)
            if isinstance(child, ast.Name):
                name = child.id

                # Check if this name is defined in our source map
                if name in source_map and name not in visited:
                    dependencies.add(name)
                    visited.add(name)

                    # Recursively find dependencies of this dependency
                    dep_node = source_map[name]['node']
                    try:
                        sub_deps = self._find_dependencies(
                            dep_node,
                            source_map,
                            max_depth - 1,
                            visited
                        )
                        dependencies.update(sub_deps)
                    except RecursionError:
                        # Safety net for deep recursion
                        pass

            # Find function calls
            elif isinstance(child, ast.Call):
                # Direct function call: predict(text)
                if isinstance(child.func, ast.Name):
                    name = child.func.id

                    if name in source_map and name not in visited:
                        dependencies.add(name)
                        visited.add(name)

                        # Recursively find dependencies
                        dep_node = source_map[name]['node']
                        try:
                            sub_deps = self._find_dependencies(
                                dep_node,
                                source_map,
                                max_depth - 1,
                                visited
                            )
                            dependencies.update(sub_deps)
                        except RecursionError:
                            pass

                # Attribute call: obj.method()
                elif isinstance(child.func, ast.Attribute):
                    # MODEL.predict() - the object is 'MODEL'
                    if isinstance(child.func.value, ast.Name):
                        obj_name = child.func.value.id

                        if obj_name in source_map and obj_name not in visited:
                            dependencies.add(obj_name)
                            visited.add(obj_name)

        return dependencies

    def _extract_relevant_code_targeted(
        self,
        source_file: str,
        test_file: str,
        error_message: str,
        max_lines: int = 300
    ) -> str:
        """
        Extract only the code relevant to the failing test (TARGETED VERSION).

        Algorithm:
        1. Parse test imports to find what test uses
        2. Build source map to index all definitions
        3. Parse error traceback for additional context
        4. Find dependencies recursively
        5. Extract targeted code with priority ordering

        Args:
            source_file: Path to source file
            test_file: Path to test file
            error_message: Error message with traceback
            max_lines: Maximum lines to extract

        Returns:
            Extracted code string
        """
        try:
            with open(source_file, 'r') as f:
                content = f.read()
        except (FileNotFoundError, IOError):
            return ""

        total_lines = len(content.split('\n'))

        # If file is small enough, return everything
        if total_lines <= max_lines:
            return content

        if self.verbose:
            print(f"    🎯 Using targeted extraction for {os.path.basename(source_file)} ({total_lines} lines)...")

        # Step 1: Parse test imports
        test_imports = self._parse_test_imports_detailed(test_file)

        # Get imported names from this source file
        imported_names = set()
        source_file_name = Path(source_file).stem  # 'main' from 'app/main.py'

        for module_path, names in test_imports.items():
            # Check if this module corresponds to our source file
            # E.g., 'app.main' matches 'app/main.py'
            if source_file_name in module_path.replace('.', '/'):
                imported_names.update(names)

        # Step 2: Build source map
        source_map = self._build_source_map(source_file)

        if not source_map:
            # Fallback: return blind truncation
            if self.verbose:
                print(f"      ⚠️  Could not parse source file, using blind truncation")
            return self._extract_relevant_code(source_file, set())

        # Step 3: Parse error traceback
        error_functions = self._parse_error_traceback(error_message, source_file)

        # Step 4: Combine all target names
        target_names = imported_names | error_functions

        if self.verbose and target_names:
            targets_str = ', '.join(list(target_names)[:5])
            if len(target_names) > 5:
                targets_str += f', ... ({len(target_names)} total)'
            print(f"      🎯 Target functions: {targets_str}")

        if not target_names:
            # No specific targets found, fallback to blind truncation
            if self.verbose:
                print(f"      ⚠️  No specific targets found, using blind truncation")
            return self._extract_relevant_code(source_file, set())

        # Step 5: Extract with priority ordering
        extracted = []
        extracted_names = set()
        current_lines = 0

        # Priority 1: Imports (always include if space)
        for name, info in source_map.items():
            node = info['node']
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                code = info['code']
                lines = len(code.split('\n'))

                if current_lines + lines <= max_lines:
                    extracted.append(code)
                    extracted_names.add(name)
                    current_lines += lines

        # Priority 2: Constants used by target functions
        all_dependencies = set()
        for target in target_names:
            if target in source_map:
                try:
                    deps = self._find_dependencies(
                        source_map[target]['node'],
                        source_map
                    )
                    all_dependencies.update(deps)
                except:
                    pass  # Skip if dependency finding fails

        for name in all_dependencies:
            if name not in extracted_names and name in source_map:
                node = source_map[name]['node']
                if isinstance(node, ast.Assign):
                    code = source_map[name]['code']
                    lines = len(code.split('\n'))

                    if current_lines + lines <= max_lines:
                        extracted.append(code)
                        extracted_names.add(name)
                        current_lines += lines

        # Priority 3: Target functions (the ones actually used)
        for target in target_names:
            if target not in extracted_names and target in source_map:
                code = source_map[target]['code']
                lines = len(code.split('\n'))

                if current_lines + lines <= max_lines:
                    extracted.append(code)
                    extracted_names.add(target)
                    current_lines += lines

                    if self.verbose:
                        print(f"        ✓ Extracted: {target} ({lines} lines)")

        # Priority 4: Dependencies of target functions
        for dep in all_dependencies:
            if dep not in extracted_names and dep in source_map:
                code = source_map[dep]['code']
                lines = len(code.split('\n'))

                if current_lines + lines <= max_lines:
                    extracted.append(code)
                    extracted_names.add(dep)
                    current_lines += lines

                    if self.verbose:
                        print(f"        ✓ Extracted: {dep} ({lines} lines, dependency)")

        # Priority 5: Fill remaining space with other definitions
        if current_lines < max_lines:
            for name, info in source_map.items():
                if name not in extracted_names:
                    node = info['node']
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        code = info['code']
                        lines = len(code.split('\n'))

                        if current_lines + lines <= max_lines:
                            extracted.append(code)
                            extracted_names.add(name)
                            current_lines += lines

        # Build result
        if not extracted:
            # Fallback if nothing extracted
            return self._extract_relevant_code(source_file, set())

        result = "\n\n".join(extracted)

        # Add metadata
        result += f"\n\n# ... (extracted {current_lines} targeted lines from {total_lines} total)"
        result += f"\n# Targeted extraction: {len(extracted_names)} definitions"

        if self.verbose:
            print(f"      ✅ Extracted {current_lines}/{total_lines} lines ({len(extracted_names)} definitions)")

        return result

    def get_full_context_string(
        self,
        test_file_path: str,
        test_function_name: str,
        error_message: str = ""
    ) -> str:
        """
        Get a formatted string with all relevant context.

        Args:
            test_file_path: Path to test file
            test_function_name: Name of failing test
            error_message: Error message with traceback (for targeted extraction)

        Returns:
            Formatted context string
        """
        context = self.extract_context(test_file_path, test_function_name, error_message)

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
