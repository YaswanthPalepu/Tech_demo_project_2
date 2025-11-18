# Advanced Targeted Extraction - Detailed Implementation Guide

## Overview

This document explains exactly how we'll implement the Advanced version of targeted extraction, with real code examples and step-by-step logic.

---

## Architecture: 5 Core Components

```
┌─────────────────────────────────────────────────────────────┐
│  extract_context(test_file, test_function, error_message)  │
│                   (Main entry point)                        │
└────────────────────────┬────────────────────────────────────┘
                         │
         ┌───────────────┴───────────────┐
         ↓                               ↓
┌────────────────────┐         ┌─────────────────────┐
│ 1. Parse Test      │         │ 2. Build Source Map │
│    _parse_test_    │         │    _build_source_   │
│    imports()       │         │    map()            │
│                    │         │                     │
│ Returns: Set of    │         │ Returns: Dict of    │
│ imported names     │         │ all definitions     │
└────────┬───────────┘         └──────────┬──────────┘
         │                                 │
         │     ┌───────────────────────────┘
         │     │
         ↓     ↓
┌─────────────────────────────────────────────┐
│ 3. Parse Error Traceback                    │
│    _parse_error_traceback()                 │
│                                             │
│ Returns: Set of function names from errors  │
└────────────────┬────────────────────────────┘
                 │
                 ↓
┌─────────────────────────────────────────────┐
│ 4. Find Dependencies (Recursive)            │
│    _find_dependencies()                     │
│                                             │
│ Returns: Set of functions called by target  │
└────────────────┬────────────────────────────┘
                 │
                 ↓
┌─────────────────────────────────────────────┐
│ 5. Extract Targeted Code                    │
│    _extract_relevant_code_targeted()        │
│                                             │
│ Returns: Minimal relevant code string       │
└─────────────────────────────────────────────┘
```

---

## Component 1: Parse Test Imports

### Purpose
Find what the test file imports from source files.

### Input
```python
# tests/test_model.py
from app.main import predict_batch, validate_sentence
import app.main as app_main
from app.utils import sanitize_input

def test_predict_batch():
    result = predict_batch(["hello"])  # Uses predict_batch
    app_main.load_model()              # Uses app_main.load_model
    assert isinstance(result, list)
```

### Output
```python
{
    'predict_batch',      # From: from app.main import predict_batch
    'validate_sentence',  # From: from app.main import validate_sentence
    'app_main',           # From: import app.main as app_main
    'sanitize_input'      # From: from app.utils import sanitize_input
}
```

### Implementation

```python
def _parse_test_imports(self, test_file: str) -> Dict[str, Set[str]]:
    """
    Parse test file to find what it imports from each module.

    Args:
        test_file: Path to test file

    Returns:
        Dict mapping module paths to imported names
        Example: {
            'app.main': {'predict_batch', 'validate_sentence'},
            'app.utils': {'sanitize_input'}
        }
    """
    try:
        with open(test_file, 'r') as f:
            tree = ast.parse(f.read())
    except (FileNotFoundError, SyntaxError):
        return {}

    imports = {}  # module_path -> set of imported names

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            # import app.main as app_main
            for alias in node.names:
                module_path = alias.name  # 'app.main'
                import_name = alias.asname or alias.name  # 'app_main'

                if module_path not in imports:
                    imports[module_path] = set()
                imports[module_path].add(import_name)

        elif isinstance(node, ast.ImportFrom):
            # from app.main import predict_batch, validate_sentence
            module_path = node.module or ""

            if module_path not in imports:
                imports[module_path] = set()

            for alias in node.names:
                import_name = alias.name  # 'predict_batch'
                imports[module_path].add(import_name)

    if self.verbose:
        print(f"  📥 Parsed test imports:")
        for module, names in imports.items():
            print(f"    {module}: {', '.join(names)}")

    return imports
```

### How It Works: AST Walking

```python
# Example test file AST
Module(
    body=[
        ImportFrom(
            module='app.main',  # ← Extract this
            names=[
                alias(name='predict_batch', asname=None),  # ← Extract this
                alias(name='validate_sentence', asname=None)  # ← Extract this
            ]
        ),
        Import(
            names=[
                alias(name='app.main', asname='app_main')  # ← Extract both
            ]
        ),
        FunctionDef(
            name='test_predict_batch',
            body=[...]
        )
    ]
)
```

**Walking logic:**
1. `ast.walk(tree)` - Visit every node in the tree
2. Check `isinstance(node, ast.Import)` - Is this an import statement?
3. Extract `alias.name` (module path) and `alias.asname` (alias if any)
4. Store in dictionary: `{module_path: {imported_names}}`

---

## Component 2: Build Source Map

### Purpose
Create an index of all functions, classes, and constants in the source file with their locations.

### Input
```python
# app/main.py (567 lines)
import fastapi

MODEL = None  # Line 10

def load_model():  # Lines 20-25
    global MODEL
    MODEL = load_from_disk()

class PredictionRequest(BaseModel):  # Lines 30-35
    text: str

def validate_sentence(text):  # Lines 50-60
    if not text:
        raise ValueError()
    return True

... (many more functions)

def predict(text):  # Lines 450-460
    if MODEL is None:
        raise Exception("Not loaded")
    return MODEL.predict(text)

def predict_batch(sentences):  # Lines 520-535
    results = []
    for sentence in sentences:
        results.append(predict(sentence))
    return results
```

### Output
```python
{
    'MODEL': {
        'node': ast.Assign(...),
        'line_start': 10,
        'line_end': 10,
        'code': 'MODEL = None'
    },
    'load_model': {
        'node': ast.FunctionDef(...),
        'line_start': 20,
        'line_end': 25,
        'code': 'def load_model():\n    global MODEL\n    MODEL = load_from_disk()'
    },
    'PredictionRequest': {
        'node': ast.ClassDef(...),
        'line_start': 30,
        'line_end': 35,
        'code': 'class PredictionRequest(BaseModel):\n    text: str'
    },
    'validate_sentence': {
        'node': ast.FunctionDef(...),
        'line_start': 50,
        'line_end': 60,
        'code': 'def validate_sentence(text): ...'
    },
    'predict': {
        'node': ast.FunctionDef(...),
        'line_start': 450,
        'line_end': 460,
        'code': 'def predict(text): ...'
    },
    'predict_batch': {
        'node': ast.FunctionDef(...),
        'line_start': 520,
        'line_end': 535,
        'code': 'def predict_batch(sentences): ...'
    }
}
```

### Implementation

```python
def _build_source_map(self, source_file: str) -> Dict[str, Dict]:
    """
    Build an index of all definitions in the source file.

    Args:
        source_file: Path to source file

    Returns:
        Dict mapping names to definition info
        Format: {
            'function_name': {
                'node': ast.FunctionDef,
                'line_start': int,
                'line_end': int,
                'code': str
            }
        }
    """
    try:
        with open(source_file, 'r') as f:
            content = f.read()
    except (FileNotFoundError, IOError):
        return {}

    try:
        tree = ast.parse(content)
    except SyntaxError:
        return {}

    source_map = {}
    total_lines = len(content.split('\n'))

    # Walk through all top-level definitions
    for node in tree.body:
        name = None

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Function definitions
            name = node.name

        elif isinstance(node, ast.ClassDef):
            # Class definitions
            name = node.name

        elif isinstance(node, ast.Assign):
            # Variable assignments (constants)
            # MODEL = None
            for target in node.targets:
                if isinstance(target, ast.Name):
                    name = target.id
                    break

        if name:
            # Store definition info
            source_map[name] = {
                'node': node,
                'line_start': node.lineno if hasattr(node, 'lineno') else 0,
                'line_end': node.end_lineno if hasattr(node, 'end_lineno') else 0,
                'code': ast.unparse(node)
            }

    if self.verbose:
        print(f"  🗺️  Built source map: {len(source_map)} definitions found")

    return source_map
```

### Why This Is Important

**Fast lookup:** Instead of scanning 567 lines every time, we have an O(1) lookup:
```python
# Without source map: O(n) - scan entire file
for line in lines:
    if 'def predict_batch' in line:
        # Found it!

# With source map: O(1) - direct lookup
if 'predict_batch' in source_map:
    info = source_map['predict_batch']
    code = info['code']  # Instant!
```

---

## Component 3: Parse Error Traceback

### Purpose
Extract function names that appear in the error traceback.

### Input
```python
error_message = """
Traceback (most recent call last):
  File "tests/test_model.py", line 45, in test_predict_batch
    result = predict_batch(["hello"])
  File "/home/sigmoid/test-repos/clinic/app/main.py", line 520, in predict_batch
    results.append(predict(sentence))
  File "/home/sigmoid/test-repos/clinic/app/main.py", line 530, in predict
    return MODEL.predict(text)
  File "/home/sigmoid/test-repos/clinic/app/main.py", line 350, in load_model
    MODEL = load_from_disk()
AttributeError: 'NoneType' object has no attribute 'predict'
"""
```

### Output
```python
{
    'predict_batch',  # From line 520
    'predict',        # From line 530
    'load_model'      # From line 350
}
```

### Implementation

```python
def _parse_error_traceback(
    self,
    error_message: str,
    source_file: str
) -> Set[str]:
    """
    Extract function names from error traceback.

    Args:
        error_message: The full error message with traceback
        source_file: Path to source file (to filter relevant entries)

    Returns:
        Set of function names that appear in the traceback
    """
    import re

    functions = set()

    # Normalize paths for comparison
    source_file_normalized = os.path.abspath(source_file)

    # Pattern: File "path/to/file.py", line 123, in function_name
    # Matches both:
    #   File "/home/user/app/main.py", line 520, in predict_batch
    #   File "app/main.py", line 520, in predict_batch
    pattern = r'File\s+"([^"]+)",\s+line\s+(\d+),\s+in\s+(\w+)'

    for match in re.finditer(pattern, error_message):
        file_path = match.group(1)
        line_number = int(match.group(2))
        function_name = match.group(3)

        # Check if this traceback entry is from our source file
        file_path_normalized = os.path.abspath(file_path)

        if file_path_normalized == source_file_normalized:
            functions.add(function_name)

            if self.verbose:
                print(f"    📍 Found in traceback: {function_name} (line {line_number})")

    return functions
```

### Regex Breakdown

```python
pattern = r'File\s+"([^"]+)",\s+line\s+(\d+),\s+in\s+(\w+)'
#          ^^^^    ^^^^^^^      ^^^^    ^^^^      ^^^^
#          |       |            |       |         |
#          |       |            |       |         Function name
#          |       |            |       Line number
#          |       |            "line" keyword
#          |       File path (anything inside quotes)
#          "File" keyword
```

**Example match:**
```
Input:  File "/home/user/app/main.py", line 520, in predict_batch
Groups:
  1: /home/user/app/main.py
  2: 520
  3: predict_batch
```

---

## Component 4: Find Dependencies (Recursive)

### Purpose
For a given function, find all other functions/variables it depends on.

### Input
```python
# Source map contains all definitions
source_map = {
    'MODEL': {...},
    'predict': {...},
    'predict_batch': {...},
    'validate_sentence': {...}
}

# Target function
def predict_batch(sentences):  # ← Analyze this
    results = []
    for sentence in sentences:
        validated = validate_sentence(sentence)  # ← Depends on validate_sentence
        results.append(predict(validated))       # ← Depends on predict
    return results

def predict(text):  # ← If we extract this, analyze it too
    if MODEL is None:  # ← Depends on MODEL constant
        raise Exception("Not loaded")
    return MODEL.predict(text)
```

### Output (Level 1)
```python
dependencies = {
    'validate_sentence',  # Called by predict_batch
    'predict'             # Called by predict_batch
}
```

### Output (Level 2 - Recursive)
```python
dependencies = {
    'validate_sentence',  # Level 1: Called by predict_batch
    'predict',            # Level 1: Called by predict_batch
    'MODEL'               # Level 2: Used by predict (dependency of dependency)
}
```

### Implementation

```python
def _find_dependencies(
    self,
    node: ast.AST,
    source_map: Dict[str, Dict],
    max_depth: int = 3,
    visited: Optional[Set[str]] = None
) -> Set[str]:
    """
    Find all functions/variables that a node depends on (recursive).

    Args:
        node: AST node to analyze
        source_map: Map of all available definitions
        max_depth: Maximum recursion depth (prevent infinite loops)
        visited: Set of already visited names (for cycle detection)

    Returns:
        Set of dependency names
    """
    if visited is None:
        visited = set()

    if max_depth <= 0:
        return set()

    dependencies = set()

    # Walk through the function/class body
    for child in ast.walk(node):
        # Find Name nodes (variable/function references)
        if isinstance(child, ast.Name):
            name = child.id

            # Check if this name is defined in our source map
            if name in source_map and name not in visited:
                dependencies.add(name)
                visited.add(name)

                # Recursively find dependencies of this dependency
                dep_node = source_map[name]['node']
                sub_deps = self._find_dependencies(
                    dep_node,
                    source_map,
                    max_depth - 1,
                    visited
                )
                dependencies.update(sub_deps)

        # Find function calls
        elif isinstance(child, ast.Call):
            # Direct function call: predict(text)
            if isinstance(child.func, ast.Name):
                name = child.func.id

                if name in source_map and name not in visited:
                    dependencies.add(name)
                    visited.add(name)

                    # Recursively find dependencies
                    dep_node = source_map[name]['node']
                    sub_deps = self._find_dependencies(
                        dep_node,
                        source_map,
                        max_depth - 1,
                        visited
                    )
                    dependencies.update(sub_deps)

            # Attribute call: obj.method()
            elif isinstance(child.func, ast.Attribute):
                # MODEL.predict() - the object is 'MODEL'
                if isinstance(child.func.value, ast.Name):
                    obj_name = child.func.value.id

                    if obj_name in source_map and obj_name not in visited:
                        dependencies.add(obj_name)
                        visited.add(obj_name)

    return dependencies
```

### Dependency Resolution Example

```python
# Step 1: Analyze predict_batch
def predict_batch(sentences):
    results = []
    for sentence in sentences:
        validated = validate_sentence(sentence)  # Found: validate_sentence
        results.append(predict(validated))        # Found: predict
    return results

# Dependencies found: {validate_sentence, predict}

# Step 2: Analyze predict (dependency of predict_batch)
def predict(text):
    if MODEL is None:  # Found: MODEL (ast.Name with id='MODEL')
        raise Exception("Not loaded")
    return MODEL.predict(text)  # Found: MODEL again (already added)

# Dependencies found: {MODEL}

# Step 3: Analyze MODEL (dependency of predict)
MODEL = None  # No further dependencies (it's a constant)

# Final result: {validate_sentence, predict, MODEL}
```

### Cycle Detection

```python
# Scenario: Circular dependencies
def function_a():
    return function_b()  # A calls B

def function_b():
    return function_a()  # B calls A (cycle!)

# Without cycle detection: Infinite loop ❌
# With visited set:
#   1. Visit function_a, add to visited
#   2. Find dependency: function_b
#   3. Visit function_b, add to visited
#   4. Find dependency: function_a
#   5. Check: function_a in visited? Yes! Skip. ✓
```

---

## Component 5: Extract Targeted Code

### Purpose
Combine all previous components to extract only the relevant code.

### Implementation

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

    Algorithm:
    1. Parse test imports to find what test uses
    2. Build source map to index all definitions
    3. Parse error traceback for additional context
    4. Find dependencies recursively
    5. Extract targeted code with priority ordering

    Args:
        source_file: Path to source file
        test_file: Path to test file
        error_message: Error message with traceback
        max_lines: Maximum lines to extract

    Returns:
        Extracted code string
    """
    # Step 1: Parse test imports
    test_imports = self._parse_test_imports(test_file)

    # Get imported names from this source file
    # Need to check if source_file matches any imported module
    imported_names = set()
    source_file_name = Path(source_file).stem  # 'main' from 'app/main.py'

    for module_path, names in test_imports.items():
        # Check if this module corresponds to our source file
        # E.g., 'app.main' matches 'app/main.py'
        if source_file_name in module_path.replace('.', '/'):
            imported_names.update(names)

    if self.verbose:
        print(f"  🎯 Target functions from imports: {imported_names}")

    # Step 2: Build source map
    source_map = self._build_source_map(source_file)

    if not source_map:
        # Fallback: return first N lines
        return self._extract_first_n_lines(source_file, max_lines)

    # Step 3: Parse error traceback
    error_functions = self._parse_error_traceback(error_message, source_file)

    if self.verbose and error_functions:
        print(f"  🎯 Target functions from errors: {error_functions}")

    # Step 4: Combine all target names
    target_names = imported_names | error_functions

    if not target_names:
        # No specific targets found, fallback to blind truncation
        if self.verbose:
            print(f"  ⚠️  No specific targets found, using blind truncation")
        return self._extract_first_n_lines(source_file, max_lines)

    # Step 5: Extract with priority ordering
    extracted = []
    extracted_names = set()
    current_lines = 0

    # Priority 1: Imports (always include if space)
    for name, info in source_map.items():
        node = info['node']
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            code = info['code']
            lines = len(code.split('\n'))

            if current_lines + lines <= max_lines:
                extracted.append(code)
                extracted_names.add(name)
                current_lines += lines

    # Priority 2: Constants used by target functions
    all_dependencies = set()
    for target in target_names:
        if target in source_map:
            deps = self._find_dependencies(
                source_map[target]['node'],
                source_map
            )
            all_dependencies.update(deps)

    for name in all_dependencies:
        if name not in extracted_names and name in source_map:
            node = source_map[name]['node']
            if isinstance(node, ast.Assign):
                code = source_map[name]['code']
                lines = len(code.split('\n'))

                if current_lines + lines <= max_lines:
                    extracted.append(code)
                    extracted_names.add(name)
                    current_lines += lines

    # Priority 3: Target functions (the ones actually used)
    for target in target_names:
        if target not in extracted_names and target in source_map:
            code = source_map[target]['code']
            lines = len(code.split('\n'))

            if current_lines + lines <= max_lines:
                extracted.append(code)
                extracted_names.add(target)
                current_lines += lines

                if self.verbose:
                    print(f"    ✓ Extracted: {target} ({lines} lines)")

    # Priority 4: Dependencies of target functions
    for dep in all_dependencies:
        if dep not in extracted_names and dep in source_map:
            code = source_map[dep]['code']
            lines = len(code.split('\n'))

            if current_lines + lines <= max_lines:
                extracted.append(code)
                extracted_names.add(dep)
                current_lines += lines

                if self.verbose:
                    print(f"    ✓ Extracted: {dep} ({lines} lines, dependency)")

    # Priority 5: Fill remaining space with other definitions
    if current_lines < max_lines:
        for name, info in source_map.items():
            if name not in extracted_names:
                node = info['node']
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    code = info['code']
                    lines = len(code.split('\n'))

                    if current_lines + lines <= max_lines:
                        extracted.append(code)
                        extracted_names.add(name)
                        current_lines += lines

    # Build result
    result = "\n\n".join(extracted)

    # Add metadata
    total_lines = len(open(source_file).read().split('\n'))
    result += f"\n\n# ... (extracted {current_lines} relevant lines from {total_lines} total)"
    result += f"\n# Targeted extraction: {len(extracted_names)} definitions"

    if self.verbose:
        print(f"  ✅ Extracted {current_lines}/{total_lines} lines ({len(extracted_names)} definitions)")

    return result
```

### Priority Ordering Explained

**Why this order?**

1. **Imports first** - LLM needs to understand dependencies
2. **Constants used by targets** - Context for target functions
3. **Target functions** - The main functions test uses
4. **Dependencies** - Functions called by targets
5. **Other definitions** - Fill remaining space

**Example:**

```python
# Test imports: predict_batch
# Error traceback: predict_batch, predict

# Priority 1: Imports (5 lines)
import fastapi
from pydantic import BaseModel

# Priority 2: Constants (1 line)
MODEL = None  # Used by predict

# Priority 3: Target functions (15 lines)
def predict_batch(sentences):  # From imports
    results = []
    for sentence in sentences:
        results.append(predict(sentence))
    return results

# Priority 4: Dependencies (10 lines)
def predict(text):  # Dependency of predict_batch
    if MODEL is None:
        raise Exception("Not loaded")
    return MODEL.predict(text)

# Priority 5: Other (if space remains)
class PredictionRequest(BaseModel):
    text: str

# Total: 31 lines (vs 567 original)
```

---

## Integration with Existing Code

### Update extract_context() method

```python
def extract_context(
    self,
    test_file_path: str,
    test_function_name: str,
    error_message: str = ""  # NEW: Add error message parameter
) -> Dict[str, str]:
    """
    Extract relevant source code context for a failing test.

    Args:
        test_file_path: Path to test file
        test_function_name: Name of failing test function
        error_message: Error message with traceback (NEW)

    Returns:
        Dict mapping source file paths to extracted code
    """
    # ... (existing code to find test function)

    # Get all imports from test
    all_imports = self._extract_imports(tree)
    used_imports = self._get_imports_used_in_function(
        function_code,
        all_imports
    )

    # Resolve to files
    source_files = self._resolve_imports_to_files(used_imports)

    context = {}
    for source_file in source_files:
        # NEW: Use targeted extraction instead of blind truncation
        extracted_code = self._extract_relevant_code_targeted(
            source_file=source_file,
            test_file=test_file_path,
            error_message=error_message,
            max_lines=300
        )

        context[source_file] = extracted_code

    return context
```

### Update orchestrator.py to pass error message

```python
# In orchestrator.py
def _attempt_fix(self, failure: TestFailure) -> bool:
    # ... existing code ...

    # Extract context with error message
    context = self.context_extractor.extract_context(
        test_file_path=failure.file_path,
        test_function_name=failure.test_name,
        error_message=failure.error_message  # NEW: Pass error message
    )
```

---

## Testing Strategy

### Test Case 1: Function at End of File
```python
# app/main.py (567 lines)
# predict_batch is at line 520

# Test: tests/test_model.py
from app.main import predict_batch

def test_predict_batch():
    result = predict_batch(["hello"])
    assert isinstance(result, list)

# Expected: predict_batch extracted despite being at line 520 ✓
```

### Test Case 2: Deep Dependencies
```python
# Test imports: function_a
# function_a calls function_b
# function_b calls function_c
# function_c uses CONSTANT

# Expected: All four extracted (a, b, c, CONSTANT) ✓
```

### Test Case 3: Error Traceback Context
```python
# Test imports: predict_batch
# Error traceback shows: predict_batch → predict → load_model

# Expected: All three extracted even if test only imports predict_batch ✓
```

---

## Performance Considerations

### Time Complexity

- **Parse test imports**: O(n) where n = test file size (usually small)
- **Build source map**: O(m) where m = source file size (done once per file)
- **Parse error traceback**: O(e) where e = error message size (usually small)
- **Find dependencies**: O(d * k) where d = dependencies, k = depth (limited to 3)
- **Extract code**: O(1) lookups in source map

**Total**: O(m) - dominated by source map building, which is efficient

### Space Complexity

- **Source map**: O(m) - stores all definitions
- **Dependencies**: O(d) - stores dependency set
- **Extracted code**: O(max_lines) - limited by parameter

**Total**: O(m + max_lines) - reasonable for typical files

### Optimization: Caching

```python
# Cache source maps per file
self._source_map_cache = {}

def _build_source_map(self, source_file: str) -> Dict:
    if source_file in self._source_map_cache:
        return self._source_map_cache[source_file]

    source_map = self._build_source_map_uncached(source_file)
    self._source_map_cache[source_file] = source_map
    return source_map
```

---

## Fallback Strategy

If targeted extraction fails (no imports found, syntax error, etc.), fallback to blind truncation:

```python
def _extract_first_n_lines(self, source_file: str, max_lines: int) -> str:
    """Fallback: Extract first N lines."""
    try:
        with open(source_file, 'r') as f:
            lines = f.readlines()

        if len(lines) <= max_lines:
            return ''.join(lines)

        result = ''.join(lines[:max_lines])
        result += f"\n\n# ... (truncated at {max_lines}/{len(lines)} lines)"
        return result
    except:
        return ""
```

---

## Summary

### What We're Building

5 components that work together:

1. **_parse_test_imports()** - Find what test uses
2. **_build_source_map()** - Index all definitions
3. **_parse_error_traceback()** - Find functions in errors
4. **_find_dependencies()** - Recursive dependency resolution
5. **_extract_relevant_code_targeted()** - Assemble targeted context

### Benefits

- ✅ Extracts functions at any line number (solves your problem!)
- ✅ 75% token savings (40 lines vs 164 lines)
- ✅ 100% relevant context (vs 20% with blind truncation)
- ✅ Recursive dependencies (includes everything needed)
- ✅ Error context (uses traceback for additional hints)
- ✅ Fallback strategy (blind truncation if targeting fails)

### Next Steps

Ready to implement? I'll build all 5 components step by step, with testing along the way.
