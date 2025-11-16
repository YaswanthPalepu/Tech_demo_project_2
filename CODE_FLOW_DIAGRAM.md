# Auto-Fixer: Complete Code Flow and Data Flow

## 📊 High-Level Architecture

```
┌──────────────┐
│   pytest     │ Runs tests, captures failures
└──────┬───────┘
       │ Text/JSON output
       ↓
┌──────────────────────┐
│  FailureParser       │ Parses output → structured objects
└──────┬───────────────┘
       │ List[TestFailure]
       ↓
┌──────────────────────┐
│ RuleClassifier       │ Pattern matching (fast)
└──────┬───────────────┘
       │ "test_mistake" | "unknown"
       ↓
   ┌───────┐
   │ if    │ unknown?
   └───┬───┘
       ↓ yes
┌──────────────────────────────────────────────────────────┐
│  AST Context Extractor + LLM Classifier                  │
│  1. Extract test imports → resolve to source files       │
│  2. Extract relevant source code (classes, functions)    │
│  3. Send to LLM for deep analysis                        │
└──────┬───────────────────────────────────────────────────┘
       │ LLMClassification (with suggested fix)
       ↓
   ┌───────┐
   │ if    │ test_mistake?
   └───┬───┘
       ↓ yes
┌──────────────────────┐
│  LLM Fixer           │ Generate corrected test function
└──────┬───────────────┘
       │ Fixed code string
       ↓
┌──────────────────────┐
│  AST Patcher         │ Replace function in file
└──────┬───────────────┘
       │ Modified test file
       ↓
┌──────────────────────┐
│  Re-run pytest       │ Verify fix worked
└──────┬───────────────┘
       │ New List[TestFailure]
       ↓
   ┌───────┐
   │ Loop  │ Repeat until all fixed or max iterations
   └───────┘
```

## 🔍 Detailed Function Call Flow

### Orchestrator Main Loop

```python
# run_auto_fixer.py
main()
  ├─ Creates: AutoTestFixerOrchestrator(test_dir, max_iterations=3)
  └─ Calls: orchestrator.run(extra_pytest_args)
```

### Step-by-Step Execution

```python
AutoTestFixerOrchestrator.run(extra_pytest_args):
    iteration = 0

    WHILE iteration < max_iterations AND not all_tests_fixed:
        iteration += 1

        # ═══════════════════════════════════════════════════════
        # STEP 1: Run pytest and parse failures
        # ═══════════════════════════════════════════════════════
        failures = FailureParser.run_and_parse(extra_pytest_args)
            │
            ├─ run_pytest_json(extra_args):
            │   │
            │   ├─ subprocess.run([
            │   │      'pytest', test_directory,
            │   │      '--tb=long', '--json-report', '-v'
            │   │  ])
            │   │  ↓ Returns: CompletedProcess
            │   │
            │   ├─ TRY: json.load("pytest_report.json")
            │   │  ↓ Returns: Dict[str, Any]
            │   │
            │   └─ EXCEPT: _parse_text_output(stdout)
            │       └─ Parse "FAILED tests/..." lines
            │          ↓ Returns: Dict[str, Any] (JSON-like)
            │
            └─ parse_failures(json_output):
                │
                FOR test in json_output["tests"]:
                    IF test["outcome"] in ["failed", "error"]:
                        │
                        ├─ nodeid = test["nodeid"]
                        ├─ test_file, test_name = _parse_nodeid(nodeid)
                        │   └─ Split "tests/test_foo.py::test_bar"
                        │
                        ├─ longrepr = test["call"]["longrepr"]
                        ├─ exception_type, error_message = _parse_exception(longrepr)
                        │   └─ Parse "NameError: name 'User' is not defined"
                        │
                        ├─ line_number = _extract_line_number(longrepr, test_file)
                        │   └─ Regex search for "test_file.py:123:"
                        │
                        └─ CREATE: TestFailure(
                               test_file="tests/test_user_example.py",
                               test_name="test_user_creation",
                               exception_type="NameError",
                               error_message="name 'User' is not defined",
                               traceback="<full trace>",
                               line_number=16
                           )

                ↓ Returns: List[TestFailure]

        IF no failures:
            BREAK  # All tests passing!

        # ═══════════════════════════════════════════════════════
        # STEP 2-6: Process each failure
        # ═══════════════════════════════════════════════════════
        FOR failure in failures:

            result = _process_failure(failure)
                │
                # ─────────────────────────────────────────────────
                # Read test function code
                # ─────────────────────────────────────────────────
                ├─ test_code = _read_test_function(failure):
                │   │
                │   ├─ Read file: failure.test_file
                │   ├─ tree = ast.parse(content)
                │   │
                │   └─ FOR node in ast.walk(tree):
                │          IF isinstance(node, ast.FunctionDef):
                │              IF node.name == failure.test_name:
                │                  RETURN ast.unparse(node)
                │
                │   ↓ Returns: "def test_user_creation():\n    ..."
                │
                # ─────────────────────────────────────────────────
                # STEP 3A: Rule-based classification
                # ─────────────────────────────────────────────────
                ├─ rule_result = RuleBasedClassifier.classify(failure):
                │   │
                │   ├─ error_context = f"{exception_type} {error_message} {traceback}"
                │   │
                │   ├─ FOR pattern, description in TEST_MISTAKE_PATTERNS:
                │   │      IF re.search(pattern, error_context, IGNORECASE):
                │   │          RETURN "test_mistake"
                │   │
                │   └─ RETURN "unknown"
                │
                │   ↓ Returns: "test_mistake" | "unknown"
                │
                IF rule_result == "test_mistake":
                    RETURN _fix_test_mistake(failure, "rule-based")
                │
                # ─────────────────────────────────────────────────
                # STEP 4: Extract AST context
                # ─────────────────────────────────────────────────
                ├─ context = ASTContextExtractor.extract_context(
                │                failure.test_file,
                │                failure.test_name
                │            ):
                │   │
                │   ├─ Read test file
                │   ├─ tree = ast.parse(test_content)
                │   │
                │   ├─ imports = _extract_imports(tree):
                │   │   │
                │   │   └─ FOR node in ast.walk(tree):
                │   │          IF isinstance(node, ast.Import):
                │   │              FOR alias in node.names:
                │   │                  imports[alias.name] = alias.name
                │   │
                │   │          ELIF isinstance(node, ast.ImportFrom):
                │   │              FOR alias in node.names:
                │   │                  full = f"{node.module}.{alias.name}"
                │   │                  imports[alias.name] = full
                │   │
                │   │   ↓ Returns: {"User": "src.user_module.User", ...}
                │   │
                │   ├─ test_func_code = _extract_test_function(tree, func_name):
                │   │   └─ Find FunctionDef, ast.unparse() it
                │   │   ↓ Returns: "def test_user_creation(): ..."
                │   │
                │   ├─ used_imports = _get_function_imports(test_func_code, imports):
                │   │   │
                │   │   └─ FOR name, module_path in imports.items():
                │   │          IF name in test_func_code:
                │   │              used_imports.add(module_path)
                │   │
                │   │   ↓ Returns: {"src.user_module.User"}
                │   │
                │   ├─ source_files = _resolve_imports_to_files(used_imports):
                │   │   │
                │   │   ├─ FILTER: Remove stdlib/third-party
                │   │   │   └─ Skip: os, sys, pytest, django, etc.
                │   │   │
                │   │   └─ FOR import_path in filtered:
                │   │          file_path = _module_to_file(import_path):
                │   │              # Try: "src.user_module" → "src/user_module.py"
                │   │              # Try: "src.user_module" → "src/user_module/__init__.py"
                │   │              IF exists:
                │   │                  source_files.append(file_path)
                │   │
                │   │   ↓ Returns: ["src/user_module.py"]
                │   │
                │   └─ FOR source_file in source_files:
                │          code = _extract_relevant_code(source_file, used_imports):
                │              │
                │              ├─ tree = ast.parse(source_content)
                │              │
                │              └─ FOR node in tree.body:
                │                     IF isinstance(node, ast.FunctionDef):
                │                         relevant_code.append(ast.unparse(node))
                │                     ELIF isinstance(node, ast.ClassDef):
                │                         relevant_code.append(ast.unparse(node))
                │
                │              ↓ Returns: "class User:\n    def __init__..."
                │
                │          context[source_file] = code
                │
                │   ↓ Returns: {"src/user_module.py": "class User: ..."}
                │
                ├─ context_string = extractor.get_full_context_string(...)
                │   └─ Format context as markdown string
                │   ↓ Returns: "# src/user_module.py\n```python\nclass User:..."
                │
                # ─────────────────────────────────────────────────
                # STEP 3B: LLM classification
                # ─────────────────────────────────────────────────
                ├─ llm_result = LLMClassifier.classify(
                │                   failure, test_code, context_string
                │               ):
                │   │
                │   ├─ prompt = _build_prompt(failure, test_code, context_string):
                │   │   └─ Format as:
                │   │       # Test Failure Analysis
                │   │       ## Failing Test
                │   │       ## Error Information
                │   │       ## Traceback
                │   │       ## Test Code
                │   │       ## Source Code Being Tested
                │   │   ↓ Returns: formatted prompt string
                │   │
                │   ├─ response = openai_client.chat.completions.create(
                │   │       model="gpt-4",
                │   │       messages=[
                │   │           {"role": "system", "content": SYSTEM_PROMPT},
                │   │           {"role": "user", "content": prompt}
                │   │       ],
                │   │       temperature=0.1
                │   │   )
                │   │   ↓ Returns: ChatCompletion
                │   │
                │   ├─ content = response.choices[0].message.content
                │   │   └─ Extract JSON from markdown code blocks
                │   │
                │   └─ result = json.loads(content)
                │       ↓ Returns: LLMClassification(
                │             classification="test_mistake",
                │             reason="User class not imported",
                │             fixed_code="def test_user_creation(): ...",
                │             confidence=0.95
                │         )
                │
                IF llm_result.classification == "code_bug":
                    RETURN FixResult(
                        classification="code_bug",
                        fix_attempted=False,
                        reason=llm_result.reason
                    )
                │
                # ─────────────────────────────────────────────────
                # STEP 5: Generate fix (if needed)
                # ─────────────────────────────────────────────────
                ├─ IF llm_result.fixed_code:
                │      fixed_code = llm_result.fixed_code
                │  ELSE:
                │      fixed_code = LLMFixer.fix_test(
                │                       failure, test_code, context_string
                │                   ):
                │       │
                │       ├─ prompt = _build_prompt(...):
                │       │   └─ Format fixing prompt
                │       │
                │       ├─ response = openai_client.chat.completions.create(...)
                │       │
                │       └─ fixed_code = _extract_code(response.content):
                │              └─ Remove markdown code blocks
                │          ↓ Returns: "def test_user_creation():\n    from..."
                │
                # ─────────────────────────────────────────────────
                # STEP 6: Apply fix
                # ─────────────────────────────────────────────────
                └─ success = ASTPatcher.patch_test_function(
                                failure.test_file,
                                failure.test_name,
                                fixed_code
                            ):
                    │
                    ├─ Read original file
                    ├─ tree = ast.parse(content)
                    │
                    ├─ FOR node in ast.walk(tree):
                    │      IF isinstance(node, ast.FunctionDef):
                    │          IF node.name == test_function_name:
                    │              start_line = node.lineno - 1
                    │              end_line = node.end_lineno
                    │              BREAK
                    │
                    ├─ fixed_lines = _prepare_fixed_code(fixed_code, indent):
                    │   │
                    │   ├─ Split into lines
                    │   ├─ Find minimum indentation
                    │   └─ Adjust to match target indentation
                    │   ↓ Returns: List[str]
                    │
                    ├─ patched_lines = (
                    │       lines[:start_line] +
                    │       fixed_lines +
                    │       lines[end_line:]
                    │   )
                    │
                    ├─ Write to file
                    │
                    └─ validate_patch(test_file):
                           └─ ast.parse(new_content)
                        ↓ Returns: True if valid

            store_result(result)

        # ═══════════════════════════════════════════════════════
        # STEP 7: Check progress
        # ═══════════════════════════════════════════════════════
        IF no test_mistakes were fixed:
            BREAK  # Can't make progress

    # ═══════════════════════════════════════════════════════════
    # STEP 8: Generate summary
    # ═══════════════════════════════════════════════════════════
    RETURN _generate_summary(iteration):
        │
        ├─ Count: successful_fixes, failed_fixes, code_bugs
        ├─ Create summary dict
        ├─ Save to auto_fixer_report.json
        └─ RETURN summary
```

## 📦 Data Structures at Each Step

### 1. Pytest Output (JSON format)

```json
{
  "tests": [
    {
      "nodeid": "tests/test_user_example.py::test_user_creation",
      "outcome": "failed",
      "call": {
        "longrepr": "tests/test_user_example.py:16: in test_user_creation\n    user = User(...)\nE   NameError: name 'User' is not defined"
      }
    }
  ],
  "summary": {
    "total": 4,
    "passed": 0,
    "failed": 4
  }
}
```

### 2. TestFailure Object

```python
@dataclass
class TestFailure:
    test_file: str = "tests/test_user_example.py"
    test_name: str = "test_user_creation"
    exception_type: str = "NameError"
    error_message: str = "name 'User' is not defined"
    traceback: str = "tests/test_user_example.py:16: in test_user_creation\n..."
    line_number: int = 16
    full_test_node: str = "tests/test_user_example.py::test_user_creation"
```

### 3. Test Function Code (from AST)

```python
# Extracted by ast.parse() → find FunctionDef → ast.unparse()
"""
def test_user_creation():
    '''Test user creation - MISTAKE: User class not imported.'''
    user = User('John Doe', 'john@example.com')
    assert user.name == 'John Doe'
    assert user.email == 'john@example.com'
"""
```

### 4. Imports Dictionary (from AST)

```python
# Extracted from test file AST
{
    "pytest": "pytest",
    "validate_email": "src.user_module.validate_email"
    # Missing: "User" → not imported! This is the bug!
}
```

### 5. Source Code Context (from AST)

```python
# Dict[file_path, relevant_code]
{
    "src/user_module.py": """
class User:
    '''Simple user class.'''

    def __init__(self, name: str, email: str):
        self.name = name
        self.email = email
        self.is_active = True

    def activate(self):
        self.is_active = True
        return True

def create_user(name: str, email: str) -> User:
    return User(name, email)

def validate_email(email: str) -> bool:
    return '@' in email and '.' in email.split('@')[1]
"""
}
```

### 6. LLM Classification Result

```python
@dataclass
class LLMClassification:
    classification: str = "test_mistake"  # or "code_bug"
    reason: str = "User class is defined in src.user_module but not imported in test file"
    fixed_code: str = """def test_user_creation():
    '''Test user creation - FIXED: Added import.'''
    from src.user_module import User

    user = User('John Doe', 'john@example.com')
    assert user.name == 'John Doe'
    assert user.email == 'john@example.com'"""
    confidence: float = 0.95
```

### 7. Fixed Test Code (from LLM)

```python
"""
def test_user_creation():
    '''Test user creation - FIXED: Added import.'''
    from src.user_module import User

    user = User('John Doe', 'john@example.com')
    assert user.name == 'John Doe'
    assert user.email == 'john@example.com'
"""
```

### 8. Patching Operation

```python
# Before (original file):
lines = [
    'import pytest',
    '',
    'def test_user_creation():',
    '    """Test user creation..."""',
    '    user = User("John", "john@example.com")',  # Line 16 - ERROR
    '    assert user.name == "John"',
    '',
]

# AST analysis:
start_line = 14  # 0-indexed: line 15 in editor
end_line = 17    # 1-indexed: line 17 in editor

# After patching:
lines = [
    'import pytest',
    '',
    'def test_user_creation():',              # Line 15
    '    """Test user creation - FIXED"""',   # Line 16
    '    from src.user_module import User',   # Line 17 - NEW!
    '',                                        # Line 18 - NEW!
    '    user = User("John", "john@example.com")',  # Line 19 - FIXED
    '    assert user.name == "John"',         # Line 20
    '',
]
```

### 9. Fix Result

```python
@dataclass
class FixResult:
    test_file: str = "tests/test_user_example.py"
    test_name: str = "test_user_creation"
    classification: str = "test_mistake"
    fix_attempted: bool = True
    fix_successful: bool = True
    reason: str = "Missing import for User class"
```

### 10. Final Summary

```json
{
  "iterations": 3,
  "total_failures": 4,
  "test_mistakes": 3,
  "code_bugs": 1,
  "successful_fixes": 3,
  "failed_fixes": 0,
  "fix_history": [
    {
      "test_file": "tests/test_user_example.py",
      "test_name": "test_user_creation",
      "classification": "test_mistake",
      "fix_successful": true,
      "reason": "Missing import for User class"
    },
    {
      "test_file": "tests/test_user_example.py",
      "test_name": "test_user_activation",
      "classification": "test_mistake",
      "fix_successful": true,
      "reason": "Missing import for User class"
    },
    {
      "test_file": "tests/test_user_example.py",
      "test_name": "test_create_user_function",
      "classification": "test_mistake",
      "fix_successful": true,
      "reason": "Missing import for create_user"
    },
    {
      "test_file": "tests/test_user_example.py",
      "test_name": "test_email_validation",
      "classification": "code_bug",
      "fix_successful": false,
      "reason": "Module path resolution issue - requires project config"
    }
  ]
}
```

## 🔄 Iteration Example

### Iteration 1

**Input:** 4 failing tests
- test_user_creation → NameError: User not defined
- test_user_activation → NameError: User not defined
- test_create_user_function → NameError: create_user not defined
- test_email_validation → ModuleNotFoundError: No module 'src'

**Processing:**
1. Classify all as "test_mistake" (NameError pattern)
2. Extract source code for User class
3. Generate fixes adding imports
4. Patch all 3 test functions
5. 4th test might be code bug (module path issue)

**Output:** 3 tests fixed, 1 potentially code bug

### Iteration 2

**Input:** 1 failing test (or 0 if all fixed)
- test_email_validation → ModuleNotFoundError

**Processing:**
1. Try to fix import path
2. If it's a code bug (wrong project structure), leave it

**Output:** Report remaining code bug

### Final Result

✅ **3 test mistakes fixed automatically**
⚠️ **1 code bug requires manual attention**

## 🎯 Key Insights

1. **AST is central**: Used for extracting, analyzing, and patching code
2. **Dual classification**: Fast pattern matching + smart LLM analysis
3. **Context-aware**: Only extracts relevant source code, not entire project
4. **Surgical fixes**: Replaces only failing functions, preserves everything else
5. **Iterative**: Re-runs tests to verify fixes and catch new issues
6. **Conservative**: Stops at max iterations to prevent infinite loops
