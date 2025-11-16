#!/usr/bin/env python3
"""
Debug script to test the auto-healing system end-to-end.

This creates a sample project with intentional LLM mistakes, then runs
the auto-healing loop to verify it works correctly.
"""

import os
import pathlib
import shutil
import sys
import tempfile
from typing import Dict, Any


def create_sample_project() -> pathlib.Path:
    """Create a sample project for testing."""
    print("📁 Creating sample project...")

    # Create temp directory
    temp_dir = pathlib.Path(tempfile.mkdtemp(prefix="auto_healing_test_"))

    # Create target directory with sample code
    target_dir = temp_dir / "target"
    target_dir.mkdir()

    # Create app directory
    app_dir = target_dir / "app"
    app_dir.mkdir()

    # Create __init__.py
    (app_dir / "__init__.py").write_text("")

    # Create models.py with a User class
    (app_dir / "models.py").write_text("""
class User:
    '''User model for the application.'''

    def __init__(self, username, email):
        self.username = username
        self.email = email
        self.is_active = True

    def activate(self):
        '''Activate the user.'''
        self.is_active = True
        return True

    def deactivate(self):
        '''Deactivate the user.'''
        self.is_active = False
        return True

    def get_display_name(self):
        '''Get display name.'''
        return f"{self.username} ({self.email})"


def calculate(a, b):
    '''Calculate sum of two numbers.'''
    return a + b
""")

    # Create utils.py
    (app_dir / "utils.py").write_text("""
def format_email(email):
    '''Format email to lowercase.'''
    return email.lower().strip()


def validate_username(username):
    '''Validate username (3-20 chars, alphanumeric).'''
    if not username:
        return False
    if len(username) < 3 or len(username) > 20:
        return False
    return username.isalnum()
""")

    print(f"✅ Sample project created at: {temp_dir}")
    print(f"   Target code: {target_dir}")
    print(f"   Files: app/models.py, app/utils.py")

    return temp_dir


def create_broken_tests(temp_dir: pathlib.Path):
    """Create test files with intentional LLM mistakes."""
    print("\n🔧 Creating broken tests (simulating LLM mistakes)...")

    tests_dir = temp_dir / "tests" / "generated"
    tests_dir.mkdir(parents=True)

    # Test file 1: Import errors and syntax errors
    test_file_1 = tests_dir / "test_broken_01.py"
    test_file_1.write_text("""
'''Test file with LLM mistakes - Import errors and syntax errors.'''
import pytest
from app.models import User, calculate  # WRONG: calculate is in models, not imported from utils


def test_user_creation():
    '''Test user creation.'''
    # MISTAKE 1: Wrong import (calculate is in models.py)
    user = User("testuser", "test@example.com")
    assert user.username == "testuser"
    assert user.email == "test@example.com"


def test_user_activation():
    '''Test user activation.'''
    user = User("testuser", "test@example.com")
    result = user.activate()
    assert result == True
    assert user.is_active == True


def test_calculate_function():
    '''Test calculate function.'''
    # MISTAKE 2: calculate imported from wrong place
    result = calculate(2, 3)
    assert result == 5


def test_user_display_name()
    # MISTAKE 3: Missing colon (syntax error)
    user = User("john", "john@example.com")
    display = user.get_display_name()
    assert "john" in display
""")

    # Test file 2: Type errors and attribute errors
    test_file_2 = tests_dir / "test_broken_02.py"
    test_file_2.write_text("""
'''Test file with type errors and wrong signatures.'''
import pytest
from app.utils import format_email, validate_username


def test_format_email():
    '''Test email formatting.'''
    # MISTAKE 4: Wrong number of arguments
    result = format_email("TEST@EXAMPLE.COM", True)  # format_email takes 1 arg, not 2
    assert result == "test@example.com"


def test_validate_username():
    '''Test username validation.'''
    # This one is correct
    assert validate_username("john") == True
    assert validate_username("ab") == False  # Too short
    assert validate_username("a" * 25) == False  # Too long


def test_user_methods():
    '''Test user methods.'''
    from app.models import User

    user = User("testuser", "test@example.com")

    # MISTAKE 5: Calling non-existent method
    user.set_name("newname")  # This method doesn't exist

    assert user.username == "newname"
""")

    # Test file 3: Mocking errors
    test_file_3 = tests_dir / "test_broken_03.py"
    test_file_3.write_text("""
'''Test file with mocking errors.'''
import pytest
from unittest.mock import Mock, patch


def test_with_wrong_mock():
    '''Test with incorrect mock setup.'''
    from app.models import User

    # MISTAKE 6: Mock object used incorrectly
    mock_user = Mock(spec=User)
    mock_user.username = "testuser"
    # Forgot to set email attribute

    # This will fail because email is not mocked
    display = mock_user.get_display_name()
    assert "testuser" in display
""")

    # Create conftest.py
    conftest = tests_dir / "conftest.py"
    conftest.write_text("""
'''Pytest configuration for generated tests.'''
import sys
import pathlib

# Add target to path
target_root = pathlib.Path(__file__).parent.parent.parent / "target"
if str(target_root) not in sys.path:
    sys.path.insert(0, str(target_root))
""")

    print(f"✅ Created 3 broken test files with 6 LLM mistakes:")
    print(f"   1. Wrong import (calculate from wrong module)")
    print(f"   2. Import error (function not in module)")
    print(f"   3. Syntax error (missing colon)")
    print(f"   4. Type error (wrong number of arguments)")
    print(f"   5. Attribute error (non-existent method)")
    print(f"   6. Mock error (missing attribute)")

    return tests_dir


def test_components_individually(temp_dir: pathlib.Path, tests_dir: pathlib.Path):
    """Test each component individually."""
    print("\n" + "=" * 80)
    print("🧪 TESTING COMPONENTS INDIVIDUALLY")
    print("=" * 80)

    # Test 1: Pytest failure parser
    print("\n1️⃣  Testing pytest_failure_parser.py...")
    try:
        from src.test_healing.pytest_failure_parser import PytestFailureParser

        # Create sample pytest output
        sample_output = """
FAILED tests/generated/test_broken_01.py::test_calculate_function - ImportError
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _
tests/generated/test_broken_01.py:20: in test_calculate_function
    result = calculate(2, 3)
E   NameError: name 'calculate' is not defined
"""

        parser = PytestFailureParser(str(tests_dir))
        failures = parser.parse_pytest_output(sample_output)

        print(f"   ✅ Parser created")
        print(f"   ✅ Can parse pytest output")
        print(f"   Found {len(failures)} failures in sample")

    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        import traceback
        traceback.print_exc()

    # Test 2: Test AST extractor
    print("\n2️⃣  Testing test_ast_extractor.py...")
    try:
        from src.test_healing.test_ast_extractor import TestASTExtractor

        extractor = TestASTExtractor(tests_dir)

        # Extract from first test file
        test_file = tests_dir / "test_broken_01.py"
        structure = extractor.extract_test_structure(test_file)

        print(f"   ✅ Extractor created")
        print(f"   ✅ Can extract test structure")
        print(f"   Found {len(structure['test_functions'])} test functions")
        print(f"   Test names: {', '.join(structure['all_test_names'])}")

    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        import traceback
        traceback.print_exc()

    # Test 3: Test healer (without LLM call)
    print("\n3️⃣  Testing test_healer.py (structure only)...")
    try:
        from src.test_healing.test_healer import TestHealer
        from src.test_healing.pytest_failure_parser import TestFailure

        target_dir = temp_dir / "target"
        healer = TestHealer(target_dir, tests_dir, use_full_source=False)

        print(f"   ✅ Healer created")
        print(f"   ✅ AST mode configured")

        # Test context extraction (without LLM)
        sample_test_code = "from app.models import User"
        imports = healer._extract_imports_from_test(sample_test_code)

        print(f"   ✅ Can extract imports from test code")
        print(f"   Extracted: {imports}")

    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        import traceback
        traceback.print_exc()

    # Test 4: Auto-healing loop (structure only)
    print("\n4️⃣  Testing auto_healing_loop.py (structure only)...")
    try:
        from src.test_healing.auto_healing_loop import AutoHealingLoop, HealingSession

        loop = AutoHealingLoop(
            target_root=str(temp_dir / "target"),
            generated_tests_dir=str(tests_dir),
            max_iterations=3
        )

        print(f"   ✅ Loop created")
        print(f"   ✅ Max iterations: {loop.max_iterations}")
        print(f"   ✅ Components initialized")

    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        import traceback
        traceback.print_exc()


def run_actual_pytest(tests_dir: pathlib.Path):
    """Run actual pytest to see the failures."""
    print("\n" + "=" * 80)
    print("🔬 RUNNING ACTUAL PYTEST ON BROKEN TESTS")
    print("=" * 80)

    import subprocess

    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", str(tests_dir), "-v", "--tb=short"],
            capture_output=True,
            text=True,
            timeout=30
        )

        print("\nPytest Output:")
        print("-" * 80)
        print(result.stdout)
        if result.stderr:
            print(result.stderr)
        print("-" * 80)

        # Count failures
        import re
        failed_pattern = re.compile(r"(\d+) failed")
        match = failed_pattern.search(result.stdout)

        if match:
            num_failed = int(match.group(1))
            print(f"\n📊 Result: {num_failed} tests failed (as expected)")
            return num_failed
        else:
            print("\n⚠️  Could not parse pytest results")
            return 0

    except subprocess.TimeoutExpired:
        print("⚠️  Pytest timed out")
        return 0
    except Exception as e:
        print(f"❌ Error running pytest: {e}")
        return 0


def verify_imports():
    """Verify all imports work."""
    print("\n" + "=" * 80)
    print("📦 VERIFYING MODULE IMPORTS")
    print("=" * 80)

    modules_to_test = [
        ("src.test_healing", "Package"),
        ("src.test_healing.pytest_failure_parser", "PytestFailureParser"),
        ("src.test_healing.test_ast_extractor", "TestASTExtractor"),
        ("src.test_healing.test_healer", "TestHealer"),
        ("src.test_healing.auto_healing_loop", "AutoHealingLoop"),
        ("src.test_healing.integration", "TestGenerationWithHealing"),
    ]

    all_ok = True
    for module_name, component in modules_to_test:
        try:
            __import__(module_name)
            print(f"✅ {component:30s} - OK")
        except Exception as e:
            print(f"❌ {component:30s} - FAILED: {e}")
            all_ok = False

    return all_ok


def check_dependencies():
    """Check if required dependencies are available."""
    print("\n" + "=" * 80)
    print("🔍 CHECKING DEPENDENCIES")
    print("=" * 80)

    dependencies = {
        "pytest": "pytest",
        "OpenAI client": "src.gen.openai_client",
        "Analyzer": "src.analyzer",
    }

    all_ok = True
    for name, module in dependencies.items():
        try:
            __import__(module.replace(".", "/"))
            print(f"✅ {name:20s} - Available")
        except:
            try:
                parts = module.split(".")
                __import__(parts[0])
                print(f"✅ {name:20s} - Available")
            except Exception as e:
                print(f"⚠️  {name:20s} - Not available: {e}")
                if name == "pytest":
                    all_ok = False

    return all_ok


def main():
    """Main debug function."""
    print("=" * 80)
    print("🐛 AUTO-HEALING SYSTEM DEBUG & TEST")
    print("=" * 80)

    # Change to project root
    project_root = pathlib.Path(__file__).parent
    os.chdir(project_root)

    # Step 1: Check dependencies
    if not check_dependencies():
        print("\n❌ Missing critical dependencies!")
        return 1

    # Step 2: Verify imports
    if not verify_imports():
        print("\n❌ Module import errors detected!")
        print("\nDEBUG: Check that all files are in src/test_healing/")
        return 1

    print("\n✅ All modules imported successfully!")

    # Step 3: Create sample project
    temp_dir = create_sample_project()

    # Step 4: Create broken tests
    tests_dir = create_broken_tests(temp_dir)

    # Step 5: Test components individually
    test_components_individually(temp_dir, tests_dir)

    # Step 6: Run pytest to see failures
    num_failures = run_actual_pytest(tests_dir)

    # Summary
    print("\n" + "=" * 80)
    print("📊 DEBUG SUMMARY")
    print("=" * 80)
    print(f"✅ Sample project created: {temp_dir}")
    print(f"✅ Broken tests created: {tests_dir}")
    print(f"✅ All components loaded successfully")
    print(f"📊 Pytest found {num_failures} failures (expected: 6)")

    print("\n" + "=" * 80)
    print("🎯 NEXT STEPS TO TEST FULL AUTO-HEALING:")
    print("=" * 80)
    print("\n1. The sample project is ready at:")
    print(f"   {temp_dir}")
    print("\n2. To test auto-healing (requires OpenAI API key):")
    print(f"   python -m src.test_healing.auto_healing_loop \\")
    print(f"       --target {temp_dir / 'target'} \\")
    print(f"       --tests-dir {tests_dir} \\")
    print(f"       --max-iterations 3")
    print("\n3. Expected behavior:")
    print("   - Should detect 6 failures")
    print("   - Should classify 5-6 as LLM mistakes (healable)")
    print("   - Should attempt to heal each one")
    print("   - Should reduce failures to 0-1")

    print("\n4. Cleanup (when done):")
    print(f"   rm -rf {temp_dir}")

    print("\n" + "=" * 80)

    return 0


if __name__ == "__main__":
    sys.exit(main())
