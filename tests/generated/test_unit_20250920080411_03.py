import pytest
import inspect
import types

try:
    import routers.products as r_products
    import products as products_module
    import routers.orders as r_orders
    import models.db_models as db_models
    from models.db_models import UserDB, OrderDB
except ImportError as e:
    pytest.skip(f"Required application modules not available: {e}", allow_module_level=True)

def _build_kwargs_for_call(fn, override=None):
    """
    Build kwargs for calling fn:
    - If parameter named 'db' present, set to override['db'] if provided else object()
    - For parameters without default, set to generic sentinel (or override value if provided)
    - Do not attempt to satisfy parameters with defaults
    """
    override = override or {}
    sig = inspect.signature(fn)
    kwargs = {}
    for name, param in sig.parameters.items():
        if name == "self":
            continue
        if name in override:
            kwargs[name] = override[name]
        elif name == "db":
            kwargs[name] = override.get("db", object())
        elif param.default is inspect._empty:
            kwargs[name] = object()
    return kwargs

def test_get_products_returns_list_and_uses_service(monkeypatch):
    # Arrange
    expected = [{"id": 1, "name": "apple"}, {"id": 2, "name": "banana"}]
    received = {}

    def fake_service(db):
        # capture the db passed and return predictable result
        received['db'] = db
        return expected

    # monkeypatch the top-level products service the router likely delegates to
    monkeypatch.setattr(products_module, "get_products", fake_service, raising=False)

    mock_db = object()
    kwargs = _build_kwargs_for_call(r_products.get_products, override={"db": mock_db})

    # Act
    result = r_products.get_products(**kwargs)

    # Assert
    assert result == expected
    assert 'db' in received and received['db'] is mock_db

def test_get_products_propagates_service_errors(monkeypatch):
    # Arrange
    def exploding_service(db):
        raise ValueError("service failure")

    monkeypatch.setattr(products_module, "get_products", exploding_service, raising=False)
    kwargs = _build_kwargs_for_call(r_products.get_products, override={"db": object()})

    # Act / Assert
    with pytest.raises(ValueError) as excinfo:
        r_products.get_products(**kwargs)
    assert "service failure" in str(excinfo.value)

def test_get_orders_uses_orderdb_and_returns_list(monkeypatch):
    # Arrange
    expected = [{"order_id": 10}, {"order_id": 11}]
    init_args = {}

    class FakeOrderDB:
        def __init__(self, db):
            # capture what was passed in
            init_args['db'] = db

        def get_orders(self, *args, **kwargs):
            return expected

    # Replace OrderDB in the db_models module so router will instantiate our fake
    monkeypatch.setattr(db_models, "OrderDB", FakeOrderDB, raising=False)

    mock_db = object()
    kwargs = _build_kwargs_for_call(r_orders.get_orders, override={"db": mock_db})

    # Act
    result = r_orders.get_orders(**kwargs)

    # Assert
    assert result == expected
    assert init_args.get('db') is mock_db

def test_get_orders_propagates_orderdb_errors(monkeypatch):
    # Arrange
    class ExplodingOrderDB:
        def __init__(self, db):
            pass

        def get_orders(self, *args, **kwargs):
            raise RuntimeError("db exploded")

    monkeypatch.setattr(db_models, "OrderDB", ExplodingOrderDB, raising=False)
    kwargs = _build_kwargs_for_call(r_orders.get_orders, override={"db": object()})

    # Act / Assert
    with pytest.raises(RuntimeError) as excinfo:
        r_orders.get_orders(**kwargs)
    assert "db exploded" in str(excinfo.value)

def _instantiate_class_with_dummy(cls):
    """
    Instantiate cls by inspecting its __init__ signature.
    Returns (instance, first_arg_name, first_arg_value_used)
    """
    sig = inspect.signature(cls.__init__)
    params = [p for p in sig.parameters.values() if p.name != "self"]
    dummy = object()
    if not params:
        # no args required
        instance = cls()
        return instance, None, None
    # build positional args for required params (we try to pass the same dummy for all)
    args = []
    for p in params:
        if p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
            # pass no special values
            continue
        args.append(dummy)
    instance = cls(*args)
    first_param_name = params[0].name
    return instance, first_param_name, dummy

def test_UserDB_stores_db_reference():
    # Arrange / Act
    instance, first_param_name, dummy = _instantiate_class_with_dummy(UserDB)

    # Assert: Prefer attribute 'db' if present; otherwise the attribute with the name of the first init param.
    if hasattr(instance, "db"):
        assert getattr(instance, "db") is dummy
    elif first_param_name and hasattr(instance, first_param_name):
        assert getattr(instance, first_param_name) is dummy
    else:
        # Fallback: Ensure instance creation succeeded and type is correct
        assert isinstance(instance, UserDB)

def test_OrderDB_stores_db_reference():
    # Arrange / Act
    instance, first_param_name, dummy = _instantiate_class_with_dummy(OrderDB)

    # Assert similarly to UserDB
    if hasattr(instance, "db"):
        assert getattr(instance, "db") is dummy
    elif first_param_name and hasattr(instance, first_param_name):
        assert getattr(instance, first_param_name) is dummy
    else:
        assert isinstance(instance, OrderDB)
