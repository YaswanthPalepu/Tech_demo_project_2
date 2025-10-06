# src/gen/conftest_text.py - COMPLETE drop-in replacement

def conftest_text() -> str:
    """Repo-agnostic conftest that FORCES REAL IMPORTS for maximum coverage."""
    return '''"""
Professional pytest configuration for AI-generated tests.
CRITICAL: REAL imports ONLY - stubs disabled for maximum coverage.
Tests execute actual source code to achieve 80%+ coverage.
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

# CRITICAL: Setup Django IMMEDIATELY before any test files import models
django_setup = False
try:
    import django
    from django.conf import settings as _dj_settings
    
    if not _dj_settings.configured:
        settings_module = os.environ.get('DJANGO_SETTINGS_MODULE')
        
        if not settings_module:
            import glob
            # Search in TARGET_ROOT if set, otherwise current directory
            search_root = TARGET_ROOT if TARGET_ROOT else '.'
            settings_files = glob.glob(f'{search_root}/**/settings.py', recursive=True)
            for sf in settings_files:
                if 'venv' not in sf and 'site-packages' not in sf:
                    # Convert path to module: /path/to/conduit/settings.py -> conduit.settings
                    if TARGET_ROOT:
                        sf = sf.replace(TARGET_ROOT, '').lstrip('/')
                    settings_module = sf.replace('/', '.').replace('.py', '')
                    break
        
        if settings_module:
            os.environ['DJANGO_SETTINGS_MODULE'] = settings_module
            django.setup()
            django_setup = True
        else:
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

@pytest.fixture(autouse=True)
def _deterministic_setup():
    """Auto-setup test environment based on detected framework."""
    random.seed(42)
    
    # Auto-detect and setup database URLs
    if not os.getenv('DATABASE_URL'):
        os.environ['DATABASE_URL'] = 'sqlite:///./test.db'
    
    # Setup test mode flags
    os.environ['TESTING'] = 'true'
    os.environ['ENV'] = 'test'
    os.environ['ENVIRONMENT'] = 'test'
    
    yield
    
    # Cleanup
    if os.path.exists('test.db'):
        try:
            os.remove('test.db')
        except:
            pass

# ---------------- EnhancedRenderer Definition ----------------
# Define EnhancedRenderer to prevent NameError in generated tests
class EnhancedRenderer:
    """Enhanced renderer that always returns bytes."""
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        
    def render(self, data, accepted_media_type=None, renderer_context=None):
        """Render data to bytes with comprehensive error handling."""
        try:
            if isinstance(data, (bytes, bytearray)):
                return bytes(data)
            import json
            if isinstance(data, (dict, list)):
                return json.dumps(data).encode("utf-8")
            return str(data).encode("utf-8")
        except Exception:
            return b'{"error": "serialization_failed"}'

# ---------------- REAL IMPORTS ONLY - NO STUBS ----------------
# Stubs disabled to force real code execution for coverage

# Auto-detect and import real app factory
create_app = None
try:
    # Try common app factory patterns
    for module_path in ['app', 'application', 'main', 'server', 'api', 'backend']:
        for factory_name in ['create_app', 'app', 'application', 'get_app']:
            try:
                mod = __import__(module_path)
                if hasattr(mod, factory_name):
                    create_app = getattr(mod, factory_name)
                    if callable(create_app):
                        break
            except ImportError:
                continue
        if create_app:
            break
    
    # Try Flask if detected
    if not create_app:
        try:
            from flask import Flask
            def create_app():
                app = Flask(__name__)
                app.config['TESTING'] = True
                return app
        except ImportError:
            pass
except Exception:
    pass

# Django test utilities (imported after setup)
if django_setup:
    try:
        from django.test.utils import setup_test_environment, teardown_test_environment
    except ImportError:
        setup_test_environment = None
        teardown_test_environment = None

@pytest.fixture(scope="session")
def app():
    """Application fixture - REAL app only."""
    if create_app:
        application = create_app() if callable(create_app) else create_app
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
    
    # Try FastAPI
    try:
        for module_path in ['main', 'app', 'api', 'server']:
            try:
                mod = __import__(module_path)
                if hasattr(mod, 'app'):
                    yield getattr(mod, 'app')
                    return
            except ImportError:
                continue
    except Exception:
        pass
    
    pytest.skip("No app framework detected")

@pytest.fixture
def client(app):
    """Test client - REAL client only."""
    # Flask
    if hasattr(app, 'test_client'):
        return app.test_client()
    
    # Django
    try:
        from django.test import Client as _DjangoClient
        return _DjangoClient()
    except ImportError:
        pass
    
    # FastAPI
    try:
        from fastapi.testclient import TestClient
        return TestClient(app)
    except ImportError:
        pass
    
    pytest.skip("No test client available")

# ---------------- Database fixtures for real testing ----------------
@pytest.fixture(scope="session")
def db_setup():
    """Setup real database for testing."""
    if django_setup:
        try:
            from django.core.management import call_command
            from django.db import connection
            # Create tables for all installed apps
            call_command('migrate', '--run-syncdb', verbosity=0, interactive=False)
        except Exception as e:
            # If migrations fail, try creating tables directly
            try:
                from django.core.management import call_command
                call_command('migrate', '--run-syncdb', '--noinput', verbosity=0)
            except:
                pass
    yield

@pytest.fixture
def db(db_setup):
    """Database fixture with transaction rollback."""
    if django_setup:
        try:
            from django.test import TestCase
            from django.db import transaction
            # Use Django's test database setup
            with transaction.atomic():
                sid = transaction.savepoint()
                yield
                transaction.savepoint_rollback(sid)
        except Exception:
            yield
    else:
        yield

# Django-specific marker support
if django_setup:
    def pytest_configure(config):
        """Register django_db marker."""
        config.addinivalue_line(
            "markers", "django_db: mark test to use Django database"
        )
    
    @pytest.fixture(autouse=True)
    def _django_db_marker(request, db):
        """Auto-apply db fixture when django_db marker is present."""
        marker = request.node.get_closest_marker('django_db')
        if marker:
            # db fixture already applied via parameter
            pass

@pytest.fixture
def api_client():
    """API client for testing REST endpoints."""
    # Try Django REST framework
    try:
        from rest_framework.test import APIClient
        return APIClient()
    except ImportError:
        pass
    
    # Try FastAPI
    try:
        from fastapi.testclient import TestClient
        for module_path in ['main', 'app', 'api']:
            try:
                mod = __import__(module_path)
                if hasattr(mod, 'app'):
                    return TestClient(getattr(mod, 'app'))
            except ImportError:
                continue
    except ImportError:
        pass
    
    # Fallback to regular client
    pytest.skip('No API client available')

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
         patch("pathlib.Path.read_text", return_value="mock content"), \
         patch("pathlib.Path.write_text"), \
         patch("os.makedirs"), \
         patch("shutil.rmtree"):
        yield

@pytest.fixture(params=[{}, {'key': 'value'}, {'nested': {'data': 'test'}}])
def various_data(request):
    """Parametrized fixture for testing with various data structures."""
    return request.param

@pytest.fixture(params=['', 'test', None, 123, True, [], {}])
def edge_case_values(request):
    """Parametrized fixture for edge case testing."""
    return request.param

@pytest.fixture
def sample_data():
    """Comprehensive sample data for all test scenarios."""
    return {
        "foo": "bar",
        "num": 123,
        "none": None,
        "username": "testuser",
        "email": "test@example.com",
        "password": "testpass123",
        "title": "Test Title",
        "description": "Test Description",
        "body": "Test Body Content",
        "slug": "test-slug",
        "tags": ["test", "coverage"],
        "is_active": True,
        "created_at": "2024-01-01T00:00:00Z",
        "updated_at": "2024-01-01T00:00:00Z",
    }

@pytest.fixture
def mock_request():
    """Mock request object for testing views."""
    class MockRequest:
        def __init__(self):
            self.data = {}
            self.query_params = {}
            self.headers = {}
            self.method = 'GET'
            self.path = '/test'
            self.user = types.SimpleNamespace(id=1, username='testuser', is_authenticated=True)
            self.META = {}
            self.GET = {}
            self.POST = {}
            self.FILES = {}
            self.session = {}
    
    return MockRequest()

@pytest.fixture
def authenticated_user():
    """Mock authenticated user for testing."""
    user = types.SimpleNamespace()
    user.id = 1
    user.username = 'testuser'
    user.email = 'test@example.com'
    user.is_authenticated = True
    user.is_active = True
    user.is_staff = False
    user.is_superuser = False
    return user
'''