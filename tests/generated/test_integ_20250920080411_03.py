import pytest
import importlib
import inspect
import asyncio
import types

# Locate target functions across possible module paths
def _locate_func(func_name, module_basenames):
    for base in module_basenames:
        try:
            mod = importlib.import_module(base)
        except Exception:
            continue
        if hasattr(mod, func_name):
            return getattr(mod, func_name), mod
    raise ImportError(f"Could not find {func_name} in {module_basenames}")

module_candidates = [
    "routers.products",
    "backend_code.routers.products",
    "products",
    "backend_code.products",
    "routers.orders",
    "backend_code.routers.orders",
    "orders",
    "backend_code.orders",
]

# Attempt to import required functions; skip entire module if not present.
try:
    get_products, mod_products = _locate_func("get_products", [
        "routers.products",
        "backend_code.routers.products",
        "products",
        "backend_code.products",
    ])
    checkout, mod_orders = _locate_func("checkout", [
        "routers.orders",
        "backend_code.routers.orders",
        "orders",
        "backend_code.orders",
    ])
    get_orders, _ = _locate_func("get_orders", [
        "routers.orders",
        "backend_code.routers.orders",
        "orders",
        "backend_code.orders",
    ])
except ImportError as e:
    pytest.skip(str(e), allow_module_level=True)

# Simple helpers that are configuration-agnostic for attribute access
def _get_field(obj, name):
    if isinstance(obj, dict):
        return obj.get(name)
    if hasattr(obj, name):
        return getattr(obj, name)
    # pydantic models expose dict()
    if hasattr(obj, "dict"):
        return obj.dict().get(name)
    raise AttributeError(name)

def _set_in_globals(func, name, value):
    # If function is defined in a module, mutate its globals mapping for name
    g = func.__globals__
    g[name] = value

class FakeProduct:
    def __init__(self, id, name, price):
        self.id = id
        self.name = name
        self.price = price
    def dict(self):
        return {"id": self.id, "name": self.name, "price": self.price}
    def __repr__(self):
        return f"FakeProduct({self.id},{self.name},{self.price})"

class FakeOrder:
    def __init__(self, order_id, user_id, items, total):
        self.id = order_id
        self.user_id = user_id
        self.items = items
        self.total = total
    def dict(self):
        return {"id": self.id, "user_id": self.user_id, "items": self.items, "total": self.total}
    def __repr__(self):
        return f"FakeOrder({self.id}, user={self.user_id}, total={self.total})"

class FakeDB:
    def __init__(self, products=None):
        self.products = products or []
        self.orders = []
        self.carts = {}  # user_id -> list of (product_id, qty)
        self._next_order_id = 1

    # Commonly named helpers that might be used by handlers
    def list_products(self):
        return list(self.products)

    def get_products(self):
        return list(self.products)

    def query_products(self):
        return list(self.products)

    def get_cart(self, user_id):
        return list(self.carts.get(user_id, []))

    def add_to_cart(self, user_id, product_id, qty=1):
        self.carts.setdefault(user_id, []).append({"product_id": product_id, "qty": qty})

    def remove_from_cart(self, user_id, product_id):
        items = self.carts.get(user_id, [])
        self.carts[user_id] = [it for it in items if it["product_id"] != product_id]

    def checkout(self, user_id, checkout_data=None):
        cart = self.carts.get(user_id, [])
        if not cart:
            
            raise ValueError("cart is empty")
        items_detail = []
        total = 0
        for it in cart:
            pid = it.get("product_id")
            qty = it.get("qty", 1)
            prod = next((p for p in self.products if _get_field(p, "id") == pid), None)
            if prod is None:
                raise RuntimeError("product not found")
            price = _get_field(prod, "price")
            items_detail.append({"product_id": pid, "qty": qty, "unit_price": price})
            total += price * qty
        order = FakeOrder(self._next_order_id, user_id, items_detail, total)
        self._next_order_id += 1
        self.orders.append(order)
        self.carts[user_id] = []
        return order

    def get_orders(self, user_id):
        return [o for o in self.orders if _get_field(o, "user_id") == user_id]

class FakeUser:
    def __init__(self, id=1, email="test@example.com"):
        self.id = id
        self.email = email
    def dict(self):
        return {"id": self.id, "email": self.email}

# Call function handling sync/async
async def _maybe_await(func, *args, **kwargs):
    if inspect.iscoroutinefunction(func):
        return await func(*args, **kwargs)
    else:
        return func(*args, **kwargs)

def _call_with_fakes(func, fake_db, fake_user=None, extra_request=None):
    sig = inspect.signature(func)
    params = {}
    for name, param in sig.parameters.items():
        lname = name.lower()
        if lname in ("db", "database", "session"):
            params[name] = fake_db
        elif lname in ("user", "current_user", "owner"):
            params[name] = fake_user
        elif "checkout" in lname or "order" in lname or "request" in lname:
            # pass extra_request which may be None
            params[name] = extra_request
        else:
            # if no clue, try to pass nothing and rely on defaults; skip providing
            pass
    return asyncio.get_event_loop().run_until_complete(_maybe_await(func, **params))

@pytest.mark.parametrize("initial_products", [
    [],  # empty
    [FakeProduct(1, "Alpha", 9.99), FakeProduct(2, "Beta", 5.0)],
])
def test_get_products_returns_expected_list(monkeypatch, initial_products):
    # Arrange
    fake_db = FakeDB(products=initial_products)
    fake_user = FakeUser(id=10)
    # Inject common global names that handlers might use
    for name in ("get_db", "get_products", "list_products", "db", "session"):
        # put a callable that returns our fake_db where appropriate
        if name == "get_db":
            _set_in_globals(get_products, name, lambda: fake_db)
        else:
            _set_in_globals(get_products, name, fake_db)

    # Also place Product symbol to prevent NameError in handlers referencing schema class
    _set_in_globals(get_products, "Product", FakeProduct)

    # Act
    result = _call_with_fakes(get_products, fake_db, fake_user)

    # Assert: result should be iterable with same length as initial_products
    assert hasattr(result, "__iter__"), "get_products did not return an iterable"
    got_list = list(result)
    assert len(got_list) == len(initial_products)
    for i, item in enumerate(got_list):
        expected = initial_products[i]
        # Access id and name in flexible manner
        assert _get_field(item, "id") == _get_field(expected, "id")
        assert _get_field(item, "name") == _get_field(expected, "name")

def test_checkout_creates_order_and_get_orders_returns_it(monkeypatch):
    # Arrange
    products = [FakeProduct(1, "One", 3.0), FakeProduct(2, "Two", 7.5)]
    fake_db = FakeDB(products=products)
    user = FakeUser(id=42)
    # Populate user's cart
    fake_db.add_to_cart(user.id, 1, qty=2)  # 2 * 3.0 = 6.0
    fake_db.add_to_cart(user.id, 2, qty=1)  # 1 * 7.5 = 7.5

    # Inject names into checkout and get_orders globals
    for func in (checkout, get_orders):
        for name in ("get_db", "db", "session"):
            if name == "get_db":
                _set_in_globals(func, name, lambda: fake_db)
            else:
                _set_in_globals(func, name, fake_db)
        # place Order/Product classes
        _set_in_globals(func, "OrderDB", FakeOrder)
        _set_in_globals(func, "Product", FakeProduct)

    # Act
    created_order = _call_with_fakes(checkout, fake_db, fake_user=user, extra_request=None)

    # Assert created_order has expected properties
    assert created_order is not None
    assert _get_field(created_order, "user_id") == user.id
    # total should be 13.5
    assert pytest.approx(_get_field(created_order, "total"), rel=1e-3) == 13.5

    # After checkout, cart should be cleared
    assert fake_db.get_cart(user.id) == []

    # Now call get_orders
    orders_list = _call_with_fakes(get_orders, fake_db, fake_user=user)
    # Should include the created order
    assert any(_get_field(o, "id") == _get_field(created_order, "id") for o in orders_list)

def test_checkout_propagates_db_error(monkeypatch):
    # Arrange
    fake_db = FakeDB(products=[FakeProduct(1, "X", 1.0)])
    user = FakeUser(id=7)
    
    fake_db.add_to_cart(user.id, 1, qty=1)

    
    def failing_checkout(user_id, checkout_data=None):
        raise RuntimeError("downstream db failure")
    fake_db.checkout = failing_checkout

    # Inject globals into checkout so it uses our fake_db
    for name in ("get_db", "db", "session"):
        if name == "get_db":
            _set_in_globals(checkout, name, lambda: fake_db)
        else:
            _set_in_globals(checkout, name, fake_db)
    _set_in_globals(checkout, "OrderDB", FakeOrder)

    # Act / Assert
    with pytest.raises(RuntimeError) as exc:
        _call_with_fakes(checkout, fake_db, fake_user=user)
    assert "downstream db failure" in str(exc.value)
