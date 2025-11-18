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
        previous_fix_attempt: Optional[str] = None,
        previous_failure_output: Optional[str] = None
    ) -> Optional[str]:
        """
        Generate a fixed version of a failing test.

        Args:
            failure: TestFailure object
            test_code: Original failing test code
            source_code: Relevant source code being tested
            previous_fix_attempt: Previous fix that failed (for retry)
            previous_failure_output: Pytest output from previous failed fix attempt

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
            previous_fix_attempt,
            previous_failure_output
        )

        try:
            # Call LLM
            # Build request parameters
            request_params = {
                "model": os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4"),
                "messages": [
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                # Increased to 4000 to handle complete test functions
                # Some tests can be lengthy and we need the full fixed code
                "max_completion_tokens": 4000
            }

            # Only set temperature if environment variable is set
            # Some Azure deployments don't support custom temperature
            temp = os.getenv("AUTOFIXER_LLM_TEMPERATURE")
            if temp is not None:
                request_params["temperature"] = float(temp)

            response = self.client.chat.completions.create(**request_params)

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
        previous_fix_attempt: Optional[str],
        previous_failure_output: Optional[str] = None
    ) -> str:
        """
        Build the prompt for test fixing with learning from previous failures.

        Args:
            failure: TestFailure object
            test_code: Original failing test code
            source_code: Relevant source code
            previous_fix_attempt: Previous failed fix
            previous_failure_output: Pytest output from previous failed fix

        Returns:
            Formatted prompt
        """
        # Truncate error message and traceback if too long to avoid token limits
        max_error_chars = 1000
        max_traceback_chars = 3000

        error_message = failure.error_message
        if len(error_message) > max_error_chars:
            error_message = error_message[:max_error_chars] + "\n... (truncated)"

        traceback = failure.traceback
        if len(traceback) > max_traceback_chars:
            # Keep the last part of traceback (most relevant)
            traceback = "... (truncated)\n" + traceback[-max_traceback_chars:]

        prompt = f"""# Fix This Failing Test

## Original Test Code
```python
{test_code}
```

## Error Information
**Exception:** {failure.exception_type}
**Message:** {error_message}

## Traceback
```
{traceback}
```

## Source Code Being Tested
```python
{source_code}
```
"""

        if previous_fix_attempt and previous_failure_output:
            prompt += f"""
## Previous Fix Attempt (Failed)
```python
{previous_fix_attempt}
```

## Why the Previous Fix Failed
When we ran pytest on the above fix, it still failed with this output:

```
{previous_failure_output[:2000]}
```

**IMPORTANT:** Analyze WHY this fix failed:
- Is the API key dependency still not being handled?
- Are there other dependencies or fixtures that need to be mocked?
- Is the mock setup incorrect?
- Are there missing imports?
- Does the test need different assertions?

Generate a NEW fix that addresses these specific failure reasons. Don't repeat the same approach!
"""
        elif previous_fix_attempt:
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

**Common patterns to fix:**
1. **Missing API key handling:**
   - Mock the `verify_api_key` dependency
   - Or set `REQUIRE_API_KEY=false` in environment
   - Example: `monkeypatch.setenv("REQUIRE_API_KEY", "false")`

2. **Missing fixture mocking:**
   - Use `monkeypatch.setattr()` to mock required attributes
   - Use `@patch()` decorator for external dependencies
   - Mock database connections, external APIs, etc.

3. **Incorrect imports:**
   - Ensure all required imports are present
   - Use correct module paths

4. **Wrong test setup:**
   - Initialize required fixtures properly
   - Set up test data correctly
   - Clean up after test if needed

Return ONLY the complete fixed test function code (include decorators, docstring, everything).
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
            # Build request parameters
            request_params = {
                "model": os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4"),
                "messages": [
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                # Increased to 6000 for full file fixes (larger output)
                "max_completion_tokens": 6000
            }

            # Only set temperature if environment variable is set
            # Some Azure deployments don't support custom temperature
            temp = os.getenv("AUTOFIXER_LLM_TEMPERATURE")
            if temp is not None:
                request_params["temperature"] = float(temp)

            response = self.client.chat.completions.create(**request_params)

            content = response.choices[0].message.content.strip()
            return self._extract_code(content)

        except Exception as e:
            print(f"Error generating full file fix: {e}")
            return None
