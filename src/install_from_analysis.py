import sys, json, os, re, subprocess, pathlib

ALIASES = {
    "bs4": "beautifulsoup4",
    "yaml": "PyYAML",
    "cv2": "opencv-python",
    "sklearn": "scikit-learn",
    "pil": "Pillow",
    "pillow": "Pillow",
    "crypto": "pycryptodome",
    "mysql": "mysqlclient",
    "mysqldb": "mysqlclient",
    "psycopg2": "psycopg2-binary",
}

VALID_PIP_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")

DENY = {
    "__future__", "__main__", "__builtin__", "builtins", "typing", "types", "dataclasses", "importlib",
    "asyncio", "json", "re", "os", "sys", "pathlib", "logging", "argparse", "functools", "itertools",
    "collections", "subprocess", "datetime", "time", "math", "decimal", "fractions", "statistics",
    "sqlite3", "http", "urllib", "hmac", "hashlib", "base64", "csv", "glob", "shutil", "tempfile",
    "inspect", "traceback", "enum", "textwrap", "pprint", "string",
    # common py2 names that appear in legacy code
    "ConfigParser", "Queue", "HTMLParser", "StringIO",
}

def stdlib_set():
    s = set(getattr(sys, "stdlib_module_names", ()))  # Python 3.10+ has this
    # a few extras
    s.update(DENY)
    return s

def is_local(top: str, root: pathlib.Path) -> bool:
    return (root / (top + ".py")).exists() or (root / top).is_dir()

def main():
    if len(sys.argv) < 2:
        print("usage: python -m src.install_from_analysis /path/to/analysis.json [--root target]")
        sys.exit(0)
    analysis_path = pathlib.Path(sys.argv[1])
    root = pathlib.Path("target")
    if len(sys.argv) >= 4 and sys.argv[2] == "--root":
        root = pathlib.Path(sys.argv[3])

    data = json.loads(analysis_path.read_text())
    std = stdlib_set()

    mods = set(data.get("modules") or [])
    pkgs = set()
    for m in mods:
        top = (m.split(".")[0] or "").strip()
        if not top:
            continue
        if top in std:
            continue
        if top.startswith("_") or "__" in top:
            continue
        if any(c.isupper() for c in top):
            continue
        if not VALID_PIP_RE.match(top):
            continue
        if is_local(top, root):
            continue
        pkgs.add(ALIASES.get(top, top))

    if not pkgs:
        print("📦 No third-party packages inferred from imports.")
        return

    print("📦 Installing packages from filtered analysis:", ", ".join(sorted(pkgs)))
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-input", *sorted(pkgs)])
    except subprocess.CalledProcessError as e:
        print(f"⚠️ pip install failed with exit code {e.returncode} (continuing).")

if __name__ == "__main__":
    main()
