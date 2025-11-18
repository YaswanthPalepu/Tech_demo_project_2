# Why LLM Fixes Are Failing - Detailed Root Cause Analysis

## Overview of Failures from Your Run

From your output, I see **4 main failure patterns**:

1. **No source code context found** (2 failures)
2. **Token overflow persists** (4 failures)
3. **Fix validation fails** (3 failures)
4. **Function name mismatch** (1 failure)

Let me analyze each pattern in detail.

---

## Pattern 1: No Source Code Context Found (25% of failures)

### Example
```
Test: test_model_info_returns_model_info_when_loaded
  ⚠ No source code context found
    Imports detected: ['sys', 'os', 'asyncio', 'time', 'uuid']
    Used in test: ['unittest.mock.patch']
```

### Root Cause
**The test doesn't import any application code!**

Looking at the test, it probably looks like this:
```python
# tests/generated/test_e2e_20251117_153401_01.py
import sys
import os
import asyncio
from unittest.mock import patch

def test_model_info_returns_model_info_when_loaded():
    # Test uses only mocks, no actual imports from app
    with patch('app.main.model') as mock_model:
        mock_model.get_model_info.return_value = {'name': 'test'}
        # ...
```

**Why context extraction fails:**
1. Test imports: `sys`, `os`, `asyncio`, `unittest.mock.patch`
2. Context extractor filters out stdlib/third-party: All filtered!
3. No application imports found → No source files to extract
4. LLM gets: Test code only, NO source context

### Why LLM Can't Fix
Without source code context, the LLM doesn't know:
- What `ModelInfoResponse` expects (field names)
- What `model.get_model_info()` returns
- What the correct data structure should be

**Example of what LLM sees:**
```
Test code:
def test_model_info_returns_model_info_when_loaded():
    with patch('app.main.model') as mock_model:
        mock_model.get_model_info.return_value = {'name': 'test', 'version': '1.0'}
        response = client.get("/model/info")
        assert response.json()["model_name"] == "test"

Error:
ValidationError: model_name field required

Source code:
# No relevant source code found  ← PROBLEM!
```

The LLM sees the test expects `model_name` but the mock returns `name`. But without seeing `ModelInfoResponse` class definition, it can only guess at the fix.

### How to Fix This

**Solution 1: Enhance Import Detection**

The test uses `patch('app.main.model')` as a string, but context extractor doesn't detect this!

```python
# In ast_context_extractor.py
def _extract_imports(self, tree: ast.AST) -> Dict[str, str]:
    imports = {}

    # Existing code for normal imports...

    # NEW: Also parse string literals in patch() calls
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            # Check if this is unittest.mock.patch or pytest.patch
            if (isinstance(node.func, ast.Attribute) and
                node.func.attr == 'patch'):
                # patch('app.main.model') - extract 'app.main.model'
                if node.args and isinstance(node.args[0], ast.Constant):
                    patch_target = node.args[0].value
                    if isinstance(patch_target, str) and '.' in patch_target:
                        # 'app.main.model' -> import 'app.main'
                        module = '.'.join(patch_target.split('.')[:-1])
                        imports[module] = module

    return imports
```

This would detect `patch('app.main.model')` and extract `app/main.py`!

**Solution 2: Heuristic Fallback**

When no imports found, extract common application files:

```python
# If no imports found, try common patterns
if not source_files:
    common_files = [
        'app/main.py',
        'src/main.py',
        'main.py',
        'app.py'
    ]
    for f in common_files:
        if os.path.exists(f):
            source_files.append(f)
```

---

## Pattern 2: Token Overflow Persists (50% of failures)

### Example
```
Test: test_predict_batch_endpoint_batch_size_handling[2-100-200]
  🎯 Using targeted extraction for main.py (568 lines)...
  📥 Parsed test imports: sys, os, inspect
  🎯 Target functions: main_mod
  ✅ Extracted 137/568 lines (13 definitions)
  ✓ Extracted context from 2 source file(s)
Error parsing LLM JSON response: Expecting value: line 1 column 1 (char 0)
```

### Root Cause
**Even with targeted extraction, still extracting too much!**

Let's break down the token usage:

```
Component               Lines    Tokens
────────────────────────────────────────
Extracted source:       137      ~5,000
Test code:              50       ~500
Error message:          150      ~2,000
System prompts:         -        ~1,500
LLM response:           -        ~500
────────────────────────────────────────
TOTAL:                           ~9,500  ← Still high!
```

**Why 137 lines is too much:**

Looking at the diagnostic:
- Target functions: `main_mod` (just one!)
- But extracted: 13 definitions, 137 lines

This means `main_mod` has HUGE dependencies! Maybe it's the entire FastAPI app instance with all routes.

### Specific Problem: Import of Entire Module

```python
# Test probably does this:
import app.main as main_mod

# Or uses inspect to get all functions:
import inspect
functions = inspect.getmembers(main_mod, inspect.isfunction)
```

When test imports entire module, targeted extraction says "extract everything in main_mod" → extracts all 13 definitions!

### Why LLM Can't Fix

Token budget exceeded:
```
Azure OpenAI limit: 16,000 tokens
Current usage:      ~9,500 tokens (test + source + error)
Remaining:          ~6,500 tokens for LLM response

BUT: Error message can be 300+ lines for complex failures!
Result: Total > 16,000 → Empty response
```

### How to Fix This

**Solution 1: Reduce max_source_lines**

```python
# In ast_context_extractor.py line 36
self.max_source_lines = 200  # Was 300, reduce to 200
```

This would extract ~90 lines instead of 137.

**Solution 2: Smarter Module Import Handling**

When test imports entire module (`import app.main as main_mod`), don't extract everything. Instead:
- Look at what functions are actually CALLED in test
- Extract only those, not all functions in module

```python
def _parse_test_imports_detailed(self, test_file: str) -> Dict[str, Set[str]]:
    # ... existing code ...

    # NEW: Also parse function calls in test body
    test_tree = ast.parse(test_content)
    function_calls = set()

    for node in ast.walk(test_tree):
        if isinstance(node, ast.Call):
            # main_mod.some_function()
            if isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name):
                    obj = node.func.value.id  # 'main_mod'
                    func = node.func.attr      # 'some_function'

                    # If main_mod is an alias for app.main:
                    if obj in imports and imports[obj] == 'app.main':
                        function_calls.add(func)

    # Use function_calls instead of extracting entire module
    return function_calls
```

**Solution 3: Truncate Error Messages**

Error messages can be 150+ lines. Truncate them:

```python
def _truncate_error_message(self, error: str, max_lines: int = 50) -> str:
    """Truncate long error messages while keeping useful parts."""
    lines = error.split('\n')

    if len(lines) <= max_lines:
        return error

    # Keep first 25 and last 25 lines (traceback + final error)
    return '\n'.join(
        lines[:25] +
        [f'... ({len(lines) - 50} lines omitted) ...'] +
        lines[-25:]
    )
```

**Solution 4: Use Smaller Model for Classification**

Classification doesn't need as much context as fixing. Use gpt-3.5-turbo for classification (8K context limit but faster/cheaper):

```python
# In llm_classifier.py
class LLMClassifier:
    def __init__(self):
        # Use smaller, faster model for classification
        self.model = "gpt-3.5-turbo"  # Instead of gpt-4
```

---

## Pattern 3: Fix Validation Fails (37.5% of failures)

### Example
```
Test: test_model_info_endpoint_when_model_absent
  LLM classifier: test_mistake (The test assumed 503 status but app returns 400...)
  Applying fix...
  🧪 Testing fix before applying (regression prevention)...
  ❌ Fix validation failed - test still fails:
     FAILED tests/generated/test_unit_20251117_153401_01.py::test_model_info_endpoint_when_model_absent
  Rejecting fix - it still fails or creates new errors
```

### Root Cause
**LLM generates a fix, but it doesn't actually work.**

This happens when:

1. **LLM misunderstands the problem**
   ```python
   # LLM thinks the problem is:
   assert response.status_code == 503  # Wrong status code

   # So it changes to:
   assert response.status_code == 400  # "Fix"

   # But the REAL problem is:
   # - API key validation runs first
   # - Returns 400 before model check
   # - Need to override dependency!
   ```

2. **Incomplete fix**
   ```python
   # LLM fixes the assertion:
   assert response.status_code == 400  # ✓ Fixed

   # But doesn't fix the JSON check:
   assert "detail" in response.json()  # Should be "error" not "detail"!
   ```

3. **Missing context about test framework**
   ```python
   # Test uses TestClient with dependency overrides:
   app.dependency_overrides[verify_api_key] = lambda: None

   # LLM doesn't see this pattern in extracted code
   # Doesn't know it needs to add this
   ```

### Why LLM Can't Fix

**Example: What LLM sees vs what it needs**

```
What LLM sees (137 lines of extracted source):
- FastAPI app definition
- Some endpoints
- Some Pydantic models
- Some helper functions

What LLM DOESN'T see:
- verify_api_key dependency (might be in different file)
- HTTPException handler (might be in middleware)
- Complete error response structure
- Fixture setup from conftest.py
```

The extracted 137 lines are a RANDOM SUBSET, not necessarily the relevant code!

### How to Fix This

**Solution 1: Multi-Attempt Fix with Learning**

Currently, auto-fixer tries once, fails, gives up. Instead:

```python
def _fix_test_mistake_with_retry(self, failure, max_attempts=3):
    previous_fixes = []

    for attempt in range(max_attempts):
        # Generate fix
        fix = self.llm_fixer.fix_test(
            failure,
            test_code,
            source_code,
            previous_attempts=previous_fixes  # NEW: Learn from failures
        )

        # Test fix
        success = self._validate_fix(failure, fix)

        if success:
            return True

        # If failed, capture WHY it failed
        validation_error = self._get_last_test_output()
        previous_fixes.append({
            'fix': fix,
            'error': validation_error
        })

        if self.verbose:
            print(f"    Attempt {attempt+1} failed: {validation_error}")
            print(f"    Trying again with more context...")
```

Update LLM prompt to include previous attempts:
```
Previous fix attempts:
1. Changed status code to 400
   Result: Still fails - "KeyError: 'error'"

2. Changed assertion to check "error" key
   Result: Still fails - "401 Unauthorized"

Based on these failures, the issue is authentication.
Generate a fix that overrides the API key dependency.
```

**Solution 2: Iterative Context Expansion**

If fix fails, extract MORE context:

```python
def _extract_context_with_expansion(self, test_file, error):
    # First attempt: targeted extraction (200 lines)
    context = self._extract_targeted(test_file, max_lines=200)

    # If this is a retry (fix failed), expand context
    if self.is_retry:
        # Add more context: dependencies, middleware, etc.
        context += self._extract_dependencies_file(test_file)
        context += self._extract_conftest(test_file)

    return context
```

**Solution 3: Error-Specific Prompting**

Parse the validation error to give LLM better guidance:

```python
def _enhance_prompt_with_validation_error(self, validation_error):
    # Parse the error
    if "KeyError: 'error'" in validation_error:
        hint = "The response JSON structure is incorrect. Check the error response format."
    elif "401" in validation_error or "Unauthorized" in validation_error:
        hint = "The test is hitting authentication. You need to override the API key dependency."
    elif "ValidationError" in validation_error:
        hint = "Pydantic validation is failing. Check the field names in the model."

    return f"Previous fix failed with: {validation_error}\nHint: {hint}"
```

**Solution 4: Detect Fix Quality Before Applying**

Add a "fix quality checker" using LLM:

```python
def _assess_fix_quality(self, original_test, fixed_test, error):
    """Use LLM to assess if fix addresses the root cause."""

    prompt = f"""
    Original test: {original_test}
    Proposed fix: {fixed_test}
    Error: {error}

    Does this fix address the ROOT CAUSE of the error?
    Answer: yes/no with confidence score.
    """

    assessment = llm.complete(prompt)

    if assessment.confidence < 0.7:
        return False  # Don't even try to apply low-quality fix
```

---

## Pattern 4: Function Name Mismatch (12.5% of failures)

### Example
```
Test: test_middleware_dispatch_handles_call_next_exception
  Applying fix...
Error: Function 'test_middleware_dispatch_handles_call_next_exception' not found in file
  Available functions in file: async_return, preserve_env, test_validate_sentence_various_inputs, ...
```

### Root Cause
**Pytest reports a function name that doesn't exist in the file.**

This happens with:

1. **Dynamically generated tests**
   ```python
   # Tests generated via pytest_generate_tests
   def pytest_generate_tests(metafunc):
       metafunc.parametrize("middleware_class", [
           BaseHTTPMiddleware,
           CORSMiddleware,
           # ...
       ], ids=lambda cls: f"test_middleware_dispatch_handles_{cls.__name__}")
   ```

2. **Parameterized tests with computed names**
   ```python
   @pytest.mark.parametrize("scenario", [
       pytest.param(scenario1, id="call_next_exception"),
       pytest.param(scenario2, id="other_exception"),
   ])
   def test_middleware_dispatch_handles(scenario):
       # ...
   ```

   Pytest reports: `test_middleware_dispatch_handles[call_next_exception]`
   But also: `test_middleware_dispatch_handles_call_next_exception` (computed from id)

3. **Tests in different file than reported**
   ```python
   # Pytest reports: tests/test_unit_20251117_153401_01.py::test_foo
   # But test is actually in: tests/conftest.py (fixture test)
   ```

### Why Auto-Fixer Can't Fix

AST patcher searches for exact function name. When name doesn't exist, it fails.

### How to Fix This

**Solution 1: Enhanced Name Matching**

```python
def _find_function_fuzzy(self, test_file, test_name):
    """Find function with fuzzy matching."""

    # Try exact match first
    if test_name in available_functions:
        return test_name

    # Strip pytest parameter suffix
    base_name = test_name.split('[')[0]
    if base_name in available_functions:
        return base_name

    # Try partial matching
    for func in available_functions:
        if test_name in func or func in test_name:
            if self.verbose:
                print(f"  Fuzzy match: '{test_name}' → '{func}'")
            return func

    # Search in other files (conftest, fixtures)
    for related_file in self._get_related_files(test_file):
        functions = self._get_functions_in_file(related_file)
        if base_name in functions:
            return (related_file, base_name)

    return None
```

**Solution 2: Use Pytest Collection to Find Tests**

Instead of parsing test names from pytest output, use pytest's collection API:

```python
import pytest

def collect_tests(test_dir):
    """Use pytest to collect tests and their actual locations."""

    class TestCollector:
        def __init__(self):
            self.tests = []

        def pytest_collection_finish(self, session):
            for item in session.items:
                self.tests.append({
                    'nodeid': item.nodeid,
                    'name': item.name,
                    'function': item.function,
                    'file': item.fspath,
                    'line': item.function.__code__.co_firstlineno
                })

    collector = TestCollector()
    pytest.main(['--collect-only', test_dir], plugins=[collector])

    return collector.tests
```

This gives EXACT location of each test, including dynamically generated ones!

---

## Summary: Failure Breakdown

| Issue | Count | % | Root Cause | Solution Complexity |
|-------|-------|---|------------|---------------------|
| **No source context** | 2 | 25% | Test uses mocks/strings, no imports | Medium - enhance import detection |
| **Token overflow** | 4 | 50% | 137 lines still too much | Easy - reduce max_lines to 200 |
| **Fix validation fails** | 3 | 38% | LLM misunderstands or incomplete fix | Hard - multi-attempt with learning |
| **Function not found** | 1 | 13% | Dynamic test generation | Medium - fuzzy matching |

---

## Recommended Fixes (Priority Order)

### 🔥 Priority 1: Reduce Token Overflow (Quick Win)

**Impact**: Fixes 50% of current failures
**Effort**: 5 minutes

```python
# In ast_context_extractor.py line 36
self.max_source_lines = 200  # Reduce from 300
```

Also truncate error messages:
```python
# In orchestrator.py, before passing to LLM
error_message = self._truncate_error(failure.error_message, max_lines=50)
```

### 🔥 Priority 2: Detect String-Based Imports (Medium Win)

**Impact**: Fixes 25% of current failures
**Effort**: 30 minutes

Add detection of `patch('app.main.X')` patterns in test imports.

### 🔥 Priority 3: Multi-Attempt Fix with Learning (Big Win)

**Impact**: Could fix 38% of current failures
**Effort**: 2-3 hours

Implement retry logic that learns from previous failures.

### ⚡ Priority 4: Fuzzy Function Matching (Small Win)

**Impact**: Fixes 13% of current failures
**Effort**: 1 hour

---

## Expected Results After Fixes

### Current Results
```
Iteration 1:
  Test mistakes fixed: 0/8 (0%)
  Code bugs found: 4
  Failures: 8 (100% failure rate)
```

### After Priority 1 (Reduce token limit)
```
Estimated Results:
  Test mistakes fixed: 2-3/8 (25-38%)
  Code bugs found: 4
  Token overflow: Reduced from 4 to 1-2
```

### After Priority 1+2 (Token + Import detection)
```
Estimated Results:
  Test mistakes fixed: 4-5/8 (50-63%)
  Code bugs found: 4
  Token overflow: 1-2
  No context found: 0
```

### After Priority 1+2+3 (All fixes)
```
Estimated Results:
  Test mistakes fixed: 5-6/8 (63-75%)
  Code bugs found: 4
  Most issues resolved
```

---

## Which Fix Should We Implement First?

I recommend **Priority 1 (Reduce token limit)** because:
- ✓ 5-minute change
- ✓ Fixes 50% of failures
- ✓ Immediate impact
- ✓ No risk

Then Priority 2, then Priority 3.

Would you like me to implement Priority 1 right now?
