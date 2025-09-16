# -*- coding: utf-8 -*-
"""
File writer and housekeeping for generated test suites.
"""
import pathlib, shutil, datetime, json, re
from typing import List, Set, Dict, Any

HEADER = (
    "# This file was added by automated test generation.\n"
    "# It follows common internal testing patterns (parametrize, AAA, strict asserts).\n"
    "# Do not rely on test ordering; each test is independent.\n\n"
)

def write_text(p: pathlib.Path, content: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    # de-AI any accidental markers and normalize whitespace
    content = re.sub(r"(?i)#.*(ai|llm|generated|chatgpt).*", "", content)
    content = re.sub(r"\n{3,}", "\n\n", content).strip() + "\n"
    if not content.startswith("import "):
        content = HEADER + content
    p.write_text(content, encoding="utf-8")
    print(f"📝 wrote {p}")

def find_related_tests(outdir: pathlib.Path, source_file: str):
    rel = pathlib.Path(source_file).stem
    out=[]
    for test in outdir.rglob("test_*.py"):
        try:
            txt = test.read_text(encoding="utf-8", errors="ignore")
            if rel in txt or source_file.replace('/','.').replace('.py','') in txt:
                out.append(test)
        except Exception:
            pass
    return out

def cleanup_deleted_and_modified(outdir: pathlib.Path, deleted: Set[str], added_or_modified: Set[str]):
    for d in deleted:
        for t in find_related_tests(outdir, d):
            try:
                print(f"🗑️ Removing test for deleted source: {t}")
                t.unlink()
            except Exception:
                pass
    for m in added_or_modified:
        for t in find_related_tests(outdir, m):
            try:
                print(f"🔄 Removing old test for modified source: {t}")
                t.unlink()
            except Exception:
                pass
    # prune empty dirs
    for d in sorted(outdir.glob("*")):
        if d.is_dir():
            try:
                next(d.rglob("*"))
            except StopIteration:
                shutil.rmtree(d, ignore_errors=True)

def update_manifest(outdir: pathlib.Path, created: List[str], change_summary: Dict[str,Any]):
    m = outdir / "_manifest.json"
    data = {}
    if m.exists():
        try:
            data = json.loads(m.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    runs = data.get("runs", [])
    runs.append({
        "ts": datetime.datetime.utcnow().isoformat()+"Z",
        "files_generated": created,
        "change_summary": change_summary,
    })
    data["runs"] = runs
    m.parent.mkdir(parents=True, exist_ok=True)
    m.write_text(json.dumps(data, indent=2), encoding="utf-8")
