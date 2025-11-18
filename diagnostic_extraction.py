#!/usr/bin/env python3
"""
Diagnostic tool to analyze what's being extracted vs what's available.
"""

import ast
import sys
from pathlib import Path


def analyze_extraction(source_file: str, extracted_output: str):
    """
    Compare source file with extracted output to find missing items.

    Args:
        source_file: Path to source file
        extracted_output: The extraction log output
    """
    print("=" * 80)
    print("EXTRACTION ANALYSIS")
    print("=" * 80)

    # Parse source file
    with open(source_file, 'r') as f:
        source_content = f.read()

    try:
        tree = ast.parse(source_content)
    except SyntaxError as e:
        print(f"❌ CRITICAL: Source file has syntax errors!")
        print(f"   {e}")
        return

    # Count all definitions in source
    all_functions = []
    all_classes = []
    all_variables = []
    all_imports = []

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name not in [f['name'] for f in all_functions]:
                all_functions.append({
                    'name': node.name,
                    'line': node.lineno,
                    'async': isinstance(node, ast.AsyncFunctionDef),
                    'decorators': len(node.decorator_list)
                })

        elif isinstance(node, ast.ClassDef):
            if node.name not in [c['name'] for c in all_classes]:
                all_classes.append({
                    'name': node.name,
                    'line': node.lineno
                })

        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    if target.id not in [v['name'] for v in all_variables]:
                        all_variables.append({
                            'name': target.id,
                            'line': node.lineno
                        })

        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            all_imports.append({
                'line': node.lineno,
                'type': 'import' if isinstance(node, ast.Import) else 'from'
            })

    # Parse extraction output
    extracted_functions = []
    for line in extracted_output.split('\n'):
        if '✓ Extracted:' in line:
            # Extract function name from line like "✓ Extracted: model_info (6 lines)"
            parts = line.split('✓ Extracted:')[1].strip()
            func_name = parts.split('(')[0].strip()
            extracted_functions.append(func_name)

    # Analysis
    print(f"\n📊 SOURCE FILE INVENTORY")
    print(f"   File: {source_file}")
    print(f"   Total lines: {len(source_content.split(chr(10)))}")
    print(f"")
    print(f"   Functions: {len(all_functions)}")
    print(f"   Classes: {len(all_classes)}")
    print(f"   Variables: {len(all_variables)}")
    print(f"   Imports: {len(all_imports)}")
    print(f"   Total definitions: {len(all_functions) + len(all_classes) + len(all_variables)}")

    print(f"\n📦 EXTRACTION RESULTS")
    if '✅ Extracted' in extracted_output:
        import re
        match = re.search(r'✅ Extracted (\d+)/(\d+) lines \((\d+) definitions\)', extracted_output)
        if match:
            extracted_lines = int(match.group(1))
            total_lines = int(match.group(2))
            extracted_defs = int(match.group(3))
            print(f"   Extracted: {extracted_lines}/{total_lines} lines ({extracted_lines/total_lines*100:.1f}%)")
            print(f"   Definitions: {extracted_defs}/{len(all_functions) + len(all_classes) + len(all_variables)} ({extracted_defs/(len(all_functions) + len(all_classes) + len(all_variables))*100:.1f}%)")

    print(f"\n✅ FUNCTIONS EXTRACTED")
    if extracted_functions:
        for func in extracted_functions:
            func_info = next((f for f in all_functions if f['name'] == func), None)
            if func_info:
                async_marker = '(async)' if func_info['async'] else ''
                decorator_marker = f" +{func_info['decorators']} decorators" if func_info['decorators'] > 0 else ""
                print(f"   ✓ {func}{async_marker}{decorator_marker}")
    else:
        print("   (None found in output)")

    print(f"\n❌ FUNCTIONS NOT EXTRACTED")
    missing_functions = [f for f in all_functions if f['name'] not in extracted_functions]
    if missing_functions:
        for func in missing_functions[:10]:  # Show first 10
            async_marker = '(async)' if func['async'] else ''
            decorator_marker = f" +{func['decorators']} decorators" if func['decorators'] > 0 else ""
            print(f"   ✗ {func['name']}{async_marker}{decorator_marker} (line {func['line']})")
        if len(missing_functions) > 10:
            print(f"   ... and {len(missing_functions) - 10} more")
    else:
        print("   (All functions extracted!)")

    print(f"\n🔍 KEY INDICATORS")

    # Check for decorator dependencies
    if '🔐 Found decorator dependencies:' in extracted_output:
        deps = extracted_output.split('🔐 Found decorator dependencies:')[1].split('\n')[0].strip()
        print(f"   ✅ Decorator dependencies found: {deps}")
    else:
        print(f"   ❌ No decorator dependencies found!")
        print(f"      This means dependency functions (verify_api_key, etc.) are NOT extracted!")

    # Check for HTTP endpoint mapping
    if '🌐 Mapped endpoints to handlers:' in extracted_output:
        handlers = extracted_output.split('🌐 Mapped endpoints to handlers:')[1].split('\n')[0].strip()
        print(f"   ✅ HTTP endpoint mapping: {handlers}")
    else:
        print(f"   ⚠️  No HTTP endpoint mapping")

    # Check for target functions
    if '🎯 Target functions:' in extracted_output:
        targets = extracted_output.split('🎯 Target functions:')[1].split('\n')[0].strip()
        print(f"   ✅ Target functions: {targets}")
    else:
        print(f"   ⚠️  No target functions identified")

    print(f"\n💡 RECOMMENDATIONS")

    # Check if decorator deps missing
    if '🔐 Found decorator dependencies:' not in extracted_output:
        print(f"   ⚠️  CRITICAL: Decorator dependencies NOT being extracted!")
        print(f"      Look for functions like: verify_api_key, authenticate, rate_limit")
        print(f"      These are needed for dependency overrides in tests!")

        # Find likely dependency functions
        likely_deps = [f for f in all_functions if any(keyword in f['name'].lower()
                      for keyword in ['verify', 'auth', 'check', 'validate', 'require'])]
        if likely_deps:
            print(f"\n      Likely dependency functions in source:")
            for func in likely_deps[:5]:
                print(f"         - {func['name']} (line {func['line']})")

    # Check extraction percentage
    if '✅ Extracted' in extracted_output:
        match = re.search(r'✅ Extracted (\d+)/(\d+) lines', extracted_output)
        if match:
            extracted_lines = int(match.group(1))
            total_lines = int(match.group(2))
            percentage = extracted_lines / total_lines * 100

            if percentage < 20:
                print(f"   ⚠️  Only {percentage:.1f}% of file extracted - this is normal for large files")
                print(f"      Extraction is TARGETED - only includes what's needed")
            elif percentage > 80:
                print(f"   ℹ️  {percentage:.1f}% of file extracted - most of file included")

    print(f"\n" + "=" * 80)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python diagnostic_extraction.py <source_file> <extraction_output>")
        print("")
        print("Example:")
        print("  python diagnostic_extraction.py app/main.py output.txt")
        sys.exit(1)

    source_file = sys.argv[1]
    output_file = sys.argv[2]

    with open(output_file, 'r') as f:
        extraction_output = f.read()

    analyze_extraction(source_file, extraction_output)
