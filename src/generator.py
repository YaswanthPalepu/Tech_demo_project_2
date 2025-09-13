# generator.py
import os, sys, json, pathlib, datetime, time, re, ast, math, subprocess, importlib.util, types as _types, random, shutil
from typing import Dict, Any, List, Tuple, Set, Optional
from openai import AzureOpenAI, RateLimitError  # openai>=1.0.0
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
        content = file_path.read_text(encoding='utf-8')
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)):
                start_line = node.lineno - 1
                end_line = node.end_lineno if hasattr(node, 'end_lineno') else start_line + 1
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
        current_state[rel_path] = {
            "file_hash": _compute_content_hash(py_file.read_text(encoding='utf-8')),
            "signatures": signatures
        }
    added_or_modified, deleted, unchanged = set(), set(), set()
    for file_path, current_info in current_state.items():
        if file_path not in previous_state:
            added_or_modified.add(file_path)
        else:
            prev_info = previous_state[file_path]
            if current_info["file_hash"] != prev_info.get("file_hash", ""):
                prev_sigs = prev_info.get("signatures", {})
                curr_sigs = current_info["signatures"]
                if prev_sigs != curr_sigs:
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
            content = test_file.read_text(encoding='utf-8')
            if (source_stem in content or 
                source_file.replace('/', '.').replace('.py', '') in content):
                related_tests.append(test_file)
        except Exception:
            continue
    return related_tests

def _cleanup_deleted_tests(outdir: pathlib.Path, deleted_files: Set[str]):
    for deleted_file in deleted_files:
        related_tests = _find_related_test_files(outdir, deleted_file)
        for test_file in related_tests:
            try:
                print(f"🗑️ Removing test file for deleted source: {test_file}")
                test_file.unlink()
            except Exception as e:
                print(f"Warning: Could not remove {test_file}: {e}")

# ---------------------- conftest: compat shims ----------------------

def _create_enhanced_conftest(outdir: pathlib.Path) -> str:
    conftest_content = '''import pytest
import sys
import os
import warnings

warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=PendingDeprecationWarning)

project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

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

def _fix_collections_compatibility():
    try:
        import collections
        import collections.abc as abc
        for name in [
            'Mapping','MutableMapping','Sequence','Iterable','Container','MutableSequence',
            'Set','MutableSet','Iterator','Generator','Callable','Collection'
        ]:
            if not hasattr(collections, name) and hasattr(abc, name):
                setattr(collections, name, getattr(abc, name))
    except ImportError:
        pass

def _fix_flask_compatibility():
    try:
        import flask
        if not hasattr(flask, 'escape'):
            try:
                from markupsafe import escape
                flask.escape = escape
            except Exception:
                pass
        # Legacy flask_sqlalchemy expects __ident_func__ on context stacks
        try:
            import threading
            from flask import _app_ctx_stack, _request_ctx_stack
            for _stack in (_app_ctx_stack, _request_ctx_stack):
                if _stack is not None and not hasattr(_stack, "__ident_func__"):
                    _stack.__ident_func__ = getattr(threading, "get_ident", None) or (lambda: 0)
        except Exception:
            pass
    except ImportError:
        pass

def _fix_marshmallow_compatibility():
    try:
        import marshmallow as _mm
        if not hasattr(_mm, "__version__"):
            _mm.__version__ = "4"
    except Exception:
        pass

_fix_jinja2_compatibility()
_fix_collections_compatibility()
_fix_flask_compatibility()
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
    funcs = sorted(analysis.get("functions", []), key=lambda x: x.get("file", ""))
    clss = sorted(analysis.get("classes", [])   , key=lambda x: x.get("file", ""))
    routes = sorted(analysis.get("routes", [])  , key=lambda x: x.get("file", ""))
    return {
        "functions": _dedupe_keep(funcs, "name", soft_cap),
        "classes": _dedupe_keep(clss, "name", max(30, soft_cap // 2)),
        "routes": _dedupe_keep(routes, "handler", max(30, soft_cap // 2)),
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
    "jwt": "PyJWT", "markupsafe": "MarkupSafe",
}
VERSION_CONSTRAINTS: Dict[str, str] = {}

DENY_INFER: Set[str] = {
    *(p.strip().lower() for p in os.getenv("TESTGEN_DENY_PKGS", "models,relations").split(",") if p.strip())
}

VALID_PIP_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
BAD_GENERIC_TOPS = {
    "models", "model", "views", "view", "urls", "settings", "config", "configs",
    "tests", "test", "schemas", "schema", "forms", "admin", "migrations",
    "apps", "serializers", "permissions", "filters", "routers", "services",
    "repository", "repositories", "managers", "helpers", "utils"
}
DENY_TOPS = {
    "__future__", "__main__", "__builtin__", "builtins",
    "typing", "types", "dataclasses", "importlib", "asyncio", "json", "re", "os", "sys", "pathlib",
    "logging", "argparse", "functools", "itertools", "collections", "subprocess", "datetime", "time",
    "math", "decimal", "fractions", "statistics", "sqlite3", "http", "urllib", "hmac", "hashlib",
    "base64", "csv", "glob", "shutil", "tempfile", "inspect", "traceback", "enum", "textwrap",
    "pprint", "string",
    "ConfigParser", "Queue", "HTMLParser", "StringIO",
} | BAD_GENERIC_TOPS

def _is_stdlib(name: str) -> bool:
    try:
        stdmods = getattr(sys, "stdlib_module_names", None)
        if stdmods:
            return name in stdmods
        return name in {
            "os","sys","re","json","pathlib","math","itertools","functools","typing","subprocess",
            "datetime","time","collections","dataclasses","ast","logging","unittest","argparse",
            "asyncio","multiprocessing","threading","sqlite3","email","http","urllib","hashlib",
            "hmac","base64","statistics","random","fractions","decimal","csv","shutil","tempfile",
            "glob","inspect","traceback","textwrap","string","pprint","enum","types"
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
        f = entry.get("file") or ""
        fn = _norm_rel(f)
        if fn in focus_norm: return True
        if any(fn.endswith("/" + rel) for rel in focus_norm): return True
        if pathlib.Path(fn).name in focus_basenames: return True
        return False
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
    tops: List[str] = []
    for m in compact.get("modules") or []:
        top = (m.split(".")[0] or "").strip()
        if top:
            tops.append(top)
    tops = sorted(set(tops))
    tops_lit = repr(tops)
    include_qt = any(t.startswith(("PyQt", "PySide")) for t in tops)
    py2_alias_map_lit = repr({"ConfigParser":"configparser","Queue":"queue","StringIO":"io","cStringIO":"io","urllib2":"urllib.request"})
    qt_block = f"""
for __qt_root in ["PyQt5","PyQt6","PySide2","PySide6"]:
    if __qt_root not in _THIRD_PARTY_TOPS:
        continue
    if _safe_find_spec(__qt_root) is None:
        _pkg=_ensure_pkg(__qt_root,True); _core=_ensure_pkg(__qt_root+".QtCore",False); _gui=_ensure_pkg(__qt_root+".QtGui",False); _widgets=_ensure_pkg(__qt_root+".QtWidgets",False)
        class QObject: pass
        def pyqtSignal(*a, **k): return object()
        def pyqtSlot(*a, **k):
            def _decorator(fn): return fn
            return _decorator
        class QCoreApplication: 
            def __init__(self,*a,**k): pass
            def exec_(self): return 0
            def exec(self): return 0
        _core.QObject=QObject; _core.pyqtSignal=pyqtSignal; _core.pyqtSlot=pyqtSlot; _core.QCoreApplication=QCoreApplication
        class QFont:
            def __init__(self,*a,**k): pass
        class QDoubleValidator:
            def __init__(self,*a,**k): pass
            def setBottom(self,*a,**k): pass
            def setTop(self,*a,**k): pass
        class QIcon: 
            def __init__(self,*a,**k): pass
        class QPixmap:
            def __init__(self,*a,**k): pass
        _gui.QFont=QFont; _gui.QDoubleValidator=QDoubleValidator; _gui.QIcon=QIcon; _gui.QPixmap=QPixmap
        class QApplication:
            def __init__(self,*a,**k): pass
            def exec_(self): return 0
            def exec(self): return 0
        class QWidget: 
            def __init__(self,*a,**k): pass
        class QLabel(QWidget):
            def __init__(self,*a,**k): super().__init__(); self._text=""
            def setText(self,t): self._text=str(t)
            def text(self): return self._text
        class QLineEdit(QWidget):
            def __init__(self,*a,**k): super().__init__(); self._text=""
            def setText(self,t): self._text=str(t)
            def text(self): return self._text
            def clear(self): self._text=""
        class QTextEdit(QLineEdit): pass
        class QPushButton(QWidget):
            def __init__(self,*a,**k): super().__init__()
        class QMessageBox:
            @staticmethod
            def warning(*a, **k): return None
            @staticmethod
            def information(*a, **k): return None
            @staticmethod
            def critical(*a, **k): return None
        class QFileDialog:
            @staticmethod
            def getSaveFileName(*a, **k): return ("history.txt","")
            @staticmethod
            def getOpenFileName(*a, **k): return ("history.txt","")
        class QFormLayout:
            def __init__(self,*a,**k): pass
            def addRow(self,*a,**k): pass
        class QGridLayout(QFormLayout):
            def addWidget(self,*a,**k): pass
        _widgets.QApplication=QApplication; _widgets.QWidget=QWidget; _widgets.QLabel=QLabel; _widgets.QLineEdit=QLineEdit; _widgets.QTextEdit=QTextEdit
        _widgets.QPushButton=QPushButton; _widgets.QMessageBox=QMessageBox; _widgets.QFileDialog=QFileDialog; _widgets.QFormLayout=QFormLayout; _widgets.QGridLayout=QGridLayout
        for _name in ("QApplication","QWidget","QLabel","QLineEdit","QTextEdit","QPushButton","QMessageBox","QFileDialog","QFormLayout","QGridLayout"):
            setattr(_gui,_name,getattr(_widgets,_name))
""" if include_qt else ""
    return f'''# --- ENHANCED UNIVERSAL BOOTSTRAP ---
import os, sys, importlib as _importlib, importlib.util as _iu, importlib.machinery as _im, types as _types, pytest as _pytest, builtins as _builtins
import warnings
STRICT = os.getenv("TESTGEN_STRICT", "1").lower() in ("1","true","yes")
STRICT_FAIL = os.getenv("TESTGEN_STRICT_FAIL","0").lower() in ("1","true","yes")
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=PendingDeprecationWarning)
_target = os.environ.get("TARGET_ROOT") or os.environ.get("ANALYZE_ROOT") or "target"
if _target and os.path.exists(_target):
    if _target not in sys.path: sys.path.insert(0, _target)
    try: os.chdir(_target)
    except Exception: pass
_TARGET_ABS = os.path.abspath(_target)
def _exc_lookup(name, default):
    try:
        mod_name, _, cls_name = str(name).rpartition(".")
        if mod_name:
            mod = __import__(mod_name, fromlist=[cls_name])
            return getattr(mod, cls_name, default)
        return getattr(sys.modules.get("builtins"), str(name), default)
    except Exception:
        return default
def _apply_compatibility_fixes():
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
    try:
        import flask
        if not hasattr(flask, "escape"):
            try:
                from markupsafe import escape
                flask.escape = escape
            except Exception:
                pass
        try:
            import threading
            from flask import _app_ctx_stack, _request_ctx_stack
            for _stack in (_app_ctx_stack, _request_ctx_stack):
                if _stack is not None and not hasattr(_stack, "__ident_func__"):
                    _stack.__ident_func__ = getattr(threading, "get_ident", None) or (lambda: 0)
        except Exception:
            pass
    except ImportError:
        pass
    try:
        import collections as _collections, collections.abc as _abc
        for _n in ('Mapping','MutableMapping','Sequence','Iterable','Container','MutableSequence','Set','MutableSet','Iterator','Generator','Callable','Collection'):
            if not hasattr(_collections, _n) and hasattr(_abc, _n):
                setattr(_collections, _n, getattr(_abc, _n))
    except Exception:
        pass
    try:
        import marshmallow as _mm
        if not hasattr(_mm, "__version__"):
            _mm.__version__ = "4"
    except Exception:
        pass
_apply_compatibility_fixes()
_ADAPTED_MODULES = set()
def _attach_module_getattr(_m):
    try:
        if getattr(_m, "__name__", None) in _ADAPTED_MODULES: return
        mfile = getattr(_m, "__file__", "") or ""
        if not mfile or not os.path.abspath(mfile).startswith(_TARGET_ABS + os.sep): return
        if hasattr(_m, "__getattr__"):
            _ADAPTED_MODULES.add(_m.__name__); return
        def __getattr__(name):
            for _nm, _obj in list(_m.__dict__.items()):
                if isinstance(_obj, type) and not _nm.startswith("_"):
                    try: _inst = _obj()
                    except Exception: continue
                    if hasattr(_inst, name):
                        _val = getattr(_inst, name)
                        try: setattr(_m, name, _val)
                        except Exception: pass
                        return _val
            raise AttributeError(f"module {{_m.__name__!r}} has no attribute {{name!r}}")
        _m.__getattr__ = __getattr__; _ADAPTED_MODULES.add(_m.__name__)
    except Exception:
        pass
if not STRICT:
    _orig_import = _builtins.__import__
    def _import_with_adapter(name, globals=None, locals=None, fromlist=(), level=0):
        mod = _orig_import(name, globals, locals, fromlist, level)
        try:
            if isinstance(mod, _types.ModuleType): _attach_module_getattr(mod)
            if fromlist:
                for attr in fromlist:
                    try:
                        sub = getattr(mod, attr, None)
                        if isinstance(sub, _types.ModuleType): _attach_module_getattr(sub)
                    except Exception: pass
        except Exception: pass
        return mod
    _builtins.__import__ = _import_with_adapter
try:
    if _iu.find_spec("django") is not None:
        import django
        from django.conf import settings as _dj_settings
        if not _dj_settings.configured:
            _dj_settings.configure(SECRET_KEY="test-key", DEBUG=True, ALLOWED_HOSTS=["*"], INSTALLED_APPS=[], DATABASES={{"default": {{"ENGINE":"django.db.backends.sqlite3","NAME":":memory:"}}}})
            django.setup()
except Exception: pass
_PY2_ALIASES = {py2_alias_map_lit}
for _old, _new in list(_PY2_ALIASES.items()):
    if _old in sys.modules: continue
    try:
        __import__(_new); sys.modules[_old] = sys.modules[_new]
    except Exception: pass
def _safe_find_spec(name):
    try: return _iu.find_spec(name)
    except Exception: return None
def _ensure_pkg(name, is_pkg=None):
    if name in sys.modules:
        m = sys.modules[name]
        if getattr(m, "__spec__", None) is None:
            m.__spec__ = _im.ModuleSpec(name, loader=None, is_package=(is_pkg if is_pkg is not None else ("." not in name)))
            if "." not in name and not hasattr(m, "__path__"): m.__path__ = []
        return m
    m = _types.ModuleType(name)
    if is_pkg is None: is_pkg = ("." not in name)
    if is_pkg and not hasattr(m, "__path__"): m.__path__ = []
    m.__spec__ = _im.ModuleSpec(name, loader=None, is_package=is_pkg)
    sys.modules[name] = m
    return m
_THIRD_PARTY_TOPS = {tops_lit}
{qt_block}
# --- /ENHANCED UNIVERSAL BOOTSTRAP ---
'''

# ---------------------- prompts: developer-style tests ----------------------

_SYSTEM_MIN = (
    "Return ONLY valid Python pytest tests. No Markdown, no explanations. "
    "Prefer module-level imports guarded by try/except ImportError: on ImportError call pytest.skip at module level. "
    "Use Arrange-Act-Assert structure with clear variable names. "
    "Use pytest.mark.parametrize for normal + edge cases; include boundary values and error paths. "
    "Use tmp_path/monkeypatch/unittest.mock for I/O, environment, and collaborators. "
    "No network, no external services, no private pytest internals, no custom markers. "
    "Assert concrete outputs, types, and state changes. "
    "For exceptions never assume custom names; use _exc_lookup('Name', Exception) when checking types. "
    "Skip ONLY on ImportError. Let logic/type/attribute/value errors FAIL to expose bugs. "
    "Never import modules via 'from pkg import __init__'; import the package/module directly."
)

_UNIT_DEV = (
    "Write UNIT tests (3-6) like a senior developer would. "
    "Focus on public functions/classes in the focus list. "
    "Cover happy path, boundary conditions, invalid inputs, and stateful methods. "
    "Prefer @pytest.mark.parametrize, AAA comments optional but keep structure clear."
)

_INTEG_DEV = (
    "Write INTEGRATION tests (2-5) crossing module boundaries where natural. "
    "Use monkeypatch/mocks to isolate external calls; test realistic flows and data seams."
)

_E2E_DEV = (
    "Write E2E-style black-box tests (2-4) composed from the public API only. "
    "Deterministic, self-contained, avoid GUI/event loops."
)

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

_RAISES_QUAL = re.compile(r"pytest\.raises\(\s*([A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)+)\s*(,|\))")
_RAISES_BARE = re.compile(r"pytest\.raises\(\s*([A-Za-z_][\w]*)\s*(,|\))")
_ISINSTANCE_QUAL = re.compile(r"isinstance\(\s*([A-Za-z_][\w]*)\s*,\s*([A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)+)\s*\)")
_ISINSTANCE_BARE = re.compile(r"isinstance\(\s*([A-Za-z_][\w]*)\s*,\s*([A-Za-z_][\w]*)\s*\)")

_SKIP_ANY_EXC_RE = re.compile(
    r"except\s+Exception\s+as\s+e:\s*\n\s*pytest\.skip\((.*?)\)",
    flags=re.DOTALL
)

def _massage_generated_code(code: str) -> str:
    # Normalize exception references
    def _repl_qual(m): return f'pytest.raises(_exc_lookup("{m.group(1)}", Exception){m.group(2)}'
    def _repl_bare(m): return f'pytest.raises(_exc_lookup("{m.group(1)}", Exception){m.group(2)}'
    code = _RAISES_QUAL.sub(_repl_qual, code)
    code = _RAISES_BARE.sub(_repl_bare, code)

    def _repl_is_q(m): return f'isinstance({m.group(1)}, _exc_lookup("{m.group(2)}", Exception))'
    def _repl_is_b(m): return f'isinstance({m.group(1)}, _exc_lookup("{m.group(2)}", Exception))'
    code = _ISINSTANCE_QUAL.sub(_repl_is_q, code)
    code = _ISINSTANCE_BARE.sub(_repl_is_b, code)

    # ImportError-only skipping
    code = _SKIP_ANY_EXC_RE.sub(
        r"except ImportError as e:\n        pytest.skip(\1)\n    except Exception:\n        raise",
        code
    )

    # Fix bad pattern: "from pkg.subpkg import __init__ as alias" -> "import pkg.subpkg as alias"
    code = re.sub(
        r'^\s*from\s+([A-Za-z_][\w\.]*)\s+import\s+__init__\s+as\s+([A-Za-z_]\w*)\s*$',
        r'import \1 as \2',
        code,
        flags=re.MULTILINE,
    )
    # Fix "from pkg.subpkg import __init__"
    code = re.sub(
        r'^\s*from\s+([A-Za-z_][\w\.]*)\s+import\s+__init__\s*$',
        r'import \1',
        code,
        flags=re.MULTILINE,
    )

    # Tidy boolean asserts
    code = re.sub(r"assert\s+bool\((.+?)\)", r"assert bool(\1) is True", code)

    # Lightweight AAA hint
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
        related_tests = _find_related_test_files(outdir, modified_file)
        for test_file in related_tests:
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
            [f"if importlib.util.find_spec('{m}') is None:\n    pytest.skip('{m} not installed; skipping module', allow_module_level=True)" for m in needed]
        ) + "\n"
    bootstrap = _enhanced_universal_bootstrap(compact)
    return ("import importlib.util, pytest\n" + checks + "\n" + bootstrap + "\n")

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
                        "Guard imports (skip on ImportError only), prefer parametrize & boundaries, "
                        "use tmp_path/monkeypatch/mock, no private pytest internals, "
                        "use _exc_lookup for exception types. Never import via 'from pkg import __init__'."
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
