#!/usr/bin/env python3
"""
Demo: Embedding-Based Code Retrieval System

This script demonstrates how the embedding-based code retrieval system works
and how it solves the problems that AST-based extraction faces.

Run this to see:
1. How the codebase is indexed
2. How semantic search finds code
3. How it handles edge cases that AST can't
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from auto_fixer.codebase_indexer import CodebaseIndexer
from auto_fixer.semantic_code_retriever import SemanticCodeRetriever


def demo_indexing():
    """Demonstrate codebase indexing."""
    print("=" * 80)
    print("DEMO 1: Building Codebase Index")
    print("=" * 80)

    indexer = CodebaseIndexer(
        project_root=".",
        verbose=True
    )

    print("\n🔨 Building index...")
    indexer.build_index(force_rebuild=True)

    print("\n✅ Index built successfully!")
    print(f"\nIndex Statistics:")
    print(f"  • Total elements: {len(indexer.code_elements)}")
    print(f"  • Functions: {sum(1 for e in indexer.code_elements if e.element_type == 'function')}")
    print(f"  • Classes: {sum(1 for e in indexer.code_elements if e.element_type == 'class')}")
    print(f"  • Variables: {sum(1 for e in indexer.code_elements if e.element_type == 'variable')}")
    print(f"  • HTTP Endpoints: {sum(1 for e in indexer.code_elements if e.element_type == 'http_endpoint')}")

    print("\n📝 Sample indexed elements:")
    for elem in indexer.code_elements[:5]:
        print(f"  • {elem.element_type}: {elem.name} ({elem.file_path}:{elem.line_start})")

    return indexer


def demo_semantic_search(indexer):
    """Demonstrate semantic code search."""
    print("\n" + "=" * 80)
    print("DEMO 2: Semantic Code Search")
    print("=" * 80)

    retriever = SemanticCodeRetriever(indexer, verbose=True)

    # Test 1: Search by function name
    print("\n🔍 Test 1: Search by function name")
    print("Query: 'function that generates tests'")
    results = retriever.search_by_query(
        "function that generates tests",
        top_k=3,
        filter_type='function'
    )

    print(f"\nFound {len(results)} results:")
    for result in results:
        print(f"  {result.rank}. {result.code_element.name}")
        print(f"     Type: {result.code_element.element_type}")
        print(f"     File: {result.code_element.file_path}")
        print(f"     Score: {result.similarity_score:.3f}")
        print()

    # Test 2: Search by HTTP endpoint (if any exist)
    print("\n🌐 Test 2: Search by HTTP endpoint")
    http_endpoints = [e for e in indexer.code_elements if e.element_type == 'http_endpoint']
    if http_endpoints:
        endpoint = http_endpoints[0]
        print(f"Query: 'HTTP {endpoint.http_method} {endpoint.http_path}'")
        results = retriever.search_by_http_endpoint(
            endpoint.http_method,
            endpoint.http_path,
            top_k=3
        )

        print(f"\nFound {len(results)} results:")
        for result in results:
            print(f"  {result.rank}. {result.code_element.name}")
            print(f"     Type: {result.code_element.element_type}")
            print(f"     Score: {result.similarity_score:.3f}")
    else:
        print("No HTTP endpoints found in codebase")

    # Test 3: Fuzzy search (handles typos)
    print("\n🎯 Test 3: Fuzzy search (handles typos)")
    print("Query: 'analyzr' (note the typo, should find 'analyzer')")
    results = retriever.search_by_query(
        "analyzr function",
        top_k=3
    )

    print(f"\nFound {len(results)} results (even with typo!):")
    for result in results:
        print(f"  {result.rank}. {result.code_element.name}")
        print(f"     Type: {result.code_element.element_type}")
        print(f"     Score: {result.similarity_score:.3f}")


def demo_test_failure_search(indexer):
    """Demonstrate search by test failure."""
    print("\n" + "=" * 80)
    print("DEMO 3: Test Failure Context Retrieval")
    print("=" * 80)

    retriever = SemanticCodeRetriever(indexer, verbose=True)

    # Simulate a test failure
    test_code = """
def test_coverage_analyzer():
    analyzer = CoverageAnalyzer()
    result = analyzer.analyze_coverage('tests/')
    assert result is not None
    """

    error_message = "AttributeError: 'NoneType' object has no attribute 'analyze_coverage'"
    traceback = """
File "tests/test_analyzer.py", line 10, in test_coverage_analyzer
    result = analyzer.analyze_coverage('tests/')
AttributeError: 'NoneType' object has no attribute 'analyze_coverage'
    """

    print("\n🧪 Simulated test failure:")
    print(f"Test code: {test_code.strip()}")
    print(f"Error: {error_message}")

    print("\n🔍 Searching for relevant code...")
    results = retriever.search_by_test_failure(
        test_code=test_code,
        error_message=error_message,
        traceback=traceback,
        top_k=5
    )

    print(f"\n✅ Found {len(results)} relevant code elements:")
    for result in results:
        print(f"\n  {result.rank}. {result.code_element.name} ({result.code_element.element_type})")
        print(f"     File: {result.code_element.file_path}:{result.code_element.line_start}")
        print(f"     Similarity: {result.similarity_score:.3f}")
        print(f"     Signature: {result.code_element.signature[:80]}...")


def demo_missing_target_detection(indexer):
    """Demonstrate detection of missing targets."""
    print("\n" + "=" * 80)
    print("DEMO 4: Missing Target Detection")
    print("=" * 80)

    retriever = SemanticCodeRetriever(indexer, verbose=True)

    # Test 1: Existing function
    print("\n🔍 Test 1: Looking for existing function")
    result = retriever.find_missing_target("analyze_coverage")

    if result:
        print(f"✓ Found: {result.code_element.name} (score: {result.similarity_score:.3f})")
    else:
        print("✗ Function not found in codebase")

    # Test 2: Non-existent function
    print("\n🔍 Test 2: Looking for non-existent function")
    result = retriever.find_missing_target("does_not_exist_function_xyz")

    if result:
        print(f"✓ Found: {result.code_element.name} (score: {result.similarity_score:.3f})")
    else:
        print("✗ Function not found in codebase (as expected!)")

    # Test 3: Misspelled function
    print("\n🔍 Test 3: Looking for misspelled function")
    result = retriever.find_missing_target("analize_coverage")  # Note: 'analize' instead of 'analyze'

    if result:
        print(f"✓ Found despite typo: {result.code_element.name} (score: {result.similarity_score:.3f})")
    else:
        print("✗ Function not found")


def main():
    """Run all demos."""
    print("\n" + "=" * 80)
    print("EMBEDDING-BASED CODE RETRIEVAL SYSTEM DEMO")
    print("=" * 80)
    print()
    print("This demo shows how embeddings solve AST extraction problems:")
    print("  ✓ Handles misspellings and typos")
    print("  ✓ Finds code even with wrong imports")
    print("  ✓ Detects missing functions")
    print("  ✓ Bypasses token limits")
    print("  ✓ Works with dynamic code patterns")
    print()

    # Check environment
    if not os.getenv("AZURE_OPENAI_ENDPOINT"):
        print("⚠️  Warning: AZURE_OPENAI_ENDPOINT not set!")
        print("   Set your OpenAI API credentials to run this demo.")
        return

    try:
        # Run demos
        indexer = demo_indexing()
        demo_semantic_search(indexer)
        demo_test_failure_search(indexer)
        demo_missing_target_detection(indexer)

        print("\n" + "=" * 80)
        print("✅ DEMO COMPLETE")
        print("=" * 80)
        print("\nThe embedding system is ready to use!")
        print("Set USE_EMBEDDINGS=true to enable it in the auto-fixer.")

    except Exception as e:
        print(f"\n❌ Demo failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
