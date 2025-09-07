import os, json, pathlib, datetime, time, random
from typing import Dict, Any, List
from openai import AzureOpenAI
from openai import RateLimitError  # openai>=1.0.0

# ---- Tunables via env (safe defaults) ----
MAX_TOKENS            = int(os.getenv("OAI_MAX_TOKENS", "800"))          # limit model output
MAX_FUNCS             = int(os.getenv("ANALYSIS_MAX_FUNCTIONS", "40"))   # compact analysis
MAX_CLASSES           = int(os.getenv("ANALYSIS_MAX_CLASSES", "25"))
MAX_ROUTES            = int(os.getenv("ANALYSIS_MAX_ROUTES", "25"))
TESTGEN_KINDS         = os.getenv("TESTGEN_KINDS", "unit,integ,e2e")      # e.g. "unit" or "unit,integ"
TESTGEN_MAX_TESTS     = int(os.getenv("TESTGEN_MAX_TESTS", "6"))          # cap tests per kind in prompt
OAI_MAX_RETRIES       = int(os.getenv("OAI_MAX_RETRIES", "6"))
OAI_BASE_BACKOFF      = float(os.getenv("OAI_BASE_BACKOFF", "3"))         # seconds
OAI_PAUSE_BETWEEN     = float(os.getenv("OAI_PAUSE_BETWEEN_CALLS", "3"))  # seconds
OAI_REQ_INTERVAL      = float(os.getenv("OAI_REQ_INTERVAL", "0"))         # seconds, force min interval between calls (0=off)

_last_call = 0.0

SYSTEM = """You are an expert Python test engineer.
Generate runnable pytest tests.
Rules:
- Output ONLY Python code.
- Use deterministic data.
- Prefer pytest + requests/httpx + FastAPI TestClient when app detected.
- Do not call external networks; mock I/O.
- Only import modules that exist in analysis.
- If unsure, emit a test_placeholder that always passes.
"""

UNIT_USER_TEMPLATE = """Analysis JSON (compacted):
{analysis}

Write focused UNIT tests for discovered functions/classes (max {max_tests} tests total).
- Use simple deterministic inputs and assert exact outputs or exceptions.
- If classes: test __init__ and one public method per class.
- No external network; mock I/O.
"""

INTEG_USER_TEMPLATE = """Analysis JSON (compacted):
{analysis}

Write INTEGRATION tests (max {max_tests} tests total):
- If FastAPI routes exist, use TestClient.
- Do 1 happy path + 1 error/validation path for at least one route group.
- Mock outbound calls with monkeypatch.
"""

E2E_USER_TEMPLATE = """Analysis JSON (compacted):
{analysis}

Write E2E tests (max {max_tests} tests total) covering a minimal full workflow.
- Use TestClient; chain requests; assert status & payload shape.
- Keep data deterministic and minimal.
"""

def _required_env(name: str) -> str:
    v = os.getenv(name)
    if not v:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return v

def _client() -> AzureOpenAI:
    return AzureOpenAI(
        api_key=_required_env("AZURE_OPENAI_KEY"),
        azure_endpoint=_required_env("AZURE_OPENAI_ENDPOINT"),
        api_version=_required_env("AZURE_OPENAI_API_VERSION"),
    )

def _deployment_name() -> str:
    return _required_env("AZURE_OPENAI_DEPLOYMENT")

def _ensure_min_interval():
    """Optionally enforce a minimum interval between API calls (helps with per-minute limits)."""
    global _last_call
    if OAI_REQ_INTERVAL <= 0:
        return
    now = time.time()
    delta = now - _last_call
    if delta < OAI_REQ_INTERVAL:
        sleep_s = OAI_REQ_INTERVAL - delta
        print(f"[RateControl] sleeping {sleep_s:.1f}s to respect OAI_REQ_INTERVAL")
        time.sleep(sleep_s)

def _sleep_from_headers(exc, attempt):
    # Respect server Retry-After if available
    retry_after = None
    try:
        retry_after = exc.response.headers.get("retry-after") if getattr(exc, "response", None) else None
    except Exception:
        pass
    if retry_after:
        try:
            return float(retry_after)
        except Exception:
            pass
    # fallback: exponential backoff + jitter
    return OAI_BASE_BACKOFF * (2 ** attempt) + random.uniform(0, 1)

def _gen(prompt: str) -> str:
    global _last_call
    client = _client()
    deployment = _deployment_name()

    for attempt in range(OAI_MAX_RETRIES):
        try:
            _ensure_min_interval()
            resp = client.chat.completions.create(
                model=deployment,  # Azure: deployment name, not a base model string
                messages=[{"role": "system", "content": SYSTEM},
                          {"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=MAX_TOKENS,  # cap output to reduce tokens
                n=1,
            )
            _last_call = time.time()
            return resp.choices[0].message.content
        except RateLimitError as e:
            sleep_s = _sleep_from_headers(e, attempt)
            print(f"[429] attempt {attempt+1}/{OAI_MAX_RETRIES}; sleeping {sleep_s:.1f}s")
            time.sleep(sleep_s)
    raise RuntimeError(f"Azure OpenAI rate-limited after {OAI_MAX_RETRIES} attempts")

def write(path: pathlib.Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

def _dedupe_keep(items: List[Dict[str, str]], key: str, limit: int) -> List[Dict[str, str]]:
    seen, out = set(), []
    for it in items:
        k = it.get(key)
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(it)
        if len(out) >= limit:
            break
    return out

def _compact_analysis(analysis: Dict[str, Any]) -> Dict[str, Any]:
    """Shrink analysis to stay within TPM: keep only top-N items and strip heavy fields."""
    funcs  = analysis.get("functions", [])
    clss   = analysis.get("classes",   [])
    routes = analysis.get("routes",    [])

    # Sort by file path for determinism; then keep first N unique by name
    funcs  = sorted(funcs,  key=lambda x: x.get("file","")) if isinstance(funcs, list) else []
    clss   = sorted(clss,   key=lambda x: x.get("file","")) if isinstance(clss, list) else []
    routes = sorted(routes, key=lambda x: x.get("file","")) if isinstance(routes, list) else []

    funcs  = _dedupe_keep(funcs,  "name",   MAX_FUNCS)
    clss   = _dedupe_keep(clss,   "name",   MAX_CLASSES)
    routes = _dedupe_keep(routes, "handler", MAX_ROUTES)

    # Keep only minimal keys
    def strip(items, allowed):
        return [{k:v for k,v in it.items() if k in allowed} for it in items]

    return {
        "functions": strip(funcs,  {"name","file"}),
        "classes":   strip(clss,   {"name","file"}),
        "routes":    strip(routes, {"handler","file","method"}),
    }

def generate_all(analysis: Dict[str, Any], outdir="tests/generated"):
    out = pathlib.Path(outdir)
    ts = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")

    compact = _compact_analysis(analysis)
    compact_json = json.dumps(compact, separators=(",",":"))  # smaller payload

    kinds = [k.strip() for k in TESTGEN_KINDS.split(",") if k.strip()]
    if "unit" in kinds:
        unit = _gen(UNIT_USER_TEMPLATE.format(analysis=compact_json, max_tests=TESTGEN_MAX_TESTS))
        write(out / f"test_unit_{ts}.py", unit)
        time.sleep(OAI_PAUSE_BETWEEN)

    if "integ" in kinds:
        integ = _gen(INTEG_USER_TEMPLATE.format(analysis=compact_json, max_tests=TESTGEN_MAX_TESTS))
        write(out / f"test_integ_{ts}.py", integ)
        time.sleep(OAI_PAUSE_BETWEEN)

    if "e2e" in kinds:
        e2e = _gen(E2E_USER_TEMPLATE.format(analysis=compact_json, max_tests=TESTGEN_MAX_TESTS))
        write(out / f"test_e2e_{ts}.py", e2e)

if __name__ == "__main__":
    import analyzer
    analysis = analyzer.analyze_python_tree(pathlib.Path("."))
    generate_all(analysis)
    print("✅ Generated tests in tests/generated")
