"""
LLM-Based Classifier

Uses LLM to classify test failures and suggest fixes.
"""

import json
from typing import Literal, Optional
from dataclasses import dataclass
from .failure_parser import TestFailure
import sys
import os

# Add parent directory to path to import gen modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from gen.openai_client import get_openai_client


ClassificationType = Literal["test_mistake", "code_bug"]


@dataclass
class LLMClassification:
    """Result from LLM classification."""
    classification: ClassificationType
    reason: str
    fixed_code: Optional[str] = None
    confidence: float = 0.0


class LLMClassifier:
    """
    Uses LLM to classify test failures and suggest fixes.

    Distinguishes between:
    - test_mistake: Error in the test code itself
    - code_bug: Error in the source code being tested
    """

    SYSTEM_PROMPT = """You are an expert test debugging assistant. Your job is to analyze failing tests and determine if the failure is due to:

1. **test_mistake**: The test code itself has an error (wrong imports, bad fixtures, incorrect assertions, wrong test setup, etc.)
2. **code_bug**: The source code being tested has a bug (logic error, wrong implementation, etc.)

When you identify a **test_mistake**, you should also provide the fixed version of the test code.

Respond with a JSON object:
{
  "classification": "test_mistake" | "code_bug",
  "reason": "Brief explanation of why this classification was chosen",
  "fixed_code": "Fixed version of the failing test function (only for test_mistake)",
  "confidence": 0.0-1.0
}

Be conservative: if you're unsure, classify as "code_bug" to avoid incorrectly modifying tests."""

    def __init__(self):
        """Initialize LLM classifier."""
        try:
            self.client = get_openai_client()
        except Exception as e:
            print(f"Warning: Could not initialize OpenAI client: {e}")
            self.client = None

    def classify(
        self,
        failure: TestFailure,
        test_code: str,
        source_code: str,
    ) -> LLMClassification:
        """
        Classify a test failure using LLM.

        Args:
            failure: TestFailure object
            test_code: The failing test function code
            source_code: Relevant source code being tested (from AST extraction)

        Returns:
            LLMClassification object
        """
        if not self.client:
            # Fallback classification
            return LLMClassification(
                classification="code_bug",
                reason="LLM client not available",
                confidence=0.0
            )

        # Build the prompt
        user_prompt = self._build_prompt(failure, test_code, source_code)

        try:
            # Call LLM with retry logic
            # Get deployment from environment (required - no fallback)
            deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")
            if not deployment:
                raise ValueError("AZURE_OPENAI_DEPLOYMENT environment variable not set")

            # Build request parameters
            request_params = {
                "model": deployment,
                "messages": [
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                "max_completion_tokens": 2000
            }

            # Only set temperature if environment variable is set
            # Some Azure deployments don't support custom temperature
            temp = os.getenv("AUTOFIXER_LLM_TEMPERATURE")
            if temp is not None:
                request_params["temperature"] = float(temp)

            # Retry logic with exponential backoff
            response = self._call_llm_with_retry(request_params, max_retries=3)

            # Parse response
            content = response.choices[0].message.content.strip()

            # Extract JSON from response (handle various formats)
            json_str = self._extract_json(content)

            result = json.loads(json_str)

            return LLMClassification(
                classification=result.get("classification", "code_bug"),
                reason=result.get("reason", "No reason provided"),
                fixed_code=result.get("fixed_code"),
                confidence=result.get("confidence", 0.5)
            )

        except json.JSONDecodeError as e:
            print(f"Error parsing LLM JSON response: {e}")
            print(f"Response preview: {content[:200] if 'content' in locals() else 'N/A'}...")
            # Conservative fallback
            return LLMClassification(
                classification="code_bug",
                reason=f"JSON parse error: {str(e)}",
                confidence=0.0
            )
        except Exception as e:
            print(f"Error in LLM classification: {e}")
            # Conservative fallback
            return LLMClassification(
                classification="code_bug",
                reason=f"Classification failed: {str(e)}",
                confidence=0.0
            )

    def _call_llm_with_retry(self, request_params: dict, max_retries: int = 3):
        """
        Call LLM API with exponential backoff retry logic.

        Args:
            request_params: Parameters for the API call
            max_retries: Maximum number of retry attempts

        Returns:
            API response

        Raises:
            Exception: If all retries fail
        """
        import time

        for attempt in range(max_retries):
            try:
                response = self.client.chat.completions.create(**request_params)

                # Validate response has content
                if not response.choices or not response.choices[0].message.content:
                    raise ValueError("Empty response from LLM")

                content = response.choices[0].message.content.strip()
                if not content:
                    raise ValueError("Empty content in LLM response")

                return response

            except Exception as e:
                if attempt < max_retries - 1:
                    # Calculate backoff time: 2^attempt seconds (2s, 4s, 8s)
                    backoff_time = 2 ** attempt
                    print(f"  ⚠️  LLM API error (attempt {attempt + 1}/{max_retries}): {e}")
                    print(f"      Retrying in {backoff_time}s...")
                    time.sleep(backoff_time)
                else:
                    # Final attempt failed
                    print(f"  ❌ LLM API failed after {max_retries} attempts: {e}")
                    raise

    def _extract_json(self, content: str) -> str:
        """
        Extract JSON from LLM response, handling various formats.

        Args:
            content: Raw LLM response

        Returns:
            JSON string
        """
        # Try markdown code blocks first
        if "```json" in content:
            return content.split("```json")[1].split("```")[0].strip()

        if "```" in content:
            parts = content.split("```")
            for part in parts[1::2]:  # Every other part (inside code blocks)
                part = part.strip()
                if part.startswith('{') and part.endswith('}'):
                    return part

        # Try to find JSON object directly
        import re
        json_pattern = r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}'
        matches = re.findall(json_pattern, content, re.DOTALL)
        if matches:
            # Return the longest match (likely the complete JSON)
            return max(matches, key=len)

        # Fallback: return as-is and hope it's valid JSON
        return content

    def _build_prompt(
        self,
        failure: TestFailure,
        test_code: str,
        source_code: str
    ) -> str:
        """
        Build the user prompt for classification.

        Args:
            failure: TestFailure object
            test_code: The failing test function code
            source_code: Relevant source code

        Returns:
            Formatted prompt string
        """
        prompt = f"""# Test Failure Analysis

## Failing Test
**File:** {failure.test_file}
**Test Name:** {failure.test_name}
**Line:** {failure.line_number or 'Unknown'}

## Error Information
**Exception Type:** {failure.exception_type}
**Error Message:** {failure.error_message}

## Traceback
```
{failure.traceback}
```

## Test Code
```python
{test_code}
```

## Source Code Being Tested
```python
{source_code}
```

## Task
Analyze this failure and determine:
1. Is this a **test_mistake** (error in test code) or **code_bug** (error in source code)?
2. Why?
3. If it's a test_mistake, provide the fixed test code.

Respond with JSON only."""

        return prompt
