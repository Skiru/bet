"""The history curve of a new market and its holdout gate, shared by the
fits of docs/sofa/history/PLAN_KRZYWE_NOWE_RYNKI_2026-10-14.md (steps 3-4).

Curve (step 3): buckets of fit_confidence.EDGES, a bucket kept only with
MIN_MARKET_BUCKET rows, its realised rate and Wilson lower bound - the
shape fit_confidence writes and CONFIDENCE reads (`realised_lo95` is the
number a leg prints).

Gate (step 4): a curve fitted on the training window is read on the holdout
the way CONFIDENCE would read it - every holdout forecast gets its training
bucket's `realised_lo95` (its "curve value"; a forecast outside every kept
bucket has none and would not print). Over the forecasts whose curve value is
at least PRINT_FLOOR (0.70, what can print), at least MIN_N (300) of them,
realised minus the mean curve value must not be below -MAX_GAP (2 pp): the
gate is ONE-SIDED (operator, 2026-10-14 ~18:55Z) - a key fails only when
its curve OVERSTATES on the holdout; a curve that understates (realised
above it, by any amount) passes - the printed confidence is cautious.
Else the key FAILS and gets no curve. The old two-sided verdict
(|gap| <= MAX_GAP, measure_calibration.py's PASS rule) stays in the result
as `two_sided_pass`, for reference only. The 95% interval (resampling
matches) is reported, never gated on.

Pure functions; nothing is read or written here.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

import numpy as np

from scripts.sofa.fit_confidence import EDGES, MIN_MARKET_BUCKET, wilson_lo

PRINT_FLOOR = 0.70
MAX_GAP = 0.02
MIN_N = 300
BOOT_REPS = 1000

RULE = "one_sided"  # since the operator's decision of 2026-10-14 ~18:55Z
RULE_TEXT = (f"curve value >= {PRINT_FLOOR}: n >= {MIN_N} and realised - curve "
             f">= -{MAX_GAP} (one-sided: only an overstatement fails)")
_EPS = 1e-9

# (p, outcome 0/1, match id) - one forecast of one line.
Forecast = tuple[float, int, int]


def bucket_index(p: float) -> int:
    for i in range(len(EDGES) - 1):
        if EDGES[i] <= p < EDGES[i + 1]:
            return i
    return len(EDGES) - 2


def bucket_label(i: int) -> str:
    return f"{EDGES[i]:.3f}-{EDGES[i + 1]:.3f}"


def fit_curve(
    rows: Iterable[tuple[float, int]], min_bucket: int = MIN_MARKET_BUCKET,
) -> dict[str, dict[str, Any]]:
    """{bucket label: {n, realised, realised_lo95}} of (p, y) pairs."""
    hits: dict[int, list[int]] = defaultdict(lambda: [0, 0])
    for p, y in rows:
        h = hits[bucket_index(float(p))]
        h[0] += int(y)
        h[1] += 1
    out: dict[str, dict[str, Any]] = {}
    for b in sorted(hits):
        k, n = hits[b]
        if n < min_bucket:
            continue
        out[bucket_label(b)] = {"n": n, "realised": round(k / n, 4),
                                "realised_lo95": round(wilson_lo(k, n), 4)}
    return out


def curve_value(curve: Mapping[str, Mapping[str, Any]], p: float) -> float | None:
    """The bucket's realised_lo95 at p, or None outside every kept bucket
    (the same lookup as confidence.Calibration._find)."""
    for key, entry in curve.items():
        lo, hi = (float(x) for x in key.split("-"))
        if lo <= p < hi:
            return float(entry["realised_lo95"])
    return None


def one_sided_pass(n: int, gap: float | None) -> bool:
    """The gate: enough printable forecasts and the curve not overstating by
    more than MAX_GAP (realised - curve >= -MAX_GAP)."""
    return gap is not None and n >= MIN_N and gap >= -MAX_GAP - _EPS


def two_sided_pass(n: int, gap: float | None) -> bool:
    """The rule before 2026-10-14 ~18:55Z (|realised - curve| <= MAX_GAP),
    kept in the reports for reference only."""
    return gap is not None and n >= MIN_N and abs(gap) <= MAX_GAP + _EPS


def fail_reason(n: int, gap: float | None) -> str:
    """Why one_sided_pass refuses ("" when it passes)."""
    if gap is None or n < MIN_N:
        return f"n {n} < {MIN_N}"
    if gap < -MAX_GAP - _EPS:
        return f"overstates: gap {gap:+.4f} < -{MAX_GAP}"
    return ""


def final_reaches_floor(curve: Mapping[str, Mapping[str, Any]]) -> bool:
    """A final curve with no bucket whose realised_lo95 reaches PRINT_FLOOR
    prints nothing: such a key fails (operator, 2026-10-14)."""
    return any(float(e["realised_lo95"]) >= PRINT_FLOOR for e in curve.values())


def require_final(g: dict[str, Any], final_curve: Mapping[str, Mapping[str, Any]]
                  ) -> dict[str, Any]:
    """A passing verdict turned FAIL when the final curve never reaches
    PRINT_FLOOR (it would print nothing); `g` is changed and returned."""
    if g.get("pass") and not final_reaches_floor(final_curve):
        g["pass"] = False
        g["why"] = f"final curve has no bucket with realised_lo95 >= {PRINT_FLOOR}"
    return g


def _boot_gap(matches: Sequence[int], diff: Sequence[float], reps: int,
              seed: int) -> tuple[float, float]:
    """95% interval of sum(diff) / n, resampling matches."""
    ids, inv = np.unique(np.asarray(matches, dtype=np.int64), return_inverse=True)
    num = np.bincount(inv, weights=np.asarray(diff, dtype=np.float64))
    den = np.bincount(inv).astype(np.float64)
    rng = np.random.default_rng(seed)
    draws = rng.integers(0, len(ids), size=(reps, len(ids)))
    stats = num[draws].sum(axis=1) / np.maximum(den[draws].sum(axis=1), 1.0)
    return float(np.percentile(stats, 2.5)), float(np.percentile(stats, 97.5))


def gate(
    curve: Mapping[str, Mapping[str, Any]], holdout: Sequence[Forecast],
    reps: int = BOOT_REPS, seed: int = 0,
) -> dict[str, Any]:
    """The holdout verdict of one key's training curve (module docstring)."""
    read = [(cv, y, m) for p, y, m in holdout
            if (cv := curve_value(curve, p)) is not None]
    printable = [(cv, y, m) for cv, y, m in read if cv >= PRINT_FLOOR]
    out: dict[str, Any] = {
        "holdout_forecasts": len(holdout),
        "with_curve_value": len(read),
        "n": len(printable),
        "matches": len({m for *_, m in printable}),
        "min_n": MIN_N, "max_gap": MAX_GAP, "print_floor": PRINT_FLOOR,
        "rule": RULE,
    }
    by_bucket: dict[str, list[tuple[float, int]]] = defaultdict(list)
    for p, y, _m in holdout:
        cv = curve_value(curve, p)
        if cv is not None and cv >= PRINT_FLOOR:
            by_bucket[bucket_label(bucket_index(p))].append((cv, y))
    out["buckets"] = {
        b: {"n": len(v), "curve": round(v[0][0], 4),
            "realised": round(sum(y for _, y in v) / len(v), 4)}
        for b, v in sorted(by_bucket.items())}
    if not printable:
        out.update({"mean_curve": None, "realised": None, "gap": None,
                    "gap_ci95": None, "pass": False, "two_sided_pass": False,
                    "why": "no holdout forecast reads a curve value >= "
                           f"{PRINT_FLOOR}"})
        return out
    n = len(printable)
    mean_curve = sum(cv for cv, _, _ in printable) / n
    realised = sum(y for _, y, _ in printable) / n
    gap = realised - mean_curve
    ci = _boot_gap([m for *_, m in printable],
                   [y - cv for cv, y, _ in printable], reps, seed)
    passed = one_sided_pass(n, gap)
    out.update({"mean_curve": round(mean_curve, 4), "realised": round(realised, 4),
                "gap": round(gap, 4), "gap_ci95": [round(ci[0], 4), round(ci[1], 4)],
                "pass": passed, "why": fail_reason(n, gap),
                "two_sided_pass": two_sided_pass(n, gap)})
    return out


def gate_lines(key: str, g: Mapping[str, Any]) -> list[str]:
    """A markdown block of one key's verdict."""
    verdict = "PASS" if g["pass"] else "FAIL"
    head = (f"## {key}: {verdict}" + (f" ({g['why']})" if g.get("why") else ""))
    if "two_sided_pass" in g:
        head += (" - two-sided rule (before 2026-10-14 18:55Z, reference): "
                 + ("PASS" if g["two_sided_pass"] else "FAIL"))
    lines = [head, "",
             f"holdout forecasts {g['holdout_forecasts']}, read by the training "
             f"curve {g['with_curve_value']}; curve value >= {g['print_floor']}: "
             f"n {g['n']} ({g['matches']} matches)"]
    if g.get("gap") is not None:
        lo, hi = g["gap_ci95"]
        lines.append(f"mean curve {g['mean_curve']:.4f}, realised {g['realised']:.4f}, "
                     f"gap {100 * g['gap']:+.2f} pp [{100 * lo:+.2f}, {100 * hi:+.2f}]")
    if g.get("buckets"):
        lines += ["", "| bucket | n | curve (lo95) | realised |", "|---|---|---|---|"]
        lines += [f"| {b} | {v['n']} | {v['curve']:.4f} | {v['realised']:.4f} |"
                  for b, v in g["buckets"].items()]
    return lines + [""]
