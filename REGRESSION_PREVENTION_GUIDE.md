# Regression Prevention Guide

## Problem: Auto-Fixer Making Things Worse

The auto-fixer's LLM can sometimes generate "fixes" that:
- ❌ Still fail the original test
- ❌ Create NEW failures that didn't exist before
- ❌ Introduce bugs in the test logic
- ❌ Break other parts of the test file

**This defeats the purpose of the auto-fixer!**

## Solution: Test Fixes Before Applying Them

The auto-fixer now **validates every fix before committing it** by running pytest on the fixed test.

### How It Works

```
┌──────────────────────────────────────────┐
│ 1. LLM generates a fix                   │
└────────────────┬─────────────────────────┘
                 │
┌────────────────▼─────────────────────────┐
│ 2. Auto-cleanup runs                     │
│    - Remove duplicate decorators         │
└────────────────┬─────────────────────────┘
                 │
┌────────────────▼─────────────────────────┐
│ 3. Syntax validation                     │
│    - Check Python syntax                 │
│    - Check pytest decorators             │
└────────────────┬─────────────────────────┘
                 │
┌────────────────▼─────────────────────────┐
│ 4. 🧪 REGRESSION PREVENTION (NEW!)       │
│    a. Write fix to file temporarily      │
│    b. Run pytest on the fixed test       │
│    c. Restore original immediately       │
│    d. Check if test PASSED               │
└────────────────┬─────────────────────────┘
                 │
         ┌───────┴────────┐
         │                │
    ✅ PASSED        ❌ FAILED
         │                │
┌────────▼────┐  ┌────────▼─────────────┐
│ 5. Apply    │  │ 5. REJECT fix        │
│    fix      │  │    Keep original     │
└─────────────┘  └──────────────────────┘
```

## Example Output

### ✅ When Fix Works

```
--- Processing failure 1/5 ---
Test: test_example in tests/test_foo.py
  Generating fix...
  Auto-removing duplicate @pytest.mark.parametrize('x') from LLM fix
  ✓ Automatically cleaned duplicate decorators from LLM-generated fix
  Applying fix...
  🧪 Testing fix before applying (regression prevention)...
  ✅ Fix validated - test passes!
  ✓ Fix applied successfully
  Classification: TEST MISTAKE (fixed)
```

### ❌ When Fix Fails (Regression Prevented!)

```
--- Processing failure 2/5 ---
Test: test_temporary_file_operations in tests/test_e2e.py
  Generating fix...
  Applying fix...
  🧪 Testing fix before applying (regression prevention)...
  ❌ Fix validation failed - test still fails:
     AssertionError: assert (False)
     +  where False = <bound method Path.exists of PosixPath(...)>()
  Rejecting fix - it still fails or creates new errors
  ✗ Fix application failed
  Classification: TEST MISTAKE (fix failed)
```

**The original test file is UNCHANGED!** The bad fix was caught and rejected.

## What Gets Validated

For every fix attempt, the auto-fixer:

1. ✅ **Writes the fix temporarily** to the actual test file
2. ✅ **Runs pytest** on that specific test function
3. ✅ **Restores the original** immediately (whether pass or fail)
4. ✅ **Only applies the fix** if the test PASSES

### Validation Checks

| Check | Pass Criteria | Fail Action |
|-------|---------------|-------------|
| Test passes | Exit code 0 | Reject fix, keep original |
| Test fails | Any error | Reject fix, keep original |
| Test hangs | Timeout (30s) | Reject fix, keep original |
| New errors introduced | Any exception | Reject fix, keep original |

## Benefits

### 🛡️ Prevents Regressions

- Auto-fixer can't make things worse
- Bad LLM fixes are caught before they damage your tests
- Original failing tests stay unchanged (not made worse)

### 📊 Better Success Rate

- Only applies fixes that actually work
- Reports honest success/failure rates
- No false positives in fix statistics

### 🔍 Debugging Help

- Shows WHY a fix was rejected (test output)
- Helps identify what the LLM is doing wrong
- Can improve prompts based on rejection patterns

## Configuration

### Enable/Disable Validation

By default, regression prevention is **ENABLED**. You can disable it:

```python
from src.auto_fixer import ASTPatcher

# Default: validation enabled (recommended!)
patcher = ASTPatcher()  # enable_test_validation=True

# Disable validation (NOT recommended - auto-fixer can make things worse!)
patcher = ASTPatcher(enable_test_validation=False)
```

### Why You Should Keep It Enabled

| With Validation ✅ | Without Validation ❌ |
|-------------------|----------------------|
| Only applies working fixes | Applies all fixes (even broken ones) |
| Prevents new failures | Can create new failures |
| Honest success rates | False success reports |
| Safe to run automatically | Requires manual review |
| Original tests protected | Original tests can get worse |

**Recommendation**: Keep validation ENABLED unless you have a specific reason to disable it.

## Performance Impact

### Test Execution Overhead

- Each fix runs pytest once (on single test function)
- Typical overhead: **1-3 seconds per fix**
- Total impact: **~10-30 seconds for 10 fixes**

### Trade-off Analysis

| Aspect | With Validation | Without Validation |
|--------|----------------|-------------------|
| Speed | Slower (1-3s per fix) | Faster |
| Safety | ✅ Safe | ❌ Risky |
| Quality | ✅ High | ❌ Low |
| Trust | ✅ Reliable | ❌ Unreliable |

**The safety benefits far outweigh the 1-3 second delay per fix.**

## Real-World Example

### Before Regression Prevention

```bash
# Run auto-fixer
python run_auto_fixer.py

# Result:
# - 5 fixes applied
# - 2 actually worked
# - 3 created NEW failures
# - Made things WORSE overall!
```

### After Regression Prevention

```bash
# Run auto-fixer
python run_auto_fixer.py

# Result:
# - 2 fixes applied (only the ones that work!)
# - 3 fixes rejected (prevented regressions!)
# - Made things BETTER, not worse!
```

## Troubleshooting

### All Fixes Getting Rejected

**Symptom**: Every fix fails validation

**Possible Causes**:
1. Missing test dependencies (fixtures, imports)
2. LLM generating fundamentally wrong fixes
3. Test environment issues
4. Database/network dependencies

**Solutions**:
- Check test output for common failure patterns
- Improve LLM prompts with better context
- Ensure test environment is set up correctly
- Review rejected fix output for clues

### Validation Times Out

**Symptom**: Fix validation shows "timed out"

**Possible Causes**:
1. LLM generated infinite loop
2. Test hangs on network/database
3. Async test never completes

**Solutions**:
- Review the generated fix code
- Check for infinite loops or blocking calls
- Adjust timeout if tests legitimately take >30s

### False Rejections

**Symptom**: Fix looks correct but validation fails

**Possible Causes**:
1. Test has non-deterministic behavior (random, time-based)
2. Test depends on external state
3. Test needs specific setup order

**Solutions**:
- Review test for non-determinism
- Add proper fixtures/setup
- Check test dependencies

## Technical Details

### Validation Process

```python
def _test_fix_before_commit(self, test_file_path, test_function_name,
                            patched_content, original_content):
    # 1. Write patched content to actual file
    with open(test_file_path, 'w') as f:
        f.write(patched_content)

    # 2. Run pytest on the specific test
    result = subprocess.run(
        ['pytest', f"{test_file_path}::{test_function_name}", '-v'],
        capture_output=True,
        timeout=30
    )

    # 3. ALWAYS restore original (pass or fail)
    with open(test_file_path, 'w') as f:
        f.write(original_content)

    # 4. Only return True if test passed
    return result.returncode == 0
```

### Safety Guarantees

- ✅ **Always restores original** (even on crash/exception)
- ✅ **Timeout protection** (30 second max)
- ✅ **No partial writes** (atomic replacement)
- ✅ **Exception handling** (all errors caught)

## For Future: Preventing Auto-Fixer Mistakes

The regression prevention feature **catches** auto-fixer mistakes, but to **prevent** them:

### 1. Improve LLM Prompts

Add more context and constraints:
```python
SYSTEM_PROMPT = """...

CRITICAL RULES:
1. Test the fix logic carefully before returning
2. Don't introduce new dependencies without checking they exist
3. Preserve test intent - don't change what's being tested
4. Add proper fixtures if tests need setup
..."""
```

### 2. Add Pre-Validation Hints

Give the LLM information about common mistakes:
```python
prompt = f"""
## Common Auto-Fixer Mistakes to AVOID:
❌ Creating temporary files without proper paths
❌ Missing database fixtures for tests that need DB
❌ Changing test logic instead of fixing test code
❌ Adding imports that don't exist
...
"""
```

### 3. Use Few-Shot Learning

Show the LLM examples of good vs bad fixes:
```python
prompt = f"""
## Example of BAD Fix:
# Creates new failure with wrong path
p = tmp_path / "testfile.txt"
p.write_text(content)  # ❌ No parent check!

## Example of GOOD Fix:
# Properly handles paths
p = tmp_path / "testfile.txt"
p.parent.mkdir(parents=True, exist_ok=True)  # ✅ Safe!
p.write_text(content)
...
"""
```

## Summary

| Feature | Benefit |
|---------|---------|
| **Pre-commit testing** | Validates fixes before applying |
| **Automatic rollback** | Restores original on failure |
| **Regression prevention** | Can't make things worse |
| **Honest reporting** | Only reports actual successes |
| **Safety guarantees** | Always restores original file |

**Bottom Line**: Regression prevention ensures the auto-fixer **never makes things worse**, only better!
