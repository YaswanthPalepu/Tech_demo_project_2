import pytest
import re

try:
    from fastapi.testclient import TestClient
except ImportError:
    pytest.skip("fastapi not available", allow_module_level=True)

try:
    from main import app  # adjust import if application is located differently
except Exception:
    pytest.skip("Could not import FastAPI app from main.py", allow_module_level=True)

# Optional schema/model imports used to assert JSON keys; skip tests that require them if missing.
try:
    from models import schemas as models_schemas  # try package style
except Exception:
    try:
        import models.schemas as models_schemas  # fallback
    except Exception:
        models_schemas = None

try:
    import models.db_models as models_db_models
except Exception:
    models_db_models = None

client = TestClient(app)

def _find_route(app_obj, endpoint_name):
    for route in getattr(app_obj, "routes", []):
        # APIRoute has .endpoint (callable) and .name; route.path is the path string
        endpoint = getattr(route, "endpoint", None)
        name = None
        if endpoint is not None:
            name = getattr(endpoint, "__name__", None)
        # route.name can be set to operation_id; accept either
        if name == endpoint_name or getattr(route, "name", None) == endpoint_name:
            return getattr(route, "path", None), getattr(route, "methods", None)
    return None, None

def _fill_path_params(path):
    # Replace {param} with '1' to produce a concrete path for testing.
    if not path:
        return path
    return re.sub(r"{[^}]+}", "1", path)

def _is_json_list(resp):
    try:
        data = resp.json()
    except Exception:
        return False
    return isinstance(data, list)

def _first_item_keys(resp):
    data = resp.json()
    if isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
        return set(data[0].keys())
    return set()

@pytest.mark.parametrize("endpoint_name", ["get_products"])
def test_get_products_success_structure(endpoint_name):
    # Arrange
    path, methods = _find_route(app, endpoint_name)
    if not path:
        pytest.skip(f"Route for {endpoint_name} not found")
    url = _fill_path_params(path)

    # Act
    resp = client.get(url)

    # Assert
    assert resp.status_code in (200, 401, 403), "expected public products or auth gate"
    if resp.status_code == 200:
        assert _is_json_list(resp), "expected a JSON list of products"
        data = resp.json()
        if len(data) == 0:
            pytest.skip("Products list is empty; cannot assert product keys")
        first_keys = set(data[0].keys())
        
        if models_schemas and hasattr(models_schemas, "Product"):
            expected = set(models_schemas.Product.__fields__.keys())
            assert expected.issubset(first_keys), f"product keys missing: {expected - first_keys}"
        else:
            # Fallback: assert at least some common keys exist
            assert first_keys & {"id", "name", "title", "price"} , "expected product to have id/name/price/title"

@pytest.mark.parametrize("endpoint_name", ["get_cart"])
def test_get_cart_returns_list_or_authorized(endpoint_name):
    # Arrange
    path, methods = _find_route(app, endpoint_name)
    if not path:
        pytest.skip(f"Route for {endpoint_name} not found")
    url = _fill_path_params(path)

    # Act
    resp = client.get(url)

    # Assert
    assert resp.status_code in (200, 401, 403), "expected either 200 or auth challenge"
    if resp.status_code == 200:
        assert _is_json_list(resp), "expected cart to be a JSON list"
        data = resp.json()
        if len(data) == 0:
            # empty cart is a valid state
            assert data == []
        else:
            first_keys = set(data[0].keys())
            if models_schemas and hasattr(models_schemas, "DetailedCartItem"):
                expected = set(models_schemas.DetailedCartItem.__fields__.keys())
                assert expected.issubset(first_keys), f"cart item keys missing: {expected - first_keys}"
            else:
                assert first_keys & {"product_id", "id", "quantity", "price"} , "expected cart item to have product_id/quantity/price"

@pytest.mark.parametrize("endpoint_name", ["get_orders"])
def test_get_orders_list_or_authorized(endpoint_name):
    # Arrange
    path, methods = _find_route(app, endpoint_name)
    if not path:
        pytest.skip(f"Route for {endpoint_name} not found")
    url = _fill_path_params(path)

    # Act
    resp = client.get(url)

    # Assert
    assert resp.status_code in (200, 401, 403), "expected 200 or auth challenge for orders"
    if resp.status_code == 200:
        assert _is_json_list(resp), "expected orders to be a JSON list"
        data = resp.json()
        if len(data) == 0:
            # empty orders list allowed
            assert data == []
        else:
            first_keys = set(data[0].keys())
            
            if models_db_models and hasattr(models_db_models, "OrderDB"):
                try:
                    cols = {c.name for c in models_db_models.OrderDB.__table__.columns}
                    assert cols & first_keys, "no overlap between returned order keys and OrderDB columns"
                except Exception:
                    # fallback if model lacks __table__
                    assert first_keys & {"id", "user_id", "total", "items"}, "expected some order keys"
            else:
                assert first_keys & {"id", "user_id", "total", "items"}, "expected some order keys"

@pytest.mark.parametrize("endpoint_name", ["checkout"])
def test_checkout_negative_invalid_payload(endpoint_name):
    # Arrange
    path, methods = _find_route(app, endpoint_name)
    if not path:
        pytest.skip(f"Route for {endpoint_name} not found")
    url = _fill_path_params(path)

    # Act: send an empty/invalid payload to trigger validation error or auth challenge
    resp = client.post(url, json={})

    # Assert: FastAPI typically responds with 422 for invalid body; but auth may trigger 401/403 earlier.
    assert resp.status_code in (422, 400, 401, 403), f"unexpected status {resp.status_code}"
    if resp.status_code == 422:
        
        body = resp.json()
        assert "detail" in body and isinstance(body["detail"], list)
    else:
        
        body = resp.json()
        assert "detail" in body
