"""Tests for import portability and import-origin safety."""
from __future__ import annotations

import copy
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from bet.pipeline.orchestrator import Orchestrator


def test_import_does_not_modify_sys_path():
    # 1. import bet does not modify sys.path
    import subprocess
    import sys
    src_dir = Path(__file__).resolve().parents[1] / "src"
    res = subprocess.run(
        [sys.executable, "-c", "import sys; orig = list(sys.path); import bet; assert sys.path == orig"],
        env={"PYTHONPATH": str(src_dir)},
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0


def test_package_imports_in_arbitrary_temp_path(tmp_path):
    # 2. The package imports after installation in an arbitrary temporary path
    src_dir = Path(__file__).resolve().parents[1] / "src"
    res = subprocess.run(
        [sys.executable, "-c", "import bet; print(bet.__file__)"],
        cwd=str(tmp_path),
        env={"PYTHONPATH": str(src_dir)},
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    assert "bet" in res.stdout


def test_package_imports_projects_bet_suffix(tmp_path):
    # 3. It imports when the repository is located at a path ending exactly in projects/bet
    fake_repo = tmp_path / "projects" / "bet"
    fake_repo.mkdir(parents=True)
    src_bet = Path(__file__).resolve().parents[1] / "src" / "bet"
    shutil.copytree(src_bet, fake_repo / "src" / "bet")

    res = subprocess.run(
        [sys.executable, "-c", "import sys; sys.path.insert(0, 'src'); import bet; print(bet.__file__)"],
        cwd=str(fake_repo),
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    assert "bet" in res.stdout


def test_imports_with_no_developer_paths():
    # 4. It imports from a clean wheel with no developer paths
    import bet
    with open(bet.__file__, encoding="utf-8") as f:
        content = f.read()
    assert "/Users/" not in content


def test_no_tracked_source_contains_dev_path():
    # 5. No tracked source file contains /Users/mkoziol/projects/bet
    repo_root = Path(__file__).resolve().parents[1]
    src_dir = repo_root / "src"
    for path in src_dir.rglob("*.py"):
        content = path.read_text(encoding="utf-8")
        assert "/Users/mkoziol/projects/bet" not in content


def test_canonical_runner_blocks_on_external_import():
    # 6. The canonical runner blocks when bet.__file__ is outside the expected runtime repository
    from unittest.mock import patch

    import bet

    with patch.object(bet, "__file__", "/some/other/path/bet/__init__.py"):
        with pytest.raises(RuntimeError) as exc:
            Orchestrator(
                betting_day="2026-06-25",
                run_id="run-999",
                runtime_mode="DRY_RUN",
            )
        assert "Import-origin violation" in str(exc.value)
