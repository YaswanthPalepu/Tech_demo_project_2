#!/usr/bin/env python3
"""
Decide constraints for arbitrary repos.
- If repo pins old Flask stack (Flask<2.3 or Flask-SQLAlchemy<3 or Werkzeug<2.3 or SQLAlchemy<2)
  -> emit legacy constraints (fixes LocalStack.__ident_func__ errors)
- Else -> emit empty constraints (modern/default)
Writes:
  .constraints.txt   – pip constraints file
  .stack_mode.txt    – "legacy_flask" or "modern"
Prints chosen mode for logs.
"""
import os, re, sys, pathlib

ROOT = pathlib.Path(os.environ.get("TARGET_ROOT") or ".").resolve()

REQ_GLOBS = [
    "requirements.txt",
    "requirements/*.txt",
    "pyproject.toml",     # we only sniff (no export here)
    "Pipfile",            # sniff only
]

PIN_RE = re.compile(r"^\s*([A-Za-z0-9_.-]+)\s*([<>=!~]=.*?)?\s*(#.*)?$")

def _iter_req_lines():
    for pat in REQ_GLOBS:
        for p in ROOT.glob(pat):
            try:
                for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
                    yield p.name, line
            except Exception:
                pass

def _norm(name: str) -> str:
    return name.lower().replace("_","-")

def _wants_legacy(pins: dict) -> bool:
    """Heuristics for legacy Flask stack."""
    def vlt(name, major):
        pin = pins.get(name)
        if not pin: return False
        # quick and permissive check
        return any(s in pin for s in (f"<{major}", f"=={major-1}."))

    # If any *explicit* pin forces the old stack, use legacy
    if vlt("flask", 2.3) or vlt("werkzeug", 2.3) or vlt("flask-sqlalchemy", 3) or vlt("sqlalchemy", 2):
        return True

    # If Flask-SQLAlchemy is present but *explicitly modern*, prefer modern
    if pins.get("flask-sqlalchemy") and (">=3" in pins["flask-sqlalchemy"] or "==3." in pins["flask-sqlalchemy"]):
        return False
    if pins.get("sqlalchemy") and (">=2" in pins["sqlalchemy"] or "==2." in pins["sqlalchemy"]):
        return False

    # If the repo *mentions* flask_sqlalchemy in code and no modern pins detected, be conservative? -> NO.
    # Default to modern unless old pins are found (safer for new apps).
    return False

def sniff_pins() -> dict:
    pins = {}
    for fn, line in _iter_req_lines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        m = PIN_RE.match(s)
        if not m:
            continue
        name, spec, _ = m.groups()
        n = _norm(name)
        if n in {"-r","--requirement","--find-links","--extra-index-url","--index-url"}:
            continue
        if n not in pins:
            pins[n] = (spec or "").replace(" ", "")
    return pins

def write_constraints(mode: str, path: pathlib.Path):
    if mode == "legacy_flask":
        path.write_text(
            "\n".join([
                "Flask<2.3",
                "Werkzeug<2.3",
                "Flask-SQLAlchemy<3",
                "SQLAlchemy<2.0",
                "Jinja2<3.1",
                "itsdangerous<2.1",
                "click<8.1",
                "MarkupSafe<2.1",
                "",
            ]),
            encoding="utf-8",
        )
    else:
        # Modern/default: no pins (keep file empty but present)
        path.write_text("", encoding="utf-8")

def main():
    pins = sniff_pins()
    mode = "legacy_flask" if _wants_legacy(pins) else "modern"
    out = pathlib.Path(".constraints.txt").resolve()
    write_constraints(mode, out)
    pathlib.Path(".stack_mode.txt").write_text(mode, encoding="utf-8")
    print(f"[py-stack-guard] mode={mode} constraints={out}")
    # Export for later steps
    print(f"PIP_CONSTRAINT={out}", file=sys.stdout)
    # For your generator.py (it honors TESTGEN_PIP_CONSTRAINTS)
    print(f"TESTGEN_PIP_CONSTRAINTS={out}", file=sys.stdout)

if __name__ == "__main__":
    main()
