"""T00 — `sofa` imports nothing from `simple` (PLAN §0.1).

Enforced by test, not by promise. `simple` carries ~28 000 lines shaped around
six providers, quotas, corroboration and backward compatibility that do not
exist here; one import is enough to drag that shape back in.
"""

from __future__ import annotations

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

# Only these top-level names may be imported from within the repo.
ALLOWED_INTERNAL_PREFIXES = ("bet.sofa", "scripts.sofa")

ROOT = Path(__file__).resolve().parents[2]
SOFA_SRC = ROOT / "src" / "bet" / "sofa"
SOFA_SCRIPTS = ROOT / "scripts" / "sofa"


def module_name_for(path: Path) -> str:
    """The dotted package name a file lives at, for resolving relative imports."""
    resolved = path.resolve()
    for base in (ROOT / "src", ROOT):
        try:
            relative = resolved.relative_to(base)
        except ValueError:
            continue
        return ".".join(relative.with_suffix("").parts)
    # A file outside the repo (a temporary one in a test) has no package name;
    # level-based resolution then yields a bare module, which is still checked.
    return resolved.stem


def resolve_relative(module: str | None, level: int, importer: str) -> str:
    """Turn `from ..x import y` into the absolute module it actually names.

    A relative import is the hole a prefix check leaves open: `from
    ..simple_stats import contracts` inside `bet/sofa/` names
    `bet.simple_stats` and matches none of the forbidden literals.
    """
    parts = importer.split(".")
    # level 1 is the containing package, level 2 its parent, and so on.
    base = parts[: len(parts) - level] if level <= len(parts) else []
    return ".".join([*base, module] if module else base)


def check_file(path: Path) -> list[str]:
    violations: list[str] = []

    resolved = path.resolve()
    if "scripts" in resolved.parts and "simple" in resolved.parts:
        violations.append(f"{path}: a sofa module must not live under scripts/simple")

    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        return [f"{path}: does not parse ({exc})"]

    importer = module_name_for(path)

    def flag(name: str, form: str) -> None:
        for prefix in FORBIDDEN_PREFIXES:
            if name == prefix or name.startswith(prefix + "."):
                violations.append(f"{path}: forbidden {form} '{name}'")
                return
        # A repo-internal import outside bet.sofa / scripts.sofa is forbidden
        # even if it is not on the explicit list — the list is a floor, not a
        # specification, and a new `bet.*` package must not slip in.
        top = name.split(".")[0]
        if top in {"bet", "scripts"} and not name.startswith(ALLOWED_INTERNAL_PREFIXES):
            violations.append(f"{path}: repo-internal {form} '{name}' outside sofa")

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                flag(alias.name, "import")

        elif isinstance(node, ast.ImportFrom):
            if node.level:
                flag(
                    resolve_relative(node.module, node.level, importer),
                    f"relative from-import (level {node.level})",
                )
            elif node.module:
                flag(node.module, "from-import")

        elif isinstance(node, ast.Call):
            func = node.func
            is_import_module = (
                isinstance(func, ast.Attribute) and func.attr == "import_module"
            ) or (isinstance(func, ast.Name) and func.id == "import_module")
            is_dunder_import = isinstance(func, ast.Name) and func.id == "__import__"
            if not (is_import_module or is_dunder_import):
                continue
            for arg in node.args[:1]:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    flag(arg.value, "dynamic import")

    return violations


def sofa_files() -> list[Path]:
    paths: list[Path] = []
    for root in (SOFA_SRC, SOFA_SCRIPTS):
        if root.exists():
            paths.extend(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)
    return sorted(paths)


def test_there_are_files_to_check() -> None:
    """A test that silently checks nothing is worse than no test."""
    assert len(sofa_files()) >= 15


def test_no_import_from_simple() -> None:
    violations = [v for path in sofa_files() for v in check_file(path)]
    if violations:
        pytest.fail("\n".join(violations))


def test_the_checker_catches_a_relative_import(tmp_path: Path) -> None:
    """Guard the guard: a relative import must not slip past the prefix check."""
    package = tmp_path / "src" / "bet" / "sofa"
    package.mkdir(parents=True)
    offender = package / "sneaky.py"
    offender.write_text("from ..simple_stats import contracts\n", encoding="utf-8")

    parts = offender.resolve().parts
    importer = ".".join(parts[parts.index("src") + 1 :]).removesuffix(".py")
    assert resolve_relative("simple_stats", 2, importer) == "bet.simple_stats"


@pytest.mark.parametrize(
    "source",
    [
        "import bet.simple_stats\n",
        "from bet.discovery import discover\n",
        "from bet.api_clients.superbet import SuperbetClient\n",
        "import importlib\nimportlib.import_module('bet.simple_stats.contracts')\n",
        "from importlib import import_module\nimport_module('bet.db')\n",
        "__import__('bet.stats')\n",
        "from bet.forecast import forecast\n",
    ],
)
def test_the_checker_catches_each_forbidden_form(tmp_path: Path, source: str) -> None:
    offender = tmp_path / "offender.py"
    offender.write_text(source, encoding="utf-8")
    assert check_file(offender), f"checker missed: {source!r}"


@pytest.mark.parametrize(
    "source",
    [
        "from bet.sofa.engine import devig\n",
        "from scripts.sofa.run_sheet import process_fixture\n",
        "import json\nimport statistics\n",
        "from rapidfuzz import fuzz\n",
        "from curl_cffi import requests\n",
    ],
)
def test_the_checker_allows_what_the_plan_allows(tmp_path: Path, source: str) -> None:
    allowed = tmp_path / "fine.py"
    allowed.write_text(source, encoding="utf-8")
    assert check_file(allowed) == []


def test_sofa_uses_its_own_database_file() -> None:
    """§0.1/I3: separate file, so the rule is checkable with `ls`."""
    from bet.sofa.config import SofaConfig

    assert SofaConfig().db_path == "data/sofa.db"
    assert "bet.db" not in SofaConfig().db_path
