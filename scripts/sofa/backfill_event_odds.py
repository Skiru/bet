#!/usr/bin/env python3
"""Fetch Sofascore's historical odds of finished games for the POSITION of
their lines (audit 2026-10-13 A7, operator O2).

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/backfill_event_odds.py \\
        --sport basketball --before 2026-10-13 --days 395 --max-minutes 7
    ... --report            # coverage of the cache, no network

The targets are the games the history curve's walk-forward replays
(bet.sofa.sport_confidence.parse_history over the cached listings, friendlies
out) that started in [before - days, before): first the games
fit_sport_confidence scores by default (its evenly thinned --max-games of the
fit window and --max-holdout-games of the holdout), then every other game of
the window, newest first. One request a game: `/event/{id}/odds/1/all`.

Cache: data/a7_odds/<sport>.jsonl, one asked game a line. Resumable: a game
with a record - an answer with markets, an answer without, or a 404 - is
never asked again; an error (403 / 429 / 5xx / timeout) writes nothing. Only
the full-game total and spread markets are kept, with their line and choice
names (bet.sofa.market_lines.trim_markets): no price is written, so no reader
of the cache can put one into a probability.

Same client, same token bucket, same bridge as SAMPLES, at most
SOFA_MAX_CONCURRENCY workers. The first 403 stops the run (exit 2): resume
later, never by refreshing tokens. --max-minutes: no new game is started
after that many minutes (short chunks keep the daily loops fed).
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
import threading
import time
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import sport_confidence as scf  # noqa: E402
from bet.sofa.client import SofascoreClient, breaker_tripped  # noqa: E402
from bet.sofa.comparability import competition_id  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.errors import CircuitOpenError, ProviderError  # noqa: E402
from bet.sofa.market_lines import (  # noqa: E402
    event_names,
    load_market_lines,
    trim_markets,
)
from bet.sofa.score_model import load_events  # noqa: E402
from bet.sofa.shadow import SPORTS  # noqa: E402

ODDS_SPORTS = ("basketball", "hockey")
DEFAULT_CACHE_DIR = "data/a7_odds"
# A league's size on Sofascore (uniqueTournament.userCount) as a tier: the
# coverage report only, never a filter.
TIERS = ((100_000, "A >=100k"), (10_000, "B 10k-100k"), (1_000, "C 1k-10k"),
         (0, "D <1k"))


def tier_of(user_count: int | None) -> str:
    for floor, name in TIERS:
        if (user_count or 0) >= floor:
            return name
    return TIERS[-1][1]


def thinned_ids(window: Sequence[scf.HistoryGame], max_games: int | None
                ) -> set[int]:
    """The games walk_forward_rows scores in a window (its own thinning)."""
    step = max(1, len(window) // max_games) if max_games else 1
    return {g.rating.event_id for i, g in enumerate(window) if i % step == 0}


def select_targets(history: Sequence[scf.HistoryGame], before_ts: int,
                   days: int, holdout_days: int, max_games: int | None,
                   max_holdout_games: int | None) -> list[dict[str, Any]]:
    """Every game of [before - days, before), the default fit's scored games
    first (prio 0), the rest after (prio 1), newest first inside each."""
    hold_ts = before_ts - holdout_days * 86400
    start_ts = before_ts - days * 86400
    fit_start = hold_ts - 365 * 86400
    fit_w = [g for g in history if fit_start <= g.rating.ts < hold_ts]
    hold_w = [g for g in history if hold_ts <= g.rating.ts < before_ts]
    first = thinned_ids(fit_w, max_games) | thinned_ids(hold_w, max_holdout_games)
    out: list[dict[str, Any]] = []
    for g in history:
        if not start_ts <= g.rating.ts < before_ts:
            continue
        e = g.event
        ut = ((e.get("tournament") or {}).get("uniqueTournament") or {})
        out.append({
            "event_id": g.rating.event_id, "ts": g.rating.ts,
            "competition_id": competition_id(e),
            "tournament": ut.get("name") or (e.get("tournament") or {}).get("name"),
            "user_count": ut.get("userCount"), "women": bool(g.rating.women),
            "home_names": event_names(e, "homeTeam"),
            "away_names": event_names(e, "awayTeam"),
            "prio": 0 if g.rating.event_id in first else 1})
    out.sort(key=lambda t: (t["prio"], -int(t["ts"]), int(t["event_id"])))
    return out


def asked_ids(cache: Path) -> set[int]:
    """Games with a record in the cache (an answer or a 404)."""
    out: set[int] = set()
    if not cache.exists():
        return out
    with cache.open(encoding="utf-8") as f:
        for raw in f:
            try:
                rec = json.loads(raw)
            except json.JSONDecodeError:
                continue  # a line cut by a kill: asked again
            if isinstance(rec, dict) and rec.get("status") in ("ok", "not_found"):
                out.add(int(rec["event_id"]))
    return out


def record(target: dict[str, Any], body: Any | None) -> dict[str, Any]:
    """The cache line of one answered game (None = a 404)."""
    rec = {k: target[k] for k in ("event_id", "ts", "competition_id",
                                  "tournament", "user_count", "women",
                                  "home_names", "away_names")}
    rec["fetched_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    if body is None:
        rec.update(status="not_found", markets=[])
    else:
        rec.update(status="ok", markets=trim_markets(body))
    return rec


class Runner:
    """One game at a time, from SOFA_MAX_CONCURRENCY worker threads."""

    def __init__(self, client: Any, cache: Path, deadline: float | None) -> None:
        self.client = client
        self.cache = cache
        self.deadline = deadline
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.timed_out = threading.Event()
        self.counts: Counter[str] = Counter()

    def fetch(self, target: dict[str, Any]) -> None:
        if self.stop.is_set() or self.timed_out.is_set():
            return
        if self.deadline is not None and time.monotonic() >= self.deadline:
            self.timed_out.set()
            return
        try:
            body = self.client.event_odds(int(target["event_id"]))
        except CircuitOpenError:
            self.stop.set()
            return
        except ProviderError as e:
            with self.lock:
                self.counts["errors"] += 1
                if "403" in str(e):
                    # a refusal means slow down: stop, resume later
                    self.counts["http_403"] += 1
                    self.stop.set()
            if breaker_tripped(self.client):
                self.stop.set()
            return
        rec = record(target, body)
        line = json.dumps(rec, ensure_ascii=False) + "\n"
        with self.lock:
            with self.cache.open("a", encoding="utf-8") as f:
                f.write(line)
            self.counts["done"] += 1
            self.counts[rec["status"]] += 1
            if rec["markets"]:
                self.counts["with_line_markets"] += 1
            if self.counts["done"] % 500 == 0:
                print(json.dumps({"ts_utc": datetime.now(UTC).isoformat(),
                                  **self.counts}), flush=True)


def coverage(targets: Iterable[dict[str, Any]], cache: Path) -> dict[str, Any]:
    """Asked / answered / with a total / with a spread, per tier, per prio
    and for the 20 biggest competitions of the window."""
    asked = asked_ids(cache)
    lines = load_market_lines(cache)
    agg: dict[str, Counter[str]] = defaultdict(Counter)
    comp_names: dict[str, str] = {}
    for t in targets:
        eid = int(t["event_id"])
        ml = lines.get(eid)
        keys = ["all", f"tier {tier_of(t.get('user_count'))}",
                f"prio {t['prio']}", f"comp {t.get('competition_id')}"]
        comp_names[f"comp {t.get('competition_id')}"] = str(t.get("tournament"))
        for k in keys:
            c = agg[k]
            c["games"] += 1
            c["asked"] += eid in asked
            c["total"] += bool(ml and ml.totals)
            c["spread"] += bool(ml and ml.home_handicaps)
            c["both"] += bool(ml and ml.totals and ml.home_handicaps)
    comps = sorted((k for k in agg if k.startswith("comp ")),
                   key=lambda k: -agg[k]["games"])[:20]
    return {
        "summary": {k: dict(v) for k, v in sorted(agg.items())
                    if not k.startswith("comp ")},
        "top_competitions": [{"competition": comp_names[k], **agg[k]}
                             for k in comps],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--sport", choices=ODDS_SPORTS, default="basketball")
    ap.add_argument("--before", required=True,
                    help="the fit's --before (UTC date): window end, exclusive")
    ap.add_argument("--days", type=int, default=395,
                    help="window length (fit 365 + holdout 30)")
    ap.add_argument("--holdout-days", type=int, default=30)
    ap.add_argument("--max-games", type=int, default=4000)
    ap.add_argument("--max-holdout-games", type=int, default=3000)
    ap.add_argument("--max-minutes", type=float, default=7.0,
                    help="start no new game after this many minutes")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--cache-dir", default=DEFAULT_CACHE_DIR)
    ap.add_argument("--events-db", default=None,
                    help="the DB the targets are read from (default SOFA_DB_PATH)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--report", action="store_true",
                    help="coverage of the cache over the targets; no network")
    args = ap.parse_args()

    config = SofaConfig.from_env()
    if not config.run_id:
        config = dataclasses.replace(
            config, run_id="backfill-odds-" + datetime.now(UTC).strftime(
                "%Y%m%dT%H%M%SZ"))
    cache_dir = Path(args.cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache = cache_dir / f"{args.sport}.jsonl"
    targets_path = cache_dir / f"{args.sport}_targets_{args.before}_{args.days}.json"
    if targets_path.exists():
        targets: list[dict[str, Any]] = json.loads(
            targets_path.read_text(encoding="utf-8"))
    else:
        sport = SPORTS[args.sport]
        events = load_events(args.events_db or config.db_path, sport)
        history = scf.parse_history(events, sport)
        targets = select_targets(history, scf.day_ts(args.before), args.days,
                                 args.holdout_days, args.max_games,
                                 args.max_holdout_games)
        targets_path.write_text(json.dumps(targets, ensure_ascii=False),
                                encoding="utf-8")
    if args.report:
        print(json.dumps(coverage(targets, cache), indent=1, ensure_ascii=False))
        return 0
    asked = asked_ids(cache)
    todo = [t for t in targets if int(t["event_id"]) not in asked]
    if args.limit is not None:
        todo = todo[: args.limit]
    print(json.dumps({"run_id": config.run_id, "sport": args.sport,
                      "targets": len(targets), "asked": len(asked),
                      "todo": len(todo),
                      "todo_prio0": sum(1 for t in todo if t["prio"] == 0)}),
          flush=True)
    if args.dry_run or not todo:
        return 0
    deadline = time.monotonic() + args.max_minutes * 60 if args.max_minutes else None
    runner = Runner(SofascoreClient(config), cache, deadline)
    with ThreadPoolExecutor(max_workers=max(1, config.max_concurrency)) as pool:
        list(pool.map(runner.fetch, todo))
    print(json.dumps({"final": True, "stopped": runner.stop.is_set(),
                      "timed_out": runner.timed_out.is_set(), **runner.counts}),
          flush=True)
    return 2 if runner.stop.is_set() else (1 if runner.counts["errors"] else 0)


if __name__ == "__main__":
    sys.exit(main())
