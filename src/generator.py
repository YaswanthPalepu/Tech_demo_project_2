import os
import json
import argparse
import pathlib
import glob
from typing import Optional, Union

try:
    from openai import AzureOpenAI  # type: ignore
    AzureOpenAIClient = AzureOpenAI
except Exception:
    AzureOpenAIClient = None


class TestGenerator:
    def __init__(
        self,
        use_ai: bool = False,
        model: str = "gpt-4",
        provider: str = "azure",
        azure_endpoint: Optional[str] = None,
        azure_api_key: Optional[str] = None,
    ):
        self.use_ai = use_ai
        self.model = model
        self.provider = (provider or "azure").lower()
        self.api_key = azure_api_key or os.getenv("AZURE_OPENAI_API_KEY") or os.getenv("AZURE_OPENAI_KEY")
        self.azure_endpoint = azure_endpoint or os.getenv("AZURE_OPENAI_ENDPOINT")
        self.azure_api_version = os.getenv("AZURE_OPENAI_API_VERSION")
        self.max_completion_tokens = int(os.getenv("AZURE_OPENAI_MAX_COMPLETION_TOKENS", "2048"))
        self.openai_client = None

        if self.use_ai and self.provider == "azure":
            if AzureOpenAIClient and self.api_key and self.azure_endpoint:
                kwargs = {"api_key": self.api_key, "azure_endpoint": self.azure_endpoint}
                if self.azure_api_version:
                    kwargs["api_version"] = self.azure_api_version
                self.openai_client = AzureOpenAIClient(**kwargs)

    # ---------------- AI-backed generators ----------------
    def generate_unit_tests(self, analysis: dict, code: Union[str, dict, None] = None) -> str:
        return self._gen_from_ai("unit", analysis, code)

    def generate_integration_tests(self, analysis: dict, code: Union[str, dict, None] = None) -> str:
        return self._gen_from_ai("integration", analysis, code)

    def generate_e2e_tests(self, analysis: dict, code: Union[str, dict, None] = None) -> str:
        return self._gen_from_ai("e2e", analysis, code)

    def _gen_from_ai(self, kind: str, analysis: dict, code: Union[str, dict, None]) -> str:
        if not (self.use_ai and self.openai_client):
            return ""
        try:
            src_path = code.get("src_path") if isinstance(code, dict) else None
            code_content = code.get("content") if isinstance(code, dict) else None
            prompt = self._build_prompt(kind, analysis, code_content, src_path)
            resp = self.openai_client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=self.max_completion_tokens,
            )
            out = (resp.choices[0].message.content or "").strip()
            if "def test_" not in out or "assert" not in out:
                return ""
            return out
        except Exception:
            return ""

    # ---------------- prompt builder ----------------
    def _build_prompt(self, kind: str, analysis: dict, code_content: Optional[str], src_path: Optional[str]) -> str:
        guidance = (
            f"Generate pytest {kind} tests for the following Python code.\n"
            "- Only output valid Python test code (no prose).\n"
            "- Must include at least one `def test_...` with real assertions.\n"
            "- Use importlib to import the module if src_path is provided.\n"
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
        return f"{guidance}\n{import_header}\n# Source code:\n{(code_content or '')[:3000]}\n\n# Analysis:\n{json.dumps(analysis, indent=2)}"


# ---------------- fallback smoke test ----------------
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


# ---------------- main generator ----------------
def generate_all(repo: str = ".", outdir: str = "tests/generated", test_type: str = "all"):
    gen = TestGenerator(
        use_ai=bool(os.getenv("AZURE_OPENAI_KEY")),
        model=os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4"),
    )
    pathlib.Path(outdir).mkdir(parents=True, exist_ok=True)
    kinds = ["unit", "integration", "e2e"] if test_type == "all" else [test_type]

    # 🔍 Find all .py files (excluding tests/ folders and __init__.py)
    py_files = [
        f for f in glob.glob(f"{repo}/**/*.py", recursive=True)
        if "tests" not in f and not f.endswith("__init__.py")
    ]

    for name in py_files:
        base = os.path.splitext(os.path.basename(name))[0]
        try:
            file_content = pathlib.Path(name).read_text(encoding="utf-8", errors="ignore")
        except Exception:
            file_content = ""

        # Minimal "fake" analysis since we’re not using analyzer
        analysis = {"functions": [], "classes": [], "variables": [], "dependencies": []}

        for kind in kinds:
            if kind == "unit":
                code = gen.generate_unit_tests(analysis, {"src_path": name, "content": file_content})
                suffix = ".unit.test.py"
            elif kind == "integration":
                code = gen.generate_integration_tests(analysis, {"src_path": name, "content": file_content})
                suffix = ".integration.test.py"
            else:
                code = gen.generate_e2e_tests(analysis, {"src_path": name, "content": file_content})
                suffix = ".e2e.test.py"

            if not code.strip():
                print(f"[ai] empty output for {kind} on {name} → using smoke fallback")
                code = smoke_test_content(name)

            out = os.path.join(outdir, f"{base}{suffix}")
            pathlib.Path(out).write_text(code, encoding="utf-8")
            print(f"Generated {kind} -> {out}")


# ---------------- CLI entrypoint ----------------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".", help="Path to the repo to scan")
    parser.add_argument("--output", default="tests/generated", help="Output directory for tests")
    parser.add_argument("--test_type", default="all", choices=["unit", "integration", "e2e", "all"])
    args = parser.parse_args()

    generate_all(repo=args.repo, outdir=args.output, test_type=args.test_type)


if __name__ == "__main__":
    main()
