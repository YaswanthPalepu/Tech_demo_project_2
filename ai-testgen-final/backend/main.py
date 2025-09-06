from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from pathlib import Path
import json

app = FastAPI(title="AI-TestGen Backend")

ART = Path("artifacts")
DASH = Path("dashboard-frontend")

@app.get("/")
def root():
    return {"ok": True, "message": "AI-TestGen Backend"}

@app.get("/metrics")
def metrics():
    p = ART / "report.json"
    if not p.exists():
        raise HTTPException(status_code=404, detail="report.json not found. Run the orchestrator first.")
    data = json.loads(p.read_text(encoding="utf-8"))
    return JSONResponse(data)

@app.get("/coverage.xml")
def coverage_xml():
    p = ART / "coverage" / "coverage.xml"
    if not p.exists():
        raise HTTPException(status_code=404, detail="coverage.xml not found (Python projects only).")
    return FileResponse(str(p), media_type="application/xml")

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    index = DASH / "index.html"
    if not index.exists():
        return HTMLResponse("<h1>Dashboard not found</h1><p>Run the orchestrator to create artifacts first.</p>")
    return HTMLResponse(index.read_text(encoding="utf-8"))
