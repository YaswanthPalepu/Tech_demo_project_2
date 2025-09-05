# AI-TestGen (Any Python Framework) — Unit / Integration / E2E

Generates **developer-style** tests for Python projects across common frameworks:
- Web: **FastAPI**, **Flask**, **Django**
- CLI: **Click**, **Typer**, **argparse**
- Pure libraries: solid unit tests from analysis (AI-backed with fallback)

## Quick start
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Optional (AI-backed generation):
export AZURE_OPENAI_API_KEY=...
export AZURE_OPENAI_ENDPOINT="https://<resource>.openai.azure.com/"
export AZURE_OPENAI_API_VERSION="2024-06-01"
export AZURE_OPENAI_DEPLOYMENT="gpt-4o-mini"

# Run against a target repo
python src/orchestrator.py --target /path/to/repo --use-ai true --min-coverage 60 --max-files 80
```
Artifacts → `artifacts/`:
- `coverage/coverage.xml`
- `test-results/junit.xml`
- `report.json`

CI/CD: use the two workflows in `.github/workflows/` (Generate first, then Run).
