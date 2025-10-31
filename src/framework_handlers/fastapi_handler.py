# src/framework_handlers/fastapi_handler.py
"""
FastAPI-specific framework handler for analysis and test generation.
"""

import ast
import pathlib
from typing import Any, Dict, List

from .base_handler import BaseFrameworkHandler


class FastAPIHandler(BaseFrameworkHandler):
    """FastAPI framework handler."""
    
    def __init__(self):
        super().__init__()
        self.framework_name = "fastapi"
        self.supported_patterns = {"routes", "dependencies", "middleware"}
    
    def can_handle(self, analysis: Dict[str, Any]) -> bool:
        """Check if project uses FastAPI based on analysis."""
        # Check for FastAPI routes
        fastapi_routes = analysis.get("fastapi_routes", [])
        if len(fastapi_routes) > 0:
            return True
        
        # Check imports for FastAPI
        imports = analysis.get("imports", [])
        fastapi_imports = any(
            any("fastapi" in str(module).lower() for module in imp.get("modules", []))
            for imp in imports
        )
        
        return fastapi_imports
    
    def analyze_framework_specifics(self, tree: ast.AST, file_path: str) -> Dict[str, Any]:
        """Analyze FastAPI-specific patterns in the AST."""
        fastapi_routes = []
        
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for decorator in node.decorator_list:
                    route_info = self._extract_fastapi_route_info(decorator)
                    if route_info and route_info.get("path"):
                        route_info.update({
                            "handler": node.name,
                            "file": file_path,
                            "lineno": getattr(node, "lineno", 1),
                            "end_lineno": getattr(node, "end_lineno", getattr(node, "lineno", 1)),
                        })
                        fastapi_routes.append(route_info)
        
        return {"fastapi_routes": fastapi_routes}
    
    def _extract_fastapi_route_info(self, dec) -> Dict[str, Any]:
        """Extract route information from FastAPI decorators."""
        info = {}
        try:
            # Handle @router.get("/path") style (FastAPI, Starlette)
            if hasattr(dec, 'func'):
                func = dec.func
                if hasattr(func, 'attr'):
                    if func.attr in {"get", "post", "put", "patch", "delete", "options", "head"}:
                        info["method"] = func.attr
                        
                    # Extract path from first argument
                    if hasattr(dec, "args") and dec.args:
                        arg0 = dec.args[0]
                        if isinstance(arg0, ast.Constant) and isinstance(arg0.value, str):
                            info["path"] = arg0.value
            
        except Exception:
            pass
        return info
    
    def get_framework_dependencies(self) -> List[str]:
        """Get FastAPI-specific dependencies."""
        return [
            "fastapi",
            "uvicorn",
            "pytest-asyncio",
            "httpx",
            "pytest-httpx"
        ]
    
    def detect_framework_patterns(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Detect FastAPI-specific patterns in the analysis."""
        fastapi_specific = {
            "framework": "fastapi",
            "route_count": len(analysis.get("fastapi_routes", [])),
            "async_functions": len(analysis.get("async_functions", [])),
            "has_async": len(analysis.get("async_functions", [])) > 0,
        }
        return fastapi_specific