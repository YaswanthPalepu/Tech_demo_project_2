#!/bin/bash
# Verification script for improvements

echo "🔍 AI TestGen - Verification Script"
echo "===================================="
echo ""

# Check if files exist
echo "✓ Checking improved files..."
files=(
    "src/analyzer.py"
    "src/gen/enhanced_analysis_utils.py"
    "src/gen/enhanced_prompt.py"
    "src/gen/enhanced_generate.py"
    "src/gen/conftest_text.py"
    "pytest.ini"
)

for file in "${files[@]}"; do
    if [ -f "$file" ]; then
        echo "  ✓ $file"
    else
        echo "  ✗ $file (MISSING)"
    fi
done

echo ""
echo "📊 Testing analyzer on current project..."
python -m src.analyzer --root . --output analysis_test.json 2>&1 | head -20

echo ""
echo "🎯 Analysis complete. Check analysis_test.json for results."
echo ""
echo "📝 Next steps:"
echo "  1. Set OpenAI credentials:"
echo "     export AZURE_OPENAI_API_KEY='your-key'"
echo "     export AZURE_OPENAI_ENDPOINT='your-endpoint'"
echo "     export AZURE_OPENAI_DEPLOYMENT='your-deployment'"
echo ""
echo "  2. Test on any Python project:"
echo "     python -m src.gen --target /path/to/project --force"
echo ""
echo "  3. Run tests with coverage:"
echo "     pytest tests/generated --cov=/path/to/project --cov-report=html"
echo ""
echo "✅ Verification complete!"
