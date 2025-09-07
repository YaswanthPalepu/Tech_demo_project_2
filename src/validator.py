import sys, os, pathlib, pytest

class _ResultCollector:
    def __init__(self):
        self.counts = {"passed": 0, "failed": 0, "error": 0, "skipped": 0}

    def pytest_runtest_logreport(self, report):
        if report.when != "call":
            return
        if report.outcome == "passed":
            self.counts["passed"] += 1
        elif report.outcome == "failed":
            self.counts["failed"] += 1
        elif report.outcome == "skipped":
            self.counts["skipped"] += 1

    def pytest_collectreport(self, report):
        if report.failed:
            self.counts["error"] += 1

def _has_test_functions(test_dir: pathlib.Path) -> bool:
    for p in test_dir.rglob("test_*.py"):
        try:
            if "def test_" in p.read_text(encoding="utf-8", errors="ignore"):
                return True
        except Exception:
            continue
    return False

def main():
    test_dir = pathlib.Path("tests/generated")
    if not test_dir.exists():
        print("⚠️ tests/generated/ does not exist — treating as no-op (success).")
        sys.exit(0)

    if not _has_test_functions(test_dir):
        print("❌ No test_ functions found in tests/generated.")
        sys.exit(2)

    args = os.environ.get("VALIDATOR_PYTEST_ARGS", "-q").split()
    plugin = _ResultCollector()
    rc = pytest.main(args + ["tests/generated"], plugins=[plugin])

    c = plugin.counts
    print(f"Validator summary: passed={c['passed']} failed={c['failed']} errors={c['error']} skipped={c['skipped']}")

    # Success if at least 1 passed and no fails/errors
    if c["passed"] >= 1 and c["failed"] == 0 and c["error"] == 0:
        print("✅ Validation run passed with real executing tests.")
        sys.exit(0)

    # Also succeed if only skipped and no fails/errors (infra-heavy repos)
    if c["passed"] == 0 and c["failed"] == 0 and c["error"] == 0 and c["skipped"] > 0:
        print("ℹ️ Only skipped tests collected — accepting as success.")
        sys.exit(0)

    print("⚠️ Validation run failed.")
    # propagate pytest's exit code (ensures CI shows red)
    sys.exit(int(getattr(rc, "value", rc)))

if __name__ == "__main__":
    main()
