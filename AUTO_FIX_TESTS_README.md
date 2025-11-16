# Auto-Fix Tests - Enhanced Documentation

## Overview

The `auto_fix_tests.py` module automatically fixes failing tests using LLM assistance with comprehensive logging and validation to track the LLM's behavior and decision-making process.

## Key Features

### 1. **Comprehensive Error Handling**

The module now properly handles all pytest exit codes:

- **Exit Code 0**: All tests passed ✅
- **Exit Code 1**: Some tests failed (fixable)
- **Exit Code 2**: Test collection/execution error (syntax errors, import errors, Django config issues)
- **Exit Code 3**: Internal pytest error
- **Exit Code 4**: Command line usage error
- **Exit Code 5**: No tests collected

### 2. **Enhanced Logging & Visibility**

Track exactly what the LLM is doing with detailed logging:

```
🔧 AUTO-FIX FAILING TESTS
================================================================================

🔄 Iteration 1/3
================================================================================

🧪 Running pytest on tests/generated...
⚠️  Some tests failed (exit code: 1 - Some tests failed)

📋 Found 31 failing test(s):
  1. tests/generated/test_integ_20251115_131946_01.py::test_contactsform_and_contactflow
  ...

🔧 Fixing test 1/31: test_contactsform_and_contactflow
  🤖 Asking LLM to fix the test...
  🔍 [DEBUG] LLM Request for: test_contactsform_and_contactflow
  🔍 [DEBUG] Error: AssertionError: ...
  🔍 [DEBUG] Prompt preview: Fix the following failing test...
  🔍 [DEBUG] LLM Response length: 2453 chars
  🔍 [DEBUG] Validation: {
    "has_code": true,
    "has_imports": true,
    "has_test_function": true,
    "is_complete": true
  }
  ✅ Fixed and saved: /path/to/test_file.py
```

### 3. **LLM Response Validation**

Every LLM response is validated to ensure quality:

- ✓ Has code content
- ✓ Has necessary imports
- ✓ Has test function definition
- ✓ Has pytest markers
- ✓ No syntax errors
- ✓ Complete and valid Python code

### 4. **Detailed Behavior Analysis**

At the end of execution, you get a complete summary:

```
🔬 LLM BEHAVIOR ANALYSIS
================================================================================

Total LLM interactions: 31

1. Test: test_contactsform_and_contactflow
   Prompt length: 2341 chars
   Response length: 2453 chars
   Validation:
     - Has code: True
     - Has imports: True
     - Has test function: True
     - Is complete: True

2. Test: test_ctreateItem_update_and_delete_views_workflow
   ...
```

This helps you understand:
- Whether the LLM is following all steps correctly
- If the LLM is generating complete, valid code
- Where the LLM might be making mistakes

## Usage

### Basic Usage

```bash
python -m src.gen.auto_fix_tests \
  --test-dir "tests/generated" \
  --max-iterations 3
```

### With Project Directories

```bash
python -m src.gen.auto_fix_tests \
  --test-dir "tests/generated" \
  --target-dir "$TARGET_DIR" \
  --current-dir "$CURRENT_DIR" \
  --max-iterations 3
```

### Quiet Mode (Less Verbose)

```bash
python -m src.gen.auto_fix_tests \
  --test-dir "tests/generated" \
  --quiet
```

## Prerequisites

### Required Python Package

The module requires `pytest-json-report` for structured test results:

```bash
pip install pytest-json-report
```

### Environment Variables

Ensure your Azure OpenAI credentials are set:

```bash
export AZURE_OPENAI_KEY="your-key"
export AZURE_OPENAI_ENDPOINT="your-endpoint"
export AZURE_OPENAI_DEPLOYMENT="your-deployment"
```

## How It Works

### 1. **Test Execution**

Runs pytest with JSON reporting:
```bash
pytest tests/generated/ --json-report --json-report-file=.pytest_report.json
```

### 2. **Failure Analysis**

Parses the JSON report to extract:
- Test node ID (file path + test name)
- Error messages and tracebacks
- Test metadata

### 3. **LLM Fix Generation**

For each failing test:
1. Reads the entire test file
2. Sends a structured prompt to the LLM:
   - System: Expert test engineer instructions
   - User: Test code + error + requirements
3. Validates the LLM response
4. Writes the fixed code back

### 4. **Iterative Refinement**

Re-runs pytest after each round of fixes, up to `max-iterations` times.

## Troubleshooting Common Issues

### Exit Code 2: Collection/Execution Error

This usually indicates:

**Syntax Errors in Generated Tests:**
```python
# Check the debug output for:
🔍 [DEBUG] === STDOUT ===
SyntaxError: invalid syntax
```

**Import Errors:**
```python
# Common causes:
- Missing test dependencies
- Incorrect import paths
- Django settings not configured
```

**Django Configuration:**
```bash
# Ensure DJANGO_SETTINGS_MODULE is set
export DJANGO_SETTINGS_MODULE=your_project.settings
```

### Exit Code 5: No Tests Collected

Check:
- Test directory exists and is not empty
- Test files follow pytest naming conventions (`test_*.py` or `*_test.py`)
- Test functions follow naming conventions (`test_*`)

### LLM Not Following Steps

Check the LLM Behavior Analysis section:

```
Validation:
  - Has code: True
  - Has imports: True
  - Has test function: False  ← Problem!
  - Is complete: False
```

If validation fails:
1. Check the debug logs for the actual LLM response
2. Verify your Azure OpenAI deployment is working correctly
3. Check token limits (default: 4000 tokens for response)

## Determining if it's an LLM Mistake

### Signs of LLM Issues:

1. **Incomplete Responses:**
   ```
   Validation: is_complete: False
   ```

2. **Missing Critical Components:**
   ```
   Validation: has_test_function: False
   ```

3. **Syntax Errors:**
   ```
   Validation: has_syntax_errors: True
   ```

### Signs of Configuration Issues:

1. **Exit Code 2 with Import Errors:**
   - Not an LLM issue
   - Check test environment setup

2. **Exit Code 2 with Django Errors:**
   - Not an LLM issue
   - Check Django settings

3. **Consistent Pattern Across All Tests:**
   - Likely environment/configuration issue
   - Check pytest setup and dependencies

## Advanced Debugging

### Enable Debug Mode

Set the environment variable:
```bash
export TESTGEN_DEBUG=1
```

This provides:
- Full LLM prompts and responses
- Detailed validation results
- Complete pytest output
- Stack traces for errors

### Manual Test Run

Before auto-fixing, run pytest manually to see the raw errors:

```bash
pytest tests/generated/ -v --tb=short
```

This helps determine if the errors are:
- Actual test logic issues (fixable by LLM)
- Environment/setup issues (need manual intervention)

### Check Individual Test Files

If a specific test keeps failing:

```python
# Read the test file
cat tests/generated/test_integ_20251115_131946_01.py

# Run just that test
pytest tests/generated/test_integ_20251115_131946_01.py::test_contactsform_and_contactflow -v
```

## Best Practices

1. **Start with Manual Review:**
   - Run pytest manually first
   - Fix obvious environment issues
   - Ensure pytest-json-report is installed

2. **Use Iterations Wisely:**
   - Start with `--max-iterations 1` for testing
   - Increase to 3-5 for production
   - Don't set too high (wastes LLM credits)

3. **Monitor LLM Behavior:**
   - Always review the LLM Behavior Analysis
   - Check validation results
   - Look for patterns in failures

4. **Version Control:**
   - Commit before running auto-fix
   - Review changes made by LLM
   - Revert if fixes are incorrect

## Example Output

### Successful Run:

```bash
$ python -m src.gen.auto_fix_tests --test-dir tests/generated --max-iterations 3

================================================================================
🔧 AUTO-FIX FAILING TESTS
================================================================================

✅ LLM client initialized (deployment: gpt-4)

================================================================================
🔄 Iteration 1/3
================================================================================

🧪 Running pytest on tests/generated...
⚠️  Some tests failed (exit code: 1 - Some tests failed)
🔍 [DEBUG] JSON report loaded: 45 tests

📋 Found 5 failing test(s):
  1. tests/generated/test_example.py::test_function_1
  2. tests/generated/test_example.py::test_function_2
  ...

🔧 Fixing test 1/5: test_function_1
  🤖 Asking LLM to fix the test...
  ✅ Fixed and saved: tests/generated/test_example.py

✅ Fixed 5/5 test(s)
ℹ️  Re-running pytest to verify fixes...

================================================================================
🔄 Iteration 2/3
================================================================================

🧪 Running pytest on tests/generated...
✅ All tests passed!

🔬 LLM BEHAVIOR ANALYSIS
================================================================================
Total LLM interactions: 5
[Details of each interaction...]
```

## Summary

The enhanced `auto_fix_tests.py` module provides:

1. ✅ **Better error handling** for all pytest exit codes
2. ✅ **Comprehensive logging** to track LLM behavior
3. ✅ **Validation** to ensure LLM follows steps correctly
4. ✅ **Detailed analysis** to identify LLM vs. configuration issues
5. ✅ **Debug mode** for deep troubleshooting

This makes it easy to determine whether failures are due to:
- LLM mistakes (check validation results)
- Configuration issues (check exit codes and error messages)
- Test logic issues (check the actual test errors)
