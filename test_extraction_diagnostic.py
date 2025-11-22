#!/usr/bin/env python3
"""
Test Function Extraction Diagnostic

This script shows you EXACTLY what gets extracted when auto-fixer tries to
read a test function. It will reveal if you're getting the full 700-line file
or just the specific test function.

Usage:
    python test_extraction_diagnostic.py /path/to/test_file.py test_function_name

Example:
    python test_extraction_diagnostic.py \
        generated_tests/test_e2e_20251122_214922_01.py \
        test_get_products_endpoint_returns_200
"""

import sys
import ast
import re
from pathlib import Path


def extract_with_ast(content: str, test_name: str) -> tuple[str, bool]:
    """
    Try to extract test function using AST (same logic as orchestrator.py).

    Returns:
        (extracted_code, success)
    """
    try:
        tree = ast.parse(content)

        # Strip parameter suffix for parameterized tests
        base_test_name = test_name.split('[')[0]

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == base_test_name:
                    extracted = ast.unparse(node)
                    return extracted, True

        return None, False
    except Exception as e:
        return None, False


def extract_with_regex(content: str, test_name: str) -> tuple[str, bool]:
    """
    Try to extract test function using regex fallback.

    Returns:
        (extracted_code, success)
    """
    try:
        # Strip parameter suffix
        base_test_name = test_name.split('[')[0]

        # Match function definition with decorators
        pattern = rf'^(@.*\n)*(?:async\s+)?def\s+{re.escape(base_test_name)}\s*\([^)]*\):.*?(?=\n(?:def\s+|class\s+|@|$))'
        match = re.search(pattern, content, re.MULTILINE | re.DOTALL)

        if match:
            return match.group(0), True

        return None, False
    except Exception as e:
        return None, False


def diagnose_test_extraction(test_file: str, test_function_name: str):
    """
    Diagnose what gets extracted from a test file.
    """
    test_path = Path(test_file)

    print("=" * 80)
    print("TEST FUNCTION EXTRACTION DIAGNOSTIC")
    print("=" * 80)
    print(f"\n📄 Test file: {test_file}")
    print(f"🎯 Test function: {test_function_name}")

    # Check if file exists
    if not test_path.exists():
        print(f"\n❌ ERROR: File not found: {test_file}")
        print("\nPlease provide the full path to your test file.")
        return

    # Read file
    with open(test_path, 'r') as f:
        content = f.read()

    total_lines = content.count('\n') + 1
    total_chars = len(content)
    estimated_tokens = total_chars // 4

    print(f"\n📊 File stats:")
    print(f"   Total lines: {total_lines}")
    print(f"   Total chars: {total_chars:,}")
    print(f"   Est. tokens: ~{estimated_tokens:,}")

    # Count test functions in file
    tree = ast.parse(content)
    test_functions = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name.startswith('test_'):
                test_functions.append(node.name)

    print(f"\n🧪 Test functions found in file: {len(test_functions)}")
    if test_functions:
        print(f"   First 5: {', '.join(test_functions[:5])}")
        if len(test_functions) > 5:
            print(f"   ... and {len(test_functions) - 5} more")

    # Strip parameter suffix for display
    base_test_name = test_function_name.split('[')[0]
    print(f"\n🔍 Searching for: '{base_test_name}' (stripped from '{test_function_name}')")

    print("\n" + "=" * 80)
    print("EXTRACTION METHOD 1: AST (Primary)")
    print("=" * 80)

    ast_code, ast_success = extract_with_ast(content, test_function_name)

    if ast_success:
        ast_lines = ast_code.count('\n') + 1
        ast_chars = len(ast_code)
        ast_tokens = ast_chars // 4
        reduction_pct = ((total_lines - ast_lines) / total_lines) * 100

        print(f"✅ SUCCESS: AST extracted the function!")
        print(f"   Extracted lines: {ast_lines} (vs {total_lines} full file)")
        print(f"   Extracted chars: {ast_chars:,} (vs {total_chars:,} full file)")
        print(f"   Est. tokens: ~{ast_tokens:,} (vs ~{estimated_tokens:,} full file)")
        print(f"   Reduction: {reduction_pct:.1f}%")

        # Show first 10 lines
        print(f"\n📝 First 10 lines of extracted code:")
        for i, line in enumerate(ast_code.split('\n')[:10], 1):
            print(f"   {i:3}: {line}")
        if ast_lines > 10:
            print(f"   ... and {ast_lines - 10} more lines")
    else:
        print(f"❌ FAILED: AST could not find function '{base_test_name}'")
        print(f"   This means AST extraction failed - would try regex next")

    print("\n" + "=" * 80)
    print("EXTRACTION METHOD 2: Regex Fallback (NEW FIX)")
    print("=" * 80)

    regex_code, regex_success = extract_with_regex(content, test_function_name)

    if regex_success:
        regex_lines = regex_code.count('\n') + 1
        regex_chars = len(regex_code)
        regex_tokens = regex_chars // 4
        reduction_pct = ((total_lines - regex_lines) / total_lines) * 100

        print(f"✅ SUCCESS: Regex extracted the function!")
        print(f"   Extracted lines: {regex_lines} (vs {total_lines} full file)")
        print(f"   Extracted chars: {regex_chars:,} (vs {total_chars:,} full file)")
        print(f"   Est. tokens: ~{regex_tokens:,} (vs ~{estimated_tokens:,} full file)")
        print(f"   Reduction: {reduction_pct:.1f}%")

        # Show first 10 lines
        print(f"\n📝 First 10 lines of extracted code:")
        for i, line in enumerate(regex_code.split('\n')[:10], 1):
            print(f"   {i:3}: {line}")
        if regex_lines > 10:
            print(f"   ... and {regex_lines - 10} more lines")
    else:
        print(f"❌ FAILED: Regex could not find function '{base_test_name}'")
        print(f"   This means regex extraction also failed - would use full file")

    print("\n" + "=" * 80)
    print("EXTRACTION METHOD 3: Full File Fallback (OLD BEHAVIOR)")
    print("=" * 80)

    print(f"⚠️⚠️⚠️  USING FULL FILE - THIS IS THE BLOAT!")
    print(f"   Full file lines: {total_lines}")
    print(f"   Full file chars: {total_chars:,}")
    print(f"   Est. tokens: ~{estimated_tokens:,}")
    print(f"\n   If this happens, you're sending ALL {len(test_functions)} test functions")
    print(f"   to the LLM, not just the 1 failing test!")

    print("\n" + "=" * 80)
    print("FINAL RESULT - What gets sent to the LLM")
    print("=" * 80)

    if ast_success:
        final_lines = ast_code.count('\n') + 1
        final_chars = len(ast_code)
        method = "AST"
        print(f"✅ Method used: {method}")
        print(f"   Lines sent: {final_lines}")
        print(f"   Chars sent: {final_chars:,}")
        print(f"   Est. tokens: ~{final_chars // 4:,}")
        print(f"\n   This is GOOD - only the failing function is sent!")
    elif regex_success:
        final_lines = regex_code.count('\n') + 1
        final_chars = len(regex_code)
        method = "Regex (NEW FIX)"
        print(f"✅ Method used: {method}")
        print(f"   Lines sent: {final_lines}")
        print(f"   Chars sent: {final_chars:,}")
        print(f"   Est. tokens: ~{final_chars // 4:,}")
        print(f"\n   This is GOOD - only the failing function is sent!")
    else:
        method = "Full File Fallback (BLOAT!)"
        print(f"❌ Method used: {method}")
        print(f"   Lines sent: {total_lines}")
        print(f"   Chars sent: {total_chars:,}")
        print(f"   Est. tokens: ~{estimated_tokens:,}")
        print(f"\n   ⚠️  THIS IS THE PROBLEM!")
        print(f"   You're sending all {len(test_functions)} test functions instead of just 1!")
        print(f"   This creates massive token bloat!")

    print("\n" + "=" * 80)
    print("RECOMMENDATIONS")
    print("=" * 80)

    if ast_success or regex_success:
        print("✅ Extraction is working correctly!")
        print("   The fix should reduce your token usage significantly.")
    else:
        print("❌ Both AST and Regex extraction failed!")
        print("\nPossible reasons:")
        print(f"   1. Function '{base_test_name}' doesn't exist in the file")
        print(f"   2. Function name has typo or different format")
        print(f"   3. File has syntax errors preventing parsing")
        print("\nDebugging steps:")
        print(f"   1. Check if '{base_test_name}' is in the list above")
        print(f"   2. Look for syntax errors in the file")
        print(f"   3. Check if the function uses async or decorators")

    # Show what's currently being extracted
    print(f"\n💡 To test with your actual auto-fixer:")
    print(f"   1. Update orchestrator.py with the regex fallback (already done)")
    print(f"   2. Clear cache: rm -rf .codebase_index/")
    print(f"   3. Run auto-fixer and watch for these messages:")
    print(f"      '⚠️  AST couldn't find...'")
    print(f"      '✓ Regex extracted...'")
    print(f"      '⚠️⚠️⚠️  USING FULL FILE...'")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Diagnose test function extraction for auto-fixer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Test a specific function extraction
  python test_extraction_diagnostic.py \\
      generated_tests/test_e2e_20251122_214922_01.py \\
      test_get_products_endpoint_returns_200

  # Test with parameterized test name
  python test_extraction_diagnostic.py \\
      generated_tests/test_integ_20251122_214922_01.py \\
      "test_login[valid_credentials]"
        """
    )

    parser.add_argument(
        "test_file",
        help="Path to the test file"
    )
    parser.add_argument(
        "test_function",
        help="Name of the test function (with or without parameters)"
    )

    if len(sys.argv) == 1:
        # No arguments - show help and example
        parser.print_help()
        print("\n" + "=" * 80)
        print("QUICK START")
        print("=" * 80)
        print("\nTo find your test files:")
        print("  find . -name 'test_*.py' -type f | grep -v venv")
        print("\nTo see test function names in a file:")
        print("  grep 'def test_' your_test_file.py")
        print("\nThen run:")
        print("  python test_extraction_diagnostic.py <test_file> <test_function>")
        sys.exit(0)

    args = parser.parse_args()
    diagnose_test_extraction(args.test_file, args.test_function)
