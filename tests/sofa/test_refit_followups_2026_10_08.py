"""Second review of the 2026-10-08 refit packages: install carries the staged
count dispersion / tennis rating / by_market K (and never drops one silently),
the K / dispersion pair is validated at argument level, a fit never defaults
to the live database, and the dispersion file refuses nonsense. Offline."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import count_dispersion as cd
from bet.sofa import tennis_rating as tr
from scripts.sofa import calibrate_from_cache as cc
from scripts.sofa import fit_count_dispersion as fcd
from scripts.sofa import prepare_refit as pr
from tests.sofa.test_prepare_refit import (
    _db,
    _fake_calibrate,
    _paths,
    _ready_to_install,
    _sha,
    _write,
)

DISP = {"markets": {"goals_for": {"family": "nb", "alpha": 0.2}}}


def _rating() -> dict[str, Any]:
    name = tr.ALL_FEATURES[0]
    return {"features": [name], "tiers": {"atp": {"coefficients": [0.1, 0.2]}}}


def _stage(paths: pr.Paths, *, dispersion: bool = True, rating: bool = True,
           by_market: bool = False) -> None:
    if dispersion:
        _write(paths.scratch_config / "sofa_count_dispersion.json", DISP)
    if rating:
        _write(paths.scratch_config / "tennis_rating.json", _rating())
    if by_market:
        p = paths.scratch_config / "sofa_engine_constants.json"
        doc = json.loads(p.read_text())
        doc["K_CENTRE"]["by_market"] = {"football": {"goals_for": 12.0}}
        p.write_text(json.dumps(doc, indent=2, ensure_ascii=False))


def test_install_carries_the_staged_extras_when_flagged(tmp_path: Path) -> None:
    paths = _ready_to_install(tmp_path)
    live_rating = paths.config_dir / "tennis_rating.json"
    _write(live_rating, {"old": True})
    shutil.rmtree(paths.backup_dir)
    pr.backup(paths, None)
    _stage(paths)
    pr.install(paths, confirm=True, tests=lambda: 0,
               count_dispersion=True, tennis_rating=True)
    installed = paths.config_dir / "sofa_count_dispersion.json"
    assert json.loads(installed.read_text()) == DISP
    assert json.loads(live_rating.read_text()) == _rating()


def test_install_without_the_flags_leaves_the_extras_alone(tmp_path: Path) -> None:
    paths = _ready_to_install(tmp_path)
    _stage(paths)
    pr.install(paths, confirm=True, tests=lambda: 0)
    assert not (paths.config_dir / "sofa_count_dispersion.json").exists()
    assert json.loads((paths.config_dir / "tennis_rating.json").read_text()) == {}


@pytest.mark.parametrize("flag, kw", [
    ("sofa_count_dispersion.json", {"count_dispersion": True}),
    ("tennis_rating.json", {"tennis_rating": True}),
])
def test_a_flagged_extra_missing_from_the_staged_dir_is_refused(
    tmp_path: Path, flag: str, kw: dict[str, bool],
) -> None:
    paths = _ready_to_install(tmp_path)
    _stage(paths, dispersion=False, rating=False)
    (paths.scratch_config / flag).unlink(missing_ok=True)
    before = {p.name: _sha(p) for p in paths.config_dir.glob("*.json")}
    with pytest.raises(pr.RefitError, match="missing"):
        pr.install(paths, confirm=True, tests=lambda: 0, **kw)
    assert {p.name: _sha(p) for p in paths.config_dir.glob("*.json")} == before


def test_a_flagged_extra_that_does_not_parse_is_refused(tmp_path: Path) -> None:
    paths = _ready_to_install(tmp_path)
    _write(paths.scratch_config / "sofa_count_dispersion.json",
           {"markets": {"goals_for": {"family": "nb", "alpha": True}}})
    with pytest.raises(pr.RefitError, match="not installable"):
        pr.install(paths, confirm=True, tests=lambda: 0, count_dispersion=True)


def test_per_market_k_flag_needs_the_staged_by_market(tmp_path: Path) -> None:
    paths = _ready_to_install(tmp_path)
    with pytest.raises(pr.RefitError, match="by_market"):
        pr.install(paths, confirm=True, tests=lambda: 0, per_market_k=True)


def test_a_failed_install_restores_the_extras_and_removes_a_new_one(
    tmp_path: Path,
) -> None:
    paths = _ready_to_install(tmp_path)  # backup taken: no dispersion file live
    _write(paths.config_dir / "tennis_rating.json", {"old": True})
    shutil.rmtree(paths.backup_dir)
    pr.backup(paths, None)
    _stage(paths)
    before = {p.name: _sha(p) for p in paths.config_dir.glob("*.json")}
    with pytest.raises(pr.RefitError, match="restored"):
        pr.install(paths, confirm=True, tests=lambda: 1,
                   count_dispersion=True, tennis_rating=True)
    assert {p.name: _sha(p) for p in paths.config_dir.glob("*.json")} == before
    assert not (paths.config_dir / "sofa_count_dispersion.json").exists()


def test_the_install_cli_takes_the_flags() -> None:
    args = pr.build_parser().parse_args(
        ["install", "--confirm", "--count-dispersion", "--tennis-rating",
         "--per-market-k"])
    assert args.count_dispersion and args.tennis_rating and args.per_market_k


# --- 4: the pair -------------------------------------------------------------


@pytest.mark.parametrize("argv", [
    ["--per-market-k"], ["--count-dispersion"],
])
def test_calibrate_rejects_one_of_the_pair(
    monkeypatch: pytest.MonkeyPatch, argv: list[str],
) -> None:
    monkeypatch.setattr(sys, "argv", ["calibrate_from_cache.py", *argv])
    with pytest.raises(SystemExit) as exc:
        cc.main()
    assert exc.value.code == 2


def test_rebuild_cache_rows_rejects_one_of_the_pair(tmp_path: Path) -> None:
    paths = _paths(tmp_path)
    _db(paths.db_path)
    called: list[int] = []

    def runner(cmd: Any, env: Any, log: Any) -> tuple[int, list[str]]:
        called.append(1)
        return _fake_calibrate(paths.db_path)(cmd, env, log)

    for kw in ({"per_market_k": True}, {"count_dispersion": True}):
        with pytest.raises(pr.RefitError, match="go together"):
            pr.rebuild_cache_rows(paths, dry_run=False, confirm=True, runner=runner,
                                  require_db_backup=False, **kw)
    assert called == []  # nothing ran, nothing deleted


# --- 5: the fit never defaults to the live database --------------------------


def test_collecting_cases_needs_a_copy_not_the_live_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert fcd.collection_db_refusal(None)
    assert fcd.collection_db_refusal(str(fcd.LIVE_DB))
    assert fcd.collection_db_refusal(str(tmp_path / "copy.db")) is None
    monkeypatch.setattr(sys, "argv", [
        "fit_count_dispersion.py", "--before", "2026-10-08",
        "--cases", str(tmp_path / "empty_cases")])
    assert fcd.main() == 2
    assert "REFUSED" in capsys.readouterr().err


# --- 6: parse_table ----------------------------------------------------------


@pytest.mark.parametrize("bad", [True, False, cd.ALPHA_MAX + 0.01, 1e9])
def test_parse_table_refuses_bool_and_absurd_alphas(bad: Any) -> None:
    with pytest.raises(ValueError):
        cd.parse_table({"markets": {"goals_for": {"family": "nb", "alpha": bad}}})
    with pytest.raises(ValueError):
        cd.parse_table({"markets": {"goals_for": {
            "family": "nb", "alpha": 0.2, "by_competition": {"17": bad}}}})
    with pytest.raises(ValueError):
        cd.parse_table({"markets": {"goals_for": {
            "family": "nb", "alpha": 0.2, "by_competition": {"17": {"alpha": bad}}}}})


@pytest.mark.parametrize("key", ["-1", "1.5", "abc", "", " 3", "1e2", True, -3, 2.5])
def test_parse_table_refuses_bad_competition_keys(key: Any) -> None:
    table = {"markets": {"goals_for": {
        "family": "nb", "alpha": 0.2, "by_competition": {}}}}
    table["markets"]["goals_for"]["by_competition"][key] = 0.3
    with pytest.raises(ValueError):
        cd.parse_table(table)


def test_parse_table_accepts_the_shipped_range() -> None:
    t = cd.parse_table({"markets": {"goals_for": {
        "family": "nb", "alpha": cd.ALPHA_MAX, "by_competition": {"17": 1.5878}}}})
    assert t.read("football", "goals_for", 17).alpha == 1.5878  # type: ignore[union-attr]
    cd.load_table()  # the shipped file still parses
