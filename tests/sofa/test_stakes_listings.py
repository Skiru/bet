"""STAKES_LISTINGS (operator 2026-11-19; bet.sofa.stakes_listings,
scripts/sofa/refresh_stakes_listings.py): the national group teams' `last` /
`next` page 0 refreshed before the coupon so the display-only group stakes
flags stop missing games - scope, freshness, refusals, zero requests with
no national fixture, an INCOMPLETE_GROUP / STALE group made whole once the
pages carry the games, and the rebuild step. Offline, a fake client."""

from __future__ import annotations

import itertools
import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from bet.sofa import rebuild_plan as rp
from bet.sofa import stakes_groups as sg
from bet.sofa import stakes_listings as sl
from bet.sofa.cache import SofaCache
from bet.sofa.config import SofaConfig
from bet.sofa.db import migrate
from bet.sofa.errors import CircuitOpenError, ProviderError

AFCON, CONCACAF, SEASON, TID = 1848, 14100, 77001, 88001
NOW = datetime.now(UTC).replace(microsecond=0)
T0 = int((NOW - timedelta(days=60)).timestamp())  # matchday 1
DAY = 86400


def ev(eid: int, ts: int, home: int, away: int, score: tuple[int, int] | None,
       ut: int = AFCON) -> dict[str, Any]:
    finished = score is not None
    return {
        "id": eid, "startTimestamp": ts,
        "tournament": {"id": TID, "name": "Group C", "uniqueTournament": {"id": ut}},
        "season": {"id": SEASON}, "roundInfo": {"round": 1},
        "status": {"type": "finished" if finished else "notstarted"},
        "homeTeam": {"id": home, "name": f"T{home}", "gender": "M", "national": True},
        "awayTeam": {"id": away, "name": f"T{away}", "gender": "M", "national": True},
        "homeScore": {"normaltime": score[0]} if finished else {},
        "awayScore": {"normaltime": score[1]} if finished else {},
        "winnerCode": (1 if score[0] > score[1] else 2 if score[1] > score[0] else 3)
        if score else None,
    }


TEAMS = (101, 102, 103, 104)


def double_round_robin(ut: int = AFCON) -> list[dict[str, Any]]:
    """Twelve games, matchdays 1-6; matchdays 1-4 played (home side wins
    1-0), 5-6 to play. Matchday 5's first game is the fixture."""
    pairs = list(itertools.combinations(TEAMS, 2))
    rounds = [[(101, 102), (103, 104)], [(101, 103), (102, 104)],
              [(101, 104), (102, 103)]]
    out, eid = [], 1000
    for md in range(6):
        for h, a in rounds[md % 3]:
            if md >= 3:
                h, a = a, h
            eid += 1
            out.append(ev(eid, T0 + md * 10 * DAY, h, a,
                          (1, 0) if md < 4 else None, ut))
    assert len(pairs) * 2 == len(out)
    return out


@pytest.fixture
def db(tmp_path: Path) -> tuple[str, SofaCache, sqlite3.Connection]:
    path = str(tmp_path / "sofa.db")
    migrate(path)
    cache = SofaCache(SofaConfig(db_path=path, runs_dir=str(tmp_path)))
    con = sqlite3.connect(path)
    return path, cache, con


def seed(cache: SofaCache, con: sqlite3.Connection, games: list[dict[str, Any]],
         fixture: dict[str, Any], fetched_at: datetime | None = None) -> None:
    """Each team's cached `last` page 0 holds `games` it played in."""
    for t in TEAMS:
        mine = [g for g in games if t in (g["homeTeam"]["id"], g["awayTeam"]["id"])]
        if mine:
            cache.save_entity_events(t, "last", 0, {"events": mine})
    if fetched_at is not None:
        con.execute("UPDATE sofa_entity_events SET fetched_at = ?",
                    (fetched_at.isoformat(),))
    con.execute("INSERT OR REPLACE INTO sofa_event_detail VALUES (?, 'x', ?, ?)",
                (fixture["id"], "notstarted", json.dumps({"event": fixture})))
    con.commit()


class FakeClient:
    def __init__(self, games: list[dict[str, Any]],
                 fail: Exception | None = None) -> None:
        self.games, self.fail, self.calls = games, fail, []  # type: list[Any]

    def __call__(self, team: int, kind: str, page: int) -> Any:
        self.calls.append((team, kind, page))
        if self.fail is not None:
            raise self.fail
        mine = [g for g in self.games
                if team in (g["homeTeam"]["id"], g["awayTeam"]["id"])
                and (g["status"]["type"] == "finished") == (kind == "last")]
        return {"events": mine, "hasNextPage": False} if mine else None


def row(fixture: dict[str, Any], kickoff: datetime | None = None,
        competition: int = AFCON) -> dict[str, Any]:
    ko = kickoff or NOW + timedelta(hours=5)
    return {"sport": "football", "sofascore_event_id": fixture["id"],
            "competition_id": competition,
            "kickoff_utc": ko.isoformat().replace("+00:00", "Z")}


def refresher(con: sqlite3.Connection, cache: SofaCache, client: Any,
              record: dict[str, Any] | None = None) -> sl.Refresher:
    return sl.Refresher(con, client, cache.save_entity_events, NOW,
                        {} if record is None else record)


# ------------------------------------------------------------------ scope


def test_scope_is_open_national_football_only() -> None:
    fx = {"id": 1}
    rows = [row(fx), row({"id": 2}, NOW - timedelta(minutes=1)),
            row({"id": 3}, competition=17),
            {**row({"id": 4}), "sport": "tennis"}]
    assert [r["sofascore_event_id"] for r in sl.open_national(rows, NOW)] == [1]


def test_no_national_fixture_asks_nothing(db: Any) -> None:
    _, cache, con = db
    client = FakeClient([])
    res = refresher(con, cache, client).run(
        [row({"id": 5}, competition=17), {**row({"id": 6}), "sport": "tennis"}])
    assert res.requests == 0 and client.calls == []


def test_knockout_fixture_is_not_walked(db: Any) -> None:
    _, cache, con = db
    games = double_round_robin()
    fixture = {**games[8], "roundInfo": {"name": "Final", "cupRoundType": 1}}
    seed(cache, con, [], fixture)
    client = FakeClient(games)
    res = refresher(con, cache, client).run([row(fixture)])
    assert client.calls == [] and res.out_of_group_scope == 1


# ------------------------------------------- INCOMPLETE / STALE made whole


def test_incomplete_group_becomes_complete(db: Any) -> None:
    """AFCON qualifiers (Angola's group, 11-14..18): 4 teams / 12 games, the
    cache held 8 - the October games were on no cached page."""
    _, cache, con = db
    games = double_round_robin()
    fixture = games[8]  # matchday 5
    # matchdays 3-4 (October) missing from the cache: 8 of 12 known
    seed(cache, con, games[:4], fixture, fetched_at=NOW - timedelta(days=2))
    since = fixture["startTimestamp"] - sg.LISTING_DAYS * DAY
    assert sg.national_states(fixture, sg.group_events(con, fixture, since)) \
        == "INCOMPLETE_GROUP"
    assert sg.for_day(con, [row(fixture)]) == {}
    client = FakeClient(games)
    res = refresher(con, cache, client).run([row(fixture)])
    assert res.stopped is None and res.teams == 4
    assert res.requests == 8  # last / next page 0 of the four teams
    states = sg.national_states(fixture, sg.group_events(con, fixture, since))
    assert isinstance(states, dict) and set(states) == {
        fixture["homeTeam"]["id"], fixture["awayTeam"]["id"]}


def test_stale_group_becomes_fresh(db: Any) -> None:
    """CONCACAF Nations League B (Puerto Rico - Dominica 11-13, Guyana -
    Puerto Rico 11-16): a played game still `notstarted` in the cache."""
    _, cache, con = db
    games = double_round_robin(CONCACAF)
    fixture = games[8]
    stale = [dict(g) for g in games[:8]]
    stale[7] = ev(stale[7]["id"], stale[7]["startTimestamp"],
                  stale[7]["homeTeam"]["id"], stale[7]["awayTeam"]["id"], None,
                  CONCACAF)
    # the page was fetched before the game was played
    seed(cache, con, stale, fixture, fetched_at=datetime.fromtimestamp(
        stale[7]["startTimestamp"] - DAY, UTC))
    since = fixture["startTimestamp"] - sg.LISTING_DAYS * DAY
    assert sg.national_states(fixture, sg.group_events(con, fixture, since)) == "STALE"
    client = FakeClient(games)
    refresher(con, cache, client).run([row(fixture, competition=CONCACAF)])
    assert isinstance(
        sg.national_states(fixture, sg.group_events(con, fixture, since)), dict)


# -------------------------------------------------------------- freshness


def test_page_fetched_within_fresh_h_is_not_asked(db: Any) -> None:
    _, cache, con = db
    games = double_round_robin()
    fixture = games[8]
    seed(cache, con, games[:8], fixture,
         fetched_at=NOW - timedelta(hours=sl.FRESH_H - 1))
    record = {f"{t}/next/0": {"asked_at_utc": (NOW - timedelta(hours=1)).isoformat(),
                              "status": "EMPTY"} for t in TEAMS}
    client = FakeClient(games)
    res = refresher(con, cache, client, record).run([row(fixture)])
    assert client.calls == [] and res.fresh_skipped == 8


def test_old_page_is_asked_again(db: Any) -> None:
    _, cache, con = db
    games = double_round_robin()
    fixture = games[8]
    seed(cache, con, games[:8], fixture,
         fetched_at=NOW - timedelta(hours=sl.FRESH_H + 1))
    client = FakeClient(games)
    refresher(con, cache, client).run([row(fixture)])
    assert {(t, "last", 0) for t in TEAMS} <= set(client.calls)


def test_fresh_page_that_cannot_hold_a_result_is_asked(db: Any) -> None:
    """Fetched 2 h ago, before a group game it shows unfinished ended."""
    _, cache, con = db
    games = double_round_robin()
    fixture = games[8]
    started = int((NOW - timedelta(hours=4)).timestamp())
    late = ev(5000, started, 101, 102, None)
    seed(cache, con, [*games[:8], late], fixture,
         fetched_at=NOW - timedelta(hours=3))
    client = FakeClient(games)
    refresher(con, cache, client).run([row(fixture)])
    assert (101, "last", 0) in client.calls and (102, "last", 0) in client.calls
    assert (103, "last", 0) not in client.calls


# --------------------------------------------------------------- refusals


@pytest.mark.parametrize("fail", [ProviderError("HTTP 403"),
                                  ProviderError("HTTP 429"),
                                  CircuitOpenError("Circuit breaker is open")])
def test_refusal_stops_at_once(db: Any, fail: Exception) -> None:
    _, cache, con = db
    games = double_round_robin()
    fixture = games[8]
    seed(cache, con, games[:8], fixture,
         fetched_at=NOW - timedelta(days=2))
    client = FakeClient(games, fail)
    other = {**games[9], "id": 9999}
    res = refresher(con, cache, client).run([row(fixture), row(other)])
    assert len(client.calls) == 1 and res.stopped


def test_error_streak_stops(db: Any) -> None:
    _, cache, con = db
    games = double_round_robin()
    fixture = games[8]
    seed(cache, con, games[:8], fixture, fetched_at=NOW - timedelta(days=2))
    client = FakeClient(games, ProviderError("HTTP 504"))
    res = refresher(con, cache, client).run([row(fixture)])
    assert len(client.calls) == sl.MAX_ERROR_STREAK and res.errors == 2
    assert res.stopped


# ----------------------------------------------------------- rebuild step

LIMIT = timedelta(minutes=45)


def test_rebuild_plans_the_step_only_with_an_open_national_fixture() -> None:
    day, at = "2026-11-20", datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
    assert "STAKES_LISTINGS" not in rp.build_plan(rp.DayState(day, at, LIMIT)).names()
    names = rp.build_plan(rp.DayState(day, at, LIMIT,
                                      stakes_national_open=2)).names()
    i = names.index("STAKES_LISTINGS")
    assert names.index("FIXTURE_CHECK") < i < names.index("COUPON_ASSEMBLY")
    step = rp.build_plan(rp.DayState(day, at, LIMIT, stakes_national_open=2)).steps[i]
    assert step.soft


def test_observe_counts_open_national_fixtures_only_under_the_switch(
        tmp_path: Path) -> None:
    run = tmp_path / "2026-11-20"
    run.mkdir()
    ko = datetime(2026, 11, 20, 19, 0, tzinfo=UTC)
    (run / "02_fixtures.json").write_text(json.dumps(
        [row({"id": 1}, ko), row({"id": 2}, ko, competition=17)]))
    at = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
    assert rp.observe(str(tmp_path), "2026-11-20", at, LIMIT).stakes_national_open == 1
    before = tmp_path / "2026-11-17"
    before.mkdir()
    (before / "02_fixtures.json").write_text(json.dumps(
        [row({"id": 1}, datetime(2026, 11, 17, 19, 0, tzinfo=UTC))]))
    assert rp.observe(str(tmp_path), "2026-11-17",
                      datetime(2026, 11, 17, 12, 0, tzinfo=UTC),
                      LIMIT).stakes_national_open == 0


def test_script_builds_no_client_without_a_national_fixture(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    import bet.sofa.client as client_mod
    from scripts.sofa import refresh_stakes_listings as script

    day = (NOW + timedelta(days=1)).strftime("%Y-%m-%d")
    run = tmp_path / day
    run.mkdir()
    (run / "02_fixtures.json").write_text(json.dumps(
        [row({"id": 1}, NOW + timedelta(days=1), competition=17)]))
    monkeypatch.setenv("SOFA_RUNS_DIR", str(tmp_path))
    monkeypatch.setenv("SOFA_DB_PATH", str(tmp_path / "none.db"))
    monkeypatch.delenv("SOFA_NOW", raising=False)

    def boom(*_: Any, **__: Any) -> None:
        raise AssertionError("a client was built")

    monkeypatch.setattr(client_mod, "SofascoreClient", boom)
    monkeypatch.setattr("sys.argv", ["x", "--date", day])
    assert script.main() == 0
    out = capsys.readouterr().out
    assert '"requests": 0' in out and not (run / sl.RECORD_FILE).exists()
