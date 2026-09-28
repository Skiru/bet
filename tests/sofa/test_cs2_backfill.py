"""CS2_BACKFILL against a fake Sofascore: team resolution, paging back to the
cutoff, opponents one hop out, storage, resumability, and the breaker; and
CS2_SETTLE's two links to the store (it writes the series, it reads history
for the engine without reading its own answer)."""

import json
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from bet.sofa.config import SofaConfig
from bet.sofa.errors import CircuitOpenError
from scripts.sofa import backfill_cs2, settle_cs2

AT = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)
DAY = 86400


def cs_event(
    eid: int,
    days_ago: float,
    home: int,
    away: int,
    status: str = "finished",
    category: str = "Counter Strike",
) -> dict[str, Any]:
    return {
        "id": eid,
        "startTimestamp": int((AT - timedelta(days=days_ago)).timestamp()),
        "homeTeam": {"id": home, "name": f"T{home}"},
        "awayTeam": {"id": away, "name": f"T{away}"},
        "homeScore": {"current": 1},
        "awayScore": {"current": 0},
        "status": {"type": status, "description": "Ended"},
        "tournament": {"name": "CCT", "category": {"name": category}},
    }


class FakeSofascore:
    """GamerLegion (1) plays magic (2); magic also played Astralis (3)."""

    def __init__(self, breaker_on_games: bool = False) -> None:
        self.breaker_on_games = breaker_on_games
        self.calls: list[str] = []
        self.listings = {
            1: [cs_event(11, 2, 1, 2), cs_event(12, 400, 1, 2)],  # 2nd outside window
            2: [
                cs_event(11, 2, 1, 2),
                cs_event(13, 5, 2, 3),
                cs_event(14, 3, 2, 3, status="inprogress"),
            ],
            3: [cs_event(13, 5, 2, 3)],
            9: [cs_event(90, 1, 9, 8, category="LoL")],  # the LoL namesake
        }

    def search(self, q: str) -> dict[str, Any]:
        self.calls.append(f"search {q}")
        teams = {
            "GamerLegion": [(9, "GamerLegion"), (1, "GamerLegion")],
            "magic": [(2, "magic")],
            "Nobody": [],
        }.get(q, [])
        return {
            "results": [
                {
                    "type": "team",
                    "entity": {"id": i, "name": n, "sport": {"slug": "esports"}},
                }
                for i, n in teams
            ]
        }

    def entity_events(self, team_id: int, kind: str, page: int) -> dict[str, Any]:
        self.calls.append(f"listing {team_id} {page}")
        return {
            "events": self.listings.get(team_id, []) if page == 0 else [],
            "hasNextPage": False,
        }

    def esports_games(self, event_id: int) -> dict[str, Any]:
        if self.breaker_on_games:
            raise CircuitOpenError("open")
        self.calls.append(f"games {event_id}")
        return {
            "games": [
                {
                    "id": event_id * 10,
                    "startTimestamp": 1,
                    "status": {"type": "finished"},
                    "homeScore": {"display": 13},
                    "awayScore": {"display": 9},
                    "hasCompleteStatistics": True,
                }
            ]
        }

    def esports_game_lineups(self, game_id: int) -> dict[str, Any]:
        self.calls.append(f"lineups {game_id}")
        rows = [
            {"player": {"id": game_id + i, "name": f"p{i}"}, "kills": 15}
            for i in range(5)
        ]
        return {"homeTeamPlayers": rows, "awayTeamPlayers": rows}


def config(tmp_path: Path) -> SofaConfig:
    cfg = SofaConfig(db_path=str(tmp_path / "t.db"), runs_dir=str(tmp_path / "runs"))
    day = tmp_path / "runs" / "cs2" / "2026-09-27"
    day.mkdir(parents=True)
    rec = {"team1": "GamerLegion", "team2": "magic", "lines": []}
    (day / "snapshots.jsonl").write_text(json.dumps(rec) + "\n")
    return cfg


def run(tmp_path: Path, fake: FakeSofascore, **kw: Any) -> dict[str, Any]:
    args = {
        "days": 180,
        "hops": 1,
        "max_minutes": 5,
        "dry_run": False,
        "extra_team_ids": [],
        "at": AT,
        **kw,
    }
    return backfill_cs2.run(
        fake,
        config(tmp_path)
        if not (tmp_path / "runs").exists()  # type: ignore[arg-type]
        else SofaConfig(
            db_path=str(tmp_path / "t.db"), runs_dir=str(tmp_path / "runs")
        ),
        **args,
    )


def db(tmp_path: Path) -> sqlite3.Connection:
    return sqlite3.connect(str(tmp_path / "t.db"))


def test_backfill_resolves_pages_hops_and_stores(tmp_path: Path) -> None:
    fake = FakeSofascore()
    result = run(tmp_path, fake)
    m = result["metrics"]
    assert result["verdict"] == "OK"
    assert m["seed_teams"] == 2  # the LoL "GamerLegion" (9) is not taken
    assert m["teams_listed"] == 3  # 1 and 2, then opponent 3 one hop out
    assert m["series_in_window"] == 2  # 11 and 13: 12 too old, 14 unfinished
    stored = {
        r[0] for r in db(tmp_path).execute("SELECT sofascore_event_id FROM cs2_series")
    }
    assert stored == {11, 13}
    assert (
        db(tmp_path).execute("SELECT COUNT(*) FROM cs2_player_map").fetchone()[0] == 20
    )
    # The LoL namesake (9) was looked at to be rejected, and its event never fetched.
    assert "listing 9 0" in fake.calls and "games 90" not in fake.calls


def test_backfill_is_resumable(tmp_path: Path) -> None:
    run(tmp_path, FakeSofascore())
    again = FakeSofascore()
    result = run(tmp_path, again)
    assert result["metrics"]["series_to_fetch"] == 0
    assert not any(c.startswith("games") for c in again.calls)


def test_hops_zero_stays_with_the_seeds(tmp_path: Path) -> None:
    result = run(tmp_path, FakeSofascore(), hops=0)
    assert result["metrics"]["teams_listed"] == 2


def test_dry_run_fetches_no_maps(tmp_path: Path) -> None:
    fake = FakeSofascore()
    result = run(tmp_path, fake, dry_run=True)
    assert result["dry_run"] and result["metrics"]["series_to_fetch"] == 2
    assert not any(c.startswith("games") for c in fake.calls)


def test_an_open_breaker_fails_rather_than_pretending(tmp_path: Path) -> None:
    result = run(tmp_path, FakeSofascore(breaker_on_games=True))
    assert result["verdict"] == "FAILED"


def test_no_seed_is_a_failure(tmp_path: Path) -> None:
    cfg = SofaConfig(db_path=str(tmp_path / "t.db"), runs_dir=str(tmp_path / "empty"))
    result = backfill_cs2.run(
        FakeSofascore(),
        cfg,
        days=180,
        hops=1,
        max_minutes=5,  # type: ignore[arg-type]
        dry_run=False,
        extra_team_ids=[],
        at=AT,
    )
    assert result["verdict"] == "FAILED"


def test_workers_log_under_their_own_stage(tmp_path: Path) -> None:
    """Worker threads start with the default ContextVar; without set_stage in
    each task every request was billed to "CLIENT" (seen live 2026-09-28)."""
    from bet.sofa.stage import current_stage

    seen: list[str] = []

    class Spy(FakeSofascore):
        def esports_games(self, event_id: int) -> dict[str, Any]:
            seen.append(current_stage())
            return super().esports_games(event_id)

    run(tmp_path, Spy())
    assert seen and set(seen) == {"CS2_BACKFILL"}


# --- CS2_SETTLE and the store --------------------------------------------------------


def test_settle_writes_the_series_and_attaches_a_leak_free_model(
    tmp_path: Path,
) -> None:
    """Review A-7: the old version was excluded by time alone and never looked
    at the direction of model_p."""
    from bet.sofa.cs2_store import save_series
    from bet.sofa.db import migrate
    from tests.sofa.test_cs2_stages import DATE
    from tests.sofa.test_cs2_stages import FakeSofascore as SettleFake

    dbp = str(tmp_path / "t.db")
    migrate(dbp)
    # History: GamerLegion (away id 20) beat magic (home id 10) on 12 maps.
    conn = sqlite3.connect(dbp)
    kick = int(datetime(2026, 9, 26, 15, tzinfo=UTC).timestamp())
    for i in range(12):
        ev = {
            "id": 700 + i,
            "startTimestamp": kick - (i + 1) * DAY,
            "homeTeam": {"id": 10, "name": "magic"},
            "awayTeam": {"id": 20, "name": "GL"},
            "homeScore": {"current": 0},
            "awayScore": {"current": 1},
            "status": {"type": "finished", "description": "Ended"},
            "tournament": {"category": {"name": "Counter Strike"}},
        }
        games = [
            {
                "id": 7000 + i,
                "startTimestamp": 1,
                "status": {"type": "finished"},
                "homeScore": {"display": 5},
                "awayScore": {"display": 13},
            }
        ]
        save_series(conn, ev, games, {}, "t", True)
    conn.close()

    lines = [
        {
            "superbet_event_id": "1",
            "family": "match_winner",
            "map_nr": 0,
            "subject": "",
            "line": None,
            "side": s,
            "odds": o,
        }
        for s, o in (("T1", 1.5), ("T2", 2.6))
    ] + [
        {
            "superbet_event_id": "1",
            "family": "maps_total",
            "map_nr": 0,
            "subject": "",
            "line": 2.5,
            "side": s,
            "odds": o,
        }
        for s, o in (("UNDER", 1.8), ("OVER", 1.95))
    ]
    rec = {
        "fetched_at_utc": "2026-09-26T12:00:00Z",
        "superbet_event_id": "1",
        "match_name": "GamerLegion·magic",
        "team1": "GamerLegion",
        "team2": "magic",
        "kickoff_utc": "2026-09-26T15:00:00Z",
        "tournament": "CCT",
        "lines": lines,
    }
    day = tmp_path / "cs2" / DATE
    day.mkdir(parents=True)
    (day / "snapshots.jsonl").write_text(json.dumps(rec) + "\n")

    fake = SettleFake()
    ids = {
        "homeTeam": {"name": "magic", "id": 10},
        "awayTeam": {"name": "GamerLegion", "id": 20},
    }
    listing = fake._event
    fake._event = lambda: {**listing(), **ids}  # type: ignore[method-assign]
    # The detail reports a start three hours before the listing's, so the
    # graded series is stored *inside* the time window - only the exclusion
    # by id keeps its own maps out of its history.
    early = {**fake._event(), "startTimestamp": kick - 3 * 3600}
    fake.event = lambda event_id: {"event": early}  # type: ignore[method-assign,assignment]
    settle_cs2.settle(
        DATE,
        fake,
        str(tmp_path),
        datetime(2026, 9, 26, 21, tzinfo=UTC),
        dbp,  # type: ignore[arg-type]
    )
    rec = json.loads((day / "settled.json").read_text())["events"]["1"]
    assert rec["state"] == "SETTLED"
    stored = (
        sqlite3.connect(dbp)
        .execute("SELECT start_ts FROM cs2_series WHERE sofascore_event_id = 900")
        .fetchone()
    )
    assert stored == (kick - 3 * 3600,)  # joined the history, inside the window
    by = {(r["family"], r["side"]): r for r in rec["graded"]}
    t1 = by[("match_winner", "T1")]
    assert t1["model"] == "elo_series" and t1["model_n"] == 12  # not 13+: 900 excluded
    assert t1["model_p"] > 0.5  # GamerLegion, team1, won every stored map
    assert t1["model_p"] + by[("match_winner", "T2")]["model_p"] == pytest.approx(1.0)
    assert t1["unfitted_constants"]


def test_settle_marks_the_store_incomplete_when_it_skipped_lineups(
    tmp_path: Path,
) -> None:
    """Review B-5: settle fetches lineups only for priced player lines, and
    marking the series complete stopped the backfill from ever fetching them."""
    from bet.sofa.db import migrate
    from tests.sofa.test_cs2_stages import DATE
    from tests.sofa.test_cs2_stages import FakeSofascore as SettleFake

    dbp = str(tmp_path / "t.db")
    migrate(dbp)
    rec = {
        "fetched_at_utc": "2026-09-26T12:00:00Z",
        "superbet_event_id": "1",
        "match_name": "GamerLegion·magic",
        "team1": "GamerLegion",
        "team2": "magic",
        "kickoff_utc": "2026-09-26T15:00:00Z",
        "tournament": "CCT",
        "lines": [
            {
                "superbet_event_id": "1",
                "family": "maps_total",
                "map_nr": 0,
                "subject": "",
                "line": 2.5,
                "side": s,
                "odds": 1.9,
            }
            for s in ("OVER", "UNDER")
        ],
    }
    day = tmp_path / "cs2" / DATE
    day.mkdir(parents=True)
    (day / "snapshots.jsonl").write_text(json.dumps(rec) + "\n")
    settle_cs2.settle(
        DATE,
        SettleFake(),
        str(tmp_path),  # type: ignore[arg-type]
        datetime(2026, 9, 26, 21, tzinfo=UTC),
        dbp,
    )
    complete = (
        sqlite3.connect(dbp)
        .execute("SELECT complete FROM cs2_series WHERE sofascore_event_id = 900")
        .fetchone()
    )
    assert complete == (0,)


def test_a_store_failure_does_not_fail_the_grade(tmp_path: Path) -> None:
    from tests.sofa.test_cs2_stages import DATE, write_snapshot
    from tests.sofa.test_cs2_stages import FakeSofascore as SettleFake

    write_snapshot(tmp_path)
    bad_db = str(tmp_path / "no" / "such" / "dir" / "t.db")
    settle_cs2.settle(
        DATE,
        SettleFake(),
        str(tmp_path),  # type: ignore[arg-type]
        datetime(2026, 9, 26, 21, tzinfo=UTC),
        bad_db,
    )
    rec = json.loads((tmp_path / "cs2" / DATE / "settled.json").read_text())["events"][
        "1"
    ]
    assert rec["state"] == "SETTLED" and "store_error" in rec


# --- discovery (review B-3, B-6, B-7) ----------------------------------------------


def test_listing_pages_back_to_the_cutoff(tmp_path: Path) -> None:
    class Paged(FakeSofascore):
        def entity_events(self, team_id: int, kind: str, page: int) -> dict[str, Any]:
            self.calls.append(f"listing {team_id} {page}")
            if team_id != 1:
                return {"events": [], "hasNextPage": False}
            # Ascending within a page; page 0 the newest. Page 2 crosses the
            # cutoff, so page 3 must never be asked.
            days = {0: [3, 1], 1: [60, 30], 2: [300, 150], 3: [500, 400]}[page]
            return {
                "events": [
                    cs_event(100 + page * 10 + i, d, 1, 2) for i, d in enumerate(days)
                ],
                "hasNextPage": page < 3,
            }

    fake = Paged()
    result = run(tmp_path, fake, hops=0)
    assert "listing 1 2" in fake.calls and "listing 1 3" not in fake.calls
    assert result["metrics"]["series_in_window"] == 5  # 150 in, 300 out


def test_a_provider_error_in_discovery_is_counted_not_fatal(tmp_path: Path) -> None:
    from bet.sofa.errors import ProviderError

    class Flaky(FakeSofascore):
        def entity_events(self, team_id: int, kind: str, page: int) -> dict[str, Any]:
            if team_id == 3:
                raise ProviderError("HTTP 500")
            return super().entity_events(team_id, kind, page)

    result = run(tmp_path, Flaky())
    assert result["verdict"] == "PARTIAL"
    assert result["metrics"]["listing_errors"] == 1
    assert result["metrics"]["series_stored"] == 2


def test_the_deadline_stops_discovery_too(tmp_path: Path) -> None:
    fake = FakeSofascore()
    result = run(tmp_path, fake, max_minutes=0)
    assert result["verdict"] == "FAILED"  # nothing could be resolved in time
    assert not any(c.startswith("games") for c in fake.calls)


def test_an_equal_name_tie_is_not_cached_as_a_miss(tmp_path: Path) -> None:
    from bet.sofa.cache import SofaCache

    class Twins(FakeSofascore):
        def search(self, q: str) -> dict[str, Any]:
            self.calls.append(f"search {q}")
            return {
                "results": [
                    {
                        "type": "team",
                        "entity": {
                            "id": i,
                            "name": "magic",
                            "sport": {"slug": "esports"},
                        },
                    }
                    for i in (2, 3)
                ]
            }

    run(tmp_path, Twins(), dry_run=True)
    cfg = SofaConfig(db_path=str(tmp_path / "t.db"), runs_dir=str(tmp_path / "runs"))
    assert not SofaCache(cfg).get_entity_miss("cs2", "magic")


def test_every_request_is_logged_under_the_stage(tmp_path: Path) -> None:
    from bet.sofa.stage import current_stage

    seen: set[str] = set()

    class Spy(FakeSofascore):
        def search(self, q: str) -> dict[str, Any]:
            seen.add(current_stage())
            return super().search(q)

        def entity_events(self, team_id: int, kind: str, page: int) -> dict[str, Any]:
            seen.add(current_stage())
            return super().entity_events(team_id, kind, page)

        def esports_game_lineups(self, game_id: int) -> dict[str, Any]:
            seen.add(current_stage())
            return super().esports_game_lineups(game_id)

    run(tmp_path, Spy())
    assert seen == {"CS2_BACKFILL"}


def test_a_404_games_list_is_stored_incomplete_and_asked_again(tmp_path: Path) -> None:
    class NoGames(FakeSofascore):
        def esports_games(self, event_id: int) -> dict[str, Any] | None:  # type: ignore[override]
            self.calls.append(f"games {event_id}")
            return None

    run(tmp_path, NoGames())
    assert db(tmp_path).execute("SELECT SUM(complete) FROM cs2_series").fetchone() == (
        0,
    )
    again = FakeSofascore()
    run(tmp_path, again)
    assert "games 11" in again.calls  # asked again, now complete
    assert db(tmp_path).execute("SELECT SUM(complete) FROM cs2_series").fetchone() == (
        2,
    )


@pytest.mark.parametrize("hours", [21])
def test_settle_without_a_store_still_grades(tmp_path: Path, hours: int) -> None:
    from tests.sofa.test_cs2_stages import FakeSofascore as SettleFake
    from tests.sofa.test_cs2_stages import write_snapshot

    write_snapshot(tmp_path)
    settle_cs2.settle(
        "2026-09-26",
        SettleFake(),
        str(tmp_path),  # type: ignore[arg-type]
        datetime(2026, 9, 26, hours, tzinfo=UTC),
    )
    rec = json.loads((tmp_path / "cs2" / "2026-09-26" / "settled.json").read_text())[
        "events"
    ]["1"]
    assert rec["state"] == "SETTLED" and "model_p" not in rec["graded"][0]


# --- round 2 --------------------------------------------------------------------


def test_a_deadline_after_the_seeds_is_partial_not_ok(tmp_path: Path) -> None:
    """Round 2: with a --team-id seed and every listing skipped by the
    deadline, the run said OK with zero series found."""
    fake = FakeSofascore()
    result = run(tmp_path, fake, max_minutes=0, extra_team_ids=[1])
    assert result["verdict"] == "PARTIAL"
    assert result["metrics"]["listing_skipped"] >= 1
    assert not any(c.startswith("listing") for c in fake.calls)


def test_a_dry_run_with_errors_is_partial(tmp_path: Path) -> None:
    from bet.sofa.errors import ProviderError

    class Flaky(FakeSofascore):
        def entity_events(self, team_id: int, kind: str, page: int) -> dict[str, Any]:
            if team_id == 3:
                raise ProviderError("HTTP 500")
            return super().entity_events(team_id, kind, page)

    assert run(tmp_path, Flaky(), dry_run=True)["verdict"] == "PARTIAL"


def test_a_late_page_error_keeps_the_newer_pages(tmp_path: Path) -> None:
    from bet.sofa.errors import ProviderError

    class LatePage(FakeSofascore):
        def entity_events(self, team_id: int, kind: str, page: int) -> dict[str, Any]:
            if team_id == 1 and page == 1:
                raise ProviderError("HTTP 500")
            data = super().entity_events(team_id, kind, page)
            if team_id == 1 and page == 0:
                data["hasNextPage"] = True
            return data

    result = run(tmp_path, LatePage(), hops=0)
    assert result["metrics"]["series_in_window"] >= 1  # page 0's series kept


def test_a_refusal_stops_the_run_and_cools_down(tmp_path: Path) -> None:
    """2026-09-28: 5 x 403 from Sofascore. The run stops, and the next one
    refuses to start for COOLDOWN unless forced."""
    from bet.sofa.errors import ProviderError

    class Refusing(FakeSofascore):
        def esports_game_lineups(self, game_id: int) -> dict[str, Any]:
            raise ProviderError("HTTP 403")

    first = run(tmp_path, Refusing())
    assert first["refused"] is True and first["verdict"] in ("PARTIAL", "FAILED")
    assert (tmp_path / "runs" / "cs2" / "backfill_cooldown.json").exists()
    fake = FakeSofascore()
    blocked = run(tmp_path, fake)
    assert blocked["verdict"] == "FAILED" and "cooling down" in blocked["error"]
    assert fake.calls == []  # not one request
    forced = run(tmp_path, FakeSofascore(), force=True)
    assert forced["verdict"] == "OK"
    later = run(
        tmp_path, FakeSofascore(), at=AT + backfill_cs2.COOLDOWN + timedelta(minutes=1)
    )
    assert later["verdict"] == "OK"


def test_a_refused_search_does_not_stop_known_teams(tmp_path: Path) -> None:
    """2026-09-28 19:41: /search/all answered 403 while /event and listings
    answered 200. Known teams (cached, or already in the store) need no
    search; the run goes on without it and is not a refusal of the run."""
    from bet.sofa.errors import ProviderError

    run(tmp_path, FakeSofascore(), hops=0)  # stores series of teams 1, 2

    class SearchBlocked(FakeSofascore):
        def search(self, q: str) -> dict[str, Any]:
            raise ProviderError("HTTP 403")

    # A new name no cache knows, next to the known ones.
    day = tmp_path / "runs" / "cs2" / "2026-09-28"
    day.mkdir(parents=True)
    (day / "snapshots.jsonl").write_text(
        json.dumps({"team1": "Nobody New", "team2": "magic", "lines": []}) + "\n"
    )
    blocked = SearchBlocked()
    result = run(tmp_path, blocked, hops=0)
    assert result["search_refused"] is True and result["refused"] is False
    assert result["metrics"]["teams_listed"] >= 2  # 1 and 2, from cache and store
    assert any(c.startswith("listing") for c in blocked.calls)
    assert not (tmp_path / "runs" / "cs2" / "backfill_cooldown.json").exists()
