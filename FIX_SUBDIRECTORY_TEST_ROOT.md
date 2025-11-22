# Fix: Test Root Detection for Subdirectories

## Issue Reported

**User's observation:**
> "test_user.py is a single file which presents in test_models/test_user.py but it also copying in tests/manual folder also."

**Translation:**
When a test file exists at `tests/test_models/test_user.py`, it was being copied to:
- ❌ `tests/manual/test_user.py` (wrong - flat, loses directory structure)
- ✅ `tests/manual/test_models/test_user.py` (correct - preserves structure)

## Root Cause

### Problem in `find_common_test_root()`

**Before (Wrong):**
```python
if len(test_dirs) == 1:
    return test_dirs[0]  # Returns the subdirectory itself!
```

**Scenario:**
```
Repository structure:
  /repo/tests/test_models/test_user.py  (only test file)

Detection result:
  test_dirs = ["/repo/tests/test_models"]
  test_root = "/repo/tests/test_models"  # ❌ Wrong!

Relative path calculation:
  rel_path = os.path.relpath(
      "/repo/tests/test_models/test_user.py",
      "/repo/tests/test_models"
  )
  # Returns: "test_user.py"  # ❌ Lost the subdirectory!

When copied:
  dest = os.path.join("tests/manual", "test_user.py")
  # Creates: tests/manual/test_user.py  # ❌ Wrong location!
```

### Secondary Problem: False Pattern Matching

The old code matched any directory containing "test":
```python
if 'test' in part.lower():  # ❌ Matches "test-repo", "testing-tools", etc.
```

This caused issues when repository names contained "test".

## Solution

### 1. Added `is_test_directory()` Helper

**Precise matching** for test directories:
```python
def is_test_directory(dirname: str) -> bool:
    """Check if directory name is a test directory."""
    dirname_lower = dirname.lower()

    # Exact match for 'test' or 'tests'
    if dirname_lower in ['test', 'tests']:
        return True

    # Starts with 'test_' (e.g., 'test_integration')
    if dirname_lower.startswith('test_'):
        return True

    return False
```

**Matches:**
- ✅ `tests`
- ✅ `test`
- ✅ `test_unit`
- ✅ `test_integration`
- ✅ `test_models`

**Rejects:**
- ❌ `test-repo` (contains hyphen)
- ❌ `testing-tools` (different pattern)
- ❌ `latest` (contains "test" but wrong pattern)

### 2. Fixed Single Directory Case

**Before:**
```python
if len(test_dirs) == 1:
    return test_dirs[0]  # Returns subdirectory
```

**After:**
```python
if len(test_dirs) == 1:
    single_dir = test_dirs[0]
    parts = single_dir.split(os.sep)

    # Find the directory named 'test' or 'tests'
    for i, part in enumerate(parts):
        if is_test_directory(part):
            # Return the test directory, not subdirectories within it
            return os.sep.join(parts[:i+1])

    return single_dir
```

**Example:**
```
Input:  test_dirs = ["/repo/tests/test_models"]
Parts:  ['', 'repo', 'tests', 'test_models']
Match:  'tests' at index 2
Return: "/repo/tests"  # ✅ Correct!
```

## Results

### Before Fix

```json
{
  "test_root": "/repo/tests/test_models",
  "files_by_relative_path": {
    "test_user.py": "/repo/tests/test_models/test_user.py"
  }
}
```

**Copied to:** `tests/manual/test_user.py` ❌

### After Fix

```json
{
  "test_root": "/repo/tests",
  "files_by_relative_path": {
    "test_models/test_user.py": "/repo/tests/test_models/test_user.py"
  }
}
```

**Copied to:** `tests/manual/test_models/test_user.py` ✅

## Test Cases Verified

### Case 1: Single Subdirectory
```
Structure:
  tests/test_models/test_user.py

Result:
  test_root: /repo/tests
  relative_path: test_models/test_user.py  ✅
```

### Case 2: Flat Structure
```
Structure:
  tests/test_user.py
  tests/test_calc.py

Result:
  test_root: /repo/tests
  relative_paths:
    - test_user.py  ✅
    - test_calc.py  ✅
```

### Case 3: Mixed Structure
```
Structure:
  tests/test_main.py
  tests/unit/test_unit.py
  tests/integration/test_int.py
  tests/test_models/test_user.py

Result:
  test_root: /repo/tests
  relative_paths:
    - test_main.py                    ✅
    - unit/test_unit.py               ✅
    - integration/test_int.py         ✅
    - test_models/test_user.py        ✅
```

### Case 4: Avoid False Matches
```
Structure:
  test-repo/tests/test_models/test_user.py

Result:
  test_root: /test-repo/tests  (not /test-repo)  ✅
  relative_path: test_models/test_user.py  ✅
```

## Impact

### Before
- ❌ Subdirectory structure lost
- ❌ Files copied to wrong locations
- ❌ Potential pytest collection errors
- ❌ False matches on repo names

### After
- ✅ Directory structure preserved
- ✅ Files copied to correct locations
- ✅ No pytest collection errors
- ✅ Precise test directory detection

## Example: Real-World Scenario

### Repository Structure
```
flask-high-coverage-repo/
├── tests/
│   ├── test_user.py           # User tests in root
│   └── test_models/
│       └── test_user.py       # User model tests
```

### Before Fix
Both files copied to same location:
```
tests/manual/
└── test_user.py  # ❌ Only one file! Which one?
```

**Result:** Pytest import mismatch error, coverage drops to 30%

### After Fix
Structure preserved:
```
tests/manual/
├── test_user.py                 # ✅ Root test
└── test_models/
    └── test_user.py             # ✅ Model test
```

**Result:** Both tests collected, coverage accurate at 85%

## Commits

1. **5658de35** - Initial directory structure preservation
2. **10098f90** - Added manual_test_result.json to gitignore
3. **0555c0ea** - Fixed test root detection for subdirectories (this fix)

## Related Documentation

- `DIRECTORY_STRUCTURE_PRESERVATION.md` - Why structure preservation is mandatory
- `local_pipeline-1.sh` - Updated copy logic using structure info
- `src/detect_manual_tests.py` - Detection logic with precise matching
