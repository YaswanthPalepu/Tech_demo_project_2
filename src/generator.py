import os, json, pathlib, datetime, re, ast, math
from typing import Dict, Any, List, Tuple
from openai import AzureOpenAI

# ---------------- System Prompt ----------------
SYSTEM = """You are an expert Python test engineer.
Return ONLY valid Python source code (no Markdown, no prose).
Rules:
- Test ONLY project modules + stdlib
- No private pytest APIs, no repr/address asserts
- Deterministic data, no real network
- Must contain multiple test_* functions with real assertions
- Never emit placeholders (assert True, test_placeholder, etc.)
- Use TestClient for FastAPI routes if detected
"""

# ---------------- Templates ----------------
UNIT_TEMPLATE = """Shard {shard}/{total} • Focus: {focus}
Analysis JSON:
{analysis}
Write 4–8 UNIT tests. Return ONLY Python code.
"""

INTEG_GENERIC = """Shard {shard}/{total} • Focus: {focus}
Analysis JSON:
{analysis}
Write 3–6 INTEGRATION tests. Return ONLY Python code.
"""

INTEG_FASTAPI = """Shard {shard}/{total} • Routes: {focus}
Analysis JSON:
{analysis}
Write FastAPI INTEGRATION tests using TestClient. Import app module and call endpoints.
"""

E2E_GENERIC = """Shard {shard}/{total} • Focus: {focus}
Analysis JSON:
{analysis}
Write 2–4 realistic E2E tests. Return ONLY Python code.
"""

E2E_FASTAPI = """Shard {shard}/{total} • Routes: {focus}
Analysis JSON:
{analysis}
Write FastAPI E2E tests using TestClient. Compose flows across endpoints.
"""

# ---------------- Azure OpenAI Helpers ----------------
def _get_any_env(*names: str) -> str:
    for n in names:
        v = os.getenv(n)
        if v:
            return v
    raise RuntimeError(f"Missing env var (tried: {', '.join(names)})")

def _client() -> AzureOpenAI:
    return AzureOpenAI(
        api_key=_get_any_env("AZURE_OPENAI_KEY", "AZURE_OPENAI_API_KEY"),
        azure_endpoint=_get_any_env("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_ENDPOINT"),
        api_version=_get_any_env("AZURE_OPENAI_API_VERSION", "OPENAI_API_VERSION"),
    )

def _deployment_name() -> str:
    return _get_any_env("AZURE_OPENAI_DEPLOYMENT", "OPENAI_DEPLOYMENT")

def _chat_completion_create(client: AzureOpenAI, deployment: str, messages: list):
    return client.chat.completions.create(model=deployment, messages=messages)

# ---------------- Validators ----------------
def _extract_python_only(text: str) -> str:
    if "```" in text:
        blocks = re.findall(r"```(?:python)?\s*(.*?)```", text, re.DOTALL)
        text = "\n\n".join(blocks) if blocks else text.replace("```", "")
    return text.strip() + "\n"

TEST_FUNC_RE = re.compile(r"^\s*def\s+test_", re.MULTILINE)

def _validate_code(code: str) -> Tuple[bool, str]:
    if not code.strip():
        return False, "empty"
    if not TEST_FUNC_RE.search(code):
        return False, "no test functions"
    try:
        ast.parse(code)
    except SyntaxError as e:
        return False, f"syntax error {e}"
    return True, ""

_PLACEHOLDER_PATTERNS = [r"test_placeholder", r"assert\s+True"]

def _looks_like_placeholder(code: str) -> bool:
    for pat in _PLACEHOLDER_PATTERNS:
        if re.search(pat, code):
            return True
    return False

# ---------------- LLM Wrapper ----------------
def _gen_validated(prompt: str, attempts: int = 3) -> str:
    client = _client()
    deployment = _deployment_name()
    messages = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]
    for _ in range(attempts):
        raw = _chat_completion_create(client, deployment, messages).choices[0].message.content or ""
        code = _extract_python_only(raw)
        ok, reason = _validate_code(code)
        if ok and not _looks_like_placeholder(code):
            return code
        messages.append({"role": "user", "content": f"Previous invalid ({reason}), regenerate strict Python tests"})
    raise RuntimeError("Failed to generate valid tests")

# ---------------- Analysis Helpers ----------------
def _dedupe_keep(items: List[Dict[str,str]], key: str, limit: int = None):
    seen, out = set(), []
    for it in items or []:
        k = it.get(key)
        if not k or k in seen: continue
        seen.add(k)
        out.append(it)
        if limit and len(out) >= limit: break
    return out

def _compact_analysis(analysis: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "functions": _dedupe_keep(analysis.get("functions", []), "name", 50),
        "classes":   _dedupe_keep(analysis.get("classes", []), "name", 25),
        "routes":    _dedupe_keep(analysis.get("routes", []), "handler", 25),
        "modules":   sorted(set(analysis.get("modules", []))),
    }

def _has_fastapi_routes(compact: Dict[str, Any]) -> bool:
    return bool(compact.get("routes"))

def _guess_app_module_name(compact: Dict[str, Any]) -> str:
    for mod in compact.get("modules", []):
        if "dashboard_api" in mod:
            return "dashboard_api"
    return "dashboard_api"

def _partition(lst, n_parts):
    if not lst: return [[] for _ in range(n_parts)]
    size = max(1, math.ceil(len(lst)/n_parts))
    return [lst[i:i+size] for i in range(0,len(lst),size)]

def _auto_files_per_kind(compact, kind: str) -> int:
    n = len(compact.get("functions", [])) + len(compact.get("classes", []))
    if kind != "unit": n = len(compact.get("routes", [])) or n
    if n <= 8: return 1
    if n <= 20: return 2
    if n <= 40: return 3
    return 4

def _focus_for_shard(compact, kind, shard_idx, total):
    if kind == "unit":
        targets = compact.get("functions", []) + compact.get("classes", [])
    else:
        targets = compact.get("routes", []) or (compact.get("functions", []) + compact.get("classes", []))
    groups = _partition(targets, total)
    names = [d.get("name") or d.get("handler") for d in groups[shard_idx] if d.get("name") or d.get("handler")]
    return (", ".join(names) if names else "(none)"), names

# ---------------- Main ----------------
def write(path: pathlib.Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

def generate_all(analysis: Dict[str, Any], outdir="tests/generated"):
    out = pathlib.Path(outdir)
    ts = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
    compact = _compact_analysis(analysis)
    compact_json = json.dumps(compact, separators=(",",":"))
    kinds = ["unit","integ","e2e"]

    fastapi_present = _has_fastapi_routes(compact)
    app_module = _guess_app_module_name(compact) if fastapi_present else None

    for kind in kinds:
        files_per_kind = _auto_files_per_kind(compact, kind)
        if kind == "unit" and not (compact.get("functions") or compact.get("classes")):
            print(f"⚠️ No functions/classes → skipping {kind}"); continue
        if kind in ("integ","e2e") and not (compact.get("routes") or compact.get("functions") or compact.get("classes")):
            print(f"⚠️ No routes/modules → skipping {kind}"); continue

        for i in range(files_per_kind):
            focus_label, _ = _focus_for_shard(compact, kind, i, files_per_kind)
            if kind == "unit":
                prompt = UNIT_TEMPLATE.format(analysis=compact_json, shard=i+1, total=files_per_kind, focus=focus_label)
            elif kind == "integ":
                if fastapi_present:
                    prompt = INTEG_FASTAPI.format(analysis=compact_json, shard=i+1, total=files_per_kind, focus=focus_label)
                    prompt += f"\n\nUse TestClient from {app_module}.app"
                else:
                    prompt = INTEG_GENERIC.format(analysis=compact_json, shard=i+1, total=files_per_kind, focus=focus_label)
            else:
                if fastapi_present:
                    prompt = E2E_FASTAPI.format(analysis=compact_json, shard=i+1, total=files_per_kind, focus=focus_label)
                    prompt += f"\n\nUse TestClient from {app_module}.app"
                else:
                    prompt = E2E_GENERIC.format(analysis=compact_json, shard=i+1, total=files_per_kind, focus=focus_label)
            code = _gen_validated(prompt)
            write(out / f"test_{kind}_{ts}_{i+1:02d}.py", code)

if __name__ == "__main__":
    import analyzer
    analysis = analyzer.analyze_python_tree(pathlib.Path("."))
    generate_all(analysis)
    print("✅ Generated tests in tests/generated")
