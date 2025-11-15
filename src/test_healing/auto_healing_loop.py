#!/usr/bin/env python3
"""
Auto-Healing Loop - Orchestrates the self-healing test loop.

This module implements the complete auto-healing workflow:
1. Run pytest on generated tests
2. Parse failures
3. Extract error details
4. Send to LLM for correction
5. Replace failing tests
6. Re-run pytest
7. Repeat until tests pass or max iterations reached
"""

import json
import pathlib
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict

from .pytest_failure_parser import PytestFailureParser, TestFailure
from .test_ast_extractor import TestASTExtractor
from .test_healer import TestHealer


@dataclass
class HealingIteration:
    """Represents one iteration of the healing loop."""
    iteration: int
    total_failures: int
    healable_failures: int
    healed_tests: List[str]
    failed_to_heal: List[str]
    pytest_output: str
    duration_seconds: float


@dataclass
class HealingSession:
    """Represents a complete healing session."""
    start_time: float
    end_time: Optional[float] = None
    total_iterations: int = 0
    max_iterations: int = 3
    initial_failures: int = 0
    final_failures: int = 0
    tests_healed: int = 0
    tests_failed_to_heal: int = 0
    success: bool = False
    iterations: List[HealingIteration] = None

    def __post_init__(self):
        if self.iterations is None:
            self.iterations = []


class AutoHealingLoop:
    """Orchestrates the auto-healing test loop."""

    def __init__(self,
                 target_root: str,
                 generated_tests_dir: str = "tests/generated",
                 max_iterations: int = 3,
                 use_full_source: bool = False,
                 pytest_args: Optional[List[str]] = None):
        """
        Initialize the auto-healing loop.

        Args:
            target_root: Root directory of target project
            generated_tests_dir: Directory with generated tests
            max_iterations: Maximum healing iterations
            use_full_source: Whether to use full source code or AST snippets
            pytest_args: Additional pytest arguments
        """
        self.target_root = pathlib.Path(target_root)
        self.generated_tests_dir = pathlib.Path(generated_tests_dir)
        self.max_iterations = max_iterations
        self.use_full_source = use_full_source
        self.pytest_args = pytest_args or []

        # Initialize components
        self.failure_parser = PytestFailureParser(str(generated_tests_dir))
        self.test_extractor = TestASTExtractor(generated_tests_dir)
        self.healer = TestHealer(self.target_root, generated_tests_dir, use_full_source)

        # Session tracking
        self.current_session: Optional[HealingSession] = None

    def run_healing_loop(self) -> HealingSession:
        """
        Run the complete auto-healing loop.

        Returns:
            HealingSession with complete results
        """
        print("=" * 80)
        print("🔧 AUTO-HEALING TEST LOOP STARTED")
        print("=" * 80)
        print(f"Target: {self.target_root}")
        print(f"Tests: {self.generated_tests_dir}")
        print(f"Max Iterations: {self.max_iterations}")
        print(f"Source Context: {'Full' if self.use_full_source else 'AST snippets'}")
        print("=" * 80)
        print()

        # Initialize session
        session = HealingSession(
            start_time=time.time(),
            max_iterations=self.max_iterations
        )
        self.current_session = session

        # Initial test run
        print("📊 Running initial test suite...")
        initial_output = self._run_pytest()
        initial_failures = self.failure_parser.parse_pytest_output(initial_output)

        session.initial_failures = len(initial_failures)
        print(f"Initial failures: {session.initial_failures}")

        if session.initial_failures == 0:
            print("✅ All tests passing! No healing needed.")
            session.success = True
            session.end_time = time.time()
            return session

        # Filter to only healable failures (LLM mistakes)
        healable_failures = [f for f in initial_failures if f.is_llm_mistake]
        print(f"Healable failures (LLM mistakes): {len(healable_failures)}")
        print(f"Non-healable failures (potential bugs): {len(initial_failures) - len(healable_failures)}")

        if not healable_failures:
            print("\n⚠️  No healable failures found.")
            print("All failures may be due to actual bugs in source code, not test issues.")
            session.tests_failed_to_heal = len(initial_failures)
            session.final_failures = len(initial_failures)
            session.end_time = time.time()
            return session

        print("\n" + "=" * 80)
        print("🔄 Starting healing iterations...")
        print("=" * 80)

        # Healing loop
        current_failures = healable_failures
        for iteration in range(1, self.max_iterations + 1):
            print(f"\n{'=' * 80}")
            print(f"ITERATION {iteration}/{self.max_iterations}")
            print(f"{'=' * 80}")

            iteration_start = time.time()
            healed_tests = []
            failed_to_heal = []

            # Attempt to heal each failure
            for i, failure in enumerate(current_failures, 1):
                print(f"\n[{i}/{len(current_failures)}] Healing: {failure.test_name}")
                print(f"  Error: {failure.error_type}: {failure.error_message[:100]}")

                corrected_code = self.healer.heal_test(failure, max_attempts=3)

                if corrected_code:
                    # Replace the test with corrected version
                    success = self._replace_test(failure, corrected_code)
                    if success:
                        print(f"  ✅ Healed successfully")
                        healed_tests.append(failure.test_name)
                    else:
                        print(f"  ❌ Failed to replace test")
                        failed_to_heal.append(failure.test_name)
                else:
                    print(f"  ❌ Healing failed")
                    failed_to_heal.append(failure.test_name)

            # Record iteration
            iteration_duration = time.time() - iteration_start
            pytest_output = self._run_pytest() if healed_tests else ""

            session.iterations.append(HealingIteration(
                iteration=iteration,
                total_failures=len(current_failures),
                healable_failures=len(healable_failures),
                healed_tests=healed_tests,
                failed_to_heal=failed_to_heal,
                pytest_output=pytest_output,
                duration_seconds=iteration_duration
            ))

            session.tests_healed += len(healed_tests)
            session.tests_failed_to_heal = len(failed_to_heal)

            # Re-run tests to check if healing worked
            if healed_tests:
                print(f"\n🔍 Re-running tests after healing {len(healed_tests)} tests...")
                new_output = self._run_pytest()
                new_failures = self.failure_parser.parse_pytest_output(new_output)
                new_healable = [f for f in new_failures if f.is_llm_mistake]

                print(f"Remaining failures: {len(new_failures)} (healable: {len(new_healable)})")

                if not new_healable:
                    print("\n✅ All healable tests fixed!")
                    session.success = True
                    session.final_failures = len(new_failures)
                    break

                # Continue with new failures
                current_failures = new_healable
            else:
                print("\n❌ No tests were healed in this iteration")
                session.final_failures = len(current_failures)
                break

        # Session summary
        session.end_time = time.time()
        session.total_iterations = len(session.iterations)

        # Final test run
        print("\n" + "=" * 80)
        print("📊 Running final test suite...")
        print("=" * 80)
        final_output = self._run_pytest()
        final_failures = self.failure_parser.parse_pytest_output(final_output)
        session.final_failures = len(final_failures)

        # Determine overall success
        session.success = session.final_failures == 0 or (
            session.final_failures < session.initial_failures and
            all(not f.is_llm_mistake for f in final_failures)
        )

        self._print_session_summary(session)

        # Save session report
        self._save_session_report(session)

        return session

    def _run_pytest(self) -> str:
        """
        Run pytest on generated tests directory.

        Returns:
            Pytest output as string
        """
        cmd = [
            sys.executable, "-m", "pytest",
            str(self.generated_tests_dir),
            "-v",
            "--tb=long",
            "--no-header",
            "--color=no"
        ] + self.pytest_args

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )

            output = result.stdout + "\n" + result.stderr
            return output

        except subprocess.TimeoutExpired:
            print("⚠️  Pytest timed out after 5 minutes")
            return "TIMEOUT"
        except Exception as e:
            print(f"Error running pytest: {e}")
            return f"ERROR: {e}"

    def _replace_test(self, failure: TestFailure, corrected_code: str) -> bool:
        """
        Replace a failing test with corrected version.

        Args:
            failure: TestFailure object
            corrected_code: Corrected test code

        Returns:
            True if replacement successful
        """
        try:
            test_file = pathlib.Path(failure.test_file)

            if not test_file.exists():
                print(f"  Error: Test file not found: {test_file}")
                return False

            # Read current file
            current_content = test_file.read_text(encoding="utf-8")

            # Extract test info to find exact location
            test_info = self.test_extractor.extract_test_by_name(test_file, failure.test_name)

            if not test_info:
                print(f"  Error: Could not locate test {failure.test_name} in file")
                return False

            # Replace the test
            lines = current_content.splitlines(keepends=True)
            start_line = test_info["line_start"] - 1
            end_line = test_info["line_end"]

            # Build new content
            new_content = (
                "".join(lines[:start_line]) +
                corrected_code + "\n" +
                "".join(lines[end_line:])
            )

            # Write back
            test_file.write_text(new_content, encoding="utf-8")

            return True

        except Exception as e:
            print(f"  Error replacing test: {e}")
            return False

    def _print_session_summary(self, session: HealingSession):
        """Print comprehensive session summary."""
        duration = session.end_time - session.start_time if session.end_time else 0

        print("\n" + "=" * 80)
        print("📋 AUTO-HEALING SESSION SUMMARY")
        print("=" * 80)
        print(f"Status: {'✅ SUCCESS' if session.success else '⚠️  PARTIAL SUCCESS' if session.tests_healed > 0 else '❌ FAILED'}")
        print(f"Duration: {duration:.2f} seconds")
        print(f"Iterations: {session.total_iterations}/{session.max_iterations}")
        print()
        print(f"Initial Failures: {session.initial_failures}")
        print(f"Final Failures: {session.final_failures}")
        print(f"Tests Healed: {session.tests_healed}")
        print(f"Tests Failed to Heal: {session.tests_failed_to_heal}")
        print(f"Improvement: {session.initial_failures - session.final_failures} fewer failures")
        print()

        if session.iterations:
            print("Iteration Details:")
            print("-" * 80)
            for it in session.iterations:
                print(f"  Iteration {it.iteration}:")
                print(f"    Healed: {len(it.healed_tests)}")
                print(f"    Failed: {len(it.failed_to_heal)}")
                print(f"    Duration: {it.duration_seconds:.2f}s")

        print("=" * 80)

    def _save_session_report(self, session: HealingSession):
        """Save session report to JSON file."""
        report_file = self.generated_tests_dir / "healing_session_report.json"

        # Convert to serializable format
        report_data = {
            "start_time": session.start_time,
            "end_time": session.end_time,
            "duration_seconds": session.end_time - session.start_time if session.end_time else 0,
            "total_iterations": session.total_iterations,
            "max_iterations": session.max_iterations,
            "initial_failures": session.initial_failures,
            "final_failures": session.final_failures,
            "tests_healed": session.tests_healed,
            "tests_failed_to_heal": session.tests_failed_to_heal,
            "success": session.success,
            "iterations": [
                {
                    "iteration": it.iteration,
                    "total_failures": it.total_failures,
                    "healable_failures": it.healable_failures,
                    "healed_tests": it.healed_tests,
                    "failed_to_heal": it.failed_to_heal,
                    "duration_seconds": it.duration_seconds
                }
                for it in session.iterations
            ]
        }

        try:
            with open(report_file, 'w') as f:
                json.dump(report_data, f, indent=2)
            print(f"\n💾 Session report saved to: {report_file}")
        except Exception as e:
            print(f"\n⚠️  Could not save session report: {e}")


def main():
    """Main entry point for auto-healing loop."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Auto-healing loop for AI-generated tests",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage
  python -m src.test_healing.auto_healing_loop --target ./target

  # Custom settings
  python -m src.test_healing.auto_healing_loop --target ./app --max-iterations 5

  # Use full source code context
  python -m src.test_healing.auto_healing_loop --target ./app --full-source

  # Custom pytest args
  python -m src.test_healing.auto_healing_loop --target ./app --pytest-args "-k test_user"
"""
    )

    parser.add_argument(
        "--target",
        default="target",
        help="Target project root directory (default: target)"
    )

    parser.add_argument(
        "--tests-dir",
        default="tests/generated",
        help="Generated tests directory (default: tests/generated)"
    )

    parser.add_argument(
        "--max-iterations",
        type=int,
        default=3,
        help="Maximum healing iterations (default: 3)"
    )

    parser.add_argument(
        "--full-source",
        action="store_true",
        help="Use full source code instead of AST snippets"
    )

    parser.add_argument(
        "--pytest-args",
        nargs="+",
        default=[],
        help="Additional pytest arguments"
    )

    args = parser.parse_args()

    # Validate paths
    target_root = pathlib.Path(args.target)
    if not target_root.exists():
        print(f"Error: Target directory not found: {target_root}")
        sys.exit(1)

    tests_dir = pathlib.Path(args.tests_dir)
    if not tests_dir.exists():
        print(f"Error: Tests directory not found: {tests_dir}")
        print(f"Please generate tests first using: python -m src.gen --target {args.target}")
        sys.exit(1)

    # Run healing loop
    loop = AutoHealingLoop(
        target_root=str(target_root),
        generated_tests_dir=str(tests_dir),
        max_iterations=args.max_iterations,
        use_full_source=args.full_source,
        pytest_args=args.pytest_args
    )

    session = loop.run_healing_loop()

    # Exit code based on success
    sys.exit(0 if session.success else 1)


if __name__ == "__main__":
    main()
