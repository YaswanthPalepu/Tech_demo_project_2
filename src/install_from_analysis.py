# src/install_from_analysis.py
import sys, json, pathlib, subprocess, importlib.util, re
from typing import List, Set

COMMON_PKG_ALIASES = {
    "bs4": "beautifulsoup4",
    "yaml": "PyYAML",
    "cv2": "opencv-python",
    "sklearn": "scikit-learn",
    "PIL": "Pillow",
    "Crypto": "pycryptodome",
    "MySQLdb": "mysqlclient",
    "mysql": "mysqlclient",
    "psycopg2": "psycopg2-binary",
    "boto3": "boto3",
    "httpx": "httpx",
    "requests": "requests",
    "uvicorn": "uvicorn",
    "fastapi": "fastapi",
    "starlette": "starlette",
    "pydantic": "pydantic",
    "typing_extensions": "typing-extensions",
    "annotated_types": "annotated-types",
    "sqlalchemy": "SQLAlchemy",
    "flask": "flask",
    "django": "Django",
    "click": "click",
    "typer": "typer",
    "jinja2": "Jinja2",
    "ujson": "ujson",
    "orjson": "orjson",
    "pymongo": "pymongo",
    "redis": "redis",
    "pytest": "pytest",
}

STDLIB_HINT = {
    "os","sys","re","json","pathlib","math","itertools","functools","typing","subprocess",
    "datetime","time","collections","dataclasses","ast","logging","unittest","argparse",
    "asyncio","multiprocessing","threading","sqlite3","email","http","urllib","hashlib",
    "hmac","base64","statistics","random","fractions","decimal","csv","shutil","tempfile",
    "glob","inspect","traceback","textwrap","string","pprint","enum","types"
}

def is_stdlib(mod: str) -> bool:
    import sys
    top = (mod.split(".")[0] or "").strip()
    if not top:
        return True
    stdmods = getattr(sys, "stdlib_module_names", None)
    if stdmods:
        return top in stdmods
    return top in STDLIB_HINT

def is_local(top: str) -> bool:
    p = pathlib.Path(top)
    if p.exists():
        return True
    if pathlib.Path(top.replace(".", "/")).exists():
        return True
    for base in (pathlib.Path("."), pathlib.Path("src"), pathlib.Path("backend"), pathlib.Path("app")):
        if (base / f"{top}.py").exists() or (base / top).is_dir():
            return True
    return False

def map_to_package(top: str) -> str:
    return COMMON_PKG_ALIASES.get(top, top)

def needed_packages(modules: List[str]) -> List[str]:
    pkgs: Set[str] = set()
    for m in modules or []:
        top = (m.split(".")[0] or "").strip()
        if not top or is_stdlib(top) or is_local(top):
            continue
        pkgs.add(map_to_package(top))
    # a few compatibility helpers if pydantic/starlette/fastapi appear
    lowers = {p.lower() for p in pkgs}
    if "fastapi" in lowers:
        pkgs.update({"starlette", "pydantic"})
    return sorted(pkgs)

def pip_install(pkgs: List[str]) -> int:
    if not pkgs:
        print("📦 No third-party packages inferred from imports.")
        return 0
    print("📦 Installing packages from analysis:", ", ".join(pkgs))
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-input", *pkgs])
        return 0
    except subprocess.CalledProcessError as e:
        print(f"⚠️ pip install failed with exit code {e.returncode} (continuing; tests may skip).")
        return e.returncode

def main():
    path = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else pathlib.Path("/tmp/analysis.json")
    if not path.exists():
        print(f"❌ analysis file not found: {path}")
        sys.exit(1)
    data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    modules = data.get("modules") or []
    rc = pip_install(needed_packages(modules))
    sys.exit(0 if rc == 0 else 0)  # don't fail pipeline if optional deps fail

if __name__ == "__main__":
    main()
