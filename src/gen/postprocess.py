# src/gen/postprocess.py
import re, ast

__all__ = [
    "extract_python_only",
    "validate_code",
    "skip_brittle_functions",
    "header_guard_banned",
    "massage",
]

def extract_python_only(text: str) -> str:
    if "```" in text:
        blocks = re.findall(r"```(?:python)?\s*(.*?)```", text, flags=re.IGNORECASE|re.DOTALL)
        if blocks: return "\n\n".join(blocks)
        return text.replace("```","")
    return text

def validate_code(code: str):
    if not code.strip(): return False, "empty output"
    if not re.search(r"^\s*def\s+test_[A-Za-z0-9_]*\s*\(", code, re.MULTILINE):
        return False, "no test_ functions found"
    try:
        ast.parse(code); return True, ""
    except SyntaxError as e:
        return False, f"syntax error: {e}"

def skip_brittle_functions(code: str) -> str:
    return code

def header_guard_banned(code: str) -> str:
    code = re.sub(r"^\s*_pytest\.skip\(.*?\)\s*$", "", code, flags=re.MULTILINE)
    code = re.sub(r"\b_pytest\b", "pytest", code)
    code = code.replace("pytest._code", "pytest")
    return code

def _dedupe_imports(s: str) -> str:
    # Collapse duplicate identical import lines
    seen = set()
    out = []
    for line in s.splitlines():
        if re.match(r"^\s*(import|from)\s+", line):
            key = line.strip()
            if key in seen: continue
            seen.add(key)
        out.append(line)
    return "\n".join(out)

def _dedupe_framework_guards(s: str) -> str:
    # Keep a single consolidated block for importlib.util + pytest.skip guards
    pat = re.compile(
        r"(?:^|\n)import\s+importlib\.util,\s*pytest\s*\n"
        r"(?:\s*if\s+importlib\.util\.find_spec\('[^']+'\)\s+is\s+None:\s*\n"
        r"\s*pytest\.skip\('[^']+'\s*,\s*allow_module_level=True\)\s*\n?)+",
        flags=re.MULTILINE
    )
    blocks = pat.findall(s)
    if not blocks: return s
    # Keep only first block
    s = pat.sub("", s, count=0)
    s = blocks[0].strip() + "\n\n" + s.lstrip()
    return s

def _ensure_single_pytest_import(s: str) -> str:
    # Ensure exactly one 'import pytest' if referenced
    if "pytest" not in s: return s
    s = re.sub(r"^\s*import\s+pytest\s*$", "", s, flags=re.MULTILINE)
    return "import pytest\n" + s.lstrip()

def massage(code: str) -> str:
    code = _dedupe_framework_guards(code)
    code = _dedupe_imports(code)
    code = _ensure_single_pytest_import(code)
    # Trim extra blank lines
    code = re.sub(r"\n{3,}", "\n\n", code).strip() + "\n"
    return code
