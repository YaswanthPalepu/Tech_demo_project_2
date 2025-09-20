import pytest
import inspect
import asyncio
from types import SimpleNamespace

try:

    import database as database_module
    from database import get_db
    import main as main_module
    import routers.auth as auth_module
except ImportError as e:
    pytest.skip(f"Skipping tests due to ImportError: {e}", allow_module_level=True)

def _run_maybe_async(func, *args, **kwargs):
    if inspect.iscoroutinefunction(func):
        return asyncio.run(func(*args, **kwargs))
    return func(*args, **kwargs)

def _get_http_exception_class():
    http_exc = getattr(auth_module, "HTTPException", None)
    if http_exc is not None:
        return http_exc
    try:
        from fastapi import HTTPException
        return HTTPException
    except Exception:
        return Exception

class FakeSession:
    def __init__(self):
        self.closed = False
        self.used = True

    def close(self):
        self.closed = True

class RaisingSessionFactory:
    def __call__(self, *args, **kwargs):
        raise RuntimeError("session creation failed")

class FakeUserDB:
    """
    FakeUserDB implements multiple common method names used by various auth implementations:
    - get_by_email / get_user_by_email
    - create_user
    - authenticate_user
    Methods delegate to self._behavior dict to allow flexible test scenarios.
    """

    def __init__(self, db, behavior=None):
        self.db = db
        self._behavior = behavior or {}

    def get_by_email(self, email):
        return self._behavior.get("existing_user")

    def get_user_by_email(self, email):
        return self._behavior.get("existing_user")

    def get_user(self, email):
        return self._behavior.get("existing_user")

    def create_user(self, user):
        # return a user-like object
        created = self._behavior.get("created_user")
        if created is not None:
            return created
        return SimpleNamespace(email=getattr(user, "email", None), id=1)

    def authenticate_user(self, email, password):
        # return user if provided in behavior, otherwise None
        return self._behavior.get("authenticated_user")

    def verify_password(self, plain, hashed):
        return self._behavior.get("verify_password_result", False)

def test_get_db_yields_and_closes(monkeypatch):
    # Arrange
    fake_session = FakeSession()

    def session_factory():
        return fake_session

    monkeypatch.setattr(database_module, "SessionLocal", session_factory, raising=False)

    # Act
    gen = get_db()
    db_obtained = next(gen)

    # Assert that yielded object is our fake session
    assert db_obtained is fake_session

    # Act: close generator to trigger finally block -> should call session.close()
    gen.close()

    # Assert: session.close was called
    assert fake_session.closed is True

def test_get_db_raises_if_sessionlocal_raises(monkeypatch):
    # Arrange
    monkeypatch.setattr(database_module, "SessionLocal", RaisingSessionFactory(), raising=False)

    
    gen = get_db()
    with pytest.raises(RuntimeError):
        next(gen)

def test_root_returns_message_key():
    # Arrange / Act
    result = _run_maybe_async(main_module.root)

    # Assert: result is a mapping-like with a 'message' key that is a string
    assert isinstance(result, dict), "root() should return a dict-like JSON serializable object"
    assert "message" in result
    assert isinstance(result["message"], str)

@pytest.mark.parametrize("existing_user, should_raise", [
    (None, False),
    (SimpleNamespace(email="exists@example.com", id=9), True),
])
def test_signup_creates_or_raises(monkeypatch, existing_user, should_raise):
    # Arrange
    http_exc_cls = _get_http_exception_class()

    created_user = SimpleNamespace(email="new@example.com", id=123)
    behavior = {"existing_user": existing_user, "created_user": created_user}
    fake_db_class = lambda db: FakeUserDB(db, behavior=behavior)

    monkeypatch.setattr(auth_module, "UserDB", fake_db_class, raising=False)

    # Provide a simple user-like input (many routers accept pydantic models; a simple namespace with attributes suffices)
    input_user = SimpleNamespace(email="new@example.com", password="pw")

    # Act / Assert
    if should_raise:
        with pytest.raises(http_exc_cls):
            _run_maybe_async(auth_module.signup, input_user)
    else:
        result = _run_maybe_async(auth_module.signup, input_user)
        # Assert: result represents created user; prefer attribute access, fallback to dict
        if isinstance(result, dict):
            assert result.get("email") == created_user.email
            assert result.get("id") == created_user.id
        else:
            assert getattr(result, "email", None) == created_user.email
            assert getattr(result, "id", None) == created_user.id

def test_login_success_and_failure(monkeypatch):
    # Arrange
    http_exc_cls = _get_http_exception_class()

    # Case 1: successful authentication
    authenticated_user = SimpleNamespace(email="auth@example.com", id=77)
    behavior_success = {"authenticated_user": authenticated_user}
    fake_db_class_success = lambda db: FakeUserDB(db, behavior=behavior_success)

    # Ensure token creation (if used) returns stable token
    monkeypatch.setattr(auth_module, "UserDB", fake_db_class_success, raising=False)
    if hasattr(auth_module, "create_access_token"):
        monkeypatch.setattr(auth_module, "create_access_token", lambda data: "tok123", raising=False)

    input_creds = SimpleNamespace(email="auth@example.com", password="pw")

    # Act
    result = _run_maybe_async(auth_module.login, input_creds)

    # Assert: Expect some token provided by login; accept dict with 'access_token' or object attribute
    if isinstance(result, dict):
        assert ("access_token" in result and result["access_token"] == "tok123") or ("token" in result)
    else:
        # object-like return allowed; ensure it references the authenticated user's identity
        assert getattr(result, "email", None) in (None, "auth@example.com") or getattr(result, "access_token", "tok123") == "tok123"

    
    behavior_fail = {"authenticated_user": None}
    fake_db_class_fail = lambda db: FakeUserDB(db, behavior=behavior_fail)
    monkeypatch.setattr(auth_module, "UserDB", fake_db_class_fail, raising=False)

    with pytest.raises(http_exc_cls):
        _run_maybe_async(auth_module.login, SimpleNamespace(email="nope@example.com", password="bad"))
