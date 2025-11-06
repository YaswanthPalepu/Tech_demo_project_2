# src/gen/enhanced_prompt.py - UNIVERSAL AGNOSTIC TEST GENERATION

import json
import os
import random
from typing import Any, Dict, List, Optional, Tuple

SYSTEM_MIN = (
    "Generate comprehensive pytest test code that works with ANY Python project structure.\n"
    "UNIVERSAL TESTING REQUIREMENTS:\n"
    " - Use REAL imports and REAL code execution whenever possible\n"
    " - Test both success paths AND error conditions\n"
    " - Include edge cases: empty inputs, None values, invalid data\n"
    " - Test ALL public methods, properties, and class attributes\n"
    " - Generate multiple test methods per class/function for maximum coverage\n"
    " - Return ONLY Python code, no markdown\n"
    " - Be completely framework-agnostic and project-structure-agnostic\n"
)

# Universal test templates for any project
UNIT_ENHANCED = (
    "Generate COMPREHENSIVE UNIT tests for ANY Python code:\n"
    "- Test EVERY public method in classes/functions\n"
    "- Test constructor/initialization with various parameters\n"
    "- Test property getters and setters\n"
    "- Test validation methods with valid AND invalid inputs\n"
    "- Test string representations (__str__, __repr__)\n"
    "- Test equality operations (__eq__, __hash__ if present)\n"
    "- Test exception handling and error conditions\n"
    "- Use parametrized tests for multiple input scenarios\n"
    "- Target minimum 80% line coverage per file\n"
    "- Use REAL imports, avoid mocking unless absolutely necessary\n"
)

INTEG_ENHANCED = (
    "Generate COMPREHENSIVE INTEGRATION tests for ANY project:\n"
    "- Test component interactions with REAL implementations\n"
    "- Test complete workflows between modules\n"
    "- Test data flow between different parts of the system\n"
    "- Use real imports and actual code execution\n"
    "- Test both happy paths and error scenarios\n"
    "- Verify integration points work correctly\n"
    "- Avoid mocking internal project components\n"
)

E2E_ENHANCED = (
    "Generate COMPREHENSIVE END-TO-END tests for ANY application:\n"
    "- Test complete user workflows\n"
    "- Test API endpoints with real request/response cycles\n"
    "- Test file operations with temporary files\n"
    "- Test database interactions with test databases\n"
    "- Include both success and failure scenarios\n"
    "- Test response formats, headers, and status codes\n"
    "- Use real application setup and teardown\n"
)

MAX_TEST_FILES = {"unit": 4, "integ": 4, "e2e": 2}  

# Universal scaffold for any Python project
UNIVERSAL_SCAFFOLD = '''
"""
Universal test suite - works with ANY Python project structure.
REAL IMPORTS ONLY - Minimal mocking for maximum coverage.
"""

import pytest
import sys
import os
from unittest.mock import patch, Mock, MagicMock
from typing import Any, Dict, List, Optional

os.environ['COVERAGE_OMIT_PATTERNS'] = 'tests/*,*/wsgi.py,*/asgi.py'

# UNIVERSAL IMPORT SETUP - Works with any project structure
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# Universal test utilities
def safe_import(module_path):
    """Safely import any module with comprehensive error handling."""
    try:
        import importlib
        return importlib.import_module(module_path)
    except ImportError as e:
        pytest.skip(f"Module {module_path} not available: {e}")
    except Exception as e:
        pytest.skip(f"Could not import {module_path}: {e}")

def dynamic_import(module_name, class_name=None):
    """Dynamically import modules/classes from ANY project structure."""
    try:
        module = safe_import(module_name)
        if class_name:
            return getattr(module, class_name)
        return module
    except AttributeError:
        pytest.skip(f"Class {class_name} not found in {module_name}")

def create_minimal_stub(**attrs):
    """Create minimal stub only when absolutely necessary."""
    stub = Mock()
    for key, value in attrs.items():
        setattr(stub, key, value)
    return stub

# Universal fixtures for any project
@pytest.fixture
def universal_sample_data():
    """Universal sample data for any Python project."""
    return {
        "string_data": "test value",
        "number_data": 42,
        "list_data": [1, 2, 3],
        "dict_data": {"key": "value"},
        "none_data": None,
        "empty_string": "",
        "empty_list": [],
        "empty_dict": {},
        "boolean_true": True,
        "boolean_false": False,
    }

@pytest.fixture
def temp_file_fixture():
    """Universal temporary file fixture."""
    import tempfile
    with tempfile.NamedTemporaryFile(delete=False, mode='w') as f:
        f.write('test content')
        temp_path = f.name
    yield temp_path
    # Cleanup
    try:
        os.unlink(temp_path)
    except:
        pass

@pytest.fixture
def mock_external_apis():
    """ONLY mock external APIs, never internal project code."""
    with patch('requests.get') as mock_get, \
         patch('requests.post') as mock_post:
        # Setup default responses for external APIs
        mock_get.return_value.status_code = 200
        mock_get.return_value.json.return_value = {'status': 'ok'}
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {'result': 'success'}
        yield {'get': mock_get, 'post': mock_post}

# Async support for any project
@pytest.fixture
def event_loop():
    """Universal event loop for async tests."""
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()

# Universal test patterns
def test_with_real_imports(test_function):
    """Decorator to ensure tests use real imports."""
    def wrapper(*args, **kwargs):
        try:
            return test_function(*args, **kwargs)
        except ImportError as e:
            pytest.skip(f"Required import not available: {e}")
    return wrapper

def parametrized_test_cases():
    """Universal parametrized test cases for any project."""
    return [
        ("normal_case", "test_value", True),
        ("empty_case", "", False),
        ("none_case", None, False),
        ("numeric_case", 123, True),
        ("list_case", [1, 2, 3], True),
    ]
'''

def targets_count(compact: Dict[str, Any], kind: str) -> int:
    functions = compact.get("functions", [])
    classes = compact.get("classes", [])
    methods = compact.get("methods", [])
    routes = compact.get("routes", [])
    
    if kind == "unit":
        return len(functions) + len(classes) + len(methods)
    if kind == "e2e":
        return len(routes)
    return max(len(functions) + len(classes) + len(methods), len(routes))

def files_per_kind(compact: Dict[str, Any], kind: str) -> int:
    """Distribute ALL targets across appropriate number of files."""
    
    total_targets = targets_count(compact, kind)
    if total_targets == 0:
        return 0
    
    targets_per_file = 50
    
    if kind == "unit":
        return max(1, (total_targets + targets_per_file - 1) // targets_per_file)
    elif kind == "e2e":
        return max(1, (total_targets + 19) // 20)
    else:
        return max(1, (total_targets + 29) // 30)

def create_strategic_groups(targets: List[Dict[str, Any]], num_groups: int) -> List[List[Dict[str, Any]]]:
    if not targets or num_groups <= 0:
        return []
    
    if len(targets) <= num_groups:
        return [[t] for t in targets]
    
    file_groups = {}
    for target in targets:
        file_path = target.get("file", "unknown")
        if file_path not in file_groups:
            file_groups[file_path] = []
        file_groups[file_path].append(target)
    
    groups = [[] for _ in range(num_groups)]
    group_index = 0
    
    for file_targets in file_groups.values():
        for target in file_targets:
            groups[group_index].append(target)
            group_index = (group_index + 1) % num_groups
    
    return [g for g in groups if g]

def focus_for(compact: Dict[str, Any], kind: str, shard_idx: int, total_shards: int) -> Tuple[str, List[str], List[Dict[str, Any]]]:
    functions = compact.get("functions", [])
    classes = compact.get("classes", [])
    methods = compact.get("methods", [])
    routes = compact.get("routes", [])
    
    if kind == "unit":
        target_list = functions + classes + methods
    elif kind == "e2e":
        target_list = routes
    else:
        target_list = routes if routes else (functions + classes + methods)
    
    groups = create_strategic_groups(target_list, total_shards)
    shard_targets = groups[shard_idx] if 0 <= shard_idx < len(groups) else []
    
    target_names: List[str] = []
    for t in shard_targets:
        name = t.get("name") or t.get("handler")
        if name:
            target_names.append(name)
    
    focus_label = ", ".join(target_names) if target_names else "(none)"
    return focus_label, target_names, shard_targets

def build_prompt(kind: str, compact_json: str, focus_label: str, shard: int, total: int,
                 compact: Dict[str, Any], context: str = "") -> List[Dict[str, str]]:
    """
    Override build_prompt with defensive clarification to prevent pytest
    collection errors like:
      "function uses no argument 'expected_redirect_name'"
    """
    test_instructions = {
        "unit": UNIT_ENHANCED,
        "integ": INTEG_ENHANCED,
        "e2e": E2E_ENHANCED
    }
    dev_instructions = test_instructions.get(kind, UNIT_ENHANCED)
    max_ctx = 60000
    trimmed_context = context[:max_ctx] if context else ""

    user_content = f"""
UNIVERSAL {kind.upper()} TEST GENERATION - FILE {shard + 1}/{total}

{dev_instructions}

CRITICAL PARAMETRIZATION REQUIREMENTS:
- If you use @pytest.mark.parametrize, ensure **EVERY parameter listed there**
  appears in the test function's signature. (Avoid pytest collection errors.)
- Do NOT parametrize unused names.
- When in doubt, rename or drop unused parameters.

OTHER UNIVERSAL REQUIREMENTS:
1. Use REAL imports and execution.
2. Framework-agnostic (works with Django, Flask, FastAPI, etc.).
3. Test real code paths and edge cases.
4. Never generate stubs or placeholder asserts.
5. Ensure syntactically valid, runnable pytest code.

FOCUS TARGETS: {focus_label}
PROJECT ANALYSIS: {compact_json}
ADDITIONAL CONTEXT: {trimmed_context}
UNIVERSAL SCAFFOLD: {UNIVERSAL_SCAFFOLD}
""".strip()

    return [
        {"role": "system", "content": SYSTEM_MIN},
        {"role": "user", "content": user_content},
    ]

def build_prompt(kind: str, compact_json: str, focus_label: str, shard: int, total: int,
                 compact: Dict[str, Any], context: str = "") -> List[Dict[str, str]]:
    """
    Append-only override: reinforce rules that avoid invalid function calls and
    pytest collection errors. Keeps all earlier behavior but adds stronger
    guidance to the LLM.
    """
    SYSTEM_MIN_LOCAL = SYSTEM_MIN  # reuse existing
    test_instructions = {
        "unit": UNIT_ENHANCED,
        "integ": INTEG_ENHANCED,
        "e2e": E2E_ENHANCED
    }
    dev_instructions = test_instructions.get(kind, UNIT_ENHANCED)
    max_ctx = 60000
    trimmed_context = context[:max_ctx] if context else ""

    user_content = f"""
UNIVERSAL {kind.upper()} TEST GENERATION - FILE {shard + 1}/{total}

{dev_instructions}

CRITICAL PARAMETRIZATION REQUIREMENTS:
- If you use @pytest.mark.parametrize, every parameter listed there MUST also
  appear in the test function's signature. Do NOT parametrize unused names.

CRITICAL CALL-SAFETY REQUIREMENTS:
- Do NOT repeat the same keyword argument in a single call
  (e.g., use Mock(name="x") only once; never Mock(name="x", name="y")).
- Ensure all function calls are syntactically valid Python.

OTHER UNIVERSAL REQUIREMENTS:
1. Use REAL imports and execution (no stubs).
2. Framework-agnostic (Django/Flask/FastAPI/vanilla Python).
3. Cover success paths, failures, and edge cases.
4. Avoid placeholder asserts.
5. Only output runnable Python code (no markdown).

FOCUS TARGETS: {focus_label}
PROJECT ANALYSIS: {compact_json}
ADDITIONAL CONTEXT (TRIMMED): {trimmed_context}

{UNIVERSAL_SCAFFOLD}
""".strip()

    return [
        {"role": "system", "content": SYSTEM_MIN_LOCAL},
        {"role": "user", "content": user_content},
    ]



def build_prompt(kind: str, compact_json: str, focus_label: str, shard: int, total: int,
                 compact: Dict[str, Any], context: str = "") -> List[Dict[str, str]]:
    """
    Final override (append-only): steer generation toward Django-correct patterns.
    """
    SYSTEM_MIN_LOCAL = SYSTEM_MIN
    test_instructions = {"unit": UNIT_ENHANCED, "integ": INTEG_ENHANCED, "e2e": E2E_ENHANCED}
    dev_instructions = test_instructions.get(kind, UNIT_ENHANCED)
    max_ctx = 60000
    trimmed_context = context[:max_ctx] if context else ""

    user_content = f"""
UNIVERSAL {kind.upper()} TEST GENERATION - FILE {shard + 1}/{total}

{dev_instructions}

DJANGO-SPECIFIC RULES (when Django is detected):
- Use RequestFactory (not SimpleNamespace/DummyRequest) to build HttpRequest.
- When setting request.POST/GET, use QueryDict (or helper) so .getlist works.
- If tests touch models/querysets, mark tests with pytest.mark.django_db.
- Prefer asserting substrings in response.content/HttpResponse, avoid strict equality to full HTML.
- Do NOT set arbitrary .object_list lists unless you wrap them in a queryset-like with .order_by/.all.

CRITICAL PARAMETRIZATION REQUIREMENTS:
- Every name in @pytest.mark.parametrize MUST appear in the function signature.

CRITICAL CALL-SAFETY REQUIREMENTS:
- Never repeat the same keyword in a call (e.g., Mock(name=...) only once).
- Generate syntactically valid Python.

FOCUS TARGETS: {focus_label}
PROJECT ANALYSIS: {compact_json}
ADDITIONAL CONTEXT (TRIMMED): {trimmed_context}

{UNIVERSAL_SCAFFOLD}
""".strip()

    return [
        {"role": "system", "content": SYSTEM_MIN_LOCAL},
        {"role": "user", "content": user_content},
    ]



def _merge_universal_text():
    # combines the strongest parts of the prior variants
    return (
        "UNIVERSAL REQUIREMENTS:\n"
        "1) Use REAL imports and execution; no stubs.\n"
        "2) Test success, failure, and edge cases (None/empty/invalid).\n"
        "3) Multiple test methods per target; aim high coverage.\n"
        "4) Only output runnable Python (no markdown).\n"
        "5) @pytest.mark.parametrize: EVERY name listed MUST appear in the test "
        "   function signature. Do NOT parametrize unused names.\n"
        "6) Call-safety: Never repeat the same keyword in a single call "
        "   (e.g., Mock(name=...) only once). Ensure all calls are valid Python.\n"
        "\n"
        "DJANGO RULES (when Django is present):\n"
        "- Build requests with RequestFactory (not SimpleNamespace/DummyRequest).\n"
        "- Use QueryDict (or helper) for request.POST/GET so .getlist works.\n"
        "- If touching models/querysets, mark with pytest.mark.django_db.\n"
        "- Prefer substring assertions (response/content), avoid strict HTML equality.\n"
        "- Don’t fabricate .object_list as raw lists; use queryset-like objects "
        "  (supporting .order_by/.all) when needed.\n"
    )

def build_prompt(kind: str, compact_json: str, focus_label: str, shard: int, total: int,
                 compact: Dict[str, Any], context: str = "") -> List[Dict[str, str]]:
    """
    Final, unified override (append-only).
    This merges: (a) parametrize-safety, (b) call-safety, and (c) Django-aware guidance.
    The LAST definition in the file is the one Python will use.
    """
    SYSTEM_MIN_LOCAL = SYSTEM_MIN
    test_instructions = {
        "unit": UNIT_ENHANCED,
        "integ": INTEG_ENHANCED,
        "e2e": E2E_ENHANCED
    }
    dev_instructions = test_instructions.get(kind, UNIT_ENHANCED)
    max_ctx = 60000
    trimmed_context = context[:max_ctx] if context else ""
    merged_rules = _merge_universal_text()

    user_content = f"""
UNIVERSAL {kind.upper()} TEST GENERATION - FILE {shard + 1}/{total}

{dev_instructions}

{merged_rules}

FOCUS TARGETS: {focus_label}
PROJECT ANALYSIS: {compact_json}
ADDITIONAL CONTEXT (TRIMMED): {trimmed_context}

{UNIVERSAL_SCAFFOLD}
""".strip()

    return [
        {"role": "system", "content": SYSTEM_MIN_LOCAL},
        {"role": "user", "content": user_content},
    ]
