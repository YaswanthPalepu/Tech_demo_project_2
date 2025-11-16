# Auto Test Fixer - Implementation Summary

## Overview

Successfully implemented an **automated test fixer system** that intelligently fixes failing tests by distinguishing between test mistakes and code bugs.

## System Architecture

### Step-by-Step Logic (As Requested)

1. **Run pytest with JSON output**
   - Uses `pytest --json-report` when available
   - Falls back to text output parsing if JSON not available
   - Component: `FailureParser`

2. **Parse all failures into structured objects**
   - Each failure contains: test_file, test_name, exception_type, error_message, traceback, line_number
   - Component: `TestFailure` dataclass

3. **Classify failures**

   **A. Rule-based classifier**
   - Fast pattern matching against common test mistakes
   - Returns: "test_mistake" or "unknown"
   - Component: `RuleBasedClassifier`

   **B. LLM classifier**
   - Input: failing test code, AST source code, traceback + error
   - Output: JSON with classification ("test_mistake" | "code_bug"), reason, fixed_code, confidence
   - Component: `LLMClassifier`

4. **AST Context Extraction**
   - Based on imports → extract only relevant:
     - Classes
     - Functions
     - Routes
     - Models
     - Utils
   - Filters out stdlib and third-party imports
   - Component: `ASTContextExtractor`

5. **LLM Fixer**
   - Generates fixed version of test function or full file
   - Uses context from AST extraction
   - Supports retry with different approaches
   - Component: `LLMFixer`

6. **AST Patcher**
   - Replaces only failing function in the test file
   - Preserves all other code, imports, formatting
   - Uses AST manipulation for precision
   - Component: `ASTPatcher`

7. **Re-run pytest**
   - Continues until:
     - All test_mistake failures fixed, OR
     - Code_bug failures remain untouched, OR
     - Max iterations reached

8. **Stop after max_iterations = 3** (configurable)

## Implemented Components

### 1. Failure Parser (`src/auto_fixer/failure_parser.py`)
- Runs pytest with JSON or text output
- Parses failures into `TestFailure` objects
- Extracts structured information from tracebacks

### 2. Rule-Based Classifier (`src/auto_fixer/rule_classifier.py`)
- Pattern-based classification
- Handles 15+ common test mistake patterns:
  - Import errors
  - Fixture issues
  - Mock problems
  - Syntax errors
  - Database setup issues
  - Async errors

### 3. LLM Classifier (`src/auto_fixer/llm_classifier.py`)
- Azure OpenAI integration
- Returns structured classification with:
  - Classification type
  - Reason
  - Suggested fix (for test mistakes)
  - Confidence score

### 4. AST Context Extractor (`src/auto_fixer/ast_context_extractor.py`)
- Analyzes test file imports
- Resolves imports to source files
- Extracts relevant code elements
- Filters out stdlib/third-party code

### 5. LLM Fixer (`src/auto_fixer/llm_fixer.py`)
- Generates fixed test functions
- Supports full file fixes
- Handles retry with context

### 6. AST Patcher (`src/auto_fixer/ast_patcher.py`)
- Precise function replacement
- Preserves indentation and formatting
- Validates patches before writing

### 7. Orchestrator (`src/auto_fixer/orchestrator.py`)
- Coordinates entire workflow
- Implements iterative fix-and-rerun loop
- Tracks fix history
- Generates detailed reports

### 8. CLI Interface (`run_auto_fixer.py`)
- Command-line tool for running the fixer
- Configurable options:
  - `--test-dir`: Test directory
  - `--project-root`: Project root
  - `--max-iterations`: Max fix iterations
  - `--pytest-args`: Additional pytest arguments

## File Structure

```
src/auto_fixer/
├── __init__.py                  # Module exports
├── README.md                    # Detailed documentation
├── failure_parser.py            # Pytest output parser
├── rule_classifier.py           # Rule-based classification
├── llm_classifier.py            # LLM-based classification
├── ast_context_extractor.py    # Source code context extraction
├── llm_fixer.py                # Test fix generation
├── ast_patcher.py              # AST-based patching
└── orchestrator.py             # Main workflow orchestrator

run_auto_fixer.py               # CLI entry point
requirements.txt                # Updated with pytest-json-report
```

## Usage Examples

### Basic Usage
```bash
python run_auto_fixer.py
```

### Advanced Usage
```bash
python run_auto_fixer.py \
  --test-dir tests/generated \
  --max-iterations 5 \
  --pytest-args "-v,-x"
```

### Python API
```python
from src.auto_fixer import AutoTestFixerOrchestrator

orchestrator = AutoTestFixerOrchestrator(
    test_directory="tests",
    max_iterations=3
)

summary = orchestrator.run()
print(f"Fixed: {summary['successful_fixes']}")
print(f"Code bugs: {summary['code_bugs']}")
```

## Demo Files

Created demo files to test the system:

- `demo_calculator.py`: Simple calculator with functions and class
- `tests/test_calculator_demo.py`: Test file with intentional mistakes:
  - Missing imports
  - Typos in fixture names
  - Wrong class names
  - Missing fixtures

## Output

The system generates:

1. **Console output**: Real-time progress
2. **auto_fixer_report.json**: Detailed JSON report with:
   - Iteration count
   - Total failures
   - Test mistakes vs code bugs
   - Fix success/failure
   - Complete fix history

## Key Features

✅ **Intelligent Classification**: Distinguishes test mistakes from code bugs
✅ **Iterative Fixing**: Re-runs tests until all test mistakes are fixed
✅ **Max Iterations**: Prevents infinite loops (default: 3)
✅ **Precise Patching**: Only modifies failing functions
✅ **Context-Aware**: Extracts relevant source code for accurate fixes
✅ **Dual Classification**: Rule-based + LLM for accuracy
✅ **Comprehensive Logging**: Detailed reports and history
✅ **Fallback Support**: Works with or without pytest-json-report

## Dependencies Added

- `pytest-json-report>=1.5.0`: For structured test output (optional)

## Integration with Existing System

The auto-fixer integrates seamlessly with the existing test generation system:

- Uses the same Azure OpenAI client (`src/gen/openai_client.py`)
- Leverages existing AST analysis capabilities
- Compatible with generated tests from the test generation pipeline
- Can be run as part of CI/CD after test generation

## Future Enhancements

Possible improvements:
- Support for other test frameworks (unittest, nose)
- Integration with coverage reports
- Batch processing of similar failures
- Learning from successful fixes
- Custom classification rules
- Parallel fix attempts

## Testing

To test the auto-fixer:

1. Run on the demo file:
   ```bash
   python run_auto_fixer.py --test-dir tests
   ```

2. Check the generated report:
   ```bash
   cat auto_fixer_report.json
   ```

3. Verify fixes were applied:
   ```bash
   git diff tests/test_calculator_demo.py
   ```

## Configuration

Set environment variables for LLM access:

```bash
export AZURE_OPENAI_KEY="your-key"
export AZURE_OPENAI_ENDPOINT="https://your-endpoint.openai.azure.com/"
export AZURE_OPENAI_DEPLOYMENT="gpt-4"
```

## Conclusion

Successfully implemented a complete auto-test-fixer system following the exact step-by-step logic provided:

1. ✅ Run pytest with JSON output
2. ✅ Parse failures into structured objects
3. ✅ Rule-based + LLM classification
4. ✅ AST context extraction
5. ✅ LLM fix generation
6. ✅ AST patching
7. ✅ Re-run pytest loop
8. ✅ Max iterations limit

The system is ready for use and can automatically fix common test mistakes while leaving code bugs for manual review.
