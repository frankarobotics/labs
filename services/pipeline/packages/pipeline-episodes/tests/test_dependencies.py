import ast
import sys
from pathlib import Path

import pipeline_episodes

# the contract is imported by ROS and non-ROS services alike, so it stays free of framework and IO deps
ALLOWED_THIRD_PARTY = {"pipeline_episodes", "pydantic", "uuid7"}


def imported_top_level_modules(source: Path) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(ast.parse(source.read_text())):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.add(node.module.split(".")[0])
    return modules


def test_package_imports_only_stdlib_pydantic_and_uuid7() -> None:
    package_dir = Path(pipeline_episodes.__file__).parent

    offenders = {
        f"{source.name}: {module}"
        for source in package_dir.rglob("*.py")
        for module in imported_top_level_modules(source)
        if module not in sys.stdlib_module_names and module not in ALLOWED_THIRD_PARTY
    }

    assert not offenders
