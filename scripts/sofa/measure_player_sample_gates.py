#!/usr/bin/env python3
"""Do CONFIDENCE's sample-shape gates protect a footballer's leg, or only
remove legs its curve already describes? Read-only evidence.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_player_sample_gates.py \\
        --db-path data/refit_<d>/sofa_replay.db [--from <d> --to <d>] \\
        [--calibration <file>] [--md-out f] [--json-out f]

The player curves are fitted on the history replay
(`calibrate_from_cache.build_player_rows`, starts only), which admits a
sample of `config.min_sample` (5) starts and applies no shape gate.
CONFIDENCE then refuses a leg whose sample has fewer than
`MIN_BUILDER_SAMPLE` (10) values (THIN_SAMPLE_FOR_BUILDER), whose line lies
outside every sampled value (LINE_BEYOND_SAMPLE) or whose modal value loses
(MODE_LOSES). A player's sample is his starts in his team's last
`sample_n` (10) matches, so the first gate admits only a player who started
all ten.

Section 1 - history: the replay's player rows are rebuilt from `--db-path`
(the same code; each row's sample values captured), read through the
calibration's curve (`Calibration.realised`, the leg's confidence before the
line evidence), and those with confidence >= 0.70 are grouped by the gate
that would refuse them (in run_confidence's order) and by the sample size.
Reported: n, matches, mean confidence, realised rate, realised minus
confidence with a match bootstrap, and the difference against the rows every
gate passes. The curve was fitted on these rows, so its pooled gap is ~0 by
construction; the question is whether a refused group realises BELOW the
passing one at the same curve.

Section 2 - Superbet's lines (`--from` .. `--to`): every priced football
player row of each day's 05_sheet.json, its sample from 03_samples.json and
its outcome from 07_settled.json, kept when it clears the coupon's
confidence x odds >= 0.90; same grouping, plus ROI at the offered price.
Out of sample for the curve where the day is after its fit.

Nothing is written but --md-out / --json-out. Exit 0, 2 on a crash.
"""

from __future__ import annotations

import argparse
import collections
import dataclasses
import json
import pickle
import statistics
import sys
from collections.abc import Callable, Iterable, Sequence
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from bet.sofa.confidence import (  # noqa: E402
    MIN_BUILDER_SAMPLE,
    MIN_ODDS_FOR_CEILING,
    Calibration,
    player_shape_gate_scope,
    shape_gate_refusal,
)
from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.line_curves import day_reads_per_line, leg_line  # noqa: E402
from bet.sofa.players import is_player_metric, player_observations  # noqa: E402
from scripts.sofa import calibrate_from_cache as cfc  # noqa: E402

FLOOR = 0.70
MIN_X = 0.90  # COUPON_PROFILE: confidence x odds, Superbet rows only
BOOT = 1000
PASS = "PASS"


@dataclasses.dataclass(frozen=True)
class Row:
    event_id: int
    market: str
    line: float
    direction: str
    n: int
    gate: str
    confidence: float
    won: bool
    odds: float | None = None


def gate_of(line: float, direction: str, values: Sequence[float]) -> str:
    """The first of CONFIDENCE's shape gates that refuses
    (confidence.shape_gate_refusal), PASS when none does. A player row's
    values are raw (opponent_correction excludes players), so MODE_LOSES
    reads them as they are."""
    return shape_gate_refusal(line, direction, list(values)) or PASS


class _CapturingStatistics:
    """`statistics` for calibrate_from_cache: records the last sample whose
    mean player_rows_for_event takes, so each row can carry its values."""

    def __init__(self) -> None:
        self.last: list[float] = []

    def mean(self, data: Iterable[float]) -> float:
        values = list(data)
        self.last = values
        return statistics.mean(values)

    def __getattr__(self, name: str) -> Any:
        return getattr(statistics, name)


def replay_rows(db_path: Path, runs_dir: Path, cal: Calibration) -> list[Row]:
    """The replay's starts-only player rows with confidence >= FLOOR."""
    capture = _CapturingStatistics()
    out: list[Row] = []
    real_row = cfc.SettledRow

    def make_row(**kw: Any) -> Any:
        row = real_row(**kw)
        hit = cal.realised(row.market, row.p_central, "football", row.direction, None)
        if hit is not None and hit[0] >= FLOOR:
            out.append(Row(
                event_id=row.event_id, market=row.market, line=row.line,
                direction=row.direction, n=row.sample_size,
                gate=gate_of(row.line, row.direction, capture.last),
                confidence=float(hit[0]), won=row.won,
            ))
        return row

    config = SofaConfig.from_env()
    # calibrate_from_cache builds a row from the sample's mean: swap its
    # `statistics` and `SettledRow` for the run (measurement only)
    saved = (getattr(cfc, "statistics"), cfc.SettledRow)
    setattr(cfc, "statistics", capture)
    setattr(cfc, "SettledRow", make_row)
    try:
        cfc.build_player_rows(
            db_path, cfc.printed_player_ladder(runs_dir),
            sample_n=config.sample_n, min_sample=config.min_sample,
            starts_only=True,
        )
    finally:
        setattr(cfc, "statistics", saved[0])
        setattr(cfc, "SettledRow", saved[1])
    return out


def day_rows(runs_dir: Path, day: str, cal: Calibration) -> list[Row]:
    """A built day's priced player rows with an outcome and confidence >= FLOOR."""
    d = runs_dir / day
    try:
        sheet = json.loads((d / "05_sheet.json").read_text(encoding="utf-8"))
        samples = {
            int(s["sofascore_event_id"]): s
            for s in json.loads((d / "03_samples.json").read_text(encoding="utf-8"))
        }
        settled = json.loads((d / "07_settled.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    outcome = {
        (r["sofascore_event_id"], r["market"], str(r.get("subject") or ""),
         float(r["line"]), r["direction"]): r["outcome"]
        for r in settled
        if r.get("sport") == "football" and is_player_metric(str(r["market"]))
    }
    out: list[Row] = []
    for r in sheet:
        if not player_shape_gate_scope(r.get("sport"), str(r["market"])):
            continue
        odds = r.get("offered_odds")
        if not odds or float(odds) < MIN_ODDS_FOR_CEILING:
            continue  # unpriced / ODDS_TOO_LOW
        key = (r["sofascore_event_id"], r["market"], str(r.get("subject") or ""),
               float(r["line"]), r["direction"])
        o = outcome.get(key)
        if o not in ("WIN", "LOSS"):
            continue
        hit = cal.realised(
            r["market"], r["p_central"], "football", r["direction"], None,
            line=leg_line({**r, "sport": "football"}, day_reads_per_line(day)))
        if hit is None or hit[0] < FLOOR or hit[0] * float(odds) < MIN_X:
            continue
        obs = player_observations(
            samples.get(int(r["sofascore_event_id"]), {}), r["market"],
            r.get("subject") or "")
        values = [float(x["value"]) for x in obs if x.get("value") is not None]
        out.append(Row(
            event_id=int(r["sofascore_event_id"]), market=str(r["market"]),
            line=float(r["line"]), direction=str(r["direction"]), n=len(values),
            gate=gate_of(float(r["line"]), str(r["direction"]), values),
            confidence=float(hit[0]), won=o == "WIN", odds=float(odds),
        ))
    return out


def _arrays(rows: Sequence[Row], ids: Sequence[int]) -> np.ndarray:
    """Per match of `ids` (columns): legs, wins, confidence, priced legs and
    their profit - the sums every statistic here is a ratio of."""
    col = {e: i for i, e in enumerate(ids)}
    a = np.zeros((5, len(ids)))
    for r in rows:
        j = col[r.event_id]
        a[0, j] += 1.0
        a[1, j] += 1.0 if r.won else 0.0
        a[2, j] += r.confidence
        if r.odds:
            a[3, j] += 1.0
            a[4, j] += (r.odds - 1.0) if r.won else -1.0
    return a


def _stat(a: np.ndarray, kind: str) -> np.ndarray:
    """gap = (wins - confidence) / legs; roi = profit / priced legs; `a` is
    (5, ...) - one column per draw or the sample's total."""
    with np.errstate(invalid="ignore", divide="ignore"):
        if kind == "gap":
            return np.asarray((a[1] - a[2]) / a[0])
        return np.asarray(a[4] / a[3])


def _weights(n_ids: int, seed: int) -> np.ndarray:
    """BOOT match-bootstrap draws: how often each match is picked."""
    rng = np.random.default_rng(seed)
    return rng.multinomial(n_ids, np.full(n_ids, 1.0 / n_ids), size=BOOT)


def _interval(point: float, draws: np.ndarray) -> tuple[float, float, float]:
    d = draws[np.isfinite(draws)]
    return point, float(np.quantile(d, 0.025)), float(np.quantile(d, 0.975))


def boot(rows: Sequence[Row], kind: str, seed: int = 7) -> tuple[float, float, float]:
    """The statistic and its 95% match-bootstrap interval."""
    ids = sorted({r.event_id for r in rows})
    a = _arrays(rows, ids)
    w = _weights(len(ids), seed)
    point = float(_stat(a.sum(axis=1), kind))
    return _interval(point, _stat(a @ w.T, kind))


def boot_diff(group: Sequence[Row], base: Sequence[Row],
              seed: int = 11) -> tuple[float, float, float]:
    """gap(group) - gap(base), both resampled by match from their union."""
    ids = sorted({r.event_id for r in group} | {r.event_id for r in base})
    g, b = _arrays(group, ids), _arrays(base, ids)
    w = _weights(len(ids), seed)
    point = float(_stat(g.sum(axis=1), "gap") - _stat(b.sum(axis=1), "gap"))
    return _interval(point, _stat(g @ w.T, "gap") - _stat(b @ w.T, "gap"))


def table(
    rows: Sequence[Row], key: Callable[[Row], str], priced: bool,
    base_of: Callable[[Row], Any] = lambda r: (r.market, r.direction),
) -> list[dict[str, Any]]:
    """One entry per `key` group; "vs PASS" against the PASS rows of the same
    `base_of` (market and direction by default - a group is compared with the
    rows the gates pass in its own population, never with another
    direction's)."""
    out = []
    groups: dict[str, list[Row]] = collections.defaultdict(list)
    for r in rows:
        groups[key(r)].append(r)
    for name in sorted(groups):
        g = groups[name]
        gap = boot(g, "gap")
        entry: dict[str, Any] = {
            "group": name, "n": len(g), "matches": len({r.event_id for r in g}),
            "confidence": round(sum(r.confidence for r in g) / len(g), 4),
            "realised": round(sum(r.won for r in g) / len(g), 4),
            "gap": [round(x, 4) for x in gap],
        }
        scopes = {base_of(r) for r in g}
        base = [r for r in rows if r.gate == PASS and base_of(r) in scopes]
        if base and not all(r.gate == PASS for r in g):
            entry["vs_pass"] = [round(x, 4) for x in boot_diff(g, base)]
        if priced:
            entry["roi"] = [round(x, 4) for x in boot(g, "roi")]
        out.append(entry)
    return out


def _fmt(t: Sequence[float]) -> str:
    return f"{100 * t[0]:+.1f} [{100 * t[1]:+.1f}, {100 * t[2]:+.1f}]"


def render(title: str, entries: list[dict[str, Any]], priced: bool) -> list[str]:
    head = ("| grupa | n | mecze | pewność | zrealizowane "
            "| zreal. - pewn. (pp) | vs PASS (pp) |")
    sep = "|---|---|---|---|---|---|---|"
    if priced:
        head += " ROI % |"
        sep += "---|"
    lines = [f"### {title}", "", head, sep]
    for e in entries:
        cells = [e["group"], str(e["n"]), str(e["matches"]), f"{e['confidence']:.3f}",
                 f"{e['realised']:.3f}", _fmt(e["gap"]),
                 _fmt(e["vs_pass"]) if "vs_pass" in e else "-"]
        if priced:
            cells.append(_fmt(e["roi"]))
        lines.append("| " + " | ".join(cells) + " |")
    return lines + [""]


def sections(
    rows: Sequence[Row], label: str, priced: bool
) -> tuple[dict[str, Any], list[str]]:
    """Grouped by gate, by sample size and by market; every "vs PASS" reads
    the PASS rows of the group's own direction (and market where the group is
    one market's). Superbet quotes a footballer's markets OVER only."""
    by_direction: Callable[[Row], Any] = lambda r: r.direction  # noqa: E731
    by_gate = table(rows, lambda r: f"{r.direction} {r.gate}", priced, by_direction)
    over = [r for r in rows if r.direction == "OVER"]
    by_n = table(over, lambda r: f"OVER n={r.n:02d}", priced, by_direction)
    full = table([r for r in rows if r.n >= MIN_BUILDER_SAMPLE],
                 lambda r: f"{r.direction} {r.gate}", priced, by_direction)
    by_market = table(rows, lambda r: f"{r.market} {r.direction} / {r.gate}", priced)
    md = [f"## {label}", ""]
    md += render("wg bramki (kolejność run_confidence; vs PASS tego kierunku)",
                 by_gate, priced)
    md += render("OVER wg liczby startów w próbce (vs OVER PASS)", by_n, priced)
    md += render("tylko próbki 10/10 - LINE_BEYOND / MODE vs PASS tego kierunku",
                 full, priced)
    md += render("wg rynku i bramki (vs PASS tego rynku i kierunku)",
                 by_market, priced)
    return ({"by_gate": by_gate, "by_n_over": by_n, "full_sample": full,
             "by_market": by_market}, md)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db-path", type=Path)
    ap.add_argument("--runs-dir", type=Path, default=ROOT / "runs" / "sofa")
    ap.add_argument("--calibration", type=Path,
                    default=ROOT / "config" / "sofa_confidence_calibration.json")
    ap.add_argument("--from", dest="date_from")
    ap.add_argument("--to", dest="date_to")
    ap.add_argument("--rows-cache", type=Path,
                    help="pickle of the history rows: read if present, else written")
    ap.add_argument("--md-out", type=Path)
    ap.add_argument("--json-out", type=Path)
    args = ap.parse_args(argv)
    cal = Calibration.load(args.calibration)
    cal = dataclasses.replace(cal, gap_shrink_k=0.0, cap_market_by_thin=True,
                              cap_pool_by_neighbour=True)
    report: dict[str, Any] = {"calibration": str(args.calibration), "floor": FLOOR}
    md = ["# Bramki próbki zawodników - pomiar", "",
          f"Krzywa: `{args.calibration}`; pewność = krzywa przed line evidence; "
          f"wiersze z pewnością >= {FLOOR}; przedziały 95% bootstrap po meczach.", ""]
    if args.db_path:
        if args.rows_cache and args.rows_cache.exists():
            with args.rows_cache.open("rb") as fh:
                rows = pickle.load(fh)
        else:
            rows = replay_rows(args.db_path, args.runs_dir, cal)
            if args.rows_cache:
                with args.rows_cache.open("wb") as fh:
                    pickle.dump(rows, fh)
        print(f"history rows >= {FLOOR}: {len(rows)}", file=sys.stderr)
        report["history"], part = sections(
            rows, f"1. Historia (replay {args.db_path})", False)
        md += part
    if args.date_from and args.date_to:
        d0, d1 = date.fromisoformat(args.date_from), date.fromisoformat(args.date_to)
        live: list[Row] = []
        day = d0
        while day <= d1:
            live += day_rows(args.runs_dir, day.isoformat(), cal)
            day += timedelta(days=1)
        print(f"Superbet rows >= {FLOOR}: {len(live)}", file=sys.stderr)
        report["superbet"], part = sections(
            live, f"2. Linie Superbetu {args.date_from}..{args.date_to}", True)
        md += part
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
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED: {exc!r}", file=sys.stderr)
        sys.exit(2)
