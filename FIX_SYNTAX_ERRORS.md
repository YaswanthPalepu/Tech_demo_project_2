# Fix Syntax Errors in Generated Tests

## Problem
Generated tests may have syntax errors like:
- Circular class definitions: `class X(X):`
- Indentation errors
- Undefined names

## Quick Fix

### 1. Clean Up Invalid Tests
```bash
# Check and remove invalid test files
python cleanup_invalid_tests.py
```

### 2. Regenerate Tests
```bash
# The improved code will generate valid tests
python -m src.gen --target /path/to/your/project --force
```

## What Was Fixed

### Enhanced Validation (`src/gen/postprocess.py`)
- ✅ Detects circular class definitions
- ✅ Fixes indentation issues
- ✅ Removes self-referencing base classes
- ✅ Provides fallback test if unfixable

### Improved Prompts (`src/gen/enhanced_prompt.py`)
- ✅ Emphasizes simple, valid syntax
- ✅ Warns against circular definitions
- ✅ Requests proper indentation
- ✅ Focuses on simple test functions

### Better Retry Logic (`src/gen/enhanced_generate.py`)
- ✅ Validates before saving
- ✅ Provides specific error feedback to AI
- ✅ Uses fallback test if all retries fail
- ✅ Never saves invalid code

## Manual Fix (If Needed)

If you see errors like:
```
NameError: name 'EnhancedRenderer' is not defined
```

This is from: `class EnhancedRenderer(EnhancedRenderer):`

**Fix**: Edit the file and change to:
```python
class EnhancedRenderer:  # Remove circular inheritance
```

Or simply delete the invalid test file and regenerate.

## Prevention

The updated code now:
1. **Validates** all generated code before saving
2. **Fixes** common issues automatically
3. **Falls back** to simple valid test if unfixable
4. **Retries** with specific error feedback

## Verification

After regeneration, verify all tests are valid:
```bash
# Check syntax of all test files
python cleanup_invalid_tests.py

# Run tests
pytest tests/generated -v

# Should see no collection errors
```

## Expected Output

```
✓ test_unit_20251005_120000_01.py
✓ test_unit_20251005_120000_02.py
✓ test_integ_20251005_120000_01.py

Summary:
  Valid: 3
  Invalid: 0

✓ All test files are valid!
```

## If Issues Persist

1. **Delete all generated tests**:
   ```bash
   rm -rf tests/generated/test_*.py
   ```

2. **Regenerate with updated code**:
   ```bash
   python -m src.gen --target /path/to/project --force
   ```

3. **Check for valid syntax**:
   ```bash
   python cleanup_invalid_tests.py
   ```

The improved code should now generate only valid tests!
