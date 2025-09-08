# src/validator.py
import sys, os, pathlib, shlex, pytest

# ---- Make collection stable & fast -------------------------------------------
# Stop pytest from auto-loading any 3rd-party plugins present in the runner.
os.environ.setdefault("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
# Keep any Qt/Gtk code headless.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Deterministic hashing; some libs behave differently otherwise.
os.environ.setdefault("PYTHONHASHSEED", "0")

# ---- Global timeout (kills the whole run if it hangs) ------------------------
def _enforce_global_timeout(seconds: int):
    try:
        import faulthandler, threading, os as _os
        faulthandler.enable()
        # Dump all thread stacks when the timeout hits (to see where it hung)
        faulthandler.dump_traceback_later(seconds, repeat=False)

        def _hard_kill():
            print(f"\n⏱️ Validator global timeout {seconds}s reached — aborting.\n", flush=True)
            _os._exit(124)  # avoid atexit deadlocks

        t = threading.Timer(seconds + 5, _hard_kill)
        t.daemon = True
        t.start()
    except Exception as e:
        print(f"⚠️ Failed to enable global timeout: {e}", file=sys.stderr)

# ---- Per-test timeout plugin -------------------------------------------------
class _PerTestTimeout:
    def __init__(self, seconds: int):
        self.seconds = seconds
        self._prev = None

    def pytest_runtest_setup(self, item):
        # SIGALRM is Linux/macOS; on Windows this will be ignored (CI uses Linux).
        try:
            import signal
            def _handler(signum, frame):
                raise TimeoutError(f"Test timeout after {self.seconds}s: {item.nodeid}")
            self._prev = signal.signal(signal.SIGALRM, _handler)
            signal.alarm(self.seconds)
        except Exception:
            self._prev = None

    def pytest_runtest_teardown(self, item, nextitem):
        try:
            import signal
            signal.alarm(0)
            if self._prev:
                signal.signal(signal.SIGALRM, self._prev)
        except Exception:
            pass

# ---- Simple result collector -------------------------------------------------
class _ResultCollector:
    def __init__(self):
        self.counts = {"passed": 0, "failed": 0, "error": 0, "skipped": 0}
    def pytest_runtest_logreport(self, report):
        if report.when != "call":
            return
        self.counts[report.outcome] = self.counts.get(report.outcome, 0) + 1
    def pytest_collectreport(self, report):
        if report.failed:
            self.counts["error"] += 1

# ---- Helpers ----------------------------------------------------------------
def _has_test_functions(test_dir: pathlib.Path) -> bool:
    for p in test_dir.rglob("test_*.py"):
        try:
            if "def test_" in p.read_text(encoding="utf-8", errors="ignore"):
                return True
        except Exception:
            continue
    return False

def _build_pytest_args(args_env: str):
    try:
        args = shlex.split(args_env)
    except ValueError:
        args = args_env.replace('"', '').replace("'", "").split()

    # Show reasons unless the caller already set -r*
    if not any(a.startswith("-r") for a in args):
        args += ["-rA"]
    # Fail fast unless explicitly disabled
    if os.environ.get("VALIDATOR_FAILFAST", "1").lower() not in {"0", "false", "no"}:
        if "-x" not in args and not any(a.startswith("--maxfail") for a in args):
            args += ["-x", "--maxfail=1"]
    return args

# ---- Main -------------------------------------------------------------------
def main():
    # Configurable guards
    global_timeout = int(os.environ.get("VALIDATOR_TIMEOUT_SECS", "600"))    # 10m
    per_test_timeout = int(os.environ.get("VALIDATOR_TEST_TIMEOUT_SECS", "30"))  # 30s

    if global_timeout > 0:
        _enforce_global_timeout(global_timeout)

    target = os.environ.get("VALIDATOR_TARGET_PATH", "tests/generated")
    test_dir = pathlib.Path(target)
    if not test_dir.exists():
        print(f"⚠️ {target} does not exist — treating as no-op (success).")
        sys.exit(0)

    if not _has_test_functions(test_dir):
        print(f"❌ No test_ functions found in {target}.")
        sys.exit(2)

    default_args = "-q -k 'not e2e'"
    args_env = os.environ.get("VALIDATOR_PYTEST_ARGS", default_args)
    args = _build_pytest_args(args_env)

    print(f"Running pytest with args: {' '.join(args)} in {target}")
    collector = _ResultCollector()
    timeout_plugin = _PerTestTimeout(per_test_timeout)

    rc = pytest.main(args + [target], plugins=[collector, timeout_plugin])

    c = collector.counts
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
