# src/gen/conftest_text.py - COMPLETE drop-in replacement

def conftest_text() -> str:
    """Repo-agnostic conftest that PRIORITIZES REAL IMPORTS for actual coverage."""
    return '''"""
Professional pytest configuration for AI-generated tests.
CRITICAL CHANGE: Uses REAL imports first, stubs ONLY as absolute last resort.
This ensures tests execute actual code for real coverage metrics.
"""

import os
import sys
import warnings
import builtins
import random
import types
import importlib
import inspect
import pytest
from unittest.mock import patch

# ---------------- General test env ----------------
warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", category=PendingDeprecationWarning)
warnings.filterwarnings("ignore", category=UserWarning, module="pydantic")
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("DATABASE_URL", "sqlite:///./test.db")
os.environ.setdefault("LOG_LEVEL", "ERROR")

# Insert TARGET_ROOT if provided
TARGET_ROOT = os.environ.get("TARGET_ROOT", "")
if TARGET_ROOT and TARGET_ROOT not in sys.path:
    sys.path.insert(0, TARGET_ROOT)

@pytest.fixture(autouse=True)
def _deterministic_setup():
    random.seed(42)
    yield

# ---------------- CRITICAL: Minimal stub system (last resort only) ----------------
# REMOVED aggressive import override that created fake modules
# Tests will now fail if imports don't work, forcing real imports

# Only create minimal stub classes for framework compatibility
class EnhancedRenderer:
    """Minimal stub only if real renderer not available."""
    def render(self, data, *args, **kwargs):
        if isinstance(data, (dict, list)):
            import json
            return json.dumps(data).encode('utf-8')
        return str(data).encode('utf-8')

# Try to import real app components first
try:
    from conduit.app import create_app as _real_create_app
    create_app = _real_create_app
except ImportError:
    try:
        from flask import Flask
        def create_app():
            app = Flask(__name__)
            app.config['TESTING'] = True
            return app
    except ImportError:
        create_app = None

# Try Django setup
django_setup = False
try:
    import django
    from django.conf import settings as _dj_settings
    from django.test.utils import setup_test_environment, teardown_test_environment
    
    if not _dj_settings.configured:
        _dj_settings.configure(
            DEBUG=True,
            TESTING=True,
            SECRET_KEY='test-secret-for-coverage',
            DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}},
            INSTALLED_APPS=[
                'django.contrib.auth',
                'django.contrib.contenttypes',
                'django.contrib.sessions',
            ],
            MIDDLEWARE=[],
        )
        django.setup()
    django_setup = True
except ImportError:
    pass

@pytest.fixture(scope="session")
def app():
    """Application fixture - REAL app first, stub only if unavailable."""
    if create_app:
        application = create_app()
        if hasattr(application, 'app_context'):
            ctx = application.app_context()
            ctx.push()
            yield application
            ctx.pop()
        else:
            yield application
        return
    
    if django_setup:
        setup_test_environment()
        yield None
        teardown_test_environment()
        return
    
    pytest.skip("No app framework detected")

@pytest.fixture
def client(app):
    """Test client - REAL client first."""
    try:
        if hasattr(app, 'test_client'):
            return app.test_client()
    except Exception:
        pass
    
    try:
        from django.test import Client as _DjangoClient
        return _DjangoClient()
    except Exception:
        pass
    
    pytest.skip("No test client available")

# ---------------- Helper fixtures for coverage ----------------
def _permissive_stub(**kwargs):
    """Minimal stub creator - use sparingly."""
    obj = types.SimpleNamespace()
    for k, v in kwargs.items():
        setattr(obj, k, v)
    return obj

@pytest.fixture
def clean_environment(monkeypatch):
    """Reset environment for each test."""
    for var in ("DATABASE_URL", "REDIS_URL", "API_KEY", "SECRET_KEY"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("TESTING", "true")
    yield

@pytest.fixture
def mock_file_operations():
    """Mock file I/O for deterministic tests."""
    with patch("pathlib.Path.exists", return_value=True), \
         patch("pathlib.Path.read_text", return_value="mock"), \
         patch("pathlib.Path.write_text"), \
         patch("os.makedirs"), \
         patch("shutil.rmtree"):
        yield

@pytest.fixture
def sample_data():
    """Generic sample data."""
    return {
        "foo": "bar",
        "num": 123,
        "none": None,
        "username": "testuser",
        "email": "test@example.com",
        "password": "testpass123",
    }

@pytest.fixture
def mock_request():
    """Generic request stub - use real requests when possible."""
    req = _permissive_stub(data={}, headers={}, user=_permissive_stub())
    return req
'''
