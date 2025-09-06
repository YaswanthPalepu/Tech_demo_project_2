import os
from typing import Optional, Dict, Any
from openai import AzureOpenAI

BASE_GUARDS = (
    "Write production-quality pytest modules. Prefer parametrization; use meaningful assertions; "
    "no sleeps, network, or disk I/O; deterministic; no test order coupling; avoid brittle mocks."
)

UNIT_SYS = "Generate high-signal UNIT tests for a Python module. " + BASE_GUARDS
INTEG_SYS = "Generate realistic INTEGRATION tests for Python apps (web/CLI/libs). " + BASE_GUARDS
E2E_SYS = "Generate small but effective E2E flows that could catch real defects. " + BASE_GUARDS

CRITERIA = """
Focus on defect-revealing tests:
- Explore boundary values, empty inputs, wrong types (where appropriate), and error branches.
- Assert exact outputs, state transitions, and raised exceptions.
- For web: use FastAPI TestClient / Flask test_client / Django Client as applicable.
- For CLI: use typer.testing.CliRunner or click.testing.CliRunner; argparse -> monkeypatch sys.argv.
- Avoid external I/O; use in-memory objects only.
- Keep each test independent; add helpful docstrings in tests.
Return ONLY Python test code.
"""

class AzureProvider:
    def __init__(self):
        key = os.getenv("AZURE_OPENAI_API_KEY")
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        ver = os.getenv("AZURE_OPENAI_API_VERSION") or "2024-06-01"
        deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT")
        if not (key and endpoint and deployment):
            self.client = None
            self.deployment = None
            return
        self.client = AzureOpenAI(api_key=key, api_version=ver, azure_endpoint=endpoint)
        self.deployment = deployment

    def available(self) -> bool:
        return self.client is not None and self.deployment is not None

    def _chat(self, system: str, user: str, temperature: float = 0.15) -> Optional[str]:
        if not self.available():
            return None
        resp = self.client.chat.completions.create(
            model=self.deployment,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            temperature=temperature,
        )
        if not resp or not resp.choices:
            return None
        return resp.choices[0].message.content

    def gen_unit(self, ctx: Dict[str, Any]) -> Optional[str]:
        module = ctx.get("module"); code = ctx.get("source_snippet","")[:12000]
        analysis = ctx
        user = f"""
Module: {module}

Code (truncated):
```python
{code}
```

Static analysis (JSON):
```json
{analysis}
```

{CRITERIA}
"""
        return self._chat(UNIT_SYS, user)

    def gen_integration(self, project_ctx: Dict[str, Any]) -> Optional[str]:
        user = f"""
Project context (JSON):
```json
{project_ctx}
```

{CRITERIA}
"""
        return self._chat(INTEG_SYS, user)

    def gen_e2e(self, project_ctx: Dict[str, Any]) -> Optional[str]:
        user = f"""
Project context (JSON):
```json
{project_ctx}
```

{CRITERIA}
"""
        return self._chat(E2E_SYS, user)
