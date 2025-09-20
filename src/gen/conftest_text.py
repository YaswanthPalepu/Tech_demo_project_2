def conftest_text() -> str:
    return r'''import os, sys, types, warnings, builtins, importlib, importlib.util, random, re, pathlib
import pytest

warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=PendingDeprecationWarning)

# --- DB defaults so import-time engines don't crash ---
# Use a file-based SQLite so multiple imports share the same DB.
os.environ.setdefault("DATABASE_URL", "sqlite:///./_testgen.db")
os.environ.setdefault("SQLALCHEMY_DATABASE_URL", os.environ["DATABASE_URL"])
# Some projects read from .env at import time; keep it simple here.

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

# ---- rest of your existing file unchanged (Django auto-setup, GUI shims, smart import) ----
# ... keep everything else exactly as you have it ...
'''
