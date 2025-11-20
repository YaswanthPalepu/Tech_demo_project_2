#!/bin/bash
# Convenience script to run multi-iteration test generation
# This script orchestrates multiple rounds of AI test generation to achieve 90%+ coverage

set -e

# Default values
TARGET_DIR="app"
MAX_ITERATIONS=3
TARGET_COVERAGE=90.0
OUTPUT_DIR="tests/generated"

# Color codes for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --target)
            TARGET_DIR="$2"
            shift 2
            ;;
        --max-iterations)
            MAX_ITERATIONS="$2"
            shift 2
            ;;
        --target-coverage)
            TARGET_COVERAGE="$2"
            shift 2
            ;;
        --outdir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --help)
            echo "Multi-Iteration Test Generation Script"
            echo ""
            echo "Usage: ./run_multi_iteration_tests.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --target DIR            Target directory to test (default: app)"
            echo "  --max-iterations N      Maximum iterations (default: 3)"
            echo "  --target-coverage PCT   Target coverage percentage (default: 90.0)"
            echo "  --outdir DIR           Output directory (default: tests/generated)"
            echo "  --help                 Show this help message"
            echo ""
            echo "Example:"
            echo "  ./run_multi_iteration_tests.sh --target ./app --max-iterations 3"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Multi-Iteration Test Generation${NC}"
echo -e "${GREEN}========================================${NC}"
echo -e "Target Directory: ${YELLOW}${TARGET_DIR}${NC}"
echo -e "Max Iterations: ${YELLOW}${MAX_ITERATIONS}${NC}"
echo -e "Target Coverage: ${YELLOW}${TARGET_COVERAGE}%${NC}"
echo -e "Output Directory: ${YELLOW}${OUTPUT_DIR}${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Check if target directory exists
if [ ! -d "$TARGET_DIR" ]; then
    echo -e "${RED}Error: Target directory '$TARGET_DIR' not found${NC}"
    exit 1
fi

# Run multi-iteration test generator
echo -e "${GREEN}Starting multi-iteration test generation...${NC}"
echo ""

python -m src.multi_iteration_test_generator \
    --target "$TARGET_DIR" \
    --max-iterations "$MAX_ITERATIONS" \
    --target-coverage "$TARGET_COVERAGE" \
    --outdir "$OUTPUT_DIR"

EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo ""
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}✅ Multi-iteration generation completed!${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo ""
    echo "Generated files are in: $OUTPUT_DIR"
    echo "Coverage report: htmlcov/index.html"
    echo "Iteration log: iteration_log.json"
    echo "Full report: multi_iteration_report.txt"
else
    echo ""
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}❌ Multi-iteration generation failed${NC}"
    echo -e "${RED}========================================${NC}"
    exit $EXIT_CODE
fi
