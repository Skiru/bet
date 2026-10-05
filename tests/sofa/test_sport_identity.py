"""bet.sofa.sport_identity / scripts/sofa/run_sport_identity.py - the
pre-match Sofascore identity of the measured sports (plan 2026-10-05, F1, C5).
Offline: a fake listing client, never the bridge."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import sport_identity as si
from bet.sofa.errors import ProviderError

AT = datetime(2026, 10, 6, 8, 0, tzinfo=UTC)
KICK = datetime(2026, 10, 6, 18, 0, tzinfo=UTC)


def _ev(sb: str, t1: str, t2: str, kick: datetime = KICK, sport: str = "hockey"
        ) -> si.BoardEvent:
    return si.BoardEvent(sport, sb, f"{t1}·{t2}", t1, t2,
                         kick.isoformat().replace("+00:00", "Z"), "Liga", "2026-10-06")


def _listed(eid: int, home: tuple[int, str], away: tuple[int, str],
            start: datetime = KICK, slug: str = "ice-hockey",
            category: str | None = None) -> dict[str, Any]:
    cat: dict[str, Any] = {"sport": {"slug": slug}}
    if category:
        cat["name"] = category
    return {"id": eid, "startTimestamp": int(start.timestamp()),
            "tournament": {"id": 7, "name": "Extraliga",
                           "uniqueTournament": {"id": 55, "name": "Extraliga"},
                           "category": cat},
            "homeTeam": {"id": home[0], "name": home[1], "gender": "M"},
            "awayTeam": {"id": away[0], "name": away[1], "gender": "M"}}


class FakeClient:
    def __init__(self, listings: dict[int, list[dict[str, Any]]],
                 refuse: set[int] | None = None) -> None:
        self.listings = listings
        self.refuse = refuse or set()
        self.calls: list[int] = []

    def entity_events(self, entity_id: int, kind: Any, page: int) -> Any | None:
        assert kind == "next" and page == 0
        self.calls.append(entity_id)
        if entity_id in self.refuse:
            raise ProviderError("HTTP 403")
        if entity_id not in self.listings:
            return None
        return {"events": self.listings[entity_id]}


class FakeCache:
    def __init__(self) -> None:
        self.saved: dict[int, dict[str, Any]] = {}

    def get_entity_events(self, sofascore_entity_id: int, kind: str, page: int
                          ) -> dict[str, Any] | None:
        return self.saved.get(sofascore_entity_id)

    def save_entity_events(self, sofascore_entity_id: int, kind: str, page: int,
                           events: dict[str, Any]) -> None:
        self.saved[sofascore_entity_id] = events


TEAMS = {"Sparta Praha": 10, "Kometa Brno": 20, "Ocelari Trinec": 30,
         "Dynamo Pardubice": 40}


def _teams(sport: str, name: str) -> int | None:
    return TEAMS.get(name)


def test_a_game_is_identified_with_both_names_and_its_orientation():
    client = FakeClient({10: [_listed(9001, (20, "HC Kometa Brno"),
                                      (10, "HC Sparta Praha"),
                                      KICK + timedelta(minutes=20))]})
    recs, summary = si.identify([_ev("1", "Sparta Praha", "Kometa Brno")], client,
                                None, _teams, AT, "2026-10-06")
    (r,) = recs
    assert r["status"] == si.IDENTIFIED
    assert r["sofascore_event_id"] == 9001
    assert r["home_is_team1"] is False  # Sofascore's home is Superbet's team2
    assert (r["home_id"], r["away_id"]) == (20, 10)
    assert r["competition_id"] == 55
    assert r["start_gap_h"] == pytest.approx(0.33, abs=0.01)
    assert set(r["name_scores"]) == {"team1", "team2"}
    assert r["match_method"] == "LISTING_ID_AND_NAME"
    assert r["matched_at_utc"] == "2026-10-06T08:00:00Z"
    assert summary["sports"]["hockey"]["identified"] == 1
    assert client.calls == [10]


def test_the_other_team_must_be_named_in_the_listing():
    client = FakeClient({10: [_listed(9001, (10, "Sparta Praha"),
                                      (77, "Bili Tygri Liberec"))]})
    (r,), _ = si.identify([_ev("1", "Sparta Praha", "Kometa Brno")], client, None,
                          _teams, AT, "2026-10-06")
    assert r["status"] == si.NOT_IDENTIFIED and r["reason"] == "NO_MATCH_IN_LISTING"


def test_a_start_more_than_an_hour_off_is_not_this_game():
    client = FakeClient({10: [_listed(9001, (10, "Sparta Praha"),
                                      (20, "Kometa Brno"), KICK + timedelta(hours=2))]})
    (r,), _ = si.identify([_ev("1", "Sparta Praha", "Kometa Brno")], client, None,
                          _teams, AT, "2026-10-06")
    assert r["status"] == si.NOT_IDENTIFIED and r["reason"] == "NO_GAME_WITHIN_1H"


def test_another_sport_in_the_listing_is_ignored():
    client = FakeClient({10: [_listed(9001, (10, "Sparta Praha"),
                                      (20, "Kometa Brno"), slug="football")]})
    (r,), _ = si.identify([_ev("1", "Sparta Praha", "Kometa Brno")], client, None,
                          _teams, AT, "2026-10-06")
    assert r["status"] == si.NOT_IDENTIFIED


def test_two_fitting_events_are_ambiguous():
    client = FakeClient({10: [
        _listed(9001, (10, "Sparta Praha"), (20, "Kometa Brno")),
        _listed(9002, (10, "Sparta Praha"), (20, "Kometa Brno"),
                KICK + timedelta(minutes=30))]})
    (r,), _ = si.identify([_ev("1", "Sparta Praha", "Kometa Brno")], client, None,
                          _teams, AT, "2026-10-06")
    assert r["reason"] == "AMBIGUOUS"


def test_no_team_id_means_no_request():
    client = FakeClient({})
    (r,), _ = si.identify([_ev("1", "Nobody", "Nowhere")], client, None, _teams, AT,
                          "2026-10-06")
    assert r["reason"] == "TEAM_UNRESOLVED" and client.calls == []


def test_team2_is_asked_when_team1_has_no_id():
    client = FakeClient({20: [_listed(9001, (99, "Unknown Side"),
                                      (20, "Kometa Brno"))]})
    (r,), _ = si.identify([_ev("1", "Unknown Side", "Kometa Brno")], client, None,
                          _teams, AT, "2026-10-06")
    assert client.calls == [20]
    assert r["status"] == si.IDENTIFIED and r["home_is_team1"] is True


def test_c5_a_team_in_two_events_under_three_hours_apart_is_out():
    events = [_ev("1", "Vitality Academy", "Kometa Brno"),
              _ev("2", "Vitality Academy", "Sparta Praha", KICK + timedelta(hours=2)),
              _ev("3", "Ocelari Trinec", "Dynamo Pardubice")]
    client = FakeClient({30: [_listed(9003, (30, "Ocelari Trinec"),
                                      (40, "Dynamo Pardubice"))]})
    recs, summary = si.identify(events, client, None, _teams, AT, "2026-10-06")
    status = {r["superbet_event_id"]: r["status"] for r in recs}
    assert status == {"1": si.DUPLICATE_SUPERBET_TEAM, "2": si.DUPLICATE_SUPERBET_TEAM,
                      "3": si.IDENTIFIED}
    assert client.calls == [30]  # a duplicate is never asked
    assert summary["sports"]["hockey"]["refused"] == {si.DUPLICATE_SUPERBET_TEAM: 2}
    # three hours apart or more is two games
    far = [_ev("1", "Vitality Academy", "Kometa Brno"),
           _ev("2", "Vitality Academy", "Sparta Praha", KICK + timedelta(hours=3))]
    assert si.duplicate_team_events(far) == {}


def test_a_refusal_aborts_the_run_without_a_retry():
    events = [_ev("1", "Sparta Praha", "Kometa Brno"),
              _ev("2", "Ocelari Trinec", "Dynamo Pardubice", KICK + timedelta(hours=4))]
    client = FakeClient({30: []}, refuse={10})
    recs, summary = si.identify(events, client, None, _teams, AT, "2026-10-06")
    assert [r["reason"] for r in recs] == ["BRIDGE_ABORTED", "BRIDGE_ABORTED"]
    assert client.calls == [10]  # once, and nothing after it
    assert summary["aborted"] == "HTTP 403"


def test_one_sofascore_id_for_two_superbet_events_is_a_duplicate():
    listing = [_listed(9001, (10, "Sparta Praha"), (20, "Kometa Brno"))]
    client = FakeClient({10: listing})
    teams = {**TEAMS}
    events = [_ev("1", "Sparta Praha", "Kometa Brno"),
              _ev("2", "Sparta", "Brno Kometa", KICK + timedelta(minutes=5))]
    # no folded name is shared, so C5 does not catch it; event 2 has no id
    # of its own and is asked through its query team: both read as 9001
    recs, _ = si.identify(events, client, None, lambda s, n: teams.get(n), AT,
                          "2026-10-06", query_teams=lambda s, n: 10)
    assert [r["status"] for r in recs] == [si.DUPLICATE_SOFASCORE_ID] * 2
    assert all(r["duplicate_of"] == 9001 for r in recs)


def test_a_resolved_id_that_differs_from_the_listing_refuses_the_side():
    """The name alone no longer carries a side whose resolved id is another
    team's (F1.2): "Sparta" resolved to 30 is not Sofascore's team 10."""
    listing = [_listed(9001, (10, "Sparta Praha"), (20, "Kometa Brno"))]
    teams = {**TEAMS, "Sparta": 30}
    (r,), _ = si.identify([_ev("2", "Sparta", "Kometa Brno")],
                          FakeClient({30: listing}), None,
                          lambda s, n: teams.get(n), AT, "2026-10-06")
    assert r["status"] == si.NOT_IDENTIFIED


def test_only_the_days_utc_window_is_identified():
    events = [_ev("1", "Sparta Praha", "Kometa Brno",
                  datetime(2026, 10, 7, 0, 30, tzinfo=UTC))]
    client = FakeClient({})
    recs, _ = si.identify(events, client, None, _teams, AT, "2026-10-06")
    assert recs == [] and client.calls == []


def test_a_pinned_record_is_never_asked_again_and_the_cache_serves_a_listing():
    client = FakeClient({10: [_listed(9001, (10, "Sparta Praha"), (20, "Kometa Brno"))]})
    cache = FakeCache()
    ev = _ev("1", "Sparta Praha", "Kometa Brno")
    (first,), _ = si.identify([ev], client, cache, _teams, AT, "2026-10-06")
    assert cache.saved[10]["events"][0]["id"] == 9001
    (again,), _ = si.identify([ev], client, cache, _teams, AT, "2026-10-06",
                              pinned={"1": first})
    assert again["pinned"] is True and again["sofascore_event_id"] == 9001
    assert client.calls == [10]
    (cached,), _ = si.identify([ev], client, cache, _teams, AT, "2026-10-06")
    assert cached["listing_from_cache"] is True and client.calls == [10]


def test_cs2_goes_through_pick_event():
    series = _listed(7001, (501, "Natus Vincere Junior"), (502, "ENCE Prospects"),
                     slug="esports", category="Counter Strike")
    client = FakeClient({501: [series]})
    ev = _ev("9", "Natus Vincere Junior", "ENCE Prospects", sport="cs2")
    recs, _ = si.identify([ev], client, None,
                          lambda s, n: {"Natus Vincere Junior": 501}.get(n), AT,
                          "2026-10-06")
    (r,) = recs
    assert r["status"] == si.IDENTIFIED and r["match_method"] == "CS2_PICK_EVENT"
    assert r["home_is_team1"] is True and r["sofascore_event_id"] == 7001
    late = _listed(7002, (501, "Natus Vincere Junior"), (502, "ENCE Prospects"),
                   KICK + timedelta(hours=2), slug="esports", category="Counter Strike")
    (r2,), _ = si.identify([ev], FakeClient({501: [late]}), None,
                           lambda s, n: {"Natus Vincere Junior": 501}.get(n), AT,
                           "2026-10-06")
    assert r2["reason"] == "START_GAP_OVER_1H"


def test_cs2_team_ids_come_from_the_series_store_by_exact_name():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE cs2_series (home_id INT, home_name TEXT, "
                 "away_id INT, away_name TEXT)")
    conn.execute("INSERT INTO cs2_series VALUES (1, 'NAVI Junior', 2, 'BIG'), "
                 "(3, 'BIG', 4, 'Other')")
    resolver = si.TeamResolver(conn, 0)
    assert resolver.team_id("cs2", "Natus Vincere Junior") == 1  # the alias
    assert resolver.team_id("cs2", "BIG") is None  # two ids: no guess
    assert resolver.team_id("cs2", "Nobody") is None


def _snapshot(sb: str, t1: str, t2: str, kick: str) -> dict[str, Any]:
    return {"fetched_at_utc": "2026-10-06T07:00:00Z", "superbet_event_id": sb,
            "match_name": f"{t1}·{t2}", "team1": t1, "team2": t2,
            "kickoff_utc": kick, "tournament": "Czechy - Extraliga",
            "lines": [{"superbet_event_id": sb, "market_id": 630, "family": "winner",
                       "period": 0, "subject": "", "line": None, "side": s,
                       "odds": o} for s, o in (("T1", 1.8), ("T2", 2.0))]}


def test_the_script_writes_sport_fixtures_into_the_runs_dir(tmp_path: Path,
                                                            monkeypatch):
    from scripts.sofa import run_sport_identity as rsi

    day = tmp_path / "shadow" / "hockey" / "2026-10-06"
    day.mkdir(parents=True)
    (day / "snapshots.jsonl").write_text(json.dumps(
        _snapshot("1", "Sparta Praha", "Kometa Brno", "2026-10-06T18:00:00Z")) + "\n")
    conn = sqlite3.connect(":memory:")
    monkeypatch.setattr(si.TeamResolver, "team_id",
                        lambda self, sport, name: TEAMS.get(name))
    monkeypatch.setattr(rsi, "now", lambda: AT)
    client = FakeClient({10: [_listed(9001, (10, "Sparta Praha"), (20, "Kometa Brno"))]})
    doc, code = rsi.run("2026-10-06", ["hockey"], str(tmp_path), client, None, conn)
    assert code == 0
    out = json.loads((tmp_path / "2026-10-06" / si.FIXTURES_FILE).read_text())
    (rec,) = out["fixtures"]
    for key in ("superbet_event_id", "sport", "sofascore_event_id", "home_id",
                "away_id", "home_is_team1", "competition_id", "match_method",
                "name_scores", "start_gap_h", "matched_at_utc"):
        assert key in rec
    assert out["sports_run"] == ["hockey"]
    # a second run asks nothing: the record is pinned
    client.calls.clear()
    _, code = rsi.run("2026-10-06", ["hockey"], str(tmp_path), client, None, conn)
    assert code == 0 and client.calls == []
    # no snapshot of any sport asked: FAILED
    _, code = rsi.run("2026-10-06", ["volleyball"], str(tmp_path), client, None, conn)
    assert code == 2


# --- F1.2 (production-grade plan 2026-10-05): recall without losing precision ---


def _bb(eid: int, home: tuple[int, str], away: tuple[int, str],
        start: datetime = KICK, status: str = "notstarted",
        gender: str = "M") -> dict[str, Any]:
    e = _listed(eid, home, away, start, slug="basketball")
    e["status"] = {"type": status}
    e["homeTeam"]["gender"] = e["awayTeam"]["gender"] = gender
    return e


def _bev(sb: str, t1: str, t2: str, kick: datetime = KICK) -> si.BoardEvent:
    return _ev(sb, t1, t2, kick, sport="basketball")


def test_a_postponed_copy_beside_the_real_game_is_not_a_second_candidate():
    """10-05 Partizan - Mega: Sofascore listed the game twice at 16:30, one
    copy postponed (reversed) - refused before."""
    listing = [_bb(1, (38317, "KK Mega Basket"), (6637, "KK Partizan"),
                   status="postponed"),
               _bb(2, (6637, "KK Partizan"), (38317, "KK Mega Basket"))]
    teams = {"Partizan": 6637, "Mega Basket": 38317}
    (r,), _ = si.identify([_bev("1", "Partizan", "Mega Basket")],
                          FakeClient({6637: listing}), None,
                          lambda s, n: teams.get(n), AT, "2026-10-06")
    assert r["status"] == si.IDENTIFIED and r["sofascore_event_id"] == 2
    (r2,), _ = si.identify([_bev("1", "Partizan", "Mega Basket")],
                           FakeClient({6637: listing[:1]}), None,
                           lambda s, n: teams.get(n), AT, "2026-10-06")
    assert r2["status"] == si.NOT_IDENTIFIED and r2["reason"] == "NOT_AS_SCHEDULED"


def test_the_womens_marker_does_not_cost_the_name_score():
    """"Helios VS (K)" scored 81.8 against "Helios VS Basket" on the marker
    alone; the gender gate reads the marker, the score does not."""
    listing = [_bb(1, (5, "Helios VS Basket"), (6, "Nyon Basket"), gender="F")]
    (r,), _ = si.identify([_bev("1", "Helios VS (K)", "Nyon Basket (K)")],
                          FakeClient({5: listing}), None,
                          lambda s, n: {"Helios VS (K)": 5}.get(n), AT, "2026-10-06")
    assert r["status"] == si.IDENTIFIED and r["match_method"] == "LISTING_ID_AND_NAME"
    men = [_bb(1, (5, "Helios VS Basket"), (6, "Nyon Basket"), gender="M")]
    (r2,), _ = si.identify([_bev("1", "Helios VS (K)", "Nyon Basket (K)")],
                           FakeClient({5: men}), None,
                           lambda s, n: {"Helios VS (K)": 5}.get(n), AT, "2026-10-06")
    assert r2["status"] == si.NOT_IDENTIFIED  # a men's game is not the women's


def test_one_side_by_id_and_the_opponent_by_the_settles_rule():
    """Sierre - Bellinzona Rockets (09-29): Sofascore's "GDT Bellinzona
    Snakes" shares one distinctive word and the clocks agree."""
    listing = [_listed(1, (5573, "HC Sierre"), (77, "GDT Bellinzona Snakes"))]
    (r,), _ = si.identify([_ev("1", "Sierre", "Bellinzona Rockets")],
                          FakeClient({5573: listing}), None,
                          lambda s, n: {"Sierre": 5573}.get(n), AT, "2026-10-06")
    assert r["status"] == si.IDENTIFIED
    assert r["match_method"] == "LISTING_ID_AND_OPPONENT" and r["home_is_team1"] is True
    # the shared word needs both clocks within 15 minutes
    late = [_listed(1, (5573, "HC Sierre"), (77, "GDT Bellinzona Snakes"),
                    KICK + timedelta(minutes=30))]
    (r2,), _ = si.identify([_ev("1", "Sierre", "Bellinzona Rockets")],
                           FakeClient({5573: late}), None,
                           lambda s, n: {"Sierre": 5573}.get(n), AT, "2026-10-06")
    assert r2["status"] == si.NOT_IDENTIFIED
    # an opponent resolved to another team is never confirmed by a word
    (r3,), _ = si.identify([_ev("1", "Sierre", "Bellinzona Rockets")],
                           FakeClient({5573: listing}), None,
                           lambda s, n: {"Sierre": 5573, "Bellinzona Rockets": 99}.get(n),
                           AT, "2026-10-06")
    assert r3["status"] == si.NOT_IDENTIFIED


def test_another_squad_of_the_club_is_not_the_club():
    """"Kataja Talents" (Kataja Basket's 1. Division B side) against
    Sofascore's "Kataja Basket": the shared "kataja" no longer confirms it."""
    listing = [_bb(1, (6509, "Kataja Basket"), (176596, "Helsinki Seagulls"))]
    (r,), _ = si.identify([_bev("1", "Kataja Talents", "Helsinki")],
                          FakeClient({176596: listing}), None,
                          lambda s, n: {"Helsinki": 176596}.get(n), AT, "2026-10-06")
    assert r["status"] == si.NOT_IDENTIFIED
    assert not si.same_squad("vitality academy", "vitality")
    assert si.same_squad("kataja basket talents", "kataja talents")


def test_cs2_c5_refuses_the_same_pair_only():
    """A CS2 team plays two series a day against two opponents (09-28..10-04:
    the team rule refused series the settle found); the same pair twice is a
    loop or a rematch no start tells apart."""
    two_opponents = [_ev("1", "Masonic", "Linx Legacy", sport="cs2"),
                     _ev("2", "Masonic", "STATE", KICK + timedelta(hours=2),
                         sport="cs2")]
    assert si.duplicate_team_events(two_opponents) == {}
    loop = [_ev("1", "DeeKkaa", "-proHor", sport="cs2"),
            _ev("2", "-proHor", "DeeKkaa", KICK + timedelta(minutes=33), sport="cs2")]
    assert set(si.duplicate_team_events(loop)) == {"1", "2"}
    # hockey keeps the team rule: a club does not play twice in 3 h
    hockey = [_ev("1", "Masonic", "Linx Legacy"),
              _ev("2", "Masonic", "STATE", KICK + timedelta(hours=2))]
    assert set(si.duplicate_team_events(hockey)) == {"1", "2"}


def test_a_query_only_team_is_asked_but_never_an_id_match():
    listing = [_bb(1, (233932, "CD Español de Talca"),
                   (1217902, "Universidad Santiago de Chile"))]
    client = FakeClient({233932: listing})
    query = {"Espanol de Talca": 233932}
    (r,), _ = si.identify([_bev("1", "Espanol de Talca", "U. De Santiago")], client,
                          None, lambda s, n: None, AT, "2026-10-06",
                          query_teams=lambda s, n: query.get(n))
    assert client.calls == [233932]
    assert r["status"] == si.IDENTIFIED and r["query_only"] is True
    assert r["match_method"] == "LISTING_NAMES"
    # the asked team's id alone confirms nothing: the other name must match
    wrong = [_bb(1, (233932, "CD Español de Talca"), (5, "Colo Colo"))]
    (r2,), _ = si.identify([_bev("1", "Espanol de Talca", "U. De Santiago")],
                           FakeClient({233932: wrong}), None, lambda s, n: None, AT,
                           "2026-10-06", query_teams=lambda s, n: query.get(n))
    assert r2["status"] == si.NOT_IDENTIFIED


def _resolver_db(rows: list[tuple[str, int, dict[str, Any]]]) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE sofa_entity (sport TEXT, query_key TEXT, "
                 "sofascore_id INT, status TEXT)")
    conn.execute("CREATE TABLE sofa_listed_event (sport TEXT, start_ts INT, "
                 "event_json TEXT)")
    conn.executemany("INSERT INTO sofa_listed_event VALUES (?, ?, ?)",
                     [(s, ts, json.dumps(e)) for s, ts, e in rows])
    return conn


def test_the_name_index_covers_an_off_season():
    """10-05: every NBA team was TEAM_UNRESOLVED - their last game was in
    April, past player_model's 120 days."""
    from bet.sofa.player_model import team_name_index

    april = int(datetime(2026, 4, 10, tzinfo=UTC).timestamp())
    e = _listed(1, (3421, "New York Knicks"), (3424, "Detroit Pistons"),
                slug="basketball")
    conn = _resolver_db([("basketball", april, e)])
    resolver = si.TeamResolver(conn, int(AT.timestamp()))
    assert resolver.team_id("basketball", "New York Knicks") == 3421
    assert team_name_index(conn, "basketball", int(AT.timestamp())) == {}


def test_query_id_is_the_one_fuzzy_team_of_the_same_squad():
    ts = int(AT.timestamp()) - 86400
    rows = [("basketball", ts, _listed(1, (233932, "CD Español de Talca"),
                                       (416642, "CD Español de Osorno"),
                                       slug="basketball")),
            ("basketball", ts, _listed(2, (477919, "ŽKK Zadar U19"),
                                       (25740, "ŽKK Zadar"), slug="basketball"))]
    resolver = si.TeamResolver(_resolver_db(rows), int(AT.timestamp()))
    assert resolver.team_id("basketball", "Espanol de Talca") is None
    assert resolver.query_id("basketball", "Espanol de Talca") == 233932
    assert resolver.query_id("basketball", "Zadar") == 25740  # U19 is another squad
    assert resolver.query_id("basketball", "Espanol") is None  # two teams
    assert resolver.query_id("cs2", "Anything") is None


def test_cs2_ids_fall_back_to_the_name_without_esports_affixes():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE cs2_series (home_id INT, home_name TEXT, "
                 "away_id INT, away_name TEXT)")
    conn.execute("INSERT INTO cs2_series VALUES (424876, 'Aurora Gaming', "
                 "485866, 'BetBoom Team'), (469629, 'Aurora Young Blood', 1, 'X')")
    resolver = si.TeamResolver(conn, 0)
    assert resolver.team_id("cs2", "BetBoom") == 485866
    assert resolver.team_id("cs2", "Aurora") == 424876  # Young Blood is another core
