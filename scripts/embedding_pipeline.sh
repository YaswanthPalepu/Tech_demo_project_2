#!/bin/bash
# Enhanced test generation pipeline with embedding-based bug detection

set -e  # Exit on error

echo "=== Enhanced Pipeline with Embeddings ==="

# Configuration
PROJECT_ROOT=$(pwd)
APP_DIR="${PROJECT_ROOT}/app"
ANALYSIS_FILE="${PROJECT_ROOT}/analysis.json"
COVERAGE_FILE="${PROJECT_ROOT}/coverage_gaps.json"
BUG_SCAN_FILE="${PROJECT_ROOT}/bug_scan.json"
CLASSIFICATION_FILE="${PROJECT_ROOT}/error_classification.json"

# Step 1: Clean previous artifacts
echo ""
echo "Step 1: Cleaning previous artifacts..."
rm -f coverage_gaps.json analysis.json bug_scan.json error_classification.json
rm -f .coverage coverage.xml
rm -rf htmlcov/

# Step 2: Detect manual tests
echo ""
echo "Step 2: Detecting manual tests..."
python -m src.detect_manual_tests

# Step 3: Analyze codebase
echo ""
echo "Step 3: Analyzing codebase structure..."
python -m src.analyzer "${APP_DIR}" > "${ANALYSIS_FILE}"
echo "Analysis saved to ${ANALYSIS_FILE}"

# Step 4: INDEX CODEBASE INTO CHROMADB (NEW)
echo ""
echo "Step 4: Indexing codebase into ChromaDB..."
python -m src.embeddings.cli index "${ANALYSIS_FILE}"

# Step 5: INITIAL BUG SCAN (NEW)
echo ""
echo "Step 5: Scanning for bugs and security issues..."
python -m src.embeddings.cli scan \
    --min-severity medium \
    --output "${BUG_SCAN_FILE}" \
    --format json

# Check if critical issues found
CRITICAL_COUNT=$(cat "${BUG_SCAN_FILE}" | jq '[.files_with_issues[].entities[].security_issues[] | select(.severity == "critical")] | length')

if [ "$CRITICAL_COUNT" -gt 0 ]; then
    echo ""
    echo "⚠️  WARNING: Found ${CRITICAL_COUNT} CRITICAL security issue(s)!"
    echo "Review ${BUG_SCAN_FILE} before continuing."
    cat "${BUG_SCAN_FILE}" | jq '.files_with_issues[] | select(.total_security > 0)'
fi

# Step 6: Run manual tests with coverage (if any)
echo ""
echo "Step 6: Running manual tests with coverage..."
if [ -f manual_test_result.json ]; then
    MANUAL_COUNT=$(cat manual_test_result.json | jq '.manual_test_count')
    echo "Found ${MANUAL_COUNT} manual test(s)"

    if [ "$MANUAL_COUNT" -gt 0 ]; then
        # Extract manual test paths and run pytest
        MANUAL_TESTS=$(cat manual_test_result.json | jq -r '.manual_test_paths[]' | tr '\n' ' ')

        pytest -v \
            --cov=app \
            --cov-report=xml \
            --cov-report=html \
            ${MANUAL_TESTS}

        echo "Manual test coverage generated"
    fi
else
    echo "No manual tests found, skipping coverage"
fi

# Step 7: Analyze coverage gaps
echo ""
echo "Step 7: Analyzing coverage gaps..."
if [ -f coverage.xml ]; then
    python -m src.coverage_gap_analyzer
    echo "Coverage gaps saved to ${COVERAGE_FILE}"

    # Show coverage summary
    OVERALL_COVERAGE=$(cat "${COVERAGE_FILE}" | jq -r '.overall_coverage')
    echo "Overall coverage: ${OVERALL_COVERAGE}%"
else
    echo "No coverage data available"
fi

# Step 8: UPDATE INDEX WITH COVERAGE DATA (NEW)
echo ""
echo "Step 8: Updating index with coverage data..."
if [ -f "${COVERAGE_FILE}" ]; then
    python -m src.embeddings.cli index "${ANALYSIS_FILE}" \
        --coverage-file "${COVERAGE_FILE}"
    echo "Index updated with coverage information"
fi

# Step 9: Generate AI tests for gaps
echo ""
echo "Step 9: Generating AI tests for coverage gaps..."
if [ -f "${COVERAGE_FILE}" ]; then
    NEEDS_AI=$(cat "${COVERAGE_FILE}" | jq -r '.needs_ai_generation')

    if [ "$NEEDS_AI" = "true" ]; then
        echo "Coverage below 90%, generating AI tests..."
        export GAP_FOCUSED_MODE=true
        python -m src.gen
        echo "AI test generation complete"
    else
        echo "Coverage ≥90%, skipping AI test generation"
    fi
else
    echo "No coverage data, running full AI test generation..."
    python -m src.gen
fi

# Step 10: Run all tests (manual + AI generated)
echo ""
echo "Step 10: Running all tests..."
set +e  # Don't exit on test failures
pytest -v \
    --cov=app \
    --cov-report=xml \
    --cov-report=html \
    --cov-report=term \
    --tb=short \
    --json-report \
    --json-report-file=test_results.json

TEST_EXIT_CODE=$?
set -e

# Step 11: CLASSIFY TEST FAILURES (NEW)
echo ""
echo "Step 11: Classifying test failures..."
if [ -f test_results.json ]; then
    # Convert pytest JSON to classification format
    python - <<EOF
import json
import sys

with open('test_results.json', 'r') as f:
    results = json.load(f)

failures = []
for test in results.get('tests', []):
    if test.get('outcome') in ['failed', 'error']:
        failure = {
            'test_name': test.get('nodeid', 'unknown'),
            'error_type': test.get('call', {}).get('crash', {}).get('type', 'Unknown'),
            'error_message': test.get('call', {}).get('crash', {}).get('message', ''),
            'stacktrace': '\n'.join(test.get('call', {}).get('traceback', [])),
        }
        failures.append(failure)

with open('test_failures.json', 'w') as f:
    json.dump(failures, f, indent=2)

print(f"Extracted {len(failures)} test failure(s)")
EOF

    if [ -f test_failures.json ]; then
        FAILURE_COUNT=$(cat test_failures.json | jq 'length')

        if [ "$FAILURE_COUNT" -gt 0 ]; then
            echo "Classifying ${FAILURE_COUNT} test failure(s)..."

            python -m src.embeddings.cli classify test_failures.json \
                --output "${CLASSIFICATION_FILE}" \
                --format detailed

            # Show summary
            echo ""
            echo "=== Classification Summary ==="
            cat "${CLASSIFICATION_FILE}" | jq '.summary'

            echo ""
            echo "=== Recommendations ==="
            cat "${CLASSIFICATION_FILE}" | jq -r '.recommendations[]'

            # Show real bugs
            REAL_BUGS=$(cat "${CLASSIFICATION_FILE}" | jq '[.classifications[] | select(.classification == "REAL_BUG")] | length')
            if [ "$REAL_BUGS" -gt 0 ]; then
                echo ""
                echo "⚠️  Found ${REAL_BUGS} REAL BUG(S) - Fix these first!"
                cat "${CLASSIFICATION_FILE}" | jq '.classifications[] | select(.classification == "REAL_BUG") | {test: .test_name, action: .suggested_action}'
            fi
        else
            echo "No test failures to classify"
        fi
    fi
fi

# Step 12: Final coverage report
echo ""
echo "Step 12: Final coverage report..."
if [ -f coverage.xml ]; then
    python -m src.coverage_gap_analyzer

    FINAL_COVERAGE=$(cat coverage_gaps.json | jq -r '.overall_coverage')
    echo ""
    echo "=== FINAL RESULTS ==="
    echo "Coverage: ${FINAL_COVERAGE}%"

    if (( $(echo "$FINAL_COVERAGE >= 90" | bc -l) )); then
        echo "✓ Coverage target achieved (≥90%)"
    else
        echo "✗ Coverage below target (<90%)"
    fi
fi

# Step 13: Generate summary report
echo ""
echo "Step 13: Generating summary report..."
python - <<EOF
import json
from datetime import datetime

report = {
    'timestamp': datetime.now().isoformat(),
    'pipeline_version': 'v2.0-embeddings',
}

# Add bug scan summary
if True:
    try:
        with open('${BUG_SCAN_FILE}', 'r') as f:
            bug_scan = json.load(f)
            report['bug_scan'] = {
                'total_issues': bug_scan.get('issues_found', 0),
                'files_affected': len(bug_scan.get('files_with_issues', [])),
            }
    except:
        pass

# Add coverage summary
if True:
    try:
        with open('${COVERAGE_FILE}', 'r') as f:
            coverage = json.load(f)
            report['coverage'] = {
                'overall': coverage.get('overall_coverage', 0),
                'target_met': coverage.get('overall_coverage', 0) >= 90,
            }
    except:
        pass

# Add classification summary
if True:
    try:
        with open('${CLASSIFICATION_FILE}', 'r') as f:
            classification = json.load(f)
            report['test_failures'] = classification.get('summary', {})
    except:
        pass

with open('pipeline_report.json', 'w') as f:
    json.dump(report, f, indent=2)

print("Report saved to pipeline_report.json")
EOF

# Display final report
echo ""
echo "=== PIPELINE COMPLETE ==="
cat pipeline_report.json | jq .

# Exit with test result code
exit $TEST_EXIT_CODE
