# src/gen/generate.py
import os, re, ast, json, pathlib, datetime, time, argparse
from typing import Dict, Any, List, Optional, Set

__all__ = ["generate_all", "main"]

try:
    from .postprocess import (
        extract_python_only, validate_code, skip_brittle_functions, header_guard_banned, massage
    )
except Exception as _e:
    print(f"⚠️ postprocess import failed: {_e}; using minimal fallbacks")
    import re as _re, ast as _ast
    def extract_python_only(text: str) -> str:
        if "```" in text:
            blocks = _re.findall(r"```(?:python)?\s*(.*?)```", text, flags=_re.IGNORECASE|_re.DOTALL)
            text = "\n\n".join(blocks) if blocks else text.replace("```","")
        return text
    def validate_code(code: str):
        if not code.strip(): return False, "empty output"
        if not _re.search(r"^\s*def\s+test_[A-Za-z0-9_]*\s*\(", code, _re.MULTILINE):
            return False, "no test_ functions found"
        try: _ast.parse(code); return True, ""
        except SyntaxError as e: return False, f"syntax error: {e}"
    def skip_brittle_functions(code: str): return code
    def header_guard_banned(code: str): return code
    def massage(code: str): return code

def _create_conftest(outdir: pathlib.Path) -> str:
    from .conftest_text import conftest_text
    from .writer import write_text
    p = outdir / "conftest.py"
    write_text(p, conftest_text())
    return str(p)

def _gen_validated(messages, attempts=3, backoff=(3,7,15)):
    from .openai_client import client, deployment_name, chat_completion_create, RateLimitError
    cli = client()
    dep = deployment_name()
    reason = "unknown"
    for attempt in range(1, attempts+1):
        for sleep_s in (0, *backoff):
            try:
                if sleep_s: time.sleep(sleep_s)
                resp = chat_completion_create(cli, dep, messages)
                raw = resp.choices[0].message.content or ""
                cleaned = extract_python_only(raw)
                ok, reason = validate_code(cleaned)
                if ok:
                    base = header_guard_banned(skip_brittle_functions(cleaned))
                    post = massage(base)
                    ok2, r2 = validate_code(post)
                    if ok2: return post
                    ok3, r3 = validate_code(base)
                    if ok3: return base
                    reason = f"post-process and base validation failed: {r2} / {r3}"
                messages.append({"role":"user","content":
                                 "Invalid: {reason}. Regenerate strict pytest code only. "
                                 "Guard imports; prefer parametrize; no custom fixtures."})
                break
            except RateLimitError:
                if sleep_s < backoff[-1]: continue
                else: break
            except Exception as e:
                print(f"⚠️ gen attempt {attempt} error: {e}")
                break
    raise RuntimeError(f"LLM generation failed after {attempts} attempts: {reason}")

def generate_all(analysis: Dict[str, Any], outdir="tests/generated", focus_files: Optional[List[str]] = None):
    from . import env
    from .change import detect_changes
    from .analysis_utils import compact_analysis, filter_by_files, infer_required_packages, pip_install, prune_unavailable_targets
    from .prompt import build_prompt, files_per_kind, focus_for, runtime_guard
    from .writer import write_text, cleanup_deleted_and_modified, update_manifest

    out = pathlib.Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    manifest = out / "_manifest.json"

    print("📝 Creating conftest.py...")
    _create_conftest(out)

    target_root = pathlib.Path(os.environ.get("TARGET_ROOT", "target"))

    # Correct order: (added_or_modified, deleted, unchanged)
    added_or_modified, deleted, unchanged = detect_changes(target_root, manifest)

    summary = {
        "added_or_modified": len(added_or_modified),
        "deleted": len(deleted),
        "no_changes": bool(unchanged),
        "files_analyzed": len(added_or_modified)+len(deleted),
    }
    print(f"📊 Changes: +/Δ={summary['added_or_modified']}  −={summary['deleted']}  no_changes={summary['no_changes']}")

    force = os.getenv("TESTGEN_FORCE","false").lower() == "true"
    if not force and unchanged:
        if list(out.rglob("test_*.py")):
            print("✅ No code changes and tests exist. Skipping generation.")
            return
        else:
            print("📝 No tests found. Will attempt initial generation.")
    if force:
        print("🔧 Force generation enabled.")

    cleanup_deleted_and_modified(out, deleted, added_or_modified)

    ts = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
    raw_focus: Set[str] = set(focus_files or env.load_list(os.getenv("FOCUS_FILES_JSON_PATH")) or [])
    if not raw_focus and not force:
        raw_focus = set(added_or_modified)

    filtered, _ = filter_by_files(analysis, raw_focus if raw_focus else None)
    compact = prune_unavailable_targets(compact_analysis(filtered))

    pkgs = infer_required_packages(compact)
    if pkgs:
        print("📦 Installing inferred packages…")
        pip_install(pkgs)

    compact_json = json.dumps(compact, separators=(",",":"))
    created: List[str] = []

    total_targets = sum(len(compact.get(k,[])) for k in ("functions","classes","routes"))
    if total_targets == 0:
        raise RuntimeError("No test targets found in analysis.")

    has_routes = bool(compact.get("routes"))
    if not has_routes:
        for p in out.glob("test_e2e_*.py"):
            try: p.unlink()
            except Exception: pass
    kinds = ["unit","integ"] if not has_routes else ["unit","integ","e2e"]

    header = runtime_guard(compact)
    for kind in kinds:
        nfiles = files_per_kind(compact, kind)
        if nfiles <= 0:
            print(f"⚠️ No targets for {kind}; skipping.")
            continue
        print(f"🔧 Generating {nfiles} {kind} files…")
        for i in range(nfiles):
            label, _ = focus_for(compact, kind, i, nfiles)
            msgs = build_prompt(kind, compact_json, label, i+1, nfiles, compact)
            code = _gen_validated(msgs)

            # Only prepend our header if the model did not already emit one
            already_guarded = bool(re.search(r"TARGET_ROOT|pytest\.skip\(.*allow_module_level=True\)", code))
            final_code = code if already_guarded else (header + code)

            fname = f"test_{kind}_{ts}_{i+1:02d}.py"
            ast.parse(final_code, filename=fname)  # fail fast if broken
            write_text(out / fname, final_code)
            created.append(str(out / fname))

    update_manifest(out, created, summary)
    print(f"✅ Generated {len(created)} test files" if created else "ℹ️ No tests generated.")

def main():
    ap = argparse.ArgumentParser(description="Generate pytest suites via Azure OpenAI.")
    ap.add_argument("--target", default="target", help="Path to the Python project to test")
    ap.add_argument("--outdir", default="tests/generated", help="Where to write tests")
    ap.add_argument("--focus-json", default=os.getenv("FOCUS_FILES_JSON_PATH",""), help="Optional JSON list of files to focus")
    ap.add_argument("--force", action="store_true", help="Force generation even if unchanged")
    args = ap.parse_args()

    if args.force: os.environ["TESTGEN_FORCE"] = "true"
    os.environ["TARGET_ROOT"] = args.target

    try:
        try:
            import src.analyzer as analyzer
        except Exception:
            import analyzer
        analysis = analyzer.analyze_python_tree(pathlib.Path(args.target))
    except Exception as e:
        raise RuntimeError(f"Analyzer import/run failed: {e}") from e

    if args.focus_json:
        os.environ["FOCUS_FILES_JSON_PATH"] = args.focus_json

    generate_all(analysis, outdir=args.outdir)
    print(f"✅ Generated tests in {args.outdir}")

if __name__ == "__main__":
    main()
