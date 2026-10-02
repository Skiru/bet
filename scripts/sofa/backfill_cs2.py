#!/usr/bin/env python3
"""CS2_BACKFILL - Sofascore CS2 history into data/sofa.db (cs2_* tables).

Results only. Historical Superbet prices do not exist (the offer API serves
the current board), so this fills the history a CS2 model or a base rate
would read - series, maps with overtime, per-player map rows - and cannot
speed up the price-against-outcome measurement, which only CS2's own daily
snapshots can feed.

Which teams: every team name in runs/sofa/cs2/*/snapshots.jsonl, found on
Sofascore as an esports team whose listing holds Counter Strike events (the
organisation is a separate entity per title), plus - with --hops 1, the
default - every opponent those teams met in the window, so a team's history
comes with its opponents' history too.

Per team: listing pages back to --days. Per finished CS series not already
complete in cs2_series: /event/{id}/esports-games, and one
/esports-game/{id}/lineups per finished map with complete statistics.
Resumable - a complete series is never asked again - and newest first, so a
run cut short by --max-minutes has filled the part that matters most.

Same client, same token bucket, same bridge as the pipeline; workers =
SOFA_MAX_CONCURRENCY. It cannot be faster than the pipeline and must not try.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/backfill_cs2.py --dry-run
    PYTHONPATH=src:. .venv/bin/python scripts/sofa/backfill_cs2.py --days 180

Exit: 0 OK, 1 PARTIAL (requests failed, or the deadline cut it short),
2 FAILED (no seeds, or the breaker opened before anything was stored).
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
for _path in (str(_REPO_ROOT), str(_REPO_ROOT / "src")):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from bet.sofa.cache import SofaCache  # noqa: E402
from bet.sofa.client import SofascoreClient  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.cs2 import SNAPSHOTS_FILE, esports_name, esports_score  # noqa: E402
from bet.sofa.cs2_store import (  # noqa: E402
    complete_ids,
    is_complete,
    is_cs_event,
    save_series,
)
from bet.sofa.db import get_connection, migrate  # noqa: E402
from bet.sofa.errors import CircuitOpenError, ProviderError  # noqa: E402
from bet.sofa.resolve import NAME_MATCH_THRESHOLD  # noqa: E402
from bet.sofa.stage import set_stage  # noqa: E402
from bet.sofa.timeutil import now  # noqa: E402

STAGE = "CS2_BACKFILL"
ENTITY_SPORT = "cs2"  # sofa_entity / sofa_entity_miss key space for CS teams
MAX_PAGES = 20  # 30 events a page; 600 series is years for a tier-2 team
MAX_CANDIDATES = 5
# 2026-09-28: Sofascore answered 403 after ~8 min at ~14 req/s through five
# windows - the first refusal on record. A refusal stops the run at once and
# is remembered on disk, so the next invocation does not simply start again at
# full width against a service that has just said no.
COOLDOWN = timedelta(hours=12)
COOLDOWN_FILE = "backfill_cooldown.json"
# /search/all alone refused (2026-09-28 19:41 and 20:01) while listings and
# maps answered 200. Remembered so the next runs do not search at all: five
# parallel 403s trip the client's shared breaker, which then refuses the
# listings too - the 20:01 run skipped 402 of them that way.
SEARCH_COOLDOWN = timedelta(hours=6)
# How many 403/429 in one run make it a refusal. A single one is not: at
# 20:21Z one listing answered 403 (retry-after 0) among 39 answering 200, and
# stopping on it cost the run 1,461 series. The one skipped item is retried
# next run; three in a run is Sofascore saying no.
REFUSALS_TO_STOP = 3
SEARCH_COOLDOWN_FILE = "search_cooldown.json"


def is_refusal(exc: BaseException) -> bool:
    """Sofascore saying no, as opposed to a missing or broken record."""
    return isinstance(exc, ProviderError) and any(
        code in str(exc) for code in ("HTTP 403", "HTTP 429")
    )


def cooldown_path(runs_dir: str) -> Path:
    return Path(runs_dir) / "cs2" / COOLDOWN_FILE


def cooldown_until(runs_dir: str, name: str = COOLDOWN_FILE) -> datetime | None:
    path = Path(runs_dir) / "cs2" / name
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))["until"]
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return None


def start_cooldown(
    runs_dir: str,
    at: datetime,
    reason: str,
    name: str = COOLDOWN_FILE,
    length: timedelta = COOLDOWN,
) -> None:
    path = Path(runs_dir) / "cs2" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    until = (at + length).isoformat().replace("+00:00", "Z")
    path.write_text(json.dumps({"until": until, "reason": reason}), encoding="utf-8")


def seed_names(runs_dir: str) -> list[str]:
    """Every team name Superbet has put on a CS2 snapshot, sorted."""
    names: set[str] = set()
    pattern = str(Path(runs_dir) / "cs2" / "*" / SNAPSHOTS_FILE)
    for path in glob.glob(pattern):
        for raw in Path(path).read_text(encoding="utf-8").splitlines():
            if not raw.strip():
                continue
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError:
                continue
            names.update(n for n in (rec.get("team1"), rec.get("team2")) if n)
    return sorted(names)


@dataclass
class Stats:
    lock: threading.Lock = field(default_factory=threading.Lock)
    counts: dict[str, int] = field(default_factory=dict)

    def add(self, key: str, n: int = 1) -> None:
        with self.lock:
            self.counts[key] = self.counts.get(key, 0) + n


class Backfill:
    def __init__(
        self,
        client: SofascoreClient,
        cache: SofaCache,
        db_path: str,
        deadline: float,
        stats: Stats,
    ) -> None:
        self.client, self.cache, self.db_path = client, cache, db_path
        self.deadline, self.stats = deadline, stats
        self.breaker_open = False
        # A 403/429 from Sofascore. Checked by every task, so one refusal
        # stops the pool - the client's breaker alone may not trip when other
        # routes keep answering 200 and reset its failure count.
        self.refused = False
        self.refusals = 0
        self._refusal_lock = threading.Lock()
        # A 403 from /search/all alone. Seen 2026-09-28 19:41: search refused
        # while /event and the listings still answered 200. It stops further
        # searching, not the run - known teams need no search at all.
        self.search_refused = False
        # Every CS team already in cs2_series, id -> the names it played under.
        self.stored_teams: dict[int, set[str]] = {}

    # --- listings ------------------------------------------------------------

    def listing_page(self, team_id: int, page: int) -> dict[str, Any] | None:
        data = self.cache.get_entity_events(team_id, "last", page)
        if data is not None:
            return data
        if self.cache.get_listing_miss(team_id, "last", page):
            return None
        data = self.client.entity_events(team_id, "last", page)
        if data:
            self.cache.save_entity_events(team_id, "last", page, data)
        else:
            self.cache.save_listing_miss(team_id, "last", page)
        return data

    def note_refusal(self) -> None:
        """One 403/429 on a listing or a map; the third in a run stops it."""
        with self._refusal_lock:
            self.refusals += 1
            if self.refusals >= REFUSALS_TO_STOP:
                self.refused = True

    def stopped(self) -> bool:
        return self.breaker_open or self.refused or time.monotonic() > self.deadline

    def guarded(self, task: str, fn: Any, *args: Any) -> Any:
        """Run one discovery task; a failure is counted, never the whole run.

        Review 2026-09-28: a single 403 or 5xx from a search or a listing page
        escaped pool.map and killed discovery with nothing stored.
        """
        set_stage(STAGE)
        if self.stopped():
            self.stats.add(f"{task}_skipped")
            return None
        try:
            return fn(*args)
        except CircuitOpenError:
            self.breaker_open = True
            self.stats.add("errors")
        except Exception as exc:
            self.stats.add("errors")
            self.stats.add(f"{task}_errors")
            if is_refusal(exc):
                if task == "resolve":
                    self.search_refused = True
                else:
                    self.note_refusal()
        return None

    def history(self, team_id: int, cutoff_ts: int) -> list[dict[str, Any]]:
        """Finished CS series of this team since the cutoff, all pages."""
        # Every pool task sets it: a worker thread starts from the ContextVar's
        # default, and on 2026-09-28 every backfill request was logged "CLIENT".
        set_stage(STAGE)
        out: list[dict[str, Any]] = []
        for page in range(MAX_PAGES):
            if self.stopped():
                break
            try:
                data = self.listing_page(team_id, page)
            except CircuitOpenError:
                self.breaker_open = True
                self.stats.add("errors")
                break
            except Exception as exc:
                # Keep the pages already read; a late page failing must not
                # discard the team's newer history (round 2 review).
                self.stats.add("errors")
                self.stats.add("listing_errors")
                if is_refusal(exc):
                    self.note_refusal()
                break
            events = (data or {}).get("events") or []
            cs = [e for e in events if is_cs_event(e)]
            out.extend(
                e
                for e in cs
                if int(e.get("startTimestamp") or 0) >= cutoff_ts
                and (e.get("status") or {}).get("type") == "finished"
            )
            oldest = min((int(e.get("startTimestamp") or 0) for e in events), default=0)
            if not data or not data.get("hasNextPage") or oldest < cutoff_ts:
                break
        return out

    # --- teams -----------------------------------------------------------------

    def cached_team(self, name: str) -> int | None:
        """A team already verified in an earlier run - no request at all."""
        cached = self.cache.get_entity(ENTITY_SPORT, esports_name(name))
        if cached and cached.get("status") == "verified":
            return int(cached["sofascore_id"])
        return None

    def resolve_team(self, name: str) -> list[int]:
        """Superbet's team name -> the Sofascore CS entities to seed with.

        A candidate counts only if it is known to play Counter Strike - its
        own listing holds CS events, it is a side of a CS event the search
        itself returned, or it is a side of a series already in cs2_series -
        and its name clears the threshold on `esports_score`. One best
        candidate is cached as the name's entity. Several equally named CS
        entities are all seeded and none is cached: a backfill only stores
        series by their own event id, so a namesake's history is real CS
        history, never a misattribution - but which of them Superbet means is
        not known, so the name maps to none of them.
        """
        set_stage(STAGE)
        key = esports_name(name)
        cached = self.cached_team(name)
        if cached is not None:
            return [cached]
        fits: dict[int, tuple[float, str]] = {}
        # The store first, at no request: on 2026-10-02 "DEPO", "Rush",
        # "STATE", "Grêmio Esports" and "THUNDER dOWNUNDER" were all in
        # cs2_series as opponents while their Superbet names stayed misses.
        for tid, names in self.stored_teams.items():
            if not names:
                continue
            score = max(esports_score(key, esports_name(n)) for n in names)
            if score > NAME_MATCH_THRESHOLD:
                fits[tid] = (score, max(names, key=len))
        if fits:
            self.stats.add("teams_from_store")
        searched = False
        if self.search_refused:
            self.stats.add("search_skipped")
        elif not self.cache.get_entity_miss(ENTITY_SPORT, key):
            searched = True
            self._search_fits(name, key, fits)
        best = sorted(fits.items(), key=lambda kv: -kv[1][0])
        if not best:
            if searched:
                self.cache.save_entity_miss(ENTITY_SPORT, key)
                self.stats.add("teams_unresolved")
            return []
        if len(best) > 1 and best[0][1][0] == best[1][1][0]:
            # Equally named CS entities: not cached as a miss, since the tie
            # is about our scorer, not about Sofascore lacking the team.
            tied = [tid for tid, (s, _) in best if s == best[0][1][0]]
            self.stats.add("teams_ambiguous")
            self.stats.add("teams_ambiguous_seeded", len(tied))
            return tied
        tid, (_, team_name) = best[0]
        self.cache.save_entity(
            ENTITY_SPORT, key, tid, team_name, "team", None, "verified"
        )
        return [tid]

    def _search_fits(
        self, name: str, key: str, fits: dict[int, tuple[float, str]]
    ) -> None:
        """Add /search/all's CS candidates for this name to `fits`."""
        found = self.client.search(name) or {}
        results = found.get("results") or []
        teams = [
            r["entity"]
            for r in results
            if r.get("type") == "team"
            and ((r.get("entity") or {}).get("sport") or {}).get("slug") == "esports"
        ][:MAX_CANDIDATES]
        for team in teams:
            tid = int(team["id"])
            team_name = str(team.get("name") or "")
            score = esports_score(key, esports_name(team_name))
            if score <= NAME_MATCH_THRESHOLD or tid in fits:
                continue
            page = self.listing_page(tid, 0)
            if any(is_cs_event(e) for e in (page or {}).get("events") or []):
                fits[tid] = (score, team_name)
        # /search/all answers 20 results across every sport, so a common name
        # ("Gremio", "Huskies", "5Star eSports") can have its CS team pushed
        # out by football clubs while the team's CS events are still listed
        # (2026-10-02: 36 of 176 seed names were cached as misses that way or
        # were not on Sofascore at all). A side of a CS event is a CS team.
        for r in results:
            event = r.get("entity") or {}
            if r.get("type") != "event" or not is_cs_event(event):
                continue
            for side in ("homeTeam", "awayTeam"):
                team = event.get(side) or {}
                if not team.get("id") or int(team["id"]) in fits:
                    continue
                team_name = str(team.get("name") or "")
                score = esports_score(key, esports_name(team_name))
                if score > NAME_MATCH_THRESHOLD:
                    fits[int(team["id"])] = (score, team_name)
                    self.stats.add("teams_from_search_events")

    # --- series ----------------------------------------------------------------

    def fetch_series(self, event: dict[str, Any], at: datetime) -> None:
        set_stage(STAGE)
        if self.stopped():
            self.stats.add("skipped_deadline_or_breaker")
            return
        eid = int(event["id"])
        try:
            games = (self.client.esports_games(eid) or {}).get("games") or []
            lineups: dict[int, dict[str, Any] | None] = {}
            for g in games:
                finished = (g.get("status") or {}).get("type") == "finished"
                if finished and g.get("hasCompleteStatistics"):
                    lineups[int(g["id"])] = self.client.esports_game_lineups(
                        int(g["id"])
                    )
            age = at - datetime.fromtimestamp(
                int(event.get("startTimestamp") or 0), at.tzinfo
            )
            complete = is_complete(event, games, lineups, age)
            with get_connection(self.db_path) as conn:
                save_series(
                    conn,
                    event,
                    games,
                    lineups,
                    at.isoformat().replace("+00:00", "Z"),
                    complete,
                )
            self.stats.add("series_stored")
            self.stats.add("series_complete" if complete else "series_incomplete")
            self.stats.add("maps_stored", len(games))
            self.stats.add("lineups_fetched", len(lineups))
        except CircuitOpenError:
            self.breaker_open = True
            self.stats.add("errors")
        except Exception as exc:
            self.stats.add("errors")
            if is_refusal(exc):
                self.note_refusal()


def run(
    client: SofascoreClient,
    config: SofaConfig,
    *,
    days: int,
    hops: int,
    max_minutes: float,
    dry_run: bool,
    extra_team_ids: list[int],
    at: datetime,
    force: bool = False,
) -> dict[str, Any]:
    migrate(config.db_path)
    until = cooldown_until(config.runs_dir)
    if until is not None and at < until and not force:
        return {
            "verdict": "FAILED",
            "error": f"cooling down after a Sofascore refusal until {until.isoformat()}"
            " (--force to override)",
            "metrics": {},
        }
    stats = Stats()
    bf = Backfill(
        client,
        SofaCache(config),
        config.db_path,
        time.monotonic() + 60 * max_minutes,
        stats,
    )
    cutoff_ts = int((at - timedelta(days=days)).timestamp())

    search_until = cooldown_until(config.runs_dir, SEARCH_COOLDOWN_FILE)
    if search_until is not None and at < search_until:
        bf.search_refused = True  # known teams only this run; no search at all
        stats.add("search_cooling_down", 1)

    def finish(verdict: str, **extra: Any) -> dict[str, Any]:
        if bf.refused:
            start_cooldown(config.runs_dir, at, "HTTP 403/429 from Sofascore")
        if bf.search_refused and not stats.counts.get("search_cooling_down"):
            start_cooldown(
                config.runs_dir,
                at,
                "HTTP 403/429 from /search/all",
                SEARCH_COOLDOWN_FILE,
                SEARCH_COOLDOWN,
            )
        return {
            "verdict": verdict,
            "breaker_open": bf.breaker_open,
            "refused": bf.refused,
            "search_refused": bf.search_refused,
            "refusals": bf.refusals,
            **extra,
            "metrics": stats.counts,
        }

    names = seed_names(config.runs_dir)
    stats.add("seed_names", len(names))
    team_ids: set[int] = set(extra_team_ids)
    workers = max(1, config.max_concurrency)
    events: dict[int, dict[str, Any]] = {}
    seen: set[int] = set()
    # Discovery runs on the same pool width as the fetch. One request at a
    # time leaves every other bridge window idle and pays a poll cycle per
    # request - measured 2-4 s a listing page here, against ~0.35 s at width.
    # Known teams first, with no request: those verified in earlier runs, and
    # every team the store already holds. Only names never seen are searched.
    unknown: list[str] = []
    for name in names:
        tid = bf.cached_team(name)
        if tid is not None:
            team_ids.add(tid)
        else:
            unknown.append(name)
    stats.add("seed_cached", len(team_ids))
    with get_connection(config.db_path) as conn:
        for tid, tname in conn.execute(
            "SELECT home_id, home_name FROM cs2_series"
            " UNION SELECT away_id, away_name FROM cs2_series"
        ):
            if tid:
                played_as = bf.stored_teams.setdefault(int(tid), set())
                if tname:
                    played_as.add(str(tname))
        stored = set(bf.stored_teams)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        resolved = pool.map(
            lambda n: bf.guarded("resolve", bf.resolve_team, n), unknown
        )
        # guarded() answers None for a resolve that raised.
        team_ids.update(tid for tids in resolved for tid in tids or [])
        if not team_ids and not stored:
            why = (
                "stopped (deadline, breaker or refusal) before a seed resolved"
                if bf.stopped() or bf.search_refused
                else "no seed team resolved"
            )
            return finish("FAILED", error=why)
        stats.add("seed_teams", len(team_ids))
        stats.add("stored_teams", len(stored - team_ids))
        # Opponents are added only around the seeds: the stored teams are
        # already the earlier runs' one-hop closure, and expanding them again
        # would walk the whole scene.
        expand = set(team_ids)
        frontier: set[int] = set(team_ids) | stored
        for hop in range(hops + 1):
            batch = sorted(frontier - seen)
            seen.update(batch)
            nxt: set[int] = set()
            listings = pool.map(
                lambda t: bf.guarded("listing", bf.history, t, cutoff_ts), batch
            )
            for team, listed in zip(batch, listings, strict=True):
                for e in listed or []:
                    events[int(e["id"])] = e
                    if hop < hops and team in expand:
                        for side in ("homeTeam", "awayTeam"):
                            oid = int((e.get(side) or {}).get("id") or 0)
                            if oid and oid not in seen:
                                nxt.add(oid)
            frontier = nxt
    stats.add("teams_listed", len(seen))
    stats.add("series_in_window", len(events))
    if (bf.breaker_open or bf.refused) and not events:
        return finish("FAILED", error="stopped by Sofascore during discovery")

    with get_connection(config.db_path) as conn:
        done = complete_ids(conn, events, int(at.timestamp()))
    todo = sorted(
        (e for i, e in events.items() if i not in done),
        key=lambda e: -int(e.get("startTimestamp") or 0),
    )
    stats.add("series_already_complete", len(done))
    stats.add("series_to_fetch", len(todo))

    # Anything skipped or failed is PARTIAL, whatever phase it happened in:
    # a deadline hit during discovery once reported OK with nothing found.
    def degraded() -> bool:
        return bool(
            stats.counts.get("errors")
            or any(k.endswith("_skipped") for k in stats.counts)
            or stats.counts.get("skipped_deadline_or_breaker")
            or bf.refused
        )

    if dry_run:
        return finish("PARTIAL" if degraded() else "OK", dry_run=True)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(lambda e: bf.fetch_series(e, at), todo))

    if (bf.breaker_open or bf.refused) and not stats.counts.get("series_stored"):
        return finish("FAILED")
    return finish("PARTIAL" if degraded() else "OK")


def main() -> int:
    set_stage(STAGE)
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--days", type=int, default=180)
    ap.add_argument(
        "--hops",
        type=int,
        choices=(0, 1),
        default=1,
        help="1 = also every opponent the seed teams met",
    )
    # Short by default and resumable: the one refusal on record came after
    # ~8 minutes at full width. Run it again later for more.
    ap.add_argument("--max-minutes", type=float, default=6.0)
    ap.add_argument(
        "--force", action="store_true", help="ignore a cooldown after a refusal"
    )
    ap.add_argument(
        "--team-id",
        type=int,
        action="append",
        default=[],
        help="an extra Sofascore CS team id to seed with",
    )
    ap.add_argument(
        "--dry-run", action="store_true", help="resolve and list only; fetch no maps"
    )
    args = ap.parse_args()
    config = SofaConfig.from_env()
    result = run(
        SofascoreClient(config),
        config,
        days=args.days,
        hops=args.hops,
        max_minutes=args.max_minutes,
        dry_run=args.dry_run,
        extra_team_ids=args.team_id,
        at=now(),
        force=args.force,
    )
    print(
        "SOFA_SUMMARY: " + json.dumps({"stage": "CS2_BACKFILL", **result}), flush=True
    )
    return {"OK": 0, "PARTIAL": 1}.get(str(result["verdict"]), 2)


if __name__ == "__main__":
    sys.exit(main())
