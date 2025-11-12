#!/bin/bash
set -euo pipefail
trap 'echo "❌ Script failed at line $LINENO"; exit 1' ERR

echo "🚀 Starting Local Pipeline 1 - Manual + AI Test Flow"
echo "==================================================================="
echo ""

# 1️⃣ Set target directory flask-high-coverage-repo ecommerce clinic pytest-fun
export CURRENT_DIR="/home/sigmoid/TECH_DEMO/new-tech-demo"
export TARGET_DIR="/home/sigmoid/test-repos/clinic"
export TARGET_ROOT="$TARGET_DIR"
export PYTHONPATH="$TARGET_DIR"
echo "🎯 Target Directory: $TARGET_DIR"
echo ""

# 🧹 CRITICAL: Clean all coverage artifacts before starting
echo "🧹 Cleaning previous coverage data..."
rm -f .coverage
rm -f coverage.xml
rm -rf htmlcov/
rm -rf .pytest_cache/
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$TARGET_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
echo "✅ Coverage data cleaned"
echo ""


# 2️⃣ Detect Manual Tests
echo "🔍 Running detect_manual_tests.py on target repo..."
python src/detect_manual_tests.py "$TARGET_DIR" || true

FOUND=$(python3 -c "import json; print(json.load(open('manual_test_result.json'))['manual_tests_found'])")
PATHS=$(python3 -c "import json; print(' '.join(json.load(open('manual_test_result.json'))['manual_test_paths']))")

echo ""
echo "📁 Manual Tests Found: $FOUND"
echo "📂 Test Paths: $PATHS"
echo ""

# -------------------------------------------------------------------
# CASE 1️⃣: Manual Tests Found
# -------------------------------------------------------------------
if [[ "${FOUND,,}" == "false" ]]; then
  echo "✅ Manual test cases detected. Running pytest..."
  echo ""

  export JSON_FILE="manual_test_result.json"
  export TEST_PATHS=$(python3 - <<'PYCODE'
import json
with open("manual_test_result.json") as f:
    data = json.load(f)
print(" ".join(data.get("manual_test_paths", [])))
PYCODE
)
  
  # 📦 Install project dependencies if requirements.txt exists
  if [ -f "$TARGET_DIR/requirements.txt" ]; then
    echo "📦 Installing project dependencies..."
    pip install -q -r "$TARGET_DIR/requirements.txt"
  else
    echo "⚠️ No requirements.txt found — skipping dependency installation"
  fi
  echo ""

  echo "📂 Copying manual tests to local folder: ./tests/manual"
  rm -rf "./tests/manual"
  mkdir -p ./tests/manual

  # Copy all manual test files to local tests/manual/
  for path in $TEST_PATHS; do
    if [ -f "$path" ]; then
      cp "$path" ./tests/manual/
    elif [ -d "$path" ]; then
      cp -r "$path"/* ./tests/manual/ 2>/dev/null || true
    fi
  done

  echo ""
  echo "✅ Manual test files copied to ./tests/manual"
  echo "📄 Files:"
  find ./tests/manual -type f -name 'test_*.py'
  echo ""

  # 🧹 Clean cache again after copying
  find ./tests/manual -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

  echo "🧪 Running manual tests from local directory: ./tests/manual"
  echo ""

  # Run pytest with explicit source path
  pytest "$CURRENT_DIR/tests/manual" \
    --cov="$TARGET_DIR" \
    --cov-config=pytest.ini \
    --cov-report=term-missing \
    --cov-report=xml \
    --cov-report=html \
    -v || true

  echo ""
  echo "✅ Pytest completed for manual tests."
  echo ""

  if [ -f coverage.xml ]; then
    COVERAGE=$(python3 -c "import xml.etree.ElementTree as ET; \
      tree = ET.parse('coverage.xml'); root = tree.getroot(); \
      print(f'{float(root.attrib.get(\"line-rate\", 0)) * 100:.2f}')")
    echo "✅ Manual Test Coverage: $COVERAGE%"
    
    # Show which files were covered
    echo ""
    echo "📊 Coverage Summary:"
    python3 - <<'PYCODE'
import xml.etree.ElementTree as ET
tree = ET.parse('coverage.xml')
root = tree.getroot()
for pkg in root.findall('.//package'):
    for cls in pkg.findall('.//class'):
        filename = cls.get('filename')
        line_rate = float(cls.get('line-rate', 0)) * 100
        print(f"  {filename}: {line_rate:.1f}%")
PYCODE
  else
    COVERAGE=0
    echo "❌ No coverage.xml found"
  fi

  MIN_COVERAGE=70
  if (( $(echo "$COVERAGE < $MIN_COVERAGE" | bc -l) )); then
    echo "❌ Quality Gate Failed: Coverage below ${MIN_COVERAGE}%"
    exit 1
  else
    echo "✅ Quality Gate Passed: Coverage ${COVERAGE}% ≥ ${MIN_COVERAGE}%"
  fi

  echo ""
  echo "🎯 Local Pipeline 1 completed successfully with manual tests!"
  exit 0
fi

# -------------------------------------------------------------------
# CASE 2️⃣: No Manual Tests Found → Generate AI Tests
# -------------------------------------------------------------------
echo "⚠️ No manual tests found. Proceeding with AI Test Generation..."
echo ""

echo "=== Starting granular AI test generation ==="
export TESTGEN_FORCE=true
echo "Force regeneration: $TESTGEN_FORCE"

# Remove previous test cases
rm -rf "./tests/generated"


# Run AI test generator
python -m src.gen --target "$TARGET_ROOT" --outdir "./tests/generated" --force

echo "=== AI Test Generation Completed ==="

# Count generated tests
if [ -d "./tests/generated" ]; then
  TEST_COUNT=$(find "./tests/generated" -name 'test_*.py' -type f | wc -l)
  echo "🧩 Total AI-generated test files: $TEST_COUNT"
  find "./tests/generated" -name 'test_*.py' -type f | head -10
else
  echo "❌ No tests generated!"
  TEST_COUNT=0
fi

echo ""

# 📦 Install project dependencies if requirements.txt exists
if [ -f "$TARGET_DIR/requirements.txt" ]; then
  echo "📦 Installing project dependencies..."
  pip install -q -r "$TARGET_DIR/requirements.txt"
else
  echo "⚠️ No requirements.txt found — skipping dependency installation"
fi

# 🧹 Clean cache for generated tests
find ./tests/generated -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# Run pytest on AI-generated tests
if [ "$TEST_COUNT" -gt 0 ]; then
  echo "🧪 Running pytest on AI-generated tests..."
  
  pytest "$CURRENT_DIR/tests/generated" \
    --cov="$TARGET_DIR" \
    --cov-config=pytest.ini \
    --cov-report=term-missing \
    --cov-report=xml \
    --cov-report=html \
    -v || true

  echo ""
  echo "✅ Pytest completed for AI-generated tests."
  echo ""

  # Parse coverage
  if [ -f coverage.xml ]; then
    COVERAGE=$(python3 -c "import xml.etree.ElementTree as ET; \
      tree = ET.parse('coverage.xml'); root = tree.getroot(); \
      print(f'{float(root.attrib.get(\"line-rate\", 0)) * 100:.2f}')")
    echo "✅ AI Test Coverage: $COVERAGE%"
    
    # Show which files were covered
    echo ""
    echo "📊 Coverage Summary:"
    python3 - <<'PYCODE'
import xml.etree.ElementTree as ET
tree = ET.parse('coverage.xml')
root = tree.getroot()
for pkg in root.findall('.//package'):
    for cls in pkg.findall('.//class'):
        filename = cls.get('filename')
        line_rate = float(cls.get('line-rate', 0)) * 100
        print(f"  {filename}: {line_rate:.1f}%")
PYCODE
  else
    COVERAGE=0
    echo "❌ No coverage.xml found"
  fi

  MIN_COVERAGE=70
  if (( $(echo "$COVERAGE < $MIN_COVERAGE" | bc -l) )); then
    echo "❌ Quality Gate Failed: Coverage below ${MIN_COVERAGE}%"
    exit 1
  else
    echo "✅ Quality Gate Passed: Coverage ${COVERAGE}% ≥ ${MIN_COVERAGE}%"
  fi

  echo ""
  echo "🎯 Local Pipeline 1 completed successfully with AI-generated tests!"
  exit 0
else
  echo "❌ No AI-generated tests found. Pipeline cannot proceed."
  exit 1
fi