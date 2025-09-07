# src/diffscan.py
import argparse, hashlib, json, os, pathlib, sys

IGNORE_DIRS = {"tests/generated", ".venv", "venv", ".git", "__pycache__"}

def _iter_py_files(root: pathlib.Path):
    for p in root.rglob("*.py"):
        parts = set(p.parts)
        if parts & IGNORE_DIRS:
            continue
        # Skip our generated tests
        if "tests" in parts and "generated" in parts:
            continue
        yield p

def _sha256(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help="project root to scan")
    ap.add_argument("--manifest", required=True, help="existing manifest path (JSON) to compare against")
    ap.add_argument("--out-changed", required=True, help="write JSON list of changed file paths")
    ap.add_argument("--out-hashes", required=True, help="write JSON of {path: sha256} for all source files")
    args = ap.parse_args()

    root = pathlib.Path(args.root).resolve()
    manifest_path = pathlib.Path(args.manifest)
    out_changed = pathlib.Path(args.out_changed)
    out_hashes = pathlib.Path(args.out_hashes)

    # Load previous manifest if any
    prev = {}
    if manifest_path.exists():
        try:
            prev = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            prev = {}
    prev_hashes = (prev or {}).get("source_hashes", {})

    # Current hashes
    cur_hashes = {}
    for p in _iter_py_files(root):
        try:
            cur_hashes[str(p)] = _sha256(p)
        except Exception:
            # If a file can't be read, treat it as changed by adding a dummy hash
            cur_hashes[str(p)] = "ERR"

    # Changed/new files = path not in prev or hash differs
    changed = [p for p, h in cur_hashes.items() if prev_hashes.get(p) != h]

    out_hashes.parent.mkdir(parents=True, exist_ok=True)
    out_changed.parent.mkdir(parents=True, exist_ok=True)
    out_hashes.write_text(json.dumps(cur_hashes, indent=2), encoding="utf-8")
    out_changed.write_text(json.dumps(changed, indent=2), encoding="utf-8")

    print(f"Found {len(changed)} changed .py files")

if __name__ == "__main__":
    main()
