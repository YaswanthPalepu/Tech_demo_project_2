#!/usr/bin/env bash
set -euo pipefail

# USAGE: ci/run_tests.sh /absolute/path/to/target_repo
TARGET_REPO="${1:?pass path to target repo}"
cd "$TARGET_REPO"

REPORT_DIR="$(pwd)/reports/tests"
mkdir -p "$REPORT_DIR"

export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
export PYTHONPATH="${TARGET_REPO}:${PYTHONPATH-}"
[[ -d src ]] && export PYTHONPATH="${TARGET_REPO}/src:${PYTHONPATH-}"

# Decide test targets
TEST_DIRS=()
[[ -d tests ]] && TEST_DIRS+=("tests")
[[ -d tests/generated ]] && TEST_DIRS+=("tests/generated")
if [[ ${#TEST_DIRS[@]} -eq 0 ]]; then
  echo "No tests/ dirs found; using repo root for discovery"
  TEST_DIRS=(".")
fi

# Enable pytest-django only if settings present
ENABLE_DJANGO=()
if [[ -n "${DJANGO_SETTINGS_MODULE-}" ]]; then
  ENABLE_DJANGO+=(-p django)
elif [[ -f manage.py ]] || compgen -G "*settings.py" >/dev/null; then
  ENABLE_DJANGO+=(-p django)
fi

# Compute coverage sources
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
  COV_ARGS+=(--cov-omit '*/tests/*' '*/tests/generated/*' '*/.venv/*' '*/venv/*' '*/env/*' '*/site-packages/*' '**/__init__.py')
else
  echo "Coverage sources not detected. Running without --cov."
fi

# Optional plugins
HTML_ARGS=""
TIMEOUT_ARGS=""
if python -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('pytest_html') else 1)"; then
  HTML_ARGS="--html=${REPORT_DIR}/test-report.html --self-contained-html"
fi
if python -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('pytest_timeout') else 1)"; then
  TIMEOUT_ARGS="--timeout=300"
fi

PLUGINS=(-p pytest_cov -p pytest_jsonreport "${ENABLE_DJANGO[@]}")

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

# Ensure JSON exists even if pytest crashed early
[[ -f "${REPORT_DIR}/test-results.json" ]] || echo '{"summary":{"total":0,"passed":0,"failed":0,"error":0,"skipped":0}}' > "${REPORT_DIR}/test-results.json"

# Coverage outputs if we collected coverage
if [[ ${#COV_ARGS[@]} -gt 0 ]]; then
  coverage xml -o "${REPORT_DIR}/coverage.xml" || true
  coverage json -o "${REPORT_DIR}/coverage.json" || true
  coverage html -d "${REPORT_DIR}/htmlcov" || true
  coverage report || true
fi

echo "pytest_exit_code=$CODE"
exit "$CODE"
