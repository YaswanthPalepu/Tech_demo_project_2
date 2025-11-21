# Diagnosing Zero Test Generation Issue

## Problem Statement

The multi-iteration orchestrator runs successfully but generates **0 tests** in all iterations, causing coverage to remain flat at 80.56%.

## Common Causes

### 1. **Code Analysis Failed**
The analyzer couldn't parse the target directory or found no testable code.

**Check:**
```bash
# Run analyzer directly to see output
python src/analyzer.py /home/sigmoid/test-repos/ExamplePythonTravis

# Expected: Should find functions, classes, etc.
# If empty output → analyzer issue
```

### 2. **Gap Filtering Removed Everything**
The gap-aware filter is too aggressive and filters out all code.

**Check:**
```bash
# Look at coverage_gaps.json
cat coverage_gaps.json | python -m json.tool

# Check if it has data:
# - files_with_gaps: should have entries
# - uncovered_functions: should have entries
# - uncovered_lines_by_file: should have entries

# If all empty → gap analyzer issue
```

### 3. **No Functions/Classes Found**
The project structure isn't recognized (wrong file types, naming issues).

**Check:**
```bash
# List Python files in target
find /home/sigmoid/test-repos/ExamplePythonTravis -name "*.py" -type f

# Check file contents
head -20 /home/sigmoid/test-repos/ExamplePythonTravis/example.py
head -20 /home/sigmoid/test-repos/ExamplePythonTravis/points/nn.py
```

### 4. **OpenAI API Error**
The API call is failing silently.

**Check:**
```bash
# Verify API key is set
echo $OPENAI_API_KEY

# If empty → Set it:
export OPENAI_API_KEY="sk-your-key-here"
```

### 5. **Test Generation Exits Early**
Some condition causes early exit without generating tests.

**Check:**
```bash
# Run test generation with verbose output
GAP_FOCUSED_MODE=true python -m src.gen \
  --target /home/sigmoid/test-repos/ExamplePythonTravis \
  --outdir ./tests/generated \
  --force \
  --coverage-mode gap-focused 2>&1 | tee generation.log

# Review generation.log for errors
```

## Diagnostic Commands

### Step 1: Check Coverage Gaps

```bash
cat coverage_gaps.json
```

**Expected:**
```json
{
  "overall_coverage": 80.56,
  "files_with_gaps": {
    "example.py": {
      "missing_lines": [1, 2, 3, 5, 6, 8],
      "coverage_percentage": 0.0
    },
    "points/nn.py": {
      "missing_lines": [9],
      "coverage_percentage": 90.0
    }
  },
  "uncovered_functions": [...],  // Should have entries
  "uncovered_lines_by_file": {...}  // Should have entries
}
```

**If empty or missing keys:** Gap analyzer didn't parse correctly.

### Step 2: Check Code Analysis

```bash
# Analyze the target directory
python src/analyzer.py /home/sigmoid/test-repos/ExamplePythonTravis > analysis.json

# Check output
cat analysis.json | python -m json.tool | head -50
```

**Expected:**
```json
{
  "functions": [
    {
      "name": "distance",
      "file": "points/nn.py",
      "line_start": 5,
      "line_end": 10
    }
  ],
  "classes": [...],
  "imports": [...]
}
```

**If empty:** Analyzer isn't finding the code.

### Step 3: Check Test Generation Directly

```bash
# Run with explicit environment variable
export GAP_FOCUSED_MODE=true
export OPENAI_API_KEY="your-key-here"

# Run generation with full output
python -m src.gen \
  --target /home/sigmoid/test-repos/ExamplePythonTravis \
  --outdir ./tests/generated \
  --force \
  --coverage-mode gap-focused \
  --verbose  # If available
```

**Look for:**
- "Analyzing codebase..." - Should appear
- "Found X functions, Y classes" - Should show counts
- "Generating tests..." - Should appear
- "Calling OpenAI API..." - Should appear
- Error messages

### Step 4: Check File Structure

```bash
# Verify target directory structure
tree /home/sigmoid/test-repos/ExamplePythonTravis -L 3

# Or use ls
ls -laR /home/sigmoid/test-repos/ExamplePythonTravis

# Check for __init__.py files
find /home/sigmoid/test-repos/ExamplePythonTravis -name "__init__.py"
```

**Expected:**
```
ExamplePythonTravis/
├── example.py
├── points/
│   ├── __init__.py
│   ├── nn.py
│   ├── point.py
│   ├── random.py
│   └── scipy/
│       ├── __init__.py
│       └── pdist.py
```

## Quick Fixes

### Fix 1: OpenAI API Key Missing

```bash
# Check if set
echo $OPENAI_API_KEY

# If empty, set it
export OPENAI_API_KEY="sk-your-actual-key-here"

# Run orchestrator again
python multi_iteration_orchestrator.py \
  --target /home/sigmoid/test-repos/ExamplePythonTravis \
  --iterations 3
```

### Fix 2: Gap-Focused Mode Issues

```bash
# Try WITHOUT gap-focused mode first
python -m src.gen \
  --target /home/sigmoid/test-repos/ExamplePythonTravis \
  --outdir ./tests/generated \
  --force

# If this generates tests, gap filtering is the issue
```

### Fix 3: Target Path Issues

```bash
# Use absolute path
python multi_iteration_orchestrator.py \
  --target "$(realpath /home/sigmoid/test-repos/ExamplePythonTravis)" \
  --current-dir "$(pwd)" \
  --iterations 3
```

### Fix 4: Analyzer Can't Parse Code

```bash
# Check if Python files are valid
python -m py_compile /home/sigmoid/test-repos/ExamplePythonTravis/example.py
python -m py_compile /home/sigmoid/test-repos/ExamplePythonTravis/points/nn.py

# If syntax errors, analyzer will fail
```

## Debug Mode: Run Each Step Manually

### Step 1: Analyze Code
```bash
python src/analyzer.py /home/sigmoid/test-repos/ExamplePythonTravis > analysis.json
cat analysis.json | python -m json.tool
```

### Step 2: Check Gap Filtering
```python
# In Python REPL
from src.gen.gap_aware_analysis import load_coverage_gaps, filter_analysis_by_coverage_gaps
import json

# Load gaps
gaps = load_coverage_gaps("coverage_gaps.json")
print("Gaps loaded:", gaps)

# Load analysis
with open("analysis.json") as f:
    analysis = json.load(f)
print("Functions found:", len(analysis.get("functions", [])))

# Apply filtering
from src.gen.gap_aware_analysis import apply_gap_aware_filtering
filtered = apply_gap_aware_filtering(analysis, gaps)
print("After filtering:", len(filtered.get("functions", [])))

# If 0 after filtering → gap filter is too aggressive
```

### Step 3: Test OpenAI Call
```python
# In Python REPL
import os
from openai import OpenAI

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Simple test
response = client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Hello"}]
)
print(response.choices[0].message.content)

# If error → API key issue
```

## Most Likely Causes (In Order)

### 1. **OpenAI API Key Not Set** (60% probability)
```bash
echo $OPENAI_API_KEY
# If empty → export OPENAI_API_KEY="sk-..."
```

### 2. **Gap Filtering Too Aggressive** (20% probability)
- `coverage_gaps.json` exists but filtering removes all code
- Try without `--coverage-mode gap-focused`

### 3. **Code Analysis Failed** (10% probability)
- Analyzer doesn't recognize code structure
- Check `python src/analyzer.py <target>`

### 4. **Target Path Issues** (5% probability)
- Path doesn't exist or isn't accessible
- Use absolute paths

### 5. **Dependencies Missing** (5% probability)
- `openai` package not installed
- Run `pip install -r requirements.txt`

## Expected Behavior (When Working)

```
🤖 ITERATION 1: Generating AI Tests (Gap-Focused)
  ▶ Analyzing codebase...
  ▶ Found 5 functions, 2 classes
  ▶ Gap-focused filtering: 2 uncovered functions
  ▶ Generating tests for uncovered code...
  ▶ Calling OpenAI API...
  ▶ Generated test_unit_20251120_001.py
  ▶ Generated test_unit_20251120_002.py
  ✅ Generated 2 test files
```

## Get Help

Run these diagnostic commands and share output:

```bash
# 1. Check API key (don't share the actual key!)
echo "API key set: $([ -n "$OPENAI_API_KEY" ] && echo 'YES' || echo 'NO')"

# 2. Check coverage gaps
cat coverage_gaps.json | python -m json.tool | head -30

# 3. Check code analysis
python src/analyzer.py /home/sigmoid/test-repos/ExamplePythonTravis | python -m json.tool | head -50

# 4. Check file structure
tree /home/sigmoid/test-repos/ExamplePythonTravis -L 2

# 5. Try generation directly
GAP_FOCUSED_MODE=true python -m src.gen \
  --target /home/sigmoid/test-repos/ExamplePythonTravis \
  --outdir ./tests/generated \
  --force \
  --coverage-mode gap-focused 2>&1 | head -50
```

Share these outputs to diagnose the issue!
