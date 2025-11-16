#!/usr/bin/env python3
"""
Fix Duplicate Parametrize Decorator

Detects and removes duplicate @pytest.mark.parametrize decorators
with the same parameter name in test files.
"""

import ast
import sys
from typing import List, Set
from pathlib import Path


class DuplicateParametrizeRemover(ast.NodeTransformer):
    """AST transformer that removes duplicate parametrize decorators."""

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        """Visit function definitions and check for duplicate parametrize decorators."""
        if not node.decorator_list:
            return node

        # Track seen parametrize argument names
        seen_params: Set[str] = set()
        new_decorators: List[ast.expr] = []
        duplicates_found = False

        for decorator in node.decorator_list:
            # Check if this is a parametrize decorator
            param_name = self._get_parametrize_param_name(decorator)

            if param_name:
                if param_name in seen_params:
                    # Duplicate found - skip this decorator
                    duplicates_found = True
                    print(f"  Removing duplicate @pytest.mark.parametrize('{param_name}', ...) from {node.name}")
                    continue
                else:
                    seen_params.add(param_name)

            new_decorators.append(decorator)

        if duplicates_found:
            node.decorator_list = new_decorators

        return node

    def _get_parametrize_param_name(self, decorator: ast.expr) -> str:
        """
        Extract parameter name from @pytest.mark.parametrize decorator.

        Returns:
            Parameter name if this is a parametrize decorator, empty string otherwise
        """
        # Pattern 1: @pytest.mark.parametrize("param_name", ...)
        if isinstance(decorator, ast.Call):
            if isinstance(decorator.func, ast.Attribute):
                # Check if it's pytest.mark.parametrize
                if (isinstance(decorator.func.value, ast.Attribute) and
                    decorator.func.value.attr == "mark" and
                    decorator.func.attr == "parametrize"):
                    # Get the first argument (parameter name)
                    if decorator.args and isinstance(decorator.args[0], ast.Constant):
                        return decorator.args[0].value

        return ""


def fix_file(file_path: Path) -> bool:
    """
    Fix duplicate parametrize decorators in a test file.

    Args:
        file_path: Path to the test file

    Returns:
        True if file was modified, False otherwise
    """
    try:
        # Read the file
        with open(file_path, 'r') as f:
            content = f.read()

        # Parse into AST
        try:
            tree = ast.parse(content)
        except SyntaxError as e:
            print(f"Syntax error in {file_path}: {e}")
            return False

        # Transform the AST
        remover = DuplicateParametrizeRemover()
        new_tree = remover.visit(tree)

        # Convert back to code
        new_content = ast.unparse(new_tree)

        # Check if content changed
        if new_content == content:
            return False

        # Write back
        with open(file_path, 'w') as f:
            f.write(new_content)

        print(f"✓ Fixed {file_path}")
        return True

    except Exception as e:
        print(f"Error fixing {file_path}: {e}")
        return False


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Fix duplicate @pytest.mark.parametrize decorators'
    )
    parser.add_argument(
        'files',
        nargs='*',
        help='Test files to fix (default: scan tests/generated/)'
    )
    parser.add_argument(
        '--test-dir',
        default='tests/generated',
        help='Test directory to scan (default: tests/generated)'
    )

    args = parser.parse_args()

    # Determine files to process
    files_to_fix: List[Path] = []

    if args.files:
        # Use provided files
        files_to_fix = [Path(f) for f in args.files]
    else:
        # Scan test directory
        test_dir = Path(args.test_dir)
        if test_dir.exists():
            files_to_fix = list(test_dir.glob('test_*.py'))
        else:
            print(f"Error: Test directory not found: {test_dir}")
            sys.exit(1)

    if not files_to_fix:
        print("No test files found")
        sys.exit(0)

    print(f"Scanning {len(files_to_fix)} test file(s)...")
    print()

    # Fix each file
    fixed_count = 0
    for file_path in files_to_fix:
        if fix_file(file_path):
            fixed_count += 1

    print()
    print(f"{'=' * 80}")
    print(f"Fixed {fixed_count} file(s)")
    print(f"{'=' * 80}")


if __name__ == '__main__':
    main()
