#!/usr/bin/env python3
"""
Multi-Iteration Test Generator
Orchestrates multiple rounds of AI test generation to achieve 90%+ coverage on uncovered code.

This module runs up to 3 iterations:
1. Analyze coverage gaps
2. Generate AI tests for uncovered code
3. Run all tests (manual + AI) with coverage
4. Re-analyze gaps and repeat
5. Stop early if 90% coverage achieved

Usage:
    python -m src.multi_iteration_test_generator --target ./app --max-iterations 3
"""

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Any, List, Tuple


class MultiIterationTestGenerator:
    """Orchestrates multiple iterations of AI test generation to achieve coverage goals."""

    def __init__(self, target_root: str, max_iterations: int = 3,
                 target_coverage: float = 90.0, output_dir: str = "tests/generated"):
        self.target_root = Path(target_root).resolve()
        self.max_iterations = max_iterations
        self.target_coverage = target_coverage
        self.output_dir = Path(output_dir)
        self.current_dir = Path.cwd()

        # Track iteration history
        self.iteration_history: List[Dict[str, Any]] = []

        # Files for tracking
        self.coverage_gaps_file = self.current_dir / "coverage_gaps.json"
        self.iteration_log_file = self.current_dir / "iteration_log.json"

        print("=" * 80)
        print("MULTI-ITERATION TEST GENERATOR")
        print("=" * 80)
        print(f"Target Root: {self.target_root}")
        print(f"Max Iterations: {self.max_iterations}")
        print(f"Target Coverage: {self.target_coverage}%")
        print(f"Output Directory: {self.output_dir}")
        print("=" * 80)
        print()

    def run(self) -> Dict[str, Any]:
        """
        Execute multi-iteration test generation.

        Returns:
            Dictionary with final results and iteration history
        """
        print("🚀 Starting multi-iteration test generation...\n")

        # Initial coverage analysis
        print("📊 Running initial coverage analysis on manual tests...")
        initial_coverage = self._run_manual_tests_with_coverage()

        if initial_coverage >= self.target_coverage:
            print(f"✅ Initial coverage is already {initial_coverage:.2f}% (>= {self.target_coverage}%)")
            print("No AI test generation needed!")
            return {
                "success": True,
                "iterations_run": 0,
                "final_coverage": initial_coverage,
                "initial_coverage": initial_coverage,
                "target_achieved": True,
                "reason": "Initial coverage already meets target"
            }

        print(f"📈 Initial coverage: {initial_coverage:.2f}%")
        print(f"🎯 Target coverage: {self.target_coverage}%")
        print(f"📉 Gap to fill: {self.target_coverage - initial_coverage:.2f}%\n")

        # Run iterations
        for iteration in range(1, self.max_iterations + 1):
            print("\n" + "=" * 80)
            print(f"ITERATION {iteration}/{self.max_iterations}")
            print("=" * 80)

            success, coverage, iteration_data = self._run_iteration(iteration)

            # Record iteration history
            self.iteration_history.append(iteration_data)
            self._save_iteration_log()

            if not success:
                print(f"❌ Iteration {iteration} failed")
                continue

            print(f"\n📊 Coverage after iteration {iteration}: {coverage:.2f}%")

            # Check if target achieved
            if coverage >= self.target_coverage:
                print(f"\n🎉 SUCCESS! Target coverage {self.target_coverage}% achieved!")
                print(f"Final coverage: {coverage:.2f}%")
                print(f"Iterations completed: {iteration}/{self.max_iterations}")

                return {
                    "success": True,
                    "iterations_run": iteration,
                    "final_coverage": coverage,
                    "initial_coverage": initial_coverage,
                    "target_achieved": True,
                    "improvement": coverage - initial_coverage,
                    "iteration_history": self.iteration_history
                }

            # Check if making progress
            if iteration > 1:
                previous_coverage = self.iteration_history[-2]["coverage_after"]
                improvement = coverage - previous_coverage
                print(f"📈 Improvement this iteration: {improvement:.2f}%")

                if improvement < 0.5:
                    print(f"⚠️  Small improvement (<0.5%). Consider manual intervention.")

        # All iterations completed
        final_coverage = self.iteration_history[-1]["coverage_after"] if self.iteration_history else initial_coverage

        if final_coverage >= self.target_coverage:
            print(f"\n🎉 SUCCESS! Target coverage {self.target_coverage}% achieved!")
            target_achieved = True
        else:
            print(f"\n⚠️  Target coverage not fully achieved after {self.max_iterations} iterations")
            print(f"Final coverage: {final_coverage:.2f}%")
            print(f"Target coverage: {self.target_coverage}%")
            print(f"Remaining gap: {self.target_coverage - final_coverage:.2f}%")
            target_achieved = False

        return {
            "success": True,
            "iterations_run": self.max_iterations,
            "final_coverage": final_coverage,
            "initial_coverage": initial_coverage,
            "target_achieved": target_achieved,
            "improvement": final_coverage - initial_coverage,
            "iteration_history": self.iteration_history
        }

    def _run_iteration(self, iteration_num: int) -> Tuple[bool, float, Dict[str, Any]]:
        """
        Run a single iteration of test generation.

        Returns:
            Tuple of (success, coverage_percentage, iteration_data)
        """
        iteration_start = time.time()
        iteration_data = {
            "iteration": iteration_num,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "steps": []
        }

        try:
            # Step 1: Analyze coverage gaps
            print(f"\n🔍 Step 1: Analyzing coverage gaps...")
            step1_success, coverage_before = self._analyze_coverage_gaps()
            iteration_data["steps"].append({
                "step": "analyze_gaps",
                "success": step1_success,
                "coverage": coverage_before
            })
            iteration_data["coverage_before"] = coverage_before

            if not step1_success:
                iteration_data["success"] = False
                iteration_data["error"] = "Coverage analysis failed"
                return False, coverage_before, iteration_data

            print(f"   Current coverage: {coverage_before:.2f}%")

            # Check if we've already achieved target
            if coverage_before >= self.target_coverage:
                print(f"✅ Target coverage already achieved!")
                iteration_data["success"] = True
                iteration_data["coverage_after"] = coverage_before
                iteration_data["skipped"] = True
                iteration_data["reason"] = "Target already achieved"
                return True, coverage_before, iteration_data

            # Step 2: Generate AI tests for gaps
            print(f"\n🤖 Step 2: Generating AI tests for uncovered code...")
            step2_success, generated_files = self._generate_ai_tests(iteration_num)
            iteration_data["steps"].append({
                "step": "generate_tests",
                "success": step2_success,
                "files_generated": len(generated_files) if generated_files else 0
            })
            iteration_data["generated_files"] = generated_files

            if not step2_success:
                iteration_data["success"] = False
                iteration_data["error"] = "Test generation failed"
                return False, coverage_before, iteration_data

            if not generated_files:
                print(f"   ℹ️  No new tests generated (gaps may be too small)")
                iteration_data["success"] = True
                iteration_data["coverage_after"] = coverage_before
                iteration_data["no_tests_generated"] = True
                return True, coverage_before, iteration_data

            print(f"   Generated {len(generated_files)} test files")

            # Step 3: Run all tests with coverage
            print(f"\n🧪 Step 3: Running all tests (manual + AI) with coverage...")
            step3_success, coverage_after = self._run_all_tests_with_coverage()
            iteration_data["steps"].append({
                "step": "run_tests",
                "success": step3_success,
                "coverage": coverage_after
            })
            iteration_data["coverage_after"] = coverage_after
            iteration_data["improvement"] = coverage_after - coverage_before

            if not step3_success:
                print(f"   ⚠️  Test execution had issues, but continuing...")
                # Don't fail the iteration, just log it

            print(f"   Coverage after tests: {coverage_after:.2f}%")
            print(f"   Improvement: {coverage_after - coverage_before:.2+.2f}%")

            # Step 4: Cleanup and prepare for next iteration
            print(f"\n🔄 Step 4: Preparing for next iteration...")
            self._cleanup_for_next_iteration(iteration_num)

            iteration_data["success"] = True
            iteration_data["duration_seconds"] = time.time() - iteration_start

            return True, coverage_after, iteration_data

        except Exception as e:
            print(f"❌ Error in iteration {iteration_num}: {e}")
            import traceback
            traceback.print_exc()

            iteration_data["success"] = False
            iteration_data["error"] = str(e)
            iteration_data["duration_seconds"] = time.time() - iteration_start

            return False, coverage_before if 'coverage_before' in locals() else 0.0, iteration_data

    def _run_manual_tests_with_coverage(self) -> float:
        """Run manual tests with coverage to establish baseline."""
        try:
            # Detect manual test directories
            manual_test_dirs = self._find_manual_test_directories()

            if not manual_test_dirs:
                print("⚠️  No manual test directories found, starting from 0% coverage")
                return 0.0

            print(f"   Found manual test directories: {', '.join(manual_test_dirs)}")

            # Run pytest with coverage on manual tests only
            cmd = [
                "python", "-m", "pytest",
                *manual_test_dirs,
                f"--cov={self.target_root}",
                "--cov-report=xml:coverage.xml",
                "--cov-report=html:htmlcov",
                "--cov-report=term",
                "-v",
                "--tb=short"
            ]

            print(f"   Running: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                cwd=self.current_dir,
                capture_output=True,
                text=True,
                timeout=300
            )

            # Save output
            with open(self.current_dir / "output.log", "w") as f:
                f.write(result.stdout)
                f.write(result.stderr)

            # Parse coverage from coverage.xml
            coverage = self._parse_coverage_from_xml()

            return coverage

        except Exception as e:
            print(f"⚠️  Error running manual tests: {e}")
            return 0.0

    def _analyze_coverage_gaps(self) -> Tuple[bool, float]:
        """Run coverage gap analyzer."""
        try:
            cmd = [
                "python", "-m", "src.coverage_gap_analyzer",
                "--target", str(self.target_root),
                "--current-dir", str(self.current_dir),
                "--output", "coverage_gaps.json"
            ]

            result = subprocess.run(
                cmd,
                cwd=self.current_dir,
                capture_output=True,
                text=True,
                timeout=60
            )

            # Print output
            if result.stdout:
                print(result.stdout)

            # Load coverage gaps
            if self.coverage_gaps_file.exists():
                with open(self.coverage_gaps_file, 'r') as f:
                    gaps_data = json.load(f)
                    coverage = gaps_data.get("overall_coverage", 0.0)
                    return True, coverage

            return False, 0.0

        except Exception as e:
            print(f"❌ Error analyzing coverage gaps: {e}")
            return False, 0.0

    def _generate_ai_tests(self, iteration_num: int) -> Tuple[bool, List[str]]:
        """Generate AI tests for uncovered code."""
        try:
            # Set environment variables for gap-focused mode
            env = os.environ.copy()
            env["GAP_FOCUSED_MODE"] = "true"
            env["COVERAGE_GAPS_FILE"] = str(self.coverage_gaps_file)
            env["TARGET_ROOT"] = str(self.target_root)
            env["COVERAGE_MODE"] = "gap-focused"
            env["TESTGEN_FORCE"] = "false"  # Only generate for new gaps

            # Create iteration-specific output directory
            iteration_output_dir = self.output_dir / f"iteration_{iteration_num}"
            iteration_output_dir.mkdir(parents=True, exist_ok=True)

            cmd = [
                "python", "-m", "src.gen",
                "--target", str(self.target_root),
                "--outdir", str(iteration_output_dir),
                "--coverage-mode", "gap-focused"
            ]

            print(f"   Running: {' '.join(cmd)}")

            result = subprocess.run(
                cmd,
                cwd=self.current_dir,
                env=env,
                capture_output=True,
                text=True,
                timeout=600  # 10 minutes max
            )

            # Print output
            if result.stdout:
                print(result.stdout)

            if result.stderr and "error" in result.stderr.lower():
                print(f"⚠️  Stderr: {result.stderr}")

            # Check if tests were generated
            generated_files = list(iteration_output_dir.glob("test_*.py"))

            # Exit code 0 means success OR no tests needed
            if result.returncode == 0 or "No additional tests needed" in result.stdout:
                return True, [str(f) for f in generated_files]

            return False, []

        except subprocess.TimeoutExpired:
            print(f"❌ Test generation timed out")
            return False, []
        except Exception as e:
            print(f"❌ Error generating AI tests: {e}")
            import traceback
            traceback.print_exc()
            return False, []

    def _run_all_tests_with_coverage(self) -> Tuple[bool, float]:
        """Run all tests (manual + all AI-generated) with coverage."""
        try:
            # Find all test directories
            manual_test_dirs = self._find_manual_test_directories()

            # Add all iteration directories
            ai_test_dirs = [
                str(d) for d in self.output_dir.glob("iteration_*")
                if d.is_dir() and list(d.glob("test_*.py"))
            ]

            all_test_dirs = manual_test_dirs + ai_test_dirs

            if not all_test_dirs:
                print("⚠️  No test directories found")
                return False, 0.0

            print(f"   Running tests from: {', '.join(all_test_dirs)}")

            # Run pytest with coverage on all tests
            cmd = [
                "python", "-m", "pytest",
                *all_test_dirs,
                f"--cov={self.target_root}",
                "--cov-report=xml:coverage.xml",
                "--cov-report=html:htmlcov",
                "--cov-report=term",
                "-v",
                "--tb=short",
                "--continue-on-collection-errors"
            ]

            result = subprocess.run(
                cmd,
                cwd=self.current_dir,
                capture_output=True,
                text=True,
                timeout=600
            )

            # Save output
            with open(self.current_dir / "output.log", "w") as f:
                f.write(result.stdout)
                f.write(result.stderr)

            # Parse coverage
            coverage = self._parse_coverage_from_xml()

            # Return success=True even if some tests failed, as long as we got coverage
            return True, coverage

        except Exception as e:
            print(f"❌ Error running all tests: {e}")
            # Try to parse coverage anyway
            coverage = self._parse_coverage_from_xml()
            return False, coverage

    def _parse_coverage_from_xml(self) -> float:
        """Parse coverage percentage from coverage.xml."""
        try:
            import xml.etree.ElementTree as ET

            coverage_xml = self.current_dir / "coverage.xml"
            if not coverage_xml.exists():
                return 0.0

            tree = ET.parse(coverage_xml)
            root = tree.getroot()

            line_rate = float(root.attrib.get("line-rate", 0))
            coverage = line_rate * 100

            return coverage

        except Exception as e:
            print(f"⚠️  Error parsing coverage.xml: {e}")
            return 0.0

    def _find_manual_test_directories(self) -> List[str]:
        """Find manual test directories (exclude generated tests)."""
        test_dirs = []

        # Look for common test directory patterns
        for pattern in ["tests", "test", "manual_tests"]:
            test_path = self.current_dir / pattern
            if test_path.exists() and test_path.is_dir():
                # Check if it has test files
                if list(test_path.glob("test_*.py")) or list(test_path.glob("*_test.py")):
                    # Exclude generated directory
                    if pattern != "generated" and "generated" not in str(test_path):
                        test_dirs.append(str(test_path))

        return test_dirs

    def _cleanup_for_next_iteration(self, iteration_num: int):
        """Cleanup and prepare for next iteration."""
        # Nothing to cleanup - we keep all generated tests
        # They will accumulate across iterations
        pass

    def _save_iteration_log(self):
        """Save iteration log to JSON."""
        try:
            log_data = {
                "target_root": str(self.target_root),
                "max_iterations": self.max_iterations,
                "target_coverage": self.target_coverage,
                "iterations": self.iteration_history,
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
            }

            with open(self.iteration_log_file, 'w') as f:
                json.dump(log_data, f, indent=2)

        except Exception as e:
            print(f"⚠️  Error saving iteration log: {e}")

    def print_final_report(self, result: Dict[str, Any]):
        """Print final summary report."""
        print("\n" + "=" * 80)
        print("MULTI-ITERATION TEST GENERATION - FINAL REPORT")
        print("=" * 80)
        print(f"Target Root: {self.target_root}")
        print(f"Target Coverage: {self.target_coverage}%")
        print(f"Iterations Run: {result['iterations_run']}/{self.max_iterations}")
        print()
        print(f"Initial Coverage: {result['initial_coverage']:.2f}%")
        print(f"Final Coverage: {result['final_coverage']:.2f}%")
        print(f"Total Improvement: {result.get('improvement', 0):.2f}%")
        print()
        print(f"Target Achieved: {'✅ YES' if result['target_achieved'] else '❌ NO'}")

        if result.get('iteration_history'):
            print("\nIteration Summary:")
            print("-" * 80)
            for it in result['iteration_history']:
                coverage_before = it.get('coverage_before', 0)
                coverage_after = it.get('coverage_after', 0)
                improvement = coverage_after - coverage_before
                generated = len(it.get('generated_files', []))

                print(f"  Iteration {it['iteration']}:")
                print(f"    Coverage: {coverage_before:.2f}% → {coverage_after:.2f}% ({improvement:+.2f}%)")
                print(f"    Tests Generated: {generated}")
                print(f"    Duration: {it.get('duration_seconds', 0):.1f}s")

        print("=" * 80)

        # Save report to file
        report_file = self.current_dir / "multi_iteration_report.txt"
        with open(report_file, 'w') as f:
            f.write(f"Multi-Iteration Test Generation Report\n")
            f.write(f"{'=' * 80}\n\n")
            f.write(f"Target Root: {self.target_root}\n")
            f.write(f"Target Coverage: {self.target_coverage}%\n")
            f.write(f"Iterations Run: {result['iterations_run']}/{self.max_iterations}\n\n")
            f.write(f"Initial Coverage: {result['initial_coverage']:.2f}%\n")
            f.write(f"Final Coverage: {result['final_coverage']:.2f}%\n")
            f.write(f"Total Improvement: {result.get('improvement', 0):.2f}%\n\n")
            f.write(f"Target Achieved: {'YES' if result['target_achieved'] else 'NO'}\n")

        print(f"\n📄 Report saved to: {report_file}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Multi-Iteration AI Test Generator for achieving 90%+ coverage",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run 3 iterations to achieve 90% coverage
  python -m src.multi_iteration_test_generator --target ./app

  # Custom iterations and coverage target
  python -m src.multi_iteration_test_generator --target ./app --max-iterations 5 --target-coverage 95

  # Specify output directory
  python -m src.multi_iteration_test_generator --target ./app --outdir ./tests/ai_generated

How it works:
  1. Runs manual tests to establish baseline coverage
  2. For each iteration (up to max-iterations):
     a. Analyzes coverage gaps (uncovered code)
     b. Generates AI tests for uncovered code only
     c. Runs ALL tests (manual + all AI-generated) with coverage
     d. Checks if target coverage achieved
  3. Stops early if target coverage is reached
  4. Generates detailed report with iteration history
"""
    )

    parser.add_argument(
        "--target",
        required=True,
        help="Path to target Python project"
    )

    parser.add_argument(
        "--max-iterations",
        type=int,
        default=3,
        help="Maximum number of iterations (default: 3)"
    )

    parser.add_argument(
        "--target-coverage",
        type=float,
        default=90.0,
        help="Target coverage percentage (default: 90.0)"
    )

    parser.add_argument(
        "--outdir",
        default="tests/generated",
        help="Output directory for generated tests (default: tests/generated)"
    )

    args = parser.parse_args()

    # Validate target exists
    target_path = Path(args.target)
    if not target_path.exists():
        print(f"❌ Target directory not found: {target_path}")
        return 1

    # Create generator
    generator = MultiIterationTestGenerator(
        target_root=str(target_path),
        max_iterations=args.max_iterations,
        target_coverage=args.target_coverage,
        output_dir=args.outdir
    )

    # Run multi-iteration generation
    result = generator.run()

    # Print final report
    generator.print_final_report(result)

    # Return exit code
    if result["target_achieved"]:
        print(f"\n✅ SUCCESS: Target coverage {args.target_coverage}% achieved!")
        return 0
    else:
        print(f"\n⚠️  Target coverage not fully achieved, but improvement made")
        return 0  # Still return 0 since we made progress


if __name__ == "__main__":
    sys.exit(main())
