#!/usr/bin/env python3
"""E11 — fit `sofa`'s OWN constants from `sofa_settled_row`.

PLAN §6.0 lists what may be carried over from `simple` and what may not. The
"may not" column is not conservatism: `market_reliability.json` is a calibration
curve measured on another provider's samples, and applying it here would be a
correction that does not know what it is correcting. Starting from identity is
correct. Starting from somebody else's curve is a mistake that never surfaces.

So this script fits nothing it cannot fit. Every constant it writes carries the
row count it was fitted on and the curve it was chosen from, and a constant with
no data is written as ``null`` with a reason — never as a plausible default.

Usage:
    python -m scripts.sofa.fit_constants --db-path data/sofa.db
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import statistics
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bet.sofa.config import SofaConfig
from bet.sofa.db import get_connection
from bet.sofa.engine import (
    P_CEILING,
    P_FLOOR,
    calc_p_central,
    calc_p_central_nb_raw,
    support_floor_for,
    uses_negative_binomial,
    winning_boundary,
)

K_GRID = [0.0, 2.0, 5.0, 8.0, 10.0, 15.0, 25.0, 1000.0]

# A league baseline below this many observations is noise wearing a prior.
MIN_BASELINE_OBSERVATIONS = 30

# How far 1H + 2H may sit from the full-match baseline before it is reported.
SUM_TOLERANCE = 0.10

# What fraction of a match's counting events may fall in the second half.
#
# Measured on this repo's own settled rows: corners 53.7%, goals 55.6%. An
# independent 141,316-match study puts corners at 52.8%. Football's halves are
# close to even with a slight second-half lean, so the band is generous in both
# directions and still catches the 61.5% that shipped on 2026-09-21.
SECOND_HALF_SHARE_BAND = (0.45, 0.60)
# A reliability bucket below this many rows cannot support a correction.
#
# Was 10, which is a count, not evidence. The ci_lower > 0 gate that decides
# whether a correction is emitted at all clears easily when the measured gap
# is large, and a large gap is exactly what a tiny bucket produces by chance:
# after the estimator changed, goals_1h_for 0.6-0.7 emitted a correction of
# 0.2105 off 42 rows — larger than any well-evidenced bias in the table, and
# larger than the bound test_no_correction_is_large_enough_to_be_doing_the_
# model_s_job exists to hold. The per-half markets carry only 190-352 settled
# rows in total, so at 10 their buckets were always going to be noise.
#
# 200 is the same argument MIN_DIRECTION_BUCKET_ROWS makes at 500 for a
# narrower claim: a correction has to be better evidenced than the thing it
# corrects, not worse.
MIN_BUCKET_ROWS = 200

# A direction-keyed bucket is a narrower claim than a market-keyed one, so it
# has to be better evidenced, not worse. At MIN_BUCKET_ROWS the layer emitted
# a 0.176 correction on 86 rows and 0.140 on 45 — the two largest in the whole
# config — while the biases it exists to catch were measured at n = 600-1300.
# With ~120 direction buckets, a 95% interval clears zero by chance often
# enough that the thin ones are noise wearing a confidence interval. Below
# this the bucket falls back to the market curve, then to the pooled one.
MIN_DIRECTION_BUCKET_ROWS = 500
# Two K values whose median error differs by less than this are on a plateau.
PLATEAU_TOLERANCE = 0.002

# K_CENTRE is scored with Brier, whose differences are an order of magnitude
# smaller than the median-absolute-error the criterion used to be, so it needs
# its own band. At 0.002 on the Brier scale the plateau swallowed five of the
# eight grid points including the sentinel.
BRIER_PLATEAU_TOLERANCE = 0.0005

# "Ignore the sample and use the league prior" — the far end of K_GRID, there
# to let the fit say the sample is worthless if it is. It is a diagnostic, not
# a shippable value: selecting it would switch off the sampling pipeline that
# every other stage exists to feed. See _pick_plateau_k.
IGNORE_SAMPLE_K = 1000.0


def bucket_p(p: float) -> str:
    b = min(9, int(p * 10))
    return f"{b / 10.0:.1f}-{(b + 1) / 10.0:.1f}"


def fit_baselines(conn: sqlite3.Connection) -> dict[str, Any]:
    """Per-league mean of each market's realised value, keyed on competition_id.

    Two things this must not do, both of which bias the prior:

    * Aggregate across subjects. A `_for` market has two rows per event with
      two different realised values; taking MAX over the event picks the
      larger every time and walks the prior upward. The grouping key includes
      `subject` so one group is one measured quantity.
    * Filter on outcome. Excluding PUSH drops exactly the events that landed on
      an integer line — a non-random slice of the distribution, removed from a
      statistic that is about values, not about results.
    """
    cursor = conn.execute(
        """
        SELECT competition_id, market, subject, sofascore_event_id,
               MAX(actual_value) AS value
        FROM sofa_settled_row
        WHERE competition_id IS NOT NULL
        GROUP BY competition_id, market, subject, sofascore_event_id
        ORDER BY market, competition_id, sofascore_event_id
        """
    )

    by_market: dict[str, dict[str, list[float]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in cursor:
        by_market[row["market"]][str(row["competition_id"])].append(row["value"])

    baselines: dict[str, Any] = {}
    for market in sorted(by_market):
        entry: dict[str, Any] = {}
        pooled: list[float] = []
        for comp_id in sorted(by_market[market]):
            values = by_market[market][comp_id]
            pooled.extend(values)
            if len(values) >= MIN_BASELINE_OBSERVATIONS:
                entry[comp_id] = {
                    "mean": round(statistics.mean(values), 4),
                    "n": len(values),
                }
        # L11: the global fallback exists, but a league-blind prior was
        # once the whole edge, so the per-league entries are the point.
        #
        # The pool is held to the SAME evidence bar as a league entry, and it
        # records its own `n`. Until 2026-09-21 it did neither, and the two
        # omissions compounded: `corners_2h_for` carried a bare 3.4286 fitted
        # from a handful of rows, nothing on the entry said how few, and at
        # K_CENTRE=25 that constant took 76% of the centre for any football
        # sample of n=8. A team averaging 1.12 second-half corners was priced
        # at 62% to go over 2.5. Refusing the pool is safe: `get_prior`
        # returns None and run_sheet falls back to `centre = mean`, which is
        # the sample speaking for itself rather than a constant nobody could
        # audit.
        if len(pooled) >= MIN_BASELINE_OBSERVATIONS:
            entry["global"] = {
                "mean": round(statistics.mean(pooled), 4),
                "n": len(pooled),
            }
        if entry:
            baselines[market] = entry
    return baselines


def check_half_match_coherence(baselines: dict[str, Any]) -> list[str]:
    """First half + second half must add up to the whole match.

    Two things are checked, and the second is the one that bit.

    1. The halves should roughly add up to the whole match.
    2. The SHARE taken by the second half must be plausible. This is the
       quantity that was wrong on 2026-09-21 and the sum test would have
       missed it: `corners_1h_total` 4.08 + `corners_2h_total` 6.50 = 10.58
       against a full-match 9.90, only 6.8% adrift and well inside any sane
       sum tolerance — while the split it implied put **61.5%** of a match's
       corners in the second half. Measured on this repo's own settled rows
       the share is 53.7% for corners and 55.6% for goals; 141k matches
       elsewhere put corners at 52.8%. Both halves of football are close to
       even, slightly favouring the second, and anything outside SECOND_HALF_
       SHARE_BAND is a fit artifact rather than a fact about football.

    The arithmetic downstream was internally perfect at every step, which is
    exactly why no other gate caught it: the number was consistent, just wrong.
    """
    findings: list[str] = []
    for full in sorted(baselines):
        if "_1h_" in full or "_2h_" in full:
            continue
        h1 = baselines.get(full.replace("_", "_1h_", 1))
        h2 = baselines.get(full.replace("_", "_2h_", 1))
        if not (isinstance(h1, dict) and isinstance(h2, dict)):
            continue
        whole = _pooled_mean(baselines[full])
        a = _pooled_mean(h1)
        b = _pooled_mean(h2)
        if whole is None or a is None or b is None:
            continue
        if whole <= 0 or (a + b) <= 0:
            continue

        drift = (a + b) / whole - 1.0
        if abs(drift) > SUM_TOLERANCE:
            findings.append(
                f"{full}: 1H {a:.3f} + 2H {b:.3f} = {a + b:.3f} vs "
                f"full {whole:.3f} ({drift:+.1%})"
            )

        share = b / (a + b)
        low, high = SECOND_HALF_SHARE_BAND
        if not low <= share <= high:
            findings.append(
                f"{full}: second half is {share:.1%} of 1H+2H, outside "
                f"{low:.0%}-{high:.0%} (1H {a:.3f}, 2H {b:.3f})"
            )
    return findings


def _pooled_mean(entry: dict[str, Any]) -> float | None:
    """The market-wide mean of a baseline entry, whatever shape it is in."""
    g = entry.get("global")
    if isinstance(g, dict) and isinstance(g.get("mean"), int | float):
        return float(g["mean"])
    if isinstance(g, int | float) and not isinstance(g, bool):
        return float(g)
    return None


def fit_reliability(conn: sqlite3.Connection) -> dict[str, Any]:
    """Per-market, per-bucket realised rate and the correction it justifies.

    A correction is emitted only where the confidence interval of the
    (declared − realised) gap stays entirely above zero. A correction that
    fires in both directions is fitting noise it has not measured.
    """
    cursor = conn.execute(
        """
        SELECT market, direction, p_central, outcome
        FROM sofa_settled_row
        WHERE outcome IN ('WIN', 'LOSS')
        ORDER BY market, p_central
        """
    )

    buckets: dict[str, dict[str, list[tuple[float, float]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for row in cursor:
        outcome = 1.0 if row["outcome"] == "WIN" else 0.0
        pair = (row["p_central"], outcome)
        bucket = bucket_p(row["p_central"])
        buckets[row["market"]][bucket].append(pair)
        # F48. Also keyed by direction. OVER and UNDER of a rung are exact
        # complements, so a bias toward one of them cancels *exactly* when the
        # two are pooled, and the pooled curve reports a calibrated market.
        # Measured on tennis after the K fix: games_total UNDER runs 1.40 /
        # 1.27 / 1.09 realised-over-predicted across 0.2-0.8 and aces_for
        # UNDER 1.35 / 1.30 / 1.20, on thousands of rows each — while their
        # pooled curves look clean. run_sheet reads this layer first.
        direction = row["direction"]
        if direction in ("OVER", "UNDER"):
            buckets[f"{row['market']}|{direction}"][bucket].append(pair)

    reliability: dict[str, Any] = {}
    for market in sorted(buckets):
        entry: dict[str, Any] = {}
        minimum = MIN_DIRECTION_BUCKET_ROWS if "|" in market else MIN_BUCKET_ROWS
        for bucket in sorted(buckets[market]):
            pairs = buckets[market][bucket]
            n = len(pairs)
            if n < minimum:
                continue

            diffs = [declared - realised for declared, realised in pairs]
            mean_diff = statistics.mean(diffs)
            std_diff = statistics.stdev(diffs) if n > 1 else 0.0
            lower = mean_diff - 1.96 * (std_diff / math.sqrt(n))

            # Only overconfidence is corrected, and only when the interval
            # clears zero. §6.5 step 2 may raise the bar, never lower it.
            correction = round(mean_diff, 4) if lower > 0 else 0.0
            entry[bucket] = {
                "realised": round(
                    statistics.mean([realised for _, realised in pairs]), 4
                ),
                "n": n,
                "correction": correction,
                "ci_lower": round(lower, 4),
                # F48. run_sheet.get_calibration_correction only honours a
                # bucket that says MEASURED, and this writer never said it.
                # Every correction ever fitted here — 39 non-zero ones in the
                # shipped config — was read back as 0.0, so the calibration
                # curve has never been applied to a single row. The reader's
                # tests passed because they hand-write "status": "MEASURED"
                # into their own fixtures, so they check the reader against a
                # shape the writer does not produce. Same family as the
                # WON/LOST-vs-WIN/LOSS break this file already carries.
                "status": "MEASURED",
            }
        if entry:
            reliability[market] = entry

    # The same measurement with every market pooled. A market whose own
    # bucket is too thin used to get a correction of exactly zero, and zero is
    # not the neutral choice it looks like — it asserts the estimator is
    # calibrated there, while the pooled figure says it is not. The
    # overconfidence is mostly a property of the estimator (a normal
    # approximation over ten observations), not of the market, so this is the
    # better fallback and `run_sheet.get_calibration_correction` reads it as
    # one.
    pooled_buckets: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for market in buckets:
        # The "market|DIRECTION" keys hold the same rows again; pooling them
        # too would count every row twice and halve every confidence interval.
        if "|" in market:
            continue
        for bucket, pairs in buckets[market].items():
            pooled_buckets[bucket].extend(pairs)

    pooled: dict[str, Any] = {}
    for bucket in sorted(pooled_buckets):
        pairs = pooled_buckets[bucket]
        n = len(pairs)
        if n < MIN_BUCKET_ROWS:
            continue
        diffs = [declared - realised for declared, realised in pairs]
        mean_diff = statistics.mean(diffs)
        std_diff = statistics.stdev(diffs) if n > 1 else 0.0
        lower = mean_diff - 1.96 * (std_diff / math.sqrt(n))
        pooled[bucket] = {
            "realised": round(
                statistics.mean([realised for _, realised in pairs]), 4
            ),
            "n": n,
            "correction": round(mean_diff, 4) if lower > 0 else 0.0,
            "ci_lower": round(lower, 4),
            "status": "MEASURED",
        }
    if pooled:
        reliability["_pooled"] = pooled

    return reliability


def _pick_plateau_k(
    curve: dict[float, float], tolerance: float | None = None
) -> float | None:
    """The most conservative K whose error is within tolerance of the best.

    The curve is flat, so the point minimum is mostly noise. Trusting the
    sample too much is the error that has already cost money, and a smaller K
    trusts the sample more, so among the values the data cannot tell apart the
    *largest* K wins. The previous rule said this in prose and then returned
    ``min(on_plateau)``, which selects the single most sample-trusting value on
    the grid — the opposite of its own reasoning.

    ``None`` means the data does not identify K at all. When the plateau
    swallows the whole grid, "K = 0, use the sample alone" and "K = 1000,
    ignore the sample" are both inside tolerance, and reporting either as
    FITTED claims a measurement nobody made. That is exactly what happened
    once the F41 support floor flattened the curve: its full range fell to
    0.00198, under PLATEAU_TOLERANCE of 0.002, and K_CENTRE was published as
    0.0 — down from 8.0 — on a curve whose own minimum was at 5.0.
    """
    if not curve:
        return None
    tolerance = PLATEAU_TOLERANCE if tolerance is None else tolerance
    best = min(curve.values())
    on_plateau = [k for k, err in curve.items() if err <= best + tolerance]
    if len(on_plateau) == len(curve):
        return None
    # The sentinel may sit on the plateau — it did, on Brier, in the
    # 2026-09-18 refit — but it can never be the answer.
    candidates = [k for k in on_plateau if k != IGNORE_SAMPLE_K]
    if not candidates:
        return None
    return max(candidates)


K_CENTRE_ROWS_SQL = """
    SELECT sport, competition_id, market, line, direction, sample_size,
           sample_mean, sample_sd, outcome
    FROM sofa_settled_row
    WHERE outcome IN ('WIN', 'LOSS')
    ORDER BY id
"""

# Below this a sport has not been measured, and the pooled value is the
# honest answer rather than a curve fitted on a few hundred rows.
MIN_ROWS_PER_SPORT = 5000


def _k_centre_curve(
    rows: list[dict[str, Any]], baselines: dict[str, Any]
) -> dict[float, float]:
    """Brier by K over one population of settled rows."""
    curve: dict[float, float] = {}
    for k in K_GRID:
        errors: list[float] = []
        for row in rows:
            market = row["market"]
            comp_id = str(row["competition_id"])
            # Same precedence as run_sheet.get_prior, and the same tolerance
            # of both pool shapes: `{"mean": x, "n": k}` since 2026-09-21,
            # a bare float in every file written before it. K_CENTRE is
            # fitted against these priors, so reading them differently here
            # than the sheet does would fit a constant for a model that does
            # not ship.
            prior = None
            if market in baselines:
                if comp_id in baselines[market]:
                    prior = baselines[market][comp_id]["mean"]
                else:
                    prior = _pooled_mean(baselines[market])

            mean = row["sample_mean"]
            n = row["sample_size"]
            if prior is not None:
                w = n / (n + k)
                centre = w * mean + (1.0 - w) * prior
            else:
                centre = mean

            var_sample = max(row["sample_sd"] ** 2, mean)
            pred_sd = math.sqrt(var_sample * (1.0 + 1.0 / n))
            boundary = winning_boundary(row["line"], row["direction"])
            # Must be the estimator run_sheet actually ships, or the curve is
            # fitted on one model and applied to another. See
            # NEGATIVE_BINOMIAL_METRICS.
            if uses_negative_binomial(market):
                p = max(
                    P_FLOOR,
                    min(
                        P_CEILING,
                        calc_p_central_nb_raw(centre, pred_sd, boundary, row["direction"]),
                    ),
                )
            else:
                p = calc_p_central(
                    centre,
                    pred_sd,
                    boundary,
                    row["direction"],
                    support_floor_for(market),
                )
            # Brier, not |p - outcome|. Median absolute error is not a proper
            # scoring rule: it is insensitive to the tails and it rewards a
            # blunt forecast, so it is minimised by throwing the sample away.
            # Measured on 516,900 settled rows it fell monotonically to
            # K = 1000 — "ignore the sample entirely" — while Brier and log
            # loss both put the optimum at K = 25 and rated K = 1000 worse
            # than K = 8. The criterion was choosing to switch the pipeline
            # off (F44).
            errors.append((p - (1.0 if row["outcome"] == "WIN" else 0.0)) ** 2)

        if errors:
            curve[k] = statistics.mean(errors)
    return curve


def fit_k_centre(
    conn: sqlite3.Connection, baselines: dict[str, Any]
) -> tuple[float | None, dict[float, float]]:
    """Weight of the league prior against the sample mean, pooled."""
    rows = [dict(r) for r in conn.execute(K_CENTRE_ROWS_SQL)]
    if not rows:
        return None, {}
    curve = _k_centre_curve(rows, baselines)
    return _pick_plateau_k(curve, BRIER_PLATEAU_TOLERANCE), curve


def fit_k_centre_by_sport(
    conn: sqlite3.Connection, baselines: dict[str, Any]
) -> dict[str, float]:
    """K_CENTRE per sport. The pooled fit is, in practice, a football fit.

    K_CENTRE weighs the league prior against the sample, so it can only be as
    transferable as the priors are. Football carries 419 per-competition
    baselines and the prior is genuinely informative; tennis carries exactly
    one — the global mean of all tennis, ATP down to ITF — so leaning on it is
    close to leaning on nothing in particular. The settled history is 98%
    football, so the pooled answer (K = 25) is football's.

    Measured per sport on 2026-09-18: football's Brier minimises at K = 25
    (0.16311), tennis's at **K = 2** (0.18873), and tennis at K = 25 scores
    0.20492 — 8.6% worse. One number was asking a UTR PTT group match to be
    two-thirds "the average tennis match" (F46).
    """
    rows = [dict(r) for r in conn.execute(K_CENTRE_ROWS_SQL)]
    by_sport: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_sport.setdefault(str(row["sport"]), []).append(row)

    fitted: dict[str, float] = {}
    for sport, sport_rows in sorted(by_sport.items()):
        if len(sport_rows) < MIN_ROWS_PER_SPORT:
            continue
        picked = _pick_plateau_k(
            _k_centre_curve(sport_rows, baselines), BRIER_PLATEAU_TOLERANCE
        )
        if picked is not None:
            fitted[sport] = picked
    return fitted


def fit_k_price(
    conn: sqlite3.Connection,
) -> tuple[float | None, dict[float, float]]:
    """Weight of the sample against the devigged market price.

    Backfilled rows carry ``market_p = NULL`` by construction (A9), so this
    fits only on rows settled live. With none, the curve is empty and the
    caller must say so rather than write a number.
    """
    rows = [
        dict(r)
        for r in conn.execute(
            """
            SELECT p_central, market_p, sample_size, outcome
            FROM sofa_settled_row
            WHERE outcome IN ('WIN', 'LOSS') AND market_p IS NOT NULL
            ORDER BY id
            """
        )
    ]
    if not rows:
        return None, {}

    curve: dict[float, float] = {}
    for k in K_GRID:
        errors = []
        for row in rows:
            n = row["sample_size"]
            w = n / (n + k)
            p_bar = w * row["p_central"] + (1.0 - w) * row["market_p"]
            # Brier, for the reason given in fit_k_centre: the median of an
            # absolute error is not a proper scoring rule and is minimised by
            # a blunt forecast. This curve is empty today — backfilled rows
            # carry no price — so the flaw has never shipped here, but it
            # would the first day live-settled rows arrive (F44).
            errors.append((p_bar - (1.0 if row["outcome"] == "WIN" else 0.0)) ** 2)
        curve[k] = statistics.mean(errors)

    return _pick_plateau_k(curve, BRIER_PLATEAU_TOLERANCE), curve


def fit_max_ladder_sigma(
    conn: sqlite3.Connection,
) -> tuple[float | None, dict[str, Any]]:
    """Threshold above which the sample stops describing the priced match.

    This one cannot be fitted from the backfill: there are no historical
    Superbet ladders, so a backfilled row has no ladder sigma to threshold.
    It can only be fitted from rows settled live.

    When there is nothing to fit on, this returns ``None`` and a reason. The
    caller writes null. Writing 1.25 instead — a value measured on another
    provider's dispersion — would look exactly like a fitted constant.
    """
    rows = [
        dict(r)
        for r in conn.execute(
            """
            SELECT ladder_sigma, p_central, outcome
            FROM sofa_settled_row
            WHERE outcome IN ('WIN', 'LOSS') AND ladder_sigma IS NOT NULL
            ORDER BY ladder_sigma
            """
        )
    ]
    if len(rows) < 200:
        return None, {
            "status": "NOT_FITTED",
            "rows_available": len(rows),
            "rows_required": 200,
            "reason": (
                "MAX_LADDER_SIGMA needs rows settled against a live Superbet "
                "ladder. Backfilled rows have market_p = NULL and no ladder "
                "(PLAN §A9), so they cannot support this constant."
            ),
        }

    # Walk sigma bands and find where declared probability stops tracking
    # realisation. Bands are quantile-based so the threshold is a property of
    # this data's own spread, not of an absolute number (L15).
    sigmas = sorted(r["ladder_sigma"] for r in rows)
    bands: list[dict[str, Any]] = []
    n_bands = 10
    for i in range(n_bands):
        lo = sigmas[int(len(sigmas) * i / n_bands)]
        hi = sigmas[min(len(sigmas) - 1, int(len(sigmas) * (i + 1) / n_bands))]
        in_band = [r for r in rows if lo <= r["ladder_sigma"] <= hi]
        if len(in_band) < 20:
            continue
        declared = statistics.mean(r["p_central"] for r in in_band)
        realised = statistics.mean(
            1.0 if r["outcome"] == "WIN" else 0.0 for r in in_band
        )
        bands.append(
            {
                "lo": round(lo, 4),
                "hi": round(hi, 4),
                "n": len(in_band),
                "declared": round(declared, 4),
                "realised": round(realised, 4),
                "gap": round(declared - realised, 4),
            }
        )

    threshold: float | None = None
    for band in bands:
        if band["gap"] > 0.10:
            threshold = band["lo"]
            break

    return threshold, {
        "status": "FITTED" if threshold is not None else "NO_DIVERGENCE",
        "rows_available": len(rows),
        "bands": bands,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", default=SofaConfig.from_env().db_path)
    parser.add_argument("--config-dir", default="config")
    args = parser.parse_args()

    db_path = Path(args.db_path)
    if not db_path.exists():
        print(f"DB {db_path} does not exist", file=sys.stderr)
        return 2

    config_dir = Path(args.config_dir)
    config_dir.mkdir(parents=True, exist_ok=True)

    with get_connection(str(db_path)) as conn:
        total_rows = conn.execute(
            "SELECT COUNT(*) AS c FROM sofa_settled_row"
        ).fetchone()["c"]
        leagues = conn.execute(
            "SELECT COUNT(DISTINCT competition_id) AS c FROM sofa_settled_row"
        ).fetchone()["c"]

        baselines = fit_baselines(conn)
        reliability = fit_reliability(conn)
        k_centre, k_centre_curve = fit_k_centre(conn, baselines)
        k_centre_by_sport = fit_k_centre_by_sport(conn, baselines)
        k_price, k_price_curve = fit_k_price(conn)
        max_sigma, sigma_report = fit_max_ladder_sigma(conn)

    # Metadata first, so a reader can tell how old the file is and what it was
    # built from. Until 2026-09-21 this file carried none at all: the copy in
    # config was written 2026-09-19 against a settled table that had since
    # grown by 88,185 rows and 120 competitions, and nothing on disk said so.
    # `sofa_engine_constants.json` had `fitted_from` from the start; this one
    # is the file the centre actually comes from.
    coherence = check_half_match_coherence(baselines)
    baselines_out: dict[str, Any] = {
        "_doc": (
            "Per-competition mean of each market's realised value, fitted by "
            "scripts/sofa/fit_constants.py from sofa_settled_row. An entry "
            "below MIN_BASELINE_OBSERVATIONS is not written — including the "
            "`global` pool, which is held to the same bar and records its own "
            "`n`. No entry means no prior, and run_sheet then uses the "
            "sample's own mean as the centre."
        ),
        "fitted_from": {
            "db_path": str(db_path),
            "settled_rows": total_rows,
            "distinct_competitions": leagues,
            "fitted_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "min_baseline_observations": MIN_BASELINE_OBSERVATIONS,
        },
        "half_match_coherence": coherence or "OK",
        **baselines,
    }
    if coherence:
        for line in coherence:
            print(f"BASELINE_INCOHERENT {line}", file=sys.stderr, flush=True)
    (config_dir / "sofa_league_baselines.json").write_text(
        json.dumps(baselines_out, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (config_dir / "sofa_market_reliability.json").write_text(
        json.dumps(reliability, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    constants: dict[str, Any] = {
        "_doc": (
            "Fitted by scripts/sofa/fit_constants.py from sofa_settled_row. "
            "A null value means NOT FITTED — the engine falls back to its "
            "documented starting behaviour, which is identity, not a default "
            "borrowed from another provider (PLAN §6.0)."
        ),
        "fitted_from": {
            "db_path": str(db_path),
            "settled_rows": total_rows,
            "distinct_competitions": leagues,
        },
        "K_CENTRE": {
            "value": k_centre,
            "by_sport": k_centre_by_sport,
            "curve": {str(k): round(v, 6) for k, v in k_centre_curve.items()},
            "status": "FITTED" if k_centre is not None else "NOT_FITTED",
            "criterion": "largest non-sentinel K within "
            f"{BRIER_PLATEAU_TOLERANCE} of the minimum Brier score; "
            "NOT_FITTED when that band covers the whole grid",
        },
        "K_PRICE": {
            # Keyed off the value, not the curve. _pick_plateau_k can now
            # return None on a *non-empty* curve — a degenerate plateau, or one
            # only the sentinel wins — and "status FITTED, value null" would be
            # a constant reported as measured with nothing in it.
            "value": k_price,
            "curve": {str(k): round(v, 6) for k, v in k_price_curve.items()},
            "status": "FITTED" if k_price is not None else "NOT_FITTED",
            "criterion": "as K_CENTRE (Brier), on rows carrying a devigged "
            "market price",
        },
        "MAX_LADDER_SIGMA": {"value": max_sigma, **sigma_report},
    }
    (config_dir / "sofa_engine_constants.json").write_text(
        json.dumps(constants, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    fitted = sum(
        1
        for key in ("K_CENTRE", "K_PRICE", "MAX_LADDER_SIGMA")
        if constants[key]["value"] is not None
    )
    verdict = "OK" if fitted == 3 and baselines else "PARTIAL"

    print(
        "SOFA_SUMMARY: "
        + json.dumps(
            {
                "stage": "FIT_CONSTANTS",
                "verdict": verdict,
                "metrics": {
                    "settled_rows": total_rows,
                    "distinct_competitions": leagues,
                    "baseline_markets": len(baselines),
                    "reliability_markets": len(reliability),
                    "constants_fitted": fitted,
                    "k_centre": constants["K_CENTRE"]["value"],
                    "k_price": constants["K_PRICE"]["value"],
                    "max_ladder_sigma": max_sigma,
                },
                "output_path": str(config_dir),
            }
        )
    )
    return 0 if verdict == "OK" else 1


if __name__ == "__main__":
    sys.exit(main())
