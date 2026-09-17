import ast
from pathlib import Path

import pytest

FORBIDDEN_PREFIXES = (
    "bet.simple_stats",
    "bet.discovery",
    "bet.api_clients",
    "bet.db",
    "bet.stats",
    "bet.enrichment",
    "scripts.simple",
)

def check_file(path: Path) -> list[str]:
    violations = []
    try:
        content = path.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(path))
    except Exception as e:
        return [f"Failed to parse {path}: {e}"]

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for name in node.names:
                for prefix in FORBIDDEN_PREFIXES:
                    if name.name == prefix or name.name.startswith(prefix + "."):
                        violations.append(f"Forbidden import '{name.name}' in {path}")
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                for prefix in FORBIDDEN_PREFIXES:
                    if node.module == prefix or node.module.startswith(prefix + "."):
                        violations.append(
                            f"Forbidden from-import '{node.module}' in {path}"
                        )
        elif isinstance(node, ast.Call):
            if (
                isinstance(node.func, ast.Attribute)
                and node.func.attr == "import_module"
            ):
                if (
                    node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)
                ):
                    val = node.args[0].value
                    for prefix in FORBIDDEN_PREFIXES:
                        if val == prefix or val.startswith(prefix + "."):
                            violations.append(
                                f"Forbidden import_module('{val}') in {path}"
                            )
            elif isinstance(node.func, ast.Name) and node.func.id == "import_module":
                if (
                    node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)
                ):
                    val = node.args[0].value
                    for prefix in FORBIDDEN_PREFIXES:
                        if val == prefix or val.startswith(prefix + "."):
                            violations.append(
                                f"Forbidden import_module('{val}') in {path}"
                            )

    return violations

def test_isolation() -> None:
    root = Path(__file__).parent.parent.parent
    sofa_src = root / "src" / "bet" / "sofa"
    sofa_scripts = root / "scripts" / "sofa"

    paths_to_check: list[Path] = []
    if sofa_src.exists():
        paths_to_check.extend(sofa_src.rglob("*.py"))
    if sofa_scripts.exists():
        paths_to_check.extend(sofa_scripts.rglob("*.py"))

    all_violations = []
    for p in paths_to_check:
        all_violations.extend(check_file(p))

    if all_violations:
        pytest.fail("\n".join(all_violations))
