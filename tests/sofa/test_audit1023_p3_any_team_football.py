"""P3 / K7 of the coverage audit 2026-10-23 (B1), football: a footballer's
starts for another team, found by his Sofascore player id
(epochs.PLAYER_HISTORY_ANY_TEAM_FROM_UTC).

Zian Flemming (10-23): n=1 for Ipswich while his starts for Burnley sat in
the cache unread. Off: his thin sample stays thin. On: a sample still under
min_sample after the wide window is topped up with his starts in the cached
squads of his side's peers (opponents in its sampled matches), matched by
id - never by name.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from bet.sofa.contracts import Fixture, GapEntry
from bet.sofa.players import PLAYER_ID_KEY, squad_statistics
from bet.sofa.samples import (
    ANY_TEAM_NOTE,
    _foreign_side_results,
    coverage_player_samples,
)

PID = 863001
T0 = 1_780_000_000


def squad(name: str, pid: int, shots: int, start: bool = True) -> dict[str, Any]:
    return {name: {"minutesPlayed": 90, "totalShots": shots,
                   "_started": start, PLAYER_ID_KEY: pid}}


def res(eid: int, day: int, sq: dict[str, Any], opp: int = 0) -> dict[str, Any]:
    return {"event_id": eid, "squad": sq,
            "match_date_utc": datetime(2026, 10, day, tzinfo=UTC),
            "opponent": "X", "competition_id": 35, "season_id": 1,
            "venue": "home", "opponent_id": opp}


def base() -> dict[str, list[dict[str, Any]]]:
    # two starts for his new side; the other matches name nobody like him
    own = [res(100, 20, squad("zian flemming", PID, 1), opp=55),
           res(101, 13, squad("zian flemming", PID, 2), opp=56)]
    own += [res(102 + i, 1 + i, squad("someone else", 1, 0)) for i in range(5)]
    return {"side_a": own, "side_b": []}


def foreign(pid: int = PID) -> dict[str, list[dict[str, Any]]]:
    return {"side_a": [res(200 + i, 1 + i, squad("z. flemming", pid, 3))
                       for i in range(6)], "side_b": []}


def run(foreign_results: Any) -> tuple[dict[str, Any], list[GapEntry]]:
    gaps: list[GapEntry] = []
    got = coverage_player_samples(
        {"player_shots_for": {"Zian Flemming"}}, base(), base, gaps,
        min_sample=5, sample_n=10, starts_only=True,
        foreign_results=foreign_results)
    return got, gaps


def test_off_the_thin_sample_stays_thin() -> None:
    got, gaps = run(None)
    (sample,) = got.values()
    assert len(sample.observations) == 2
    assert not any(ANY_TEAM_NOTE in g.detail for g in gaps)


def test_on_his_starts_for_another_team_top_it_up() -> None:
    got, gaps = run(foreign)
    (sample,) = got.values()
    assert len(sample.observations) == 8
    assert sorted(o.value for o in sample.observations) == [1, 2] + [3] * 6
    assert any(ANY_TEAM_NOTE in g.detail and "topped up with 6" in g.detail
               for g in gaps)


def test_on_another_players_id_is_never_read() -> None:
    got, _ = run(lambda: foreign(pid=999))
    (sample,) = got.values()
    assert len(sample.observations) == 2


def test_on_a_full_sample_never_reads_other_teams() -> None:
    def boom() -> dict[str, list[dict[str, Any]]]:
        raise AssertionError("not needed")

    gaps: list[GapEntry] = []
    full = {"side_a": [res(300 + i, 1 + i, squad("zian flemming", PID, 1))
                       for i in range(6)], "side_b": []}
    got = coverage_player_samples(
        {"player_shots_for": {"Zian Flemming"}}, full, lambda: full, gaps,
        min_sample=5, sample_n=10, foreign_results=boom)
    assert len(next(iter(got.values())).observations) == 6


def test_squad_statistics_records_the_id_only_on_request() -> None:
    lineups = {"home": {"players": [{"player": {"name": "Zian Flemming",
                                                "id": PID},
                                     "statistics": {"minutesPlayed": 90}}]}}
    off = squad_statistics(lineups, is_home=True)
    on = squad_statistics(lineups, is_home=True, player_id=True)
    assert off is not None and on is not None
    assert PLAYER_ID_KEY not in off["zian flemming"]
    assert on["zian flemming"][PLAYER_ID_KEY] == PID


def test_foreign_results_read_peers_from_the_cache_only() -> None:
    peer_event = {
        "id": 400, "startTimestamp": T0 - 86400 * 30,
        "homeTeam": {"id": 55, "name": "Burnley"},
        "awayTeam": {"id": 60, "name": "Leeds"},
        "homeScore": {"current": 1}, "awayScore": {"current": 0},
        "status": {"type": "finished", "code": 100},
        "tournament": {"uniqueTournament": {"id": 17}},
    }
    lineups = {"home": {"players": [{"player": {"name": "Zian Flemming",
                                                "id": PID},
                                     "substitute": False,
                                     "statistics": {"minutesPlayed": 90,
                                                    "totalShots": 4}}]},
               "away": {"players": []}}

    class Cache:
        def get_listed_events(self, entity: int, *_: Any) -> list[dict[str, Any]]:
            return [peer_event] if entity == 55 else []

        def get_event_lineups(self, eid: int) -> dict[str, Any] | None:
            return lineups if eid == 400 else None

        def get_event_stats(self, eid: int) -> None:
            return None

    fixture = Fixture(
        sofascore_event_id=1, superbet_event_ids=["1"], sport="football",
        kickoff_utc=datetime.fromtimestamp(T0, UTC),
        home_name="Ipswich", away_name="X", home_entity_id=7, away_entity_id=8,
        competition_name="C", competition_id=17, season_id=1, category_name="X",
        identity="CONFIRMED", round_number=None, round_name=None,
        cup_round_type=None, previous_leg_event_id=None, venue_name=None,
        referee=None, ground_type=None, default_period_count=None,
    )
    out = _foreign_side_results(Cache(), fixture, base())  # type: ignore[arg-type]
    (row,) = out["side_a"]
    assert row["event_id"] == 400 and row["venue"] == "home"
    assert row["squad"]["zian flemming"][PLAYER_ID_KEY] == PID
    assert out["side_b"] == []


def test_the_player_switches_by_day_and_build_clock(monkeypatch: Any) -> None:
    from bet.sofa import epochs, timeutil
    from bet.sofa.samples import player_switches

    def fx(sport: str) -> Fixture:
        return Fixture(
            sofascore_event_id=1, superbet_event_ids=["1"], sport=sport,  # type: ignore[arg-type]
            kickoff_utc=datetime(2026, 10, 24, 15, tzinfo=UTC),
            home_name="A", away_name="B", home_entity_id=7, away_entity_id=8,
            competition_name="C", competition_id=17, season_id=1,
            category_name="X", identity="CONFIRMED", round_number=None,
            round_name=None, cup_round_type=None, previous_leg_event_id=None,
            venue_name=None, referee=None, ground_type=None,
            default_period_count=None)

    on = datetime(2026, 10, 24, tzinfo=UTC)
    for name in ("PLAYER_OMITTED_ZERO_FROM_UTC", "PLAYER_SLUG_NAME_FROM_UTC",
                 "PLAYER_HISTORY_ANY_TEAM_FROM_UTC"):
        monkeypatch.setattr(epochs, name, None)
    monkeypatch.setattr(timeutil, "now", lambda: on)
    assert player_switches(fx("football")) == {
        "omitted_zero": False, "slug_name": False, "player_id": False}
    for name in ("PLAYER_OMITTED_ZERO_FROM_UTC", "PLAYER_SLUG_NAME_FROM_UTC",
                 "PLAYER_HISTORY_ANY_TEAM_FROM_UTC"):
        monkeypatch.setattr(epochs, name, on)
    # the any-team switch is per sport (epochs.PLAYER_HISTORY_ANY_TEAM_SPORTS)
    monkeypatch.setattr(epochs, "PLAYER_HISTORY_ANY_TEAM_SPORTS",
                        frozenset({"hockey"}))
    assert player_switches(fx("football"))["player_id"] is False
    monkeypatch.setattr(epochs, "PLAYER_HISTORY_ANY_TEAM_SPORTS",
                        frozenset({"hockey", "football"}))
    assert all(player_switches(fx("football")).values())
    assert not any(player_switches(fx("tennis")).values())
    monkeypatch.setattr(timeutil, "now", lambda: datetime(2026, 10, 23, tzinfo=UTC))
    assert not any(player_switches(fx("football")).values())
