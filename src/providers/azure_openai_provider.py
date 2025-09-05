import os
from typing import Optional
from openai import AzureOpenAI

class AzureProvider:
    """Thin wrapper around Azure OpenAI client. Returns None if not configured."""
    def __init__(self):
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        api_version = os.getenv("AZURE_OPENAI_API_VERSION") or "2024-06-01"
        deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")
        if not (api_key and endpoint and deployment):
            self.client = None
            self.deployment = None
            return
        self.client = AzureOpenAI(api_key=api_key, api_version=api_version, azure_endpoint=endpoint)
        self.deployment = deployment

    def available(self) -> bool:
        return self.client is not None and self.deployment is not None

    def generate_pytest(self, file_path: str, code: str, analysis: dict) -> Optional[str]:
        """Ask the model to produce focused, runnable pytest tests (unit tests)."""
        if not self.available():
            return None

        sys_prompt = (
            "You are an expert software engineer generating high-quality pytest tests. "
            "Rules: 1) Produce a single file of pytest tests, no explanations; "
            "2) Import from the module under test using relative imports when needed; "
            "3) Avoid flaky/external I/O; 4) Use parametrization where useful; "
            "5) If functions are pure, test edge cases; 6) If there is FastAPI, use TestClient."
        )

        user_prompt = f"""
Generate UNIT pytest tests for the following Python file.

FILE PATH (relative to repo root):
{file_path}

CODE:
```python
{code}
```

ANALYSIS (JSON):
```json
{analysis}
```

Return only valid Python test code.
"""
        resp = self.client.chat.completions.create(
            model=self.deployment,
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.2,
        )
        return resp.choices[0].message.content if resp and resp.choices else None
