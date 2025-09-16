import ast, hashlib, json, pathlib
from typing import Dict, Tuple, Set

def _h(s: str) -> str: return hashlib.sha256(s.encode("utf-8")).hexdigest()

def _extract_signatures(py: pathlib.Path) -> Dict[str,str]:
    sigs: Dict[str,str] = {}
    try:
        txt = py.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(txt)
        lines = txt.splitlines()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                a, b = node.lineno-1, getattr(node,"end_lineno", node.lineno)
                seg = "\n".join(lines[a:b])
                sigs[f"{type(node).__name__.lower()}:{node.name}"] = _h(seg)
    except Exception:
        pass
    return sigs

def _load_state(manifest: pathlib.Path) -> Dict[str,dict]:
    if not manifest.exists(): return {}
    try:
        return json.loads(manifest.read_text(encoding="utf-8")).get("code_state", {})
    except Exception:
        return {}

def _save_state(manifest: pathlib.Path, state: Dict[str,dict]) -> None:
    data = {}
    if manifest.exists():
        try: data = json.loads(manifest.read_text(encoding="utf-8"))
        except Exception: data = {}
    data["code_state"] = state
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(data, indent=2), encoding="utf-8")

def detect_changes(target_root: pathlib.Path, manifest_path: pathlib.Path) -> Tuple[Set[str],Set[str],Set[str]]:
    prev = _load_state(manifest_path)
    cur: Dict[str,dict] = {}
    for py in target_root.rglob("*.py"):
        if any(part.startswith(".") for part in py.parts): continue
        if "test" in str(py).lower(): continue
        rel = str(py.relative_to(target_root))
        try: txt = py.read_text(encoding="utf-8", errors="ignore")
        except Exception: txt = ""
        cur[rel] = {"file_hash": _h(txt), "signatures": _extract_signatures(py)}
    addmod, deleted, unchanged = set(), set(), set()
    for fn, info in cur.items():
        if fn not in prev: addmod.add(fn); continue
        p = prev[fn]
        if info["file_hash"] != p.get("file_hash",""):
            if p.get("signatures",{}) != info["signatures"]: addmod.add(fn)
            else: unchanged.add(fn)
        else:
            unchanged.add(fn)
    for fn in prev:
        if fn not in cur: deleted.add(fn)
    _save_state(manifest_path, cur)
    return addmod, deleted, unchanged
