import ast, pathlib, json, os, argparse
from typing import Any, Dict, List

SKIP_DIR_NAMES = {".git", ".github", ".venv", "venv", "env", "node_modules", "site-packages", "dist", "build", "__pycache__", "tests", "tests/generated", ".mypy_cache"}

def read_text(p: pathlib.Path) -> str:
    return p.read_text(encoding="utf-8", errors="ignore")

def _should_skip(p: pathlib.Path, root: pathlib.Path) -> bool:
    try:
        rel = p.relative_to(root)
    except Exception:
        return False
    return any(part in SKIP_DIR_NAMES for part in rel.parts)

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
            if isinstance(node, ast.FunctionDef):
                out["functions"].append({"name": node.name, "file": str(f)})
                for d in node.decorator_list:
                    try:
                        # FastAPI-style: @router.get/post/... or @app.get(...)
                        attr = getattr(getattr(d, "func", None), "attr", None)
                        if attr in {"get", "post", "put", "patch", "delete"}:
                            out["routes"].append({"handler": node.name, "file": str(f), "method": attr})
                    except Exception:
                        pass
            elif isinstance(node, ast.ClassDef):
                out["classes"].append({"name": node.name, "file": str(f)})
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
