import os
from pathlib import Path
from typing import Iterable, List

PY_EXT = {".py"}

def iter_files(root: str | os.PathLike, exts: Iterable[str] = PY_EXT, max_files: int | None = None) -> List[Path]:
    root = Path(root)
    out = []
    for p in root.rglob("*"):
        if p.is_file() and p.suffix in exts:
            out.append(p)
            if max_files and len(out) >= max_files:
                break
    return out

def ensure_dir(path: str | os.PathLike) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p
