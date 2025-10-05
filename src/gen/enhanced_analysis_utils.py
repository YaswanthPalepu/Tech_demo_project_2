# src/gen/enhanced_analysis_utils.py - ULTIMATE VERSION - NO PRIORITY SCORES
import importlib.util
import json
import os
import pathlib
import random
import re
import subprocess
import sys
from typing import Any, Dict, List, Optional, Set, Tuple

from .env import norm_rel

COMMON_PKG_ALIASES = {
    "bs4": "beautifulsoup4", "yaml": "PyYAML", "cv2": "opencv-python",
    "sklearn": "scikit-learn", "PIL": "Pillow", "Crypto": "pycryptodome",
    "MySQLdb": "mysqlclient", "mysql": "mysqlclient", "mysqlconnector": "mysql-connector-python",
    "psycopg2": "psycopg2-binary", "pymongo": "pymongo", "redis": "redis",
    "boto3": "boto3", "botocore": "botocore", "httpx": "httpx", "requests": "requests",
    "uvicorn": "uvicorn", "fastapi": "fastapi", "starlette": "starlette",
    "pydantic": "pydantic", "typing_extensions": "typing-extensions",
    "annotated_types": "annotated-types", "sqlalchemy": "SQLAlchemy",
    "flask": "flask", "django": "Django", "werkzeug": "werkzeug",
    "click": "click", "typer": "typer", "jinja2": "Jinja2",
    "ujson": "ujson", "orjson": "orjson", 
    "pytest": "pytest", "jwt": "PyJWT", "markupsafe": "MarkupSafe",
    "rest_framework": "djangorestframework", "drf": "djangorestframework",
    "django_filters": "django-filter", "djangofilters": "django-filter",
    "rest_framework_simplejwt": "djangorestframework-simplejwt",
    "drf_yasg": "drf-yasg", "channels": "channels", "celery": "celery",
    "environs": "environs", "dotenv": "python-dotenv", "env": "python-dotenv",
    "pydotenv": "python-dotenv", "decouple": "python-decouple",
    "pandas": "pandas", "numpy": "numpy", "scipy": "scipy",
    "matplotlib": "matplotlib", "seaborn": "seaborn", "plotly": "plotly",
    "aiohttp": "aiohttp", "aiofiles": "aiofiles", "asyncpg": "asyncpg",
    "marshmallow": "marshmallow", "cerberus": "cerberus", "pydantic": "pydantic",
    "alembic": "alembic", "gunicorn": "gunicorn", "uvloop": "uvloop",
    "websockets": "websockets", "graphql": "graphene", "graphene": "graphene",
}

# REDUCED deny lists - only truly generic names
DENY_GENERIC = {
    "tests", "migrations", "__pycache__"
}

DENY_TOPS = set(DENY_GENERIC) | {
    "__future__", "__main__", "builtins", "typing", "types", "dataclasses",
}

def _is_stdlib(top: str) -> bool:
    """Check if a module is part of Python standard library - EXPANDED."""
    if hasattr(sys, "stdlib_module_names"):
        return top in sys.stdlib_module_names
    
    stdlib_modules = {
        "os", "sys", "re", "json", "pathlib", "math", "itertools",
        "functools", "typing", "subprocess", "datetime", "time",
        "collections", "dataclasses", "ast", "logging", "unittest",
        "argparse", "asyncio", "threading", "sqlite3", "email",
        "http", "urllib", "hashlib", "hmac", "base64", "statistics",
        "random", "fractions", "decimal", "csv", "shutil", "tempfile",
        "glob", "inspect", "traceback", "textwrap", "string", "pprint",
        "enum", "types", "weakref", "copy", "pickle", "operator",
        "keyword", "heapq", "bisect", "array", "struct", "codecs",
        "unicodedata", "locale", "calendar", "secrets", "uuid",
        "mimetypes", "socket", "ssl", "concurrent", "queue",
        "multiprocessing", "gc", "contextlib", "abc", "io",
        "selectors", "signal", "threading", "multiprocessing",
    }
    return top in stdlib_modules

def _is_local(top: str) -> bool:
    """Check if a module appears to be local to the project - ENHANCED detection."""
    target_root = os.environ.get("TARGET_ROOT")
    if target_root:
        target_path = pathlib.Path(target_root)
        
        # Check for direct Python file
        if (target_path / f"{top}.py").exists():
            return True
        
        # Check for package directory
        if (target_path / top).is_dir():
            init_file = target_path / top / "__init__.py"
            if init_file.exists():
                return True
        
        # Check for nested modules
        if "." in top:
            module_path = target_path / top.replace(".", "/")
            if module_path.exists():
                return True
            if (module_path.parent / f"{module_path.name}.py").exists():
                return True
    
    # Check common project structures
    project_roots = [".", "src", "backend", "app", "target", "lib", "project"]
    for root in project_roots:
        root_path = pathlib.Path(root)
        if not root_path.exists():
            continue
        
        # Check for Python file
        if (root_path / f"{top}.py").exists():
            return True
        
        # Check for package
        if (root_path / top).is_dir():
            if (root_path / top / "__init__.py").exists():
                return True
    
    # Check if path exists directly
    if pathlib.Path(top).exists():
        return True
    
    # Check for dotted path
    if "." in top:
        dotted_path = top.replace(".", "/")
        if pathlib.Path(dotted_path).exists():
            return True
        if pathlib.Path(f"{dotted_path}.py").exists():
            return True
    
    return False

def compact_analysis(analysis: Dict[str, Any]) -> Dict[str, Any]:
    """Create analysis with ALL targets - NO LIMITS, NO PRIORITY SCORES."""
    
    # Get ALL targets without any filtering
    functions = analysis.get("functions", [])
    classes = analysis.get("classes", [])
    methods = analysis.get("methods", [])
    routes = analysis.get("routes", [])
    nested_functions = analysis.get("nested_functions", [])
    fastapi_routes = analysis.get("fastapi_routes", [])
    
    # Include nested functions in functions list for testing
    all_functions = functions + nested_functions
    all_routes = routes + fastapi_routes
    
    # Sort by file and line number for logical organization
    all_functions = sorted(all_functions, key=lambda x: (x.get("file", ""), x.get("lineno", 0)))
    classes = sorted(classes, key=lambda x: (x.get("file", ""), x.get("lineno", 0)))
    methods = sorted(methods, key=lambda x: (x.get("file", ""), x.get("lineno", 0)))
    all_routes = sorted(all_routes, key=lambda x: (x.get("file", ""), x.get("lineno", 0)))
    
    print(f"🎯 INCLUDING ALL TARGETS WITHOUT LIMITS:")
    print(f"   📊 Functions: {len(all_functions)} (including {len(nested_functions)} nested)")
    print(f"   🏗️  Classes: {len(classes)}")
    print(f"   🔧 Methods: {len(methods)}")
    print(f"   🌐 Routes: {len(all_routes)}")
    print(f"   ⚡ FastAPI Routes: {len(fastapi_routes)}")
    print(f"   📈 Total testable targets: {len(all_functions) + len(classes) + len(methods) + len(all_routes)}")
    
    return {
        "functions": all_functions,  # ALL functions including nested
        "classes": classes,          # ALL classes
        "methods": methods,          # ALL methods
        "routes": all_routes,        # ALL routes
        "modules": sorted(set(analysis.get("modules", []))),
        "django_patterns": analysis.get("django_patterns", {}),
        "imports": analysis.get("imports", []),  # Include import analysis
    }

def filter_by_files(analysis: Dict[str, Any], focus_files: Optional[Set[str]]) -> Tuple[Dict[str, Any], bool]:
    """Filter analysis to focus on specific files - ENHANCED with import tracking."""
    if not focus_files:
        return analysis, False
    
    focus_normalized = {norm_rel(f) for f in focus_files}
    focus_basenames = {pathlib.Path(f).name for f in focus_normalized}
    
    def should_keep(entry):
        file_path = norm_rel(entry.get("file") or "")
        file_basename = pathlib.Path(file_path).name
        return (file_path in focus_normalized or
                file_basename in focus_basenames or
                any(focus in file_path for focus in focus_normalized))
    
    # Also track imports from focus files
    focus_imports = []
    for imp in analysis.get("imports", []):
        if should_keep(imp):
            focus_imports.append(imp)
    
    filtered = {
        "functions": [item for item in analysis.get("functions", []) if should_keep(item)],
        "classes": [item for item in analysis.get("classes", []) if should_keep(item)],
        "methods": [item for item in analysis.get("methods", []) if should_keep(item)],
        "routes": [item for item in analysis.get("routes", []) if should_keep(item)],
        "modules": analysis.get("modules", []),
        "django_patterns": analysis.get("django_patterns", {}),
        "imports": focus_imports,
    }
    
    has_targets = any(filtered[key] for key in ["functions", "classes", "methods", "routes"])
    return (filtered, not has_targets)

def enhance_coverage_targeting(compact: Dict[str, Any]) -> Dict[str, Any]:
    """NO PRIORITY SCORING - Return targets as-is for maximum coverage."""
    print("🎯 Using ALL targets without priority scoring for 100% coverage")
    return compact

# EXPANDED heavy dependencies list
HEAVY_DEPENDENCIES = {
    "PyQt5": ("import PyQt5", "from PyQt5"),
    "PyQt6": ("import PyQt6", "from PyQt6"),
    "PySide2": ("import PySide2", "from PySide2"),
    "PySide6": ("import PySide6", "from PySide6"),
    "tkinter": ("import tkinter", "from tkinter"),
    "wx": ("import wx", "from wx"),
    "cv2": ("import cv2", "from cv2"),
    "opencv": ("import opencv", "from opencv"),
    "tensorflow": ("import tensorflow", "from tensorflow"),
    "torch": ("import torch", "from torch"),
    "keras": ("import keras", "from keras"),
    "cupy": ("import cupy", "from cupy"),
    "numba": ("import numba", "from numba"),
    "serial": ("import serial", "from serial"),
    "gpio": ("import gpio", "from gpio"),
    "RPi": ("import RPi", "from RPi"),
    "pygame": ("import pygame", "from pygame"),
    "pyglet": ("import pyglet", "from pyglet"),
    "mayavi": ("import mayavi", "from mayavi"),
    "vtk": ("import vtk", "from vtk"),
    "pyspark": ("import pyspark", "from pyspark"),
    "dask": ("import dask", "from dask"),
    "jax": ("import jax", "from jax"),
}

def _is_dependency_available(module_name: str) -> bool:
    """Check if a module is available for import - ENHANCED detection."""
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False

def _file_contains_patterns(file_path: str, patterns: Tuple[str, ...]) -> bool:
    """Check if a file contains any of the specified import patterns."""
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        return any(pattern in content for pattern in patterns)
    except (OSError, IOError):
        return False

def prune_unavailable_targets(compact: Dict[str, Any]) -> Dict[str, Any]:
    """Remove targets that depend on unavailable heavy dependencies."""
    if os.getenv("TESTGEN_ENABLE_GUI_SHIMS", "0").lower() in ("1", "true", "yes"):
        return compact
    
    problematic_files = set()
    
    for module_name, import_patterns in HEAVY_DEPENDENCIES.items():
        if not _is_dependency_available(module_name):
            for collection in ["functions", "classes", "methods", "routes"]:
                for item in compact.get(collection, []):
                    file_path = item.get("file")
                    if file_path and _file_contains_patterns(file_path, import_patterns):
                        problematic_files.add(file_path)
    
    if not problematic_files:
        return compact
    
    print(f"⚠️ Pruning {len(problematic_files)} files with unavailable dependencies")
    
    def is_file_usable(item):
        return item.get("file") not in problematic_files
    
    return {
        "functions": [item for item in compact.get("functions", []) if is_file_usable(item)],
        "classes": [item for item in compact.get("classes", []) if is_file_usable(item)],
        "methods": [item for item in compact.get("methods", []) if is_file_usable(item)],
        "routes": [item for item in compact.get("routes", []) if is_file_usable(item)],
        "modules": compact.get("modules", []),
        "django_patterns": compact.get("django_patterns", {}),
        "imports": compact.get("imports", []),
    }

def infer_required_packages(compact: Dict[str, Any]) -> List[str]:
    """Infer required third-party packages from module analysis - ENHANCED detection."""
    modules = compact.get("modules", [])
    imports = compact.get("imports", [])
    required_packages = set()
    
    # Analyze both modules and individual imports
    all_imports = set(modules)
    for imp in imports:
        if imp.get("type") == "import":
            all_imports.update(imp.get("modules", []))
        elif imp.get("type") == "import_from":
            if imp.get("module"):
                all_imports.add(imp["module"])
    
    for module_name in all_imports:
        if not module_name or module_name.startswith('_'):
            continue
            
        top_module = module_name.split(".")[0].strip()
        
        if (not top_module or
            top_module in DENY_TOPS or
            any(char.isupper() for char in top_module)):
            continue
        
        if _is_stdlib(top_module) or _is_local(top_module):
            continue
        
        package_name = COMMON_PKG_ALIASES.get(top_module, top_module)
        required_packages.add(package_name)
    
    packages_list = sorted(required_packages, key=str.lower)
    enhanced_packages = enhance_framework_dependencies(packages_list)
    
    print(f"📦 Inferred {len(enhanced_packages)} required packages: {', '.join(enhanced_packages)}")
    return enhanced_packages

def enhance_framework_dependencies(packages: List[str]) -> List[str]:
    """Add additional packages needed for specific frameworks - ENHANCED."""
    enhanced = packages.copy()
    packages_lower = {pkg.lower() for pkg in packages}
    
    # FastAPI ecosystem
    if "fastapi" in packages_lower:
        fastapi_deps = ["starlette", "pydantic", "uvicorn", "httpx"]
        for dep in fastapi_deps:
            if dep not in packages_lower:
                enhanced.append(dep)
    
    # Django ecosystem
    if "django" in packages_lower:
        django_deps = ["djangorestframework", "django-filter", "django-cors-headers"]
        for dep in django_deps:
            if dep not in packages_lower and f"django{dep}" not in packages_lower:
                enhanced.append(dep)
    
    # SQLAlchemy database drivers
    if "sqlalchemy" in packages_lower:
        db_drivers = []
        if any("postgres" in pkg.lower() or "psycopg" in pkg.lower() for pkg in packages):
            db_drivers.append("psycopg2-binary")
        if any("mysql" in pkg.lower() for pkg in packages):
            db_drivers.append("mysqlclient")
        if any("sqlite" in pkg.lower() for pkg in packages):
            pass  # Built-in
        enhanced.extend(db_drivers)
    
    # Testing ecosystem
    if "pytest" in packages_lower:
        test_deps = ["pytest-asyncio", "pytest-mock", "pytest-django", "pytest-cov"]
        for dep in test_deps:
            if dep not in packages_lower:
                enhanced.append(dep)
    
    # Web framework common dependencies
    if any(fw in packages_lower for fw in ["flask", "fastapi", "django"]):
        web_deps = ["requests", "httpx"]
        for dep in web_deps:
            if dep not in packages_lower:
                enhanced.append(dep)
    
    return sorted(set(enhanced), key=str.lower)

def pip_install(packages: List[str]) -> None:
    """Install packages with robust error handling - ENHANCED with better reporting."""
    if not packages:
        print("ℹ️ No third-party packages to install.")
        return
    
    constraints_file = (os.getenv("TESTGEN_PIP_CONSTRAINTS") or
                       os.getenv("PIP_CONSTRAINT") or
                       os.getenv("CONSTRAINTS"))
    
    print(f"📦 Installing packages for real code execution: {', '.join(packages)}")
    
    successful_installs = []
    failed_installs = []
    
    for package in packages:
        if not package or not package.strip():
            continue
        
        cmd = [
            sys.executable, "-m", "pip", "install",
            "--disable-pip-version-check",
            "--no-input",
            "--upgrade-strategy", "only-if-needed",
            "--quiet"
        ]
        
        if constraints_file and os.path.exists(constraints_file):
            cmd.extend(["-c", constraints_file])
        
        cmd.append(package)
        
        try:
            subprocess.check_call(cmd,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE)
            successful_installs.append(package)
            print(f"   ✅ {package}")
        except subprocess.CalledProcessError as e:
            error_output = e.stderr.decode() if e.stderr else "Unknown error"
            failed_installs.append((package, error_output))
            print(f"   ❌ {package}: {error_output.split(chr(10))[0]}")
        except Exception as e:
            failed_installs.append((package, str(e)))
            print(f"   ❌ {package}: {e}")
    
    if successful_installs:
        print(f"✅ Successfully installed {len(successful_installs)} packages.")
    if failed_installs:
        print(f"⚠️ Failed to install {len(failed_installs)} packages (tests will use available packages):")
        for package, error in failed_installs:
            print(f"   - {package}: {error[:100]}...")

def validate_analysis_quality(analysis: Dict[str, Any]) -> Tuple[bool, str]:
    """Validate that analysis contains sufficient data for test generation - ENHANCED."""
    functions = analysis.get("functions", [])
    classes = analysis.get("classes", [])
    methods = analysis.get("methods", [])
    routes = analysis.get("routes", [])
    modules = analysis.get("modules", [])
    
    total_targets = len(functions) + len(classes) + len(methods) + len(routes)
    
    if total_targets == 0:
        return False, "❌ No testable targets found (functions, classes, methods, or routes)"
    
    if len(modules) == 0:
        return False, "❌ No modules detected in analysis"
    
    files_with_targets = set()
    for item in functions + classes + methods + routes:
        if item.get("file"):
            files_with_targets.add(item["file"])
    
    if len(files_with_targets) == 0:
        return False, "❌ No files contain identifiable targets"
    
    warnings = []
    if total_targets < 10:
        warnings.append(f"Low target count ({total_targets}) - ensure comprehensive code analysis")
    
    if len(files_with_targets) == 1:
        warnings.append("All targets in single file - verify project structure analysis")
    
    # Enhanced framework detection warnings
    has_web_framework = any(fw in str(modules).lower() for fw in ["flask", "fastapi", "django", "starlette"])
    if has_web_framework and len(routes) == 0:
        warnings.append("Web framework detected but no routes found - check route detection")
    
    has_django = any("django" in str(m).lower() for m in modules)
    if has_django and len(analysis.get("django_patterns", {}).get("models", [])) == 0:
        warnings.append("Django detected but no models found - check model detection")
    
    status_msg = f"✅ Analysis valid: {total_targets} targets across {len(files_with_targets)} files"
    if warnings:
        status_msg += f". Warnings: {'; '.join(warnings)}"
    
    return True, status_msg