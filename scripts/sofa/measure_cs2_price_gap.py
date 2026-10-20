#!/usr/bin/env python3
"""CS2: does a confidence above the price realise below it? Read-only.

The football / tennis flag (bet.sofa.price_gap) was measured on printed legs;
CS2 printed too few (80 legs on 10-07..10-19) to say anything. So this reads
every settled Superbet CS2 line (runs/sofa/cs2/<d>/settled.json `graded`):
the engine's `model_p` at settle mapped through the installed sport curve
(sport_confidence.SportCalibration.lookup, any fitted key, as CONFIDENCE reads
it under line evidence), kept when it would clear the coupon's floor and x
(COUPON_PROFILE), split by confidence minus 1/odds > price_gap.GAP. Reported:
realised minus confidence and minus Superbet's de-margined price (`fair_p`),
and ROI at the printed price, each with a 95% interval from resampling series.

Not applied: the line evidence (offset / price-band cap only lower a
confidence, so some of these lines would not have cleared the floor), and the
`model_p` of an older day is the engine of that day.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_cs2_price_gap.py \\
        [--from 2026-09-28] [--to 2026-10-19] [--md-out f]
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import price_gap as pgap  # noqa: E402
from bet.sofa.confidence import COUPON_PROFILE  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.sport_confidence import (  # noqa: E402
    SportCalibration,
    calibration_path_for,
)

SERIES_FAMILIES = frozenset(
    {"team_maps", "maps_handicap", "match_winner", "maps_total"})
BOOT = 2000


@dataclass(frozen=True)
class Line:
    game: str
    family: str
    conf: float
    fair: float
    odds: float
    won: int

    @property
    def over_price(self) -> float:
        return self.conf - 1.0 / self.odds


def lines_of(doc: dict[str, Any], day: str, cal: SportCalibration) -> list[Line]:
    """One settled.json's graded WIN / LOSS lines that carry a model p, a fair
    price and a fitted curve, the confidence the curve gives them."""
    out: list[Line] = []
    for ev in (doc.get("events") or {}).values():
        if ev.get("state") != "SETTLED":
            continue
        for g in ev.get("graded") or []:
            if (g.get("outcome") not in ("WIN", "LOSS") or g.get("model_p") is None
                    or g.get("fair_p") is None or not g.get("odds")):
                continue
            c = cal.lookup("cs2", str(g["family"]), str(g.get("side") or ""),
                           float(g["model_p"]), require_admitted=False)
            if c is None:
                continue
            out.append(Line(f"{day}:{ev.get('sofascore_event_id')}", str(g["family"]),
                            c.value, float(g["fair_p"]), float(g["odds"]),
                            int(g["outcome"] == "WIN")))
    return out


def printable(lines: Sequence[Line]) -> list[Line]:
    return [x for x in lines
            if x.conf >= COUPON_PROFILE.floor
            and COUPON_PROFILE.clears_price(x.conf, x.odds)]


def flagged(x: Line) -> bool:
    """The flag's own rule (price_gap.annotate)."""
    return round(x.over_price, 9) > pgap.GAP


def summary(lines: Sequence[Line], rng: random.Random,
            boot: int = BOOT) -> dict[str, Any]:
    """Realised minus confidence / fair price and ROI, with 95% intervals from
    resampling series (lines of one series are not independent)."""
    if not lines:
        return {"n": 0}
    games: dict[str, list[Line]] = defaultdict(list)
    for x in lines:
        games[x.game].append(x)
    keys = list(games)

    def stat(xs: Sequence[Line]) -> tuple[float, float, float]:
        n = len(xs)
        hit = sum(x.won for x in xs) / n
        return (hit - sum(x.conf for x in xs) / n, hit - sum(x.fair for x in xs) / n,
                sum(x.won * x.odds - 1.0 for x in xs) / n)

    point = stat(lines)
    draws = [stat([x for k in rng.choices(keys, k=len(keys)) for x in games[k]])
             for _ in range(boot)]

    def ci(i: int) -> list[float]:
        vals = sorted(d[i] for d in draws)
        return [round(vals[int(0.025 * boot)], 4),
                round(vals[int(0.975 * boot) - 1], 4)]

    n = len(lines)
    return {"n": n, "games": len(keys),
            "hit": round(sum(x.won for x in lines) / n, 4),
            "conf": round(sum(x.conf for x in lines) / n, 4),
            "fair": round(sum(x.fair for x in lines) / n, 4),
            "hit_minus_conf": round(point[0], 4), "hit_minus_conf_ci": ci(0),
            "hit_minus_fair": round(point[1], 4), "hit_minus_fair_ci": ci(1),
            "roi": round(point[2], 4), "roi_ci": ci(2)}


def sections(lines: Sequence[Line], rng: random.Random) -> dict[str, dict[str, Any]]:
    pr = printable(lines)
    series = [x for x in pr if x.family in SERIES_FAMILIES]
    return {
        "printable": summary(pr, rng),
        "flagged": summary([x for x in pr if flagged(x)], rng),
        "not_flagged": summary([x for x in pr if not flagged(x)], rng),
        "series_flagged": summary([x for x in series if flagged(x)], rng),
        "series_not_flagged": summary([x for x in series if not flagged(x)], rng),
    }


LABELS = {
    "printable": "drukowalne (pewność >= 0,70, x >= 0,90)",
    "flagged": f"pewność > 1/kurs + {pgap.GAP:.2f} (flaga)",
    "not_flagged": "reszta",
    "series_flagged": "rodziny serii, flaga",
    "series_not_flagged": "rodziny serii, reszta",
}


def render(res: dict[str, dict[str, Any]], lo: str, hi: str) -> str:
    def pp(v: float) -> str:
        return f"{100 * v:+.1f}"

    out = [f"# CS2: pewność ponad cenę - linie Superbetu {lo}..{hi}", "",
           "Krzywa CS2 na `model_p` z rozliczenia, bez dowodów z linii; "
           "bootstrap po seriach.", "",
           "| grupa | linie | serie | trafione | pewność | cena bez marży "
           "| trafione - pewność, pp [95%] | trafione - cena, pp [95%] | ROI % [95%] |",
           "|---|---|---|---|---|---|---|---|---|"]
    for key, s in res.items():
        if not s.get("n"):
            out.append(f"| {LABELS[key]} | 0 | | | | | | | |")
            continue
        a, b, c = s["hit_minus_conf_ci"], s["hit_minus_fair_ci"], s["roi_ci"]
        out.append(
            f"| {LABELS[key]} | {s['n']} | {s['games']} | {s['hit']:.3f} "
            f"| {s['conf']:.3f} "
            f"| {s['fair']:.3f} | {pp(s['hit_minus_conf'])} [{pp(a[0])}, {pp(a[1])}] "
            f"| {pp(s['hit_minus_fair'])} [{pp(b[0])}, {pp(b[1])}] "
            f"| {pp(s['roi'])} [{pp(c[0])}, {pp(c[1])}] |")
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--from", dest="date_from", default="2026-09-28")
    ap.add_argument("--to", dest="date_to", default="2026-10-19")
    ap.add_argument("--md-out", default=None)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()
    runs = Path(SofaConfig.from_env().runs_dir)
    cal = SportCalibration.load(calibration_path_for(args.date_to))
    if cal is None:
        print("NO_CALIBRATION", file=sys.stderr)
        return 2
    lines: list[Line] = []
    for path in sorted((runs / "cs2").glob("2026-*/settled.json")):
        day = path.parent.name
        if args.date_from <= day <= args.date_to:
            lines += lines_of(json.loads(path.read_text("utf-8")), day, cal)
    res = sections(lines, random.Random(7))
    text = render(res, args.date_from, args.date_to)
    if args.md_out:
        Path(args.md_out).write_text(text, encoding="utf-8")
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 - exit code contract: 2 on a crash
        print(f"MEASURE_CS2_PRICE_GAP_FAILED: {exc!r}", file=sys.stderr)
        sys.exit(2)
