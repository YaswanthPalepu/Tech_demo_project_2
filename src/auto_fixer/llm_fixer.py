"""
LLM Fixer

Generates fixed versions of failing test functions.
"""

import os
import sys
from typing import Optional

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from gen.openai_client import get_openai_client
from .failure_parser import TestFailure


class LLMFixer:
    """
    Uses LLM to generate fixed versions of failing tests.

    Only fixes test_mistake failures, not code bugs.
    """

    SYSTEM_PROMPT = """You are an expert Python test fixing assistant. Your job is to fix failing test code.

Given:
1. A failing test function
2. The error/traceback
3. Relevant source code being tested

Generate a fixed version of the test function that will pass.

Rules:
- Fix ONLY the test code, never modify source code
- Preserve the test's original intent and coverage goals
- Fix common issues: imports, fixtures, assertions, mocks, setup/teardown
- Ensure the fixed test is syntactically correct
- Return ONLY the complete fixed test function, no explanations
- Include all necessary imports if they're missing
- Use proper pytest conventions

Return the complete fixed test function code."""

    def __init__(self):
        """Initialize LLM fixer."""
        try:
            self.client = get_openai_client()
        except Exception as e:
            print(f"Warning: Could not initialize OpenAI client: {e}")
            self.client = None

    def fix_test(
        self,
        failure: TestFailure,
        test_code: str,
        source_code: str,
        previous_fix_attempt: Optional[str] = None
    ) -> Optional[str]:
        """
        Generate a fixed version of a failing test.

        Args:
            failure: TestFailure object
            test_code: Original failing test code
            source_code: Relevant source code being tested
            previous_fix_attempt: Previous fix that failed (for retry)

        Returns:
            Fixed test code or None if fix failed
        """
        if not self.client:
            print("Error: OpenAI client not available")
            return None

        # Build prompt
        user_prompt = self._build_prompt(
            failure,
            test_code,
            source_code,
            previous_fix_attempt
        )

        try:
            # Call LLM
            response = self.client.chat.completions.create(
                model=os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4"),
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.2,  # Low temperature for consistent fixes
                max_tokens=2000
            )

            # Extract fixed code
            content = response.choices[0].message.content.strip()

            # Clean up markdown code blocks if present
            fixed_code = self._extract_code(content)

            return fixed_code

        except Exception as e:
            print(f"Error generating fix: {e}")
            return None

    def _build_prompt(
        self,
        failure: TestFailure,
        test_code: str,
        source_code: str,
        previous_fix_attempt: Optional[str]
    ) -> str:
        """
        Build the prompt for test fixing.

        Args:
            failure: TestFailure object
            test_code: Original failing test code
            source_code: Relevant source code
            previous_fix_attempt: Previous failed fix

        Returns:
            Formatted prompt
        """
        prompt = f"""# Fix This Failing Test

## Original Test Code
```python
{test_code}
```

## Error Information
**Exception:** {failure.exception_type}
**Message:** {failure.error_message}

## Traceback
```
{failure.traceback}
```

## Source Code Being Tested
```python
{source_code}
```
"""

        if previous_fix_attempt:
            prompt += f"""
## Previous Fix Attempt (Failed)
```python
{previous_fix_attempt}
```

The previous fix attempt failed. Try a different approach.
"""

        prompt += """
## Task
Generate a fixed version of the test function that will pass.

Return ONLY the fixed test function code (no explanations, no markdown unless it's code).
"""

        return prompt

    def _extract_code(self, content: str) -> str:
        """
        Extract Python code from LLM response.

        Args:
            content: LLM response content

        Returns:
            Extracted code
        """
        # Remove markdown code blocks
        if "```python" in content:
            parts = content.split("```python")
            if len(parts) > 1:
                code = parts[1].split("```")[0]
                return code.strip()

        if "```" in content:
            parts = content.split("```")
            if len(parts) >= 3:
                code = parts[1]
                return code.strip()

        # If no code blocks, return as-is
        return content.strip()

    def fix_test_full_file(
        self,
        failure: TestFailure,
        full_test_file_content: str,
        source_code: str
    ) -> Optional[str]:
        """
        Generate a fixed version of the entire test file.

        Useful when the fix requires changes to imports or setup.

        Args:
            failure: TestFailure object
            full_test_file_content: Complete test file content
            source_code: Relevant source code

        Returns:
            Fixed full test file or None
        """
        if not self.client:
            return None

        prompt = f"""# Fix This Test File

## Complete Test File
```python
{full_test_file_content}
```

## Failing Test
**Test Name:** {failure.test_name}
**Error:** {failure.exception_type}: {failure.error_message}

## Traceback
```
{failure.traceback}
```

## Source Code
```python
{source_code}
```

## Task
Fix the failing test `{failure.test_name}` in this test file.
You may need to fix imports, fixtures, or the test function itself.

Return the COMPLETE fixed test file."""

        try:
            response = self.client.chat.completions.create(
                model=os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4"),
                messages=[
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2,
                max_tokens=4000
            )

            content = response.choices[0].message.content.strip()
            return self._extract_code(content)

        except Exception as e:
            print(f"Error generating full file fix: {e}")
            return None
