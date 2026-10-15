#!/usr/bin/env python3
"""Settle Superbet's recorded prices of the tennis market "1. set - będzie
prowadzić po 2 gemach", selection "po 2 - Remis" (set 1 stands 1:1 after its
first two games), against the point-by-point. Read-only evidence: nothing is
wired into the pipeline.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_tennis_draw_after_two.py \\
        --date 2026-10-14 --date 2026-10-15 [--fetch [--max-minutes 5]] \\
        [--k-games 40] [--threshold 0.80] [--reps 2000] [--md-out f] [--json-out f]

Prices: runs/sofa/<d>/unmapped_prices/*.jsonl.gz (bet.sofa.unmapped_prices;
every OFFER run of the day appends a file). Each record already carries the
Sofascore event id RESOLVE paired the Superbet event with, so the mapping is
the pipeline's own. Per event the LAST price fetched strictly before the
earliest start clock is kept - the earliest of 02_fixtures `kickoff_utc` /
`superbet_kickoff_utc`, 04_offer `superbet_started_utc` /
`superbet_kickoff_seen_utc`, fixture_status `start_utc` and the cached
Sofascore /event `startTimestamp`; an odd in Superbet's live offer state
(`offerStateId` 2) or not `active` is never read.

Outcome: Sofascore /event (sofa_event_detail) for the status, /point-by-point
(sofa_event_extra) for the games. The selection wins when set 1 stands 1:1
after game 2 - both held OR both broken. Retired / walkover / cancelled is a
refund (VOID), as SETTLE treats them (settle.REFUND_REASONS; a retirement
after set 1's second game is counted apart, RETIRED_AFTER_2 - Superbet may
stand a market already decided); a match not yet finished (also one
suspended, e.g. by rain) is PENDING; a finished match with no
point-by-point, or one whose set-1 games disagree with the set-1 score, is
NOT_FOUND / MISMATCH. None of them enters the money.

Forecast: scripts/sofa/measure_tennis_game_order.py's serve model, as of the
match (only matches started before it are learnt): hold_A, hold_B from the
players' earlier service / return games. P(1:1) = hA hB + (1-hA)(1-hB);
that script's own "draw" row is hA hB (both hold) and is reported beside it.

--fetch asks the bridge (same client, token bucket and breaker as the
pipeline) for /event and /point-by-point of exactly the selected events that
should have ended (earliest start > 2 h ago) and lack a finished record,
writing them into the cache (sofa_event_detail, sofa_event_extra) like the
pipeline / backfill_event_extra.py would; it stops on the first refusal.

ROI is at Superbet's price, stake 1 on every graded selection; the 95%
interval is a match bootstrap (one selection per match, so events are
resampled). Exit 0, 1 when --fetch was refused, 2 on a crash.
"""

from __future__ import annotations

import argparse
import json
import random
import sqlite3
import sys
import time
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import point_by_point as pbp  # noqa: E402
from bet.sofa import unmapped_prices  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402
from scripts.sofa.measure_tennis_game_order import (  # noqa: E402
    Row,
    hold_rate,
    learn,
    load_pbps,
    load_rows,
)

MARKET = "1. set - będzie prowadzić po 2 gemach"
SELECTION = "po 2 - Remis"
LIVE_OFFER_STATE = "2"
FETCH_AFTER = timedelta(hours=2)


@dataclass(frozen=True)
class Quote:
    event_id: int
    price: float
    fetched_at: datetime


@dataclass(frozen=True)
class Outcome:
    status: str  # GRADED / VOID / PENDING / NOT_FOUND / MISMATCH
    won: int | None = None
    reason: str = ""


def _ts(raw: object) -> datetime | None:
    if raw in (None, ""):
        return None
    if isinstance(raw, (int, float)):
        return datetime.fromtimestamp(float(raw), UTC)
    try:
        got = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    return got if got.tzinfo else got.replace(tzinfo=UTC)


def is_selection(rec: Mapping[str, Any]) -> bool:
    """The draw-after-2-games selection of set 1, pre-match and active."""
    return (rec.get("marketName") == MARKET and rec.get("name") == SELECTION
            and str(rec.get("offerStateId")) != LIVE_OFFER_STATE
            and rec.get("status", "active") == "active"
            and rec.get("sofascore_event_id") is not None
            and rec.get("price") is not None)


def last_prematch(records: Iterable[Mapping[str, Any]],
                  starts: Mapping[int, datetime]) -> tuple[dict[int, Quote], int]:
    """Per event the last selection price fetched strictly before its start;
    and how many records were dropped as at or after the start (or with no
    start clock at all)."""
    out: dict[int, Quote] = {}
    dropped = 0
    for rec in records:
        if not is_selection(rec):
            continue
        eid = int(rec["sofascore_event_id"])
        at = _ts(rec.get("fetched_at_utc"))
        start = starts.get(eid)
        if at is None or start is None or at >= start:
            dropped += 1
            continue
        q = Quote(eid, float(rec["price"]), at)
        if eid not in out or at >= out[eid].fetched_at:
            out[eid] = q
    return out, dropped


def start_clocks(run_dir: Path) -> dict[int, list[datetime]]:
    """Every start clock the day's artifacts hold, per Sofascore event."""
    clocks: dict[int, list[datetime]] = {}

    def add(eid: object, raw: object) -> None:
        t = _ts(raw)
        if eid is not None and t is not None:
            clocks.setdefault(int(str(eid)), []).append(t)

    for name, keys in (("02_fixtures.json", ("kickoff_utc", "superbet_kickoff_utc")),
                       ("04_offer.json", ("superbet_started_utc",
                                          "superbet_kickoff_seen_utc"))):
        path = run_dir / name
        if path.exists():
            for row in json.loads(path.read_text(encoding="utf-8")):
                for k in keys:
                    add(row.get("sofascore_event_id"), row.get(k))
    status = run_dir / "fixture_status.json"
    if status.exists():
        for eid, row in (json.loads(status.read_text(encoding="utf-8"))
                         .get("events") or {}).items():
            add(eid, row.get("start_utc"))
    return clocks


def outcome(event: Mapping[str, Any] | None,
            payload: Mapping[str, Any] | None) -> Outcome:
    """The selection's result from the /event payload's `event` and the
    point-by-point."""
    if not event:
        return Outcome("NOT_FOUND", reason="no /event")
    st = event.get("status") or {}
    code, kind = st.get("code"), st.get("type")
    if kind == "canceled" or code == 70:
        return Outcome("VOID", reason="CANCELED")
    if code == 91:
        return Outcome("VOID", reason="WALKOVER")
    if code == 92:
        # SETTLE refunds a retirement; whether Superbet stands a market the
        # first two games already decided is not modelled - counted apart.
        decided = pbp.games(payload)
        played = decided and pbp.score_after(pbp.in_set(decided, 1), 2)
        return Outcome("VOID", reason="RETIRED_AFTER_2" if played else "RETIRED")
    if kind != "finished":
        return Outcome("PENDING", reason=str(kind))
    games = pbp.games(payload)
    if not games:
        return Outcome("NOT_FOUND", reason="no point-by-point")
    set1 = pbp.in_set(games, 1)
    after = pbp.score_after(set1, 2)
    if after is None:
        return Outcome("MISMATCH", reason="set 1 shorter than 2 games")
    p1h = (event.get("homeScore") or {}).get("period1")
    p1a = (event.get("awayScore") or {}).get("period1")
    last = set1[-1]
    if p1h is not None and p1a is not None and (
            (last.home_games, last.away_games) != (int(p1h), int(p1a))):
        return Outcome("MISMATCH", reason="set-1 games != set-1 score")
    return Outcome("GRADED", won=int(after == (1, 1)))


def forecasts(rows: Sequence[Row], targets: Sequence[tuple[int, int, int, int]],
              k_games: float) -> dict[int, tuple[float, float]]:
    """(hold of home, hold of away) per target (ts, event, home, away), from
    the matches that started before it only (never the target itself)."""
    accd: dict[int, list[float]] = defaultdict(lambda: [0.0] * 8)
    pool = [0.0] * 8
    out: dict[int, tuple[float, float]] = {}
    i = 0
    target_ids = {t[1] for t in targets}
    for ts, eid, home, away in sorted(targets):
        while i < len(rows) and rows[i][0] < ts:
            _t, rid, h, a, hn, an = rows[i]
            if rid not in target_ids:  # a priced match is never its own history
                learn(accd, pool, h, a, hn, an)
            i += 1
        if pool[1] <= 0:
            continue
        ph = pool[0] / pool[1]
        out[eid] = (hold_rate(accd[home], accd[away], ph, k_games),
                    hold_rate(accd[away], accd[home], ph, k_games))
    return out


def p_draw(ha: float, hb: float) -> float:
    """P(1:1 after two games): both hold or both broken."""
    return ha * hb + (1 - ha) * (1 - hb)


def summarise(items: Sequence[Mapping[str, Any]], reps: int,
              seed: int = 7) -> dict[str, Any]:
    """n, hits, hit rate, mean forecasts, mean 1/odds, ROI with a bootstrap
    over matches (one item per match)."""
    n = len(items)
    if n == 0:
        return {"n": 0}
    pnl = [it["won"] * it["price"] - 1.0 for it in items]
    rng = random.Random(seed)
    boots = sorted(sum(rng.choice(pnl) for _ in range(n)) / n for _ in range(reps))
    return {
        "n": n,
        "hits": sum(it["won"] for it in items),
        "hit_rate": sum(it["won"] for it in items) / n,
        "mean_p_draw": sum(it["p_draw"] for it in items) / n,
        "mean_p_both_hold": sum(it["p_both_hold"] for it in items) / n,
        "mean_implied": sum(1 / it["price"] for it in items) / n,
        "mean_price": sum(it["price"] for it in items) / n,
        "roi": sum(pnl) / n,
        "roi_lo": boots[int(0.025 * reps)],
        "roi_hi": boots[min(reps - 1, int(0.975 * reps))],
    }


def fetch(config: SofaConfig, ids: Sequence[int],
          max_minutes: float | None) -> dict[str, int]:
    """Ask the bridge for /event and /point-by-point of `ids`; cache them."""
    from bet.sofa.cache import SofaCache
    from bet.sofa.client import SofascoreClient, breaker_tripped
    from bet.sofa.errors import CircuitOpenError, ProviderError

    cache, client = SofaCache(config), SofascoreClient(config)
    deadline = time.monotonic() + max_minutes * 60 if max_minutes else None
    counts = {"asked": 0, "finished": 0, "pbp": 0, "errors": 0, "refused": 0}
    for eid in ids:
        if deadline is not None and time.monotonic() >= deadline:
            break
        try:
            detail = client.event(eid)
            counts["asked"] += 1
            if not detail:
                continue
            kind = ((detail.get("event") or {}).get("status") or {}).get("type")
            cache.save_event_detail(eid, detail, kind)
            if kind != "finished":
                continue
            counts["finished"] += 1
            got = client.event_point_by_point(eid)
            ok = isinstance(got, dict) and bool(got.get("pointByPoint"))
            cache.save_event_extra(eid, "point_by_point", got if ok else None,
                                   "finished")
            counts["pbp"] += int(ok)
        except CircuitOpenError:
            counts["refused"] += 1
            break
        except ProviderError:
            counts["errors"] += 1
            if breaker_tripped(client):
                counts["refused"] += 1
                break
    return counts


def _details(db: sqlite3.Connection, ids: Iterable[int]) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for eid in ids:
        r = db.execute("SELECT detail_json FROM sofa_event_detail "
                       "WHERE sofascore_event_id = ?", (eid,)).fetchone()
        if r:
            out[eid] = (json.loads(r[0]).get("event") or {})
    return out


def _players(run_dir: Path) -> dict[int, tuple[int, int, str]]:
    path = run_dir / "02_fixtures.json"
    out: dict[int, tuple[int, int, str]] = {}
    if path.exists():
        for row in json.loads(path.read_text(encoding="utf-8")):
            if row.get("home_entity_id") and row.get("away_entity_id"):
                out[int(row["sofascore_event_id"])] = (
                    int(row["home_entity_id"]), int(row["away_entity_id"]),
                    f"{row.get('home_name')} - {row.get('away_name')}")
    return out


def _fmt(s: Mapping[str, Any]) -> str:
    if not s.get("n"):
        return "| 0 | | | | | | |"
    return (f"| {s['n']} | {s['hits']} | {s['hit_rate']:.3f} | {s['mean_p_draw']:.3f} "
            f"| {s['mean_p_both_hold']:.3f} | {s['mean_implied']:.3f} "
            f"| {s['roi']:+.3f} [{s['roi_lo']:+.3f}, {s['roi_hi']:+.3f}] |")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--date", action="append", required=True)
    ap.add_argument("--k-games", type=float, default=40.0)
    ap.add_argument("--threshold", type=float, default=0.80)
    ap.add_argument("--reps", type=int, default=2000)
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--max-minutes", type=float, default=5.0)
    ap.add_argument("--md-out")
    ap.add_argument("--json-out")
    args = ap.parse_args()
    config = SofaConfig.from_env()
    now = datetime.now(UTC)

    days: dict[str, dict[str, Any]] = {}
    for d in args.date:
        run_dir = _REPO / "runs" / "sofa" / d
        clocks = start_clocks(run_dir)
        records = [r for r in unmapped_prices.read(run_dir) if is_selection(r)]
        days[d] = {"run_dir": run_dir, "clocks": clocks, "records": records}

    db = sqlite3.connect(f"file:{config.db_path}?mode=ro", uri=True)
    every = {int(r["sofascore_event_id"]) for v in days.values() for r in v["records"]}
    for v in days.values():  # the cached /event start is a clock too
        day_ids = {int(r["sofascore_event_id"]) for r in v["records"]}
        for eid, ev in _details(db, day_ids).items():
            t = _ts(ev.get("startTimestamp"))
            if t is not None:
                v["clocks"].setdefault(eid, []).append(t)
    fetch_counts: dict[str, int] | None = None
    if args.fetch:
        have = load_pbps(db, every)
        det = _details(db, every)
        want = sorted(
            eid for v in days.values() for eid in {int(r["sofascore_event_id"])
                                                   for r in v["records"]}
            if v["clocks"].get(eid) and min(v["clocks"][eid]) < now - FETCH_AFTER
            and not (eid in have and (det.get(eid, {}).get("status") or {})
                     .get("type") == "finished"))
        print(json.dumps({"fetch_targets": len(want)}), flush=True)
        db.close()
        fetch_counts = fetch(config, want, args.max_minutes)
        print(json.dumps({"fetch": fetch_counts}), flush=True)
        db = sqlite3.connect(f"file:{config.db_path}?mode=ro", uri=True)

    rows = load_rows(db)
    pbps = load_pbps(db, every)
    details = _details(db, every)
    items: list[dict[str, Any]] = []
    tallies: dict[str, dict[str, int]] = {}
    for d, v in days.items():
        starts = {e: min(c) for e, c in v["clocks"].items()}
        quotes, dropped = last_prematch(v["records"], starts)
        players = _players(v["run_dir"])
        targets = [(int(starts[e].timestamp()), e, *players[e][:2])
                   for e in quotes if e in players]
        fc = forecasts(rows, targets, args.k_games)
        tally: dict[str, int] = {"events_priced": len(quotes),
                                 "records_dropped_not_prematch": dropped,
                                 "no_players": len(quotes) - len(targets)}
        for eid, q in sorted(quotes.items()):
            oc = outcome(details.get(eid), pbps.get(eid))
            key = oc.status + (f":{oc.reason}" if oc.status == "VOID" else "")
            tally[key] = tally.get(key, 0) + 1
            if oc.status != "GRADED" or eid not in fc:
                continue
            ha, hb = fc[eid]
            items.append({"day": d, "event_id": eid, "match": players[eid][2],
                          "price": q.price, "fetched_at": q.fetched_at.isoformat(),
                          "won": oc.won, "p_draw": p_draw(ha, hb),
                          "p_both_hold": ha * hb})
        tallies[d] = tally

    def groups() -> list[tuple[str, list[dict[str, Any]]]]:
        out = []
        for label, scope in [("all", items)] + [(d, [i for i in items if i["day"] == d])
                                                for d in days]:
            out.append((f"{label}", scope))
            out.append((f"{label}, P(1:1) >= {args.threshold:.2f}",
                        [i for i in scope if i["p_draw"] >= args.threshold]))
            out.append((f"{label}, hA*hB >= {args.threshold:.2f}",
                        [i for i in scope if i["p_both_hold"] >= args.threshold]))
        return out

    summary = {label: summarise(scope, args.reps) for label, scope in groups()}
    lines = [f"# Tennis '{SELECTION}' (set 1 after 2 games) at Superbet's price", "",
             "| group | n | hits | hit rate | mean P(1:1) | mean hA*hB | mean 1/odds "
             "| ROI [95% match bootstrap] |", "|---|---|---|---|---|---|---|---|"]
    lines += [f"| {label} {_fmt(s)}" for label, s in summary.items()]
    lines += ["", "status counts per day: " + json.dumps(tallies, ensure_ascii=False)]
    if fetch_counts is not None:
        lines.append("fetch: " + json.dumps(fetch_counts))
    text = "\n".join(lines)
    print(text)
    if args.md_out:
        Path(args.md_out).write_text(text + "\n", encoding="utf-8")
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(
            {"summary": summary, "tallies": tallies, "fetch": fetch_counts,
             "items": items}, indent=1, ensure_ascii=False), encoding="utf-8")
    return 1 if fetch_counts and fetch_counts["refused"] else 0


if __name__ == "__main__":
    sys.exit(main())
