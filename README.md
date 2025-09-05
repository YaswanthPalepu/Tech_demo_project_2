# AI-TestGen — AI-Powered Test Generation (Azure OpenAI)

Python-focused generator that creates **Unit / Integration / E2E** tests,
runs them in CI via GitHub Actions, checks coverage against quality gates,
and serves a tiny dashboard.

## Quick start
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Azure OpenAI (optional but recommended for richer unit tests)
export AZURE_OPENAI_API_KEY=...
export AZURE_OPENAI_ENDPOINT="https://<resource>.openai.azure.com/"
export AZURE_OPENAI_API_VERSION="2024-06-01"
export AZURE_OPENAI_DEPLOYMENT="gpt-4o-mini"

# Run locally against a Python repo
python src/orchestrator.py --target /path/to/repo --use-ai true --min-coverage 60 --max-files 50

# Start dashboard
uvicorn backend.main:app --reload --port 8000
# http://localhost:8000/dashboard
```
Artifacts -> `artifacts/`:
- `test-results/junit.xml`
- `coverage/coverage.xml`
- `report.json` (dashboard summary)

## CI/CD
- `.github/workflows/testgen-generate.yml` — idempotent generation (uses cache, won’t overwrite existing tests).
- `.github/workflows/testgen-run.yml` — executes tests, computes coverage, lists gaps & failing tests.

> **Python-only** test generation. Non-Python repos are detected and generation is skipped.
