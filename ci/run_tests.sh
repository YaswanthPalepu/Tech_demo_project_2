#!/usr/bin/env bash
set -euo pipefail

# USAGE: ci/run_tests.sh /absolute/path/to/target_repo
TARGET_REPO="${1:?pass path to target repo}"
cd "$TARGET_REPO"

# Keep target repo clean (only runtime artifacts under reports/)
REPORT_DIR="$(pwd)/reports/tests"
mkdir -p "$REPORT_DIR"

# Block hostile env/site plugins
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1

# Import paths for plain and src/ layouts
export PYTHONPATH="${TARGET_REPO}:${PYTHONPATH-}"
[[ -d src ]] && export PYTHONPATH="${TARGET_REPO}/src:${PYTHONPATH-}"

# Decide test dirs
TEST_DIRS=()
[[ -d tests ]] && TEST_DIRS+=("tests")
[[ -d tests/generated ]] && TEST_DIRS+=("tests/generated")
if [[ ${#TEST_DIRS[@]} -eq 0 ]]; then
  echo "No test directories found. Exiting 1 to signal no tests."
  exit 1
fi

# Enable pytest-django only if settings present
ENABLE_DJANGO=()
if [[ -n "${DJANGO_SETTINGS_MODULE-}" ]]; then
  ENABLE_DJANGO+=(-p django)
elif [[ -f manage.py ]] || compgen -G "*settings.py" >/dev/null; then
  ENABLE_DJANGO+=(-p django)
fi

# Compute coverage sources dynamically
COV_SOURCES="$(python - <<'PY'
import pathlib, os
root=pathlib.Path('.').resolve()
skip={'tests','tests_generated','tests-generated','.git','.github','venv','.venv','env',
      'node_modules','dist','build','__pycache__','.mypy_cache','.idea','.vscode','reports'}
sources=set()
for p in root.iterdir():
    if p.is_dir() and p.name not in skip and (p/'__init__.py').exists():
        sources.add(p.name)
for p in root.iterdir():
    if p.is_file() and p.suffix=='.py' and p.name not in {'conftest.py','sitecustomize.py'}:
        sources.add(p.stem)
src=root/'src'
if src.is_dir():
    for p in src.iterdir():
        if p.is_dir() and (p/'__init__.py').exists():
            sources.add(p.name)
print(','.join(sorted(sources)))
PY
)"

COV_ARGS=()
if [[ -n "$COV_SOURCES" ]]; then
  echo "Coverage on source dirs: $COV_SOURCES"
  IFS=, read -r -a covlist <<< "$COV_SOURCES"
  for m in "${covlist[@]}"; do COV_ARGS+=(--cov="$m"); done
  COV_ARGS+=(--cov-branch)
  # inline omit to avoid .coveragerc in target repo
  COV_ARGS+=(--cov-omit '*/tests/*' '*/tests/generated/*' '*/.venv/*' '*/venv/*' '*/env/*' '*/site-packages/*' '**/__init__.py')
else
  echo "Coverage sources not detected. Running without --cov."
fi

# Pick plugins explicitly
PLUGINS=(-p pytest_cov -p pytest_jsonreport "${ENABLE_DJANGO[@]}")

# Optional plugin flags detection
HTML_ARGS=""
TIMEOUT_ARGS=""
if python - <<'PY' 2>/dev/null | grep -q HAVE_HTML; then
    HTML_ARGS="--html=${REPORT_DIR}/test-report.html --self-contained-html"
fi <<'PY'
import importlib.util
print("HAVE_HTML" if importlib.util.find_spec("pytest_html") else "NO")
PY
if python - <<'PY' 2>/dev/null | grep -q HAVE_TIMEOUT; then
    TIMEOUT_ARGS="--timeout=300"
fi <<'PY'
import importlib.util
print("HAVE_TIMEOUT" if importlib.util.find_spec("pytest_timeout") else "NO")
PY

set +e
pytest "${TEST_DIRS[@]}" \
  "${PLUGINS[@]}" \
  -rA --tb=short \
  $TIMEOUT_ARGS \
  --json-report --json-report-file "${REPORT_DIR}/test-results.json" \
  $HTML_ARGS \
  "${COV_ARGS[@]}" \
  --junitxml "${REPORT_DIR}/junit.xml"
CODE=$?
set -e

# Produce coverage reports if coverage ran
if [[ ${#COV_ARGS[@]} -gt 0 ]]; then
  coverage xml -o "${REPORT_DIR}/coverage.xml" || true
  coverage json -o "${REPORT_DIR}/coverage.json" || true
  coverage html -d "${REPORT_DIR}/htmlcov" || true
  coverage report || true
fi

echo "pytest_exit_code=$CODE"
exit "$CODE"
