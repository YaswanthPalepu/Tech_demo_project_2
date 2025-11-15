# Auto-Healing Test Loop

## Overview

The Auto-Healing Test Loop is a self-correcting system for AI-generated tests. It automatically detects and fixes errors in generated tests that are caused by LLM mistakes, ensuring higher test quality and reducing manual intervention.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Auto-Healing Loop                         │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
    ┌──────────────────────────────────────────────┐
    │ 1. Run pytest on tests/generated              │
    └──────────────────────────────────────────────┘
                            │
                            ▼
    ┌──────────────────────────────────────────────┐
    │ 2. Parse failures (pytest_failure_parser.py) │
    │    - Extract error details                    │
    │    - Get traceback & line numbers            │
    │    - Identify expected vs actual             │
    └──────────────────────────────────────────────┘
                            │
                            ▼
    ┌──────────────────────────────────────────────┐
    │ 3. Classify failures                          │
    │    - LLM mistakes (healable) ✓               │
    │    - Real bugs (not healable) ✗              │
    └──────────────────────────────────────────────┘
                            │
                            ▼
    ┌──────────────────────────────────────────────┐
    │ 4. Extract test code (test_ast_extractor.py) │
    │    - Parse test structure with AST           │
    │    - Get function/class source code          │
    └──────────────────────────────────────────────┘
                            │
                            ▼
    ┌──────────────────────────────────────────────┐
    │ 5. Get relevant source code                  │
    │    Option A: Full source files               │
    │    Option B: AST snippets (from analyzer.py) │
    └──────────────────────────────────────────────┘
                            │
                            ▼
    ┌──────────────────────────────────────────────┐
    │ 6. Send to LLM (test_healer.py)              │
    │    - Failing test code                       │
    │    - Error details & traceback               │
    │    - Relevant source code context            │
    └──────────────────────────────────────────────┘
                            │
                            ▼
    ┌──────────────────────────────────────────────┐
    │ 7. LLM generates corrected test              │
    └──────────────────────────────────────────────┘
                            │
                            ▼
    ┌──────────────────────────────────────────────┐
    │ 8. Replace failing test in file              │
    └──────────────────────────────────────────────┘
                            │
                            ▼
    ┌──────────────────────────────────────────────┐
    │ 9. Re-run pytest                             │
    └──────────────────────────────────────────────┘
                            │
                            ▼
    ┌──────────────────────────────────────────────┐
    │ 10. Check if tests pass                      │
    │     - All pass? → Done ✓                     │
    │     - Failures remain? → Repeat (max 3x)     │
    └──────────────────────────────────────────────┘
```

## Components

### 1. `test_ast_extractor.py`
Extracts test structure from `tests/generated` using AST parsing.

**Why separate from analyzer.py?**
- `analyzer.py` skips `tests/generated` directory (line 15, 40)
- Need dedicated AST extraction for generated test code
- Extracts: test functions, classes, methods, fixtures, imports

**Features:**
- Parse test files to extract structure
- Get source code of specific tests
- Find test locations across multiple files
- Extract parametrize decorators and fixtures

### 2. `pytest_failure_parser.py`
Parses pytest output to extract failure details.

**Extracts:**
- Test names and file locations
- Error types and messages
- Full tracebacks with line numbers
- Expected vs actual values (for assertions)
- Classifies failures as LLM mistakes or potential bugs

**LLM Mistake Detection:**
```python
# Automatically identifies LLM mistakes:
- Syntax errors in test code ✓
- Import errors for non-existent modules ✓
- Wrong function signatures ✓
- Incorrect mocking/patching ✓
- Wrong assertions in test setup ✓

# Not classified as LLM mistakes:
- Assertion failures in business logic ✗
- Real bugs in source code ✗
```

### 3. `test_healer.py`
Uses LLM to fix failing tests.

**Features:**
- Builds context-rich prompts for LLM
- Includes failing test + error + source code
- Supports two modes:
  - Full source: Include complete source files
  - AST mode: Include only relevant snippets
- Validates corrected code before replacement
- Retry logic with exponential backoff

### 4. `auto_healing_loop.py`
Orchestrates the complete healing workflow.

**Features:**
- Runs pytest and parses failures
- Heals LLM mistakes automatically
- Tracks healing progress across iterations
- Generates detailed session reports
- Stops when tests pass or max iterations reached

### 5. `integration.py`
Integrates healing with test generation workflow.

**Features:**
- One-command test generation + healing
- Seamless integration with existing system
- Configurable healing behavior
- Comprehensive result reporting

## Usage

### Option 1: Standalone Healing

```bash
# Run auto-healing on existing generated tests
python -m src.test_healing.auto_healing_loop --target ./target

# Custom settings
python -m src.test_healing.auto_healing_loop \
  --target ./target \
  --tests-dir tests/generated \
  --max-iterations 5 \
  --full-source
```

### Option 2: Integrated with Generation

```bash
# Generate tests AND auto-heal in one command
python -m src.test_healing.integration --target ./target

# With custom settings
python -m src.test_healing.integration \
  --target ./target \
  --max-iterations 3 \
  --force

# Disable healing
python -m src.test_healing.integration \
  --target ./target \
  --no-healing
```

### Option 3: Programmatic Usage

```python
from src.test_healing import AutoHealingLoop

loop = AutoHealingLoop(
    target_root="./target",
    generated_tests_dir="tests/generated",
    max_iterations=3,
    use_full_source=False  # Use AST snippets
)

session = loop.run_healing_loop()

if session.success:
    print(f"Healed {session.tests_healed} tests!")
```

## Configuration

### Source Code Context Modes

**AST Mode (Default - Recommended):**
```python
use_full_source=False
```
- Uses `analyzer.py` to extract relevant code snippets
- Faster and more focused
- Reduces token usage
- Better for large codebases

**Full Source Mode:**
```python
use_full_source=True
```
- Includes complete source files
- More context for LLM
- Better for complex dependencies
- Higher token usage

## How It Determines LLM Mistakes

The system identifies LLM mistakes using multiple heuristics:

### 1. Syntax Errors in Tests
```python
# Always LLM mistakes:
SyntaxError: invalid syntax
IndentationError: unexpected indent
```

### 2. Import Errors in Test Code
```python
# LLM mistake if error is in test file:
ImportError: cannot import name 'Foo'
ModuleNotFoundError: No module named 'bar'
```

### 3. Function Signature Errors
```python
# LLM mistake indicators:
TypeError: takes 2 positional arguments but 3 were given
TypeError: unexpected keyword argument 'foo'
TypeError: takes no arguments
```

### 4. Attribute Errors in Tests
```python
# LLM mistake if in test code:
AttributeError: has no attribute 'foo'
AttributeError: is not callable
```

### 5. Test Setup Errors
```python
# LLM mistake if related to mocking:
Error message contains: "mock", "patch", "fixture"
```

## AST Integration

### Why AST for Source Code?

The healing system uses AST in two ways:

1. **For Test Code** (`test_ast_extractor.py`):
   - Parses `tests/generated` (skipped by main analyzer)
   - Extracts test structure for precise replacement

2. **For Source Code** (`analyzer.py`):
   - Already analyzes source code
   - Reuses existing analysis
   - Provides focused context to LLM

### AST vs Full Source

| Aspect | AST Mode | Full Source |
|--------|----------|-------------|
| Speed | ✓ Fast | Slower |
| Tokens | ✓ Minimal | High |
| Context | Focused | Complete |
| Accuracy | Good | Better |
| Best For | Large projects | Complex dependencies |

## Output and Reports

### Session Report
Saved to `tests/generated/healing_session_report.json`:

```json
{
  "start_time": 1234567890,
  "end_time": 1234567950,
  "duration_seconds": 60,
  "total_iterations": 2,
  "max_iterations": 3,
  "initial_failures": 10,
  "final_failures": 0,
  "tests_healed": 10,
  "tests_failed_to_heal": 0,
  "success": true,
  "iterations": [
    {
      "iteration": 1,
      "total_failures": 10,
      "healable_failures": 8,
      "healed_tests": ["test_foo", "test_bar"],
      "failed_to_heal": [],
      "duration_seconds": 30
    }
  ]
}
```

### Console Output

```
🔧 AUTO-HEALING TEST LOOP STARTED
================================================================================
Target: ./target
Tests: tests/generated
Max Iterations: 3
Source Context: AST snippets
================================================================================

📊 Running initial test suite...
Initial failures: 10
Healable failures (LLM mistakes): 8
Non-healable failures (potential bugs): 2

================================================================================
🔄 Starting healing iterations...
================================================================================

================================================================================
ITERATION 1/3
================================================================================

[1/8] Healing: test_user_creation
  Error: ImportError: cannot import name 'User'
  ✅ Healed successfully

[2/8] Healing: test_login_validation
  Error: TypeError: takes 2 positional arguments but 3 were given
  ✅ Healed successfully

...

📋 AUTO-HEALING SESSION SUMMARY
================================================================================
Status: ✅ SUCCESS
Duration: 45.23 seconds
Iterations: 2/3

Initial Failures: 10
Final Failures: 2
Tests Healed: 8
Tests Failed to Heal: 0
Improvement: 8 fewer failures

Iteration Details:
--------------------------------------------------------------------------------
  Iteration 1:
    Healed: 5
    Failed: 0
    Duration: 25.50s
  Iteration 2:
    Healed: 3
    Failed: 0
    Duration: 19.73s
================================================================================
```

## Error Handling

### Healable vs Non-Healable

**Healable (LLM Mistakes):**
- ✓ Syntax errors in tests
- ✓ Import errors
- ✓ Wrong signatures
- ✓ Mocking errors
- ✓ Test setup issues

**Not Healable (Potential Bugs):**
- ✗ Business logic assertion failures
- ✗ Source code bugs
- ✗ Integration issues
- ✗ Data validation errors

### Max Iterations

Default: 3 iterations

**Why 3?**
- Most LLM mistakes fixed in 1-2 iterations
- Prevents infinite loops
- Balances time vs thoroughness

**Configurable:**
```bash
--max-iterations 5  # For stubborn failures
```

## Best Practices

### 1. Run After Initial Generation
```bash
# Generate tests first
python -m src.gen --target ./target

# Then heal
python -m src.test_healing.auto_healing_loop --target ./target
```

### 2. Use AST Mode for Large Projects
```bash
# Faster and more efficient
python -m src.test_healing.auto_healing_loop \
  --target ./large_project \
  --tests-dir tests/generated
```

### 3. Use Full Source for Complex Code
```bash
# More context for complex dependencies
python -m src.test_healing.auto_healing_loop \
  --target ./complex_app \
  --full-source
```

### 4. Review Non-Healable Failures
```bash
# Check final failures - they might be real bugs!
cat tests/generated/healing_session_report.json
```

## Integration with CI/CD

```yaml
# .github/workflows/test-generation.yml
name: Generate and Heal Tests

on: [push]

jobs:
  test-generation:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2

      - name: Generate and Heal Tests
        run: |
          python -m src.test_healing.integration \
            --target ./src \
            --max-iterations 3

      - name: Run Final Tests
        run: |
          pytest tests/generated -v

      - name: Upload Results
        uses: actions/upload-artifact@v2
        with:
          name: healing-report
          path: tests/generated/healing_session_report.json
```

## Troubleshooting

### Issue: Healing Loop Never Completes

**Solution:**
- Check if failures are actually LLM mistakes
- Review error classification logic
- Reduce max_iterations
- Use --full-source for more context

### Issue: Too Many Non-Healable Failures

**Solution:**
- These are likely real bugs in source code
- Fix source code first
- Or adjust LLM mistake detection heuristics

### Issue: LLM Generates Invalid Code

**Solution:**
- Check LLM model configuration
- Ensure source context is adequate
- Try --full-source mode
- Review prompt in test_healer.py

## FAQ

**Q: Will it fix bugs in my source code?**
A: No, it only fixes LLM mistakes in generated tests.

**Q: How does it know if it's an LLM mistake?**
A: It uses heuristics to classify errors. See "How It Determines LLM Mistakes".

**Q: Can I customize the classification?**
A: Yes, edit `pytest_failure_parser.py::_is_llm_mistake()`.

**Q: Why use AST instead of importing all code?**
A: AST is faster, uses fewer tokens, and avoids runtime errors.

**Q: Does analyzer.py work with tests/generated?**
A: No, analyzer.py skips tests/generated. That's why we have test_ast_extractor.py.

**Q: Can I run healing without regenerating tests?**
A: Yes! Use `auto_healing_loop.py` directly.

## Future Enhancements

- [ ] Parallel healing of independent failures
- [ ] Learning from successful healings
- [ ] Custom healing strategies per error type
- [ ] Integration with coverage reports
- [ ] Automatic PR creation for healed tests

## License

Part of the Tech Demo Project 2.
