#!/usr/bin/env bash
set -Eeuo pipefail

REPO_DIR="${1:-${GITHUB_WORKSPACE:-}/target_repo}"
if [ -z "${REPO_DIR}" ] || [ ! -d "$REPO_DIR" ]; then
  echo "Repo dir missing: '$REPO_DIR'"
  exit 1
fi

cd "$REPO_DIR"

# Make repo/target importable
export TARGET_ROOT="${TARGET_ROOT:-$REPO_DIR/target}"
[ -d "$TARGET_ROOT" ] || TARGET_ROOT="$REPO_DIR"

export PYTHONPATH="${PYTHONPATH-}"
case ":$PYTHONPATH:" in *":$REPO_DIR:"*) ;; *) PYTHONPATH="$REPO_DIR${PYTHONPATH:+:$PYTHONPATH}";; esac
case ":$PYTHONPATH:" in *":$TARGET_ROOT:"*) ;; *) PYTHONPATH="$TARGET_ROOT${PYTHONPATH:+:$PYTHONPATH}";; esac
export PYTHONPATH

# Allow plugin autoload so optional plugins can register their CLI flags
export PYTEST_DISABLE_PLUGIN_AUTOLOAD="${PYTEST_DISABLE_PLUGIN_AUTOLOAD:-0}"

# Helper: try to ensure a package exists (best-effort)
ensure_pkg() {
  local pkg="$1"
  python - <<PY || true
import importlib, sys, subprocess, os
pkg = "$pkg"
try:
    importlib.import_module(pkg.replace("-","_"))
except Exception:
    args=[sys.executable,"-m","pip","install","-q"]
    if os.environ.get("PIP_CONSTRAINT"): args += ["-c", os.environ["PIP_CONSTRAINT"]]
    args += [pkg]
    try: subprocess.check_call(args)
    except Exception: pass
PY
}

# Try to make the two plugins available; if install not allowed, we’ll fall back gracefully
ensure_pkg "pytest-json-report"
ensure_pkg "pytest-cov"

# Feature-detect flags
has_opt() { pytest -q -h 2>&1 | grep -q -- "$1" ; }

json_ok=0
cov_ok=0
has_opt "--json-report" && json_ok=1 || json_ok=0
has_opt "--cov=" && cov_ok=1 || cov_ok=0

mkdir -p reports/tests

pytest_args=(-q --maxfail=1 --disable-warnings)

if [ "$json_ok" -eq 1 ]; then
  pytest_args+=( --json-report --json-report-file=reports/tests/test-results.json )
fi
if [ "$cov_ok" -eq 1 ]; then
  pytest_args+=( --cov=. --cov-report=json:reports/tests/coverage.json )
fi

# Pick paths
paths=()
[ -d tests ] && paths+=(tests)
[ -d tests/generated ] && paths+=(tests/generated)

if [ ${#paths[@]} -eq 0 ]; then
  echo "No tests directory found (tests/ or tests/generated/)."
  # still create empty report files so downstream step doesn't crash
  printf '{"summary":{"total":0,"passed":0,"failed":0,"error":0,"skipped":0}}' > reports/tests/test-results.json
  printf '{"totals":{"percent_covered":0}}' > reports/tests/coverage.json
  exit 0
fi

echo "Running pytest on: ${paths[*]}"
pytest "${pytest_args[@]}" "${paths[@]}" || true

# Ensure report stubs exist if plugins weren’t available
[ -f reports/tests/test-results.json ] || printf '{"summary":{"total":0,"passed":0,"failed":0,"error":0,"skipped":0}}' > reports/tests/test-results.json
[ -f reports/tests/coverage.json ] || printf '{"totals":{"percent_covered":0}}' > reports/tests/coverage.json
