from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from xml.etree import ElementTree as ET
import subprocess
import os

app = FastAPI(title="AI TestGen Dashboard")

# Serve static frontend (index.html) at /dashboard
if os.path.isdir("dashboard_frontend"):
    app.mount("/dashboard", StaticFiles(directory="dashboard_frontend", html=True), name="dashboard")

def _parse_coverage():
    if not os.path.exists("coverage.xml"):
        return {"coverage": 0.0}
    try:
        tree = ET.parse("coverage.xml")
        root = tree.getroot()
        line_rate = float(root.get("line-rate", "0")) * 100
        return {"coverage": round(line_rate, 2)}
    except Exception:
        return {"coverage": 0.0}

def _ensure_junit():
    # Generate junit.xml only if missing to avoid heavy runs on every refresh
    if not os.path.exists("junit.xml"):
        try:
            subprocess.run(["pytest", "-q", "--junitxml=junit.xml"], check=False)
        except Exception:
            pass

def _parse_junit():
    if not os.path.exists("junit.xml"):
        return {"tests": 0, "failures": 0, "errors": 0}
    try:
        root = ET.parse("junit.xml").getroot()
        suites = list(root.iter("testsuite"))
        tests = sum(int(s.get("tests", 0)) for s in suites)
        failures = sum(int(s.get("failures", 0)) for s in suites)
        errors = sum(int(s.get("errors", 0)) for s in suites)
        return {"tests": tests, "failures": failures, "errors": errors}
    except Exception:
        return {"tests": 0, "failures": 0, "errors": 0}

@app.get("/api/metrics")
def metrics(refresh: int = 0):
    if refresh or not os.path.exists("junit.xml"):
        _ensure_junit()
    cov = _parse_coverage()
    junit = _parse_junit()
    return JSONResponse({
        **cov,
        **junit
    })
