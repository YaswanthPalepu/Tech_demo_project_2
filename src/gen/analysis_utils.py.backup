# src/gen/enhanced_analysis_utils.py - Drop-in replacement for analysis_utils.py

import os, re, math, pathlib, random, json, subprocess, sys, importlib.util
from typing import Dict, Any, List, Tuple, Optional, Set
from .env import norm_rel

# Enhanced package alias mapping (same as original)
COMMON_PKG_ALIASES = {
    # Web scraping and parsing
    "bs4": "beautifulsoup4", "yaml": "PyYAML", "cv2": "opencv-python",
    "sklearn": "scikit-learn", "PIL": "Pillow", "Crypto": "pycryptodome",
    # Database drivers
    "MySQLdb": "mysqlclient", "mysql": "mysqlclient",
    "psycopg2": "psycopg2-binary", "pymongo": "pymongo",
    # Cloud and networking
    "boto3": "boto3", "httpx": "httpx", "requests": "requests",
    # Web frameworks and ASGI/WSGI
    "uvicorn": "uvicorn", "fastapi": "fastapi", "starlette": "starlette",
    "pydantic": "pydantic", "typing_extensions": "typing-extensions",
    "annotated_types": "annotated-types", "sqlalchemy": "SQLAlchemy",
    "flask": "flask", "django": "Django", "werkzeug": "werkzeug",
    # CLI and utilities
    "click": "click", "typer": "typer", "jinja2": "Jinja2",
    "ujson": "ujson", "orjson": "orjson", "redis": "redis",
    # Testing and development
    "pytest": "pytest", "jwt": "PyJWT", "markupsafe": "MarkupSafe",
    # Django ecosystem
    "rest_framework": "djangorestframework",
    "django_filters": "django-filter",
    "rest_framework_simplejwt": "djangorestframework-simplejwt",
    "drf_yasg": "drf-yasg", "channels": "channels",
    # Configuration and environment
    "environs": "environs", "dotenv": "python-dotenv",
    "pydotenv": "python-dotenv", "decouple": "python-decouple",
    # Data processing
    "pandas": "pandas", "numpy": "numpy", "scipy": "scipy",
    "matplotlib": "matplotlib", "seaborn": "seaborn",
    # Async and concurrency
    "aiohttp": "aiohttp", "aiofiles": "aiofiles", "asyncpg": "asyncpg",
    # Serialization and validation
    "marshmallow": "marshmallow", "cerberus": "cerberus",
}

# Modules to avoid treating as third-party dependencies
DENY_GENERIC = {
    "models", "views", "urls", "settings", "config", "tests", "schemas",
    "forms", "admin", "migrations", "apps", "serializers", "permissions",
    "filters", "routers", "services", "repository", "helpers", "utils",
    "compat", "extensions", "renderers", "relations", "handlers", "middleware",
    "exceptions", "constants", "enums", "validators", "decorators"
}

DENY_TOPS = set(DENY_GENERIC) | {
    # Python built-ins and standard library essentials
    "__future__", "__main__", "builtins", "typing", "types", "dataclasses",
    "importlib", "asyncio", "json", "re", "os", "sys", "pathlib", "logging",
    "argparse", "functools", "itertools", "collections", "subprocess",
    "datetime", "time", "math", "decimal", "fractions", "statistics",
    "sqlite3", "http", "urllib", "hmac", "hashlib", "base64", "csv",
    "glob", "shutil", "tempfile", "inspect", "traceback", "enum",
    "textwrap", "pprint", "string", "threading", "multiprocessing",
    "concurrent", "queue", "socket", "ssl", "email", "mimetypes",
    "uuid", "pickle", "copy", "weakref", "gc", "operator", "keyword",
    "heapq", "bisect", "array", "struct", "codecs", "unicodedata",
    "locale", "calendar", "random", "secrets"
}

def _is_stdlib(top: str) -> bool:
    """Check if a module is part of Python standard library."""
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
        "multiprocessing", "gc"
    }
    return top in stdlib_modules

def _is_local(top: str) -> bool:
    """Check if a module appears to be local to the project."""
    target_root = os.environ.get("TARGET_ROOT")
    if target_root:
        target_path = pathlib.Path(target_root)
        if (target_path / f"{top}.py").exists() or (target_path / top).is_dir():
            return True
    
    project_roots = [".", "src", "backend", "app", "target", "lib"]
    for root in project_roots:
        root_path = pathlib.Path(root)
        if not root_path.exists():
            continue
        
        if (root_path / f"{top}.py").exists():
            return True
        
        if (root_path / top).is_dir():
            if (root_path / top / "__init__.py").exists():
                return True
    
    if pathlib.Path(top).exists() or pathlib.Path(top.replace(".", "/")).exists():
        return True
    
    return False

def dedupe_keep(items: List[Dict[str, str]], key: str, limit: int) -> List[Dict[str, str]]:
    """Deduplicate items by key and keep essential information."""
    seen = set()
    result = []
    
    for item in items or []:
        identifier = item.get(key)
        if not identifier or identifier in seen:
            continue
        
        seen.add(identifier)
        
        # Keep essential fields for test generation
        filtered_item = {}
        essential_fields = ["name", "file", "handler", "method", "path", "lineno", "end_lineno", "class"]
        for field in essential_fields:
            if field in item:
                filtered_item[field] = item[field]
        
        result.append(filtered_item)
        if len(result) >= limit:
            break
    
    return result

def compact_analysis(analysis: Dict[str, Any]) -> Dict[str, Any]:
    """Create compact analysis optimized for maximum test coverage."""
    
    total_functions = len(analysis.get("functions", []))
    total_classes = len(analysis.get("classes", []))
    total_routes = len(analysis.get("routes", []))
    
    # SIGNIFICANTLY INCREASED limits for maximum coverage
    if total_functions > 500:
        func_limit = 400  # Doubled from original 200
        class_limit = 200  # Doubled from original 100
        route_limit = 150  # Doubled from original 75
    elif total_functions > 200:
        func_limit = 300  # Doubled from original 150
        class_limit = 150  # Doubled from original 75
        route_limit = 120  # Doubled from original 60
    else:
        func_limit = 240  # Doubled from original 120
        class_limit = 120  # Doubled from original 60
        route_limit = 90   # Doubled from original 45
    
    # Sort by file for logical grouping
    functions = sorted(analysis.get("functions", []), key=lambda x: (x.get("file", ""), x.get("lineno", 0)))
    classes = sorted(analysis.get("classes", []), key=lambda x: (x.get("file", ""), x.get("lineno", 0)))
    routes = sorted(analysis.get("routes", []), key=lambda x: (x.get("file", ""), x.get("lineno", 0)))
    
    # Enhanced priority scoring for maximum coverage
    def priority_score(item):
        name = item.get("name") or item.get("handler", "")
        file_path = item.get("file", "")
        score = 0
        
        # HIGHER priority for public functions/classes (increased coverage targets)
        if not name.startswith("_"):
            score += 25  # Increased from 15
        
        # HIGHER priority for main modules
        if any(main_file in file_path for main_file in ["main.py", "app.py", "api.py", "views.py"]):
            score += 20  # Increased from 10
        
        # HIGHER priority for router/endpoint files
        if any(pattern in file_path for pattern in ["router", "endpoint", "api", "view", "controller"]):
            score += 15  # Increased from 7
        
        # HIGHER priority for model files (critical for coverage)
        if any(pattern in file_path for pattern in ["model", "schema", "serializer"]):
            score += 18  # Increased from 5
        
        # HIGHER priority for service/business logic files
        if any(pattern in file_path for pattern in ["service", "business", "logic", "manager"]):
            score += 12  # Increased from 4
        
        # Prioritize Django app files
        if any(pattern in file_path for pattern in ["apps/", "django"]):
            score += 15  # Increased from 6
        
        # Prioritize FastAPI/Flask route handlers
        if item.get("method") in ["get", "post", "put", "delete", "patch"]:
            score += 20  # Increased from 8
        
        # HIGHER priority for utility and helper functions (often missed in coverage)
        if any(pattern in file_path for pattern in ["util", "helper", "tool", "lib"]):
            score += 10
        
        # HIGHER priority for exception and error handling
        if any(pattern in name.lower() for pattern in ["error", "exception", "handle", "validate"]):
            score += 15
        
        # Lower priority for test files (shouldn't be many, but just in case)
        if "test" in file_path.lower():
            score -= 30  # Increased penalty
        
        # Lower priority for migration files
        if "migration" in file_path.lower():
            score -= 25  # Increased penalty
        
        return score
    
    # Sort by priority and take top items
    functions.sort(key=priority_score, reverse=True)
    classes.sort(key=priority_score, reverse=True)
    routes.sort(key=priority_score, reverse=True)
    
    return {
        "functions": dedupe_keep(functions, "name", func_limit),
        "classes": dedupe_keep(classes, "name", class_limit),
        "routes": dedupe_keep(routes, "handler", route_limit),
        "modules": sorted(set(analysis.get("modules", []))),
    }

def filter_by_files(analysis: Dict[str, Any], focus_files: Optional[Set[str]]) -> Tuple[Dict[str, Any], bool]:
    """Filter analysis to focus on specific files."""
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
    
    filtered = {
        "functions": [item for item in analysis.get("functions", []) if should_keep(item)],
        "classes": [item for item in analysis.get("classes", []) if should_keep(item)],
        "routes": [item for item in analysis.get("routes", []) if should_keep(item)],
        "modules": analysis.get("modules", [])  # Keep all modules for context
    }
    
    has_targets = any(filtered[key] for key in ["functions", "classes", "routes"])
    return (filtered, not has_targets)

# Enhanced coverage targeting for critical paths
def enhance_coverage_targeting(compact: Dict[str, Any]) -> Dict[str, Any]:
    """Enhance targeting to improve test coverage of critical paths."""
    
    # Identify critical coverage patterns with expanded list
    critical_patterns = {
        "django_views": ["views.py", "api.py", "viewsets.py"],
        "django_models": ["models.py", "model.py"],
        "django_serializers": ["serializers.py", "serializer.py"],
        "django_signals": ["signals.py", "signal.py"],
        "django_forms": ["forms.py", "form.py"],
        "django_admin": ["admin.py"],
        "django_managers": ["managers.py", "manager.py"],
        "fastapi_routes": ["main.py", "app.py", "router", "route"],
        "fastapi_dependencies": ["depend", "auth", "security"],
        "flask_routes": ["app.py", "routes.py", "blueprint"],
        "business_logic": ["service", "manager", "business", "logic"],
        "data_access": ["repository", "dao", "database"],
        "authentication": ["auth", "login", "permission", "security"],
        "validation": ["validator", "validate", "clean"],
        "utilities": ["util", "helper", "tool", "common"],
        "exceptions": ["exception", "error", "handler"],
    }
    
    # Score items based on coverage importance with higher weights
    def coverage_score(item):
        file_path = item.get("file", "").lower()
        name = item.get("name", "").lower()
        score = 0
        
        # MUCH higher priority for web framework entry points
        for pattern_name, patterns in critical_patterns.items():
            if any(pattern in file_path for pattern in patterns):
                if "django" in pattern_name:
                    score += 40  # Doubled from 20
                elif "fastapi" in pattern_name or "flask" in pattern_name:
                    score += 50  # Doubled from 25
                elif "business" in pattern_name:
                    score += 30  # Doubled from 15
                elif "authentication" in pattern_name:
                    score += 35
                elif "validation" in pattern_name:
                    score += 25
                elif "utilities" in pattern_name:
                    score += 20
                elif "exceptions" in pattern_name:
                    score += 30
        
        # Priority for public APIs
        if not name.startswith("_"):
            score += 20  # Doubled from 10
        
        # HIGHER priority for CRUD operations
        if any(crud in name for crud in ["create", "read", "update", "delete", "get", "post", "put", "patch", "save"]):
            score += 25  # More than doubled from 8
        
        # HIGHER priority for authentication/authorization
        if any(auth in name for auth in ["login", "auth", "permission", "token", "logout", "register"]):
            score += 30  # More than doubled from 12
        
        # Additional scoring for coverage-critical patterns
        if any(pattern in name for pattern in ["validate", "clean", "serialize", "deserialize"]):
            score += 20
            
        if any(pattern in name for pattern in ["__str__", "__repr__", "__eq__", "to_dict", "to_json"]):
            score += 15  # String representations and conversions
            
        if any(pattern in name for pattern in ["handle", "process", "execute", "run"]):
            score += 18  # Processing methods
        
        return score
    
    # Re-sort all targets by enhanced coverage importance
    for key in ["functions", "classes", "routes"]:
        if key in compact:
            compact[key].sort(key=coverage_score, reverse=True)
    
    return compact

# Enhanced heavy dependency detection (same as original but with additional coverage-focused dependencies)
HEAVY_DEPENDENCIES = {
    # GUI frameworks that often cause import issues in test environments
    "PyQt5": ("import PyQt5", "from PyQt5"),
    "PyQt6": ("import PyQt6", "from PyQt6"),
    "PySide2": ("import PySide2", "from PySide2"),
    "PySide6": ("import PySide6", "from PySide6"),
    "tkinter": ("import tkinter", "from tkinter"),
    "wx": ("import wx", "from wx"),
    # Computer vision and heavy ML libraries
    "cv2": ("import cv2", "from cv2"),
    "opencv": ("import opencv", "from opencv"),
    "tensorflow": ("import tensorflow", "from tensorflow"),
    "torch": ("import torch", "from torch"),
    "keras": ("import keras", "from keras"),
    # GPU/CUDA libraries
    "cupy": ("import cupy", "from cupy"),
    "numba": ("import numba", "from numba"),
    # Hardware interface libraries
    "serial": ("import serial", "from serial"),
    "gpio": ("import gpio", "from gpio"),
    "RPi": ("import RPi", "from RPi"),
    # Game development
    "pygame": ("import pygame", "from pygame"),
    "pyglet": ("import pyglet", "from pyglet"),
    # Scientific computing that might not be available
    "mayavi": ("import mayavi", "from mayavi"),
    "vtk": ("import vtk", "from vtk"),
}

def _is_dependency_available(module_name: str) -> bool:
    """Check if a module is available for import."""
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
    # Allow override for testing environments that have GUI libraries
    if os.getenv("TESTGEN_ENABLE_GUI_SHIMS", "0").lower() in ("1", "true", "yes"):
        return compact
    
    problematic_files = set()
    
    # Check each heavy dependency
    for module_name, import_patterns in HEAVY_DEPENDENCIES.items():
        if not _is_dependency_available(module_name):
            # Find files that import this unavailable module
            for collection in ["functions", "classes", "routes"]:
                for item in compact.get(collection, []):
                    file_path = item.get("file")
                    if file_path and _file_contains_patterns(file_path, import_patterns):
                        problematic_files.add(file_path)
    
    if not problematic_files:
        return compact
    
    print(f"Pruning {len(problematic_files)} files with unavailable dependencies")
    
    def is_file_usable(item):
        return item.get("file") not in problematic_files
    
    return {
        "functions": [item for item in compact.get("functions", []) if is_file_usable(item)],
        "classes": [item for item in compact.get("classes", []) if is_file_usable(item)],
        "routes": [item for item in compact.get("routes", []) if is_file_usable(item)],
        "modules": compact.get("modules", []),  # Keep modules list for context
    }

def infer_required_packages(compact: Dict[str, Any]) -> List[str]:
    """Infer required third-party packages from module analysis."""
    modules = compact.get("modules", [])
    required_packages = set()
    
    for module_name in modules:
        # Extract top-level module name
        top_module = module_name.split(".")[0].strip()
        
        # Skip if empty, private, or in deny lists
        if (not top_module or
            top_module.startswith("_") or
            top_module in DENY_TOPS or
            any(char.isupper() for char in top_module)):
            continue
        
        # Skip stdlib and local modules
        if _is_stdlib(top_module) or _is_local(top_module):
            continue
        
        # Map to package name using our alias dictionary
        package_name = COMMON_PKG_ALIASES.get(top_module, top_module)
        required_packages.add(package_name)
    
    # Sort for consistent output
    packages_list = sorted(required_packages, key=str.lower)
    
    # Add framework-specific dependencies
    enhanced_packages = enhance_framework_dependencies(packages_list)
    
    return enhanced_packages

def enhance_framework_dependencies(packages: List[str]) -> List[str]:
    """Add additional packages needed for specific frameworks."""
    enhanced = packages.copy()
    packages_lower = {pkg.lower() for pkg in packages}
    
    # FastAPI ecosystem
    if "fastapi" in packages_lower:
        fastapi_deps = ["starlette", "pydantic", "uvicorn"]
        for dep in fastapi_deps:
            if dep not in packages_lower:
                enhanced.append(dep)
    
    # Django ecosystem
    if "django" in packages_lower:
        django_deps = ["djangorestframework"]
        for dep in django_deps:
            if dep not in packages_lower and f"django{dep}" not in packages_lower:
                enhanced.append(dep)
    
    # SQLAlchemy with common drivers
    if "sqlalchemy" in packages_lower:
        db_drivers = []
        # Only add database drivers if they seem to be used
        if any("postgres" in pkg.lower() or "psycopg" in pkg.lower() for pkg in packages):
            db_drivers.append("psycopg2-binary")
        if any("mysql" in pkg.lower() for pkg in packages):
            db_drivers.append("mysqlclient")
        enhanced.extend(db_drivers)
    
    # Testing ecosystem - Enhanced for better coverage
    if "pytest" in packages_lower:
        test_deps = ["pytest-asyncio", "pytest-mock", "pytest-django", "pytest-cov"]
        for dep in test_deps:
            if dep not in packages_lower:
                enhanced.append(dep)
    
    return sorted(set(enhanced), key=str.lower)

def pip_install(packages: List[str]) -> None:
    """Install packages with robust error handling and constraints support."""
    if not packages:
        print("No third-party packages to install.")
        return
    
    # Get pip constraints if specified
    constraints_file = (os.getenv("TESTGEN_PIP_CONSTRAINTS") or
                       os.getenv("PIP_CONSTRAINT") or
                       os.getenv("CONSTRAINTS"))
    
    print(f"Installing packages (if needed): {', '.join(packages)}")
    
    successful_installs = []
    failed_installs = []
    
    for package in packages:
        if not package or not package.strip():
            continue
        
        # Build pip command
        cmd = [
            sys.executable, "-m", "pip", "install",
            "--disable-pip-version-check",
            "--no-input",
            "--upgrade-strategy", "only-if-needed",
            "--quiet"  # Reduce noise
        ]
        
        # Add constraints file if specified
        if constraints_file and os.path.exists(constraints_file):
            cmd.extend(["-c", constraints_file])
        
        cmd.append(package)
        
        try:
            subprocess.check_call(cmd,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.PIPE)
            successful_installs.append(package)
            print(f" ✓ {package}")
        except subprocess.CalledProcessError as e:
            error_output = e.stderr.decode() if e.stderr else "Unknown error"
            failed_installs.append((package, error_output))
            print(f" ✗ {package}: {error_output.split(chr(10))[0]}")  # First line of error
        except Exception as e:
            failed_installs.append((package, str(e)))
            print(f" ✗ {package}: {e}")
    
    # Summary
    if successful_installs:
        print(f"Successfully installed {len(successful_installs)} packages.")
    if failed_installs:
        print(f"Failed to install {len(failed_installs)} packages:")
        for package, error in failed_installs:
            print(f" - {package}: {error[:100]}...")  # Truncate long errors
        print("Tests will continue with available packages and intelligent mocking.")

def validate_analysis_quality(analysis: Dict[str, Any]) -> Tuple[bool, str]:
    """Validate that analysis contains sufficient data for test generation."""
    functions = analysis.get("functions", [])
    classes = analysis.get("classes", [])
    routes = analysis.get("routes", [])
    modules = analysis.get("modules", [])
    
    total_targets = len(functions) + len(classes) + len(routes)
    
    if total_targets == 0:
        return False, "No testable targets found (functions, classes, or routes)"
    
    if len(modules) == 0:
        return False, "No modules detected in analysis"
    
    # Check for reasonable file coverage
    files_with_targets = set()
    for item in functions + classes + routes:
        if item.get("file"):
            files_with_targets.add(item["file"])
    
    if len(files_with_targets) == 0:
        return False, "No files contain identifiable targets"
    
    # Warn about potential issues but don't fail
    warnings = []
    if total_targets < 5:
        warnings.append(f"Low target count ({total_targets}) - tests may be limited")
    
    if len(files_with_targets) == 1:
        warnings.append("All targets in single file - consider project structure")
    
    if len(routes) == 0 and any("fastapi" in str(m).lower() or "flask" in str(m).lower()
                               for m in modules):
        warnings.append("Web framework detected but no routes found")
    
    status_msg = f"Analysis valid: {total_targets} targets across {len(files_with_targets)} files"
    if warnings:
        status_msg += f". Warnings: {'; '.join(warnings)}"
    
    return True, status_msg