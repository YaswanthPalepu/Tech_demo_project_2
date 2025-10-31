# src/framework_handlers/django_handler.py
"""
Django-specific framework handler for analysis and test generation.
"""

import ast
import os
import pathlib
from typing import Any, Dict, List, Optional

from .base_handler import BaseFrameworkHandler


class DjangoHandler(BaseFrameworkHandler):
    """Django framework handler."""
    
    def __init__(self):
        super().__init__()
        self.framework_name = "django"
        self.supported_patterns = {
            "models", "views", "viewsets", "serializers", 
            "forms", "admin", "urls", "middleware"
        }
    
    def can_handle(self, analysis: Dict[str, Any]) -> bool:
        """Check if project uses Django based on analysis."""
        django_patterns = analysis.get("django_patterns", {})
        
        # Check for Django-specific patterns
        has_django_models = len(django_patterns.get("models", [])) > 0
        has_django_views = len(django_patterns.get("views", [])) > 0
        has_django_forms = len(django_patterns.get("forms", [])) > 0
        
        # Check imports for Django modules
        imports = analysis.get("imports", [])
        django_imports = any(
            any("django" in str(module).lower() for module in imp.get("modules", []))
            for imp in imports
        )
        
        return has_django_models or has_django_views or has_django_forms or django_imports
    
    def analyze_framework_specifics(self, tree: ast.AST, file_path: str) -> Dict[str, Any]:
        """Analyze Django-specific patterns in the AST."""
        django_patterns = {
            "models": [],
            "serializers": [],
            "views": [],
            "viewsets": [],
            "forms": [],
            "admin": [],
            "urls": [],
            "middleware": [],
        }
        
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
                
            bases = []
            for b in node.bases:
                if isinstance(b, ast.Name):
                    bases.append(b.id)
                elif isinstance(b, ast.Attribute):
                    bases.append(getattr(b, 'attr', ''))
            
            base_str = ' '.join(bases).lower()
            
            # Django Models
            if (any("model" in b.lower() for b in bases) or 
                node.name.lower().endswith('model')):
                django_patterns["models"].append({
                    "name": node.name,
                    "file": file_path,
                    "lineno": getattr(node, "lineno", 1),
                    "type": "django_model",
                    "bases": bases
                })
            
            # DRF Serializers
            if (any("serializer" in b.lower() for b in bases) or
                node.name.lower().endswith('serializer')):
                django_patterns["serializers"].append({
                    "name": node.name,
                    "file": file_path,
                    "lineno": getattr(node, "lineno", 1),
                    "type": "serializer",
                    "bases": bases
                })
            
            # DRF ViewSets
            if (any("viewset" in b.lower() for b in bases) or
                node.name.lower().endswith('viewset')):
                django_patterns["viewsets"].append({
                    "name": node.name,
                    "file": file_path,
                    "lineno": getattr(node, "lineno", 1),
                    "type": "viewset",
                    "bases": bases
                })
            
            # Django/DRF Views
            if (any("view" in b.lower() or "apiview" in b.lower() for b in bases) or
                node.name.lower().endswith('view')):
                django_patterns["views"].append({
                    "name": node.name,
                    "file": file_path,
                    "lineno": getattr(node, "lineno", 1),
                    "type": "view",
                    "bases": bases
                })
            
            # Django Forms
            if (any("form" in b.lower() for b in bases) or
                node.name.lower().endswith('form')):
                django_patterns["forms"].append({
                    "name": node.name,
                    "file": file_path,
                    "lineno": getattr(node, "lineno", 1),
                    "type": "form",
                    "bases": bases
                })
            
            # Django Admin
            if (any("admin" in b.lower() for b in bases) or
                node.name.lower().endswith('admin')):
                django_patterns["admin"].append({
                    "name": node.name,
                    "file": file_path,
                    "lineno": getattr(node, "lineno", 1),
                    "type": "admin",
                    "bases": bases
                })
        
        return django_patterns
    
    def get_framework_dependencies(self) -> List[str]:
        """Get Django-specific dependencies."""
        return [
            "django",
            "djangorestframework",
            "pytest-django",
            "pytest-asyncio"
        ]
    
    def setup_framework_environment(self, target_root: pathlib.Path):
        """Setup Django testing environment."""
        # Set Django settings module if not set
        if not os.environ.get('DJANGO_SETTINGS_MODULE'):
            # Try to find settings.py
            settings_files = list(target_root.rglob("settings.py"))
            if settings_files:
                settings_file = settings_files[0]
                # Convert to module path
                rel_path = settings_file.relative_to(target_root)
                module_path = str(rel_path).replace('/', '.').replace('.py', '')
                os.environ['DJANGO_SETTINGS_MODULE'] = module_path
    
    def detect_framework_patterns(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Detect Django-specific patterns in the analysis."""
        django_specific = {
            "framework": "django",
            "has_models": len(analysis.get("django_patterns", {}).get("models", [])) > 0,
            "has_views": len(analysis.get("django_patterns", {}).get("views", [])) > 0,
            "has_serializers": len(analysis.get("django_patterns", {}).get("serializers", [])) > 0,
            "has_forms": len(analysis.get("django_patterns", {}).get("forms", [])) > 0,
            "model_count": len(analysis.get("django_patterns", {}).get("models", [])),
            "view_count": len(analysis.get("django_patterns", {}).get("views", [])),
        }
        return django_specific