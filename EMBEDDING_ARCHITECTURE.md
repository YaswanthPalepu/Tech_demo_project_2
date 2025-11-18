# Embedding-Based Bug Detection Architecture

## Problem Statement

**Current Issues:**
1. Unable to find target/source code using pattern matching
2. Cannot distinguish real bugs from test mistakes
3. Context size limitations (120KB truncation)
4. No semantic code understanding
5. Duplicate test scenarios not detected

## Solution: ChromaDB + Embeddings

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    EMBEDDING PIPELINE                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                   │
│  Source Code → Chunking → Embedding → ChromaDB Storage          │
│  Bug Patterns → Embedding → Bug Pattern Collection              │
│  Test Failures → Classification → Real Bug vs Test Issue        │
│                                                                   │
└─────────────────────────────────────────────────────────────────┘
```

## Components

### 1. **Code Embedding Pipeline**

**Purpose**: Create semantic representations of all code entities

**Process**:
```
Input: analyzer.py output (functions, classes, methods)
   ↓
Chunk: Individual code entities with context
   ↓
Embed: OpenAI text-embedding-3-small/large
   ↓
Store: ChromaDB collection "code_entities"
```

**Metadata Stored**:
- `file_path`: Source file location
- `entity_type`: function/class/method/route
- `name`: Entity name
- `line_start`, `line_end`: Source location
- `coverage_pct`: Current coverage percentage
- `is_covered`: Boolean coverage status
- `framework`: Detected framework (Django/Flask/FastAPI)
- `complexity`: Cyclomatic complexity score
- `dependencies`: Import dependencies

### 2. **Bug Pattern Database**

**Purpose**: Store known bug patterns for semantic matching

**Collections**:

#### A. **Historical Bugs** (`bug_patterns`)
- Embed: Stack traces, error messages, failing code
- Metadata: bug_type, severity, fix_description, file_pattern

#### B. **Common Vulnerabilities** (`security_patterns`)
- Embed: OWASP patterns (SQL injection, XSS, etc.)
- Metadata: vulnerability_type, severity, cwe_id

#### C. **Anti-Patterns** (`code_smells`)
- Embed: Code smell examples
- Metadata: smell_type, refactor_suggestion

### 3. **Semantic Search Layer**

**Purpose**: Replace pattern matching with embedding similarity

**Queries**:

```python
# Find similar uncovered code
similar_code = chroma.query(
    collection="code_entities",
    query_embeddings=embed(target_code),
    where={"is_covered": False},
    n_results=10
)

# Find related bug patterns
bug_matches = chroma.query(
    collection="bug_patterns",
    query_embeddings=embed(error_stacktrace),
    n_results=5
)

# Find relevant context for test generation
context = chroma.query(
    collection="code_entities",
    query_embeddings=embed(uncovered_function),
    where={"file_path": {"$ne": test_file}},
    n_results=20
)
```

### 4. **Bug Detection Engine**

**Purpose**: Classify issues and detect real bugs

**Classification Process**:

```
Test Failure → Extract Error Context
                    ↓
            Embed Error Pattern
                    ↓
        ┌───────────┴───────────┐
        ↓                       ↓
  Query Bug Patterns    Query Code Entities
        ↓                       ↓
  Similarity Score        Similarity Score
        ↓                       ↓
        └───────────┬───────────┘
                    ↓
            Decision Logic:

    • High bug pattern similarity (>0.85) → REAL BUG
    • High code similarity + low coverage → COVERAGE GAP
    • Low similarity overall → TEST MISTAKE
    • Security pattern match → SECURITY ISSUE
```

### 5. **Context Retrieval System**

**Purpose**: Intelligent context gathering for test generation

**Instead of truncating to 120KB:**

```python
# Old approach (truncation)
context = full_code[:120000]

# New approach (semantic retrieval)
context_chunks = chroma.query(
    collection="code_entities",
    query_embeddings=embed(target_function),
    n_results=50,  # Get 50 most relevant chunks
)
context = aggregate_relevant_context(context_chunks, max_tokens=16000)
```

**Benefits**:
- Get MOST RELEVANT code, not just first N bytes
- Include dependencies even if far away in file
- Include similar patterns from other files
- Prioritize by coverage gaps

## Implementation Plan

### Phase 1: Core Infrastructure

**Files to Create**:
1. `src/embeddings/chroma_client.py` - ChromaDB client wrapper
2. `src/embeddings/embedder.py` - Embedding generation (OpenAI)
3. `src/embeddings/code_indexer.py` - Index analyzer.py output
4. `src/embeddings/config.py` - ChromaDB configuration

### Phase 2: Bug Pattern Database

**Files to Create**:
1. `src/embeddings/bug_patterns.py` - Bug pattern definitions
2. `src/embeddings/pattern_loader.py` - Load patterns into ChromaDB
3. `data/bug_patterns.json` - Bug pattern data
4. `data/security_patterns.json` - Security vulnerability patterns

### Phase 3: Semantic Search Integration

**Files to Modify**:
1. `src/gen/enhanced_generate.py` - Use semantic context retrieval
2. `src/coverage_gap_analyzer.py` - Add similarity-based gap grouping
3. `src/test_generation/import_resolver.py` - Semantic module resolution

**Files to Create**:
1. `src/embeddings/semantic_search.py` - Search interface

### Phase 4: Bug Detection

**Files to Create**:
1. `src/embeddings/bug_detector.py` - Main bug detection logic
2. `src/embeddings/error_classifier.py` - Test vs bug classifier
3. `src/embeddings/vulnerability_scanner.py` - Security issue detector

**Files to Modify**:
1. `src/test_generation/orchestrator.py` - Integrate bug detection

### Phase 5: Pipeline Integration

**Files to Modify**:
1. `local_pipeline-1.sh` - Add embedding pipeline steps

**New Pipeline Flow**:
```bash
1. Clean coverage artifacts
2. Detect manual tests
3. **Index codebase into ChromaDB**  # NEW
4. **Load bug patterns**             # NEW
5. Run manual tests with coverage
6. Analyze coverage gaps
7. **Semantic gap clustering**       # NEW
8. **Bug pattern scanning**          # NEW
9. Gap-focused test generation (with semantic context)
10. **Classify test failures**       # NEW
11. Run combined tests
12. Verify coverage
```

## Technology Stack

### ChromaDB Configuration

```python
# Local persistent storage
chroma_client = chromadb.PersistentClient(
    path="./chroma_db"
)

# Collections
code_collection = client.get_or_create_collection(
    name="code_entities",
    metadata={"hnsw:space": "cosine"},
    embedding_function=openai_ef
)
```

### Embedding Model

**OpenAI `text-embedding-3-small`**:
- Dimensions: 1536
- Cost: $0.02 / 1M tokens
- Speed: ~5000 chunks/min
- Quality: Excellent for code

**Alternative**: `text-embedding-3-large`
- Dimensions: 3072
- Better accuracy, 2x cost

### Estimated Costs

**For 10,000 code entities (typical medium project)**:
- Embedding cost: ~$0.50-$1.00
- Storage: <100MB locally (ChromaDB)
- Query latency: <100ms per search

## Key Algorithms

### 1. **Code Chunking Strategy**

```python
def chunk_code_entity(entity, source_code):
    """
    Create embedding-ready chunk with context
    """
    chunk = f"""
Entity: {entity['type']} {entity['name']}
File: {entity['file']}
Lines: {entity['line_start']}-{entity['line_end']}

Code:
{entity['source']}

Dependencies: {', '.join(entity['imports'])}
Docstring: {entity.get('docstring', 'None')}
"""
    return chunk
```

### 2. **Bug Pattern Matching**

```python
def match_bug_patterns(error_context, threshold=0.80):
    """
    Find similar bug patterns
    """
    error_embedding = embedder.embed(error_context)

    results = chroma.query(
        collection="bug_patterns",
        query_embeddings=[error_embedding],
        n_results=10
    )

    matches = [
        {
            'pattern': r['metadata'],
            'similarity': r['distance'],
            'is_match': r['distance'] >= threshold
        }
        for r in results
    ]

    return matches
```

### 3. **Semantic Context Retrieval**

```python
def get_relevant_context(target_entity, max_tokens=10000):
    """
    Get most relevant context for test generation
    """
    # Embed target
    target_embedding = embedder.embed(target_entity['source'])

    # Find similar code
    similar = chroma.query(
        collection="code_entities",
        query_embeddings=[target_embedding],
        n_results=100,
        where={
            "file_path": {"$ne": target_entity['file']},  # Different file
        }
    )

    # Find dependencies
    deps = chroma.query(
        collection="code_entities",
        query_embeddings=[target_embedding],
        where={
            "name": {"$in": target_entity['imports']}
        },
        n_results=20
    )

    # Combine and rank
    context_chunks = rank_by_relevance(similar, deps, target_entity)

    # Aggregate within token limit
    return aggregate_chunks(context_chunks, max_tokens)
```

### 4. **Bug vs Test Error Classification**

```python
def classify_failure(test_failure):
    """
    Classify test failure as bug or test issue
    """
    error_embedding = embedder.embed(test_failure['error_msg'])

    # Check bug patterns
    bug_matches = chroma.query(
        collection="bug_patterns",
        query_embeddings=[error_embedding],
        n_results=5
    )

    # Check code patterns
    code_matches = chroma.query(
        collection="code_entities",
        query_embeddings=[error_embedding],
        where={"file_path": test_failure['source_file']},
        n_results=5
    )

    # Decision logic
    if max(bug_matches['distances']) > 0.85:
        return {
            'type': 'REAL_BUG',
            'confidence': max(bug_matches['distances']),
            'similar_bugs': bug_matches['metadatas']
        }
    elif test_failure['error_type'] in ['ImportError', 'AttributeError']:
        return {
            'type': 'TEST_MISTAKE',
            'confidence': 0.9,
            'reason': 'Import/attribute errors usually indicate test issues'
        }
    elif max(code_matches['distances']) > 0.75:
        return {
            'type': 'COVERAGE_GAP',
            'confidence': max(code_matches['distances']),
            'uncovered_code': code_matches['metadatas']
        }
    else:
        return {
            'type': 'UNKNOWN',
            'confidence': 0.5,
            'needs_manual_review': True
        }
```

## Benefits Summary

| Issue | Current Approach | Embedding Approach |
|-------|------------------|-------------------|
| **Finding target code** | Pattern matching paths | Semantic similarity search |
| **Context retrieval** | Truncate to 120KB | Retrieve most relevant chunks |
| **Bug detection** | Manual inspection | Automatic pattern matching |
| **Test vs bug** | Cannot distinguish | Classify with confidence score |
| **Duplicate tests** | No detection | Find similar test scenarios |
| **Module resolution** | Heuristic path matching | Semantic import resolution |
| **Gap prioritization** | Coverage % only | Coverage + bug likelihood |
| **Security issues** | Not detected | Automatic vulnerability scanning |

## Migration Path

**Step 1**: Add ChromaDB alongside existing system (no breaking changes)
**Step 2**: Index codebase and populate collections
**Step 3**: Add semantic search as alternative to pattern matching
**Step 4**: Gradually replace pattern matching with semantic search
**Step 5**: Add bug detection and classification
**Step 6**: Full integration with test generation pipeline

## Performance Considerations

**Indexing Time**:
- Small project (1K entities): ~2-3 minutes
- Medium project (10K entities): ~15-20 minutes
- Large project (50K entities): ~1-2 hours

**Query Performance**:
- Single similarity search: 50-100ms
- Batch search (10 queries): 200-300ms
- Full bug scan: 1-2 seconds

**Storage**:
- 1K entities: ~10MB
- 10K entities: ~100MB
- 50K entities: ~500MB

**Recommendations**:
- Index once, query many times
- Use incremental updates for changed files
- Cache embeddings for unchanged code
- Run full re-index weekly or on major changes

## Next Steps

1. Install dependencies (`chromadb`, `openai`)
2. Implement core infrastructure (Phase 1)
3. Create initial bug pattern database (Phase 2)
4. Test semantic search on current codebase
5. Integrate with existing pipeline
6. Measure accuracy improvements
