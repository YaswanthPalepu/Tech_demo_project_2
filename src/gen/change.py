# src/gen/change.py
import ast, hashlib, json, pathlib, time
from typing import Dict, Tuple, Set, Optional

def _compute_hash(content: str) -> str:
    """Compute SHA256 hash of content for change detection."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()

def _extract_function_signatures(file_path: pathlib.Path) -> Dict[str, str]:
    """Extract function and class signatures with their content hashes."""
    signatures = {}
    
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(content)
        lines = content.splitlines()
        
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                start_line = node.lineno - 1
                end_line = getattr(node, "end_lineno", node.lineno) or node.lineno
                
                # Extract the relevant code segment
                code_segment = "\n".join(lines[start_line:end_line])
                
                # Create signature identifier
                node_type = type(node).__name__.lower().replace("def", "")  # functiondef -> function
                signature_key = f"{node_type}:{node.name}"
                
                # Store hash of the code segment
                signatures[signature_key] = _compute_hash(code_segment)
                
    except (SyntaxError, UnicodeDecodeError, OSError) as e:
        # Log error but don't fail - some files might have syntax issues
        print(f"Warning: Could not parse {file_path}: {e}")
    except Exception as e:
        print(f"Unexpected error parsing {file_path}: {e}")
    
    return signatures

def _load_change_state(manifest_path: pathlib.Path) -> Dict[str, dict]:
    """Load previous change detection state from manifest."""
    if not manifest_path.exists():
        return {}
    
    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data.get("code_state", {})
    except (json.JSONDecodeError, OSError) as e:
        print(f"Warning: Could not load change state: {e}")
        return {}

def _save_change_state(manifest_path: pathlib.Path, state: Dict[str, dict]) -> None:
    """Save current change detection state to manifest."""
    
    # Load existing manifest data or create new
    manifest_data = {}
    if manifest_path.exists():
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                manifest_data = json.load(f)
        except (json.JSONDecodeError, OSError):
            print("Warning: Could not load existing manifest, creating new one")
    
    # Update code state
    manifest_data["code_state"] = state
    manifest_data["last_scan"] = time.time()
    
    # Ensure directory exists
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        with open(manifest_path, 'w', encoding='utf-8') as f:
            json.dump(manifest_data, f, indent=2, ensure_ascii=False)
    except OSError as e:
        print(f"Warning: Could not save change state: {e}")

def _should_scan_file(file_path: pathlib.Path, target_root: pathlib.Path) -> bool:
    """Determine if a Python file should be included in change detection."""
    
    try:
        relative_path = file_path.relative_to(target_root)
    except ValueError:
        return False
    
    # Skip hidden directories and files
    if any(part.startswith('.') for part in relative_path.parts):
        return False
    
    # Skip common non-source directories
    skip_dirs = {
        "__pycache__", "node_modules", ".git", ".venv", "venv", 
        "env", "dist", "build", ".mypy_cache", ".pytest_cache",
        "site-packages", "eggs", ".eggs"
    }
    
    if any(skip_dir in relative_path.parts for skip_dir in skip_dirs):
        return False
    
    # Skip test directories for change detection (we're generating tests)
    if any("test" in part.lower() for part in relative_path.parts):
        return False
    
    # Only process Python files
    if file_path.suffix != '.py':
        return False
    
    # Skip files that are clearly not source code
    skip_files = {
        "setup.py", "conftest.py", "__init__.py"
    }
    
    if file_path.name in skip_files:
        return False
    
    return True

def detect_changes(target_root: pathlib.Path, manifest_path: pathlib.Path) -> Tuple[Set[str], Set[str], Set[str]]:
    """
    Detect code changes by comparing file contents and function signatures.
    
    Returns:
        Tuple of (added_or_modified, deleted, unchanged) file sets
    """
    
    print(f"Scanning for changes in: {target_root}")
    
    # Load previous state
    previous_state = _load_change_state(manifest_path)
    
    # Scan current state
    current_state = {}
    scanned_files = 0
    
    for python_file in target_root.rglob("*.py"):
        if not _should_scan_file(python_file, target_root):
            continue
        
        scanned_files += 1
        relative_path = str(python_file.relative_to(target_root))
        
        try:
            file_content = python_file.read_text(encoding="utf-8", errors="ignore")
        except OSError as e:
            print(f"Warning: Could not read {python_file}: {e}")
            file_content = ""
        
        # Compute file hash and extract signatures
        file_hash = _compute_hash(file_content)
        signatures = _extract_function_signatures(python_file)
        
        current_state[relative_path] = {
            "file_hash": file_hash,
            "signatures": signatures,
            "last_modified": python_file.stat().st_mtime if python_file.exists() else 0
        }
    
    print(f"Scanned {scanned_files} Python files")
    
    # Compare states to detect changes
    added_or_modified = set()
    deleted = set()
    unchanged = set()
    
    # Check for new or modified files
    for file_path, current_info in current_state.items():
        if file_path not in previous_state:
            # New file
            added_or_modified.add(file_path)
            continue
        
        previous_info = previous_state[file_path]
        current_hash = current_info["file_hash"]
        previous_hash = previous_info.get("file_hash", "")
        
        if current_hash != previous_hash:
            # File content changed - check if it's just whitespace/comments
            current_sigs = current_info["signatures"]
            previous_sigs = previous_info.get("signatures", {})
            
            if current_sigs != previous_sigs:
                # Significant code changes (functions/classes modified)
                added_or_modified.add(file_path)
            else:
                # Only superficial changes (comments, whitespace, etc.)
                unchanged.add(file_path)
        else:
            # File unchanged
            unchanged.add(file_path)
    
    # Check for deleted files
    for file_path in previous_state:
        if file_path not in current_state:
            deleted.add(file_path)
    
    # Save current state
    _save_change_state(manifest_path, current_state)
    
    # Print summary
    print(f"Change detection results:")
    print(f"  Added/Modified: {len(added_or_modified)} files")
    print(f"  Deleted: {len(deleted)} files") 
    print(f"  Unchanged: {len(unchanged)} files")
    
    if added_or_modified:
        print("  Modified files:")
        for file_path in sorted(added_or_modified):
            print(f"    - {file_path}")
    
    if deleted:
        print("  Deleted files:")
        for file_path in sorted(deleted):
            print(f"    - {file_path}")
    
    return added_or_modified, deleted, unchanged

def force_rescan(target_root: pathlib.Path, manifest_path: pathlib.Path) -> None:
    """Force a complete rescan by clearing previous state."""
    
    print("Forcing complete rescan...")
    
    if manifest_path.exists():
        try:
            with open(manifest_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            data = {}
        
        # Clear code state to force rescan
        data["code_state"] = {}
        
        try:
            with open(manifest_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except OSError as e:
            print(f"Warning: Could not clear change state: {e}")

def get_change_summary(added_or_modified: Set[str], deleted: Set[str], unchanged: Set[str]) -> Dict[str, any]:
    """Generate a comprehensive change summary for reporting."""
    
    total_files = len(added_or_modified) + len(deleted) + len(unchanged)
    
    return {
        "total_files_analyzed": total_files,
        "added_or_modified_count": len(added_or_modified),
        "deleted_count": len(deleted),
        "unchanged_count": len(unchanged),
        "change_percentage": round((len(added_or_modified) / max(total_files, 1)) * 100, 1),
        "needs_test_generation": len(added_or_modified) > 0 or len(deleted) > 0,
        "added_or_modified_files": sorted(added_or_modified),
        "deleted_files": sorted(deleted),
        "scan_timestamp": time.time()
    }