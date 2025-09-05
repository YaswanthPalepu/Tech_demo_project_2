from pathlib import Path
import json
from validator import parse_coverage_xml

def write_report(report_path: Path, summary: dict, md: str):
    report_path.parent.mkdir(parents=True, exist_ok=True)
    data = {"coverage": summary, "summary_markdown": md}
    report_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
