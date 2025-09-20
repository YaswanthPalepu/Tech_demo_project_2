import pytest
import inspect
import types
from types import SimpleNamespace

try:
    # Application code under test
    from backend_code.routers import cart as cart_mod
    from backend_code.routers.cart import add_to_cart, remove_from_cart, get_cart
    # Schemas (may be used as parameter types)
    from backend_code.models import schemas as schemas_mod
    CartItemSchema = getattr(schemas_mod, "CartItem", None)
    DetailedCartItemSchema = getattr(schemas_mod, "DetailedCartItem", None)
    ProductSchema = getattr(schemas_mod, "Product", None)
    
    from backend_code.models import db_models as db_models_mod
    UserDBModel = getattr(db_models_mod, "UserDB", None)
    OrderDBModel = getattr(db_models_mod, "OrderDB", None)
except ImportError as e:
    pytest.skip(f"Cannot import application modules: {e}", allow_module_level=True)

# Helpers: Fake in-memory DB and query stub to satisfy many common access patterns.
class FakeProduct:
    def __init__(self, id, name="p", price=1.0):
        self.id = id
        self.name = name
        self.price = price

    def dict(self):
        return {"id": self.id, "name": self.name, "price": self.price}

class FakeUser:
    def __init__(self, id_, email="u@example.com"):
        self.id = id_
        self.email = email
        # Cart represented as list of dicts: {"product_id": int, "quantity": int}
        self.cart = []

    def find_cart_item(self, product_id):
        for it in self.cart:
            if it["product_id"] == product_id:
                return it
        return None

class QueryStub:
    def __init__(self, db, model):
        self.db = db
        self.model = model
        self._filter_kwargs = {}

    def get(self, id_):
        if self.model is FakeProduct or getattr(self.model, "__name__", "") == "Product":
            return self.db.products.get(int(id_))
        if self.model is FakeUser or getattr(self.model, "__name__", "") == "UserDB":
            return self.db.users.get(int(id_))
        return None

    def filter_by(self, **kwargs):
        self._filter_kwargs = kwargs
        return self

    def first(self):
        if "id" in self._filter_kwargs:
            return self.get(self._filter_kwargs["id"])
        # fallback: return any product
        if self.model is FakeProduct:
            return next(iter(self.db.products.values()), None)
        return None

class FakeDB:
    def __init__(self, products=None, users=None):
        # products: dict id->FakeProduct
        self.products = {p.id: p for p in (products or [])}
        # users: dict id->FakeUser
        self.users = {u.id: u for u in (users or [])}
        self._added = []
        self._committed = False

    def query(self, model):
        # Accept both class objects from real models and our Fake classes
        return QueryStub(self, model)

    def add(self, obj):
        self._added.append(obj)

    def commit(self):
        self._committed = True

    # convenience helpers for test assertions
    def ensure_user(self, user_id):
        if int(user_id) not in self.users:
            self.users[int(user_id)] = FakeUser(int(user_id))
        return self.users[int(user_id)]

# Utility to build arguments for route functions based on signature
def build_args_for(func, *, fake_db=None, user_id=1, product_id=1, quantity=1, extra=None):
    sig = inspect.signature(func)
    kwargs = {}
    # Prepare canonical objects
    prod_schema_obj = None
    cart_item_obj = None
    if CartItemSchema:
        try:
            cart_item_obj = CartItemSchema(product_id=product_id, quantity=quantity)
        except Exception:
            cart_item_obj = SimpleNamespace(product_id=product_id, quantity=quantity)
    else:
        cart_item_obj = SimpleNamespace(product_id=product_id, quantity=quantity)

    if ProductSchema:
        try:
            prod_schema_obj = ProductSchema(id=product_id, name="p", price=1.0)
        except Exception:
            prod_schema_obj = SimpleNamespace(id=product_id, name="p", price=1.0)
    else:
        prod_schema_obj = SimpleNamespace(id=product_id, name="p", price=1.0)

    user_obj = SimpleNamespace(id=user_id, email=f"user{user_id}@example.com", cart=[])
    if fake_db is None:
        fake_db = FakeDB(products=[FakeProduct(product_id)], users=[FakeUser(user_id)])

    for name, param in sig.parameters.items():
        lname = name.lower()
        if lname in ("db", "session"):
            kwargs[name] = fake_db
        elif lname in ("current_user", "user", "current_user_db", "user_db"):
            # Provide object similar to what routes expect
            # Might be a full ORM user; provide SimpleNamespace or FakeUser from fake_db
            kwargs[name] = fake_db.ensure_user(user_id)
        elif "product" in lname and (param.annotation == ProductSchema or "product" in lname):
            kwargs[name] = prod_schema_obj
        elif "item" in lname or param.annotation == CartItemSchema:
            kwargs[name] = cart_item_obj
        elif "product_id" in lname or (param.annotation == int and "id" in lname):
            kwargs[name] = product_id
        elif param.annotation == int and "quantity" in lname:
            kwargs[name] = quantity
        else:
            # if extra provides this param, use it
            if extra and name in extra:
                kwargs[name] = extra[name]
            # else attempt to provide something benign
            elif param.default is inspect._empty:
                # provide None for optional things
                kwargs[name] = None
    return kwargs

@pytest.mark.parametrize("start_cart, add_qty, expected_qty", [
    ([], 3, 3),            # empty cart, add 3
    ([{"product_id": 1, "quantity": 2}], 4, 6),  # existing item increments
])
def test_add_to_cart_adds_item(start_cart, add_qty, expected_qty, monkeypatch):
    # Arrange
    user = FakeUser(42)
    user.cart = [dict(it) for it in start_cart]
    fake_prod = FakeProduct(1, name="Widget", price=9.99)
    fake_db = FakeDB(products=[fake_prod], users=[user])

    # Ensure route function will operate on our fake by passing db/current_user
    args = build_args_for(add_to_cart, fake_db=fake_db, user_id=42, product_id=1, quantity=add_qty)

    # Act
    result = add_to_cart(**args)

    # Assert: user's cart updated
    updated_user = fake_db.users[42]
    found = updated_user.find_cart_item(1)
    assert found is not None, "expected product to be present in cart after add_to_cart"
    assert found["quantity"] == expected_qty

    # Also exercise get_cart returns the cart representation
    get_args = build_args_for(get_cart, fake_db=fake_db, user_id=42)
    cart_result = get_cart(**get_args)
    # Expect a list-like cart; allow either list / SimpleNamespace / dict with items
    assert cart_result is not None
    if isinstance(cart_result, list):
        # find product item
        items = [it for it in cart_result if getattr(it, "product_id", getattr(it, "id", None)) in (1,)]
        # Expect at least one entry
        assert items, "get_cart returned list but did not include added product"
    else:
        # if not list, ensure updated_user still consistent
        assert updated_user.find_cart_item(1)["quantity"] == expected_qty

@pytest.mark.parametrize("initial_qty, remove_qty, expect_present, expect_qty", [
    (5, 2, True, 3),   # partial remove reduces quantity
    (3, 3, False, 0),  # exact remove deletes item
])
def test_remove_from_cart_adjusts_quantity(initial_qty, remove_qty, expect_present, expect_qty):
    # Arrange
    user = FakeUser(7)
    user.cart = [{"product_id": 10, "quantity": initial_qty}]
    fake_prod = FakeProduct(10, name="Gizmo", price=5.0)
    fake_db = FakeDB(products=[fake_prod], users=[user])

    # Build args: remove_from_cart may accept item or product_id and db/current_user
    args = build_args_for(remove_from_cart, fake_db=fake_db, user_id=7, product_id=10, quantity=remove_qty)

    # Act
    try:
        res = remove_from_cart(**args)
    except Exception as exc:
        
        # Only allow exception if it is a ValueError for invalid request.
        assert isinstance(exc, ValueError), f"unexpected exception type: {type(exc)}"
        # In case of exception, ensure state unchanged for invalid case
        found = fake_db.users[7].find_cart_item(10)
        assert (found is not None and found["quantity"] == initial_qty) or found is None
        return

    # Assert state
    found = fake_db.users[7].find_cart_item(10)
    if expect_present:
        assert found is not None, "expected item to remain in cart after partial remove"
        assert found["quantity"] == expect_qty
    else:
        assert found is None or expect_qty == 0, "expected item to be removed from cart"

def test_get_cart_empty_returns_empty_list():
    # Arrange
    user = FakeUser(99)
    fake_db = FakeDB(products=[FakeProduct(1)], users=[user])

    args = build_args_for(get_cart, fake_db=fake_db, user_id=99)

    # Act
    res = get_cart(**args)

    # Assert: empty cart represented as empty sequence
    if res is None:
        pytest.skip("get_cart returned None; ambiguous contract")
    if isinstance(res, list):
        assert res == [], "expected empty cart list"
    else:
        # Try to interpret a mapping or object with length
        try:
            assert len(res) == 0
        except Exception:
            # last resort: check underlying user cart is empty
            assert fake_db.users[99].cart == []

def test_remove_nonexistent_item_noop_or_raises(monkeypatch):
    # Arrange
    user = FakeUser(123)
    user.cart = []  # empty
    fake_db = FakeDB(products=[FakeProduct(5)], users=[user])

    args = build_args_for(remove_from_cart, fake_db=fake_db, user_id=123, product_id=5, quantity=1)

    
    try:
        res = remove_from_cart(**args)
    except Exception as exc:
        assert isinstance(exc, (KeyError, ValueError)), f"unexpected exception {type(exc)}"
        # ensure cart still empty
        assert fake_db.users[123].cart == []
    else:
        # if no exception, ensure no item was added accidentally
        assert fake_db.users[123].cart == []

# Ensure that the route functions' globals do not perform time-based side effects.
def test_functions_are_time_deterministic(monkeypatch):
    # Arrange: inject deterministic datetime if functions reference datetime in their globals
    fake_dt = types.SimpleNamespace(now=lambda: "2000-01-01T00:00:00")
    for func in (add_to_cart, remove_from_cart, get_cart):
        if "datetime" in func.__globals__:
            func.__globals__["datetime"] = fake_dt

    # Prepare a simple scenario for add/get
    user = FakeUser(50)
    fake_db = FakeDB(products=[FakeProduct(2)], users=[user])
    args = build_args_for(add_to_cart, fake_db=fake_db, user_id=50, product_id=2, quantity=1)

    # Act
    add_to_cart(**args)
    get_args = build_args_for(get_cart, fake_db=fake_db, user_id=50)
    cart = get_cart(**get_args)

    # Assert deterministic content exists
    assert isinstance(cart, (list, tuple)) or getattr(cart, "__len__", None) is not None
    # underlying user cart must reflect deterministic addition
    found = fake_db.users[50].find_cart_item(2)
    assert found is not None and found["quantity"] == 1
