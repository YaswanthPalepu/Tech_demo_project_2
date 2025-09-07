import os, json, pathlib, datetime
from typing import Dict, Any
from openai import AzureOpenAI

SYSTEM = """You are an expert Python test engineer.
Generate runnable pytest tests.
Rules:
- Output ONLY Python code.
- Use deterministic data.
- Prefer pytest + requests/httpx + FastAPI TestClient when app detected.
- Do not call external networks; mock I/O.
- Only import modules that exist in analysis.
- If unsure, emit a test_placeholder that always passes.
"""

UNIT_USER_TEMPLATE = """Analysis JSON:
{analysis}

Write focused UNIT tests for discovered functions/classes (max 12 tests).
"""

INTEG_USER_TEMPLATE = """Analysis JSON:
{analysis}

Write INTEGRATION tests for FastAPI routes or modules with side effects.
"""

E2E_USER_TEMPLATE = """Analysis JSON:
{analysis}

Write E2E tests covering full workflows (auth, CRUD).
"""

def _client() -> AzureOpenAI:
    return AzureOpenAI(
        api_key=os.getenv("AZURE_OPENAI_KEY"),
        api_version=os.getenv("AZURE_OPENAI_API_VERSION"),
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
    )

def _gen(code_prompt: str) -> str:
    client = _client()
    resp = client.chat.completions.create(
        model=os.getenv("AZURE_OPENAI_DEPLOYMENT", "prasad1972"),
        messages=[{"role":"system", "content":SYSTEM},
                  {"role":"user", "content":code_prompt}],
        temperature=0.1
    )
    return resp.choices[0].message.content

def write(path: pathlib.Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

def generate_all(analysis: Dict[str, Any], outdir="tests/generated"):
    out = pathlib.Path(outdir)
    ts = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
    unit = _gen(UNIT_USER_TEMPLATE.format(analysis=json.dumps(analysis)))
    write(out/f"test_unit_{ts}.py", unit)
    integ = _gen(INTEG_USER_TEMPLATE.format(analysis=json.dumps(analysis)))
    write(out/f"test_integ_{ts}.py", integ)
    e2e = _gen(E2E_USER_TEMPLATE.format(analysis=json.dumps(analysis)))
    write(out/f"test_e2e_{ts}.py", e2e)

if __name__ == "__main__":
    import analyzer, json
    analysis = analyzer.analyze_python_tree(pathlib.Path("."))
    generate_all(analysis)
    print("✅ Generated tests in tests/generated")
