"""P14 (coverage audit 2026-10-23, B14): the tennis rating takes the winner of
an "Ended" match from its set score when Sofascore's winnerCode is absent, and
reads a non-team type-0 side as a player (epochs.TENNIS_RATING_SCORE_WINNER).

Event 17362029 (ITF M15 Ithaca, Arseneault - Markovic 6-0 6-1, winnerCode
null) was dropped from the rating; with the switch it enters it. Off, the
parser is the old one exactly. A retired / walked-over match never takes a
winner from its score, and a team tie (Davis Cup nations, type 0 national)
stays out.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import epochs, tennis_rating
from bet.sofa.db import migrate
from bet.sofa.tennis_rating import load_history, parse_event, winner_from_sets


def _ithaca(**over: Any) -> dict[str, Any]:
    """The cached listing copy of 17362029, trimmed to what the parser reads."""
    base: dict[str, Any] = {
        "id": 17362029, "startTimestamp": 1792418400,
        "groundType": "Hardcourt indoor", "winnerCode": None,
        "homeScore": {"current": 2, "display": 2, "period1": 6, "period2": 6},
        "awayScore": {"current": 0, "display": 0, "period1": 0, "period2": 1},
        "time": {},
        "status": {"code": 100, "description": "Ended", "type": "finished"},
        "tournament": {"name": "ITF M15 Ithaca, NY Men",
                       "category": {"name": "ITF Men",
                                    "sport": {"slug": "tennis"}}},
        "homeTeam": {"id": 457262, "name": "Nicolas Arseneault", "type": 1,
                     "gender": "M", "national": False},
        "awayTeam": {"id": 217472, "name": "Lazar Markovic", "type": 1,
                     "gender": "M", "national": False},
    }
    base.update(over)
    return base


def test_17362029_enters_the_rating_only_with_the_switch() -> None:
    assert parse_event(_ithaca()) is None  # off: as before
    r = parse_event(_ithaca(), score_winner=True)
    assert r is not None
    assert r.event_id == 17362029 and r.home_won and r.completed
    assert r.sets == ((6, 0), (6, 1)) and r.tier == "ITF"


def test_an_away_win_and_a_match_tiebreak_are_read_from_the_sets() -> None:
    ev = _ithaca(homeScore={"period1": 6, "period2": 3, "period3": 8},
                 awayScore={"period1": 4, "period2": 6, "period3": 10})
    r = parse_event(ev, score_winner=True)
    assert r is not None and not r.home_won
    assert r.sets == ((6, 4), (3, 6), (0, 1))


def test_a_retired_or_walked_over_match_never_takes_a_winner_from_its_score() -> None:
    for description in ("Retired", "Walkover", "Defaulted"):
        ev = _ithaca(status={"type": "finished", "description": description})
        assert parse_event(ev, score_winner=True) is None
        assert parse_event(ev) is None


def test_winner_code_3_is_not_absent_and_stays_out() -> None:
    assert parse_event(_ithaca(winnerCode=3), score_winner=True) is None


def test_an_unfinished_or_contradictory_score_names_no_winner() -> None:
    # one set only; 1-1; an unfinished second set; last set to the loser;
    # Sofascore's own set count disagreeing; no score at all
    assert winner_from_sets({"period1": 6}, {"period1": 2}) is None
    assert winner_from_sets({"period1": 6, "period2": 3},
                            {"period1": 2, "period2": 6}) is None
    assert winner_from_sets({"period1": 6, "period2": 4},
                            {"period1": 2, "period2": 3}) is None
    assert winner_from_sets({"period1": 6, "period2": 6, "period3": 2},
                            {"period1": 2, "period2": 3, "period3": 6}) is None
    assert winner_from_sets({"current": 1, "period1": 6, "period2": 6},
                            {"current": 1, "period1": 2, "period2": 3}) is None
    assert winner_from_sets({}, {}) is None
    assert parse_event(_ithaca(homeScore={}, awayScore={}),
                       score_winner=True) is None


def test_best_of_five_three_sets_to_two() -> None:
    hs = {"period1": 6, "period2": 4, "period3": 7, "period4": 3, "period5": 6}
    as_ = {"period1": 3, "period2": 6, "period3": 6, "period4": 6, "period5": 4}
    assert winner_from_sets(hs, as_) == 1


def test_a_type_0_player_is_a_player_only_with_the_switch() -> None:
    ev = _ithaca(winnerCode=2,
                 homeScore={"period1": 3, "period2": 4},
                 awayScore={"period1": 6, "period2": 6},
                 homeTeam={"id": 5, "name": "Sammy Guinau", "type": 0,
                           "gender": "M", "national": False, "subTeams": []})
    assert parse_event(ev) is None
    r = parse_event(ev, score_winner=True)
    assert r is not None and r.home_id == 5 and not r.home_won


@pytest.mark.parametrize("team", [
    {"id": 5, "name": "Russia", "type": 0, "national": True},
    {"id": 5, "name": "Arnautovic L / Freeman P", "type": 0},
    {"id": 5, "name": "Team", "type": 0, "subTeams": [{"id": 9}]},
    {"id": 5, "name": "Pair", "type": 2},
])
def test_a_team_tie_or_a_pair_stays_out(team: dict[str, Any]) -> None:
    ev = _ithaca(winnerCode=1, homeTeam=team)
    assert parse_event(ev, score_winner=True) is None
    assert parse_event(ev) is None


def test_with_a_winner_code_the_switch_changes_nothing() -> None:
    ev = _ithaca(winnerCode=1)
    assert parse_event(ev) == parse_event(ev, score_winner=True)


def test_load_history_passes_the_rule(tmp_path: Path) -> None:
    db = str(tmp_path / "sofa.db")
    migrate(db)
    con = sqlite3.connect(db)
    con.execute(
        "INSERT INTO sofa_entity_events VALUES (?, 'last', 0, ?, ?)",
        (457262, "2026-10-20T00:00:00+00:00",
         json.dumps({"events": [_ithaca(), _ithaca(id=1, winnerCode=1)]})))
    con.commit()
    con.close()
    assert [r.event_id for r in load_history(db)] == [1]
    # same start: time order breaks the tie by event id
    assert [r.event_id for r in load_history(db, score_winner=True)] == [
        1, 17362029]


def test_load_history_off_keeps_the_one_argument_parse_call(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    # scripts/sofa/measure_tennis_outcome_model wraps parse_event with a
    # one-argument function; off, load_history must still call it so.
    db = str(tmp_path / "sofa.db")
    migrate(db)
    con = sqlite3.connect(db)
    con.execute(
        "INSERT INTO sofa_entity_events VALUES (?, 'last', 0, ?, ?)",
        (457262, "2026-10-20T00:00:00+00:00",
         json.dumps({"events": [_ithaca(id=1, winnerCode=1)]})))
    con.commit()
    con.close()
    original = tennis_rating.parse_event
    seen: list[int] = []

    def capture(event: dict[str, Any]) -> tennis_rating.TennisResult | None:
        seen.append(int(event["id"]))
        return original(event)

    monkeypatch.setattr(tennis_rating, "parse_event", capture)
    assert [r.event_id for r in load_history(db)] == [1]
    assert seen == [1]


def test_the_switch_reads_the_day_and_the_build_clock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    on = datetime(2026, 10, 24, 0, 0, 0, tzinfo=UTC)
    monkeypatch.setattr(epochs, "TENNIS_RATING_SCORE_WINNER_FROM_UTC", on)
    assert epochs.tennis_rating_score_winner("2026-10-24", on)
    assert not epochs.tennis_rating_score_winner(
        "2026-10-23", datetime(2026, 10, 24, 1, tzinfo=UTC))
    assert not epochs.tennis_rating_score_winner(
        "2026-10-24", datetime(2026, 10, 23, 23, tzinfo=UTC))
    monkeypatch.setattr(epochs, "TENNIS_RATING_SCORE_WINNER_FROM_UTC", None)
    assert not epochs.tennis_rating_score_winner("2026-10-30", on)
