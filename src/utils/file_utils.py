from pathlib import Path
from typing import Iterable, List

PY_EXT = {".py"}

def iter_files(root: Path, exts: Iterable[str] = PY_EXT, max_files: int | None = None) -> List[Path]:
    out = []
    for p in root.rglob("*"):
        if p.is_file() and p.suffix in exts:
            out.append(p)
            if max_files and len(out) >= max_files:
                break
    return out
