#!/usr/bin/env python3
"""
Pytest Failure Parser - Parses pytest output to extract failure details.

This module parses pytest's output to extract:
- Test names that failed
- Tracebacks with file paths and line numbers
- Error messages
- Expected vs actual values (for assertion errors)
- Full error context
"""

import re
import pathlib
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field


@dataclass
class TestFailure:
    """Represents a single test failure."""
    test_name: str
    test_file: str
    test_line: int
    error_type: str
    error_message: str
    traceback: List[str] = field(default_factory=list)
    assertion_details: Optional[Dict[str, Any]] = None
    full_output: str = ""
    is_syntax_error: bool = False
    is_import_error: bool = False
    is_assertion_error: bool = False
    is_llm_mistake: bool = False  # Determined by analysis


class PytestFailureParser:
    """Parse pytest output to extract failure information."""

    # Patterns for parsing pytest output
    FAILED_TEST_PATTERN = re.compile(r"FAILED\s+(.+?)::(.+?)\s+-")
    ERROR_TEST_PATTERN = re.compile(r"ERROR\s+(.+?)::(.+?)\s+-")
    TRACEBACK_FILE_PATTERN = re.compile(r'File\s+"(.+?)",\s+line\s+(\d+)')
    ASSERTION_PATTERN = re.compile(r"assert\s+(.+)")
    EXPECTED_ACTUAL_PATTERN = re.compile(r"Expected:\s*(.+?)\s+Actual:\s*(.+)")

    def __init__(self, generated_tests_dir: str = "tests/generated"):
        """
        Initialize the pytest failure parser.

        Args:
            generated_tests_dir: Directory containing generated tests
        """
        self.generated_tests_dir = pathlib.Path(generated_tests_dir)

    def parse_pytest_output(self, output: str) -> List[TestFailure]:
        """
        Parse pytest output and extract all failures.

        Args:
            output: Raw pytest output string

        Returns:
            List of TestFailure objects
        """
        failures = []

        # Split output into test sections
        sections = self._split_into_test_sections(output)

        for section in sections:
            failure = self._parse_test_section(section)
            if failure:
                # Only include failures from generated tests
                if self._is_generated_test(failure.test_file):
                    # Classify the failure type
                    failure.is_llm_mistake = self._is_llm_mistake(failure)
                    failures.append(failure)

        return failures

    def parse_pytest_json_report(self, json_report: Dict[str, Any]) -> List[TestFailure]:
        """
        Parse pytest JSON report (from pytest --json-report plugin).

        Args:
            json_report: Parsed JSON report

        Returns:
            List of TestFailure objects
        """
        failures = []

        for test in json_report.get("tests", []):
            if test.get("outcome") in ["failed", "error"]:
                failure = self._parse_json_test(test)
                if failure and self._is_generated_test(failure.test_file):
                    failure.is_llm_mistake = self._is_llm_mistake(failure)
                    failures.append(failure)

        return failures

    def _split_into_test_sections(self, output: str) -> List[str]:
        """Split pytest output into individual test failure sections."""
        # Look for test failure markers
        sections = []
        current_section = []
        in_failure = False

        for line in output.splitlines():
            # Start of failure section
            if "FAILED" in line or "ERROR" in line or "_ _ _" in line:
                if current_section and in_failure:
                    sections.append("\n".join(current_section))
                    current_section = []
                in_failure = True

            if in_failure:
                current_section.append(line)

            # End of failure section (next test starts or summary)
            if line.startswith("=") and "short test summary" in line.lower():
                if current_section:
                    sections.append("\n".join(current_section))
                    current_section = []
                in_failure = False

        # Add last section
        if current_section:
            sections.append("\n".join(current_section))

        return sections

    def _parse_test_section(self, section: str) -> Optional[TestFailure]:
        """Parse a single test failure section."""
        lines = section.splitlines()

        # Extract test name and file
        test_name = None
        test_file = None
        test_line = 0

        for line in lines:
            # Match FAILED or ERROR line
            match = self.FAILED_TEST_PATTERN.search(line)
            if not match:
                match = self.ERROR_TEST_PATTERN.search(line)

            if match:
                test_file = match.group(1)
                test_name = match.group(2)
                break

        if not test_name or not test_file:
            return None

        # Extract traceback
        traceback = []
        error_type = "Unknown"
        error_message = ""
        in_traceback = False

        for i, line in enumerate(lines):
            # Detect traceback start
            if "Traceback (most recent call last):" in line or "_ _ _" in line:
                in_traceback = True
                continue

            if in_traceback:
                traceback.append(line)

                # Extract file and line from traceback
                file_match = self.TRACEBACK_FILE_PATTERN.search(line)
                if file_match:
                    test_file = file_match.group(1)
                    test_line = int(file_match.group(2))

                # Extract error type and message
                if line.strip() and not line.startswith(" ") and "Error" in line:
                    parts = line.split(":", 1)
                    if len(parts) == 2:
                        error_type = parts[0].strip()
                        error_message = parts[1].strip()

        # Extract assertion details
        assertion_details = self._extract_assertion_details(section)

        # Classify error types
        is_syntax_error = "SyntaxError" in error_type
        is_import_error = "ImportError" in error_type or "ModuleNotFoundError" in error_type
        is_assertion_error = "AssertionError" in error_type

        failure = TestFailure(
            test_name=test_name,
            test_file=test_file,
            test_line=test_line,
            error_type=error_type,
            error_message=error_message,
            traceback=traceback,
            assertion_details=assertion_details,
            full_output=section,
            is_syntax_error=is_syntax_error,
            is_import_error=is_import_error,
            is_assertion_error=is_assertion_error
        )

        return failure

    def _parse_json_test(self, test_data: Dict[str, Any]) -> Optional[TestFailure]:
        """Parse a test from JSON report."""
        test_name = test_data.get("nodeid", "")
        test_file = test_name.split("::")[0] if "::" in test_name else ""

        call_info = test_data.get("call", {})
        longrepr = call_info.get("longrepr", "")

        # Extract error details
        error_type = "Unknown"
        error_message = ""
        traceback = []

        if isinstance(longrepr, str):
            traceback = longrepr.splitlines()
            for line in traceback:
                if "Error" in line and ":" in line:
                    parts = line.split(":", 1)
                    error_type = parts[0].strip()
                    error_message = parts[1].strip()
                    break

        failure = TestFailure(
            test_name=test_name,
            test_file=test_file,
            test_line=call_info.get("lineno", 0),
            error_type=error_type,
            error_message=error_message,
            traceback=traceback,
            full_output=longrepr if isinstance(longrepr, str) else str(longrepr),
            is_syntax_error="SyntaxError" in error_type,
            is_import_error="ImportError" in error_type or "ModuleNotFoundError" in error_type,
            is_assertion_error="AssertionError" in error_type
        )

        return failure

    def _extract_assertion_details(self, section: str) -> Optional[Dict[str, Any]]:
        """Extract assertion details like expected vs actual values."""
        assertion_details = {}

        # Look for assertion comparison
        for line in section.splitlines():
            # pytest assertion rewriting shows comparisons
            if " == " in line or " != " in line or " > " in line or " < " in line:
                assertion_details["comparison"] = line.strip()

            # Extract expected/actual if formatted
            match = self.EXPECTED_ACTUAL_PATTERN.search(line)
            if match:
                assertion_details["expected"] = match.group(1).strip()
                assertion_details["actual"] = match.group(2).strip()

            # Extract assert line
            if line.strip().startswith("assert"):
                assertion_details["assertion"] = line.strip()

        return assertion_details if assertion_details else None

    def _is_generated_test(self, test_file: str) -> bool:
        """Check if test file is in generated tests directory."""
        test_path = pathlib.Path(test_file)
        return str(self.generated_tests_dir) in str(test_path)

    def _is_llm_mistake(self, failure: TestFailure) -> bool:
        """
        Determine if failure is likely an LLM mistake vs a real code bug.

        LLM mistakes include:
        - Syntax errors in generated tests
        - Import errors for modules that don't exist
        - Incorrect mocking/patching
        - Wrong function signatures
        - Incorrect assertions
        """
        # Syntax errors in tests are always LLM mistakes
        if failure.is_syntax_error:
            return True

        # Import errors in test code (not in source) are LLM mistakes
        if failure.is_import_error:
            # Check if error is in test file itself
            for line in failure.traceback:
                if failure.test_file in line:
                    return True

        # Check for common LLM mistakes in error messages
        llm_mistake_indicators = [
            "takes",
            "positional argument",  # Wrong number of args
            "unexpected keyword argument",  # Wrong kwargs
            "has no attribute",  # Wrong attribute access in test
            "is not callable",  # Trying to call non-callable
            "not iterable",  # Wrong iteration in test
            "cannot unpack",  # Wrong unpacking
            "takes no arguments",  # Wrong method call
        ]

        error_msg_lower = failure.error_message.lower()
        for indicator in llm_mistake_indicators:
            if indicator in error_msg_lower:
                # Check if error is in test file
                if failure.test_file in failure.full_output:
                    return True

        # Assertion errors might be real bugs or test bugs
        # Need context to determine - default to False (real bug)
        if failure.is_assertion_error:
            # If assertion is about test setup/mocking, it's an LLM mistake
            setup_indicators = ["mock", "patch", "fixture", "setup"]
            for indicator in setup_indicators:
                if indicator in error_msg_lower:
                    return True
            return False  # Assume real bug

        return False

    def generate_failure_report(self, failures: List[TestFailure]) -> str:
        """Generate a human-readable failure report."""
        report = []
        report.append("=" * 80)
        report.append("PYTEST FAILURE ANALYSIS REPORT")
        report.append("=" * 80)
        report.append("")

        # Summary
        total_failures = len(failures)
        llm_mistakes = sum(1 for f in failures if f.is_llm_mistake)
        real_bugs = total_failures - llm_mistakes

        report.append(f"Total Failures: {total_failures}")
        report.append(f"LLM Mistakes (Auto-healable): {llm_mistakes}")
        report.append(f"Potential Real Bugs: {real_bugs}")
        report.append("")

        # Breakdown by error type
        error_types = {}
        for failure in failures:
            error_types[failure.error_type] = error_types.get(failure.error_type, 0) + 1

        report.append("Failures by Error Type:")
        for error_type, count in sorted(error_types.items(), key=lambda x: -x[1]):
            report.append(f"  {error_type}: {count}")
        report.append("")

        # Detailed failures
        report.append("=" * 80)
        report.append("DETAILED FAILURES")
        report.append("=" * 80)

        for i, failure in enumerate(failures, 1):
            report.append("")
            report.append(f"{i}. {failure.test_name}")
            report.append(f"   File: {failure.test_file}:{failure.test_line}")
            report.append(f"   Error: {failure.error_type}")
            report.append(f"   Message: {failure.error_message}")
            report.append(f"   LLM Mistake: {'YES ✓ (Auto-healable)' if failure.is_llm_mistake else 'NO (May be real bug)'}")

            if failure.assertion_details:
                report.append(f"   Assertion Details:")
                for key, value in failure.assertion_details.items():
                    report.append(f"     {key}: {value}")

        report.append("")
        report.append("=" * 80)

        return "\n".join(report)


def main():
    """Test the pytest failure parser."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python pytest_failure_parser.py <pytest_output_file>")
        sys.exit(1)

    output_file = pathlib.Path(sys.argv[1])
    if not output_file.exists():
        print(f"Error: File not found: {output_file}")
        sys.exit(1)

    output = output_file.read_text(encoding="utf-8")

    parser = PytestFailureParser()
    failures = parser.parse_pytest_output(output)

    print(parser.generate_failure_report(failures))

    # Print healable failures
    healable = [f for f in failures if f.is_llm_mistake]
    print(f"\n🔧 Auto-healable failures: {len(healable)}")
    for failure in healable:
        print(f"  - {failure.test_name}")


if __name__ == "__main__":
    main()
