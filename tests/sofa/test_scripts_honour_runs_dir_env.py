"""read_set / merge_reads / build_slip / verify_legs default --runs-dir to
SOFA_RUNS_DIR (a scratch replay must never write the real day - review R4
2026-10-23: read_set.py wrote a rehearsal's read_set / dossier into the real
runs/sofa), and the three writers refuse a frozen clock on the real dir."""

from __future__ import annotations

import importlib

import pytest

from bet.sofa import timeutil

WRITERS = ("read_set", "merge_reads", "build_slip")
REQUIRED = {"read_set": [], "merge_reads": ["--report", "x.md"],
            "build_slip": ["--target", "4"]}


@pytest.mark.parametrize("name", WRITERS)
def test_a_writer_refuses_a_frozen_clock_on_the_real_runs_dir(
        name: str, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    mod = importlib.import_module(f"scripts.sofa.{name}")
    monkeypatch.setenv("SOFA_NOW", "2026-10-24T06:00:00Z")
    monkeypatch.delenv("SOFA_RUNS_DIR", raising=False)
    assert mod.main(["--date", "2026-10-23", *REQUIRED[name],
                     "--runs-dir", str(timeutil.REAL_RUNS_DIR)]) == 2
    assert "REFUSED" in capsys.readouterr().err


@pytest.mark.parametrize("name", (*WRITERS, "verify_legs"))
def test_the_runs_dir_default_reads_sofa_runs_dir(name: str) -> None:
    src = importlib.import_module(f"scripts.sofa.{name}").__file__
    assert src is not None
    text = open(src, encoding="utf-8").read()
    assert 'default=os.environ.get("SOFA_RUNS_DIR", "runs/sofa")' in text
    assert 'add_argument("--runs-dir", default="runs/sofa")' not in text
