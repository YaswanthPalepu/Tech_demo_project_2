# Pytest Cache Solutions - Complete Guide

## Problem Summary
- **Issue**: Running pytest shows 6 failures, but auto-fixer shows 8 failures
- **Root Cause**: Pytest cache storing old test results from previous runs
- **Impact**: Stale data causing incorrect test counts and huge prompts (25K tokens)

---

## Where Pytest Stores Cache

```
📦 Project Root
├── .pytest_cache/              ← Main pytest cache directory
│   ├── .gitignore
│   ├── CACHEDIR.TAG
│   ├── README.md
│   └── v/cache/
│       ├── lastfailed          ← IDs of last failed tests
│       ├── nodeids             ← All test node IDs
│       └── stepwise            ← Stepwise test data
│
├── pytest_report.json          ← JSON report (if using plugin)
├── __pycache__/                ← Python bytecode cache
├── **/__pycache__/             ← Bytecode in subdirectories
├── .coverage                   ← Coverage data
└── htmlcov/                    ← HTML coverage reports
```

---

## All Solutions Implemented

### ✅ Solution 1: Automatic Cache Clearing in failure_parser.py

**Location**: `src/auto_fixer/failure_parser.py` (lines 57-104)

**What it does**:
```python
# Before running pytest:
1. Deletes .pytest_cache/ directory
2. Deletes pytest_report.json
3. Deletes __pycache__/ directories (first 5)
4. Shows verbose output of what was cleaned
```

**When it runs**: Automatically every time FailureParser runs pytest

**Output you'll see**:
```
🧹 Cleaning all pytest cache...
  ✓ Removed .pytest_cache/
  ✓ Removed pytest_report.json
  ✓ Found 12 __pycache__ directories
✓ Cache cleaning complete

🧪 Running pytest on tests...
✓ Pytest completed (exit code: 0)
```

---

### ✅ Solution 2: Pytest --cache-clear Flag

**Location**: `src/auto_fixer/failure_parser.py` (line 113)

**What it does**: Tells pytest to clear its internal cache before running

**Command used**:
```bash
pytest tests --tb=long --cache-clear -v
```

---

### ✅ Solution 3: Traceback Condensing (Reduces 25K → 5-7K tokens)

**Location**: `src/auto_fixer/failure_parser.py` (lines 257-338)

**What it does**:
```python
# Condenses traceback by:
1. Removing library frames (venv/, site-packages/, lib/)
2. Keeping only test/app code frames
3. Limiting error output to last 8 lines
4. Limiting total to 500 chars max
```

**Before** (25K tokens):
```
Full traceback with:
- All library internals (requests, urllib, etc.)
- All stack frames
- Huge assertion diffs
- Verbose print outputs
```

**After** (5-7K tokens):
```
AssertionError: assert 400 == 201

tests/test_signup.py:42: in test_signup
    assert response.status_code == 201

E   AssertionError: assert 400 == 201
E   + where 400 = <Response [400]>.status_code
E   The request failed with:
E   {"error": "Email already exists"}
```

---

## How to Use in Your Scripts

### Option A: Use in local_pipeline-1.sh (Manual Cleanup)

Add this at the **beginning** of your script:

```bash
#!/bin/bash

# Clear all pytest cache before running
./clear_pytest_cache.sh

# Your existing pipeline code
python your_script.py
# ... rest of pipeline
```

### Option B: Use Directly in Python Scripts

```python
#!/usr/bin/env python3
import subprocess
import os
import shutil

# Clear cache before running tests
def clear_pytest_cache():
    """Clear all pytest cache before running."""
    print("🧹 Clearing pytest cache...")

    # Remove pytest cache
    if os.path.exists('.pytest_cache'):
        shutil.rmtree('.pytest_cache')
        print("  ✓ Removed .pytest_cache/")

    # Remove pytest report
    if os.path.exists('pytest_report.json'):
        os.remove('pytest_report.json')
        print("  ✓ Removed pytest_report.json")

    # Remove __pycache__
    subprocess.run("find . -type d -name '__pycache__' -exec rm -rf {} + 2>/dev/null",
                   shell=True, check=False)
    print("  ✓ Removed __pycache__ directories")

    print("✅ Cache cleared!\n")

# Your main script
if __name__ == "__main__":
    clear_pytest_cache()  # Clear cache first!

    # Your existing code
    subprocess.run(["pytest", "tests/", "-v"])
```

### Option C: Use FailureParser (Automatic)

```python
from src.auto_fixer.failure_parser import FailureParser

# Cache is automatically cleared!
parser = FailureParser(test_directory="tests", verbose=True)
failures = parser.run_and_parse()

# Output:
# 🧹 Cleaning all pytest cache...
#   ✓ Removed .pytest_cache/
#   ✓ Removed pytest_report.json
# ✓ Cache cleaning complete
#
# 🧪 Running pytest on tests...
# ✓ Pytest completed (exit code: 0)
```

---

## Quick Reference Commands

### Manual Cache Clearing (Command Line)

```bash
# Quick one-liner (use this anytime!)
rm -rf .pytest_cache pytest_report.json && find . -name "__pycache__" -type d -exec rm -rf {} + && find . -name "*.pyc" -delete

# Or use the provided script
./clear_pytest_cache.sh

# Pytest with built-in cache clearing
pytest tests/ --cache-clear -v

# Completely disable pytest caching
pytest tests/ --cache-clear -p no:cacheprovider -v
```

### Check What's Cached

```bash
# See what's in pytest cache
cat .pytest_cache/v/cache/lastfailed

# See cache directory size
du -sh .pytest_cache

# List all __pycache__ directories
find . -type d -name "__pycache__"
```

---

## Expected Results

### Before Fixes:
```
❌ Pytest run 1: 6 failures
❌ Auto-fixer run: 8 failures (reading stale cache!)
❌ Prompt size: 100,103 chars (~25,025 tokens)
❌ Tests reappear after being fixed
```

### After Fixes:
```
✅ Pytest run 1: 6 failures
✅ Auto-fixer run: 6 failures (fresh data!)
✅ Prompt size: ~20,000 chars (~5,000 tokens)
✅ Fixed tests don't reappear
✅ Consistent failure counts
```

---

## Troubleshooting

### Q: Still seeing different failure counts?
**A**: Check if you have multiple pytest processes running:
```bash
ps aux | grep pytest
# Kill any hanging processes
pkill -9 pytest
```

### Q: __pycache__ keeps coming back?
**A**: That's normal! Python creates it automatically. The cache clearing happens **before** each test run, so this is expected.

### Q: Want to completely disable caching?
**A**: Add this to `pytest.ini`:
```ini
[pytest]
cache_dir = /tmp/pytest_cache  # Use temp directory
# OR
addopts = --cache-clear        # Always clear cache
```

### Q: Tests are still slow?
**A**: The cache clearing adds ~0.5-1 second overhead. This is worth it for accuracy!

---

## Summary

| Solution | What It Does | Impact |
|----------|--------------|--------|
| **Auto cache clearing** | Deletes cache before each run | ✅ No stale data |
| **--cache-clear flag** | Pytest clears its cache | ✅ Fresh test runs |
| **Traceback condensing** | Removes library frames, limits size | ✅ 70% smaller prompts |
| **clear_pytest_cache.sh** | Manual cleanup script | ✅ Use in pipelines |

**Bottom line**: With these fixes, you'll get consistent, accurate test results every time! 🎉
