"""
Auto Test Fixer Orchestrator with Embedding Support

Main orchestrator that coordinates the entire test fixing workflow
with hybrid AST + embedding-based context extraction.
"""

import json
import os
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict

from .failure_parser import FailureParser, TestFailure
from .rule_classifier import RuleBasedClassifier
from .llm_classifier import LLMClassifier
from .enhanced_context_extractor import EnhancedContextExtractor
from .llm_fixer import LLMFixer
from .ast_patcher import ASTPatcher


@dataclass
class FixResult:
    """Result of a fix attempt."""
    test_file: str
    test_name: str
    classification: str
    fix_attempted: bool
    fix_successful: bool
    reason: str
    extraction_method: str = "unknown"  # 'ast', 'embedding', or 'hybrid'
    context_elements: int = 0


class AutoTestFixerOrchestrator:
    """
    Orchestrates the automatic test fixing workflow with embeddings.

    Enhanced Workflow:
    1. Run pytest with JSON output
    2. Parse all failures
    3. Classify each failure (rule-based + LLM)
    4. Extract context using HYBRID approach (AST + Embeddings)
    5. Detect "source not found" / "target not found" errors
    6. Chunk context to fit token limits
    7. Generate fixes using LLM (with chunked context)
    8. Apply fixes using AST patcher
    9. Re-run tests
    10. Repeat until all test mistakes fixed or max iterations reached
    """

    def __init__(
        self,
        test_directory: str = "tests",
        project_root: str = ".",
        max_iterations: int = 3,
        use_embeddings: bool = True,
        max_context_tokens: int = 6000,
        rebuild_index: bool = False
    ):
        """
        Initialize orchestrator.

        Args:
            test_directory: Directory containing tests
            project_root: Root directory of the project
            max_iterations: Maximum fix iterations
            use_embeddings: Enable embedding-based extraction
            max_context_tokens: Maximum tokens for context
            rebuild_index: Force rebuild of embedding index
        """
        self.test_directory = test_directory
        self.project_root = project_root
        self.max_iterations = max_iterations
        self.use_embeddings = use_embeddings

        # Check for verbose mode
        verbose = os.getenv("AUTOFIXER_VERBOSE", "").lower() in ("true", "1", "yes")

        # Initialize components
        self.failure_parser = FailureParser(test_directory)
        self.rule_classifier = RuleBasedClassifier()
        self.llm_classifier = LLMClassifier()

        # Initialize enhanced context extractor (with embeddings)
        self.context_extractor = EnhancedContextExtractor(
            project_root=project_root,
            max_context_tokens=max_context_tokens,
            use_embeddings=use_embeddings,
            verbose=verbose
        )

        self.llm_fixer = LLMFixer()
        self.ast_patcher = ASTPatcher()

        # Track results
        self.fix_history: List[FixResult] = []
        self.code_bugs: List[TestFailure] = []

        # Rebuild index if requested
        if rebuild_index and use_embeddings:
            print("🔨 Rebuilding embedding index...")
            if self.context_extractor.indexer:
                self.context_extractor.indexer.build_index(force_rebuild=True)

    def run(self, extra_pytest_args: List[str] = None) -> Dict[str, Any]:
        """
        Run the auto-fixer workflow.

        Args:
            extra_pytest_args: Additional pytest arguments

        Returns:
            Summary of fixes and results
        """
        print("=" * 80)
        print("AUTO TEST FIXER WITH EMBEDDINGS - STARTING")
        print("=" * 80)

        # Show extractor statistics
        if self.use_embeddings:
            stats = self.context_extractor.get_statistics()
            print(f"\n📊 Embedding Index Statistics:")
            if 'index_stats' in stats:
                idx_stats = stats['index_stats']
                print(f"  Total elements indexed: {idx_stats['total_elements']}")
                print(f"  Files indexed: {idx_stats['files']}")
                print(f"  By type: {idx_stats['by_type']}")
                if idx_stats['http_endpoints']:
                    print(f"  HTTP endpoints: {len(idx_stats['http_endpoints'])}")
            if 'retrieval_stats' in stats:
                ret_stats = stats['retrieval_stats']
                print(f"  Embedding coverage: {ret_stats['coverage']}")

        print()

        iteration = 0
        all_tests_fixed = False

        while iteration < self.max_iterations and not all_tests_fixed:
            iteration += 1
            print(f"\n{'=' * 80}")
            print(f"ITERATION {iteration}/{self.max_iterations}")
            print(f"{'=' * 80}\n")

            # Step 1: Run pytest and parse failures
            print("Step 1: Running pytest and parsing failures...")
            failures = self.failure_parser.run_and_parse(extra_pytest_args)

            if not failures:
                print("✓ No test failures found!")
                all_tests_fixed = True
                break

            print(f"Found {len(failures)} failing test(s)")

            # Step 2-9: Process each failure
            test_mistakes_fixed = []
            code_bugs_found = []
            source_not_found = []
            target_not_found = []

            for idx, failure in enumerate(failures, 1):
                print(f"\n--- Processing failure {idx}/{len(failures)} ---")
                print(f"Test: {failure.test_name} in {failure.test_file}")

                result = self._process_failure(failure)
                self.fix_history.append(result)

                if result.classification == "code_bug":
                    code_bugs_found.append(failure)
                    print(f"  Classification: CODE BUG (skipped)")
                elif result.classification == "source_not_found":
                    source_not_found.append(failure)
                    print(f"  ❌ SOURCE CODE NOT FOUND")
                elif result.classification == "target_not_found":
                    target_not_found.append(failure)
                    print(f"  ❌ TARGET FUNCTION NOT FOUND")
                elif result.fix_successful:
                    test_mistakes_fixed.append(failure)
                    print(f"  ✅ TEST MISTAKE FIXED")
                else:
                    print(f"  ⚠ TEST MISTAKE (fix failed)")

            print(f"\n{'=' * 80}")
            print(f"Iteration {iteration} Summary:")
            print(f"  Test mistakes fixed: {len(test_mistakes_fixed)}")
            print(f"  Code bugs found: {len(code_bugs_found)}")
            if source_not_found:
                print(f"  ❌ Source code not found: {len(source_not_found)}")
            if target_not_found:
                print(f"  ❌ Target function not found: {len(target_not_found)}")
            print(f"{'=' * 80}")

            # Update code bugs list
            self.code_bugs.extend(code_bugs_found)

            # Stop if no progress
            if len(test_mistakes_fixed) == 0 and iteration > 1:
                print("\nNo test mistakes fixed in this iteration. Stopping.")
                break

        # Final summary
        return self._generate_summary(iteration)

    def _process_failure(self, failure: TestFailure) -> FixResult:
        """
        Process a single test failure with embedding support.

        Args:
            failure: TestFailure object

        Returns:
            FixResult object
        """
        # Step 2: Rule-based classification
        rule_classification = self.rule_classifier.classify(failure)

        if rule_classification == "test_mistake":
            print(f"  Rule classifier: test_mistake")
            return self._fix_test_mistake(failure, "rule-based classification")

        # Step 3: Extract context using HYBRID approach
        print(f"  Rule classifier: unknown, extracting context...")

        test_code = self._read_test_function(failure)

        # Enhanced extraction with embeddings
        context_string, extraction_metadata = self.context_extractor.extract_context(
            test_file_path=failure.test_file,
            test_function_name=failure.test_name,
            error_message=failure.error_message,
            test_code=test_code
        )

        extraction_method = extraction_metadata.get('method', 'unknown')
        context_elements = extraction_metadata.get('total_results', 0)

        print(f"  Extraction: {extraction_method} method, {context_elements} elements")

        # Check for "source not found" error
        if context_elements == 0:
            print(f"  ❌ No source code found for this test")
            return FixResult(
                test_file=failure.test_file,
                test_name=failure.test_name,
                classification="source_not_found",
                fix_attempted=False,
                fix_successful=False,
                reason="No source code found matching test imports or error traceback",
                extraction_method=extraction_method,
                context_elements=0
            )

        # Step 4: LLM classification (with extracted context)
        llm_result = self.llm_classifier.classify(failure, test_code, context_string)
        print(f"  LLM classifier: {llm_result.classification} ({llm_result.reason})")

        if llm_result.classification == "test_mistake":
            # Try to use LLM's suggested fix first
            if llm_result.fixed_code:
                success = self._apply_fix(failure, llm_result.fixed_code)
                if success:
                    return FixResult(
                        test_file=failure.test_file,
                        test_name=failure.test_name,
                        classification="test_mistake",
                        fix_attempted=True,
                        fix_successful=True,
                        reason=llm_result.reason,
                        extraction_method=extraction_method,
                        context_elements=context_elements
                    )

            # If LLM fix didn't work, generate a new fix
            return self._fix_test_mistake(
                failure,
                llm_result.reason,
                context_string,
                extraction_metadata
            )

        # Code bug - don't fix
        return FixResult(
            test_file=failure.test_file,
            test_name=failure.test_name,
            classification="code_bug",
            fix_attempted=False,
            fix_successful=False,
            reason=llm_result.reason,
            extraction_method=extraction_method,
            context_elements=context_elements
        )

    def _fix_test_mistake(
        self,
        failure: TestFailure,
        reason: str,
        context_string: Optional[str] = None,
        extraction_metadata: Optional[Dict] = None
    ) -> FixResult:
        """
        Fix a test mistake with multi-attempt learning.

        Args:
            failure: TestFailure object
            reason: Reason for classification
            context_string: Pre-extracted context (optional)
            extraction_metadata: Metadata from extraction (optional)

        Returns:
            FixResult object
        """
        # Extract context if not provided
        if context_string is None:
            test_code = self._read_test_function(failure)

            context_string, extraction_metadata = self.context_extractor.extract_context(
                test_file_path=failure.test_file,
                test_function_name=failure.test_name,
                error_message=failure.error_message,
                test_code=test_code
            )
        else:
            test_code = self._read_test_function(failure)

        extraction_method = extraction_metadata.get('method', 'unknown') if extraction_metadata else 'unknown'
        context_elements = extraction_metadata.get('total_results', 0) if extraction_metadata else 0

        max_attempts = 3
        previous_fix = None
        previous_failure_output = None

        for attempt in range(1, max_attempts + 1):
            # Step 5: Generate fix
            if attempt == 1:
                print(f"  Generating fix...")
            else:
                print(f"  Generating fix (attempt {attempt}/{max_attempts})...")
                print(f"    Learning from previous failure...")

            fixed_code = self.llm_fixer.fix_test(
                failure,
                test_code,
                context_string,
                previous_fix_attempt=previous_fix,
                previous_failure_output=previous_failure_output
            )

            if not fixed_code:
                if attempt == max_attempts:
                    return FixResult(
                        test_file=failure.test_file,
                        test_name=failure.test_name,
                        classification="test_mistake",
                        fix_attempted=True,
                        fix_successful=False,
                        reason=f"{reason} (fix generation failed after {attempt} attempts)",
                        extraction_method=extraction_method,
                        context_elements=context_elements
                    )
                continue  # Try again

            # Step 6: Apply fix (returns success flag and failure output if failed)
            success, failure_output = self._apply_fix_with_feedback(failure, fixed_code)

            if success:
                print(f"  ✅ Fix successful on attempt {attempt}!")
                return FixResult(
                    test_file=failure.test_file,
                    test_name=failure.test_name,
                    classification="test_mistake",
                    fix_attempted=True,
                    fix_successful=True,
                    reason=reason,
                    extraction_method=extraction_method,
                    context_elements=context_elements
                )

            # Fix failed - prepare for next attempt
            previous_fix = fixed_code
            previous_failure_output = failure_output

            if attempt < max_attempts:
                print(f"  ⚠️  Fix attempt {attempt} failed, will retry with feedback...")
            else:
                print(f"  ❌ All {max_attempts} fix attempts failed")

        return FixResult(
            test_file=failure.test_file,
            test_name=failure.test_name,
            classification="test_mistake",
            fix_attempted=True,
            fix_successful=False,
            reason=f"{reason} (fix validation failed after {max_attempts} attempts)",
            extraction_method=extraction_method,
            context_elements=context_elements
        )

    def _apply_fix(self, failure: TestFailure, fixed_code: str) -> bool:
        """Apply a fix to a test file."""
        print(f"  Applying fix...")

        base_test_name = self._strip_test_parameters(failure.test_name)

        success = self.ast_patcher.patch_test_function(
            failure.test_file,
            base_test_name,
            fixed_code
        )

        if success:
            if self.ast_patcher.validate_patch(failure.test_file):
                print(f"  ✓ Fix applied successfully")
                return True
            else:
                print(f"  ✗ Fix validation failed")
                return False
        else:
            print(f"  ✗ Fix application failed")
            return False

    def _apply_fix_with_feedback(self, failure: TestFailure, fixed_code: str) -> tuple:
        """Apply a fix and return detailed feedback if it fails."""
        print(f"  Applying fix...")

        base_test_name = self._strip_test_parameters(failure.test_name)

        success, failure_output = self.ast_patcher.patch_test_function_with_feedback(
            failure.test_file,
            base_test_name,
            fixed_code
        )

        if success:
            if self.ast_patcher.validate_patch(failure.test_file):
                print(f"  ✓ Fix applied successfully")
                return True, ""
            else:
                print(f"  ✗ Fix validation failed")
                return False, "Syntax validation failed after applying fix"
        else:
            if failure_output:
                print(f"  ✗ Fix validation failed - test still fails")
            else:
                print(f"  ✗ Fix application failed")
            return False, failure_output

    def _strip_test_parameters(self, test_name: str) -> str:
        """Strip pytest parameter suffix from test name."""
        if '[' in test_name:
            return test_name.split('[')[0]
        return test_name

    def _read_test_function(self, failure: TestFailure) -> str:
        """Read the failing test function code."""
        try:
            with open(failure.test_file, 'r') as f:
                content = f.read()

            import ast
            tree = ast.parse(content)

            base_test_name = self._strip_test_parameters(failure.test_name)

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == base_test_name:
                    return ast.unparse(node)

            return content

        except Exception as e:
            print(f"Error reading test function: {e}")
            return ""

    def _generate_summary(self, iterations: int) -> Dict[str, Any]:
        """Generate final summary report."""
        total_failures = len(self.fix_history)
        test_mistakes = [r for r in self.fix_history if r.classification == "test_mistake"]
        code_bugs = [r for r in self.fix_history if r.classification == "code_bug"]
        source_not_found = [r for r in self.fix_history if r.classification == "source_not_found"]
        target_not_found = [r for r in self.fix_history if r.classification == "target_not_found"]
        successful_fixes = [r for r in test_mistakes if r.fix_successful]

        # Extraction method statistics
        extraction_methods = {}
        for r in self.fix_history:
            method = r.extraction_method
            extraction_methods[method] = extraction_methods.get(method, 0) + 1

        summary = {
            "iterations": iterations,
            "total_failures": total_failures,
            "test_mistakes": len(test_mistakes),
            "code_bugs": len(code_bugs),
            "source_not_found": len(source_not_found),
            "target_not_found": len(target_not_found),
            "successful_fixes": len(successful_fixes),
            "failed_fixes": len(test_mistakes) - len(successful_fixes),
            "extraction_methods": extraction_methods,
            "fix_history": [asdict(r) for r in self.fix_history],
            "code_bugs_list": [f.to_dict() for f in self.code_bugs]
        }

        # Print summary
        print("\n" + "=" * 80)
        print("FINAL SUMMARY")
        print("=" * 80)
        print(f"Iterations: {iterations}/{self.max_iterations}")
        print(f"Total failures processed: {total_failures}")
        print(f"Test mistakes: {len(test_mistakes)}")
        print(f"  - Fixed: {len(successful_fixes)}")
        print(f"  - Failed to fix: {len(test_mistakes) - len(successful_fixes)}")
        print(f"Code bugs (not fixed): {len(code_bugs)}")
        if source_not_found:
            print(f"❌ Source code not found: {len(source_not_found)}")
        if target_not_found:
            print(f"❌ Target function not found: {len(target_not_found)}")
        print(f"\nExtraction methods used: {extraction_methods}")
        print("=" * 80)

        # Save report
        with open("auto_fixer_report.json", "w") as f:
            json.dump(summary, f, indent=2)

        print("\nDetailed report saved to: auto_fixer_report.json")

        return summary
