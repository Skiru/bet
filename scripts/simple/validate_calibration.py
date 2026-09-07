#!/usr/bin/env python3
"""Does the calibration correction help on a day it has never seen?

    python3 scripts/simple/measure_market_reliability.py --emit-rungs /tmp/rungs.json
    python3 scripts/simple/validate_calibration.py --rungs /tmp/rungs.json

A correction fitted on the same rows it is scored against cannot lose. So this
holds **one date out at a time**: the curve is refit from every other date's
settled rungs, applied blind to the held-out day, and the day's results are
pooled. Every number printed is out-of-sample.

Three quantities, because they answer different questions and can disagree:

``gap``  -- claimed minus realised, count-weighted. This is what the correction
targets, and the one it should move.
``|gap| by scope`` -- the same per market, fixture-weighted. A correction can
flatten the pooled figure by cancelling one market's overconfidence against
another's caution, which would be an accounting trick and not an improvement.
``Brier`` -- mean squared error of the probability itself. The honesty check:
subtracting a constant from every claim improves calibration and can leave
Brier alone or worsen it. If a correction improves the gap and not Brier, it is
moving numbers rather than knowing more.

The difference between the corrected and the raw figure is bootstrapped over
**fixtures**, never rungs -- one match contributes up to forty rungs off one
sample, and treating those as forty trials is how this repo once turned a
population artifact into a corroboration effect.

Exit codes: 0 = the correction improved things out of sample, or left them
exactly where they were (a no-op on a calibrated board is the right answer, not
a failure); 1 = it made something worse, and then it must not ship; 2 = missing
input.
"""
from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
for entry in (str(ROOT), str(ROOT / "src"), str(ROOT / "scripts")):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from simple.measure_market_reliability import calibration_curve  # noqa: E402

from bet.simple_stats.calibration import honest_probability  # noqa: E402


def _favoured(points: list[list]) -> list[tuple[float, float, str, str]]:
    """The side anybody would actually take, one row per line.

    The same filter the shipped measurement applies, and for the same reason:
    each line is published on both sides, the two probabilities sum to one and
    exactly one of them wins, so reading both makes every market on the board
    claim 0.500 and realise 0.500 by construction.
    """
    return [
        (float(p), float(w), str(f), str(d)) for p, w, f, d in points if p >= 0.5
    ]


def _fit(subset: list[tuple[float, float, str, str]]) -> dict:
    """A config-shaped entry for one scope, built from a subset of dates."""
    curve = calibration_curve([(p, w, f) for p, w, f, _ in subset])
    return {
        "fixtures": len({f for _, _, f, _ in subset}),
        "rungs": len(subset),
        "calibration_curve": curve,
    }


def _brier(points: list[tuple[float, float]]) -> float:
    return statistics.fmean((p - w) ** 2 for p, w in points)


def _gap(points: list[tuple[float, float]]) -> float:
    return statistics.fmean(p for p, _ in points) - statistics.fmean(
        w for _, w in points
    )


def _fixture_totals(
    by_fixture: dict[str, list[tuple[float, float, float]]]
) -> dict[str, tuple[float, ...]]:
    """Per fixture: the six sums both metrics are built from.

    Both ``gap`` and ``Brier`` are means over rungs, so a resample only needs
    each fixture's *totals*, never its rows. Precomputing them turns one
    bootstrap draw from O(rungs) into O(fixtures) -- a hundredfold on a real
    board, and the difference between a check that runs and one that gets
    killed halfway.
    """
    return {
        key: (
            float(len(rows)),
            sum(r[0] for r in rows),
            sum(r[1] for r in rows),
            sum(r[2] for r in rows),
            sum((r[0] - r[2]) ** 2 for r in rows),
            sum((r[1] - r[2]) ** 2 for r in rows),
        )
        for key, rows in by_fixture.items()
    }


def _bootstrap(
    by_fixture: dict[str, list[tuple[float, float, float]]],
    which: str,
    draws: int,
) -> tuple[float, float]:
    """95% interval on ``metric(corrected) - metric(raw)``, resampling fixtures.

    Negative means the correction reduced the quantity. Both arms are drawn on
    the *same* resampled fixtures -- pairing them is the whole point, since the
    two differ only by the correction and the sampling noise they share cancels,
    leaving an interval on the effect rather than on the board.
    """
    totals = _fixture_totals(by_fixture)
    keys = list(totals)
    rng = random.Random(11)
    spread = []
    for _ in range(draws):
        n = p_raw = p_new = won = sq_raw = sq_new = 0.0
        for _ in keys:
            row = totals[rng.choice(keys)]
            n += row[0]
            p_raw += row[1]
            p_new += row[2]
            won += row[3]
            sq_raw += row[4]
            sq_new += row[5]
        if not n:
            continue
        if which == "gap":
            spread.append((p_new - p_raw) / n)
        else:
            spread.append((sq_new - sq_raw) / n)
    spread.sort()
    return spread[int(0.025 * len(spread))], spread[int(0.975 * len(spread))]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rungs", required=True)
    parser.add_argument("--draws", type=int, default=2000)
    parser.add_argument(
        "--no-isotonic",
        action="store_true",
        help="Score the raw buckets instead of the monotone fit",
    )
    parser.add_argument(
        "--mode",
        default="gated",
        choices=("ci", "shrink", "gated"),
        help=(
            "'ci' subtracts only what the clustered interval puts beyond zero; "
            "'shrink' subtracts the damped point estimate everywhere; 'gated' "
            "subtracts the damped point estimate only where the interval says "
            "the overconfidence is real"
        ),
    )
    parser.add_argument(
        "--tail",
        type=float,
        default=0.75,
        help="Also report the confident tail on its own",
    )
    args = parser.parse_args()

    path = Path(args.rungs)
    if not path.exists():
        print(json.dumps({"error": f"missing {path}"}), file=sys.stderr)
        return 2
    raw_rungs: dict[str, list[list]] = json.loads(path.read_text())

    # (raw claim, corrected claim, won, scope, fixture)
    scored: list[tuple[float, float, float, str, str]] = []
    skipped_dates: dict[str, int] = defaultdict(int)
    for scope, points in sorted(raw_rungs.items()):
        favoured = _favoured(points)
        dates = sorted({d for _, _, _, d in favoured})
        for held_out in dates:
            train = [row for row in favoured if row[3] != held_out]
            test = [row for row in favoured if row[3] == held_out]
            if not train or not test:
                continue
            entry = _fit(train)
            if not entry["calibration_curve"]:
                # Every date but this one is still too thin to bucket. The rows
                # are dropped from BOTH arms rather than passed through
                # uncorrected: carrying them would dilute the comparison with
                # rows where the two arms are identical by construction and
                # make any real effect look smaller than it is.
                skipped_dates[scope] += len(test)
                continue
            for claim, won, fixture, _ in test:
                honest, _note = honest_probability(
                    claim,
                    entry,
                    isotonic=not args.no_isotonic,
                    mode=args.mode,
                )
                scored.append((claim, float(honest), won, scope, fixture))

    if not scored:
        print(json.dumps({"error": "nothing to score"}), file=sys.stderr)
        return 2

    fit_label = "raw buckets" if args.no_isotonic else "monotone (isotonic) fit"
    print(
        f"out-of-sample, leave-one-date-out, {fit_label}, mode={args.mode}"
    )
    print(f"rungs scored: {len(scored)}  fixtures: {len({r[4] for r in scored})}")
    if skipped_dates:
        total = sum(skipped_dates.values())
        print(f"rungs skipped (no curve without the held-out date): {total}")

    def report(label: str, rows: list[tuple[float, float, float, str, str]]) -> None:
        if len(rows) < 50:
            print(f"\n{label}: {len(rows)} rungs -- too few to read")
            return
        by_fixture: dict[str, list[tuple[float, float, float]]] = defaultdict(list)
        for claim, honest, won, _scope, fixture in rows:
            by_fixture[fixture].append((claim, honest, won))
        raw_gap = _gap([(r[0], r[2]) for r in rows])
        new_gap = _gap([(r[1], r[2]) for r in rows])
        raw_brier = _brier([(r[0], r[2]) for r in rows])
        new_brier = _brier([(r[1], r[2]) for r in rows])
        gap_lo, gap_hi = _bootstrap(by_fixture, "gap", args.draws)
        br_lo, br_hi = _bootstrap(by_fixture, "brier", args.draws)
        print(f"\n{label}  ({len(rows)} rungs, {len(by_fixture)} fixtures)")
        print(
            f"  gap    {raw_gap:+.4f} -> {new_gap:+.4f}   "
            f"change {new_gap - raw_gap:+.4f} [{gap_lo:+.4f}, {gap_hi:+.4f}]"
        )
        print(
            f"  Brier  {raw_brier:.4f} -> {new_brier:.4f}   "
            f"change {new_brier - raw_brier:+.4f} [{br_lo:+.4f}, {br_hi:+.4f}]"
        )

    # The pooled signed gap can be zero by cancellation and often is: on
    # 2026-09-07 the board read -0.0001 while holding player_tackles at +0.019
    # against red_cards_total at -0.119. So the headline is the *absolute*
    # error inside each market's own claim buckets, rung-weighted, which
    # cancellation cannot flatter.
    def bucketed_error(
        rows: list[tuple[float, float, float, str, str]]
    ) -> tuple[float, float]:
        raw_cells: dict[
            tuple[str, int], list[tuple[float, float, float]]
        ] = defaultdict(list)
        for claim, honest, won, scope, _fixture in rows:
            cell = (scope, min(9, int(claim * 20) - 10))
            raw_cells[cell].append((claim, honest, won))
        before = after = weight = 0.0
        for cells in raw_cells.values():
            n = len(cells)
            if n < 20:
                continue
            realised = statistics.fmean(w for _, _, w in cells)
            before += abs(statistics.fmean(c for c, _, _ in cells) - realised) * n
            after += abs(statistics.fmean(h for _, h, _ in cells) - realised) * n
            weight += n
        return (before / weight, after / weight) if weight else (0.0, 0.0)

    cal_before, cal_after = bucketed_error(scored)
    print(
        f"\nmean |claimed - realised| inside each market's own claim buckets: "
        f"{cal_before:.4f} -> {cal_after:.4f}"
    )

    report("all favoured rungs", scored)
    report(
        f"claims >= {args.tail:.2f}", [r for r in scored if r[0] >= args.tail]
    )

    # Per scope, so a pooled improvement cannot be one market's overconfidence
    # cancelling another's caution.
    print(f"\n{'scope':<26} {'rungs':>6} {'gap':>17} {'|gap|':>15} {'Brier':>15}")
    improved = worsened = 0
    for scope in sorted({r[3] for r in scored}):
        rows = [r for r in scored if r[3] == scope]
        if len(rows) < 50:
            continue
        raw_gap = _gap([(r[0], r[2]) for r in rows])
        new_gap = _gap([(r[1], r[2]) for r in rows])
        raw_brier = _brier([(r[0], r[2]) for r in rows])
        new_brier = _brier([(r[1], r[2]) for r in rows])
        if abs(new_gap) < abs(raw_gap) - 1e-6:
            improved += 1
        elif abs(new_gap) > abs(raw_gap) + 1e-6:
            worsened += 1
        print(
            f"{scope:<26} {len(rows):>6} {raw_gap:>+8.4f}->{new_gap:>+8.4f} "
            f"{abs(raw_gap):>7.4f}->{abs(new_gap):>6.4f} "
            f"{raw_brier:>7.4f}->{new_brier:>6.4f}"
        )
    print(f"\nscopes with |gap| closer to zero: {improved}, further: {worsened}")

    # The ship gate. Both have to hold: the correction must reduce the pooled
    # overconfidence AND must not make the probability itself worse. The second
    # is the one that can fail, and it is why this script has an exit code.
    brier_before = _brier([(r[0], r[2]) for r in scored])
    brier_after = _brier([(r[1], r[2]) for r in scored])
    # Three outcomes, not two. A correction that fires on a board with nothing
    # wrong with it is a no-op, and a no-op is not a failure -- it is the right
    # answer, and the property the whole design is built around. Only a
    # correction that makes something *worse* is a reason not to ship.
    worse_calibration = cal_after > cal_before + 1e-6
    worse_brier = brier_after > brier_before + 1e-6
    unchanged = (
        abs(cal_after - cal_before) <= 1e-6 and abs(brier_after - brier_before) <= 1e-6
    )
    verdict = (
        "REGRESSION"
        if worse_calibration or worse_brier
        else "NO CHANGE"
        if unchanged
        else "IMPROVEMENT"
    )
    print(
        f"\nverdict: {verdict} "
        f"(bucketed |gap| {cal_before:.4f}->{cal_after:.4f}, "
        f"Brier {brier_before:.4f}->{brier_after:.4f})"
    )
    print(
        "  the gate is the bucketed figure and not the pooled signed gap: the "
        "pooled one is zero by cancellation on a real board and a correction "
        "cannot improve it without making some market worse."
    )
    if verdict == "NO CHANGE":
        print(
            "  nothing to correct on this data. Not a failure -- a correction "
            "that leaves a calibrated market alone is the point."
        )
    return 1 if verdict == "REGRESSION" else 0


if __name__ == "__main__":
    raise SystemExit(main())
