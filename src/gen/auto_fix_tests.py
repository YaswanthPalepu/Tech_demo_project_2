"""
Auto-fix failing tests using LLM-powered test correction.

This module automatically detects, analyzes, and fixes failing pytest tests
by leveraging LLM to understand errors and generate corrected test code.
"""

import json
import os
import pathlib
import re
import subprocess
import sys
import time
from typing import Dict, List, Optional, Set, Tuple

from .openai_client import create_client, create_chat_completion, get_deployment_name


class TestFailure:
    """Represents a single test failure with all relevant context."""

    def __init__(self, test_file: str, test_name: str, error_message: str,
                 traceback: str, line_number: Optional[int] = None):
        self.test_file = test_file
        self.test_name = test_name
        self.error_message = error_message
        self.traceback = traceback
        self.line_number = line_number
        self.source_files: List[str] = []

    def __repr__(self):
        return f"TestFailure({self.test_file}::{self.test_name})"


def parse_pytest_json(json_report_path: str) -> List[TestFailure]:
    """
    Parse pytest JSON report to extract failed tests.

    Args:
        json_report_path: Path to pytest JSON report file

    Returns:
        List of TestFailure objects
    """
    if not os.path.exists(json_report_path):
        print(f"⚠️  JSON report not found: {json_report_path}")
        return []

    try:
        with open(json_report_path, 'r') as f:
            report = json.load(f)
    except Exception as e:
        print(f"❌ Failed to parse JSON report: {e}")
        return []

    failures = []

    # Parse the report structure
    for test in report.get('tests', []):
        if test.get('outcome') in ['failed', 'error']:
            # Extract test information
            test_id = test.get('nodeid', '')

            # Parse test file and test name from nodeid (format: path/to/test.py::test_name)
            if '::' in test_id:
                test_file, test_name = test_id.split('::', 1)
            else:
                test_file = test_id
                test_name = 'unknown'

            # Get error details
            call_info = test.get('call', {})
            error_message = call_info.get('longrepr', 'No error message')

            # Extract traceback
            traceback = error_message
            if isinstance(error_message, dict):
                traceback = error_message.get('reprcrash', {}).get('message', str(error_message))
            elif isinstance(error_message, list):
                traceback = '\n'.join(str(item) for item in error_message)

            # Try to extract line number from traceback
            line_number = None
            line_match = re.search(r':(\d+):', str(traceback))
            if line_match:
                line_number = int(line_match.group(1))

            failure = TestFailure(
                test_file=test_file,
                test_name=test_name,
                error_message=str(error_message),
                traceback=str(traceback),
                line_number=line_number
            )

            failures.append(failure)

    return failures


def parse_pytest_output(output: str, test_dir: str) -> List[TestFailure]:
    """
    Parse pytest terminal output to extract failed tests (fallback method).

    Args:
        output: Raw pytest output
        test_dir: Directory containing tests

    Returns:
        List of TestFailure objects
    """
    failures = []

    # Pattern to match FAILED lines: FAILED path/to/test.py::test_name - Error
    failed_pattern = re.compile(r'FAILED\s+(.+?)::(.+?)\s+-\s+(.+?)(?:\n|$)')

    for match in failed_pattern.finditer(output):
        test_file = match.group(1).strip()
        test_name = match.group(2).strip()
        error_msg = match.group(3).strip()

        # Try to find the full traceback for this test
        traceback = _extract_traceback_for_test(output, test_file, test_name)

        failure = TestFailure(
            test_file=test_file,
            test_name=test_name,
            error_message=error_msg,
            traceback=traceback or error_msg
        )

        failures.append(failure)

    return failures


def _extract_traceback_for_test(output: str, test_file: str, test_name: str) -> Optional[str]:
    """Extract full traceback for a specific test from pytest output."""
    # Look for the test failure section
    pattern = rf'{re.escape(test_file)}::\s*{re.escape(test_name)}.*?(?=_{10,}|FAILED|PASSED|$)'
    match = re.search(pattern, output, re.DOTALL)

    if match:
        return match.group(0).strip()

    return None


def extract_source_files_from_test(test_file_path: str, target_root: str) -> List[str]:
    """
    Analyze test file to determine which source files it's testing.

    Args:
        test_file_path: Path to the test file
        target_root: Root directory of the source code

    Returns:
        List of source file paths that the test imports/tests
    """
    try:
        with open(test_file_path, 'r') as f:
            test_content = f.read()
    except Exception as e:
        print(f"⚠️  Could not read test file {test_file_path}: {e}")
        return []

    source_files = []
    target_path = pathlib.Path(target_root)

    # Find import statements
    import_patterns = [
        r'from\s+(\S+)\s+import',  # from module import ...
        r'import\s+(\S+)',          # import module
    ]

    for pattern in import_patterns:
        for match in re.finditer(pattern, test_content):
            module_name = match.group(1).strip()

            # Skip standard library and test modules
            if module_name.startswith(('pytest', 'unittest', 'mock', 'sys', 'os', 'pathlib')):
                continue

            # Convert module name to file path
            module_parts = module_name.split('.')

            # Try to find the actual file
            for py_file in target_path.rglob('*.py'):
                if py_file.stem in module_parts or module_parts[-1] in str(py_file):
                    source_files.append(str(py_file))

    return list(set(source_files))  # Remove duplicates


def read_source_code(file_path: str, max_lines: int = 500) -> str:
    """Read source code file with size limit."""
    try:
        with open(file_path, 'r') as f:
            lines = f.readlines()
            if len(lines) > max_lines:
                return ''.join(lines[:max_lines]) + f'\n... (truncated, {len(lines) - max_lines} more lines)'
            return ''.join(lines)
    except Exception as e:
        return f"# Could not read file: {e}"


def generate_fix_prompt(failure: TestFailure, test_code: str, source_code: Dict[str, str]) -> List[Dict]:
    """
    Generate LLM prompt to fix the failing test.

    Args:
        failure: TestFailure object with error details
        test_code: Full content of the failing test file
        source_code: Dict mapping source file paths to their content

    Returns:
        List of message dicts for chat completion
    """
    source_code_context = ""
    if source_code:
        source_code_context = "\n\n".join(
            f"# SOURCE FILE: {file_path}\n{code}"
            for file_path, code in source_code.items()
        )
    else:
        source_code_context = "# No source files detected"

    system_message = {
        "role": "system",
        "content": """You are an expert Python test engineer. Your task is to fix failing pytest tests.

CRITICAL REQUIREMENTS:
1. Analyze the test failure carefully
2. Understand what the test is trying to verify
3. Fix the test code to make it pass while maintaining test integrity
4. DO NOT change the source code - only fix the test
5. Ensure imports are correct
6. Fix any assertion errors, type mismatches, or logic errors
7. Return ONLY the complete, fixed test file code
8. Maintain all existing test functions (don't remove tests)
9. Keep the same file structure and imports

Common issues to fix:
- Incorrect assertions (assertEqual, assertTrue, etc.)
- Wrong expected values
- Missing or incorrect mocks
- Import errors
- Incorrect test setup/teardown
- Type mismatches
- Async/await issues
"""
    }

    user_message = {
        "role": "user",
        "content": f"""Fix this failing test:

# FAILING TEST FILE: {failure.test_file}
# FAILING TEST NAME: {failure.test_name}

# ERROR MESSAGE:
{failure.error_message}

# FULL TRACEBACK:
{failure.traceback}

# CURRENT TEST FILE CODE:
```python
{test_code}
```

# RELEVANT SOURCE CODE BEING TESTED:
{source_code_context}

# INSTRUCTIONS:
1. Analyze why the test is failing
2. Fix the test code to make it pass
3. Ensure the fix maintains test integrity (tests real functionality)
4. Return the COMPLETE fixed test file code inside ```python``` markers
5. Keep all existing tests in the file, just fix the failing one(s)

Generate the fixed test file now:
"""
    }

    return [system_message, user_message]


def fix_test_with_llm(failure: TestFailure, test_code: str, source_code: Dict[str, str],
                      max_retries: int = 2) -> Optional[str]:
    """
    Use LLM to generate fixed version of the failing test.

    Args:
        failure: TestFailure object
        test_code: Current test file content
        source_code: Source files being tested
        max_retries: Maximum number of LLM retries

    Returns:
        Fixed test code or None if failed
    """
    client = create_client()
    deployment = get_deployment_name()

    messages = generate_fix_prompt(failure, test_code, source_code)

    for attempt in range(max_retries):
        try:
            if attempt > 0:
                print(f"  Retry {attempt + 1}/{max_retries}...")
                time.sleep(2)

            # Call LLM
            response = create_chat_completion(client, deployment, messages)

            if not response or not response.strip():
                print(f"  ⚠️  Empty response from LLM")
                continue

            # Extract Python code from response
            fixed_code = _extract_python_code(response)

            if not fixed_code:
                print(f"  ⚠️  No Python code found in LLM response")
                continue

            # Basic validation
            if 'def test_' not in fixed_code:
                print(f"  ⚠️  Fixed code doesn't contain test functions")
                continue

            # Validate Python syntax
            try:
                compile(fixed_code, '<string>', 'exec')
            except SyntaxError as e:
                print(f"  ⚠️  Fixed code has syntax error: {e}")
                continue

            return fixed_code

        except Exception as e:
            print(f"  ⚠️  LLM call failed: {e}")
            continue

    print(f"  ❌ Failed to generate fix after {max_retries} attempts")
    return None


def _extract_python_code(text: str) -> Optional[str]:
    """Extract Python code from markdown code blocks or raw text."""
    # Try to find code blocks
    code_block_pattern = r'```(?:python)?\s*(.*?)```'
    matches = re.findall(code_block_pattern, text, re.DOTALL | re.IGNORECASE)

    if matches:
        # Return the largest code block (likely the full file)
        return max(matches, key=len).strip()

    # If no code blocks, check if the entire response is code
    if 'import' in text and 'def ' in text:
        return text.strip()

    return None


def run_pytest_with_json(test_dir: str, target_dir: str, json_output: str,
                         current_dir: str) -> Tuple[int, str]:
    """
    Run pytest and generate JSON report.

    Args:
        test_dir: Directory containing tests
        target_dir: Directory to measure coverage
        json_output: Path for JSON report output
        current_dir: Current working directory

    Returns:
        (return_code, stdout)
    """
    cmd = [
        'pytest',
        f'{current_dir}/{test_dir}',
        f'--cov={target_dir}',
        '--cov-config=pytest.ini',
        '--cov-report=term-missing',
        '--cov-report=xml',
        '--cov-report=html',
        '--cov-fail-under=0',
        f'--json-report',
        f'--json-report-file={json_output}',
        '-v'
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300  # 5 minute timeout
        )
        return result.returncode, result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        print("⚠️  Pytest timed out after 5 minutes")
        return 1, "Timeout"
    except Exception as e:
        print(f"❌ Failed to run pytest: {e}")
        return 1, str(e)


def auto_fix_failing_tests(test_dir: str, target_dir: str, current_dir: str,
                           max_iterations: int = 3) -> bool:
    """
    Automatically fix failing tests using LLM.

    Args:
        test_dir: Directory containing tests (e.g., 'tests/generated')
        target_dir: Directory of source code being tested
        current_dir: Current working directory
        max_iterations: Maximum number of fix iterations

    Returns:
        True if all tests pass, False otherwise
    """
    print("\n" + "="*80)
    print("🔧 AUTO-FIX FAILING TESTS")
    print("="*80)

    json_report = f'{current_dir}/.pytest_report.json'

    for iteration in range(1, max_iterations + 1):
        print(f"\n{'='*80}")
        print(f"🔄 Iteration {iteration}/{max_iterations}")
        print(f"{'='*80}\n")

        # Run pytest with JSON report
        print(f"🧪 Running pytest on {test_dir}...")
        return_code, output = run_pytest_with_json(test_dir, target_dir, json_report, current_dir)

        # Check if all tests passed
        if return_code == 0:
            print(f"\n✅ SUCCESS! All tests passed on iteration {iteration}")
            return True

        print(f"\n⚠️  Some tests failed (exit code: {return_code})")

        # Parse failures
        failures = parse_pytest_json(json_report)

        if not failures:
            # Fallback to parsing terminal output
            print("  Falling back to terminal output parsing...")
            failures = parse_pytest_output(output, test_dir)

        if not failures:
            print("  ❌ Could not parse test failures - stopping auto-fix")
            return False

        print(f"\n📋 Found {len(failures)} failing test(s):")
        for i, failure in enumerate(failures, 1):
            print(f"  {i}. {failure.test_file}::{failure.test_name}")

        # Fix each failing test
        fixed_count = 0
        for i, failure in enumerate(failures, 1):
            print(f"\n🔧 Fixing test {i}/{len(failures)}: {failure.test_name}")

            # Read current test file
            test_file_path = os.path.join(current_dir, failure.test_file)
            if not os.path.exists(test_file_path):
                print(f"  ⚠️  Test file not found: {test_file_path}")
                continue

            try:
                with open(test_file_path, 'r') as f:
                    test_code = f.read()
            except Exception as e:
                print(f"  ⚠️  Could not read test file: {e}")
                continue

            # Find source files being tested
            source_file_paths = extract_source_files_from_test(test_file_path, target_dir)
            failure.source_files = source_file_paths

            # Read source code
            source_code = {}
            for src_path in source_file_paths[:3]:  # Limit to 3 files to avoid token limits
                source_code[src_path] = read_source_code(src_path)

            # Generate fix using LLM
            print(f"  🤖 Asking LLM to fix the test...")
            fixed_code = fix_test_with_llm(failure, test_code, source_code)

            if not fixed_code:
                print(f"  ❌ Could not generate fix for {failure.test_name}")
                continue

            # Write fixed code back to file
            try:
                with open(test_file_path, 'w') as f:
                    f.write(fixed_code)
                print(f"  ✅ Fixed and saved: {test_file_path}")
                fixed_count += 1
            except Exception as e:
                print(f"  ❌ Could not write fixed code: {e}")
                continue

        if fixed_count == 0:
            print(f"\n❌ Could not fix any tests in iteration {iteration}")
            return False

        print(f"\n✅ Fixed {fixed_count}/{len(failures)} test(s)")
        print(f"   Re-running pytest to verify fixes...")

    # If we've exhausted all iterations
    print(f"\n⚠️  Max iterations ({max_iterations}) reached")
    print(f"   Some tests may still be failing")

    # Final run to check status
    final_return_code, _ = run_pytest_with_json(test_dir, target_dir, json_report, current_dir)
    return final_return_code == 0


def main():
    """CLI entry point for auto-fix."""
    import argparse

    parser = argparse.ArgumentParser(description='Auto-fix failing pytest tests using LLM')
    parser.add_argument('--test-dir', required=True, help='Directory containing tests')
    parser.add_argument('--target-dir', required=True, help='Directory of source code')
    parser.add_argument('--current-dir', default=os.getcwd(), help='Current directory')
    parser.add_argument('--max-iterations', type=int, default=3, help='Max fix iterations')

    args = parser.parse_args()

    success = auto_fix_failing_tests(
        test_dir=args.test_dir,
        target_dir=args.target_dir,
        current_dir=args.current_dir,
        max_iterations=args.max_iterations
    )

    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
