import os, re, ast, json, pathlib, datetime, time
from typing import Dict, Any, List, Optional, Set

__all__ = ["generate_all"]

# --- lazy postprocess import with fallbacks to avoid hard import failures at module import time
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
    # local import to avoid module-level failures
    from .conftest_text import conftest_text
    from .writer import write_text
    p = outdir / "conftest.py"
    write_text(p, conftest_text())
    return str(p)

def _gen_validated(messages, attempts=3, backoff=(3,7,15)):
    # local import to avoid module-level failures
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
                    base = skip_brittle_functions(cleaned)
                    base = header_guard_banned(base)
                    post = massage(base)
                    ok2, r2 = validate_code(post)
                    if ok2:
                        return post
                    print(f"↩️ postprocess broke syntax, using base: {r2}")
                    ok3, r3 = validate_code(base)
                    if ok3:
                        return base
                    reason = f"post-process and base validation failed: {r2} / {r3}"
                messages.append({"role":"user","content":
                                 f"Invalid: {reason}. Regenerate strict pytest code only. "
                                 f"Guard imports; prefer parametrize; no custom fixtures."})
                break
            except RateLimitError:
                if sleep_s < backoff[-1]:
                    continue
                else:
                    break
            except Exception as e:
                print(f"⚠️ gen attempt {attempt} error: {e}")
                break
    raise RuntimeError(f"LLM generation failed after {attempts} attempts: {reason}")

def generate_all(analysis: Dict[str, Any], outdir="tests/generated", focus_files: Optional[List[str]] = None):
    # local imports to prevent import errors from blocking symbol export
    from . import env
    from .change import detect_changes
    from .analysis_utils import (
        compact_analysis, filter_by_files, infer_required_packages, pip_install,
        prune_unavailable_targets,
    )
    from .prompt import build_prompt, files_per_kind, focus_for, runtime_guard
    from .writer import write_text, cleanup_deleted_and_modified, update_manifest

    out = pathlib.Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    manifest = out / "_manifest.json"

    print("📝 Creating conftest.py...")
    _create_conftest(out)

    target_root = pathlib.Path(os.environ.get("TARGET_ROOT", "target"))

    # detect_changes returns: (deleted, added_or_modified, unchanged_bool)
    deleted, added_or_modified, unchanged = detect_changes(target_root, manifest)

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

    # Filter, compact, then prune targets that require unavailable GUI/heavy libs
    filtered, _ = filter_by_files(analysis, raw_focus if raw_focus else None)
    compact = compact_analysis(filtered)
    before = sum(len(compact.get(k,[])) for k in ("functions","classes","routes"))
    compact = prune_unavailable_targets(compact)
    after = sum(len(compact.get(k,[])) for k in ("functions","classes","routes"))
    if after < before:
        print(f"⏭️  Pruned {before - after} targets requiring unavailable GUI/heavy libs")

    # Install inferred deps to help imports in generated tests
    pkgs = infer_required_packages(compact)
    if pkgs:
        print("📦 Installing inferred packages…")
        pip_install(pkgs)

    compact_json = json.dumps(compact, separators=(",",":"))
    created: List[str] = []

    total_targets = sum(len(compact.get(k,[])) for k in ("functions","classes","routes"))
    if total_targets == 0:
        raise RuntimeError("No test targets found in analysis.")

    # decide kinds and purge stale e2e when no routes
    has_routes = bool(compact.get("routes"))
    if not has_routes:
        for p in out.glob("test_e2e_*.py"):
            try: p.unlink()
            except Exception: pass
    kinds = ["unit","integ"] if not has_routes else ["unit","integ","e2e"]

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
            ast.parse(final_code, filename=fname)
            path = out / fname
            write_text(path, final_code)
            created.append(str(path))

    if os.getenv("GENERATED_LIST_PATH"):
        try:
            pathlib.Path(os.getenv("GENERATED_LIST_PATH")).write_text(json.dumps(created, indent=2), encoding="utf-8")
        except Exception:
            pass

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
