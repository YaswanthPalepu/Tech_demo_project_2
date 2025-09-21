# src/gen/analysis_utils.py
import os, re, math, pathlib, random, json, subprocess, sys, importlib.util
from typing import Dict, Any, List, Tuple, Optional, Set
from .env import norm_rel

# Enhanced package alias mapping for better dependency detection
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
    # Use Python 3.10+ stdlib_module_names if available
    if hasattr(sys, "stdlib_module_names"):
        return top in sys.stdlib_module_names
    
    # Fallback comprehensive list for older Python versions
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
    # Check for explicit target root
    target_root = os.environ.get("TARGET_ROOT")
    if target_root:
        target_path = pathlib.Path(target_root)
        if (target_path / f"{top}.py").exists() or (target_path / top).is_dir():
            return True
    
    # Check common project structure patterns
    project_roots = [".", "src", "backend", "app", "target", "lib"]
    
    for root in project_roots:
        root_path = pathlib.Path(root)
        if not root_path.exists():
            continue
            
        # Check for module file or directory
        if (root_path / f"{top}.py").exists():
            return True
        if (root_path / top).is_dir():
            # Verify it's a Python package
            if (root_path / top / "__init__.py").exists():
                return True
    
    # Check if it exists as a relative path
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
    """Create compact analysis optimized for test generation with better coverage targeting."""
    
    # Calculate dynamic limits based on codebase size with increased coverage focus
    total_functions = len(analysis.get("functions", []))
    total_classes = len(analysis.get("classes", []))
    total_routes = len(analysis.get("routes", []))
    
    # Scale limits based on codebase complexity - increased limits for better coverage
    if total_functions > 500:
        func_limit = 200  # Increased from 150
        class_limit = 100  # Increased from 75
        route_limit = 75   # Increased from 50
    elif total_functions > 200:
        func_limit = 150  # Increased from 100
        class_limit = 75  # Increased from 50
        route_limit = 60  # Increased from 40
    else:
        func_limit = 120  # Increased from 80
        class_limit = 60  # Increased from 40
        route_limit = 45  # Increased from 30
    
    # Sort by file for logical grouping
    functions = sorted(analysis.get("functions", []), key=lambda x: (x.get("file", ""), x.get("lineno", 0)))
    classes = sorted(analysis.get("classes", []), key=lambda x: (x.get("file", ""), x.get("lineno", 0)))
    routes = sorted(analysis.get("routes", []), key=lambda x: (x.get("file", ""), x.get("lineno", 0)))
    
    # Enhanced priority scoring for better test coverage
    def priority_score(item):
        name = item.get("name") or item.get("handler", "")
        file_path = item.get("file", "")
        
        score = 0
        
        # Higher priority for public functions/classes
        if not name.startswith("_"):
            score += 15  # Increased from 10
        
        # Higher priority for main modules
        if any(main_file in file_path for main_file in ["main.py", "app.py", "api.py", "views.py"]):
            score += 10  # Increased from 5
        
        # Higher priority for router/endpoint files
        if any(pattern in file_path for pattern in ["router", "endpoint", "api", "view", "controller"]):
            score += 7   # Increased from 3
        
        # Higher priority for model files
        if any(pattern in file_path for pattern in ["model", "schema", "serializer"]):
            score += 5
        
        # Higher priority for service/business logic files
        if any(pattern in file_path for pattern in ["service", "business", "logic", "manager"]):
            score += 4
        
        # Prioritize Django app files
        if any(pattern in file_path for pattern in ["apps/", "django"]):
            score += 6
        
        # Prioritize FastAPI/Flask route handlers
        if item.get("method") in ["get", "post", "put", "delete", "patch"]:
            score += 8
        
        # Lower priority for test files (shouldn't be many, but just in case)
        if "test" in file_path.lower():
            score -= 20  # Increased penalty
        
        # Lower priority for migration files
        if "migration" in file_path.lower():
            score -= 15
        
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
    
    # Normalize file paths for comparison
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
    
    # Check if filtering resulted in empty targets
    has_targets = any(filtered[key] for key in ["functions", "classes", "routes"])
    
    return (filtered, not has_targets)

# Enhanced heavy dependency detection for better test reliability
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
    
    # Testing ecosystem
    if "pytest" in packages_lower:
        test_deps = ["pytest-asyncio", "pytest-mock"]
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
            print(f"  ✓ {package}")
            
        except subprocess.CalledProcessError as e:
            error_output = e.stderr.decode() if e.stderr else "Unknown error"
            failed_installs.append((package, error_output))
            print(f"  ✗ {package}: {error_output.split(chr(10))[0]}")  # First line of error
            
        except Exception as e:
            failed_installs.append((package, str(e)))
            print(f"  ✗ {package}: {e}")
    
    # Summary
    if successful_installs:
        print(f"Successfully installed {len(successful_installs)} packages.")
    
    if failed_installs:
        print(f"Failed to install {len(failed_installs)} packages:")
        for package, error in failed_installs:
            print(f"  - {package}: {error[:100]}...")  # Truncate long errors
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

def enhance_coverage_targeting(compact: Dict[str, Any]) -> Dict[str, Any]:
    """Enhance targeting to improve test coverage of critical paths."""
    
    # Identify critical coverage patterns
    critical_patterns = {
        "django_views": ["views.py", "api.py"],
        "django_models": ["models.py"],
        "django_serializers": ["serializers.py"],
        "django_signals": ["signals.py"],
        "fastapi_routes": ["main.py", "app.py", "router"],
        "flask_routes": ["app.py", "routes.py"],
        "business_logic": ["service", "manager", "business"]
    }
    
    # Score items based on coverage importance
    def coverage_score(item):
        file_path = item.get("file", "").lower()
        score = 0
        
        # High priority for web framework entry points
        for pattern_name, patterns in critical_patterns.items():
            if any(pattern in file_path for pattern in patterns):
                if "django" in pattern_name:
                    score += 20
                elif "fastapi" in pattern_name or "flask" in pattern_name:
                    score += 25
                elif "business" in pattern_name:
                    score += 15
        
        # Priority for public APIs
        name = item.get("name", "")
        if not name.startswith("_"):
            score += 10
        
        # Priority for CRUD operations
        if any(crud in name.lower() for crud in ["create", "read", "update", "delete", "get", "post", "put", "patch"]):
            score += 8
        
        # Priority for authentication/authorization
        if any(auth in name.lower() for auth in ["login", "auth", "permission", "token"]):
            score += 12
        
        return score
    
    # Re-sort all targets by coverage importance
    for key in ["functions", "classes", "routes"]:
        if key in compact:
            compact[key].sort(key=coverage_score, reverse=True)
    
    return compact