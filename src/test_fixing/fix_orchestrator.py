import subprocess
from pathlib import Path
from .failure_parser import parse_pytest_failures
from .ast_utils import extract_test_function
from .patcher import patch_test_function
from .llm_fixer import fix_test_with_llm

MAX_ITER = 3

def run_pytest(test_dir: str) -> str:
    """Run pytest and return the full output."""
    result = subprocess.run(
        ["pytest", "-q", test_dir],
        capture_output=True,
        text=True
    )
    return result.stdout + result.stderr


def fix_tests(test_dir: str):
    for iteration in range(MAX_ITER):
        print(f"\n🔁 FIX ITERATION {iteration + 1}")

        output = run_pytest(test_dir)
        failures = parse_pytest_failures(output)

        if not failures:
            print("🎉 All failing tests fixed!")
            return True

        for file_path, test_name in failures:
            abs_path = str(Path(file_path).resolve())

            with open(abs_path, "r") as f:
                source = f.read()

            # AST extract
            test_code, start, end = extract_test_function(source, test_name)

            # LLM fix
            fixed_code = fix_test_with_llm(
                test_name=test_name,
                test_code=test_code,
                full_file=source,
                traceback=output
            )

            # Patch test function
            patch_test_function(abs_path, start, end, fixed_code)

    print("❌ Could not fix all tests after max iterations.")
    return False
