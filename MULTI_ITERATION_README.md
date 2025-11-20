# Multi-Iteration AI Test Generation

Automatically generate AI-powered tests across multiple iterations to achieve **90%+ code coverage** on uncovered parts of your codebase.

## Overview

The multi-iteration test generator runs up to **3 iterations** of AI test generation, each time:

1. **Analyzing** coverage gaps (uncovered code)
2. **Generating** AI tests targeting only the uncovered sections
3. **Running** all tests (manual + AI-generated) with coverage measurement
4. **Re-analyzing** to find remaining gaps
5. **Stopping early** if 90% coverage is achieved

### Key Features

- ✅ **Iterative Improvement**: Runs multiple rounds until target coverage achieved
- ✅ **Gap-Focused**: Only generates tests for uncovered code (not already covered)
- ✅ **Early Stopping**: Stops once 90% coverage reached (doesn't waste resources)
- ✅ **Cumulative Testing**: Each iteration runs ALL tests (manual + all AI-generated)
- ✅ **Detailed Tracking**: Logs each iteration's progress and coverage improvement
- ✅ **Smart Analysis**: Re-analyzes gaps after each iteration for targeted generation

## Quick Start

### Method 1: Using the Shell Script (Recommended)

```bash
# Basic usage - 3 iterations to achieve 90% coverage on ./app
./run_multi_iteration_tests.sh --target app

# Custom iterations and coverage target
./run_multi_iteration_tests.sh --target app --max-iterations 5 --target-coverage 95

# Specify output directory
./run_multi_iteration_tests.sh --target app --outdir ./tests/ai_generated
```

### Method 2: Using Python Module

```bash
# Basic usage
python -m src.multi_iteration_test_generator --target app

# With custom parameters
python -m src.multi_iteration_test_generator \
    --target app \
    --max-iterations 3 \
    --target-coverage 90.0 \
    --outdir tests/generated
```

## How It Works

### Iteration Flow

```
┌─────────────────────────────────────────────────────────┐
│  ITERATION 1                                            │
├─────────────────────────────────────────────────────────┤
│  1. Run manual tests → baseline coverage (e.g., 85%)   │
│  2. Analyze gaps → identify uncovered lines/functions   │
│  3. Generate AI tests → target uncovered code           │
│  4. Run ALL tests → manual + iteration_1 tests          │
│  5. Measure coverage → e.g., 87% (improvement: +2%)     │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│  ITERATION 2                                            │
├─────────────────────────────────────────────────────────┤
│  1. Re-analyze gaps → find NEW uncovered code           │
│  2. Generate NEW AI tests → target remaining gaps       │
│  3. Run ALL tests → manual + iteration_1 + iteration_2  │
│  4. Measure coverage → e.g., 89.5% (improvement: +2.5%) │
└─────────────────────────────────────────────────────────┘
                         ↓
┌─────────────────────────────────────────────────────────┐
│  ITERATION 3                                            │
├─────────────────────────────────────────────────────────┤
│  1. Re-analyze gaps → find NEW uncovered code           │
│  2. Generate NEW AI tests → target remaining gaps       │
│  3. Run ALL tests → manual + iteration_1 + 2 + 3        │
│  4. Measure coverage → e.g., 91% (improvement: +1.5%)   │
│  ✅ TARGET ACHIEVED! Stop early                         │
└─────────────────────────────────────────────────────────┘
```

### Directory Structure After Running

```
project/
├── app/                          # Your source code
├── tests/                        # Manual tests
└── tests/generated/              # AI-generated tests
    ├── iteration_1/              # Tests from iteration 1
    │   ├── test_unit_*.py
    │   ├── test_integ_*.py
    │   └── conftest.py
    ├── iteration_2/              # Tests from iteration 2
    │   ├── test_unit_*.py
    │   └── test_integ_*.py
    └── iteration_3/              # Tests from iteration 3
        └── test_unit_*.py
```

## Configuration Options

| Option | Default | Description |
|--------|---------|-------------|
| `--target` | (required) | Path to Python project to test |
| `--max-iterations` | `3` | Maximum number of iterations to run |
| `--target-coverage` | `90.0` | Target coverage percentage |
| `--outdir` | `tests/generated` | Output directory for generated tests |

## Output Files

After running, you'll get:

1. **`iteration_log.json`** - Detailed log of each iteration
   ```json
   {
     "target_root": "app",
     "max_iterations": 3,
     "target_coverage": 90.0,
     "iterations": [
       {
         "iteration": 1,
         "coverage_before": 85.0,
         "coverage_after": 87.0,
         "improvement": 2.0,
         "generated_files": [...],
         "duration_seconds": 45.2
       },
       ...
     ]
   }
   ```

2. **`multi_iteration_report.txt`** - Human-readable summary report
   ```
   Multi-Iteration Test Generation Report
   ========================================

   Target Root: app
   Target Coverage: 90.0%
   Iterations Run: 3/3

   Initial Coverage: 85.00%
   Final Coverage: 91.00%
   Total Improvement: 6.00%

   Target Achieved: YES

   Iteration Summary:
     Iteration 1: 85.00% → 87.00% (+2.00%)
     Iteration 2: 87.00% → 89.50% (+2.50%)
     Iteration 3: 89.50% → 91.00% (+1.50%)
   ```

3. **`coverage_gaps.json`** - Latest coverage gap analysis (updated each iteration)

4. **`coverage.xml`** - XML coverage report (updated each iteration)

5. **`htmlcov/`** - HTML coverage report (updated each iteration)

## Example Usage

### Example 1: Basic Multi-Iteration Run

```bash
# Your current coverage: 85%
./run_multi_iteration_tests.sh --target app

# Output:
# ========================================
# ITERATION 1/3
# ========================================
# 🔍 Analyzing coverage gaps...
#    Current coverage: 85.00%
# 🤖 Generating AI tests for uncovered code...
#    Generated 5 test files
# 🧪 Running all tests with coverage...
#    Coverage after tests: 87.50%
#    Improvement: +2.50%
#
# ========================================
# ITERATION 2/3
# ========================================
# ...
# Coverage after tests: 90.20%
#
# 🎉 SUCCESS! Target coverage 90% achieved!
# Final coverage: 90.20%
# Iterations completed: 2/3
```

### Example 2: Higher Coverage Target

```bash
# Aim for 95% coverage with up to 5 iterations
./run_multi_iteration_tests.sh \
    --target app \
    --max-iterations 5 \
    --target-coverage 95.0
```

### Example 3: Integration with CI/CD

```yaml
# .github/workflows/multi-iteration-tests.yml
name: Multi-Iteration Test Generation

on:
  push:
    branches: [ main ]

jobs:
  multi-iteration-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2

      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.9'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt

      - name: Run multi-iteration test generation
        env:
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
        run: |
          ./run_multi_iteration_tests.sh --target app --max-iterations 3

      - name: Upload coverage report
        uses: actions/upload-artifact@v2
        with:
          name: coverage-report
          path: htmlcov/

      - name: Upload iteration log
        uses: actions/upload-artifact@v2
        with:
          name: iteration-log
          path: iteration_log.json
```

## Understanding the Results

### Success Scenarios

✅ **Target Achieved Early**: Stops at iteration 2 if 90% reached
```
Iterations Run: 2/3
Target Achieved: YES
```

✅ **Target Achieved at Last Iteration**
```
Iterations Run: 3/3
Final Coverage: 91.5%
Target Achieved: YES
```

✅ **Good Progress Made** (even if target not fully achieved)
```
Iterations Run: 3/3
Initial Coverage: 85.0%
Final Coverage: 89.5%
Improvement: +4.5%
Target Achieved: NO (but close!)
```

### Interpreting Coverage Improvements

- **+2-5% per iteration**: Excellent progress
- **+0.5-2% per iteration**: Good progress, may need more iterations
- **<0.5% per iteration**: Limited progress, may need manual intervention

### Common Issues

**Issue**: No tests generated in iteration
```
ℹ️  No new tests generated (gaps may be too small)
```
**Solution**: Remaining gaps may be in error handlers, edge cases, or complex logic that's hard to auto-generate. Consider manual test additions.

**Issue**: Coverage not improving
```
⚠️  Small improvement (<0.5%). Consider manual intervention.
```
**Solution**: AI may be struggling with specific code patterns. Review `coverage_gaps.json` to see what's uncovered and add manual tests.

## Architecture

### Key Components

1. **`src/multi_iteration_test_generator.py`**
   - Main orchestrator
   - Manages iteration loop
   - Tracks progress and history

2. **`src/coverage_gap_analyzer.py`**
   - Analyzes coverage reports
   - Identifies uncovered lines, functions, classes
   - Generates `coverage_gaps.json`

3. **`src/gen/enhanced_generate.py`**
   - AI test generation engine
   - Gap-focused mode support
   - Generates tests targeting uncovered code

4. **`src/gen/gap_aware_analysis.py`**
   - Filters analysis to uncovered code only
   - Enhances prompts with coverage context
   - Ensures AI focuses on gaps

### Data Flow

```
Manual Tests → Coverage Report → Gap Analysis → AI Generation → All Tests → New Coverage
      ↓              ↓                ↓               ↓              ↓            ↓
   tests/      coverage.xml    coverage_gaps.json  iteration_1/  combined     higher %
                                                                  pytest        ↓
                                                                            re-analyze
                                                                                ↓
                                                                          iteration_2/...
```

## Advanced Usage

### Environment Variables

You can customize behavior with environment variables:

```bash
# Enable debug mode
export TESTGEN_DEBUG=true

# Custom OpenAI settings
export AZURE_OPENAI_API_KEY="your-key"
export AZURE_OPENAI_ENDPOINT="your-endpoint"
export AZURE_OPENAI_DEPLOYMENT="gpt-4"

# Run multi-iteration
./run_multi_iteration_tests.sh --target app
```

### Programmatic Usage

```python
from src.multi_iteration_test_generator import MultiIterationTestGenerator

# Create generator
generator = MultiIterationTestGenerator(
    target_root="app",
    max_iterations=3,
    target_coverage=90.0,
    output_dir="tests/generated"
)

# Run iterations
result = generator.run()

# Check results
if result["target_achieved"]:
    print(f"Success! Coverage: {result['final_coverage']:.2f}%")
    print(f"Iterations: {result['iterations_run']}")
else:
    print(f"Partial success. Coverage: {result['final_coverage']:.2f}%")
```

## Comparison: Single-Pass vs Multi-Iteration

### Single-Pass (Old Approach)

```bash
# Run once
python -m src.gen --target app --coverage-mode gap-focused

# Result: 85% → 87% coverage (limited improvement)
```

### Multi-Iteration (New Approach)

```bash
# Run 3 iterations
./run_multi_iteration_tests.sh --target app

# Result: 85% → 91% coverage (excellent improvement!)
# Each iteration targets NEW gaps discovered
```

## Best Practices

1. **Start with Good Manual Tests**: The better your baseline coverage, the more focused AI generation will be

2. **Review Generated Tests**: After each iteration, review tests in `iteration_*/` to ensure quality

3. **Set Realistic Targets**: 90% is a good target; 100% may be unrealistic for complex codebases

4. **Monitor Improvements**: If improvement < 0.5% per iteration, consider manual intervention

5. **Commit Generated Tests**: Add generated tests to version control so they run in CI/CD

## Troubleshooting

### Tests fail during iteration

The system continues even if some tests fail. Check `output.log` for details.

### Coverage not parsed correctly

Ensure pytest-cov is installed:
```bash
pip install pytest-cov
```

### API rate limits

If you hit OpenAI rate limits, the system will retry with backoff. Consider:
- Reducing concurrent test generation
- Using a higher-tier API plan

## Contributing

Found a bug or have a feature request? Please open an issue!

## License

This tool is part of your test generation framework.
