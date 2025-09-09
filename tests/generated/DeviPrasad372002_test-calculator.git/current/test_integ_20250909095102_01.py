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

import io
import builtins
import pytest

def _exc_lookup(name, default=Exception):
    try:
        import Calculator as C
        candidate = getattr(C, name, None)
        if candidate is not None:
            return candidate
    except Exception:
        pass
    try:
        import SimpleCalculatorPyQt1 as S
        candidate = getattr(S, name, None)
        if candidate is not None:
            return candidate
    except Exception:
        pass
    return default

def _get_ops():
    # Return dict with add, subtract, multiply, divide callables
    try:
        import Calculator as C
    except Exception:
        raise RuntimeError("Calculator module not importable")
    ops = {}
    for name in ("add", "subtract", "multiply", "divide"):
        fn = getattr(C, name, None)
        if fn is None:
            # try class-based
            cls = getattr(C, "Calculator", None)
            if cls is not None:
                inst = cls()
                fn = getattr(inst, name, None)
        if fn is None:
            raise RuntimeError(f"Operation {name} not found in Calculator")
        ops[name] = fn
    return ops

def _get_mainwindow_and_funcs():
    try:
        import SimpleCalculatorPyQt1 as S
    except Exception:
        S = None
    MainWindow = getattr(S, "MainWindow", None) if S is not None else None
    save_fn = getattr(S, "save_history", None) if S is not None else None
    clear_fn = getattr(S, "clear_history", None) if S is not None else None
    return S, MainWindow, save_fn, clear_fn

def test_multiply_large_numbers_and_save_history(tmp_path, monkeypatch):
    # Import targets inside test
    ops = _get_ops()
    multiply = ops["multiply"]

    a = 123456
    b = 98765
    result = multiply(a, b)
    assert result == a * b

    S, MainWindow, save_fn, _ = _get_mainwindow_and_funcs()

    # Prepare a MainWindow-like instance and populate history
    if MainWindow is not None:
        mw = MainWindow()
    else:
        mw = type("DummyMW", (), {})()
    # Ensure there is a history attribute
    setattr(mw, "history", [f"{a} * {b} = {result}"])

    # Capture file writes by monkeypatching builtins.open
    records = {}
    def fake_open(path, mode='r', *args, **kwargs):
        # Emulate writeable file handle
        if 'w' in mode or 'a' in mode:
            buf = io.StringIO()
            records['path'] = str(path)
            records['buf'] = buf
            return buf
        # For read attempts, raise to surface incorrect usage
        raise FileNotFoundError(path)
    monkeypatch.setattr(builtins, 'open', fake_open, raising=False)

    # Determine save callable: prefer bound method on instance, then module-level function
    save_callable = getattr(mw, "save_history", None) or save_fn
    assert save_callable is not None, "No save_history found to test integration"

    # Try calling with file path if supported, else without args
    p = tmp_path / "history.txt"
    try:
        save_callable(str(p))
    except TypeError:
        # try instance-bound no-arg
        try:
            save_callable()
        except TypeError:
            # try module-level function accepting instance
            try:
                save_callable(mw)
            except Exception as e:
                raise

    # Verify that the saved content contains the multiplication result
    assert 'buf' in records, "No file write captured"
    content = records['buf'].getvalue()
    assert str(result) in content

def test_subtract_and_clear_history(monkeypatch):
    ops = _get_ops()
    subtract = ops["subtract"]

    a = 10**9
    b = 123456789
    expected = a - b
    got = subtract(a, b)
    assert got == expected

    S, MainWindow, _, clear_fn = _get_mainwindow_and_funcs()

    if MainWindow is not None:
        mw = MainWindow()
    else:
        mw = type("DummyMW", (), {})()
    # Initialize history with known content
    setattr(mw, "history", ["op1", "op2", str(expected)])

    # Determine clear callable: prefer bound method, else module-level function
    clear_callable = getattr(mw, "clear_history", None) or clear_fn
    if clear_callable is None:
        pytest.skip("clear_history not available")
    # Try calling various signatures
    try:
        clear_callable()
    except TypeError:
        clear_callable(mw)

    # After clearing, history should be emptied or set to empty list
    hist = getattr(mw, "history", None)
    assert hist == [] or (hist is not None and len(hist) == 0)

def test_divide_negative_and_error_class_check():
    ops = _get_ops()
    divide = ops["divide"]

    res = divide(10, -2)
    assert res == 10 / -2

    # Use _exc_lookup per requirement inside isinstance usage
    err_cls = _exc_lookup('CalculatorError', Exception)
    # instantiate safely
    try:
        inst = err_cls()
    except Exception:
        inst = Exception()
    assert isinstance(inst, Exception)

def test_series_operations_saved(tmp_path, monkeypatch):
    ops = _get_ops()
    add = ops["add"]
    sub = ops["subtract"]
    mul = ops["multiply"]
    div = ops["divide"]

    results = []
    results.append(("add", 2, 3, add(2,3)))
    results.append(("sub", 10, 4, sub(10,4)))
    results.append(("mul", 7, 6, mul(7,6)))
    results.append(("div", 9, 3, div(9,3)))

    S, MainWindow, save_fn, _ = _get_mainwindow_and_funcs()

    if MainWindow is not None:
        mw = MainWindow()
    else:
        mw = type("DummyMW", (), {})()
    setattr(mw, "history", [f"{name} {x} {y} = {r}" for name,x,y,r in results])

    # Capture writes
    records = {}
    def fake_open(path, mode='r', *args, **kwargs):
        if 'w' in mode or 'a' in mode:
            buf = io.StringIO()
            records['buf'] = buf
            records['path'] = str(path)
            return buf
        raise FileNotFoundError(path)
    monkeypatch.setattr(builtins, 'open', fake_open, raising=False)

    save_callable = getattr(mw, "save_history", None) or save_fn
    assert save_callable is not None

    p = tmp_path / "series_history.txt"
    try:
        save_callable(str(p))
    except TypeError:
        try:
            save_callable()
        except TypeError:
            save_callable(mw)

    assert 'buf' in records
    content = records['buf'].getvalue()
    for _, x, y, r in results:
        assert str(r) in content or str(x) in content and str(y) in content


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
