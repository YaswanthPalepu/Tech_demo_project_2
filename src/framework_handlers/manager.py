# src/framework_handlers/manager.py
"""
Framework manager to detect and manage framework handlers.
"""

from typing import Any, Dict, List, Optional

from .base_handler import BaseFrameworkHandler
from .django_handler import DjangoHandler
from .fastapi_handler import FastAPIHandler
from .flask_handler import FlaskHandler
from .universal_handler import UniversalHandler


class FrameworkManager:
    """Manages framework detection and handler selection."""
    
    def __init__(self):
        self.handlers = [
            DjangoHandler(),
            FastAPIHandler(),
            FlaskHandler(),
            UniversalHandler()  # Always last as fallback
        ]
        self.detected_framework = None
        self.active_handler = None
    
    def detect_framework(self, analysis: Dict[str, Any]) -> str:
        """Detect the main framework used in the project."""
        framework_scores = {}
        
        for handler in self.handlers:
            if handler.can_handle(analysis):
                score = self._calculate_framework_score(handler, analysis)
                framework_scores[handler.framework_name] = score
        
        if framework_scores:
            self.detected_framework = max(framework_scores, key=framework_scores.get)
            
            # Set active handler
            for handler in self.handlers:
                if handler.framework_name == self.detected_framework:
                    self.active_handler = handler
                    break
        
        return self.detected_framework or "universal"
    
    def _calculate_framework_score(self, handler: BaseFrameworkHandler, analysis: Dict[str, Any]) -> int:
        """Calculate a score for how well a handler can handle the project."""
        score = 0
        
        if handler.framework_name == "django":
            django_patterns = analysis.get("django_patterns", {})
            score += len(django_patterns.get("models", [])) * 10
            score += len(django_patterns.get("views", [])) * 5
            score += len(django_patterns.get("forms", [])) * 3
        
        elif handler.framework_name == "fastapi":
            score += len(analysis.get("fastapi_routes", [])) * 10
            score += len(analysis.get("async_functions", [])) * 2
        
        elif handler.framework_name == "flask":
            routes = analysis.get("routes", [])
            flask_routes = [r for r in routes if r.get("framework") == "flask"]
            score += len(flask_routes) * 10
        
        # Universal handler gets base score
        elif handler.framework_name == "universal":
            score = 1
        
        return score
    
    def get_active_handler(self) -> Optional[BaseFrameworkHandler]:
        """Get the active framework handler."""
        return self.active_handler
    
    def get_framework_dependencies(self) -> List[str]:
        """Get dependencies for the detected framework."""
        if self.active_handler:
            return self.active_handler.get_framework_dependencies()
        return []
    
    def setup_framework_environment(self, target_root):
        """Setup environment for the detected framework."""
        if self.active_handler:
            self.active_handler.setup_framework_environment(target_root)
    
    def get_framework_analysis(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Get framework-specific analysis."""
        if self.active_handler:
            return self.active_handler.detect_framework_patterns(analysis)
        return {}
    
    def get_all_handlers(self) -> List[BaseFrameworkHandler]:
        """Get all available framework handlers."""
        return self.handlers