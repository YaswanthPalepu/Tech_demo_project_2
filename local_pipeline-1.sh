#!/bin/bash
set -euo pipefail
trap 'echo "❌ Script failed at line $LINENO"; exit 1' ERR

echo "🚀 Starting Local Pipeline 1 - Manual + AI Test Flow"
echo "==================================================================="
echo ""

# 1️⃣ Set target directory flask-high-coverage-repo
export CURRENT_DIR="/home/sigmoid/TECH_DEMO/new-tech-demo"
export TARGET_DIR="/home/sigmoid/test-repos/backend_code"
export TARGET_ROOT="$TARGET_DIR"
export PYTHONPATH="$TARGET_DIR"
echo "🎯 Target Directory: $TARGET_DIR"
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
if [[ "${FOUND,,}" == "true" ]]; then
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
    pip install -r "$TARGET_DIR/requirements.txt"
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

  echo "🧪 Running manual tests from local directory: ./tests/manual"
  echo ""

  pytest "$CURRENT_DIR/tests/manual" \
    --cov=$TARGET_DIR \
    --cov-config=.coveragerc \
    --cov-report=term-missing \
    --cov-report=xml \
    --cov-report=html \
    --cov-fail-under=70 \
    -v || true

  echo "📊 Debug: Coverage report details"
  coverage report --show-missing

  echo ""
  echo "✅ Pytest completed for manual tests."
  echo ""

  if [ -f coverage.xml ]; then
    COVERAGE=$(python3 -c "import xml.etree.ElementTree as ET; \
      tree = ET.parse('coverage.xml'); root = tree.getroot(); \
      print(f'{float(root.attrib.get(\"line-rate\", 0)) * 100:.2f}')")
    echo "✅ Manual Test Coverage: $COVERAGE%"
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

#remove previous test cases
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
  pip install -r "$TARGET_DIR/requirements.txt"
else
  echo "⚠️ No requirements.txt found — skipping dependency installation"
fi

# Run pytest on AI-generated tests
if [ "$TEST_COUNT" -gt 0 ]; then
  echo "🧪 Running pytest on AI-generated tests..."
  pytest "$CURRENT_DIR/tests/generated" \
    --cov=$TARGET_DIR \
    --cov-report=term-missing \
    --cov-report=xml \
    --cov-report=html \
    --cov-fail-under=70 \
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
  else
    COVERAGE=0
    echo "❌ No coverage.xml found"
  fi

  # Optional: Commented artifact saving
  # mkdir -p local_artifacts/ai-test-coverage
  # cp coverage.xml local_artifacts/ai-test-coverage/ 2>/dev/null || true
  # cp -r htmlcov/ local_artifacts/ai-test-coverage/ 2>/dev/null || true
  # echo "📤 Saved coverage artifacts for AI tests."
  # echo ""

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
