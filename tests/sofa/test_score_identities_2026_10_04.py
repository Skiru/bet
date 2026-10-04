"""A score that contradicts itself is no count (review 2026-10-04).

Both payloads are verbatim from the cache. SETTLE and the cache replay read
extract_metric without check_identities, so the contradiction reached
sofa_settled_row: Buxton - South Shields graded goals_2h_total 0.5 OVER a
loss (incidents: away goals at 7' and 64'), and Shang - Mannarino graded
games_total 19 on a 6-7(9) 2-6 match, flipping eight rows.
"""

from __future__ import annotations

from typing import Any

from bet.sofa.contracts import GapReason
from bet.sofa.metrics import extract_metric, goal_score_inconsistent

FINISHED = {"code": 100, "description": "Ended", "type": "finished"}

BUXTON: dict[str, Any] = {  # 17160371, 2026-10-03
    "id": 17160371, "status": FINISHED,
    "homeScore": {"current": 0, "display": 0, "period1": 0, "period2": 0,
                  "normaltime": 0},
    "awayScore": {"current": 2, "display": 2, "period1": 1, "period2": 0,
                  "normaltime": 1},
}

SHANG_MANNARINO: dict[str, Any] = {  # 17149657, 2026-09-24
    "id": 17149657, "status": FINISHED,
    "homeScore": {"current": 0, "display": 0, "period1": 6, "period2": 2,
                  "period1TieBreak": 9, "point": "15", "normaltime": 0},
    "awayScore": {"current": 2, "display": 2, "period1": 7, "period2": 6,
                  "period1TieBreak": 11, "point": "40", "normaltime": 2},
}
GAMES_WON = {"ALL": {"gamesWon": (8.0, 11.0)}}


def test_an_away_side_score_that_does_not_add_up_is_refused() -> None:
    assert goal_score_inconsistent(BUXTON)
    for metric in ("goals_total", "goals_2h_total", "goals_1h_total"):
        got = extract_metric(metric, "football", {}, None, BUXTON, True)
        assert got == GapReason.INTERNAL_INCONSISTENT, metric
    got = extract_metric("goals_2h_for", "football", {}, None, BUXTON, False)
    assert got == GapReason.INTERNAL_INCONSISTENT


def test_a_consistent_score_still_counts() -> None:
    event = {
        "status": FINISHED,
        "homeScore": {"current": 2, "period1": 1, "period2": 1, "normaltime": 2},
        "awayScore": {"current": 1, "period1": 0, "period2": 1, "normaltime": 1},
    }
    assert not goal_score_inconsistent(event)
    assert extract_metric("goals_total", "football", {}, None, event, True) == 3.0
    assert extract_metric("goals_2h_for", "football", {}, None, event, False) == 1.0


def test_extra_time_reads_normaltime_and_is_not_inconsistent() -> None:
    event = {  # 1-1 at 90, 2-1 after extra time
        "status": {"code": 110, "type": "finished"},
        "homeScore": {"current": 2, "period1": 1, "period2": 0, "normaltime": 1},
        "awayScore": {"current": 1, "period1": 0, "period2": 1, "normaltime": 1},
    }
    assert not goal_score_inconsistent(event)
    assert extract_metric("goals_total", "football", {}, None, event, True) == 2.0


def test_games_come_from_the_set_score_when_games_won_contradicts_it() -> None:
    total = extract_metric("games_total", "tennis", GAMES_WON, None,
                           SHANG_MANNARINO, True)
    assert total == 21.0
    mannarino = extract_metric("games_won_for", "tennis", GAMES_WON, None,
                               SHANG_MANNARINO, False)
    assert mannarino == 13.0


def test_games_won_is_still_read_when_the_sets_are_unreadable() -> None:
    event = {"status": FINISHED, "homeScore": {}, "awayScore": {}}
    got = extract_metric("games_total", "tennis", {"ALL": {"gamesWon": (12.0, 7.0)}},
                         None, event, True)
    assert got == 19.0


def test_the_cache_replay_reads_the_same_counts() -> None:
    # Review round 2: the replay read full-match goals through regulation_score
    # and tennis games from gamesWon, around both fixes above.
    from scripts.sofa.calibrate_from_cache import match_values

    assert "goals" not in match_values(BUXTON, "football", None, None)
    stats = ('{"statistics": [{"period": "ALL", "groups": [{"statisticsItems": '
             '[{"key": "gamesWon", "homeValue": 8, "awayValue": 11}]}]}]}')
    assert match_values(SHANG_MANNARINO, "tennis", stats, None)["games"] == (8.0, 13.0)
    # no /statistics, no games row - the replay's population is unchanged
    assert "games" not in match_values(SHANG_MANNARINO, "tennis", None, None)


def test_the_cache_replay_skips_retirements_and_walkovers(tmp_path: Any) -> None:
    import json
    import sqlite3

    from bet.sofa.db import migrate
    from scripts.sofa.calibrate_from_cache import load_cache

    def event(eid: int, code: int, description: str) -> dict[str, Any]:
        return {
            "id": eid, "startTimestamp": 1_780_000_000 + eid,
            "status": {"type": "finished", "code": code, "description": description},
            "homeTeam": {"id": eid * 10 + 1, "name": "A"},
            "awayTeam": {"id": eid * 10 + 2, "name": "B"},
            "homeScore": {"current": 1, "period1": 1, "period2": 0, "normaltime": 1},
            "awayScore": {"current": 0, "period1": 0, "period2": 0, "normaltime": 0},
            "tournament": {"uniqueTournament": {"id": 17},
                           "category": {"sport": {"slug": "football"}}},
        }

    db = tmp_path / "sofa.db"
    migrate(str(db))
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO sofa_entity_events VALUES (1, 'last', 0, 'x', ?)",
            (json.dumps({"events": [event(1, 100, "Ended"),
                                    event(2, 92, "Retired"),
                                    event(3, 91, "Walkover")]}),))
    assert [p.event_id for p in load_cache(db)] == [1]


def test_tiebreaks_are_counted_off_the_set_score() -> None:
    # 16196102 shape: 3-6 7-6 5-7, the statistic 0/0 in every period.
    event = {"status": FINISHED,
             "homeScore": {"current": 1, "period1": 3, "period2": 7, "period3": 5},
             "awayScore": {"current": 2, "period1": 6, "period2": 6, "period3": 7}}
    zero = {"ALL": {"tiebreaks": (0.0, 0.0)}}
    assert extract_metric("tiebreaks_total", "tennis", zero, None, event, True) == 1.0
    # a match tiebreak (10-8) is no set tiebreak
    mtb = {"status": FINISHED,
           "homeScore": {"current": 2, "period1": 7, "period2": 4, "period3": 10},
           "awayScore": {"current": 1, "period1": 6, "period2": 6, "period3": 8}}
    assert extract_metric("tiebreaks_total", "tennis", zero, None, mtb, True) == 1.0


def test_a_newer_retired_copy_is_not_undercut_by_an_older_ended_one(
    tmp_path: Any,
) -> None:
    import json
    import sqlite3

    from bet.sofa.db import migrate
    from scripts.sofa.calibrate_from_cache import load_cache

    ended = {"id": 7, "startTimestamp": 1_780_000_000,
             "status": {"type": "finished", "code": 100, "description": "Ended"},
             "homeTeam": {"id": 1, "name": "A"}, "awayTeam": {"id": 2, "name": "B"},
             "homeScore": {"current": 1, "normaltime": 1},
             "awayScore": {"current": 0, "normaltime": 0},
             "tournament": {"uniqueTournament": {"id": 17},
                            "category": {"sport": {"slug": "football"}}}}
    retired = {**ended, "status": {"type": "finished", "code": 92,
                                   "description": "Retired"}}
    db = tmp_path / "sofa.db"
    migrate(str(db))
    with sqlite3.connect(db) as conn:
        conn.execute("INSERT INTO sofa_entity_events VALUES "
                     "(1, 'last', 0, '2026-10-01T00:00:00Z', ?)",
                     (json.dumps({"events": [ended]}),))
        conn.execute(  # the index's copy, fetched later: the newest wins
            "INSERT INTO sofa_listed_event VALUES (7, 'football', 1780000000, "
            "'2026-10-03T00:00:00Z', ?)", (json.dumps(retired),))
    assert load_cache(db) == []


def test_coverage_canceled_is_no_completed_match() -> None:
    from bet.sofa.settle import is_completed_event

    assert not is_completed_event({"status": {
        "type": "finished", "code": 100, "description": "Coverage canceled"}})
    assert is_completed_event({"status": {
        "type": "finished", "code": 100, "description": "Ended"}})


def test_a_tennis_exhibition_settles_no_replay_row() -> None:
    from scripts.sofa import calibrate_from_cache as cfc

    def played(eid: int, kind: str) -> Any:
        return cfc.Played(event_id=eid, timestamp=eid, home_id=1, away_id=2,
                          sport="tennis", competition_id=5,
                          values={"aces": (5.0, 4.0)}, kind=kind)

    history = [played(i, "REGULAR") for i in range(10)]
    rows = list(cfc.iter_rows([*history, played(50, "FRIENDLY")], {}))
    assert rows and not any(r.event_id == 50 for r in rows)
