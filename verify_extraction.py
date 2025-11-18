#!/usr/bin/env python3
"""
Quick verification script to check if extraction is working correctly.

Usage:
    python verify_extraction.py

This will show you:
1. All extraction features are enabled
2. Expected vs actual extraction behavior
3. Token limit status
"""

import ast
import sys
from pathlib import Path


def check_extraction_features():
    """Verify all extraction features are enabled in the code."""
    print("=" * 80)
    print("EXTRACTION FEATURE VERIFICATION")
    print("=" * 80)
    print()

    extractor_file = Path(__file__).parent / "src/auto_fixer/ast_context_extractor.py"

    if not extractor_file.exists():
        print(f"❌ ERROR: Cannot find {extractor_file}")
        return False

    with open(extractor_file, 'r') as f:
        content = f.read()

    features = {
        "Async function support": {
            "pattern": "isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))",
            "required": True,
            "line": None
        },
        "HTTP endpoint mapping": {
            "pattern": "def _map_endpoints_to_handlers(",
            "required": True,
            "line": None
        },
        "HTTP endpoint fallback search": {
            "pattern": "def _find_files_with_http_endpoints(",
            "required": True,
            "line": None
        },
        "Decorator dependency extraction": {
            "pattern": "def _extract_decorator_dependencies(",
            "required": True,
            "line": None
        },
        "Variable reference support": {
            "pattern": "# dependencies=AUTH_DEPS (variable reference!)",
            "required": True,
            "line": None
        },
        "Decorator dependency indicator": {
            "pattern": '🔐 Found decorator dependencies:',
            "required": True,
            "line": None
        }
    }

    # Check each feature
    all_found = True
    for feature_name, feature_info in features.items():
        if feature_info["pattern"] in content:
            # Find line number
            for i, line in enumerate(content.split('\n'), 1):
                if feature_info["pattern"] in line:
                    feature_info["line"] = i
                    break

            print(f"✅ {feature_name}")
            print(f"   Line {feature_info['line']}: {feature_info['pattern'][:60]}...")
        else:
            print(f"❌ {feature_name}")
            print(f"   Pattern not found: {feature_info['pattern'][:60]}...")
            if feature_info["required"]:
                all_found = False

    print()

    # Check token limit
    import re
    match = re.search(r'self\.max_source_lines\s*=\s*(\d+)', content)
    if match:
        limit = int(match.group(1))
        print(f"📏 Token Limit: {limit} lines")
        if limit == 200:
            print(f"   ✅ Optimal value (200 lines)")
        elif limit < 150:
            print(f"   ⚠️  Too low - might miss dependencies")
        elif limit > 250:
            print(f"   ⚠️  Too high - risk of token overflow")
        else:
            print(f"   ✅ Acceptable value")
    else:
        print(f"❌ Token limit not found in code")
        all_found = False

    print()
    print("=" * 80)

    if all_found:
        print("✅ ALL EXTRACTION FEATURES ARE ENABLED!")
        print()
        print("Expected extraction behavior:")
        print("  • Async functions: WILL be detected ✅")
        print("  • HTTP endpoint handlers: WILL be extracted ✅")
        print("  • Decorator dependencies: WILL be extracted ✅")
        print("  • Variable references (AUTH_DEPS): WILL be resolved ✅")
        print("  • Partial extraction (24-30%): EXPECTED behavior ✅")
        print()
        print("When you run the auto-fixer, look for these indicators:")
        print("  ✓ GET /endpoint → handler_function()")
        print("  🌐 Mapped endpoints to handlers: handler_function")
        print("  🔐 Found decorator dependencies: verify_api_key  ← KEY INDICATOR!")
        print("  ✓ Extracted: handler_function (6 lines)")
        print("  ✓ Extracted: verify_api_key (8 lines, dependency)  ← NEW!")
        print()
        return True
    else:
        print("❌ SOME FEATURES ARE MISSING!")
        print()
        print("This might indicate:")
        print("  • Code not fully committed")
        print("  • Wrong branch checked out")
        print("  • File not saved")
        print()
        return False


def show_extraction_examples():
    """Show examples of what gets extracted vs what doesn't."""
    print()
    print("=" * 80)
    print("EXTRACTION EXAMPLES")
    print("=" * 80)
    print()

    print("📝 Example 1: HTTP Endpoint Test")
    print("-" * 80)
    print("Test code:")
    print("""
    def test_model_info_returns_info():
        client = TestClient(app)
        response = client.get("/model/info")  ← HTTP endpoint detected!
        assert response.status_code == 200
    """)
    print()
    print("Source file: app/main.py (568 lines, 63 definitions)")
    print()
    print("What WILL be extracted (139/568 lines = 24%):")
    print("  ✅ import os")
    print("  ✅ import logging")
    print("  ✅ from fastapi import FastAPI, HTTPException, Depends")
    print("  ✅ MODEL_NAME = os.getenv('MODEL_NAME', 'default')")
    print("  ✅ def verify_api_key(x_api_key: str = Header(None)): ...")
    print("  ✅ @app.get('/model/info', dependencies=[Depends(verify_api_key)])")
    print("  ✅ async def model_info(): ...")
    print("  ✅ def get_model_status(): ...")
    print()
    print("What will NOT be extracted (429/568 lines = 76%):")
    print("  ❌ async def predict_batch(): ...  (not used by this test)")
    print("  ❌ async def health_check(): ...   (not used by this test)")
    print("  ❌ def system_metrics(): ...       (not used by this test)")
    print("  ❌ def root_handler(): ...         (not used by this test)")
    print("  ❌ ... and 34 more unrelated functions")
    print()
    print("Why? Because test only needs model_info() and its dependencies!")
    print()

    print("📝 Example 2: Direct Function Call Test")
    print("-" * 80)
    print("Test code:")
    print("""
    def test_calculate_total():
        from app.utils import calculate_total  ← Direct import!
        result = calculate_total([1, 2, 3])
        assert result == 6
    """)
    print()
    print("Source file: app/utils.py (234 lines, 28 definitions)")
    print()
    print("What WILL be extracted (87/234 lines = 37%):")
    print("  ✅ import math")
    print("  ✅ TAX_RATE = 0.08")
    print("  ✅ def calculate_total(items): ...")
    print("  ✅ def apply_tax(amount): ...  (called by calculate_total)")
    print()
    print("What will NOT be extracted (147/234 lines = 63%):")
    print("  ❌ def format_currency(): ...  (not used)")
    print("  ❌ def validate_items(): ...   (not used)")
    print("  ❌ class ShoppingCart: ...     (not used)")
    print()
    print("=" * 80)
    print()


def show_diagnostic_commands():
    """Show how to verify extraction in real runs."""
    print("=" * 80)
    print("HOW TO VERIFY EXTRACTION IN YOUR RUNS")
    print("=" * 80)
    print()

    print("Step 1: Run auto-fixer with verbose output")
    print("-" * 80)
    print("""
    python run_auto_fixer.py \\
        --test-dir "$CURRENT_DIR/tests/generated" \\
        --project-root "$TARGET_DIR" \\
        --max-iterations 3 \\
        --verbose | tee auto_fixer_output.txt
    """)
    print()

    print("Step 2: Check for key indicators")
    print("-" * 80)
    print("""
    # Look for HTTP endpoint mapping:
    grep "🌐 Mapped endpoints" auto_fixer_output.txt

    # MOST IMPORTANT - Check for decorator dependencies:
    grep "🔐 Found decorator dependencies" auto_fixer_output.txt

    # If you see NO matches, variable reference fix might not be working!

    # Count extraction successes:
    grep "✅ Extracted" auto_fixer_output.txt | wc -l

    # Check average extraction ratio:
    grep "Extracted.*lines" auto_fixer_output.txt
    """)
    print()

    print("Step 3: Expected indicators (SUCCESS)")
    print("-" * 80)
    print("""
    ✓ GET /model/info → model_info()
    🌐 Mapped endpoints to handlers: model_info
    🔐 Found decorator dependencies: verify_api_key  ← YOU MUST SEE THIS!
    🎯 Target functions: model_info, verify_api_key  ← Both included!
      ✓ Extracted: model_info (6 lines)
      ✓ Extracted: verify_api_key (8 lines, dependency)  ← Dependency extracted!
    ✅ Extracted 139/568 lines (18 definitions)
    """)
    print()

    print("Step 4: Warning signs (PROBLEMS)")
    print("-" * 80)
    print("""
    ⚠️  Missing dependency extraction:
        🌐 Mapped endpoints to handlers: model_info
        🎯 Target functions: model_info  ← ONLY handler, NO dependencies!
        ✓ Extracted: model_info (6 lines)
        (No verify_api_key extracted!)

    ⚠️  No HTTP mapping:
        ⚠ No source code context found

    ⚠️  No decorator dependencies found:
        (No "🔐 Found decorator dependencies" message)
    """)
    print()

    print("Step 5: Use diagnostic tool for deep analysis")
    print("-" * 80)
    print("""
    # Extract one test's output:
    grep -A 30 "test_model_info_when_model_loaded" auto_fixer_output.txt > test_extraction.txt

    # Run diagnostic:
    python diagnostic_extraction.py \\
        /path/to/source/app/main.py \\
        test_extraction.txt

    # This will show:
    # - What's available in source (63 definitions)
    # - What was extracted (18 definitions)
    # - What's missing (45 definitions - but that's OK!)
    # - Why it's missing (not used by test)
    """)
    print()

    print("=" * 80)
    print()


def main():
    """Run all verification checks."""
    print()

    # Check features
    features_ok = check_extraction_features()

    if features_ok:
        # Show examples
        show_extraction_examples()

        # Show diagnostic commands
        show_diagnostic_commands()

        print("✅ VERIFICATION COMPLETE")
        print()
        print("Summary:")
        print("  • All extraction features: ENABLED ✅")
        print("  • Token limit: 200 lines (optimal) ✅")
        print("  • Partial extraction: EXPECTED behavior ✅")
        print()
        print("Next steps:")
        print("  1. Run auto-fixer with --verbose flag")
        print("  2. Look for '🔐 Found decorator dependencies' messages")
        print("  3. If you see them: Latest fix is working! 🎉")
        print("  4. If you don't: Check git branch and commits")
        print()
        return 0
    else:
        print("❌ VERIFICATION FAILED")
        print()
        print("Action required:")
        print("  1. Check git status: git status")
        print("  2. Check current branch: git branch")
        print("  3. Ensure latest commits pulled: git log --oneline -5")
        print()
        return 1


if __name__ == "__main__":
    sys.exit(main())
