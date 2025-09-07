import subprocess, sys, pathlib

def run_pytest():
    cmd = [sys.executable, "-m", "pytest", "-q"]
    return subprocess.call(cmd, cwd=str(pathlib.Path(".")))

if __name__ == "__main__":
    rc = run_pytest()
    if rc != 0:
        print("⚠️ Validation run failed.")
        sys.exit(rc)
    print("✅ Validation run passed.")
