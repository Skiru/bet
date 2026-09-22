"""Pricing the markets that are about both sides of a fixture at once.

`run_sheet.py` prices one marginal at a time: a ladder of lines against one
sample. That is the right shape for "liczba rzutów rożnych" and for
"Brentford - liczba rzutów rożnych", and the wrong shape for every market in
this module, which asks a question no marginal can answer:

  * ``both_over_<metric>``  — "Każda z drużyn powyżej 3.5 rz.rożnych", and
    "Obie drużyny strzelą", which is the same market at line 0.5.
  * ``most_<metric>``       — "Najwięcej kartek", "Liczba rzutów rożnych - H2H".
  * ``handicap_<metric>``   — "Rzuty rożne handicap", "Handicap gemy".

Each side's marginal comes from its own sample, exactly as before. The
dependence between them is measured, not assumed — see joint.py and
config/sofa_side_correlations.json.

Two things this module deliberately does NOT do differently from the marginal
path, because they are the guards that make a row trustworthy rather than
merely produced:

  * the [0.05, 0.95] resolution refusal (F35) applies unchanged, so a
    both-teams rung the model cannot resolve is refused rather than floored;
  * the ladder gate applies unchanged, so a rung with no measurable ladder is
    a LEAN with the reason recorded, never a VALUE. Comparative markets have
    no ladder at all and therefore cannot currently reach a coupon. That is a
    known ceiling, stated rather than worked around.
"""

from __future__ import annotations

import json
import math
import statistics
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz

from bet.sofa.contracts import (
    Direction,
    Fixture,
    FixtureOffer,
    FixtureSamples,
    GapReason,
    Observation,
    PricedRung,
    SheetRow,
    Veto,
)
from bet.sofa.engine import (
    bar_probability,
    devig,
    devig_many,
    get_required_odds,
    ladder_centre,
    outside_model_resolution,
)
from bet.sofa.joint import (
    JointCounts,
    build_joint,
    joint_tail_from_marginal_tails,
    latent_rho,
)
from bet.sofa.market_mapper import (
    DERIVED_DRAW_SUBJECT,
    derived_base,
    derived_side_metric,
    is_derived,
)
from bet.sofa.names import normalize_name

CORRELATIONS_PATH = Path("config/sofa_side_correlations.json")

# Same threshold the marginal path uses for attributing a per-side market.
SIDE_MATCH_THRESHOLD = 70.0

# How hard a handicap centre is pulled onto the bookmaker's own ladder.
#
# The marginal path shrinks its centre toward a league baseline at line 405 of
# run_sheet.py. The derived path never shrank at all: `centre` came out equal
# to `sample_mean` on 17,496 of 17,496 derived rows written across
# 2026-09-18..22, while a `ladder_centre` was computed and discarded on 58.1%
# of them.
#
# That is not a cosmetic difference, because a handicap centre is a difference
# of two marginals taken over *different* opponents. In tennis both players'
# `games_won_for` means sit in roughly [6, 13] whatever their strength — the
# loser of a BO3 still wins six or seven games — so the difference of the two
# carries almost no signal about the margin. Measured on 313 unique
# subject-fixtures that settled:
#
#     centre                        MAE        corr with realised margin
#     our sample                    4.93            +0.137
#     Superbet's handicap ladder    3.86            +0.516
#
# On 2026-09-21 that shipped three tennis handicap legs whose centre had the
# wrong SIGN — Ostapenkov +0.40 (ladder -4.82, actual -8.0), Dinev +3.43
# (ladder -6.27, actual -8.0), Villanueva +2.60 (ladder -1.79, actual -4.0).
# All three lost.
#
# K is fitted by minimising the residual sd of the realised margin, in the
# same n/(n+K) form the marginal path uses. The curve is flat from K=20 to
# K=60 (sd 4.813 -> 4.813, optimum 4.801 at K=32.5) and leave-one-day-out
# refits it at 30.0, 32.5 and 35.0 with the held-out day improving every time:
#
#     held out      fitted K     test sd      test sd at today's K=0
#     2026-09-19      35.0         4.208            5.069
#     2026-09-20      32.5         5.048            5.878
#     2026-09-21      30.0         4.901            5.703
#
# Caveat kept deliberately: every sample behind this fit has n in [5, 10], so
# the n-dependence of the n/(n+K) form is barely exercised. Over that range it
# is indistinguishable from a flat weight of 0.25 on our own sample.
K_DERIVED_CENTRE = 30.0


def _ladder_diff_centre(
    handicap_ladders: dict[str, float | None],
    fixture: Fixture,
) -> float | None:
    """The market's own centre for (side A - side B), in the metric's units.

    `handicap_ladders` holds, per subject, the handicap line at which the
    ladder crosses P = 0.5. A subject on side A covering `+L` at even money
    means the median of A - B is `-L`; the same reading on side B is `+L`.
    Both sides are used when both are quoted, which also averages out the
    half-rung granularity of the ladder.
    """
    implied: list[float] = []
    for subject, centre in handicap_ladders.items():
        if centre is None:
            continue
        side = resolve_subject(subject, fixture)
        if side == "side_a":
            implied.append(-centre)
        elif side == "side_b":
            implied.append(centre)
    if not implied:
        return None
    return statistics.mean(implied)


def _shrink_sides_to_diff(
    stats_a: SideStats,
    stats_b: SideStats,
    diff_target: float,
) -> tuple[SideStats, SideStats]:
    """Move the two means until their difference is `diff_target`.

    The shift is split evenly between the sides, which leaves A + B untouched.
    That matters: for tennis the total is the match length, it is a real
    quantity priced by `games_total` on its own ladder, and it is not the one
    measured to be broken. Only the margin moves.
    """
    diff_model = stats_a.mean - stats_b.mean
    delta = (diff_target - diff_model) / 2.0
    mean_a = max(1e-6, stats_a.mean + delta)
    mean_b = max(1e-6, stats_b.mean - delta)
    return (
        SideStats(n=stats_a.n, mean=mean_a, variance=stats_a.variance,
                  sd=stats_a.sd),
        SideStats(n=stats_b.n, mean=mean_b, variance=stats_b.variance,
                  sd=stats_b.sd),
    )


def load_side_correlations(
    path: Path = CORRELATIONS_PATH,
) -> dict[str, float | None]:
    """Measured per-metric correlation between the two sides of a match.

    A missing file means every metric is unmeasured, and an unmeasured metric
    is priced as independent. That is the wrong answer — the measurement says
    corners are negatively correlated — but it is the *documented* wrong
    answer, and it is what the marginal path already implies today. Inventing
    a number here would be worse.
    """
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if not isinstance(raw, dict):
        return {}
    out: dict[str, float | None] = {}
    for key, value in raw.items():
        if key.startswith("_") or not isinstance(value, dict):
            continue
        correlation = value.get("correlation")
        if isinstance(correlation, int | float) and not isinstance(correlation, bool):
            out[key] = float(correlation)
        else:
            out[key] = None
    return out


def market_marginal_tails(
    offer: FixtureOffer, base: str, fixture: Fixture
) -> dict[str, dict[float, float]]:
    """What Superbet itself says about each side separately, per line.

    Read off the per-team ladder of the underlying metric ("Brentford -
    liczba rzutow roznych"), devigged. Returns {"side_a": {line: P(> line)}}.
    """
    side_metric = derived_side_metric(base)
    out: dict[str, dict[float, float]] = {}
    for rung in offer.rungs:
        if rung.market != side_metric or not rung.subject:
            continue
        probs = devig(rung.over_odds, rung.under_odds)
        if probs is None:
            continue
        side = resolve_subject(rung.subject, fixture)
        if side not in ("side_a", "side_b"):
            continue
        out.setdefault(side, {})[rung.line] = probs[0]
    return out


@dataclass(frozen=True)
class SideStats:
    n: int
    mean: float
    variance: float
    sd: float


def _side_stats(observations: list[Observation]) -> SideStats | None:
    values = [o.value for o in observations]
    n = len(values)
    if n == 0:
        return None
    mean = statistics.mean(values)
    if n > 1:
        variance = statistics.variance(values)
        sd = statistics.stdev(values)
    else:
        variance = 0.0
        sd = 0.0
    return SideStats(n=n, mean=mean, variance=variance, sd=sd)


def resolve_subject(subject: str, fixture: Fixture) -> str | None:
    """Which side a comparative or handicap selection names.

    Superbet writes the two sides either as their names or as "1" and "2".
    Returns "side_a", "side_b", "draw", or None when it cannot be told —
    and None means the row is skipped, never quietly attributed to the home
    side.
    """
    if subject == DERIVED_DRAW_SUBJECT:
        return "draw"
    cleaned = subject.strip()
    if cleaned == "1":
        return "side_a"
    if cleaned == "2":
        return "side_b"

    normalised = normalize_name(cleaned)
    home = fuzz.token_sort_ratio(normalised, normalize_name(fixture.home_name))
    away = fuzz.token_sort_ratio(normalised, normalize_name(fixture.away_name))
    best = max(home, away)
    if best < SIDE_MATCH_THRESHOLD:
        return None
    if abs(home - away) < 1e-9:
        return None
    return "side_a" if home > away else "side_b"


def _shifted(stats: SideStats, direction: int) -> tuple[float, float]:
    """Mean shifted one standard error against the bet, and its variance.

    This is the derived-market analogue of `calculate_p_low`: the marginal
    path shifts one centre by 1.96 standard errors in the direction that hurts
    the bet, and here both centres move, each in the direction that hurts.
    """
    if stats.n <= 0:
        return stats.mean, stats.variance
    se = stats.sd / math.sqrt(stats.n)
    return max(1e-6, stats.mean + direction * 1.96 * se), stats.variance


def probability(
    joint: JointCounts, market: str, line: float, direction: Direction, side: str | None
) -> float | None:
    """The model's probability for one derived selection."""
    base = derived_base(market)
    if base is None:
        return None

    if market.startswith("both_over_"):
        # "powyżej 3.5" on an integer count is ">= 4".
        threshold = math.floor(line) + 1
        p_yes = joint.p_both_at_least(threshold, threshold)
        return p_yes if direction == "OVER" else 1.0 - p_yes

    if market.startswith("most_"):
        if side == "draw":
            return joint.p_equal()
        if side == "side_a":
            return joint.p_a_greater()
        if side == "side_b":
            return joint.p_b_greater()
        return None

    if market.startswith("handicap_"):
        # "Brentford (-1.5)" wins when Brentford's count minus Chelsea's
        # exceeds 1.5. The sign is already on the selection's own line.
        if side == "side_a":
            return joint.p_diff_greater(-line)
        if side == "side_b":
            # Mirror: B - A > -line  <=>  A - B < line.
            return 1.0 - joint.p_diff_greater(line) - _p_diff_equals(joint, line)
        return None

    return None


def _p_diff_equals(joint: JointCounts, threshold: float) -> float:
    """Mass exactly on the handicap, which a half-line never carries."""
    if threshold != math.floor(threshold):
        return 0.0
    target = int(threshold)
    total = 0.0
    for i in range(joint.kmax + 1):
        j = i - target
        if 0 <= j <= joint.kmax:
            total += joint.pmf[i][j]
    return total


def _market_probabilities(
    rungs: list[PricedRung],
) -> dict[tuple[str, float, str], float]:
    """Devigged market probabilities for one derived family.

    Three shapes, three devigs:
      * both_over — over and under of the same line are complements;
      * most_     — the three selections are a complete partition;
      * handicap  — the two selections of one line are complements.
    """
    out: dict[tuple[str, float, str], float] = {}
    if not rungs:
        return out

    market = rungs[0].market

    if market.startswith("both_over_"):
        for rung in rungs:
            probs = devig(rung.over_odds, rung.under_odds)
            if probs:
                out[(rung.subject, rung.line, "OVER")] = probs[0]
                out[(rung.subject, rung.line, "UNDER")] = probs[1]
        return out

    if market.startswith("most_"):
        implied = [
            (r.subject, 1.0 / r.over_odds)
            for r in rungs
            if r.over_odds and r.over_odds > 1.0
        ]
        # `devig_many`, not `p / total`: the three selections are a complete
        # market, so they get the same treatment as the two sides of a rung.
        # Dividing by the sum is the proportional devig, which on 2026-09-18's
        # settled two-way rungs overstated the long shot by 7 points — and
        # "who takes more corners" is mostly long shots, with no ladder check
        # behind it to catch the consequence (F51).
        devigged = devig_many([p for _, p in implied])
        if devigged is not None:
            for (subject, _), p in zip(implied, devigged, strict=True):
                out[(subject, 0.0, "OVER")] = p
        return out

    if market.startswith("handicap_"):
        # The complement of "Brentford (-0.5)" is "Chelsea (+0.5)" — the other
        # subject at the negated line, not every rung sharing |line|.
        # Superbet quotes both {A(-0.5), B(+0.5)} and {A(+0.5), B(-0.5)} as
        # separate markets, so grouping on abs(line) pools four selections
        # that do not sum to one and the devig silently produced nothing.
        by_subject_line = {(r.subject, r.line): r for r in rungs}
        for (subject, line), rung in by_subject_line.items():
            mate = next(
                (
                    other
                    for (other_subject, other_line), other in by_subject_line.items()
                    if other_subject != subject and other_line == -line
                ),
                None,
            )
            if mate is None:
                continue
            if not rung.over_odds or not mate.over_odds:
                continue
            if rung.over_odds <= 1.0 or mate.over_odds <= 1.0:
                continue
            total = 1.0 / rung.over_odds + 1.0 / mate.over_odds
            if total > 0:
                out[(subject, line, "OVER")] = (1.0 / rung.over_odds) / total
        return out

    return out


def price_derived_rungs(
    fixture: Fixture,
    samples: FixtureSamples,
    offer: FixtureOffer,
    correlations: dict[str, float | None],
    vetoes: list[Veto],
    min_sample: int,
    max_ladder_sigma: float,
    k_price: float,
    unfitted: list[str],
    correction_for: Callable[[str, float, str], float] | None = None,
) -> tuple[list[SheetRow], list[tuple[PricedRung, GapReason, str]]]:
    rows: list[SheetRow] = []
    skipped: list[tuple[PricedRung, GapReason, str]] = []

    by_market: dict[str, list[PricedRung]] = {}
    for rung in offer.rungs:
        if is_derived(rung.market):
            by_market.setdefault(rung.market, []).append(rung)

    joint_cache: dict[str, tuple[JointCounts, SideStats, SideStats, float]] = {}

    for market, rungs in sorted(by_market.items()):
        base = derived_base(market)
        if base is None:
            continue
        side_metric = derived_side_metric(base)
        if side_metric not in samples.metrics:
            for rung in rungs:
                skipped.append(
                    (rung, GapReason.STAT_KEY_ABSENT, f"no {side_metric} sample")
                )
            continue

        sample = samples.metrics[side_metric]
        stats_a = _side_stats(sample.side_a)
        stats_b = _side_stats(sample.side_b)
        if stats_a is None or stats_b is None:
            for rung in rungs:
                skipped.append((rung, GapReason.THIN_SAMPLE, "one side has no sample"))
            continue
        n = min(stats_a.n, stats_b.n)
        if n < min_sample:
            for rung in rungs:
                skipped.append(
                    (rung, GapReason.THIN_SAMPLE, f"n={n} < min_sample={min_sample}")
                )
            continue
        if all(o.value == 0.0 for o in sample.side_a) and all(
            o.value == 0.0 for o in sample.side_b
        ):
            for rung in rungs:
                skipped.append(
                    (rung, GapReason.ALL_ZERO_SAMPLE, "both sides all zero")
                )
            continue

        rho = correlations.get(base)
        if base not in joint_cache:
            joint_cache[base] = (
                build_joint(
                    stats_a.mean,
                    stats_a.variance,
                    stats_b.mean,
                    stats_b.variance,
                    rho if rho is not None else 0.0,
                ),
                stats_a,
                stats_b,
                rho if rho is not None else 0.0,
            )
        joint, stats_a, stats_b, rho_used = joint_cache[base]

        market_ps = _market_probabilities(rungs)

        # The market's own view of each side separately. Comparing our joint
        # against this isolates the one quantity this module actually
        # measures — the dependence — from the marginal disagreement the rest
        # of the sheet already carries and which is not calibrated.
        marginal_tails = market_marginal_tails(offer, base, fixture)
        rho_latent = latent_rho(
            stats_a.mean,
            stats_a.variance,
            stats_b.mean,
            stats_b.variance,
            rho if rho is not None else 0.0,
        )

        # Ladder centre, where the family has a ladder at all.
        #
        # Superbet quotes most both-teams ladders on the "tak" side only —
        # every corner rung on Brentford-Chelsea, for instance — so requiring
        # a devigged pair leaves the whole family without a ladder check and
        # therefore permanently LEAN. A one-sided ladder still carries the
        # shape the check is about; what it does not carry is the margin, so
        # the crossing is read off prices that are inflated by roughly half
        # the overround. At the measured 8.7% that moves the implied centre by
        # well under a tenth of a line, against a gate measured in standard
        # deviations. Rows read this way say so.
        devigged: list[tuple[float, float]] = []
        one_sided: list[tuple[float, float]] = []
        ladder_is_one_sided = False
        if market.startswith("both_over_"):
            for rung in rungs:
                p_over = market_ps.get((rung.subject, rung.line, "OVER"))
                if p_over is not None:
                    devigged.append((rung.line, p_over))
                elif rung.over_odds and rung.over_odds > 1.0:
                    one_sided.append((rung.line, 1.0 / rung.over_odds))
        lc = ladder_centre(devigged)
        if lc is None and len(one_sided) >= 3:
            lc = ladder_centre(one_sided)
            ladder_is_one_sided = lc is not None

        # A handicap family is a ladder too — P(A - B > h) falls as h rises —
        # but it is one ladder per subject, not one per market.
        handicap_ladders: dict[str, float | None] = {}
        handicap_one_sided: set[str] = set()
        if market.startswith("handicap_"):
            per_subject: dict[str, list[tuple[float, float]]] = {}
            per_subject_raw: dict[str, list[tuple[float, float]]] = {}
            for rung in rungs:
                p_over = market_ps.get((rung.subject, rung.line, "OVER"))
                if p_over is not None:
                    per_subject.setdefault(rung.subject, []).append(
                        (rung.line, p_over)
                    )
                elif rung.over_odds and rung.over_odds > 1.0:
                    per_subject_raw.setdefault(rung.subject, []).append(
                        (rung.line, 1.0 / rung.over_odds)
                    )
            for subject in set(per_subject) | set(per_subject_raw):
                centre = ladder_centre(per_subject.get(subject, []))
                if centre is None and len(per_subject_raw.get(subject, [])) >= 3:
                    centre = ladder_centre(per_subject_raw[subject])
                    if centre is not None:
                        handicap_one_sided.add(subject)
                handicap_ladders[subject] = centre

        # See K_DERIVED_CENTRE. The handicap family — and only it, because it
        # is the only derived family whose centre has been measured against a
        # realised outcome — is repriced off a joint whose margin has been
        # pulled onto the ladder. The cached joint is left alone: the same
        # base metric also feeds both_over_* and most_*, which are not in
        # scope and must keep seeing the unshifted distribution.
        centre_shrunk_to: float | None = None
        raw_diff_mean = stats_a.mean - stats_b.mean
        if market.startswith("handicap_"):
            diff_ladder = _ladder_diff_centre(handicap_ladders, fixture)
            if diff_ladder is not None:
                diff_model = stats_a.mean - stats_b.mean
                w = n / (n + K_DERIVED_CENTRE)
                diff_target = w * diff_model + (1.0 - w) * diff_ladder
                if abs(diff_target - diff_model) > 1e-9:
                    stats_a, stats_b = _shrink_sides_to_diff(
                        stats_a, stats_b, diff_target
                    )
                    joint = build_joint(
                        stats_a.mean,
                        stats_a.variance,
                        stats_b.mean,
                        stats_b.variance,
                        rho_used,
                    )
                    centre_shrunk_to = diff_target

        # The scale a disagreement is measured in has to be the spread of the
        # variable the ladder is actually on: min(A, B) for a both-teams
        # ladder, A - B for a handicap. Using the sum's spread understates
        # every disagreement by about half, which on 2026-09-18 walked an
        # entire corners ladder — every rung of it — past the gate as VALUE.
        min_mean, min_sd = joint.min_moments()
        diff_mean, diff_sd = joint.diff_moments()

        for rung in rungs:
            side = resolve_subject(rung.subject, fixture) if rung.subject else None
            if rung.subject and side is None:
                skipped.append(
                    (
                        rung,
                        GapReason.NO_MATCHING_EVENT,
                        f"subject {rung.subject!r} matches neither side",
                    )
                )
                continue

            directions: tuple[Direction, ...] = (
                ("OVER", "UNDER") if market.startswith("both_over_") else ("OVER",)
            )

            for direction in directions:
                offered = rung.over_odds if direction == "OVER" else rung.under_odds

                p_raw = probability(joint, market, rung.line, direction, side)
                if p_raw is None:
                    continue
                if outside_model_resolution(p_raw):
                    skipped.append(
                        (
                            rung,
                            GapReason.OUTSIDE_MODEL_RESOLUTION,
                            f"p={p_raw:.4g} for {direction} outside [0.05, 0.95]",
                        )
                    )
                    continue

                p_low = _adverse_probability(
                    stats_a, stats_b, rho_used, market, rung.line, direction, side
                )

                m_p = market_ps.get((rung.subject, rung.line, direction))

                force_weight_0 = _vetoed(vetoes, fixture, rung, direction)

                # The same measured overconfidence correction the marginal
                # path takes. A derived row is built from the same marginals
                # by the same estimator, and leaving it uncorrected while
                # correcting everything else would make the joint families
                # look systematically cheaper than they are. Measured on
                # 48,644 replayed matches the goals joint predicts 0.3157
                # against an actual 0.3054, so the overstatement is real and
                # in the same direction.
                correction = (
                    correction_for(market, p_raw, direction)
                    if correction_for
                    else 0.0
                )

                p_bar, bar_reason = bar_probability(
                    p_central=p_raw,
                    hits=0,
                    n=n,
                    p_low_val=p_low,
                    market_p=m_p,
                    k_price=k_price,
                    correction=correction,
                    force_weight_0=force_weight_0,
                )

                req_odds = round(get_required_odds(p_bar, "LEAN"), 4)
                p_cent_out = round(p_raw, 4)
                m_p_out = round(m_p, 4) if m_p is not None else None
                edge = (
                    round(p_cent_out - m_p_out, 4) if m_p_out is not None else None
                )
                surplus = round(offered - req_odds, 4) if offered is not None else None

                if market.startswith("both_over_"):
                    scale_mean, scale_sd = min_mean, min_sd
                    raw_scale_mean = min_mean
                    family_ladder = lc
                    one_sided_here = ladder_is_one_sided
                elif market.startswith("handicap_"):
                    # `scale_mean` is the centre actually priced; on this
                    # family it may have been pulled onto the ladder above, so
                    # the raw sample difference is reported separately and the
                    # row can be read against its own p_central.
                    scale_mean, scale_sd = diff_mean, diff_sd
                    raw_scale_mean = raw_diff_mean
                    if side == "side_b":
                        scale_mean = -scale_mean
                        raw_scale_mean = -raw_scale_mean
                    family_ladder = handicap_ladders.get(rung.subject)
                    one_sided_here = rung.subject in handicap_one_sided
                else:
                    scale_mean, scale_sd = diff_mean, diff_sd
                    raw_scale_mean = diff_mean
                    family_ladder = None
                    one_sided_here = False

                l_sigma = None
                if family_ladder is not None and scale_sd > 0:
                    model_line = _model_half_line(joint, market, side)
                    if model_line is not None:
                        l_sigma = abs(model_line - family_ladder) / scale_sd

                notes: list[str] = [
                    f"DERIVED: joint of both sides, rho={rho_used:+.3f}"
                    + ("" if rho is not None else " (UNMEASURED, independent)")
                ]
                if centre_shrunk_to is not None:
                    notes.append(
                        "CENTRE_SHRUNK_TO_LADDER: sample difference "
                        f"{raw_diff_mean:+.2f} pulled to {centre_shrunk_to:+.2f} "
                        f"(K_DERIVED_CENTRE={K_DERIVED_CENTRE:g}, n={n})"
                    )
                if one_sided_here and l_sigma is not None:
                    notes.append(
                        "ONE_SIDED_LADDER: centre read off quoted side only, "
                        "margin not removed"
                    )

                # What the same bet is worth if the market's own marginals
                # are taken at face value and only the measured dependence is
                # ours. A row that beats its bar on our sample but not on
                # this is a marginal disagreement wearing a correlation
                # market's clothes, and on 2026-09-18 the two pointed in
                # opposite directions on the very first fixture checked.
                p_marginal = None
                if market.startswith("both_over_") and marginal_tails:
                    tail_a = marginal_tails.get("side_a", {}).get(rung.line)
                    tail_b = marginal_tails.get("side_b", {}).get(rung.line)
                    if tail_a is not None and tail_b is not None:
                        both = joint_tail_from_marginal_tails(
                            tail_a, tail_b, rho_latent
                        )
                        p_marginal = both if direction == "OVER" else 1.0 - both

                verdict: Any = "BELOW_BAR"
                if offered is None:
                    verdict = "NO_PRICE"
                elif surplus is not None and surplus > 0:
                    if p_marginal is None:
                        # No measurement means no check — the same rule the
                        # marginal-disagreement branch below applies when the
                        # marginals DO disagree, for the same reason. Without
                        # per-side ladders at this line there is no price to
                        # test the joint against and no way to isolate the
                        # dependence, so the row is selected by our own sample
                        # alone. On 2026-09-19 that let 23 both_over_* rows
                        # into the coupon at a median price of 12.0, carrying
                        # NO_MARKET_MARGINAL and ONE_SIDED_LADDER at once and
                        # with no per-side sample that could check either.
                        verdict = "LEAN"
                        notes.append(
                            "NO_MARKET_MARGINAL_CHECK: the market's own "
                            "marginals are not quoted at this line, so the "
                            "joint cannot be checked against a price; "
                            "VALUE withheld"
                        )
                    elif offered <= get_required_odds(p_marginal, "LEAN"):
                        verdict = "LEAN"
                        notes.append(
                            "MARGINAL_DISAGREEMENT: clears the bar on our "
                            f"sample (p={p_raw:.4f}) but not on the market's "
                            f"own marginals with our measured dependence "
                            f"(p={p_marginal:.4f}, needs "
                            f"{get_required_odds(p_marginal, 'LEAN'):.2f}); "
                            "VALUE withheld"
                        )
                    elif l_sigma is None:
                        verdict = "LEAN"
                        notes.append(
                            "NO_LADDER_CHECK: no measurable ladder for this "
                            "derived family; VALUE withheld"
                        )
                    elif l_sigma <= max_ladder_sigma:
                        verdict = "VALUE"
                    else:
                        verdict = "LEAN"
                        notes.append(
                            f"LADDER_DISAGREES: ladder_sigma {l_sigma:.3f} > "
                            f"{max_ladder_sigma:.3f}"
                        )

                if p_marginal is not None:
                    notes.append(
                        f"MARKET_MARGINAL_JOINT: p={p_marginal:.4f} "
                        f"(market's own per-side prices + rho={rho_used:+.3f})"
                    )
                elif market.startswith("both_over_"):
                    notes.append(
                        "NO_MARKET_MARGINAL: per-side ladders not quoted at "
                        "this line, dependence could not be isolated"
                    )

                if unfitted:
                    notes.append(f"UNFITTED_CONSTANTS: {', '.join(unfitted)}")
                if edge is not None and abs(edge) >= 0.15:
                    notes.append(f"PRICE_GAP: edge {edge:+.3f} vs market")

                rows.append(
                    SheetRow(
                        sofascore_event_id=fixture.sofascore_event_id,
                        sport=fixture.sport,
                        market=market,
                        subject=rung.subject,
                        line=rung.line,
                        direction=direction,
                        sample_size=n,
                        sample_mean=round(raw_scale_mean, 4),
                        sample_sd=round(scale_sd, 4),
                        centre=round(scale_mean, 4),
                        p_central=p_cent_out,
                        market_p=m_p_out,
                        ladder_centre=(
                            round(family_ladder, 4)
                            if family_ladder is not None
                            else None
                        ),
                        ladder_sigma=round(l_sigma, 4) if l_sigma is not None else None,
                        p_bar=round(p_bar, 4),
                        bar_reason=bar_reason,
                        # F48. Published for the same reason the direct path
                        # publishes it: without this term the row does not
                        # determine its own p_bar. 162 derived rows on the
                        # 2026-09-18 sheet carried a correction the artifact
                        # did not mention.
                        calibration_correction=round(correction, 4),
                        required_odds=req_odds,
                        offered_odds=offered,
                        edge=edge,
                        surplus=surplus,
                        verdict=verdict,
                        notes=notes,
                    )
                )

    return rows, skipped


def _model_half_line(
    joint: JointCounts, market: str, side: str | None = None
) -> float | None:
    """The line at which the model puts this family's YES side at 0.5.

    Comparative markets are a single proposition, not a ladder, so they have
    no such line and their rows stay LEAN by design.
    """
    if market.startswith("both_over_"):
        previous = 1.0
        for threshold in range(0, joint.kmax + 1):
            p = joint.p_both_at_least(threshold, threshold)
            if p <= 0.5:
                if previous == p:
                    return threshold - 0.5
                return (threshold - 1) + (previous - 0.5) / (previous - p) - 0.5
            previous = p
        return None

    if market.startswith("handicap_"):
        # Walk the handicap up until the subject's chance of covering falls
        # through a half. Half-integer steps match the lines Superbet quotes.
        previous = 1.0
        step = -joint.kmax - 0.5
        while step <= joint.kmax + 0.5:
            if side == "side_b":
                p = 1.0 - joint.p_diff_greater(-step) - _p_diff_equals(joint, -step)
            else:
                p = joint.p_diff_greater(step)
            if p <= 0.5:
                if previous == p:
                    return step
                return step - 1.0 + (previous - 0.5) / (previous - p)
            previous = p
            step += 1.0
        return None

    return None


def _adverse_probability(
    stats_a: SideStats,
    stats_b: SideStats,
    rho: float,
    market: str,
    line: float,
    direction: Direction,
    side: str | None,
) -> float:
    """`p_low` for a derived row: both centres moved against the bet."""
    if market.startswith("both_over_"):
        shift = -1 if direction == "OVER" else 1
        mean_a, var_a = _shifted(stats_a, shift)
        mean_b, var_b = _shifted(stats_b, shift)
    elif market.startswith("most_"):
        if side == "side_a":
            mean_a, var_a = _shifted(stats_a, -1)
            mean_b, var_b = _shifted(stats_b, 1)
        elif side == "side_b":
            mean_a, var_a = _shifted(stats_a, 1)
            mean_b, var_b = _shifted(stats_b, -1)
        else:
            # A draw is hurt by the two sides moving apart, either way.
            mean_a, var_a = _shifted(stats_a, 1)
            mean_b, var_b = _shifted(stats_b, -1)
    else:
        if side == "side_a":
            mean_a, var_a = _shifted(stats_a, -1)
            mean_b, var_b = _shifted(stats_b, 1)
        else:
            mean_a, var_a = _shifted(stats_a, 1)
            mean_b, var_b = _shifted(stats_b, -1)

    adverse = build_joint(mean_a, var_a, mean_b, var_b, rho)
    p = probability(adverse, market, line, direction, side)
    return p if p is not None else 0.0


def _vetoed(
    vetoes: list[Veto], fixture: Fixture, rung: PricedRung, direction: Direction
) -> bool:
    for veto in vetoes:
        if veto.sofascore_event_id != fixture.sofascore_event_id:
            continue
        if veto.market is not None and veto.market != rung.market:
            continue
        if veto.subject is not None and veto.subject != rung.subject:
            continue
        if veto.line is not None and veto.line != rung.line:
            continue
        if veto.direction is not None and veto.direction != direction:
            continue
        if veto.reason_class == "SAMPLE_UNINFORMATIVE":
            return True
    return False
