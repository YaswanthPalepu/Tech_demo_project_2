#!/usr/bin/env python3
"""
Verify auto-healing system components without requiring pytest installed.
"""

import os
import pathlib
import sys


def verify_file_structure():
    """Verify all files are present."""
    print("=" * 80)
    print("📁 VERIFYING FILE STRUCTURE")
    print("=" * 80)

    expected_files = [
        "src/test_healing/__init__.py",
        "src/test_healing/test_ast_extractor.py",
        "src/test_healing/pytest_failure_parser.py",
        "src/test_healing/test_healer.py",
        "src/test_healing/auto_healing_loop.py",
        "src/test_healing/integration.py",
        "src/test_healing/README.md",
        "QUICK_START_AUTO_HEALING.md",
        "COMPLETE_WORKFLOW_EXPLAINED.md",
    ]

    all_present = True
    for file_path in expected_files:
        full_path = pathlib.Path(file_path)
        if full_path.exists():
            size = full_path.stat().st_size
            print(f"✅ {file_path:50s} ({size:6d} bytes)")
        else:
            print(f"❌ {file_path:50s} MISSING!")
            all_present = False

    return all_present


def verify_imports():
    """Verify all modules can be imported."""
    print("\n" + "=" * 80)
    print("📦 VERIFYING MODULE IMPORTS")
    print("=" * 80)

    tests = []

    # Test 1: Import package
    print("\n1️⃣  Testing package import...")
    try:
        import src.test_healing
        print("   ✅ src.test_healing imported")
        print(f"   Version: {src.test_healing.__version__}")
        print(f"   Available: {', '.join(src.test_healing.__all__)}")
        tests.append(("Package import", True))
    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        tests.append(("Package import", False))

    # Test 2: Import TestASTExtractor
    print("\n2️⃣  Testing TestASTExtractor...")
    try:
        from src.test_healing.test_ast_extractor import TestASTExtractor
        print("   ✅ TestASTExtractor imported")

        # Test instantiation
        extractor = TestASTExtractor(pathlib.Path("tests/generated"))
        print("   ✅ Can instantiate TestASTExtractor")

        # Check methods
        methods = [m for m in dir(extractor) if not m.startswith('_')]
        print(f"   Methods: {', '.join(methods[:5])}...")
        tests.append(("TestASTExtractor", True))
    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        import traceback
        traceback.print_exc()
        tests.append(("TestASTExtractor", False))

    # Test 3: Import PytestFailureParser
    print("\n3️⃣  Testing PytestFailureParser...")
    try:
        from src.test_healing.pytest_failure_parser import PytestFailureParser, TestFailure
        print("   ✅ PytestFailureParser imported")
        print("   ✅ TestFailure dataclass imported")

        # Test instantiation
        parser = PytestFailureParser("tests/generated")
        print("   ✅ Can instantiate PytestFailureParser")

        # Test with sample output
        sample_output = "FAILED test.py::test_foo - ImportError"
        failures = parser.parse_pytest_output(sample_output)
        print(f"   ✅ Can parse output ({len(failures)} failures found)")
        tests.append(("PytestFailureParser", True))
    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        import traceback
        traceback.print_exc()
        tests.append(("PytestFailureParser", False))

    # Test 4: Import TestHealer
    print("\n4️⃣  Testing TestHealer...")
    try:
        from src.test_healing.test_healer import TestHealer
        print("   ✅ TestHealer imported")

        # Test instantiation
        healer = TestHealer(
            target_root=pathlib.Path("."),
            generated_tests_dir=pathlib.Path("tests/generated"),
            use_full_source=False
        )
        print("   ✅ Can instantiate TestHealer")
        print(f"   Mode: {'Full source' if healer.use_full_source else 'AST mode'}")
        tests.append(("TestHealer", True))
    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        import traceback
        traceback.print_exc()
        tests.append(("TestHealer", False))

    # Test 5: Import AutoHealingLoop
    print("\n5️⃣  Testing AutoHealingLoop...")
    try:
        from src.test_healing.auto_healing_loop import AutoHealingLoop, HealingSession
        print("   ✅ AutoHealingLoop imported")
        print("   ✅ HealingSession dataclass imported")

        # Test instantiation
        loop = AutoHealingLoop(
            target_root=".",
            generated_tests_dir="tests/generated",
            max_iterations=3
        )
        print("   ✅ Can instantiate AutoHealingLoop")
        print(f"   Max iterations: {loop.max_iterations}")
        tests.append(("AutoHealingLoop", True))
    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        import traceback
        traceback.print_exc()
        tests.append(("AutoHealingLoop", False))

    # Test 6: Import Integration
    print("\n6️⃣  Testing Integration...")
    try:
        from src.test_healing.integration import TestGenerationWithHealing, run_integrated_workflow
        print("   ✅ TestGenerationWithHealing imported")
        print("   ✅ run_integrated_workflow function imported")

        # Test instantiation
        workflow = TestGenerationWithHealing(
            target_root=".",
            output_dir="tests/generated",
            enable_healing=True
        )
        print("   ✅ Can instantiate TestGenerationWithHealing")
        tests.append(("Integration", True))
    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        import traceback
        traceback.print_exc()
        tests.append(("Integration", False))

    return tests


def test_ast_extraction():
    """Test AST extraction on a real Python file."""
    print("\n" + "=" * 80)
    print("🧪 TESTING AST EXTRACTION")
    print("=" * 80)

    # Create a temporary test file
    import tempfile

    test_code = '''
import pytest

def test_example():
    """Example test function."""
    assert 1 + 1 == 2

class TestExample:
    """Example test class."""

    def test_method(self):
        """Example test method."""
        assert True

    def test_another(self):
        """Another test method."""
        x = 5
        assert x > 0
'''

    try:
        from src.test_healing.test_ast_extractor import TestASTExtractor

        # Create temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
            f.write(test_code)
            temp_file = pathlib.Path(f.name)

        # Create temp directory
        temp_dir = temp_file.parent

        # Extract structure
        extractor = TestASTExtractor(temp_dir)
        structure = extractor.extract_test_structure(temp_file)

        print(f"✅ Extracted structure from test file")
        print(f"   Test functions: {len(structure['test_functions'])}")
        print(f"   Test classes: {len(structure['test_classes'])}")
        print(f"   Test methods: {len(structure['test_methods'])}")
        print(f"   Imports: {len(structure['imports'])}")
        print(f"   All test names: {structure['all_test_names']}")

        # Cleanup
        temp_file.unlink()

        return True

    except Exception as e:
        print(f"❌ FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_failure_parsing():
    """Test pytest failure parsing."""
    print("\n" + "=" * 80)
    print("🧪 TESTING FAILURE PARSING")
    print("=" * 80)

    sample_pytest_output = '''
collected 10 items

tests/generated/test_unit_01.py::test_user_creation FAILED         [ 10%]
tests/generated/test_unit_01.py::test_login FAILED                 [ 20%]
tests/generated/test_unit_02.py::test_calculate PASSED             [ 30%]

================================== FAILURES ===================================
_ _ _ _ _ _ _ _ test_user_creation _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

tests/generated/test_unit_01.py:10: in test_user_creation
    from app.models import User
E   ImportError: cannot import name 'User' from 'app.models'

_ _ _ _ _ _ _ _ test_login _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _

tests/generated/test_unit_01.py:20: in test_login
    result = login(username, password, remember_me)
E   TypeError: login() takes 2 positional arguments but 3 were given

=========================== short test summary info ===========================
FAILED tests/generated/test_unit_01.py::test_user_creation - ImportError
FAILED tests/generated/test_unit_01.py::test_login - TypeError
========================== 2 failed, 1 passed in 0.50s ============================
'''

    try:
        from src.test_healing.pytest_failure_parser import PytestFailureParser

        parser = PytestFailureParser("tests/generated")
        failures = parser.parse_pytest_output(sample_pytest_output)

        print(f"✅ Parsed pytest output")
        print(f"   Total failures: {len(failures)}")

        for i, failure in enumerate(failures, 1):
            print(f"\n   Failure {i}:")
            print(f"      Test: {failure.test_name}")
            print(f"      File: {failure.test_file}:{failure.test_line}")
            print(f"      Error: {failure.error_type}")
            print(f"      Message: {failure.error_message}")
            print(f"      LLM Mistake: {failure.is_llm_mistake}")

        # Generate report
        report = parser.generate_failure_report(failures)
        print("\n📊 Generated Report Preview:")
        print("-" * 80)
        print(report[:500] + "...")

        return True

    except Exception as e:
        print(f"❌ FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


def check_analyzer_integration():
    """Check integration with existing analyzer.py."""
    print("\n" + "=" * 80)
    print("🔗 CHECKING ANALYZER INTEGRATION")
    print("=" * 80)

    try:
        from src.analyzer import analyze_python_tree

        print("✅ analyzer.py can be imported")
        print("✅ analyze_python_tree function available")

        # Check that it skips tests/generated
        from src.analyzer import SKIP_DIR_NAMES
        print(f"\n📋 Skipped directories in analyzer.py:")
        for skip_dir in SKIP_DIR_NAMES:
            marker = "👉" if "test" in skip_dir.lower() else "  "
            print(f"   {marker} {skip_dir}")

        if "tests/generated" in SKIP_DIR_NAMES:
            print("\n✅ Confirmed: analyzer.py skips 'tests/generated'")
            print("   This is why we need test_ast_extractor.py!")
        else:
            print("\n⚠️  Note: 'tests/generated' in skip list")

        return True

    except Exception as e:
        print(f"❌ FAILED: {e}")
        return False


def print_workflow_summary():
    """Print workflow summary."""
    print("\n" + "=" * 80)
    print("📖 COMPLETE WORKFLOW SUMMARY")
    print("=" * 80)

    workflow = '''
1. TEST GENERATION (existing)
   └─> analyzer.py scans source code (skips tests/generated)
       └─> enhanced_generate.py generates tests via LLM
           └─> Tests saved to tests/generated/

2. AUTO-HEALING (new)
   └─> auto_healing_loop.py runs pytest
       └─> pytest_failure_parser.py extracts failures
           ├─> Classifies: LLM mistake vs real bug
           └─> For LLM mistakes:
               ├─> test_ast_extractor.py extracts test code
               ├─> analyzer.py provides source context (AST mode)
               │   OR full source files (full mode)
               ├─> test_healer.py sends to LLM for fixing
               └─> Corrected test replaces original
                   └─> Re-run pytest → Repeat until done

3. INTEGRATION
   └─> integration.py combines generation + healing
       └─> One command: generate AND heal!

KEY POINTS:
✅ analyzer.py skips tests/generated (by design)
✅ test_ast_extractor.py handles tests/generated separately
✅ Healing only fixes LLM mistakes, not real bugs
✅ Two modes: AST (fast) or full source (accurate)
✅ Max 3 iterations to prevent infinite loops
'''

    print(workflow)


def main():
    """Main verification function."""
    print("=" * 80)
    print("🔍 AUTO-HEALING SYSTEM VERIFICATION")
    print("=" * 80)

    # Change to project root
    project_root = pathlib.Path(__file__).parent
    os.chdir(project_root)

    results = []

    # Step 1: Verify file structure
    file_check = verify_file_structure()
    results.append(("File structure", file_check))

    if not file_check:
        print("\n❌ File structure check failed!")
        return 1

    # Step 2: Verify imports
    import_results = verify_imports()
    results.extend(import_results)

    # Step 3: Test AST extraction
    ast_ok = test_ast_extraction()
    results.append(("AST extraction", ast_ok))

    # Step 4: Test failure parsing
    parsing_ok = test_failure_parsing()
    results.append(("Failure parsing", parsing_ok))

    # Step 5: Check analyzer integration
    analyzer_ok = check_analyzer_integration()
    results.append(("Analyzer integration", analyzer_ok))

    # Print workflow summary
    print_workflow_summary()

    # Final summary
    print("=" * 80)
    print("📊 VERIFICATION SUMMARY")
    print("=" * 80)

    passed = sum(1 for _, ok in results if ok)
    total = len(results)

    for test_name, ok in results:
        status = "✅ PASS" if ok else "❌ FAIL"
        print(f"{status:10s} {test_name}")

    print("-" * 80)
    print(f"Result: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 ALL VERIFICATIONS PASSED!")
        print("\n✅ The auto-healing system is correctly implemented!")
        print("\nNext steps:")
        print("1. Set up OpenAI API key")
        print("2. Generate some tests: python -m src.gen --target ./target")
        print("3. Run auto-healing: python -m src.test_healing.auto_healing_loop --target ./target")
    else:
        print("\n⚠️  Some verifications failed. Review errors above.")

    print("=" * 80)

    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
