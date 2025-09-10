import sys, json, os, re, subprocess, pathlib
from typing import Set, Dict, List

# Enhanced aliases with more mappings
ALIASES = {
    "bs4": "beautifulsoup4",
    "yaml": "PyYAML", 
    "cv2": "opencv-python",
    "sklearn": "scikit-learn",
    "pil": "Pillow",
    "pillow": "Pillow",
    "crypto": "pycryptodome",
    "mysql": "mysqlclient",
    "mysqldb": "mysqlclient",
    "psycopg2": "psycopg2-binary",
    "boto3": "boto3",
    "httpx": "httpx",
    "requests": "requests",
    "uvicorn": "uvicorn",
    "fastapi": "fastapi",
    "starlette": "starlette",
    "pydantic": "pydantic",
    "typing_extensions": "typing-extensions",
    "annotated_types": "annotated-types",
    "sqlalchemy": "SQLAlchemy",
    "flask": "flask",
    "django": "Django",
    "click": "click",
    "typer": "typer",
    "jinja2": "Jinja2",
    "markupsafe": "MarkupSafe",
    "ujson": "ujson",
    "orjson": "orjson",
    "pymongo": "pymongo",
    "redis": "redis",
    "pytest": "pytest",
    "jwt": "PyJWT",
}

# Version constraints for problematic packages
VERSION_CONSTRAINTS = {
    "flask": ">=2.0.0,<3.0.0",
    "jinja2": ">=3.0.0,<3.1.0",
    "markupsafe": ">=2.0.0,<2.1.0",
    "click": ">=8.0.0,<8.1.0",
    "typer": ">=0.7.0,<0.8.0",
    "werkzeug": ">=2.0.0,<2.3.0",
    "itsdangerous": ">=2.0.0,<2.2.0",
}

# Ecosystem dependencies - packages that should be installed together
ECOSYSTEM_DEPS = {
    "flask": ["markupsafe", "jinja2", "werkzeug", "itsdangerous"],
    "fastapi": ["starlette", "pydantic"],
    "django": ["sqlparse"],
}

VALID_PIP_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")

# Enhanced deny list with more stdlib modules
DENY = {
    "__future__", "__main__", "__builtin__", "builtins", "typing", "types", "dataclasses", "importlib",
    "asyncio", "json", "re", "os", "sys", "pathlib", "logging", "argparse", "functools", "itertools",
    "collections", "subprocess", "datetime", "time", "math", "decimal", "fractions", "statistics",
    "sqlite3", "http", "urllib", "hmac", "hashlib", "base64", "csv", "glob", "shutil", "tempfile",
    "inspect", "traceback", "enum", "textwrap", "pprint", "string", "threading", "multiprocessing",
    "unittest", "email", "xml", "html", "urllib", "socket", "ssl", "random", "uuid", "pickle",
    "gzip", "zipfile", "tarfile", "configparser", "ast", "token", "tokenize", "keyword", "dis",
    # Common py2 names that appear in legacy code
    "ConfigParser", "Queue", "HTMLParser", "StringIO", "cStringIO", "urllib2",
}

def stdlib_set():
    """Get comprehensive set of standard library modules."""
    s = set(getattr(sys, "stdlib_module_names", ()))  # Python 3.10+ has this
    s.update(DENY)
    return s

def is_local(top: str, root: pathlib.Path) -> bool:
    """Check if a module is local to the project."""
    if not root.exists():
        return False
    return (root / (top + ".py")).exists() or (root / top).is_dir()

def apply_version_constraints(packages: Set[str]) -> List[str]:
    """Apply version constraints to packages and add ecosystem dependencies."""
    constrained_packages = []
    package_names = {pkg.lower() for pkg in packages}
    
    # Process each package
    for pkg in sorted(packages):
        pkg_lower = pkg.lower()
        
        # Apply version constraint if available
        if pkg_lower in VERSION_CONSTRAINTS:
            constrained_packages.append(f"{pkg}{VERSION_CONSTRAINTS[pkg_lower]}")
            print(f"📌 Applied version constraint: {pkg}{VERSION_CONSTRAINTS[pkg_lower]}")
        else:
            constrained_packages.append(pkg)
        
        # Add ecosystem dependencies
        if pkg_lower in ECOSYSTEM_DEPS:
            for dep in ECOSYSTEM_DEPS[pkg_lower]:
                if dep not in package_names:
                    if dep in VERSION_CONSTRAINTS:
                        constrained_packages.append(f"{ALIASES.get(dep, dep)}{VERSION_CONSTRAINTS[dep]}")
                        print(f"🔗 Added ecosystem dependency: {ALIASES.get(dep, dep)}{VERSION_CONSTRAINTS[dep]}")
                    else:
                        constrained_packages.append(ALIASES.get(dep, dep))
                        print(f"🔗 Added ecosystem dependency: {ALIASES.get(dep, dep)}")
                    package_names.add(dep)
    
    return constrained_packages

def detect_problematic_combinations(packages: Set[str]) -> List[str]:
    """Detect potentially problematic package combinations."""
    warnings = []
    package_names = {pkg.lower() for pkg in packages}
    
    # Flask ecosystem warnings
    if "flask" in package_names:
        if "markupsafe" not in package_names:
            warnings.append("Flask detected without MarkupSafe - adding MarkupSafe for compatibility")
        if "jinja2" not in package_names:
            warnings.append("Flask detected without Jinja2 - adding Jinja2 for compatibility")
    
    # Click/Typer conflicts
    if "click" in package_names and "typer" in package_names:
        warnings.append("Both Click and Typer detected - using compatible versions")
    
    return warnings

def install_packages(packages: List[str], force_reinstall: bool = False) -> bool:
    """Install packages with enhanced error handling."""
    if not packages:
        print("📦 No packages to install.")
        return True
    
    print(f"📦 Installing {len(packages)} packages with compatibility constraints...")
    for pkg in packages:
        print(f"   • {pkg}")
    
    cmd = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-input"]
    
    if force_reinstall:
        cmd.append("--force-reinstall")
        print("🔄 Using --force-reinstall for compatibility")
    
    cmd.extend(packages)
    
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        
        if result.returncode == 0:
            print("✅ Package installation completed successfully")
            return True
        else:
            print(f"⚠️ pip install failed with exit code {result.returncode}")
            print(f"STDOUT: {result.stdout}")
            print(f"STDERR: {result.stderr}")
            
            # Try without version constraints as fallback
            if any("==" in pkg or ">=" in pkg or "<=" in pkg for pkg in packages):
                print("🔄 Retrying without version constraints...")
                simple_packages = [pkg.split(">=")[0].split("==")[0].split("<=")[0] for pkg in packages]
                return install_simple_packages(simple_packages)
            
            return False
            
    except subprocess.TimeoutExpired:
        print("⚠️ Package installation timed out after 5 minutes")
        return False
    except Exception as e:
        print(f"⚠️ Package installation failed: {e}")
        return False

def install_simple_packages(packages: List[str]) -> bool:
    """Fallback installation without version constraints."""
    cmd = [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", "--no-input"] + packages
    
    try:
        subprocess.check_call(cmd)
        print("✅ Fallback installation completed")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Fallback installation also failed with exit code {e.returncode}")
        return False

def verify_installation(packages: List[str]) -> Dict[str, bool]:
    """Verify that packages were installed correctly."""
    results = {}
    
    for pkg_spec in packages:
        # Extract package name from version spec
        pkg_name = pkg_spec.split(">=")[0].split("==")[0].split("<=")[0].split("<")[0].split(">")[0]
        
        try:
            __import__(pkg_name)
            results[pkg_name] = True
        except ImportError:
            # Try common import name variations
            import_name = ALIASES.get(pkg_name.lower(), pkg_name)
            try:
                __import__(import_name)
                results[pkg_name] = True
            except ImportError:
                results[pkg_name] = False
    
    return results

def main():
    """Main function with enhanced argument handling and error checking."""
    if len(sys.argv) < 2:
        print("Usage: python -m src.install_from_analysis /path/to/analysis.json [--root target] [--force-reinstall]")
        print("")
        print("Options:")
        print("  --root PATH          Project root directory (default: target)")
        print("  --force-reinstall    Force reinstall packages for compatibility")
        print("  --verify             Verify installation after completion")
        sys.exit(0)
    
    analysis_path = pathlib.Path(sys.argv[1])
    root = pathlib.Path("target")
    force_reinstall = False
    verify = False
    
    # Parse additional arguments
    i = 2
    while i < len(sys.argv):
        if sys.argv[i] == "--root" and i + 1 < len(sys.argv):
            root = pathlib.Path(sys.argv[i + 1])
            i += 2
        elif sys.argv[i] == "--force-reinstall":
            force_reinstall = True
            i += 1
        elif sys.argv[i] == "--verify":
            verify = True
            i += 1
        else:
            print(f"⚠️ Unknown argument: {sys.argv[i]}")
            i += 1
    
    # Validate inputs
    if not analysis_path.exists():
        print(f"❌ Analysis file not found: {analysis_path}")
        sys.exit(1)
    
    print(f"📄 Reading analysis from: {analysis_path}")
    print(f"📁 Project root: {root}")
    
    try:
        data = json.loads(analysis_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"❌ Failed to read analysis file: {e}")
        sys.exit(1)
    
    std = stdlib_set()
    mods = set(data.get("modules") or [])
    pkgs = set()
    
    print(f"🔍 Analyzing {len(mods)} imported modules...")
    
    for m in mods:
        top = (m.split(".")[0] or "").strip()
        if not top:
            continue
        if top in std:
            continue
        if top.startswith("_") or "__" in top:
            continue
        if any(c.isupper() for c in top):  # Skip likely GUI packages
            continue
        if not VALID_PIP_RE.match(top):
            continue
        if is_local(top, root):
            continue
        
        # Apply alias mapping
        pkg_name = ALIASES.get(top.lower(), top)
        pkgs.add(pkg_name)
    
    if not pkgs:
        print("📦 No third-party packages inferred from imports.")
        return
    
    print(f"🎯 Found {len(pkgs)} third-party packages:")
    for pkg in sorted(pkgs):
        print(f"   • {pkg}")
    
    # Check for problematic combinations
    warnings = detect_problematic_combinations(pkgs)
    if warnings:
        print("\n⚠️ Compatibility warnings:")
        for warning in warnings:
            print(f"   • {warning}")
    
    # Apply version constraints and ecosystem dependencies
    constrained_packages = apply_version_constraints(pkgs)
    
    print(f"\n📦 Installing {len(constrained_packages)} packages...")
    
    # Install packages
    success = install_packages(constrained_packages, force_reinstall)
    
    if not success:
        print("❌ Package installation failed")
        sys.exit(1)
    
    # Verify installation if requested
    if verify:
        print("\n🔍 Verifying installation...")
        verification_results = verify_installation(constrained_packages)
        
        failed_packages = [pkg for pkg, success in verification_results.items() if not success]
        if failed_packages:
            print(f"⚠️ Failed to verify {len(failed_packages)} packages:")
            for pkg in failed_packages:
                print(f"   • {pkg}")
        else:
            print("✅ All packages verified successfully")
    
    print(f"\n✅ Installation complete! Installed {len(constrained_packages)} packages with compatibility constraints.")

if __name__ == "__main__":
    main()