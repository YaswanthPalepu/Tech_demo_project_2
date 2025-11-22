#!/bin/bash
"""
Clear all auto-fixer caches and force rebuild with new fixes

This clears:
1. .codebase_index/ - Embedding index cache (has OLD full function bodies)
2. __pycache__ - Python bytecode cache
3. .pytest_cache - Pytest cache
4. Any *.pyc files

After clearing, the next run will rebuild the index with the NEW smart
summary logic, reducing token usage by 75%.
"""

set -e  # Exit on error

echo "================================================================================"
echo "CACHE CLEANUP - Force Rebuild with Smart Summaries"
echo "================================================================================"

# Find all cache locations
PROJECT_ROOT="/home/sigmoid/test-repos/backend_code"
TECH_DEMO_ROOT="."

echo ""
echo "🔍 Finding cache directories..."

# Check for codebase index caches
CACHES_FOUND=0

for dir in "$PROJECT_ROOT" "$TECH_DEMO_ROOT"; do
    if [ -d "$dir/.codebase_index" ]; then
        echo "   Found: $dir/.codebase_index"
        CACHES_FOUND=$((CACHES_FOUND + 1))
    fi
done

if [ -d "$PROJECT_ROOT/__pycache__" ]; then
    echo "   Found: $PROJECT_ROOT/__pycache__"
    CACHES_FOUND=$((CACHES_FOUND + 1))
fi

if [ -d "$PROJECT_ROOT/.pytest_cache" ]; then
    echo "   Found: $PROJECT_ROOT/.pytest_cache"
    CACHES_FOUND=$((CACHES_FOUND + 1))
fi

# Check in tech demo
if [ -d "$TECH_DEMO_ROOT/.codebase_index" ]; then
    echo "   Found: $TECH_DEMO_ROOT/.codebase_index"
    CACHES_FOUND=$((CACHES_FOUND + 1))
fi

echo ""
echo "📊 Total cache locations found: $CACHES_FOUND"

if [ $CACHES_FOUND -eq 0 ]; then
    echo "✅ No caches found - nothing to clean!"
    exit 0
fi

echo ""
echo "⚠️  These caches contain OLD data from BEFORE the smart summary fix!"
echo "   They need to be cleared to use the new token-optimized code."
echo ""
read -p "Clear all caches? (y/n) " -n 1 -r
echo

if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Cancelled - no changes made"
    exit 1
fi

echo ""
echo "🧹 Clearing caches..."

# Clear backend_code caches
if [ -d "$PROJECT_ROOT/.codebase_index" ]; then
    echo "   Removing $PROJECT_ROOT/.codebase_index..."
    rm -rf "$PROJECT_ROOT/.codebase_index"
    echo "      ✓ Removed"
fi

if [ -d "$PROJECT_ROOT/__pycache__" ]; then
    echo "   Removing $PROJECT_ROOT/__pycache__..."
    rm -rf "$PROJECT_ROOT/__pycache__"
    echo "      ✓ Removed"
fi

if [ -d "$PROJECT_ROOT/.pytest_cache" ]; then
    echo "   Removing $PROJECT_ROOT/.pytest_cache..."
    rm -rf "$PROJECT_ROOT/.pytest_cache"
    echo "      ✓ Removed"
fi

# Clear tech demo caches
if [ -d "$TECH_DEMO_ROOT/.codebase_index" ]; then
    echo "   Removing $TECH_DEMO_ROOT/.codebase_index..."
    rm -rf "$TECH_DEMO_ROOT/.codebase_index"
    echo "      ✓ Removed"
fi

# Clear any *.pyc files
echo "   Removing *.pyc files..."
find "$PROJECT_ROOT" -name "*.pyc" -delete 2>/dev/null || true
find "$TECH_DEMO_ROOT/src" -name "*.pyc" -delete 2>/dev/null || true
echo "      ✓ Removed"

echo ""
echo "================================================================================"
echo "✅ CACHE CLEANUP COMPLETE"
echo "================================================================================"
echo ""
echo "📊 What happens next:"
echo "   1. Next auto-fixer run will rebuild the embedding index"
echo "   2. New index will use SMART SUMMARIES (signature + 15 lines)"
echo "   3. Token usage will drop from ~32k to ~8k (75% reduction)"
echo "   4. Each CodeElement will be 15-20 lines instead of 50-200 lines"
echo ""
echo "🧪 To verify the fix worked, run:"
echo "   python inspect_embeddings.py --project-root $PROJECT_ROOT"
echo ""
echo "   Before fix: ~177 lines stored (but full bodies)"
echo "   After fix:  ~100-150 lines stored (smart summaries)"
echo ""
echo "✅ Ready to run auto-fixer with optimized token usage!"
