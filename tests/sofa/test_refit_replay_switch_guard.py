"""Audit 2026-10-21 D4 / D5: prepare_refit passes --player-coverage (and
--closeness-stretch) to the cache replay and records both in
fitted_from.replay_rules.flags; `install` refuses a fit whose replay lacks the
flag of a replayable switch on for the day after the install
(FOOTBALL_CLOSENESS_STRETCH, FOOTBALL_PLAYER_COVERAGE, and from 2026-11-05
FOOTBALL_REFEREE / FOOTBALL_PLAYER_SHARE / P1 / P14, replayed by
calibrate_from_cache --referee / --player-share / --sample-conflict-cut /
--tennis-score-winner) unless named with --allow-missing-replay-flag; no
switch is left that the replay cannot carry (UNREPLAYABLE_SWITCHES empty).
Offline and fast."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import epochs
from scripts.sofa import prepare_refit as pr
from tests.sofa.test_prepare_refit import _ready_to_install, _write

AT = datetime(2026, 10, 21, 9, 0, tzinfo=UTC)
BEFORE = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


def _staged(**flags: Any) -> dict[str, Any]:
    return {"fitted_from": {"replay_rules": {"flags": flags}}}


def _cfg(tmp_path: Path) -> Path:
    _write(tmp_path / "sofa_referee_effect.json",
           {"markets": {"fouls_total": {}, "cards_points_total": {}}})
    _write(tmp_path / "sofa_player_share.json",
           {"markets": ["player_shots_for", "player_fouls_for"]})
    return tmp_path


def test_the_replay_flag_keys_carry_both_switches() -> None:
    assert "player_coverage" in pr.REPLAY_FLAG_KEYS
    assert "closeness_stretch" in pr.REPLAY_FLAG_KEYS
    keys = {k for _, _, k in pr.REPLAYABLE_SWITCHES}
    assert keys == {"player_coverage", "closeness_stretch", "awarded_excluded",
                    "referee", "player_share", "tennis_score_winner",
                    "sample_conflict_cut", "form_table_per_family",
                    "cards_closeness_off"}
    assert pr.UNREPLAYABLE_SWITCHES == ()
    assert keys <= set(pr.REPLAY_FLAG_KEYS)


def test_the_rebuild_cli_takes_player_coverage() -> None:
    args = pr.build_parser().parse_args(
        ["--date", "2026-10-21", "rebuild-cache-rows", "--player-coverage",
         "--closeness-stretch"])
    assert args.player_coverage and args.closeness_stretch
    args = pr.build_parser().parse_args(
        ["--date", "2026-10-21", "install",
         "--allow-missing-replay-flag=--player-coverage",
         "--allow-missing-replay-flag", "closeness_stretch"])
    assert args.allow_missing_replay_flag == ["--player-coverage",
                                              "closeness_stretch"]


def test_a_replay_without_an_on_switch_flag_is_refused(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    refusals, _ = pr.replay_switch_gaps(_staged(), at=AT, config_dir=cfg)
    assert refusals == [
        "FOOTBALL_CLOSENESS_STRETCH is on, the replay lacks --closeness-stretch",
        "FOOTBALL_PLAYER_COVERAGE is on, the replay lacks --player-coverage",
        "FOOTBALL_REFEREE is on, the replay lacks --referee",
        "FOOTBALL_PLAYER_SHARE is on, the replay lacks --player-share"]
    refusals, _ = pr.replay_switch_gaps(
        _staged(closeness_stretch=True, player_coverage=True, referee=True,
                player_share=True), at=AT, config_dir=cfg)
    assert refusals == []


def test_the_escape_names_each_flag(tmp_path: Path) -> None:
    cfg = _cfg(tmp_path)
    refusals, _ = pr.replay_switch_gaps(
        _staged(closeness_stretch=True, referee=True, player_share=True),
        at=AT, config_dir=cfg, allow_missing=["--player-coverage"])
    assert refusals == []
    refusals, _ = pr.replay_switch_gaps(
        _staged(referee=True), at=AT, config_dir=cfg,
        allow_missing=["player-coverage", "--player-share"])
    assert refusals == [
        "FOOTBALL_CLOSENESS_STRETCH is on, the replay lacks --closeness-stretch"]


def test_a_switch_on_only_from_tomorrow_already_counts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    cfg = _cfg(tmp_path)
    monkeypatch.setattr(epochs, "FOOTBALL_CLOSENESS_STRETCH_FROM_UTC",
                        datetime(2026, 10, 22, 12, tzinfo=UTC))
    monkeypatch.setattr(epochs, "FOOTBALL_PLAYER_COVERAGE_FROM_UTC", None)
    monkeypatch.setattr(epochs, "FOOTBALL_REFEREE_FROM_UTC", None)
    monkeypatch.setattr(epochs, "FOOTBALL_PLAYER_SHARE_FROM_UTC", None)
    refusals, _ = pr.replay_switch_gaps(_staged(), at=AT, config_dir=cfg)
    assert refusals == [
        "FOOTBALL_CLOSENESS_STRETCH is on, the replay lacks --closeness-stretch"]
    # two days off: not yet
    monkeypatch.setattr(epochs, "FOOTBALL_CLOSENESS_STRETCH_FROM_UTC",
                        datetime(2026, 10, 23, tzinfo=UTC))
    assert pr.replay_switch_gaps(_staged(), at=AT, config_dir=cfg)[0] == []


def test_switches_off_refuse_and_warn_nothing(tmp_path: Path) -> None:
    refusals, warnings = pr.replay_switch_gaps(
        _staged(), at=BEFORE, config_dir=_cfg(tmp_path))
    assert refusals == [] and warnings == []


def test_referee_and_share_replayed_are_neither_refused_nor_warned(
        tmp_path: Path) -> None:
    refusals, warnings = pr.replay_switch_gaps(
        _staged(closeness_stretch=True, player_coverage=True, referee=True,
                player_share=True), at=AT, config_dir=_cfg(tmp_path))
    assert refusals == []
    assert warnings == []


def test_install_refuses_then_allows_by_name(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    paths = _ready_to_install(tmp_path, replay_flags={
        "closeness_stretch": True, "referee": True, "player_share": True})
    before = {p.name: p.read_bytes() for p in paths.config_dir.glob("*.json")}
    with pytest.raises(pr.RefitError, match="--player-coverage"):
        pr.install(paths, confirm=True, tests=lambda: 0, at=AT)
    assert {p.name: p.read_bytes()
            for p in paths.config_dir.glob("*.json")} == before
    _cfg(paths.config_dir)
    result = pr.install(paths, confirm=True, tests=lambda: 0, at=AT,
                        allow_missing_replay_flags=["--player-coverage"])
    assert result["allowed_missing_replay_flags"] == ["player_coverage"]
    assert not any("FOOTBALL_REFEREE" in w
                   for w in result["replay_switch_warnings"])
    manifest = json.loads((paths.scratch / "install_manifest.json").read_text())
    assert manifest["allowed_missing_replay_flags"] == ["player_coverage"]


def test_install_before_the_switches_needs_no_flag(tmp_path: Path) -> None:
    paths = _ready_to_install(tmp_path, replay_flags={})
    pr.install(paths, confirm=True, tests=lambda: 0, at=BEFORE)


def test_the_rebuild_passes_player_coverage_and_records_it(tmp_path: Path) -> None:
    """rebuild_cache_rows hands --player-coverage to calibrate_from_cache and
    stamps it in replay_rules.json (D4)."""
    from tests.sofa.test_prepare_refit import _db, _fake_calibrate, _paths
    paths = _paths(tmp_path)
    from tests.sofa.test_prepare_refit import _config_set
    _config_set(paths.config_dir, new=False)
    _db(paths.db_path)
    seen: list[list[str]] = []
    runner = _fake_calibrate(paths.db_path)

    def spy(cmd: list[str], env: Any, cwd: Any) -> Any:
        seen.append(list(cmd))
        return runner(cmd, env, cwd)

    pr.rebuild_cache_rows(paths, dry_run=False, confirm=True,
                          require_db_backup=False, runner=spy,
                          player_coverage=True)
    assert "--player-coverage" in seen[0]
    rules = json.loads((paths.scratch / pr.REPLAY_RULES).read_text())
    assert rules["flags"]["player_coverage"] is True
