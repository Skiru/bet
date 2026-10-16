#!/usr/bin/env python3
"""Would a footballer's line-evidence offset measured on the lines the coupon
would actually take (confidence x odds >= 0.90) correct the overstatement of
his printable Superbet lines? Walk-forward, read-only evidence.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_player_line_evidence.py \\
        --from <d> --to <d> [--md-out f] [--json-out f]

fit_line_evidence.py measures a key's offset on every settled sheet line whose
curve reads >= PRINTABLE_FROM (0.70), whatever its price. The coupon then
takes only the lines whose confidence x odds clears 0.90 - the ones where the
curve stands near or above Superbet's price - and on 10-12..10-15 the
footballers' such lines realised ~12 pp below their curve
(docs/sofa/evidence/player_sample_gates_2026-10-16.md) while the offset of
player_shots_for OVER read -0.007.

For each test day D in --from .. --to, the evidence is fitted on the
stats-only days before D exactly as fit_line_evidence.py fits it (the
football / tennis sheet rows, the installed curves) in two variants:

* V0 - today's rule;
* V1 - the `player_*` keys' printable lines are only those whose curve
  confidence x Superbet's price >= 0.90 (every other key, the bands and the
  buckets unchanged; the football pool loses those player lines too).

Every priced football player row of D's sheet with a WIN / LOSS is read as
CONFIDENCE reads it (curve, then LineEvidence.read: offset and price-band
cap; floor 0.70, x >= 0.90, one-sided single on a "market:" curve of
n >= 300), with the sample-shape gates ON (today) and OFF (the player-gate
switch). Reported per variant and scenario: legs that print, confidence,
realised, realised minus confidence and ROI (match bootstrap, days pooled),
and the legs V1 drops from V0's print with how they did.

Nothing is written but --md-out / --json-out. Exit 0, 2 on a crash.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from collections.abc import Callable, Sequence
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
for _p in (str(ROOT), str(ROOT / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import line_evidence as le  # noqa: E402
from bet.sofa.confidence import (  # noqa: E402
    Calibration,
    curve_market,
    direction_key,
)
from bet.sofa.epochs import ONE_SIDED_MIN_CURVE_N  # noqa: E402
from bet.sofa.players import is_player_metric, player_observations  # noqa: E402
from scripts.sofa import fit_line_evidence as fle  # noqa: E402
from scripts.sofa.measure_player_sample_gates import PASS, gate_of  # noqa: E402

FLOOR = 0.70
MIN_X = 0.90
BOOT = 1000
PLAYER_PREFIX = "player_"


@dataclasses.dataclass(frozen=True)
class Leg:
    day: str
    event_id: int
    market: str
    subject: str
    line: float
    odds: float
    won: bool
    gate: str
    conf: dict[str, float | None]  # variant -> printed confidence, None = refused


def v1_rows(rows: Sequence[le.Row]) -> list[le.Row]:
    """V1: a player key's line counts as printable only when the coupon could
    take it at its price (base x odds >= MIN_X)."""
    out = []
    for r in rows:
        if str(r["key"]).startswith(PLAYER_PREFIX) and r.get("base") is not None \
                and float(r["base"]) * float(r["odds"] or 0.0) < MIN_X:
            r = {**r, "base": None}
        out.append(r)
    return out


def evidence(rows: Sequence[le.Row]) -> le.LineEvidence:
    """A LineEvidence of these rows, as fit_line_evidence.py writes it."""
    fitted = le.fit(rows)
    doc = {**fitted,
           "min_bucket": le.MIN_EVIDENCE_BUCKET, "min_cap_cell": le.MIN_CAP_CELL,
           "min_offset_rows": le.MIN_OFFSET_ROWS,
           "min_offset_games": le.MIN_OFFSET_GAMES,
           "min_sport_offset_games": le.MIN_SPORT_OFFSET_GAMES,
           "min_evidence_games": le.MIN_EVIDENCE_GAMES,
           "concentration_max": le.CONCENTRATION_MAX,
           "printable_from": le.PRINTABLE_FROM,
           "price_bands": [list(b) for b in le.PRICE_BANDS]}
    return le.LineEvidence(doc, v2=True, bucket_deff=True)


def read(cal: Calibration, ev: le.LineEvidence, r: dict[str, Any]) -> float | None:
    """The confidence the leg prints at, None when CONFIDENCE refuses it
    (no curve / evidence, floor, x, not an own-curve one-sided single)."""
    p, odds = float(r["p_central"]), float(r["offered_odds"])
    hit = cal.realised(curve_market(r), p, "football", r["direction"], None)
    key = le.evidence_key(direction_key(r["market"], r["direction"]))
    got = ev.read("football", key, p, hit, odds)
    if got is None or got.value < FLOOR or got.value * odds < MIN_X:
        return None
    if not (str(got.source).startswith("market:") and got.n >= ONE_SIDED_MIN_CURVE_N):
        return None
    return float(got.value)


def day_legs(runs: Path, day: str, cal: Calibration,
             evs: dict[str, le.LineEvidence]) -> list[Leg]:
    d = runs / day
    sheet = json.loads((d / "05_sheet.json").read_text(encoding="utf-8"))
    samples = {int(s["sofascore_event_id"]): s for s in
               json.loads((d / "03_samples.json").read_text(encoding="utf-8"))}
    outcome = {
        (r["sofascore_event_id"], r["market"], str(r.get("subject") or ""),
         float(r["line"]), r["direction"]): r["outcome"]
        for r in json.loads((d / "07_settled.json").read_text(encoding="utf-8"))
        if r.get("sport") == "football" and is_player_metric(str(r["market"]))}
    legs = []
    for r in sheet:
        if r.get("sport") != "football" or not is_player_metric(str(r["market"])) \
                or not r.get("offered_odds"):
            continue
        o = outcome.get((r["sofascore_event_id"], r["market"],
                         str(r.get("subject") or ""), float(r["line"]),
                         r["direction"]))
        if o not in ("WIN", "LOSS"):
            continue
        conf = {name: read(cal, ev, r) for name, ev in evs.items()}
        if all(c is None for c in conf.values()):
            continue
        obs = player_observations(samples.get(int(r["sofascore_event_id"]), {}),
                                  r["market"], r.get("subject") or "")
        values = [float(x["value"]) for x in obs if x.get("value") is not None]
        legs.append(Leg(day=day, event_id=int(r["sofascore_event_id"]),
                        market=str(r["market"]), subject=str(r.get("subject") or ""),
                        line=float(r["line"]), odds=float(r["offered_odds"]),
                        won=o == "WIN",
                        gate=gate_of(float(r["line"]), str(r["direction"]), values),
                        conf=conf))
    return legs


def _boot(legs: Sequence[Leg], conf: Callable[[Leg], float],
          seed: int = 7) -> dict[str, list[float]]:
    """Realised minus confidence and ROI, each with a 95% match bootstrap."""
    ids = sorted({(x.day, x.event_id) for x in legs})
    col = {e: i for i, e in enumerate(ids)}
    a = np.zeros((4, len(ids)))
    for x in legs:
        j = col[(x.day, x.event_id)]
        a[0, j] += 1.0
        a[1, j] += (1.0 if x.won else 0.0) - conf(x)
        a[2, j] += (x.odds - 1.0) if x.won else -1.0
    w = np.random.default_rng(seed).multinomial(
        len(ids), np.full(len(ids), 1.0 / len(ids)), size=BOOT)
    tot, draws = a.sum(axis=1), a @ w.T

    def ci(k: int) -> list[float]:
        d = draws[k] / draws[0]
        return [round(float(tot[k] / tot[0]), 4),
                round(float(np.quantile(d, 0.025)), 4),
                round(float(np.quantile(d, 0.975)), 4)]
    return {"gap": ci(1), "roi": ci(2)}


def describe(legs: Sequence[Leg], conf: Callable[[Leg], float]) -> dict[str, Any]:
    if not legs:
        return {"n": 0}
    return {"n": len(legs), "matches": len({(x.day, x.event_id) for x in legs}),
            "confidence": round(sum(conf(x) for x in legs) / len(legs), 4),
            "price": round(sum(1.0 / x.odds for x in legs) / len(legs), 4),
            "realised": round(sum(x.won for x in legs) / len(legs), 4),
            **_boot(legs, conf)}


def conf_of(variant: str) -> Callable[[Leg], float]:
    """A leg's printed confidence under `variant` (0 where it is refused)."""
    def get(leg: Leg) -> float:
        return float(leg.conf[variant] or 0.0)
    return get


def _fmt(t: Sequence[float]) -> str:
    return f"{100 * t[0]:+.1f} [{100 * t[1]:+.1f}, {100 * t[2]:+.1f}]"


def render(rows: list[tuple[str, dict[str, Any]]]) -> list[str]:
    out = ["| grupa | nogi | mecze | pewność | cena | zrealizowane "
           "| zreal. - pewn. (pp) | ROI % |", "|---|---|---|---|---|---|---|---|"]
    for name, e in rows:
        if not e["n"]:
            out.append(f"| {name} | 0 | | | | | | |")
            continue
        out.append(f"| {name} | {e['n']} | {e['matches']} | {e['confidence']:.3f} "
                   f"| {e['price']:.3f} | {e['realised']:.3f} | {_fmt(e['gap'])} "
                   f"| {_fmt(e['roi'])} |")
    return out + [""]


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--from", dest="date_from", required=True)
    ap.add_argument("--to", dest="date_to", required=True)
    ap.add_argument("--runs-dir", type=Path, default=ROOT / "runs" / "sofa")
    ap.add_argument("--calibration", type=Path,
                    default=ROOT / "config" / "sofa_confidence_calibration.json")
    ap.add_argument("--md-out", type=Path)
    ap.add_argument("--json-out", type=Path)
    args = ap.parse_args(argv)
    cal = dataclasses.replace(Calibration.load(args.calibration), gap_shrink_k=0.0,
                              cap_market_by_thin=True, cap_pool_by_neighbour=True)
    d0, d1 = date.fromisoformat(args.date_from), date.fromisoformat(args.date_to)
    all_days = fle.stats_only_days(args.runs_dir, (d1 + timedelta(days=1)).isoformat())
    rows_of = {day: list(fle.sheet_rows(args.runs_dir, [day], cal)) for day in all_days}
    legs: list[Leg] = []
    offsets: dict[str, dict[str, Any]] = {}
    for day in all_days:
        if not d0.isoformat() <= day <= d1.isoformat():
            continue
        train = [r for t in all_days if t < day for r in rows_of[t]]
        evs = {"V0": evidence(train), "V1": evidence(v1_rows(train))}
        offsets[day] = {
            v: {k: ev.offset("football", k) for k in sorted(
                (ev.doc.get("keys") or {}).get("football") or {})
                if k.startswith(PLAYER_PREFIX)}
            for v, ev in evs.items()}
        legs += day_legs(args.runs_dir, day, cal, evs)
        print(f"{day}: train days {len([t for t in all_days if t < day])}, "
              f"legs {len(legs)}", file=sys.stderr)

    report: dict[str, Any] = {"offsets": offsets, "groups": {}}
    md = ["# Line evidence zawodników liczone na liniach x >= 0.90 - walk-forward",
          "", f"Dni testowe {args.date_from}..{args.date_to}; evidence dopasowane na "
          "dniach stats-only przed każdym dniem; krzywa "
          f"`{args.calibration}`; przedziały 95% bootstrap po meczach.", ""]
    md += ["## Offset kluczy zawodników (V0 -> V1) na każdy dzień", "",
           "| dzień | klucz | V0 | V1 |", "|---|---|---|---|"]
    for day, by_v in offsets.items():
        for k in sorted(set(by_v["V0"]) | set(by_v["V1"])):
            a, b = by_v["V0"].get(k, 0.0), by_v["V1"].get(k, 0.0)
            if a or b:
                md.append(f"| {day} | {k.replace('|', ' ')} | {a:+.4f} | {b:+.4f} |")
    md.append("")
    for scenario, keep in (("bramki próbki WŁĄCZONE (dziś)", lambda x: x.gate == PASS),
                           ("bramki próbki WYŁĄCZONE dla zawodników", lambda x: True)):
        rows = []
        for v in ("V0", "V1"):
            got = [x for x in legs if keep(x) and x.conf[v] is not None]
            e = describe(got, conf_of(v))
            report["groups"][f"{scenario} / {v}"] = e
            rows.append((f"{v} drukuje", e))
        dropped = [x for x in legs if keep(x) and x.conf["V0"] is not None
                   and x.conf["V1"] is None]
        kept = [x for x in legs if keep(x) and x.conf["V0"] is not None
                and x.conf["V1"] is not None]
        for name, grp in (("V1 zdejmuje (pewność V0)", dropped),
                          ("V1 zostawia (pewność V0)", kept)):
            e = describe(grp, lambda x: float(x.conf["V0"] or 0.0))
            report["groups"][f"{scenario} / {name}"] = e
            rows.append((name, e))
        md += [f"## {scenario}", ""] + render(rows)
    by_day = []
    for day in sorted({x.day for x in legs}):
        for v in ("V0", "V1"):
            got = [x for x in legs if x.day == day and x.conf[v] is not None]
            by_day.append((f"{day} {v} (bez bramek)",
                           describe(got, conf_of(v))))
    md += ["## Dzień po dniu (bramki wyłączone)", ""] + render(by_day)
    text = "\n".join(md)
    print(text)
    if args.md_out:
        args.md_out.write_text(text + "\n", encoding="utf-8")
    if args.json_out:
        args.json_out.write_text(json.dumps(report, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 - exit code contract: 2 on a crash
        print(f"FAILED: {exc!r}", file=sys.stderr)
        sys.exit(2)
