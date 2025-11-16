"""
COMPLETE AUTO-HEALING WORKFLOW - STEP BY STEP
==============================================

SCENARIO: You have a Python project and want to generate tests with auto-healing

┌────────────────────────────────────────────────────────────────────┐
│                    PHASE 1: TEST GENERATION                         │
└────────────────────────────────────────────────────────────────────┘

Step 1: Analyze Your Codebase
------------------------------
Command: python -m src.gen --target ./target

What happens:
├─ analyzer.py scans your source code
├─ Skips tests/generated directory (line 15: "tests/generated" in SKIP_DIR_NAMES)
├─ Extracts: functions, classes, methods, routes, imports
└─ Creates AST-based analysis of your codebase

Output: analysis = {
    "functions": [...],
    "classes": [...],
    "methods": [...],
    "imports": [...],
    ...
}

Step 2: Generate Tests with LLM
--------------------------------
File: src/gen/enhanced_generate.py

What happens:
├─ Takes the analysis from Step 1
├─ For each target (function/class/method):
│   ├─ Builds a prompt with context
│   ├─ Sends to LLM (OpenAI)
│   └─ LLM generates test code
├─ Saves tests to tests/generated/test_*.py
└─ Creates conftest.py with fixtures

Output: tests/generated/
    ├── test_unit_20241116_120000_01.py
    ├── test_unit_20241116_120000_02.py
    ├── test_integ_20241116_120000_01.py
    └── conftest.py

⚠️  PROBLEM: LLM might make mistakes!
    - Wrong imports
    - Syntax errors
    - Wrong function signatures
    - Incorrect mocking

┌────────────────────────────────────────────────────────────────────┐
│                    PHASE 2: AUTO-HEALING                            │
└────────────────────────────────────────────────────────────────────┘

Step 3: Run Initial pytest
---------------------------
File: src/test_healing/auto_healing_loop.py::_run_pytest()

Command executed internally:
  pytest tests/generated -v --tb=long --no-header --color=no

What happens:
├─ pytest runs all generated tests
├─ Some tests PASS ✓
└─ Some tests FAIL ✗ (due to LLM mistakes)

Output:
  FAILED tests/generated/test_unit_01.py::test_user_creation - ImportError
  FAILED tests/generated/test_unit_01.py::test_login - TypeError
  PASSED tests/generated/test_unit_02.py::test_calculate
  ...
  10 failed, 5 passed

Step 4: Parse Failures
----------------------
File: src/test_healing/pytest_failure_parser.py

What happens:
├─ PytestFailureParser reads pytest output
├─ For each failure, extracts:
│   ├─ Test name (e.g., "test_user_creation")
│   ├─ File path (e.g., "tests/generated/test_unit_01.py")
│   ├─ Line number (e.g., 45)
│   ├─ Error type (e.g., "ImportError")
│   ├─ Error message (e.g., "cannot import name 'User'")
│   └─ Full traceback
└─ Creates TestFailure objects

Example:
  TestFailure(
      test_name="test_user_creation",
      test_file="tests/generated/test_unit_01.py",
      test_line=45,
      error_type="ImportError",
      error_message="cannot import name 'User' from 'app.models'",
      traceback=[
          "  File 'test_unit_01.py', line 45, in test_user_creation",
          "    from app.models import User",
          "ImportError: cannot import name 'User' from 'app.models'"
      ],
      is_import_error=True
  )

Step 5: Classify Failures
--------------------------
File: src/test_healing/pytest_failure_parser.py::_is_llm_mistake()

What happens:
├─ For each failure, determines if it's an LLM mistake:
│   ├─ Syntax errors in tests → LLM mistake ✓
│   ├─ Import errors in test file → LLM mistake ✓
│   ├─ Wrong signatures (TypeError) → LLM mistake ✓
│   ├─ Wrong mocking → LLM mistake ✓
│   └─ Assertion failures in business logic → Real bug ✗
└─ Sets failure.is_llm_mistake flag

Result:
  10 failures total:
  ├─ 7 LLM mistakes (healable) ✓
  └─ 3 Real bugs (not healable) ✗

Step 6: Extract Failing Test Code
----------------------------------
File: src/test_healing/test_ast_extractor.py

WHY THIS EXISTS:
  analyzer.py SKIPS tests/generated directory!
  We need a separate AST parser just for tests.

What happens:
├─ TestASTExtractor parses the test file
├─ Builds AST tree of the test file
├─ Finds the failing test function/class
└─ Extracts its source code

Example:
  test_code = '''
  def test_user_creation():
      """Test user creation."""
      from app.models import User  # ← WRONG IMPORT!
      user = User(name="Test")
      assert user.name == "Test"
  '''

Step 7: Get Original Source Code Context
-----------------------------------------
File: src/test_healing/test_healer.py::_get_source_context()

TWO MODES:

MODE A: AST Mode (Default - Recommended)
  What happens:
  ├─ Looks at test imports to understand what's being tested
  ├─ Calls analyzer.py to analyze source code
  ├─ Extracts ONLY relevant functions/classes from analysis
  └─ Builds focused context

  Example context:
    '''
    # Function: create_user from app/models.py
    # Lines 10-25
    # Class: User from app/models.py
    # Lines 5-30
    # Methods: __init__, save, validate
    '''

  Pros: Fast, efficient, low token usage
  When: Large codebases, simple dependencies

MODE B: Full Source Mode
  What happens:
  ├─ Looks at test imports
  ├─ Finds the actual source files
  └─ Includes COMPLETE file contents

  Example context:
    '''
    # File: app/models.py
    <entire file content>
    '''

  Pros: More context, better accuracy
  When: Complex dependencies, AST mode fails

Step 8: Build Healing Prompt
-----------------------------
File: src/test_healing/test_healer.py::_build_healing_prompt()

What happens:
├─ Combines all information into a rich prompt:
│   ├─ System prompt (you're an expert test engineer)
│   ├─ Error details (type, message, traceback)
│   ├─ Failing test code
│   └─ Source code context
└─ Sends to LLM

Prompt structure:
  '''
  You are an expert Python test engineer.

  TEST FAILURE:
  Test: test_user_creation
  Error: ImportError: cannot import name 'User'
  Traceback: [...]

  FAILING TEST CODE:
  def test_user_creation():
      from app.models import User  # Wrong!
      ...

  RELEVANT SOURCE CODE:
  # Class: User from app/models.py
  class User:
      def __init__(self, name):
          self.name = name

  INSTRUCTIONS:
  Fix the test. The error is in the TEST, not the source code.
  '''

Step 9: LLM Generates Corrected Test
-------------------------------------
File: src/test_healing/test_healer.py::heal_test()

What happens:
├─ LLM analyzes the failure
├─ Understands the correct import should be "from app.models import User"
└─ Generates corrected test code

LLM response:
  '''python
  def test_user_creation():
      """Test user creation."""
      from target.app.models import User  # ← FIXED!
      user = User(name="Test")
      assert user.name == "Test"
  '''

Step 10: Validate Corrected Code
---------------------------------
File: src/test_healing/test_healer.py::_validate_corrected_code()

What happens:
├─ Extracts Python code from LLM response
├─ Parses with ast.parse() to check syntax
├─ Verifies test name is present
└─ Returns True if valid

If invalid:
├─ Adds feedback to prompt
└─ Retries (max 3 attempts per test)

Step 11: Replace Failing Test
------------------------------
File: src/test_healing/auto_healing_loop.py::_replace_test()

What happens:
├─ Reads the test file
├─ Uses line numbers from AST to find exact test location
├─ Replaces old test with corrected version
└─ Writes file back

Before:
  ```python
  def test_user_creation():
      from app.models import User  # Wrong
      ...
  ```

After:
  ```python
  def test_user_creation():
      from target.app.models import User  # Fixed
      ...
  ```

Step 12: Re-run pytest
-----------------------
File: src/test_healing/auto_healing_loop.py

What happens:
├─ Runs pytest again on tests/generated
├─ Checks if fixed tests now pass
└─ Parses new failures

Result:
  PASSED tests/generated/test_unit_01.py::test_user_creation ✓
  FAILED tests/generated/test_unit_01.py::test_login - TypeError
  ...
  3 failed, 12 passed

Step 13: Iteration Loop
------------------------
File: src/test_healing/auto_healing_loop.py::run_healing_loop()

What happens:
├─ If tests still failing AND are LLM mistakes:
│   ├─ Repeat Steps 6-12 for remaining failures
│   └─ Continue until:
│       ├─ All LLM mistakes fixed ✓
│       ├─ OR max iterations reached (default: 3)
│       └─ OR no healable failures remain
└─ If only real bugs remain → Stop (success!)

Iteration tracking:
  Iteration 1: 7 failures → 5 healed → 2 remaining
  Iteration 2: 2 failures → 2 healed → 0 remaining
  SUCCESS! ✓

Step 14: Generate Session Report
---------------------------------
File: src/test_healing/auto_healing_loop.py::_save_session_report()

What happens:
├─ Collects all metrics
├─ Saves to tests/generated/healing_session_report.json
└─ Prints summary

Report contents:
  {
    "initial_failures": 10,
    "final_failures": 3,
    "tests_healed": 7,
    "tests_failed_to_heal": 0,
    "success": true,
    "iterations": [...]
  }

┌────────────────────────────────────────────────────────────────────┐
│                    PHASE 3: FINAL RESULTS                           │
└────────────────────────────────────────────────────────────────────┘

Step 15: Review Results
------------------------

HEALED (LLM Mistakes Fixed):
├─ ImportError: wrong imports → FIXED ✓
├─ TypeError: wrong signatures → FIXED ✓
├─ SyntaxError: invalid syntax → FIXED ✓
├─ AttributeError: wrong mocking → FIXED ✓
└─ NameError: undefined variables → FIXED ✓

NOT HEALED (Real Bugs - Need Manual Review):
├─ AssertionError: calculate(2, 2) == 5 → Real bug in code!
├─ AssertionError: user.is_active == True → Business logic issue
└─ ConnectionError: Database connection failed → Integration issue

FINAL STATE:
├─ 15 tests passing ✓
├─ 3 tests failing (real bugs - need manual fix) ✗
└─ 87% improvement!

┌────────────────────────────────────────────────────────────────────┐
│                    KEY ARCHITECTURAL POINTS                         │
└────────────────────────────────────────────────────────────────────┘

1. WHY SEPARATE test_ast_extractor.py?
   ├─ analyzer.py skips "tests/generated" directory
   ├─ Need to parse generated tests separately
   └─ Same AST technique, different target

2. HOW DOES IT GET ORIGINAL SOURCE CODE?
   ├─ Option A (AST mode): Reuses analyzer.py analysis
   ├─ Option B (Full mode): Reads source files directly
   └─ Both modes work with existing codebase

3. WHAT GETS HEALED?
   ├─ ONLY LLM mistakes in TEST code
   ├─ NOT bugs in source code
   └─ Classification is automatic and smart

4. HOW MANY ITERATIONS?
   ├─ Default: 3 iterations
   ├─ Most issues fixed in 1-2 iterations
   └─ Prevents infinite loops

5. WHAT IF HEALING FAILS?
   ├─ Test remains unchanged
   ├─ Marked as "failed to heal"
   └─ Reported for manual review

┌────────────────────────────────────────────────────────────────────┐
│                    USAGE PATTERNS                                   │
└────────────────────────────────────────────────────────────────────┘

PATTERN 1: Two-Step (Recommended for debugging)
  Step 1: python -m src.gen --target ./target
  Step 2: python -m src.test_healing.auto_healing_loop --target ./target

PATTERN 2: One-Step (Automated)
  python -m src.test_healing.integration --target ./target

PATTERN 3: Programmatic
  from src.test_healing import AutoHealingLoop
  loop = AutoHealingLoop(...)
  session = loop.run_healing_loop()

┌────────────────────────────────────────────────────────────────────┐
│                    DATA FLOW SUMMARY                                │
└────────────────────────────────────────────────────────────────────┘

SOURCE CODE (target/)
    │
    ├─→ analyzer.py (skip tests/generated)
    │       │
    │       └─→ analysis.json
    │               │
    │               └─→ enhanced_generate.py
    │                       │
    │                       └─→ GENERATED TESTS (tests/generated/)
    │                               │
    │                               ├─→ pytest (run tests)
    │                               │       │
    │                               │       └─→ FAILURES
    │                               │               │
    │                               │               └─→ pytest_failure_parser.py
    │                               │                       │
    │                               │                       └─→ TestFailure objects
    │                               │                               │
    │                               └─→ test_ast_extractor.py ←────┤
    │                                       │                       │
    │                                       └─→ test_code ←────────┤
    │                                                               │
    └─→ analyzer.py (for context) ─────────────────────────────────┤
            │                                                       │
            └─→ source_context ────────────────────────────────────┤
                                                                    │
                    test_healer.py ←───────────────────────────────┘
                            │
                            └─→ LLM (OpenAI)
                                    │
                                    └─→ corrected_test_code
                                            │
                                            └─→ auto_healing_loop.py
                                                    │
                                                    └─→ Replace in file
                                                            │
                                                            └─→ Re-run pytest
                                                                    │
                                                                    └─→ REPEAT or SUCCESS

┌────────────────────────────────────────────────────────────────────┐
│                    SUCCESS CRITERIA                                 │
└────────────────────────────────────────────────────────────────────┘

SUCCESS = (All LLM mistakes fixed) OR (Only real bugs remain)

session.success == True if:
├─ No failures remain, OR
├─ Only non-healable failures remain (real bugs)
└─ At least some tests were healed

session.success == False if:
├─ Healable failures remain after max iterations
└─ No tests could be healed
"""
