"""Football per-player statistics (`/event/{id}/lineups`) for the leagues and
teams Superbet prices player markets on.

SAMPLES asks /lineups only for the sides of a fixture that carries player
markets that day, and only for the events of that fixture's sample, so the
player history grows a fixture at a time (2026-10-02: 944 of 3,051 matches of
the 135 player-market teams in the last 365 days had it). This fills the rest,
so a player model can be measured and fitted on more than a week of rows.

Scope, from the day artifacts on disk (no request): every football fixture
whose 04_offer.json carries a `player_*` rung, joined to 02_fixtures.json for
its competition and sides. A target is a finished event in the last --days of
one of those competitions (friendlies out, as in SAMPLES) or of one of those
teams, whose lineups were never asked. An event Sofascore marks
`hasEventPlayerStatistics: false` is not asked.

An event with no sofa_event_stats row at all is asked /statistics and
/incidents first, exactly as backfill_event_stats.py would: writing the
lineups alone would create a row whose NULL statistics read as "asked, 404",
and the team backfill would then never ask for them.

Same client, same token bucket, same bridge as the pipeline; workers =
SOFA_MAX_CONCURRENCY. Resumable and newest first; run in chunks.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/backfill_football_lineups.py \\
        --dry-run
    PYTHONPATH=src:. .venv/bin/python scripts/sofa/backfill_football_lineups.py \\
        --days 365 --max-minutes 7

Exit: 0 OK, 1 PARTIAL (requests failed), 2 FAILED (the breaker opened).
"""

from __future__ import annotations

import argparse
import dataclasses
import glob
import json
import sys
import threading
import time
from collections.abc import Iterable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bet.sofa.cache import PROVISIONAL_FETCH_HOURS, SofaCache
from bet.sofa.client import SofascoreClient
from bet.sofa.config import SofaConfig
from bet.sofa.errors import CircuitOpenError, ProviderError
from bet.sofa.samples import FRIENDLY_COMPETITION_IDS
from scripts.sofa.backfill_event_stats import (
    MAX_BARREN_MISSES,
    _competition,
    _iter_listings,
    _sport_events,
)
from scripts.sofa.backfill_listings import read_only_connection


def player_market_scope(runs_dir: str) -> tuple[set[int], set[int]]:
    """(competition ids, team ids) of every football fixture whose offer
    carried a player market, over every day on disk."""
    comps: set[int] = set()
    teams: set[int] = set()
    for offer_path in glob.glob(str(Path(runs_dir) / "*" / "04_offer.json")):
        fixtures_path = Path(offer_path).with_name("02_fixtures.json")
        try:
            offer = json.loads(Path(offer_path).read_text())
            fixtures = json.loads(fixtures_path.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        by_id = {fx.get("sofascore_event_id"): fx for fx in fixtures
                 if isinstance(fx, dict)}
        for rec in offer if isinstance(offer, list) else []:
            rungs = rec.get("rungs") or []
            if not any(str(r.get("market", "")).startswith("player_") for r in rungs):
                continue
            fx = by_id.get(rec.get("sofascore_event_id"))
            if not fx or fx.get("sport") != "football":
                continue
            if isinstance(fx.get("competition_id"), int):
                comps.add(int(fx["competition_id"]))
            for side in ("home_entity_id", "away_entity_id"):
                if isinstance(fx.get(side), int):
                    teams.add(int(fx[side]))
    return comps - FRIENDLY_COMPETITION_IDS, teams


@dataclass(frozen=True)
class Target:
    event: dict[str, Any]
    needs_stats: bool  # no sofa_event_stats row at all


def _states(db_path: str) -> dict[int, tuple[bool, bool]]:
    """Event id -> (statistics column written, lineups column written).

    A row exists for every id returned; NULL statistics on an existing row is
    the asked-and-404 answer for football, never re-asked here.
    """
    conn = read_only_connection(db_path)
    try:
        return {
            int(r["sofascore_event_id"]): (
                r["statistics_json"] is not None, r["lineups_json"] is not None)
            for r in conn.execute(
                "SELECT sofascore_event_id, statistics_json, lineups_json "
                "FROM sofa_event_stats")
        }
    finally:
        conn.close()


def _empty(raw: str | None) -> bool:
    return raw in (None, "", "{}", "null")


def barren_lineup_competitions(
    events: Iterable[dict[str, Any]], db_path: str
) -> set[int | None]:
    """Competitions whose asked lineups are all empty, MAX_BARREN_MISSES+."""
    ids = {int(e["id"]): _competition(e) for e in events}
    hits: dict[int | None, int] = {}
    misses: dict[int | None, int] = {}
    conn = read_only_connection(db_path)
    try:
        for r in conn.execute(
            "SELECT sofascore_event_id, lineups_json FROM sofa_event_stats "
            "WHERE lineups_json IS NOT NULL"
        ):
            eid = int(r["sofascore_event_id"])
            if eid not in ids:
                continue
            bucket = misses if _empty(r["lineups_json"]) else hits
            bucket[ids[eid]] = bucket.get(ids[eid], 0) + 1
    finally:
        conn.close()
    return {c for c, n in misses.items() if n >= MAX_BARREN_MISSES and not hits.get(c)}


def select_targets(
    events: Iterable[dict[str, Any]],
    states: dict[int, tuple[bool, bool]],
    comps: set[int],
    teams: set[int],
    since_ts: int,
    until_ts: int,
    barren: set[int | None],
) -> list[Target]:
    """Events in scope whose lineups were never asked, newest first."""
    out: list[Target] = []
    for e in events:
        ts = int(e.get("startTimestamp") or 0)
        if not since_ts <= ts <= until_ts:
            continue
        comp = _competition(e)
        if comp in FRIENDLY_COMPETITION_IDS or comp in barren:
            continue
        sides = {(e.get(s) or {}).get("id") for s in ("homeTeam", "awayTeam")}
        if comp not in comps and not sides & teams:
            continue
        if e.get("hasEventPlayerStatistics") is False:
            continue
        state = states.get(int(e["id"]))
        if state is not None and state[1]:
            continue  # lineups already asked
        out.append(Target(e, needs_stats=state is None))
    return sorted(out, key=lambda t: -int(t.event.get("startTimestamp") or 0))


class Backfill:
    def __init__(self, client: Any, cache: Any, deadline: float | None) -> None:
        self.client, self.cache, self.deadline = client, cache, deadline
        self.stop = threading.Event()
        self.timed_out = threading.Event()
        self.lock = threading.Lock()
        self.counts = {"done": 0, "lineups": 0, "no_lineups": 0, "stats": 0,
                       "no_stats": 0, "errors": 0, "skipped_barren": 0}
        self.hits: dict[int | None, int] = {}
        self.misses: dict[int | None, int] = {}

    def _barren(self, comp: int | None) -> bool:
        with self.lock:
            return (self.misses.get(comp, 0) >= MAX_BARREN_MISSES
                    and not self.hits.get(comp))

    def fetch(self, target: Target) -> None:
        if self.stop.is_set() or self.timed_out.is_set():
            return
        if self.deadline is not None and time.monotonic() >= self.deadline:
            self.timed_out.set()
            return
        comp = _competition(target.event)
        if self._barren(comp):
            with self.lock:
                self.counts["skipped_barren"] += 1
            return
        eid = int(target.event["id"])
        try:
            if target.needs_stats:
                stats = self.client.event_statistics(eid)
                incidents = self.client.event_incidents(eid)
                self.cache.save_event_stats(eid, stats, incidents, "finished")
                with self.lock:
                    self.counts["stats" if stats else "no_stats"] += 1
            got = self.client.event_lineups(eid)
        except CircuitOpenError:
            self.stop.set()
            return
        except ProviderError:
            with self.lock:
                self.counts["errors"] += 1
            return
        ok = isinstance(got, dict) and bool(got)
        self.cache.save_event_lineups(eid, got if ok else None, "finished")
        with self.lock:
            self.counts["done"] += 1
            self.counts["lineups" if ok else "no_lineups"] += 1
            bucket = self.hits if ok else self.misses
            bucket[comp] = bucket.get(comp, 0) + 1
            if self.counts["done"] % 500 == 0:
                print(json.dumps({"ts_utc": datetime.now(UTC).isoformat(),
                                  **self.counts}), flush=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--days", type=int, default=365)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max-minutes", type=float, default=None,
                    help="start no new event after this many minutes")
    args = ap.parse_args()

    config = SofaConfig.from_env()
    if not config.run_id:
        config = dataclasses.replace(
            config,
            run_id="backfill-lineups-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ"),
        )
    comps, teams = player_market_scope(config.runs_dir)
    now = int(time.time())
    events = _sport_events(_iter_listings(config.db_path), "football")
    barren = barren_lineup_competitions(events, config.db_path)
    targets = select_targets(
        events, _states(config.db_path), comps, teams,
        now - args.days * 86400, now - int(PROVISIONAL_FETCH_HOURS * 3600), barren,
    )
    if args.limit is not None:
        targets = targets[: args.limit]
    needs_stats = sum(t.needs_stats for t in targets)
    print(json.dumps({
        "run_id": config.run_id, "days": args.days,
        "competitions": len(comps), "teams": len(teams),
        "targets": len(targets), "targets_without_stats_row": needs_stats,
        "requests": len(targets) + 2 * needs_stats,
        "barren_competitions_skipped": len(barren),
    }), flush=True)
    if args.dry_run or not targets:
        return 0

    deadline = (
        time.monotonic() + args.max_minutes * 60 if args.max_minutes else None
    )
    runner = Backfill(SofascoreClient(config), SofaCache(config), deadline)
    with ThreadPoolExecutor(max_workers=max(1, config.max_concurrency)) as pool:
        list(pool.map(runner.fetch, targets))
    print(json.dumps({"final": True, "circuit_open": runner.stop.is_set(),
                      "timed_out": runner.timed_out.is_set(),
                      "targets": len(targets), **runner.counts}), flush=True)
    return 2 if runner.stop.is_set() else (1 if runner.counts["errors"] else 0)


if __name__ == "__main__":
    sys.exit(main())
