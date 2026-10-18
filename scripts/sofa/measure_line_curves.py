#!/usr/bin/env python3
# ruff: noqa: E501  - report lines are tables.
"""Curve per line vs the pooled curve, football, out of sample on the history
replay (read-only evidence).

A football curve (`fit_confidence`) is fitted per market x direction over
every line the replay prices (`lines_for`: a ladder around the centre), while
Superbet quotes a few lines near the centre. Where the model's p is not
calibrated alike across lines, the pooled curve is right on average and wrong
at the quoted lines (2026-10-18: goals_for UNDER 1.5 -2.4 pp on 305k rows of
2026, the far UNDER lines +1..+3 pp).

Arms, each fitted on TRAIN rows exactly as the curve files are built (bucket
EDGES, Wilson lower bound, buckets of >= MIN_MARKET_BUCKET rows):
  A  pooled - every line (today's curve shape),
  B  per line - the line's own rows; a bucket without enough reads A's,
  C  quoted lines only - the market x direction's quoted lines pooled; a
     bucket without enough reads A's.
Judged on TEST rows at the QUOTED lines only (lines Superbet offered on the
live sheet rows of --live-from..--live-to, >= --min-live rows a line):
realised - curve at curve >= 0.70 (the printable claim) and the log-loss of
the bucket's realised rate, on the rows both arms cover. Intervals: 95%,
resampling events in 100 hash groups (`event_id % 100`). Women's
competitions out (they read their class's curves).

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_line_curves.py \\
        --db data/refit_2026-10-17/sofa_replay.db [--md-out f] [--json-out f]
"""

from __future__ import annotations

import argparse
import datetime
import json
import math
import random
import sqlite3
import sys
import time
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT / "src"), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa.confidence import is_derived, load_women_competitions  # noqa: E402
from scripts.sofa.fit_confidence import (  # noqa: E402
    EDGES,
    MIN_MARKET_BUCKET,
    wilson_lo,
)

GROUPS = 100
FLOOR = 0.70
Key = tuple[str, str]          # market, direction
LineKey = tuple[str, str, float]


def bucket_of(p: float) -> int:
    for i in range(len(EDGES) - 1):
        if EDGES[i] <= p < EDGES[i + 1]:
            return i
    return len(EDGES) - 2


def curve(counts: Mapping[int, list[int]]) -> dict[int, tuple[float, float, int]]:
    """bucket -> (realised_lo95, realised, n) of buckets with enough rows."""
    out = {}
    for b, (k, n) in counts.items():
        if n >= MIN_MARKET_BUCKET:
            out[b] = (wilson_lo(k, n), k / n, n)
    return out


def quoted_lines(live_db: str, first: str, last: str, min_live: int,
                 women: frozenset[int]) -> dict[Key, set[float]]:
    con = sqlite3.connect(f"file:{live_db}?mode=ro", uri=True)
    counts: dict[LineKey, int] = defaultdict(int)
    for market, direction, line, comp in con.execute(
            "select market, direction, line, competition_id from sofa_settled_row "
            "where sport = 'football' and offered_odds is not null "
            "and run_date between ? and ?", (first, last)):
        if comp in women:
            continue
        counts[(market, direction, float(line))] += 1
    out: dict[Key, set[float]] = defaultdict(set)
    for (m, d, line), n in counts.items():
        if n >= min_live:
            out[(m, d)].add(line)
    return out


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", required=True, help="the history replay DB (read-only)")
    ap.add_argument("--live-db", default="data/sofa.db")
    ap.add_argument("--live-from", default="2026-10-09")
    ap.add_argument("--live-to", default="2026-10-17")
    ap.add_argument("--min-live", type=int, default=20)
    ap.add_argument("--train-from", default="2025-07-01")
    ap.add_argument("--test-from", default="2026-04-01")
    ap.add_argument("--test-to", default="2026-10-12")
    ap.add_argument("--md-out", default=None)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)
    women = load_women_competitions()
    quoted = quoted_lines(args.live_db, args.live_from, args.live_to, args.min_live, women)

    t0 = time.time()
    train: dict[LineKey, dict[int, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    test: dict[LineKey, dict[tuple[int, int], list[int]]] = defaultdict(
        lambda: defaultdict(lambda: [0, 0]))
    con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    # replay rows carry run_date 'cache-calibration': the match's day comes
    # from its listed start
    day: dict[int, str] = {}
    for table in ("sofa_listing_event", "sofa_listed_event"):
        for event, ts in con.execute(
                f"select event_id, start_ts from {table} where start_ts is not null"):
            day[int(event)] = datetime.datetime.fromtimestamp(
                int(ts), datetime.UTC).date().isoformat()
    rows = 0
    undated = 0
    for event, comp, market, line, direction, p, outcome in con.execute(
            "select sofascore_event_id, competition_id, market, line, direction, "
            "p_central, outcome from sofa_settled_row indexed by sofa_settled_row_run_date "
            "where run_date = 'cache-calibration' and sport = 'football' "
            "and outcome in ('WIN', 'LOSS')"):
        if comp in women or is_derived(market):
            continue
        run_date = day.get(int(event))
        if run_date is None:
            undated += 1
            continue
        if not args.train_from <= run_date <= args.test_to:
            continue
        rows += 1
        b = bucket_of(float(p))
        won = int(outcome == "WIN")
        key = (market, direction, float(line))
        if run_date < args.test_from:
            cell = train[key][b]
        elif float(line) in quoted.get((market, direction), ()):
            cell = test[key][(b, int(event) % GROUPS)]
        else:
            continue
        cell[0] += won
        cell[1] += 1
    secs = round(time.time() - t0)

    pooled_all: dict[Key, dict[int, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    pooled_q: dict[Key, dict[int, list[int]]] = defaultdict(lambda: defaultdict(lambda: [0, 0]))
    for (m, d, line), buckets in train.items():
        for b, (k, n) in buckets.items():
            pooled_all[(m, d)][b][0] += k
            pooled_all[(m, d)][b][1] += n
            if line in quoted.get((m, d), ()):
                pooled_q[(m, d)][b][0] += k
                pooled_q[(m, d)][b][1] += n
    curve_a = {k: curve(v) for k, v in pooled_all.items()}
    curve_c = {k: curve(v) for k, v in pooled_q.items()}

    def arm(name: str, key: LineKey) -> dict[int, tuple[float, float, int]]:
        a = curve_a.get(key[:2], {})
        if name == "A":
            return a
        own = curve(train.get(key, {})) if name == "B" else curve_c.get(key[:2], {})
        return {**a, **own}

    # per line: (group -> [sum of (y - conf) at conf >= FLOOR, n at floor,
    #            log-loss sum, n common]) for each arm
    results: list[dict[str, Any]] = []
    for key in sorted(test):
        arms = {n: arm(n, key) for n in "ABC"}
        per: dict[str, dict[int, list[float]]] = {n: defaultdict(lambda: [0.0, 0, 0.0, 0]) for n in "ABC"}
        for (b, g), (k, n) in test[key].items():
            # log-loss only where a leg can print: the model's p >= 0.70
            covered = b >= 2 and all(b in arms[x] for x in "ABC")
            for name in "ABC":
                entry = arms[name].get(b)
                if entry is None:
                    continue
                lo95, real, _n = entry
                acc = per[name][g]
                if lo95 >= FLOOR:
                    acc[0] += k - n * lo95
                    acc[1] += n
                if covered:
                    q = min(max(real, 1e-6), 1 - 1e-6)
                    acc[2] += -(k * math.log(q) + (n - k) * math.log(1 - q))
                    acc[3] += n
        results.append({"key": key, "per": per})

    def agg(per: Mapping[int, list[float]], groups: Sequence[int]) -> tuple[float, int, float, int]:
        s = [0.0, 0, 0.0, 0]
        for g in groups:
            v = per.get(g)
            if v:
                for i in range(4):
                    s[i] += v[i]
        return s[0], int(s[1]), s[2], int(s[3])

    rnd = random.Random(7)
    draws = [[rnd.randrange(GROUPS) for _ in range(GROUPS)] for _ in range(400)]
    everything = list(range(GROUPS))

    def summary(res: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        def total(name: str, groups: Sequence[int]) -> tuple[float, int, float, int]:
            s = [0.0, 0, 0.0, 0]
            for r in res:
                v = agg(r["per"][name], groups)
                for i in range(4):
                    s[i] += v[i]
            return s[0], int(s[1]), s[2], int(s[3])
        out: dict[str, Any] = {}
        point = {n: total(n, everything) for n in "ABC"}
        boots = [{n: total(n, d) for n in "ABC"} for d in draws]
        for n in "ABC":
            gsum, gn, _ll, _c = point[n]
            gaps = sorted(b[n][0] / b[n][1] for b in boots if b[n][1])
            out[n] = {"n_floor": gn, "gap": gsum / gn if gn else None,
                      "gap_ci": [gaps[10], gaps[389]] if len(gaps) > 389 else None}
        for n in "BC":
            if point[n][3] and point["A"][3] == point[n][3]:
                diffs = sorted((b[n][2] - b["A"][2]) / b["A"][3] for b in boots if b["A"][3])
                out[f"{n}-A_logloss"] = {
                    "value": (point[n][2] - point["A"][2]) / point["A"][3],
                    "ci": [diffs[10], diffs[389]] if len(diffs) > 389 else None,
                    "rows": point["A"][3]}
        return out

    by_market: dict[Key, list[dict[str, Any]]] = defaultdict(list)
    for r in results:
        by_market[r["key"][:2]].append(r)
    report: list[dict[str, Any]] = []
    for mk, res in sorted(by_market.items()):
        s = summary(res)
        lines = []
        for r in res:
            one = summary([r])
            lines.append({"line": r["key"][2], **one})
        wabs = {}
        for name in "ABC":
            tot = sum(ln[name]["n_floor"] for ln in lines if ln[name]["gap"] is not None)
            wabs[name] = (sum(ln[name]["n_floor"] * abs(ln[name]["gap"]) for ln in lines
                              if ln[name]["gap"] is not None) / tot) if tot else None
        report.append({"market": mk[0], "direction": mk[1], **s, "lines": lines, "wabs": wabs})
    allsum = summary(results)

    def fmt_gap(x: Mapping[str, Any]) -> str:
        if x["gap"] is None:
            return "-"
        ci = x["gap_ci"] or [float("nan")] * 2
        return f"{x['gap'] * 100:+.2f} [{ci[0] * 100:+.2f}, {ci[1] * 100:+.2f}] (n {x['n_floor']})"

    def fmt_ll(x: Mapping[str, Any] | None) -> str:
        if not x:
            return "-"
        if not x["ci"]:
            return f"{x['value'] * 1e4:+.1f}"
        return f"{x['value'] * 1e4:+.1f} [{x['ci'][0] * 1e4:+.1f}, {x['ci'][1] * 1e4:+.1f}]"

    md = [f"# Krzywa per linia vs krzywa wspólna - piłka, historia (trening {args.train_from}..{args.test_from}, test {args.test_from}..{args.test_to})", "",
          f"Wiersze replayu w oknie: {rows:,}, bez daty meczu {undated:,} ({secs} s). Linie rynkowe: linie z >= {args.min_live} wierszami z ceną Superbetu {args.live_from}..{args.live_to}. "
          "Luka = trafione - krzywa (Wilson) przy krzywej >= 0,70; log-loss x1e4 na wierszach z p >= 0,70 pokrytych przez wszystkie warianty (ujemny = lepiej niż A); śr. abs. luka = średnia |luka| linii ważona liczbą wierszy przy krzywej >= 0,70.", "",
          "| rynek | kier. | A: luka [95%] | B per linia: luka | C linie rynkowe: luka | śr. abs. luka linii A / B / C (pp) | B-A log-loss | C-A log-loss |",
          "|---|---|---|---|---|---|---|---|"]
    tot_w: dict[str, list[float]] = {a: [0.0, 0.0] for a in "ABC"}
    for r in report:
        for a in "ABC":
            for ln in r["lines"]:
                if ln[a]["gap"] is not None:
                    tot_w[a][0] += ln[a]["n_floor"] * abs(ln[a]["gap"])
                    tot_w[a][1] += ln[a]["n_floor"]
    wtxt = " / ".join(f"{tot_w[a][0] / tot_w[a][1] * 100:.2f}" if tot_w[a][1] else "-" for a in "ABC")
    md.append(f"| **wszystkie** | | {fmt_gap(allsum['A'])} | {fmt_gap(allsum['B'])} | {fmt_gap(allsum['C'])} | {wtxt} | "
              f"{fmt_ll(allsum.get('B-A_logloss'))} | {fmt_ll(allsum.get('C-A_logloss'))} |")
    for r in report:
        w = " / ".join("-" if r["wabs"][n] is None else f"{r['wabs'][n] * 100:.2f}" for n in "ABC")
        md.append(f"| {r['market']} | {r['direction']} | {fmt_gap(r['A'])} | {fmt_gap(r['B'])} | {fmt_gap(r['C'])} | {w} | "
                  f"{fmt_ll(r.get('B-A_logloss'))} | {fmt_ll(r.get('C-A_logloss'))} |")
    md += ["", "## Per linia", "", "| rynek | kier. | linia | A: luka | B: luka | B-A log-loss |", "|---|---|---|---|---|---|"]
    for r in report:
        for ln in r["lines"]:
            md.append(f"| {r['market']} | {r['direction']} | {ln['line']} | {fmt_gap(ln['A'])} | {fmt_gap(ln['B'])} | {fmt_ll(ln.get('B-A_logloss'))} |")
    text = "\n".join(md)
    if args.md_out:
        Path(args.md_out).write_text(text + "\n", encoding="utf-8")
    if args.json_out:
        Path(args.json_out).write_text(json.dumps({"all": allsum, "markets": report}, default=str), encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
