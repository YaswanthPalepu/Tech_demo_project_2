import argparse, json, os, shutil, subprocess, sys
from pathlib import Path
from typing import List

from analyzer import summarize_repo
from generator import generate_pytests
from utils.file_utils import iter_files
from utils.language_support import detect_project
from validator import run_pytest_with_coverage
from coverage_analyzer import load_python_coverage, write_report
from quality_gates import check_minimum_coverage

def run_node_coverage(repo_root: Path, artifacts: Path):
    subprocess.run(["npm", "test", "--silent"], cwd=repo_root, check=False)
    final_json = repo_root / "coverage" / "coverage-final.json"
    if final_json.exists():
        (artifacts / "coverage").mkdir(parents=True, exist_ok=True)
        import shutil as _sh
        _sh.copy(final_json, artifacts / "coverage" / "coverage-final.json")
    return final_json.exists()

def run_java_coverage(repo_root: Path, artifacts: Path):
    try:
        subprocess.run(["mvn", "-q", "test"], cwd=repo_root, check=False)
        jacoco_xml = repo_root / "target" / "site" / "jacoco" / "jacoco.xml"
        jacoco_alt = repo_root / "target" / "jacoco" / "jacoco.xml"
        out_dir = artifacts / "coverage"
        out_dir.mkdir(parents=True, exist_ok=True)
        import shutil as _sh
        if jacoco_xml.exists():
            _sh.copy(jacoco_xml, out_dir / "jacoco.xml"); return True
        if jacoco_alt.exists():
            _sh.copy(jacoco_alt, out_dir / "jacoco.xml"); return True
    except Exception:
        pass
    return False

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True)
    ap.add_argument("--use-ai", default="false", choices=["true","false"])
    ap.add_argument("--max-files", type=int, default=40)
    ap.add_argument("--min-coverage", type=int, default=60)
    args = ap.parse_args()

    repo_root = Path(args.target).resolve()
    artifacts = Path("artifacts").resolve()
    junit_out = artifacts / "test-results" / "junit.xml"
    cov_xml_out = artifacts / "coverage" / "coverage.xml"
    report_out = artifacts / "report.json"

    proj = detect_project(repo_root)
    if not proj or proj.name != "python":
        print("Non-Python repository detected (or not detected). AI generation is Python-only. Exiting.")
        sys.exit(0)

    print(f"Detected project: {proj.name}")

    py_files = iter_files(repo_root, max_files=args.max_files)
    analysis = summarize_repo(py_files)
    gen_dir = repo_root / "tests" / "generated"
    created_files = generate_pytests(repo_root, analysis["files"], gen_dir)

    code, out = run_pytest_with_coverage(repo_root, junit_out, cov_xml_out)
    cov_summary = load_python_coverage(cov_xml_out) if cov_xml_out.exists() else {}
    line_rate = cov_summary.get("line_rate")
    ok = check_minimum_coverage(line_rate, float(args.min_coverage)/100.0)

    md = [
        f"**Project:** python",
        f"**Generated tests:** {len(created_files)} (unit/integration/e2e)",
        f"**Coverage:** {line_rate*100:.1f}% (threshold {args.min_coverage}%)" if line_rate is not None else "**Coverage:** n/a",
        f"**Tests exit code:** {code}",
    ]
    write_report(report_out, cov_summary, "\n".join([f"- {m}" for m in md]))
    print("\n".join(md))
    sys.exit(0 if ok else 1)

if __name__ == "__main__":
    main()
