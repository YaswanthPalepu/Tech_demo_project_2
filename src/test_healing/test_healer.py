#!/usr/bin/env python3
"""
Test Healer - Uses LLM to fix failing tests.

This module uses the LLM to analyze failing tests and generate corrected versions.
It provides context about the failure, the test code, and relevant source code.
"""

import pathlib
import time
from typing import Any, Dict, List, Optional, Tuple

from .pytest_failure_parser import TestFailure
from .test_ast_extractor import TestASTExtractor


class TestHealer:
    """Heals failing tests using LLM-based code correction."""

    def __init__(self,
                 target_root: pathlib.Path,
                 generated_tests_dir: pathlib.Path,
                 use_full_source: bool = False):
        """
        Initialize the test healer.

        Args:
            target_root: Root directory of the target project
            generated_tests_dir: Directory containing generated tests
            use_full_source: If True, include full source code; if False, use AST snippets
        """
        self.target_root = pathlib.Path(target_root)
        self.generated_tests_dir = pathlib.Path(generated_tests_dir)
        self.use_full_source = use_full_source
        self.test_extractor = TestASTExtractor(generated_tests_dir)

        # Import OpenAI client from existing code
        try:
            from ..gen.openai_client import create_client, create_chat_completion, get_deployment_name
            self.create_client = create_client
            self.create_chat_completion = create_chat_completion
            self.get_deployment_name = get_deployment_name
        except ImportError as e:
            print(f"Warning: Could not import OpenAI client: {e}")
            self.create_client = None

        # Import analyzer for AST extraction
        try:
            from ..analyzer import analyze_python_tree
            self.analyze_python_tree = analyze_python_tree
        except ImportError as e:
            print(f"Warning: Could not import analyzer: {e}")
            self.analyze_python_tree = None

    def heal_test(self,
                  failure: TestFailure,
                  max_attempts: int = 3) -> Optional[str]:
        """
        Heal a failing test using LLM.

        Args:
            failure: TestFailure object with failure details
            max_attempts: Maximum number of LLM attempts

        Returns:
            Corrected test code or None if healing failed
        """
        if not self.create_client:
            print("Error: OpenAI client not available")
            return None

        # Extract test code
        test_file = pathlib.Path(failure.test_file)
        test_code = self.test_extractor.get_test_source_code(test_file, failure.test_name)

        if not test_code:
            print(f"Error: Could not extract test code for {failure.test_name}")
            return None

        # Get relevant source code context
        source_context = self._get_source_context(test_file, test_code)

        # Build healing prompt
        messages = self._build_healing_prompt(failure, test_code, source_context)

        # Attempt healing with retry
        client = self.create_client()
        deployment = self.get_deployment_name()

        for attempt in range(max_attempts):
            try:
                if attempt > 0:
                    print(f"  Retry {attempt + 1}/{max_attempts}")
                    time.sleep(2 ** attempt)  # Exponential backoff

                response = self.create_chat_completion(client, deployment, messages)

                # Extract Python code from response
                corrected_code = self._extract_python_code(response)

                if corrected_code:
                    # Validate the corrected code
                    if self._validate_corrected_code(corrected_code, failure):
                        return corrected_code
                    else:
                        # Add feedback for next attempt
                        messages.append({
                            "role": "assistant",
                            "content": response
                        })
                        messages.append({
                            "role": "user",
                            "content": "The corrected code still has issues. Please ensure:\n"
                                       "1. Valid Python syntax\n"
                                       "2. Proper imports\n"
                                       "3. Correct function/class signatures\n"
                                       "4. Proper indentation\n"
                                       "Please provide a complete corrected version."
                        })

            except Exception as e:
                print(f"  Error during healing attempt {attempt + 1}: {e}")
                if attempt < max_attempts - 1:
                    continue
                else:
                    return None

        return None

    def _build_healing_prompt(self,
                              failure: TestFailure,
                              test_code: str,
                              source_context: str) -> List[Dict[str, str]]:
        """Build the prompt for LLM to heal the test."""
        system_prompt = """You are an expert Python test engineer specializing in fixing failing tests.

Your task is to analyze failing pytest tests and fix them. The failures are typically due to:
- Incorrect imports
- Wrong function/method signatures
- Improper mocking/patching
- Syntax errors
- Incorrect assertions
- Missing fixtures or setup

You should:
1. Analyze the error carefully
2. Understand what the test is trying to test
3. Fix ONLY the test code, not the source code being tested
4. Maintain the test's original intent
5. Return the complete corrected test function/class

IMPORTANT: Only return the corrected test code, nothing else."""

        # Build error context
        error_context = f"""
TEST FAILURE DETAILS:
====================
Test Name: {failure.test_name}
Test File: {failure.test_file}:{failure.test_line}
Error Type: {failure.error_type}
Error Message: {failure.error_message}

TRACEBACK:
{chr(10).join(failure.traceback[:20])}  # Limit traceback

{"ASSERTION DETAILS:" if failure.assertion_details else ""}
{self._format_assertion_details(failure.assertion_details) if failure.assertion_details else ""}
"""

        # Build user prompt
        user_prompt = f"""{error_context}

FAILING TEST CODE:
==================
```python
{test_code}
```

RELEVANT SOURCE CODE CONTEXT:
==============================
{source_context}

INSTRUCTIONS:
=============
Please analyze the failure and provide a corrected version of the test.
The test is failing because of an LLM mistake in test generation, not because of a bug in the source code.

Common issues to fix:
- Import errors: Ensure all imports are correct and modules exist
- Syntax errors: Fix any Python syntax issues
- Function signature errors: Match the actual function signatures from the source code
- Mocking errors: Ensure mocks are set up correctly
- Assertion errors: Verify assertions match expected behavior

Provide the complete corrected test function or class. Include all necessary imports.
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]

        return messages

    def _get_source_context(self, test_file: pathlib.Path, test_code: str) -> str:
        """
        Get relevant source code context for healing.

        Args:
            test_file: Path to test file
            test_code: The test code being healed

        Returns:
            Source code context string
        """
        context_parts = []

        # Extract imports from test to understand what's being tested
        imports = self._extract_imports_from_test(test_code)

        if self.use_full_source:
            # Include full source files
            for imp in imports:
                source_file = self._find_source_file(imp)
                if source_file:
                    try:
                        content = source_file.read_text(encoding="utf-8")
                        context_parts.append(f"# File: {source_file}\n{content}\n")
                    except Exception as e:
                        print(f"Error reading source file {source_file}: {e}")
        else:
            # Use AST to extract only relevant parts
            context_parts.append(self._get_ast_context(imports))

        return "\n".join(context_parts)

    def _get_ast_context(self, imports: List[str]) -> str:
        """Get relevant code context using AST analysis."""
        if not self.analyze_python_tree:
            return "# AST analysis not available"

        try:
            # Analyze target codebase
            analysis = self.analyze_python_tree(self.target_root)

            context_parts = []
            context_parts.append("# RELEVANT SOURCE CODE (from AST analysis):\n")

            # Extract relevant functions, classes, methods
            for imp in imports:
                # Find matching items in analysis
                for func in analysis.get("functions", []):
                    if func["name"] in imp or func["file"] in imp:
                        context_parts.append(f"\n# Function: {func['name']} from {func['file']}")
                        context_parts.append(f"# Lines {func['lineno']}-{func.get('end_lineno', func['lineno'])}")

                for cls in analysis.get("classes", []):
                    if cls["name"] in imp or cls["file"] in imp:
                        context_parts.append(f"\n# Class: {cls['name']} from {cls['file']}")
                        context_parts.append(f"# Lines {cls['lineno']}-{cls.get('end_lineno', cls['lineno'])}")
                        context_parts.append(f"# Methods: {', '.join([m['name'] for m in analysis.get('methods', []) if m.get('class') == cls['name']])}")

            return "\n".join(context_parts)

        except Exception as e:
            print(f"Error getting AST context: {e}")
            return "# Error extracting AST context"

    def _extract_imports_from_test(self, test_code: str) -> List[str]:
        """Extract import statements from test code."""
        imports = []
        for line in test_code.splitlines():
            line = line.strip()
            if line.startswith("import ") or line.startswith("from "):
                imports.append(line)
        return imports

    def _find_source_file(self, import_statement: str) -> Optional[pathlib.Path]:
        """Find source file from import statement."""
        # Parse import to get module name
        if import_statement.startswith("from "):
            parts = import_statement.split()
            if len(parts) >= 2:
                module = parts[1].split(".")[0]
        elif import_statement.startswith("import "):
            parts = import_statement.split()
            if len(parts) >= 2:
                module = parts[1].split(".")[0]
        else:
            return None

        # Search for module in target root
        for py_file in self.target_root.rglob(f"{module}.py"):
            return py_file

        # Try as directory with __init__.py
        for init_file in self.target_root.rglob(f"{module}/__init__.py"):
            return init_file

        return None

    def _format_assertion_details(self, assertion_details: Optional[Dict[str, Any]]) -> str:
        """Format assertion details for prompt."""
        if not assertion_details:
            return ""

        parts = []
        for key, value in assertion_details.items():
            parts.append(f"  {key}: {value}")
        return "\n".join(parts)

    def _extract_python_code(self, response: str) -> Optional[str]:
        """Extract Python code from LLM response."""
        import re

        # Try to extract code from markdown code blocks
        code_blocks = re.findall(r"```python\s*(.*?)```", response, re.DOTALL)
        if code_blocks:
            return code_blocks[0].strip()

        # Try generic code blocks
        code_blocks = re.findall(r"```\s*(.*?)```", response, re.DOTALL)
        if code_blocks:
            return code_blocks[0].strip()

        # If no code blocks, assume entire response is code
        return response.strip()

    def _validate_corrected_code(self, code: str, failure: TestFailure) -> bool:
        """Validate that corrected code is syntactically correct."""
        import ast

        try:
            # Check syntax
            ast.parse(code)

            # Check that it contains the test
            test_name = failure.test_name.split("::")[-1]  # Get just the function name
            if f"def {test_name}" not in code and f"class {test_name}" not in code:
                print(f"  Warning: Corrected code doesn't contain {test_name}")
                return False

            return True

        except SyntaxError as e:
            print(f"  Syntax error in corrected code: {e}")
            return False


def main():
    """Test the healer."""
    import sys
    from .pytest_failure_parser import TestFailure

    # Example usage
    if len(sys.argv) < 3:
        print("Usage: python test_healer.py <target_root> <generated_tests_dir>")
        sys.exit(1)

    target_root = pathlib.Path(sys.argv[1])
    generated_tests_dir = pathlib.Path(sys.argv[2])

    healer = TestHealer(target_root, generated_tests_dir)

    # Create a sample failure for testing
    sample_failure = TestFailure(
        test_name="test_example",
        test_file=str(generated_tests_dir / "test_example.py"),
        test_line=10,
        error_type="ImportError",
        error_message="cannot import name 'foo' from 'module'",
        traceback=["  File 'test.py', line 10, in test_example", "    from module import foo", "ImportError: cannot import name 'foo'"],
        is_llm_mistake=True
    )

    print("Testing healer with sample failure...")
    corrected = healer.heal_test(sample_failure)

    if corrected:
        print("\n✅ Healing successful!")
        print("\nCorrected code:")
        print(corrected)
    else:
        print("\n❌ Healing failed")


if __name__ == "__main__":
    main()
