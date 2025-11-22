#!/usr/bin/env python3
"""
SIMPLIFIED PROMPT TRACER - Skip embeddings, just show test extraction

This version skips the slow embedding search and just shows you what
test_code gets extracted, which is the main bloat source.

Usage:
    python trace_test_extraction.py --test-file <path>
"""

import sys
import os
import subprocess
import ast
import re
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from auto_fixer.failure_parser import FailureParser


def run_pytest(test_file: str):
    """Run pytest and capture failures."""
    print("=" * 80)
    print("STEP 1: Running pytest")
    print("=" * 80)
    print(f"\n🧪 Running: pytest {test_file} -v --tb=long\n")

    result = subprocess.run(
        ["pytest", test_file, "-v", "--tb=long"],
        capture_output=True,
        text=True,
        timeout=60
    )

    output = result.stdout + "\n" + result.stderr

    # Parse failures
    parser = FailureParser()
    json_data = parser._parse_text_output(output)
    failures = parser.parse_failures(json_data)

    print(f"✅ Pytest completed")
    print(f"   Failures found: {len(failures)}")

    if failures:
        print(f"\n📋 First failure:")
        failure = failures[0]
        print(f"   Test: {failure.test_name}")
        print(f"   Exception: {failure.exception_type}")

    return output, failures


def extract_test_code(failure, test_file_path: str):
    """Extract test code using AST/regex (same as orchestrator.py)."""
    print("\n" + "=" * 80)
    print("STEP 2: Extracting TEST CODE")
    print("=" * 80)

    with open(test_file_path, 'r') as f:
        content = f.read()

    total_lines = content.count('\n') + 1
    total_chars = len(content)

    print(f"\n📄 Test file: {test_file_path}")
    print(f"   Total lines: {total_lines:,}")
    print(f"   Total chars: {total_chars:,}")
    print(f"   Est. tokens: ~{total_chars // 4:,}")

    base_test_name = failure.test_name.split('[')[0]
    print(f"\n🔍 Looking for function: '{base_test_name}'")

    # Try AST
    try:
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == base_test_name:
                    test_code = ast.unparse(node)
                    lines = test_code.count('\n') + 1
                    chars = len(test_code)

                    print(f"\n✅ AST extraction SUCCESS!")
                    print(f"   Extracted lines: {lines:,}")
                    print(f"   Extracted chars: {chars:,}")
                    print(f"   Est. tokens: ~{chars // 4:,}")
                    print(f"   Reduction: {((total_lines - lines) / total_lines * 100):.1f}%")

                    return test_code, "AST", lines, chars

        # AST failed - try regex
        print(f"\n⚠️  AST failed - trying regex...")
        pattern = rf'^(@.*\n)*(?:async\s+)?def\s+{re.escape(base_test_name)}\s*\([^)]*\):.*?(?=\n(?:def\s+|class\s+|@|$))'
        match = re.search(pattern, content, re.MULTILINE | re.DOTALL)

        if match:
            test_code = match.group(0)
            lines = test_code.count('\n') + 1
            chars = len(test_code)

            print(f"\n✅ Regex extraction SUCCESS!")
            print(f"   Extracted lines: {lines:,}")
            print(f"   Extracted chars: {chars:,}")
            print(f"   Est. tokens: ~{chars // 4:,}")
            print(f"   Reduction: {((total_lines - lines) / total_lines * 100):.1f}%")

            return test_code, "Regex", lines, chars

        # Both failed
        print(f"\n❌ BOTH extractions FAILED!")
        print(f"   Using FULL FILE - THIS IS BLOAT!")
        print(f"   Full file lines: {total_lines:,}")
        print(f"   Full file chars: {total_chars:,}")
        print(f"   Est. tokens: ~{total_chars // 4:,}")

        return content, "FullFile", total_lines, total_chars

    except Exception as e:
        print(f"\n❌ Exception: {e}")
        print(f"   Using FULL FILE")
        return content, "FullFile", total_lines, total_chars


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Quick test extraction diagnostic")
    parser.add_argument("--test-file", required=True, help="Path to test file")
    args = parser.parse_args()

    print("\n" + "=" * 80)
    print("TEST EXTRACTION TRACER (No Embeddings)")
    print("=" * 80)

    # Run pytest
    output, failures = run_pytest(args.test_file)

    if not failures:
        print("\n❌ No failures found!")
        return

    failure = failures[0]

    # Extract test code
    test_code, method, lines, chars = extract_test_code(failure, args.test_file)

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    print(f"\n📊 Test code extraction:")
    print(f"   Method: {method}")
    print(f"   Lines: {lines:,}")
    print(f"   Chars: {chars:,}")
    print(f"   Tokens: ~{chars // 4:,}")

    if method == "FullFile":
        print(f"\n❌ BLOAT DETECTED!")
        print(f"   You're sending the ENTIRE test file to the LLM!")
        print(f"   This is the main source of token bloat!")
    else:
        print(f"\n✅ Extraction working correctly!")
        print(f"   Only the failing test function is extracted.")
        print(f"   This is good - no bloat from test code!")

    # Estimate with typical source code
    typical_source_lines = 100  # Estimated from embeddings
    total_prompt_lines = lines + typical_source_lines + 100  # +100 for overhead

    print(f"\n📈 Estimated prompt size:")
    print(f"   Test code: {lines:,} lines")
    print(f"   Source code: ~{typical_source_lines} lines (from embeddings)")
    print(f"   Overhead: ~100 lines (errors, instructions)")
    print(f"   TOTAL: ~{total_prompt_lines:,} lines (~{total_prompt_lines * 4:,} tokens)")

    if method == "FullFile":
        optimal_lines = 30
        savings = lines - optimal_lines
        print(f"\n💡 If extraction worked:")
        print(f"   Test code would be: ~{optimal_lines} lines")
        print(f"   Total prompt: ~{optimal_lines + typical_source_lines + 100} lines")
        print(f"   Savings: ~{savings:,} lines (~{savings * 4:,} tokens)")


if __name__ == "__main__":
    main()
