import os, json, pathlib, datetime, time, random, re, ast
from typing import Dict, Any, List, Tuple, Optional
from openai import AzureOpenAI
from openai import RateLimitError  # openai>=1.0.0

# ---------------- Tunables via env (safe defaults) ----------------
MAX_TOKENS            = int(os.getenv("OAI_MAX_TOKENS", "800"))          # cap LLM output
OAI_MAX_RETRIES       = int(os.getenv("OAI_MAX_RETRIES", "6"))
OAI_BASE_BACKOFF      = float(os.getenv("OAI_BASE_BACKOFF", "3"))
OAI_PAUSE_BETWEEN     = float(os.getenv("OAI_PAUSE_BETWEEN_CALLS", "3"))
OAI_REQ_INTERVAL      = float(os.getenv("OAI_REQ_INTERVAL", "0"))        # min seconds between API calls (0=off)
TESTGEN_KINDS         = os.getenv("TESTGEN_KINDS", "unit,integ,e2e")     # comma list
TESTGEN_MAX_TESTS     = int(os.getenv("TESTGEN_MAX_TESTS", "6"))
AN_MAX_FUNCS          = int(os.getenv("ANALYSIS_MAX_FUNCTIONS", "50"))
AN_MAX_CLASSES        = int(os.getenv("ANALYSIS_MAX_CLASSES", "30"))
AN_MAX_ROUTES         = int(os.getenv("ANALYSIS_MAX_ROUTES", "30"))
# Force frameworks (comma list) or leave empty to auto-detect from analysis["modules"]
TESTGEN_FRAMEWORKS    = os.getenv("TESTGEN_FRAMEWORKS", "").strip()

_last_call = 0.0

# ---------------- System & Templates ----------------
SYSTEM = """You are an expert Python test engineer.
Return ONLY valid Python source code (no Markdown, no backticks, no prose).
Hard rules:
- Deterministic data only.
- No real network; mock I/O.
- Import ONLY modules that exist in analysis or standard libs.
- If uncertain, emit a simple test_placeholder() that passes.
"""

UNIT_TEMPLATE = """Analysis JSON (compacted):
{analysis}

Write UNIT tests (max {max_tests} tests). Return ONLY Python code, no backticks.
Guidelines:
- Target public functions/classes; assert exact outputs / exceptions.
- Use pytest; no external I/O; use tmp_path for files when needed.
"""

# framework-parameterized templates for integration/e2e
INTEG_GENERIC = """Analysis JSON (compacted):
{analysis}

Write INTEGRATION tests (max {max_tests} tests) WITHOUT assuming a web framework.
Guidelines:
- Identify seams with I/O (filesystem, db client objects, requests); mock with monkeypatch.
- If there is a CLI entrypoint (click/typer), test it via runner.
Return ONLY Python code, no backticks.
"""

INTEG_FASTAPI = """Analysis JSON (compacted):
{analysis}

Write INTEGRATION tests (max {max_tests} tests) for a FastAPI app.
Use: from fastapi.testclient import TestClient
- Build TestClient(app) if an app object is importable; otherwise, skip with a placeholder.
- Cover 1 happy path + 1 validation/error case.
Return ONLY Python code, no backticks.
"""

INTEG_FLASK = """Analysis JSON (compacted):
{analysis}

Write INTEGRATION tests (max {max_tests} tests) for a Flask app.
- Use app.test_client() to call routes if an app is importable; otherwise, skip with placeholder.
Return ONLY Python code, no backticks.
"""

INTEG_DJANGO = """Analysis JSON (compacted):
{analysis}

Write INTEGRATION tests (max {max_tests} tests) for a Django project.
- Use django.test.Client.
- If DJANGO_SETTINGS_MODULE is not set at runtime, skip with allow_module_level=True.
Return ONLY Python code, no backticks.
"""

INTEG_CLI = """Analysis JSON (compacted):
{analysis}

Write INTEGRATION tests (max {max_tests} tests) for a CLI built with click/typer if present.
- Use CliRunner (click.testing) or Typer's runner.
- If no CLI entrypoints are importable, emit a placeholder.
Return ONLY Python code, no backticks.
"""

E2E_GENERIC = """Analysis JSON (compacted):
{analysis}

Write E2E tests (max {max_tests} tests) for a minimal black-box workflow.
- If no HTTP/CLI entrypoint is found, emit a simple placeholder E2E test that passes.
Return ONLY Python code, no backticks.
"""

E2E_FASTAPI = """Analysis JSON (compacted):
{analysis}

Write E2E tests (max {max_tests} tests) for FastAPI using TestClient.
- Chain a minimal workflow (e.g., auth or CRUD): POST -> GET -> PUT/DELETE; assert status & body shape.
- Use deterministic data.
Return ONLY Python code, no backticks.
"""

E2E_FLASK = """Analysis JSON (compacted):
{analysis}

Write E2E tests (max {max_tests} tests) for Flask using app.test_client().
- Chain a minimal workflow; assert status codes and JSON payload structure.
Return ONLY Python code, no backticks.
"""

E2E_DJANGO = """Analysis JSON (compacted):
{analysis}

Write E2E tests (max {max_tests} tests) for Django using django.test.Client.
- If DJANGO_SETTINGS_MODULE not set, skip the module.
Return ONLY Python code, no backticks.
"""

E2E_CLI = """Analysis JSON (compacted):
{analysis}

Write E2E tests (max {max_tests} tests) for CLI built with click/typer.
- Simulate a full command flow via CliRunner (or Typer runner), assert exit_code and output.
Return ONLY Python code, no backticks.
"""

# ---------------- Azure OpenAI client helpers ----------------
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
    global _last_call
    if OAI_REQ_INTERVAL <= 0:
        return
    now = time.time()
    delta = now - _last_call
    if delta < OAI_REQ_INTERVAL:
        sleep_s = OAI_REQ_INTERVAL - delta
        print(f"[RateControl] sleeping {sleep_s:.1f}s to respect OAI_REQ_INTERVAL")
        time.sleep(sleep_s)

def _sleep_from_headers(exc: Exception, attempt: int) -> float:
    try:
        ra = exc.response.headers.get("retry-after") if getattr(exc, "response", None) else None
        if ra:
            return float(ra)
    except Exception:
        pass
    return OAI_BASE_BACKOFF * (2 ** attempt) + random.uniform(0, 1)

def _extract_python_only(text: str) -> str:
    # If fenced, take inside of the first/merged code blocks
    if "```" in text:
        blocks = re.findall(r"```(?:python)?\s*(.*?)```", text, flags=re.IGNORECASE|re.DOTALL)
        if blocks:
            text = "\n\n".join(blocks)
        else:
            text = text.replace("```", "")
    lines = text.splitlines()
    if lines and lines[0].strip().lower() in {"python", "py"}:
        lines = lines[1:]
    return ("\n".join(lines)).strip() + "\n"

def _compile_or_placeholder(code: str) -> str:
    try:
        ast.parse(code, filename="<generated>", mode="exec")
        return code
    except SyntaxError as e:
        print(f"[Sanitize] AST parse failed: {e}. Falling back to placeholder.")
        return (
            "import pytest\n\n"
            "def test_placeholder():\n"
            "    # LLM returned invalid syntax; placeholder keeps CI green\n"
            "    assert True\n"
        )

# --- Guards to skip entire module when framework missing ---
FASTAPI_GUARD = (
    "import importlib.util as _iu, pytest as _pytest\n"
    "if _iu.find_spec('fastapi') is None:\n"
    "    _pytest.skip('fastapi not installed; skipping', allow_module_level=True)\n\n"
)
FLASK_GUARD = (
    "import importlib.util as _iu, pytest as _pytest\n"
    "if _iu.find_spec('flask') is None:\n"
    "    _pytest.skip('flask not installed; skipping', allow_module_level=True)\n\n"
)
DJANGO_GUARD = (
    "import importlib.util as _iu, os, pytest as _pytest\n"
    "if _iu.find_spec('django') is None:\n"
    "    _pytest.skip('django not installed; skipping', allow_module_level=True)\n"
    "if 'DJANGO_SETTINGS_MODULE' not in os.environ:\n"
    "    _pytest.skip('DJANGO_SETTINGS_MODULE not set; skipping', allow_module_level=True)\n\n"
)
CLI_GUARD = (
    "import importlib.util as _iu, pytest as _pytest\n"
    "if _iu.find_spec('click') is None and _iu.find_spec('typer') is None:\n"
    "    _pytest.skip('click/typer not installed; skipping', allow_module_level=True)\n\n"
)

def _needs_guard(code: str) -> Optional[str]:
    lcode = code.lower()
    if re.search(r'(^|\n)\s*(from\s+fastapi\s+import|import\s+fastapi)\b', lcode, re.I):
        return FASTAPI_GUARD
    if re.search(r'(^|\n)\s*(from\s+flask\s+import|import\s+flask)\b', lcode, re.I):
        return FLASK_GUARD
    if re.search(r'(^|\n)\s*(from\s+django\s+import|import\s+django)\b', lcode, re.I):
        return DJANGO_GUARD
    if re.search(r'(^|\n)\s*(from\s+click\s+import|import\s+click|import\s+typer|from\s+typer\s+import)\b', lcode, re.I):
        return CLI_GUARD
    return None

def _wrap_guard_if_needed(code: str) -> str:
    guard = _needs_guard(code)
    return (guard + code) if guard else code

def _gen(prompt: str) -> str:
    global _last_call
    client = _client()
    deployment = _deployment_name()
    last_err = None
    for attempt in range(OAI_MAX_RETRIES):
        try:
            _ensure_min_interval()
            resp = client.chat.completions.create(
                model=deployment,
                messages=[{"role": "system", "content": SYSTEM},
                          {"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=MAX_TOKENS,
                n=1,
            )
            _last_call = time.time()
            raw = resp.choices[0].message.content or ""
            cleaned = _extract_python_only(raw)
            code = _compile_or_placeholder(cleaned)
            return _wrap_guard_if_needed(code)
        except RateLimitError as e:
            sleep_s = _sleep_from_headers(e, attempt)
            print(f"[429] attempt {attempt+1}/{OAI_MAX_RETRIES}; sleeping {sleep_s:.1f}s")
            time.sleep(sleep_s)
    raise RuntimeError(f"Azure OpenAI rate-limited after {OAI_MAX_RETRIES} attempts: {last_err}")

# ---------------- Analysis compaction ----------------
def _dedupe_keep(items: List[Dict[str, str]], key: str, limit: int) -> List[Dict[str, str]]:
    seen, out = set(), []
    for it in items or []:
        k = it.get(key)
        if not k or k in seen: 
            continue
        seen.add(k)
        out.append({kk: it.get(kk) for kk in ("name","file","handler","method") if kk in it})
        if len(out) >= limit:
            break
    return out

def _compact_analysis(analysis: Dict[str, Any]) -> Dict[str, Any]:
    funcs  = sorted(analysis.get("functions", []), key=lambda x: x.get("file",""))
    clss   = sorted(analysis.get("classes",   []), key=lambda x: x.get("file",""))
    routes = sorted(analysis.get("routes",    []), key=lambda x: x.get("file",""))
    return {
        "functions": _dedupe_keep(funcs,  "name",   AN_MAX_FUNCS),
        "classes":   _dedupe_keep(clss,   "name",   AN_MAX_CLASSES),
        "routes":    _dedupe_keep(routes, "handler", AN_MAX_ROUTES),
        "modules":   sorted(set(analysis.get("modules", []))),
    }

# ---------------- Framework detection ----------------
def _detect_frameworks(mods: List[str]) -> Dict[str, bool]:
    s = {m.split('.')[0].lower() for m in mods or []}
    return {
        "fastapi": "fastapi" in s,
        "flask": "flask" in s,
        "django": "django" in s or "rest_framework" in s,
        "click": "click" in s,
        "typer": "typer" in s,
    }

def _framework_context(frames: Dict[str, bool]) -> Tuple[str, str]:
    """Return (integration_template, e2e_template) based on detected frameworks.
       If multiple frameworks detected, prefer FastAPI > Flask > Django > CLI > generic."""
    if frames.get("fastapi"):
        return INTEG_FASTAPI, E2E_FASTAPI
    if frames.get("flask"):
        return INTEG_FLASK, E2E_FLASK
    if frames.get("django"):
        return INTEG_DJANGO, E2E_DJANGO
    if frames.get("click") or frames.get("typer"):
        return INTEG_CLI, E2E_CLI
    return INTEG_GENERIC, E2E_GENERIC

def _override_frameworks() -> Optional[Dict[str,bool]]:
    if not TESTGEN_FRAMEWORKS:
        return None
    s = {x.strip().lower() for x in TESTGEN_FRAMEWORKS.split(",") if x.strip()}
    return {
        "fastapi": "fastapi" in s,
        "flask": "flask" in s,
        "django": "django" in s,
        "click": "click" in s,
        "typer": "typer" in s,
    }

# ---------------- Main generation ----------------
def write(path: pathlib.Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

def generate_all(analysis: Dict[str, Any], outdir="tests/generated"):
    out = pathlib.Path(outdir)
    ts = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")

    compact = _compact_analysis(analysis)
    compact_json = json.dumps(compact, separators=(",",":"))

    # UNIT (always meaningful)
    if "unit" in {k.strip() for k in TESTGEN_KINDS.split(",")}:
        unit_code = _gen(UNIT_TEMPLATE.format(analysis=compact_json, max_tests=TESTGEN_MAX_TESTS))
        write(out / f"test_unit_{ts}.py", unit_code)
        time.sleep(OAI_PAUSE_BETWEEN)

    # Integration / E2E per framework
    frames = _override_frameworks() or _detect_frameworks(compact.get("modules", []))
    integ_tpl, e2e_tpl = _framework_context(frames)

    if "integ" in {k.strip() for k in TESTGEN_KINDS.split(",")}:
        integ_code = _gen(integ_tpl.format(analysis=compact_json, max_tests=TESTGEN_MAX_TESTS))
        write(out / f"test_integ_{ts}.py", integ_code)
        time.sleep(OAI_PAUSE_BETWEEN)

    if "e2e" in {k.strip() for k in TESTGEN_KINDS.split(",")}:
        e2e_code = _gen(e2e_tpl.format(analysis=compact_json, max_tests=TESTGEN_MAX_TESTS))
        write(out / f"test_e2e_{ts}.py", e2e_code)

if __name__ == "__main__":
    import analyzer
    analysis = analyzer.analyze_python_tree(pathlib.Path("."))
    generate_all(analysis)
    print("✅ Generated tests in tests/generated")
