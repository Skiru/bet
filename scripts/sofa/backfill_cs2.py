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


def is_refusal(exc: BaseException) -> bool:
    """Sofascore saying no, as opposed to a missing or broken record."""
    return isinstance(exc, ProviderError) and any(
        code in str(exc) for code in ("HTTP 403", "HTTP 429")
    )


def cooldown_path(runs_dir: str) -> Path:
    return Path(runs_dir) / "cs2" / COOLDOWN_FILE


def cooldown_until(runs_dir: str) -> datetime | None:
    path = cooldown_path(runs_dir)
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))["until"]
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return None


def start_cooldown(runs_dir: str, at: datetime, reason: str) -> None:
    path = cooldown_path(runs_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    until = (at + COOLDOWN).isoformat().replace("+00:00", "Z")
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
                self.refused = True
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
                self.refused = self.refused or is_refusal(exc)
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

    def resolve_team(self, name: str) -> int | None:
        """Superbet's team name -> the Sofascore CS entity, or None.

        A candidate counts only if its own listing holds Counter Strike events
        and its name clears the threshold on `esports_score`; two different
        entities that both do is ambiguous and neither is taken.
        """
        set_stage(STAGE)
        key = esports_name(name)
        cached = self.cache.get_entity(ENTITY_SPORT, key)
        if cached and cached.get("status") == "verified":
            return int(cached["sofascore_id"])
        if self.cache.get_entity_miss(ENTITY_SPORT, key):
            return None
        found = self.client.search(name) or {}
        teams = [
            r["entity"]
            for r in found.get("results") or []
            if r.get("type") == "team"
            and ((r.get("entity") or {}).get("sport") or {}).get("slug") == "esports"
        ][:MAX_CANDIDATES]
        fits: dict[int, tuple[float, dict[str, Any]]] = {}
        for team in teams:
            score = esports_score(key, esports_name(str(team.get("name") or "")))
            if score <= NAME_MATCH_THRESHOLD:
                continue
            page = self.listing_page(int(team["id"]), 0)
            if any(is_cs_event(e) for e in (page or {}).get("events") or []):
                fits[int(team["id"])] = (score, team)
        best = sorted(fits.items(), key=lambda kv: -kv[1][0])
        if not best:
            self.cache.save_entity_miss(ENTITY_SPORT, key)
            self.stats.add("teams_unresolved")
            return None
        if len(best) > 1 and best[0][1][0] == best[1][1][0]:
            # Two CS entities, equally named: not cached as a miss, since the
            # tie is about our scorer, not about Sofascore lacking the team.
            self.stats.add("teams_ambiguous")
            return None
        tid, (_, team) = best[0]
        self.cache.save_entity(
            ENTITY_SPORT,
            key,
            tid,
            str(team.get("name") or ""),
            "team",
            None,
            "verified",
        )
        return tid

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
                self.refused = True


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

    def finish(verdict: str, **extra: Any) -> dict[str, Any]:
        if bf.refused:
            start_cooldown(config.runs_dir, at, "HTTP 403/429 from Sofascore")
        return {
            "verdict": verdict,
            "breaker_open": bf.breaker_open,
            "refused": bf.refused,
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
    with ThreadPoolExecutor(max_workers=workers) as pool:
        resolved = pool.map(lambda n: bf.guarded("resolve", bf.resolve_team, n), names)
        team_ids.update(tid for tid in resolved if tid is not None)
        if not team_ids:
            why = (
                "stopped (deadline, breaker or refusal) before a seed resolved"
                if bf.stopped()
                else "no seed team resolved"
            )
            return finish("FAILED", error=why)
        stats.add("seed_teams", len(team_ids))
        frontier: set[int] = set(team_ids)
        for hop in range(hops + 1):
            batch = sorted(frontier - seen)
            seen.update(batch)
            nxt: set[int] = set()
            listings = pool.map(
                lambda t: bf.guarded("listing", bf.history, t, cutoff_ts), batch
            )
            for listed in listings:
                for e in listed or []:
                    events[int(e["id"])] = e
                    if hop < hops:
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
