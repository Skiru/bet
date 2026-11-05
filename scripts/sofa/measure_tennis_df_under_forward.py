#!/usr/bin/env python3
"""The forward test `T-TENNIS-DF-UNDER-FORWARD` (config/sofa_test_registry.json,
docs/sofa/evidence/tennis_serve_markets_plan_2026-10-26.md item A).

Frozen rule (registered 2026-10-26): every settled `double_faults_total` /
`double_faults_for` UNDER line of `sofa_settled_row` with run_date >=
2026-10-27, WIN / LOSS with a Superbet price, every line of the match kept;
ROI at the quoted price, 95% bootstrap over matches. Judged only at >= 400
legs from >= 120 matches: PASSED when the lower ROI bound > 0, FAILED when the
upper bound < +0.02, otherwise not decided. Grades are SETTLE's own
(`outcome`), never recomputed here.

Coverage: the day's 05_sheet.json UNDER rows of the two markets with an
offered price are matched to the settled rows by the table's natural key; a
sheet line with no WIN / LOSS row is counted as ungraded (with the event's
07_settle_skips.json reasons when SETTLE listed it).

Read-only: the DB is opened `mode=ro`; nothing is written.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_tennis_df_under_forward.py \\
        [--from 2026-10-27] [--to <last settled day>] [--reps 2000]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

from bet.sofa.settled_by_market import Line, bootstrap_roi, roi_of

_REPO = Path(__file__).resolve().parents[2]
RUNS = _REPO / "runs" / "sofa"
DB = _REPO / "data" / "sofa.db"
MARKETS = ("double_faults_total", "double_faults_for")
FROM = "2026-10-27"
NEED_LEGS = 400
NEED_MATCHES = 120
FAIL_UPPER = 0.02

Key = tuple[int, str, str, float, str]


def frozen_verdict(legs: int, matches: int, lo: float, hi: float) -> str | None:
    """The registry status the frozen rule gives, or None below the required n.

    PASSED: lower ROI bound > 0. FAILED: upper bound < +0.02. NOT_PASSED:
    neither at the required n - no price rule, the markets stay off."""
    if legs < NEED_LEGS or matches < NEED_MATCHES:
        return None
    if lo > 0:
        return "PASSED"
    if hi < FAIL_UPPER:
        return "FAILED"
    return "NOT_PASSED"


def settled_days(start: str, end: str | None) -> list[str]:
    """Days in [start, end] whose SETTLE wrote 07_settled.json."""
    out: list[str] = []
    d = date.fromisoformat(start)
    stop = date.fromisoformat(end) if end else date.today() - timedelta(days=1)
    while d <= stop:
        if (RUNS / d.isoformat() / "07_settled.json").exists():
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def sheet_keys(day: str) -> dict[Key, float]:
    path = RUNS / day / "05_sheet.json"
    if not path.exists():
        return {}
    out: dict[Key, float] = {}
    for r in json.loads(path.read_text()):
        if (r.get("sport") == "tennis" and r.get("market") in MARKETS
                and r.get("direction") == "UNDER" and r.get("offered_odds")):
            key = (int(r["sofascore_event_id"]), str(r["market"]),
                   str(r.get("subject") or ""), float(r["line"]), "UNDER")
            out[key] = float(r["offered_odds"])
    return out


def skip_reasons(day: str) -> dict[int, list[str]]:
    path = RUNS / day / "07_settle_skips.json"
    if not path.exists():
        return {}
    doc = json.loads(path.read_text())
    return {int(e["sofascore_event_id"]): sorted(e.get("skipped") or {})
            for e in doc.get("skipped_events") or []}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--from", dest="start", default=FROM)
    ap.add_argument("--to", dest="end", default=None)
    ap.add_argument("--reps", type=int, default=2000)
    args = ap.parse_args()

    days = settled_days(args.start, args.end)
    if not days:
        print("no settled day in the window")
        return 1
    last = days[-1]
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    rows = conn.execute(
        f"""SELECT run_date, sofascore_event_id, market, subject, line, direction,
                   outcome, offered_odds
              FROM sofa_settled_row
             WHERE run_date >= ? AND run_date <= ? AND run_date != 'cache-calibration'
               AND sport = 'tennis' AND direction = 'UNDER'
               AND market IN ({",".join("?" * len(MARKETS))})""",
        (args.start, last, *MARKETS)).fetchall()

    outcomes = Counter(str(r[6]) for r in rows)
    graded: dict[Key, tuple[str, int, float]] = {}
    no_price = 0
    for run_date, ev, market, subject, line, direction, outcome, odds in rows:
        if outcome not in ("WIN", "LOSS"):
            continue
        if not odds or odds <= 1.0:
            no_price += 1
            continue
        graded[(int(ev), market, subject, float(line), direction)] = (
            run_date, 1 if outcome == "WIN" else 0, float(odds))

    lines = [Line(game=str(k[0]), p=0.0, odds=v[2], y=v[1]) for k, v in graded.items()]
    per_day: dict[str, list[Line]] = defaultdict(list)
    for k, v in graded.items():
        per_day[v[0]].append(Line(game=str(k[0]), p=0.0, odds=v[2], y=v[1]))

    # Coverage against the sheets.
    ungraded: Counter[str] = Counter()
    ungraded_n = 0
    seen: set[Key] = set()
    for day in days:
        skips = skip_reasons(day)
        for key in sheet_keys(day):
            if key in seen:  # the same line on two days' sheets counts once
                continue
            seen.add(key)
            if key in graded:
                continue
            ungraded_n += 1
            reasons = skips.get(key[0]) or ["no settled row"]
            ungraded[",".join(reasons)] += 1

    print(f"T-TENNIS-DF-UNDER-FORWARD  window {args.start} .. {last} "
          f"(settled days {len(days)}: {days[0]} .. {last})")
    print("collector: none in the repo before this script; source "
          "sofa_settled_row (SETTLE's grades)")
    print(f"settled_row UNDER rows by outcome: {dict(outcomes)}; "
          f"WIN/LOSS without a price: {no_price}")
    print(f"sheet UNDER priced lines {len(seen)}; graded {len(seen) - ungraded_n}; "
          f"ungraded {ungraded_n} {dict(ungraded)}")
    print("\nday         legs matches  hit   1/odds  ROI")
    for day in days:
        d = per_day.get(day, [])
        if d:
            print(f"{day}  {len(d):4d}  {len({x.game for x in d}):5d}  "
                  f"{sum(x.y for x in d) / len(d):.3f}  "
                  f"{sum(1 / x.odds for x in d) / len(d):.3f}  {roi_of(d):+.3f}")
    if not lines:
        print("no graded leg")
        return 1
    for label, mk in (("all", None), *((m, m) for m in MARKETS)):
        sel = [x for k, x in zip(graded, lines, strict=True)
               if mk is None or k[1] == mk]
        if not sel:
            continue
        lo, hi = bootstrap_roi(sel, reps=args.reps)
        n, games = len(sel), len({x.game for x in sel})
        print(f"\n[{label}] legs {n}, matches {games}, hit "
              f"{sum(x.y for x in sel) / n:.4f}, mean 1/odds "
              f"{sum(1 / x.odds for x in sel) / n:.4f}, ROI {roi_of(sel):+.4f} "
              f"[{lo:+.4f}, {hi:+.4f}] (match bootstrap, {args.reps} reps)")

    n, games = len(lines), len({x.game for x in lines})
    lo, hi = bootstrap_roi(lines, reps=args.reps)
    verdict = frozen_verdict(n, games, lo, hi)
    if verdict is not None:
        print(f"\nthreshold reached ({n} >= {NEED_LEGS} legs, {games} >= "
              f"{NEED_MATCHES} matches): frozen rule -> {verdict}")
    else:
        print(f"\nINTERIM - NOT A VERDICT: {n}/{NEED_LEGS} legs, "
              f"{games}/{NEED_MATCHES} matches")
    seen_games: set[str] = set()
    cum = 0
    for day in days:
        cum += len(per_day.get(day, []))
        seen_games |= {x.game for x in per_day.get(day, [])}
        if cum >= NEED_LEGS and len(seen_games) >= NEED_MATCHES:
            print(f"both thresholds first met on settled day {day} "
                  f"({cum} legs, {len(seen_games)} matches)")
            break
    span = len(days)
    lpd, mpd = n / span, games / span
    print(f"rate over {span} settled days: {lpd:.1f} legs/day, {mpd:.1f} matches/day")
    need_days = max((NEED_LEGS - n) / lpd if lpd else float("inf"),
                    (NEED_MATCHES - games) / mpd if mpd else float("inf"), 0.0)
    eta = date.fromisoformat(last) + timedelta(days=int(-(-need_days // 1)))
    word = "reached" if need_days == 0 else "projected"
    print(f"threshold {word} by day {eta.isoformat()}"
          + ("" if need_days == 0 else f" (+{need_days:.1f} days)"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
