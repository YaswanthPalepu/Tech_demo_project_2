from dataclasses import dataclass
from pathlib import Path

@dataclass
class ProjectType:
    name: str
    test_cmd: list[str]
    coverage_path: Path | None

def detect_project(root: Path) -> ProjectType | None:
    if (root / "requirements.txt").exists() or (root / "pyproject.toml").exists():
        return ProjectType(name="python",
                           test_cmd=["pytest", "-q"],
                           coverage_path=Path("artifacts/coverage/coverage.xml"))
    if (root / "package.json").exists():
        return ProjectType(name="node",
                           test_cmd=["npm", "test", "--silent"],
                           coverage_path=Path("artifacts/coverage/coverage-final.json"))
    if (root / "pom.xml").exists():
        return ProjectType(name="java",
                           test_cmd=["mvn", "-q", "test"],
                           coverage_path=Path("artifacts/coverage/jacoco.xml"))
    return None
