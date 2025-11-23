#!/bin/bash
# Clear all pytest cache before running tests
# Use this script in your pipeline to ensure fresh test runs

echo "🧹 Clearing all pytest cache..."

# Remove pytest cache directory
if [ -d ".pytest_cache" ]; then
    rm -rf .pytest_cache
    echo "  ✓ Removed .pytest_cache/"
fi

# Remove pytest JSON report
if [ -f "pytest_report.json" ]; then
    rm -f pytest_report.json
    echo "  ✓ Removed pytest_report.json"
fi

# Remove Python bytecode cache
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
echo "  ✓ Removed all __pycache__ directories"

# Remove .pyc files
find . -type f -name "*.pyc" -delete 2>/dev/null
echo "  ✓ Removed all .pyc files"

# Remove coverage data (optional)
if [ -f ".coverage" ]; then
    rm -f .coverage
    echo "  ✓ Removed .coverage"
fi

if [ -d "htmlcov" ]; then
    rm -rf htmlcov
    echo "  ✓ Removed htmlcov/"
fi

echo "✅ Cache clearing complete!"
echo ""
