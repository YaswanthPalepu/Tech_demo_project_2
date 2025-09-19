def conftest_text() -> str:
    return r'''import os, sys, types, warnings, builtins, importlib, importlib.util, random, re, pathlib
import pytest

warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=PendingDeprecationWarning)

# ----------------------------
# Deterministic seeds
# ----------------------------
@pytest.fixture(autouse=True)
def _deterministic_seed():
    random.seed(1337)
    try:
        import numpy as _np
        _np.random.seed(1337)
    except Exception:
        pass
    try:
        import torch as _torch
        _torch.manual_seed(1337)
    except Exception:
        pass

# ----------------------------
# Path bootstrapping
# ----------------------------
_TR = os.environ.get("TARGET_ROOT") or "target"
if _TR and os.path.isdir(_TR):
    _parent = os.path.abspath(os.path.join(_TR, os.pardir))
    for p in (_parent, _TR):
        if p not in sys.path:
            sys.path.insert(0, p)
    if "target" not in sys.modules:
        _pkg = types.ModuleType("target"); _pkg.__path__ = [_TR]; sys.modules["target"] = _pkg

# Headless GUI defaults + optional shims
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# ----------------------------
# Make sqlalchemy.Binary available for legacy code using db.Binary(...)
# ----------------------------
try:
    import sqlalchemy as _sa
    # Many older Flask projects expect db.Binary to exist; newest SQLAlchemy only has LargeBinary
    if not hasattr(_sa, "Binary") and hasattr(_sa, "LargeBinary"):
        _sa.Binary = _sa.LargeBinary  # type: ignore[attr-defined]
except Exception:
    pass

# ----------------------------
# Shim for flask_jwt_extended.jwt_optional removed in v4+
# ----------------------------
try:
    import flask_jwt_extended as _fje
    if not hasattr(_fje, "jwt_optional") and hasattr(_fje, "jwt_required"):
        from flask_jwt_extended import jwt_required
        def jwt_optional(fn=None, **kwargs):
            dec = jwt_required(optional=True)
            return dec(fn) if callable(fn) else dec
        _fje.jwt_optional = jwt_optional  # type: ignore[attr-defined]
except Exception:
    pass

# ----------------------------
# Auto-setup Django if a project is present
# ----------------------------
def _detect_django_settings():
    if os.environ.get("DJANGO_SETTINGS_MODULE"):
        return os.environ["DJANGO_SETTINGS_MODULE"]
    root = pathlib.Path(_TR if os.path.isdir(_TR) else ".").resolve()
    # Try manage.py first
    mpy = root / "manage.py"
    if mpy.exists():
        try:
            s = mpy.read_text(encoding="utf-8", errors="ignore")
            m = re.search(r"DJANGO_SETTINGS_MODULE\s*=\s*['\"]([^'\"]+)['\"]", s) \
                or re.search(r"setdefault\(\s*['\"]DJANGO_SETTINGS_MODULE['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)", s)
            if m:
                return m.group(1)
        except Exception:
            pass
    # Fallback: first non-migrations settings.py
    for p in root.rglob("settings.py"):
        if "migrations" in str(p) or "site-packages" in str(p):
            continue
        try:
            rel = p.relative_to(root)
            return ".".join(rel.with_suffix("").parts)
        except Exception:
            pass
    return ""

def _auto_setup_django():
    ds = _detect_django_settings()
    if not ds:
        return
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", ds)
    os.environ.setdefault("SECRET_KEY", "test-secret")
    # Keep it simple: ensure a DB exists if project uses dj-database-url/ENV
    os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
    try:
        import django
        django.setup()
    except Exception as e:
        warnings.warn(f"Django auto-setup failed: {e!r}")

try:
    _auto_setup_django()
except Exception:
    # Not a Django repo, or best-effort setup failed—tests may still run.
    pass

# ----------------------------
# Optional GUI shims
# ----------------------------
if os.environ.get("TESTGEN_ENABLE_GUI_SHIMS","0").lower() in ("1","true","yes"):
    def _shim_pyqt5():
        if importlib.util.find_spec("PyQt5") is not None:
            return
        mod = types.ModuleType("PyQt5"); sys.modules["PyQt5"] = mod
        for sub in ("QtWidgets","QtCore","QtGui"):
            m = types.ModuleType(f"PyQt5.{sub}")
            setattr(mod, sub, m)
            sys.modules[f"PyQt5.{sub}"] = m
            class _QWidget:
                def __init__(self,*a,**kw): pass
                def show(self): pass
            class _QApplication:
                def __init__(self,*a,**kw): pass
                def exec_(self): return 0
            setattr(m,"QWidget",_QWidget)
            setattr(m,"QApplication",_QApplication)
    _shim_pyqt5()

# ----------------------------
# Case-insensitive + path-based import fallback for local modules
# ----------------------------
_real_import = builtins.__import__
def _smart_import(name, *args, **kwargs):
    try:
        return _real_import(name, *args, **kwargs)
    except ModuleNotFoundError:
        base = _TR or "target"
        low = name.lower()
        if low != name:
            try:
                return _real_import(low, *args, **kwargs)
            except ModuleNotFoundError:
                pass
        for cand in (os.path.join(base, f"{name}.py"), os.path.join(base, f"{low}.py")):
            if os.path.isfile(cand):
                spec = importlib.util.spec_from_file_location(name, cand)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
                    sys.modules[name] = mod
                    return mod
        raise
builtins.__import__ = _smart_import
'''
