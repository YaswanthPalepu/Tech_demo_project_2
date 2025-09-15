#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="${1:-$PWD}"
REPORT_DIR="$REPO_ROOT/reports/tests"
mkdir -p "$REPORT_DIR"

echo "Running pytest on: tests tests/generated"
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
export QT_QPA_PLATFORM=offscreen
export PYTHONPATH="$REPO_ROOT:$REPO_ROOT/src:$REPO_ROOT/target:$PYTHONPATH"

pytest \
  --maxfail=5 \
  --disable-warnings \
  --json-report \
  --json-report-file="$REPORT_DIR/test-results.json" \
  --html="$REPORT_DIR/report.html" \
  --self-contained-html \
  --cov="$REPO_ROOT" \
  --cov-report=term-missing \
  --cov-report=json:"$REPORT_DIR/coverage.json" \
  tests tests/generated || true
