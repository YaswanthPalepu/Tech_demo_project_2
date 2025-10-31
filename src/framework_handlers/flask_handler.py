# src/framework_handlers/flask_handler.py
"""
Flask-specific framework handler for analysis and test generation.
"""

import ast
import pathlib
from typing import Any, Dict, List

from .base_handler import BaseFrameworkHandler


class FlaskHandler(BaseFrameworkHandler):
    """Flask framework handler."""
    
    def __init__(self):
        super().__init__()
        self.framework_name = "flask"
        self.supported_patterns = {"routes", "blueprints", "extensions"}
    
    def can_handle(self, analysis: Dict[str, Any]) -> bool:
        """Check if project uses Flask based on analysis."""
        # Check for Flask routes
        routes = analysis.get("routes", [])
        flask_routes = [route for route in routes if route.get("framework") == "flask"]
        if len(flask_routes) > 0:
            return True
        
        # Check imports for Flask
        imports = analysis.get("imports", [])
        flask_imports = any(
            any("flask" in str(module).lower() for module in imp.get("modules", []))
            for imp in imports
        )
        
        return flask_imports
    
    def analyze_framework_specifics(self, tree: ast.AST, file_path: str) -> Dict[str, Any]:
        """Analyze Flask-specific patterns in the AST."""
        flask_routes = []
        
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for decorator in node.decorator_list:
                    route_info = self._extract_flask_route_info(decorator)
                    if route_info and route_info.get("path"):
                        route_info.update({
                            "handler": node.name,
                            "file": file_path,
                            "framework": "flask"
                        })
                        flask_routes.append(route_info)
        
        return {"flask_routes": flask_routes}
    
    def _extract_flask_route_info(self, dec) -> Dict[str, Any]:
        """Extract route information from Flask decorators."""
        info = {}
        try:
            # Handle @app.route("/path") style (Flask)
            if isinstance(dec, ast.Call):
                if (isinstance(dec.func, ast.Attribute) and 
                    dec.func.attr in {"route", "as_view", "add_url_rule"}):
                    info["is_view"] = True
                    if dec.args:
                        arg0 = dec.args[0]
                        if isinstance(arg0, ast.Constant):
                            info["path"] = arg0.value
            
            # Handle @api.route() style
            if (isinstance(dec, ast.Call) and
                isinstance(dec.func, ast.Attribute) and
                'route' in dec.func.attr.lower()):
                info["is_view"] = True
                if dec.args:
                    arg0 = dec.args[0]
                    if isinstance(arg0, ast.Constant):
                        info["path"] = arg0.value
                        
        except Exception:
            pass
        return info
    
    def get_framework_dependencies(self) -> List[str]:
        """Get Flask-specific dependencies."""
        return [
            "flask",
            "flask-sqlalchemy",
            "flask-login",
            "flask-wtf",
            "flask-bcrypt",
            "flask-testing"
        ]
    
    def detect_framework_patterns(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Detect Flask-specific patterns in the analysis."""
        flask_routes = [route for route in analysis.get("routes", []) if route.get("framework") == "flask"]
        
        flask_specific = {
            "framework": "flask",
            "route_count": len(flask_routes),
            "has_blueprints": any("blueprint" in str(route.get("path", "")).lower() for route in flask_routes),
        }
        return flask_specific