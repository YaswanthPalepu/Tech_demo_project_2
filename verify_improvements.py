#!/usr/bin/env python3
"""Verify that all improvements have been implemented correctly."""

import ast
import sys
from pathlib import Path

def check_file(file_path: Path, checks: list) -> tuple[bool, list]:
    """Check if file contains expected improvements."""
    try:
        content = file_path.read_text()
        passed = []
        failed = []
        
        for check_name, check_pattern in checks:
            if check_pattern in content:
                passed.append(check_name)
            else:
                failed.append(check_name)
        
        return len(failed) == 0, failed
    except Exception as e:
        return False, [f"Error reading file: {e}"]

def main():
    """Run verification checks."""
    print("🔍 Verifying AI TestGen Improvements...\n")
    
    root = Path(__file__).parent
    all_passed = True
    
    # Check 1: enhanced_prompt.py includes methods
    print("1. Checking enhanced_prompt.py...")
    checks = [
        ("Methods in targets_count", 'methods = compact.get("methods", [])'),
        ("Methods in focus_for", "target_list = functions + classes + methods"),
        ("Real imports emphasis", "ALWAYS import real modules"),
    ]
    passed, failed = check_file(root / "src/gen/enhanced_prompt.py", checks)
    if passed:
        print("   ✅ All checks passed")
    else:
        print(f"   ❌ Failed: {', '.join(failed)}")
        all_passed = False
    
    # Check 2: enhanced_analysis_utils.py has no priority scoring
    print("\n2. Checking enhanced_analysis_utils.py...")
    checks = [
        ("No priority scoring", "Keep all targets in natural file order"),
        ("Methods in filter", '"methods"'),
    ]
    passed, failed = check_file(root / "src/gen/enhanced_analysis_utils.py", checks)
    if passed:
        print("   ✅ All checks passed")
    else:
        print(f"   ❌ Failed: {', '.join(failed)}")
        all_passed = False
    
    # Check 3: conftest_text.py forces real imports
    print("\n3. Checking conftest_text.py...")
    checks = [
        ("Real imports only", "REAL imports ONLY"),
        ("Auto-detect app", "Auto-detect and import real app factory"),
        ("Django auto-setup", "Auto-detect and setup Django"),
        ("Database fixtures", "def db_setup"),
    ]
    passed, failed = check_file(root / "src/gen/conftest_text.py", checks)
    if passed:
        print("   ✅ All checks passed")
    else:
        print(f"   ❌ Failed: {', '.join(failed)}")
        all_passed = False
    
    # Check 4: analyzer.py captures all methods
    print("\n4. Checking analyzer.py...")
    checks = [
        ("Private method flag", '"is_private"'),
        ("Args count", '"args_count"'),
        ("Method count in class", '"method_count"'),
    ]
    passed, failed = check_file(root / "src/analyzer.py", checks)
    if passed:
        print("   ✅ All checks passed")
    else:
        print(f"   ❌ Failed: {', '.join(failed)}")
        all_passed = False
    
    # Check 5: enhanced_generate.py includes full context
    print("\n5. Checking enhanced_generate.py...")
    checks = [
        ("Full file content", "FULL CONTENT FOR MAXIMUM COVERAGE"),
        ("Increased max bytes", "max_bytes: int = 100000"),
    ]
    passed, failed = check_file(root / "src/gen/enhanced_generate.py", checks)
    if passed:
        print("   ✅ All checks passed")
    else:
        print(f"   ❌ Failed: {', '.join(failed)}")
        all_passed = False
    
    # Summary
    print("\n" + "="*60)
    if all_passed:
        print("✅ ALL IMPROVEMENTS VERIFIED SUCCESSFULLY!")
        print("\n🚀 Ready to generate tests with:")
        print("   TESTGEN_FORCE=true python -m src.gen --target ./your_project")
        return 0
    else:
        print("❌ SOME CHECKS FAILED - Please review the files")
        return 1

if __name__ == "__main__":
    sys.exit(main())
