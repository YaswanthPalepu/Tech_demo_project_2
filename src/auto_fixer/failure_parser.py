"""
Test Failure Parser

Parses pytest JSON output and extracts structured failure information.
"""

import json
import subprocess
from dataclasses import dataclass
from typing import List, Optional, Dict, Any
import re


@dataclass
class TestFailure:
    """Structured representation of a test failure."""
    test_file: str
    test_name: str
    exception_type: str
    error_message: str
    traceback: str
    line_number: Optional[int] = None
    full_test_node: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "test_file": self.test_file,
            "test_name": self.test_name,
            "exception_type": self.exception_type,
            "error_message": self.error_message,
            "traceback": self.traceback,
            "line_number": self.line_number,
            "full_test_node": self.full_test_node
        }


class FailureParser:
    """Parses pytest output and extracts test failures."""

    def __init__(self, test_directory: str = "tests", verbose: bool = True):
        self.test_directory = test_directory
        self.verbose = verbose

    def run_pytest_json(self, extra_args: List[str] = None) -> Dict[str, Any]:
        """
        Run pytest with JSON output.

        Args:
            extra_args: Additional pytest arguments

        Returns:
            JSON output from pytest or parsed text output
        """
        args = extra_args or []

        # CRITICAL: Clean stale data before running pytest
        import os
        import shutil

        # Remove old pytest report
        report_file = "pytest_report.json"
        if os.path.exists(report_file):
            try:
                os.remove(report_file)
                if self.verbose:
                    print(f"  🗑️  Removed old {report_file}")
            except OSError as e:
                print(f"  ⚠️  Warning: Could not remove old {report_file}: {e}")

        # Remove pytest cache to prevent stale results
        cache_dir = ".pytest_cache"
        if os.path.exists(cache_dir):
            try:
                shutil.rmtree(cache_dir)
                if self.verbose:
                    print(f"  🗑️  Cleared pytest cache")
            except OSError as e:
                if self.verbose:
                    print(f"  ⚠️  Warning: Could not clear pytest cache: {e}")

        # Run pytest with text output and parse it
        # Note: --json-report is not available, so we use text parsing
        cmd = [
            "pytest",
            self.test_directory,
            "--tb=long",
            "-v"
        ] + args

        if self.verbose:
            print(f"  🧪 Running pytest on {self.test_directory}...")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120  # 2 minute overall timeout
            )

            if self.verbose:
                print(f"  ✓ Pytest completed (exit code: {result.returncode})")
        except subprocess.TimeoutExpired:
            print("⚠️  Pytest timed out after 120 seconds - tests may be hanging")
            print("   Try running pytest manually to debug: pytest", self.test_directory, "-v")
            return {"tests": [], "summary": {"total": 0, "passed": 0, "failed": 0}}

        return self._parse_text_output(result.stdout)

    def _parse_text_output(self, output: str) -> Dict[str, Any]:
        """
        Parse pytest text output to extract failures.

        Args:
            output: Pytest stdout

        Returns:
            Dictionary compatible with JSON report format
        """
        tests = []
        lines = output.split('\n')

        # Parse test failures - traceback appears BEFORE the FAILED line
        # Format:
        # ______________________ test_name _______________________
        # <traceback content>
        # <blank line(s)>
        # FAILED tests/test_foo.py::test_name - ErrorType: message

        i = 0
        while i < len(lines):
            line = lines[i]

            # Look for test separator lines (start of failure section)
            if re.match(r'^_{3,}.*_{3,}$', line):
                # Extract test name from separator
                test_name_match = re.search(r'_{3,}\s*(.+?)\s*_{3,}', line)

                # Collect all lines until we hit FAILED or next separator
                traceback_lines = []
                j = i + 1
                nodeid = None
                error_preview = ""

                while j < len(lines):
                    current_line = lines[j]

                    # Check if this is the FAILED line for this test
                    if current_line.startswith('FAILED '):
                        # Extract nodeid and error
                        parts = current_line.split(' - ', 1)
                        nodeid = parts[0].replace('FAILED ', '').strip()
                        error_preview = parts[1] if len(parts) > 1 else ""
                        break

                    # Check if we hit the next test's separator or end section
                    if re.match(r'^_{3,}.*_{3,}$', current_line) or current_line.startswith('==='):
                        # This means we're at the next section without finding FAILED
                        # (might be a different kind of output)
                        break

                    # Collect traceback content
                    traceback_lines.append(current_line)
                    j += 1

                # Create test entry if we have traceback content
                if traceback_lines:
                    traceback_text = '\n'.join(traceback_lines).strip()

                    # If we don't have nodeid from FAILED line, extract from traceback
                    if not nodeid:
                        test_name = test_name_match.group(1).strip() if test_name_match else "unknown_test"
                        nodeid = self._extract_nodeid_from_traceback(traceback_text, test_name)

                    # Condense traceback to only relevant parts to avoid huge prompts
                    condensed_traceback = self._condense_traceback(traceback_text, error_preview)

                    tests.append({
                        "nodeid": nodeid,
                        "outcome": "failed",
                        "call": {
                            "longrepr": condensed_traceback
                        }
                    })

                # Move to next section
                i = j if j < len(lines) else i + 1
                continue

            i += 1

        return {
            "tests": tests,
            "summary": {"failed": len(tests)}
        }

    def _extract_nodeid_from_traceback(self, traceback_text: str, test_name: str) -> str:
        """
        Extract nodeid (test file path + test name) from traceback text.

        Looks for patterns like:
        - tests/test_file.py:123: in test_name
        - tests/generated/test_file.py:456:

        Args:
            traceback_text: The traceback content
            test_name: The test function name from the separator

        Returns:
            Constructed nodeid like "tests/test_file.py::test_name"
        """
        # Look for file path pattern in traceback
        # Pattern: tests/some/path.py:line_number:
        file_match = re.search(r'(tests/[^\s:]+\.py):\d+:', traceback_text)

        if file_match:
            file_path = file_match.group(1)
            return f"{file_path}::{test_name}"

        # Fallback: return test name only
        return f"unknown::{test_name}"

    def _condense_traceback(self, traceback_text: str, error_preview: str) -> str:
        """
        Condense traceback to only the most relevant parts to avoid huge prompts.

        Focuses on:
        - Test code and application code (not library internals)
        - The actual error/assertion message
        - File/line where error occurred

        Args:
            traceback_text: Full traceback text
            error_preview: Error message from FAILED line

        Returns:
            Condensed traceback with only essential information (max ~500 chars)
        """
        lines = traceback_text.split('\n')

        # Collect error lines (start with 'E   ')
        error_lines = []

        # Collect relevant stack frames (from test/src code, not libraries)
        relevant_frames = []

        i = 0
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            # Capture error/assertion output lines
            if stripped.startswith('E   '):
                error_lines.append(line)
                i += 1
                continue

            # Capture stack frames from test/src code (ignore venv/site-packages)
            if re.match(r'^[^\s]+\.py:\d+:', stripped):
                # Skip library frames (venv, site-packages, lib/)
                if not any(skip in line for skip in ['venv/', 'site-packages/', '/lib/', '\\lib\\']):
                    # Add frame header
                    relevant_frames.append(line)
                    # Add next 1-2 lines of context (code)
                    for j in range(i + 1, min(i + 3, len(lines))):
                        if lines[j].strip() and not lines[j].strip().startswith(('E   ', '>')):
                            relevant_frames.append(lines[j])
                        else:
                            break

            i += 1

        # Build condensed output
        condensed = []

        # Add error type from FAILED line
        if error_preview:
            condensed.append(f"{error_preview}")

        # Add relevant stack frames (keep last 2-3 frames, max 8 lines)
        if relevant_frames:
            condensed.append("")
            condensed.extend(relevant_frames[-8:])

        # Add error/assertion details (last 8 lines to avoid huge diffs)
        if error_lines:
            condensed.append("")
            condensed.extend(error_lines[-8:])

        # Fallback: if no structured content found, use last 10 lines
        if not condensed or len(condensed) < 2:
            condensed = lines[-10:]

        result = '\n'.join(condensed).strip()

        # Safety limit: max 500 chars to keep prompts reasonable
        if len(result) > 500:
            # Keep the error message and last part of traceback
            result = result[-500:]
            result = "...\n" + result

        return result

    def _parse_legacy_output(self, stdout: str, stderr: str) -> Dict[str, Any]:
        """Fallback parser for when JSON report is not available."""
        return {
            "tests": [],
            "summary": {"failed": 0, "passed": 0},
            "stdout": stdout,
            "stderr": stderr
        }

    def parse_failures(self, json_output: Dict[str, Any]) -> List[TestFailure]:
        """
        Parse test failures from pytest JSON output.

        Args:
            json_output: JSON output from pytest

        Returns:
            List of TestFailure objects
        """
        failures = []

        # Handle different JSON report formats
        tests = json_output.get("tests", [])

        for test in tests:
            # Only process failed tests
            outcome = test.get("outcome", "")
            if outcome not in ["failed", "error"]:
                continue

            # Extract test information
            nodeid = test.get("nodeid", "")
            test_file, test_name = self._parse_nodeid(nodeid)

            # Extract failure information
            call = test.get("call", {})
            longrepr = call.get("longrepr", "")

            # Parse exception type and message
            exception_type, error_message = self._parse_exception(longrepr)

            # Extract line number from traceback
            line_number = self._extract_line_number(longrepr, test_file)

            # Get full traceback
            traceback = str(longrepr)

            failure = TestFailure(
                test_file=test_file,
                test_name=test_name,
                exception_type=exception_type,
                error_message=error_message,
                traceback=traceback,
                line_number=line_number,
                full_test_node=nodeid
            )

            failures.append(failure)

        return failures

    def _parse_nodeid(self, nodeid: str) -> tuple[str, str]:
        """
        Parse pytest nodeid to extract file and test name.

        Example: tests/test_foo.py::TestClass::test_method
        Returns: ("tests/test_foo.py", "test_method")
        """
        parts = nodeid.split("::")
        test_file = parts[0] if parts else ""
        test_name = parts[-1] if len(parts) > 1 else ""
        return test_file, test_name

    def _parse_exception(self, longrepr: str) -> tuple[str, str]:
        """
        Parse exception type and message from longrepr.

        Args:
            longrepr: Long representation of the error

        Returns:
            Tuple of (exception_type, error_message)
        """
        # Try to find exception type and message
        # Format is usually: "ExceptionType: message"
        lines = str(longrepr).split('\n')

        for line in reversed(lines):
            line = line.strip()
            if ':' in line and not line.startswith(('>', 'E', ' ')):
                parts = line.split(':', 1)
                if len(parts) == 2:
                    exception_type = parts[0].strip()
                    error_message = parts[1].strip()
                    return exception_type, error_message

        # Try alternative format: "E   AssertionError: message"
        for line in reversed(lines):
            if line.strip().startswith('E   '):
                content = line.strip()[4:]  # Remove "E   "
                if ':' in content:
                    parts = content.split(':', 1)
                    if len(parts) == 2:
                        exception_type = parts[0].strip()
                        error_message = parts[1].strip()
                        return exception_type, error_message

        # Fallback: return full last line
        last_line = lines[-1].strip() if lines else ""
        return "Unknown", last_line

    def _extract_line_number(self, longrepr: str, test_file: str) -> Optional[int]:
        """
        Extract the line number where the failure occurred.

        Args:
            longrepr: Long representation of the error
            test_file: Path to the test file

        Returns:
            Line number or None
        """
        # Look for patterns like "test_file.py:123:"
        pattern = rf"{re.escape(test_file)}:(\d+):"
        match = re.search(pattern, str(longrepr))

        if match:
            return int(match.group(1))

        # Alternative pattern: "line 123"
        pattern = r"line (\d+)"
        match = re.search(pattern, str(longrepr), re.IGNORECASE)

        if match:
            return int(match.group(1))

        return None

    def run_and_parse(self, extra_args: List[str] = None) -> List[TestFailure]:
        """
        Run pytest and parse failures in one step.

        Args:
            extra_args: Additional pytest arguments

        Returns:
            List of TestFailure objects
        """
        json_output = self.run_pytest_json(extra_args)
        return self.parse_failures(json_output)
