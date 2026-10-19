#!/usr/bin/env python3
# ruff: noqa: E501  - report lines are tables.
"""Red flags on the official coupon's printed legs (read-only evidence;
docs/sofa/evidence/red_flags_2026-10-19.md, registered before the run).

A flag is worth showing only if the legs it marks realise BELOW their
confidence by more than the legs it does not mark. For each flag: the gap
(hit rate - mean confidence) of the flagged legs minus the control's, with a
paired bootstrap over (day, match) clusters, 98.75% (Bonferroni over the four
flags); ROI at the printed price as a second number; the sign day by day.
F3 judges the printed builders against their own combined probability.

Reads only day artifacts: 13_results.json (the ledger's grades), 11_coupon.json
and 05_sheet.json (the side's expected goal difference SHEET wrote in its
GAME_STATE / COUNT_STRETCH note). No network, no database.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_red_flags.py \\
        --from 2026-10-13 --to 2026-10-18 [--md-out f]
"""

from __future__ import annotations

import argparse
import datetime
import json
import random
import re
import sys
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
LEVEL = 0.9875  # 1 - 0.05 / 4
DRAWS = 2000
SEED = 20261019
SCRIPT_MARKETS = frozenset({
    "shots_for", "shots_on_target_for", "shots_1h_for", "shots_2h_for",
    "corners_for", "corners_1h_for", "corners_2h_for",
})
EGD = re.compile(r"expected goal difference ([+-]?\d+(?:\.\d+)?)")


@dataclass(frozen=True)
class Leg:
    day: str
    event: int
    sport: str
    market: str
    subject: str
    direction: str
    odds: float
    confidence: float
    won: bool
    single: dict[str, Any] | None
    egd: float | None

    @property
    def cluster(self) -> tuple[str, int]:
        return self.day, self.event

    @property
    def units(self) -> float:
        return self.odds - 1.0 if self.won else -1.0


def leg_key(event: Any, market: str, subject: Any, line: Any, direction: str) -> str:
    return json.dumps([event, market, subject or "", line, direction], ensure_ascii=False)


def side_egd(sheet: list[dict[str, Any]]) -> dict[tuple[int, str], float]:
    """(event, team subject) -> the expected goal difference SHEET used."""
    out: dict[tuple[int, str], float] = {}
    for row in sheet:
        if row.get("sport") != "football" or not row.get("subject"):
            continue
        if str(row.get("market", "")).startswith("player_"):
            continue
        for note in row.get("notes") or []:
            m = EGD.search(str(note))
            if m:
                out[(int(row["sofascore_event_id"]), str(row["subject"]))] = float(m.group(1))
                break
    return out


def load_day(runs: Path, day: str) -> tuple[list[Leg], list[dict[str, Any]]]:
    d = runs / day
    results = json.loads((d / "13_results.json").read_text())
    coupon = json.loads((d / "11_coupon.json").read_text())
    sheet = json.loads((d / "05_sheet.json").read_text())
    egd = side_egd(sheet)
    singles = {
        leg_key(o["sofascore_event_id"], o["market"], o.get("subject"), o["line"], o["direction"]): o
        for o in coupon.get("singles") or []
    }
    legs: list[Leg] = []
    for key, v in (results.get("legs") or {}).items():
        if v.get("status") not in ("won", "lost") or not v.get("odds") or v.get("confidence") is None:
            continue
        parsed = json.loads(key)
        single = singles.get(key)
        event = int(parsed[0])
        market = str(parsed[1])
        subject = str(parsed[2]) if isinstance(parsed[2], str) else ""
        direction = next((str(x) for x in parsed if x in ("OVER", "UNDER")), "")
        legs.append(Leg(
            day=day, event=event, sport=str(v.get("sport") or "football"), market=market,
            subject=subject, direction=direction, odds=float(v["odds"]),
            confidence=float(v["confidence"]), won=v["status"] == "won", single=single,
            egd=egd.get((event, subject)) if subject else None,
        ))
    builders: list[dict[str, Any]] = []
    by_legs = {}
    for b in coupon.get("builders") or []:
        keys = sorted(
            leg_key(b["sofascore_event_id"], x["market"], x.get("subject"), x["line"], x["direction"])
            for x in b.get("legs") or []
        )
        by_legs[(int(b["sofascore_event_id"]), tuple(keys))] = b
    for key, v in (results.get("builders") or {}).items():
        if v.get("status") not in ("won", "lost"):
            continue
        event, keys = json.loads(key)
        b = by_legs.get((int(event), tuple(sorted(keys))))
        if b is None or b.get("combined_probability") is None:
            continue
        builders.append({
            "day": day, "event": int(event), "won": v["status"] == "won",
            "combined": float(b["combined_probability"]),
            "product": float(b.get("product_probability") or float("nan")),
            "n_legs": len(keys),
        })
    return legs, builders


def gap(legs: Sequence[Leg]) -> float:
    return sum(x.won - x.confidence for x in legs) / len(legs) if legs else float("nan")


def roi(legs: Sequence[Leg]) -> float:
    return sum(x.units for x in legs) / len(legs) if legs else float("nan")


def interval(values: list[float]) -> tuple[float, float]:
    values = sorted(v for v in values if v == v)
    if not values:
        return float("nan"), float("nan")
    lo = values[int((1 - LEVEL) / 2 * len(values))]
    hi = values[min(len(values) - 1, int((1 + LEVEL) / 2 * len(values)))]
    return lo, hi


def paired(flagged: Sequence[Leg], control: Sequence[Leg],
           stat: Callable[[Sequence[Leg]], float]) -> tuple[float, float, float]:
    """flagged-minus-control `stat` and its interval, resampling (day, match)."""
    groups: dict[tuple[str, int], tuple[list[Leg], list[Leg]]] = defaultdict(lambda: ([], []))
    for x in flagged:
        groups[x.cluster][0].append(x)
    for x in control:
        groups[x.cluster][1].append(x)
    keys = list(groups)
    rnd = random.Random(SEED)
    out = []
    for _ in range(DRAWS):
        f: list[Leg] = []
        c: list[Leg] = []
        for _ in keys:
            a, b = groups[keys[rnd.randrange(len(keys))]]
            f.extend(a)
            c.extend(b)
        if f and c:
            out.append(stat(f) - stat(c))
    lo, hi = interval(out)
    return stat(flagged) - stat(control), lo, hi


def pp(v: float) -> str:
    return f"{v * 100:+.1f}"


def describe(name: str, legs: Sequence[Leg]) -> str:
    if not legs:
        return f"| {name} | 0 | | | | | |"
    matches = len({x.cluster for x in legs})
    conf = sum(x.confidence for x in legs) / len(legs)
    hit = sum(x.won for x in legs) / len(legs)
    price = sum(1 / x.odds for x in legs) / len(legs)
    return (f"| {name} | {len(legs):,} / {matches:,} | {conf:.3f} | {hit:.3f} | {price:.3f} "
            f"| {pp(hit - conf)} | {roi(legs) * 100:+.1f}% |")


def flag_section(title: str, flagged: list[Leg], control: list[Leg], extra: list[tuple[str, list[Leg]]]) -> list[str]:
    lines = [f"### {title}", "",
             "| grupa | nogi / mecze | pewność | trafienie | 1/kurs | luka pp | ROI |",
             "|---|---|---|---|---|---|---|",
             describe("oznaczone", flagged), describe("kontrola", control)]
    lines += [describe(n, x) for n, x in extra]
    if flagged and control:
        d, lo, hi = paired(flagged, control, gap)
        r, rlo, rhi = paired(flagged, control, roi)
        lines += ["", f"- luka oznaczone - kontrola: **{pp(d)} pp [{pp(lo)}, {pp(hi)}]** ({LEVEL:.2%})",
                  f"- ROI oznaczone - kontrola: {r * 100:+.1f} pp [{rlo * 100:+.1f}, {rhi * 100:+.1f}]"]
        per_day = []
        neg = counted = 0
        for day in sorted({x.day for x in flagged}):
            f = [x for x in flagged if x.day == day]
            c = [x for x in control if x.day == day]
            if not c:
                continue
            delta = gap(f) - gap(c)
            per_day.append(f"{day[5:]} {pp(delta)} (n {len(f)})")
            if len(f) >= 30:
                counted += 1
                neg += delta < 0
        lines.append(f"- dzień po dniu (luka oznaczone - kontrola, pp): {'; '.join(per_day)}")
        works = hi < 0 and counted > 0 and neg * 2 > counted
        lines.append(f"- dni z >= 30 oznaczonymi: {neg} z {counted} ujemne")
        lines.append(f"- **werdykt: {'DZIAŁA' if works else 'brak'}**")
    lines.append("")
    return lines


def builder_section(builders: list[dict[str, Any]]) -> list[str]:
    lines = ["### F3 BUILDER", ""]
    if not builders:
        return lines + ["brak ocenionych builderów", ""]

    def stat(sample: Sequence[dict[str, Any]], field: str) -> float:
        rows = [b for b in sample if b[field] == b[field]]
        return sum(b["won"] - b[field] for b in rows) / len(rows) if rows else float("nan")

    groups: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for b in builders:
        groups[(b["day"], b["event"])].append(b)
    keys = list(groups)
    lines += ["| porównanie | buildery / mecze | obiecane | trafienie | luka pp | przedział 98,75% |", "|---|---|---|---|---|---|"]
    for field, label in (("combined", "combined_probability"), ("product", "iloczyn pewności nóg")):
        rows = [b for b in builders if b[field] == b[field]]
        rnd = random.Random(SEED)
        draws = []
        for _ in range(DRAWS):
            sample = [b for _ in keys for b in groups[keys[rnd.randrange(len(keys))]]]
            draws.append(stat(sample, field))
        lo, hi = interval(draws)
        promised = sum(b[field] for b in rows) / len(rows)
        hit = sum(b["won"] for b in rows) / len(rows)
        lines.append(f"| {label} | {len(rows):,} / {len({(b['day'], b['event']) for b in rows}):,} | {promised:.3f} | {hit:.3f} | {pp(hit - promised)} | [{pp(lo)}, {pp(hi)}] |")
        if field == "combined":
            works = hi < 0
    by_n: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for b in builders:
        by_n[min(b["n_legs"], 4)].append(b)
    lines += ["", "| nóg | buildery | combined | trafienie | luka pp |", "|---|---|---|---|---|"]
    for n in sorted(by_n):
        rows = by_n[n]
        c = sum(b["combined"] for b in rows) / len(rows)
        h = sum(b["won"] for b in rows) / len(rows)
        lines.append(f"| {n}{'+' if n == 4 else ''} | {len(rows):,} | {c:.3f} | {h:.3f} | {pp(h - c)} |")
    lines += ["", f"- **werdykt: {'DZIAŁA (buildery obiecują za dużo)' if works else 'brak'}**", ""]
    return lines


def days_between(start: str, end: str) -> list[str]:
    a, b = datetime.date.fromisoformat(start), datetime.date.fromisoformat(end)
    return [(a + datetime.timedelta(days=i)).isoformat() for i in range((b - a).days + 1)]


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--from", dest="start", required=True)
    ap.add_argument("--to", dest="end", required=True)
    ap.add_argument("--runs-dir", default=str(_ROOT / "runs" / "sofa"))
    ap.add_argument("--md-out")
    args = ap.parse_args(argv)

    legs: list[Leg] = []
    builders: list[dict[str, Any]] = []
    used: list[str] = []
    for day in days_between(args.start, args.end):
        try:
            day_legs, day_builders = load_day(Path(args.runs_dir), day)
        except FileNotFoundError as exc:
            print(f"{day}: skipped ({exc.filename})", file=sys.stderr)
            continue
        legs += day_legs
        builders += day_builders
        used.append(day)

    script = [x for x in legs if x.sport == "football" and x.market in SCRIPT_MARKETS
              and x.direction == "OVER" and x.egd is not None]
    f1 = [x for x in script if x.egd is not None and x.egd >= 0.5]
    c1 = [x for x in script if x.egd is not None and x.egd < 0.5]
    f1b = [x for x in script if x.egd is not None and x.egd >= 1.0]
    unknown = sum(1 for x in legs if x.sport == "football" and x.market in SCRIPT_MARKETS
                  and x.direction == "OVER" and x.egd is None)

    sampled = []
    for x in legs:
        s = x.single
        if x.sport not in ("football", "tennis") or not s:
            continue
        if s.get("sample_hit_rate") is None or (s.get("sample_size") or 0) < 5:
            continue
        sampled.append((x, x.confidence - float(s["sample_hit_rate"])))
    f2 = [x for x, g in sampled if g >= 0.10]
    c2 = [x for x, g in sampled if g < 0.10]

    f4 = [x for x in legs if x.odds >= 1.40 and x.confidence < 0.75]
    c4 = [x for x in legs if not (x.odds >= 1.40 and x.confidence < 0.75)]

    out = [f"# Czerwone flagi - wynik ({', '.join(d[5:] for d in used)})", "",
           f"Nogi ocenione (won / lost): {len(legs):,}; mecze: {len({x.cluster for x in legs}):,}. "
           f"Luka = trafienie - pewność. Przedziały {LEVEL:.2%}, bootstrap po (dzień, mecz), {DRAWS} powtórzeń.", ""]
    out += flag_section("F1 SCENARIUSZ (strona OVER strzały / rożne, s >= +0,5)", f1, c1,
                        [("s >= +1,0 (wtórnie)", f1b)])
    out.append(f"Nogi F1-rynków OVER bez znanego s (poza pomiarem): {unknown:,}.\n")
    out += flag_section("F2 PRÓBKA (pewność - k/n >= 0,10)", f2, c2, [])
    out += builder_section(builders)
    out += flag_section("F4 KURS (kurs >= 1,40 i pewność < 0,75)", f4, c4, [])
    text = "\n".join(out)
    print(text)
    if args.md_out:
        Path(args.md_out).write_text(text + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
