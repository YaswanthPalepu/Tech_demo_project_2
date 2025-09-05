import ast
from pathlib import Path
from typing import Dict, List, Any

def analyze_python_file(path: Path) -> Dict[str, Any]:
    info: Dict[str, Any] = {"path": str(path), "functions": [], "classes": [], "routes": []}
    try:
        src = path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                info["functions"].append(node.name)
                # crude FastAPI route detection via decorators names (at AST level this is limited)
                for deco in node.decorator_list:
                    attr = getattr(getattr(deco, "func", None), "attr", None)
                    if attr in {"get", "post", "put", "delete", "patch"}:
                        info["routes"].append(node.name)
            elif isinstance(node, ast.ClassDef):
                info["classes"].append(node.name)
        info["loc"] = len(src.splitlines())
        info["has_tests"] = "test" in path.stem.lower()
        info["source"] = src
    except Exception as e:
        info["error"] = str(e)
    return info

def summarize_repo(py_files: List[Path]) -> Dict[str, Any]:
    files = []
    total_loc = 0
    for p in py_files:
        an = analyze_python_file(p)
        total_loc += an.get("loc", 0)
        files.append(an)
    return {"total_files": len(py_files), "total_loc": total_loc, "files": files}
