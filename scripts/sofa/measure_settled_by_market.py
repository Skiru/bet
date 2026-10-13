#!/usr/bin/env python3
"""Settled lines by market family and direction, every sport (read-only evidence).

For a date range: how the settled lines realised against the model and the
price, per (market, direction) and per (quantity family, direction) - n lines,
n games, hit rate, mean model p, mean 1/odds, ROI per unit and a 95% bootstrap
interval of the ROI over games (fixed seed), at p >= --p-min (default 0.70).

Measured: the RAW model p (football / tennis `p_central`; the sports' pre-game
model p), NOT the calibrated confidence; every offered rung; no coupon gate
(margin, freshness, ODDS_TOO_LOW...). Football and tennis come from
`sofa_settled_row` (data/sofa.db, opened read-only); hockey / basketball /
volleyball from the line-evidence rows (the model's p built before each day,
SHADOW_SETTLE's graded price) and CS2 from runs/sofa/cs2/<d>/settled.json.
The sports are never pooled: each has its own table.

  PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_settled_by_market.py \
      --from 2026-10-09 --to 2026-10-12 [--p-min 0.70] [--min-n 20] \
      [--sport-rows-dir data/line_evidence/rows_before_2026-10-13] \
      [--md-out f] [--json-out f]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT / "src"), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import settled_by_market as sbm  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.settleability import settle_family  # noqa: E402

DB_SPORTS = ("football", "tennis")
ROW_SPORTS = ("hockey", "basketball", "volleyball")
Cells = dict[tuple[str, ...], list[sbm.Line]]
Rows = list[tuple[str, str, sbm.Line]]


def day_range(first: str, last: str) -> list[str]:
    d, end = date.fromisoformat(first), date.fromisoformat(last)
    out = []
    while d <= end:
        out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def db_lines(db_path: str, first: str, last: str) -> dict[str, Rows]:
    """sport -> [(market, direction, Line)] of football / tennis WIN / LOSS rows."""
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        cur = con.execute(
            "select sport, market, direction, sofascore_event_id, p_central,"
            " offered_odds, outcome from sofa_settled_row"
            " where run_date between ? and ? and run_date != 'cache-calibration'"
            " and outcome in ('WIN','LOSS') and p_central is not null"
            " and offered_odds is not null and offered_odds > 1.0", (first, last))
        out: dict[str, Rows] = defaultdict(list)
        for sport, market, direction, eid, p, odds, outcome in cur:
            out[str(sport)].append((str(market), str(direction), sbm.Line(
                f"{sport}:{eid}", float(p), float(odds),
                1 if outcome == "WIN" else 0)))
        return out
    finally:
        con.close()


def row_sport_lines(rows_dir: Path, runs_dir: str, sport: str,
                    days: set[str]) -> Rows:
    """The line-evidence rows of a sport (model p) joined to the graded price."""
    from scripts.sofa.fit_line_evidence import graded_odds
    path = rows_dir / f"{sport}_superbet_settled.jsonl"
    if not path.exists():
        return []
    prices: dict[str, dict[tuple[Any, ...], float]] = {}
    out: Rows = []
    for text in path.read_text(encoding="utf-8").splitlines():
        r = json.loads(text)
        _, day, eid = str(r["game"]).split(":")
        if day not in days:
            continue
        if day not in prices:
            prices[day] = graded_odds(runs_dir, sport, day)
        odds = prices[day].get((eid, r["family"], int(r.get("period") or 0),
                                str(r.get("subject") or ""), r.get("line"),
                                r["side"]))
        if odds is None or odds <= 1.0:
            continue
        out.append((str(r["family"]), str(r["key"]).split("|")[1], sbm.Line(
            str(r["game"]), float(r["p"]), float(odds), int(r["y"]))))
    return out


def cs2_lines(runs_dir: str, days: list[str]) -> Rows:
    out: Rows = []
    for day in days:
        path = Path(runs_dir) / "cs2" / day / "settled.json"
        if not path.exists():
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        for sb_id, ev in (doc.get("events") or {}).items():
            for g in ev.get("graded") or []:
                if g.get("outcome") not in ("WIN", "LOSS") \
                        or g.get("model_p") is None or not g.get("odds") \
                        or float(g["odds"]) <= 1.0:
                    continue
                out.append((str(g["family"]), str(g["side"]), sbm.Line(
                    f"cs2:{day}:{sb_id}", float(g["model_p"]), float(g["odds"]),
                    1 if g["outcome"] == "WIN" else 0)))
    return out


def group(rows: Rows, by_family: bool) -> Cells:
    cells: Cells = defaultdict(list)
    for market, direction, line in rows:
        key = settle_family(market) if by_family else market
        cells[(key, direction)].append(line)
    return cells


def sport_section(sport: str, rows: Rows, p_min: float, min_n: int,
                  football_like: bool) -> dict[str, Any]:
    """Tables of one sport; the quantity-family view only for football /
    tennis markets (settle_family reads those names)."""
    views: dict[str, Any] = {
        "market_direction": sbm.table(group(rows, False), p_min, min_n)}
    if football_like:
        views["family_direction"] = sbm.table(group(rows, True), p_min, min_n)
    return {"sport": sport, "lines_all": len(rows),
            "games_all": len({x[2].game for x in rows}),
            "overall": sbm.cell_stats([x[2] for x in rows], p_min), **views}


def render(result: dict[str, Any]) -> str:
    p_min, min_n = result["p_min"], result["min_n"]
    out = [f"# Settled lines by market and direction, {result['from']}..{result['to']}",
           "",
           f"Measured: RAW model p (not the calibrated confidence) >= {p_min:.2f}, "
           "every offered rung, no coupon gates (margin, freshness, "
           "ODDS_TOO_LOW, reads). ROI per unit at the offered price; interval = "
           f"95% bootstrap over games/matches ({sbm.REPS} draws, seed {sbm.SEED}). "
           f"Cells under n = {min_n} lines are left out. Each sport has its own "
           "table and is never pooled with another.", ""]
    total = sum(len(sec[k]) for sec in result["sports"]
                for k in ("market_direction", "family_direction") if k in sec)
    out += [f"**Multiple comparisons: this report holds {total} table rows "
            f"({len(result['sports'])} sports). One row in twenty clears zero "
            "by chance alone (CLAUDE.md); the market and family views of one "
            "sport overlap and one game gives several lines. A row is a lead "
            "for a pre-registered check, never a rule.**", ""]
    for sec in result["sports"]:
        ov = sec["overall"]
        out += [f"## {sec['sport']}", "",
                f"{sec['lines_all']} settled WIN/LOSS lines with a price, "
                f"{sec['games_all']} games (all p).", ""]
        if ov:
            out += [f"At p >= {p_min:.2f}: n {ov['n']}, games {ov['games']}, "
                    f"hit {ov['hit']:.3f}, model {ov['model']:.3f}, "
                    f"1/odds {ov['implied']:.3f}, ROI {100 * ov['roi']:+.1f}% "
                    f"[{100 * ov['roi_lo']:+.1f}, {100 * ov['roi_hi']:+.1f}].", ""]
        else:
            out += [f"No lines at p >= {p_min:.2f}.", ""]
        out.append(sbm.render_markdown(f"{sec['sport']}: market x direction",
                                       sec["market_direction"],
                                       ["market", "direction"]))
        if "family_direction" in sec:
            out.append(sbm.render_markdown(
                f"{sec['sport']}: quantity family x direction",
                sec["family_direction"], ["family", "direction"]))
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--from", dest="first", required=True)
    ap.add_argument("--to", dest="last", required=True)
    ap.add_argument("--p-min", type=float, default=0.70)
    ap.add_argument("--min-n", type=int, default=20)
    ap.add_argument("--db-path", default=None)
    ap.add_argument("--sport-rows-dir", default=None)
    ap.add_argument("--md-out", default=None)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()

    cfg = SofaConfig.from_env()
    days = day_range(args.first, args.last)
    db_path = args.db_path or str(_ROOT / "data" / "sofa.db")
    next_day = (date.fromisoformat(args.last) + timedelta(days=1)).isoformat()
    rows_dir = Path(args.sport_rows_dir or
                    _ROOT / "data" / "line_evidence" / f"rows_before_{next_day}")
    sections: list[dict[str, Any]] = []
    skipped: list[str] = []
    by_sport = db_lines(db_path, args.first, args.last)
    for sport in DB_SPORTS:
        sections.append(sport_section(sport, by_sport.get(sport, []), args.p_min,
                                      args.min_n, True))
    for sport in ROW_SPORTS:
        rows = row_sport_lines(rows_dir, cfg.runs_dir, sport, set(days))
        if not rows:
            skipped.append(f"{sport}: no rows in {rows_dir}")
        sections.append(sport_section(sport, rows, args.p_min, args.min_n, False))
    cs2 = cs2_lines(cfg.runs_dir, days)
    if not cs2:
        skipped.append("cs2: no settled.json lines")
    sections.append(sport_section("cs2", cs2, args.p_min, args.min_n, False))
    result = {"from": args.first, "to": args.last, "p_min": args.p_min,
              "min_n": args.min_n, "seed": sbm.SEED, "reps": sbm.REPS,
              "sport_rows_dir": str(rows_dir), "skipped": skipped,
              "sports": sections}
    text = render(result)
    if skipped:
        text += "\nSkipped: " + "; ".join(skipped) + "\n"
    print(text)
    if args.md_out:
        Path(args.md_out).write_text(text, encoding="utf-8")
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(result, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
