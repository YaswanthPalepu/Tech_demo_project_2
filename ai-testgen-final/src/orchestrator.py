import argparse, sys
from pathlib import Path
from utils.file_utils import iter_files
from utils.language_support import detect_project
from analyzer import summarize_repo
from generator import generate_pytests

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True)
    ap.add_argument("--max-files", type=int, default=120)
    args = ap.parse_args()

    repo = Path(args.target).resolve()
    proj = detect_project(repo)
    if not proj or proj.name != "python":
        print("Non-Python or undetected project; generator is Python-only.")
        sys.exit(0)

    py_files = iter_files(repo, max_files=args.max_files)
    analysis = summarize_repo(py_files)

    out_dir = repo / "tests" / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)
    created = generate_pytests(repo, analysis["files"], out_dir)
    print(f"Generated {len(created)} test files under {out_dir}")

if __name__ == "__main__":
    main()
