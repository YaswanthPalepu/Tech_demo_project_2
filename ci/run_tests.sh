#!/usr/bin/env bash
set -Eeuo pipefail

REPO_DIR="${1:-${GITHUB_WORKSPACE:-}/target_repo}"
if [ -z "${REPO_DIR}" ] || [ ! -d "$REPO_DIR" ]; then
  echo "Repo dir missing: '$REPO_DIR'"
  exit 1
fi

cd "$REPO_DIR"

# Make the repo (and target, if present) importable
export TARGET_ROOT="${TARGET_ROOT:-$REPO_DIR/target}"
if [ ! -d "$TARGET_ROOT" ]; then
  # fall back to repo root if there's no ./target
  TARGET_ROOT="$REPO_DIR"
fi

# Safely build PYTHONPATH even under 'set -u'
export PYTHONPATH="${PYTHONPATH-}"
case ":$PYTHONPATH:" in
  *":$REPO_DIR:"*) ;;
  *) PYTHONPATH="$REPO_DIR${PYTHONPATH:+:$PYTHONPATH}";;
esac
if [ -d "$TARGET_ROOT" ]; then
  case ":$PYTHONPATH:" in
    *":$TARGET_ROOT:"*) ;;
    *) PYTHONPATH="$TARGET_ROOT${PYTHONPATH:+:$PYTHONPATH}";;
  esac
fi
export PYTHONPATH

# Keep plugin auto-discovery predictable (generator handles its own conftest)
export PYTEST_DISABLE_PLUGIN_AUTOLOAD="${PYTEST_DISABLE_PLUGIN_AUTOLOAD:-0}"

mkdir -p reports/tests

pytest_args=(
  -q
  --maxfail=1
  --disable-warnings
  --json-report
  --json-report-file=reports/tests/test-results.json
  --cov=.
  --cov-report=json:reports/tests/coverage.json
)

# Pick test paths that exist
paths=()
[ -d tests ] && paths+=(tests)
[ -d tests/generated ] && paths+=(tests/generated)

if [ ${#paths[@]} -eq 0 ]; then
  echo "No tests directory found (tests/ or tests/generated/)."
  # Exit 0 so the workflow can report no tests collected later.
  exit 0
fi

echo "Running pytest on: ${paths[*]}"
pytest "${pytest_args[@]}" "${paths[@]}" || true
