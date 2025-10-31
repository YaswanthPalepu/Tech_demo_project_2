# src/framework_handlers/universal_handler.py
"""
Universal framework handler for projects without specific frameworks.
"""

import pathlib
from typing import Any, Dict, List

from .base_handler import BaseFrameworkHandler


class UniversalHandler(BaseFrameworkHandler):
    """Universal framework handler for any Python project."""
    
    def __init__(self):
        super().__init__()
        self.framework_name = "universal"
        self.supported_patterns = {"functions", "classes", "methods", "modules"}
    
    def can_handle(self, analysis: Dict[str, Any]) -> bool:
        """Universal handler can handle any project as fallback."""
        return True
    
    def analyze_framework_specifics(self, tree, file_path: str) -> Dict[str, Any]:
        """Universal analysis - no framework-specific patterns."""
        return {}
    
    def get_framework_dependencies(self) -> List[str]:
        """Get universal dependencies for any Python project."""
        return [
            "pytest",
            "pytest-cov",
            "pytest-asyncio",
            "coverage"
        ]
    
    def detect_framework_patterns(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Detect universal patterns in the analysis."""
        universal_specific = {
            "framework": "universal",
            "function_count": len(analysis.get("functions", [])),
            "class_count": len(analysis.get("classes", [])),
            "method_count": len(analysis.get("methods", [])),
            "module_count": len(analysis.get("modules", [])),
            "has_async": len(analysis.get("async_functions", [])) > 0,
        }
        return universal_specific