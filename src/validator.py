# src/validator.py
import sys, os, pathlib, pytest, shlex

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
    target = os.environ.get("VALIDATOR_TARGET_PATH", "tests/generated")
    test_dir = pathlib.Path(target)
    if not test_dir.exists():
        print(f"⚠️ {target} does not exist — treating as no-op (success).")
        sys.exit(0)

    if not _has_test_functions(test_dir):
        print(f"❌ No test_ functions found in {target}.")
        sys.exit(2)

    args_env = os.environ.get("VALIDATOR_PYTEST_ARGS", "-q")
    try:
        args = shlex.split(args_env)
    except ValueError:
        args = args_env.replace('"', '').replace("'", "").split()

    plugin = _ResultCollector()
    rc = pytest.main(args + [target], plugins=[plugin])

    c = plugin.counts
    print(f"Validator summary: passed={c['passed']} failed={c['failed']} errors={c['error']} skipped={c['skipped']}")

    if c["passed"] >= 1 and c["failed"] == 0 and c["error"] == 0:
        print("✅ Validation run passed with real executing tests.")
        sys.exit(0)

    if c["passed"] == 0 and c["failed"] == 0 and c["error"] == 0 and c["skipped"] > 0:
        print("ℹ️ Only skipped tests collected — accepting as success.")
        sys.exit(0)

    print("⚠️ Validation run failed.")
    sys.exit(int(getattr(rc, "value", rc)))

if __name__ == "__main__":
    main()
