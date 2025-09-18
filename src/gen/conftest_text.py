def conftest_text() -> str:
    return '''import os, sys, types, warnings, builtins, importlib, importlib.util, random
import pytest

warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=PendingDeprecationWarning)

# deterministic seeds
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

# path bootstrapping
_tr = os.environ.get("TARGET_ROOT") or "target"
if _tr and os.path.isdir(_tr):
    _parent = os.path.abspath(os.path.join(_tr, os.pardir))
    for p in (_parent, _tr):
        if p not in sys.path:
            sys.path.insert(0, p)
    if "target" not in sys.modules:
        _pkg = types.ModuleType("target"); _pkg.__path__ = [_tr]; sys.modules["target"] = _pkg

# headless GUI defaults + optional shims
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
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

# case-insensitive + path-based import fallback for local modules
_real_import = builtins.__import__
def _smart_import(name, *args, **kwargs):
    try:
        return _real_import(name, *args, **kwargs)
    except ModuleNotFoundError:
        base = _tr or "target"
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
