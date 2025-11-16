#!/usr/bin/env python3
"""
Auto-Fixer Demo with Detailed Code Flow Tracing

This script demonstrates:
1. How the auto-fixer works step-by-step
2. How it fetches source code and test code
3. The exact function call flow
4. The output at each step
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from auto_fixer.failure_parser import FailureParser, TestFailure
from auto_fixer.rule_classifier import RuleBasedClassifier
from auto_fixer.llm_classifier import LLMClassifier
from auto_fixer.ast_context_extractor import ASTContextExtractor
from auto_fixer.llm_fixer import LLMFixer
from auto_fixer.ast_patcher import ASTPatcher
import ast


def print_section(title):
    """Print a section header."""
    print("\n" + "=" * 80)
    print(f"  {title}")
    print("=" * 80)


def print_step(step_num, description):
    """Print a step header."""
    print(f"\n>>> STEP {step_num}: {description}")
    print("-" * 80)


def demonstrate_code_flow():
    """Demonstrate the complete auto-fixer code flow."""

    print_section("AUTO-FIXER CODE FLOW DEMONSTRATION")

    # ==========================================================================
    # STEP 1: Run pytest and parse failures
    # ==========================================================================
    print_step(1, "Run pytest and parse failures")

    parser = FailureParser(test_directory="tests")
    print(f"✓ Created FailureParser(test_directory='tests')")

    print(f"\n📝 Calling: parser.run_pytest_json()")
    print(f"   → This runs: pytest tests --tb=long -v")
    print(f"   → Captures test results")

    # For demo, let's parse just the test file directly to show structure
    print(f"\n📝 Calling: parser.run_and_parse()")
    failures = parser.run_and_parse(["-k", "test_user_example.py"])

    print(f"\n✓ Found {len(failures)} failure(s)")

    if not failures:
        print("\n⚠️  No failures found. The tests may have already passed!")
        print("   Check tests/test_user_example.py for intentional errors.")
        return

    # Show first failure in detail
    failure = failures[0]
    print(f"\n📊 First failure details (TestFailure object):")
    print(f"   test_file      : {failure.test_file}")
    print(f"   test_name      : {failure.test_name}")
    print(f"   exception_type : {failure.exception_type}")
    print(f"   error_message  : {failure.error_message}")
    print(f"   line_number    : {failure.line_number}")
    print(f"   traceback      : {failure.traceback[:200]}...")

    # ==========================================================================
    # STEP 2: Read the test code
    # ==========================================================================
    print_step(2, "Read the failing test code")

    test_file_path = failure.test_file
    print(f"📝 Reading test file: {test_file_path}")

    try:
        with open(test_file_path, 'r') as f:
            test_file_content = f.read()

        print(f"✓ Read {len(test_file_content)} characters from test file")

        # Parse AST to extract the specific test function
        tree = ast.parse(test_file_content)
        test_function_code = None

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == failure.test_name:
                test_function_code = ast.unparse(node)
                break

        print(f"\n📝 Extracted test function '{failure.test_name}':")
        print("─" * 80)
        print(test_function_code)
        print("─" * 80)

    except Exception as e:
        print(f"❌ Error reading test: {e}")
        return

    # ==========================================================================
    # STEP 3A: Rule-based classification
    # ==========================================================================
    print_step("3A", "Rule-based classification")

    rule_classifier = RuleBasedClassifier()
    print(f"✓ Created RuleBasedClassifier()")

    print(f"\n📝 Calling: rule_classifier.classify(failure)")
    print(f"   → Checks error patterns against known test mistakes")

    rule_result = rule_classifier.classify(failure)
    reason = rule_classifier.get_classification_reason(failure)

    print(f"\n✓ Rule classifier result: '{rule_result}'")
    print(f"  Reason: {reason}")

    # ==========================================================================
    # STEP 4: Extract AST context (source code being tested)
    # ==========================================================================
    print_step(4, "Extract AST context from source code")

    extractor = ASTContextExtractor(project_root=".")
    print(f"✓ Created ASTContextExtractor(project_root='.')")

    print(f"\n📝 Calling: extractor.extract_context()")
    print(f"   test_file: {test_file_path}")
    print(f"   test_function: {failure.test_name}")
    print(f"\n   This will:")
    print(f"   1. Parse the test file AST")
    print(f"   2. Extract all imports")
    print(f"   3. Find imports used in the failing test")
    print(f"   4. Resolve import paths to source files")
    print(f"   5. Extract relevant code from source files")

    context = extractor.extract_context(test_file_path, failure.test_name)

    print(f"\n✓ Extracted context from {len(context)} source file(s):")
    for source_file, code in context.items():
        print(f"\n   📄 {source_file} ({len(code)} characters)")
        print(f"      Preview: {code[:150]}...")

    # Get formatted context
    context_string = extractor.get_full_context_string(test_file_path, failure.test_name)

    print(f"\n📝 Full context string (for LLM):")
    print("─" * 80)
    print(context_string[:500] + "..." if len(context_string) > 500 else context_string)
    print("─" * 80)

    # ==========================================================================
    # STEP 3B: LLM classification (if rule classifier returned "unknown")
    # ==========================================================================
    if rule_result == "unknown":
        print_step("3B", "LLM-based classification")

        llm_classifier = LLMClassifier()
        print(f"✓ Created LLMClassifier()")

        print(f"\n📝 Calling: llm_classifier.classify()")
        print(f"   failure: TestFailure object")
        print(f"   test_code: {len(test_function_code)} chars")
        print(f"   source_code: {len(context_string)} chars")
        print(f"\n   This will:")
        print(f"   1. Build a prompt with failure details + code")
        print(f"   2. Send to Azure OpenAI")
        print(f"   3. Parse JSON response")
        print(f"   4. Return classification + suggested fix")

        # Note: We won't actually call LLM in demo to avoid API costs
        print(f"\n⚠️  Skipping actual LLM call in demo")
        print(f"   In real execution, this would return:")
        print("   {")
        print('     "classification": "test_mistake",')
        print('     "reason": "Missing import for User class",')
        print('     "fixed_code": "<corrected test function>",')
        print('     "confidence": 0.95')
        print("   }")

    # ==========================================================================
    # STEP 5: Generate fix (if test_mistake)
    # ==========================================================================
    print_step(5, "Generate fix for test mistake")

    fixer = LLMFixer()
    print(f"✓ Created LLMFixer()")

    print(f"\n📝 Would call: fixer.fix_test()")
    print(f"   failure: TestFailure object")
    print(f"   test_code: {len(test_function_code)} chars")
    print(f"   source_code: {len(context_string)} chars")
    print(f"\n   This would:")
    print(f"   1. Build a fixing prompt with all context")
    print(f"   2. Send to Azure OpenAI")
    print(f"   3. Extract fixed code from response")
    print(f"   4. Return corrected test function")

    # Simulate a fix for demo
    simulated_fix = f'''def {failure.test_name}():
    """Test user creation - FIXED: Added import."""
    from src.user_module import User

    user = User("John Doe", "john@example.com")
    assert user.name == "John Doe"
    assert user.email == "john@example.com"'''

    print(f"\n✓ Example fixed code:")
    print("─" * 80)
    print(simulated_fix)
    print("─" * 80)

    # ==========================================================================
    # STEP 6: Apply fix using AST patcher
    # ==========================================================================
    print_step(6, "Apply fix using AST patcher")

    patcher = ASTPatcher()
    print(f"✓ Created ASTPatcher()")

    print(f"\n📝 Would call: patcher.patch_test_function()")
    print(f"   test_file_path: {test_file_path}")
    print(f"   test_function_name: {failure.test_name}")
    print(f"   fixed_function_code: <corrected code>")
    print(f"\n   This would:")
    print(f"   1. Read the original test file")
    print(f"   2. Parse it into AST")
    print(f"   3. Find the specific function node")
    print(f"   4. Get its line range (start_line to end_line)")
    print(f"   5. Replace only those lines with fixed code")
    print(f"   6. Preserve indentation and formatting")
    print(f"   7. Write back to file")
    print(f"   8. Validate the result")

    print(f"\n⚠️  Not actually patching file in demo mode")

    # ==========================================================================
    # STEP 7: Re-run pytest
    # ==========================================================================
    print_step(7, "Re-run pytest to verify fix")

    print(f"📝 Would call: parser.run_and_parse() again")
    print(f"   → Re-runs pytest on the same tests")
    print(f"   → Checks if the fix worked")
    print(f"   → Returns new list of failures")
    print(f"\n   If fix worked: list would be shorter")
    print(f"   If fix failed: same test would still fail")

    # ==========================================================================
    # STEP 8: Iteration control
    # ==========================================================================
    print_step(8, "Iteration control (max 3 iterations)")

    print(f"📝 Orchestrator checks:")
    print(f"   1. Are there still failures?")
    print(f"   2. Were any test_mistakes fixed this iteration?")
    print(f"   3. Have we reached max_iterations (3)?")
    print(f"\n   Continue if: failures exist AND fixes were made AND iterations < 3")
    print(f"   Stop if: no failures OR no fixes made OR iterations >= 3")

    # ==========================================================================
    # SUMMARY
    # ==========================================================================
    print_section("FUNCTION CALL FLOW SUMMARY")

    print("""
MAIN WORKFLOW:
└── AutoTestFixerOrchestrator.run()
    │
    ├── [ITERATION 1]
    │   │
    │   ├── 1. FailureParser.run_and_parse()
    │   │   ├── run_pytest_json()
    │   │   │   ├── subprocess.run(['pytest', 'tests', '--tb=long', '-v'])
    │   │   │   └── json.load('pytest_report.json') or _parse_text_output()
    │   │   └── parse_failures(json_output)
    │   │       └── Returns: List[TestFailure]
    │   │
    │   ├── [FOR EACH FAILURE]
    │   │   │
    │   │   ├── 2. RuleBasedClassifier.classify(failure)
    │   │   │   └── Returns: "test_mistake" | "unknown"
    │   │   │
    │   │   ├── 3. IF unknown:
    │   │   │   │
    │   │   │   ├── ASTContextExtractor.extract_context()
    │   │   │   │   ├── _extract_imports(test_file_ast)
    │   │   │   │   ├── _extract_test_function(ast, func_name)
    │   │   │   │   ├── _get_function_imports(func_code, all_imports)
    │   │   │   │   ├── _resolve_imports_to_files(imports)
    │   │   │   │   └── _extract_relevant_code(source_file)
    │   │   │   │       └── Returns: Dict[file_path, code]
    │   │   │   │
    │   │   │   └── LLMClassifier.classify(failure, test_code, source_code)
    │   │   │       ├── _build_prompt(failure, test_code, source_code)
    │   │   │       ├── openai_client.chat.completions.create()
    │   │   │       └── Returns: LLMClassification
    │   │   │
    │   │   ├── 4. IF test_mistake:
    │   │   │   │
    │   │   │   ├── LLMFixer.fix_test()
    │   │   │   │   ├── _build_prompt(failure, test_code, source_code)
    │   │   │   │   ├── openai_client.chat.completions.create()
    │   │   │   │   ├── _extract_code(llm_response)
    │   │   │   │   └── Returns: fixed_code_string
    │   │   │   │
    │   │   │   └── ASTPatcher.patch_test_function()
    │   │   │       ├── Read test file
    │   │   │       ├── ast.parse(test_file_content)
    │   │   │       ├── Find function node by name
    │   │   │       ├── Get line range (node.lineno to node.end_lineno)
    │   │   │       ├── _prepare_fixed_code(fixed_code, indent)
    │   │   │       ├── Replace lines in file
    │   │   │       ├── Write back to file
    │   │   │       └── validate_patch(test_file)
    │   │   │
    │   │   └── 5. Store FixResult
    │   │
    │   └── Check if any fixes were made
    │
    ├── [ITERATION 2 - if needed]
    │   └── (repeat above)
    │
    ├── [ITERATION 3 - if needed]
    │   └── (repeat above)
    │
    └── _generate_summary()
        ├── Count: test_mistakes, code_bugs, successful_fixes
        ├── Save auto_fixer_report.json
        └── Returns: summary_dict


DATA FLOW:

pytest output (text/JSON)
    ↓
TestFailure objects
    ├── test_file: "tests/test_user_example.py"
    ├── test_name: "test_user_creation"
    ├── exception_type: "NameError"
    ├── error_message: "name 'User' is not defined"
    ├── traceback: "..."
    └── line_number: 12
    ↓
Rule Classifier → "test_mistake" or "unknown"
    ↓
AST Context Extractor → Dict[source_file, code]
    {
        "src/user_module.py": "class User:\\n    def __init__..."
    }
    ↓
LLM Classifier → LLMClassification
    {
        "classification": "test_mistake",
        "reason": "Missing import for User class",
        "fixed_code": "def test_user_creation():\\n    from src.user_module import User\\n...",
        "confidence": 0.95
    }
    ↓
LLM Fixer (if needed) → fixed_code_string
    ↓
AST Patcher → Modified test file
    ↓
Re-run pytest → New List[TestFailure] (hopefully shorter!)
""")

    print_section("KEY FUNCTIONS AND THEIR RETURNS")

    print("""
1. FailureParser.run_and_parse(extra_args) → List[TestFailure]
   - Runs pytest
   - Parses output (JSON or text)
   - Returns structured failure objects

2. RuleBasedClassifier.classify(failure) → "test_mistake" | "unknown"
   - Pattern matching on error messages
   - Fast, no LLM calls
   - Conservative: returns "unknown" when unsure

3. ASTContextExtractor.extract_context(test_file, func_name) → Dict[str, str]
   - Parses test file imports
   - Resolves to source files
   - Extracts relevant code
   - Returns: {source_file_path: relevant_code}

4. LLMClassifier.classify(failure, test_code, source_code) → LLMClassification
   - Builds prompt with all context
   - Calls Azure OpenAI
   - Returns: classification, reason, fixed_code, confidence

5. LLMFixer.fix_test(failure, test_code, source_code) → Optional[str]
   - Generates fixed version of test function
   - Returns corrected code or None

6. ASTPatcher.patch_test_function(file, func_name, fixed_code) → bool
   - Precisely replaces function in file
   - Preserves formatting
   - Returns: True if successful

7. AutoTestFixerOrchestrator.run(extra_args) → Dict[str, Any]
   - Coordinates entire workflow
   - Implements iteration loop
   - Returns: summary with statistics
""")


if __name__ == '__main__':
    demonstrate_code_flow()
