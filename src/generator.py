import os, sys, json, pathlib, datetime, time, re, ast, math, subprocess, importlib.util, types as _types
from typing import Dict, Any, List, Tuple, Set
from openai import AzureOpenAI, RateLimitError, BadRequestError  # openai>=1.0.0

# ---------------- System & Templates ----------------
SYSTEM = """You are an expert Python test engineer.
Return ONLY valid Python source code (no Markdown, no backticks, no prose).
Hard rules:
- Test ONLY symbols from the project's own modules in analysis and standard library.
- Never import private/underscored modules (e.g., _pytest, pytest._code) or rely on internal APIs.
- Never assert equality on repr() or values that include memory addresses.
- Deterministic data only. No real network; mock I/O.
- If uncertain about a specific function, choose a different discovered function and write real assertions; DO NOT emit placeholders.
- Ensure the output contains at least ONE function whose name starts with test_.
- Import target modules INSIDE each test (lazy import), not at module import time.
"""

UNIT_TEMPLATE = """Shard {shard}/{total} • Focus targets: {focus}
Analysis JSON (compacted):
{analysis}

Write UNIT tests (aim 4–8 tests). Return ONLY Python code, no backticks.
Constraints:
- Do NOT import private modules or use pytest internals; do NOT assert on repr().
- Output MUST contain at least one test function named test_*.
- Import the module(s) you test INSIDE the test body (lazy import).
Guidelines:
- Target public functions/classes from the listed focus targets when possible; assert exact outputs / exceptions.
- Use pytest; no external I/O; use tmp_path for files when needed.
"""

INTEG_GENERIC = """Shard {shard}/{total} • Focus targets: {focus}
Analysis JSON (compacted):
{analysis}

Write INTEGRATION tests (aim 3–6 tests) WITHOUT assuming any web framework.
Constraints:
- No private modules; no repr-based assertions.
- Output MUST contain at least one test function named test_*.
- Import the module(s) you test INSIDE the test body (lazy import).
Guidelines:
- Identify seams with I/O (filesystem, db clients, HTTP calls); mock with monkeypatch.
- If a CLI entrypoint (click/typer) exists among focus targets, you may test it via runner; else mock I/O seams.
Return ONLY Python code, no backticks.
"""

E2E_GENERIC = """Shard {shard}/{total} • Focus targets: {focus}
Analysis JSON (compacted):
{analysis}

Write E2E tests (aim 2–4 tests) for a black-box workflow across multiple functions/modules.
- Prefer composing the listed focus targets.
- If no clear end-to-end entrypoint exists, compose two or more discovered functions into a realistic workflow.
Constraints:
- No private modules; no repr-based assertions.
- Output MUST contain at least one test function named test_*.
- Import the module(s) you test INSIDE the test body (lazy import).
Return ONLY Python code, no backticks.
"""

INTEG_FASTAPI = """Shard {shard}/{total} • Focus targets: {focus}
Analysis JSON (compacted):
{analysis}

Write INTEGRATION tests (aim 3–6 tests) for a FastAPI application.
Constraints:
- Use: from fastapi.testclient import TestClient
- Build TestClient(app) from the project’s FastAPI app object; assert status codes and JSON shapes.
- Output MUST contain at least one test function named test_*.
- Import the app INSIDE the test body (lazy import).
Return ONLY Python code, no backticks.
"""

E2E_FASTAPI = """Shard {shard}/{total} • Focus targets: {focus}
Analysis JSON (compacted):
{analysis}

Write E2E tests (aim 2–4 tests) for FastAPI using TestClient.
- Chain a minimal workflow across endpoints (e.g., POST -> GET -> PUT/DELETE) with deterministic payloads.
- Assert status codes and response JSON keys/values.
Constraints:
- Output MUST contain at least one test function named test_*.
- Import the app INSIDE the test body (lazy import).
Return ONLY Python code, no backticks.
"""

# ---------------- Minimal Azure OpenAI helpers ----------------
def _get_any_env(*names: str) -> str:
    for n in names:
        v = os.getenv(n)
        if v:
            return v
    raise RuntimeError(f"Missing required environment variable (tried: {', '.join(names)})")

def _client() -> AzureOpenAI:
    return AzureOpenAI(
        api_key=_get_any_env("AZURE_OPENAI_KEY", "AZURE_OPENAI_API_KEY"),
        azure_endpoint=_get_any_env("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_ENDPOINT"),
        api_version=_get_any_env("AZURE_OPENAI_API_VERSION", "OPENAI_API_VERSION"),
    )

def _deployment_name() -> str:
    return _get_any_env("AZURE_OPENAI_DEPLOYMENT", "OPENAI_DEPLOYMENT")

def _chat_completion_create(client: AzureOpenAI, deployment: str, messages: list):
    # Azure-friendly defaults: no temperature/n, no token caps
    return client.chat.completions.create(model=deployment, messages=messages)

# ---------------- Sanitizers & validators ----------------
def _extract_python_only(text: str) -> str:
    if "```" in text:
        blocks = re.findall(r"```(?:python)?\s*(.*?)```", text, flags=re.IGNORECASE|re.DOTALL)
        text = "\n\n".join(blocks) if blocks else text.replace("```", "")
    lines = text.splitlines()
    if lines and lines[0].strip().lower() in {"python", "py"}:
        lines = lines[1:]
    return ("\n".join(lines)).strip() + "\n"

TEST_FUNC_RE = re.compile(r"^\s*def\s+test_[A-Za-z0-9_]*\s*\(", re.MULTILINE)

def _validate_code(code: str) -> Tuple[bool, str]:
    if not code or not code.strip():
        return False, "empty output"
    if not TEST_FUNC_RE.search(code):
        return False, "no test_ functions found"
    try:
        ast.parse(code, filename="<generated>", mode="exec")
    except SyntaxError as e:
        return False, f"syntax error: {e}"
    return True, ""

# --- Brittle patterns to avoid in generated tests ---
BANNED_IMPORT_SUBSTRS = ["_pytest", "pytest._code"]
BRITTLE_SNIPPETS = [r"assert\s+repr\(", r"\.fullsource\b", r"\.source\b", r"0x[0-9a-fA-F]+"]

def _ensure_pytest_import(text: str) -> str:
    if "@pytest.mark.skip" in text and not re.search(r"^\s*import\s+pytest\b", text, re.MULTILINE):
        return "import pytest\n" + text
    return text

def _skip_brittle_test_functions(code: str) -> str:
    lines = code.splitlines()
    out, current = [], []

    def is_test_header(s: str) -> bool:
        return TEST_FUNC_RE.match(s) is not None

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
            func_lines = [line]; i += 1
            while i < len(lines) and not is_test_header(lines[i]):
                func_lines.append(lines[i]); i += 1
            if needs_skip(func_lines):
                out.append("@pytest.mark.skip(reason='auto-skip brittle assertion/import from generator')")
            out.extend(func_lines)
        else:
            current.append(line); i += 1

    if current:
        out.extend(current)
    text = "\n".join(out)
    if not text.endswith("\n"):
        text += "\n"
    return _ensure_pytest_import(text)

def _header_guard_for_banned_imports(code: str) -> str:
    if any(sub in code for sub in BANNED_IMPORT_SUBSTRS):
        return (
            "import pytest as _pytest\n"
            "_pytest.skip('generator: banned private imports detected; skipping module', allow_module_level=True)\n\n"
        ) + code
    return code

# ---------------- LLM wrapper with basic regeneration ----------------
def _gen_validated(prompt: str, attempts_per_file: int = 3, backoff_seq=(3, 7, 15)) -> str:
    client = _client()
    deployment = _deployment_name()

    messages = [
        {"role": "system", "content": SYSTEM},
        {"role": "user",   "content": prompt},
    ]

    attempts = 0
    while attempts < attempts_per_file:
        attempts += 1
        last_err = None
        for sleep_s in (0, *backoff_seq):
            try:
                if sleep_s:
                    time.sleep(sleep_s)
                resp = _chat_completion_create(client, deployment, messages)
                break
            except RateLimitError as e:
                last_err = e
                continue
        else:
            raise RuntimeError(f"Azure OpenAI rate-limited after retries: {last_err}")

        raw = resp.choices[0].message.content or ""
        cleaned = _extract_python_only(raw)

        ok, reason = _validate_code(cleaned)
        if ok:
            code = _skip_brittle_test_functions(cleaned)
            code = _header_guard_for_banned_imports(code)
            return code

        messages.append({
            "role": "user",
            "content": f"Previous attempt invalid: {reason}. Regenerate STRICT Python tests with at least one test_ function, no markdown, no prose. Import inside tests only."
        })

    raise RuntimeError(f"Test generation failed after {attempts_per_file} attempts (last reason: {reason}).")

# ---------------- Analysis compaction (light dedupe) ----------------
def _dedupe_keep(items: List[Dict[str, str]], key: str, limit: int = None) -> List[Dict[str, str]]:
    seen, out = set(), []
    for it in items or []:
        k = it.get(key)
        if not k or k in seen:
            continue
        seen.add(k)
        out.append({kk: it.get(kk) for kk in ("name","file","handler","method") if kk in it})
        if limit and len(out) >= limit:
            break
    return out

def _compact_analysis(analysis: Dict[str, Any]) -> Dict[str, Any]:
    total_funcs = len(analysis.get("functions", []))
    soft_cap = 120 if total_funcs > 400 else 80 if total_funcs > 200 else 50

    funcs  = sorted(analysis.get("functions", []), key=lambda x: x.get("file",""))
    clss   = sorted(analysis.get("classes",   []), key=lambda x: x.get("file",""))
    routes = sorted(analysis.get("routes",    []), key=lambda x: x.get("file",""))

    return {
        "functions": _dedupe_keep(funcs,  "name",   soft_cap),
        "classes":   _dedupe_keep(clss,   "name",   max(30, soft_cap // 2)),
        "routes":    _dedupe_keep(routes, "handler", max(30, soft_cap // 2)),
        "modules":   sorted(set(analysis.get("modules", []))),
    }

# ---------------- Dependency inference & installation ----------------
COMMON_PKG_ALIASES = {
    "bs4": "beautifulsoup4",
    "yaml": "PyYAML",
    "cv2": "opencv-python",
    "sklearn": "scikit-learn",
    "PIL": "Pillow",
    "Crypto": "pycryptodome",
    "MySQLdb": "mysqlclient",
    "mysql": "mysqlclient",
    "psycopg2": "psycopg2-binary",
    "boto3": "boto3",
    "httpx": "httpx",
    "requests": "requests",
    "uvicorn": "uvicorn",
    "fastapi": "fastapi",
    "starlette": "starlette",
    "pydantic": "pydantic",
    "typing_extensions": "typing-extensions",
    "annotated_types": "annotated-types",
    "sqlalchemy": "SQLAlchemy",
    "flask": "flask",
    "django": "Django",
    "click": "click",
    "typer": "typer",
    "jinja2": "Jinja2",
    "ujson": "ujson",
    "orjson": "orjson",
    "pymongo": "pymongo",
    "redis": "redis",
    "pytest": "pytest",
}

def _is_stdlib(name: str) -> bool:
    try:
        stdmods = getattr(sys, "stdlib_module_names", None)
        if stdmods:
            return name in stdmods
        return name in {
            "os","sys","re","json","pathlib","math","itertools","functools","typing","subprocess",
            "datetime","time","collections","dataclasses","ast","logging","unittest","argparse",
            "asyncio","multiprocessing","threading","sqlite3","email","http","urllib","hashlib",
            "hmac","base64","statistics","random","fractions","decimal","csv","shutil","tempfile",
            "glob","inspect","traceback","textwrap","string","pprint","enum","types"
        }
    except Exception:
        return False

def _is_local_import(top: str) -> bool:
    p = pathlib.Path(top)
    if p.exists():
        return True
    if pathlib.Path(top.replace(".", "/")).exists():
        return True
    for base in (pathlib.Path("."), pathlib.Path("src"), pathlib.Path("backend"), pathlib.Path("app")):
        if (base / f"{top}.py").exists() or (base / top).is_dir():
            return True
    return False

def _infer_required_packages(compact: Dict[str, Any]) -> List[str]:
    mods = compact.get("modules") or []
    needed: Set[str] = set()
    for m in mods:
        top = (m.split(".")[0] or "").strip()
        if not top or _is_stdlib(top) or _is_local_import(top):
            continue
        pkg = COMMON_PKG_ALIASES.get(top, top)
        needed.add(pkg)
    lowers = {p.lower() for p in needed}
    if "fastapi" in lowers:
        needed.update({"starlette", "pydantic"})
    return sorted(needed)

def _pip_install(packages: List[str]) -> None:
    if not packages:
        print("📦 No third-party packages inferred from imports.")
        return
    print("📦 Installing packages from analysis:", ", ".join(packages))
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-input", *packages])
    except subprocess.CalledProcessError as e:
        print(f"⚠️ pip install failed with exit code {e.returncode} (continuing; tests may skip).")

# ---------------- Sharding helpers ----------------
def _partition(lst: List[Dict[str, str]], n_parts: int) -> List[List[Dict[str, str]]]:
    if not lst:
        return [[] for _ in range(n_parts)]
    size = max(1, math.ceil(len(lst) / n_parts))
    groups = [lst[i:i+size] for i in range(0, len(lst), size)]
    while len(groups) < n_parts:
        groups.append([])
    return groups

def _auto_files_per_kind(compact: Dict[str, Any], kind: str) -> int:
    if kind == "unit":
        n = len(compact.get("functions", [])) + len(compact.get("classes", []))
    else:
        n = len(compact.get("routes", []))
        if n == 0:
            n = len(compact.get("functions", [])) + len(compact.get("classes", []))
    if n <= 8:    return 3
    if n <= 20:   return 4
    if n <= 40:   return 6
    if n <= 100:  return 8
    return 12

def _focus_for_shard(compact: Dict[str, Any], kind: str, shard_idx: int, total: int) -> Tuple[str, List[str]]:
    if kind == "unit":
        targets = (compact.get("functions", []) or []) + (compact.get("classes", []) or [])
        groups = _partition(targets, total)
        names = [d.get("name") for d in groups[shard_idx] if d.get("name")]
        return ", ".join(names) if names else "(none)", names

    routes = compact.get("routes", []) or []
    if routes:
        groups = _partition(routes, total)
        names = [d.get("handler") for d in groups[shard_idx] if d.get("handler")]
        label = ", ".join(sorted(set(names))) if names else "(none)"
        return label, names

    targets = (compact.get("functions", []) or []) + (compact.get("classes", []) or [])
    groups = _partition(targets, total)
    names = [d.get("name") for d in groups[shard_idx] if d.get("name")]
    return (", ".join(names) if names else "(none)"), names

# ---------------- FastAPI detection helpers ----------------
def _has_fastapi_routes(compact: Dict[str, Any]) -> bool:
    mods = {m.split(".")[0].lower() for m in (compact.get("modules") or [])}
    return "fastapi" in mods and bool(compact.get("routes"))

def _path_to_module(p: pathlib.Path) -> str:
    try:
        root = pathlib.Path(".").resolve()
        rp = p.resolve().relative_to(root)
    except Exception:
        rp = p
    if rp.name == "__init__.py":
        rp = rp.parent
    else:
        rp = rp.with_suffix("")
    return ".".join([part for part in rp.parts if part])

def _guess_app_module_name(compact: Dict[str, Any]) -> str:
    file_candidates = set()
    for col in ("functions", "classes", "routes"):
        for it in compact.get(col, []) or []:
            f = it.get("file")
            if f:
                file_candidates.add(f)
    if not file_candidates:
        file_candidates = {str(p) for p in pathlib.Path(".").rglob("*.py")}
    for f in file_candidates:
        try:
            p = pathlib.Path(f)
            txt = p.read_text(encoding="utf-8", errors="ignore")
            if "FastAPI(" in txt and re.search(r"\bapp\s*=\s*FastAPI\(", txt):
                return _path_to_module(p)
        except Exception:
            continue
    return "main"

# ---------------- Universal bootstrap (always prepended to tests) ----------------
def _universal_bootstrap(compact: Dict[str, Any]) -> str:
    # collect third-party tops for potential stubbing
    tops: List[str] = []
    for m in compact.get("modules") or []:
        top = (m.split(".")[0] or "").strip()
        if top and not _is_stdlib(top) and not _is_local_import(top):
            tops.append(top)
    tops = sorted(set(tops))
    tops_lit = repr(tops)

    return f'''# --- UNIVERSAL BOOTSTRAP (generated) ---
import os, sys, importlib.util as _iu, types as _types, pytest as _pytest

# Safe DB defaults for frameworks that read URLs at import-time
for _k in ("DATABASE_URL","DB_URL","SQLALCHEMY_DATABASE_URI"):
    _v = os.environ.get(_k)
    if not _v or "://" not in str(_v):
        os.environ[_k] = "sqlite:///:memory:"

# Configure minimal Django if present but not configured
try:
    if _iu.find_spec("django") is not None:
        import django
        from django.conf import settings as _dj_settings
        if not _dj_settings.configured:
            _dj_settings.configure(
                SECRET_KEY="test",
                DEBUG=True,
                ALLOWED_HOSTS=["*"],
                INSTALLED_APPS=[],
                DATABASES={{"default": {{"ENGINE":"django.db.backends.sqlite3","NAME":":memory:"}}}},
            )
            django.setup()
except Exception:
    pass

# Make SQLAlchemy create_engine resilient (fallback to SQLite on bad URL)
try:
    if _iu.find_spec("sqlalchemy") is not None:
        import sqlalchemy as _s_sa
        from sqlalchemy.exc import ArgumentError as _s_ArgErr
        _s_orig_create_engine = _s_sa.create_engine
        def _s_safe_create_engine(url, *args, **kwargs):
            try_url = url
            try:
                if not isinstance(try_url, str) or "://" not in try_url:
                    try_url = os.environ.get("DATABASE_URL") or os.environ.get("DB_URL") or os.environ.get("SQLALCHEMY_DATABASE_URI") or "sqlite:///:memory:"
                return _s_orig_create_engine(try_url, *args, **kwargs)
            except _s_ArgErr:
                return _s_orig_create_engine("sqlite:///:memory:", *args, **kwargs)
        _s_sa.create_engine = _s_safe_create_engine
except Exception:
    pass

# Stub any missing third-party tops so imports don't explode during collection
_THIRD_PARTY_TOPS = {tops_lit}
for _name in list(_THIRD_PARTY_TOPS):
    _top = (_name or "").split(".")[0]
    if not _top:
        continue
    if _iu.find_spec(_top) is None and _top not in sys.modules:
        _m = _types.ModuleType(_top)
        # minimal helpful stubs for a few common libs
        if _top == "sqlalchemy" and not hasattr(_m, "create_engine"):
            def create_engine(url, *a, **k): return object()
            _m.create_engine = create_engine
        sys.modules[_top] = _m
# --- /UNIVERSAL BOOTSTRAP ---
'''

# ---------------- Runtime guard (deps present check + bootstrap) ----------------
def _runtime_guard_for(compact: Dict[str, Any]) -> str:
    critical = {"fastapi", "flask", "django", "sqlalchemy", "starlette", "pydantic"}
    mods = {m.split(".")[0].lower() for m in (compact.get("modules") or [])}
    needed = sorted(critical & mods)

    checks = ""
    if needed:
        checks = "\n".join(
            [f"if importlib.util.find_spec('{m}') is None:\n    pytest.skip('{m} not installed; skipping module', allow_module_level=True)"
             for m in needed]
        ) + "\n"

    bootstrap = _universal_bootstrap(compact)

    return (
        "import importlib.util, pytest\n"
        + checks + "\n"
        + bootstrap + "\n"
    )

# ---------------- Main generation ----------------
def write(path: pathlib.Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

def generate_all(analysis: Dict[str, Any], outdir="tests/generated"):
    out = pathlib.Path(outdir)
    ts = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")

    compact = _compact_analysis(analysis)

    # Install inferred third-party deps BEFORE generating tests
    _pip_install(_infer_required_packages(compact))

    compact_json = json.dumps(compact, separators=(",",":"))
    kinds = ["unit", "integ", "e2e"]

    fastapi_present = _has_fastapi_routes(compact)
    app_module = _guess_app_module_name(compact) if fastapi_present else None

    guard = _runtime_guard_for(compact)

    for kind in kinds:
        files_per_kind = _auto_files_per_kind(compact, kind)

        if kind == "unit" and not (compact.get("functions") or compact.get("classes")):
            print(f"⚠️ No functions/classes found → skipping {kind} test generation")
            continue
        if kind in ("integ", "e2e") and not (compact.get("routes") or compact.get("functions") or compact.get("classes")):
            print(f"⚠️ No routes or modules found → skipping {kind} test generation")
            continue

        for i in range(files_per_kind):
            focus_label, _ = _focus_for_shard(compact, kind, i, files_per_kind)

            if kind == "unit":
                prompt = UNIT_TEMPLATE.format(analysis=compact_json, shard=i+1, total=files_per_kind, focus=focus_label)
                code = _gen_validated(prompt)
                write(out / f"test_unit_{ts}_{i+1:02d}.py", guard + code)

            elif kind == "integ":
                if fastapi_present:
                    prompt = INTEG_FASTAPI.format(analysis=compact_json, shard=i+1, total=files_per_kind, focus=focus_label)
                    prompt += f"\n\nIMPORTANT: Import the FastAPI app from '{app_module}' and use TestClient({app_module}.app), but import INSIDE the test."
                else:
                    prompt = INTEG_GENERIC.format(analysis=compact_json, shard=i+1, total=files_per_kind, focus=focus_label)
                code = _gen_validated(prompt)
                write(out / f"test_integ_{ts}_{i+1:02d}.py", guard + code)

            elif kind == "e2e":
                if fastapi_present:
                    prompt = E2E_FASTAPI.format(analysis=compact_json, shard=i+1, total=files_per_kind, focus=focus_label)
                    prompt += f"\n\nIMPORTANT: Use TestClient with '{app_module}.app', importing inside the test."
                else:
                    prompt = E2E_GENERIC.format(analysis=compact_json, shard=i+1, total=files_per_kind, focus=focus_label)
                code = _gen_validated(prompt)
                write(out / f"test_e2e_{ts}_{i+1:02d}.py", guard + code)

if __name__ == "__main__":
    import analyzer
    analysis = analyzer.analyze_python_tree(pathlib.Path("."))
    generate_all(analysis)
    print("✅ Generated tests in tests/generated")
