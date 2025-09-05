import os
from typing import Optional, Dict, Any
from openai import AzureOpenAI

_DEV_GUARDRAILS = (
    "Style: clean, developer-like tests; pytest idioms (fixtures, parametrization); "
    "No sleeps; no external IO/network; Deterministic; Meaningful assertions."
)

class AzureProvider:
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

    def _chat(self, sys_prompt: str, user_prompt: str, temperature: float = 0.2) -> Optional[str]:
        if not self.available():
            return None
        resp = self.client.chat.completions.create(
            model=self.deployment,
            messages=[{"role":"system","content":sys_prompt},{"role":"user","content":user_prompt}],
            temperature=temperature,
        )
        return resp.choices[0].message.content if resp and resp.choices else None

    # Unit
    def gen_unit(self, module_name: str, file_path: str, code: str, analysis: dict) -> Optional[str]:
        sys_prompt = "Generate high-quality UNIT tests with pytest. " + _DEV_GUARDRAILS
        user = f"""Module: {module_name}
File path: {file_path}

Code:
```python
{code}
```

Analysis (JSON):
```json
{analysis}
```

Constraints:
- Cover core logic and edge cases; prefer parametrization
- No external I/O; no sleeps; deterministic
- Output ONLY Python test code (no backticks)
"""
        return self._chat(sys_prompt, user, temperature=0.2)

    # Integration
    def gen_integration(self, kind: str, context: Dict[str, Any]) -> Optional[str]:
        kind = (kind or "generic").lower()
        if kind == "fastapi":
            sys = "Generate pytest INTEGRATION tests for a FastAPI app. " + _DEV_GUARDRAILS
            hint = "Use fastapi.testclient.TestClient; accept 2xx/3xx/4xx; fail only on 5xx."
        elif kind == "flask":
            sys = "Generate pytest INTEGRATION tests for a Flask app. " + _DEV_GUARDRAILS
            hint = "Use app.test_client(); accept 2xx/3xx/4xx; fail only on 5xx."
        elif kind == "django":
            sys = "Generate pytest-django INTEGRATION tests for a Django app. " + _DEV_GUARDRAILS
            hint = "Use django.test.Client; assume DJANGO_SETTINGS_MODULE is set in conftest."
        elif kind in {"click","typer"}:
            sys = "Generate pytest INTEGRATION tests for a CLI (Click/Typer). " + _DEV_GUARDRAILS
            hint = "Use click.testing.CliRunner or Typer's runner; assert exit_code==0; test --help."
        elif kind == "argparse":
            sys = "Generate pytest INTEGRATION tests for an argparse CLI. " + _DEV_GUARDRAILS
            hint = "Call main([...]) with monkeypatched sys.argv; assert exit code or output."
        else:
            sys = "Generate pytest INTEGRATION tests for a generic Python module. " + _DEV_GUARDRAILS
            hint = "Exercise public functions together; avoid I/O; prefer meaningful assertions."
        user = f"""HINT: {hint}
Context (JSON):
```json
{context}
```
Output ONLY Python test code.
"""
        return self._chat(sys, user, temperature=0.2)

    # E2E
    def gen_e2e(self, kind: str, context: Dict[str, Any]) -> Optional[str]:
        kind = (kind or "generic").lower()
        if kind == "fastapi":
            sys = "Generate pytest E2E flows for a FastAPI app. " + _DEV_GUARDRAILS
            hint = "Prefer POST->GET on same collection; else smoke GETs."
        elif kind == "flask":
            sys = "Generate pytest E2E flows for a Flask app. " + _DEV_GUARDRAILS
            hint = "Smoke-flow across important routes with app.test_client()."
        elif kind == "django":
            sys = "Generate pytest-django E2E flows for a Django app. " + _DEV_GUARDRAILS
            hint = "Build a small smoke flow across key pages with django.test.Client."
        elif kind in {"click","typer"}:
            sys = "Generate pytest E2E flows for a CLI (Click/Typer). " + _DEV_GUARDRAILS
            hint = "Use CliRunner on main command; chain subcommands if obvious; assert exit_code==0."
        elif kind == "argparse":
            sys = "Generate pytest E2E flows for an argparse CLI. " + _DEV_GUARDRAILS
            hint = "Invoke main([...]) with args; assert outputs and exit code."
        else:
            sys = "Generate pytest E2E flows for a generic Python module. " + _DEV_GUARDRAILS
            hint = "Exercise multi-function scenarios end-to-end within process; no external I/O."
        user = f"""HINT: {hint}
Context (JSON):
```json
{context}
```
Output ONLY Python test code.
"""
        return self._chat(sys, user, temperature=0.2)
