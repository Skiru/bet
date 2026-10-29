"""The cache replay carries AWARDED_EXCLUDED (calibrate_from_cache
--awarded-excluded): a football result awarded at the table (isAwarded -
Maardu's unplayed 0-0s, 2026-10-29) is neither a side's history nor a
target, the rating history drops it and a player's history skips it, as
SAMPLES / SHEET from 2026-10-30; an install while the switch is on refuses
a replay without the flag (prepare_refit.REPLAYABLE_SWITCHES). Offline."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from bet.sofa import epochs
from scripts.sofa import calibrate_from_cache as cfc
from scripts.sofa import prepare_refit as pr
from tests.sofa.test_cache_replay_holds_slim_events import _db, _event
from tests.sofa.test_refit_replay_switch_guard import _cfg, _staged

ON = {"closeness_stretch": True, "player_coverage": True}


def _awarded(eid: int, sport: str = "football") -> dict[str, object]:
    e = _event(eid, sport)
    e["isAwarded"] = True
    return e


def test_off_the_replay_keeps_an_awarded_result(tmp_path: Path) -> None:
    # ids days apart: one_listing_per_match keys on names and the day
    db = _db(tmp_path, "a.db", [_event(1), _awarded(300_000)])
    assert [p.event_id for p in cfc.load_cache(db)] == [1, 300_000]


def test_on_an_awarded_football_result_leaves_the_replay(tmp_path: Path) -> None:
    db = _db(tmp_path, "a.db", [_event(1), _awarded(300_000)])
    assert [p.event_id for p in cfc.load_cache(db, awarded_out=True)] == [1]


def test_a_player_history_skips_it_only_under_the_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    past = _awarded(2)
    entity = past["homeTeam"]["id"]  # type: ignore[index]
    kickoff = int(past["startTimestamp"]) + 86400  # type: ignore[call-overload]
    monkeypatch.setattr(cfc, "AWARDED_EXCLUDED", False)
    assert cfc.admitted_football_event(past, entity, kickoff)
    monkeypatch.setattr(cfc, "AWARDED_EXCLUDED", True)
    assert not cfc.admitted_football_event(past, entity, kickoff)
    assert cfc.admitted_football_event(_event(1), 11, kickoff + 10**6)


def test_an_install_while_the_switch_is_on_needs_the_flag(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(epochs, "AWARDED_EXCLUDED_FROM_UTC",
                        datetime(2026, 10, 30, tzinfo=UTC))
    eve = datetime(2026, 10, 29, 22, 0, tzinfo=UTC)
    refusals, warnings = pr.replay_switch_gaps(
        _staged(**ON), at=eve, config_dir=_cfg(tmp_path))
    assert refusals == ["AWARDED_EXCLUDED is on, the replay lacks "
                        "--awarded-excluded"]
    assert not any(w.startswith("AWARDED_EXCLUDED") for w in warnings)
    refusals, _ = pr.replay_switch_gaps(
        _staged(**ON, awarded_excluded=True), at=eve, config_dir=_cfg(tmp_path))
    assert refusals == []
    refusals, _ = pr.replay_switch_gaps(
        _staged(**ON), at=eve, config_dir=_cfg(tmp_path),
        allow_missing=["--awarded-excluded"])
    assert refusals == []
    # a day before the switch's eve: nothing asked
    refusals, _ = pr.replay_switch_gaps(
        _staged(**ON), at=datetime(2026, 10, 27, tzinfo=UTC),
        config_dir=_cfg(tmp_path))
    assert refusals == []


def test_the_flag_is_a_replay_rule_key() -> None:
    assert "awarded_excluded" in pr.REPLAY_FLAG_KEYS
    assert not any(n == "AWARDED_EXCLUDED" for n, _, _ in pr.UNREPLAYED_AUDIT_SWITCHES)
