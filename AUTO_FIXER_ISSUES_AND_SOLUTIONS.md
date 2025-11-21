# Auto Test Fixer Issues and Solutions

## 🐛 Problems Identified

### Problem 1: Fixes Failing After 3 Attempts (Most Common Issue)

**Pattern**:
```
❌ All 3 fix attempts failed
Classification: TEST MISTAKE (fix failed)
```

**Root Cause**: **Authentication/API Key Requirement**

All failing tests show:
- Expected: 200, 503, or other status codes
- Actual: 400 Bad Request
- Reason: Missing authentication

### Problem 2: Incorrect Code Bug Classification

**Misclassified Tests**:
```
test_service_status_endpoint_contains_expected_keys
test_health_check_when_model_not_loaded_returns_503
test_metrics_endpoint_returns_prometheus_content_type
test_root_endpoint_reflects_model_state
test_middleware_dispatch_runs_when_processing_request
```

**Classified as**: CODE BUG ❌
**Should be**: TEST MISTAKE ✅

**Why Misclassified**:
- Classifier sees endpoint code is correct
- Classifier sees 400 response
- Classifier thinks: "Code is right but returns wrong status = code bug"
- Classifier misses: "400 is from auth middleware BEFORE endpoint runs"

### Problem 3: Prompt Context Missing

The fixer doesn't have enough context about:
1. Authentication system (`REQUIRE_API_KEY`, `verify_api_key`)
2. How to bypass auth in tests
3. Available test fixtures
4. Environment variable handling
5. Examples of working authenticated tests

---

## 🔍 Root Cause Analysis

### The Authentication System

Your application has conditional authentication:

```python
# app/auth.py or app/main.py
from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import os

security = HTTPBearer(auto_error=False)

def verify_api_key(
    credentials: HTTPAuthorizationCredentials = Security(security)
) -> str:
    """Verify API key from Authorization header"""
    api_key = os.getenv("API_KEY")

    if not credentials:
        raise HTTPException(status_code=400, detail="Missing authorization header")

    if credentials.credentials != api_key:
        raise HTTPException(status_code=403, detail="Invalid API key")

    return credentials.credentials

# In endpoints:
REQUIRE_API_KEY = os.getenv("REQUIRE_API_KEY")

@app.get("/some-endpoint")
async def endpoint(
    api_key: str = Depends(verify_api_key) if REQUIRE_API_KEY else None
):
    ...
```

### What's Happening in Tests

```
Step 1: Test generated WITHOUT auth handling
  client.get("/status")  # No auth header

Step 2: Test runs in environment with REQUIRE_API_KEY=true

Step 3: FastAPI middleware checks auth BEFORE endpoint
  → verify_api_key() called
  → No credentials provided
  → Raises HTTPException(400, "Missing authorization header")

Step 4: Test receives 400 instead of expected 200
  → Test fails

Step 5: Auto-fixer tries to add auth
  → Generates fix with client.get("/status", headers={"Authorization": "Bearer something"})
  → Still fails (wrong key, wrong format, or other issues)
  → Tries 3 times, gives up
```

---

## ✅ Solutions

### Solution 1: Disable Auth in Test Environment (RECOMMENDED)

#### Option A: Environment Variable in conftest.py

**Create/Update**: `tests/generated/conftest.py`

```python
import os
import pytest

@pytest.fixture(scope="session", autouse=True)
def disable_auth_for_tests():
    """Disable API key requirement during tests"""
    # Save original value
    original_require_api_key = os.environ.get("REQUIRE_API_KEY")
    original_api_key = os.environ.get("API_KEY")

    # Disable auth requirement
    os.environ.pop("REQUIRE_API_KEY", None)
    os.environ.pop("API_KEY", None)

    yield

    # Restore original values
    if original_require_api_key is not None:
        os.environ["REQUIRE_API_KEY"] = original_require_api_key
    if original_api_key is not None:
        os.environ["API_KEY"] = original_api_key
```

#### Option B: Monkeypatch in Individual Tests

```python
def test_service_status_endpoint_contains_expected_keys(client, monkeypatch):
    """Test service status endpoint"""
    # Disable auth for this test
    monkeypatch.delenv("REQUIRE_API_KEY", raising=False)
    monkeypatch.delenv("API_KEY", raising=False)

    response = client.get("/status")
    assert response.status_code == 200
    assert "status" in response.json()
```

#### Option C: Check Current Environment

First, check if the env var is set:

```bash
# Check if REQUIRE_API_KEY is set
echo $REQUIRE_API_KEY

# If set, unset it before running tests
unset REQUIRE_API_KEY
unset API_KEY

# Then run tests
pytest tests/generated/
```

---

### Solution 2: Provide Valid Auth in Tests

#### Create Auth Fixture in conftest.py

```python
import pytest
import os
from fastapi.testclient import TestClient
from app.main import app

@pytest.fixture(scope="session")
def api_key():
    """Get or create API key for tests"""
    key = os.getenv("API_KEY", "test-api-key-12345")
    os.environ["API_KEY"] = key
    return key

@pytest.fixture
def auth_client(api_key):
    """Test client with authentication"""
    client = TestClient(app)
    client.headers = {"Authorization": f"Bearer {api_key}"}
    return client

@pytest.fixture
def client():
    """Test client without authentication"""
    return TestClient(app)
```

#### Update Tests to Use auth_client

```python
def test_service_status_endpoint_contains_expected_keys(auth_client):
    """Test service status endpoint with auth"""
    response = auth_client.get("/status")
    assert response.status_code == 200
    assert "status" in response.json()
```

---

### Solution 3: Fix the Classifier (Improve Prompts)

#### Update Classifier Prompt to Recognize Auth Issues

The classifier needs to understand that 400 errors might be auth-related:

**Add to classifier prompt**:

```
AUTHENTICATION DETECTION:

Before classifying as CODE BUG, check if the failure is auth-related:

1. Response is 400/401/403
2. Error message contains: "authorization", "auth", "credentials", "api key", "token"
3. Endpoint has optional auth dependency: `Depends(verify_api_key) if REQUIRE_API_KEY else None`
4. Test doesn't provide auth headers

If these conditions match:
- Classification: TEST MISTAKE (missing authentication)
- Fix: Add auth fixture or disable REQUIRE_API_KEY in test

NEVER classify as CODE BUG if:
- The only issue is missing authentication
- The endpoint logic itself is correct
- The 400/401/403 comes from auth middleware BEFORE endpoint runs
```

**Example improved classification**:

```python
# BAD (current)
Classifier: code_bug (GET /status returned 400 instead of 200, indicating the service_status endpoint is broken)

# GOOD (improved)
Classifier: test_mistake (GET /status returned 400 due to missing authentication - the test should either:
  1. Disable REQUIRE_API_KEY via monkeypatch.delenv("REQUIRE_API_KEY")
  2. Use auth_client fixture with valid Bearer token
  3. Add Authorization header: {"Authorization": f"Bearer {api_key}"})
```

---

### Solution 4: Improve Fixer Prompts

#### Add Context About Auth System

**Add to fixer system prompt**:

```
AUTHENTICATION HANDLING IN TESTS:

This application uses conditional authentication via environment variable:
- REQUIRE_API_KEY: When set, endpoints require API key
- API_KEY: The valid API key value
- verify_api_key: FastAPI dependency that validates auth

Common auth-related failures:
- 400 Bad Request: Missing Authorization header
- 401 Unauthorized: Invalid credentials
- 403 Forbidden: Wrong API key

FIX OPTIONS:

Option 1: Disable auth for test (RECOMMENDED for most tests)
```python
def test_example(client, monkeypatch):
    monkeypatch.delenv("REQUIRE_API_KEY", raising=False)
    response = client.get("/endpoint")
    assert response.status_code == 200
```

Option 2: Use authenticated client
```python
def test_example(auth_client):  # Note: uses auth_client, not client
    response = auth_client.get("/endpoint")
    assert response.status_code == 200
```

Option 3: Add auth header manually
```python
def test_example(client):
    headers = {"Authorization": "Bearer test-api-key-12345"}
    response = client.get("/endpoint", headers=headers)
    assert response.status_code == 200
```

IMPORTANT:
- Check if fixture 'auth_client' exists in conftest.py
- If not, use Option 1 (monkeypatch)
- Never assume auth_client exists without checking
```

#### Add Examples to Few-Shot Learning

```python
EXAMPLE_FIXES = [
    {
        "failure": "400 Bad Request - Missing authorization header",
        "fix": """
def test_endpoint(client, monkeypatch):
    # Disable auth requirement
    monkeypatch.delenv("REQUIRE_API_KEY", raising=False)

    response = client.get("/endpoint")
    assert response.status_code == 200
""",
        "explanation": "Disabled REQUIRE_API_KEY to bypass auth check"
    },
    {
        "failure": "400 Bad Request on /predict/single",
        "fix": """
def test_predict(client, monkeypatch):
    # Disable auth AND ensure model is loaded
    monkeypatch.delenv("REQUIRE_API_KEY", raising=False)

    # Mock model
    mock_model = MagicMock()
    mock_model.predict.return_value = ["positive"]
    monkeypatch.setattr("app.main.model", mock_model)

    response = client.post("/predict/single", json={"text": "test"})
    assert response.status_code == 200
""",
        "explanation": "Disabled auth AND provided model mock"
    }
]
```

---

### Solution 5: Manual Quick Fix for Generated Tests

#### Batch Fix All Generated Tests

Create a script to add auth disabling to all tests:

**Script**: `fix_auth_in_tests.py`

```python
#!/usr/bin/env python3
"""
Add monkeypatch to disable auth in all generated tests
"""
import re
from pathlib import Path

def fix_test_file(file_path: Path):
    """Add monkeypatch.delenv to all test functions"""
    content = file_path.read_text()

    # Pattern: def test_xxx(client):
    pattern = r'(def test_\w+)\(client\):'

    # Replacement: def test_xxx(client, monkeypatch):
    #                  monkeypatch.delenv("REQUIRE_API_KEY", raising=False)
    def replacement(match):
        func_def = match.group(1)
        return f'''{func_def}(client, monkeypatch):
    """Test with auth disabled"""
    monkeypatch.delenv("REQUIRE_API_KEY", raising=False)'''

    # Apply replacement
    new_content = re.sub(pattern, replacement, content)

    # Only write if changed
    if new_content != content:
        file_path.write_text(new_content)
        print(f"✓ Fixed: {file_path}")
        return True
    else:
        print(f"  Skipped: {file_path} (no changes)")
        return False

def main():
    """Fix all test files in tests/generated/"""
    test_dir = Path("tests/generated")

    if not test_dir.exists():
        print(f"❌ Directory not found: {test_dir}")
        return

    fixed_count = 0
    for test_file in test_dir.glob("test_*.py"):
        if fix_test_file(test_file):
            fixed_count += 1

    print(f"\n✅ Fixed {fixed_count} test files")

if __name__ == "__main__":
    main()
```

Run it:
```bash
python fix_auth_in_tests.py
```

---

### Solution 6: Regenerate Tests with Auth Context

#### Update Test Generation Prompts

When generating tests, include auth context:

**Add to test generation prompt**:

```
TEST AUTHENTICATION REQUIREMENTS:

This application uses conditional authentication:
- Environment variable REQUIRE_API_KEY controls whether auth is required
- When set, endpoints use verify_api_key dependency
- Tests should disable this to avoid auth failures

ALWAYS include in generated tests:

```python
def test_example(client, monkeypatch):
    # Disable auth requirement for testing
    monkeypatch.delenv("REQUIRE_API_KEY", raising=False)

    # Your test logic here
    response = client.get("/endpoint")
    assert response.status_code == 200
```

For tests that specifically TEST auth:

```python
def test_auth_required(client, monkeypatch):
    # Enable auth requirement
    monkeypatch.setenv("REQUIRE_API_KEY", "true")
    monkeypatch.setenv("API_KEY", "test-key")

    # Without auth - should fail
    response = client.get("/endpoint")
    assert response.status_code == 400

    # With auth - should succeed
    headers = {"Authorization": "Bearer test-key"}
    response = client.get("/endpoint", headers=headers)
    assert response.status_code == 200
```
```

---

## 📊 Summary of Issues and Fixes

| Issue | Current State | Solution | Priority |
|-------|---------------|----------|----------|
| **Tests fail with 400** | 13+ tests failing | Disable `REQUIRE_API_KEY` in tests | 🔴 **HIGH** |
| **Misclassified as CODE BUG** | 7 tests | Improve classifier prompt | 🟡 **MEDIUM** |
| **Fixer can't fix auth issues** | 8+ tests | Add auth examples to fixer prompt | 🟡 **MEDIUM** |
| **No auth fixtures** | Missing conftest.py | Create conftest.py with fixtures | 🟢 **LOW** |

---

## 🚀 Recommended Action Plan

### Immediate (Fix Now)

1. **Check environment variables**:
   ```bash
   echo $REQUIRE_API_KEY
   echo $API_KEY
   ```

2. **Disable auth for tests** (quickest fix):
   ```bash
   unset REQUIRE_API_KEY
   unset API_KEY
   pytest tests/generated/
   ```

3. **If that works**, add to conftest.py to make permanent:
   ```python
   @pytest.fixture(scope="session", autouse=True)
   def disable_auth_for_tests():
       os.environ.pop("REQUIRE_API_KEY", None)
       os.environ.pop("API_KEY", None)
   ```

### Short-term (Today/Tomorrow)

4. **Improve classifier prompt**:
   - Add auth detection logic
   - Recognize 400 + auth message = TEST MISTAKE (not CODE BUG)

5. **Improve fixer prompt**:
   - Add auth system context
   - Add examples of fixing auth issues
   - Include monkeypatch usage

6. **Run auto-fixer again**:
   - Should now correctly classify auth issues
   - Should successfully fix them

### Long-term (Next Week)

7. **Update test generation**:
   - Include auth disabling in all generated tests
   - Add proper auth test fixtures

8. **Review "code bugs"**:
   - Re-run tests after auth fixes
   - See if any real code bugs remain
   - Most will likely be resolved

---

## 🧪 Testing the Fixes

### Step 1: Verify Environment

```bash
# Check current environment
env | grep -E "REQUIRE_API_KEY|API_KEY"

# Temporarily disable
export REQUIRE_API_KEY=""
export API_KEY=""

# Or completely unset
unset REQUIRE_API_KEY
unset API_KEY
```

### Step 2: Run Tests

```bash
# Run all tests
pytest tests/generated/ -v

# Expected: Most/all tests should now pass
```

### Step 3: Check Results

If tests still fail after disabling auth:
- Check the specific error messages
- Those might be REAL code bugs or other test issues
- But the 400 auth errors should be gone

### Step 4: Make Permanent

Add to `tests/conftest.py` or `tests/generated/conftest.py`:

```python
import pytest
import os

@pytest.fixture(scope="session", autouse=True)
def setup_test_environment():
    """Configure environment for testing"""
    # Disable authentication requirements
    os.environ.pop("REQUIRE_API_KEY", None)
    os.environ.pop("API_KEY", None)

    # Add other test environment setup here

    yield

    # Cleanup if needed
```

---

## 🎯 Expected Results After Fixes

### Before:
```
================================================================================
Iteration 1 Summary:
  Test mistakes fixed: 11
  Code bugs found: 7
  Failed to fix: 8+
================================================================================
```

### After:
```
================================================================================
Iteration 1 Summary:
  Test mistakes fixed: 20+  ← Should increase significantly
  Code bugs found: 1-2      ← Should decrease (most were auth issues)
  Failed to fix: 0-2        ← Should be minimal (real bugs only)
================================================================================
```

---

## 📞 Need More Help?

If issues persist after trying these solutions:

1. **Share the full output** of:
   ```bash
   env | grep -E "REQUIRE|API|KEY"
   pytest tests/generated/test_e2e_20251120_221843_01.py::test_service_status_endpoint_contains_expected_keys -vv
   ```

2. **Share your**:
   - `app/auth.py` or auth code
   - `app/main.py` (endpoint definitions)
   - `tests/conftest.py` or `tests/generated/conftest.py`

3. **Check if there are OTHER issues** besides auth:
   - Model loading issues
   - Database connection issues
   - Missing dependencies
