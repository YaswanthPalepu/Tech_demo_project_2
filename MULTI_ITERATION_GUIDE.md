# Multi-Iteration Test Generation Guide

## Overview

The **Multi-Iteration Orchestrator** (`multi_iteration_orchestrator.py`) is a sophisticated tool that runs **up to 3 iterations** of AI-powered test generation to achieve **>90% code coverage** on uncovered parts of your codebase.

## How It Works

```
Manual Tests (85% coverage)
    ↓
┌─────────────────────────────────────┐
│   Multi-Iteration Orchestrator     │
├─────────────────────────────────────┤
│  Iteration 1:                       │
│    → coverage_gap_analyzer.py       │ ← Analyzes uncovered code
│    → enhanced_generate.py           │ ← Generates AI tests
│    → pytest --cov (all tests)       │ ← Runs manual + AI tests
│    → Result: 87% (+2%)              │
├─────────────────────────────────────┤
│  Iteration 2:                       │
│    → Re-analyze NEW gaps            │
│    → Generate MORE AI tests         │
│    → pytest --cov (all tests)       │
│    → Result: 89.5% (+2.5%)          │
├─────────────────────────────────────┤
│  Iteration 3:                       │
│    → Re-analyze FINAL gaps          │
│    → Generate FINAL AI tests        │
│    → pytest --cov (all tests)       │
│    → Result: 91% (+1.5%)            │
│    ✅ TARGET ACHIEVED!              │
└─────────────────────────────────────┘
```

## Usage

### Basic Usage

```bash
python multi_iteration_orchestrator.py --target app
```

This will:
- Run up to 3 iterations
- Target 90% code coverage
- Generate tests in `./tests/generated/`
- Analyze the `app/` directory

### Advanced Usage

```bash
python multi_iteration_orchestrator.py \
  --target app \
  --iterations 5 \
  --target-coverage 95 \
  --outdir ./tests/ai_generated
```

### Command-Line Options

| Option | Description | Default |
|--------|-------------|---------|
| `--target` | Target directory to analyze (required) | - |
| `--current-dir` | Current working directory | `.` |
| `--iterations` | Maximum number of iterations | `3` |
| `--target-coverage` | Target coverage percentage | `90.0` |
| `--outdir` | Output directory for generated tests | `./tests/generated` |

## Prerequisites

### 1. Run Manual Tests First

Before running the orchestrator, ensure you have:

1. **Manual tests** in place (or none, orchestrator will handle both cases)
2. **Initial coverage report** generated:

```bash
# If you have manual tests
pytest tests/manual --cov=app --cov-config=pytest.ini --cov-report=xml --cov-report=html

# If you have no manual tests, the orchestrator will start from scratch
# Just ensure pytest and coverage are configured properly
```

3. **Coverage gap analysis** run at least once:

```bash
python src/coverage_gap_analyzer.py \
  --target app \
  --current-dir . \
  --output coverage_gaps.json
```

### 2. Environment Setup

Ensure you have:

- Python 3.8+
- pytest and pytest-cov installed
- OpenAI API key configured (for AI test generation)
- All dependencies from `requirements.txt` installed

```bash
pip install -r requirements.txt
```

## What Each Iteration Does

### Iteration Flow

Each iteration consists of 4 steps:

#### Step 1: Analyze Coverage Gaps
```bash
python src/coverage_gap_analyzer.py \
  --target app \
  --current-dir . \
  --output coverage_gaps.json
```

**Output:**
- `coverage_gaps.json` - Detailed analysis of uncovered code
- Line-by-line gap identification
- Function and class level gaps

#### Step 2: Generate AI Tests (Gap-Focused)
```bash
GAP_FOCUSED_MODE=true python -m src.gen \
  --target app \
  --outdir ./tests/generated \
  --force \
  --coverage-mode gap-focused
```

**Output:**
- `./tests/generated/test_unit_*.py` - Unit tests for uncovered code
- `./tests/generated/test_integ_*.py` - Integration tests
- `./tests/generated/conftest.py` - Test fixtures

#### Step 3: Run All Tests with Coverage
```bash
pytest tests/manual tests/generated \
  --cov=app \
  --cov-config=pytest.ini \
  --cov-report=xml \
  --cov-report=html \
  --cov-report=term-missing \
  -v
```

**Output:**
- `coverage.xml` - Machine-readable coverage report
- `htmlcov/` - HTML coverage report
- Terminal output with coverage percentage

#### Step 4: Check Target Coverage

The orchestrator:
- Parses `coverage_gaps.json` to get new coverage percentage
- Calculates coverage gain from this iteration
- Checks if ≥90% coverage achieved
- Decides whether to continue to next iteration

### Stopping Conditions

The orchestrator stops when:

1. ✅ **Target coverage achieved** (≥90%)
2. ⚠️ **Max iterations reached** (3 iterations)
3. ❌ **Error occurred** (but will report partial progress)

## Output Files

After running, you'll find:

```
.
├── coverage_gaps.json              # Latest coverage gap analysis
├── coverage.xml                    # Coverage report (XML)
├── htmlcov/                        # Coverage report (HTML)
│   └── index.html                  # Open this to view coverage visually
├── iteration_report.json           # Detailed iteration metrics (NEW!)
└── tests/
    ├── manual/                     # Your manual tests
    └── generated/                  # AI-generated tests
        ├── test_unit_*.py          # Unit tests
        ├── test_integ_*.py         # Integration tests
        └── conftest.py             # Test fixtures
```

### Iteration Report (`iteration_report.json`)

Example:

```json
{
  "timestamp": "2025-11-20T10:30:00",
  "configuration": {
    "target_dir": "app",
    "max_iterations": 3,
    "target_coverage": 90.0,
    "output_dir": "./tests/generated"
  },
  "summary": {
    "total_iterations": 3,
    "initial_coverage": 85.01,
    "final_coverage": 91.24,
    "total_coverage_gain": 6.23,
    "target_achieved": true
  },
  "iterations": [
    {
      "iteration": 1,
      "duration_seconds": 45.3,
      "initial_coverage": 85.01,
      "final_coverage": 87.15,
      "coverage_gain": 2.14,
      "tests_generated": 12,
      "gaps_analyzed": 73,
      "success": true
    },
    {
      "iteration": 2,
      "duration_seconds": 38.7,
      "initial_coverage": 87.15,
      "final_coverage": 89.82,
      "coverage_gain": 2.67,
      "tests_generated": 8,
      "gaps_analyzed": 52,
      "success": true
    },
    {
      "iteration": 3,
      "duration_seconds": 32.1,
      "initial_coverage": 89.82,
      "final_coverage": 91.24,
      "coverage_gain": 1.42,
      "tests_generated": 5,
      "gaps_analyzed": 34,
      "success": true
    }
  ]
}
```

## Example Run

### Starting State
- Initial coverage: 85.01%
- Missing statements: 73
- Files with gaps: 6

### Running the Orchestrator

```bash
$ python multi_iteration_orchestrator.py --target app

================================================================================
🔄 MULTI-ITERATION TEST GENERATION ORCHESTRATOR
================================================================================
Target Directory: app
Max Iterations: 3
Target Coverage: 90.0%
Output Directory: ./tests/generated
================================================================================

🎯 Starting Coverage: 85.01%
🎯 Target Coverage: 90.00%
📊 Gap to Target: 4.99%

================================================================================
🔄 STARTING ITERATION 1/3
================================================================================

📊 ITERATION 1: Analyzing Coverage Gaps
--------------------------------------------------------------------------------
  ▶ Running coverage gap analyzer
    Command: python src/coverage_gap_analyzer.py --target app --current-dir . --output coverage_gaps.json
    ✅ Success

  📈 Coverage Analysis:
     Current Coverage: 85.01%
     Missing Statements: 73/487
     Files with Gaps: 6

🤖 ITERATION 1: Generating AI Tests (Gap-Focused)
--------------------------------------------------------------------------------
  ▶ Generating tests for uncovered code
    Command: python -m src.gen --target app --outdir ./tests/generated --force --coverage-mode gap-focused
    Mode: GAP_FOCUSED_MODE=true
    ✅ Generated 12 test files

🧪 ITERATION 1: Running All Tests with Coverage
--------------------------------------------------------------------------------
  📁 Including manual tests: tests/manual
  📁 Including generated tests: tests/generated
  ▶ Running pytest with coverage
    Command: pytest tests/manual tests/generated --cov=app --cov-config=pytest.ini --cov-report=xml --cov-report=html --cov-report=term-missing -v
    ✅ Coverage report generated

📊 Final Coverage: 87.15%
📈 Coverage Gain: +2.14%

================================================================================
📋 ITERATION 1 SUMMARY
================================================================================
Duration: 45.30s
Initial Coverage: 85.01%
Final Coverage: 87.15%
Coverage Gain: +2.14%
Tests Generated: 12
Gaps Analyzed: 73
Success: ✅
================================================================================

[Iterations 2 and 3 continue similarly...]

================================================================================
📊 FINAL MULTI-ITERATION REPORT
================================================================================

Total Iterations Run: 3
Initial Coverage: 85.01%
Final Coverage: 91.24%
Total Coverage Gain: +6.23%
Target Coverage: 90.0%
Target Achieved: ✅ YES

📈 Iteration Breakdown:
--------------------------------------------------------------------------------
  Iteration 1: ✅ 85.01% → 87.15% (+2.14%) | 12 tests | 45.30s
  Iteration 2: ✅ 87.15% → 89.82% (+2.67%) | 8 tests | 38.70s
  Iteration 3: ✅ 89.82% → 91.24% (+1.42%) | 5 tests | 32.10s

================================================================================
🎉 SUCCESS! Target coverage achieved!
================================================================================

📄 Report saved to: iteration_report.json
⏱️  Total Time: 116.10s
```

## Integration with Existing Pipeline

### Option 1: Replace Gap-Based Section in `local_pipeline-1.sh`

In your existing `local_pipeline-1.sh`, replace the gap-based generation section with:

```bash
# Multi-iteration test generation
if (( $(echo "$MANUAL_COVERAGE < 90" | bc -l) )); then
  echo "📊 Running multi-iteration test generation..."
  python multi_iteration_orchestrator.py \
    --target "$TARGET_ROOT" \
    --current-dir "$CURRENT_DIR" \
    --iterations 3 \
    --target-coverage 90 \
    --outdir "./tests/generated"

  # Check if target achieved
  if [ $? -eq 0 ]; then
    echo "✅ Multi-iteration test generation succeeded!"
  else
    echo "⚠️  Multi-iteration test generation completed with warnings"
  fi
fi
```

### Option 2: Standalone Usage

Run the orchestrator independently:

```bash
# 1. Run manual tests and get initial coverage
pytest tests/manual --cov=app --cov-config=pytest.ini --cov-report=xml --cov-report=html

# 2. Run initial gap analysis
python src/coverage_gap_analyzer.py --target app --current-dir . --output coverage_gaps.json

# 3. Run multi-iteration orchestrator
python multi_iteration_orchestrator.py --target app

# 4. View final coverage report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

## Core Logic Preservation

The orchestrator **does NOT change** your existing core logic:

✅ **Preserved:**
- `coverage_gap_analyzer.py` logic (exact same commands)
- `src.gen` (enhanced_generate.py) logic (exact same commands)
- Gap-focused mode behavior
- Coverage measurement approach
- Test generation quality

✅ **Added:**
- Iteration loop (3 iterations max)
- Progress tracking and reporting
- Automatic stopping when target achieved
- Detailed metrics per iteration
- JSON report generation

## Troubleshooting

### Issue: Coverage not improving between iterations

**Solution:**
- Check if there are hard-to-test code sections (error handlers, edge cases)
- Review generated tests in `./tests/generated/`
- Consider writing manual tests for complex scenarios
- Increase iterations: `--iterations 5`

### Issue: Tests failing during pytest run

**Solution:**
- The orchestrator continues even if some tests fail
- Review test failures in pytest output
- Fix failing tests manually
- Re-run the orchestrator

### Issue: OpenAI API errors during test generation

**Solution:**
- Check OpenAI API key: `echo $OPENAI_API_KEY`
- Verify API quota and rate limits
- Check internet connectivity
- Review `src/gen/openai_client.py` configuration

### Issue: No coverage improvement after iteration

**Solution:**
- The orchestrator will continue to next iteration
- May indicate coverage plateau (hard-to-test code)
- Review `coverage_gaps.json` to see remaining gaps
- Consider manual test additions

## Performance Tips

### 1. Start with Good Manual Tests
Better initial coverage (85%+) means fewer iterations needed.

### 2. Use Specific Target Directory
```bash
# More focused
python multi_iteration_orchestrator.py --target app/auth

# Less focused (slower)
python multi_iteration_orchestrator.py --target app
```

### 3. Adjust Iterations Based on Initial Coverage

| Initial Coverage | Recommended Iterations |
|------------------|------------------------|
| 80-85% | 3 iterations |
| 85-88% | 2 iterations |
| 88-90% | 1 iteration |
| 90%+ | None needed |

### 4. Monitor Iteration Report

Check `iteration_report.json` after each run to understand:
- Which iterations were most effective
- Coverage gain trends
- Optimal stopping point

## Next Steps

After achieving >90% coverage:

1. **Review Generated Tests**
   ```bash
   ls -la tests/generated/
   ```

2. **View Coverage Report**
   ```bash
   open htmlcov/index.html
   ```

3. **Manual Review**
   - Check test quality
   - Add assertions where needed
   - Refactor duplicate tests

4. **Commit Tests**
   ```bash
   git add tests/generated/
   git commit -m "feat: add AI-generated tests (91% coverage)"
   ```

5. **Integrate into CI/CD**
   - Add to GitHub Actions
   - Set coverage thresholds
   - Run on every PR

## FAQ

**Q: Can I run more than 3 iterations?**
A: Yes! Use `--iterations 5` or any number you want.

**Q: Will this overwrite my manual tests?**
A: No, manual tests in `tests/manual/` are preserved. Only `tests/generated/` is updated.

**Q: What if I don't reach 90% after 3 iterations?**
A: The orchestrator will report the final coverage achieved and suggest next steps. You can re-run with more iterations or add manual tests.

**Q: Can I change the target coverage?**
A: Yes! Use `--target-coverage 95` for 95% target.

**Q: Does this work with any Python project?**
A: Yes! The orchestrator is framework-agnostic and works with any Python codebase that has pytest configured.

**Q: How long does each iteration take?**
A: Typically 30-60 seconds per iteration, depending on codebase size and OpenAI API response times.

## Support

For issues or questions:
1. Check the iteration report: `iteration_report.json`
2. Review coverage gaps: `coverage_gaps.json`
3. Check test output: `pytest -v tests/generated/`
4. Review the codebase documentation

Happy testing! 🎉
