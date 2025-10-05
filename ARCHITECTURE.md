# AI TestGen - Architecture Overview

## System Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                     ANY PYTHON PROJECT                          │
│  (Django / Flask / FastAPI / Plain Python / Any Framework)      │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                    1. CODE ANALYZER                             │
│                   (src/analyzer.py)                             │
│                                                                 │
│  • Complete AST traversal                                       │
│  • Captures: functions, classes, methods, async functions       │
│  • Tracks ALL code elements in all_targets[]                   │
│  • No filtering, no skipping                                    │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                 2. ANALYSIS PROCESSING                          │
│          (src/gen/enhanced_analysis_utils.py)                   │
│                                                                 │
│  • NO priority filtering (all targets equal)                    │
│  • Detect required packages from imports                        │
│  • Auto-install dependencies via pip                            │
│  • Prepare complete target list                                 │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│              3. CONTEXT GATHERING                               │
│           (src/gen/enhanced_generate.py)                        │
│                                                                 │
│  • Gather full file content for each target                     │
│  • Build comprehensive code context                             │
│  • Distribute targets evenly across test files                  │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                4. PROMPT GENERATION                             │
│            (src/gen/enhanced_prompt.py)                         │
│                                                                 │
│  • Build AI prompt with complete context                        │
│  • Emphasize REAL imports (no stubs)                            │
│  • Request 80%+ coverage                                        │
│  • Framework-agnostic instructions                              │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                  5. AI TEST GENERATION                          │
│              (OpenAI / Azure OpenAI API)                        │
│                                                                 │
│  • Generate comprehensive pytest tests                          │
│  • Use real imports from source code                            │
│  • Test all code paths and branches                             │
│  • Include edge cases and error handling                        │
│  • Retry logic with exponential backoff                         │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│               6. CODE VALIDATION                                │
│            (src/gen/postprocess.py)                             │
│                                                                 │
│  • Extract Python code from AI response                         │
│  • Validate syntax with AST parser                              │
│  • Ensure test functions exist                                  │
│  • Retry if validation fails                                    │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│              7. TEST FILE GENERATION                            │
│           (src/gen/enhanced_generate.py)                        │
│                                                                 │
│  • Save validated tests to tests/generated/                    │
│  • Create universal conftest.py                                 │
│  • Generate manifest.json with metadata                         │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                8. TEST EXECUTION                                │
│                   (pytest)                                      │
│                                                                 │
│  • Run generated tests                                          │
│  • Measure code coverage (80%+ target)                          │
│  • Generate HTML and XML reports                                │
└────────────────────────────┬────────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                9. COVERAGE REPORTS                              │
│                                                                 │
│  • htmlcov/index.html  → Visual coverage report                 │
│  • coverage.xml        → XML for CI/CD                          │
│  • Terminal output     → Quick summary                          │
└─────────────────────────────────────────────────────────────────┘
```

## Component Details

### 1. Code Analyzer (`src/analyzer.py`)
**Purpose**: Capture ALL code elements for complete coverage

**Input**: Python project directory
**Output**: Complete analysis JSON with all_targets[]

**Key Features**:
- Full AST traversal
- Captures functions, classes, methods
- No filtering or skipping
- Tracks file locations and line numbers

### 2. Analysis Processing (`src/gen/enhanced_analysis_utils.py`)
**Purpose**: Prepare targets and setup environment

**Key Features**:
- NO priority filtering (removed)
- Auto-detect required packages
- Auto-install dependencies
- All targets treated equally

### 3. Context Gathering (`src/gen/enhanced_generate.py`)
**Purpose**: Build comprehensive code context for AI

**Key Features**:
- Full file content (not snippets)
- Even distribution across test files
- Handles large codebases
- Maximum context for AI

### 4. Prompt Generation (`src/gen/enhanced_prompt.py`)
**Purpose**: Create AI prompts for test generation

**Key Features**:
- Emphasizes real imports
- Framework-agnostic
- 80%+ coverage target
- Comprehensive test instructions

### 5. AI Test Generation (OpenAI API)
**Purpose**: Generate actual test code

**Key Features**:
- Uses GPT models
- Retry logic (3 attempts)
- Exponential backoff
- Error handling

### 6. Code Validation (`src/gen/postprocess.py`)
**Purpose**: Ensure generated code is valid

**Key Features**:
- Extract Python from markdown
- AST syntax validation
- Test function verification
- Retry on failure

### 7. Test File Generation
**Purpose**: Save validated tests

**Output**:
```
tests/generated/
├── conftest.py                    # Universal fixtures
├── test_unit_TIMESTAMP_01.py      # Unit tests
├── test_unit_TIMESTAMP_02.py
├── test_integ_TIMESTAMP_01.py     # Integration tests
└── manifest.json                  # Metadata
```

### 8. Test Execution (pytest)
**Purpose**: Run tests and measure coverage

**Configuration**: `pytest.ini`
- 80% minimum coverage
- Branch coverage enabled
- HTML and XML reports

### 9. Coverage Reports
**Purpose**: Visualize test coverage

**Outputs**:
- `htmlcov/index.html` - Interactive HTML report
- `coverage.xml` - XML for CI/CD integration
- Terminal output - Quick summary

## Data Flow

```
Python Project
    ↓
[Analyzer] → analysis.json (all_targets)
    ↓
[Analysis Utils] → filtered_analysis + auto-installed packages
    ↓
[Context Gatherer] → full_context (complete file content)
    ↓
[Prompt Builder] → ai_prompt (with context)
    ↓
[OpenAI API] → raw_test_code
    ↓
[Validator] → validated_test_code
    ↓
[File Writer] → tests/generated/*.py
    ↓
[pytest] → coverage reports
```

## Key Design Decisions

### 1. No Priority Filtering
**Rationale**: Ensure complete coverage by testing ALL code elements equally

### 2. Real Imports
**Rationale**: Test actual code behavior, not mocked stubs

### 3. Auto Environment Setup
**Rationale**: Work with any project without manual configuration

### 4. Full Context
**Rationale**: Provide AI with complete information for better test generation

### 5. 80%+ Coverage Target
**Rationale**: Industry standard for comprehensive testing

### 6. Framework Agnostic
**Rationale**: Work with any Python project structure

## Configuration Files

### `pytest.ini`
```ini
[tool:pytest]
testpaths = tests/generated
addopts = --cov=. --cov-report=html --cov-report=xml --cov-fail-under=80
```

### `conftest.py` (Auto-generated)
```python
# Universal fixtures for all frameworks
# Auto-configures Django/Flask/FastAPI
# Provides permissive stubs when needed
```

## Environment Variables

```bash
# Required
AZURE_OPENAI_API_KEY          # OpenAI API key
AZURE_OPENAI_ENDPOINT         # API endpoint
AZURE_OPENAI_DEPLOYMENT       # Model deployment name

# Optional
TARGET_ROOT                   # Project to analyze (default: "target")
TESTGEN_FORCE                 # Force regeneration (default: false)
TESTGEN_DEBUG                 # Enable debug mode (default: false)
```

## Error Handling

```
Generation Attempt 1
    ↓ (fails)
Wait 2 seconds
    ↓
Generation Attempt 2 (with feedback)
    ↓ (fails)
Wait 4 seconds
    ↓
Generation Attempt 3 (with feedback)
    ↓ (fails)
Raise RuntimeError with details
```

## Success Metrics

- **Coverage**: 80%+ line and branch coverage
- **Test Quality**: Real imports, comprehensive test cases
- **Automation**: Zero manual configuration
- **Compatibility**: Works with any Python project
- **Reliability**: Retry logic handles transient failures

## Scalability

- **Small Projects** (<100 targets): Single test file per type
- **Medium Projects** (100-500 targets): Multiple test files, even distribution
- **Large Projects** (>500 targets): Sharded across many files, parallel execution possible

## Future Enhancements

1. **Dashboard**: FastAPI backend + React frontend for metrics visualization
2. **Parallel Generation**: Generate multiple test files concurrently
3. **Incremental Updates**: Only regenerate tests for changed code
4. **Custom Fixtures**: Learn from existing test patterns
5. **Coverage Optimization**: Iteratively improve low-coverage areas
