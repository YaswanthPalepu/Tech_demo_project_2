import os
import json
import time
import argparse
import logging
import inspect
import importlib.util
import pathlib
from typing import Optional, Union, Tuple, List, Dict

# OpenAI (non-Azure) is not used; Azure-only. Keep a stub for test patching.
OpenAI = None  # tests may patch this symbol

# Optional Azure OpenAI support; used only if configured
try:
    from openai import AzureOpenAI  # type: ignore
    AzureOpenAIClient = AzureOpenAI
except Exception:
    AzureOpenAIClient = None

logger = logging.getLogger(__name__)


class TestGenerator:
    def __init__(
        self,
        use_ai: bool = False,
        model: str = "prasad8792",
        provider: str = "azure",
        azure_endpoint: Optional[str] = None,
        azure_api_key: Optional[str] = None,
    ):
        self.use_ai = use_ai
        self.model = model
        self.provider = (provider or "azure").lower()
        self.api_key = (
            azure_api_key
            or os.getenv("AZURE_OPENAI_API_KEY")
            or os.getenv("AZURE_OPENAI_KEY")
        )
        self.azure_endpoint = azure_endpoint or os.getenv("AZURE_OPENAI_ENDPOINT")
        self.azure_api_version = os.getenv("AZURE_OPENAI_API_VERSION")
        try:
            self.max_completion_tokens = int(
                os.getenv("AZURE_OPENAI_MAX_COMPLETION_TOKENS", "2048")
            )
        except Exception:
            self.max_completion_tokens = 2048
        self.openai_client = None
        if self.use_ai and self.provider == "azure":
            try:
                if AzureOpenAIClient and self.api_key and self.azure_endpoint:
                    kwargs = {"api_key": self.api_key, "azure_endpoint": self.azure_endpoint}
                    if self.azure_api_version:
                        kwargs["api_version"] = self.azure_api_version
                    self.openai_client = AzureOpenAIClient(**kwargs)  # type: ignore
            except Exception as e:
                logger.warning(f"Failed to init AI client: {e}")

    # -------------------- generators --------------------
    def generate_unit_tests(self, analysis: dict, code: Union[str, dict, None] = None, framework: str = "pytest") -> str:
        return self._gen_from_ai("unit", analysis, code, framework)

    def generate_integration_tests(self, analysis: dict, code: Union[str, dict, None] = None, framework: str = "pytest") -> str:
        return self._gen_from_ai("integration", analysis, code, framework)

    def generate_e2e_tests(self, analysis: dict, code: Union[str, dict, None] = None, framework: str = "pytest") -> str:
        return self._gen_from_ai("e2e", analysis, code, framework)

    def _gen_from_ai(self, kind: str, analysis: dict, code: Union[str, dict, None], framework: str) -> str:
        """Shared AI call with validation."""
        if not (self.use_ai and self.provider == "azure" and self.openai_client):
            return ""
        try:
            src_path = code.get("src_path") if isinstance(code, dict) else None
            code_content = code.get("content") if isinstance(code, dict) else None
            prompt = self._build_prompt(kind, analysis, framework, code_content, src_path)
            resp = self.openai_client.chat.completions.create(  # type: ignore
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=self.max_completion_tokens,
            )
            out = (resp.choices[0].message.content or "").strip()
            # Validate: must contain at least one test_ function
            if "def test_" not in out or "assert" not in out:
                return ""
            return out
        except Exception:
            return ""

    # -------------------- helpers --------------------
    def _build_prompt(self, kind: str, analysis: dict, framework: str, code_content: Optional[str], src_path: Optional[str]) -> str:
        guidance = (
            f"Generate {framework} {kind} tests for the following Python code.\n"
            "- Ensure runnable pytest code with real assertions (not placeholders).\n"
            "- Use importlib to import the module safely by path.\n"
            "- Cover typical cases, edge cases, and exceptions.\n"
        )
        import_header = ""
        if src_path:
            import_header = (
                "import importlib.util, pathlib\n"
                f"_MODULE_PATH = pathlib.Path(r'{src_path}').resolve()\n"
                "_SPEC = importlib.util.spec_from_file_location('target_module', _MODULE_PATH)\n"
                "target_module = importlib.util.module_from_spec(_SPEC)\n"
                "_SPEC.loader.exec_module(target_module)\n\n"
            )
        return f"{guidance}\n{import_header}\n# Code:\n{(code_content or '')[:3000]}\n\n# Analysis:\n{json.dumps(analysis, indent=2)}"

# -------------------- smoke fallback --------------------
def smoke_test_content(src_path: str) -> str:
    return (
        "import importlib.util, pathlib\n"
        f"_MODULE_PATH = pathlib.Path(r'{src_path}').resolve()\n"
        "_SPEC = importlib.util.spec_from_file_location('target_module', _MODULE_PATH)\n"
        "target_module = importlib.util.module_from_spec(_SPEC)\n"
        "_SPEC.loader.exec_module(target_module)\n\n"
        "def test_import_target_module():\n"
        "    assert target_module is not None\n"
    )

# -------------------- main --------------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--analysis", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--framework", default="pytest")
    parser.add_argument("--test_type", default="all", choices=["unit", "integration", "e2e", "all"])
    args = parser.parse_args()

    with open(args.analysis, "r", encoding="utf-8") as f:
        analysis_results = json.load(f)

    gen = TestGenerator(use_ai=bool(os.getenv("AZURE_OPENAI_KEY")), model=os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4"))

    os.makedirs(args.output, exist_ok=True)
    kinds = ["unit", "integration", "e2e"] if args.test_type == "all" else [args.test_type]

    for name, meta in analysis_results.items():
        if name == "__repo__" or not isinstance(meta, dict):
            continue
        base = os.path.splitext(os.path.basename(name))[0]
        try:
            file_content = pathlib.Path(name).read_text(encoding="utf-8", errors="ignore")
        except Exception:
            file_content = ""
        for kind in kinds:
            if kind == "unit":
                code = gen.generate_unit_tests(meta, {"src_path": name, "content": file_content})
                suffix = ".unit.test.py"
            elif kind == "integration":
                code = gen.generate_integration_tests(meta, {"src_path": name, "content": file_content})
                suffix = ".integration.test.py"
            else:
                code = gen.generate_e2e_tests(meta, {"src_path": name, "content": file_content})
                suffix = ".e2e.test.py"
            if not code.strip():
                print(f"[ai] empty output for {kind} on {name} → using smoke fallback")
                code = smoke_test_content(name)
            out = os.path.join(args.output, f"{base}{suffix}")
            pathlib.Path(out).parent.mkdir(parents=True, exist_ok=True)
            pathlib.Path(out).write_text(code, encoding="utf-8")
            print(f"Generated {kind} -> {out}")


if __name__ == "__main__":
    main()
