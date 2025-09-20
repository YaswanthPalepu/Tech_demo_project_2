# src/gen/prompt.py
import json, random, os
from typing import Dict, Any, List, Tuple

SYSTEM_MIN = (
    "Generate robust pytest test code that handles missing imports gracefully.\n"
    "Critical requirements:\n"
    " - Use defensive programming - check if objects exist before using them\n"
    " - Never assume modules or attributes exist - always use getattr() with defaults\n"
    " - Create simple, working fallback implementations when modules are missing\n"
    " - Use isinstance() checks before calling methods on objects\n"
    " - Avoid complex mocking - prefer simple stubs and fakes\n"
    " - Test basic functionality with minimal dependencies\n"
    " - Use try/except blocks around potentially failing operations\n"
    " - Return ONLY Python code, no markdown\n"
)

UNIT = (
    "Generate simple UNIT tests that work reliably:\n"
    "- Test individual functions/classes with minimal mocking\n"
    "- Use defensive checks: hasattr(), getattr(), isinstance()\n"
    "- Create simple stubs instead of complex mocks\n"
    "- Focus on basic functionality that can be tested safely\n"
    "- Avoid testing implementation details that require deep mocking\n"
)

INTEG = (
    "Generate INTEGRATION tests with defensive patterns:\n"
    "- Test interactions between components safely\n"
    "- Use simple fakes instead of complex mock setups\n"
    "- Check object types and attributes before using them\n"
    "- Focus on data flow that can be verified without deep coupling\n"
)

E2E = (
    "Generate END-TO-END tests using TestClient with fallbacks:\n"
    "- Test HTTP endpoints if they exist\n"
    "- Use mock responses when real endpoints aren't available\n"
    "- Check response structure defensively\n"
    "- Focus on basic request/response cycles\n"
)

# Conservative file limits
MAX_TEST_FILES = {
    "unit": 4,
    "integ": 3, 
    "e2e": 2
}

# Minimal, robust scaffold
SCAFFOLD = '''
"""
Robust test suite with defensive programming patterns.
"""
import pytest
import sys
import os
from unittest.mock import MagicMock, patch
from typing import Any, Dict, List, Optional

# Defensive utilities
def safe_import(module_name):
    """Safely import a module, return None if not available."""
    try:
        return __import__(module_name)
    except ImportError:
        return None

def safe_getattr(obj, attr, default=None):
    """Safely get attribute, with better default handling."""
    if obj is None:
        return default
    return getattr(obj, attr, default)

def is_available(obj):
    """Check if object is available and not a mock."""
    return obj is not None and not isinstance(obj, MagicMock)

def create_simple_stub(attrs=None):
    """Create a simple object stub with given attributes."""
    class Stub:
        pass
    
    if attrs:
        for key, value in attrs.items():
            setattr(Stub, key, value)
    
    return Stub()

# Common test fixtures
@pytest.fixture
def sample_data():
    """Provide basic test data."""
    return {
        "id": 1,
        "name": "test",
        "email": "test@example.com"
    }

'''

def targets_count(compact: Dict[str, Any], kind: str) -> int:
    """Count total targets for test generation."""
    functions = compact.get("functions", [])
    classes = compact.get("classes", [])
    routes = compact.get("routes", [])
    
    if kind == "unit":
        return len(functions) + len(classes)
    elif kind == "e2e":
        return len(routes)
    else:  # integration
        return max(len(functions) + len(classes), len(routes))

def files_per_kind(compact: Dict[str, Any], kind: str) -> int:
    """Calculate number of test files to generate."""
    total_targets = targets_count(compact, kind)
    
    if total_targets == 0:
        return 0
    
    max_files = MAX_TEST_FILES[kind]
    
    # Conservative approach - fewer files with more comprehensive tests
    if kind == "unit":
        return min(max_files, max(1, (total_targets + 4) // 5))
    elif kind == "e2e":
        return min(max_files, max(1, (total_targets + 3) // 4))
    else:  # integration
        return min(max_files, max(1, (total_targets + 5) // 6))

def create_strategic_groups(targets: List[Dict[str, Any]], num_groups: int) -> List[List[Dict[str, Any]]]:
    """Create strategic groups for test coverage."""
    if not targets or num_groups <= 0:
        return []
    
    if len(targets) <= num_groups:
        return [[target] for target in targets]
    
    # Simple round-robin distribution
    groups = [[] for _ in range(num_groups)]
    for i, target in enumerate(targets):
        group_idx = i % num_groups
        groups[group_idx].append(target)
    
    return [group for group in groups if group]

def focus_for(compact: Dict[str, Any], kind: str, shard_idx: int, total_shards: int) -> Tuple[str, List[str], List[Dict[str, Any]]]:
    """Determine focus for test generation."""
    functions = compact.get("functions", [])
    classes = compact.get("classes", [])
    routes = compact.get("routes", [])
    
    if kind == "unit":
        target_list = functions + classes
    elif kind == "e2e":
        target_list = routes
    else:  # integration
        target_list = routes if routes else functions + classes
    
    groups = create_strategic_groups(target_list, total_shards)
    
    if shard_idx < len(groups):
        shard_targets = groups[shard_idx]
    else:
        shard_targets = []
    
    target_names = []
    for target in shard_targets:
        name = target.get("name") or target.get("handler")
        if name:
            target_names.append(name)
    
    focus_label = ", ".join(target_names) if target_names else "(none)"
    return focus_label, target_names, shard_targets

def build_prompt(kind: str, compact_json: str, focus_label: str, shard: int, total: int, 
                compact: Dict[str, Any], context: str = ""):
    """Build prompt for robust test generation."""
    
    # Get test instruction based on kind
    test_instructions = {"unit": UNIT, "integ": INTEG, "e2e": E2E}
    dev_instructions = test_instructions.get(kind, UNIT)
    
    user_content = f"""
ROBUST {kind.upper()} TEST GENERATION - FILE {shard + 1}/{total}

{dev_instructions}

DEFENSIVE PROGRAMMING REQUIREMENTS:
1. Use the provided SCAFFOLD as starting point
2. Check if modules/attributes exist before using them
3. Use getattr(obj, 'attr', default) instead of obj.attr
4. Use isinstance() checks before calling methods
5. Create simple stubs when objects are missing
6. Wrap risky operations in try/except blocks
7. Test targets: {focus_label}

EXAMPLE DEFENSIVE PATTERN:
```python
def test_some_function():
    # Safe import and attribute access
    module = safe_import('some.module')
    if module is None:
        pytest.skip("Module not available")
    
    func = safe_getattr(module, 'some_function')
    if not callable(func):
        # Create simple stub
        def stub_func(*args, **kwargs):
            return "stub_result"
        func = stub_func
    
    # Test with defensive checks
    result = func("test_input")
    assert result is not None
```

CODEBASE ANALYSIS:
{compact_json[:8000]}

SCAFFOLD TO USE:
{SCAFFOLD}

Generate defensive, robust tests that handle missing dependencies gracefully.
"""

    return [
        {"role": "system", "content": SYSTEM_MIN},
        {"role": "user", "content": user_content}
    ]

def runtime_guard(compact: Dict[str, Any]) -> str:
    """Minimal runtime guard."""
    return ""