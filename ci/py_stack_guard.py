#!/usr/bin/env python3
"""
Repo-agnostic stack guard.

- Detects likely "legacy Flask/SQLAlchemy" stacks in the TARGET_ROOT
- Emits PIP_CONSTRAINT and TESTGEN_PIP_CONSTRAINTS pointing to .constraints.txt
- Writes .stack_mode.txt with either "legacy_flask" or "modern"

Heuristics are intentionally light so this works across many repos.
"""
from __future__ import annotations
import os, re, sys, json
from pathlib import Path

def read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""

def any_exists(paths):
    return any(Path(p).exists() for p in paths)

def find_target_root() -> Path:
    # Prefer explicit env, fall back to common names
    env = os.environ.get("TARGET_ROOT")
    if env:
        return Path(env).resolve()
    for cand in ("target_repo", "target"):
        p = Path(cand)
        if p.exists():
            return p.resolve()
    return Path(".").resolve()

def collect_requirement_text(root: Path) -> str:
    blobs = []
    files = [root / "requirements.txt"]
    files += list((root / "requirements").glob("*.txt"))
    files += [root / "pyproject.toml"]
    for f in files:
        if f.exists():
            blobs.append(read_text(f))
    return "\n".join(blobs)

def looks_legacy_flask(req: str, root: Path) -> bool:
    req_low = req.lower()

    # Simple markers in requirements/pyproject
    markers = [
        r"flask[<>=]\s*2\.2", r"flask[<]\s*2\.3",
        r"werkzeug[<]\s*2\.3",
        r"sqlalchemy[<]\s*2\.0",
        r"flask[-_]?sqlalchemy",  # any presence strongly hints legacy patterns
    ]
    if any(re.search(m, req_low) for m in markers):
        return True

    # Look for imports in source code (best-effort, cheap scan)
    for py in list(root.glob("**/*.py"))[:400]:  # cap to keep fast
        content = read_text(py)
        if "flask_sqlalchemy" in content or "from flask_sqlalchemy" in content:
            return True
        if re.search(r"\.query\.get\(", content):  # SA 1.x pattern
            return True

    return False

def main() -> int:
    repo_root = Path(".").resolve()
    target_root = find_target_root()
    constraints = repo_root / ".constraints.txt"

    req_blob = collect_requirement_text(target_root)
    legacy = looks_legacy_flask(req_blob, target_root)

    mode = "legacy_flask" if legacy and constraints.exists() else "modern"

    # Persist mode for the workflows to read
    (repo_root / ".stack_mode.txt").write_text(mode, encoding="utf-8")

    print(f"[py-stack-guard] mode={mode}", file=sys.stderr)
    if mode == "legacy_flask":
        print(f"[py-stack-guard] constraints={constraints}")
        # Only emit env exports if constraints file is present
        if constraints.exists():
            print(f"PIP_CONSTRAINT={constraints}")
            print(f"TESTGEN_PIP_CONSTRAINTS={constraints}")

    return 0

if __name__ == "__main__":
    sys.exit(main())
