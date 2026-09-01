"""Audit a slip the operator is about to place, against the market's own price.

Why this exists
---------------
On 2026-08-30/31 the operator placed twenty bets off their own screen, outside
the pipeline; nine lost. Thirteen of them are football fixtures bzzoiro prices,
and reconstructing those against its consensus showed what the win/loss column
hides completely: **exactly two were worth their price, and both won. The other
eleven were at or below fair -- six lost, and five won anyway.** The losses were
not unlucky reads of good spots. With one exception they were negative-
expectation bets that had no edge to lose in the first place, and five of the
winners were just as bad and simply landed.

That is not a fact any amount of team analysis surfaces. ``analyze.py`` answers
"how often has this happened", ``bet_builder_draft`` answers "which legs are
worth assembling"; neither answers "is the number on the screen bigger than the
number this is worth". This module is that last question, and only that one.

What it does, and what it deliberately does not
-----------------------------------------------
It converts a bookmaker's consensus block into the probability the *market*
assigns, and compares it to the price the operator can actually take. It does
**not** produce a second opinion about the fixture: ``fit_match_lambdas`` fits
the market, it does not disagree with it. An edge here means "Superbet is paying
more than the ~88-bookmaker consensus implies", which is the only kind of edge
this project can evidence.

It is also not a stake sizer and not a placement gate. Everything below returns
a number and a reason; what to do about it stays with the operator.

The one arithmetic that is not the market's
-------------------------------------------
Range markets ("goals 1-3 in each half", "over 0.5 and under 2.5 in the first
half") have no consensus line anywhere in the feed, so their probability is
derived from the fitted match rate through an independent-Poisson half split.
The split constant is measured, not assumed -- see ``FIRST_HALF_GOAL_SHARE``.
Those markets turn out to have a hard mathematical ceiling no fixture can beat,
which is the single most useful thing in this file: a price below the ceiling's
reciprocal cannot be a good bet for *any* match, so it is refusable before the
first piece of team analysis is read.
"""
from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

# Measured over 7,516 finished fixtures with both a full-time and a half-time
# score, 2026-05-01..2026-08-31, across every league bzzoiro covers: mean 1.339
# first-half goals against a 2.996 full-time mean. Second halves are the higher
# scoring ones, consistently and by a wide enough margin that assuming an even
# split materially misprices every first-half market.
FIRST_HALF_GOAL_SHARE = 0.447

# The grid the lambda fit searches. A match rate outside this band is not a
# football fixture, and clamping is honest where extrapolating is not.
_LAMBDA_MIN = 0.15
_LAMBDA_MAX = 4.5
_SCORE_CEILING = 12  # goals per side; P(more) is ~1e-9 at the top of the grid


def implied_probability(price: float) -> float:
    """The bookmaker's price as a probability, vig included.

    This is what the operator is being asked to believe, not what is true.
    Compare it to a devigged number and you will systematically flatter the bet;
    that asymmetry is the whole reason ``remove_vig`` exists next to it.
    """
    if price <= 1.0:
        raise ValueError(f"decimal odds must exceed 1.0, got {price!r}")
    return 1.0 / price


def remove_vig(*prices: float) -> tuple[float, ...]:
    """Normalise a complete market's prices to probabilities summing to one.

    Requires the *whole* market -- both sides of a two-way, all three of a 1X2.
    Devigging a single price is not possible and not attempted: there is nothing
    to normalise against.
    """
    if len(prices) < 2:
        raise ValueError("devigging needs a complete market, not one price")
    inverse = [implied_probability(p) for p in prices]
    overround = sum(inverse)
    return tuple(p / overround for p in inverse)


def poisson_pmf(k: int, lam: float) -> float:
    """P(exactly k) for a Poisson rate. Local so this module has no dependency
    beyond the standard library -- it is imported by a report path that must not
    fail because an optional wheel is missing."""
    if lam <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-lam) * lam**k / math.factorial(k)


def _score_grid(
    lam_home: float, lam_away: float
) -> tuple[float, float, float, list[float]]:
    """(P(home), P(draw), P(away), P(total==n)) under independent Poisson.

    Independence between the two sides is wrong in the way every scoreline model
    is wrong -- draws are under-predicted. It is used anyway because the fit is
    anchored on the observed 1X2 *and* over/under prices, so the bias lands in
    the fitted rates rather than in the answers taken from them.
    """
    home = draw = away = 0.0
    totals = [0.0] * (2 * _SCORE_CEILING)
    for i in range(_SCORE_CEILING):
        p_i = poisson_pmf(i, lam_home)
        for j in range(_SCORE_CEILING):
            p = p_i * poisson_pmf(j, lam_away)
            if i > j:
                home += p
            elif i == j:
                draw += p
            else:
                away += p
            totals[i + j] += p
    return home, draw, away, totals


def fit_match_lambdas(
    *,
    home_win: float,
    draw: float,
    away_win: float,
    over_25: float | None = None,
    under_25: float | None = None,
) -> tuple[float, float]:
    """Home and away scoring rates consistent with the consensus prices.

    The 1X2 fixes the *difference* between the two rates; without a totals line
    it barely constrains their sum, so pass ``over_25``/``under_25`` whenever the
    feed carries them. When it does, the totals term is weighted double: a
    misfitted match rate corrupts every derived market below, while a few points
    of draw probability do not.

    Coarse-to-fine rather than one dense grid -- same answer to well under a
    hundredth of a goal, roughly two hundred times fewer evaluations, which
    matters because a report prices dozens of fixtures in a row.
    """
    target = remove_vig(home_win, draw, away_win)
    over_target: float | None = None
    if over_25 is not None and under_25 is not None:
        over_target = remove_vig(over_25, under_25)[0]

    def error(lam_home: float, lam_away: float) -> float:
        p_home, p_draw, p_away, totals = _score_grid(lam_home, lam_away)
        err = (
            (p_home - target[0]) ** 2
            + (p_draw - target[1]) ** 2
            + (p_away - target[2]) ** 2
        )
        if over_target is not None:
            over = 1.0 - (totals[0] + totals[1] + totals[2])
            err += 2.0 * (over - over_target) ** 2
        return err

    best = (float("inf"), 1.0, 1.0)
    lo_h, hi_h, lo_a, hi_a = _LAMBDA_MIN, _LAMBDA_MAX, _LAMBDA_MIN, _LAMBDA_MAX
    for step in (0.1, 0.02, 0.005):
        candidates_h = _frange(lo_h, hi_h, step)
        candidates_a = _frange(lo_a, hi_a, step)
        best = (float("inf"), best[1], best[2])
        for lam_home in candidates_h:
            for lam_away in candidates_a:
                err = error(lam_home, lam_away)
                if err < best[0]:
                    best = (err, lam_home, lam_away)
        lo_h, hi_h = best[1] - step, best[1] + step
        lo_a, hi_a = best[2] - step, best[2] + step
    return best[1], best[2]


def _frange(start: float, stop: float, step: float) -> list[float]:
    start = max(start, _LAMBDA_MIN)
    stop = min(stop, _LAMBDA_MAX)
    out: list[float] = []
    value = start
    while value <= stop + 1e-9:
        out.append(round(value, 6))
        value += step
    return out or [start]


def probability_team_scores(lam: float) -> float:
    """P(this side scores at least once) at the fitted rate.

    The market's answer to "team X to score over 0.5", which is the market the
    2026-08-31 losses were concentrated in. Read it before the team's own
    scoring record, not after: a 90% historic scoring rate and a 1.42 price are
    not evidence of an edge if the consensus says 70%.
    """
    return 1.0 - math.exp(-lam)


def half_lambdas(
    total_lambda: float, share: float = FIRST_HALF_GOAL_SHARE
) -> tuple[float, float]:
    """Split a match rate into first- and second-half rates."""
    return total_lambda * share, total_lambda * (1.0 - share)


@dataclass(frozen=True)
class RangeMarket:
    """A goals market with a bounded window rather than a single line.

    ``implies`` names the markets this one makes redundant. A slip carrying both
    a range and something it already guarantees is paying for one event and
    counting two, which is how the 2026-08-30 Honduras slip came to offer 1.80
    for a 48.6% outcome.
    """

    key: str
    label: str
    probability: Callable[[float], float]
    implies: tuple[str, ...] = ()


def _p_first_half_one_or_two_and_second_half_scores(total_lambda: float) -> float:
    lam_1h, lam_2h = half_lambdas(total_lambda)
    p_1h = poisson_pmf(1, lam_1h) + poisson_pmf(2, lam_1h)
    return p_1h * (1.0 - poisson_pmf(0, lam_2h))


def _p_each_half_one_to_three(total_lambda: float) -> float:
    lam_1h, lam_2h = half_lambdas(total_lambda)
    p_1h = sum(poisson_pmf(k, lam_1h) for k in (1, 2, 3))
    p_2h = sum(poisson_pmf(k, lam_2h) for k in (1, 2, 3))
    return p_1h * p_2h


RANGE_MARKETS: dict[str, RangeMarket] = {
    "1h_over_0_5_under_2_5_and_2h_over_0_5": RangeMarket(
        key="1h_over_0_5_under_2_5_and_2h_over_0_5",
        label="1H over 0.5 + 1H under 2.5 + 2H over 0.5",
        probability=_p_first_half_one_or_two_and_second_half_scores,
    ),
    "each_half_1_3": RangeMarket(
        key="each_half_1_3",
        label="goals 1-3 in each half",
        probability=_p_each_half_one_to_three,
        # 1-3 in each half already forces a 2-6 full-time total, and with it
        # over 1.5. A slip pairing any of these has one event in it, not two.
        implies=("total_2_6", "total_over_1_5"),
    ),
}


def range_market_ceiling(key: str) -> tuple[float, float, float]:
    """(highest attainable probability, the match rate that attains it, price floor).

    The reason this is the most useful function here: these markets are bounded
    above by their own shape. "Goals 1-3 in each half" peaks at 52.0% around a
    3.6-goal match and falls away on both sides -- a dull match fails the lower
    bound, a wild one fails the upper. So a price under ~1.92 is refusable
    without knowing which teams are playing, and a price under about 2.10 leaves
    no room for the fact that no real fixture sits exactly on the peak.
    """
    market = RANGE_MARKETS[key]
    best_p, best_lam = 0.0, _LAMBDA_MIN
    lam = _LAMBDA_MIN
    while lam <= 2 * _LAMBDA_MAX:
        p = market.probability(lam)
        if p > best_p:
            best_p, best_lam = p, lam
        lam += 0.01
    return best_p, best_lam, 1.0 / best_p


def expected_value(price: float, probability: float) -> float:
    """Return per unit staked, minus the stake. ``0.0`` is a break-even bet."""
    return price * probability - 1.0


def slip_price_floor(leg_probabilities: Sequence[float]) -> float:
    """The price a slip must beat before its legs are worth discussing.

    A slip cannot be more likely than its least likely leg, so ``1 / p_weakest``
    is a hard floor -- a *necessary* condition, never a sufficient one. It is
    worth checking first because it is cheap and it fails loudly: the
    2026-08-31 Lecce three-leg builder was offered at 1.50 against a floor of
    1.49, meaning two of its three legs were being carried for nothing.
    """
    if not leg_probabilities:
        raise ValueError("a slip has at least one leg")
    weakest = min(leg_probabilities)
    if weakest <= 0.0:
        raise ValueError("leg probability must be positive")
    return 1.0 / weakest


def redundant_legs(leg_keys: Iterable[str]) -> list[tuple[str, str]]:
    """(carrier, redundant) pairs among a slip's legs.

    Only covers what ``RANGE_MARKETS`` states outright. It is a spotter for the
    specific trap already seen, not a general implication engine, and a clean
    result means "none of the known pairs", not "the legs are independent".
    """
    keys = list(leg_keys)
    found: list[tuple[str, str]] = []
    for key in keys:
        market = RANGE_MARKETS.get(key)
        if market is None:
            continue
        for implied in market.implies:
            if implied in keys:
                found.append((key, implied))
    return found


@dataclass(frozen=True)
class LegVerdict:
    """One leg, priced. ``verdict`` is the only field worth acting on."""

    label: str
    price: float
    fair_probability: float
    implied_probability: float
    edge: float
    expected_value: float
    verdict: str
    reason: str

    @property
    def fair_odds(self) -> float:
        return 1.0 / self.fair_probability


# Below this the bet is not close enough to fair to survive a modelling slip, a
# stale price, or the fact that the consensus itself carries vig. It is a
# threshold on *this project's* tolerance, not a law -- but it is the threshold
# every one of the 2026-08-30/31 losses failed.
MINIMUM_EDGE = 0.02


def audit_leg(
    *,
    label: str,
    price: float,
    fair_probability: float,
    minimum_edge: float = MINIMUM_EDGE,
) -> LegVerdict:
    """Compare an offered price to what the leg is worth.

    ``fair_probability`` is the caller's best evidenced number: the market's,
    via ``fit_match_lambdas``, wherever the feed carries the market; otherwise a
    Wilson lower bound off a real sample. Never a raw hit rate -- ``analyze.py``
    has the whole argument for why, and the Besiktas corner leg on 2026-08-31 is
    what ignoring it looks like: 5 of 6 reads as 83%, its lower bound is 44%, and
    the price on the screen was asking for 70%.
    """
    offered = implied_probability(price)
    edge = fair_probability - offered
    if edge >= minimum_edge:
        verdict, reason = "TAKE", f"pays {price:.2f} for a {fair_probability:.1%} event"
    elif edge >= 0.0:
        verdict, reason = (
            "MARGINAL",
            f"edge {edge:+.1%} is inside the noise of the fit -- no bet",
        )
    else:
        verdict, reason = (
            "REJECT",
            f"price implies {offered:.1%} against a fair {fair_probability:.1%}",
        )
    return LegVerdict(
        label=label,
        price=price,
        fair_probability=fair_probability,
        implied_probability=offered,
        edge=edge,
        expected_value=expected_value(price, fair_probability),
        verdict=verdict,
        reason=reason,
    )
