import subprocess, sys, os
from pathlib import Path

def run_pytest_with_coverage(repo_root: Path, junit_out: Path, cov_xml_out: Path, only_generated: bool=False) -> tuple[int, str]:
    junit_out.parent.mkdir(parents=True, exist_ok=True)
    cov_xml_out.parent.mkdir(parents=True, exist_ok=True)
    args = [sys.executable, "-m", "pytest", "-q"]
    if only_generated:
        args += ["tests/generated"]
    args += ["--junitxml", str(junit_out), "--cov", ".", "--cov-report", f"xml:{cov_xml_out}"]
    proc = subprocess.run(args, cwd=str(repo_root), capture_output=True, text=True)
    return proc.returncode, proc.stdout + "\n" + proc.stderr

def parse_coverage_xml(cov_xml: Path) -> dict:
    try:
        import xml.etree.ElementTree as ET
        root = ET.parse(cov_xml).getroot()
        line_rate = root.attrib.get("line-rate")
        if line_rate is not None:
            return {"line_rate": float(line_rate)}
    except Exception:
        pass
    return {}
