# AI TestGen

## Dashboard (FastAPI + Static React)

Run locally:

```bash
pip install -r requirements.txt
pytest -q --cov=. --cov-report=xml:coverage.xml  # generate coverage.xml once
uvicorn dashboard_api:app --reload --port 8000
```

Open http://127.0.0.1:8000/dashboard to view the metrics cards.
Use the **Refresh** button to force-generate `junit.xml` if missing.
