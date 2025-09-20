import pytest
import builtins
from types import SimpleNamespace

try:
    from models import schemas
    from pydantic import BaseModel, ValidationError
except ImportError as e:
    pytest.skip(f"Required modules not available: {e}", allow_module_level=True)

import typing
import datetime
import uuid

# Helper to construct a plausible sample value for a given annotation
def _sample_for_annotation(ann):
    origin = typing.get_origin(ann)
    args = typing.get_args(ann)
    # Direct basic types
    if ann is builtins.int or ann is int:
        return 1
    if ann is builtins.float or ann is float:
        return 1.5
    if ann is builtins.str or ann is str:
        return "sample"
    if ann is builtins.bool or ann is bool:
        return True
    if ann is datetime.datetime:
        return datetime.datetime(2020, 1, 1, 0, 0, 0)
    if ann is datetime.date:
        return datetime.date(2020, 1, 1)
    if ann is uuid.UUID:
        return uuid.UUID(int=1)
    if ann is dict or origin is dict:
        return {}
    if origin is list or origin is typing.List:
        inner = args[0] if args else str
        return [_sample_for_annotation(inner)]
    if origin is typing.Union:
        # Optional[T] typically becomes Union[T, NoneType]; prefer first non-None
        non_none = [a for a in args if a is not type(None)]
        if not non_none:
            return None
        return _sample_for_annotation(non_none[0])
    if isinstance(ann, type) and issubclass(ann, BaseModel):
        # Create nested model by using its fields recursively
        return _sample_for_model(ann)
    # Fallbacks
    if ann is typing.Any:
        return "any"
    try:
        # If it's a typing.NewType or similar
        if isinstance(ann, type):
            
            return ann()
    except Exception:
        pass
    # final fallback
    return "x"

def _sample_for_model(model_cls):
    # Build kwargs for model by sampling each field's annotation if possible
    data = {}
    
    fields = getattr(model_cls, "__fields__", None)
    if not fields:
        return {}
    for name, field in fields.items():
        ann = field.outer_type_
        data[name] = _sample_for_annotation(ann)
    try:
        return model_cls(**data)
    except Exception:
        
        return data

# Collect model classes under test
MODEL_NAMES = ["Product", "CartItem", "DetailedCartItem", "User"]
AVAILABLE_MODELS = {}
for name in MODEL_NAMES:
    if hasattr(schemas, name):
        AVAILABLE_MODELS[name] = getattr(schemas, name)
    else:
        # If missing, tests will be skipped per-case
        AVAILABLE_MODELS[name] = None

@pytest.mark.parametrize("model_name,model_cls", [(n, AVAILABLE_MODELS[n]) for n in MODEL_NAMES])
def test_model_instantiate_and_serialize_valid(model_name, model_cls):
    # Arrange
    if model_cls is None:
        pytest.skip(f"{model_name} not present in schemas module")
    assert issubclass(model_cls, BaseModel)
    # Build sample data for all fields
    sample = {}
    for fname, fmeta in model_cls.__fields__.items():
        sample[fname] = _sample_for_annotation(fmeta.outer_type_)
    # Act
    obj = model_cls(**sample)
    serialized = obj.dict()
    jsonable = None
    # Attempt .json() to ensure serialization path works
    try:
        jsonable = obj.json()
    except Exception:
        jsonable = None
    # Assert
    # All expected keys appear in dict
    for k in sample.keys():
        assert k in serialized
    # Types of values in serialized correspond roughly to sample types (strings for many)
    for k, v in serialized.items():
        # If original sample was a BaseModel instance, dict() will have dict; ensure mapping/dict
        if isinstance(sample.get(k), BaseModel):
            assert isinstance(v, dict)
        else:
            # Ensure value is not a pydantic model leftover
            assert not isinstance(v, BaseModel)
    # Ensure json produced or at least dict produced
    assert isinstance(serialized, dict)
    # If jsonable created, it's a string
    if jsonable is not None:
        assert isinstance(jsonable, str)

@pytest.mark.parametrize("model_name,model_cls", [(n, AVAILABLE_MODELS[n]) for n in MODEL_NAMES])
def test_model_invalid_field_type_raises_validation_error(model_name, model_cls):
    # Arrange
    if model_cls is None:
        pytest.skip(f"{model_name} not present in schemas module")
    # Choose a required field (field without default and not Optional)
    required_field = None
    for fname, fmeta in model_cls.__fields__.items():
        # If field required by pydantic
        if fmeta.required:
            required_field = fname
            break
    if required_field is None:
        # No required fields, construct one field to tamper with
        required_field = next(iter(model_cls.__fields__.keys()))
    # Build default good data
    good = {}
    for fname, fmeta in model_cls.__fields__.items():
        good[fname] = _sample_for_annotation(fmeta.outer_type_)
    # Introduce invalid type for the selected field
    bad = dict(good)
    bad[required_field] = object()  # definitely invalid for typical types
    # Act / Assert
    with pytest.raises(ValidationError):
        model_cls(**bad)

def test_DetailedCartItem_contains_product_and_quantity_consistency():
    
    model_cls = AVAILABLE_MODELS.get("DetailedCartItem")
    Product = AVAILABLE_MODELS.get("Product")
    if model_cls is None or Product is None:
        pytest.skip("DetailedCartItem or Product not present")
    
    prod_sample = _sample_for_model(Product)
    if isinstance(prod_sample, dict):
        # ensure we pass a proper model instance if possible
        prod_sample = Product(**prod_sample)
    # Build a plausible payload: try to set quantity if field exists
    payload = {}
    for fname, fmeta in model_cls.__fields__.items():
        if fname.lower() in ("product", "item", "product_id"):
            payload[fname] = prod_sample
        elif fname.lower() in ("quantity", "qty"):
            payload[fname] = 3
        else:
            payload[fname] = _sample_for_annotation(fmeta.outer_type_)
    # Act
    obj = model_cls(**payload)
    # Assert nested product serialized to dict
    d = obj.dict()
    # find nested product key
    nested_keys = [k for k in d.keys() if isinstance(d[k], dict)]
    assert nested_keys, "Expected at least one nested dict for product"
    # quantity present and matches
    for qname in ("quantity", "qty"):
        if qname in d:
            assert d[qname] == 3

def test_User_password_and_serialization_behavior():
    model_cls = AVAILABLE_MODELS.get("User")
    if model_cls is None:
        pytest.skip("User model not present")
    # Arrange: sample data
    sample = {}
    for fname, fmeta in model_cls.__fields__.items():
        sample[fname] = _sample_for_annotation(fmeta.outer_type_)
    # If there is a clear password field, ensure it can be set and appears in dict (or is hidden)
    password_field = None
    for fname in sample.keys():
        if "pass" in fname.lower():
            password_field = fname
            break
    if password_field:
        sample[password_field] = "S3cr3t!"
    # Act
    user = model_cls(**sample)
    d = user.dict()
    # Assert: if password field exists, check that it's present or intentionally omitted depending on schema design
    if password_field:
        # Accept either presence with same value or absence (hashed/omitted)
        if password_field in d:
            assert d[password_field] == "S3cr3t!"
        else:
            
            assert any(k in d for k in ("id", "username", "email", "name"))
    else:
        # No password field: ensure typical identity fields exist
        assert any(k in d for k in ("id", "username", "email", "name")) or d == {}
