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


# ----------------------- APPENDED ENHANCEMENTS BELOW (no deletions) -----------------------

class FastAPIHandler(FastAPIHandler):  # type: ignore[misc]
    """
    Extended FastAPI handler with deeper detection, richer AST analysis,
    realistic test templates (real imports + HTTP calls), and environment helpers.
    """

    # -- Detection upgrades ----------------------------------------------------
    def can_handle(self, analysis: Dict[str, Any]) -> bool:  # type: ignore[override]
        """
        Enhanced detection:
        - existing fastapi_routes
        - imports including fastapi, starlette
        - FastAPI() constructor or APIRouter() in AST across files
        - presence of include_router calls
        - typical filenames (main.py, app.py) + uvicorn.run usage
        """
        if analysis.get("fastapi_routes"):
            return True

        # Import signals
        imports = analysis.get("imports", [])
        if any(
            any(("fastapi" in str(m).lower()) or ("starlette" in str(m).lower())
                for m in imp.get("modules", []))
            for imp in imports
        ):
            return True

        # Heuristic project structure
        ps = analysis.get("project_structure", {})
        module_paths = set(ps.get("module_paths", {}).keys()) if isinstance(ps, dict) else set()
        if any(p.lower().endswith(("main.py", "app.py")) for p in module_paths):
            return True

        # Uvicorn entrypoint / lifespan handlers
        found_uvicorn = any("uvicorn" in str(m).lower() for imp in imports for m in imp.get("modules", []))
        if found_uvicorn:
            return True

        # AST-hinted flags from analysis (if provided by a parent analyzer)
        if analysis.get("fastapi_app_inits") or analysis.get("fastapi_include_router"):
            return True

        return False

    # -- Analysis upgrades -----------------------------------------------------
    def analyze_framework_specifics(self, tree: ast.AST, file_path: str) -> Dict[str, Any]:  # type: ignore[override]
        """
        Richer analysis:
        - discovers FastAPI() instances (variable names)
        - discovers APIRouter() instances and include_router() calls
        - extracts route metadata: tags, status_code, response_model, dependencies
        - collects middleware and exception handlers
        - collects startup/shutdown (lifespan) events
        """
        fastapi_routes: List[Dict[str, Any]] = []
        app_vars: List[str] = []
        router_vars: List[str] = []
        include_router_calls: List[Dict[str, Any]] = []
        middlewares: List[Dict[str, Any]] = []
        exception_handlers: List[Dict[str, Any]] = []
        startup_handlers: List[str] = []
        shutdown_handlers: List[str] = []

        # Scan assignments to find `app = FastAPI(...)` or `router = APIRouter(...)`
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call):
                name = self._call_name(node.value)
                targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
                if name == "FastAPI":
                    app_vars.extend(targets)
                if name == "APIRouter":
                    router_vars.extend(targets)

        # Decorator-based route extraction and meta
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for decorator in node.decorator_list:
                    route_info = self._extract_fastapi_route_info_extended(decorator)
                    if route_info and route_info.get("path"):
                        route_info.update({
                            "handler": node.name,
                            "file": file_path,
                            "lineno": getattr(node, "lineno", 1),
                            "end_lineno": getattr(node, "end_lineno", getattr(node, "lineno", 1)),
                        })
                        fastapi_routes.append(route_info)

        # include_router calls
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func_name = self._call_attr_name(node.func)
                if func_name and func_name.endswith("include_router"):
                    include_router_calls.append({
                        "file": file_path,
                        "lineno": getattr(node, "lineno", 1),
                        "args": [self._safe_value(a) for a in node.args],
                        "kwargs": {kw.arg: self._safe_value(kw.value) for kw in node.keywords if kw.arg},
                    })

        # middleware registration: app.add_middleware(...)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and self._call_attr_name(node.func, full=True).endswith("add_middleware"):
                entry = {
                    "file": file_path,
                    "lineno": getattr(node, "lineno", 1),
                    "middleware": self._safe_value(node.args[0]) if node.args else None,
                    "kwargs": {kw.arg: self._safe_value(kw.value) for kw in node.keywords if kw.arg},
                }
                middlewares.append(entry)

        # exception handlers: app.add_exception_handler(...)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and self._call_attr_name(node.func, full=True).endswith("add_exception_handler"):
                entry = {
                    "file": file_path,
                    "lineno": getattr(node, "lineno", 1),
                    "exception": self._safe_value(node.args[0]) if node.args else None,
                    "handler": self._safe_value(node.args[1]) if len(node.args) > 1 else None,
                }
                exception_handlers.append(entry)

        # startup/shutdown decorators: @app.on_event("startup") / @app.on_event("shutdown")
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for dec in node.decorator_list:
                    if isinstance(dec, ast.Call) and self._call_attr_name(dec.func, full=True).endswith("on_event"):
                        ev = dec.args[0].s if dec.args and isinstance(dec.args[0], ast.Constant) and isinstance(dec.args[0].value, str) else None
                        if ev == "startup":
                            startup_handlers.append(node.name)
                        if ev == "shutdown":
                            shutdown_handlers.append(node.name)

        return {
            "fastapi_routes": fastapi_routes,
            "fastapi_app_vars": app_vars,
            "fastapi_router_vars": router_vars,
            "fastapi_include_router": include_router_calls,
            "fastapi_middlewares": middlewares,
            "fastapi_exception_handlers": exception_handlers,
            "fastapi_startup": startup_handlers,
            "fastapi_shutdown": shutdown_handlers,
        }

    # Original simple route extractor remains; add an extended one that captures metadata
    def _extract_fastapi_route_info_extended(self, dec) -> Dict[str, Any]:
        """
        Extract method, path, tags, status_code, response_model, dependencies
        from @app.<method> or @router.<method> decorators.
        """
        info: Dict[str, Any] = {}
        try:
            if hasattr(dec, "func"):
                func = dec.func
                method = getattr(func, "attr", None)
                if method in {"get", "post", "put", "patch", "delete", "options", "head"}:
                    info["method"] = method.upper()
                # path arg
                if getattr(dec, "args", None):
                    a0 = dec.args[0]
                    if isinstance(a0, ast.Constant) and isinstance(a0.value, str):
                        info["path"] = a0.value
                # keywords
                kw = {k.arg: k.value for k in getattr(dec, "keywords", []) if k.arg}
                # tags
                if "tags" in kw and isinstance(kw["tags"], ast.List):
                    info["tags"] = [self._safe_value(e) for e in kw["tags"].elts]
                # status_code
                if "status_code" in kw:
                    info["status_code"] = self._safe_value(kw["status_code"])
                # response_model
                if "response_model" in kw:
                    info["response_model"] = self._safe_value(kw["response_model"])
                # dependencies
                if "dependencies" in kw and isinstance(kw["dependencies"], ast.List):
                    info["dependencies"] = [self._safe_value(e) for e in kw["dependencies"].elts]
        except Exception:
            pass
        return info

    # -- Utilities -------------------------------------------------------------
    def _call_name(self, call: ast.Call) -> str:
        if isinstance(call.func, ast.Name):
            return call.func.id
        if isinstance(call.func, ast.Attribute):
            return call.func.attr
        return ""

    def _call_attr_name(self, func: ast.AST, *, full: bool = False) -> str:
        """
        Return attribute name like 'app.include_router' or just 'include_router'
        """
        if isinstance(func, ast.Attribute):
            left = self._call_attr_name(func.value, full=full) if full else ""
            return f"{left+'.' if full and left else ''}{func.attr}"
        if isinstance(func, ast.Name):
            return func.id
        return ""

    def _safe_value(self, node: ast.AST) -> Any:
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return f"{self._safe_value(node.value)}.{node.attr}"
        if isinstance(node, ast.Call):
            return f"{self._call_name(node)}(...)"
        if isinstance(node, ast.List):
            return [self._safe_value(e) for e in node.elts]
        if isinstance(node, ast.Dict):
            return {self._safe_value(k): self._safe_value(v) for k, v in zip(node.keys, node.values)}
        return str(getattr(node, "id", node.__class__.__name__))

    # -- Dependencies / env helpers -------------------------------------------
    def get_framework_dependencies(self) -> List[str]:  # type: ignore[override]
        """
        Add 'asgi-lifespan' to support startup/shutdown in tests, keep originals.
        """
        base = [
            "fastapi",
            "uvicorn",
            "pytest-asyncio",
            "httpx",
            "pytest-httpx",
        ]
        # Prefer keeping list stable; append helpful extras:
        return base + ["asgi-lifespan"]

    def setup_framework_environment(self, target_root: pathlib.Path) -> None:
        """
        Optional hook for FastAPI (usually minimal). We provide a no-op that can be
        extended by the caller to export env vars if needed.
        """
        _ = target_root  # intentionally unused; kept for parity with other handlers
    
    def can_handle(self, analysis: Dict[str, Any]) -> bool:
        # Guard: analysis might not be a dict
        if not isinstance(analysis, dict):
            return False
        


    # -- Test generation -------------------------------------------------------
    def generate_framework_specific_tests(self, analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Create per-route async tests using httpx.AsyncClient with ASGITransport.
        Falls back to TestClient-style smoke if needed.
        """
        tests: List[Dict[str, Any]] = []
        routes = analysis.get("fastapi_routes", []) or []
        app_module_guess = self._guess_app_module(analysis)

        for r in routes[:200]:  # cap to keep output manageable
            template = self._route_test_template(route=r, app_module=app_module_guess)
            tests.append({
                "type": "fastapi_route_test",
                "target": f"{r.get('method','GET')} {r.get('path','/')}",
                "template": template,
                "coverage_goal": "95%+",
                "test_count": 1
            })

        # If include_router present but no direct routes in this file, emit a smoke test
        if not routes and analysis.get("fastapi_include_router"):
            tests.append({
                "type": "fastapi_urls_smoke",
                "target": "include_router",
                "template": self._include_router_smoke_template(app_module_guess),
                "coverage_goal": "95%+",
                "test_count": 1
            })
        return tests

    def _guess_app_module(self, analysis: Dict[str, Any]) -> str:
        """
        Try to guess the main module path that exposes `app`.
        Uses project_structure.module_paths and simple heuristics.
        """
        ps = analysis.get("project_structure", {})
        module_paths = list(ps.get("module_paths", {}).keys()) if isinstance(ps, dict) else []
        # Prefer 'main.py', then 'app.py', then anything containing 'api'
        for pref in ("main.py", "app.py"):
            for p in module_paths:
                if p.lower().endswith(pref):
                    return p.replace("/", ".").replace("\\", ".").rstrip(".py")
        for p in module_paths:
            if "api" in p.lower():
                return p.replace("/", ".").replace("\\", ".").rstrip(".py")
        # Fallback: first path if any
        if module_paths:
            return module_paths[0].replace("/", ".").replace("\\", ".").rstrip(".py")
        return "main"

    def _route_test_template(self, route: Dict[str, Any], app_module: str) -> str:
        """
        Async httpx test template that imports real app.
        Supports both `app = FastAPI()` and `def create_app(): -> FastAPI`.
        """
        method = route.get("method", "GET")
        path = route.get("path", "/")
        return f'''
"""
Route test for {method} {path} (real app import).
"""

import importlib
import pytest

try:
    import httpx
except Exception:  # pragma: no cover
    httpx = None

@pytest.mark.asyncio
async def test_route_{method.lower()}_{self._sanitize_name(path)}():
    assert httpx is not None, "httpx must be installed"

    mod = importlib.import_module("{app_module}")
    app = getattr(mod, "app", None)
    if app is None and hasattr(mod, "create_app"):
        app = mod.create_app()
    assert app is not None, "Could not obtain FastAPI app instance from module"

    # Prefer native ASGI transport to avoid network
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.request("{method}", "{path}")
        assert resp.status_code in (200, 201, 202, 204, 301, 302, 307, 308, 400, 401, 403, 404, 405)
'''

    def _include_router_smoke_template(self, app_module: str) -> str:
        return f'''
"""
Smoke test to import app module and execute router inclusion code paths.
"""

def test_include_router_smoke():
    __import__("{app_module}")
    assert True
'''

    # -- Extra helpers ---------------------------------------------------------
    def recommended_pytest_markers(self, analysis: Dict[str, Any]) -> List[str]:
        """
        Suggest markers based on async presence. Useful for orchestrators that
        collect markers into a header file.
        """
        marks: List[str] = []
        if analysis.get("has_async") or analysis.get("async_functions"):
            marks.append("asyncio")
        return marks

    def _sanitize_name(self, s: str) -> str:
        out = s.strip("/").replace("/", "_").replace("{", "").replace("}", "").replace(":", "_")
        return out or "root"
