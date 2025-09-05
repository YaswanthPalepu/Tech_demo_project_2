from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse, FileResponse
from pathlib import Path
import json

app = FastAPI(title="AI-TestGen AnyPy")

ART = Path("artifacts")
DASH = Path("dashboard-frontend")

@app.get("/")
def root():
    return {"ok": True}

@app.get("/metrics")
def metrics():
    p = ART / "report.json"
    if not p.exists(): raise HTTPException(404, "report.json not found")
    return JSONResponse(json.loads(p.read_text()))

@app.get("/coverage.xml")
def coverage():
    p = ART / "coverage" / "coverage.xml"
    if not p.exists(): raise HTTPException(404, "coverage.xml not found")
    return FileResponse(str(p), media_type="application/xml")

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    idx = DASH / "index.html"
    if not idx.exists():
        return HTMLResponse("<h1>No dashboard yet</h1>")
    return HTMLResponse(idx.read_text())
