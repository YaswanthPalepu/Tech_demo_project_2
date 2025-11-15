# Quick Start: Auto-Healing Test Loop

## What is Auto-Healing?

The Auto-Healing Test Loop automatically fixes errors in AI-generated tests caused by LLM mistakes. It:

1. ✅ Detects test failures
2. ✅ Classifies errors (LLM mistake vs real bug)
3. ✅ Fixes LLM mistakes automatically
4. ✅ Re-runs tests until they pass
5. ✅ Reports results

## Quick Start (3 Commands)

### 1. Generate Tests (if not already done)

```bash
python -m src.gen --target ./target
```

### 2. Run Auto-Healing

```bash
python -m src.test_healing.auto_healing_loop --target ./target
```

### 3. Check Results

```bash
# View healing report
cat tests/generated/healing_session_report.json

# Run tests to verify
pytest tests/generated -v
```

## Or Use Integrated Workflow (1 Command)

```bash
# Generate AND heal in one command
python -m src.test_healing.integration --target ./target
```

## Understanding the Output

```
🔧 AUTO-HEALING TEST LOOP STARTED
================================================================================

📊 Running initial test suite...
Initial failures: 10                    ← Total failures found
Healable failures (LLM mistakes): 8     ← Can be auto-fixed
Non-healable failures: 2                ← Potential real bugs

================================================================================
ITERATION 1/3
================================================================================

[1/8] Healing: test_user_creation
  Error: ImportError: cannot import name 'User'
  ✅ Healed successfully                ← Fixed!

...

📋 AUTO-HEALING SESSION SUMMARY
Status: ✅ SUCCESS
Tests Healed: 8                         ← 8 tests fixed
Final Failures: 2                       ← 2 remain (real bugs?)
```

## What Gets Fixed Automatically?

### ✅ Healable (LLM Mistakes)

- **Syntax Errors**: Invalid Python syntax in tests
- **Import Errors**: Wrong imports or non-existent modules
- **Signature Errors**: Wrong number of arguments
- **Mocking Errors**: Incorrect mock setup
- **Test Setup**: Wrong fixtures or decorators

### ❌ Not Healable (Potential Real Bugs)

- **Business Logic**: Failed assertions about actual behavior
- **Source Code Bugs**: Errors in the code being tested
- **Integration Issues**: Database, API, external service errors

## Common Use Cases

### Use Case 1: After Generating New Tests

```bash
# Step 1: Generate tests
python -m src.gen --target ./myapp

# Step 2: Heal any LLM mistakes
python -m src.test_healing.auto_healing_loop --target ./myapp

# Step 3: Run tests
pytest tests/generated -v
```

### Use Case 2: One-Command Generation + Healing

```bash
python -m src.test_healing.integration \
  --target ./myapp \
  --max-iterations 3
```

### Use Case 3: Healing Existing Tests

```bash
# If you already have generated tests with failures
python -m src.test_healing.auto_healing_loop \
  --target ./myapp \
  --tests-dir tests/generated
```

## Configuration Options

### Max Iterations (Default: 3)

```bash
# More iterations for stubborn failures
python -m src.test_healing.auto_healing_loop \
  --target ./target \
  --max-iterations 5
```

### Source Context Mode

```bash
# Use full source files (slower, more context)
python -m src.test_healing.auto_healing_loop \
  --target ./target \
  --full-source
```

### Disable Healing

```bash
# Just generate, don't heal
python -m src.test_healing.integration \
  --target ./target \
  --no-healing
```

## Understanding AST vs Full Source

### AST Mode (Default - Recommended)

```bash
# Uses analyzer.py to extract relevant code snippets
python -m src.test_healing.auto_healing_loop --target ./target
```

**Pros:**
- ✓ Faster
- ✓ Lower token usage
- ✓ Good for large codebases

**Use when:**
- Codebase is large
- Want faster healing
- Tests have clear dependencies

### Full Source Mode

```bash
# Includes complete source files
python -m src.test_healing.auto_healing_loop \
  --target ./target \
  --full-source
```

**Pros:**
- ✓ More context for LLM
- ✓ Better for complex dependencies
- ✓ Higher accuracy

**Use when:**
- Tests have complex dependencies
- AST mode doesn't provide enough context
- Accuracy is more important than speed

## How It Works (Simple Explanation)

```
1. pytest runs → finds failures
2. Parser extracts error details
3. Classifier: Is this an LLM mistake?
   ├─ Yes → Extract test code
   │         ├─ Get source context (AST or full)
   │         ├─ Send to LLM with error details
   │         ├─ LLM generates fixed test
   │         └─ Replace failing test
   └─ No → Skip (might be real bug)
4. Re-run pytest
5. Repeat until pass or max iterations
```

## Example Session

```bash
$ python -m src.test_healing.integration --target ./myapp

🚀 Starting Test Generation with Auto-Healing
================================================================================

📝 Step 1: Generating tests...
✅ Generated 5 test files

🔧 Step 2: Running auto-healing loop...

🔧 AUTO-HEALING TEST LOOP STARTED
================================================================================

📊 Running initial test suite...
Initial failures: 7
Healable failures (LLM mistakes): 5
Non-healable failures (potential bugs): 2

================================================================================
ITERATION 1/3
================================================================================

[1/5] Healing: test_user_login
  Error: ImportError: cannot import name 'authenticate'
  ✅ Healed successfully

[2/5] Healing: test_create_post
  Error: TypeError: takes 2 positional arguments but 3 were given
  ✅ Healed successfully

[3/5] Healing: test_delete_comment
  Error: AttributeError: 'Mock' object has no attribute 'user'
  ✅ Healed successfully

[4/5] Healing: test_api_response
  Error: SyntaxError: invalid syntax
  ✅ Healed successfully

[5/5] Healing: test_validation
  Error: NameError: name 'validator' is not defined
  ✅ Healed successfully

🔍 Re-running tests after healing 5 tests...
Remaining failures: 2 (healable: 0)

✅ All healable tests fixed!

📋 AUTO-HEALING SESSION SUMMARY
================================================================================
Status: ✅ SUCCESS
Duration: 67.89 seconds
Iterations: 1/3

Initial Failures: 7
Final Failures: 2
Tests Healed: 5
Tests Failed to Heal: 0
Improvement: 5 fewer failures
================================================================================

📊 FINAL SUMMARY
================================================================================

Test Generation:
  ✅ Success - 5 files

Auto-Healing:
  ✅ Success
     Initial failures: 7
     Final failures: 2
     Tests healed: 5

Overall Status:
  ✅ SUCCESS - Tests generated and healed
================================================================================

💾 Session report saved to: tests/generated/healing_session_report.json
```

## What About the 2 Remaining Failures?

Those 2 failures are **not LLM mistakes** - they might be:

1. **Real bugs in your source code** → Fix the source code
2. **Valid test failures** → Your code doesn't match expected behavior
3. **Integration issues** → Missing database, API, etc.

**Action:** Review these failures manually:

```bash
pytest tests/generated -v --tb=short
```

## Quick Troubleshooting

### Problem: "No healable failures found"

**Cause:** All failures are real bugs, not LLM mistakes

**Solution:**
- Fix source code bugs first
- Or review error classification logic

### Problem: "Healing failed"

**Cause:** LLM couldn't generate valid fix

**Solution:**
- Try `--full-source` for more context
- Increase `--max-iterations`
- Check OpenAI API key and model

### Problem: "Tests pass but coverage is low"

**Cause:** Healing fixed syntax but tests might be shallow

**Solution:**
- Run coverage analysis
- Generate more comprehensive tests
- Use gap-focused mode

## Best Practices

1. **Always heal after generation**
   ```bash
   python -m src.test_healing.integration --target ./app
   ```

2. **Review non-healable failures**
   - They're likely real bugs!
   - Fix source code if needed

3. **Use AST mode for speed**
   ```bash
   # Default is AST mode - it's faster
   ```

4. **Use full source for accuracy**
   ```bash
   # When AST mode isn't enough
   --full-source
   ```

5. **Check session report**
   ```bash
   cat tests/generated/healing_session_report.json
   ```

## Next Steps

1. ✅ Generate tests: `python -m src.gen --target ./target`
2. ✅ Run healing: `python -m src.test_healing.auto_healing_loop --target ./target`
3. ✅ Review report: `cat tests/generated/healing_session_report.json`
4. ✅ Fix remaining bugs (if any)
5. ✅ Run final tests: `pytest tests/generated -v`
6. ✅ Check coverage: `pytest tests/generated --cov=. --cov-report=html`

## Need Help?

See detailed documentation:
- `src/test_healing/README.md` - Complete documentation
- `src/test_healing/integration.py` - Integration options
- `src/test_healing/auto_healing_loop.py` - Core logic

Or run with `--help`:
```bash
python -m src.test_healing.auto_healing_loop --help
python -m src.test_healing.integration --help
```

## Summary

The Auto-Healing Test Loop makes AI-generated tests production-ready by:

✅ Automatically fixing LLM mistakes
✅ Preserving real bug detection
✅ Providing detailed reports
✅ Working with existing workflow
✅ Being fast and efficient

**One command to rule them all:**
```bash
python -m src.test_healing.integration --target ./your-project
```

Happy healing! 🔧✨
