# src/analyzer.py - COMPLETE FINAL VERSION with comprehensive analysis
import argparse
import ast
import json
import os
import pathlib
from typing import Any, Dict, List, Set, Tuple

# Enhanced skip list - don't skip test directories to understand coverage gaps
SKIP_DIR_NAMES = {
    ".git", ".github", ".venv", "venv", "env", "node_modules", 
    "site-packages", "dist", "build", "__pycache__", ".mypy_cache",
    ".pytest_cache", ".tox", "htmlcov", ".eggs", "*.egg-info"
}

def read_text(p: pathlib.Path) -> str:
    """Safely read file content."""
    return p.read_text(encoding="utf-8", errors="ignore")

def _should_skip(p: pathlib.Path, root: pathlib.Path) -> bool:
    """Check if path should be skipped during analysis."""
    try:
        rel = p.relative_to(root)
    except Exception:
        return False
    
    # Skip generated test directory to avoid circular analysis
    if "tests/generated" in str(rel):
        return True
    
    # Check each part of the path
    for part in rel.parts:
        if part in SKIP_DIR_NAMES:
            return True
        # Skip hidden directories
        if part.startswith('.') and part not in {'.', '..'}:
            return True
    
    return False

def _extract_route_info(dec) -> Dict[str, Any]:
    """Extract route information from decorator (FastAPI/Flask style)."""
    info = {}
    try:
        # Handle @router.get("/path") style
        func = getattr(dec, "func", None)
        if func:
            attr = getattr(func, "attr", None)
            if attr in {"get", "post", "put", "patch", "delete", "options", "head"}:
                info["method"] = attr
                
                # Extract path from first argument
                if hasattr(dec, "args") and dec.args:
                    arg0 = dec.args[0]
                    if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
                        info["path"] = arg0.value
        
        # Handle @app.route("/path") style (Flask)
        if isinstance(func, ast.Attribute):
            if func.attr in {"route", "as_view"}:
                info["is_view"] = True
                if hasattr(dec, "args") and dec.args:
                    arg0 = dec.args[0]
                    if isinstance(arg0, ast.Constant):
                        info["path"] = arg0.value
                        
    except Exception:
        pass
    return info

def _analyze_class_methods(cls_node: ast.ClassDef, file_path: str) -> List[Dict[str, Any]]:
    """Extract all methods from a class including properties and special methods."""
    methods = []
    
    for item in cls_node.body:
        if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
            
        method_info = {
            "name": item.name,
            "class": cls_node.name,
            "file": file_path,
            "lineno": getattr(item, "lineno", 1),
            "end_lineno": getattr(item, "end_lineno", getattr(item, "lineno", 1)),
            "is_async": isinstance(item, ast.AsyncFunctionDef),
            "is_property": False,
            "is_classmethod": False,
            "is_staticmethod": False,
            "is_special": item.name.startswith("__") and item.name.endswith("__"),
        }
        
        # Check decorators
        for dec in getattr(item, "decorator_list", []):
            if isinstance(dec, ast.Name):
                if dec.id == "property":
                    method_info["is_property"] = True
                elif dec.id == "classmethod":
                    method_info["is_classmethod"] = True
                elif dec.id == "staticmethod":
                    method_info["is_staticmethod"] = True
        
        methods.append(method_info)
    
    return methods

def _detect_django_patterns(tree: ast.AST, file_path: str) -> Dict[str, List[Dict[str, Any]]]:
    """Detect Django-specific patterns: models, serializers, views, viewsets, forms."""
    patterns = {
        "models": [],
        "serializers": [],
        "views": [],
        "viewsets": [],
        "forms": [],
    }
    
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
            
        # Extract base class names
        bases = []
        for b in node.bases:
            if isinstance(b, ast.Name):
                bases.append(b.id)
            elif isinstance(b, ast.Attribute):
                bases.append(getattr(b, 'attr', ''))
        
        base_str = ' '.join(bases).lower()
        
        # Django Models
        if any("model" in b.lower() for b in bases) and "serializer" not in base_str:
            patterns["models"].append({
                "name": node.name,
                "file": file_path,
                "lineno": getattr(node, "lineno", 1),
                "type": "django_model",
                "bases": bases
            })
        
        # DRF Serializers
        if any("serializer" in b.lower() for b in bases):
            patterns["serializers"].append({
                "name": node.name,
                "file": file_path,
                "lineno": getattr(node, "lineno", 1),
                "type": "serializer",
                "bases": bases
            })
        
        # DRF ViewSets
        if any("viewset" in b.lower() for b in bases):
            patterns["viewsets"].append({
                "name": node.name,
                "file": file_path,
                "lineno": getattr(node, "lineno", 1),
                "type": "viewset",
                "bases": bases
            })
        
        # Django/DRF Views (but not viewsets)
        if any("view" in b.lower() or "apiview" in b.lower() for b in bases) and "viewset" not in base_str:
            patterns["views"].append({
                "name": node.name,
                "file": file_path,
                "lineno": getattr(node, "lineno", 1),
                "type": "view",
                "bases": bases
            })
        
        # Django Forms
        if any("form" in b.lower() for b in bases) and "serializer" not in base_str:
            patterns["forms"].append({
                "name": node.name,
                "file": file_path,
                "lineno": getattr(node, "lineno", 1),
                "type": "form",
                "bases": bases
            })
    
    return patterns

def analyze_python_tree(root: pathlib.Path) -> Dict[str, Any]:
    """
    Comprehensive analysis of Python codebase for maximum test coverage.
    
    Returns detailed information about:
    - Functions (top-level)
    - Classes
    - Methods (inside classes) - NEW
    - Routes (API endpoints)
    - Django patterns (models, serializers, etc.) - NEW
    - Properties - NEW
    - Async functions - NEW
    """
    files: List[pathlib.Path] = [
        p for p in root.rglob("*.py") 
        if p.is_file() and not _should_skip(p, root)
    ]
    
    print(f"Analyzing {len(files)} Python files...")
    
    out = {
        "functions": [],
        "classes": [],
        "methods": [],          # NEW: Track methods separately
        "routes": [],
        "modules": [],
        "django_patterns": {    # NEW: Django-specific patterns
            "models": [],
            "serializers": [],
            "views": [],
            "viewsets": [],
            "forms": [],
        },
        "properties": [],       # NEW: Property methods
        "async_functions": [],  # NEW: Async functions
        "files_analyzed": [],   # NEW: Track analyzed files
    }
    
    for f in files:
        rel_path = str(f.relative_to(root))
        out["files_analyzed"].append(rel_path)
        
        try:
            code = read_text(f)
            tree = ast.parse(code)
        except Exception as e:
            print(f"Warning: Failed to parse {rel_path}: {e}")
            continue
        
        # Detect Django patterns first
        django_patterns = _detect_django_patterns(tree, rel_path)
        for pattern_type, items in django_patterns.items():
            out["django_patterns"][pattern_type].extend(items)
        
        # Walk AST for all nodes
        for node in ast.walk(tree):
            # Functions and async functions
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_rec = {
                    "name": node.name,
                    "file": rel_path,
                    "lineno": getattr(node, "lineno", 1),
                    "end_lineno": getattr(node, "end_lineno", getattr(node, "lineno", 1)),
                    "is_async": isinstance(node, ast.AsyncFunctionDef),
                }
                
                out["functions"].append(func_rec)
                
                # Track async functions separately
                if isinstance(node, ast.AsyncFunctionDef):
                    out["async_functions"].append(func_rec.copy())
                
                # Check for route decorators
                for d in getattr(node, "decorator_list", []):
                    route_info = _extract_route_info(d)
                    if route_info:
                        out["routes"].append({
                            "handler": node.name,
                            "file": rel_path,
                            "method": route_info.get("method"),
                            "path": route_info.get("path"),
                            "lineno": func_rec["lineno"],
                            "end_lineno": func_rec["end_lineno"],
                        })
                    
                    # Check for property decorator
                    if isinstance(d, ast.Name) and d.id == "property":
                        out["properties"].append(func_rec.copy())
            
            # Classes
            elif isinstance(node, ast.ClassDef):
                class_rec = {
                    "name": node.name,
                    "file": rel_path,
                    "lineno": getattr(node, "lineno", 1),
                    "end_lineno": getattr(node, "end_lineno", getattr(node, "lineno", 1)),
                    "bases": [
                        b.id if isinstance(b, ast.Name) else 
                        getattr(b, 'attr', str(b)) 
                        for b in node.bases
                    ],
                }
                out["classes"].append(class_rec)
                
                # Extract all methods from the class
                methods = _analyze_class_methods(node, rel_path)
                out["methods"].extend(methods)
            
            # Import statements
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                if isinstance(node, ast.Import):
                    out["modules"].extend([a.name for a in node.names])
                elif node.module:
                    out["modules"].append(node.module)
    
    # Deduplicate modules
    out["modules"] = sorted(set(out["modules"]))
    
    # Print summary
    print(f"\nAnalysis Complete:")
    print(f"  Files analyzed: {len(out['files_analyzed'])}")
    print(f"  Functions: {len(out['functions'])}")
    print(f"  Classes: {len(out['classes'])}")
    print(f"  Methods: {len(out['methods'])}")
    print(f"  Routes: {len(out['routes'])}")
    print(f"  Properties: {len(out['properties'])}")
    print(f"  Async functions: {len(out['async_functions'])}")
    print(f"  Django models: {len(out['django_patterns']['models'])}")
    print(f"  Serializers: {len(out['django_patterns']['serializers'])}")
    print(f"  Views/ViewSets: {len(out['django_patterns']['views']) + len(out['django_patterns']['viewsets'])}")
    
    return out

def main():
    ap = argparse.ArgumentParser(
        description="Comprehensive Python code analyzer for test generation"
    )
    ap.add_argument(
        "--root", 
        default=os.getenv("ANALYZE_ROOT", "."), 
        help="root directory to analyze (default: current directory)"
    )
    ap.add_argument(
        "--output",
        help="output JSON file (default: print to stdout)"
    )
    ap.add_argument(
        "--summary-only",
        action="store_true",
        help="only print summary statistics"
    )
    
    args = ap.parse_args()
    root = pathlib.Path(args.root)
    
    if not root.exists():
        print(f"Error: Directory does not exist: {root}")
        return 1
    
    analysis = analyze_python_tree(root)
    
    if args.summary_only:
        return 0
    
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(analysis, f, indent=2)
        print(f"\nAnalysis saved to: {args.output}")
    else:
        print(json.dumps(analysis, indent=2))
    
    return 0

if __name__ == "__main__":
    exit(main())