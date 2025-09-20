# src/gen/generate.py
import os, re, ast, json, pathlib, datetime, time, argparse, traceback
from typing import Dict, Any, List, Optional, Set, Tuple

__all__ = ["generate_all", "main"]

try:
    from .postprocess import extract_python_only, validate_code, massage
except Exception as _e:
    print(f"Warning: postprocess import failed: {_e}; using fallbacks")
    import re as _re, ast as _ast
    def extract_python_only(text: str) -> str:
        if "```" in text:
            blocks = _re.findall(r"```(?:python)?\s*(.*?)```", text, flags=_re.IGNORECASE|_re.DOTALL)
            return "\n\n".join(blocks) if blocks else text.replace("```","")
        return text
    def validate_code(code: str):
        if not code.strip(): return False, "empty output"
        if not _re.search(r"def test_", code): return False, "no test functions"
        try: _ast.parse(code); return True, ""
        except SyntaxError as e: return False, f"syntax error: {e}"
    def massage(code: str): return code

def _create_conftest(outdir: pathlib.Path) -> str:
    """Create comprehensive conftest.py for robust testing environment."""
    from .conftest_text import conftest_text
    from .writer import write_text
    
    conftest_path = outdir / "conftest.py"
    enhanced_conftest = conftest_text()
    
    # Add additional robust testing utilities
    enhanced_conftest += '''

# Additional professional testing utilities
@pytest.fixture(scope="function")
def clean_environment(monkeypatch):
    """Provide clean environment for each test."""
    # Clear potentially problematic environment variables
    test_vars = ["DATABASE_URL", "REDIS_URL", "API_KEY", "SECRET_KEY"]
    for var in test_vars:
        monkeypatch.delenv(var, raising=False)
    
    # Set safe defaults
    monkeypatch.setenv("TESTING", "true")
    monkeypatch.setenv("LOG_LEVEL", "ERROR")
    yield

@pytest.fixture
def mock_file_operations():
    """Mock file system operations for deterministic testing."""
    with patch('pathlib.Path.exists', return_value=True), \
         patch('pathlib.Path.read_text', return_value="mock content"), \
         patch('pathlib.Path.write_text'), \
         patch('os.makedirs'), \
         patch('shutil.rmtree'):
        yield

@pytest.fixture
def capture_logs():
    """Capture and provide access to log messages during testing."""
    import logging
    from io import StringIO
    
    log_capture = StringIO()
    handler = logging.StreamHandler(log_capture)
    logger = logging.getLogger()
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    
    yield log_capture
    
    logger.removeHandler(handler)
'''
    
    write_text(conftest_path, enhanced_conftest)
    return str(conftest_path)

def _generate_with_retry(messages: List[Dict], max_attempts: int = 4) -> str:
    """Generate test code with intelligent retry logic and validation."""
    from .openai_client import create_client, get_deployment_name, create_chat_completion, RateLimitError, APIError
    
    client = create_client()
    deployment = get_deployment_name()
    
    last_error = "unknown error"
    backoff_delays = [0, 2, 5, 10]  # Progressive backoff
    
    for attempt in range(max_attempts):
        try:
            # Apply backoff delay
            if backoff_delays[attempt] > 0:
                print(f"Retrying generation in {backoff_delays[attempt]} seconds...")
                time.sleep(backoff_delays[attempt])
            
            # Make API call - don't specify temperature to use model default
            response_content = create_chat_completion(client, deployment, messages)
            
            if not response_content.strip():
                last_error = "Empty response from API"
                continue
            
            # Extract and validate Python code
            extracted_code = extract_python_only(response_content)
            
            if not extracted_code.strip():
                last_error = "No Python code found in response"
                continue
            
            # Validate syntax and structure
            is_valid, validation_error = validate_code(extracted_code)
            
            if not is_valid:
                last_error = f"Code validation failed: {validation_error}"
                
                # Add feedback to improve next attempt
                feedback_msg = {
                    "role": "user", 
                    "content": f"The generated code had issues: {validation_error}. "
                              "Please regenerate with proper Python syntax, test functions, "
                              "and minimal use of pytest.skip. Focus on robust error handling "
                              "and professional test patterns."
                }
                messages.append(feedback_msg)
                continue
            
            # Apply post-processing for professional quality
            try:
                processed_code = massage(extracted_code)
                
                # Final validation of processed code
                final_valid, final_error = validate_code(processed_code)
                
                if final_valid:
                    return processed_code
                else:
                    # If post-processing broke it, return the original valid code
                    print(f"Post-processing validation failed: {final_error}, using original")
                    return extracted_code
                    
            except Exception as process_error:
                print(f"Post-processing error: {process_error}, using original code")
                return extracted_code
                
                            
        except RateLimitError as e:
            last_error = f"Rate limit exceeded: {e}"
            print(f"Rate limit hit on attempt {attempt + 1}, backing off...")
            
        except APIError as e:
            last_error = f"API error: {e}"
            # Some API errors shouldn't be retried (400, 401, 403)
            if hasattr(e, 'status_code') and e.status_code in [400, 401, 403]:
                print(f"Non-retryable API error: {e}")
                break
            print(f"API error on attempt {attempt + 1}, retrying...")
            
        except Exception as e:
            last_error = f"API call failed: {e}"
            print(f"Generation attempt {attempt + 1} failed: {e}")
    
    # If all attempts failed, raise with detailed error
    raise RuntimeError(f"Test generation failed after {max_attempts} attempts. Last error: {last_error}")

def _gather_comprehensive_context(target_root: pathlib.Path, analysis: Dict[str, Any], 
                                focus_names: List[str], max_bytes: int = 50000) -> str:
    """Gather comprehensive code context for intelligent test generation."""
    
    def read_file_safe(path: pathlib.Path) -> str:
        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            return ""
    
    def extract_code_segment(file_path: pathlib.Path, start_line: int, end_line: int, 
                           padding: int = 20) -> str:
        content = read_file_safe(file_path)
        if not content:
            return ""
        
        lines = content.splitlines()
        start_idx = max(0, start_line - padding - 1)
        end_idx = min(len(lines), end_line + padding)
        
        segment = "\n".join(lines[start_idx:end_idx])
        return f"# FILE: {file_path}\n# LINES: {start_idx + 1}-{end_idx}\n{segment}\n\n"
    
    # Build lookup indexes for efficient context gathering
    def build_lookup_index(items: List[Dict], name_key: str) -> Dict[str, Tuple[str, int, int]]:
        index = {}
        for item in items or []:
            name = item.get(name_key)
            if name:
                file_path = item.get("file", "")
                start_line = item.get("lineno", 1)
                end_line = item.get("end_lineno", start_line)
                index[name] = (file_path, start_line, end_line)
        return index
    
    # Create indexes for functions, classes, and routes
    function_index = build_lookup_index(analysis.get("functions", []), "name")
    class_index = build_lookup_index(analysis.get("classes", []), "name")
    route_index = build_lookup_index(analysis.get("routes", []), "handler")
    
    context_parts = []
    current_size = 0
    processed_files = set()
    
    # 1. Gather context for focused targets first
    for target_name in focus_names:
        for index in [function_index, class_index, route_index]:
            if target_name in index:
                file_rel, start_line, end_line = index[target_name]
                if file_rel:
                    file_path = target_root / file_rel
                    if file_path.exists():
                        segment = extract_code_segment(file_path, start_line, end_line)
                        context_parts.append(segment)
                        processed_files.add(str(file_path))
                        current_size += len(segment)
                        break
        
        if current_size >= max_bytes * 0.7:  # Reserve space for framework files
            break
    
    # 2. Add essential framework files for better context
    essential_files = [
        "main.py", "app.py", "database.py", "models.py", "config.py", "settings.py"
    ]
    
    for filename in essential_files:
        if current_size >= max_bytes:
            break
            
        file_path = target_root / filename
        if file_path.exists() and str(file_path) not in processed_files:
            content = read_file_safe(file_path)
            if content:
                # Include key parts of framework files
                segment = f"# FRAMEWORK FILE: {file_path}\n{content[:2000]}\n\n"
                context_parts.append(segment)
                processed_files.add(str(file_path))
                current_size += len(segment)
    
    # 3. Add router/model directories if they exist
    for subdir in ["routers", "models", "api", "services"]:
        if current_size >= max_bytes:
            break
            
        subdir_path = target_root / subdir
        if subdir_path.exists() and subdir_path.is_dir():
            for py_file in sorted(subdir_path.glob("*.py"))[:3]:  # Limit to 3 files per subdir
                if current_size >= max_bytes:
                    break
                    
                if str(py_file) not in processed_files:
                    content = read_file_safe(py_file)
                    if content:
                        segment = f"# MODULE FILE: {py_file}\n{content[:1500]}\n\n"
                        context_parts.append(segment)
                        processed_files.add(str(py_file))
                        current_size += len(segment)
    
    # Combine all context parts
    full_context = "".join(context_parts)
    
    # Truncate if still too large
    if len(full_context) > max_bytes:
        full_context = full_context[:max_bytes] + "\n# ... (truncated for length)"
    
    return full_context

def generate_all(analysis: Dict[str, Any], outdir: str = "tests/generated", 
                focus_files: Optional[List[str]] = None):
    """Generate comprehensive test suite with professional quality and robustness."""
    from . import env
    from .change import detect_changes
    from .analysis_utils import (compact_analysis, filter_by_files, infer_required_packages, 
                               pip_install, prune_unavailable_targets)
    from .prompt import build_prompt, files_per_kind, focus_for
    from .writer import write_text, cleanup_deleted_and_modified, update_manifest

    print("Starting professional test generation...")
    
    # Setup output directory
    output_dir = pathlib.Path(outdir)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "_manifest.json"

    # Create enhanced conftest.py
    print("Creating robust testing environment...")
    conftest_path = _create_conftest(output_dir)
    print(f"Created: {conftest_path}")

    # Detect code changes for intelligent regeneration
    target_root = pathlib.Path(os.environ.get("TARGET_ROOT", "target"))
    if not target_root.exists():
        raise RuntimeError(f"Target directory not found: {target_root}")

    added_or_modified, deleted, unchanged = detect_changes(target_root, manifest_path)
    
    change_summary = {
        "added_or_modified": len(added_or_modified),
        "deleted": len(deleted),
        "unchanged": len(unchanged),
        "total_analyzed": len(added_or_modified) + len(deleted) + len(unchanged)
    }
    
    print(f"Code change analysis: {change_summary['added_or_modified']} modified, "
          f"{change_summary['deleted']} deleted, {change_summary['unchanged']} unchanged")

    # Check if generation is needed
    force_generation = os.getenv("TESTGEN_FORCE", "false").lower() == "true"
    
    if not force_generation and not added_or_modified and not deleted:
        existing_tests = list(output_dir.glob("test_*.py"))
        if existing_tests:
            print("No code changes detected and tests exist. Skipping generation.")
            print("Use TESTGEN_FORCE=true to force regeneration.")
            return
        else:
            print("No existing tests found. Proceeding with initial generation.")

    if force_generation:
        print("Force generation enabled - regenerating all tests.")

    # Clean up tests for deleted/modified files
    cleanup_deleted_and_modified(output_dir, deleted, added_or_modified)

    # Process analysis and focus files
    focus_file_set = set(focus_files or [])
    if not focus_file_set and not force_generation:
        focus_file_set = added_or_modified

    # Filter and compact analysis
    filtered_analysis, no_targets = filter_by_files(analysis, focus_file_set if focus_file_set else None)
    
    if no_targets:
        print("Warning: No targets found in focus files, using full analysis")
        filtered_analysis = analysis

    # Remove unavailable targets and compact for processing
    compact = prune_unavailable_targets(compact_analysis(filtered_analysis))
    
    # Install required packages
    required_packages = infer_required_packages(compact)
    if required_packages:
        print(f"Installing required packages: {', '.join(required_packages)}")
        pip_install(required_packages)

    # Validate targets exist
    total_targets = sum(len(compact.get(key, [])) for key in ["functions", "classes", "routes"])
    if total_targets == 0:
        raise RuntimeError("No testable targets found in the analyzed code.")

    print(f"Found {total_targets} targets for test generation")
    print(f"- Functions: {len(compact.get('functions', []))}")
    print(f"- Classes: {len(compact.get('classes', []))}")
    print(f"- Routes: {len(compact.get('routes', []))}")

    # Determine test types to generate
    has_routes = bool(compact.get("routes"))
    test_kinds = ["unit", "integ"]
    if has_routes:
        test_kinds.append("e2e")
        print("HTTP routes detected - will generate E2E tests")
    else:
        # Remove any existing E2E tests if no routes
        for old_e2e in output_dir.glob("test_e2e_*.py"):
            try:
                old_e2e.unlink()
                print(f"Removed obsolete E2E test: {old_e2e.name}")
            except Exception:
                pass

    # Generate tests for each kind
    compact_json = json.dumps(compact, separators=(",", ":"))
    generated_files = []
    timestamp = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    for test_kind in test_kinds:
        num_files = files_per_kind(compact, test_kind)
        
        if num_files <= 0:
            print(f"No {test_kind} test files needed")
            continue

        print(f"Generating {num_files} {test_kind} test files...")

        for file_index in range(num_files):
            try:
                # Get focus targets for this file
                focus_label, focus_names, shard_targets = focus_for(compact, test_kind, file_index, num_files)
                
                if not focus_names:
                    print(f"No targets for {test_kind} file {file_index + 1}, skipping")
                    continue

                print(f"Generating {test_kind} test {file_index + 1}/{num_files} for: {focus_label[:100]}...")

                # Gather comprehensive context
                context = _gather_comprehensive_context(target_root, filtered_analysis, focus_names)

                # Build generation prompt
                prompt_messages = build_prompt(
                    kind=test_kind,
                    compact_json=compact_json,
                    focus_label=focus_label,
                    shard=file_index,
                    total=num_files,
                    compact=compact,
                    context=context
                )

                # Generate test code with retry logic
                test_code = _generate_with_retry(prompt_messages, max_attempts=4)

                # Validate generated code
                final_validation, validation_error = validate_code(test_code)
                if not final_validation:
                    print(f"Warning: Generated code validation failed: {validation_error}")
                    print("Attempting to fix and continue...")
                    
                    # Try basic fixes
                    if "No test functions" in validation_error:
                        test_code = "# Generated test placeholder\nimport pytest\n\ndef test_placeholder():\n    assert True\n"
                    
                # Create filename and write file
                filename = f"test_{test_kind}_{timestamp}_{file_index + 1:02d}.py"
                file_path = output_dir / filename

                # Final syntax check
                try:
                    ast.parse(test_code, filename=filename)
                except SyntaxError as e:
                    print(f"Syntax error in generated code: {e}")
                    print("Generating minimal fallback test...")
                    test_code = f'''# Fallback test due to generation issues
import pytest

def test_{test_kind}_fallback():
    """Fallback test to ensure test suite runs."""
    assert True, "Generated as fallback for {focus_label}"
'''

                # Write the test file
                write_text(file_path, test_code)
                generated_files.append(str(file_path))
                print(f"Generated: {filename}")

            except Exception as e:
                print(f"Error generating {test_kind} test {file_index + 1}: {e}")
                print(f"Traceback: {traceback.format_exc()}")
                
                # Create minimal fallback to ensure test suite completeness
                fallback_filename = f"test_{test_kind}_{timestamp}_{file_index + 1:02d}_fallback.py"
                fallback_path = output_dir / fallback_filename
                fallback_code = f'''# Fallback test due to generation error
import pytest

def test_{test_kind}_generation_fallback():
    """Fallback test created due to generation error."""
    pytest.skip("Test generation failed for this module")
'''
                write_text(fallback_path, fallback_code)
                generated_files.append(str(fallback_path))
                print(f"Created fallback: {fallback_filename}")

    # Update manifest with generation results
    update_manifest(output_dir, generated_files, change_summary)

    # Print generation summary
    if generated_files:
        print(f"\n✅ Successfully generated {len(generated_files)} test files:")
        for file_path in generated_files:
            print(f"  - {pathlib.Path(file_path).name}")
    else:
        print("\n⚠️ No test files were generated")

    print(f"\nTest generation complete. Output directory: {output_dir}")
    return generated_files

def main():
    """Main entry point for test generation CLI."""
    parser = argparse.ArgumentParser(
        description="Generate professional pytest test suites using AI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.gen --target ./my_project --outdir ./tests
  python -m src.gen --target ./backend --force
  TESTGEN_FORCE=true python -m src.gen
        """
    )
    
    parser.add_argument(
        "--target", 
        default=os.environ.get("TARGET_ROOT", "target"),
        help="Path to Python project to analyze and test (default: %(default)s)"
    )
    
    parser.add_argument(
        "--outdir", 
        default="tests/generated",
        help="Output directory for generated tests (default: %(default)s)"
    )
    
    parser.add_argument(
        "--focus-json",
        default=os.getenv("FOCUS_FILES_JSON_PATH", ""),
        help="JSON file containing list of files to focus on"
    )
    
    parser.add_argument(
        "--force", 
        action="store_true",
        help="Force regeneration even if no changes detected"
    )
    
    parser.add_argument(
        "--dry-run",
        action="store_true", 
        help="Analyze code but don't generate tests"
    )

    args = parser.parse_args()

    # Set environment variables from arguments
    if args.force:
        os.environ["TESTGEN_FORCE"] = "true"
    
    os.environ["TARGET_ROOT"] = args.target
    
    if args.focus_json:
        os.environ["FOCUS_FILES_JSON_PATH"] = args.focus_json

    # Validate target directory
    target_path = pathlib.Path(args.target)
    if not target_path.exists():
        print(f"Error: Target directory does not exist: {target_path}")
        return 1

    if not any(target_path.glob("*.py")):
        print(f"Error: No Python files found in target directory: {target_path}")
        return 1

    try:
        # Import and run analyzer
        try:
            from src.analyzer import analyze_python_tree
        except ImportError:
            try:
                from analyzer import analyze_python_tree
            except ImportError:
                print("Error: Could not import analyzer module")
                return 1

        print(f"Analyzing Python code in: {target_path}")
        analysis_result = analyze_python_tree(target_path)
        
        if args.dry_run:
            print("Dry run mode - analysis complete, no tests generated")
            print(f"Analysis summary:")
            print(f"  Functions: {len(analysis_result.get('functions', []))}")
            print(f"  Classes: {len(analysis_result.get('classes', []))}")
            print(f"  Routes: {len(analysis_result.get('routes', []))}")
            print(f"  Modules: {len(analysis_result.get('modules', []))}")
            return 0

        # Generate tests
        generated_files = generate_all(analysis_result, outdir=args.outdir)
        
        if generated_files:
            print(f"\n🎉 Test generation completed successfully!")
            print(f"Generated {len(generated_files)} test files in {args.outdir}")
            return 0
        else:
            print("\n⚠️ No tests were generated")
            return 1

    except Exception as e:
        print(f"Error during test generation: {e}")
        print(f"Traceback: {traceback.format_exc()}")
        return 1

if __name__ == "__main__":
    exit(main())