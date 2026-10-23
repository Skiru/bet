"""P3 / K7 football (epochs.PLAYER_HISTORY_ANY_TEAM_FROM_UTC), review R2 #1 /
#2 / #8: the peers' matches an any-team top-up reads go through the sample
proper's acceptance (samples.peer_history: one listing per match, one squad
per id, the switch-only friendlies), a match between two peers is a row for
each of them, and the statistics row is read with the kick-off (a
provisional row is none) - as the sample proper reads it."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from bet.sofa import samples
from bet.sofa.contracts import Fixture
from bet.sofa.players import PLAYER_ID_KEY
from bet.sofa.samples import _foreign_side_results, peer_history

PID = 863001
T0 = 1_780_000_000
DAY = 86400


def event(eid: int, start: int, home: int, away: int, *, comp: int = 17,
          score: tuple[int, int] = (1, 0)) -> dict[str, Any]:
    return {
        "id": eid, "startTimestamp": start,
        "homeTeam": {"id": home, "name": f"T{home}"},
        "awayTeam": {"id": away, "name": f"T{away}"},
        "homeScore": {"current": score[0]}, "awayScore": {"current": score[1]},
        "status": {"type": "finished", "code": 100},
        "tournament": {"uniqueTournament": {"id": comp}},
    }


def lineups(home_pid: int | None, away_pid: int | None) -> dict[str, Any]:
    def side(pid: int | None) -> dict[str, Any]:
        if pid is None:
            return {"players": [{"player": {"name": "Somebody", "id": 1},
                                 "substitute": False,
                                 "statistics": {"minutesPlayed": 90}}]}
        return {"players": [{"player": {"name": "Zian Flemming", "id": pid},
                             "substitute": False,
                             "statistics": {"minutesPlayed": 90,
                                            "totalShots": 4}}]}
    return {"home": side(home_pid), "away": side(away_pid)}


def fixture() -> Fixture:
    return Fixture(
        sofascore_event_id=1, superbet_event_ids=["1"], sport="football",
        kickoff_utc=datetime.fromtimestamp(T0, UTC),
        home_name="Ipswich", away_name="X", home_entity_id=7, away_entity_id=8,
        competition_name="C", competition_id=17, season_id=1, category_name="X",
        identity="CONFIRMED", round_number=None, round_name=None,
        cup_round_type=None, previous_leg_event_id=None, venue_name=None,
        referee=None, ground_type=None, default_period_count=None,
    )


def base(*peers: int) -> dict[str, list[dict[str, Any]]]:
    return {"side_a": [{"event_id": 100 + i, "opponent_id": p}
                       for i, p in enumerate(peers)], "side_b": []}


class Cache:
    def __init__(self, listed: dict[int, list[dict[str, Any]]],
                 lineups: dict[int, dict[str, Any]]) -> None:
        self.listed, self.lineups = listed, lineups
        self.stats_calls: list[tuple[int, int | None]] = []

    def get_listed_events(self, entity: int, *_: Any) -> list[dict[str, Any]]:
        return self.listed.get(entity, [])

    def get_event_lineups(self, eid: int) -> dict[str, Any] | None:
        return self.lineups.get(eid)

    def get_event_stats(self, eid: int, kickoff_ts: int | None = None) -> None:
        self.stats_calls.append((eid, kickoff_ts))
        return None


def run(cache: Cache, *peers: int, conflict_cut: bool = False
        ) -> list[dict[str, Any]]:
    out = _foreign_side_results(cache, fixture(), base(*peers),  # type: ignore[arg-type]
                                conflict_cut=conflict_cut)
    return out["side_a"]


def test_a_match_between_two_peers_is_a_row_for_each() -> None:
    # 55 v 56: he played for 56 (away). Before the fix the match was taken
    # once, under 55 (the first peer), with 55's lineup side - his start lost.
    meet = event(400, T0 - 30 * DAY, 55, 56)
    cache = Cache({55: [meet], 56: [meet]}, {400: lineups(None, PID)})
    rows = run(cache, 55, 56)
    assert [(r["event_id"], r["venue"]) for r in rows] == [(400, "home"),
                                                            (400, "away")]
    away = rows[1]["squad"]
    assert away["zian flemming"][PLAYER_ID_KEY] == PID


def test_a_match_listed_twice_under_two_ids_enters_once() -> None:
    a = event(401, T0 - 30 * DAY, 55, 60)
    b = event(402, T0 - 30 * DAY, 55, 60)
    cache = Cache({55: [a, b]}, {401: lineups(PID, None), 402: lineups(PID, None)})
    assert [r["event_id"] for r in run(cache, 55)] == [401]


def test_a_peer_id_carrying_two_squads_is_left_out() -> None:
    # two matches 5 h apart against different opponents: one id, two squads
    a = event(403, T0 - 30 * DAY, 55, 60)
    b = event(404, T0 - 30 * DAY + 5 * 3600, 55, 61)
    cache = Cache({55: [a, b]}, {403: lineups(PID, None), 404: lineups(PID, None)})
    assert run(cache, 55) == []


def test_the_switch_only_friendlies_are_out(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(samples, "CONFLICT_CUT_FRIENDLY_IDS", frozenset({38292}))
    friendly = event(405, T0 - 30 * DAY, 55, 60, comp=38292)
    cache = Cache({55: [friendly]}, {405: lineups(PID, None)})
    assert run(cache, 55, conflict_cut=True) == []
    # without the switch the list is not read (the sample proper's rule)
    assert [r["event_id"] for r in run(cache, 55, conflict_cut=False)] == [405]


def test_peer_history_admits_as_the_sample_does() -> None:
    later = event(406, T0 + DAY, 55, 60)          # after kick-off
    other = event(407, T0 - 10 * DAY, 60, 61)     # the peer is not a side
    walkover = {**event(408, T0 - 12 * DAY, 55, 60),
                "status": {"type": "finished", "code": 92}}
    kept = event(409, T0 - 14 * DAY, 55, 60)
    got = peer_history([later, other, walkover, kept], 55, T0, conflict_cut=False)
    assert [e["id"] for e in got] == [409]


def test_statistics_are_read_with_the_kick_off() -> None:
    meet = event(410, T0 - 30 * DAY, 55, 60)
    cache = Cache({55: [meet]}, {410: lineups(PID, None)})
    run(cache, 55)
    assert cache.stats_calls == [(410, T0 - 30 * DAY)]
