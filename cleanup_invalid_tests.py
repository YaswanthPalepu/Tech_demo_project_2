#!/usr/bin/env python3
"""Clean up invalid test files with syntax errors."""
import ast
import pathlib
import sys

def validate_test_file(file_path: pathlib.Path) -> tuple[bool, str]:
    """Validate a test file for syntax errors."""
    try:
        code = file_path.read_text(encoding="utf-8")
        ast.parse(code)
        
        # Check for circular class definitions
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for base in node.bases:
                    if isinstance(base, ast.Name) and base.id == node.name:
                        return False, f"Circular class definition: {node.name}"
        
        return True, "OK"
    except SyntaxError as e:
        return False, f"Syntax error: {e}"
    except Exception as e:
        return False, f"Error: {e}"

def main():
    """Clean up invalid test files."""
    test_dir = pathlib.Path("tests/generated")
    
    if not test_dir.exists():
        print(f"Test directory not found: {test_dir}")
        return 1
    
    test_files = list(test_dir.glob("test_*.py"))
    if not test_files:
        print("No test files found")
        return 0
    
    print(f"Checking {len(test_files)} test files...\n")
    
    invalid_files = []
    valid_files = []
    
    for test_file in test_files:
        is_valid, error = validate_test_file(test_file)
        if is_valid:
            valid_files.append(test_file)
            print(f"✓ {test_file.name}")
        else:
            invalid_files.append((test_file, error))
            print(f"✗ {test_file.name}: {error}")
    
    print(f"\nSummary:")
    print(f"  Valid: {len(valid_files)}")
    print(f"  Invalid: {len(invalid_files)}")
    
    if invalid_files:
        print(f"\nInvalid files:")
        for file_path, error in invalid_files:
            print(f"  - {file_path.name}: {error}")
        
        response = input(f"\nDelete {len(invalid_files)} invalid files? [y/N]: ")
        if response.lower() == 'y':
            for file_path, _ in invalid_files:
                file_path.unlink()
                print(f"  Deleted: {file_path.name}")
            print(f"\n✓ Cleaned up {len(invalid_files)} invalid test files")
        else:
            print("\nNo files deleted")
    else:
        print("\n✓ All test files are valid!")
    
    return 0

if __name__ == "__main__":
    sys.exit(main())
