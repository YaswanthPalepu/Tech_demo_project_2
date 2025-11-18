# Auto Test Fixer with Embedding Support

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
export AZURE_OPENAI_KEY='your-key'
export AZURE_OPENAI_ENDPOINT='https://your-endpoint.openai.azure.com/'
export AZURE_OPENAI_DEPLOYMENT='gpt-4'

# Run auto-fixer
python run_embedding_auto_fixer.py --verbose
```

## Module Structure

```
src/auto_fixer/
├── __init__.py                     # Package exports
├── orchestrator.py                 # Main workflow coordinator
├── failure_parser.py               # Pytest failure parsing
├── rule_classifier.py              # Rule-based classification
├── llm_classifier.py               # LLM-based classification
├── enhanced_context_extractor.py   # Hybrid AST + Embedding extraction ⭐
├── embedding_indexer.py            # Code indexing with embeddings ⭐
├── embedding_retriever.py          # Semantic search ⭐
├── code_chunker.py                 # Smart chunking for token limits ⭐
├── llm_fixer.py                    # LLM-based fix generation
├── ast_patcher.py                  # AST-based fix application
└── README.md                       # This file
```

## Components

### Core Components (from auto-test-fixer branch)

**FailureParser**: Runs pytest and parses JSON output
**RuleBasedClassifier**: Quick pattern-based classification
**LLMClassifier**: LLM-powered classification
**LLMFixer**: Generates test fixes using LLM
**ASTPatcher**: Applies fixes to test files

### New Embedding Components ⭐

**EmbeddingIndexer**: Builds semantic index of codebase
- Indexes functions, classes, methods, HTTP endpoints, variables
- Generates embeddings using OpenAI API
- Caches results for fast lookup

**EmbeddingRetriever**: Performs semantic search
- Searches by error traceback
- Maps HTTP endpoints to handlers
- Resolves dependencies recursively
- Detects "source not found" / "target not found"

**CodeChunker**: Manages token limits
- Prioritizes code elements
- Estimates tokens
- Chunks context to fit LLM limits

**EnhancedContextExtractor**: Hybrid extraction (AST + Embeddings)
- Tries AST first (fast)
- Falls back to embeddings (robust)
- Merges results
- Resolves dependencies

## Workflow

```
1. Run pytest → Parse failures
2. Classify: test_mistake vs code_bug
3. Extract context:
   a. AST extraction (imports, functions)
   b. Embedding search (semantic, HTTP, traceback)
   c. Merge results
   d. Resolve dependencies
4. Chunk context to fit token limits
5. Generate fix using LLM
6. Apply fix to test file
7. Validate and re-run
8. Repeat if needed
```

## Key Features

✅ **Hybrid Approach**: Best of AST (fast) and embeddings (robust)
✅ **Token Management**: Smart chunking prevents overflow
✅ **Recursive Dependencies**: Finds transitive dependencies
✅ **HTTP Endpoint Mapping**: Maps routes to handlers
✅ **Error Detection**: "Source not found", "Target not found"
✅ **Multi-Attempt Fixing**: Learns from failed attempts

## Configuration

Environment variables:
- `AUTOFIXER_VERBOSE`: Enable verbose logging (true/false)
- `AZURE_OPENAI_KEY`: Azure OpenAI API key
- `AZURE_OPENAI_ENDPOINT`: Azure OpenAI endpoint
- `AZURE_OPENAI_DEPLOYMENT`: Deployment name

Command-line options:
- `--rebuild-index`: Force rebuild embedding index
- `--no-embeddings`: Disable embeddings (AST only)
- `--verbose`: Enable verbose logging
- `--max-tokens N`: Set max context tokens (default: 6000)
- `--max-iterations N`: Set max fix iterations (default: 3)

## Example Output

```
================================================================================
AUTO TEST FIXER WITH EMBEDDINGS - STARTING
================================================================================

📊 Embedding Index Statistics:
  Total elements indexed: 127
  Files indexed: 23
  By type: {'function': 45, 'class': 12, 'http_endpoint': 15, ...}
  Embedding coverage: 100.0%

================================================================================
ITERATION 1/3
================================================================================

Step 1: Running pytest and parsing failures...
Found 5 failing test(s)

--- Processing failure 1/5 ---
Test: test_predict_endpoint in tests/test_api.py
  Rule classifier: unknown, extracting context...
  Extraction: hybrid method, 8 elements
  Embeddings (traceback): Found 3 element(s)
  Embeddings (HTTP): Found 1 endpoint(s)
  Dependencies: Added 4 transitive dependencies
  ✓ Including predict (420 tokens, priority 90)
  ✓ Including validate_input (180 tokens, priority 70)
  LLM classifier: test_mistake (Missing import)
  Generating fix...
  Applying fix...
  ✓ Fix applied successfully
  ✅ TEST MISTAKE FIXED

================================================================================
FINAL SUMMARY
================================================================================
Iterations: 1/3
Total failures processed: 5
Test mistakes: 5
  - Fixed: 4
  - Failed to fix: 1
Code bugs (not fixed): 0

Extraction methods used: {'hybrid': 3, 'embedding': 2}
================================================================================
```

## Advanced Usage

### Programmatic API

```python
from auto_fixer.embedding_indexer import EmbeddingIndexer
from auto_fixer.embedding_retriever import EmbeddingRetriever

# Build index
indexer = EmbeddingIndexer(project_root=".", verbose=True)
indexer.build_index()

# Search
retriever = EmbeddingRetriever(indexer)
results = retriever.search("POST /predict", top_k=5)

# Find HTTP handler
handler = retriever.search_by_http_endpoint("POST", "/predict")

# Resolve dependencies
deps = retriever.resolve_dependencies_recursive(["my_function"], max_depth=3)
```

### Custom Chunking

```python
from auto_fixer.code_chunker import CodeChunker

chunker = CodeChunker(max_tokens=8000, verbose=True)
chunks = chunker.chunk_context(
    search_results=results,
    test_code=test_code,
    error_message=error_message
)
selected = chunker.select_chunks_within_limit(chunks)
context = chunker.build_final_context(selected)
```

## Troubleshooting

**Issue**: Index build fails
**Solution**: Check OpenAI API credentials, ensure project has Python files

**Issue**: No embeddings generated
**Solution**: System will fall back to text-based search automatically

**Issue**: Token limit exceeded
**Solution**: Reduce `--max-tokens` or let chunker handle automatically

**Issue**: Source code not found
**Solution**: Enable verbose mode to see extraction details, rebuild index

## Performance

- **Index build**: ~10-30 seconds for medium codebase (100 files)
- **Index loading**: < 1 second (from cache)
- **Search**: < 1 second (with embeddings)
- **Fix generation**: 2-5 seconds (LLM call)
- **Total per test**: 3-10 seconds

## License

See main project LICENSE file.
