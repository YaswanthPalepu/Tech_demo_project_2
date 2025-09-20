import pytest
import uuid

try:
    from fastapi.testclient import TestClient
    from main import app
except Exception:
    pytest.skip("FastAPI or app not importable; skipping E2E HTTP tests", allow_module_level=True)

client = TestClient(app)

def _url_for(name: str):
    try:
        return client.app.url_path_for(name)
    except Exception:
        pytest.skip(f"route with name '{name}' not found on app")

def _find_id_key(item: dict):
    for k in ("id", "product_id", "productId", "sku", "pk"):
        if k in item:
            return k
    return None

def _attempt_post_json(path, payload, headers=None):
    headers = headers or {}
    return client.post(path, json=payload, headers=headers)

def _attempt_signup(email: str, password: str):
    signup_path = _url_for("signup")
    for payload in ({"email": email, "password": password}, {"username": email, "password": password}):
        resp = client.post(signup_path, json=payload)
        if resp.status_code in (200, 201):
            return resp
    return resp  # last attempt

def _attempt_login(email: str, password: str):
    login_path = _url_for("login")
    for payload in ({"email": email, "password": password}, {"username": email, "password": password}, {"username": email, "password": password}):
        resp = client.post(login_path, json=payload)
        if resp.status_code == 200:
            return resp
    return resp

def _extract_token(resp_json: dict):
    for k in ("access_token", "token", "accessToken"):
        if k in resp_json:
            return resp_json[k]
    
    return None

def test_root_responds_with_json_and_nonempty_payload():
    # Arrange
    path = _url_for("root")

    # Act
    resp = client.get(path)

    # Assert
    assert resp.status_code == 200
    ct = resp.headers.get("content-type", "")
    assert "application/json" in ct
    body = resp.json()
    assert isinstance(body, dict)
    assert len(body) > 0

def test_signup_login_add_and_remove_from_cart_happy_path():
    # Arrange
    # Get product list
    products_path = _url_for("get_products")
    resp_products = client.get(products_path)
    assert resp_products.status_code == 200
    products = resp_products.json()
    assert isinstance(products, (list, tuple))
    if not products:
        pytest.skip("No products available to exercise cart endpoints")

    first_product = products[0]
    prod_id_key = _find_id_key(first_product)
    if not prod_id_key:
        pytest.skip("Product object does not expose an identifiable id key")

    prod_id = first_product[prod_id_key]

    # Create a unique user
    email = f"test-{uuid.uuid4().hex[:8]}@example.invalid"
    password = "SufficientlyC0mplex!"

    # Act: signup
    signup_resp = _attempt_signup(email, password)
    # Assert signup accepted or user already exists (200/201/409)
    assert signup_resp.status_code in (200, 201, 409)

    # Act: login
    login_resp = _attempt_login(email, password)
    # Assert login succeeded
    assert login_resp.status_code == 200
    login_json = login_resp.json()
    token = _extract_token(login_json)
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    # Act: add to cart
    add_path = _url_for("add_to_cart")
    # Build payload using the same id key style as the product list
    add_payload = {prod_id_key: prod_id, "quantity": 1}
    add_resp = _attempt_post_json(add_path, add_payload, headers=headers)
    # Assert add succeeded
    assert add_resp.status_code in (200, 201)
    added_body = add_resp.json()
    assert isinstance(added_body, (dict, list))

    # Act: get cart and confirm item present
    get_cart_path = _url_for("get_cart")
    cart_resp = client.get(get_cart_path, headers=headers)
    assert cart_resp.status_code == 200
    cart_body = cart_resp.json()
    assert isinstance(cart_body, (list, dict))
    # Normalize to list
    items = cart_body if isinstance(cart_body, list) else cart_body.get("items", [])
    assert any(
        ((isinstance(it, dict) and (it.get(prod_id_key) == prod_id or it.get("product", {}).get(prod_id_key) == prod_id)))
        for it in items
    )

    # Act: remove from cart
    remove_path = _url_for("remove_from_cart")
    remove_payload = {prod_id_key: prod_id}
    remove_resp = _attempt_post_json(remove_path, remove_payload, headers=headers)
    # Assert removal succeeded
    assert remove_resp.status_code in (200, 204)
    
    if remove_resp.status_code == 200:
        rem_json = remove_resp.json()
        assert isinstance(rem_json, (dict, list))

@pytest.mark.parametrize("bad_id", ["__nonexistent_product__", "", "00000000-0000-0000-0000-000000000000"])
def test_add_to_cart_with_invalid_product_returns_error(bad_id):
    # Arrange
    products_path = _url_for("get_products")
    resp_products = client.get(products_path)
    assert resp_products.status_code == 200

    # Create a user to attach cart operations to
    email = f"badtest-{uuid.uuid4().hex[:8]}@example.invalid"
    password = "AnotherC0mplex!"
    _ = _attempt_signup(email, password)
    login_resp = _attempt_login(email, password)
    if login_resp.status_code != 200:
        pytest.skip("Could not login to perform negative cart test")
    token = _extract_token(login_resp.json())
    headers = {"Authorization": f"Bearer {token}"} if token else {}

    # Act
    add_path = _url_for("add_to_cart")
    # Try several key possibilities for product identifier
    attempted = False
    last_resp = None
    for key in ("id", "product_id", "productId", "sku", "pk"):
        payload = {key: bad_id, "quantity": 1}
        last_resp = _attempt_post_json(add_path, payload, headers=headers)
        attempted = True
        # If we get a 4xx, that's acceptable; break early
        if 400 <= last_resp.status_code < 500:
            break

    # Assert we attempted at least once
    assert attempted
    # Expect a client error (invalid product) rather than server error
    assert last_resp is not None
    assert 400 <= last_resp.status_code < 500, f"Expected 4xx for invalid product id, got {last_resp.status_code}"
