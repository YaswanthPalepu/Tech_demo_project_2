# src/framework_handlers/django_handler.py
"""
Enhanced Django-specific framework handler for maximum test coverage with real code execution.
"""

import ast
import os
import pathlib
import re
from typing import Any, Dict, List, Optional, Tuple

from .base_handler import BaseFrameworkHandler


class DjangoHandler(BaseFrameworkHandler):
    """Enhanced Django framework handler for 95%+ test coverage with real imports."""
    
    def __init__(self):
        super().__init__()
        self.framework_name = "django"
        self.supported_patterns = {
            "models", "views", "viewsets", "serializers", 
            "forms", "admin", "urls", "middleware", "signals",
            "managers", "querysets", "context_processors", "templatetags"
        }
    
    def can_handle(self, analysis: Dict[str, Any]) -> bool:
        """Enhanced Django detection with comprehensive pattern matching."""
        django_patterns = analysis.get("django_patterns", {})
        
        # Check for Django-specific patterns
        has_django_models = len(django_patterns.get("models", [])) > 0
        has_django_views = len(django_patterns.get("views", [])) > 0
        has_django_forms = len(django_patterns.get("forms", [])) > 0
        has_django_admin = len(django_patterns.get("admin", [])) > 0
        
        # Enhanced import analysis for Django
        imports = analysis.get("imports", [])
        django_imports = False
        django_modules = {'django', 'django.db', 'django.contrib', 'django.conf'}
        
        for imp in imports:
            modules = imp.get("modules", [])
            if any(any(django_mod in str(module).lower() for django_mod in django_modules) 
                   for module in modules):
                django_imports = True
                break
        
        # Check for settings.py and urls.py patterns
        project_structure = analysis.get("project_structure", {})
        module_paths = project_structure.get("module_paths", {})
        django_config_files = any(
            any(pattern in path.lower() for pattern in ['settings.py', 'urls.py', 'wsgi.py', 'asgi.py'])
            for path in module_paths.keys()
        )
        
        return (has_django_models or has_django_views or has_django_forms or 
                has_django_admin or django_imports or django_config_files)
    
    def analyze_framework_specifics(self, tree: ast.AST, file_path: str) -> Dict[str, Any]:
        """Enhanced Django-specific analysis for maximum coverage targeting."""
        django_patterns = {
            "models": [],
            "serializers": [],
            "views": [],
            "viewsets": [],
            "forms": [],
            "admin": [],
            "urls": [],
            "middleware": [],
            "signals": [],
            "managers": [],
            "querysets": [],
            "context_processors": [],
            "templatetags": [],
            "model_fields": {},
            "view_methods": {},
            "url_patterns": [],
        }
        
        # Enhanced field detection for models
        current_model = None
        
        for node in ast.walk(tree):
            # Class-based analysis
            if isinstance(node, ast.ClassDef):
                bases = self._get_class_bases(node)
                base_str = ' '.join(bases).lower()
                
                # Enhanced Django Model detection with field analysis
                if (any("model" in b.lower() for b in bases) or 
                    node.name.lower().endswith('model')):
                    
                    model_info = {
                        "name": node.name,
                        "file": file_path,
                        "lineno": getattr(node, "lineno", 1),
                        "type": "django_model",
                        "bases": bases,
                        "fields": self._extract_model_fields(node),
                        "methods": self._extract_class_methods(node),
                        "meta_class": self._extract_meta_class(node)
                    }
                    django_patterns["models"].append(model_info)
                    current_model = node.name
                
                # Enhanced DRF Serializers
                elif (any("serializer" in b.lower() for b in bases) or
                    node.name.lower().endswith('serializer')):
                    django_patterns["serializers"].append({
                        "name": node.name,
                        "file": file_path,
                        "lineno": getattr(node, "lineno", 1),
                        "type": "serializer",
                        "bases": bases,
                        "fields": self._extract_serializer_fields(node),
                        "methods": self._extract_class_methods(node)
                    })
                
                # Enhanced DRF ViewSets
                elif (any("viewset" in b.lower() for b in bases) or
                    node.name.lower().endswith('viewset')):
                    django_patterns["viewsets"].append({
                        "name": node.name,
                        "file": file_path,
                        "lineno": getattr(node, "lineno", 1),
                        "type": "viewset",
                        "bases": bases,
                        "methods": self._extract_class_methods(node),
                        "http_methods": self._extract_http_methods(node)
                    })
                
                # Enhanced Django/DRF Views
                elif (any("view" in b.lower() or "apiview" in b.lower() for b in bases) or
                    node.name.lower().endswith('view')):
                    django_patterns["views"].append({
                        "name": node.name,
                        "file": file_path,
                        "lineno": getattr(node, "lineno", 1),
                        "type": "view",
                        "bases": bases,
                        "methods": self._extract_class_methods(node),
                        "http_methods": self._extract_http_methods(node)
                    })
                
                # Enhanced Django Forms
                elif (any("form" in b.lower() for b in bases) or
                    node.name.lower().endswith('form')):
                    django_patterns["forms"].append({
                        "name": node.name,
                        "file": file_path,
                        "lineno": getattr(node, "lineno", 1),
                        "type": "form",
                        "bases": bases,
                        "fields": self._extract_form_fields(node),
                        "methods": self._extract_class_methods(node)
                    })
                
                # Enhanced Django Admin
                elif (any("admin" in b.lower() for b in bases) or
                    node.name.lower().endswith('admin')):
                    django_patterns["admin"].append({
                        "name": node.name,
                        "file": file_path,
                        "lineno": getattr(node, "lineno", 1),
                        "type": "admin",
                        "bases": bases,
                        "methods": self._extract_class_methods(node),
                        "model_reference": self._extract_admin_model(node)
                    })
                
                # Django Managers
                elif (any("manager" in b.lower() for b in bases) or
                    node.name.lower().endswith('manager')):
                    django_patterns["managers"].append({
                        "name": node.name,
                        "file": file_path,
                        "lineno": getattr(node, "lineno", 1),
                        "type": "manager",
                        "bases": bases,
                        "methods": self._extract_class_methods(node)
                    })
            
            # Function-based analysis for views and signals
            elif isinstance(node, ast.FunctionDef):
                # Detect function-based views
                if self._is_function_based_view(node):
                    django_patterns["views"].append({
                        "name": node.name,
                        "file": file_path,
                        "lineno": getattr(node, "lineno", 1),
                        "type": "function_view",
                        "decorators": self._get_decorators(node),
                        "parameters": self._extract_function_parameters(node)
                    })
                
                # Detect signal handlers
                if self._is_signal_handler(node):
                    django_patterns["signals"].append({
                        "name": node.name,
                        "file": file_path,
                        "lineno": getattr(node, "lineno", 1),
                        "type": "signal_handler",
                        "decorators": self._get_decorators(node)
                    })
                
                # Detect context processors
                if self._is_context_processor(node):
                    django_patterns["context_processors"].append({
                        "name": node.name,
                        "file": file_path,
                        "lineno": getattr(node, "lineno", 1),
                        "type": "context_processor",
                        "decorators": self._get_decorators(node)
                    })
            
            # URL patterns detection
            elif isinstance(node, ast.Assign):
                url_patterns = self._extract_url_patterns(node, file_path)
                if url_patterns:
                    django_patterns["url_patterns"].extend(url_patterns)
        
        return django_patterns
    
    def _get_class_bases(self, node: ast.ClassDef) -> List[str]:
        """Extract class base names."""
        bases = []
        for b in node.bases:
            if isinstance(b, ast.Name):
                bases.append(b.id)
            elif isinstance(b, ast.Attribute):
                bases.append(getattr(b, 'attr', ''))
            elif isinstance(b, ast.Call):
                # Handle cases like class MyModel(models.Model)
                if isinstance(b.func, ast.Name):
                    bases.append(b.func.id)
                elif isinstance(b.func, ast.Attribute):
                    bases.append(b.func.attr)
        return bases
    
    def _extract_model_fields(self, node: ast.ClassDef) -> Dict[str, Any]:
        """Extract model field definitions for comprehensive testing."""
        fields = {}
        for item in node.body:
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        field_name = target.id
                        if isinstance(item.value, ast.Call):
                            # Field instantiation like name = models.CharField(...)
                            if (isinstance(item.value.func, ast.Attribute) and
                                hasattr(item.value.func, 'attr')):
                                field_type = item.value.func.attr
                                fields[field_name] = {
                                    "type": field_type,
                                    "args": self._extract_call_args(item.value),
                                    "lineno": getattr(item, "lineno", 1)
                                }
        return fields
    
    def _extract_serializer_fields(self, node: ast.ClassDef) -> Dict[str, Any]:
        """Extract serializer field definitions."""
        fields = {}
        for item in node.body:
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name):
                        field_name = target.id
                        if (field_name != 'Meta' and 
                            isinstance(item.value, (ast.Call, ast.Attribute))):
                            fields[field_name] = {
                                "lineno": getattr(item, "lineno", 1)
                            }
        return fields
    
    def _extract_form_fields(self, node: ast.ClassDef) -> Dict[str, Any]:
        """Extract form field definitions."""
        return self._extract_serializer_fields(node)  # Similar structure
    
    def _extract_class_methods(self, node: ast.ClassDef) -> List[str]:
        """Extract method names from a class."""
        methods = []
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                methods.append(item.name)
        return methods
    
    def _extract_http_methods(self, node: ast.ClassDef) -> List[str]:
        """Extract HTTP methods from view classes."""
        methods = []
        http_methods = {'get', 'post', 'put', 'patch', 'delete', 'head', 'options'}
        
        for item in node.body:
            if isinstance(item, ast.FunctionDef) and item.name.lower() in http_methods:
                methods.append(item.name.upper())
        
        return methods
    
    def _extract_meta_class(self, node: ast.ClassDef) -> Dict[str, Any]:
        """Extract Meta class information from models."""
        meta_info = {}
        for item in node.body:
            if (isinstance(item, ast.ClassDef) and item.name == 'Meta'):
                for meta_item in item.body:
                    if isinstance(meta_item, ast.Assign):
                        for target in meta_item.targets:
                            if isinstance(target, ast.Name):
                                meta_info[target.id] = self._extract_value(meta_item.value)
        return meta_info
    
    def _extract_admin_model(self, node: ast.ClassDef) -> Optional[str]:
        """Extract model reference from admin classes."""
        for item in node.body:
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if (isinstance(target, ast.Name) and 
                        target.id in ['model', 'models']):
                        return self._extract_value(item.value)
        return None
    
    def _extract_call_args(self, node: ast.Call) -> List[Any]:
        """Extract arguments from function calls."""
        args = []
        for arg in node.args:
            args.append(self._extract_value(arg))
        for keyword in node.keywords:
            args.append(f"{keyword.arg}={self._extract_value(keyword.value)}")
        return args
    
    def _extract_value(self, node: ast.AST) -> Any:
        """Extract value from AST node."""
        if isinstance(node, ast.Str):
            return node.s
        elif isinstance(node, ast.Num):
            return node.n
        elif isinstance(node, ast.NameConstant):
            return node.value
        elif isinstance(node, ast.Name):
            return node.id
        elif isinstance(node, ast.Attribute):
            return f"{self._extract_value(node.value)}.{node.attr}"
        elif isinstance(node, ast.List):
            return [self._extract_value(item) for item in node.elts]
        elif isinstance(node, ast.Dict):
            return {self._extract_value(k): self._extract_value(v) 
                   for k, v in zip(node.keys, node.values)}
        return None
    
    def _extract_function_parameters(self, node: ast.FunctionDef) -> List[str]:
        """Extract function parameter names."""
        params = []
        for arg in node.args.args:
            params.append(arg.arg)
        return params
    
    def _get_decorators(self, node: ast.FunctionDef) -> List[str]:
        """Extract function decorators."""
        decorators = []
        for decorator in node.decorator_list:
            if isinstance(decorator, ast.Name):
                decorators.append(decorator.id)
            elif isinstance(decorator, ast.Attribute):
                decorators.append(decorator.attr)
            elif isinstance(decorator, ast.Call):
                if isinstance(decorator.func, ast.Name):
                    decorators.append(decorator.func.id)
        return decorators
    
    def _is_function_based_view(self, node: ast.FunctionDef) -> bool:
        """Check if function is a Django view."""
        # Check for request parameter
        has_request_param = any(arg.arg == 'request' for arg in node.args.args)
        
        # Check for view decorators
        decorators = self._get_decorators(node)
        view_indicators = {'api_view', 'login_required', 'permission_required'}
        
        return has_request_param or any(indicator in decorators for indicator in view_indicators)
    
    def _is_signal_handler(self, node: ast.FunctionDef) -> bool:
        """Check if function is a signal handler."""
        decorators = self._get_decorators(node)
        signal_indicators = {'receiver', 'pre_save', 'post_save'}
        return any(indicator in decorators for indicator in signal_indicators)
    
    def _is_context_processor(self, node: ast.FunctionDef) -> bool:
        """Check if function is a context processor."""
        decorators = self._get_decorators(node)
        context_indicators = {'context_processor'}
        return any(indicator in decorators for indicator in context_indicators)
    
    def _extract_url_patterns(self, node: ast.Assign, file_path: str) -> List[Dict[str, Any]]:
        """Extract URL patterns from urlpatterns assignments."""
        patterns = []
        
        # Check if this is a urlpatterns assignment
        if (isinstance(node, ast.Assign) and
            any(isinstance(target, ast.Name) and target.id == 'urlpatterns' 
                for target in node.targets)):
            
            if isinstance(node.value, ast.List):
                for pattern_node in node.value.elts:
                    pattern_info = self._parse_url_pattern(pattern_node, file_path)
                    if pattern_info:
                        patterns.append(pattern_info)
        
        return patterns
    
    def _parse_url_pattern(self, node: ast.AST, file_path: str) -> Optional[Dict[str, Any]]:
        """Parse individual URL pattern."""
        try:
            if isinstance(node, ast.Call) and hasattr(node.func, 'id'):
                if node.func.id == 'path':
                    return self._parse_path_pattern(node, file_path)
                elif node.func.id == 're_path':
                    return self._parse_re_path_pattern(node, file_path)
        except:
            pass
        return None
    
    def _parse_path_pattern(self, node: ast.Call, file_path: str) -> Dict[str, Any]:
        """Parse path() URL pattern."""
        pattern_info = {"type": "path", "file": file_path}
        
        if len(node.args) >= 2:
            pattern_info["route"] = self._extract_value(node.args[0])
            pattern_info["view"] = self._extract_value(node.args[1])
            
            if len(node.args) > 2:
                pattern_info["name"] = self._extract_value(node.args[2])
        
        return pattern_info
    
    def _parse_re_path_pattern(self, node: ast.Call, file_path: str) -> Dict[str, Any]:
        """Parse re_path() URL pattern."""
        pattern_info = {"type": "re_path", "file": file_path}
        
        if len(node.args) >= 2:
            pattern_info["regex"] = self._extract_value(node.args[0])
            pattern_info["view"] = self._extract_value(node.args[1])
        
        return pattern_info
    
    def get_framework_dependencies(self) -> List[str]:
        """Get enhanced Django-specific dependencies for maximum coverage."""
        return [
            "django",
            "djangorestframework",
            "pytest-django",
            "pytest-asyncio",
            "pytest-cov",
            "factory-boy",
            "mixer",
            "model-bakery"
        ]
    
    def setup_framework_environment(self, target_root: pathlib.Path):
        """Enhanced Django environment setup for real code execution."""
        # Set Django settings module if not set
        if not os.environ.get('DJANGO_SETTINGS_MODULE'):
            # Enhanced settings detection
            settings_files = list(target_root.rglob("settings.py"))
            settings_files.extend(list(target_root.rglob("*settings.py")))
            settings_files.extend(list(target_root.rglob("*/settings.py")))
            
            if settings_files:
                settings_file = settings_files[0]
                # Convert to module path
                rel_path = settings_file.relative_to(target_root)
                module_path = str(rel_path).replace('/', '.').replace('.py', '')
                os.environ['DJANGO_SETTINGS_MODULE'] = module_path
                print(f"Django settings module set to: {module_path}")
            else:
                # Create minimal test settings
                self._create_minimal_django_settings(target_root)
        
        # Initialize Django for test generation
        try:
            import django
            if not django.conf.settings.configured:
                django.setup()
                print("Django setup completed successfully")
        except Exception as e:
            print(f"Django setup warning: {e}")
    
    def _create_minimal_django_settings(self, target_root: pathlib.Path):
        """Create minimal Django settings for testing when none found."""
        settings_content = '''
# Minimal Django settings for test generation
DEBUG = True
TESTING = True
SECRET_KEY = 'test-secret-key-for-coverage-generation'
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}
INSTALLED_APPS = [
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
]
MIDDLEWARE = []
ROOT_URLCONF = None
'''
        
        settings_file = target_root / "test_settings.py"
        settings_file.write_text(settings_content)
        os.environ['DJANGO_SETTINGS_MODULE'] = 'test_settings'
        print("Created minimal Django settings for testing")
    
    def detect_framework_patterns(self, analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Enhanced Django pattern detection for comprehensive test generation."""
        django_specific = {
            "framework": "django",
            "has_models": len(analysis.get("django_patterns", {}).get("models", [])) > 0,
            "has_views": len(analysis.get("django_patterns", {}).get("views", [])) > 0,
            "has_serializers": len(analysis.get("django_patterns", {}).get("serializers", [])) > 0,
            "has_forms": len(analysis.get("django_patterns", {}).get("forms", [])) > 0,
            "has_admin": len(analysis.get("django_patterns", {}).get("admin", [])) > 0,
            "has_signals": len(analysis.get("django_patterns", {}).get("signals", [])) > 0,
            "has_urls": len(analysis.get("django_patterns", {}).get("url_patterns", [])) > 0,
            "model_count": len(analysis.get("django_patterns", {}).get("models", [])),
            "view_count": len(analysis.get("django_patterns", {}).get("views", [])),
            "serializer_count": len(analysis.get("django_patterns", {}).get("serializers", [])),
            "form_count": len(analysis.get("django_patterns", {}).get("forms", [])),
            "coverage_target": "95%+",
            "test_strategy": "real_imports_only",
            "recommended_tests": self._generate_test_recommendations(analysis)
        }
        
        # Add detailed model information
        models = analysis.get("django_patterns", {}).get("models", [])
        if models:
            django_specific["model_details"] = [
                {
                    "name": model["name"],
                    "field_count": len(model.get("fields", {})),
                    "method_count": len(model.get("methods", [])),
                    "test_cases": self._generate_model_test_cases(model)
                }
                for model in models[:10]  # Limit to first 10 models for brevity
            ]
        
        return django_specific
    
    def _generate_test_recommendations(self, analysis: Dict[str, Any]) -> List[str]:
        """Generate specific test recommendations for maximum Django coverage."""
        recommendations = []
        django_patterns = analysis.get("django_patterns", {})
        
        if django_patterns.get("models"):
            recommendations.extend([
                "Model creation and validation tests",
                "Model method unit tests",
                "Model property tests",
                "Model manager tests",
                "Model signal tests",
                "Model relationship tests",
                "Model queryset tests"
            ])
        
        if django_patterns.get("views") or django_patterns.get("viewsets"):
            recommendations.extend([
                "View HTTP method tests",
                "View authentication tests",
                "View permission tests",
                "View response format tests",
                "View error handling tests",
                "View template tests",
                "View context tests"
            ])
        
        if django_patterns.get("serializers"):
            recommendations.extend([
                "Serializer validation tests",
                "Serializer field tests",
                "Serializer create/update tests",
                "Serializer relationship tests"
            ])
        
        if django_patterns.get("forms"):
            recommendations.extend([
                "Form validation tests",
                "Form field tests",
                "Form save method tests",
                "Form clean method tests"
            ])
        
        if django_patterns.get("admin"):
            recommendations.extend([
                "Admin registration tests",
                "Admin list display tests",
                "Admin action tests",
                "Admin permission tests"
            ])
        
        return recommendations
    
    def _generate_model_test_cases(self, model: Dict[str, Any]) -> List[str]:
        """Generate specific test cases for a Django model."""
        test_cases = [
            f"test_{model['name'].lower()}_creation",
            f"test_{model['name'].lower()}_string_representation",
            f"test_{model['name'].lower()}_field_validation",
            f"test_{model['name'].lower()}_required_fields",
        ]
        
        # Add field-specific test cases
        fields = model.get("fields", {})
        for field_name in fields.keys():
            test_cases.extend([
                f"test_{model['name'].lower()}_{field_name}_max_length",
                f"test_{model['name'].lower()}_{field_name}_blank_null",
            ])
        
        # Add method-specific test cases
        methods = model.get("methods", [])
        for method in methods:
            if not method.startswith('_'):
                test_cases.append(f"test_{model['name'].lower()}_{method}")
        
        return test_cases
    
    def generate_framework_specific_tests(self, analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Generate Django-specific test templates for maximum coverage."""
        django_tests = []
        django_patterns = analysis.get("django_patterns", {})
        
        # Model tests
        for model in django_patterns.get("models", []):
            django_tests.append({
                "type": "model_test",
                "target": model["name"],
                "template": self._generate_model_test_template(model),
                "coverage_goal": "95%+",
                "test_count": len(self._generate_model_test_cases(model))
            })
        
        # View tests
        for view in django_patterns.get("views", []) + django_patterns.get("viewsets", []):
            django_tests.append({
                "type": "view_test",
                "target": view["name"],
                "template": self._generate_view_test_template(view),
                "coverage_goal": "95%+",
                "test_count": len(view.get("http_methods", ["GET"])) * 3  # Basic CRUD tests
            })
        
        return django_tests
    
    def _generate_model_test_template(self, model: Dict[str, Any]) -> str:
        """Generate comprehensive model test template."""
        return f'''
"""
Comprehensive tests for {model['name']} model.
Target: 95%+ coverage with real database operations.
"""

import pytest
from django.test import TestCase
from django.core.exceptions import ValidationError

class Test{model['name']}(TestCase):
    """Test suite for {model['name']} model."""
    
    def test_{model['name'].lower()}_creation(self):
        """Test basic model creation with valid data."""
        # TODO: Implement with real model data
        pass
    
    def test_{model['name'].lower()}_string_representation(self):
        """Test __str__ method returns expected string."""
        # TODO: Implement string representation test
        pass
    
    def test_{model['name'].lower()}_field_validation(self):
        """Test field validation rules."""
        # TODO: Implement field validation tests
        pass
    
    def test_{model['name'].lower()}_required_fields(self):
        """Test that required fields are enforced."""
        # TODO: Implement required field tests
        pass
'''
    
    def _generate_view_test_template(self, view: Dict[str, Any]) -> str:
        """Generate comprehensive view test template."""
        return f'''
"""
Comprehensive tests for {view['name']} view.
Target: 95%+ coverage with real HTTP requests.
"""

import pytest
from django.test import TestCase, Client
from django.urls import reverse

class Test{view['name']}(TestCase):
    """Test suite for {view['name']} view."""
    
    def setUp(self):
        """Set up test client and test data."""
        self.client = Client()
        # TODO: Set up test data
    
    def test_{view['name'].lower()}_get_request(self):
        """Test GET request to view."""
        # TODO: Implement GET request test
        pass
    
    def test_{view['name'].lower()}_post_request(self):
        """Test POST request to view."""
        # TODO: Implement POST request test
        pass
    
    def test_{view['name'].lower()}_authentication(self):
        """Test view authentication requirements."""
        # TODO: Implement authentication tests
        pass
'''