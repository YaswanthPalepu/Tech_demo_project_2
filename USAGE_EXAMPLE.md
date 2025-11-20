# Usage Example: Multi-Iteration Test Generation

This guide shows how to use the multi-iteration test generator with a real project.

## Prerequisites

1. Python 3.8+
2. pytest and pytest-cov installed
3. OpenAI API credentials configured

```bash
pip install pytest pytest-cov
export AZURE_OPENAI_API_KEY="your-key"
export AZURE_OPENAI_ENDPOINT="your-endpoint"
export AZURE_OPENAI_DEPLOYMENT="gpt-4"
```

## Step-by-Step Example

### 1. Project Setup

Assume you have a FastAPI/Flask/Django project with this structure:

```
my-project/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── auth.py
│   ├── model.py
│   ├── utils.py
│   └── middleware.py
└── tests/
    ├── test_auth.py
    └── test_main.py
```

### 2. Check Initial Coverage

First, run your manual tests to see baseline coverage:

```bash
cd my-project
python -m pytest tests/ --cov=app --cov-report=term --cov-report=xml
```

Example output:
```
Name                Stmts   Miss  Cover
---------------------------------------
app/__init__.py        5      0   100%
app/auth.py           39     15    62%
app/main.py          154     40    74%
app/middleware.py     92      1    99%
app/model.py          82      3    96%
app/utils.py          49     10    80%
---------------------------------------
TOTAL                487     73    85%
```

**Current Coverage: 85%** - We need to get to 90%+

### 3. Run Multi-Iteration Test Generation

Copy the multi-iteration generator files to your project:

```bash
# Copy from this repo to your project
cp src/multi_iteration_test_generator.py my-project/src/
cp run_multi_iteration_tests.sh my-project/
cd my-project
```

Run the multi-iteration generator:

```bash
./run_multi_iteration_tests.sh --target app --max-iterations 3
```

### 4. Watch the Iterations

**Iteration 1:**
```
========================================
ITERATION 1/3
========================================

🔍 Step 1: Analyzing coverage gaps...
   Current coverage: 85.00%

🤖 Step 2: Generating AI tests for uncovered code...
   Generated 5 test files
   - test_unit_20241120_01.py (auth error handlers)
   - test_unit_20241120_02.py (main edge cases)
   - test_integ_20241120_01.py (middleware integration)
   - test_integ_20241120_02.py (utils validation)
   - test_e2e_20241120_01.py (full workflows)

🧪 Step 3: Running all tests (manual + AI) with coverage...
   Running tests from: tests, tests/generated/iteration_1
   Coverage after tests: 87.50%
   Improvement: +2.50%

🔄 Step 4: Preparing for next iteration...
```

**Iteration 2:**
```
========================================
ITERATION 2/3
========================================

🔍 Step 1: Analyzing coverage gaps...
   Current coverage: 87.50%

🤖 Step 2: Generating AI tests for uncovered code...
   Generated 3 test files (targeting NEW gaps)
   - test_unit_20241120_03.py (auth remaining gaps)
   - test_integ_20241120_03.py (error conditions)
   - test_unit_20241120_04.py (utils edge cases)

🧪 Step 3: Running all tests (manual + AI) with coverage...
   Running tests from: tests, tests/generated/iteration_1, tests/generated/iteration_2
   Coverage after tests: 89.80%
   Improvement: +2.30%

📈 Improvement this iteration: +2.30%
```

**Iteration 3:**
```
========================================
ITERATION 3/3
========================================

🔍 Step 1: Analyzing coverage gaps...
   Current coverage: 89.80%

🤖 Step 2: Generating AI tests for uncovered code...
   Generated 2 test files (targeting final gaps)
   - test_unit_20241120_05.py (final edge cases)
   - test_integ_20241120_04.py (exception paths)

🧪 Step 3: Running all tests (manual + AI) with coverage...
   Running tests from: tests, tests/generated/iteration_1, iteration_2, iteration_3
   Coverage after tests: 91.20%
   Improvement: +1.40%

🎉 SUCCESS! Target coverage 90% achieved!
Final coverage: 91.20%
Iterations completed: 3/3
```

### 5. Review Results

**Final Report:**
```
========================================
MULTI-ITERATION TEST GENERATION - FINAL REPORT
========================================
Target Root: app
Target Coverage: 90.0%
Iterations Run: 3/3

Initial Coverage: 85.00%
Final Coverage: 91.20%
Total Improvement: 6.20%

Target Achieved: ✅ YES

Iteration Summary:
--------------------------------------------------------------------------------
  Iteration 1:
    Coverage: 85.00% → 87.50% (+2.50%)
    Tests Generated: 5
    Duration: 45.2s

  Iteration 2:
    Coverage: 87.50% → 89.80% (+2.30%)
    Tests Generated: 3
    Duration: 38.7s

  Iteration 3:
    Coverage: 89.80% → 91.20% (+1.40%)
    Tests Generated: 2
    Duration: 32.1s
========================================
```

### 6. Verify Generated Tests

Check the generated test structure:

```bash
ls -la tests/generated/
```

Output:
```
tests/generated/
├── iteration_1/
│   ├── conftest.py
│   ├── test_unit_20241120_01.py
│   ├── test_unit_20241120_02.py
│   ├── test_integ_20241120_01.py
│   ├── test_integ_20241120_02.py
│   └── test_e2e_20241120_01.py
├── iteration_2/
│   ├── test_unit_20241120_03.py
│   ├── test_integ_20241120_03.py
│   └── test_unit_20241120_04.py
└── iteration_3/
    ├── test_unit_20241120_05.py
    └── test_integ_20241120_04.py
```

### 7. Run All Tests

Verify all tests pass:

```bash
python -m pytest tests/ tests/generated/ --cov=app --cov-report=html
```

View the HTML coverage report:

```bash
open htmlcov/index.html
```

### 8. Commit Generated Tests

Add the generated tests to version control:

```bash
git add tests/generated/
git commit -m "Add AI-generated tests from multi-iteration generation (85% → 91% coverage)"
git push
```

## Advanced Example: CI/CD Integration

### GitHub Actions Workflow

Create `.github/workflows/multi-iteration-tests.yml`:

```yaml
name: Multi-Iteration Test Generation

on:
  push:
    branches: [ main, develop ]
  pull_request:
    branches: [ main ]

jobs:
  generate-and-test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.9'

      - name: Install dependencies
        run: |
          pip install -r requirements.txt

      - name: Run existing manual tests
        run: |
          python -m pytest tests/ --cov=app --cov-report=term

      - name: Run multi-iteration test generation
        env:
          AZURE_OPENAI_API_KEY: ${{ secrets.AZURE_OPENAI_API_KEY }}
          AZURE_OPENAI_ENDPOINT: ${{ secrets.AZURE_OPENAI_ENDPOINT }}
          AZURE_OPENAI_DEPLOYMENT: ${{ secrets.AZURE_OPENAI_DEPLOYMENT }}
        run: |
          ./run_multi_iteration_tests.sh \
            --target app \
            --max-iterations 3 \
            --target-coverage 90

      - name: Run all tests with coverage
        run: |
          python -m pytest tests/ tests/generated/ \
            --cov=app \
            --cov-report=xml \
            --cov-report=html

      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v3
        with:
          files: ./coverage.xml
          flags: multi-iteration

      - name: Upload HTML coverage report
        uses: actions/upload-artifact@v3
        with:
          name: coverage-report
          path: htmlcov/

      - name: Upload iteration log
        uses: actions/upload-artifact@v3
        with:
          name: iteration-log
          path: |
            iteration_log.json
            multi_iteration_report.txt

      - name: Comment PR with results
        if: github.event_name == 'pull_request'
        uses: actions/github-script@v6
        with:
          script: |
            const fs = require('fs');
            const report = fs.readFileSync('multi_iteration_report.txt', 'utf8');
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: `## Multi-Iteration Test Generation Results\n\`\`\`\n${report}\n\`\`\``
            });
```

## Troubleshooting

### Issue: "No manual tests found"

If you get this warning, ensure you have manual tests:

```bash
mkdir -p tests
# Create at least one manual test
cat > tests/test_basic.py << 'EOF'
def test_example():
    assert True
EOF
```

### Issue: "Coverage not improving"

Check what's uncovered:

```bash
cat coverage_gaps.json | jq '.files_with_gaps'
```

Review the uncovered sections and consider:
1. Adding manual tests for complex logic
2. Adjusting the max iterations
3. Reviewing generated test quality

### Issue: "API rate limits"

If you hit rate limits:

1. Reduce parallelism (fewer tests per iteration)
2. Increase delays between iterations
3. Use a higher-tier OpenAI plan

## Best Practices

1. **Run manually first**: Test the flow before adding to CI/CD
2. **Review generated tests**: Check quality before committing
3. **Start with good baseline**: 70%+ manual coverage works best
4. **Iterate reasonably**: 3-5 iterations is usually optimal
5. **Monitor costs**: Each iteration calls OpenAI APIs
6. **Version control**: Commit generated tests for reproducibility

## Cost Estimation

Approximate OpenAI API costs per iteration:

- Small project (< 1000 lines): $0.10 - $0.50 per iteration
- Medium project (1000-5000 lines): $0.50 - $2.00 per iteration
- Large project (> 5000 lines): $2.00 - $10.00 per iteration

Total for 3 iterations: **$1-30** depending on project size

## Next Steps

1. Integrate into your CI/CD pipeline
2. Set up periodic test generation (weekly/monthly)
3. Monitor coverage trends over time
4. Refine based on your project's needs
