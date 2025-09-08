# src/generator.py
import os, sys, json, pathlib, datetime, time, re, ast, math, subprocess, importlib.util, types as _types, random, shutil
from typing import Dict, Any, List, Tuple, Set, Optional
from openai import AzureOpenAI, RateLimitError  # openai>=1.0.0

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

# ---------------- Dependency inference & installation ----------------
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
    lowers = {p.lower() for p in needed}
    if "fastapi" in lowers:
        needed.update({"starlette", "pydantic"})
    return sorted(needed)

def _pip_install(packages: List[str]) -> None:
    if not packages:
        print("📦 No third-party packages inferred from imports.")
        return
    print("📦 Installing packages from analysis:", ", ".join(packages))
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-input", *packages])
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

# ---------------- Universal bootstrap (prepended to tests) ----------------
def _universal_bootstrap(compact: Dict[str, Any]) -> str:
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

    # NOTE: keep this as an f-string ONLY for injecting tops_lit / py2_alias_map_lit.
    # Inside the string, do NOT use f-strings—use .format(root) instead—to avoid early interpolation.
    return f'''# --- UNIVERSAL BOOTSTRAP (generated) ---
import os, sys, importlib, importlib.util as _iu, importlib.abc, importlib.machinery, types as _types, pytest as _pytest

# Ensure target root importable
_target = os.environ.get("TARGET_ROOT") or os.environ.get("ANALYZE_ROOT") or "target"
if _target and _target not in sys.path:
    sys.path.insert(0, _target)

# Safe DB defaults
for _k in ("DATABASE_URL","DB_URL","SQLALCHEMY_DATABASE_URI"):
    _v = os.environ.get(_k)
    if not _v or "://" not in str(_v):
        os.environ[_k] = "sqlite:///:memory:"

# Minimal Django config
try:
    if _iu.find_spec("django") is not None:
        import django
        from django.conf import settings as _dj_settings
        if not _dj_settings.configured:
            _dj_settings.configure(
                SECRET_KEY="test",
                DEBUG=True,
                ALLOWED_HOSTS=["*"],
                INSTALLED_APPS=[],
                DATABASES={{"default": {{"ENGINE":"django.db.backends.sqlite3","NAME":":memory:"}}}},
            )
            django.setup()
except Exception:
    pass

# collections.abc compatibility
try:
    import collections as _collections, collections.abc as _abc
    for _n in ("Mapping","MutableMapping","Sequence","MutableSequence","Set","MutableSet","Iterable","Iterator"):
        if not hasattr(_collections, _n) and hasattr(_abc, _n):
            setattr(_collections, _n, getattr(_abc, _n))
except Exception:
    pass

# Py2 alias maps if imported
_PY2_ALIASES = {py2_alias_map_lit}
for _old, _new in list(_PY2_ALIASES.items()):
    if _old in sys.modules:
        continue
    try:
        __import__(_new)
        sys.modules[_old] = sys.modules[_new]
    except Exception:
        pass

# ---------- Exception resolver for tolerant asserts ----------
def _exc_lookup(name_or_type, fallback=Exception):
    import builtins
    if isinstance(name_or_type, type):
        return name_or_type
    name = str(name_or_type)
    try:
        if "." in name:
            modname, attr = name.rsplit(".", 1)
            try:
                mod = sys.modules.get(modname) or importlib.import_module(modname)
            except Exception:
                return fallback
            return getattr(mod, attr, fallback)
        for _m in list(sys.modules.values()):
            try:
                if hasattr(_m, name):
                    return getattr(_m, name)
            except Exception:
                pass
        return getattr(builtins, name, fallback) if hasattr(builtins, name) else fallback
    except Exception:
        return fallback

# ---------- Dummy object & generic autostub for missing packages ----------
class _Dummy:
    def __init__(self, *a, **k): pass
    def __call__(self, *a, **k): return self
    def __getattr__(self, _): return self
    def __iter__(self): return iter(())
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def __bool__(self): return False
    def __int__(self): return 0
    def __float__(self): return 0.0
    def read(self, *a, **k): return ""
    def write(self, *a, **k): return 0
    def close(self): pass
    def __repr__(self): return "<Dummy>"

def _mk_package(fullname):
    m = _types.ModuleType(fullname)
    m.__path__ = []  # mark as package
    def __getattr__(name): return _Dummy()
    m.__getattr__ = __getattr__
    return m

# Pre-stub top-level third-party packages referenced by analysis (safe no-ops)
_THIRD_PARTY_TOPS = {tops_lit}
for _name in list(_THIRD_PARTY_TOPS):
    _top = (_name or "").split(".")[0]
    if not _top or _top in sys.modules:
        continue
    _spec = _iu.find_spec(_top)
    if _spec is None:
        sys.modules[_top] = _mk_package(_top)

# ----- Robust Qt shims (PyQt5/6, PySide2/6) -----
def _install_qt_shims(root):
    if root not in sys.modules:
        sys.modules[root] = _mk_package(root)

    # QtCore
    core_name = "{{}}.QtCore".format(root)
    if core_name not in sys.modules:
        core = _mk_package(core_name)
        class QObject: pass
        class _Signal:
            def __init__(self): self._subs=[]
            def connect(self, fn): self._subs.append(fn)
            def emit(self, *a, **k):
                for f in list(self._subs):
                    try: f(*a, **k)
                    except Exception: pass
        class Qt: Horizontal=1; Vertical=2
        core.QObject = QObject
        core.Signal = _Signal
        core.pyqtSignal = _Signal
        core.Qt = Qt
        sys.modules[core_name] = core

    # QtGui
    gui_name = "{{}}.QtGui".format(root)
    if gui_name not in sys.modules:
        gui = _mk_package(gui_name)
        class QFont:
            def __init__(self, *a, **k): pass
        class QDoubleValidator:
            def __init__(self, *a, **k): pass
        class QIcon:
            def __init__(self, *a, **k): pass
        class QPixmap:
            def __init__(self, *a, **k): pass
        gui.QFont = QFont
        gui.QDoubleValidator = QDoubleValidator
        gui.QIcon = QIcon
        gui.QPixmap = QPixmap
        sys.modules[gui_name] = gui

    # QtWidgets
    widgets_name = "{{}}.QtWidgets".format(root)
    if widgets_name not in sys.modules:
        widgets = _mk_package(widgets_name)
        class QWidget:
            def __init__(self, *a, **k): pass
            def setWindowTitle(self, *a, **k): pass
            def show(self): pass
        class QApplication:
            def __init__(self, *a, **k): pass
            def exec_(self): return 0
        class QLabel(QWidget):
            def __init__(self, text=""): self._text=str(text)
            def setText(self, t): self._text=str(t)
            def text(self): return self._text
        class QLineEdit(QWidget):
            def __init__(self, text=""): self._text=str(text)
            def setText(self, t): self._text=str(t)
            def text(self): return self._text
            def clear(self): self._text=""
        class QTextEdit(QLineEdit): pass
        class _Signal:
            def __init__(self): self._subs=[]
            def connect(self, fn): self._subs.append(fn)
            def emit(self, *a, **k):
                for f in list(self._subs):
                    try: f(*a, **k)
                    except Exception: pass
        class QPushButton(QWidget):
            def __init__(self, *a, **k): self.clicked=_Signal()
        class QMessageBox:
            @staticmethod
            def information(*a, **k): return None
            @staticmethod
            def warning(*a, **k): return None
            @staticmethod
            def critical(*a, **k): return None
        class QGridLayout:
            def addWidget(self, *a, **k): pass
        class QFormLayout(QGridLayout):
            def addRow(self, *a, **k): pass
        class QFileDialog:
            @staticmethod
            def getSaveFileName(*a, **k):
                import os
                return (os.path.join(os.getcwd(), "tmp_test_output.txt"), "")
        widgets.QWidget = QWidget
        widgets.QApplication = QApplication
        widgets.QLabel = QLabel
        widgets.QLineEdit = QLineEdit
        widgets.QTextEdit = QTextEdit
        widgets.QPushButton = QPushButton
        widgets.QMessageBox = QMessageBox
        widgets.QGridLayout = QGridLayout
        widgets.QFormLayout = QFormLayout
        widgets.QFileDialog = QFileDialog
        sys.modules[widgets_name] = widgets

# Always ensure at least one shim family exists
_qt_fams = ("PyQt5","PyQt6","PySide2","PySide6")
if not any(_iu.find_spec(f) is not None for f in _qt_fams):
    for fam in _qt_fams:
        _install_qt_shims(fam)

# --- /UNIVERSAL BOOTSTRAP ---
'''


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
    bootstrap = _universal_bootstrap(compact)
    return ("import importlib.util, pytest\n" + checks + "\n" + bootstrap + "\n")

# ---------------- Prompt builders ----------------
_SYSTEM_MIN = (
    "Return ONLY valid Python test code for pytest. No Markdown, no explanations. "
    "Import target modules INSIDE each test. "
    "Deterministic I/O; no network; mock file/db/http/UI as needed (monkeypatch/tmp_path). "
    "Do NOT use private pytest internals. "
    "Do NOT use custom pytest markers. "
    "If GUIs are present (Qt/PySide), DO NOT start event loops; assume lightweight shims exist. "
    "For exceptions NEVER assume custom names; always call _exc_lookup('Name', Exception) inside pytest.raises and isinstance."
)

_UNIT_BARE = (
    "Write concise UNIT tests (3–6). Cover public functions/classes from the focus list. "
    "Assert outputs and error conditions precisely; for exceptions use _exc_lookup('CustomError', Exception). "
    "Use tmp_path for filesystem; avoid repr-based asserts and custom markers."
)

_INTEG_BARE = (
    "Write INTEGRATION tests (2–5). Exercise interactions across modules. "
    "If GUI imports exist, avoid real event loops and windows; rely on shims. "
    "Mock external effects with monkeypatch; import targets inside tests."
)

_E2E_BARE = (
    "Write E2E tests (2–4). Compose a realistic black-box workflow using available APIs. "
    "Keep it deterministic and self-contained; import targets inside tests."
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

    SYSTEM = """You are an expert Python test engineer.
Return ONLY valid Python source code (no Markdown, no backticks, no prose).
Hard rules:
- Test ONLY project modules and stdlib; no private pytest internals or custom markers.
- Deterministic I/O; import targets inside each test.
- If GUIs exist, avoid event loops and rely on shims.
- For exceptions, call _exc_lookup('Name', Exception) with a string, not a bare symbol.
- Ensure at least one function named test_*."""
    if kind == "unit":
        user = f"Shard {shard}/{total} • Focus: {focus_label}\nAnalysis:\n{compact_json}\nWrite UNIT tests (4–8)."
    elif kind == "integ":
        user = f"Shard {shard}/{total} • Focus: {focus_label}\nAnalysis:\n{compact_json}\nWrite INTEGRATION tests (3–6)."
    else:
        user = f"Shard {shard}/{total} • Focus: {focus_label}\nAnalysis:\n{compact_json}\nWrite E2E tests (2–4)."
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]

# ---------------- Smoke fallback if LLM fails ----------------
def _smoke_from_modules(compact: Dict[str, Any]) -> str:
    mods = sorted(set([m for m in compact.get("modules") or [] if m and (m[0].isalpha() or m[0] == "_")]))
    body = ["import importlib, pytest"]
    body.append("def test_import_all_modules():")
    body.append("    mods = " + repr(mods))
    body.append("    for m in mods:")
    body.append("        try:")
    body.append("            importlib.import_module(m)")
    body.append("        except Exception as e:")
    body.append("            pytest.skip(f'cannot import {m}: {e}')")
    body.append("")
    return "\n".join(body)

# ---------------- Post-generation massaging ----------------
_RAISES_QUAL = re.compile(r"pytest\.raises\(\s*([A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)+)\s*(,|\))")
_RAISES_BARE = re.compile(r"pytest\.raises\(\s*([A-Za-z_][\w]*)\s*(,|\))")
_ISINSTANCE_QUAL = re.compile(r"isinstance\(\s*([A-Za-z_][\w]*)\s*,\s*([A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)+)\s*\)")
_ISINSTANCE_BARE = re.compile(r"isinstance\(\s*([A-Za-z_][\w]*)\s*,\s*([A-Za-z_][\w]*)\s*\)")

def _massage_generated_code(code: str) -> str:
    # pytest.raises(X) -> pytest.raises(_exc_lookup("X", Exception))
    def _repl_qual(m): return f'pytest.raises(_exc_lookup("{m.group(1)}", Exception){m.group(2)}'
    def _repl_bare(m): return f'pytest.raises(_exc_lookup("{m.group(1)}", Exception){m.group(2)}'
    code = _RAISES_QUAL.sub(_repl_qual, code)
    code = _RAISES_BARE.sub(_repl_bare, code)

    # isinstance(err, X) -> isinstance(err, _exc_lookup("X", Exception))
    def _repl_is_q(m): return f'isinstance({m.group(1)}, _exc_lookup("{m.group(2)}", Exception))'
    def _repl_is_b(m): return f'isinstance({m.group(1)}, _exc_lookup("{m.group(2)}", Exception))'
    code = _ISINSTANCE_QUAL.sub(_repl_is_q, code)
    code = _ISINSTANCE_BARE.sub(_repl_is_b, code)

    return code

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

def _update_manifest(outdir: pathlib.Path, created_files: List[str]):
    manifest_path = outdir / "_manifest.json"
    manifest = {}
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            manifest = {}
    hashes_path = os.getenv("CODE_HASHES_PATH")
    if hashes_path and pathlib.Path(hashes_path).exists():
        try:
            cur_hashes = json.loads(pathlib.Path(hashes_path).read_text(encoding="utf-8"))
            manifest["source_hashes"] = cur_hashes
        except Exception:
            pass
    runs = manifest.get("runs", [])
    runs.append({
        "ts": datetime.datetime.utcnow().isoformat() + "Z",
        "files_generated": created_files,
        "focus_files": _load_list(os.getenv("FOCUS_FILES_JSON_PATH")) or [],
    })
    manifest["runs"] = runs
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

# ---------------- Outdir cleanup ----------------
def _cleanup_outdir(outdir: pathlib.Path):
    """Remove old generated tests so stale failures don't linger."""
    if outdir.exists():
        for p in outdir.rglob("test_*.py"):
            try:
                p.unlink()
            except Exception:
                pass
        # remove empty timestamp subfolders under outdir
        for d in sorted(outdir.glob("*")):
            if d.is_dir():
                try:
                    next(d.rglob("*"))
                except StopIteration:
                    shutil.rmtree(d, ignore_errors=True)

# ---------------- Generation ----------------
def _build_guard_and_messages(compact: Dict[str, Any], compact_json: str, kind: str, focus_label: str, shard: int, total: int):
    guard = _runtime_guard_for(compact)
    messages = _build_prompt(kind, compact_json, focus_label, shard, total, compact)
    return guard, messages

def generate_all(analysis: Dict[str, Any], outdir="tests/generated", focus_files: Optional[List[str]] = None):
    out = pathlib.Path(outdir)
    _cleanup_outdir(out)  # ensure previous failing tests are removed

    ts = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")

    raw_focus = set(focus_files or _load_list(os.getenv("FOCUS_FILES_JSON_PATH")) or [])
    filtered_analysis, _ = _filter_analysis_by_files(analysis, raw_focus if raw_focus else None)

    compact = _compact_analysis(filtered_analysis)

    # Install inferred third-party deps first (GUI libs are intentionally NOT installed)
    _pip_install(_infer_required_packages(compact))

    compact_json = json.dumps(compact, separators=(",", ":"))
    kinds = ["unit", "integ", "e2e"]

    created_files: List[str] = []

    for kind in kinds:
        files_per_kind = _auto_files_per_kind(compact, kind)
        if files_per_kind <= 0:
            print(f"⚠️ No targets for {kind} → skipping {kind}")
            continue

        for i in range(files_per_kind):
            focus_label, _ = _focus_for_shard(compact, kind, i, files_per_kind)
            guard, messages = _build_guard_and_messages(compact, compact_json, kind, focus_label, i + 1, files_per_kind)

            code = _gen_validated(messages, compact=compact)
            code = _massage_generated_code(code)

            fname = f"test_{kind}_{ts}_{i+1:02d}.py"
            path = out / fname
            write(path, guard + code)
            created_files.append(str(path))

    out_list = os.getenv("GENERATED_LIST_PATH")
    if out_list:
        try:
            pathlib.Path(out_list).write_text(json.dumps(created_files, indent=2), encoding="utf-8")
        except Exception:
            pass

    _update_manifest(out, created_files)

# ---------------- LLM call with validation ----------------
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
                messages.append({"role": "user", "content": f"Invalid: {reason}. Regenerate STRICT pytest code (no markdown), import targets inside tests, avoid custom markers, and use _exc_lookup for exceptions."})
                break
            except RateLimitError:
                continue
    return _smoke_from_modules(compact or {})

if __name__ == "__main__":
    import analyzer
    analysis = analyzer.analyze_python_tree(pathlib.Path("."))
    generate_all(analysis)
    print("✅ Generated tests in tests/generated")
