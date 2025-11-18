# Embedding-Based Bug Detection - Usage Guide

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Set Up Environment Variables

Create a `.env` file or export variables:

```bash
# OpenAI API (required for embeddings)
export OPENAI_API_KEY="your-api-key"

# Optional: ChromaDB path (default: ./chroma_db)
export CHROMA_DB_PATH="./chroma_db"

# Optional: Embedding model (default: text-embedding-3-small)
export EMBEDDING_MODEL="text-embedding-3-small"
```

### 3. Index Your Codebase

First, run the analyzer and coverage:

```bash
# Run your existing analysis
python -m src.analyzer /path/to/your/code > analysis.json

# Run coverage (if you have manual tests)
pytest --cov=app --cov-report=xml

# Analyze coverage gaps
python -m src.coverage_gap_analyzer
```

Then index into ChromaDB:

```bash
# Index codebase with coverage data
python -m src.embeddings.cli index analysis.json --coverage-file coverage_gaps.json
```

**Output:**
```
=== Indexing Complete ===
Total entities: 156
Indexed: 156
Updated: 0
Skipped: 0

Embedding cache hit rate: 0.0%
Total tokens used: 45,231
```

### 4. Scan for Bugs

```bash
# Scan entire project
python -m src.embeddings.cli scan

# Scan specific file
python -m src.embeddings.cli scan --file app/main.py

# Only high-severity issues
python -m src.embeddings.cli scan --min-severity high

# Save results to JSON
python -m src.embeddings.cli scan --output bug_report.json --format json
```

**Output:**
```
=== Project-Wide Scan Results ===
Entities scanned: 156
Issues found: 8
Files with issues: 3

app/auth.py
  Bugs: 2, Security: 1
  - validate_password (lines 45-58)
    [SECURITY] Weak Cryptography (high)
  - login_user (lines 112-145)
    [BUG] Missing Return Statement (medium)

app/main.py
  Bugs: 3, Security: 2
  - process_payment (lines 234-267)
    [SECURITY] Missing Authentication Check (critical)
    [BUG] Division by Zero (high)
```

### 5. Classify Test Errors

When tests fail, classify them:

```bash
# Prepare test failures JSON (see format below)
python -m src.embeddings.cli classify test_failures.json

# Detailed output
python -m src.embeddings.cli classify test_failures.json --format detailed

# Save classification results
python -m src.embeddings.cli classify test_failures.json --output classification_results.json
```

**Test Failures JSON Format:**
```json
[
  {
    "test_name": "test_user_login",
    "error_type": "AssertionError",
    "error_message": "assert response.status_code == 200 but got 401",
    "stacktrace": "...",
    "source_file": "app/auth.py",
    "test_file": "tests/test_auth.py"
  },
  {
    "test_name": "test_import_utils",
    "error_type": "ImportError",
    "error_message": "cannot import name 'helper_func' from 'app.utils'",
    "source_file": "app/utils.py",
    "test_file": "tests/test_utils.py"
  }
]
```

**Output:**
```
=== Test Error Classification ===
Total failures: 12
Real bugs: 5
Test mistakes: 6
Coverage gaps: 1
Security issues: 0
Unknown: 0

=== Recommendations ===
• Review and fix 6 test issue(s) (imports, fixtures, expectations)
• Fix 5 real bug(s) in source code before proceeding
• Improve test coverage for 1 uncovered code path(s)
• Priority: Focus on fixing test code issues
```

### 6. Semantic Search

```bash
# Search for code by query
python -m src.embeddings.cli search "authentication and password validation"

# Find similar entities
python -m src.embeddings.cli similar validate_password app/auth.py

# Search by natural language description
python -m src.embeddings.cli describe "function that handles user login" --entity-type function

# Search only uncovered code
python -m src.embeddings.cli search "database queries" --include-covered=false
```

**Output:**
```
=== Search Results (5 matches) ===

1. validate_password (function)
   File: app/auth.py:45
   Similarity: 0.912
   Covered: True (coverage: 85.7%)

2. check_password_strength (function)
   File: app/utils.py:112
   Similarity: 0.876
   Covered: False (coverage: 0.0%)

3. authenticate_user (function)
   File: app/auth.py:178
   Similarity: 0.834
   Covered: True (coverage: 100.0%)
```

## Advanced Usage

### Python API

You can also use the Python API directly:

```python
from src.embeddings import (
    ChromaClient,
    Embedder,
    CodeIndexer,
    BugDetector,
    ErrorClassifier,
    SemanticSearch,
)

# Initialize
chroma = ChromaClient()
embedder = Embedder()

# Index codebase
indexer = CodeIndexer(chroma, embedder)
stats = indexer.index_from_file("analysis.json", "coverage_gaps.json")

# Scan for bugs
detector = BugDetector(chroma, embedder)
results = detector.scan_project(min_severity="high")

# Classify errors
classifier = ErrorClassifier(chroma, embedder)
classification = classifier.classify_error(
    error_type="AssertionError",
    error_message="Expected 200 but got 404",
    stacktrace="...",
    source_file="app/api.py",
)

print(f"Classification: {classification['classification']}")
print(f"Confidence: {classification['confidence']:.2f}")
print(f"Action: {classification['suggested_action']}")

# Semantic search
search = SemanticSearch(chroma, embedder)
results = search.search_code("user authentication", n_results=10)

# Find relevant context for test generation
context = search.get_relevant_context(
    target_code="def process_payment(amount, account): ...",
    exclude_file="app/payments.py",
)
```

### Integration with Test Generation

```python
from src.embeddings import SemanticSearch
from src.gen.enhanced_generate import generate_tests

# Initialize search
search = SemanticSearch()

# Get relevant context instead of truncating
target_function = """
def calculate_discount(price, user_tier):
    if user_tier == 'premium':
        return price * 0.8
    return price * 0.95
"""

# Retrieve semantically relevant context
context_chunks = search.get_relevant_context(
    target_code=target_function,
    max_results=20,
)

# Build context from most relevant chunks
context = "\n\n".join([
    f"# {chunk['file_path']}:{chunk['line_start']}\n{chunk['content']}"
    for chunk in context_chunks
])

# Now generate tests with rich, relevant context
# instead of truncated first 120KB
tests = generate_tests(target_function, context)
```

## Configuration

### Environment Variables

```bash
# ChromaDB
CHROMA_DB_PATH=./chroma_db              # Storage path
DISTANCE_METRIC=cosine                  # cosine, l2, ip

# Embedding
EMBEDDING_MODEL=text-embedding-3-small  # OpenAI model
EMBEDDING_BATCH_SIZE=100                # Batch size
ENABLE_EMBEDDING_CACHE=true             # Enable caching

# Similarity Thresholds
SIMILARITY_THRESHOLD_BUG=0.80           # Bug pattern matching
SIMILARITY_THRESHOLD_CODE=0.75          # Code similarity
SIMILARITY_THRESHOLD_SECURITY=0.85      # Security pattern matching

# Context Retrieval
MAX_CONTEXT_TOKENS=10000                # Max tokens in context
MAX_CONTEXT_CHUNKS=50                   # Max number of chunks

# Performance
MAX_WORKERS=4                           # Parallel workers
ENABLE_INCREMENTAL_UPDATE=true          # Incremental indexing
```

## Pipeline Integration

### Updated Pipeline Flow

```bash
#!/bin/bash
# Enhanced pipeline with embeddings

# 1. Clean and setup
rm -rf coverage_gaps.json analysis.json

# 2. Detect manual tests
python -m src.detect_manual_tests

# 3. Analyze codebase
python -m src.analyzer . > analysis.json

# 4. INDEX INTO CHROMADB (NEW)
python -m src.embeddings.cli index analysis.json

# 5. SCAN FOR BUGS (NEW)
python -m src.embeddings.cli scan --min-severity medium --output bug_scan.json

# 6. Run manual tests with coverage
if [ -f manual_test_result.json ]; then
    pytest -v --cov=app --cov-report=xml $(cat manual_test_result.json | jq -r '.manual_test_paths[]')
fi

# 7. Analyze coverage gaps
python -m src.coverage_gap_analyzer

# 8. UPDATE INDEX WITH COVERAGE (NEW)
python -m src.embeddings.cli index analysis.json --coverage-file coverage_gaps.json

# 9. Generate tests for gaps
if [ -f coverage_gaps.json ]; then
    export GAP_FOCUSED_MODE=true
    python -m src.gen
fi

# 10. Run all tests and capture failures
pytest -v --tb=short --json-report --json-report-file=test_results.json

# 11. CLASSIFY TEST FAILURES (NEW)
if [ -f test_results.json ]; then
    # Convert pytest JSON to classification format
    python scripts/convert_test_results.py test_results.json > test_failures.json

    # Classify errors
    python -m src.embeddings.cli classify test_failures.json --output classification.json

    # Show recommendations
    cat classification.json | jq '.recommendations[]'
fi

# 12. Final coverage check
pytest --cov=app --cov-report=html --cov-report=term
```

## Common Workflows

### Workflow 1: First-Time Setup

```bash
# 1. Index codebase
python -m src.embeddings.cli index analysis.json

# 2. Run initial bug scan
python -m src.embeddings.cli scan --output initial_scan.json

# 3. Review and fix critical issues
cat initial_scan.json | jq '.files_with_issues[] | select(.total_security > 0)'

# 4. Re-index after fixes
python -m src.embeddings.cli index analysis.json --reset
```

### Workflow 2: Incremental Updates

```bash
# After code changes, just re-index (incremental)
python -m src.embeddings.cli index analysis.json --coverage-file coverage_gaps.json

# Only changed files will be re-indexed
# Unchanged files use cached embeddings
```

### Workflow 3: Debug Test Failures

```bash
# 1. Run tests and capture failures
pytest --json-report --json-report-file=results.json

# 2. Convert to classification format
python scripts/convert_test_results.py results.json > failures.json

# 3. Classify
python -m src.embeddings.cli classify failures.json --format detailed

# 4. Focus on real bugs first
cat failures.json | jq '.classifications[] | select(.classification == "REAL_BUG")'
```

### Workflow 4: Find Similar Uncovered Code

```python
from src.embeddings import SemanticSearch

search = SemanticSearch()

# Find what to test next based on what's already tested
covered_function = """
def authenticate_user(username, password):
    user = db.get_user(username)
    if user and verify_password(password, user.password_hash):
        return create_session(user)
    return None
"""

# Find similar uncovered code
similar = search.find_uncovered_similar_to(covered_function, n_results=5)

for entity in similar:
    print(f"Test {entity['entity_name']} in {entity['file_path']}")
    print(f"  Similarity: {entity['similarity']:.2f}")
    print(f"  Coverage: {entity['coverage_pct']:.1f}%")
```

## Performance Tips

1. **Use Caching**: Enable `ENABLE_EMBEDDING_CACHE=true` to cache embeddings
2. **Incremental Updates**: Keep `ENABLE_INCREMENTAL_UPDATE=true` for faster re-indexing
3. **Batch Size**: Increase `EMBEDDING_BATCH_SIZE` for faster initial indexing
4. **Model Choice**: Use `text-embedding-3-small` for cost/speed, `text-embedding-3-large` for accuracy

## Troubleshooting

### Issue: "No indexed entities found"

**Solution**: Run indexing first:
```bash
python -m src.embeddings.cli index analysis.json
```

### Issue: "OpenAI API key not found"

**Solution**: Set environment variable:
```bash
export OPENAI_API_KEY="sk-..."
```

### Issue: Slow indexing

**Solution**: Enable caching and increase batch size:
```bash
export ENABLE_EMBEDDING_CACHE=true
export EMBEDDING_BATCH_SIZE=200
```

### Issue: High embedding costs

**Solution**:
- Use caching (embeds are cached after first run)
- Use `text-embedding-3-small` instead of `large`
- Enable incremental updates (only re-embeds changed files)

## Cost Estimation

For a typical project:

| Project Size | Entities | First Index Cost | Incremental Cost |
|--------------|----------|------------------|------------------|
| Small (1K)   | ~500     | $0.10-$0.20     | $0.01-$0.02     |
| Medium (10K) | ~5,000   | $1.00-$2.00     | $0.10-$0.20     |
| Large (50K)  | ~25,000  | $5.00-$10.00    | $0.50-$1.00     |

**Notes:**
- Using `text-embedding-3-small` ($0.02 / 1M tokens)
- With caching enabled, subsequent runs are nearly free
- Incremental updates only process changed files

## Next Steps

1. **Review** the architecture document: `EMBEDDING_ARCHITECTURE.md`
2. **Run** the initial indexing and bug scan
3. **Integrate** with your CI/CD pipeline
4. **Customize** bug patterns in `data/bug_patterns.json`
5. **Add** security patterns in `data/security_patterns.json`
