"""A player sample is his starts (epochs.PLAYER_STARTS_ONLY_FROM_UTC).

Superbet voids a footballer's player market unless he starts (operator,
2026-10-11), so the bet is "given that he starts": SAMPLES keeps his starts
only, SHEET says so on the row, and the history replay the curves are fitted
on settles starters only, from their starts (`--player-starts-only`).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from bet.sofa import epochs
from bet.sofa.contracts import FixtureOffer
from bet.sofa.players import squad_statistics
from bet.sofa.samples import build_player_samples
from scripts.sofa import calibrate_from_cache as cfc
from tests.sofa.test_player_markets import (
    _fixture,
    _player_samples,
    _result,
    _rung,
    _sheet,
)

WANT = {"player_shots_for": {"Kowalski, Jan"}}
KEY = "player_shots_for|Kowalski, Jan"


def _squad(shots: float, substitute: bool) -> dict[str, dict[str, Any]]:
    squad = squad_statistics({"home": {"players": [
        {"player": {"name": "Jan Kowalski"}, "substitute": substitute,
         "statistics": {"minutesPlayed": 20 if substitute else 90,
                        "totalShots": shots}},
    ]}}, is_home=True)
    assert squad is not None
    return squad


# 5 starts (3, 2, 4, 3, 2 shots) and 2 cameos off the bench (0, 0)
HISTORY = [(3, False), (0, True), (2, False), (4, False), (0, True), (3, False),
           (2, False)]


def _sides() -> dict[str, list[dict[str, Any]]]:
    return {"side_a": [_result(i + 1, _squad(s, sub))
                       for i, (s, sub) in enumerate(HISTORY)],
            "side_b": []}


def test_off_the_sample_is_every_appearance() -> None:
    sample = build_player_samples(WANT, _sides(), [])[KEY]
    assert sorted(o.value for o in sample.observations) == [0, 0, 2, 2, 3, 3, 4]
    assert sample.appearances == "all"


def test_on_the_sample_is_his_starts() -> None:
    sample = build_player_samples(WANT, _sides(), [], starts_only=True)[KEY]
    assert sorted(o.value for o in sample.observations) == [2, 2, 3, 3, 4]
    assert sample.appearances == "starts"
    # The denominator is still the side's squads: he started 5 of 7.
    assert sample.squad_matches == 7


def test_a_player_who_only_came_off_the_bench_has_no_sample() -> None:
    sides = {"side_a": [_result(1, _squad(1, True)), _result(2, _squad(2, True))],
             "side_b": []}
    gaps: list[Any] = []
    assert build_player_samples(WANT, sides, gaps, starts_only=True) == {}
    assert [g.detail for g in gaps] == [
        "player 'Kowalski, Jan' named in 2 squads, never started"]


def test_the_sheet_row_says_the_sample_is_his_starts() -> None:
    samples = _player_samples([3, 2, 4, 1, 3, 2, 5, 2, 3, 2])
    sample = samples.players["player_shots_for|Romarinho"]
    samples.players["player_shots_for|Romarinho"] = sample.model_copy(
        update={"appearances": "starts"})
    offer = FixtureOffer(
        sofascore_event_id=1, status="PRICED",
        rungs=[_rung("player_shots_for", "Romarinho", 1.5, over=2.6)],
        unmapped_markets=[])
    rows = _sheet(_fixture(), samples, offer)
    assert any(n.startswith("PLAYER_STARTS_ONLY") for n in rows[0].notes)
    plain = _sheet(_fixture(), _player_samples([3, 2, 4, 1, 3, 2, 5, 2, 3, 2]), offer)
    assert not any(n.startswith("PLAYER_STARTS_ONLY") for n in plain[0].notes)


def test_the_switch_judges_the_day_and_the_build_clock(monkeypatch: Any) -> None:
    at = datetime(2026, 10, 12, 0, 0, tzinfo=UTC)
    monkeypatch.setattr(epochs, "PLAYER_STARTS_ONLY_FROM_UTC", at)
    assert epochs.player_starts_only("2026-10-12", at)
    assert not epochs.player_starts_only("2026-10-11", at)
    assert not epochs.player_starts_only(
        "2026-10-12", datetime(2026, 10, 11, 23, 0, tzinfo=UTC))
    monkeypatch.setattr(epochs, "PLAYER_STARTS_ONLY_FROM_UTC", None)
    assert not epochs.player_starts_only("2099-01-01", at)


# --- the history replay ----------------------------------------------------


def _replay(target_sub: bool, **flags: bool) -> list[cfc.SettledRow]:
    target = {True: _squad(3, target_sub), False: None}
    history = {True: [_squad(s, sub) for s, sub in HISTORY], False: []}
    event = {"id": 999, "tournament": {"uniqueTournament": {"id": 17}}}
    return cfc.player_rows_for_event(
        event, target, history, {"player_shots_for": [1.5]}, 5, **flags)


def test_the_replay_settles_a_bench_appearance_unless_told_not_to() -> None:
    assert _replay(target_sub=True)  # the old replay: every appearance
    assert _replay(target_sub=True, starters_only=True) == []


def test_the_replay_samples_his_starts() -> None:
    every = _replay(target_sub=False)
    starts = _replay(target_sub=False, starters_only=True, starts_only=True)
    assert {r.sample_size for r in every} == {7}
    assert {r.sample_size for r in starts} == {5}
    assert {r.sample_mean for r in starts} == {2.8}


# --- the staged calibration --------------------------------------------------


def test_the_starts_switch_starts_the_next_day() -> None:
    start = datetime(2026, 10, 12, 0, 0, tzinfo=UTC)
    assert epochs.PLAYER_STARTS_ONLY_FROM_UTC == start


def test_a_staged_calibration_is_read_from_its_start(tmp_path: Any) -> None:
    import json

    from bet.sofa.confidence import calibration_path_for

    main = tmp_path / "sofa_confidence_calibration.json"
    main.write_text("{}")
    assert calibration_path_for("2026-10-12", None, main) == main
    nxt = tmp_path / "sofa_confidence_calibration.next.json"
    nxt.write_text(json.dumps({"effective_from": "2026-10-12T00:00:00Z"}))
    at = datetime(2026, 10, 12, 0, 0, tzinfo=UTC)
    assert calibration_path_for("2026-10-12", at, main) == nxt
    # A day already built, or a build before the moment, keeps the installed.
    assert calibration_path_for("2026-10-11", at, main) == main
    assert calibration_path_for(
        "2026-10-12", datetime(2026, 10, 11, 23, 0, tzinfo=UTC), main) == main


def test_the_staged_file_changes_only_the_player_curves() -> None:
    """config/sofa_confidence_calibration.next.json (refit 2026-10-11): the
    team, tennis and pooled curves are the installed file's byte for byte;
    only player keys move. Vacuous once the staged file has been promoted."""
    import copy
    import json

    from bet.sofa.config import config_path

    nxt_path = config_path("sofa_confidence_calibration.next.json")
    if not nxt_path.exists():
        return
    main = json.loads(config_path("sofa_confidence_calibration.json").read_text())
    nxt = json.loads(nxt_path.read_text())

    def strip(doc: dict[str, Any]) -> dict[str, Any]:
        doc = copy.deepcopy(doc)
        for sec in ("by_market", "by_market_direction", "thin_by_market_direction"):
            for key in [k for k in doc.get(sec, {}) if k.startswith("player_")]:
                del doc[sec][key]
        for key in ("effective_from", "player_curves_fitted_from"):
            doc.pop(key, None)
        return doc

    assert strip(nxt) == strip(main)
    datetime.fromisoformat(nxt["effective_from"].replace("Z", "+00:00"))
    assert nxt["by_market_direction"]["player_shots_for|OVER"]
