#!/usr/bin/env python3
"""
Diagnostic script to inspect what's stored in the codebase index.
This will show you exactly what the embeddings contain.
"""

import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from auto_fixer.codebase_indexer import CodebaseIndexer

def inspect_index(project_root: str = "/home/sigmoid/test-repos/backend_code"):
    """Inspect the codebase index to see what's stored."""

    print("=" * 80)
    print("CODEBASE INDEX INSPECTION")
    print("=" * 80)

    # Initialize indexer
    indexer = CodebaseIndexer(
        project_root=project_root,
        verbose=True
    )

    # Build/load index
    print("\n📦 Loading or building index...")
    indexer.build_index()

    print("\n" + "=" * 80)
    print(f"TOTAL CODE ELEMENTS: {len(indexer.code_elements)}")
    print("=" * 80)

    # Group by file
    by_file = {}
    for elem in indexer.code_elements:
        if elem.file_path not in by_file:
            by_file[elem.file_path] = []
        by_file[elem.file_path].append(elem)

    print(f"\n📁 Elements grouped by file ({len(by_file)} files):\n")

    total_source_lines = 0

    for file_path, elements in sorted(by_file.items()):
        print(f"\n📄 {file_path}")
        print(f"   Elements: {len(elements)}")

        for elem in elements:
            source_lines = elem.source_code.count('\n') + 1
            total_source_lines += source_lines

            print(f"   • {elem.element_type}: {elem.name}")
            print(f"     Lines: {elem.line_start}-{elem.line_end} (stored: {source_lines} lines)")
            print(f"     Signature: {elem.signature[:80]}...")

            # Show if this looks bloated
            actual_lines = elem.line_end - elem.line_start + 1
            stored_lines = source_lines
            if stored_lines > actual_lines + 5:
                print(f"     ⚠️  BLOAT: Actual {actual_lines} lines but stored {stored_lines} lines!")

            # Show first 3 lines of source
            first_lines = '\n'.join(elem.source_code.split('\n')[:3])
            print(f"     Source preview:")
            for line in first_lines.split('\n'):
                print(f"       {line}")

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total elements: {len(indexer.code_elements)}")
    print(f"Total files: {len(by_file)}")
    print(f"Total source code lines stored: {total_source_lines}")
    print(f"Average lines per element: {total_source_lines // len(indexer.code_elements) if indexer.code_elements else 0}")

    # Check by element type
    by_type = {}
    for elem in indexer.code_elements:
        if elem.element_type not in by_type:
            by_type[elem.element_type] = []
        by_type[elem.element_type].append(elem)

    print(f"\nBy element type:")
    for elem_type, elems in sorted(by_type.items()):
        total_lines = sum(e.source_code.count('\n') + 1 for e in elems)
        avg_lines = total_lines // len(elems) if elems else 0
        print(f"  {elem_type}: {len(elems)} elements, {total_lines} total lines, {avg_lines} avg lines/element")

    print("\n" + "=" * 80)
    print("CHECKING FOR ISSUES")
    print("=" * 80)

    # Check if any test files got indexed (should be 0)
    test_files = [e for e in indexer.code_elements if 'test_' in e.file_path or '/test' in e.file_path]
    if test_files:
        print(f"❌ PROBLEM: {len(test_files)} test file elements found (should be 0)!")
        for elem in test_files[:5]:
            print(f"   • {elem.file_path}")
    else:
        print("✅ No test files indexed (correct)")

    # Check for unexpectedly large elements
    large_elements = [e for e in indexer.code_elements if e.source_code.count('\n') > 50]
    if large_elements:
        print(f"\n⚠️  {len(large_elements)} elements with >50 lines:")
        for elem in large_elements:
            lines = elem.source_code.count('\n') + 1
            print(f"   • {elem.element_type} {elem.name}: {lines} lines in {elem.file_path}")
    else:
        print("\n✅ No elements >50 lines (good for 230-line codebase)")

    return indexer


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Inspect codebase embeddings")
    parser.add_argument(
        "--project-root",
        default="/home/sigmoid/test-repos/backend_code",
        help="Path to backend_code directory"
    )

    args = parser.parse_args()

    if not os.path.exists(args.project_root):
        print(f"❌ Error: Project root not found: {args.project_root}")
        print("\nPlease provide the correct path to your backend_code directory:")
        print("  python inspect_embeddings.py --project-root /path/to/backend_code")
        sys.exit(1)

    inspect_index(args.project_root)
