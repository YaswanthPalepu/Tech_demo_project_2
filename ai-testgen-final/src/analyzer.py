import ast
from pathlib import Path
from typing import Dict, List, Any

WEB_METHODS = {"get","post","put","delete","patch"}

def _fn_info(node: ast.FunctionDef) -> Dict[str, Any]:
    args = node.args
    total = len(args.args or []) + len(args.posonlyargs or [])
    defaults = len(args.defaults or [])
    required = max(total - defaults, 0)
    returns = any(isinstance(n, ast.Return) for n in ast.walk(node))
    doc = (ast.get_docstring(node) or "")[:400]
    return {"name": node.name, "required_args": required, "total_args": total, "has_returns": returns, "doc": doc}

def analyze_python_file(path: Path) -> Dict[str, Any]:
    info: Dict[str, Any] = {
        "path": str(path),
        "module": ".".join(path.with_suffix("").parts),
        "functions": [], "classes": [], "routes": [],
        "cli": {"click": False, "typer_app": None, "argparse": False},
    }
    try:
        src = path.read_text(encoding="utf-8", errors="ignore")
        info["source_snippet"] = src[:8000]
        tree = ast.parse(src)

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                info["classes"].append(node.name)
            elif isinstance(node, ast.FunctionDef):
                info["functions"].append(_fn_info(node))

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                for deco in node.decorator_list:
                    if isinstance(deco, ast.Call) and isinstance(deco.func, ast.Attribute):
                        verb = deco.func.attr.lower()
                        if verb in WEB_METHODS:
                            path_arg = None
                            if deco.args and isinstance(deco.args[0], (ast.Constant, ast.Str)):
                                path_arg = getattr(deco.args[0], "value", None)
                            info["routes"].append({"name": node.name, "method": verb, "path": path_arg or ""})
                    if isinstance(deco, ast.Call) and isinstance(deco.func, ast.Attribute):
                        if deco.func.attr == "route":
                            p = None
                            if deco.args and isinstance(deco.args[0], (ast.Constant, ast.Str)):
                                p = getattr(deco.args[0], "value", None)
                            info["routes"].append({"name": node.name, "method": "get", "path": p or ""})

        info["cli"]["click"] = ("import click" in src) or ("from click" in src)
        info["cli"]["typer_app"] = None
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                try:
                    func = node.value.func
                    if isinstance(func, ast.Attribute) and getattr(func.value, "id", "") == "typer" and func.attr == "Typer":
                        if node.targets and hasattr(node.targets[0], "id"):
                            info["cli"]["typer_app"] = node.targets[0].id
                except Exception:
                    pass
        info["cli"]["argparse"] = "argparse" in src

        info["loc"] = len(src.splitlines())
        info["has_tests"] = "test" in path.stem.lower()
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
    routes = []
    for f in files:
        for r in f.get("routes", []):
            routes.append({"module": f.get("module"), **r})
    return {"total_files": len(py_files), "total_loc": total_loc, "files": files, "routes": routes[:500]}
