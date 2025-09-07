import ast, pathlib, json
from typing import Any, Dict

def read_text(p: pathlib.Path) -> str:
    return p.read_text(encoding="utf-8", errors="ignore")

def analyze_python_tree(root: pathlib.Path) -> Dict[str, Any]:
    files = list(root.rglob("*.py"))
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

if __name__ == "__main__":
    root = pathlib.Path(".")
    print(json.dumps(analyze_python_tree(root), indent=2))
