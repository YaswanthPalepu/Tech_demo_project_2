import importlib.util, pytest

# --- UNIVERSAL BOOTSTRAP (generated) ---
import os, sys, importlib as _importlib, importlib.util as _iu, importlib.machinery as _im, types as _types, pytest as _pytest, builtins as _builtins

# Ensure target root importable
_target = os.environ.get("TARGET_ROOT") or os.environ.get("ANALYZE_ROOT") or "target"
if _target and _target not in sys.path:
    sys.path.insert(0, _target)
_TARGET_ABS = os.path.abspath(_target)

# Provide a helper for exception lookups used by generated tests
def _exc_lookup(name, default):
    try:
        mod_name, _, cls_name = str(name).rpartition(".")
        if mod_name:
            mod = __import__(mod_name, fromlist=[cls_name])
            return getattr(mod, cls_name, default)
        return getattr(sys.modules.get("builtins"), str(name), default)
    except Exception:
        return default

# ---- Generic module attribute adapter (PEP 562 __getattr__) for target modules ----
# If a module 'm' lacks attribute 'foo', we try to find a public class in 'm' that
# provides 'foo' as an instance attribute/method via a no-arg constructor. First hit wins.
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
            raise AttributeError(f"module {_m.__name__!r} has no attribute {name!r}")
        _m.__getattr__ = __getattr__
        _ADAPTED_MODULES.add(_m.__name__)
    except Exception:
        pass

# Wrap builtins.__import__ so every target module gets the adapter automatically
_orig_import = _builtins.__import__
def _import_with_adapter(name, globals=None, locals=None, fromlist=(), level=0):
    mod = _orig_import(name, globals, locals, fromlist, level)
    try:
        # Ensure top-level module object is adapted
        top = mod
        if isinstance(mod, _types.ModuleType):
            _attach_module_getattr(top)
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

# Safe DB defaults
for _k in ("DATABASE_URL","DB_URL","SQLALCHEMY_DATABASE_URI"):
    _v = os.environ.get(_k)
    if not _v or "://" not in str(_v):
        os.environ[_k] = "sqlite:///:memory:"

# Minimal Django config (only if actually installed)
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
                DATABASES={"default": {"ENGINE":"django.db.backends.sqlite3","NAME":":memory:"}},
            )
            django.setup()
except Exception:
    pass

# SQLAlchemy safe create_engine
try:
    if _iu.find_spec("sqlalchemy") is not None:
        import sqlalchemy as _s_sa
        from sqlalchemy.exc import ArgumentError as _s_ArgErr
        _s_orig_create_engine = _s_sa.create_engine
        def _s_safe_create_engine(url, *args, **kwargs):
            try_url = url
            try:
                if not isinstance(try_url, str) or "://" not in try_url:
                    try_url = os.environ.get("DATABASE_URL") or os.environ.get("DB_URL") or os.environ.get("SQLALCHEMY_DATABASE_URI") or "sqlite:///:memory:"
                return _s_orig_create_engine(try_url, *args, **kwargs)
            except _s_ArgErr:
                return _s_orig_create_engine("sqlite:///:memory:", *args, **kwargs)
        _s_sa.create_engine = _s_safe_create_engine
except Exception:
    pass

# collections.abc compatibility for older libs (Py3.10+)
try:
    import collections as _collections
    import collections.abc as _abc
    for _n in ("Mapping","MutableMapping","Sequence","MutableSequence","Set","MutableSet","Iterable"):
        if not hasattr(_collections, _n) and hasattr(_abc, _n):
            setattr(_collections, _n, getattr(_abc, _n))
except Exception:
    pass

# Py2 alias maps if imported
_PY2_ALIASES = {'ConfigParser': 'configparser', 'Queue': 'queue', 'StringIO': 'io', 'cStringIO': 'io', 'urllib2': 'urllib.request'}
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

# ---- Qt family stubs (PyQt5/6, PySide2/6) for headless CI ----
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

        # ---- QtCore minimal API ----
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

        # ---- QtGui minimal API ----
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

        # ---- QtWidgets minimal API ----
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

        # Mirror common widget symbols into QtGui to tolerate odd imports
        for _name in ("QApplication","QWidget","QLabel","QLineEdit","QTextEdit","QPushButton","QMessageBox","QFileDialog","QFormLayout","QGridLayout"):
            setattr(_gui, _name, getattr(_widgets, _name))

# ---- Generic stub for other missing third-party tops (non-stdlib, non-local) ----
_THIRD_PARTY_TOPS = ['PyQt5']
for _name in list(_THIRD_PARTY_TOPS):
    _top = (_name or "").split(".")[0]
    if not _top:
        continue
    if _top in sys.modules:
        continue
    if _safe_find_spec(_top) is not None:
        continue
    if _top in ('PyQt5', 'PyQt6', 'PySide2', 'PySide6'):
        continue
    _m = _types.ModuleType(_top)
    _m.__spec__ = _im.ModuleSpec(_top, loader=None, is_package=False)
    sys.modules[_top] = _m

# --- /UNIVERSAL BOOTSTRAP ---

import inspect
import sys
import io
import os
import builtins
import pytest

def _exc_lookup(name, default):
    # search loaded modules for an exception class with given name
    for m in list(sys.modules.values()):
        try:
            if not m:
                continue
            attr = getattr(m, name, None)
            if isinstance(attr, type) and issubclass(attr, Exception):
                return attr
        except Exception:
            continue
    # fallback to builtins
    return getattr(builtins, name, default)

def _try_call_variants(func, args_variants):
    last_exc = None
    for args, kwargs in args_variants:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            last_exc = e
            continue
    # re-raise the last exception for visibility
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("No variants to call")

def _read_text_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

def _is_number_like(x):
    return isinstance(x, (int, float))

def _safe_getcallable(mod, name):
    obj = getattr(mod, name, None)
    if callable(obj):
        return obj
    return None

def _ensure_module_loaded(modname):
    # try import if not present
    if modname in sys.modules:
        return sys.modules[modname]
    return __import__(modname)

def _contains_any(text, substrings):
    return any(s in text for s in substrings)

def test_subtract_class_and_module_consistency():
    # Integration: class method and module-level function should behave the same
    Calculator = None
    calcmod = None
    # import inside test as required
    calcmod = __import__("Calculator")
    Calculator = getattr(calcmod, "Calculator", None)
    module_sub = getattr(calcmod, "subtract", None)

    a, b = 10, 3
    results = []

    if Calculator is not None and callable(Calculator):
        inst = Calculator()
        # prefer method if exists
        if hasattr(inst, "subtract"):
            res = inst.subtract(a, b)
            results.append(res)
            assert _is_number_like(res), "Calculator.subtract should return a number"
    if callable(module_sub):
        res2 = module_sub(a, b)
        results.append(res2)
        assert _is_number_like(res2), "module.subtract should return a number"

    # At least one implementation must exist
    assert results, "No subtract implementation found in Calculator module"

    # If we have more than one result, they should be equal
    if len(results) > 1:
        assert results[0] == results[1], "Class and module subtract results diverge"

    # Verify arithmetic correctness for a representative case
    assert results[0] == a - b

def test_save_history_writes_file(tmp_path):
    # Integration: ensure save_history can write a provided history to disk.
    ui_mod = __import__("SimpleCalculatorPyQt1")
    save_history = _safe_getcallable(ui_mod, "save_history")
    assert save_history is not None, "save_history not found in SimpleCalculatorPyQt1"

    # prepare a simple history
    history = [
        "2 + 3 = 5",
        "10 - 4 = 6",
        "6 * 7 = 42"
    ]
    out_path = tmp_path / "history_out.txt"

    # Try several plausible call signatures for save_history to be robust
    variants = []
    # common: save_history(history, filename)
    variants.append(((history, str(out_path)), {}))
    # alternate: save_history(filename, history)
    variants.append(((str(out_path), history), {}))
    # some implementations may take a file-like object
    try:
        fobj = open(str(out_path), "w", encoding="utf-8")
        variants.append(((history, fobj), {}))
    except Exception:
        fobj = None
    # single-arg filename
    variants.append(((str(out_path),), {}))
    # single-arg history
    variants.append(((history,), {}))

    try:
        _try_call_variants(save_history, variants)
    finally:
        if fobj:
            try:
                fobj.close()
            except Exception:
                pass

    # Now check that file exists and contains at least one of the history entries
    assert out_path.exists(), "save_history did not create the output file"

    content = _read_text_file(str(out_path))
    # At minimum, file should contain some representation of our history items
    assert _contains_any(content, history), "Saved file does not contain expected history entries"

def test_build_history_with_calculator_and_save(tmp_path):
    # Integration: use Calculator operations to build a history and persist with save_history
    calcmod = __import__("Calculator")
    ui_mod = __import__("SimpleCalculatorPyQt1")

    Calculator = getattr(calcmod, "Calculator", None)
    module_add = getattr(calcmod, "add", None)
    module_sub = getattr(calcmod, "subtract", None)
    module_mul = getattr(calcmod, "multiply", None)

    # Build history by trying various available APIs
    history = []

    # Helper to append formatted entry
    def add_entry(expr, result):
        history.append(f"{expr} = {result}")

    # Try using class if present
    if Calculator is not None and callable(Calculator):
        inst = Calculator()
        # attempt add/sub/mul methods on instance
        for name in ("add", "subtract", "multiply"):
            if hasattr(inst, name):
                fn = getattr(inst, name)
                try:
                    res = fn(8, 2)
                    add_entry(f"8 { {'add':'+','subtract':'-','multiply':'*'}[name] } 2", res)
                except Exception:
                    pass

    # Try module-level functions as fallback
    if callable(module_add):
        try:
            res = module_add(1, 2)
            add_entry("1 + 2", res)
        except Exception:
            pass
    if callable(module_sub):
        try:
            res = module_sub(5, 3)
            add_entry("5 - 3", res)
        except Exception:
            pass
    if callable(module_mul):
        try:
            res = module_mul(4, 6)
            add_entry("4 * 6", res)
        except Exception:
            pass

    # Ensure we have built some history
    assert history, "No history entries could be built from Calculator API"

    save_history = _safe_getcallable(ui_mod, "save_history")
    assert save_history is not None, "save_history not found in SimpleCalculatorPyQt1"

    out_path = tmp_path / "calc_history.txt"

    # Try likely signatures
    variants = [
        ((history, str(out_path)), {}),
        ((str(out_path), history), {}),
        ((history,), {}),
        ((str(out_path),), {}),
    ]

    _try_call_variants(save_history, variants)

    assert out_path.exists(), "save_history did not create file for calculator history"
    content = _read_text_file(str(out_path))
    # Ensure each entry we generated appears in the saved output (at least partially)
    for entry in history:
        assert any(part in content for part in entry.split(" = ")), f"Entry '{entry}' not found in saved output"


# --- canonical PyQt5 shim (Widgets + Gui minimal) ---
def __qt_shim_canonical():
    import types as _t
    PyQt5 = _t.ModuleType("PyQt5")
    QtWidgets = _t.ModuleType("PyQt5.QtWidgets")
    QtGui = _t.ModuleType("PyQt5.QtGui")

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

    # QtGui bits commonly imported
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

    QtWidgets.QApplication = QApplication
    QtWidgets.QWidget = QWidget
    QtWidgets.QLabel = QLabel
    QtWidgets.QLineEdit = QLineEdit
    QtWidgets.QTextEdit = QTextEdit
    QtWidgets.QPushButton = QPushButton
    QtWidgets.QMessageBox = QMessageBox
    QtWidgets.QFileDialog = QFileDialog
    QtWidgets.QFormLayout = QFormLayout
    QtWidgets.QGridLayout = QGridLayout

    QtGui.QFont = QFont
    QtGui.QDoubleValidator = QDoubleValidator
    QtGui.QIcon = QIcon
    QtGui.QPixmap = QPixmap

    return PyQt5, QtWidgets, QtGui

_make_pyqt5_shim = __qt_shim_canonical
_make_pyqt_shim = __qt_shim_canonical
_make_pyqt_shims = __qt_shim_canonical
_make_qt_shims = __qt_shim_canonical
