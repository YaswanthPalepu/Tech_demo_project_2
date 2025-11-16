#!/usr/bin/env python3
"""
Auto-fix failing tests using LLM assistance.

This module runs pytest, identifies failing tests, and uses an LLM to generate fixes.
It includes comprehensive logging to track the LLM's behavior and decision-making process.
"""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .openai_client import create_client, get_deployment_name, create_chat_completion
from .env import ENABLE_DEBUG


class TestFixLogger:
    """Enhanced logger to track LLM behavior and validation."""

    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.llm_interactions = []

    def header(self, text: str, char: str = "="):
        """Print a header."""
        print(f"\n{char * 80}")
        print(text)
        print(f"{char * 80}\n")

    def info(self, text: str, emoji: str = "ℹ️"):
        """Print info message."""
        print(f"{emoji}  {text}")

    def success(self, text: str):
        """Print success message."""
        print(f"✅ {text}")

    def warning(self, text: str):
        """Print warning message."""
        print(f"⚠️  {text}")

    def error(self, text: str):
        """Print error message."""
        print(f"❌ {text}")

    def debug(self, text: str):
        """Print debug message if verbose."""
        if self.verbose or ENABLE_DEBUG:
            print(f"🔍 [DEBUG] {text}")

    def llm_request(self, test_name: str, error_msg: str, prompt_preview: str):
        """Log LLM request details."""
        self.debug(f"LLM Request for: {test_name}")
        self.debug(f"Error: {error_msg[:200]}...")
        self.debug(f"Prompt preview: {prompt_preview[:300]}...")

        self.llm_interactions.append({
            "test": test_name,
            "error": error_msg,
            "prompt_length": len(prompt_preview)
        })

    def llm_response(self, test_name: str, response: str, validation: Dict):
        """Log LLM response and validation."""
        self.debug(f"LLM Response length: {len(response)} chars")
        self.debug(f"Validation: {json.dumps(validation, indent=2)}")

        # Update last interaction
        if self.llm_interactions:
            self.llm_interactions[-1].update({
                "response_length": len(response),
                "validation": validation
            })

    def summary(self):
        """Print summary of LLM interactions."""
        self.header("🔬 LLM BEHAVIOR ANALYSIS", "=")

        print(f"Total LLM interactions: {len(self.llm_interactions)}\n")

        for i, interaction in enumerate(self.llm_interactions, 1):
            print(f"{i}. Test: {interaction['test']}")
            print(f"   Prompt length: {interaction.get('prompt_length', 'N/A')} chars")
            print(f"   Response length: {interaction.get('response_length', 'N/A')} chars")

            validation = interaction.get('validation', {})
            print(f"   Validation:")
            print(f"     - Has code: {validation.get('has_code', False)}")
            print(f"     - Has imports: {validation.get('has_imports', False)}")
            print(f"     - Has test function: {validation.get('has_test_function', False)}")
            print(f"     - Is complete: {validation.get('is_complete', False)}")
            print()


class TestFixer:
    """Main class for auto-fixing tests."""

    def __init__(self, test_dir: str, target_dir: Optional[str], current_dir: Optional[str],
                 max_iterations: int = 3, verbose: bool = True):
        self.test_dir = Path(test_dir)
        self.target_dir = Path(target_dir) if target_dir else None
        self.current_dir = Path(current_dir) if current_dir else Path.cwd()
        self.max_iterations = max_iterations
        self.logger = TestFixLogger(verbose)

        # Initialize LLM client
        try:
            self.client = create_client()
            self.deployment = get_deployment_name()
            self.logger.success(f"LLM client initialized (deployment: {self.deployment})")
        except Exception as e:
            self.logger.error(f"Failed to initialize LLM client: {e}")
            raise

    def run_pytest(self) -> Tuple[int, Optional[Dict]]:
        """
        Run pytest and return exit code and parsed results.

        Returns:
            Tuple of (exit_code, test_results_dict or None)
        """
        self.logger.info(f"Running pytest on {self.test_dir}...", "🧪")

        # Ensure report directory exists
        report_path = self.current_dir / ".pytest_report.json"

        # Run pytest with JSON report
        cmd = [
            sys.executable, "-m", "pytest",
            str(self.test_dir),
            "-v",
            "--tb=short",
            "--json-report",
            f"--json-report-file={report_path}",
            "--json-report-indent=2"
        ]

        self.logger.debug(f"Command: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=str(self.current_dir)
            )

            exit_code = result.returncode

            # Parse exit code meaning
            exit_code_meanings = {
                0: "All tests passed",
                1: "Some tests failed",
                2: "Test execution interrupted/error",
                3: "Internal pytest error",
                4: "Command line usage error",
                5: "No tests collected"
            }

            meaning = exit_code_meanings.get(exit_code, f"Unknown exit code: {exit_code}")

            if exit_code == 0:
                self.logger.success(f"All tests passed!")
                return exit_code, None
            else:
                self.logger.warning(f"Some tests failed (exit code: {exit_code} - {meaning})")

            # Try to read JSON report
            if report_path.exists():
                try:
                    with open(report_path, 'r') as f:
                        report = json.load(f)
                    self.logger.debug(f"JSON report loaded: {len(report.get('tests', []))} tests")
                    return exit_code, report
                except Exception as e:
                    self.logger.warning(f"Failed to parse JSON report: {e}")
            else:
                self.logger.warning(f"JSON report not found: {report_path}")

            # Fallback: parse terminal output
            self.logger.info("Falling back to terminal output parsing...")
            parsed_failures = self._parse_terminal_output(result.stdout + result.stderr, exit_code)

            if parsed_failures:
                return exit_code, {"tests": parsed_failures}
            else:
                # Show actual output to help diagnose
                self.logger.error("Could not parse test failures")
                self.logger.debug("=== STDOUT ===")
                self.logger.debug(result.stdout[:2000])
                self.logger.debug("=== STDERR ===")
                self.logger.debug(result.stderr[:2000])
                return exit_code, None

        except Exception as e:
            self.logger.error(f"Failed to run pytest: {e}")
            raise

    def _parse_terminal_output(self, output: str, exit_code: int) -> List[Dict]:
        """
        Parse pytest terminal output to extract failing tests.

        This is a fallback when JSON report is not available.
        """
        self.logger.debug("Parsing terminal output for failures...")

        # Handle different exit codes
        if exit_code == 2:
            # Collection/execution error - look for the error message
            self.logger.error("Pytest exit code 2: Test collection or execution error")

            # Try to extract error details
            error_patterns = [
                r"ERROR collecting (.+)",
                r"ERRORS.*\n(.+)",
                r"ImportError: (.+)",
                r"ModuleNotFoundError: (.+)",
                r"SyntaxError: (.+)",
                r"FAILED (.+) - (.+)"
            ]

            for pattern in error_patterns:
                matches = re.findall(pattern, output, re.MULTILINE)
                if matches:
                    self.logger.error(f"Found errors: {matches[:5]}")  # Show first 5
                    break

            # Check for common issues
            if "ImportError" in output or "ModuleNotFoundError" in output:
                self.logger.error("Import error detected - check test dependencies and imports")
            if "SyntaxError" in output:
                self.logger.error("Syntax error detected - check generated test code syntax")
            if "django.core.exceptions.ImproperlyConfigured" in output:
                self.logger.error("Django configuration error - check DJANGO_SETTINGS_MODULE")

            return []

        if exit_code == 5:
            self.logger.error("No tests collected - check test directory and file names")
            return []

        # Parse FAILED lines for actual test failures (exit code 1)
        failures = []
        failed_pattern = r"FAILED (.+?) - (.+)"

        for match in re.finditer(failed_pattern, output):
            test_id = match.group(1)
            error_msg = match.group(2)

            failures.append({
                "nodeid": test_id,
                "outcome": "failed",
                "call": {
                    "longrepr": error_msg
                }
            })

        if failures:
            self.logger.debug(f"Parsed {len(failures)} failures from terminal output")

        return failures

    def extract_test_failures(self, report: Dict) -> List[Dict]:
        """Extract failing tests from pytest report."""
        failures = []

        for test in report.get("tests", []):
            if test.get("outcome") == "failed":
                failures.append({
                    "nodeid": test.get("nodeid"),
                    "error": self._extract_error_message(test),
                    "test_data": test
                })

        return failures

    def _extract_error_message(self, test: Dict) -> str:
        """Extract error message from test data."""
        # Try different locations for error message
        call = test.get("call", {})

        if "longrepr" in call:
            longrepr = call["longrepr"]
            if isinstance(longrepr, str):
                return longrepr
            elif isinstance(longrepr, dict):
                return longrepr.get("reprcrash", {}).get("message", "Unknown error")

        if "crash" in call:
            return str(call["crash"])

        return "Unknown error - check pytest output"

    def fix_test(self, test_file: Path, test_name: str, error_msg: str) -> bool:
        """
        Use LLM to fix a failing test.

        Returns:
            True if fix was applied, False otherwise
        """
        self.logger.info(f"Asking LLM to fix the test...", "🤖")

        # Read current test file
        try:
            with open(test_file, 'r') as f:
                current_code = f.read()
        except Exception as e:
            self.logger.error(f"Failed to read test file: {e}")
            return False

        # Build prompt
        system_prompt = """You are an expert Python test engineer. Your task is to fix failing pytest tests.

You will receive:
1. The current test file code
2. The name of the failing test
3. The error message

Your response MUST:
1. Contain the COMPLETE fixed test file code (not just the changed part)
2. Be valid Python code that can be directly written to the file
3. Fix the specific error while maintaining all other tests
4. Include all necessary imports
5. Follow pytest best practices

IMPORTANT: Return ONLY the complete Python code for the entire test file, nothing else.
No explanations, no markdown code blocks, just the raw Python code."""

        user_prompt = f"""Fix the following failing test:

Test name: {test_name}
Error: {error_msg}

Current test file code:
```python
{current_code}
```

Provide the complete fixed test file code."""

        # Log request
        self.logger.llm_request(test_name, error_msg, user_prompt)

        # Call LLM
        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]

            response = create_chat_completion(
                self.client,
                self.deployment,
                messages,
                max_tokens=4000
            )

            # Validate response
            validation = self._validate_llm_response(response, test_name)
            self.logger.llm_response(test_name, response, validation)

            if not validation["is_complete"]:
                self.logger.warning(f"LLM response validation failed: {validation}")
                return False

            # Clean response (remove markdown code blocks if present)
            cleaned_code = self._clean_llm_response(response)

            # Write fixed code
            with open(test_file, 'w') as f:
                f.write(cleaned_code)

            self.logger.success(f"Fixed and saved: {test_file}")
            return True

        except Exception as e:
            self.logger.error(f"LLM fix failed: {e}")
            return False

    def _validate_llm_response(self, response: str, test_name: str) -> Dict:
        """
        Validate that LLM response looks like proper test code.

        Returns:
            Dict with validation results
        """
        validation = {
            "has_code": len(response.strip()) > 0,
            "has_imports": "import" in response,
            "has_test_function": f"def {test_name}" in response or "def test_" in response,
            "has_pytest_markers": "@pytest" in response or "def test_" in response,
            "no_markdown": "```" not in response or response.count("```") >= 2,  # Either no markdown or complete blocks
            "is_complete": False
        }

        # Check for common issues
        validation["has_syntax_errors"] = False
        try:
            compile(self._clean_llm_response(response), '<string>', 'exec')
        except SyntaxError:
            validation["has_syntax_errors"] = True

        # Overall completeness check
        validation["is_complete"] = (
            validation["has_code"] and
            validation["has_imports"] and
            validation["has_test_function"] and
            not validation["has_syntax_errors"]
        )

        return validation

    def _clean_llm_response(self, response: str) -> str:
        """Clean LLM response by removing markdown code blocks if present."""
        # Remove markdown code blocks
        cleaned = response.strip()

        # If wrapped in ```python ... ```, extract the code
        if cleaned.startswith("```python"):
            cleaned = cleaned[len("```python"):].strip()
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:].strip()

        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()

        return cleaned

    def run(self):
        """Main execution loop."""
        self.logger.header("🔧 AUTO-FIX FAILING TESTS")

        for iteration in range(1, self.max_iterations + 1):
            self.logger.header(f"🔄 Iteration {iteration}/{self.max_iterations}", "=")

            # Run pytest
            exit_code, report = self.run_pytest()

            if exit_code == 0:
                self.logger.success("All tests passed!")
                self.logger.summary()
                return 0

            if report is None:
                self.logger.error("Could not parse test failures - stopping auto-fix")
                self.logger.summary()
                return 1

            # Extract failures
            failures = self.extract_test_failures(report)

            if not failures:
                self.logger.warning("No specific test failures identified")
                self.logger.summary()
                return 1

            self.logger.info(f"Found {len(failures)} failing test(s):", "📋")
            for i, failure in enumerate(failures, 1):
                print(f"  {i}. {failure['nodeid']}")
            print()

            # Fix each failure
            fixed_count = 0
            for i, failure in enumerate(failures, 1):
                nodeid = failure["nodeid"]
                error = failure["error"]

                # Parse nodeid to get file and test name
                # Format: path/to/file.py::test_name or path/to/file.py::TestClass::test_name
                parts = nodeid.split("::")
                test_file = Path(parts[0])
                test_name = parts[-1].split("[")[0]  # Remove parametrize markers

                self.logger.info(f"Fixing test {i}/{len(failures)}: {test_name}", "🔧")

                if self.fix_test(test_file, test_name, error):
                    fixed_count += 1

            self.logger.success(f"Fixed {fixed_count}/{len(failures)} test(s)")

            if fixed_count > 0:
                self.logger.info("Re-running pytest to verify fixes...")
            else:
                self.logger.warning("No fixes applied - stopping")
                self.logger.summary()
                return 1

        # Max iterations reached
        self.logger.warning(f"Reached maximum iterations ({self.max_iterations})")
        self.logger.summary()
        return 1


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Auto-fix failing tests using LLM assistance"
    )
    parser.add_argument(
        "--test-dir",
        required=True,
        help="Directory containing tests to fix"
    )
    parser.add_argument(
        "--target-dir",
        help="Target directory for the project"
    )
    parser.add_argument(
        "--current-dir",
        help="Current working directory"
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=3,
        help="Maximum number of fix iterations (default: 3)"
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Reduce output verbosity"
    )

    args = parser.parse_args()

    try:
        fixer = TestFixer(
            test_dir=args.test_dir,
            target_dir=args.target_dir,
            current_dir=args.current_dir,
            max_iterations=args.max_iterations,
            verbose=not args.quiet
        )

        return fixer.run()

    except KeyboardInterrupt:
        print("\n\nAuto-fix interrupted by user.")
        return 1
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        if ENABLE_DEBUG:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
