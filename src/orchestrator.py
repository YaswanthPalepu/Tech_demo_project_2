import argparse, sys
from pathlib import Path
from utils.file_utils import iter_files
from utils.language_support import detect_project
from analyzer import summarize_repo
from generator import generate_pytests
from validator import run_pytest_with_coverage, parse_coverage_xml
from coverage_analyzer import write_report
from quality_gates import check_minimum_coverage

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True)
    ap.add_argument("--use-ai", default="true", choices=["true","false"])
    ap.add_argument("--max-files", type=int, default=80)
    ap.add_argument("--min-coverage", type=int, default=60)
    ap.add_argument("--only-generated", default="false", choices=["true","false"])
    args = ap.parse_args()

    repo = Path(args.target).resolve()
    proj = detect_project(repo)
    if not proj or proj.name != "python":
        print("Non-Python or undetected project; generator is Python-only. Exiting.")
        sys.exit(0)

    py_files = iter_files(repo, max_files=args.max_files)
    analysis = summarize_repo(py_files)

    out_dir = repo / "tests" / "generated"
    created = generate_pytests(repo, analysis["files"], out_dir)

    artifacts = Path("artifacts")
    junit = artifacts / "test-results" / "junit.xml"
    covxml = artifacts / "coverage" / "coverage.xml"
    code, _ = run_pytest_with_coverage(repo, junit, covxml, only_generated=(args.only_generated=="true"))
    cov = parse_coverage_xml(covxml)
    line_rate = cov.get("line_rate", 0.0)

    ok = check_minimum_coverage(line_rate, args.min_coverage/100.0)
    write_report(artifacts / "report.json",
                 {"line_rate": line_rate},
                 f"Generated: {len(created)} files | Coverage: {line_rate*100:.1f}% | Exit: {code}")
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
