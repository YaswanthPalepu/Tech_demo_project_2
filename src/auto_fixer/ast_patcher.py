"""
AST Patcher

Replaces failing test functions in test files using AST manipulation.
"""

import ast
import subprocess
import tempfile
import shutil
from typing import Optional
from pathlib import Path


class ASTPatcher:
    """
    Patches test files by replacing specific test functions.

    Uses AST to precisely replace only the failing function,
    preserving all other code, imports, and formatting.

    Validates fixes by running pytest to ensure they don't introduce
    new failures (regression prevention).
    """

    def __init__(self, enable_test_validation: bool = True):
        """
        Initialize ASTPatcher.

        Args:
            enable_test_validation: If True, run pytest on fixes before applying.
                                   Prevents auto-fixer from making things worse.
        """
        self.enable_test_validation = enable_test_validation

    def patch_test_function(
        self,
        test_file_path: str,
        test_function_name: str,
        fixed_function_code: str
    ) -> bool:
        """
        Replace a specific test function in a file.

        Args:
            test_file_path: Path to the test file
            test_function_name: Name of the function to replace
            fixed_function_code: Fixed function code

        Returns:
            True if patch successful, False otherwise
        """
        # Read original file
        try:
            with open(test_file_path, 'r') as f:
                original_content = f.read()
        except FileNotFoundError:
            print(f"Error: Test file not found: {test_file_path}")
            return False

        # Parse original file
        try:
            tree = ast.parse(original_content)
        except SyntaxError as e:
            print(f"Error: Cannot parse test file: {e}")
            return False

        # Find and replace the function
        patched_content = self._replace_function(
            original_content,
            tree,
            test_function_name,
            fixed_function_code
        )

        if not patched_content:
            return False

        # Validate patched content before writing
        try:
            patched_tree = ast.parse(patched_content)
        except SyntaxError as e:
            print(f"Error: Patched code has syntax error at line {e.lineno}: {e.msg}")
            if e.text:
                print(f"  Problem line: {e.text.strip()}")
            print(f"  Keeping original file unchanged")
            return False

        # Validate for pytest-specific issues (duplicate parametrize decorators)
        if not self._validate_pytest_decorators(patched_tree):
            print(f"Error: Patched code has duplicate @pytest.mark.parametrize decorators")
            print(f"  Keeping original file unchanged")
            return False

        # CRITICAL: Test the fix before applying it (regression prevention)
        if self.enable_test_validation:
            if not self._test_fix_before_commit(test_file_path, test_function_name,
                                                patched_content, original_content):
                print(f"  Rejecting fix - it still fails or creates new errors")
                return False

        # Write patched content
        try:
            with open(test_file_path, 'w') as f:
                f.write(patched_content)
            return True
        except IOError as e:
            print(f"Error writing patched file: {e}")
            return False

    def _replace_function(
        self,
        original_content: str,
        tree: ast.AST,
        function_name: str,
        fixed_code: str
    ) -> Optional[str]:
        """
        Replace a function in the content.

        Args:
            original_content: Original file content
            tree: Parsed AST tree
            function_name: Function to replace
            fixed_code: Replacement code

        Returns:
            Patched content or None
        """
        # Find the function node
        function_node = None
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == function_name:
                function_node = node
                break

        if not function_node:
            print(f"Error: Function '{function_name}' not found in file")
            return None

        # Get the line range of the function
        start_line = function_node.lineno - 1  # 0-indexed
        end_line = function_node.end_lineno  # Inclusive, 1-indexed

        # Split content into lines
        lines = original_content.split('\n')

        # Get indentation of the original function
        if start_line < len(lines):
            original_line = lines[start_line]
            indent = len(original_line) - len(original_line.lstrip())
        else:
            indent = 0

        # Clean and indent the fixed code
        fixed_lines = self._prepare_fixed_code(fixed_code, indent)

        # Replace the function
        patched_lines = (
            lines[:start_line] +
            fixed_lines +
            lines[end_line:]
        )

        return '\n'.join(patched_lines)

    def _prepare_fixed_code(self, fixed_code: str, indent: int) -> list[str]:
        """
        Prepare fixed code with proper indentation.

        Args:
            fixed_code: Fixed function code
            indent: Number of spaces to indent

        Returns:
            List of indented lines
        """
        # Clean up markdown and formatting first
        fixed_code = self._clean_code(fixed_code)

        # Automatically remove duplicate decorators from LLM-generated code
        fixed_code = self._remove_duplicate_decorators(fixed_code)

        # Parse the fixed code to validate it
        try:
            ast.parse(fixed_code)
        except SyntaxError:
            # If parsing still fails after cleaning, return as-is
            pass

        # Split into lines
        lines = fixed_code.split('\n')

        # Remove empty lines at start and end
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()

        # Find minimum indentation in the fixed code
        min_indent = float('inf')
        for line in lines:
            if line.strip():  # Ignore empty lines
                leading_spaces = len(line) - len(line.lstrip())
                min_indent = min(min_indent, leading_spaces)

        if min_indent == float('inf'):
            min_indent = 0

        # Adjust indentation
        adjusted_lines = []
        for line in lines:
            if line.strip():
                # Remove original indentation and add target indentation
                dedented = line[min_indent:] if len(line) > min_indent else line.lstrip()
                adjusted_lines.append(' ' * indent + dedented)
            else:
                # Preserve empty lines
                adjusted_lines.append('')

        return adjusted_lines

    def _clean_code(self, code: str) -> str:
        """
        Clean up code that might have extra formatting.

        Args:
            code: Code to clean

        Returns:
            Cleaned code
        """
        # Remove markdown code blocks
        if '```python' in code:
            code = code.split('```python')[1].split('```')[0]
        elif '```' in code:
            parts = code.split('```')
            if len(parts) >= 3:
                code = parts[1]

        return code.strip()

    def patch_full_file(
        self,
        test_file_path: str,
        new_content: str
    ) -> bool:
        """
        Replace entire test file content.

        Args:
            test_file_path: Path to test file
            new_content: New file content

        Returns:
            True if successful
        """
        try:
            # Validate the new content can be parsed
            ast.parse(new_content)

            # Write new content
            with open(test_file_path, 'w') as f:
                f.write(new_content)

            return True

        except SyntaxError as e:
            print(f"Error: New content has syntax error at line {e.lineno}: {e.msg}")
            if e.text:
                print(f"  Problem line: {e.text.strip()}")
            print(f"  Keeping original file unchanged")
            return False
        except IOError as e:
            print(f"Error writing file: {e}")
            return False

    def validate_patch(self, test_file_path: str) -> bool:
        """
        Validate that a patched file is syntactically correct.

        Args:
            test_file_path: Path to test file

        Returns:
            True if valid Python
        """
        try:
            with open(test_file_path, 'r') as f:
                content = f.read()

            tree = ast.parse(content)

            # Also validate pytest-specific issues
            if not self._validate_pytest_decorators(tree):
                print(f"Validation failed: Duplicate @pytest.mark.parametrize decorators found")
                return False

            return True

        except SyntaxError as e:
            print(f"Validation failed: {e}")
            return False
        except FileNotFoundError:
            print(f"File not found: {test_file_path}")
            return False

    def _validate_pytest_decorators(self, tree: ast.AST) -> bool:
        """
        Validate that there are no duplicate @pytest.mark.parametrize decorators.

        Args:
            tree: AST tree to validate

        Returns:
            True if no duplicates found, False otherwise
        """
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Track parametrize parameter names for this function
                param_names = []

                for decorator in node.decorator_list:
                    param_name = self._get_parametrize_param_name(decorator)
                    if param_name:
                        if param_name in param_names:
                            # Duplicate found
                            print(f"  Found duplicate parametrize '{param_name}' in function '{node.name}'")
                            return False
                        param_names.append(param_name)

        return True

    def _get_parametrize_param_name(self, decorator: ast.expr) -> str:
        """
        Extract parameter name from @pytest.mark.parametrize decorator.

        Args:
            decorator: Decorator AST node

        Returns:
            Parameter name if this is a parametrize decorator, empty string otherwise
        """
        # Pattern: @pytest.mark.parametrize("param_name", ...)
        if isinstance(decorator, ast.Call):
            if isinstance(decorator.func, ast.Attribute):
                # Check if it's pytest.mark.parametrize
                if (isinstance(decorator.func.value, ast.Attribute) and
                    decorator.func.value.attr == "mark" and
                    decorator.func.attr == "parametrize"):
                    # Get the first argument (parameter name)
                    if decorator.args and isinstance(decorator.args[0], ast.Constant):
                        return decorator.args[0].value

        return ""

    def _test_fix_before_commit(
        self,
        test_file_path: str,
        test_function_name: str,
        patched_content: str,
        original_content: str
    ) -> bool:
        """
        Test a fix before committing it to prevent regressions.

        Writes the patched content temporarily, runs pytest on the specific test,
        then restores the original. Only returns True if the test passes.

        This is CRITICAL to prevent the auto-fixer from making things worse!

        Args:
            test_file_path: Path to the test file
            test_function_name: Name of the test function
            patched_content: The proposed fix
            original_content: The original content (for rollback)

        Returns:
            True if the test passes with the fix, False otherwise
        """
        print(f"  🧪 Testing fix before applying (regression prevention)...")

        # Strip parameter suffix for parameterized tests
        base_test_name = test_function_name.split('[')[0] if '[' in test_function_name else test_function_name

        try:
            # Write the patched content temporarily
            with open(test_file_path, 'w') as f:
                f.write(patched_content)

            # Run pytest on this specific test
            test_nodeid = f"{test_file_path}::{base_test_name}"
            result = subprocess.run(
                ['pytest', test_nodeid, '-v', '--tb=short', '-x'],
                capture_output=True,
                text=True,
                timeout=30  # 30 second timeout
            )

            # Restore original content IMMEDIATELY
            with open(test_file_path, 'w') as f:
                f.write(original_content)

            # Check if test passed
            if result.returncode == 0:
                print(f"  ✅ Fix validated - test passes!")
                return True
            else:
                # Test failed - fix didn't work or made things worse
                print(f"  ❌ Fix validation failed - test still fails:")
                # Show last few lines of output
                output_lines = result.stdout.split('\n')
                for line in output_lines[-5:]:
                    if line.strip():
                        print(f"     {line}")
                return False

        except subprocess.TimeoutExpired:
            # Test hung - definitely reject this fix
            print(f"  ⏱️  Fix validation timed out - test hung")
            # Restore original
            try:
                with open(test_file_path, 'w') as f:
                    f.write(original_content)
            except:
                pass
            return False

        except Exception as e:
            # Any error during testing - restore original and reject
            print(f"  ⚠️  Error during fix validation: {e}")
            try:
                with open(test_file_path, 'w') as f:
                    f.write(original_content)
            except:
                pass
            return False

    def _remove_duplicate_decorators(self, code: str) -> str:
        """
        Automatically remove duplicate @pytest.mark.parametrize decorators from code.

        LLMs sometimes generate duplicate decorators. This method detects and removes
        them automatically so the fix can proceed.

        Args:
            code: Python code (typically a function)

        Returns:
            Code with duplicate decorators removed
        """
        try:
            tree = ast.parse(code)
        except SyntaxError:
            # Can't parse, return as-is
            return code

        # Track if we made any changes
        modified = False

        # Process all function definitions
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                # Track seen parametrize parameter names
                seen_params = set()
                new_decorators = []

                for decorator in node.decorator_list:
                    param_name = self._get_parametrize_param_name(decorator)

                    if param_name:
                        if param_name in seen_params:
                            # Skip duplicate
                            print(f"  Auto-removing duplicate @pytest.mark.parametrize('{param_name}') from LLM fix")
                            modified = True
                            continue
                        seen_params.add(param_name)

                    new_decorators.append(decorator)

                if modified:
                    node.decorator_list = new_decorators

        if not modified:
            # No changes needed
            return code

        # Convert back to code
        try:
            cleaned_code = ast.unparse(tree)
            print(f"  ✓ Automatically cleaned duplicate decorators from LLM-generated fix")
            return cleaned_code
        except Exception:
            # If unparsing fails, return original
            return code
