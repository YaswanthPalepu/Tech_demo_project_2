#!/usr/bin/env python3
"""
Fix the test_parametrized_inputs test to handle None correctly.

The test fails because None is JSON-serializable (becomes "null") but the
isinstance check doesn't include type(None), causing it to take the wrong
code path.

Fix: Add type(None) to the isinstance check.
"""

import ast
import sys
from pathlib import Path


def fix_test_parametrized_inputs(file_path: Path) -> bool:
    """
    Fix the test_parametrized_inputs function to handle None correctly.

    Args:
        file_path: Path to the test file

    Returns:
        True if file was fixed, False otherwise
    """
    try:
        # Read the file
        with open(file_path, 'r') as f:
            content = f.read()

        # Check if this is the problematic test
        if 'def test_parametrized_inputs(' not in content:
            print(f"Skipping {file_path} - doesn't contain test_parametrized_inputs")
            return False

        # Parse the AST
        try:
            tree = ast.parse(content)
        except SyntaxError as e:
            print(f"Syntax error in {file_path}: {e}")
            return False

        # Find the test function
        test_func = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == 'test_parametrized_inputs':
                test_func = node
                break

        if not test_func:
            print(f"Function test_parametrized_inputs not found in {file_path}")
            return False

        # Get the function's line range
        start_line = test_func.lineno - 1  # 0-indexed
        end_line = test_func.end_lineno    # 1-indexed, inclusive

        # Split into lines
        lines = content.split('\n')

        # Find and fix the isinstance line
        fixed = False
        for i in range(start_line, min(end_line, len(lines))):
            line = lines[i]

            # Look for the isinstance check without type(None)
            if 'isinstance(input_value, (dict, list, int, str))' in line:
                # Replace with version that includes type(None)
                lines[i] = line.replace(
                    'isinstance(input_value, (dict, list, int, str))',
                    'isinstance(input_value, (dict, list, int, str, type(None)))'
                )
                fixed = True
                print(f"  Fixed isinstance check at line {i + 1}")
                break

        if not fixed:
            print(f"Could not find the isinstance line to fix in {file_path}")
            return False

        # Write back
        new_content = '\n'.join(lines)

        # Validate syntax
        try:
            ast.parse(new_content)
        except SyntaxError as e:
            print(f"Fixed code has syntax error: {e}")
            return False

        # Write the file
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
        description='Fix test_parametrized_inputs to handle None correctly'
    )
    parser.add_argument(
        'files',
        nargs='*',
        help='Test files to fix (default: scan tests/generated/test_e2e_*.py)'
    )
    parser.add_argument(
        '--test-dir',
        default='tests/generated',
        help='Test directory to scan (default: tests/generated)'
    )

    args = parser.parse_args()

    # Determine files to process
    files_to_fix = []

    if args.files:
        # Use provided files
        files_to_fix = [Path(f) for f in args.files]
    else:
        # Scan for e2e test files
        test_dir = Path(args.test_dir)
        if test_dir.exists():
            files_to_fix = list(test_dir.glob('test_e2e_*.py'))
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
        if fix_test_parametrized_inputs(file_path):
            fixed_count += 1

    print()
    print(f"{'=' * 80}")
    print(f"Fixed {fixed_count} file(s)")
    print(f"{'=' * 80}")

    if fixed_count > 0:
        print()
        print("✓ The test should now pass. Run pytest to verify:")
        print("  pytest tests/generated/test_e2e_20251117_052441_01.py::test_parametrized_inputs -v")


if __name__ == '__main__':
    main()
