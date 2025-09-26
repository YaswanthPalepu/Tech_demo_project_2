# src/gen/smart_change.py - Simplified but granular change detection

import hashlib
import json
import os
from pathlib import Path
from typing import Set, Dict, List, Tuple

def _compute_file_hash(file_path: Path) -> str:
    """Compute hash of a single file."""
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        return hashlib.md5(content.encode()).hexdigest()[:16]
    except Exception:
        return ""

def _get_source_files(target_root: Path) -> Dict[str, str]:
    """Get all Python source files with their hashes."""
    source_files = {}
    
    for py_file in target_root.rglob("*.py"):
        # Skip test files and cache
        relative_path = py_file.relative_to(target_root)
        if any(skip in str(relative_path).lower() for skip in ['test', '__pycache__', '.git', 'venv']):
            continue
            
        file_hash = _compute_file_hash(py_file)
        if file_hash:
            source_files[str(relative_path)] = file_hash
    
    return source_files

def _load_last_state(target_root: Path) -> Dict[str, str]:
    """Load the last generation state."""
    state_file = target_root / 'tests' / 'generated' / '.change_state.json'
    
    if state_file.exists():
        try:
            with open(state_file, 'r') as f:
                data = json.load(f)
                return data.get('source_files', {})
        except Exception:
            pass
    
    return {}

def _save_current_state(target_root: Path, source_files: Dict[str, str], test_mapping: Dict[str, List[str]]):
    """Save current generation state."""
    state_file = target_root / 'tests' / 'generated' / '.change_state.json'
    state_file.parent.mkdir(parents=True, exist_ok=True)
    
    state = {
        'source_files': source_files,
        'test_mapping': test_mapping,
        'generated_at': __import__('time').time()
    }
    
    with open(state_file, 'w') as f:
        json.dump(state, f, indent=2)

def detect_changed_files(target_root: str) -> Tuple[Set[str], Set[str], Dict[str, List[str]]]:
    """
    Detect which source files have changed.
    
    Returns:
        (changed_files, deleted_files, existing_test_mapping)
    """
    target_path = Path(target_root)
    
    # Get current and last source file states
    current_files = _get_source_files(target_path)
    last_files = _load_last_state(target_path)
    
    # Load existing test mapping
    state_file = target_path / 'tests' / 'generated' / '.change_state.json'
    existing_test_mapping = {}
    if state_file.exists():
        try:
            with open(state_file, 'r') as f:
                data = json.load(f)
                existing_test_mapping = data.get('test_mapping', {})
        except Exception:
            pass
    
    # Detect changes
    changed_files = set()
    deleted_files = set()
    
    # Check for new or modified files
    for file_path, current_hash in current_files.items():
        if file_path not in last_files or last_files[file_path] != current_hash:
            changed_files.add(file_path)
    
    # Check for deleted files
    for file_path in last_files:
        if file_path not in current_files:
            deleted_files.add(file_path)
    
    print(f"Changed files: {len(changed_files)}")
    print(f"Deleted files: {len(deleted_files)}")
    
    if changed_files:
        print("Files that changed:")
        for f in sorted(changed_files):
            print(f"  - {f}")
    
    return changed_files, deleted_files, existing_test_mapping

def cleanup_tests_for_deleted_files(target_root: str, deleted_files: Set[str], test_mapping: Dict[str, List[str]]):
    """Remove test files for deleted source files."""
    target_path = Path(target_root)
    test_dir = target_path / 'tests' / 'generated'
    
    cleaned_count = 0
    for deleted_file in deleted_files:
        if deleted_file in test_mapping:
            test_files = test_mapping[deleted_file]
            for test_file in test_files:
                test_path = test_dir / test_file
                if test_path.exists():
                    try:
                        test_path.unlink()
                        cleaned_count += 1
                        print(f"Deleted test file: {test_file}")
                    except Exception as e:
                        print(f"Could not delete {test_file}: {e}")
            
            # Remove from mapping
            del test_mapping[deleted_file]
    
    if cleaned_count > 0:
        print(f"Cleaned up {cleaned_count} test files for deleted source files")

def cleanup_tests_for_changed_files(target_root: str, changed_files: Set[str], test_mapping: Dict[str, List[str]]):
    """Remove existing test files for changed source files (they'll be regenerated)."""
    target_path = Path(target_root)
    test_dir = target_path / 'tests' / 'generated'
    
    cleaned_count = 0
    for changed_file in changed_files:
        if changed_file in test_mapping:
            test_files = test_mapping[changed_file]
            for test_file in test_files:
                test_path = test_dir / test_file
                if test_path.exists():
                    try:
                        test_path.unlink()
                        cleaned_count += 1
                        print(f"Removed old test for changed file: {test_file}")
                    except Exception as e:
                        print(f"Could not delete {test_file}: {e}")
            
            # Remove from mapping (will be updated with new tests)
            del test_mapping[changed_file]
    
    if cleaned_count > 0:
        print(f"Cleaned up {cleaned_count} old test files for changed source files")

def update_test_mapping(target_root: str, changed_files: Set[str], generated_test_files: List[str]):
    """Update the mapping between source files and their test files."""
    target_path = Path(target_root)
    
    # Load current state
    current_files = _get_source_files(target_path)
    
    # Load existing mapping
    state_file = target_path / 'tests' / 'generated' / '.change_state.json'
    test_mapping = {}
    if state_file.exists():
        try:
            with open(state_file, 'r') as f:
                data = json.load(f)
                test_mapping = data.get('test_mapping', {})
        except Exception:
            pass
    
    # Simple mapping: all generated tests map to all changed files
    # (You could make this more sophisticated by analyzing test content)
    for changed_file in changed_files:
        test_mapping[changed_file] = [Path(f).name for f in generated_test_files]
    
    # Save updated state
    _save_current_state(target_path, current_files, test_mapping)
    print(f"Updated test mapping for {len(changed_files)} source files")

def should_generate_tests(target_root: str) -> Tuple[bool, Set[str], Set[str]]:
    """
    Determine if tests should be generated and for which files.
    
    Returns:
        (should_generate, changed_files, deleted_files)
    """
    target_path = Path(target_root)
    
    # Check force flag - FIXED: Now handles force generation correctly
    force_flag = os.getenv('TESTGEN_FORCE', '').lower()
    print(f"TESTGEN_FORCE environment variable: '{force_flag}'")
    
    if force_flag in ['true', '1', 'yes']:
        print("🚀 Force generation enabled - will regenerate all tests")
        # When forcing, we want to generate tests for ALL source files
        all_source_files = _get_source_files(target_path)
        all_files_set = set(all_source_files.keys())
        print(f"Found {len(all_files_set)} source files for force generation:")
        for f in sorted(all_files_set):
            print(f"  - {f}")
        return True, all_files_set, set()  # Return all files as "changed"
    
    # Detect changes
    changed_files, deleted_files, test_mapping = detect_changed_files(target_root)
    
    if not changed_files and not deleted_files:
        print("No source code changes detected - skipping generation")
        return False, set(), set()
    
    print(f"Source code changes detected - will generate tests for {len(changed_files)} files")
    return True, changed_files, deleted_files

def prepare_for_generation(target_root: str, changed_files: Set[str], deleted_files: Set[str]):
    """Clean up old tests before generating new ones."""
    if not changed_files and not deleted_files:
        return
    
    # For force generation, clean up ALL existing tests
    force_flag = os.getenv('TESTGEN_FORCE', '').lower()
    if force_flag in ['true', '1', 'yes']:
        target_path = Path(target_root)
        test_dir = target_path / 'tests' / 'generated'
        if test_dir.exists():
            print("🧹 Force mode: Cleaning up all existing generated tests")
            cleaned_count = 0
            for test_file in test_dir.glob('test_*.py'):
                try:
                    test_file.unlink()
                    cleaned_count += 1
                    print(f"Deleted: {test_file.name}")
                except Exception as e:
                    print(f"Could not delete {test_file.name}: {e}")
            print(f"Cleaned up {cleaned_count} existing test files")
        return
    
    # Load test mapping for selective cleanup
    _, _, test_mapping = detect_changed_files(target_root)
    
    # Clean up tests for deleted source files
    if deleted_files:
        cleanup_tests_for_deleted_files(target_root, deleted_files, test_mapping)
    
    # Clean up old tests for changed source files
    if changed_files:
        cleanup_tests_for_changed_files(target_root, changed_files, test_mapping)

def finalize_generation(target_root: str, changed_files: Set[str], generated_test_files: List[str]):
    """Finalize the generation by updating mappings."""
    if changed_files and generated_test_files:
        update_test_mapping(target_root, changed_files, generated_test_files)
        print(f"Generation completed: {len(generated_test_files)} test files for {len(changed_files)} source files")

def detect_changes(target_root, manifest_path):
    """
    Compatibility wrapper for existing code.
    Returns the old format: (added_or_modified, deleted, unchanged)
    """
    target_root_str = str(target_root)
    should_generate, changed_files, deleted_files = should_generate_tests(target_root_str)
    
    # Convert to old format
    added_or_modified = changed_files
    deleted = deleted_files
    unchanged = set()  # We don't track unchanged files in granular mode
    
    return added_or_modified, deleted, unchanged