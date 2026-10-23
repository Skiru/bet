"""Review R2 #4: the coverage audit 2026-10-23's switches the replays do not
carry are named by a refit - prepare_refit's install warns for P1 / P3
(football) / P5 / P14 (calibrate_from_cache replays none of them), and
fit_sport_confidence warns for P7 (CS2) / P13 (volleyball) and names them
in fitted_from - never refused, like UNREPLAYABLE_SWITCHES. Offline."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from bet.sofa import epochs
from scripts.sofa import fit_sport_confidence as fsc
from scripts.sofa import prepare_refit as pr
from tests.sofa.test_refit_replay_switch_guard import _cfg, _staged

EVE = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)    # 10-24 is the next day
EARLY = datetime(2026, 10, 21, 12, 0, tzinfo=UTC)


def _audit_lines(warnings: list[str]) -> list[str]:
    return [w for w in warnings if w.split(" is on")[0].endswith(")")]


def test_install_warns_for_each_unreplayed_audit_switch(tmp_path: Path) -> None:
    refusals, warnings = pr.replay_switch_gaps(
        _staged(closeness_stretch=True, player_coverage=True), at=EVE,
        config_dir=_cfg(tmp_path))
    assert refusals == []
    names = [w.split(" is on")[0] for w in _audit_lines(warnings)]
    assert names == ["SAMPLE_CONFLICT_CUT (P1)",
                     "PLAYER_HISTORY_ANY_TEAM (P3, football)",
                     "PLAYER_SLUG_NAME (P5)",
                     "TENNIS_RATING_SCORE_WINNER (P14)"]
    assert all("the replay cannot carry it" in w for w in _audit_lines(warnings))


def test_before_the_switches_nothing_is_warned(tmp_path: Path) -> None:
    _, warnings = pr.replay_switch_gaps(
        _staged(closeness_stretch=True, player_coverage=True), at=EARLY,
        config_dir=_cfg(tmp_path))
    assert _audit_lines(warnings) == []


def test_p3_is_read_for_football_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(epochs, "PLAYER_HISTORY_ANY_TEAM_SPORTS",
                        frozenset({"hockey"}))
    _, warnings = pr.replay_switch_gaps(
        _staged(closeness_stretch=True, player_coverage=True), at=EVE,
        config_dir=_cfg(tmp_path))
    assert not any(w.startswith("PLAYER_HISTORY_ANY_TEAM") for w in warnings)


def test_the_sport_fit_names_p7_and_p13_for_their_sports() -> None:
    (cs2,) = fsc.unreplayed_switches("cs2", "2026-10-24")
    assert cs2.startswith("CS2_LINEUP_ELO_UNRATED (P7) is on for 2026-10-24")
    (vb,) = fsc.unreplayed_switches("volleyball", "2026-10-24")
    assert vb.startswith("VB_GOLDEN_SET (P13) is on")
    assert fsc.unreplayed_switches("hockey", "2026-10-24") == []
    assert fsc.unreplayed_switches("cs2", "2026-10-23") == []
