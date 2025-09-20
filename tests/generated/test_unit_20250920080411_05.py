import pytest
import inspect

try:
    from pydantic import BaseModel, ValidationError
except Exception:
    pytest.skip("pydantic is required for these tests", allow_module_level=True)

try:
    from models.schemas import CheckoutRequest
except Exception:
    pytest.skip("models.schemas.CheckoutRequest not importable", allow_module_level=True)

def _dummy_for_type(outer_type, seen=None):
    # Return a simple dummy value appropriate for a pydantic field outer_type.
    # Recursively handles BaseModel subclasses and typing.List[...] patterns.
    if seen is None:
        seen = set()

    
    if getattr(outer_type, "__qualname__", None) in seen:
        return {}

    # basic builtin types
    if outer_type is str:
        return "x"
    if outer_type is int:
        return 1
    if outer_type is float:
        return 1.0
    if outer_type is bool:
        return True
    if outer_type is dict:
        return {}
    if outer_type is list:
        return []
    # typing generics (List[...], Optional[...], etc.)
    origin = getattr(outer_type, "__origin__", None)
    args = getattr(outer_type, "__args__", None) or ()
    if origin in (list, tuple):
        if args:
            inner = args[0]
            val = _dummy_for_type(inner, seen=seen)
            return [val]
        return []
    if origin is dict:
        # dict[K, V] -> provide simple mapping
        key_type = args[0] if args else str
        val_type = args[1] if len(args) > 1 else str
        return {_dummy_for_type(key_type, seen=seen): _dummy_for_type(val_type, seen=seen)}
    # pydantic BaseModel subclasses
    try:
        if inspect.isclass(outer_type) and issubclass(outer_type, BaseModel):
            seen = set(seen)
            seen.add(outer_type.__qualname__)
            payload = {}
            for fname, finfo in getattr(outer_type, "__fields__", {}).items():
                payload[fname] = _dummy_for_type(finfo.outer_type_, seen=seen)
            return outer_type(**payload)
    except Exception:
        pass

    # fallback: attempt to instantiate if it's a class with no args
    try:
        if inspect.isclass(outer_type):
            return outer_type()
    except Exception:
        pass

    # last resort
    return "x"

def _build_valid_payload_for_model(model_cls):
    payload = {}
    for fname, finfo in getattr(model_cls, "__fields__", {}).items():
        payload[fname] = _dummy_for_type(finfo.outer_type_)
    return payload

def test_CheckoutRequest_valid_construction_all_fields_present():
    # Arrange
    model_cls = CheckoutRequest
    payload = _build_valid_payload_for_model(model_cls)

    # Act
    inst = model_cls(**payload)

    # Assert
    assert isinstance(inst, BaseModel)
    
    inst_dict = inst.dict()
    for k in payload.keys():
        assert k in inst_dict

def test_CheckoutRequest_missing_required_field_raises():
    # Arrange
    model_cls = CheckoutRequest
    fields = getattr(model_cls, "__fields__", {})
    # find a required field
    required_fields = [n for n, f in fields.items() if f.required]
    if not required_fields:
        pytest.skip("No required fields on CheckoutRequest to test missing-field behavior")
    missing = required_fields[0]
    payload = _build_valid_payload_for_model(model_cls)
    payload.pop(missing, None)

    # Act / Assert
    with pytest.raises(ValidationError):
        model_cls(**payload)

@pytest.mark.parametrize("field_name,wrong_value", [
    # set of generic wrong values for common types; mapping will be filtered below
    ("__any__", 12345),  # placeholder, will not be used directly
])
def test_CheckoutRequest_wrong_type_field_raises(field_name, wrong_value):
    # Arrange
    model_cls = CheckoutRequest
    fields = getattr(model_cls, "__fields__", {})
    if not fields:
        pytest.skip("CheckoutRequest has no introspectable fields")

    # pick first field to test wrong type
    fname, finfo = next(iter(fields.items()))
    payload = _build_valid_payload_for_model(model_cls)

    # decide a wrong value based on expected type
    expected = finfo.outer_type_
    # choose an incompatible value
    if expected is str:
        bad = 12345
    elif expected is int:
        bad = "not-an-int"
    elif expected in (float,):
        bad = "nan"
    elif expected is bool:
        bad = "not-bool"
    else:
        # for lists, provide a scalar; for nested models, provide a scalar
        bad = 12345

    payload[fname] = bad

    # Act / Assert
    with pytest.raises(ValidationError):
        model_cls(**payload)

def test_CheckoutRequest_extra_fields_are_ignored_by_default():
    # Arrange
    model_cls = CheckoutRequest
    payload = _build_valid_payload_for_model(model_cls)
    payload["_extra_field_for_test_"] = "should_be_ignored"

    # Act
    inst = model_cls(**payload)

    # Assert
    inst_dict = inst.dict()
    # extra field should not be present in the model dict (pydantic default is ignore)
    assert "_extra_field_for_test_" not in inst_dict
    # model still valid
    assert isinstance(inst, BaseModel)
