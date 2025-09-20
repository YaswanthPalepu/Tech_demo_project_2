# src/analyzer.py
import ast, pathlib, json, os, argparse
from typing import Any, Dict, List

SKIP_DIR_NAMES = {".git", ".github", ".venv", "venv", "env", "node_modules", "site-packages",
                  "dist", "build", "__pycache__", "tests", "tests/generated", ".mypy_cache"}

def read_text(p: pathlib.Path) -> str:
    return p.read_text(encoding="utf-8", errors="ignore")

def _should_skip(p: pathlib.Path, root: pathlib.Path) -> bool:
    try:
        rel = p.relative_to(root)
    except Exception:
        return False
    return any(part in SKIP_DIR_NAMES for part in rel.parts)

def _route_info(dec) -> Dict[str, Any]:
    info = {}
    try:
        func = getattr(dec, "func", None)
        attr = getattr(func, "attr", None)
        if attr in {"get","post","put","patch","delete"}:
            info["method"] = attr
            # path like @router.get("/items")
            if hasattr(dec, "args") and dec.args:
                arg0 = dec.args[0]
                if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
                    info["path"] = arg0.value
    except Exception:
        pass
    return info

def analyze_python_tree(root: pathlib.Path) -> Dict[str, Any]:
    files: List[pathlib.Path] = [p for p in root.rglob("*.py") if not _should_skip(p, root)]
    out = {"functions": [], "classes": [], "routes": [], "modules": []}
    for f in files:
        try:
            code = read_text(f)
            tree = ast.parse(code)
        except Exception:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                rec = {"name": node.name, "file": str(f.relative_to(root)), "lineno": getattr(node, "lineno", 1),
                       "end_lineno": getattr(node, "end_lineno", getattr(node, "lineno", 1))}
                out["functions"].append(rec)
                for d in getattr(node, "decorator_list", []):
                    info = _route_info(d)
                    if info:
                        out["routes"].append({"handler": node.name, "file": rec["file"],
                                              "method": info.get("method"), "path": info.get("path"),
                                              "lineno": rec["lineno"], "end_lineno": rec["end_lineno"]})
            elif isinstance(node, ast.ClassDef):
                out["classes"].append({"name": node.name, "file": str(f.relative_to(root)),
                                       "lineno": getattr(node, "lineno", 1),
                                       "end_lineno": getattr(node, "end_lineno", getattr(node, "lineno", 1))})
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.Import):
                    out["modules"].extend([a.name for a in node.names])
                else:
                    if node.module:
                        out["modules"].append(node.module)
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=os.getenv("ANALYZE_ROOT", "."), help="root directory to analyze")
    args = ap.parse_args()
    root = pathlib.Path(args.root)
    print(json.dumps(analyze_python_tree(root), indent=2))

if __name__ == "__main__":
    main()
