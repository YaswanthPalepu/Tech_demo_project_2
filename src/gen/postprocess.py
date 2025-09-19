import re, ast

__all__ = [
    "extract_python_only",
    "validate_code",
    "skip_brittle_functions",
    "header_guard_banned",
    "massage",
]

# Pull only Python blocks if the model returned markdown
def extract_python_only(text: str) -> str:
    if "```" in text:
        blocks = re.findall(r"```(?:python)?\s*(.*?)```", text, flags=re.IGNORECASE|re.DOTALL)
        if blocks:
            return "\n\n".join(blocks)
        return text.replace("```","")
    return text

def validate_code(code: str):
    if not code.strip():
        return False, "empty output"
    # must have at least one test_ function
    if not re.search(r"^\s*def\s+test_[A-Za-z0-9_]*\s*\(", code, re.MULTILINE):
        return False, "no test_ functions found"
    try:
        ast.parse(code)
        return True, ""
    except SyntaxError as e:
        return False, f"syntax error: {e}"

# You can extend this to drop tests that require network/GUI, but keep it simple
def skip_brittle_functions(code: str) -> str:
    return code

def header_guard_banned(code: str) -> str:
    # Remove generator-inserted hard-skips or private _pytest usage
    code = re.sub(r"^\s*_pytest\.skip\(.*?\)\s*$", "", code, flags=re.MULTILINE)
    code = re.sub(r"\b_pytest\b", "pytest", code)
    code = code.replace("pytest._code", "pytest")
    return code

def massage(code: str) -> str:
    # Ensure pytest import exists if referenced
    if "pytest" in code and not re.search(r"^\s*import\s+pytest\b", code, re.MULTILINE):
        code = "import pytest\n" + code
    return code
