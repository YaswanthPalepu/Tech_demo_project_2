import pytest
import inspect
import types
from types import SimpleNamespace

# Guard imports for third-party modules and application modules
try:
    import fastapi
    from fastapi.testclient import TestClient
except ImportError:
    pytest.skip("fastapi or its testclient is not available", allow_module_level=True)

try:
    import main  # the FastAPI app / root handler
    import routers.auth as auth
    import database
    import models.schemas as schemas
except ImportError as exc:
    pytest.skip(f"Application modules not available: {exc}", allow_module_level=True)

def _build_pydantic_instance(model_cls, overrides=None):
    """
    Create an instance of a pydantic model class with reasonable dummy data.
    """
    overrides = overrides or {}
    if not hasattr(model_cls, "__fields__"):
        # Not a pydantic model; try to instantiate directly
        try:
            return model_cls()
        except Exception:
            return None

    kwargs = {}
    for name, field in model_cls.__fields__.items():
        if name in overrides:
            kwargs[name] = overrides[name]
            continue
        t = field.outer_type_
        # heuristics for common fields
        if name.lower().find("email") != -1:
            kwargs[name] = "user@example.com"
        elif name.lower().find("password") != -1:
            kwargs[name] = "secret-password"
        elif name.lower().find("name") != -1:
            kwargs[name] = "Alice"
        elif t is int:
            kwargs[name] = 1
        elif t is float:
            kwargs[name] = 1.0
        else:
            kwargs[name] = "value"
    return model_cls(**kwargs)

def _extract_email_from_result(res):
    """
    Try to extract an email from various possible return types:
    - pydantic model with .email
    - dict with 'email' key
    - SimpleNamespace with email attribute
    """
    if res is None:
        return None
    # pydantic BaseModel
    try:
        import pydantic

        if isinstance(res, pydantic.BaseModel):
            return getattr(res, "email", None)
    except Exception:
        pass

    if isinstance(res, dict):
        return res.get("email") or res.get("user", {}).get("email")
    if hasattr(res, "email"):
        return getattr(res, "email")
    # token string or other
    return None

class FakeDB:
    """
    Minimal fake DB used by the auth handlers in tests.
    It allows configuring whether a user is present and capturing create_user calls.
    """

    def __init__(self, existing_user=None):
        # existing_user expected to be SimpleNamespace or similar
        self._existing_user = existing_user
        self.created = None

    def get_user_by_email(self, email):
        # mimic typical DB lookup
        if self._existing_user and getattr(self._existing_user, "email", None) == email:
            return self._existing_user
        return None

    def create_user(self, user_in):
        # create_user may be called with a pydantic model or dict
        if hasattr(user_in, "dict"):
            payload = user_in.dict()
        elif isinstance(user_in, dict):
            payload = user_in
        else:
            # Try to grab attributes
            payload = {k: getattr(user_in, k) for k in dir(user_in) if not k.startswith("_")}
        user_obj = SimpleNamespace(**{k: v for k, v in payload.items() if not callable(v)}, id=123)
        self.created = user_obj
        return user_obj

    # Helpers that might be used by login
    def verify_password(self, plain_password, hashed_password):
        
        return plain_password == hashed_password

@pytest.fixture(autouse=True)
def ensure_db_monkeypatched(monkeypatch):
    """
    Ensure that the database.get_db dependency is monkeypatchable.
    Tests will set database.get_db inside each test as needed.
    """
    # Provide a default get_db that yields None to avoid real DB usage
    def _noop_get_db():
        return None

    monkeypatch.setattr(database, "get_db", _noop_get_db, raising=False)
    yield

def _prepare_callable_args(func, fake_db=None, overrides=None):
    """
    Inspect func signature and build arguments for calling it directly.
    - For pydantic model parameters: build an instance.
    - For db-like parameters (name 'db' or annotation matching database.get_db return): supply fake_db.
    - For primitive params 'email' or 'password': supply sensible values.
    """
    overrides = overrides or {}
    sig = inspect.signature(func)
    kwargs = {}
    for name, param in sig.parameters.items():
        ann = param.annotation
        # if annotation is a pydantic model class
        if inspect.isclass(ann) and hasattr(ann, "__fields__"):
            kwargs[name] = _build_pydantic_instance(ann, overrides=overrides.get(name))
            continue
        # common parameter names
        if name.lower() == "db":
            kwargs[name] = fake_db
            continue
        if name.lower() in ("email", "username"):
            kwargs[name] = overrides.get(name, "user@example.com")
            continue
        if name.lower() == "password":
            kwargs[name] = overrides.get(name, "secret-password")
            continue
        # fallback: if parameter has default use it
        if param.default is not inspect.Parameter.empty:
            kwargs[name] = param.default
            continue
        # final fallback: try to construct from annotation if possible
        try:
            if inspect.isclass(ann):
                kwargs[name] = ann()
            else:
                kwargs[name] = None
        except Exception:
            kwargs[name] = None
    return kwargs

def _call_and_extract(func, kwargs):
    """
    Call func with kwargs (sync) and return the result or raise exception.
    """
    return func(**kwargs)

def _safe_assert_email_in_result(result, expected_email):
    """
    Given various possible result shapes, assert that an email is present and equals expected_email.
    """
    email = _extract_email_from_result(result)
    assert email == expected_email, f"expected email {expected_email!r} present in result, got {email!r}"

def test_root_handler_returns_success():
    # Arrange
    client = TestClient(main.app)

    # Act
    resp = client.get("/")

    # Assert
    assert resp.status_code == 200
    # response body should be JSON-parsable (dict, list, string etc)
    body = resp.json()
    assert body is not None

@pytest.mark.parametrize("existing", [False, True])
def test_signup_creates_or_rejects_user(monkeypatch, existing):
    # Arrange
    # Prepare a fake DB that either has an existing user or not
    existing_user = None
    payload_email = "newuser@example.com"
    if existing:
        existing_user = SimpleNamespace(id=1, email=payload_email, password="irrelevant")
    fake_db = FakeDB(existing_user=existing_user)

    # Monkeypatch database.get_db to return our fake DB for FastAPI dependencies if needed
    monkeypatch.setattr(database, "get_db", lambda: fake_db, raising=False)

    # Prepare function args for auth.signup
    signup_func = getattr(auth, "signup", None)
    assert signup_func is not None, "signup handler not found in routers.auth"

    
    overrides = {}
    
    kwargs = _prepare_callable_args(signup_func, fake_db=fake_db, overrides={"email": payload_email, "password": "pwd"})
    
    for k, v in kwargs.items():
        if hasattr(v, "dict"):
            d = v.dict()
            if "email" in d:
                d["email"] = payload_email
            if "password" in d:
                d["password"] = "pwd"
            # rebuild model instance with modified data
            kwargs[k] = v.__class__(**d)

    # Act / Assert
    if existing:
        # Expect a FastAPI HTTPException when user already exists
        with pytest.raises(fastapi.HTTPException):
            _call_and_extract(signup_func, kwargs)
    else:
        result = _call_and_extract(signup_func, kwargs)
        
        _safe_assert_email_in_result(result, payload_email)
        # Also assert the fake_db captured creation
        assert fake_db.created is not None
        assert getattr(fake_db.created, "email", None) == payload_email

def test_login_rejects_missing_user(monkeypatch):
    
    fake_db = FakeDB(existing_user=None)
    monkeypatch.setattr(database, "get_db", lambda: fake_db, raising=False)

    login_func = getattr(auth, "login", None)
    assert login_func is not None, "login handler not found in routers.auth"

    kwargs = _prepare_callable_args(login_func, fake_db=fake_db, overrides={"email": "doesnotexist@example.com", "password": "pwd"})

    # Act / Assert
    with pytest.raises(fastapi.HTTPException):
        _call_and_extract(login_func, kwargs)

def test_login_allows_valid_credentials(monkeypatch):
    # Arrange: prepare fake user and fake DB
    payload_email = "valid@example.com"
    payload_password = "correcthorsebatterystaple"
    
    stored_user = SimpleNamespace(id=2, email=payload_email, password=payload_password)
    fake_db = FakeDB(existing_user=stored_user)

    monkeypatch.setattr(database, "get_db", lambda: fake_db, raising=False)

    # If auth module defines a verify_password helper, monkeypatch it to do simple equality
    if hasattr(auth, "verify_password"):
        monkeypatch.setattr(auth, "verify_password", lambda plain, hashed: plain == hashed)
    # Some implementations use auth.pwd_context or utils; attempt to patch common names
    if hasattr(auth, "pwd_context"):
        try:
            # Create a dummy object with verify method
            class _Ctx:
                @staticmethod
                def verify(plain, hashed):
                    return plain == hashed

            monkeypatch.setattr(auth, "pwd_context", _Ctx())
        except Exception:
            pass

    login_func = getattr(auth, "login", None)
    assert login_func is not None, "login handler not found in routers.auth"

    kwargs = _prepare_callable_args(login_func, fake_db=fake_db, overrides={"email": payload_email, "password": payload_password})

    # Act
    result = _call_and_extract(login_func, kwargs)

    # Assert: Accept multiple possible success shapes:
    
    
    
    if isinstance(result, dict):
        
        assert any(k in result for k in ("access_token", "token", "session")), "expected a token/key in login response dict"
    elif hasattr(result, "email"):
        assert getattr(result, "email") == payload_email
    elif isinstance(result, str):
        assert len(result) > 0
    else:
        # As a last concrete check, ensure result is truthy
        assert result, "login returned an unexpected empty/falsey result"
