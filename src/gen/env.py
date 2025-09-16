import os, pathlib
from typing import Optional

REPO_ROOT = pathlib.Path(".").resolve()
PROMPT_STYLE = os.getenv("TESTGEN_PROMPT_STYLE", "ultra_bare").strip().lower()
STRICT_FAIL = os.getenv("TESTGEN_STRICT_FAIL", "0").lower() in ("1","true","yes")

def get_any_env(*names: str) -> str:
    for n in names:
        v = os.getenv(n)
        if v:
            return v
    raise RuntimeError(f"Missing required environment variable (tried: {', '.join(names)})")

def norm_rel(p: str) -> str:
    try:
        pp = pathlib.Path(p)
        if pp.is_absolute():
            try:
                pp = pp.resolve().relative_to(REPO_ROOT)
            except Exception:
                pass
        s = str(pp.as_posix())
    except Exception:
        s = str(p).replace("\\", "/")
    if s.startswith("./"): s = s[2:]
    if s.startswith("target/"): s = s[len("target/"):]
    return s

def load_list(path: Optional[str]):
    if not path: return None
    p = pathlib.Path(path)
    if not p.exists(): return None
    import json
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return [str(x) for x in data] if isinstance(data, list) else None
    except Exception:
        return None
