"""Pytest configuration for generated tests."""
import sys
import pathlib

# Add target to Python path
TARGET_ROOT = pathlib.Path(__file__).parent.parent.parent / "target"
if str(TARGET_ROOT) not in sys.path:
    sys.path.insert(0, str(TARGET_ROOT))
