import sys, os, pathlib, shlex, pytest, subprocess, signal, time
from contextlib import contextmanager

# ---- Make collection stable & fast -------------------------------------------
# Stop pytest from auto-loading any 3rd-party plugins present in the runner.
os.environ.setdefault("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
# Keep any Qt/Gtk code headless.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# Deterministic hashing; some libs behave differently otherwise.
os.environ.setdefault("PYTHONHASHSEED", "0")

# ---- Global timeout with better error handling -------------------------------
def _enforce_global_timeout(seconds: int):
    """Sets up a global timeout to prevent the validator from hanging indefinitely."""
    try:
        import faulthandler, threading, os as _os
        faulthandler.enable()
        # Dump all thread stacks when the timeout hits (to see where it hung)
        faulthandler.dump_traceback_later(seconds, repeat=False)

        def _hard_kill():
            print(f"\n Validator global timeout {seconds}s reached — aborting.\n", flush=True)
            try:
                # Try graceful shutdown first
                _os._exit(124)
            except Exception:
                # Force kill if graceful fails
                _os.kill(_os.getpid(), signal.SIGKILL)

        t = threading.Timer(seconds + 5, _hard_kill)
        t.daemon = True
        t.start()
        print(f"🕐 Global timeout set to {seconds}s")
    except Exception as e:
        print(f"⚠️ Failed to enable global timeout: {e}", file=sys.stderr)

# ---- Per-test timeout plugin with better cleanup -----------------------------
class _PerTestTimeout:
    def __init__(self, seconds: int):
        self.seconds = seconds
        self._prev = None
        self._timer = None

    def pytest_runtest_setup(self, item):
        """Set alarm for individual test timeout"""
        try:
            def _handler(signum, frame):
                raise TimeoutError(f"Test timeout after {self.seconds}s: {item.nodeid}")
            
            # Store previous handler
            self._prev = signal.signal(signal.SIGALRM, _handler)
            signal.alarm(self.seconds)
        except (AttributeError, OSError):
            # SIGALRM not available (Windows) - use threading timer as fallback
            def _timeout_handler():
                print(f"\n⏱️ Test timeout after {self.seconds}s: {item.nodeid}")
                # Can't easily interrupt the test, but at least log it
            
            self._timer = threading.Timer(self.seconds, _timeout_handler)
            self._timer.daemon = True
            self._timer.start()

    def pytest_runtest_teardown(self, item, nextitem):
        """Clean up timeout mechanisms"""
        try:
            signal.alarm(0)  # Cancel alarm
            if self._prev is not None:
                signal.signal(signal.SIGALRM, self._prev)
                self._prev = None
        except (AttributeError, OSError):
            # Fallback for Windows/systems without SIGALRM
            if self._timer:
                self._timer.cancel()
                self._timer = None

# ---- Enhanced result collector -----------------------------------------------
class _ResultCollector:
    def __init__(self):
        self.counts = {"passed": 0, "failed": 0, "error": 0, "skipped": 0}
        self.failed_tests = []
        self.error_tests = []
        
    def pytest_runtest_logreport(self, report):
        if report.when != "call":
            return
        
        outcome = report.outcome
        self.counts[outcome] = self.counts.get(outcome, 0) + 1
        
        if outcome == "failed":
            self.failed_tests.append({
                "nodeid": report.nodeid,
                "longrepr": str(report.longrepr) if report.longrepr else "No details"
            })
        elif outcome == "error":
            self.error_tests.append({
                "nodeid": report.nodeid, 
                "longrepr": str(report.longrepr) if report.longrepr else "No details"
            })
    
    def pytest_collectreport(self, report):
        if report.failed:
            self.counts["error"] += 1
            self.error_tests.append({
                "nodeid": getattr(report, "nodeid", "collection"),
                "longrepr": str(report.longrepr) if report.longrepr else "Collection error"
            })

# ---- Helpers with better error handling --------------------------------------
def _has_test_functions(test_dir: pathlib.Path) -> bool:
    """Check if directory contains any test functions"""
    if not test_dir.exists():
        return False
        
    for p in test_dir.rglob("test_*.py"):
        try:
            content = p.read_text(encoding="utf-8", errors="ignore")
            if "def test_" in content:
                return True
        except (OSError, IOError) as e:
            print(f"⚠️ Could not read {p}: {e}")
            continue
    return False

def _build_pytest_args(args_env: str):
    """Parse pytest arguments from environment with validation"""
    try:
        args = shlex.split(args_env)
    except ValueError as e:
        print(f"⚠️ Failed to parse pytest args '{args_env}': {e}")
        args = args_env.replace('"', '').replace("'", "").split()

    # Show reasons unless the caller already set -r*
    if not any(a.startswith("-r") for a in args):
        args += ["-rA"]
    
    # Fail fast unless explicitly disabled
    if os.environ.get("VALIDATOR_FAILFAST", "1").lower() not in {"0", "false", "no"}:
        if "-x" not in args and not any(a.startswith("--maxfail") for a in args):
            args += ["-x", "--maxfail=1"]
    
    return args

def _check_environment():
    """Validate environment and dependencies"""
    issues = []
    
    # Check Python version
    if sys.version_info < (3, 8):
        issues.append(f"Python {sys.version_info.major}.{sys.version_info.minor} may be too old (recommend 3.8+)")
    
    # Check required modules
    required = ["pytest", "pathlib"]
    for module in required:
        try:
            __import__(module)
        except ImportError:
            issues.append(f"Missing required module: {module}")
    
    if issues:
        for issue in issues:
            print(f"⚠️ {issue}")
        return False
    return True

def _cleanup_test_artifacts(test_dir: pathlib.Path):
    """Clean up any artifacts that might interfere with testing"""
    cleanup_patterns = ["*.pyc", "__pycache__", ".pytest_cache"]
    
    for pattern in cleanup_patterns:
        for item in test_dir.rglob(pattern):
            try:
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    import shutil
                    shutil.rmtree(item, ignore_errors=True)
            except (OSError, IOError):
                pass  # Ignore cleanup errors

@contextmanager
def _temporary_sys_path(additional_paths):
    """Temporarily add paths to sys.path"""
    original_path = sys.path.copy()
    try:
        for path in additional_paths:
            if str(path) not in sys.path:
                sys.path.insert(0, str(path))
        yield
    finally:
        sys.path[:] = original_path

# ---- Main with comprehensive error handling ----------------------------------
def main():
    """Main validator entry point with comprehensive error handling"""
    
    # Environment validation
    if not _check_environment():
        print("❌ Environment validation failed")
        sys.exit(2)
    
    # Configurable guards
    global_timeout = int(os.environ.get("VALIDATOR_TIMEOUT_SECS", "600"))    # 10m
    per_test_timeout = int(os.environ.get("VALIDATOR_TEST_TIMEOUT_SECS", "30"))  # 30s

    if global_timeout > 0:
        _enforce_global_timeout(global_timeout)

    target = os.environ.get("VALIDATOR_TARGET_PATH", "tests/generated")
    test_dir = pathlib.Path(target).resolve()
    
    print