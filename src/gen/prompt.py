# src/gen/prompt.py
import json, random, os
from typing import Dict, Any, List, Tuple

SYSTEM_MIN = (
    "Return ONLY valid Python test code for pytest (a .py module). No Markdown or prose.\n"
    "Style like a human engineer:\n"
    " - Use Arrange / Act / Assert; test_<function>_<case> names.\n"
    " - Prefer @pytest.mark.parametrize; cover edge/none/error paths.\n"
    " - Guard third-party imports with try/except ImportError + pytest.skip at module level.\n"
    " - Use tmp_path, monkeypatch, unittest.mock; no custom fixtures.\n"
    " - Mock outbound I/O and time; deterministic, no sleeps/network.\n"
    " - Assert concrete values and exception classes.\n"
    " - No AI/LLM comments.\n"
)

UNIT  = "Write UNIT tests for ALL public functions/classes in the focus list."
INTEG = "Write INTEGRATION tests crossing modules; mock FS/network/time."
E2E   = ("Write black-box E2E tests ONLY when real HTTP routes exist. "
         "Django: rest_framework.test.APIClient; FastAPI: TestClient; Flask: app.test_client(). "
         "Assert status codes, JSON keys, and include one negative case.")

def _env_int(name: str, default: int) -> int:
    try:
        v = int(os.getenv(name, "").strip())
        return v if v > 0 else default
    except Exception:
        return default

def _max_files_for(kind: str) -> int:
    # Per-kind caps, overridable via env. Global fallback: TESTGEN_MAX_FILES_PER_KIND
    global_cap = _env_int("TESTGEN_MAX_FILES_PER_KIND", 0) or None
    if kind == "unit":
        return _env_int("TESTGEN_MAX_UNIT_FILES", global_cap or 5)
    if kind == "integ":
        return _env_int("TESTGEN_MAX_INTEG_FILES", global_cap or 3)
    return _env_int("TESTGEN_MAX_E2E_FILES", global_cap or 2)

def targets_count(compact: Dict[str,Any], kind: str) -> int:
    if kind == "unit":
        return len(compact.get("functions",[]) or []) + len(compact.get("classes",[]) or [])
    if kind == "e2e":
        return len(compact.get("routes",[]) or [])
    return max(
        len(compact.get("functions",[]) or []) + len(compact.get("classes",[]) or []),
        len(compact.get("routes",[]) or []),
    )

def files_per_kind(compact: Dict[str,Any], kind: str) -> int:
    n = targets_count(compact, kind)
    if n <= 0:
        return 0
    cap = max(1, _max_files_for(kind))
    # Generate at most `cap` files. If n < cap, match n to avoid empty shards.
    return min(n, cap)

def _partition(lst: List[Dict[str,Any]], total: int, idx: int) -> List[str]:
    if not lst: return []
    size = max(1, (len(lst)+total-1)//total)  # ceil(len/total)
    start, end = idx*size, min(len(lst), (idx+1)*size)
    names = []
    for d in lst[start:end]:
        nm = d.get("name") or d.get("handler")
        if nm: names.append(nm)
    return names

def focus_for(compact: Dict[str,Any], kind: str, shard_idx: int, total: int) -> Tuple[str,List[str]]:
    if kind == "unit":
        L = (compact.get("functions") or []) + (compact.get("classes") or [])
    else:
        routes = compact.get("routes") or []
        L = routes if routes else (compact.get("functions") or []) + (compact.get("classes") or [])
    names = _partition(L, total, shard_idx)
    # Label lists the specific slice so shards collectively cover all targets.
    label = ", ".join(dict.fromkeys(names)) or "(none)"
    return label, names

def build_prompt(kind: str, compact_json: str, focus_label: str, shard: int, total: int, compact: Dict[str,Any]):
    fn = [f.get("name") for f in (compact.get("functions") or []) if f.get("name")]
    cn = [c.get("name") for c in (compact.get("classes")  or []) if c.get("name")]
    rn = [r.get("handler") for r in (compact.get("routes")  or []) if r.get("handler")]
    pool = fn + cn + rn
    picks = sorted(random.sample(pool, k=min(len(pool), 16))) if pool else []
    brief = json.dumps({"focus": focus_label or "(none)", "suggested_targets": picks}, ensure_ascii=False)
    dev = UNIT if kind=="unit" else INTEG if kind=="integ" else E2E
    user = (
        f"[{kind.upper()} shard {shard}/{total}] {dev}\n"
        f"Cover ONLY the functions/classes/handlers listed in 'focus'.\n"
        f"Context: {brief}\n"
        f"Analysis: {compact_json[:12000]}"
    )
    return [
        {"role":"system","content": SYSTEM_MIN},
        {"role":"user","content":   user},
    ]

def runtime_guard(compact: Dict[str,Any]) -> str:
    mods = {(m.split(".")[0] or "").lower() for m in (compact.get("modules") or [])}
    need = []
    if "fastapi" in mods: need += ["fastapi","starlette"]
    if "flask"   in mods: need += ["flask"]
    if "django"  in mods: need += ["django"]

    lines = []
    if need:
        lines.append("import importlib.util, pytest")
        for m in sorted(set(need)):
            lines.append(f"if importlib.util.find_spec('{m}') is None:")
            lines.append(f"    pytest.skip('{m} not installed; skipping module', allow_module_level=True)")
    lines.append("import os, sys, types as _types, warnings")
    lines.append("warnings.filterwarnings('ignore', category=DeprecationWarning)")
    lines.append("warnings.filterwarnings('ignore', category=PendingDeprecationWarning)")
    lines.append("_t = os.environ.get('TARGET_ROOT') or 'target'")
    lines.append("if _t and os.path.isdir(_t):")
    lines.append("    _p = os.path.abspath(os.path.join(_t, os.pardir))")
    lines.append("    [sys.path.insert(0, p) for p in (_p,_t) if p not in sys.path]")
    lines.append("    _pkg = _types.ModuleType('target'); _pkg.__path__=[_t]; sys.modules.setdefault('target', _pkg)")
    return "\n".join(lines) + "\n\n"
