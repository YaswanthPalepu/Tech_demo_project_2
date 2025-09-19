import re, ast
from typing import Tuple, List

TEST_FUNC_RE = re.compile(r"^\s*def\s+test_[A-Za-z0-9_]*\s*\(", re.MULTILINE)
BANNED_IMPORT_SUBSTRS = ["_pytest", "pytest._code"]
BRITTLE_SNIPPETS = [r"assert\s+repr\(", r"\.fullsource\b", r"\.source\b", r"0x[0-9a-fA-F]+"]

# stdlib-like modules that must not be wrapped
_STDLIKE = {
    "os","sys","re","json","pathlib","math","itertools","functools","typing","datetime","time",
    "collections","dataclasses","types","unittest","logging","subprocess","random","decimal",
    "fractions","statistics","csv","importlib","inspect","numbers","http","urllib","enum",
    "traceback","string","pprint","hashlib","hmac","base64","sqlite3"
}
def _wrap_candidate(mod: str) -> bool:
    return bool(mod) and mod not in _STDLIKE and not mod.startswith("_") and "." not in mod

def extract_python_only(text: str) -> str:
    if "```" in text:
        import re as _re
        blocks = _re.findall(r"```(?:python)?\s*(.*?)```", text, flags=_re.IGNORECASE|_re.DOTALL)
        text = "\n\n".join(blocks) if blocks else text.replace("```","")
    lines = text.splitlines()
    if lines and lines[0].strip().lower() in {"python","py"}: lines = lines[1:]
    s = "\n".join(lines).strip()
    return s + ("\n" if not s.endswith("\n") else "")

def validate_code(code: str) -> Tuple[bool,str]:
    if not code.strip(): return False, "empty output"
    if not TEST_FUNC_RE.search(code): return False, "no test_ functions found"
    try: ast.parse(code, filename="<generated>", mode="exec")
    except SyntaxError as e: return False, f"syntax error: {e}"
    return True, ""

def ensure_pytest_import_top(code: str) -> str:
    import re as _re
    return ("import pytest\n" + code) if not _re.search(r'^\s*import\s+pytest\b', code, _re.MULTILINE) else code

def _guard_local_imports(code: str) -> str:
    """Rewrite top-level likely-local imports. Skip stdlib."""
    def repl_import(m):
        mod = m.group(1); alias = m.group(2) or ""
        if not _wrap_candidate(mod): return m.group(0)
        as_part = f" as {alias}" if alias else ""
        return (
            f"try:\n    import {mod}{as_part}\n"
            f"except ModuleNotFoundError:\n"
            f"    try:\n        import {mod.lower()}{as_part}\n"
            f"    except ModuleNotFoundError:\n"
            f"        import importlib.util, sys, os\n"
            f"        _tr=os.environ.get('TARGET_ROOT') or 'target'\n"
            f"        _p1=os.path.join(_tr, '{mod}.py'); _p2=os.path.join(_tr, '{mod.lower()}.py')\n"
            f"        _pp=[_p for _p in (_p1,_p2) if os.path.isfile(_p)]\n"
            f"        if _pp:\n"
            f"            _spec=importlib.util.spec_from_file_location('{mod}', _pp[0])\n"
            f"            _m=importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_m)\n"
            f"            sys.modules.setdefault('{mod}', _m)\n"
            f"        else:\n"
            f"            raise\n"
        )
    def repl_from(m):
        mod, rest = m.group(1), m.group(2)
        if not _wrap_candidate(mod): return m.group(0)
        return (
            f"try:\n    from {mod} import {rest}\n"
            f"except ModuleNotFoundError:\n"
            f"    try:\n        from {mod.lower()} import {rest}\n"
            f"    except ModuleNotFoundError:\n"
            f"        import importlib.util, sys, os\n"
            f"        _tr=os.environ.get('TARGET_ROOT') or 'target'\n"
            f"        _p1=os.path.join(_tr, '{mod}.py'); _p2=os.path.join(_tr, '{mod.lower()}.py')\n"
            f"        _pp=[_p for _p in (_p1,_p2) if os.path.isfile(_p)]\n"
            f"        if _pp:\n"
            f"            _spec=importlib.util.spec_from_file_location('{mod}', _pp[0])\n"
            f"            _m=importlib.util.module_from_spec(_spec); _spec.loader.exec_module(_m)\n"
            f"            sys.modules.setdefault('{mod}', _m)\n"
            f"            from {mod} import {rest}\n"
            f"        else:\n"
            f"            raise\n"
        )
    code = re.sub(r'^\s*import\s+([A-Za-z_]\w*)(?:\s+as\s+([A-Za-z_]\w*))?\s*$', repl_import, code, flags=re.MULTILINE)
    code = re.sub(r'^\s*from\s+([A-Za-z_]\w*)\s+import\s+([^\n]+)$', repl_from, code, flags=re.MULTILINE)
    return code

def skip_brittle_functions(code: str) -> str:
    lines, out, cur = code.splitlines(), [], []
    def is_hdr(s): return TEST_FUNC_RE.match(s) is not None
    def needs_skip(block):
        txt = "\n".join(block)
        import re as _re
        return any(_re.search(p, txt) for p in BRITTLE_SNIPPETS) or any(sub in txt for sub in BANNED_IMPORT_SUBSTRS)
    i=0
    while i < len(lines):
        if is_hdr(lines[i]):
            if cur: out.extend(cur); cur=[]
            func=[lines[i]]; i+=1
            while i < len(lines) and not is_hdr(lines[i]): func.append(lines[i]); i+=1
            if needs_skip(func): out.append("@pytest.mark.skip(reason='auto-skip brittle assertion/import from generator')")
            out.extend(func)
        else:
            cur.append(lines[i]); i+=1
    if cur: out.extend(cur)
    s = "\n".join(out)
    if not s.endswith("\n"): s+="\n"
    return ensure_pytest_import_top(s)

def header_guard_banned(code: str) -> str:
    if any(sub in code for sub in BANNED_IMPORT_SUBSTRS):
        return "import pytest as _pytest\n_pytest.skip('generator: banned private imports detected; skipping module', allow_module_level=True)\n\n" + code
    return code

def massage(code: str) -> str:
    code = _guard_local_imports(code)  # safe; no try/except surgery
    code = re.sub(r'^\s*from\s+([A-Za-z_][\w\.]*)\s+import\s+__init__\s+as\s+([A-Za-z_]\w*)\s*',
                  r'import \1 as \2', code, flags=re.MULTILINE)
    code = re.sub(r'^\s*from\s+([A-Za-z_][\w\.]*)\s+import\s+__init__\s*',
                  r'import \1', code, flags=re.MULTILINE)
    out=[]
    for line in code.splitlines():
        out.append(line)
        if line.lstrip().startswith("def test_"):
            out.append("    # Arrange-Act-Assert: generated by ai-testgen")
    code = "\n".join(out)
    code = ensure_pytest_import_top(code)
    return code if code.endswith("\n") else code + "\n"
