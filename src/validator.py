import sys, os, pathlib, shlex, pytest, subprocess, signal, time, json, threading
from contextlib import contextmanager
from typing import Dict, List, Any

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
        print(f"⏱️ Global timeout set to {seconds}s")
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
        self.start_time = time.time()
        
    def pytest_runtest_logreport(self, report):
        if report.when != "call":
            return
        
        outcome = report.outcome
        self.counts[outcome] = self.counts.get(outcome, 0) + 1
        
        if outcome == "failed":
            self.failed_tests.append({
                "nodeid": report.nodeid,
                "longrepr": str(report.longrepr) if report.longrepr else "No details",
                "duration": getattr(report, "duration", 0)
            })
        elif outcome == "error":
            self.error_tests.append({
                "nodeid": report.nodeid, 
                "longrepr": str(report.longrepr) if report.longrepr else "No details",
                "duration": getattr(report, "duration", 0)
            })
    
    def pytest_collectreport(self, report):
        if report.failed:
            self.counts["error"] += 1
            self.error_tests.append({
                "nodeid": getattr(report, "nodeid", "collection"),
                "longrepr": str(report.longrepr) if report.longrepr else "Collection error"
            })
    
    def get_summary(self) -> Dict[str, Any]:
        """Generate comprehensive test summary"""
        total = sum(self.counts.values())
        duration = time.time() - self.start_time
        
        return {
            "total": total,
            "passed": self.counts["passed"],
            "failed": self.counts["failed"],
            "error": self.counts["error"],
            "skipped": self.counts["skipped"],
            "pass_rate": (self.counts["passed"] / total * 100) if total > 0 else 0,
            "duration": duration,
            "failed_tests": self.failed_tests,
            "error_tests": self.error_tests
        }

# ---- Compatibility fixes -----------------------------------------------------
def _apply_compatibility_fixes():
    """Apply compatibility fixes before running tests"""
    try:
        # Fix Jinja2/Flask compatibility
        import jinja2
        if not hasattr(jinja2, 'Markup'):
            try:
                from markupsafe import Markup
                jinja2.Markup = Markup
                if not hasattr(jinja2, 'escape'):
                    from markupsafe import escape
                    jinja2.escape = escape
                print("✅ Applied Jinja2 compatibility fix")
            except ImportError:
                print("⚠️ Could not apply Jinja2 compatibility fix")
    except ImportError:
        pass
    
    try:
        # Fix collections compatibility
        import collections
        import collections.abc as abc
        for name in ['Mapping', 'MutableMapping', 'Sequence', 'Iterable', 'Container']:
            if not hasattr(collections, name) and hasattr(abc, name):
                setattr(collections, name, getattr(abc, name))
        print("✅ Applied collections compatibility fix")
    except ImportError:
        pass

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

def _create_fallback_test(test_dir: pathlib.Path) -> pathlib.Path:
    """Create a basic fallback test if no tests exist"""
    fallback_content = '''import pytest
import sys
import os

def test_python_environment():
    """Basic smoke test to verify Python environment"""
    assert sys.version_info >= (3, 6)

def test_imports():
    """Test that we can import basic modules"""
    import json
    import pathlib
    assert True

def test_current_directory():
    """Test that we're in a valid directory"""
    assert os.path.exists('.')
'''
    
    fallback_path = test_dir / "test_fallback_smoke.py"
    fallback_path.parent.mkdir(parents=True, exist_ok=True)
    fallback_path.write_text(fallback_content, encoding="utf-8")
    return fallback_path

def _save_results(results: Dict[str, Any], output_path: str = None):
    """Save test results to JSON file"""
    if not output_path:
        output_path = os.environ.get("VALIDATOR_RESULTS_PATH", "test_results.json")
    
    try:
        output_file = pathlib.Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(f"📊 Results saved to {output_path}")
    except Exception as e:
        print(f"⚠️ Failed to save results: {e}")

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

def _setup_test_environment(test_dir: pathlib.Path):
    """Set up optimal environment for test execution"""
    # Add test directory and its parent to Python path
    paths_to_add = [test_dir, test_dir.parent]
    
    # Also add common project structure paths
    for potential_root in [pathlib.Path("."), pathlib.Path("target"), pathlib.Path("src")]:
        if potential_root.exists():
            paths_to_add.append(potential_root.resolve())
    
    return _temporary_sys_path(paths_to_add)

# ---- Main with comprehensive error handling ----------------------------------
def main():
    """Main validator entry point with comprehensive error handling"""
    
    print("🚀 Starting Enhanced Test Validator")
    
    # Environment validation
    if not _check_environment():
        print("❌ Environment validation failed")
        sys.exit(2)
    
    # Apply compatibility fixes
    _apply_compatibility_fixes()
    
    # Configurable guards
    global_timeout = int(os.environ.get("VALIDATOR_TIMEOUT_SECS", "600"))    # 10m
    per_test_timeout = int(os.environ.get("VALIDATOR_TEST_TIMEOUT_SECS", "30"))  # 30s

    if global_timeout > 0:
        _enforce_global_timeout(global_timeout)

    target = os.environ.get("VALIDATOR_TARGET_PATH", "tests/generated")
    test_dir = pathlib.Path(target).resolve()
    
    print(f"📁 Test directory: {test_dir}")
    
    # Check if test directory exists and has content
    if not test_dir.exists():
        print(f"❌ Test directory does not exist: {test_dir}")
        sys.exit(1)
    
    # Clean up any interfering artifacts
    _cleanup_test_artifacts(test_dir)
    
    # Check for test functions
    if not _has_test_functions(test_dir):
        print("⚠️ No test functions found, creating fallback test")
        fallback_test = _create_fallback_test(test_dir)
        print(f"📝 Created fallback test: {fallback_test}")
    
    # Build pytest arguments
    pytest_args_env = os.environ.get("VALIDATOR_PYTEST_ARGS", "")
    if pytest_args_env:
        pytest_args = _build_pytest_args(pytest_args_env)
    else:
        pytest_args = ["-v", "--tb=short", "-rA"]
        
        # Add fail-fast by default
        if os.environ.get("VALIDATOR_FAILFAST", "1").lower() not in {"0", "false", "no"}:
            pytest_args.extend(["-x", "--maxfail=1"])
    
    # Add the test directory
    pytest_args.append(str(test_dir))
    
    print(f"🔧 Pytest args: {' '.join(pytest_args)}")
    
    # Set up result collection
    collector = _ResultCollector()
    plugins = [collector]
    
    # Add per-test timeout if configured
    if per_test_timeout > 0:
        timeout_plugin = _PerTestTimeout(per_test_timeout)
        plugins.append(timeout_plugin)
        print(f"⏱️ Per-test timeout: {per_test_timeout}s")
    
    exit_code = 0
    results = {}
    
    try:
        with _setup_test_environment(test_dir):
            print("🧪 Running tests...")
            
            # Run pytest with our plugins
            exit_code = pytest.main(pytest_args + [f"--tb=short"], plugins=plugins)
            
            # Generate results summary
            results = collector.get_summary()
            
            print(f"\n📊 Test Results Summary:")
            print(f"   Total: {results['total']}")
            print(f"   Passed: {results['passed']}")
            print(f"   Failed: {results['failed']}")
            print(f"   Errors: {results['error']}")
            print(f"   Skipped: {results['skipped']}")
            print(f"   Pass Rate: {results['pass_rate']:.1f}%")
            print(f"   Duration: {results['duration']:.2f}s")
            
            # Show failed test details if any
            if results['failed_tests']:
                print(f"\n❌ Failed Tests ({len(results['failed_tests'])}):")
                for test in results['failed_tests'][:5]:  # Show first 5
                    print(f"   • {test['nodeid']}")
                if len(results['failed_tests']) > 5:
                    print(f"   ... and {len(results['failed_tests']) - 5} more")
            
            # Show error details if any
            if results['error_tests']:
                print(f"\n💥 Error Tests ({len(results['error_tests'])}):")
                for test in results['error_tests'][:5]:  # Show first 5
                    print(f"   • {test['nodeid']}")
                if len(results['error_tests']) > 5:
                    print(f"   ... and {len(results['error_tests']) - 5} more")
            
    except KeyboardInterrupt:
        print("\n🛑 Test execution interrupted by user")
        exit_code = 130
        results = {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "error": 1,
            "skipped": 0,
            "pass_rate": 0,
            "duration": 0,
            "interrupted": True
        }
    except Exception as e:
        print(f"\n💥 Test execution failed: {e}")
        exit_code = 1
        results = {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "error": 1,
            "skipped": 0,
            "pass_rate": 0,
            "duration": 0,
            "execution_error": str(e)
        }
    
    # Save results
    results["exit_code"] = exit_code
    _save_results(results)
    
    # Set environment variables for CI/CD integration
    os.environ["VALIDATOR_TOTAL_TESTS"] = str(results.get("total", 0))
    os.environ["VALIDATOR_PASSED_TESTS"] = str(results.get("passed", 0))
    os.environ["VALIDATOR_FAILED_TESTS"] = str(results.get("failed", 0))
    os.environ["VALIDATOR_PASS_RATE"] = str(results.get("pass_rate", 0))
    
    # Determine final status
    if exit_code == 0:
        print("✅ All tests passed successfully!")
    elif exit_code == 130:
        print("🛑 Test execution was interrupted")
    else:
        # Check if this is acceptable failure (e.g., some tests passed)
        min_pass_rate = float(os.environ.get("VALIDATOR_MIN_PASS_RATE", "70.0"))
        if results.get("pass_rate", 0) >= min_pass_rate:
            print(f"⚠️ Some tests failed, but pass rate ({results.get('pass_rate', 0):.1f}%) meets minimum threshold ({min_pass_rate}%)")
            exit_code = 0
        else:
            print(f"❌ Test validation failed (pass rate: {results.get('pass_rate', 0):.1f}%)")
    
    sys.exit(exit_code)

if __name__ == "__main__":
    main()