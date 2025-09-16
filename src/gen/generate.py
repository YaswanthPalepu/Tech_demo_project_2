import os, re, ast, json, pathlib, datetime, time
from typing import Dict, Any, List, Optional, Set
from . import env
from .change import detect_changes
from .analysis_utils import compact_analysis, filter_by_files, infer_required_packages, pip_install
from .conftest_text import conftest_text
from .prompt import build_prompt, files_per_kind, focus_for, runtime_guard
from .postprocess import extract_python_only, validate_code, skip_brittle_functions, header_guard_banned, massage
from .openai_client import client, deployment_name, chat_completion_create, RateLimitError
from .writer import write_text, cleanup_deleted_and_modified, update_manifest

def _create_conftest(outdir: pathlib.Path) -> str:
    p = outdir / "conftest.py"
    write_text(p, conftest_text())
    return str(p)

def _gen_validated(messages, attempts=3, backoff=(3,7,15)):
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
                    code = skip_brittle_functions(cleaned)
                    code = header_guard_banned(code)
                    code = massage(code)
                    ok2, r2 = validate_code(code)
                    if ok2: return code
                    reason = f"post-process validation failed: {r2}"
                messages.append({"role":"user","content":f"Invalid: {reason}. Regenerate strict pytest code only. Guard imports; prefer parametrize; no custom fixtures."})
                break
            except RateLimitError:
                if sleep_s < backoff[-1]: continue
                else: break
            except Exception as e:
                print(f"⚠️ gen attempt {attempt} error: {e}")
                break
    raise RuntimeError(f"LLM generation failed after {attempts} attempts: {reason}")

def generate_all(analysis: Dict[str, Any], outdir="tests/generated", focus_files: Optional[List[str]] = None):
    out = pathlib.Path(outdir)
    manifest = out / "_manifest.json"

    print("📝 Creating conftest.py...")
    _create_conftest(out)

    target_root = pathlib.Path(os.environ.get("TARGET_ROOT", "target"))
    added_or_modified, deleted, unchanged = detect_changes(target_root, manifest)
    summary = {
        "added_or_modified": len(added_or_modified),
        "deleted": len(deleted),
        "unchanged": len(unchanged),
        "files_analyzed": len(added_or_modified)+len(deleted)+len(unchanged),
    }
    print(f"📊 Changes: +/Δ={summary['added_or_modified']}  −={summary['deleted']}  = {summary['unchanged']}")

    force = os.getenv("TESTGEN_FORCE","false").lower() == "true"
    if not force and not added_or_modified and not deleted and unchanged:
        if list(out.rglob("test_*.py")):
            print("✅ No code changes and tests exist. Skipping generation.")
            return
        else:
            print("📝 No tests found. Will attempt initial generation.")
    elif not force and not added_or_modified and not deleted:
        print("✅ No code changes. Skipping generation.")
        return
    if force: print("🔧 Force generation enabled.")

    cleanup_deleted_and_modified(out, deleted, added_or_modified)

    ts = datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")
    raw_focus: Set[str] = set(focus_files or env.load_list(os.getenv("FOCUS_FILES_JSON_PATH")) or [])
    if not raw_focus and not force: raw_focus = added_or_modified

    # filter analysis by changed files
    filtered, _ = filter_by_files(analysis, raw_focus if raw_focus else None)
    compact = compact_analysis(filtered)

    # install third-party requirements inferred from imports
    pkgs = infer_required_packages(compact)
    if pkgs:
        print("📦 Installing inferred packages…")
        pip_install(pkgs)

    compact_json = json.dumps(compact, separators=(",",":"))
    kinds = ["unit","integ","e2e"]
    created: List[str] = []

    total_targets = len(compact.get("functions",[])) + len(compact.get("classes",[])) + len(compact.get("routes",[]))
    if total_targets == 0:
        raise RuntimeError("No test targets found in analysis.")

    for kind in kinds:
        nfiles = files_per_kind(compact, kind)
        if nfiles <= 0:
            print(f"⚠️ No targets for {kind}; skipping.")
            continue
        print(f"🔧 Generating {nfiles} {kind} files…")
        for i in range(nfiles):
            label, _names = focus_for(compact, kind, i, nfiles)
            guard = runtime_guard(compact)
            msgs = build_prompt(kind, compact_json, label, i+1, nfiles, compact)
            code = _gen_validated(msgs)
            fname = f"test_{kind}_{ts}_{i+1:02d}.py"
            final_code = guard + code
            ast.parse(final_code, filename=fname)  # safety check
            path = out / fname
            write_text(path, final_code)
            created.append(str(path))

    if os.getenv("GENERATED_LIST_PATH"):
        try:
            pathlib.Path(os.getenv("GENERATED_LIST_PATH")).write_text(json.dumps(created, indent=2), encoding="utf-8")
        except Exception: pass

    update_manifest(out, created, summary)
    if created:
        print(f"✅ Generated {len(created)} test files")
        if added_or_modified:
            print(f"   focused on {len(added_or_modified)} changed files")
    else:
        print("ℹ️ No tests generated.")

if __name__ == "__main__":
    try:
        try:
            import src.analyzer as analyzer  # type: ignore
        except Exception:
            import analyzer  # type: ignore
        analysis = analyzer.analyze_python_tree(pathlib.Path("."))
    except Exception as e:
        raise RuntimeError(f"Analyzer import/run failed: {e}") from e
    generate_all(analysis)
    print("✅ Generated tests in tests/generated")
