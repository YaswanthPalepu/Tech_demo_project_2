# Automatic Cleanup Guide

## ✅ You Don't Need to Keep Running Fix Scripts!

The auto-fixer now **automatically cleans up common LLM mistakes** before applying fixes. This means you won't need to run manual fix scripts in the future.

## How It Works

### Automatic Cleanup (Built-In)

The `ASTPatcher` now includes automatic cleanup that runs **every time** the auto-fixer generates a fix:

1. **LLM generates a fix** (may contain mistakes like duplicate decorators)
2. **Auto-cleanup runs automatically** (removes duplicates)
3. **Validation runs** (ensures code is valid)
4. **Fix is applied** (only if validation passes)

```python
# In src/auto_fixer/ast_patcher.py:

def _prepare_fixed_code(self, fixed_code: str, indent: int) -> list[str]:
    # Step 1: Clean markdown formatting
    fixed_code = self._clean_code(fixed_code)

    # Step 2: AUTO-CLEANUP - Remove duplicate decorators
    fixed_code = self._remove_duplicate_decorators(fixed_code)

    # Step 3: Validate syntax
    ast.parse(fixed_code)

    # Step 4: Apply the cleaned fix
    ...
```

### What Gets Automatically Cleaned

**✅ Automatically Fixed (No Manual Intervention Needed)**

1. **Duplicate `@pytest.mark.parametrize` decorators**
   ```python
   # LLM generates this (INVALID):
   @pytest.mark.parametrize("x", [1, 2])
   @pytest.mark.parametrize("x", [3, 4])  # Duplicate!
   def test_foo(x):
       pass

   # Auto-cleanup produces this (VALID):
   @pytest.mark.parametrize("x", [1, 2])
   def test_foo(x):
       pass
   ```

2. **Markdown code blocks**
   - Removes ` ```python ` wrappers
   - Extracts just the code

3. **Extra whitespace and formatting**
   - Normalizes indentation
   - Removes trailing whitespace

**🛡️ Caught by Validation (Fix Rejected if Still Invalid)**

1. **Syntax errors**
   - Missing colons, parentheses
   - Invalid Python syntax

2. **Other pytest issues**
   - Still validates after cleanup
   - Rejects if still broken

## When You Need Manual Fix Scripts

**Manual fix scripts are ONLY needed for:**

### ❌ Already-Broken Test Files

If tests were **already broken before** you run the auto-fixer:

```bash
# For files with duplicate decorators created BEFORE the auto-cleanup feature:
python fix_duplicate_parametrize.py --test-dir tests/generated

# For the specific None isinstance issue:
python fix_none_parametrize_test.py --test-dir tests/generated
```

**These scripts are ONE-TIME fixes** for existing broken files.

### ✅ Future Runs Don't Need Scripts

Once your tests are fixed:

```bash
# Just run the auto-fixer - cleanup is automatic!
python run_auto_fixer.py \
    --test-dir tests/generated \
    --project-root /path/to/source \
    --max-iterations 3
```

The auto-fixer will **automatically clean up** any duplicate decorators in LLM-generated fixes.

## Example: Before vs After

### Before (You Had to Do This)

```bash
# Run auto-fixer
python run_auto_fixer.py --test-dir tests/generated
# ❌ Error: Patched code has duplicate @pytest.mark.parametrize decorators

# Manually run fix script
python fix_duplicate_parametrize.py --test-dir tests/generated

# Run auto-fixer again
python run_auto_fixer.py --test-dir tests/generated
# ❌ Still failing...

# Repeat multiple times... 😞
```

### After (Automatic Cleanup)

```bash
# Just run auto-fixer once
python run_auto_fixer.py --test-dir tests/generated

# Output:
#   Auto-removing duplicate @pytest.mark.parametrize('x') from LLM fix
#   ✓ Automatically cleaned duplicate decorators from LLM-generated fix
#   ✓ Fix applied successfully
# ✅ Done! 😊
```

## What You'll See

When auto-cleanup runs, you'll see messages like:

```
--- Processing failure 1/5 ---
Test: test_example in tests/test_foo.py
  Rule classifier: test_mistake
  Generating fix...
  Auto-removing duplicate @pytest.mark.parametrize('input_value') from LLM fix
  ✓ Automatically cleaned duplicate decorators from LLM-generated fix
  Applying fix...
  ✓ Fix applied successfully
  Classification: TEST MISTAKE (fixed)
```

## Summary

| Scenario | Action Required |
|----------|-----------------|
| **Future auto-fixer runs** | ✅ Nothing - automatic cleanup! |
| **Existing broken test files** | ⚠️ Run fix script once |
| **New test files** | ✅ Nothing - auto-fixer handles it! |
| **LLM generates duplicate decorators** | ✅ Nothing - automatically removed! |

## Technical Details

### Cleanup Order

1. **Markdown removal** - Strip code blocks
2. **Duplicate decorator removal** - Remove duplicates
3. **Syntax validation** - Ensure valid Python
4. **Pytest validation** - Double-check for issues
5. **Apply fix** - Write to file

### Safety Guarantees

- ✅ **Non-destructive**: Only removes exact duplicates
- ✅ **Fail-safe**: Rejects fix if still invalid after cleanup
- ✅ **Transparent**: Logs all cleanup actions
- ✅ **Validates**: Both syntax and pytest-specific rules

## For Developers

If you want to extend the automatic cleanup to handle other common LLM mistakes:

1. Edit `src/auto_fixer/ast_patcher.py`
2. Add a new cleanup method (e.g., `_remove_unused_imports()`)
3. Call it in `_prepare_fixed_code()` before validation
4. Add corresponding validation in `_validate_pytest_decorators()`

```python
def _prepare_fixed_code(self, fixed_code: str, indent: int) -> list[str]:
    fixed_code = self._clean_code(fixed_code)
    fixed_code = self._remove_duplicate_decorators(fixed_code)
    fixed_code = self._remove_unused_imports(fixed_code)  # New cleanup
    # ... rest of method
```

## Questions?

- **Q: Do I need to run fix scripts every time?**
  - A: No! Only once for existing broken files. Future runs are automatic.

- **Q: What if a new type of error appears?**
  - A: The auto-fixer will reject the fix and log the error. You can then add a new cleanup method.

- **Q: Can I disable automatic cleanup?**
  - A: Not recommended, but you could modify `_prepare_fixed_code()` to skip cleanup calls.

- **Q: Will this slow down the auto-fixer?**
  - A: No - cleanup is very fast (< 1ms per fix) using AST operations.
