import ast
from pathlib import Path

import pytest

SRC = Path(__file__).parents[1] / "src"
POLICY_PACKAGES = ["jobs", "configs", "recording_conversion"]


def module_name(path: Path) -> str:
    parts = path.relative_to(SRC).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def imports(path: Path) -> set[str]:
    parts = module_name(path).split(".")
    package = parts if path.name == "__init__.py" else parts[:-1]
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            # Relative imports are resolved so `from ..adapters import x` cannot bypass the checks
            base = package[: len(package) - node.level + 1] if node.level else []
            names.add(".".join([*base, *filter(None, [node.module])]))
    return names


def depends_on(path: Path, prefix: str) -> bool:
    return any(name == prefix or name.startswith(f"{prefix}.") for name in imports(path))


def packages_importing(prefix: str) -> set[str]:
    return {module_name(path).split(".")[0] for path in SRC.rglob("*.py") if depends_on(path, prefix)}


@pytest.mark.parametrize("package", POLICY_PACKAGES)
def test_policy_never_depends_on_adapters_or_the_http_layer(package: str) -> None:
    forbidden = ["nomadic", "adapters", "handlers", "dependencies", "main", "fastapi"]
    violations = [
        (module_name(path), prefix)
        for path in (SRC / package).rglob("*.py")
        for prefix in forbidden
        if depends_on(path, prefix)
    ]
    assert not violations


def test_recording_conversion_knows_nothing_about_jobs() -> None:
    assert "recording_conversion" not in packages_importing("jobs")


def test_only_the_adapter_imports_the_nomadic_sdk() -> None:
    assert packages_importing("nomadic") == {"adapters"}


def test_only_the_composition_root_wires_adapters() -> None:
    assert packages_importing("adapters") == {"dependencies"}


def test_http_framework_stays_in_the_delivery_layer() -> None:
    assert packages_importing("fastapi") <= {"handlers", "main"}
