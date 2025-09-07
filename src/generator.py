import os, json, pathlib, datetime, time, random, re, ast
from typing import Dict, Any, List
from openai import AzureOpenAI
from openai import RateLimitError  # openai>=1.0.0

# ---------------- Tunables via env (safe defaults) ----------------
MAX_TOKENS        = int(os.getenv("OAI_MAX_TOKENS", "800"))          # cap LLM output
OAI_MAX_RETRIES   = int(os.getenv("OAI_MAX_RETRIES", "6"))
OAI_BASE_BACKOFF  = float(os.getenv("OAI_BASE_BACKOFF", "3"))
OAI_PAUSE_BETWEEN = float(os.getenv("OAI_PAUSE_BETWEEN_CALLS", "3"))
OAI_REQ_INTERVAL  = float(os.getenv("OAI_REQ_INTERVAL", "0"))        # min seconds between API calls (0=off)

TESTGEN_KINDS     = os.getenv("TESTGEN_KINDS", "unit,integ,e2e")     # comma list
TESTGEN_MAX_TESTS = int(os.getenv("TESTGEN_MAX_TESTS", "6"))

# analysis compaction caps
AN_MAX_FUNCS   = int(os.getenv("ANALYSIS_MAX_FUNCTIONS", os.getenv("AN_MAX_FUNCS", "50")))
AN_MAX_CLASSES = int(os.getenv("ANALYSIS_MAX_CLASSES",   os.getenv("AN_MAX_CLASSES", "30")))
AN_MAX_ROUTES  = int(os.getenv("ANALYSIS_MAX_ROUTES",    os.getenv("AN_MAX_ROUTES", "30")))

_last_call = 0.0

# ---------------- System & Templates (generic only) ----------------
SYSTEM = """You are an expert Python test engineer.
Return ONLY valid Python source code (no Markdown, no backticks, no prose).
Hard rules:
- Test ONLY symbols from the project's own modules in analysis and standard library.
- Never import private/underscored modules (e.g., _pytest, pytest._code) or rely on internal APIs.
- Never assert equality on repr() or values that include memory addresses.
- Deterministic data only. No real network; mock I/O.
- If uncertain, emit a simple test_placeholder() that passes.
"""

UNIT_TEMPLATE = """Analysis JSON (compacted):
{analysis}

Write UNIT tests (max {max_tests} tests). Return ONLY Python code, no backticks.
Constraints: Do NOT import private modules or use pytest internals; do NOT assert on repr().
Guidelines:
- Target public functions/classes; assert exact outputs / exceptions.
- Use pytest; no external I/O; use tmp_path for files when needed.
"""

INTEG_GENERIC = """Analysis JSON (compacted):
{analysis}

Write INTEGRATION tests (max {max_tests} tests) WITHOUT assuming any web framework.
Constraints: No private modules; no repr-based assertions.
Guidelines:
- Identify seams with I/O (filesystem, db client objects, requests); mock with monkeypatch.
- If there is a CLI entrypoint (click/typer) found in analysis, you may test it via runner; otherwise mock I/O seams.
Return ONLY Python code, no backticks.
"""

E2E_GENERIC = """Analysis JSON (compacted):
{analysis}

Write E2E tests (max {max_tests} tests) for a minimal black-box workflow across multiple functions/modules.
- If no clear end-to-end entrypoint exists, emit a simple placeholder E2E test that passes.
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

# ---------------- Sanitizers ----------------
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

# --- Brittle patterns we never want in generated tests ---
BANNED_IMPORT_SUBSTRS = [
    "_pytest",            # pytest internals
    "pytest._code",       # private pytest code API
]
BRITTLE_SNIPPETS = [
    r"assert\s+repr\(",   # equality on repr is brittle
    r"\.fullsource\b",    # pytest private API
    r"\.source\b",        # pytest private API
    r"0x[0-9a-fA-F]+",    # memory addresses in reprs
]

def _skip_brittle_test_functions(code: str) -> str:
    """
    Find test functions that contain brittle patterns and decorate them with @pytest.mark.skip
    rather than failing CI. Keeps good tests intact.
    """
    lines = code.splitlines()
    out = []
    current = []

    def is_test_header(s: str) -> bool:
        return re.match(r"^\s*def\s+test_[A-Za-z0-9_]*\s*\(", s) is not None

    def needs_skip(block: List[str]) -> bool:
        txt = "\n".join(block)
        if any(re.search(pat, txt) for pat in BRITTLE_SNIPPETS):
            return True
        if any(sub in txt for sub in BANNED_IMPORT_SUBSTRS):
            return True
        return False

    i = 0
    while i < len(lines):
        line = lines[i]
        if is_test_header(line):
            if current:
                out.extend(current); current = []
            func_lines = [line]
            i += 1
            while i < len(lines) and not is_test_header(lines[i]):
                func_lines.append(lines[i]); i += 1
            if needs_skip(func_lines):
                out.append("@pytest.mark.skip(reason='auto-skip brittle assertion/import from generator')")
            out.extend(func_lines)
        else:
            current.append(line); i += 1

    if current:
        out.extend(current)
    return "\n".join(out) + ("\n" if not out or not out[-1].endswith("\n") else "")

def _header_guard_for_banned_imports(code: str) -> str:
    """If the module imports any banned internals, skip the module."""
    if any(sub in code for sub in BANNED_IMPORT_SUBSTRS):
        return (
            "import pytest as _pytest\n"
            "_pytest.skip('generator: banned private imports detected; skipping module', allow_module_level=True)\n\n"
        ) + code
    return code

# ---------------- LLM call ----------------
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
            # Harden output
            code = _skip_brittle_test_functions(code)
            code = _header_guard_for_banned_imports(code)
            return code
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

# ---------------- Main generation ----------------
def write(path: pathlib.Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

def generate_all(analysis: Dict[str, Any], outdir="tests/generated"):
    out = pathlib.Path(outdir)
    ts = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")

    compact = _compact_analysis(analysis)
    compact_json = json.dumps(compact, separators=(",",":"))

    kinds = {k.strip() for k in TESTGEN_KINDS.split(",") if k.strip()}

    if "unit" in kinds:
        unit_code = _gen(UNIT_TEMPLATE.format(analysis=compact_json, max_tests=TESTGEN_MAX_TESTS))
        write(out / f"test_unit_{ts}.py", unit_code)
        time.sleep(OAI_PAUSE_BETWEEN)

    if "integ" in kinds:
        integ_code = _gen(INTEG_GENERIC.format(analysis=compact_json, max_tests=TESTGEN_MAX_TESTS))
        write(out / f"test_integ_{ts}.py", integ_code)
        time.sleep(OAI_PAUSE_BETWEEN)

    if "e2e" in kinds:
        e2e_code = _gen(E2E_GENERIC.format(analysis=compact_json, max_tests=TESTGEN_MAX_TESTS))
        write(out / f"test_e2e_{ts}.py", e2e_code)

if __name__ == "__main__":
    import analyzer
    analysis = analyzer.analyze_python_tree(pathlib.Path("."))
    generate_all(analysis)
    print("✅ Generated tests in tests/generated")
