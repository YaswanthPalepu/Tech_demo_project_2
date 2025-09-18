import os, re, math, pathlib, random, json, subprocess, sys, importlib.util
from typing import Dict, Any, List, Tuple, Optional, Set
from .env import norm_rel

COMMON_PKG_ALIASES = {
    "bs4":"beautifulsoup4","yaml":"PyYAML","cv2":"opencv-python","sklearn":"scikit-learn",
    "PIL":"Pillow","Crypto":"pycryptodome","MySQLdb":"mysqlclient","mysql":"mysqlclient",
    "psycopg2":"psycopg2-binary","boto3":"boto3","httpx":"httpx","requests":"requests",
    "uvicorn":"uvicorn","fastapi":"fastapi","starlette":"starlette","pydantic":"pydantic",
    "typing_extensions":"typing-extensions","annotated_types":"annotated-types","sqlalchemy":"SQLAlchemy",
    "flask":"flask","django":"Django","click":"click","typer":"typer","jinja2":"Jinja2",
    "ujson":"ujson","orjson":"orjson","pymongo":"pymongo","redis":"redis","pytest":"pytest",
    "jwt":"PyJWT","markupsafe":"MarkupSafe","rest_framework":"djangorestframework",
}
DENY_GENERIC = {"models","views","urls","settings","config","tests","schemas","forms","admin","migrations","apps","serializers","permissions","filters","routers","services","repository","helpers","utils"}
DENY_TOPS = set(DENY_GENERIC) | {"__future__","__main__","builtins","typing","types","dataclasses","importlib","asyncio","json","re","os","sys","pathlib","logging","argparse","functools","itertools","collections","subprocess","datetime","time","math","decimal","fractions","statistics","sqlite3","http","urllib","hmac","hashlib","base64","csv","glob","shutil","tempfile","inspect","traceback","enum","textwrap","pprint","string"}

def _is_stdlib(top: str) -> bool:
    std = getattr(sys, "stdlib_module_names", None)
    if std: return top in std
    return top in {"os","sys","re","json","pathlib","math","itertools","functools","typing","subprocess","datetime","time","collections","dataclasses","ast","logging","unittest","argparse","asyncio","threading","sqlite3","email","http","urllib","hashlib","hmac","base64","statistics","random","fractions","decimal","csv","shutil","tempfile","glob","inspect","traceback","textwrap","string","pprint","enum","types"}

def _is_local(top: str) -> bool:
    roots = [pathlib.Path(p) for p in (os.environ.get("TARGET_ROOT") or "", ".", "src", "backend", "app", "target") if p]
    if pathlib.Path(top).exists() or pathlib.Path(top.replace(".","/")).exists(): return True
    for base in roots:
        if (base / f"{top}.py").exists() or (base / top).is_dir():
            return True
    return False

def dedupe_keep(items: List[Dict[str, str]], key: str, limit: int) -> List[Dict[str,str]]:
    seen, out = set(), []
    for it in items or []:
        k = it.get(key)
        if not k or k in seen: continue
        seen.add(k)
        out.append({kk: it.get(kk) for kk in ("name","file","handler","method") if kk in it})
        if len(out) >= limit: break
    return out

def compact_analysis(analysis: Dict[str, Any]) -> Dict[str, Any]:
    total_funcs = len(analysis.get("functions", []))
    cap = 120 if total_funcs > 400 else 80 if total_funcs > 200 else 50
    funcs  = sorted(analysis.get("functions", []), key=lambda x: x.get("file",""))
    clss   = sorted(analysis.get("classes", []),  key=lambda x: x.get("file",""))
    routes = sorted(analysis.get("routes", []),   key=lambda x: x.get("file",""))
    return {
        "functions": dedupe_keep(funcs,  "name", cap),
        "classes":   dedupe_keep(clss,  "name", max(30, cap//2)),
        "routes":    dedupe_keep(routes, "handler", max(30, cap//2)),
        "modules": sorted(set(analysis.get("modules", []))),
    }

def filter_by_files(analysis: Dict[str, Any], focus_files: Optional[Set[str]]):
    if not focus_files: return analysis, False
    focus_norm = {norm_rel(f) for f in focus_files}
    focus_basenames = {pathlib.Path(f).name for f in focus_norm}
    def keep(e): 
        fn = norm_rel(e.get("file") or "")
        return (fn in focus_norm) or (pathlib.Path(fn).name in focus_basenames)
    f = {
        "functions":[d for d in (analysis.get("functions") or []) if keep(d)],
        "classes":[d for d in (analysis.get("classes") or []) if keep(d)],
        "routes":[d for d in (analysis.get("routes") or []) if keep(d)],
        "modules": analysis.get("modules", [])
    }
    if not (f["functions"] or f["classes"] or f["routes"]):
        return analysis, True
    return f, False

# --- Skip GUI/heavy deps when not installed ---
_HEAVY = {
    "PyQt5": ("import PyQt5", "from PyQt5"),
    "PySide6": ("import PySide6", "from PySide6"),
    "PySide2": ("import PySide2", "from PySide2"),
    "tkinter": ("import tkinter", "from tkinter"),
    "wx": ("import wx", "from wx"),
    "cv2": ("import cv2", "from cv2"),
}

def _missing(mod: str) -> bool:
    try:
        return importlib.util.find_spec(mod) is None
    except Exception:
        return True

def _file_has_marker(path: str, needles) -> bool:
    try:
        txt = pathlib.Path(path).read_text(encoding="utf-8", errors="ignore")
        return any(n in txt for n in needles)
    except Exception:
        return False

def prune_unavailable_targets(compact: Dict[str, Any]) -> Dict[str, Any]:
    bad_files = set()
    for mod, needles in _HEAVY.items():
        if _missing(mod):
            for coll in ("functions","classes","routes"):
                for d in compact.get(coll, []) or []:
                    f = d.get("file")
                    if f and _file_has_marker(f, needles):
                        bad_files.add(f)
    if not bad_files:
        return compact
    def keep(d): return d.get("file") not in bad_files
    return {
        "functions":[d for d in (compact.get("functions") or []) if keep(d)],
        "classes":[d for d in (compact.get("classes") or []) if keep(d)],
        "routes":[d for d in (compact.get("routes") or []) if keep(d)],
        "modules": compact.get("modules", []),
    }

def infer_required_packages(compact: Dict[str, Any]) -> List[str]:
    mods = compact.get("modules") or []
    needed = set()
    for m in mods:
        top = (m.split(".")[0] or "").strip()
        if not top or top in DENY_TOPS or top.startswith("_") or any(c.isupper() for c in top): continue
        if _is_stdlib(top) or _is_local(top): continue
        needed.add(COMMON_PKG_ALIASES.get(top, top))
    out = sorted(needed, key=str.lower)
    if "fastapi" in {x.lower() for x in out}:
        for extra in ("starlette","pydantic"):
            if extra not in out: out.append(extra)
    return out

def pip_install(packages: List[str]) -> None:
    pkgs = [p for p in (packages or []) if p and p.strip()]
    if not pkgs:
        print("📦 No third-party packages inferred.")
        return
    constraints = os.getenv("TESTGEN_PIP_CONSTRAINTS") or os.getenv("PIP_CONSTRAINT")
    print("📦 Installing (only-if-needed):", ", ".join(pkgs))
    for pkg in pkgs:
        cmd = [sys.executable,"-m","pip","install","--disable-pip-version-check","--no-input","--upgrade-strategy","only-if-needed"]
        if constraints: cmd += ["-c", constraints]
        cmd.append(pkg)
        try: subprocess.check_call(cmd); print(f"  ✅ {pkg}")
        except Exception as e: print(f"  ⚠️ {pkg}: {e}")
