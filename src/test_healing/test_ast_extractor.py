#!/usr/bin/env python3
"""
Test AST Extractor - Extracts test code structure from generated tests.

This module specifically parses tests in tests/generated folder (which are skipped
by the main analyzer.py) to extract test functions, classes, and methods for healing.
"""

import ast
import pathlib
from typing import Any, Dict, List, Optional, Set, Tuple


class TestASTExtractor:
    """Extract AST information specifically from generated test files."""

    def __init__(self, tests_dir: pathlib.Path):
        """
        Initialize the test AST extractor.

        Args:
            tests_dir: Path to tests/generated directory
        """
        self.tests_dir = pathlib.Path(tests_dir)

    def extract_test_structure(self, test_file: pathlib.Path) -> Dict[str, Any]:
        """
        Extract complete test structure from a test file.

        Args:
            test_file: Path to test file

        Returns:
            Dictionary containing test functions, classes, methods, and imports
        """
        structure = {
            "file_path": str(test_file),
            "test_functions": [],
            "test_classes": [],
            "test_methods": [],
            "imports": [],
            "fixtures": [],
            "parametrize_decorators": [],
            "all_test_names": set(),
            "source_code": "",
            "ast_tree": None
        }

        try:
            source_code = test_file.read_text(encoding="utf-8")
            structure["source_code"] = source_code

            tree = ast.parse(source_code)
            structure["ast_tree"] = tree

            # Extract imports
            structure["imports"] = self._extract_imports(tree)

            # Extract fixtures
            structure["fixtures"] = self._extract_fixtures(tree)

            # Extract test functions and classes
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    if node.name.startswith("test_"):
                        func_info = self._extract_function_info(node, source_code)
                        structure["test_functions"].append(func_info)
                        structure["all_test_names"].add(node.name)

                        # Extract parametrize decorators
                        for dec in node.decorator_list:
                            if self._is_parametrize_decorator(dec):
                                structure["parametrize_decorators"].append({
                                    "function": node.name,
                                    "decorator": ast.unparse(dec),
                                    "line": node.lineno
                                })
                    elif node.name.startswith("fixture") or self._has_fixture_decorator(node):
                        fixture_info = self._extract_function_info(node, source_code)
                        structure["fixtures"].append(fixture_info)

                elif isinstance(node, ast.ClassDef):
                    if node.name.startswith("Test"):
                        class_info = self._extract_class_info(node, source_code)
                        structure["test_classes"].append(class_info)
                        structure["all_test_names"].add(node.name)

                        # Extract methods from test class
                        for item in node.body:
                            if isinstance(item, ast.FunctionDef) and item.name.startswith("test_"):
                                method_info = self._extract_method_info(item, node.name, source_code)
                                structure["test_methods"].append(method_info)
                                structure["all_test_names"].add(f"{node.name}.{item.name}")

            # Convert set to list for JSON serialization
            structure["all_test_names"] = list(structure["all_test_names"])

        except Exception as e:
            print(f"Error extracting test structure from {test_file}: {e}")

        return structure

    def _extract_imports(self, tree: ast.AST) -> List[Dict[str, Any]]:
        """Extract all import statements."""
        imports = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append({
                        "type": "import",
                        "module": alias.name,
                        "alias": alias.asname,
                        "line": node.lineno
                    })
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    imports.append({
                        "type": "import_from",
                        "module": node.module,
                        "name": alias.name,
                        "alias": alias.asname,
                        "line": node.lineno
                    })

        return imports

    def _extract_fixtures(self, tree: ast.AST) -> List[Dict[str, Any]]:
        """Extract pytest fixtures."""
        fixtures = []

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if self._has_fixture_decorator(node):
                    fixtures.append({
                        "name": node.name,
                        "line": node.lineno,
                        "end_line": getattr(node, "end_lineno", node.lineno),
                        "scope": self._get_fixture_scope(node),
                        "params": self._get_fixture_params(node)
                    })

        return fixtures

    def _has_fixture_decorator(self, node: ast.FunctionDef) -> bool:
        """Check if function has @pytest.fixture decorator."""
        for dec in node.decorator_list:
            if isinstance(dec, ast.Name) and dec.id == "fixture":
                return True
            if isinstance(dec, ast.Attribute) and dec.attr == "fixture":
                return True
            if isinstance(dec, ast.Call):
                if isinstance(dec.func, ast.Name) and dec.func.id == "fixture":
                    return True
                if isinstance(dec.func, ast.Attribute) and dec.func.attr == "fixture":
                    return True
        return False

    def _get_fixture_scope(self, node: ast.FunctionDef) -> Optional[str]:
        """Extract fixture scope from decorator."""
        for dec in node.decorator_list:
            if isinstance(dec, ast.Call):
                for keyword in dec.keywords:
                    if keyword.arg == "scope":
                        if isinstance(keyword.value, ast.Constant):
                            return keyword.value.value
        return None

    def _get_fixture_params(self, node: ast.FunctionDef) -> List[str]:
        """Extract fixture parameter names."""
        return [arg.arg for arg in node.args.args if arg.arg != "self"]

    def _is_parametrize_decorator(self, dec: ast.expr) -> bool:
        """Check if decorator is @pytest.mark.parametrize."""
        if isinstance(dec, ast.Call):
            if isinstance(dec.func, ast.Attribute):
                if (isinstance(dec.func.value, ast.Attribute) and
                    dec.func.value.attr == "mark" and
                    dec.func.attr == "parametrize"):
                    return True
        return False

    def _extract_function_info(self, node: ast.FunctionDef, source_code: str) -> Dict[str, Any]:
        """Extract detailed information about a test function."""
        return {
            "name": node.name,
            "line_start": node.lineno,
            "line_end": getattr(node, "end_lineno", node.lineno),
            "args": [arg.arg for arg in node.args.args],
            "decorators": [ast.unparse(dec) for dec in node.decorator_list],
            "docstring": ast.get_docstring(node),
            "is_async": isinstance(node, ast.AsyncFunctionDef),
            "source": ast.get_source_segment(source_code, node) if hasattr(ast, 'get_source_segment') else None
        }

    def _extract_class_info(self, node: ast.ClassDef, source_code: str) -> Dict[str, Any]:
        """Extract detailed information about a test class."""
        methods = []
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                if item.name.startswith("test_"):
                    methods.append(item.name)

        return {
            "name": node.name,
            "line_start": node.lineno,
            "line_end": getattr(node, "end_lineno", node.lineno),
            "bases": [ast.unparse(base) for base in node.bases],
            "decorators": [ast.unparse(dec) for dec in node.decorator_list],
            "docstring": ast.get_docstring(node),
            "test_methods": methods,
            "method_count": len(methods),
            "source": ast.get_source_segment(source_code, node) if hasattr(ast, 'get_source_segment') else None
        }

    def _extract_method_info(self, node: ast.FunctionDef, class_name: str,
                            source_code: str) -> Dict[str, Any]:
        """Extract detailed information about a test method."""
        info = self._extract_function_info(node, source_code)
        info["class"] = class_name
        info["full_name"] = f"{class_name}.{node.name}"
        return info

    def extract_test_by_name(self, test_file: pathlib.Path, test_name: str) -> Optional[Dict[str, Any]]:
        """
        Extract a specific test by name from a test file.

        Args:
            test_file: Path to test file
            test_name: Name of test (e.g., 'test_foo' or 'TestClass.test_method')

        Returns:
            Dictionary with test information or None if not found
        """
        structure = self.extract_test_structure(test_file)

        # Check if it's a method (contains dot)
        if "." in test_name:
            class_name, method_name = test_name.split(".", 1)
            for method in structure["test_methods"]:
                if method["class"] == class_name and method["name"] == method_name:
                    return method
        else:
            # Check test functions
            for func in structure["test_functions"]:
                if func["name"] == test_name:
                    return func

            # Check test classes
            for cls in structure["test_classes"]:
                if cls["name"] == test_name:
                    return cls

        return None

    def get_test_source_code(self, test_file: pathlib.Path, test_name: str) -> Optional[str]:
        """
        Get the source code of a specific test.

        Args:
            test_file: Path to test file
            test_name: Name of test

        Returns:
            Source code string or None
        """
        test_info = self.extract_test_by_name(test_file, test_name)
        if test_info and test_info.get("source"):
            return test_info["source"]

        # Fallback: extract by line numbers
        if test_info:
            try:
                source_code = test_file.read_text(encoding="utf-8")
                lines = source_code.splitlines()
                start = test_info["line_start"] - 1
                end = test_info["line_end"]
                return "\n".join(lines[start:end])
            except Exception as e:
                print(f"Error extracting source code: {e}")

        return None

    def extract_all_tests_from_directory(self) -> Dict[str, Dict[str, Any]]:
        """
        Extract test structures from all test files in the directory.

        Returns:
            Dictionary mapping file paths to their test structures
        """
        all_tests = {}

        if not self.tests_dir.exists():
            print(f"Tests directory does not exist: {self.tests_dir}")
            return all_tests

        for test_file in self.tests_dir.glob("test_*.py"):
            if test_file.is_file():
                structure = self.extract_test_structure(test_file)
                all_tests[str(test_file)] = structure

        return all_tests

    def find_test_location(self, test_name: str) -> Optional[Tuple[pathlib.Path, Dict[str, Any]]]:
        """
        Find which file contains a specific test.

        Args:
            test_name: Name of test to find

        Returns:
            Tuple of (file_path, test_info) or None if not found
        """
        all_tests = self.extract_all_tests_from_directory()

        for file_path, structure in all_tests.items():
            test_info = self.extract_test_by_name(pathlib.Path(file_path), test_name)
            if test_info:
                return (pathlib.Path(file_path), test_info)

        return None


def main():
    """Test the AST extractor."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python test_ast_extractor.py <tests_directory>")
        sys.exit(1)

    tests_dir = pathlib.Path(sys.argv[1])
    extractor = TestASTExtractor(tests_dir)

    print(f"Extracting tests from: {tests_dir}")
    all_tests = extractor.extract_all_tests_from_directory()

    for file_path, structure in all_tests.items():
        print(f"\n📄 {file_path}")
        print(f"   Functions: {len(structure['test_functions'])}")
        print(f"   Classes: {len(structure['test_classes'])}")
        print(f"   Methods: {len(structure['test_methods'])}")
        print(f"   Fixtures: {len(structure['fixtures'])}")
        print(f"   All tests: {', '.join(structure['all_test_names'])}")


if __name__ == "__main__":
    main()
