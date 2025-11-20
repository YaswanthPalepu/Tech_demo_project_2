# Multi-Iteration Orchestrator Troubleshooting Guide

## Common Issues and Solutions

### Issue 1: Coverage Gap Analyzer Returns Exit Code 1

**Symptom:**
```
⚠️  Warning: Command returned code 1
```

**Possible Causes:**

1. **Missing coverage files** - Coverage analysis needs existing coverage data
2. **Warnings in output** - The analyzer may have warnings but still succeed
3. **Python path issues** - `src/` module not in PYTHONPATH

**Solutions:**

#### Solution 1: Run Manual Tests with Coverage First

Before running the orchestrator, ensure you have coverage data:

```bash
# Option A: If you have manual tests
pytest tests/manual \
  --cov=app \
  --cov-config=pytest.ini \
  --cov-report=xml \
  --cov-report=html

# Option B: If you have no tests yet (will create empty coverage)
pytest --cov=app --cov-config=pytest.ini --cov-report=xml --cov-report=html || true
```

#### Solution 2: Run Coverage Gap Analyzer Manually

Test the command manually to see the full error:

```bash
python src/coverage_gap_analyzer.py \
  --target /path/to/your/target/dir \
  --current-dir . \
  --output coverage_gaps.json
```

**Expected behavior:** Even with exit code 1, if `coverage_gaps.json` is created, the orchestrator will continue successfully.

#### Solution 3: Check Required Files

Ensure these files exist:
```bash
ls -la coverage.xml       # XML coverage report
ls -la htmlcov/          # HTML coverage report directory
ls -la pytest.ini         # Pytest configuration
```

If missing:
```bash
# Generate them
pytest --cov=app --cov-config=pytest.ini --cov-report=xml --cov-report=html
```

---

### Issue 2: Test Generation Not Working / No Tests Generated

**Symptom:**
```
⚠️  No test files found in ./tests/generated
```

**Possible Causes:**

1. **Missing OpenAI API key**
2. **Missing coverage_gaps.json**
3. **Network issues**
4. **Target directory doesn't exist**
5. **Python dependencies missing**

**Solutions:**

#### Solution 1: Set OpenAI API Key

```bash
export OPENAI_API_KEY="sk-..."
echo $OPENAI_API_KEY  # Verify it's set
```

To set permanently, add to `~/.bashrc` or `~/.zshrc`:
```bash
export OPENAI_API_KEY="sk-your-key-here"
```

#### Solution 2: Run Test Generation Manually

Test the command manually to see the full error:

```bash
GAP_FOCUSED_MODE=true python -m src.gen \
  --target /path/to/your/target/dir \
  --outdir ./tests/generated \
  --force \
  --coverage-mode gap-focused
```

#### Solution 3: Check Dependencies

```bash
pip install -r requirements.txt
pip list | grep -E "openai|pytest|coverage"
```

Expected packages:
- `openai`
- `pytest`
- `pytest-cov`
- `coverage`

#### Solution 4: Verify Target Directory

```bash
ls -la /path/to/your/target/dir
```

The target directory should contain Python files (`.py`) to analyze.

#### Solution 5: Check Internet Connectivity

```bash
curl -I https://api.openai.com
```

If this fails, you have network issues blocking OpenAI API access.

---

### Issue 3: Coverage Not Improving Between Iterations

**Symptom:**
```
Coverage Gain: +0.00%
```

**Possible Causes:**

1. **Hard-to-test code** (error handlers, edge cases)
2. **Generated tests not covering gaps**
3. **Coverage measurement issues**

**Solutions:**

#### Solution 1: Review Coverage Gaps

```bash
cat coverage_gaps.json | python -m json.tool
```

Look at `files_with_gaps` to see which files have remaining gaps.

#### Solution 2: Review Generated Tests

```bash
ls -la tests/generated/
cat tests/generated/test_unit_*.py
```

Check if tests are actually testing the uncovered code.

#### Solution 3: Run Tests Manually

```bash
pytest tests/generated -v
```

See if tests are passing or failing.

#### Solution 4: Check Coverage Report Visually

```bash
# Open HTML coverage report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
start htmlcov/index.html  # Windows
```

Red lines = uncovered, green lines = covered.

#### Solution 5: Add Manual Tests for Complex Code

Some code is hard for AI to test. Consider writing manual tests:

```python
# tests/manual/test_edge_cases.py
def test_error_handler():
    # Test specific edge case
    pass
```

---

### Issue 4: Path Issues (Target Directory Not Found)

**Symptom:**
```
Target directory doesn't exist
```

**Solutions:**

#### Solution 1: Use Absolute Paths

```bash
python multi_iteration_orchestrator.py \
  --target "$(pwd)/app" \
  --current-dir "$(pwd)"
```

#### Solution 2: Verify Current Directory

```bash
pwd
ls -la app/  # Or your target directory
```

#### Solution 3: Use Correct Relative Path

From your project root:
```bash
cd /path/to/your/project
python multi_iteration_orchestrator.py --target ./app
```

---

### Issue 5: Environment Variable Issues

**Symptom:**
```
Gap-focused mode not activating
```

**Solutions:**

#### Solution 1: Check Environment Variable

```bash
echo $GAP_FOCUSED_MODE
```

The orchestrator sets this automatically, but you can verify:

```bash
GAP_FOCUSED_MODE=true python -m src.gen --target app --outdir ./tests/generated --force --coverage-mode gap-focused
```

#### Solution 2: Check .env File

If using a `.env` file:

```bash
cat .env
```

Ensure it contains:
```
OPENAI_API_KEY=sk-...
```

Load it:
```bash
source .env
# Or use python-dotenv in your code
```

---

## Debugging Workflow

### Step 1: Verify Prerequisites

```bash
# Check Python version (3.8+)
python --version

# Check pip packages
pip list | grep -E "pytest|coverage|openai"

# Check OpenAI API key
echo $OPENAI_API_KEY

# Check target directory exists
ls -la app/  # Replace with your target
```

### Step 2: Run Commands Manually (One by One)

```bash
# Step 1: Generate initial coverage (if you have manual tests)
pytest tests/manual --cov=app --cov-config=pytest.ini --cov-report=xml --cov-report=html

# Step 2: Analyze coverage gaps
python src/coverage_gap_analyzer.py \
  --target app \
  --current-dir . \
  --output coverage_gaps.json

# Step 3: Check gaps file
cat coverage_gaps.json | python -m json.tool

# Step 4: Generate AI tests
GAP_FOCUSED_MODE=true python -m src.gen \
  --target app \
  --outdir ./tests/generated \
  --force \
  --coverage-mode gap-focused

# Step 5: Check generated tests
ls -la tests/generated/

# Step 6: Run all tests
pytest tests/ --cov=app --cov-config=pytest.ini --cov-report=xml --cov-report=html -v
```

### Step 3: Check Output Files

```bash
# Coverage files
ls -la coverage.xml htmlcov/

# Gap analysis
cat coverage_gaps.json

# Generated tests
ls -la tests/generated/

# Iteration report
cat iteration_report.json
```

### Step 4: Review Logs

The orchestrator now shows detailed error output. Look for:
- `❌ Error Output:` - Actual error messages
- `📋 Output:` - Command output
- `💡` - Helpful hints

---

## Quick Fixes

### Fix 1: Fresh Start

```bash
# Clean up old files
rm -rf tests/generated/ coverage.xml htmlcov/ .coverage coverage_gaps.json iteration_report.json

# Run manual tests to get fresh coverage
pytest tests/manual --cov=app --cov-config=pytest.ini --cov-report=xml --cov-report=html

# Run orchestrator
python multi_iteration_orchestrator.py --target app
```

### Fix 2: Check Installation

```bash
# Reinstall dependencies
pip install -r requirements.txt --upgrade

# Verify installation
python -c "import openai; import pytest; import coverage; print('All packages OK')"
```

### Fix 3: Simplify Command

```bash
# Minimal command
python multi_iteration_orchestrator.py --target app

# With explicit paths
python multi_iteration_orchestrator.py \
  --target "$(pwd)/app" \
  --current-dir "$(pwd)"
```

---

## Getting More Information

### Enable Verbose Pytest Output

Edit the orchestrator or run pytest manually with `-vv`:

```bash
pytest tests/generated -vv --tb=short
```

### Check Pytest Configuration

```bash
cat pytest.ini
```

Ensure coverage settings are correct.

### Review Coverage Configuration

```bash
# Check what's being covered
cat pytest.ini | grep -A 20 "\[run\]"
```

### Test OpenAI API Connection

```bash
python -c "
import openai
import os
openai.api_key = os.getenv('OPENAI_API_KEY')
print('API key configured:', 'sk-...' + openai.api_key[-4:] if openai.api_key else 'NOT SET')
"
```

---

## Still Having Issues?

### Collect Diagnostic Information

```bash
# System info
python --version
pip --version
pwd

# Environment
env | grep -E "OPENAI|PYTHON|PATH"

# Files
ls -la tests/ app/ src/
ls -la coverage.xml htmlcov/ coverage_gaps.json

# Package versions
pip list | grep -E "openai|pytest|coverage"
```

### Run With Debug Output

The improved orchestrator now shows:
- Full error messages from commands
- Output from test generation
- Detailed diagnostics when things fail

### Check the Iteration Report

```bash
cat iteration_report.json | python -m json.tool
```

This shows exactly what happened in each iteration.

---

## Example: Full Working Flow

Here's a complete example from start to finish:

```bash
# 1. Navigate to project
cd /path/to/your/project

# 2. Set API key
export OPENAI_API_KEY="sk-your-key-here"

# 3. Install dependencies
pip install -r requirements.txt

# 4. Run manual tests (if any) to get initial coverage
pytest tests/manual --cov=app --cov-config=pytest.ini --cov-report=xml --cov-report=html

# 5. Run orchestrator
python multi_iteration_orchestrator.py --target app --iterations 3 --target-coverage 90

# 6. View results
cat iteration_report.json
open htmlcov/index.html
```

That's it! 🎉
