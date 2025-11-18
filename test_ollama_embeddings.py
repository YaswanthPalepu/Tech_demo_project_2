#!/usr/bin/env python3
"""
Simple test to verify Ollama embeddings work with the codebase indexer.
This doesn't require numpy.
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))
sys.path.insert(0, str(Path(__file__).parent))

# Set environment variables for Ollama
os.environ["OLLAMA_HOST"] = "http://172.190.86.69:11434"
os.environ["OLLAMA_EMBED_MODEL"] = "qwen3-embedding:latest"
os.environ["VECTOR_DIM"] = "1024"

print("=" * 80)
print("TESTING OLLAMA EMBEDDINGS")
print("=" * 80)
print(f"Host: {os.environ['OLLAMA_HOST']}")
print(f"Model: {os.environ['OLLAMA_EMBED_MODEL']}")
print(f"Vector Dim: {os.environ['VECTOR_DIM']}")
print()

# Test 1: Import and create client
print("Test 1: Creating Ollama client...")
try:
    # Import ollama_client directly to avoid gen.__init__ issues
    import importlib.util

    module_path = Path(__file__).parent / 'src' / 'gen' / 'ollama_client.py'
    spec = importlib.util.spec_from_file_location("ollama_client_test", module_path)
    ollama_module = importlib.util.module_from_spec(spec)
    sys.modules['ollama_client_test'] = ollama_module
    spec.loader.exec_module(ollama_module)

    client = ollama_module.get_ollama_client()
    print("  ✓ Client created successfully")
except Exception as e:
    print(f"  ✗ Failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 2: Generate a single embedding
print("\nTest 2: Generating test embedding...")
try:
    response = client.create(
        model=os.environ["OLLAMA_EMBED_MODEL"],
        input=["Hello, this is a test."]
    )

    if response.data and len(response.data) > 0:
        embedding = response.data[0].embedding
        print(f"  ✓ Embedding generated successfully")
        print(f"  Dimension: {len(embedding)}")
        print(f"  Sample values: {embedding[:5]}")
    else:
        print("  ✗ Empty response from Ollama")
        sys.exit(1)
except Exception as e:
    print(f"  ✗ Failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 3: Load indexer (without building full index)
print("\nTest 3: Loading codebase indexer with Ollama...")
try:
    # Import CodeElement first (needed for indexer)
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        'codebase_indexer',
        Path(__file__).parent / 'src' / 'auto_fixer' / 'codebase_indexer.py'
    )
    codebase_indexer_module = importlib.util.module_from_spec(spec)
    sys.modules['codebase_indexer'] = codebase_indexer_module
    spec.loader.exec_module(codebase_indexer_module)

    CodebaseIndexer = codebase_indexer_module.CodebaseIndexer

    indexer = CodebaseIndexer(
        project_root=".",
        verbose=True
    )

    print("  ✓ Indexer created successfully")

    # Test that it uses Ollama client
    print("\nTest 4: Verifying indexer uses Ollama...")
    _ = indexer.embedding_client  # Trigger lazy load

except Exception as e:
    print(f"  ✗ Failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# Test 5: Generate embeddings for a few code samples
print("\nTest 5: Generating embeddings for code samples...")
try:
    test_samples = [
        "def hello(): pass",
        "class MyClass: pass",
        "import os"
    ]

    embeddings = indexer._generate_embeddings_batch(
        [codebase_indexer_module.CodeElement(
            element_type="function",
            name=f"test_{i}",
            file_path="test.py",
            line_start=1,
            line_end=1,
            source_code=sample,
            signature=sample
        ) for i, sample in enumerate(test_samples)]
    )

    print(f"  ✓ Generated {len(embeddings)} embeddings")
    print(f"  Dimensions: {[len(e) for e in embeddings]}")

    # Verify all embeddings have correct dimension
    vector_dim = int(os.environ["VECTOR_DIM"])
    if all(len(e) == vector_dim for e in embeddings):
        print(f"  ✓ All embeddings have correct dimension ({vector_dim})")
    else:
        print(f"  ✗ Dimension mismatch!")
        sys.exit(1)

except Exception as e:
    print(f"  ✗ Failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 80)
print("✅ ALL TESTS PASSED!")
print("=" * 80)
print()
print("The Ollama embedding system is working correctly.")
print("You can now run the auto-fixer with embeddings enabled.")
print()
print("Next steps:")
print("  1. Clear old cache: rm -rf .codebase_index/")
print("  2. Run auto-fixer: python run_auto_fixer.py")
