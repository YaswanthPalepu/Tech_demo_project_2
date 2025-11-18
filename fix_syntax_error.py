#!/usr/bin/env python3
"""
Emergency fix for syntax error introduced by auto-fixer.

Usage:
    python fix_syntax_error.py /path/to/tests/generated
"""

import os
import sys
import re

def fix_syntax_errors_in_file(filepath):
    """Fix common syntax errors in test files."""
    print(f"Checking: {filepath}")

    try:
        with open(filepath, 'r') as f:
            content = f.read()
    except FileNotFoundError:
        print(f"  ✗ File not found")
        return False

    original_content = content
    fixed = False

    # Fix 1: Remove trailing comma in assert statements
    # Pattern: assert ..., f"...",
    pattern1 = r'(assert\s+[^,]+,\s+f"[^"]*")\s*,'
    if re.search(pattern1, content):
        content = re.sub(pattern1, r'\1', content)
        print(f"  ✓ Fixed trailing comma in assert")
        fixed = True

    # Fix 2: Fix type(e).name → type(e).__name__
    pattern2 = r'\{type\((\w+)\)\.name\}'
    if re.search(pattern2, content):
        content = re.sub(pattern2, r'{type(\1).__name__}', content)
        print(f"  ✓ Fixed type(e).name → type(e).__name__")
        fixed = True

    # Fix 3: Check for syntax errors by trying to parse
    import ast
    try:
        ast.parse(content)
        print(f"  ✓ Syntax is valid")
    except SyntaxError as e:
        print(f"  ⚠ Syntax error still present at line {e.lineno}: {e.msg}")
        print(f"    Preview: {e.text}")
        return False

    if fixed:
        # Write back
        with open(filepath, 'w') as f:
            f.write(content)
        print(f"  ✓ File fixed and saved")
        return True
    else:
        print(f"  - No fixes needed")
        return False


def main():
    if len(sys.argv) < 2:
        print("Usage: python fix_syntax_error.py /path/to/tests/generated")
        sys.exit(1)

    test_dir = sys.argv[1]

    if not os.path.isdir(test_dir):
        print(f"Error: {test_dir} is not a directory")
        sys.exit(1)

    print("=" * 80)
    print("EMERGENCY SYNTAX ERROR FIX")
    print("=" * 80)
    print(f"\nScanning: {test_dir}\n")

    fixed_count = 0

    # Find all Python test files
    for root, dirs, files in os.walk(test_dir):
        for filename in files:
            if filename.startswith('test_') and filename.endswith('.py'):
                filepath = os.path.join(root, filename)
                if fix_syntax_errors_in_file(filepath):
                    fixed_count += 1

    print("\n" + "=" * 80)
    print(f"SUMMARY: Fixed {fixed_count} file(s)")
    print("=" * 80)

    if fixed_count > 0:
        print("\n✓ You can now run pytest again!")
    else:
        print("\n- No fixes applied")


if __name__ == '__main__':
    main()
