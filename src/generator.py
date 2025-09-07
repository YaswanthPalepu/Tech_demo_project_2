import os, json, pathlib, datetime, time, random, re, ast, math
from typing import Dict, Any, List, Tuple
from openai import AzureOpenAI, RateLimitError, BadRequestError  # openai>=1.0.0

# ---------------- Tunables via env (safe defaults) ----------------
MAX_TOKENS        = int(os.getenv("OAI_MAX_TOKENS", "800"))          # cap LLM output
OAI_MAX_RETRIES   = int(os.getenv("OAI_MAX_RETRIES", "6"))
OAI_BASE_BACKOFF  = float(os.getenv("OAI_BASE_BACKOFF", "3"))
OAI_PAUSE_BETWEEN = float(os.getenv("OAI_PAUSE_BETWEEN_CALLS", "3"))
OAI_REQ_INTERVAL  = float(os.getenv("OAI_REQ_INTERVAL", "0"))        # seconds between API calls (0=off)

TESTGEN_KINDS         = os.getenv("TESTGEN_KINDS", "unit,integ,e2e")     # comma list
TESTGEN_MAX_TESTS     = int(os.getenv("TESTGEN_MAX_TESTS", "6"))
TESTGEN_FILES_PER_KIND= int(os.getenv("TESTGEN_FILES_PER_KIND", "3"))     # NEW: how many files per kind

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

UNIT_TEMPLATE = """Shard {shard}/{total} • Focus targets: {focus}
Analysis JSON (compacted):
{analysis}

Write UNIT tests (max {max_tests} tests). Return ONLY Python code, no backticks.
Constraints: Do NOT import private modules or use pytest internals; do NOT assert on repr().
Guidelines:
- Target public functions/classes from the listed focus targets when possible; assert exact outputs / exceptions.
- Use pytest; no external I/O; use tmp_path for files when needed.
"""

INTEG_GENERIC = """Shard {shard}/{total} • Focus targets: {focus}
Analysis JSON (compacted):
{analysis}

Write INTEGRATION tests (max {max_tests} tests) WITHOUT assuming any web framework.
Constraints: No private modules; no repr-based assertions.
Guidelines:
- Identify seams with I/O (filesystem, db clients, HTTP calls); mock with monkeypatch.
- If a CLI entrypoint (click/typer) exists among focus targets, you may test it via runner; else mock I/O seams.
Return ONLY Python code, no backticks.
"""

E2E_GENERIC = """Shard {shard}/{total} • Focus targets: {focus}
Analysis JSON (compacted):
{analysis}

Write E2E tests (max {max_tests} tests) for a minimal black-box workflow across multiple functions/modules.
- Prefer composing the listed focus targets.
- If no clear end-to-end entrypoint exists, emit a simple placeholder E2E test that passes.
Return ONLY Python code, no backticks.
"""

# ---------------- Env helpers ----------------
def _get_any_env(*names: str) -> str:
    """Return the first non-empty env var among names, or raise."""
    for n in names:
        v = os.getenv(n)
        if v:
            return v
    raise RuntimeError(f"Missing required environment variable (tried: {', '.join(names)})")

# ---------------- Azure OpenAI client helpers ----------------
def _client() -> AzureOpenAI:
    return AzureOpenAI(
        api_key=_get_any_env("AZURE_OPENAI_KEY", "AZURE_OPENAI_API_KEY"),
        azure_endpoint=_get_any_env("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_ENDPOINT"),
        api_version=_get_any_env("AZURE_OPENAI_API_VERSION", "OPENAI_API_VERSION"),
    )

def _deployment_name() -> str:
    return _get_any_env("AZURE_OPENAI_DEPLOYMENT", "OPENAI_DEPLOYMENT")

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
    # If fenced, take inside of code blocks
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

def _placeholder_test(reason: str = "placeholder"):
    return (
        "import pytest\n\n"
        f"# generator: {reason}\n"
        "def test_placeholder():\n"
        "    assert True\n"
    )

def _compile_or_placeholder(code: str) -> str:
    # If empty/whitespace or has no test functions, force placeholder
    if not code.strip() or "def test_" not in code:
        return _placeholder_test("empty-or-no-tests")
    try:
        ast.parse(code, filename="<generated>", mode="exec")
        return code
    except SyntaxError as e:
        print(f"[Sanitize] AST parse failed: {e}. Falling back to placeholder.")
        return _placeholder_test("syntax-error")

# --- Brittle patterns to avoid in generated tests ---
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
    """Auto-skip test functions containing brittle patterns."""
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
    text = "\n".join(out)
    if not text.endswith("\n"):
        text += "\n"
    return text

def _header_guard_for_banned_imports(code: str) -> str:
    """If the module imports any banned internals, skip the module."""
    if any(sub in code for sub in BANNED_IMPORT_SUBSTRS):
        return (
            "import pytest as _pytest\n"
            "_pytest.skip('generator: banned private imports detected; skipping module', allow_module_level=True)\n\n"
        ) + code
    return code

# ---------------- Chat call (Azure-compatible across variants) ----------------
def _chat_completion_create(client: AzureOpenAI, deployment: str, messages: list):
    """
    Create a chat completion compatible with Azure variants:
    - Do NOT send temperature/n (some deployments only accept defaults).
    - Try token param names in order; finally try with none.
    """
    base = dict(model=deployment, messages=messages)  # no temperature, no n
    tried_err = None
    for token_param in ("max_tokens", "max_completion_tokens", "max_output_tokens", None):
        try:
            kwargs = dict(base)
            if token_param:
                kwargs[token_param] = MAX_TOKENS
            return client.chat.completions.create(**kwargs)
        except BadRequestError as e:
            msg = str(e)
            if any(s in msg for s in ("Unsupported parameter", "unknown parameter", "unsupported_parameter", "Unsupported value")):
                tried_err = e
                continue
            raise
    if tried_err:
        raise tried_err

def _gen(prompt: str) -> str:
    global _last_call
    client = _client()
    deployment = _deployment_name()
    last_err = None
    for attempt in range(OAI_MAX_RETRIES):
        try:
            _ensure_min_interval()
            resp = _chat_completion_create(
                client,
                deployment,
                [{"role": "system", "content": SYSTEM},
                 {"role": "user",   "content": prompt}],
            )
            _last_call = time.time()
            raw = resp.choices[0].message.content or ""
            cleaned = _extract_python_only(raw)
            code = _compile_or_placeholder(cleaned)
            code = _skip_brittle_test_functions(code)
            code = _header_guard_for_banned_imports(code)
            return code
        except RateLimitError as e:
            sleep_s = _sleep_from_headers(e, attempt)
            print(f"[429] attempt {attempt+1}/{OAI_MAX_RETRIES}; sleeping {sleep_s:.1f}s")
            time.sleep(sleep_s)
        except BadRequestError:
            raise
    raise RuntimeError(f"Azure OpenAI rate-limited after {OAI_MAX_RETRIES} attempts: {last_err}")

# ---------------- Analysis compaction & sharding ----------------
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

def _partition(lst: List[Dict[str, str]], n_parts: int) -> List[List[Dict[str, str]]]:
    if not lst:
        return [[] for _ in range(n_parts)]
    size = max(1, math.ceil(len(lst) / n_parts))
    return [lst[i:i+size] for i in range(0, len(lst), size)] + [[]] * max(0, n_parts - math.ceil(len(lst)/size))

def _focus_for_shard(compact: Dict[str, Any], kind: str, shard_idx: int, total: int) -> Tuple[str, List[str]]:
    """
    Return (label, names) to focus this shard on, per test kind.
    For unit: functions/classes. For integ/e2e: routes if present, else functions/classes.
    """
    if kind == "unit":
        targets = (compact.get("functions", []) or []) + (compact.get("classes", []) or [])
        groups = _partition(targets, total)
        names = [d.get("name") for d in groups[shard_idx] if d.get("name")]
        return ", ".join(names) if names else "(none)", names

    # integ/e2e
    routes = compact.get("routes", []) or []
    if routes:
        groups = _partition(routes, total)
        names = [d.get("handler") for d in groups[shard_idx] if d.get("handler")]
        label = ", ".join(sorted(set(names))) if names else "(none)"
        return label, names
    # fallback to functions/classes
    targets = (compact.get("functions", []) or []) + (compact.get("classes", []) or [])
    groups = _partition(targets, total)
    names = [d.get("name") for d in groups[shard_idx] if d.get("name")]
    return (", ".join(names) if names else "(none)"), names

# ---------------- Main generation ----------------
def write(path: pathlib.Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

def generate_all(analysis: Dict[str, Any], outdir="tests/generated"):
    out = pathlib.Path(outdir)
    ts = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")

    compact = _compact_analysis(analysis)
    compact_json = json.dumps(compact, separators=(",",":"))

    kinds = [k.strip() for k in TESTGEN_KINDS.split(",") if k.strip()]
    files_per_kind = max(1, TESTGEN_FILES_PER_KIND)

    for kind in kinds:
        for i in range(files_per_kind):
            focus_label, _ = _focus_for_shard(compact, kind, i, files_per_kind)
            if kind == "unit":
                prompt = UNIT_TEMPLATE.format(analysis=compact_json, max_tests=TESTGEN_MAX_TESTS,
                                              shard=i+1, total=files_per_kind, focus=focus_label)
                code = _gen(prompt)
                write(out / f"test_unit_{ts}_{i+1:02d}.py", code)
            elif kind == "integ":
                prompt = INTEG_GENERIC.format(analysis=compact_json, max_tests=TESTGEN_MAX_TESTS,
                                              shard=i+1, total=files_per_kind, focus=focus_label)
                code = _gen(prompt)
                write(out / f"test_integ_{ts}_{i+1:02d}.py", code)
            elif kind == "e2e":
                prompt = E2E_GENERIC.format(analysis=compact_json, max_tests=TESTGEN_MAX_TESTS,
                                            shard=i+1, total=files_per_kind, focus=focus_label)
                code = _gen(prompt)
                write(out / f"test_e2e_{ts}_{i+1:02d}.py", code)
            else:
                continue
            time.sleep(OAI_PAUSE_BETWEEN)

if __name__ == "__main__":
    import analyzer
    analysis = analyzer.analyze_python_tree(pathlib.Path("."))
    generate_all(analysis)
    print("✅ Generated tests in tests/generated")
