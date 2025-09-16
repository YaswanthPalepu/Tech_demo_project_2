def conftest_text() -> str:
    return '''import pytest, sys, os, warnings, types as _types
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=PendingDeprecationWarning)

project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

_tr = os.environ.get("TARGET_ROOT", "target")
if _tr and os.path.isdir(_tr):
    _parent = os.path.abspath(os.path.join(_tr, os.pardir))
    for p in (_parent, _tr):
        if p not in sys.path:
            sys.path.insert(0, p)
    if "target" not in sys.modules:
        _pkg = _types.ModuleType("target")
        _pkg.__path__ = [_tr]
        sys.modules["target"] = _pkg

# Compatibility fixes
def _fix():
    try:
        import jinja2
        if not hasattr(jinja2,'Markup'):
            from markupsafe import Markup, escape
            jinja2.Markup = Markup
            if not hasattr(jinja2,'escape'):
                jinja2.escape = escape
    except Exception: pass
    try:
        import collections, collections.abc as abc
        for n in ['Mapping','MutableMapping','Sequence','Iterable','Container','MutableSequence','Set','MutableSet','Iterator','Generator','Callable','Collection']:
            if not hasattr(collections,n) and hasattr(abc,n):
                setattr(collections,n,getattr(abc,n))
    except Exception: pass
_fix()

@pytest.fixture
def expected_status(): return 404

@pytest.fixture
def expected_status_code(expected_status): return expected_status

@pytest.fixture
def CalcError(): return ZeroDivisionError

os.environ.setdefault('WTF_CSRF_ENABLED', 'False')
'''
