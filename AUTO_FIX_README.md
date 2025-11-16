# Auto-Fix Failing Tests Feature

## Overview

The auto-fix feature automatically detects and fixes failing pytest tests using LLM-powered analysis and code generation. When tests fail, the system analyzes the errors, understands the context, and generates corrected test code.

## How It Works

### Flow Diagram

```
AI Test Generation → Run pytest → Tests fail?
                                      ↓ YES
                          ┌──────────────────────────────┐
                          │ 1. Parse failed tests        │
                          │ 2. Extract error details     │
                          │    - Traceback               │
                          │    - Line numbers            │
                          │    - Expected vs actual      │
                          │ 3. Read failing test code    │
                          │ 4. Read source code context  │
                          │ 5. Send to LLM for fix       │
                          │ 6. Replace test file         │
                          │ 7. Re-run pytest             │
                          └──────────────────────────────┘
                                      ↓
                          Tests pass OR max iterations (3)?
                                      ↓
                                   SUCCESS
```

## Integration Points

The auto-fix is automatically triggered in `local_pipeline-1.sh` after each pytest run:

1. **Manual Tests** (line ~108-121)
   - Runs after manual test execution
   - Fixes any failing manual tests

2. **Combined Tests** (line ~246-260)
   - Runs after combined (manual + AI) test execution
   - Focuses on fixing AI-generated tests

3. **AI-Generated Tests Only** (line ~384-397)
   - Runs when only AI tests are available
   - Fixes failing AI-generated tests

## Configuration

### Environment Variables

- `CURRENT_DIR`: Current working directory (e.g., `/home/sigmoid/TECH_DEMO/new-tech-demo`)
- `TARGET_DIR`: Source code directory to test (e.g., `/home/sigmoid/test-repos/food-menu`)
- `MAX_ITERATIONS`: Maximum fix iterations (default: 3)

### Command Line Usage

```bash
# Standalone usage
python -m src.gen.auto_fix_tests \
  --test-dir "tests/generated" \
  --target-dir "$TARGET_DIR" \
  --current-dir "$CURRENT_DIR" \
  --max-iterations 3
```

### Pipeline Integration

Auto-fix is automatically enabled in the pipeline. No additional configuration needed.

## Features

### 1. Intelligent Error Parsing

- Extracts test failures from pytest JSON reports
- Fallback to parsing terminal output
- Captures full tracebacks and error messages
- Identifies line numbers and error types

### 2. Context-Aware Fixing

- Reads failing test code
- Identifies source files being tested
- Includes relevant source code in LLM prompt
- Maintains test integrity while fixing

### 3. Iterative Fixing

- Maximum 3 iterations by default
- Re-runs tests after each fix
- Stops when all tests pass
- Provides detailed progress reporting

### 4. Safety Features

- Never modifies source code (only test files)
- Validates Python syntax before saving
- Preserves existing test functions
- Maintains file structure and imports

## Output

### Success Output

```
🔧 AUTO-FIX FAILING TESTS
================================================================================
🔄 Iteration 1/3
================================================================================

🧪 Running pytest on tests/generated...
⚠️  Some tests failed (exit code: 1)

📋 Found 2 failing test(s):
  1. tests/generated/test_unit_20241116_01.py::test_user_creation
  2. tests/generated/test_unit_20241116_01.py::test_user_validation

🔧 Fixing test 1/2: test_user_creation
  🤖 Asking LLM to fix the test...
  ✅ Fixed and saved: tests/generated/test_unit_20241116_01.py

🔧 Fixing test 2/2: test_user_validation
  🤖 Asking LLM to fix the test...
  ✅ Fixed and saved: tests/generated/test_unit_20241116_01.py

✅ Fixed 2/2 test(s)
   Re-running pytest to verify fixes...

✅ SUCCESS! All tests passed on iteration 1
```

### Failure Output (Max Iterations)

```
⚠️  Max iterations (3) reached
   Some tests may still be failing
```

## Requirements

### Python Packages

- `pytest` - Test framework
- `pytest-json-report` - JSON output for parsing
- `pytest-cov` - Coverage reporting
- OpenAI client (configured in `src/gen/openai_client.py`)

Installation:
```bash
pip install pytest pytest-json-report pytest-cov
```

### LLM Configuration

Ensure your LLM API credentials are configured in the environment or config files used by `src/gen/openai_client.py`.

## Limitations

1. **Max Iterations**: Limited to 3 iterations to prevent infinite loops
2. **Source Code Read-Only**: Never modifies source code, only test files
3. **Context Size**: Limited to ~500 lines per source file to avoid token limits
4. **LLM Dependency**: Requires working LLM API connection

## Troubleshooting

### Auto-fix not triggering

1. Check that `pytest-json-report` is installed
2. Verify LLM API credentials are configured
3. Ensure test failures are actual failures (not skipped/xfailed)

### Fixes not working

1. Check LLM response quality in logs
2. Verify source code context is being read correctly
3. Increase max iterations if needed
4. Check for complex test scenarios requiring manual intervention

### Performance issues

1. Reduce number of source files included in context
2. Use more specific test directories
3. Consider running auto-fix on subsets of tests

## Best Practices

1. **Review Fixed Tests**: Always review auto-fixed tests to ensure correctness
2. **Commit Incrementally**: Commit after successful auto-fixes
3. **Monitor Iterations**: If reaching max iterations frequently, investigate root causes
4. **Manual Intervention**: Some complex tests may require manual fixes

## Files Modified

- `src/gen/auto_fix_tests.py` - Main auto-fix implementation
- `local_pipeline-1.sh` - Pipeline integration (3 locations)

## Future Enhancements

- [ ] Parallel fixing of multiple tests
- [ ] Learning from previous fixes
- [ ] Custom fix strategies per test type
- [ ] Integration with CI/CD pipelines
- [ ] Detailed fix reports and analytics
