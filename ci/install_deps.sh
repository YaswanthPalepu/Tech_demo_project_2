#!/usr/bin/env bash
set -euo pipefail

python -m pip install --upgrade "pip<25" wheel setuptools
pip install -c "$PIP_CONSTRAINT" \
  "openai>=1.51.0" pytest pytest-cov httpx requests \
  "fastapi>=0.110" "starlette>=0.37" "pydantic>=2" \
  "annotated-types>=0.6" "uvicorn>=0.23" "typing-extensions>=4.8" \
  psycopg2-binary || true

sanitize_and_install() {
  local req_file="$1"
  [ -f "$req_file" ] || return 0
  echo "🔧 Sanitizing $req_file"

  sed -E 's/^psycopg2([^a-zA-Z0-9]|$)/psycopg2-binary\1/i' "$req_file" \
  | grep -viE '^[[:space:]]*(django|djangorestframework)\b' \
  > /tmp/req.candidate.txt

  awk '
    /^[[:space:]]*$/ {next}
    /^[[:space:]]*#/ {next}
    /^[[:space:]]*-/ {next}
    /^[[:space:]]*--/ {next}
    /^\-e[[:space:]]/ {next}
    /^git\+|^hg\+|^svn\+|^bzr\+/ {next}
    /^file:/ {next}
    {print}
  ' /tmp/req.candidate.txt > /tmp/req.clean.txt

  : > /tmp/req.final.txt
  while IFS= read -r line; do
    pkg="$(echo "$line" | sed 's/[[:space:]]*#.*$//' )"
    [ -z "$pkg" ] && continue
    if python - <<PY >/dev/null 2>&1
import sys, subprocess, shlex
pkg = sys.argv[1]
cmd = f"python -m pip index versions {shlex.quote(pkg)}"
sys.exit(subprocess.call(cmd, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))
PY
 "$pkg"; then
      echo "$pkg" >> /tmp/req.final.txt
    else
      echo "⏭️  Skipping unresolved package: $pkg"
    fi
  done < /tmp/req.clean.txt

  if [ -s /tmp/req.final.txt ]; then
    echo "📦 Installing $(wc -l < /tmp/req.final.txt) vetted deps from $req_file"
    pip install -c "$PIP_CONSTRAINT" -r /tmp/req.final.txt || echo "Some optional deps failed; continuing"
  else
    echo "ℹ️  No installable deps found in $req_file after sanitization"
  fi
}

sanitize_and_install "target/requirements.txt"
if compgen -G "target/requirements/*.txt" >/dev/null; then
  for f in target/requirements/*.txt; do sanitize_and_install "$f"; done
fi

if [ -f "target/pyproject.toml" ] && grep -q "\[tool.poetry\]" target/pyproject.toml; then
  pip install -c "$PIP_CONSTRAINT" poetry || true
  (cd target && poetry export -f requirements.txt --without-hashes -o /tmp/poetry.lock.req) || true
  [ -s /tmp/poetry.lock.req ] && sanitize_and_install "/tmp/poetry.lock.req"
fi

if [ -f "target/pyproject.toml" ] && grep -q "\[tool.pdm\]" target/pyproject.toml; then
  pip install -c "$PIP_CONSTRAINT" pdm || true
  (cd target && pdm export -o /tmp/pdm.lock.req --without-hashes --dev) || true
  [ -s /tmp/pdm.lock.req ] && sanitize_and_install "/tmp/pdm.lock.req"
fi
