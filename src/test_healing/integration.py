#!/usr/bin/env python3
"""
Integration module for auto-healing with test generation workflow.

This module provides seamless integration between test generation and auto-healing,
allowing the complete pipeline to run automatically.
"""

import pathlib
import sys
from typing import Any, Dict, List, Optional

from .auto_healing_loop import AutoHealingLoop, HealingSession


class TestGenerationWithHealing:
    """Combines test generation with auto-healing."""

    def __init__(self,
                 target_root: str,
                 output_dir: str = "tests/generated",
                 enable_healing: bool = True,
                 max_healing_iterations: int = 3,
                 use_full_source: bool = False):
        """
        Initialize test generation with healing.

        Args:
            target_root: Root directory of target project
            output_dir: Output directory for generated tests
            enable_healing: Whether to enable auto-healing
            max_healing_iterations: Maximum healing iterations
            use_full_source: Whether to use full source code for context
        """
        self.target_root = pathlib.Path(target_root)
        self.output_dir = pathlib.Path(output_dir)
        self.enable_healing = enable_healing
        self.max_healing_iterations = max_healing_iterations
        self.use_full_source = use_full_source

    def generate_and_heal(self,
                         force_regeneration: bool = False,
                         focus_files: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Generate tests and automatically heal failures.

        Args:
            force_regeneration: Force test regeneration
            focus_files: Specific files to focus on

        Returns:
            Dictionary with generation and healing results
        """
        print("🚀 Starting Test Generation with Auto-Healing")
        print("=" * 80)

        results = {
            "generation": {
                "success": False,
                "generated_files": [],
                "error": None
            },
            "healing": {
                "enabled": self.enable_healing,
                "success": False,
                "session": None,
                "error": None
            },
            "overall_success": False
        }

        # Step 1: Generate tests
        try:
            print("\n📝 Step 1: Generating tests...")
            generated_files = self._generate_tests(force_regeneration, focus_files)

            results["generation"]["success"] = True
            results["generation"]["generated_files"] = generated_files

            print(f"✅ Generated {len(generated_files)} test files")

        except Exception as e:
            print(f"❌ Test generation failed: {e}")
            results["generation"]["error"] = str(e)
            return results

        # Step 2: Run auto-healing if enabled
        if self.enable_healing and generated_files:
            try:
                print("\n🔧 Step 2: Running auto-healing loop...")

                healing_loop = AutoHealingLoop(
                    target_root=str(self.target_root),
                    generated_tests_dir=str(self.output_dir),
                    max_iterations=self.max_healing_iterations,
                    use_full_source=self.use_full_source
                )

                session = healing_loop.run_healing_loop()

                results["healing"]["success"] = session.success
                results["healing"]["session"] = {
                    "total_iterations": session.total_iterations,
                    "initial_failures": session.initial_failures,
                    "final_failures": session.final_failures,
                    "tests_healed": session.tests_healed,
                    "tests_failed_to_heal": session.tests_failed_to_heal,
                    "success": session.success
                }

                if session.success:
                    print("\n✅ Auto-healing completed successfully!")
                else:
                    print("\n⚠️  Auto-healing completed with some remaining failures")

            except Exception as e:
                print(f"❌ Auto-healing failed: {e}")
                results["healing"]["error"] = str(e)

        # Determine overall success
        results["overall_success"] = (
            results["generation"]["success"] and
            (not self.enable_healing or results["healing"]["success"])
        )

        # Print final summary
        self._print_final_summary(results)

        return results

    def _generate_tests(self,
                       force_regeneration: bool,
                       focus_files: Optional[List[str]]) -> List[str]:
        """
        Generate tests using the existing generation system.

        Args:
            force_regeneration: Force regeneration
            focus_files: Files to focus on

        Returns:
            List of generated test file paths
        """
        import os

        # Set environment variables
        os.environ["TARGET_ROOT"] = str(self.target_root)
        if force_regeneration:
            os.environ["TESTGEN_FORCE"] = "true"

        # Import and run generation
        try:
            from ..gen.enhanced_generate import generate_all
            from ..analyzer import analyze_python_tree

            # Analyze codebase
            analysis = analyze_python_tree(self.target_root)

            # Generate tests
            generated_files = generate_all(
                analysis=analysis,
                outdir=str(self.output_dir),
                focus_files=focus_files
            )

            return generated_files

        except ImportError as e:
            raise RuntimeError(f"Could not import test generation modules: {e}")

    def _print_final_summary(self, results: Dict[str, Any]):
        """Print final summary of generation and healing."""
        print("\n" + "=" * 80)
        print("📊 FINAL SUMMARY")
        print("=" * 80)

        # Generation summary
        print("\nTest Generation:")
        if results["generation"]["success"]:
            print(f"  ✅ Success - {len(results['generation']['generated_files'])} files")
        else:
            print(f"  ❌ Failed - {results['generation']['error']}")

        # Healing summary
        if results["healing"]["enabled"]:
            print("\nAuto-Healing:")
            if results["healing"]["success"]:
                session = results["healing"]["session"]
                print(f"  ✅ Success")
                print(f"     Initial failures: {session['initial_failures']}")
                print(f"     Final failures: {session['final_failures']}")
                print(f"     Tests healed: {session['tests_healed']}")
            elif results["healing"]["error"]:
                print(f"  ❌ Failed - {results['healing']['error']}")
            else:
                print(f"  ⚠️  Completed with remaining failures")

        # Overall
        print("\nOverall Status:")
        if results["overall_success"]:
            print("  ✅ SUCCESS - Tests generated and healed")
        else:
            print("  ⚠️  PARTIAL SUCCESS - Review results above")

        print("=" * 80)


def run_integrated_workflow(target_root: str,
                            output_dir: str = "tests/generated",
                            enable_healing: bool = True,
                            max_healing_iterations: int = 3,
                            force_regeneration: bool = False,
                            focus_files: Optional[List[str]] = None) -> bool:
    """
    Convenience function to run the integrated workflow.

    Args:
        target_root: Root directory of target project
        output_dir: Output directory for generated tests
        enable_healing: Whether to enable auto-healing
        max_healing_iterations: Maximum healing iterations
        force_regeneration: Force test regeneration
        focus_files: Specific files to focus on

    Returns:
        True if successful, False otherwise
    """
    workflow = TestGenerationWithHealing(
        target_root=target_root,
        output_dir=output_dir,
        enable_healing=enable_healing,
        max_healing_iterations=max_healing_iterations
    )

    results = workflow.generate_and_heal(
        force_regeneration=force_regeneration,
        focus_files=focus_files
    )

    return results["overall_success"]


def main():
    """Main entry point for integrated workflow."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Integrated test generation with auto-healing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate and heal tests
  python -m src.test_healing.integration --target ./target

  # Disable healing
  python -m src.test_healing.integration --target ./app --no-healing

  # Custom iterations
  python -m src.test_healing.integration --target ./app --max-iterations 5

  # Force regeneration
  python -m src.test_healing.integration --target ./app --force
"""
    )

    parser.add_argument(
        "--target",
        required=True,
        help="Target project root directory"
    )

    parser.add_argument(
        "--output",
        default="tests/generated",
        help="Output directory for generated tests (default: tests/generated)"
    )

    parser.add_argument(
        "--no-healing",
        action="store_true",
        help="Disable auto-healing"
    )

    parser.add_argument(
        "--max-iterations",
        type=int,
        default=3,
        help="Maximum healing iterations (default: 3)"
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Force test regeneration"
    )

    parser.add_argument(
        "--full-source",
        action="store_true",
        help="Use full source code for context (slower but more accurate)"
    )

    args = parser.parse_args()

    # Validate target
    target_root = pathlib.Path(args.target)
    if not target_root.exists():
        print(f"Error: Target directory not found: {target_root}")
        sys.exit(1)

    # Run workflow
    workflow = TestGenerationWithHealing(
        target_root=str(target_root),
        output_dir=args.output,
        enable_healing=not args.no_healing,
        max_healing_iterations=args.max_iterations,
        use_full_source=args.full_source
    )

    results = workflow.generate_and_heal(
        force_regeneration=args.force
    )

    sys.exit(0 if results["overall_success"] else 1)


if __name__ == "__main__":
    main()
