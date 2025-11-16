#!/usr/bin/env python3
"""
Simplified Auto-Fixer Flow Demo

Shows the exact code flow without running the full system.
"""

import subprocess
import json


def print_section(title):
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def print_step(step_num, description):
    print(f"\n>>> STEP {step_num}: {description}")
    print("-" * 80)


print_section("AUTO-FIXER CODE FLOW DEMONSTRATION")
print("\nThis demonstrates how the auto-fixer processes failing tests")

# =============================================================================
# STEP 1: Show the test file with mistakes
# =============================================================================
print_step(1, "Show test file with intentional mistakes")

print("\n📄 tests/test_user_example.py:")
print("-" * 80)
with open("tests/test_user_example.py", "r") as f:
    content = f.read()
    print(content)
print("-" * 80)

print("\n🔍 Mistakes in this file:")
print("   1. Line 11: User class not imported")
print("   2. Line 19: User class not imported")
print("   3. Line 28: create_user function not imported")

# =============================================================================
# STEP 2: Show the source code being tested
# =============================================================================
print_step(2, "Show source code being tested")

print("\n📄 src/user_module.py:")
print("-" * 80)
with open("src/user_module.py", "r") as f:
    content = f.read()
    print(content)
print("-" * 80)

# =============================================================================
# STEP 3: Run pytest to see the failures
# =============================================================================
print_step(3, "Run pytest to capture failures")

print("\n📝 Running: pytest tests/test_user_example.py -v --tb=short")
result = subprocess.run(
    ["pytest", "tests/test_user_example.py", "-v", "--tb=short"],
    capture_output=True,
    text=True
)

print("\n📊 Pytest output:")
print("-" * 80)
print(result.stdout)
print("-" * 80)

# =============================================================================
# STEP 4: Parse failures from output
# =============================================================================
print_step(4, "Parse failures into structured objects")

print("\n📝 The FailureParser extracts:")
print("""
For each FAILED line like:
  FAILED tests/test_user_example.py::test_user_creation - NameError: name 'User' is not defined

It creates a TestFailure object:
  {
    "test_file": "tests/test_user_example.py",
    "test_name": "test_user_creation",
    "exception_type": "NameError",
    "error_message": "name 'User' is not defined",
    "traceback": "<full traceback>",
    "line_number": 11
  }
""")

# Count failures
failures = [line for line in result.stdout.split('\n') if line.startswith('FAILED')]
print(f"\n✓ Found {len(failures)} failure(s)")
for i, failure in enumerate(failures, 1):
    print(f"   {i}. {failure}")

# =============================================================================
# STEP 5: Classify each failure
# =============================================================================
print_step(5, "Classify failures (test_mistake vs code_bug)")

print("\n📝 Rule-based classification:")
print("""
The RuleBasedClassifier checks patterns:

Pattern: "NameError.*is not defined"
Reason:  "Undefined variable in test"
Result:  → test_mistake

Why? Because NameError in a test usually means missing import or typo.
""")

print("\n📝 If rule classifier returns 'unknown', use LLM classifier:")
print("""
LLM receives:
  - Test code: def test_user_creation(): ...
  - Source code: class User: ...
  - Error: NameError: name 'User' is not defined

LLM analyzes and returns:
  {
    "classification": "test_mistake",
    "reason": "User class is defined in src.user_module but not imported in test",
    "fixed_code": "<corrected test with import>",
    "confidence": 0.95
  }
""")

# =============================================================================
# STEP 6: Extract source code context
# =============================================================================
print_step(6, "Extract source code context using AST")

print("\n📝 How AST extraction works:")
print("""
1. Parse test file AST:
   import ast
   tree = ast.parse(test_file_content)

2. Extract all imports:
   for node in ast.walk(tree):
       if isinstance(node, ast.Import):
           # Extract import names
       elif isinstance(node, ast.ImportFrom):
           # Extract from-import names

3. Find the failing test function:
   for node in ast.walk(tree):
       if isinstance(node, ast.FunctionDef) and node.name == "test_user_creation":
           test_code = ast.unparse(node)

4. Identify which imports are used in that function:
   - Look for "User" in test_code
   - Find that it should come from src.user_module

5. Resolve import path to file:
   "src.user_module" → "src/user_module.py"

6. Extract relevant code from source file:
   - Parse src/user_module.py
   - Extract class User definition
   - Extract related functions
""")

import ast

print("\n📝 Example: Extracting test function AST")
with open("tests/test_user_example.py", "r") as f:
    test_content = f.read()

tree = ast.parse(test_content)
for node in ast.walk(tree):
    if isinstance(node, ast.FunctionDef) and node.name == "test_user_creation":
        print("-" * 80)
        print(ast.unparse(node))
        print("-" * 80)
        break

print("\n📝 Example: Extracting source class AST")
with open("src/user_module.py", "r") as f:
    source_content = f.read()

tree = ast.parse(source_content)
for node in tree.body:
    if isinstance(node, ast.ClassDef) and node.name == "User":
        code = ast.unparse(node)
        print("-" * 80)
        print(code[:300] + "..." if len(code) > 300 else code)
        print("-" * 80)
        break

# =============================================================================
# STEP 7: Generate fix
# =============================================================================
print_step(7, "Generate fix using LLM")

print("\n📝 LLM receives a prompt like:")
print("-" * 80)
print("""# Fix This Failing Test

## Original Test Code
```python
def test_user_creation():
    \"\"\"Test user creation - MISTAKE: User class not imported.\"\"\"
    user = User("John Doe", "john@example.com")
    assert user.name == "John Doe"
```

## Error Information
**Exception:** NameError
**Message:** name 'User' is not defined

## Traceback
```
tests/test_user_example.py:11: in test_user_creation
    user = User("John Doe", "john@example.com")
E   NameError: name 'User' is not defined
```

## Source Code Being Tested
```python
class User:
    def __init__(self, name: str, email: str):
        self.name = name
        self.email = email
        ...
```

## Task
Generate a fixed version of the test function.
Return ONLY the fixed code.
""")
print("-" * 80)

print("\n📝 LLM returns:")
print("-" * 80)
print("""def test_user_creation():
    \"\"\"Test user creation - FIXED: Added import.\"\"\"
    from src.user_module import User

    user = User("John Doe", "john@example.com")
    assert user.name == "John Doe"
    assert user.email == "john@example.com\"""")
print("-" * 80)

# =============================================================================
# STEP 8: Apply fix using AST patcher
# =============================================================================
print_step(8, "Apply fix using AST patcher")

print("\n📝 AST patcher process:")
print("""
1. Read original test file
2. Parse into AST to find the function:
   for node in ast.walk(tree):
       if isinstance(node, ast.FunctionDef) and node.name == "test_user_creation":
           start_line = node.lineno - 1        # e.g., 10 (0-indexed)
           end_line = node.end_lineno          # e.g., 14 (1-indexed)

3. Get the line range to replace:
   Original lines 10-14:
   [10] def test_user_creation():
   [11]     \"\"\"Test user creation...\"\"\"
   [12]     user = User("John Doe", "john@example.com")
   [13]     assert user.name == "John Doe"
   [14]     assert user.email == "john@example.com"

4. Replace with fixed code (preserving indentation):
   [10] def test_user_creation():
   [11]     \"\"\"Test user creation - FIXED\"\"\"
   [12]     from src.user_module import User
   [13]
   [14]     user = User("John Doe", "john@example.com")
   [15]     assert user.name == "John Doe"
   [16]     assert user.email == "john@example.com"

5. Write back to file
6. Validate with ast.parse() to ensure no syntax errors
""")

# =============================================================================
# STEP 9: Re-run pytest
# =============================================================================
print_step(9, "Re-run pytest to verify fix")

print("\n📝 After patching, run pytest again:")
print("""
pytest tests/test_user_example.py -v

Expected result:
  - test_user_creation: PASSED ✓ (was failing, now fixed)
  - test_user_activation: FAILED (still has same error)
  - test_create_user_function: FAILED (still has same error)

Progress: 1 test fixed, 2 still failing
Continue to iteration 2...
""")

# =============================================================================
# STEP 10: Complete flow
# =============================================================================
print_section("COMPLETE FUNCTION CALL FLOW")

print("""
┌─────────────────────────────────────────────────────────────────────────────┐
│ AutoTestFixerOrchestrator.run()                                              │
└─────────────────────────────────────────────────────────────────────────────┘
  │
  ├─ ITERATION 1
  │  │
  │  ├─ 1. FailureParser.run_and_parse()
  │  │     │
  │  │     ├─ run_pytest_json()
  │  │     │   └─ subprocess.run(['pytest', 'tests', '--tb=long', '-v'])
  │  │     │      → Returns: {"tests": [...], "summary": {...}}
  │  │     │
  │  │     └─ parse_failures(json_output)
  │  │        └─ For each failed test in json_output["tests"]:
  │  │           ├─ Extract: nodeid, outcome, longrepr
  │  │           ├─ Parse: test_file, test_name from nodeid
  │  │           ├─ Parse: exception_type, error_message from longrepr
  │  │           └─ Create: TestFailure object
  │  │              → Returns: List[TestFailure]
  │  │
  │  ├─ 2. FOR EACH failure in failures:
  │  │     │
  │  │     ├─ Read test file and extract test function code
  │  │     │  └─ ast.parse() → find FunctionDef → ast.unparse()
  │  │     │
  │  │     ├─ RuleBasedClassifier.classify(failure)
  │  │     │  └─ Match error patterns against TEST_MISTAKE_PATTERNS
  │  │     │     → Returns: "test_mistake" | "unknown"
  │  │     │
  │  │     ├─ IF "unknown": (SKIP FOR DEMO - NO LLM)
  │  │     │  │
  │  │     │  ├─ ASTContextExtractor.extract_context(test_file, test_name)
  │  │     │  │  │
  │  │     │  │  ├─ Parse test file: ast.parse(test_content)
  │  │     │  │  ├─ _extract_imports(tree)
  │  │     │  │  │  └─ Find all "import X" and "from X import Y"
  │  │     │  │  │     → Returns: {"User": "src.user_module.User", ...}
  │  │     │  │  │
  │  │     │  │  ├─ _extract_test_function(tree, "test_user_creation")
  │  │     │  │  │  └─ Find FunctionDef with matching name
  │  │     │  │  │     → Returns: function source code
  │  │     │  │  │
  │  │     │  │  ├─ _get_function_imports(function_code, all_imports)
  │  │     │  │  │  └─ Find which imports are used in function
  │  │     │  │  │     (Check if "User" appears in code → yes)
  │  │     │  │  │     → Returns: {"src.user_module.User"}
  │  │     │  │  │
  │  │     │  │  ├─ _resolve_imports_to_files(imports)
  │  │     │  │  │  └─ Convert module path to file path
  │  │     │  │  │     "src.user_module" → "src/user_module.py"
  │  │     │  │  │     → Returns: ["src/user_module.py"]
  │  │     │  │  │
  │  │     │  │  └─ _extract_relevant_code("src/user_module.py")
  │  │     │  │     └─ Parse source file AST
  │  │     │  │        Extract: ClassDef, FunctionDef, Assign nodes
  │  │     │  │        → Returns: {"src/user_module.py": "class User:..."}
  │  │     │  │
  │  │     │  └─ LLMClassifier.classify(failure, test_code, source_code)
  │  │     │     │
  │  │     │     ├─ _build_prompt(failure, test_code, source_code)
  │  │     │     │  └─ Format prompt with all context
  │  │     │     │
  │  │     │     ├─ openai_client.chat.completions.create(
  │  │     │     │     messages=[system_prompt, user_prompt]
  │  │     │     │  )
  │  │     │     │  → Returns: AI response
  │  │     │     │
  │  │     │     └─ Parse JSON response
  │  │     │        → Returns: LLMClassification{
  │  │     │             classification: "test_mistake",
  │  │     │             reason: "Missing import",
  │  │     │             fixed_code: "...",
  │  │     │             confidence: 0.95
  │  │     │          }
  │  │     │
  │  │     ├─ IF classification == "test_mistake":
  │  │     │  │
  │  │     │  ├─ IF llm_result.fixed_code exists:
  │  │     │  │  └─ Use that fix directly
  │  │     │  │
  │  │     │  ├─ ELSE: LLMFixer.fix_test(failure, test_code, source_code)
  │  │     │  │  │
  │  │     │  │  ├─ _build_prompt(failure, test_code, source_code)
  │  │     │  │  │  └─ Format fixing prompt
  │  │     │  │  │
  │  │     │  │  ├─ openai_client.chat.completions.create(...)
  │  │     │  │  │  → Returns: AI response with fixed code
  │  │     │  │  │
  │  │     │  │  └─ _extract_code(response)
  │  │     │  │     └─ Remove markdown code blocks
  │  │     │  │        → Returns: "def test_user_creation():\\n    ..."
  │  │     │  │
  │  │     │  └─ ASTPatcher.patch_test_function(test_file, func_name, fixed_code)
  │  │     │     │
  │  │     │     ├─ Read original test file
  │  │     │     ├─ Parse: tree = ast.parse(content)
  │  │     │     ├─ Find function:
  │  │     │     │  for node in ast.walk(tree):
  │  │     │     │      if node.name == "test_user_creation":
  │  │     │     │          start = node.lineno - 1
  │  │     │     │          end = node.end_lineno
  │  │     │     │
  │  │     │     ├─ _prepare_fixed_code(fixed_code, indent)
  │  │     │     │  └─ Adjust indentation to match file
  │  │     │     │
  │  │     │     ├─ Replace lines[start:end] with fixed_lines
  │  │     │     ├─ Write back to file
  │  │     │     └─ validate_patch(test_file)
  │  │     │        └─ ast.parse(new_content) to check syntax
  │  │     │           → Returns: True if successful
  │  │     │
  │  │     └─ Create FixResult{
  │  │          test_file, test_name,
  │  │          classification: "test_mistake",
  │  │          fix_attempted: True,
  │  │          fix_successful: True
  │  │        }
  │  │
  │  └─ Check: Were any fixes made?
  │     ├─ Yes: Continue to iteration 2
  │     └─ No: Stop
  │
  ├─ ITERATION 2 (repeat for remaining failures)
  ├─ ITERATION 3 (if needed)
  │
  └─ _generate_summary()
     ├─ Count statistics
     ├─ Save to auto_fixer_report.json
     └─ Return summary dict


DATA OBJECTS AT EACH STEP:

1. Pytest Output (JSON):
   {
     "tests": [
       {
         "nodeid": "tests/test_user_example.py::test_user_creation",
         "outcome": "failed",
         "call": {
           "longrepr": "E   NameError: name 'User' is not defined"
         }
       }
     ]
   }

2. TestFailure Object:
   TestFailure(
     test_file="tests/test_user_example.py",
     test_name="test_user_creation",
     exception_type="NameError",
     error_message="name 'User' is not defined",
     traceback="...full trace...",
     line_number=11
   )

3. Test Code (from AST):
   \"\"\"
   def test_user_creation():
       \"\"\"Test user creation...\"\"\"
       user = User("John Doe", "john@example.com")
       assert user.name == "John Doe"
   \"\"\"

4. Source Context (from AST):
   {
     "src/user_module.py": \"\"\"
       class User:
           def __init__(self, name: str, email: str):
               self.name = name
               self.email = email
       \"\"\"
   }

5. LLM Classification:
   LLMClassification(
     classification="test_mistake",
     reason="User class exists in src.user_module but is not imported",
     fixed_code="def test_user_creation():\\n    from src.user_module import User\\n    ...",
     confidence=0.95
   )

6. Fixed Code (from LLM):
   \"\"\"
   def test_user_creation():
       \"\"\"Test user creation - FIXED\"\"\"
       from src.user_module import User

       user = User("John Doe", "john@example.com")
       assert user.name == "John Doe"
   \"\"\"

7. Patched File (written to disk):
   tests/test_user_example.py now contains the fixed version

8. Re-run Results:
   [
     TestFailure(...),  # Different test still failing
     TestFailure(...),  # Another test still failing
   ]
   # This test no longer in the list = SUCCESS!
""")

print_section("SUMMARY")
print("""
The auto-fixer works through this flow:

1. Run pytest → Get failures as structured objects
2. For each failure:
   a. Classify using patterns (fast)
   b. If unclear, classify using LLM (smart)
3. For test mistakes:
   a. Extract source code context using AST
   b. Generate fix using LLM
   c. Apply fix precisely using AST patcher
4. Re-run pytest
5. Repeat until all test mistakes fixed (max 3 iterations)

Key insight: AST (Abstract Syntax Tree) is used for:
- Extracting test function code
- Finding imports in test files
- Extracting source code context
- Precisely patching only the failing function

This ensures fixes are surgical and don't break anything else!
""")


if __name__ == '__main__':
    pass
