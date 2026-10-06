"""Printed confidence against the realised rate, per curve (plan
docs/sofa/PLAN_2026-10-05_PRODUCTION_GRADE.md, F2.1).

The question: does a leg printed at confidence c win c of the time? Asked per
curve (the leg's `calibrated_on`), per sport and per ledger variant - the
variant carries the epoch (`official` = stats_only from 2026-10-05 07:15Z,
`official:pre_stats_only` = the 10-05 morning's locked legs, `official` on an
older day = the old rule), and variants are never pooled
(record_results.py / audit_ledger.py).

The grades are not re-derived here: scripts/sofa/measure_calibration.py
reads them through record_results.graded_confidence, the function the ledger
records 7c / 7i from, and hands this module the graded positions.

    gap = mean printed confidence - realised hit rate   (> 0: over-confident)

Its 95% interval comes from resampling whole MATCHES (clv.cluster_ratio_
interval): the legs of one match share its game script and a ladder of one
quantity is one outcome several times, so a leg is not independent evidence.
Only WIN / LOSS count; VOID, REFUND, PENDING, UNSETTLED, MISMATCH, NOT_GRADED
and the like are counted beside, never as a result.

Verdict per curve:
    PASS          n_settled >= MIN_SETTLED, |gap| <= MAX_GAP, interval holds 0
    FAIL          n_settled >= MIN_SETTLED and not the above
    INSUFFICIENT  n_settled < MIN_SETTLED (or fewer than clv.MIN_CLUSTERS
                  matches, when no interval means what it says)
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, dataclass
from typing import Any

from bet.sofa.clv import MIN_CLUSTERS, cluster_ratio_interval

MIN_SETTLED = 300
MAX_GAP = 0.02
PASS, FAIL, INSUFFICIENT = "PASS", "FAIL", "INSUFFICIENT"
BUILDER_CURVE = "builder:combined_probability"


@dataclass(frozen=True)
class CalLeg:
    """One printed position and its graded outcome class (WIN / LOSS count;
    anything else is printed, not settled)."""

    date: str
    variant: str
    epoch: str
    sport: str
    curve: str
    confidence: float
    outcome: str
    match: str

    @property
    def settled(self) -> bool:
        return self.outcome in ("WIN", "LOSS")

    @property
    def won(self) -> bool:
        return self.outcome == "WIN"


@dataclass(frozen=True)
class CurveResult:
    variant: str
    epoch: str
    sport: str
    curve: str
    n_printed: int
    n_settled: int
    n_matches: int
    mean_confidence: float | None
    realised: float | None
    gap: float | None
    ci95: tuple[float, float] | None
    verdict: str
    reason: str
    days: tuple[str, ...]

    def to_json(self) -> dict[str, Any]:
        out = asdict(self)
        out["ci95"] = list(self.ci95) if self.ci95 is not None else None
        out["days"] = list(self.days)
        return out


def match_key(src: Mapping[str, Any]) -> str:
    """The match a position belongs to - record_results.match_key's rule
    (a Sofascore id, else a Superbet id)."""
    if src.get("sofascore_event_id") is not None:
        return f"sofa:{src['sofascore_event_id']}"
    if src.get("superbet_event_id") is not None:
        return f"sb:{src['superbet_event_id']}"
    return f"unkeyed:{id(src)}"


def outcome_class(outcome: object) -> str:
    """WIN / LOSS, else the outcome's head (NOT_GRADED:ID_CHANGED ->
    NOT_GRADED) - the bucket it is counted in beside the result."""
    return str(outcome).split(":")[0]


def legs_from_positions(
    date: str,
    variant: str,
    epoch: str,
    singles: Iterable[Mapping[str, Any]],
    builders: Iterable[Mapping[str, Any]] = (),
) -> tuple[list[CalLeg], dict[str, int]]:
    """Graded positions ({source, outcome}) -> one CalLeg each, and the
    count of every outcome that is not a result.

    A single reads its printed `confidence` and `calibrated_on`; a builder is
    one position at its `combined_probability` under BUILDER_CURVE (the slip
    is what is graded, not its legs one by one)."""
    legs: list[CalLeg] = []
    other: dict[str, int] = defaultdict(int)
    tagged = [(s, False) for s in singles] + [(b, True) for b in builders]
    for pos, is_builder in tagged:
        src = pos["source"]
        oc = outcome_class(pos.get("outcome"))
        if oc not in ("WIN", "LOSS"):
            other[oc] += 1
        if is_builder:
            p, curve, sport = src.get("combined_probability"), BUILDER_CURVE, "builder"
        else:
            p = src.get("confidence")
            curve = str(src.get("calibrated_on") or "UNKNOWN")
            sport = str(src.get("sport") or "football")
        if p is None:
            other["NO_CONFIDENCE"] += 1
            continue
        legs.append(CalLeg(date, variant, epoch, sport, curve, float(p), oc,
                           match_key(src)))
    return legs, dict(other)


def verdict(n: int, n_matches: int, gap: float | None,
            ci95: tuple[float, float] | None) -> tuple[str, str]:
    if n < MIN_SETTLED or gap is None:
        return INSUFFICIENT, f"n_settled {n} < {MIN_SETTLED}"
    if ci95 is None:
        return INSUFFICIENT, f"{n_matches} matches < {MIN_CLUSTERS}: no interval"
    holds_zero = ci95[0] <= 0.0 <= ci95[1]
    small = abs(gap) <= MAX_GAP + 1e-12
    if small and holds_zero:
        return PASS, f"|gap| <= {MAX_GAP:.0%} and the interval holds 0"
    why = []
    if not small:
        why.append(f"|gap| {abs(gap):.1%} > {MAX_GAP:.0%}")
    if not holds_zero:
        why.append("the interval excludes 0")
    return FAIL, "; ".join(why)


def measure(printed: list[CalLeg], variant: str, epoch: str, sport: str,
            curve: str, seed: int = 7, n_boot: int = 2000) -> CurveResult:
    legs = [leg for leg in printed if leg.settled]
    n = len(legs)
    clusters: dict[str, list[float]] = defaultdict(lambda: [0.0, 0])
    for leg in legs:
        acc = clusters[leg.match]
        acc[0] += leg.confidence - (1.0 if leg.won else 0.0)
        acc[1] += 1
    mean_c = sum(leg.confidence for leg in legs) / n if n else None
    hit = sum(1 for leg in legs if leg.won) / n if n else None
    gap = (mean_c - hit) if mean_c is not None and hit is not None else None
    ci = cluster_ratio_interval(
        {k: (v[0], int(v[1])) for k, v in clusters.items()}, seed, n_boot
    ) if n else None
    v, reason = verdict(n, len(clusters), gap, ci)
    return CurveResult(
        variant, epoch, sport, curve, len(printed), n, len(clusters),
        None if mean_c is None else round(mean_c, 4),
        None if hit is None else round(hit, 4),
        None if gap is None else round(gap, 4),
        None if ci is None else (round(ci[0], 4), round(ci[1], 4)),
        v, reason, tuple(sorted({leg.date for leg in printed})),
    )


def group(
    legs: list[CalLeg], key: Callable[[CalLeg], tuple[str, str, str, str]],
    seed: int = 7, n_boot: int = 2000,
) -> list[CurveResult]:
    """One result per key (variant, epoch, sport, curve), largest n first."""
    buckets: dict[tuple[str, str, str, str], list[CalLeg]] = defaultdict(list)
    for leg in legs:
        buckets[key(leg)].append(leg)
    out = [measure(v, *k, seed=seed, n_boot=n_boot) for k, v in buckets.items()]
    return sorted(out, key=lambda r: (r.variant, r.sport, -r.n_settled, r.curve))


def by_curve(legs: list[CalLeg], **kw: Any) -> list[CurveResult]:
    return group(legs, lambda x: (x.variant, x.epoch, x.sport, x.curve), **kw)


def by_sport(legs: list[CalLeg], **kw: Any) -> list[CurveResult]:
    """Every curve of a sport pooled - a summary that says it pooled across
    curves (curve "*"), never a verdict on any one of them."""
    return group(legs, lambda x: (x.variant, x.epoch, x.sport, "*"), **kw)


def by_variant(legs: list[CalLeg], **kw: Any) -> list[CurveResult]:
    return group(legs, lambda x: (x.variant, x.epoch, "*", "*"), **kw)


def failed_curves(results: Iterable[CurveResult], variant: str,
                  epoch: str) -> dict[str, dict[str, Any]]:
    """The FAIL curves of one variant and epoch, as the status file lists
    them (bet.sofa.curve_status): curve -> its measurement. Builders are
    not a curve CONFIDENCE reads and are never listed."""
    out: dict[str, dict[str, Any]] = {}
    for r in results:
        if (r.variant, r.epoch) != (variant, epoch) or r.verdict != FAIL:
            continue
        if r.curve in ("*", BUILDER_CURVE):
            continue
        out[r.curve] = {
            "sport": r.sport, "n_settled": r.n_settled, "n_matches": r.n_matches,
            "mean_confidence": r.mean_confidence, "realised": r.realised,
            "gap": r.gap, "ci95": list(r.ci95) if r.ci95 else None,
            "reason": r.reason,
        }
    return dict(sorted(out.items()))
