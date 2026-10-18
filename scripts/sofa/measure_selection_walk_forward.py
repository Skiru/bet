#!/usr/bin/env python3
# ruff: noqa: E501  - report lines are tables.
"""Walk-forward of leg selections on the official coupon's printed legs
(read-only evidence; T-FAMILY-SELECTION).

For every test day D: the families' record of the days before D exactly as
the HTML view builds it (bet.sofa.family_record: `window(D)`, `on_plus`,
`selected`), then the ROI of the legs of D each selection keeps and of the
rest, graded as the ledger grades them (build_family_record.graded_day, with
today's settlement - a live record at D's build saw D-1 less settled).
Intervals: 95%, resampling (day, match) clusters; the selection minus the
rest is paired on the same draws. One day can hold most of the legs, so the
per-day table and the count of days the selection beat the rest are the
check that the pooled number is not one day.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_selection_walk_forward.py \\
        --from 2026-10-12 --to 2026-10-17 [--md-out f]
"""

from __future__ import annotations

import argparse
import datetime
import random
import sys
from collections import defaultdict
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT / "src"), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import family_record as fr  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402
from scripts.sofa.build_family_record import graded_day  # noqa: E402

# (day, leg, outcome, odds) of a WIN / LOSS leg
Leg = tuple[str, Any, str, float]
EDGES = ((-1.0, -0.05), (-0.05, -0.02), (-0.02, 0.0), (0.0, 0.03), (0.03, 1.0))
SELECTION = "x >= 1 i rodzina na plusie (przycisk widoku)"


def units(leg: Leg) -> float:
    return leg[3] - 1.0 if leg[2] == "WIN" else -1.0


def edge(leg: Leg) -> float:
    return float(leg[1]["confidence"]) - 1.0 / leg[3]


def sport(leg: Leg) -> str:
    return str(leg[1].get("sport") or "football")


def cluster(leg: Leg) -> tuple[str, str]:
    return leg[0], str(leg[1].get("group_key") or leg[1].get("sofascore_event_id"))


def roi(legs: Sequence[Leg]) -> float:
    return sum(map(units, legs)) / len(legs) if legs else float("nan")


def gap(legs: Sequence[Leg]) -> float:
    return sum((x[2] == "WIN") - float(x[1]["confidence"]) for x in legs) / len(legs)


def draws(legs: Sequence[Leg], stat: Callable[[list[Leg]], float],
          n: int = 2000, seed: int = 7) -> tuple[float, float]:
    """95% interval of `stat` over resampled (day, match) clusters."""
    groups: dict[tuple[str, str], list[Leg]] = defaultdict(list)
    for leg in legs:
        groups[cluster(leg)].append(leg)
    keys = list(groups)
    rnd = random.Random(seed)
    out = []
    for _ in range(n):
        sample = [x for _ in keys for x in groups[keys[rnd.randrange(len(keys))]]]
        value = stat(sample)
        if value == value:  # a draw without one side has no difference
            out.append(value)
    out.sort()
    return out[int(0.025 * len(out))], out[int(0.975 * len(out)) - 1]


def pct(value: float, unit: str) -> str:
    return "—" if value != value else f"{value * 100:+.1f}{unit}"


def calib(name: str, legs: Sequence[Leg]) -> str:
    """Mean confidence and realised minus confidence, with its interval."""
    lo, hi = draws(legs, gap, n=1000)
    n = len(legs)
    return (f"| {name} | {n} | {len({cluster(x) for x in legs})} | "
            f"{sum(float(x[1]['confidence']) for x in legs) / n:.3f} | "
            f"{sum(x[2] == 'WIN' for x in legs) / n:.3f} | {gap(legs) * 100:+.1f} pp "
            f"[{lo * 100:+.1f}, {hi * 100:+.1f}] | {roi(legs) * 100:+.1f}% | {sum(map(units, legs)):+.1f} |")


def row(name: str, legs: Sequence[Leg]) -> str:
    if not legs:
        return f"| {name} | 0 | | | | | |"
    lo, hi = draws(legs, roi)
    n = len(legs)
    return (f"| {name} | {n} | {len({cluster(x) for x in legs})} | "
            f"{sum(x[2] == 'WIN' for x in legs) / n:.3f} | {sum(1 / x[3] for x in legs) / n:.3f} | "
            f"{sum(map(units, legs)):+.2f} | {roi(legs) * 100:+.1f}% [{lo * 100:+.1f}, {hi * 100:+.1f}] |")


def load(runs_dir: str, days: Sequence[str], db: str) -> dict[str, list[Leg]]:
    out: dict[str, list[Leg]] = {}
    for d in days:
        out[d] = [(d, leg, outcome, float(odds)) for leg, outcome, odds in
                  graded_day(runs_dir, d, db) if outcome in ("WIN", "LOSS") and odds]
    return out


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--from", dest="first", required=True)
    ap.add_argument("--to", dest="last", required=True)
    ap.add_argument("--runs-dir", default="runs/sofa")
    ap.add_argument("--db-path", default=None)
    ap.add_argument("--md-out", default=None)
    args = ap.parse_args(argv)
    db = args.db_path or SofaConfig.from_env().db_path
    first, last = (datetime.date.fromisoformat(x) for x in (args.first, args.last))
    tests = [(first + datetime.timedelta(days=i)).isoformat()
             for i in range((last - first).days + 1)]
    days = sorted({d for t in tests for d in fr.window(t)} | set(tests))
    legs = load(args.runs_dir, days, db)

    picks: dict[str, list[Leg]] = defaultdict(list)
    rest: list[Leg] = []
    chosen: list[str] = []
    daily = ["| dzień | okno (dni) | nogi dnia | selekcja: nogi | ROI selekcji | ROI reszty | selekcja - reszta |",
             "|---|---|---|---|---|---|---|"]
    beat = 0
    for t in tests:
        rec = fr.summarize((leg, outcome, odds) for d in fr.window(t)
                           for _d, leg, outcome, odds in legs.get(d, []))
        plus = frozenset(k for k, v in rec.items() if fr.on_plus(v))
        chosen.append(f"- {t}: {', '.join(sorted(plus)) or '-'}")
        sel_day: list[Leg] = []
        rest_day: list[Leg] = []
        for x in legs[t]:
            sel = fr.selected(x[1], plus)
            (sel_day if sel else rest_day).append(x)
            xv = fr.selection_x(x[1])
            rules = {"cały kupon": True, "x >= 1": xv is not None and xv >= 1.0,
                     "rodzina na plusie": fr.family_key(x[1]) in plus,
                     SELECTION: sel, "kurs 1.40-2.00": 1.4 <= x[3] < 2.0}
            for name, keep in rules.items():
                if keep:
                    picks[name].append(x)
        rest += rest_day
        diff = roi(sel_day) - roi(rest_day) if sel_day and rest_day else float("nan")
        beat += diff > 0
        daily.append(f"| {t} | {len(fr.window(t))} | {len(legs[t])} | {len(sel_day)} | "
                     f"{pct(roi(sel_day), '%')} | {pct(roi(rest_day), '%')} | {pct(diff, ' pp')} |")

    sel_all = picks[SELECTION]
    tagged = [(x, True) for x in sel_all] + [(x, False) for x in rest]
    pos = {id(x): s for x, s in tagged}

    def sel_minus_rest(sample: list[Leg]) -> float:
        a = [x for x in sample if pos[id(x)]]
        b = [x for x in sample if not pos[id(x)]]
        return roi(a) - roi(b) if a and b else float("nan")

    lo, hi = draws([x for x, _ in tagged], sel_minus_rest)
    share = max((sum(x[0] == t for x in sel_all) for t in tests), default=0)
    lines = [f"# Selekcja nóg walk-forward, dni testu {tests[0]}..{tests[-1]}", "",
             f"Rodziny z dni przed każdym dniem (`family_record.window`, >= {fr.MIN_LEGS} nóg, jednostki > 0); "
             "ROI przy cenie wydruku, przedziały 95% z losowania (dzień, mecz).", "",
             "| selekcja | nogi | mecze | trafione | 1/kurs | jednostki | ROI [95%] |",
             "|---|---|---|---|---|---|---|"]
    lines += [row(k, v) for k, v in picks.items()]
    lines += [row("reszta kuponu (bez selekcji)", rest), "",
              f"**Selekcja minus reszta: {(roi(sel_all) - roi(rest)) * 100:+.1f} pp "
              f"[{lo * 100:+.1f}, {hi * 100:+.1f}]** (pary na tych samych losowaniach). "
              f"Selekcja lepsza od reszty w {beat} z {len(tests)} dni; największy dzień to "
              f"{share / len(sel_all):.0%} nóg selekcji." if sel_all else "Selekcja pusta.", "",
              *daily, "", "Selekcja wg sportu:", "",
              "| sport | nogi | mecze | trafione | 1/kurs | jednostki | ROI [95%] |",
              "|---|---|---|---|---|---|---|"]
    lines += [row(s, [x for x in sel_all if sport(x) == s])
              for s in sorted({sport(x) for x in sel_all})]
    lines += ["", "Rodziny na plusie w dniu testu:", *chosen, ""]
    every = [x for d in days for x in legs.get(d, [])]
    lines += [f"Wszystkie nogi {days[0]}..{days[-1]}:", "",
              "| sport | nogi | mecze | trafione | 1/kurs | jednostki | ROI [95%] |",
              "|---|---|---|---|---|---|---|", row("wszystkie sporty", every)]
    lines += [row(s, [x for x in every if sport(x) == s]) for s in sorted({sport(x) for x in every})]
    calib_head = ["| {} | nogi | mecze | pewność | trafione | luka [95%] | ROI | jednostki |",
                  "|---|---|---|---|---|---|---|---|"]
    lines += ["", "Kalibracja wg sportu:", "", calib_head[0].format("sport"), calib_head[1]]
    lines += [calib(s, [x for x in every if sport(x) == s]) for s in sorted({sport(x) for x in every})]
    by_market: dict[tuple[str, str, str], list[Leg]] = defaultdict(list)
    for x in every:
        by_market[(sport(x), str(x[1].get("market")), str(x[1].get("direction")))].append(x)
    worst = sorted((v for v in by_market.values() if len(v) >= 60),
                   key=lambda v: sum(map(units, v)))[:10]
    lines += ["", "Rynki z największą stratą (>= 60 nóg):", "",
              calib_head[0].format("sport / rynek / kierunek"), calib_head[1]]
    lines += [calib(" / ".join((sport(v[0]), str(v[0][1].get("market")), str(v[0][1].get("direction")))), v)
              for v in worst]
    lines.append("")
    for s in sorted({sport(x) for x in every}):
        mine = [x for x in every if sport(x) == s]
        lines += [f"## {s}: luka kalibracji i ROI wg pewność - 1/kurs ({days[0]}..{days[-1]})", "",
                  "| pewność - 1/kurs | nogi | luka (trafione - pewność) [95%] | ROI |", "|---|---|---|---|"]
        for a, b in EDGES:
            cell = [x for x in mine if a <= edge(x) < b]
            if len(cell) < 20:
                continue
            glo, ghi = draws(cell, gap, n=1000)
            lines.append(f"| {a:+.2f}..{b:+.2f} | {len(cell)} | {gap(cell) * 100:+.1f} pp "
                         f"[{glo * 100:+.1f}, {ghi * 100:+.1f}] | {roi(cell) * 100:+.1f}% |")
        lines.append("")
    text = "\n".join(lines)
    if args.md_out:
        Path(args.md_out).write_text(text + "\n", encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
