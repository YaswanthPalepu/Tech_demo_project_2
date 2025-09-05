import ast
from pathlib import Path
from typing import Dict, List, Any

def analyze_python_file(path: Path) -> Dict[str, Any]:
    info: Dict[str, Any] = {"path": str(path), "functions": [], "classes": [], "imports": [], "has_tests": False}
    try:
        src = path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                info["functions"].append(node.name)
            elif isinstance(node, ast.ClassDef):
                info["classes"].append(node.name)
            elif isinstance(node, ast.Import):
                for n in node.names:
                    info["imports"].append(n.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    info["imports"].append(node.module.split(".")[0])
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
