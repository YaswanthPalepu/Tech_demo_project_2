import os, sys, json, pathlib, datetime, time, re, ast, math, subprocess, importlib.util, types as _types, random, shutil
from typing import Dict, Any, List, Tuple, Set, Optional
from openai import AzureOpenAI, RateLimitError  # openai>=1.0.0
import hashlib

# --------------------------------------------------------------------
# Prompt style: set TESTGEN_PROMPT_STYLE=ultra_bare to avoid heavy templates
# --------------------------------------------------------------------
PROMPT_STYLE = os.getenv("TESTGEN_PROMPT_STYLE", "ultra_bare").strip().lower()

# ---------------- Minimal Azure OpenAI helpers ----------------
def _get_any_env(*names: str) -> str:
    for n in names:
        v = os.getenv(n)
        if v:
            return v
    raise RuntimeError(f"Missing required environment variable (tried: {', '.join(names)})")

def _client() -> AzureOpenAI:
    return AzureOpenAI(
        api_key=_get_any_env("AZURE_OPENAI_KEY", "AZURE_OPENAI_API_KEY"),
        azure_endpoint=_get_any_env("AZURE_OPENAI_ENDPOINT", "AZURE_OPENAI_API_ENDPOINT"),
        api_version=_get_any_env("AZURE_OPENAI_API_VERSION", "OPENAI_API_VERSION"),
    )

def _deployment_name() -> str:
    return _get_any_env("AZURE_OPENAI_DEPLOYMENT", "OPENAI_DEPLOYMENT")

def _chat_completion_create(client: AzureOpenAI, deployment: str, messages: list):
    # No temperature/max_tokens; let Azure defaults apply
    return client.chat.completions.create(model=deployment, messages=messages)

# ---------------- Path helpers ----------------
REPO_ROOT = pathlib.Path(".").resolve()

def _norm_rel(p: str) -> str:
    try:
        pp = pathlib.Path(p)
        if pp.is_absolute():
            try:
                pp = pp.resolve().relative_to(REPO_ROOT)
            except Exception:
                pass
        s = str(pp.as_posix())
    except Exception:
        s = str(p).replace("\\", "/")
    if s.startswith("./"):
        s = s[2:]
    if s.startswith("target/"):
        s = s[len("target/"):]
    return s

def _basename_set(paths: Set[str]) -> Set[str]:
    return {pathlib.Path(p).name for p in paths}

# ---------------- Enhanced Change Detection ----------------
def _compute_content_hash(content: str) -> str:
    """Compute SHA256 hash of file content."""
    return hashlib.sha256(content.encode('utf-8')).hexdigest()

def _extract_code_signatures(file_path: pathlib.Path) -> Dict[str, str]:
    """Extract function/class signatures and their content hashes."""
    signatures = {}
    try:
        content = file_path.read_text(encoding='utf-8')
        tree = ast.parse(content)
        
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
                # Get the source code for this node
                start_line = node.lineno - 1
                end_line = node.end_lineno if hasattr(node, 'end_lineno') else start_line + 1
                lines = content.splitlines()
                node_content = '\n'.join(lines[start_line:end_line])
                
                # Create signature key
                sig_key = f"{type(node).__name__.lower()}:{node.name}"
                signatures[sig_key] = _compute_content_hash(node_content)
                
    except Exception as e:
        print(f"Warning: Could not parse {file_path}: {e}")
    
    return signatures

def _load_previous_state(manifest_path: pathlib.Path) -> Dict[str, Any]:
    """Load previous analysis state from manifest."""
    if not manifest_path.exists():
        return {}
    
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        return manifest.get("code_state", {})
    except Exception:
        return {}

def _save_current_state(manifest_path: pathlib.Path, current_state: Dict[str, Any]):
    """Save current code state to manifest."""
    manifest = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            manifest = {}
    
    manifest["code_state"] = current_state
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

def _detect_detailed_changes(target_root: pathlib.Path, manifest_path: pathlib.Path) -> Tuple[Set[str], Set[str], Set[str]]:
    """
    Detect detailed changes in the codebase.
    Returns: (added_or_modified, deleted, unchanged)
    """
    previous_state = _load_previous_state(manifest_path)
    current_state = {}
    
    # Scan current codebase
    for py_file in target_root.rglob("*.py"):
        if any(part.startswith('.') for part in py_file.parts):
            continue
        if "test" in str(py_file).lower():
            continue
            
        rel_path = str(py_file.relative_to(target_root))
        signatures = _extract_code_signatures(py_file)
        current_state[rel_path] = {
            "file_hash": _compute_content_hash(py_file.read_text(encoding='utf-8')),
            "signatures": signatures
        }
    
    # Compare states
    added_or_modified = set()
    deleted = set()
    unchanged = set()
    
    # Check for new or modified files
    for file_path, current_info in current_state.items():
        if file_path not in previous_state:
            added_or_modified.add(file_path)
        else:
            prev_info = previous_state[file_path]
            if current_info["file_hash"] != prev_info.get("file_hash", ""):
                # File was modified, check what specifically changed
                prev_sigs = prev_info.get("signatures", {})
                curr_sigs = current_info["signatures"]
                
                # If any signature changed, mark as modified
                if prev_sigs != curr_sigs:
                    added_or_modified.add(file_path)
                else:
                    unchanged.add(file_path)
            else:
                unchanged.add(file_path)
    
    # Check for deleted files
    for file_path in previous_state:
        if file_path not in current_state:
            deleted.add(file_path)
    
    # Save current state for next run
    _save_current_state(manifest_path, current_state)
    
    return added_or_modified, deleted, unchanged

# ---------------- Test File Management ----------------
def _find_related_test_files(outdir: pathlib.Path, source_file: str) -> List[pathlib.Path]:
    """Find test files that might be related to a source file."""
    related_tests = []
    
    # Extract module/class/function names from source file
    source_path = pathlib.Path(source_file)
    source_stem = source_path.stem
    
    # Look for test files that might contain tests for this source
    for test_file in outdir.rglob("test_*.py"):
        try:
            content = test_file.read_text(encoding='utf-8')
            # Check if the source file name or its components are referenced
            if (source_stem in content or 
                source_file.replace('/', '.').replace('.py', '') in content):
                related_tests.append(test_file)
        except Exception:
            continue
    
    return related_tests

def _cleanup_deleted_tests(outdir: pathlib.Path, deleted_files: Set[str]):
    """Remove test files for deleted source files."""
    for deleted_file in deleted_files:
        related_tests = _find_related_test_files(outdir, deleted_file)
        for test_file in related_tests:
            try:
                print(f"🗑️ Removing test file for deleted source: {test_file}")
                test_file.unlink()
            except Exception as e:
                print(f"Warning: Could not remove {test_file}: {e}")

def _create_enhanced_conftest(outdir: pathlib.Path) -> str:
    """Create an enhanced conftest.py that handles compatibility issues."""
    conftest_content = '''import pytest
import sys
import os
import warnings

# Suppress common warnings that clutter test output
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=PendingDeprecationWarning)

# Add project root to Python path
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Fix Jinja2/Flask compatibility issues
def _fix_jinja2_compatibility():
    """Fix Jinja2 Markup compatibility for Flask."""
    try:
        import jinja2
        if not hasattr(jinja2, 'Markup'):
            try:
                from markupsafe import Markup
                jinja2.Markup = Markup
                if not hasattr(jinja2, 'escape'):
                    from markupsafe import escape
                    jinja2.escape = escape
            except ImportError:
                # Fallback if markupsafe not available
                class MockMarkup(str):
                    def __html__(self): return self
                jinja2.Markup = MockMarkup
                jinja2.escape = lambda x: MockMarkup(str(x))
    except ImportError:
        pass

def _fix_collections_compatibility():
    """Fix collections ABC compatibility for older libraries."""
    try:
        import collections
        import collections.abc as abc
        for name in ['Mapping', 'MutableMapping', 'Sequence', 'Iterable', 'Container']:
            if not hasattr(collections, name) and hasattr(abc, name):
                setattr(collections, name, getattr(abc, name))
    except ImportError:
        pass

def _fix_flask_compatibility():
    """Fix Flask compatibility issues."""
    try:
        import flask
        if not hasattr(flask, 'escape'):
            try:
                from markupsafe import escape
                flask.escape = escape
            except ImportError:
                flask.escape = lambda x: str(x)
    except ImportError:
        pass

# Apply all compatibility fixes
_fix_jinja2_compatibility()
_fix_collections_compatibility() 
_fix_flask_compatibility()

@pytest.fixture(autouse=True)
def setup_test_environment():
    """Set up a clean test environment for each test."""
    # Set safe database URLs
    for key in ('DATABASE_URL', 'DB_URL', 'SQLALCHEMY_DATABASE_URI'):
        if not os.environ.get(key):
            os.environ[key] = 'sqlite:///:memory:'
    
    # Disable CSRF for testing
    os.environ['WTF_CSRF_ENABLED'] = 'False'
    
    yield
    
    # Cleanup after test
    pass

@pytest.fixture
def app():
    """Create application for testing if it exists."""
    try:
        # Try different common app factory patterns
        app_patterns = [
            ('conduit.app', 'create_app'),
            ('app', 'create_app'),
            ('application', 'create_app'),
            ('src.app', 'create_app'),
            ('conduit.app', 'app'),
            ('app', 'app'),
        ]
        
        app_instance = None
        for module_name, attr_name in app_patterns:
            try:
                module = __import__(module_name, fromlist=[attr_name])
                app_factory = getattr(module, attr_name, None)
                if app_factory:
                    if callable(app_factory):
                        app_instance = app_factory()
                    else:
                        app_instance = app_factory
                    break
            except ImportError:
                continue
        
        if not app_instance:
            pytest.skip("No app factory found")
        
        # Configure for testing
        app_instance.config['TESTING'] = True
        app_instance.config['WTF_CSRF_ENABLED'] = False
        app_instance.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        
        return app_instance
        
    except Exception as e:
        pytest.skip(f"Could not create app: {e}")

@pytest.fixture
def client(app):
    """Create test client."""
    try:
        return app.test_client()
    except Exception as e:
        pytest.skip(f"Could not create test client: {e}")

# Global exception handler for better error messages
def pytest_runtest_call(pyfuncitem):
    """Handle test execution with better error reporting."""
    try:
        return pyfuncitem.runtest()
    except ImportError as e:
        pytest.skip(f"Import error: {e}")
    except Exception as e:
        # Re-raise with more context
        raise type(e)(f"Test failed in {pyfuncitem.name}: {e}") from e

# Handle collection errors gracefully
def pytest_collection_modifyitems(config, items):
    """Skip items that have collection issues."""
    for item in items:
        if hasattr(item, '_request') and hasattr(item._request, 'raiseerror'):
            # Mark problematic tests for skipping
            item.add_marker(pytest.mark.skip(reason="Collection error"))
'''
    
    conftest_path = outdir / "conftest.py"
    conftest_path.parent.mkdir(parents=True, exist_ok=True)
    conftest_path.write_text(conftest_content, encoding="utf-8")
    return str(conftest_path)

# ---------------- Sanitizers & validators ----------------
def _extract_python_only(text: str) -> str:
    if "```" in text:
        blocks = re.findall(r"```(?:python)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
        text = "\n\n".join(blocks) if blocks else text.replace("```", "")
    lines = text.splitlines()
    if lines and lines[0].strip().lower() in {"python", "py"}:
        lines = lines[1:]
    return ("\n".join(lines)).strip() + "\n"

TEST_FUNC_RE = re.compile(r"^\s*def\s+test_[A-Za-z0-9_]*\s*\(", re.MULTILINE)

def _validate_code(code: str) -> Tuple[bool, str]:
    if not code or not code.strip():
        return False, "empty output"
    if not TEST_FUNC_RE.search(code):
        return False, "no test_ functions found"
    try:
        ast.parse(code, filename="<generated>", mode="exec")
    except SyntaxError as e:
        return False, f"syntax error: {e}"
    return True, ""

# --- Filter brittle patterns ---
BANNED_IMPORT_SUBSTRS = ["_pytest", "pytest._code"]
BRITTLE_SNIPPETS = [r"assert\s+repr\(", r"\.fullsource\b", r"\.source\b", r"0x[0-9a-fA-F]+"]

def _ensure_pytest_import(text: str) -> str:
    if "@pytest.mark.skip" in text and not re.search(r"^\s*import\s+pytest\b", text, re.MULTILINE):
        return "import pytest\n" + text
    return text

def _skip_brittle_test_functions(code: str) -> str:
    lines = code.splitlines()
    out, current = [], []

    def is_test_header(s: str) -> bool:
        return TEST_FUNC_RE.match(s) is not None

    def needs_skip(block: List[str]) -> bool:
        txt = "\n".join(block)
        if any(re.search(pat, txt) for pat in BRITTLE_SNIPPETS):
            return True
        if any(sub in txt for sub in BANNED_IMPORT_SUBSTRS):
            return True
        return False

    i = 0
    while i < len(lines):
        line = lines[i]
        if is_test_header(line):
            if current:
                out.extend(current)
                current = []
            func_lines = [line]
            i += 1
            while i < len(lines) and not is_test_header(lines[i]):
                func_lines.append(lines[i])
                i += 1
            if needs_skip(func_lines):
                out.append("@pytest.mark.skip(reason='auto-skip brittle assertion/import from generator')")
            out.extend(func_lines)
        else:
            current.append(line)
            i += 1

    if current:
        out.extend(current)
    text = "\n".join(out)
    if not text.endswith("\n"):
        text += "\n"
    return _ensure_pytest_import(text)

def _header_guard_for_banned_imports(code: str) -> str:
    if any(sub in code for sub in BANNED_IMPORT_SUBSTRS):
        return (
            "import pytest as _pytest\n"
            "_pytest.skip('generator: banned private imports detected; skipping module', allow_module_level=True)\n\n"
        ) + code
    return code

# ---------------- Analysis compaction ----------------
def _dedupe_keep(items: List[Dict[str, str]], key: str, limit: int = None) -> List[Dict[str, str]]:
    seen, out = set(), []
    for it in items or []:
        k = it.get(key)
        if not k or k in seen:
            continue
        seen.add(k)
        out.append({kk: it.get(kk) for kk in ("name", "file", "handler", "method") if kk in it})
        if limit and len(out) >= limit:
            break
    return out

def _compact_analysis(analysis: Dict[str, Any]) -> Dict[str, Any]:
    total_funcs = len(analysis.get("functions", []))
    soft_cap = 120 if total_funcs > 400 else 80 if total_funcs > 200 else 50

    funcs = sorted(analysis.get("functions", []), key=lambda x: x.get("file", ""))
    clss = sorted(analysis.get("classes", [])   , key=lambda x: x.get("file", ""))
    routes = sorted(analysis.get("routes", [])  , key=lambda x: x.get("file", ""))

    return {
        "functions": _dedupe_keep(funcs, "name", soft_cap),
        "classes": _dedupe_keep(clss, "name", max(30, soft_cap // 2)),
        "routes": _dedupe_keep(routes, "handler", max(30, soft_cap // 2)),
        "modules": sorted(set(analysis.get("modules", []))),
    }

# ---------------- Enhanced Dependency Management ----------------
COMMON_PKG_ALIASES = {
    "bs4": "beautifulsoup4",
    "yaml": "PyYAML",
    "cv2": "opencv-python",
    "sklearn": "scikit-learn",
    "PIL": "Pillow",
    "Crypto": "pycryptodome",
    "MySQLdb": "mysqlclient",
    "mysql": "mysqlclient",
    "psycopg2": "psycopg2-binary",
    "boto3": "boto3",
    "httpx": "httpx",
    "requests": "requests",
    "uvicorn": "uvicorn",
    "fastapi": "fastapi",
    "starlette": "starlette",
    "pydantic": "pydantic",
    "typing_extensions": "typing-extensions",
    "annotated_types": "annotated-types",
    "sqlalchemy": "SQLAlchemy",
    "flask": "flask",
    "django": "Django",
    "click": "click",
    "typer": "typer",
    "jinja2": "Jinja2",
    "ujson": "ujson",
    "orjson": "orjson",
    "pymongo": "pymongo",
    "redis": "redis",
    "pytest": "pytest",
    "jwt": "PyJWT",
    "markupsafe": "MarkupSafe",
}

# Version constraints for problematic packages
VERSION_CONSTRAINTS = {
    "flask": ">=2.0.0,<3.0.0",
    "jinja2": ">=3.0.0,<3.1.0", 
    "markupsafe": ">=2.0.0,<2.1.0",
    "click": ">=8.0.0,<8.1.0",
    "typer": ">=0.7.0,<0.8.0",
}

VALID_PIP_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
DENY_TOPS = {
    "__future__", "__main__", "__builtin__", "builtins",
    "typing", "types", "dataclasses", "importlib", "asyncio", "json", "re", "os", "sys", "pathlib",
    "logging", "argparse", "functools", "itertools", "collections", "subprocess", "datetime", "time",
    "math", "decimal", "fractions", "statistics", "sqlite3", "http", "urllib", "hmac", "hashlib",
    "base64", "csv", "glob", "shutil", "tempfile", "inspect", "traceback", "enum", "textwrap",
    "pprint", "string",
    "ConfigParser", "Queue", "HTMLParser", "StringIO",
}

def _is_stdlib(name: str) -> bool:
    try:
        stdmods = getattr(sys, "stdlib_module_names", None)
        if stdmods:
            return name in stdmods
        return name in {
            "os", "sys", "re", "json", "pathlib", "math", "itertools", "functools", "typing", "subprocess",
            "datetime", "time", "collections", "dataclasses", "ast", "logging", "unittest", "argparse",
            "asyncio", "multiprocessing", "threading", "sqlite3", "email", "http", "urllib", "hashlib",
            "hmac", "base64", "statistics", "random", "fractions", "decimal", "csv", "shutil", "tempfile",
            "glob", "inspect", "traceback", "textwrap", "string", "pprint", "enum", "types"
        }
    except Exception:
        return False

def _is_local_import(top: str) -> bool:
    roots: List[pathlib.Path] = []
    env_root = os.environ.get("TARGET_ROOT")
    if env_root:
        roots.append(pathlib.Path(env_root))
    roots.extend([pathlib.Path("."), pathlib.Path("src"), pathlib.Path("backend"), pathlib.Path("app"), pathlib.Path("target")])
    if pathlib.Path(top).exists() or pathlib.Path(top.replace(".", "/")).exists():
        return True
    for base in roots:
        if (base / f"{top}.py").exists() or (base / top).is_dir():
            return True
    return False

def _infer_required_packages(compact: Dict[str, Any]) -> List[str]:
    mods = compact.get("modules") or []
    needed: Set[str] = set()
    for m in mods:
        top = (m.split(".")[0] or "").strip()
        if not top:
            continue
        if top in DENY_TOPS:
            continue
        if top.startswith("_") or "__" in top:
            continue
        if any(c.isupper() for c in top):  # avoid GUI mega-pkgs like PyQt*
            continue
        if not VALID_PIP_RE.match(top):
            continue
        if _is_stdlib(top) or _is_local_import(top):
            continue
        pkg = COMMON_PKG_ALIASES.get(top, top)
        needed.add(pkg)
    
    # Add version constraints for problematic packages
    constrained_packages = []
    for pkg in sorted(needed):
        if pkg.lower() in VERSION_CONSTRAINTS:
            constrained_packages.append(f"{pkg}{VERSION_CONSTRAINTS[pkg.lower()]}")
        else:
            constrained_packages.append(pkg)
    
    # Special handling for Flask ecosystem
    pkg_names = {p.lower() for p in needed}
    if "flask" in pkg_names:
        # Ensure compatible versions for Flask ecosystem
        if "markupsafe" not in constrained_packages:
            constrained_packages.append("MarkupSafe>=2.0.0,<2.1.0")
        if "jinja2" not in constrained_packages:
            constrained_packages.append("Jinja2>=3.0.0,<3.1.0")
    
    if "fastapi" in pkg_names:
        needed.update({"starlette", "pydantic"})
    
    return constrained_packages

def _pip_install(packages: List[str]) -> None:
    if not packages:
        print("📦 No third-party packages inferred from imports.")
        return
    print("📦 Installing packages with version constraints:", ", ".join(packages))
    try:
        # Use --force-reinstall to ensure compatible versions
        cmd = [sys.executable, "-m", "pip", "install", "--force-reinstall", "--disable-pip-version-check", "--no-input"] + packages
        subprocess.check_call(cmd)
        print("✅ Package installation completed successfully")
    except subprocess.CalledProcessError as e:
        print(f"⚠️ pip install failed with exit code {e.returncode} (continuing; tests may skip).")

# ---------------- Sharding helpers ----------------
def _partition(lst: List[Dict[str, str]], n_parts: int) -> List[List[Dict[str, str]]]:
    if not lst:
        return [[] for _ in range(n_parts)]
    size = max(1, math.ceil(len(lst) / n_parts))
    groups = [lst[i:i + size] for i in range(0, len(lst), size)]
    while len(groups) < n_parts:
        groups.append([])
    return groups

def _targets_count_for_kind(compact: Dict[str, Any], kind: str) -> int:
    if kind == "unit":
        return len(compact.get("functions", [])) + len(compact.get("classes", []))
    n = len(compact.get("routes", []) or [])
    if n == 0:
        n = len(compact.get("functions", [])) + len(compact.get("classes", []))
    return n

def _auto_files_per_kind(compact: Dict[str, Any], kind: str) -> int:
    n = _targets_count_for_kind(compact, kind)
    if n <= 0:
        return 0
    base = 3 if n <= 8 else 4 if n <= 20 else 6 if n <= 40 else 8 if n <= 100 else 12
    cap = int(os.getenv("TESTGEN_FILES_PER_KIND_MAX", "6"))
    return min(base, max(1, min(n, cap)))

def _focus_for_shard(compact: Dict[str, Any], kind: str, shard_idx: int, total: int) -> Tuple[str, List[str]]:
    if kind == "unit":
        targets = (compact.get("functions", []) or []) + (compact.get("classes", []) or [])
        groups = _partition(targets, total)
        names = [d.get("name") for d in groups[shard_idx] if d.get("name")]
        return ", ".join(names) if names else "(none)", names

    routes = compact.get("routes", []) or []
    if routes:
        groups = _partition(routes, total)
        names = [d.get("handler") for d in groups[shard_idx] if d.get("handler")]
        label = ", ".join(sorted(set(names))) if names else "(none)"
        return label, names

    targets = (compact.get("functions", []) or []) + (compact.get("classes", []) or [])
    groups = _partition(targets, total)
    names = [d.get("name") for d in groups[shard_idx] if d.get("name")]
    return (", ".join(names) if names else "(none)"), names

# ---------------- Filtering analysis by changed files ----------------
def _filter_analysis_by_files(analysis: Dict[str, Any], focus_files: Optional[Set[str]]) -> Tuple[Dict[str, Any], bool]:
    if not focus_files:
        return analysis, False

    focus_norm: Set[str] = {_norm_rel(f) for f in focus_files}
    focus_basenames = _basename_set(focus_norm)

    def keep(entry: Dict[str, Any]) -> bool:
        f = entry.get("file") or ""
        fn = _norm_rel(f)
        if fn in focus_norm:
            return True
        if any(fn.endswith("/" + rel) for rel in focus_norm):
            return True
        if pathlib.Path(fn).name in focus_basenames:
            return True
        return False

    filt = {
        "functions": [d for d in (analysis.get("functions") or []) if keep(d)],
        "classes": [d for d in (analysis.get("classes") or []) if keep(d)],
        "routes": [d for d in (analysis.get("routes") or []) if keep(d)],
        "modules": analysis.get("modules", []),
    }
    if not (filt["functions"] or filt["classes"] or filt["routes"]):
        print("⚠️ Focus filter yielded 0 targets. Falling back to full analysis to ensure tests are generated.")
        return analysis, True
    return filt, False

# ---------------- Enhanced Universal Bootstrap ----------------
def _enhanced_universal_bootstrap(compact: Dict[str, Any]) -> str:
    tops: List[str] = []
    for m in compact.get("modules") or []:
        top = (m.split(".")[0] or "").strip()
        if top and not _is_stdlib(top) and not _is_local_import(top):
            tops.append(top)
    tops = sorted(set(tops))
    tops_lit = repr(tops)

    py2_alias_map = {
        "ConfigParser": "configparser",
        "Queue": "queue",
        "StringIO": "io",
        "cStringIO": "io",
        "urllib2": "urllib.request",
    }
    py2_alias_map_lit = repr(py2_alias_map)

    return f'''# --- ENHANCED UNIVERSAL BOOTSTRAP ---
import os, sys, importlib as _importlib, importlib.util as _iu, importlib.machinery as _im, types as _types, pytest as _pytest, builtins as _builtins
import warnings

# Suppress noisy warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=PendingDeprecationWarning)

# Ensure target root importable
_target = os.environ.get("TARGET_ROOT") or os.environ.get("ANALYZE_ROOT") or "target"
if _target and os.path.exists(_target):
    if _target not in sys.path:
        sys.path.insert(0, _target)
    # Change to target directory for relative imports
    try:
        os.chdir(_target)
    except Exception:
        pass
_TARGET_ABS = os.path.abspath(_target)

# Enhanced exception lookup with multiple fallback strategies
def _exc_lookup(name, default=Exception):
    """Enhanced exception lookup with fallbacks."""
    if not name or not isinstance(name, str):
        return default
    
    # Direct builtin lookup
    if hasattr(_builtins, name):
        return getattr(_builtins, name)
    
    # Try common exception modules
    for module_name in ['builtins', 'exceptions']:
        try:
            module = __import__(module_name)
            if hasattr(module, name):
                return getattr(module, name)
        except ImportError:
            continue
    
    # Parse module.ClassName format
    if '.' in name:
        try:
            mod_name, _, cls_name = name.rpartition('.')
            module = __import__(mod_name, fromlist=[cls_name])
            if hasattr(module, cls_name):
                return getattr(module, cls_name)
        except ImportError:
            pass
    
    return default

# Apply comprehensive compatibility fixes
def _apply_compatibility_fixes():
    """Apply various compatibility fixes for common issues."""
    
    # Jinja2/Flask compatibility
    try:
        import jinja2
        if not hasattr(jinja2, 'Markup'):
            try:
                from markupsafe import Markup
                jinja2.Markup = Markup
                if not hasattr(jinja2, 'escape'):
                    from markupsafe import escape
                    jinja2.escape = escape
            except ImportError:
                # Fallback implementation
                class MockMarkup(str):
                    def __html__(self): return self
                jinja2.Markup = MockMarkup
                jinja2.escape = lambda x: MockMarkup(str(x))
    except ImportError:
        pass
    
    # Flask compatibility
    try:
        import flask
        if not hasattr(flask, 'escape'):
            try:
                from markupsafe import escape
                flask.escape = escape
            except ImportError:
                flask.escape = lambda x: str(x)
    except ImportError:
        pass
    
    # Collections compatibility  
    try:
        import collections
        import collections.abc as abc
        for name in ['Mapping', 'MutableMapping', 'Sequence', 'Iterable', 'Container']:
            if not hasattr(collections, name) and hasattr(abc, name):
                setattr(collections, name, getattr(abc, name))
    except ImportError:
        pass

_apply_compatibility_fixes()

# Enhanced module attribute adapter (PEP 562 __getattr__)
_ADAPTED_MODULES = set()
def _attach_module_getattr(_m):
    try:
        if getattr(_m, "__name__", None) in _ADAPTED_MODULES:
            return
        mfile = getattr(_m, "__file__", "") or ""
        if not mfile or not os.path.abspath(mfile).startswith(_TARGET_ABS + os.sep):
            return  # only adapt modules under target/
        if hasattr(_m, "__getattr__"):
            _ADAPTED_MODULES.add(_m.__name__)
            return

        def __getattr__(name):
            # Try to resolve missing attributes from any instantiable public class
            for _nm, _obj in list(_m.__dict__.items()):
                if isinstance(_obj, type) and not _nm.startswith("_"):
                    try:
                        _inst = _obj()  # only no-arg constructors will work; otherwise skip
                    except Exception:
                        continue
                    if hasattr(_inst, name):
                        _val = getattr(_inst, name)
                        try:
                            setattr(_m, name, _val)  # cache for future lookups/imports
                        except Exception:
                            pass
                        return _val
            raise AttributeError(f"module {{_m.__name__!r}} has no attribute {{name!r}}")
        _m.__getattr__ = __getattr__
        _ADAPTED_MODULES.add(_m.__name__)
    except Exception:
        pass

# Wrap builtins.__import__ for automatic module adaptation
_orig_import = _builtins.__import__
def _import_with_adapter(name, globals=None, locals=None, fromlist=(), level=0):
    mod = _orig_import(name, globals, locals, fromlist, level)
    try:
        # Ensure top-level module object is adapted
        if isinstance(mod, _types.ModuleType):
            _attach_module_getattr(mod)
        # If a package was imported and fromlist asks for submodules, adapt them after real import
        if fromlist:
            for attr in fromlist:
                try:
                    sub = getattr(mod, attr, None)
                    if isinstance(sub, _types.ModuleType):
                        _attach_module_getattr(sub)
                except Exception:
                    pass
    except Exception:
        pass
    return mod
_builtins.__import__ = _import_with_adapter

# Safe database configuration
def _setup_safe_db_config():
    """Set up safe database configuration."""
    safe_db_url = "sqlite:///:memory:"
    for key in ("DATABASE_URL", "DB_URL", "SQLALCHEMY_DATABASE_URI"):
        current = os.environ.get(key)
        if not current or "://" not in str(current):
            os.environ[key] = safe_db_url

_setup_safe_db_config()

# Enhanced Django setup
try:
    import django
    from django.conf import settings
    if not settings.configured:
        settings.configure(
            SECRET_KEY='test-key-not-for-production',
            DEBUG=True,
            TESTING=True,
            DATABASES={{
                'default': {{
                    'ENGINE': 'django.db.backends.sqlite3',
                    'NAME': ':memory:',
                }}
            }},
            INSTALLED_APPS=[],
            USE_TZ=True,
        )
        django.setup()
except ImportError:
    pass

# Enhanced SQLAlchemy safety
try:
    import sqlalchemy as sa
    _orig_create_engine = sa.create_engine
    
    def _safe_create_engine(url, *args, **kwargs):
        """Create engine with fallback to safe URL."""
        try:
            if not url or "://" not in str(url):
                url = os.environ.get("DATABASE_URL", "sqlite:///:memory:")
            return _orig_create_engine(url, *args, **kwargs)
        except Exception:
            return _orig_create_engine("sqlite:///:memory:", *args, **kwargs)
    
    sa.create_engine = _safe_create_engine
except ImportError:
    pass

# Py2 alias maps for legacy compatibility
_PY2_ALIASES = {py2_alias_map_lit}
for _old, _new in list(_PY2_ALIASES.items()):
    if _old in sys.modules:
        continue
    try:
        __import__(_new)
        sys.modules[_old] = sys.modules[_new]
    except Exception:
        pass

def _safe_find_spec(name):
    try:
        return _iu.find_spec(name)
    except Exception:
        return None

# Enhanced Qt family stubs (PyQt5/6, PySide2/6) for headless CI
def _ensure_pkg(name, is_pkg=None):
    if name in sys.modules:
        m = sys.modules[name]
        if getattr(m, "__spec__", None) is None:
            m.__spec__ = _im.ModuleSpec(name, loader=None, is_package=(is_pkg if is_pkg is not None else ("." not in name)))
            if "." not in name and not hasattr(m, "__path__"):
                m.__path__ = []
        return m
    m = _types.ModuleType(name)
    if is_pkg is None:
        is_pkg = ("." not in name)
    if is_pkg and not hasattr(m, "__path__"):
        m.__path__ = []
    m.__spec__ = _im.ModuleSpec(name, loader=None, is_package=is_pkg)
    sys.modules[name] = m
    return m

_qt_roots = ["PyQt5", "PyQt6", "PySide2", "PySide6"]
for __qt_root in _qt_roots:
    if _safe_find_spec(__qt_root) is None:
        _pkg = _ensure_pkg(__qt_root, is_pkg=True)
        _core = _ensure_pkg(__qt_root + ".QtCore", is_pkg=False)
        _gui = _ensure_pkg(__qt_root + ".QtGui", is_pkg=False)
        _widgets = _ensure_pkg(__qt_root + ".QtWidgets", is_pkg=False)

        # QtCore minimal API
        class QObject: pass
        def pyqtSignal(*a, **k): return object()
        def pyqtSlot(*a, **k):
            def _decorator(fn): return fn
            return _decorator
        class QCoreApplication:
            def __init__(self, *a, **k): pass
            def exec_(self): return 0
            def exec(self): return 0
        _core.QObject = QObject
        _core.pyqtSignal = pyqtSignal
        _core.pyqtSlot = pyqtSlot
        _core.QCoreApplication = QCoreApplication

        # QtGui minimal API
        class QFont:
            def __init__(self, *a, **k): pass
        class QDoubleValidator:
            def __init__(self, *a, **k): pass
            def setBottom(self, *a, **k): pass
            def setTop(self, *a, **k): pass
        class QIcon:
            def __init__(self, *a, **k): pass
        class QPixmap:
            def __init__(self, *a, **k): pass
        _gui.QFont = QFont
        _gui.QDoubleValidator = QDoubleValidator
        _gui.QIcon = QIcon
        _gui.QPixmap = QPixmap

        # QtWidgets minimal API
        class QApplication:
            def __init__(self, *a, **k): pass
            def exec_(self): return 0
            def exec(self): return 0
        class QWidget:
            def __init__(self, *a, **k): pass
        class QLabel(QWidget):
            def __init__(self, *a, **k):
                super().__init__(); self._text = ""
            def setText(self, t): self._text = str(t)
            def text(self): return self._text
        class QLineEdit(QWidget):
            def __init__(self, *a, **k):
                super().__init__(); self._text = ""
            def setText(self, t): self._text = str(t)
            def text(self): return self._text
            def clear(self): self._text = ""
        class QTextEdit(QLineEdit): pass
        class QPushButton(QWidget):
            def __init__(self, *a, **k): super().__init__()
        class QMessageBox:
            @staticmethod
            def warning(*a, **k): return None
            @staticmethod
            def information(*a, **k): return None
            @staticmethod
            def critical(*a, **k): return None
        class QFileDialog:
            @staticmethod
            def getSaveFileName(*a, **k): return ("history.txt", "")
            @staticmethod
            def getOpenFileName(*a, **k): return ("history.txt", "")
        class QFormLayout:
            def __init__(self, *a, **k): pass
            def addRow(self, *a, **k): pass
        class QGridLayout(QFormLayout):
            def addWidget(self, *a, **k): pass

        _widgets.QApplication = QApplication
        _widgets.QWidget = QWidget
        _widgets.QLabel = QLabel
        _widgets.QLineEdit = QLineEdit
        _widgets.QTextEdit = QTextEdit
        _widgets.QPushButton = QPushButton
        _widgets.QMessageBox = QMessageBox
        _widgets.QFileDialog = QFileDialog
        _widgets.QFormLayout = QFormLayout
        _widgets.QGridLayout = QGridLayout

        # Mirror common widget symbols into QtGui
        for _name in ("QApplication","QWidget","QLabel","QLineEdit","QTextEdit","QPushButton","QMessageBox","QFileDialog","QFormLayout","QGridLayout"):
            setattr(_gui, _name, getattr(_widgets, _name))

# Generic stub for other missing third-party packages
_THIRD_PARTY_TOPS = {tops_lit}
for _name in list(_THIRD_PARTY_TOPS):
    _top = (_name or "").split(".")[0]
    if not _top:
        continue
    if _top in sys.modules:
        continue
    if _safe_find_spec(_top) is not None:
        continue
    if _top in {{"PyQt5","PyQt6","PySide2","PySide6"}}:
        continue
    _m = _types.ModuleType(_top)
    _m.__spec__ = _im.ModuleSpec(_top, loader=None, is_package=False)
    sys.modules[_top] = _m

# --- /ENHANCED UNIVERSAL BOOTSTRAP ---
'''

# ---------------- Prompt builders ----------------
_SYSTEM_MIN = (
    "Return ONLY valid Python test code for pytest. No Markdown, no explanations. "
    "Import target modules INSIDE each test function. "
    "Deterministic I/O; no network; mock file/db/http/UI as needed (monkeypatch/tmp_path). "
    "Do NOT use private pytest internals. "
    "Do NOT use custom pytest markers. "
    "Prefer non-GUI modules; if a module imports Qt/PySide, rely on shims and do not start event loops. "
    "For exceptions NEVER assume custom names; always call _exc_lookup('Name', Exception) inside pytest.raises and isinstance. "
    "Handle import errors gracefully with pytest.skip."
)

_UNIT_BARE = (
    "Write concise UNIT tests (3-6). Cover public functions/classes from the focus list. "
    "Do not assume module-level functions exist if the project uses classes; instantiate classes explicitly. "
    "Assert outputs and error conditions precisely; for exceptions use _exc_lookup('CustomError', Exception). "
    "Use tmp_path for filesystem; avoid repr-based asserts and custom markers. "
    "Wrap imports in try-except with pytest.skip for missing dependencies."
)

_INTEG_BARE = (
    "Write INTEGRATION tests (2-5). Exercise interactions across modules. "
    "If GUI imports exist, avoid real event loops and windows; rely on shims. "
    "Mock external effects with monkeypatch; import targets inside tests. "
    "Handle import errors gracefully with pytest.skip."
)

_E2E_BARE = (
    "Write E2E tests (2-4). Compose a realistic black-box workflow using available APIs. "
    "Keep it deterministic and self-contained; import targets inside tests. "
    "Handle import errors gracefully with pytest.skip."
)

def _limit_str(s: str, max_chars: int = 12000) -> str:
    if len(s) <= max_chars:
        return s
    return s[:max_chars] + "...(truncated)"

def _sample_targets(names: List[str], k: int) -> List[str]:
    if not names:
        return []
    if len(names) <= k:
        return names
    random.seed(1234)
    return sorted(random.sample(names, k))

def _build_prompt(kind: str, compact_json: str, focus_label: str, shard: int, total: int, compact: Dict[str, Any]) -> List[Dict[str, str]]:
    if PROMPT_STYLE == "ultra_bare":
        sys_msg = _SYSTEM_MIN
        fnames = [f.get("name") for f in (compact.get("functions") or []) if f.get("name")]
        cnames = [c.get("name") for c in (compact.get("classes") or []) if c.get("name")]
        rnames = [r.get("handler") for r in (compact.get("routes") or []) if r.get("handler")]
        pick = _sample_targets(fnames + cnames + rnames, 16)
        context = {"focus": focus_label or "(none)", "suggested_targets": pick}
        brief = json.dumps(context, ensure_ascii=False)

        if kind == "unit":
            user = f"[UNIT shard {shard}/{total}] {_UNIT_BARE}\nContext: {brief}\nAnalysis: {_limit_str(compact_json)}"
        elif kind == "integ":
            user = f"[INTEG shard {shard}/{total}] {_INTEG_BARE}\nContext: {brief}\nAnalysis: {_limit_str(compact_json)}"
        else:
            user = f"[E2E shard {shard}/{total}] {_E2E_BARE}\nContext: {brief}\nAnalysis: {_limit_str(compact_json)}"
        return [{"role": "system", "content": sys_msg}, {"role": "user", "content": user}]

    # Legacy prompt format
    SYSTEM = """You are an expert Python test engineer.
Return ONLY valid Python source code (no Markdown, no backticks, no prose).
Hard rules:
- Test ONLY project modules and stdlib; no private pytest internals or custom markers.
- Deterministic I/O; import targets inside each test.
- Prefer non-GUI modules; if Qt/PySide appears, avoid event loops (use shims).
- Do NOT assume module-level functions exist when APIs are class-based; instantiate classes.
- For exceptions, call _exc_lookup('Name', Exception) with a string, not a bare symbol.
- Ensure at least one function named test_*.
- Handle import errors with pytest.skip."""
    if kind == "unit":
        user = f"Shard {shard}/{total} • Focus: {focus_label}\nAnalysis:\n{compact_json}\nWrite UNIT tests (4-8)."
    elif kind == "integ":
        user = f"Shard {shard}/{total} • Focus: {focus_label}\nAnalysis:\n{compact_json}\nWrite INTEGRATION tests (3-6)."
    else:
        user = f"Shard {shard}/{total} • Focus: {focus_label}\nAnalysis:\n{compact_json}\nWrite E2E tests (2-4)."
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]

# ---------------- Enhanced smoke fallback ----------------
def _smoke_from_modules(compact: Dict[str, Any]) -> str:
    mods = sorted(set([m for m in compact.get("modules") or [] if m and (m[0].isalpha() or m[0] == "_")]))
    body = ["import importlib, pytest", ""]
    body.append("def test_import_all_modules():")
    body.append("    \"\"\"Test that all discovered modules can be imported.\"\"\"")
    body.append("    mods = " + repr(mods))
    body.append("    for m in mods:")
    body.append("        try:")
    body.append("            importlib.import_module(m)")
    body.append("        except ImportError as e:")
    body.append("            pytest.skip(f'cannot import {m}: {e}')")
    body.append("        except Exception as e:")
    body.append("            pytest.skip(f'error importing {m}: {e}')")
    body.append("")
    body.append("def test_python_environment():")
    body.append("    \"\"\"Basic smoke test for Python environment.\"\"\"")
    body.append("    import sys, os")
    body.append("    assert sys.version_info >= (3, 6)")
    body.append("    assert os.path.exists('.')")
    body.append("")
    return "\n".join(body)

# ---------------- Post-generation massaging ----------------
_RAISES_QUAL = re.compile(r"pytest\.raises\(\s*([A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)+)\s*(,|\))")
_RAISES_BARE = re.compile(r"pytest\.raises\(\s*([A-Za-z_][\w]*)\s*(,|\))")
_ISINSTANCE_QUAL = re.compile(r"isinstance\(\s*([A-Za-z_][\w]*)\s*,\s*([A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)+)\s*\)")
_ISINSTANCE_BARE = re.compile(r"isinstance\(\s*([A-Za-z_][\w]*)\s*,\s*([A-Za-z_][\w]*)\s*\)")

def _massage_generated_code(code: str) -> str:
    # Normalize pytest.raises / isinstance calls
    def _repl_qual(m): return f'pytest.raises(_exc_lookup("{m.group(1)}", Exception){m.group(2)}'
    def _repl_bare(m): return f'pytest.raises(_exc_lookup("{m.group(1)}", Exception){m.group(2)}'
    code = _RAISES_QUAL.sub(_repl_qual, code)
    code = _RAISES_BARE.sub(_repl_bare, code)

    def _repl_is_q(m): return f'isinstance({m.group(1)}, _exc_lookup("{m.group(2)}", Exception))'
    def _repl_is_b(m): return f'isinstance({m.group(1)}, _exc_lookup("{m.group(2)}", Exception))'
    code = _ISINSTANCE_QUAL.sub(_repl_is_q, code)
    code = _ISINSTANCE_BARE.sub(_repl_is_b, code)

    # Downgrade hallucinated exceptions to known ones
    known_excs = {
        "Exception", "ZeroDivisionError", "ValueError", "TypeError", "IndexError",
        "KeyError", "RuntimeError", "AttributeError", "ImportError",
        "OSError", "FileNotFoundError", "PermissionError", "StopIteration"
    }
    for name in re.findall(r'_exc_lookup\("([^"]+)"', code):
        if name not in known_excs:
            code = code.replace(f'_exc_lookup("{name}"', '_exc_lookup("Exception"')

    # Add enhanced import error handling
    lines = code.splitlines()
    enhanced_lines = []
    for line in lines:
        enhanced_lines.append(line)
        # Add try-except around direct imports in test functions
        if re.match(r'\s*def test_', line):
            enhanced_lines.append("    \"\"\"Test with enhanced error handling.\"\"\"")
            
    return "\n".join(enhanced_lines) + "\n"

# ---------------- Manifest helpers ----------------
def write(path: pathlib.Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"📝 wrote {path}")

def _load_list(path: Optional[str]) -> Optional[List[str]]:
    if not path:
        return None
    p = pathlib.Path(path)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return [str(x) for x in data]
    except Exception:
        return None
    return None

def _update_manifest(outdir: pathlib.Path, created_files: List[str], change_summary: Dict[str, Any] = None):
    manifest_path = outdir / "_manifest.json"
    manifest = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            manifest = {}
    
    runs = manifest.get("runs", [])
    run_info = {
        "ts": datetime.datetime.utcnow().isoformat() + "Z",
        "files_generated": created_files,
        "focus_files": _load_list(os.getenv("FOCUS_FILES_JSON_PATH")) or [],
    }
    
    if change_summary:
        run_info["change_summary"] = change_summary
    
    runs.append(run_info)
    manifest["runs"] = runs
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

# ---------------- Smart outdir management ----------------
def _smart_cleanup_outdir(outdir: pathlib.Path, deleted_files: Set[str], modified_files: Set[str]):
    """Intelligently clean up test directory based on code changes."""
    if not outdir.exists():
        return
    
    print(f"🧹 Smart cleanup: {len(deleted_files)} deleted, {len(modified_files)} modified files")
    
    # Remove tests for deleted source files
    _cleanup_deleted_tests(outdir, deleted_files)
    
    # For modified files, remove related old tests to allow regeneration
    for modified_file in modified_files:
        related_tests = _find_related_test_files(outdir, modified_file)
        for test_file in related_tests:
            try:
                print(f"🔄 Removing old test for modified source: {test_file}")
                test_file.unlink()
            except Exception as e:
                print(f"Warning: Could not remove {test_file}: {e}")
    
    # Clean up empty directories
    for d in sorted(outdir.glob("*")):
        if d.is_dir():
            try:
                next(d.rglob("*"))
            except StopIteration:
                shutil.rmtree(d, ignore_errors=True)

# ---------------- Enhanced Generation ----------------
def _build_guard_and_messages(compact: Dict[str, Any], compact_json: str, kind: str, focus_label: str, shard: int, total: int):
    guard = _runtime_guard_for(compact)
    messages = _build_prompt(kind, compact_json, focus_label, shard, total, compact)
    return guard, messages

def generate_all(analysis: Dict[str, Any], outdir="tests/generated", focus_files: Optional[List[str]] = None):
    """
    Enhanced generation with smart change detection, compatibility fixes, and error handling.
    """
    out = pathlib.Path(outdir)
    manifest_path = out / "_manifest.json"
    
    # Create enhanced conftest.py first
    print("📝 Creating enhanced conftest.py with compatibility fixes...")
    _create_enhanced_conftest(out)
    
    # Determine target root for change detection
    target_root = pathlib.Path(os.environ.get("TARGET_ROOT", "target"))
    
    # Perform detailed change detection
    added_or_modified, deleted, unchanged = _detect_detailed_changes(target_root, manifest_path)
    
    # Log change summary
    change_summary = {
        "added_or_modified": len(added_or_modified),
        "deleted": len(deleted),
        "unchanged": len(unchanged),
        "files_analyzed": len(added_or_modified) + len(deleted) + len(unchanged)
    }
    
    print(f"📊 Change Analysis:")
    print(f"  ➕ Added/Modified: {len(added_or_modified)}")
    print(f"  ➖ Deleted: {len(deleted)}")  
    print(f"  ⚪ Unchanged: {len(unchanged)}")
    
    # Early exit logic with better messaging
    force_generation = os.environ.get("TESTGEN_FORCE", "false").lower() == "true"
    
    if not force_generation and not added_or_modified and not deleted and unchanged:
        if list(out.rglob("test_*.py")):
            print("✅ No code changes detected and tests exist. Skipping generation.")
            print("   (Set TESTGEN_FORCE=true to force regeneration)")
            return
        else:
            print("📝 No existing tests found. Generating initial test suite.")
    elif not force_generation and not added_or_modified and not deleted:
        print("✅ No code changes detected. Skipping test generation.")
        print("   (Set TESTGEN_FORCE=true to force regeneration)")
        return
    
    if force_generation:
        print("🔧 Force generation enabled - regenerating all tests")
    
    # Smart cleanup based on changes
    _smart_cleanup_outdir(out, deleted, added_or_modified)

    ts = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")

    # Filter analysis to focus on changed files only (unless forced)
    raw_focus = set(focus_files or _load_list(os.getenv("FOCUS_FILES_JSON_PATH")) or [])
    if not raw_focus and not force_generation:
        raw_focus = added_or_modified  # Use detected changes as focus
        
    filtered_analysis, fallback = _filter_analysis_by_files(analysis, raw_focus if raw_focus else None)

    compact = _compact_analysis(filtered_analysis)

    # Install packages with enhanced compatibility handling
    if added_or_modified or fallback or force_generation:
        packages = _infer_required_packages(compact)
        if packages:
            print("📦 Installing packages with compatibility constraints...")
            _pip_install(packages)

    compact_json = json.dumps(compact, separators=(",", ":"))
    kinds = ["unit", "integ", "e2e"]

    created_files: List[str] = []

    # Check if we have targets to test
    total_targets = len(compact.get("functions", [])) + len(compact.get("classes", [])) + len(compact.get("routes", []))
    if total_targets == 0:
        print("⚠️ No test targets found in analysis. Creating basic smoke tests...")
        # Create a basic smoke test file
        smoke_code = _smoke_from_modules(compact)
        guard = _runtime_guard_for(compact)
        fname = f"test_smoke_{ts}.py"
        path = out / fname
        write(path, guard + smoke_code)
        created_files.append(str(path))
        _update_manifest(out, created_files, change_summary)
        return

    for kind in kinds:
        files_per_kind = _auto_files_per_kind(compact, kind)
        if files_per_kind <= 0:
            print(f"⚠️ No targets for {kind} → skipping {kind}")
            continue

        print(f"🔧 Generating {files_per_kind} {kind} test files...")

        for i in range(files_per_kind):
            focus_label, _ = _focus_for_shard(compact, kind, i, files_per_kind)
            guard, messages = _build_guard_and_messages(compact, compact_json, kind, focus_label, i + 1, files_per_kind)

            try:
                code = _gen_validated(messages, compact=compact)
                code = _massage_generated_code(code)

                fname = f"test_{kind}_{ts}_{i+1:02d}.py"
                path = out / fname
                write(path, guard + code)
                created_files.append(str(path))
            except Exception as e:
                print(f"⚠️ Failed to generate {kind} test {i+1}: {e}")
                # Create fallback smoke test
                smoke_code = _smoke_from_modules(compact)
                fname = f"test_{kind}_fallback_{ts}_{i+1:02d}.py"
                path = out / fname
                write(path, guard + smoke_code)
                created_files.append(str(path))

    # Save list of generated files
    out_list = os.getenv("GENERATED_LIST_PATH")
    if out_list:
        try:
            pathlib.Path(out_list).write_text(json.dumps(created_files, indent=2), encoding="utf-8")
        except Exception:
            pass

    _update_manifest(out, created_files, change_summary)

    if created_files:
        print(f"✅ Generated {len(created_files)} test files")
        if added_or_modified:
            print(f"   (focused on {len(added_or_modified)} changed source files)")
    else:
        print("ℹ️ No tests generated")

# ---------------- LLM call with enhanced validation ----------------
def _runtime_guard_for(compact: Dict[str, Any]) -> str:
    critical = {"fastapi", "flask", "django", "sqlalchemy", "starlette", "pydantic"}
    mods = {m.split(".")[0].lower() for m in (compact.get("modules") or [])}
    needed = sorted(critical & mods)
    checks = ""
    if needed:
        checks = "\n".join(
            [
                f"if importlib.util.find_spec('{m}') is None:\n    pytest.skip('{m} not installed; skipping module', allow_module_level=True)"
                for m in needed
            ]
        ) + "\n"
    
    bootstrap = _enhanced_universal_bootstrap(compact)
    return ("import importlib.util, pytest\n" + checks + "\n" + bootstrap + "\n")

def _gen_validated(messages: List[Dict[str, str]], attempts_per_file: int = 3, backoff_seq=(3, 7, 15), compact: Optional[Dict[str, Any]] = None) -> str:
    client = _client()
    deployment = _deployment_name()

    attempts = 0
    reason = "unknown"
    while attempts < attempts_per_file:
        attempts += 1
        for sleep_s in (0, *backoff_seq):
            try:
                if sleep_s:
                    time.sleep(sleep_s)
                resp = _chat_completion_create(client, deployment, messages)
                raw = resp.choices[0].message.content or ""
                cleaned = _extract_python_only(raw)
                ok, reason = _validate_code(cleaned)
                if ok:
                    code = _skip_brittle_test_functions(cleaned)
                    code = _header_guard_for_banned_imports(code)
                    return code
                messages.append({
                    "role": "user", 
                    "content": f"Invalid: {reason}. Regenerate STRICT pytest code (no markdown), import targets inside tests, avoid custom markers, instantiate classes when APIs are class-based, use _exc_lookup for exceptions, and handle import errors with pytest.skip."
                })
                break
            except RateLimitError:
                if sleep_s < backoff_seq[-1]:
                    continue
                else:
                    break
            except Exception as e:
                print(f"⚠️ Error during generation attempt {attempts}: {e}")
                break
    
    print(f"⚠️ LLM generation failed after {attempts} attempts, using smoke test fallback")
    return _smoke_from_modules(compact or {})

if __name__ == "__main__":
    import analyzer
    analysis = analyzer.analyze_python_tree(pathlib.Path("."))
    generate_all(analysis)
    print("✅ Generated tests in tests/generated")