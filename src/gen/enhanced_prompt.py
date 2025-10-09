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
    with patch('requests.get') as mock_get, \\
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
WORKS WITH ANY PYTHON PROJECT STRUCTURE

{dev_instructions}

CRITICAL UNIVERSAL REQUIREMENTS:
1. USE REAL IMPORTS AND REAL CODE EXECUTION
2. Be completely agnostic to project structure and frameworks
3. Only mock EXTERNAL dependencies (APIs, databases, network calls)
4. NEVER mock internal project code or Python built-ins
5. Use dynamic import discovery for any project structure
6. Test ACTUAL behavior, not assumed behavior

CRITICAL CODE STRUCTURE REQUIREMENTS:
1. ALWAYS indent code blocks properly after colons
2. Use 4 spaces for indentation, never mix tabs and spaces
3. Ensure every 'if', 'for', 'while', 'def', 'class', 'with', 'try' block has properly indented content
4. Never put unindented code immediately after a colon

REAL CODE EXECUTION STRATEGY:
- Import and use whatever modules/functions actually exist in the project
- Test with real data and real execution paths
- Use sys.path modification to handle any project structure
- Skip tests gracefully when dependencies aren't available
- Verify actual system behavior, not mocked fantasies

PROPER INDENTATION EXAMPLES:
```python
# CORRECT: Properly indented after if statement
if condition:
    try:
        # code here
    except:
        pass

# INCORRECT: Unindented after if statement  
if condition:
try:  # THIS WILL CAUSE SYNTAX ERROR
    # code here

# CORRECT: All blocks properly indented
def test_function():
    if some_condition:
        for item in items:
            try:
                result = process(item)
            except Exception:
                handle_error()
DYNAMIC IMPORT PATTERNS FOR ANY PROJECT:



def test_with_real_imports():
    \"\"\"Universal test pattern that works with any project.\"\"\"
    # Try to import whatever actually exists
    target_module = None
    target_class = None
    
    # Try common module patterns
    for module_name in ['app', 'main', 'application', 'models', 'services']:
        try:
            target_module = safe_import(module_name)
            break
        except:
            continue
    
    if target_module is None:
        pytest.skip("No importable modules found in project")
    
    # Use the actual imported module for testing
    # Test real behavior with real data
MINIMAL MOCKING GUIDELINES:


# ONLY mock external dependencies:
with patch('requests.get') as mock_api:
    mock_api.return_value.status_code = 200
    # test code that uses external API

# NEVER mock internal code or Python built-ins:
# with patch('time.time'):  # DON'T DO THIS!
# with patch('os.path.exists'):  # DON'T DO THIS!

# Use real internal implementations:
result = actual_function_under_test(real_parameters)
UNIVERSAL TEST PATTERNS:


# Pattern 1: Real imports with graceful fallbacks
def test_real_implementation():
    try:
        from actual_project_module import RealClass
        instance = RealClass()
        result = instance.actual_method('test_input')
        assert result is not None
    except ImportError:
        pytest.skip("Required project module not available")

# Pattern 2: Test actual API behavior
def test_api_behavior():
    \"\"\"Test what the API actually does, not what we think it should do.\"\"\"
    response = client.get('/actual/endpoint')
    # Accept whatever status code is returned and test accordingly
    if response.status_code == 200:
        assert 'data' in response.json()
    elif response.status_code == 400:
        assert 'error' in response.json()
    # Don't assert specific status codes - test the actual behavior

# Pattern 3: Use real data flows
def test_data_processing():
    \"\"\"Test with real data through real processing pipelines.\"\"\"
    input_data = universal_sample_data['string_data']
    try:
        processor = dynamic_import('processing', 'DataProcessor')
        result = processor.process(input_data)
        # Test the actual result, not a mocked one
        assert isinstance(result, (str, dict, list))
    except:
        pytest.skip("Data processing components not available")
AGNOSTIC PROJECT STRUCTURE HANDLING:

No assumptions about package names ('myapp', 'app', etc.)

No hardcoded import paths

Works with flat structures, nested packages, or any layout

Dynamically discovers what's actually available

Uses sys.path to make project modules importable

FOCUS TARGETS: {focus_label}
PROJECT ANALYSIS: {compact_json}
ADDITIONAL CONTEXT: {trimmed_context}
UNIVERSAL SCAFFOLD: {UNIVERSAL_SCAFFOLD}

GENERATE TESTS THAT:

Work with ANY Python project structure

Use REAL imports and REAL execution

Test ACTUAL system behavior

Are completely framework-agnostic

Have minimal mocking (external dependencies only)
""".strip()

    return [
    {"role": "system", "content": SYSTEM_MIN},
    {"role": "user", "content": user_content},
    ]