import json, random, os
from typing import Dict, Any, List, Tuple

SYSTEM_MIN = (
    "Return ONLY valid Python pytest tests. No Markdown.\n"
    "Guard third-party imports with try/except ImportError and call pytest.skip at module level.\n"
    "Use Arrange-Act-Assert, parametrize normal and edge cases; include error paths.\n"
    "Use tmp_path/monkeypatch/unittest.mock only; do not invent custom fixtures.\n"
    "Assert concrete outputs and types; refer to exception classes directly."
)
UNIT = "Write UNIT tests (3-6). Prefer public functions/classes in the focus list."
INTEG = "Write INTEGRATION tests (2-5) that cross modules; mock external I/O."
E2E = "Write E2E-style black-box tests (2-4) from public API only. Deterministic."

def targets_count(compact: Dict[str,Any], kind: str) -> int:
    if kind == "unit":
        return len(compact.get("functions",[])) + len(compact.get("classes",[]))
    n = len(compact.get("routes",[]) or [])
    return n or len(compact.get("functions",[])) + len(compact.get("classes",[]))

def files_per_kind(compact: Dict[str,Any], kind: str) -> int:
    n = targets_count(compact, kind)
    if n <= 0: return 0
    base = 3 if n <= 8 else 4 if n <= 20 else 6 if n <= 40 else 8 if n <= 100 else 12
    cap = int(os.getenv("TESTGEN_FILES_PER_KIND_MAX","6"))
    return min(base, max(1, min(n, cap)))

def focus_for(compact: Dict[str,Any], kind: str, shard_idx: int, total: int) -> Tuple[str,List[str]]:
    def _part(lst, total, idx):
        if not lst: return []
        size = max(1, (len(lst)+total-1)//total)
        return [d.get("name") or d.get("handler") for d in lst[idx*size:(idx+1)*size] if d.get("name") or d.get("handler")]
    if kind=="unit":
        L = (compact.get("functions") or []) + (compact.get("classes") or [])
        names = _part(L,total,shard_idx)
        return (", ".join(names) if names else "(none)"), names
    routes = compact.get("routes") or []
    if routes:
        names = _part(routes,total,shard_idx); return (", ".join(set(names)) or "(none)"), names
    L = (compact.get("functions") or []) + (compact.get("classes") or [])
    names = _part(L,total,shard_idx); return (", ".join(names) or "(none)"), names

def build_prompt(kind: str, compact_json: str, focus_label: str, shard: int, total: int, compact: Dict[str,Any]):
    fn = [f.get("name") for f in (compact.get("functions") or []) if f.get("name")]
    cn = [c.get("name") for c in (compact.get("classes")  or []) if c.get("name")]
    rn = [r.get("handler") for r in (compact.get("routes")  or []) if r.get("handler")]
    picks = sorted(random.sample(fn+cn+rn, k=min(len(fn+cn+rn), 16))) if fn or cn or rn else []
    brief = json.dumps({"focus": focus_label or "(none)", "suggested_targets": picks}, ensure_ascii=False)
    dev = UNIT if kind=="unit" else INTEG if kind=="integ" else E2E
    user = f"[{kind.upper()} shard {shard}/{total}] {dev}\nContext: {brief}\nAnalysis: {compact_json[:12000]}"
    return [{"role":"system","content":SYSTEM_MIN},{"role":"user","content":user}]

def runtime_guard(compact: Dict[str,Any]) -> str:
    crit = {"fastapi","flask","django","sqlalchemy","starlette","pydantic"}
    mods = { (m.split(".")[0] or "").lower() for m in (compact.get("modules") or []) }
    need = sorted(crit & mods)
    checks = ""
    if need:
        checks = "\n".join([f"import importlib.util, pytest\nif importlib.util.find_spec('{m}') is None:\n    pytest.skip('{m} not installed; skipping module', allow_module_level=True)" for m in need]) + "\n"
    # minimal bootstrap
    return checks + "\n" + \
        "import os, sys, types as _types, pytest as _pytest, warnings\n" \
        "warnings.filterwarnings('ignore', category=DeprecationWarning)\n" \
        "warnings.filterwarnings('ignore', category=PendingDeprecationWarning)\n" \
        "_t = os.environ.get('TARGET_ROOT') or 'target'\n" \
        "if _t and os.path.isdir(_t):\n" \
        "    _p = os.path.abspath(os.path.join(_t, os.pardir))\n" \
        "    [sys.path.insert(0, p) for p in (_p,_t) if p not in sys.path]\n" \
        "    _pkg=_types.ModuleType('target'); _pkg.__path__=[_t]; sys.modules.setdefault('target', _pkg)\n\n"
