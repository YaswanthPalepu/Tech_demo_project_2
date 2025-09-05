from dataclasses import dataclass
from pathlib import Path

@dataclass
class ProjectType:
    name: str

def detect_project(root: Path) -> ProjectType | None:
    # Python-only generator; we still detect non-Python to exit early if needed
    if (root / "requirements.txt").exists() or (root / "pyproject.toml").exists():
        return ProjectType(name="python")
    return None
