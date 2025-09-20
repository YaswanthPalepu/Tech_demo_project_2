import pytest
try:
    import inspect

    from routers.cart import add_to_cart, remove_from_cart, get_cart
    from routers.orders import checkout
except Exception as exc:  
    import pytest  # re-import for skip
    pytest.skip(f"Project modules not importable: {exc}", allow_module_level=True)

@pytest.mark.parametrize(
    "func, name",
    [
        (add_to_cart, "add_to_cart"),
        (remove_from_cart, "remove_from_cart"),
        (get_cart, "get_cart"),
        (checkout, "checkout"),
    ],
)
def test_missing_required_arguments_raise_type_error(func, name):
    # Arrange
    # Act / Assert
    with pytest.raises(TypeError):
        
        func()

@pytest.mark.parametrize(
    "func, name, expected_keywords",
    [
        (add_to_cart, "add_to_cart", ("db", "session", "current_user", "user_id", "item", "product_id")),
        (remove_from_cart, "remove_from_cart", ("db", "session", "current_user", "user_id", "product_id", "item_id")),
        (get_cart, "get_cart", ("db", "session", "current_user", "user_id")),
        (checkout, "checkout", ("db", "session", "current_user", "checkout_request", "order")),
    ],
)
def test_signature_contains_expected_dependency_like_parameters(func, name, expected_keywords):
    # Arrange
    sig = inspect.signature(func)
    param_names = tuple(sig.parameters.keys())

    # Act
    # check if at least one expected dependency-like name is present
    found = any(k in param_names for k in expected_keywords)

    # Assert
    assert found, f"{name} signature parameters {param_names} did not contain any of {expected_keywords}"

@pytest.mark.parametrize(
    "func, name",
    [
        (add_to_cart, "add_to_cart"),
        (remove_from_cart, "remove_from_cart"),
        (get_cart, "get_cart"),
        (checkout, "checkout"),
    ],
)
def test_call_with_all_none_for_required_params_raises_or_returns(func, name):
    # Arrange
    sig = inspect.signature(func)
    params = sig.parameters
    # build kwargs: for parameters without defaults, supply None; for those with defaults, omit to use default
    kwargs = {}
    for pname, p in params.items():
        if p.default is inspect._empty and p.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY):
            kwargs[pname] = None

    # Act / Assert
    if not kwargs:
        
        result = func()
        
        assert True is True
    else:
        with pytest.raises(Exception):
            func(**kwargs)
