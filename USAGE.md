# AI TestGen - Complete Coverage Guide

## Quick Start

### 1. Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Set OpenAI credentials (use your Azure OpenAI or OpenAI key)
export AZURE_OPENAI_API_KEY="your-key"
export AZURE_OPENAI_ENDPOINT="your-endpoint"
export AZURE_OPENAI_DEPLOYMENT="your-deployment"
```

### 2. Generate Tests for ANY Python Project
```bash
# Analyze and generate tests
python -m src.gen --target /path/to/any/python/project --force

# Example: Test a Django project
python -m src.gen --target ~/projects/my-django-app --force

# Example: Test a Flask project
python -m src.gen --target ~/projects/my-flask-api --force

# Example: Test a FastAPI project
python -m src.gen --target ~/projects/my-fastapi-service --force
```

### 3. Run Tests with Coverage
```bash
# Run generated tests
pytest tests/generated -v

# Run with coverage report
pytest tests/generated --cov=/path/to/your/project --cov-report=html --cov-report=xml

# View HTML coverage report
open htmlcov/index.html
```

## Key Features

### ✅ Repository Agnostic
- Works with ANY Python project
- Auto-detects Django, Flask, FastAPI, or plain Python
- No manual configuration needed

### ✅ Automatic Environment Setup
- Detects required packages from imports
- Auto-installs test dependencies
- Configures framework-specific test environments

### ✅ Complete Coverage (80%+ Target)
- Analyzes ALL code: functions, classes, methods
- Tests ALL code paths and branches
- Generates 5-10 test methods per target
- Includes edge cases and error handling

### ✅ Real Code Testing
- Imports and tests actual source code
- No stubs unless absolutely necessary
- Tests real database operations (with fixtures)
- Tests real API endpoints

### ✅ Robust Target Selection
- Captures every function, class, and method
- No code is missed
- Distributes targets evenly across test files
- Handles large codebases efficiently

## Advanced Usage

### Analyze Only (Dry Run)
```bash
python -m src.gen --target /path/to/project --dry-run
```

### Custom Output Directory
```bash
python -m src.gen --target /path/to/project --outdir custom/test/dir
```

### Debug Mode
```bash
TESTGEN_DEBUG=1 python -m src.gen --target /path/to/project
```

### Incremental Testing (Changed Files Only)
```bash
# Without --force, only changed files are tested
python -m src.gen --target /path/to/project
```

## Coverage Improvement Tips

1. **Run multiple times**: AI generation improves with retries
2. **Review generated tests**: Add manual tests for complex logic
3. **Check coverage report**: `htmlcov/index.html` shows uncovered lines
4. **Add integration tests**: Some code needs real database/API testing

## Framework-Specific Notes

### Django Projects
- Auto-configures Django settings
- Tests models, views, serializers, forms
- Uses Django TestCase automatically

### Flask Projects
- Auto-creates Flask test client
- Tests routes and blueprints
- Handles Flask-RESTX APIs

### FastAPI Projects
- Uses FastAPI TestClient
- Tests all endpoints
- Handles async routes

### Plain Python
- Standard pytest tests
- Tests all functions and classes
- No framework overhead

## Troubleshooting

### Low Coverage?
- Run generation again: `python -m src.gen --target /path --force`
- Check if source code is importable
- Verify dependencies are installed

### Import Errors?
- Ensure project is in PYTHONPATH
- Install project dependencies: `pip install -e /path/to/project`

### Tests Failing?
- Check if database/services are needed
- Add fixtures in `tests/generated/conftest.py`
- Review test code and adjust

## Output Structure
```
tests/generated/
├── conftest.py              # Auto-generated fixtures
├── test_unit_20240101_120000_01.py
├── test_unit_20240101_120000_02.py
├── test_integ_20240101_120000_01.py
└── manifest.json            # Generation metadata
```

## Coverage Reports
```
htmlcov/index.html           # HTML coverage report
coverage.xml                 # XML coverage (for CI/CD)
.coverage                    # Coverage database
```
