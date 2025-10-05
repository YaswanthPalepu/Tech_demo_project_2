# Quick Start - AI TestGen

## 1️⃣ Setup (One Time)
```bash
# Install dependencies
pip install -r requirements.txt

# Set OpenAI credentials
export AZURE_OPENAI_API_KEY="your-key-here"
export AZURE_OPENAI_ENDPOINT="https://your-endpoint.openai.azure.com/"
export AZURE_OPENAI_DEPLOYMENT="your-deployment-name"
```

## 2️⃣ Generate Tests (Any Project)
```bash
# Generate tests for ANY Python project
python -m src.gen --target /path/to/your/project --force
```

## 3️⃣ Run Tests
```bash
# Run with coverage
pytest tests/generated --cov=/path/to/your/project --cov-report=html

# View results
open htmlcov/index.html
```

## ✅ That's It!

### Expected Results
- ✅ 80%+ code coverage
- ✅ Tests use real imports (no stubs)
- ✅ Works with Django/Flask/FastAPI/any Python
- ✅ Auto-installs dependencies
- ✅ Tests all functions, classes, methods

### Examples
```bash
# Django project
python -m src.gen --target ~/my-django-blog --force

# Flask API
python -m src.gen --target ~/my-flask-api --force

# FastAPI service
python -m src.gen --target ~/my-fastapi-app --force

# Any Python code
python -m src.gen --target ~/my-python-lib --force
```

### Troubleshooting
- **Low coverage?** Run again: `python -m src.gen --target /path --force`
- **Import errors?** Install project: `pip install -e /path/to/project`
- **Need help?** Check `USAGE.md` for detailed guide

### Files Generated
```
tests/generated/
├── conftest.py                    # Auto-generated fixtures
├── test_unit_TIMESTAMP_01.py      # Unit tests
├── test_unit_TIMESTAMP_02.py
├── test_integ_TIMESTAMP_01.py     # Integration tests
└── manifest.json                  # Metadata
```

### Coverage Reports
```
htmlcov/index.html    # Visual coverage report
coverage.xml          # XML for CI/CD
.coverage             # Coverage database
```

## 🎯 Key Features
- 🌍 **Repository Agnostic**: Works with any Python project
- 🤖 **Auto Setup**: Detects and installs dependencies
- 📊 **80%+ Coverage**: Comprehensive test generation
- 🔧 **Real Code**: Tests actual imports, not stubs
- 🚀 **One Command**: No configuration needed

## 📚 More Info
- **Detailed Guide**: See `USAGE.md`
- **Improvements**: See `IMPROVEMENTS.md`
- **Implementation**: See `IMPLEMENTATION_SUMMARY.md`
