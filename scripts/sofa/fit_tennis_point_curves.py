#!/usr/bin/env python3
"""Fit config/sofa_tennis_point_curves.json - the history curves of the
tennis point model's keys (epochs.TENNIS_POINT_MODEL; read by CONFIDENCE
through bet.sofa.tennis_point_curves).

The rule (CLAUDE.md): curves are fitted on the HISTORY of events and
statistics, replayed as of each match with the estimator SHEET prices with
today. Here the estimator is bet.sofa.tennis_point_model: one walk-forward
over the cached singles history (tennis_point_model.walk_forward - every
fitted match forecast from the beliefs before its start), each fitted match
simulated as SHEET simulates a fixture (tennis_point_sheet.PointPricer: 4,000
matches, seeded by the event id), and every key of
epochs.TENNIS_POINT_MODEL_MARKETS read at market-like lines:

  * lines: every half line whose OVER p lies in [LINE_P_LO, LINE_P_HI] (a
    ladder around the model's own median; chosen from the forecast alone,
    never from the result); a per-player market for each player;
  * both directions are rows (OVER p, UNDER 1 - p), graded on the match's own
    statistic (per-set: conditional on the set being played, as Superbet
    voids it otherwise);
  * matches: completed best-of-three singles between --from and --before
    (default 2026-01-01 .. 2026-10-20: after the window the model's constants
    were chosen on, before the Superbet hold-out of the 11-05 measurement);
    the serve markets on matches with serve statistics, the per-set games on
    those plus --extra-games random matches without them (seeded).

Curves exactly as fit_confidence writes them: EDGES, MIN_MARKET_BUCKET for
by_market / by_market_direction, MIN_THIN_BUCKET..MIN_MARKET_BUCKET for
thin_by_market_direction, realised_lo95 the Wilson lower bound; every row in
the top-level curves, a women's match (either side "F") also in
by_class.tennis_women. A team-cup class gets no section (its legs read no
curve: NO_CLASS_CURVE).

Read-only on the DB (or --history-cache, a pickle of load_point_history).
Never the network. Writes --out (default the config file) and, with
--rows-out, the fitted rows (jsonl.gz, OVER side) for audit.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_tennis_point_curves.py \\
        [--history-cache <pkl>] [--out <json>] [--rows-out <jsonl>]
"""

from __future__ import annotations

import argparse
import gzip
import json
import math
import pickle
import random
import subprocess
import sys
from collections import defaultdict
from collections.abc import Sequence
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import tennis_point_curves as tpc  # noqa: E402
from bet.sofa import tennis_point_sheet as tps  # noqa: E402
from bet.sofa.atomic import write_atomic  # noqa: E402
from bet.sofa.confidence import CLASS_TENNIS_WOMEN, direction_key  # noqa: E402
from bet.sofa.config import config_path  # noqa: E402
from bet.sofa.epochs import (  # noqa: E402
    TENNIS_HANDICAP_POINT_MODEL_MARKETS,
    TENNIS_POINT_MODEL_MARKETS,
)
from bet.sofa.tennis_point_model import (  # noqa: E402
    MatchForecast,
    PointMatch,
    load_point_history,
    walk_forward,
)
from scripts.sofa.fit_confidence import (  # noqa: E402
    EDGES,
    MIN_MARKET_BUCKET,
    MIN_THIN_BUCKET,
    bucket_of,
    wilson_lo,
)

DEFAULT_FROM = "2026-01-01"
DEFAULT_BEFORE = "2026-10-20"
LINE_P_LO = 0.10
LINE_P_HI = 0.90
EXTRA_GAMES = 20000
SEED = 11
SET_GAMES = ("games_set1_total", "games_set2_total")
SERVE = tuple(sorted(TENNIS_POINT_MODEL_MARKETS - set(SET_GAMES)))


def actual(m: PointMatch, market: str, side: int | None) -> float | None:
    """The match's own value of a key (None = not recorded / set not
    played)."""
    if market in SET_GAMES:
        k = 0 if market == "games_set1_total" else 1
        return float(sum(m.sets[k])) if len(m.sets) > k else None
    if m.home is None or m.away is None:
        return None
    stat, _, rest = market.partition("_set")
    scope = 0
    if rest:
        scope = int(rest[0])
        kind = rest.split("_", 1)[1]
    else:
        stat, kind = market.rsplit("_", 1)
    sides = [m.home, m.away]
    players = [side] if kind == "for" and side is not None else [0, 1]

    def one(i: int, which: str) -> int | None:
        s = sides[i]
        if scope == 0:
            return s.aces if which == "aces" else s.dfs
        seq = s.set_aces if which == "aces" else s.set_dfs
        if len(m.sets) < scope or len(seq) < scope:
            return None
        return seq[scope - 1]

    total = 0
    for i in players:
        whiches = (("aces", "dfs") if stat == "serve_points"
                   else ("aces",) if stat == "aces" else ("dfs",))
        for w in whiches:
            v = one(i, w)
            if v is None:
                return None
            total += v
    return float(total)


def _lines(pricer: tps.PointPricer, eid: int, market: str,
           side: int | None) -> list[tuple[float, float]]:
    ms = pricer.market_sim(eid)
    if ms is None:
        return []
    centre = tps.mean_sd(ms, market, side)
    if centre is None:
        return []
    mean, sd = centre
    lo = max(0.5, math.floor(mean - 3.5 * sd - 1) + 0.5)
    hi = mean + 3.5 * sd + 1
    out: list[tuple[float, float]] = []
    line = lo
    while line <= hi:
        p = ms.p_over(market, side, line)
        if p is not None and LINE_P_LO <= p <= LINE_P_HI:
            out.append((line, p))
        line += 1.0
    return out


def rows_for(job: tuple[PointMatch, MatchForecast, bool]) -> list[dict[str, Any]]:
    """Every row of one fitted match (run in a worker)."""
    m, forecast, serve = job
    pricer = tps.PointPricer({m.event_id: forecast})
    markets = SET_GAMES + (SERVE if serve else ())
    out: list[dict[str, Any]] = []
    for market in markets:
        sides: Sequence[int | None] = (0, 1) if market.endswith("_for") else (None,)
        for side in sides:
            value = actual(m, market, side)
            if value is None:
                continue
            for line, p in _lines(pricer, m.event_id, market, side):
                out.append({"eid": m.event_id, "market": market, "side": side,
                            "line": line, "p": round(p, 5),
                            "y": 1 if value > line else 0,
                            "female": m.female, "tier": m.tier, "ts": m.ts})
    return out


Counts = dict[str, dict[int, list[int]]]


def _counts() -> dict[str, Counts]:
    return {"market": defaultdict(lambda: defaultdict(lambda: [0, 0])),
            "direction": defaultdict(lambda: defaultdict(lambda: [0, 0]))}


def add(counts: dict[str, Counts], market: str, p_over: float, y_over: int) -> None:
    """Both directions of one line: OVER at p, UNDER at 1 - p."""
    for direction, p, hit in (("OVER", p_over, y_over),
                              ("UNDER", 1.0 - p_over, 1 - y_over)):
        b = bucket_of(min(max(p, 0.0), 1.0))
        for cell in (counts["market"][market][b],
                     counts["direction"][direction_key(market, direction)][b]):
            cell[0] += hit
            cell[1] += 1


def curve(counts: dict[int, list[int]], floor: int,
          below: int | None = None) -> dict[str, dict[str, Any]]:
    """fit_confidence.main's curve(): one bucket per EDGES cell."""
    out: dict[str, dict[str, Any]] = {}
    for b, (k, n) in sorted(counts.items()):
        if n < floor or (below is not None and n >= below):
            continue
        out[f"{EDGES[b]:.3f}-{EDGES[b + 1]:.3f}"] = {
            "n": n, "realised": round(k / n, 4),
            "realised_lo95": round(wilson_lo(k, n), 4)}
    return out


def sections(counts: dict[str, Counts]) -> dict[str, Any]:
    by_market, by_dir = counts["market"], counts["direction"]
    return {
        "by_market": {m: c for m, cs in sorted(by_market.items())
                      if (c := curve(cs, MIN_MARKET_BUCKET))},
        "by_market_direction": {k: c for k, cs in sorted(by_dir.items())
                                if (c := curve(cs, MIN_MARKET_BUCKET))},
        "thin_by_market_direction": {
            k: c for k, cs in sorted(by_dir.items())
            if (c := curve(cs, MIN_THIN_BUCKET, below=MIN_MARKET_BUCKET))},
    }


def _day_rows(run_dir: Path,
              markets: frozenset[str] = tps.MARKETS) -> list[dict[str, Any]]:
    """The in-scope tennis rows of a day: its settled rows (what the line
    evidence reads), or its sheet while it is not settled yet."""
    for name in ("07_settled.json", "05_sheet.json"):
        path = run_dir / name
        if path.exists():
            return [r for r in json.loads(path.read_text(encoding="utf-8"))
                    if tps.in_scope(r.get("sport"), str(r.get("market")), markets)]
    return []


def backfill(history: Sequence[PointMatch], runs_dir: Path, days: Sequence[str],
             markets: frozenset[str] = tps.MARKETS,
             ) -> tuple[dict[str, float], dict[str, int]]:
    """The point model's p of every in-scope tennis row of `days`, priced by
    SHEET's own path (run_sheet.load_point_pricer's pieces: the fixture from
    02_fixtures.json, as of its start; run_sheet.determine_side)."""
    from pydantic import RootModel

    from bet.sofa.contracts import Fixture
    from scripts.sofa.run_sheet import determine_side

    female_of = tps.female_by_player(history)
    per_day: dict[str, list[dict[str, Any]]] = {}
    fixtures: dict[tuple[str, int], Fixture] = {}
    matches: dict[int, PointMatch] = {}
    counts = {"rows": 0, "priced": 0, "no_fixture": 0, "no_forecast": 0,
              "no_side": 0, "no_p": 0}
    for day in days:
        run_dir = runs_dir / day
        rows = _day_rows(run_dir, markets)
        if not rows:
            continue
        per_day[day] = rows
        try:
            parsed = RootModel[list[Fixture]].model_validate_json(
                (run_dir / "02_fixtures.json").read_bytes()).root
        except ValueError:
            counts["day_unreadable"] = counts.get("day_unreadable", 0) + 1
            continue
        for fx in parsed:
            if fx.sport != "tennis":
                continue
            fixtures[(day, fx.sofascore_event_id)] = fx
            m = tps.fixture_match(
                fx.sofascore_event_id, fx.kickoff_utc, fx.home_entity_id,
                fx.away_entity_id, fx.category_name, fx.ground_type,
                fx.competition_id, fx.default_period_count, female_of)
            if m is not None:
                matches[m.event_id] = m
    pricer = tps.PointPricer(tps.forecast_fixtures(history, list(matches.values())),
                             markets=markets)
    out: dict[str, float] = {}
    for day, rows in per_day.items():
        for r in rows:
            counts["rows"] += 1
            eid = int(r["sofascore_event_id"])
            fixture = fixtures.get((day, eid))
            if fixture is None:
                counts["no_fixture"] += 1
                continue
            if eid not in pricer.forecasts:
                counts["no_forecast"] += 1
                continue
            side: int | None = None
            if r.get("subject"):
                key = determine_side(str(r["subject"]), fixture)
                side = 0 if key == "side_a" else 1 if key == "side_b" else None
                if side is None:
                    counts["no_side"] += 1
                    continue
            p = pricer.p(eid, str(r["market"]), side, float(r["line"]),
                         str(r["direction"]))
            if p is None:
                counts["no_p"] += 1
                continue
            out[tpc.backfill_key(day, eid, str(r["market"]), r.get("subject"),
                                 r["line"], str(r["direction"]))] = round(p, 5)
            counts["priced"] += 1
        pricer._cache.clear()
    return out, counts


def _ts(day: str) -> int:
    return int(datetime.fromisoformat(day).replace(tzinfo=UTC).timestamp())


def _commit() -> str | None:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                              capture_output=True, text=True, check=True,
                              cwd=_REPO).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db-path", default=str(_REPO / "data" / "sofa.db"))
    ap.add_argument("--history-cache", default=None,
                    help="a pickle of tennis_point_model.load_point_history")
    ap.add_argument("--from", dest="from_day", default=DEFAULT_FROM)
    ap.add_argument("--before", default=DEFAULT_BEFORE)
    ap.add_argument("--extra-games", type=int, default=EXTRA_GAMES)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--out", default=str(config_path(tpc.FILE)))
    ap.add_argument("--rows-out", default=None)
    ap.add_argument("--backfill-out", default=None,
                    help="write the point model's p of every in-scope tennis "
                    "sheet row of --backfill-from..--backfill-to (gzipped JSON, "
                    "tennis_point_curves.BACKFILL) instead of fitting curves")
    ap.add_argument("--handicap", action="store_true",
                    help="with --backfill-out: the per-set games handicap "
                    "(epochs.TENNIS_HANDICAP_POINT_MODEL_MARKETS, "
                    "tennis_point_curves.HANDICAP_BACKFILL) instead")
    ap.add_argument("--backfill-from", default="2026-09-18")
    ap.add_argument("--backfill-to", default="2026-11-05")
    ap.add_argument("--runs-dir", default=str(_REPO / "runs" / "sofa"))
    args = ap.parse_args()

    if args.history_cache and Path(args.history_cache).exists():
        with open(args.history_cache, "rb") as fh:
            history: list[PointMatch] = pickle.load(fh)
    else:
        history = load_point_history(args.db_path)
    if args.backfill_out:
        runs = Path(args.runs_dir)
        days = sorted(d.name for d in runs.iterdir()
                      if d.is_dir() and len(d.name) == 10 and d.name[4] == "-"
                      and args.backfill_from <= d.name <= args.backfill_to)
        out, counts = backfill(
            history, runs, days,
            TENNIS_HANDICAP_POINT_MODEL_MARKETS if args.handicap
            else tps.MARKETS)
        with gzip.open(args.backfill_out, "wt", encoding="utf-8") as fh:
            json.dump(out, fh)
        print(json.dumps({"stage": "TENNIS_POINT_BACKFILL", "verdict": "OK",
                          "days": [days[0], days[-1]] if days else None,
                          "metrics": counts, "output_path": args.backfill_out}))
        return 0
    lo, hi = _ts(args.from_day), _ts(args.before)
    window = [m for m in history if lo <= m.ts < hi and m.completed
              and m.best_of != 5 and len(m.sets) >= 2]
    with_serve = [m for m in window if m.home is not None and m.away is not None]
    without = [m for m in window if m.home is None or m.away is None]
    rng = random.Random(SEED)
    extra = rng.sample(without, min(args.extra_games, len(without)))
    fitted = {m.event_id: (m, True) for m in with_serve}
    fitted.update({m.event_id: (m, False) for m in extra})
    forecasts = walk_forward(history, set(fitted))
    jobs = [(m, forecasts[eid], serve) for eid, (m, serve) in sorted(fitted.items())
            if eid in forecasts]
    every, women = _counts(), _counts()
    n_rows = 0
    sink = gzip.open(args.rows_out, "wt", encoding="utf-8") if args.rows_out else None
    try:
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            for i, chunk in enumerate(pool.map(rows_for, jobs, chunksize=64)):
                for r in chunk:
                    add(every, r["market"], r["p"], r["y"])
                    if r["female"]:
                        add(women, r["market"], r["p"], r["y"])
                    if sink is not None:
                        sink.write(json.dumps(r) + "\n")
                n_rows += len(chunk)
                if (i + 1) % 5000 == 0:
                    print(f"{i + 1} / {len(jobs)} matches, {n_rows} rows",
                          flush=True)
    finally:
        if sink is not None:
            sink.close()
    doc: dict[str, Any] = {
        "_doc": (
            "History curves of the tennis point model's keys "
            "(epochs.TENNIS_POINT_MODEL_MARKETS), read by CONFIDENCE only "
            "under epochs.TENNIS_POINT_MODEL (bet.sofa.tennis_point_curves): "
            "they REPLACE the installed curves of these keys. Fitted by "
            "scripts/sofa/fit_tennis_point_curves.py on the model's "
            "walk-forward over the Sofascore history (as of each match), in "
            "fit_confidence's format (realised_lo95 = Wilson lower bound)."),
        "fitted_from": {
            "estimator": "bet.sofa.tennis_point_model via tennis_point_sheet "
                         f"(sims {tps.SIMS}, seed = event id)",
            "history": "tennis_point_model.load_point_history "
                       f"({len(history)} matches)",
            "window": [args.from_day, args.before],
            "matches_serve": sum(1 for _, s in fitted.values() if s),
            "matches_games_only": sum(1 for _, s in fitted.values() if not s),
            "matches_forecast": len(jobs),
            "rows": n_rows,
            "lines": f"half lines with OVER p in [{LINE_P_LO}, {LINE_P_HI}]",
            "min_market_bucket": MIN_MARKET_BUCKET,
            "min_thin_bucket": MIN_THIN_BUCKET,
            "classes": {CLASS_TENNIS_WOMEN: "either side F"},
            "code_commit": _commit(),
            "fitted_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        },
        **sections(every),
        "by_class": {CLASS_TENNIS_WOMEN: sections(women)},
    }
    write_atomic(Path(args.out), json.dumps(doc, indent=1) + "\n")
    print(json.dumps({"stage": "FIT_TENNIS_POINT_CURVES", "verdict": "OK",
                      "metrics": {k: doc["fitted_from"][k] for k in (
                          "matches_serve", "matches_games_only", "rows")},
                      "keys": len(doc["by_market_direction"]),
                      "output_path": args.out}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
