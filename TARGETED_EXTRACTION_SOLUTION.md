# Targeted Extraction Solution: Extract Only What's Needed

## The Problem with Blind Truncation

**Current approach (blind):**
```python
# Extract first 300 lines (first 15-20 functions)
# Problem: Test might need function at line 500!
```

**Example failure:**
```
Test: test_predict_batch_returns_list
Uses: app.main.predict_batch (at line 520)
Extracted: Lines 1-164 (doesn't include line 520)
Result: LLM doesn't see the function it needs ❌
```

---

## The Solution: Targeted Extraction

**Extract ONLY the functions the test actually uses**, regardless of where they are in the file.

### Step 1: Analyze Test File to Find What It Imports

```python
# Test file: tests/test_model.py
from app.main import predict_batch, validate_sentence
import app.main as app_main

def test_predict_batch():
    result = predict_batch(["hello"])  # Uses predict_batch
    assert isinstance(result, list)

def test_validate():
    result = app_main.validate_sentence("hi")  # Uses validate_sentence
    assert result == True
```

**Parse imports to find:**
- `predict_batch` (imported directly)
- `validate_sentence` (imported directly)
- `app_main.*` (may use any function via module import)

### Step 2: Find These Specific Functions in Source File

```python
# app/main.py (567 lines)

def function_1():  # Line 10 - NOT USED
    pass

def validate_sentence(text):  # Line 50 - USED! ✓
    if not text:
        raise ValueError()
    return True

def function_3():  # Line 80 - NOT USED
    pass

... (many more functions)

def predict_batch(sentences):  # Line 520 - USED! ✓
    results = []
    for sentence in sentences:
        results.append(predict(sentence))
    return results

def predict(text):  # Line 530 - DEPENDENCY! ✓
    # predict_batch calls this
    return model.predict(text)
```

**Extract only:**
1. `validate_sentence` (line 50) - directly imported
2. `predict_batch` (line 520) - directly imported
3. `predict` (line 530) - called by predict_batch

**Skip:**
- `function_1`, `function_3`, and 20 other unused functions

### Step 3: Extract Dependencies Recursively

```python
def predict_batch(sentences):  # ← Test imports this
    results = []
    for sentence in sentences:
        results.append(predict(sentence))  # ← Calls predict()
    return results

def predict(text):  # ← predict_batch depends on this
    if MODEL is None:  # ← Uses MODEL constant
        raise Exception("Not loaded")
    return MODEL.predict(text)
```

**Dependency chain:**
1. Test uses `predict_batch`
2. `predict_batch` calls `predict`
3. `predict` uses `MODEL` constant

**Extract all three:**
```python
MODEL = None  # Constant (dependency)

def predict(text):  # Function (dependency)
    if MODEL is None:
        raise Exception("Not loaded")
    return MODEL.predict(text)

def predict_batch(sentences):  # Function (directly used)
    results = []
    for sentence in sentences:
        results.append(predict(sentence))
    return results

# Total: ~30 lines instead of 567 ✓
```

---

## Step 4: Parse Error Traceback for Additional Context

Some functions aren't imported but appear in error messages:

```python
# Test error message
Traceback (most recent call last):
  File "tests/test_model.py", line 45, in test_predict_batch
    result = predict_batch(["hello"])
  File "app/main.py", line 520, in predict_batch
    results.append(predict(sentence))
  File "app/main.py", line 530, in predict
    return MODEL.predict(text)
  File "app/main.py", line 350, in load_model  # ← Additional context!
    MODEL = load_from_disk()
AttributeError: 'NoneType' object has no attribute 'predict'
```

**Parse traceback to extract:**
- Line 520: `predict_batch` (already extracted)
- Line 530: `predict` (already extracted)
- Line 350: `load_model` (NEW - add this too!)

---

## Implementation Algorithm

```python
def _extract_relevant_code_targeted(
    self,
    source_file: str,
    test_file: str,
    error_message: str,
    max_lines: int = 300
) -> str:
    """
    Extract only the code relevant to the failing test.

    Steps:
    1. Parse test file to find imported names
    2. Parse source file to build function/class map
    3. Extract imported functions and their dependencies
    4. Parse error traceback for additional functions
    5. Fill remaining space with imports/constants
    """

    # Step 1: Find what the test imports
    test_imports = self._parse_test_imports(test_file)
    # Example: {'predict_batch', 'validate_sentence', 'app_main'}

    # Step 2: Build map of all functions in source file
    source_map = self._build_source_map(source_file)
    # Example: {
    #   'validate_sentence': (ast.FunctionDef, lines 50-60),
    #   'predict_batch': (ast.FunctionDef, lines 520-535),
    #   'predict': (ast.FunctionDef, lines 530-545),
    #   'MODEL': (ast.Assign, line 10)
    # }

    # Step 3: Find functions mentioned in error traceback
    error_functions = self._parse_error_traceback(error_message, source_file)
    # Example: {'predict_batch', 'predict', 'load_model'}

    # Step 4: Combine all targets
    target_names = test_imports | error_functions

    # Step 5: Extract target functions + their dependencies
    extracted = []
    current_lines = 0

    # Priority 1: Imports and constants (always include)
    for name, (node, line_range) in source_map.items():
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.Assign)):
            code = ast.unparse(node)
            lines = len(code.split('\n'))
            if current_lines + lines <= max_lines:
                extracted.append(code)
                current_lines += lines

    # Priority 2: Target functions (the ones actually used)
    for target_name in target_names:
        if target_name in source_map:
            node, line_range = source_map[target_name]
            code = ast.unparse(node)
            lines = len(code.split('\n'))

            if current_lines + lines <= max_lines:
                extracted.append(code)
                current_lines += lines

                # Also extract dependencies
                deps = self._find_dependencies(node, source_map)
                for dep in deps:
                    if dep in source_map:
                        dep_node, _ = source_map[dep]
                        dep_code = ast.unparse(dep_node)
                        dep_lines = len(dep_code.split('\n'))
                        if current_lines + dep_lines <= max_lines:
                            extracted.append(dep_code)
                            current_lines += dep_lines

    # Step 6: If still have space, add surrounding context
    if current_lines < max_lines:
        # Add other functions that might be relevant
        for name, (node, line_range) in source_map.items():
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                if name not in target_names:  # Not already added
                    code = ast.unparse(node)
                    lines = len(code.split('\n'))
                    if current_lines + lines <= max_lines:
                        extracted.append(code)
                        current_lines += lines

    result = "\n\n".join(extracted)
    result += f"\n\n# ... (extracted {current_lines} relevant lines from {total_lines} total)"

    return result
```

---

## Helper Functions

### Parse Test Imports
```python
def _parse_test_imports(self, test_file: str) -> Set[str]:
    """Extract what the test imports from source files."""
    with open(test_file, 'r') as f:
        tree = ast.parse(f.read())

    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.asname or alias.name)

        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imports.add(alias.asname or alias.name)

    return imports
```

### Build Source Map
```python
def _build_source_map(self, source_file: str) -> Dict[str, Tuple[ast.AST, Tuple[int, int]]]:
    """Build a map of all definitions in source file."""
    with open(source_file, 'r') as f:
        content = f.read()

    tree = ast.parse(content)
    source_map = {}

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            name = node.name
            line_start = node.lineno
            line_end = node.end_lineno
            source_map[name] = (node, (line_start, line_end))

        elif isinstance(node, ast.Assign):
            # Constants like MODEL = None
            for target in node.targets:
                if isinstance(target, ast.Name):
                    source_map[target.id] = (node, (node.lineno, node.lineno))

    return source_map
```

### Parse Error Traceback
```python
def _parse_error_traceback(self, error_message: str, source_file: str) -> Set[str]:
    """Extract function names from error traceback."""
    import re

    functions = set()

    # Pattern: File "app/main.py", line 520, in predict_batch
    pattern = rf'File "{re.escape(source_file)}", line \d+, in (\w+)'

    for match in re.finditer(pattern, error_message):
        function_name = match.group(1)
        functions.add(function_name)

    return functions
```

### Find Dependencies
```python
def _find_dependencies(self, node: ast.AST, source_map: Dict) -> Set[str]:
    """Find what functions/variables this node uses."""
    dependencies = set()

    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            # Variable or function reference
            if child.id in source_map:
                dependencies.add(child.id)

        elif isinstance(child, ast.Call):
            # Function call
            if isinstance(child.func, ast.Name):
                if child.func.id in source_map:
                    dependencies.add(child.func.id)

    return dependencies
```

---

## Example: Before vs After

### Test Case
```python
# tests/test_model.py
from app.main import predict_batch

def test_predict_batch():
    result = predict_batch(["hello", "world"])
    assert isinstance(result, list)
```

### Source File (567 lines)
```python
# app/main.py

import fastapi

MODEL = None  # Line 10

def load_model():  # Lines 20-25
    global MODEL
    MODEL = load_from_disk()

def function_1():  # Lines 30-35 - NOT USED
    pass

def function_2():  # Lines 40-45 - NOT USED
    pass

... (15 more unused functions)

def predict(text):  # Lines 450-460 - DEPENDENCY
    if MODEL is None:
        raise Exception("Not loaded")
    return MODEL.predict(text)

def predict_batch(sentences):  # Lines 520-535 - USED!
    results = []
    for sentence in sentences:
        results.append(predict(sentence))
    return results

def function_20():  # Lines 540-567 - NOT USED
    pass
```

### Blind Truncation (Current)
```python
# Extracted: Lines 1-164 (first 20 functions)
import fastapi
MODEL = None
def load_model(): ...
def function_1(): ...
def function_2(): ...
... (15 more functions)

# MISSING: predict_batch (line 520) ❌
# MISSING: predict (line 450) ❌
```

**Result**: Test fix fails - LLM doesn't see the needed functions!

### Targeted Extraction (Improved)
```python
# Extracted: Only what's needed (~40 lines)
import fastapi

MODEL = None  # Constant (used by predict)

def predict(text):  # Dependency of predict_batch
    if MODEL is None:
        raise Exception("Not loaded")
    return MODEL.predict(text)

def predict_batch(sentences):  # Directly imported by test
    results = []
    for sentence in sentences:
        results.append(predict(sentence))
    return results

# ... (extracted 40 relevant lines from 567 total)
```

**Result**: Test fix succeeds - LLM has exactly what it needs! ✓

---

## Token Savings

### Blind Truncation
- Extracted: 164 lines (many irrelevant functions)
- Token usage: ~6,000 tokens
- Relevance: ~20% (only 2-3 functions actually needed)

### Targeted Extraction
- Extracted: 40 lines (only relevant functions)
- Token usage: ~1,500 tokens
- Relevance: 100% (every function is needed)

**Improvement:**
- 75% fewer tokens used ✓
- 100% relevant context ✓
- Can extract more files with saved tokens ✓

---

## When Targeted Extraction Helps Most

### Scenario 1: Large Single File
```
app/main.py (567 lines, 50 functions)
Test uses: 2 functions at lines 450-520

Blind: Extract first 164 lines ❌
Targeted: Extract 2 specific functions ✓
```

### Scenario 2: Deep Call Stack
```
Test → function_a (line 500) → function_b (line 400) → function_c (line 300)

Blind: Might miss all three ❌
Targeted: Follows dependency chain ✓
```

### Scenario 3: Error in Utility Function
```
Error traceback shows:
  test_predict → predict_batch → validate → sanitize_input (line 100)

Blind: Might not extract sanitize_input ❌
Targeted: Extracts all functions in traceback ✓
```

---

## Fallback Strategy

If targeted extraction can't find specific functions:

```python
if not extracted:
    # Fallback to blind truncation (first N lines)
    return self._extract_first_n_lines(source_file, max_lines)
```

This ensures we always have SOME context, even if targeting fails.

---

## Implementation Complexity

### Simple Version (Good Enough)
1. Parse test imports ✓ (easy)
2. Find those functions in source ✓ (easy)
3. Extract them ✓ (easy)

**Estimated effort**: 2-3 hours

### Advanced Version (Ideal)
1. Parse test imports ✓
2. Find functions in source ✓
3. Parse error traceback ✓ (medium)
4. Extract dependencies recursively ✓ (hard)
5. Handle circular dependencies ✗ (complex)

**Estimated effort**: 1-2 days

---

## Summary

### Your Question
> "so what if the context or error fixing needs last function which is not included then it will fail right, so tell me how to fix this."

### The Answer

**Yes, blind truncation fails when needed functions are excluded!**

**Solution: Targeted Extraction**

1. **Parse test imports** → Find what functions the test uses
2. **Parse error traceback** → Find what functions appear in errors
3. **Extract those specific functions** → Regardless of line number
4. **Extract dependencies** → Include functions they call
5. **Fill remaining space** → Add imports/constants

**Result:**
- ✓ Always extracts the functions the test needs (even if at line 500)
- ✓ Uses fewer tokens (only relevant code)
- ✓ Higher fix success rate (LLM has the right context)

---

## Next Steps

Would you like me to implement targeted extraction? I can create:

1. **Simple version** (parse imports → extract those functions)
2. **Advanced version** (+ error traceback + dependencies)

Which would you prefer?
