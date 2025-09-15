# src/generator.py
import os, sys, json, pathlib, datetime, time, re, ast, math, subprocess, importlib.util, types as _types, random, shutil
from typing import Dict, Any, List, Tuple, Set, Optional
from openai import AzureOpenAI, RateLimitError
import hashlib

PROMPT_STYLE = os.getenv("TESTGEN_PROMPT_STYLE", "ultra_bare").strip().lower()
REPO_ROOT = pathlib.Path(".").resolve()
STRICT_FAIL = os.getenv("TESTGEN_STRICT_FAIL", "0").lower() in ("1","true","yes")

# ---------------------- Azure OpenAI wiring ----------------------

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
    return client.chat.completions.create(model=deployment, messages=messages)

# ---------------------- helpers: paths, hashing, change detect ----------------------

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

def _compute_content_hash(content: str) -> str:
    return hashlib.sha256(content.encode('utf-8')).hexdigest()

def _extract_code_signatures(file_path: pathlib.Path) -> Dict[str, str]:
    signatures = {}
    try:
        content = file_path.read_text(encoding='utf-8', errors="ignore")
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
                start_line = node.lineno - 1
                end_line = getattr(node, "end_lineno", start_line + 1)
                lines = content.splitlines()
                node_content = '\n'.join(lines[start_line:end_line])
                sig_key = f"{type(node).__name__.lower()}:{node.name}"
                signatures[sig_key] = _compute_content_hash(node_content)
    except Exception as e:
        print(f"Warning: Could not parse {file_path}: {e}")
    return signatures

def _load_previous_state(manifest_path: pathlib.Path) -> Dict[str, Any]:
    if not manifest_path.exists():
        return {}
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        return manifest.get("code_state", {})
    except Exception:
        return {}

def _save_current_state(manifest_path: pathlib.Path, current_state: Dict[str, Any]):
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
    previous_state = _load_previous_state(manifest_path)
    current_state = {}
    for py_file in target_root.rglob("*.py"):
        if any(part.startswith('.') for part in py_file.parts):
            continue
        if "test" in str(py_file).lower():
            continue
        rel_path = str(py_file.relative_to(target_root))
        signatures = _extract_code_signatures(py_file)
        try:
            content_hash = _compute_content_hash(py_file.read_text(encoding='utf-8', errors="ignore"))
        except Exception:
            content_hash = ""
        current_state[rel_path] = {"file_hash": content_hash, "signatures": signatures}
    added_or_modified, deleted, unchanged = set(), set(), set()
    for file_path, current_info in current_state.items():
        if file_path not in previous_state:
            added_or_modified.add(file_path)
        else:
            prev_info = previous_state[file_path]
            if current_info["file_hash"] != prev_info.get("file_hash", ""):
                if prev_info.get("signatures", {}) != current_info["signatures"]:
                    added_or_modified.add(file_path)
                else:
                    unchanged.add(file_path)
            else:
                unchanged.add(file_path)
    for file_path in previous_state:
        if file_path not in current_state:
            deleted.add(file_path)
    _save_current_state(manifest_path, current_state)
    return added_or_modified, deleted, unchanged

# ---------------------- manage generated tests vs changes ----------------------

def _find_related_test_files(outdir: pathlib.Path, source_file: str) -> List[pathlib.Path]:
    related_tests = []
    source_path = pathlib.Path(source_file)
    source_stem = source_path.stem
    for test_file in outdir.rglob("test_*.py"):
        try:
            content = test_file.read_text(encoding='utf-8', errors="ignore")
            if (source_stem in content or source_file.replace('/', '.').replace('.py', '') in content):
                related_tests.append(test_file)
        except Exception:
            continue
    return related_tests

def _cleanup_deleted_tests(outdir: pathlib.Path, deleted_files: Set[str]):
    for deleted_file in deleted_files:
        for test_file in _find_related_test_files(outdir, deleted_file):
            try:
                print(f"🗑️ Removing test file for deleted source: {test_file}")
                test_file.unlink()
            except Exception as e:
                print(f"Warning: Could not remove {test_file}: {e}")

# ---------------------- conftest: compat shims ----------------------

def _create_enhanced_conftest(outdir: pathlib.Path) -> str:
    conftest_content = '''import pytest, sys, os, warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=PendingDeprecationWarning)

project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

if os.getenv("TESTGEN_FIX_JINJA2","1") in ("1","true","yes"):
    def _fix_jinja2_compatibility():
        try:
            import jinja2
            if not hasattr(jinja2, 'Markup'):
                try:
                    from markupsafe import Markup, escape
                    jinja2.Markup = Markup
                    if not hasattr(jinja2, 'escape'):
                        jinja2.escape = escape
                except Exception:
                    pass
        except ImportError:
            pass
    _fix_jinja2_compatibility()

if os.getenv("TESTGEN_FIX_COLLECTIONS","1") in ("1","true","yes"):
    def _fix_collections_compatibility():
        try:
            import collections
            import collections.abc as abc
            for name in ['Mapping','MutableMapping','Sequence','Iterable','Container',
                         'MutableSequence','Set','MutableSet','Iterator','Generator','Callable','Collection']:
                if not hasattr(collections, name) and hasattr(abc, name):
                    setattr(collections, name, getattr(abc, name))
        except ImportError:
            pass
    _fix_collections_compatibility()

if os.getenv("TESTGEN_FIX_FLASK","0") in ("1","true","yes"):
    def _fix_flask_compatibility():
        try:
            import flask
            if not hasattr(flask, 'escape'):
                try:
                    from markupsafe import escape
                    flask.escape = escape
                except Exception:
                    pass
        except ImportError:
            pass
    _fix_flask_compatibility()

def _fix_marshmallow_compatibility():
    try:
        import marshmallow as _mm
        if not hasattr(_mm, "__version__"):
            _mm.__version__ = "4"
    except Exception:
        pass

_fix_marshmallow_compatibility()

os.environ.setdefault('WTF_CSRF_ENABLED', 'False')
'''
    conftest_path = outdir / "conftest.py"
    conftest_path.parent.mkdir(parents=True, exist_ok=True)
    conftest_path.write_text(conftest_content, encoding="utf-8")
    return str(conftest_path)

# ---------------------- output validation and hardening ----------------------

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

BANNED_IMPORT_SUBSTRS = ["_pytest", "pytest._code"]
BRITTLE_SNIPPETS = [r"assert\s+repr\(", r"\.fullsource\b", r"\.source\b", r"0x[0-9a-fA-F]+"]

def _ensure_pytest_import(text: str) -> str:
    if "@pytest.mark.skip" in text and not re.search(r"^\s*import\s+pytest\b", text, re.MULTILINE):
        return "import pytest\n" + text
    return text

def _ensure_pytest_import_top(code: str) -> str:
    if not re.search(r'^\s*import\s+pytest\b', code, re.MULTILINE):
        code = "import pytest\n" + code
    return code

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
                out.extend(current); current = []
            func_lines = [line]; i += 1
            while i < len(lines) and not is_test_header(lines[i]):
                func_lines.append(lines[i]); i += 1
            if needs_skip(func_lines):
                out.append("@pytest.mark.skip(reason='auto-skip brittle assertion/import from generator')")
            out.extend(func_lines)
        else:
            current.append(line); i += 1
    if current: out.extend(current)
    text = "\n".join(out)
    if not text.endswith("\n"): text += "\n"
    return _ensure_pytest_import(text)

def _header_guard_for_banned_imports(code: str) -> str:
    if any(sub in code for sub in BANNED_IMPORT_SUBSTRS):
        return (
            "import pytest as _pytest\n"
            "_pytest.skip('generator: banned private imports detected; skipping module', allow_module_level=True)\n\n"
        ) + code
    return code

# ---------------------- analysis compaction ----------------------

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
    funcs  = sorted(analysis.get("functions", []), key=lambda x: x.get("file", ""))
    clss   = sorted(analysis.get("classes", [])  , key=lambda x: x.get("file", ""))
    routes = sorted(analysis.get("routes", [])   , key=lambda x: x.get("file", ""))
    return {
        "functions": _dedupe_keep(funcs, "name", soft_cap),
        "classes":   _dedupe_keep(clss, "name", max(30, soft_cap // 2)),
        "routes":    _dedupe_keep(routes, "handler", max(30, soft_cap // 2)),
        "modules": sorted(set(analysis.get("modules", []))),
    }

# ---------------------- package inference ----------------------

COMMON_PKG_ALIASES = {
    "bs4": "beautifulsoup4", "yaml": "PyYAML", "cv2": "opencv-python", "sklearn": "scikit-learn",
    "PIL": "Pillow", "Crypto": "pycryptodome", "MySQLdb": "mysqlclient", "mysql": "mysqlclient",
    "psycopg2": "psycopg2-binary", "boto3": "boto3", "httpx": "httpx", "requests": "requests",
    "uvicorn": "uvicorn", "fastapi": "fastapi", "starlette": "starlette", "pydantic": "pydantic",
    "typing_extensions": "typing-extensions", "annotated_types": "annotated-types", "sqlalchemy": "SQLAlchemy",
    "flask": "flask", "django": "Django", "click": "click", "typer": "typer", "jinja2": "Jinja2",
    "ujson": "ujson", "orjson": "orjson", "pymongo": "pymongo", "redis": "redis", "pytest": "pytest",
    "jwt": "PyJWT", "markupsafe": "MarkupSafe", "rest_framework": "djangorestframework",
}
VERSION_CONSTRAINTS: Dict[str, str] = {}
DENY_INFER: Set[str] = {
    *(p.strip().lower() for p in os.getenv("TESTGEN_DENY_PKGS", "models,relations,renderers").split(",") if p.strip())
}
VALID_PIP_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
BAD_GENERIC_TOPS = {
    "models","model","views","view","urls","settings","config","configs","tests","test",
    "schemas","schema","forms","admin","migrations","apps","serializers","permissions","filters",
    "routers","services","repository","repositories","managers","helpers","utils"
}
DENY_TOPS = {
    "__future__","__main__","__builtin__","builtins","typing","types","dataclasses","importlib","asyncio","json","re","os","sys","pathlib",
    "logging","argparse","functools","itertools","collections","subprocess","datetime","time","math","decimal","fractions","statistics","sqlite3",
    "http","urllib","hmac","hashlib","base64","csv","glob","shutil","tempfile","inspect","traceback","enum","textwrap","pprint","string",
    "ConfigParser","Queue","HTMLParser","StringIO",
} | BAD_GENERIC_TOPS

def _is_stdlib(name: str) -> bool:
    try:
        stdmods = getattr(sys, "stdlib_module_names", None)
        if stdmods:
            return name in stdmods
        return name in {
            "os","sys","re","json","pathlib","math","itertools","functools","typing","subprocess","datetime","time","collections","dataclasses","ast",
            "logging","unittest","argparse","asyncio","multiprocessing","threading","sqlite3","email","http","urllib","hashlib","hmac","base64",
            "statistics","random","fractions","decimal","csv","shutil","tempfile","glob","inspect","traceback","textwrap","string","pprint","enum","types"
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
        if not top or top in DENY_TOPS or top.startswith("_") or "__" in top:
            continue
        if any(c.isupper() for c in top):
            continue
        if not VALID_PIP_RE.match(top):
            continue
        if _is_stdlib(top) or _is_local_import(top):
            continue
        pkg = COMMON_PKG_ALIASES.get(top, top)
        if pkg and pkg.lower() not in DENY_INFER:
            needed.add(pkg)

    constrained: List[str] = []
    for pkg in sorted(needed):
        pin = VERSION_CONSTRAINTS.get(pkg.lower())
        constrained.append(f"{pkg}{pin}" if pin else pkg)

    pkg_names = {p.lower() for p in needed}
    if "fastapi" in pkg_names:
        for extra in {"starlette", "pydantic"}:
            if extra not in DENY_INFER:
                constrained.append(extra)

    return sorted(set(constrained), key=str.lower)

def _pip_install(packages: List[str]) -> None:
    pkgs = [p for p in (packages or []) if p and p.strip() and p.lower() not in DENY_INFER]
    if not pkgs:
        print("📦 No third-party packages inferred from imports.")
        return

    constraints = os.getenv("TESTGEN_PIP_CONSTRAINTS") or os.getenv("PIP_CONSTRAINT")
    print("📦 Installing packages (one-by-one):", ", ".join(pkgs))
    for pkg in pkgs:
        cmd = [sys.executable, "-m", "pip", "install",
               "--disable-pip-version-check", "--no-input",
               "--upgrade-strategy", "only-if-needed"]
        if constraints:
            cmd += ["-c", constraints]
        cmd.append(pkg)
        try:
            subprocess.check_call(cmd)
            print(f"  ✅ {pkg}")
        except subprocess.CalledProcessError as e:
            print(f"  ⚠️ Skipping {pkg} (pip exit {e.returncode})")
            continue

# ---------------------- sharding and focus ----------------------

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

def _partition_targets(targets: List[Dict[str, str]], total: int, shard_idx: int) -> List[str]:
    groups = _partition(targets, total)
    return [d.get("name") or d.get("handler") for d in groups[shard_idx] if d.get("name") or d.get("handler")]

def _focus_for_shard(compact: Dict[str, Any], kind: str, shard_idx: int, total: int) -> Tuple[str, List[str]]:
    if kind == "unit":
        targets = (compact.get("functions", []) or []) + (compact.get("classes", []) or [])
        names = _partition_targets(targets, total, shard_idx)
        return (", ".join(names) if names else "(none)"), names
    routes = compact.get("routes", []) or []
    if routes:
        names = _partition_targets(routes, total, shard_idx)
        return (", ".join(sorted(set(names))) if names else "(none)"), names
    targets = (compact.get("functions", []) or []) + (compact.get("classes", []) or [])
    names = _partition_targets(targets, total, shard_idx)
    return (", ".join(names) if names else "(none)"), names

def _filter_analysis_by_files(analysis: Dict[str, Any], focus_files: Optional[Set[str]]) -> Tuple[Dict[str, Any], bool]:
    if not focus_files:
        return analysis, False
    focus_norm: Set[str] = {_norm_rel(f) for f in focus_files}
    focus_basenames = _basename_set(focus_norm)
    def keep(entry: Dict[str, Any]) -> bool:
        fn = _norm_rel(entry.get("file") or "")
        return (fn in focus_norm) or any(fn.endswith("/" + rel) for rel in focus_norm) or (pathlib.Path(fn).name in focus_basenames)
    filt = {
        "functions": [d for d in (analysis.get("functions") or []) if keep(d)],
        "classes":   [d for d in (analysis.get("classes")  or []) if keep(d)],
        "routes":    [d for d in (analysis.get("routes")   or []) if keep(d)],
        "modules": analysis.get("modules", []),
    }
    if not (filt["functions"] or filt["classes"] or filt["routes"]):
        print("⚠️ Focus filter yielded 0 targets. Falling back to full analysis to ensure tests are generated.")
        return analysis, True
    return filt, False

# ---------------------- bootstrap injected into every test file ----------------------

def _enhanced_universal_bootstrap(compact: Dict[str, Any]) -> str:
    include_qt = any((m.split(".")[0] or "").startswith(("PyQt","PySide")) for m in (compact.get("modules") or []))
    qt_env = ("import os\nos.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')\n" if include_qt else "")
    qt_probe = (
        "for __qt_root in ['PyQt5','PyQt6','PySide2','PySide6']:\n"
        "    try:\n"
        "        import importlib.util as _iu\n"
        "        if _iu.find_spec(__qt_root) is None:\n"
        "            raise ImportError\n"
        "    except Exception:\n"
        "        pass\n"
        if include_qt else ""
    )

    return f'''# --- ENHANCED UNIVERSAL BOOTSTRAP ---
import os, sys, importlib.util as _iu, types as _types, pytest as _pytest, builtins as _builtins, warnings
STRICT = os.getenv("TESTGEN_STRICT", "1").lower() in ("1","true","yes")
STRICT_FAIL = os.getenv("TESTGEN_STRICT_FAIL","0").lower() in ("1","true","yes")
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=PendingDeprecationWarning)

_target = os.environ.get("TARGET_ROOT") or os.environ.get("ANALYZE_ROOT")
if _target and os.path.isdir(_target):
    if _target not in sys.path: sys.path.insert(0, _target)

def _exc_lookup(name, default):
    try:
        mod_name, _, cls_name = str(name).rpartition(".")
        if mod_name:
            mod = __import__(mod_name, fromlist=[cls_name])
            return getattr(mod, cls_name, default)
        return getattr(sys.modules.get("builtins"), str(name), default)
    except Exception:
        return default

# Optional Django bootstrap to avoid masking real failures by default.
if os.getenv("TESTGEN_ENABLE_DJANGO_BOOTSTRAP","0") in ("1","true","yes"):
    try:
        import django
        from django.conf import settings as _dj_settings
        from django import apps as _dj_apps
        if not _dj_settings.configured:
            _cfg = dict(
                DEBUG=True, SECRET_KEY='pytest-secret',
                DATABASES={{'default': {{'ENGINE': 'django.db.backends.sqlite3','NAME': ':memory:'}}}},
                INSTALLED_APPS=['django.contrib.auth','django.contrib.contenttypes','django.contrib.sessions','django.contrib.messages'],
                MIDDLEWARE=['django.middleware.security.SecurityMiddleware','django.contrib.sessions.middleware.SessionMiddleware','django.middleware.common.CommonMiddleware'],
                USE_TZ=True, TIME_ZONE='UTC',
            )
            try: _cfg["DEFAULT_AUTO_FIELD"] = "django.db.models.AutoField"
            except Exception: pass
            try: _dj_settings.configure(**_cfg)
            except Exception: pass
        if not _dj_apps.ready:
            try: django.setup()
            except Exception: pass
        try: import django.contrib.auth.base_user as _dj_probe  # noqa
        except Exception as _e:
            _pytest.skip(f"Django core import failed safely: {{_e.__class__.__name__}}: {{_e}}", allow_module_level=True)
    except Exception as _e:
        _pytest.skip(f"Django bootstrap not available: {{_e.__class__.__name__}}: {{_e}}", allow_module_level=True)

{qt_env}{qt_probe}# --- /ENHANCED UNIVERSAL BOOTSTRAP ---
'''

def _requires_django(f):
    import functools, pytest as _pytest
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        try:
            import django
            from django.apps import apps
            if not apps.ready:
                _pytest.skip("Django not properly configured")
            return f(*args, **kwargs)
        except ImportError:
            _pytest.skip("Django not available")
        except Exception as e:
            _pytest.skip(f"Django setup issue: {e}")
    return wrapper

# ---------------------- prompts ----------------------

_SYSTEM_MIN = (
    "Return ONLY valid Python pytest tests. No Markdown.\n"
    "Guard third-party imports with try/except ImportError and call pytest.skip at module level.\n"
    "Use Arrange-Act-Assert, parametrize normal and edge cases; include error paths.\n"
    "Use tmp_path/monkeypatch/unittest.mock for I/O and collaborators.\n"
    "Do NOT use private pytest internals or custom markers.\n"
    "Assert concrete outputs, types, and state changes.\n"
    "For exceptions: do NOT indirect via string names. Refer to exception objects directly. "
    "If a custom exception may not exist, use getattr(module, 'CalculatorError', ZeroDivisionError) or ZeroDivisionError.\n"
    "Never write 'from pkg import __init__'."
)

_UNIT_DEV = "Write UNIT tests (3-6) like a senior dev. Prefer public functions/classes in the focus list."
_INTEG_DEV = "Write INTEGRATION tests (2-5) that cross modules naturally; mock external calls."
_E2E_DEV   = "Write E2E-style black-box tests (2-4) from the public API only. Deterministic & self-contained."

def _limit_str(s: str, max_chars: int = 12000) -> str:
    return s if len(s) <= max_chars else s[:max_chars] + "...(truncated)"

def _sample_targets(names: List[str], k: int) -> List[str]:
    if not names: return []
    if len(names) <= k: return names
    random.seed(1234)
    return sorted(random.sample(names, k))

def _build_prompt(kind: str, compact_json: str, focus_label: str, shard: int, total: int, compact: Dict[str, Any]) -> List[Dict[str, str]]:
    sys_msg = _SYSTEM_MIN
    fnames = [f.get("name") for f in (compact.get("functions") or []) if f.get("name")]
    cnames = [c.get("name") for c in (compact.get("classes") or []) if c.get("name")]
    rnames = [r.get("handler") for r in (compact.get("routes") or []) if r.get("handler")]
    pick = _sample_targets(fnames + cnames + rnames, 16)
    context = {"focus": focus_label or "(none)", "suggested_targets": pick}
    brief = json.dumps(context, ensure_ascii=False)
    if kind == "unit":
        user = f"[UNIT shard {shard}/{total}] {_UNIT_DEV}\nContext: {brief}\nAnalysis: {_limit_str(compact_json)}"
    elif kind == "integ":
        user = f"[INTEG shard {shard}/{total}] {_INTEG_DEV}\nContext: {brief}\nAnalysis: {_limit_str(compact_json)}"
    else:
        user = f"[E2E shard {shard}/{total}] {_E2E_DEV}\nContext: {brief}\nAnalysis: {_limit_str(compact_json)}"
    return [{"role": "system", "content": sys_msg}, {"role": "user", "content": user}]

# ---------------------- harden generated code ----------------------

_SKIP_ANY_EXC_RE = re.compile(
    r"except\s+Exception\s+as\s+e:\s*\n\s*pytest\.skip\((.*?)\)",
    flags=re.DOTALL
)

def _massage_generated_code(code: str) -> str:
    # Normalize ImportError-only skipping in user code
    code = _SKIP_ANY_EXC_RE.sub(
        r"except ImportError as e:\n        pytest.skip(\1)\n    except Exception:\n        raise",
        code
    )
    # Disallow bad import pattern
    code = re.sub(
        r'^\s*from\s+([A-Za-z_][\w\.]*)\s+import\s+__init__\s+as\s+([A-Za-z_]\w*)\s*',
        r'import \1 as \2', code, flags=re.MULTILINE,
    )
    code = re.sub(
        r'^\s*from\s+([A-Za-z_][\w\.]*)\s+import\s+__init__\s*',
        r'import \1', code, flags=re.MULTILINE,
    )
    # Inject AAA hint under each test header and ensure pytest import
    lines, out = code.splitlines(), []
    for line in lines:
        out.append(line)
        if re.match(r'\s*def\s+test_', line):
            out.append('    # Arrange-Act-Assert: generated by ai-testgen')
    code = "\n".join(out)
    code = _ensure_pytest_import_top(code)
    return code if code.endswith("\n") else code + "\n"

# ---------------------- IO ----------------------

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
        "strict_fail": STRICT_FAIL,
    }
    if change_summary:
        run_info["change_summary"] = change_summary
    runs.append(run_info)
    manifest["runs"] = runs
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

def _smart_cleanup_outdir(outdir: pathlib.Path, deleted_files: Set[str], added_or_modified: Set[str]):
    if not outdir.exists():
        return
    print(f"🧹 Smart cleanup: {len(deleted_files)} deleted, {len(added_or_modified)} modified files")
    _cleanup_deleted_tests(outdir, deleted_files)
    for modified_file in added_or_modified:
        for test_file in _find_related_test_files(outdir, modified_file):
            try:
                print(f"🔄 Removing old test for modified source: {test_file}")
                test_file.unlink()
            except Exception as e:
                print(f"Warning: Could not remove {test_file}: {e}")
    for d in sorted(outdir.glob("*")):
        if d.is_dir():
            try:
                next(d.rglob("*"))
            except StopIteration:
                shutil.rmtree(d, ignore_errors=True)

# ---------------------- generation core ----------------------

def _build_guard_and_messages(compact: Dict[str, Any], compact_json: str, kind: str, focus_label: str, shard: int, total: int):
    guard = _runtime_guard_for(compact)
    messages = _build_prompt(kind, compact_json, focus_label, shard, total, compact)
    return guard, messages

def generate_all(analysis: Dict[str, Any], outdir="tests/generated", focus_files: Optional[List[str]] = None):
    out = pathlib.Path(outdir)
    manifest_path = out / "_manifest.json"

    print("📝 Creating enhanced conftest.py with compatibility fixes...")
    _create_enhanced_conftest(out)

    target_root = pathlib.Path(os.environ.get("TARGET_ROOT", "target"))
    added_or_modified, deleted, unchanged = _detect_detailed_changes(target_root, manifest_path)
    change_summary = {
        "added_or_modified": len(added_or_modified),
        "deleted": len(deleted),
        "unchanged": len(unchanged),
        "files_analyzed": len(added_or_modified) + len(deleted) + len(unchanged)
    }
    print("📊 Change Analysis:")
    print(f"  ➕ Added/Modified: {len(added_or_modified)}")
    print(f"  ➖ Deleted: {len(deleted)}")
    print(f"  ⚪ Unchanged: {len(unchanged)}")

    force_generation = os.environ.get("TESTGEN_FORCE", "false").lower() == "true"

    if not force_generation and not added_or_modified and not deleted and unchanged:
        if list(out.rglob("test_*.py")):
            print("✅ No code changes detected and tests exist. Skipping generation.")
            print("   (Set TESTGEN_FORCE=true to force regeneration)")
            return
        else:
            print("📝 No existing tests found. Will attempt initial generation.")
    elif not force_generation and not added_or_modified and not deleted:
        print("✅ No code changes detected. Skipping test generation.")
        print("   (Set TESTGEN_FORCE=true to force regeneration)")
        return

    if force_generation:
        print("🔧 Force generation enabled - regenerating all tests")

    _smart_cleanup_outdir(out, deleted, added_or_modified)

    ts = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")

    raw_focus = set(focus_files or _load_list(os.getenv("FOCUS_FILES_JSON_PATH")) or [])
    if not raw_focus and not force_generation:
        raw_focus = added_or_modified

    filtered_analysis, _ = _filter_analysis_by_files(analysis, raw_focus if raw_focus else None)
    compact = _compact_analysis(filtered_analysis)

    packages = _infer_required_packages(compact)
    if packages:
        print("📦 Installing inferred packages (constrained, only-if-needed)…")
        _pip_install(packages)

    compact_json = json.dumps(compact, separators=(",", ":"))
    kinds = ["unit", "integ", "e2e"]
    created_files: List[str] = []

    total_targets = len(compact.get("functions", [])) + len(compact.get("classes", [])) + len(compact.get("routes", []))
    if total_targets == 0:
        raise RuntimeError("No test targets found in analysis (functions/classes/routes). Aborting without writing any tests.")

    for kind in kinds:
        files_per_kind = _auto_files_per_kind(compact, kind)
        if files_per_kind <= 0:
            print(f"⚠️ No targets for {kind} → skipping {kind}")
            continue
        print(f"🔧 Generating {files_per_kind} {kind} test files...")
        for i in range(files_per_kind):
            focus_label, _ = _focus_for_shard(compact, kind, i, files_per_kind)
            guard, messages = _build_guard_and_messages(compact, compact_json, kind, focus_label, i + 1, files_per_kind)
            code = _gen_validated(messages, compact=compact)
            fname = f"test_{kind}_{ts}_{i+1:02d}.py"
            path = out / fname
            final_code = guard + code
            try:
                ast.parse(final_code, filename=fname)
            except SyntaxError as e:
                raise RuntimeError(f"Final AST check failed for {fname}: {e}") from e
            write(path, final_code)
            created_files.append(str(path))

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

# ---------------------- runtime guard per file ----------------------

def _runtime_guard_for(compact: Dict[str, Any]) -> str:
    critical = {"fastapi", "flask", "django", "sqlalchemy", "starlette", "pydantic"}
    mods = {m.split(".")[0].lower() for m in (compact.get("modules") or [])}
    needed = sorted(critical & mods)
    checks = ""
    if needed:
        checks = "\n".join(
            [f"import importlib.util, pytest\nif importlib.util.find_spec('{m}') is None:\n    pytest.skip('{m} not installed; skipping module', allow_module_level=True)" for m in needed]
        ) + "\n"
    bootstrap = _enhanced_universal_bootstrap(compact)
    return (checks + "\n" + bootstrap + "\n")

# ---------------------- LLM loop ----------------------

def _gen_validated(messages: List[Dict[str, str]], attempts_per_file: int = 3, backoff_seq=(3, 7, 15), compact: Optional[Dict[str, Any]] = None) -> str:
    client = _client()
    deployment = _deployment_name()
    reason = "unknown"
    for attempt in range(1, attempts_per_file + 1):
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
                    code = _massage_generated_code(code)

                    ok2, reason2 = _validate_code(code)
                    if ok2:
                        return code
                    reason = f"post-process validation failed: {reason2}"

                messages.append({
                    "role": "user",
                    "content": (
                        f"Invalid: {reason}. Regenerate strict, developer-style pytest code only. "
                        "Guard imports with try/except ImportError and module-level pytest.skip, prefer parametrize & boundaries, "
                        "use tmp_path/monkeypatch/mock, no private pytest internals. "
                        "Refer to exception classes directly; do not use string lookups."
                    )
                })
                break
            except RateLimitError:
                if sleep_s < backoff_seq[-1]:
                    continue
                else:
                    break
            except Exception as e:
                print(f"⚠️ Error during generation attempt {attempt}: {e}")
                break
    raise RuntimeError(f"LLM generation failed after {attempts_per_file} attempts: {reason}")

# ---------------------- entrypoint ----------------------

if __name__ == "__main__":
    try:
        try:
            import src.analyzer as analyzer  # type: ignore
        except Exception:
            import analyzer  # type: ignore
        analysis = analyzer.analyze_python_tree(pathlib.Path("."))
    except Exception as _e:
        raise RuntimeError(f"Analyzer import/run failed: {_e}") from _e
    generate_all(analysis)
    print("✅ Generated tests in tests/generated")
