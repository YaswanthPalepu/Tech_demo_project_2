"""
Enhanced test validation with retry logic and collection checking.

This module provides comprehensive validation for generated test code:
1. Syntax validation (ast.parse) - catches duplicate parameters, missing colons, etc.
2. Collection validation (pytest --collect-only) - catches import errors
3. Retry mechanism with AI regeneration feedback
4. Context-aware validation using source code analysis

The validator ensures only valid tests are written to disk, preventing
pytest collection errors and improving test quality.
"""

import ast
import subprocess
import tempfile
from pathlib import Path
from typing import Tuple, List, Optional, Callable, Dict, Any
import traceback


class GeneratedTestValidator:
    """
    Validates generated test code before writing to disk.

    Answers the question: "How can we validate without source code?"
    - Structural validation (syntax, imports) - NO source code needed
    - Semantic validation (logical correctness) - REQUIRES source code context

    This validator does BOTH:
    - Quick syntax/collection checks (always)
    - Context-aware validation when analysis context is provided
    """

    def __init__(self, verbose: bool = True):
        self.verbose = verbose
        self.validation_stats = {
            "total_validations": 0,
            "syntax_errors_fixed": 0,
            "collection_errors_fixed": 0,
            "retries_needed": 0,
            "failures": 0
        }

    def validate_syntax(self, code: str, context: Optional[Dict[str, Any]] = None) -> Tuple[bool, List[str]]:
        """
        Comprehensive syntax validation using AST.

        Args:
            code: Generated test code to validate
            context: Optional analysis context for semantic validation

        Returns:
            (is_valid, list_of_errors)
        """
        errors = []

        # Step 1: Basic syntax check with ast.parse()
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, [f"Syntax error at line {e.lineno}: {e.msg}"]
        except Exception as e:
            return False, [f"Parse error: {str(e)}"]

        # Step 2: Check for duplicate function parameters
        # This catches errors like: def test(payload, payload): ...
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                params = [arg.arg for arg in node.args.args]
                duplicates = [p for p in params if params.count(p) > 1]
                if duplicates:
                    errors.append(
                        f"Function '{node.name}' at line {node.lineno} has "
                        f"duplicate parameters: {set(duplicates)}"
                    )

        # Step 3: Check for undefined names (requires imports)
        # Collect all imports
        imported_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imported_names.add(alias.asname or alias.name)
            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    imported_names.add(alias.asname or alias.name)

        # Check if pytest fixtures are used
        uses_pytest = any('pytest' in name for name in imported_names)
        if not uses_pytest:
            # Check if test functions exist
            has_test_functions = any(
                isinstance(node, ast.FunctionDef) and node.name.startswith('test_')
                for node in ast.walk(tree)
            )
            if has_test_functions:
                errors.append("Test functions found but 'pytest' not imported")

        # Step 4: Context-aware validation (if source code context provided)
        if context:
            errors.extend(self._validate_with_context(tree, context))

        return len(errors) == 0, errors

    def _validate_with_context(self, tree: ast.AST, context: Dict[str, Any]) -> List[str]:
        """
        Semantic validation using source code analysis context.

        This answers: "How can we validate without source code?"
        Answer: We CAN'T do full semantic validation without it!

        Args:
            tree: Parsed AST of generated test
            context: Analysis results from analyse.py/enhanced_analysis.py
                     containing functions, classes, routes from SOURCE code

        Returns:
            List of validation errors
        """
        errors = []

        # Extract what the test is trying to test
        test_targets = self._extract_test_targets(tree)

        # Check if targets exist in source code
        source_functions = set(context.get('functions', []))
        source_classes = set(context.get('classes', []))
        source_routes = set(context.get('routes', []))

        for target in test_targets:
            if target not in source_functions and \
               target not in source_classes and \
               target not in source_routes:
                errors.append(
                    f"Test targets '{target}' which doesn't exist in source code. "
                    f"Available: {source_functions | source_classes | source_routes}"
                )

        return errors

    def _extract_test_targets(self, tree: ast.AST) -> List[str]:
        """Extract what functions/classes the test is targeting."""
        targets = []

        for node in ast.walk(tree):
            # Look for function calls in test functions
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    targets.append(node.func.id)
                elif isinstance(node.func, ast.Attribute):
                    targets.append(node.func.attr)

        return list(set(targets))

    def validate_collection(
        self,
        code: str,
        temp_file: Optional[Path] = None
    ) -> Tuple[bool, str]:
        """
        Fast collection check using pytest --collect-only.

        This catches:
        - Import errors
        - Module-level execution errors
        - pytest collection failures

        Args:
            code: Generated test code
            temp_file: Optional temp file path (created if not provided)

        Returns:
            (is_valid, error_message)
        """
        # Create temp file if not provided
        if temp_file is None:
            temp_file = Path(tempfile.gettempdir()) / f"test_validation_{id(code)}.py"

        try:
            # Write to temp file
            temp_file.write_text(code, encoding='utf-8')

            # Run pytest --collect-only (fast check - ~500ms)
            result = subprocess.run(
                ['pytest', str(temp_file), '--collect-only', '--quiet', '--quiet'],
                capture_output=True,
                text=True,
                timeout=10,
                env={'PYTHONDONTWRITEBYTECODE': '1'}  # Don't create __pycache__
            )

            if result.returncode == 0:
                return True, ""
            else:
                # Extract meaningful error from stderr/stdout
                error_output = result.stderr or result.stdout
                error_lines = [
                    line for line in error_output.split('\n')
                    if 'error' in line.lower() or 'failed' in line.lower()
                ]
                error_msg = '\n'.join(error_lines[:5])  # First 5 error lines
                return False, error_msg or "Collection failed (unknown reason)"

        except subprocess.TimeoutExpired:
            return False, "Collection timeout (>10s) - possible infinite loop"
        except Exception as e:
            return False, f"Collection validation error: {str(e)}"
        finally:
            # Clean up temp file
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception:
                    pass

    def validate_and_write(
        self,
        code: str,
        output_path: Path,
        max_retries: int = 3,
        regenerate_fn: Optional[Callable[[str], str]] = None,
        analysis_context: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Validate generated test code and write only if valid.
        Includes retry logic with regeneration.

        Args:
            code: Generated test code
            output_path: Where to write the file
            max_retries: Number of retry attempts
            regenerate_fn: Function to call for regeneration
                           Signature: (error_context: str) -> new_code: str
            analysis_context: Source code analysis for semantic validation

        Returns:
            True if successfully validated and written, False otherwise
        """
        self.validation_stats["total_validations"] += 1
        temp_file = Path(tempfile.gettempdir()) / f"validate_{output_path.name}"

        try:
            for attempt in range(1, max_retries + 1):
                # Step 1: Syntax validation (~10ms)
                is_valid, errors = self.validate_syntax(code, analysis_context)

                if not is_valid:
                    self.validation_stats["syntax_errors_fixed"] += 1
                    if self.verbose:
                        print(f"  ⚠️  Syntax validation failed (attempt {attempt}/{max_retries}):")
                        for error in errors[:3]:  # Show first 3 errors
                            print(f"      - {error}")

                    if attempt < max_retries and regenerate_fn:
                        self.validation_stats["retries_needed"] += 1
                        if self.verbose:
                            print(f"  🔄 Regenerating with fix prompt...")
                        code = regenerate_fn(error_context="\n".join(errors))
                        continue
                    else:
                        self.validation_stats["failures"] += 1
                        return False

                # Step 2: Collection validation (~500ms)
                is_valid, error = self.validate_collection(code, temp_file)

                if not is_valid:
                    self.validation_stats["collection_errors_fixed"] += 1
                    if self.verbose:
                        print(f"  ⚠️  Collection validation failed (attempt {attempt}/{max_retries}):")
                        print(f"      {error}")

                    if attempt < max_retries and regenerate_fn:
                        self.validation_stats["retries_needed"] += 1
                        if self.verbose:
                            print(f"  🔄 Regenerating with fix prompt...")
                        code = regenerate_fn(error_context=error)
                        continue
                    else:
                        self.validation_stats["failures"] += 1
                        return False

                # Success! Write to final location
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_text(code, encoding='utf-8')

                if self.verbose:
                    if attempt > 1:
                        print(f"  ✅ Validated and wrote (after {attempt} attempts): {output_path.name}")
                    else:
                        print(f"  ✅ Validated and wrote: {output_path.name}")

                return True

            # Max retries exceeded
            self.validation_stats["failures"] += 1
            if self.verbose:
                print(f"  ❌ Failed to generate valid test after {max_retries} attempts")
            return False

        except Exception as e:
            self.validation_stats["failures"] += 1
            if self.verbose:
                print(f"  ❌ Validation error: {str(e)}")
                traceback.print_exc()
            return False
        finally:
            # Clean up temp file
            if temp_file.exists():
                try:
                    temp_file.unlink()
                except Exception:
                    pass

    def print_stats(self):
        """Print validation statistics."""
        if self.verbose:
            print("\n📊 Validation Statistics:")
            print(f"   Total validations: {self.validation_stats['total_validations']}")
            print(f"   Syntax errors fixed: {self.validation_stats['syntax_errors_fixed']}")
            print(f"   Collection errors fixed: {self.validation_stats['collection_errors_fixed']}")
            print(f"   Retries needed: {self.validation_stats['retries_needed']}")
            print(f"   Failures: {self.validation_stats['failures']}")

            if self.validation_stats['total_validations'] > 0:
                success_rate = (
                    (self.validation_stats['total_validations'] - self.validation_stats['failures'])
                    / self.validation_stats['total_validations'] * 100
                )
                print(f"   Success rate: {success_rate:.1f}%")


# Convenience function for quick validation
def quick_validate(code: str) -> Tuple[bool, str]:
    """
    Quick syntax-only validation without retries.

    Returns:
        (is_valid, error_message)
    """
    validator = GeneratedTestValidator(verbose=False)
    is_valid, errors = validator.validate_syntax(code)

    if is_valid:
        return True, ""
    else:
        return False, "\n".join(errors)
