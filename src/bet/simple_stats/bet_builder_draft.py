"""Bet Builder draft: which legs are worth assembling, and what each must pay.

What this is not
----------------
It is not a price. There is no bet-builder endpoint anywhere in bzzoiro's API,
and no arithmetic here turns four leg prices into the one Superbet will show.
``BetBuilderDraft.combined_price`` is typed ``None`` on the contract itself
rather than merely defaulted to it, so nothing downstream can populate it even
by mistake. The operator reads the combined price off their own screen.

What it *is*, since 2026-09-03, is a **bar** for that price:
``min_acceptable_combined_odds``. Same conditional shape every threshold in
this pipeline has -- "worth taking if the screen shows at least X" -- applied
to the slip instead of the leg. Without it a slip had no acceptance test at
all, and the file said so in a sentence that read as a refusal to help.

The correlation this module was built around was measured, and it is not there
--------------------------------------------------------------------------
The paragraph that used to sit here asserted that corners, cards, fouls and
shots in one match are "strongly positively correlated", so the product of the
leg probabilities understates the parlay's, in the direction that flatters the
bet. That was never measured. It has been now, against real results:
2,669 settled candidate rows over 356 fixtures and five slates, every
same-fixture pair of them (12,555 pairs), asking how often two legs land
*together* versus how often independence says they should.

    lambda = P(A and B) / (P(A) x P(B))

    all pairs                             12,555   1.009  95% CI [1.005, 1.013]
    non-nested markets                    10,716   1.006
    nested part-vs-whole, same direction   1,326   1.045
    nested part-vs-whole, opposite         513     0.978

Flat across every probability band (1.007 / 0.999 / 1.000 for pair minima of
0.50-0.60, 0.60-0.70, 0.70-0.80). **Same-match legs are independent to within
measurement error.**

That is not a contradiction of the underlying intuition, it is a fact about
where the lines sit. The *counts* really do move together -- a foul-heavy match
really is a card-heavy match. But a leg is not a count, it is a threshold
crossing, and these thresholds are chosen far out in the loose tail (the
settled marginals here are 0.81-0.88). Correlation in levels barely propagates
to co-crossing when both thresholds are already comfortably clear. It survives
only where one leg's outcome is arithmetically inside the other's -- a team's
goals within the match's, a half within the ninety -- and there it is worth
4.5%, not the large discount the old note asked the operator to apply.

So the product is used, corrected by the measured lambda, and the bar is
printed. See ``CORRELATION_LAMBDA_NESTED``.

Why it is code and not prose
----------------------------
``bet-analyst`` has no Write or Edit tool by design, so the alternative is
free-handing this arithmetic in every report. That is exactly the anti-pattern
``wilson_lower_bound`` already exists to avoid: a threshold computed in prose
cannot be audited, reproduced, or tested, and a rounding slip in it is invisible.
So the margins live in a table, the tier rules live in one function, and both
have tests.

The tier rules are ``bet-analyst.md``'s own table, implemented
------------------------------------------------------------
``StatsSheetRow`` carries no tier field -- CALL/LEAN/WEAK/DROP is the analyst's
vocabulary, derived from the row's numbers. ``tier_for_row`` is that derivation
written down once, including the two structural ceilings the doc states: a
single-source row can never be CALL, and a player prop off a predicted XI is
capped at LEAN however large its sample.
"""
from __future__ import annotations

import math
from collections.abc import Callable, Iterable
from typing import Literal, NamedTuple

from bet.simple_stats.contracts import StatsSheetRow, StatsSheetV1
from bet.simple_stats.providers import PRIMARY_PROVIDER_BY_SPORT
from bet.strict_model import StrictBaseModel
from pydantic import Field

Tier = Literal["CALL", "LEAN", "WEAK", "DROP"]

# Low-line UNDER props are trivially clearable and dominate a p_low sort:
# "player carded UNDER 0.5" at 10/10 lands near 0.72, above almost every corners
# row, because most players are not carded in most matches -- which is also
# exactly why that side is priced near 1.05 and is not a bet.
#
# Lives here rather than in ``coupons`` because both consumers need it and they
# disagreed. The singles list pushed these to the end and said so in the file's
# own header; ``draft_legs`` sorted on ``-p_low`` alone, so the same rows *led*
# every Bet Builder. On 2026-09-01 that produced eight slips whose leading legs
# were "goals 1H UNDER 4.5" and "goals 2H UNDER 3.5" at Superbet prices of
# 1.001 and 1.05 -- the header promised they had been demoted while the slips
# below it were built out of nothing else.
TRIVIAL_UNDER_MAX_LINE = 1.5


def is_trivial_under(row: StatsSheetRow) -> bool:
    """A low-line UNDER: real as a read, worthless as a price."""
    return row.direction == "UNDER" and row.line <= TRIVIAL_UNDER_MAX_LINE


class AnalystVeto(StrictBaseModel):
    """One row bet-analyst disagreed with, from ``<date>_analyst_vetoes.json``.

    docs/PLAN_BOGATE_STATYSTYKI.md Faza 5e, Wariant A: the analyst has no
    Write tool by design (it must not rewrite the artifacts it evaluates), so
    this is text it returns alongside its usual markdown report; the
    orchestrator running ``run-day.md`` is what persists it to a file. It never
    touches ``p_low`` -- ``VETO`` removes a row from the coupon outright,
    ``DOWNGRADE`` steps its tier down once via the same ceiling
    ``context_flags`` uses, in both cases with the analyst's own reason
    reported in the coupon file's header so nothing is struck silently.

    ``line`` and ``direction`` are both optional, and **None means "all of
    them"**. A per-line veto could only ever describe a per-line fault, and the
    faults the analyst actually finds are rarely that shape: when six of
    eighteen ``cards_total`` observations are zeros in matches with twenty-plus
    fouls, the sample is broken for every line of that market, not for 4.5 and
    3.5 specifically. On 2026-09-01 exactly that happened -- 4.5 and 3.5 were
    vetoed on Sheffield United - Bolton, 5.5 was not written down, and 5.5 went
    out as a Bet Builder leg graded CALL off the same seven zeros.

    Resolution is most-specific-first, so a file may carry a market-wide veto
    and a per-line exception to it without ambiguity.
    """

    event_id: str
    market: str
    line: float | None = None
    direction: Literal["OVER", "UNDER"] | None = None
    action: Literal["VETO", "DOWNGRADE"]
    reason: str
    # *What kind* of objection this is, added 2026-09-03. ``reason`` is prose
    # for the operator; this is the part the pipeline can act on.
    #
    # DOWNGRADE used to mean one thing -- step the tier down once, which raises
    # the margin from 1.05 to 1.10 -- and under a ``p_central`` bar that is a 5%
    # move on the price. On 2026-09-03 the Grenal's ``fouls_total`` and both
    # ``fouls_for`` rows were downgraded with the reason "conditional on this
    # match the record is 1/3, not 19/21" and printed as value anyway. A 5%
    # margin is not an answer to "this sample is not measuring this fixture";
    # it is the answer to "this sample is fine and something else is uncertain".
    #
    # What each class does lives in ``coupons.build_coupons`` (see
    # ``VETO_CLASS_ZERO_WEIGHT`` and ``VETO_CLASS_DOUBLE_K``), not here: this
    # class is the analyst's vocabulary and must stay readable as such.
    #
    # Defaults to OTHER so a vetoes file written before this field existed
    # still validates and still behaves exactly as it did.
    reason_class: Literal[
        "SAMPLE_NOT_REPRESENTATIVE",
        "LINE_ON_MODE",
        "MISSING_REFEREE",
        "ESTIMAND_WRONG",
        "DATA_CONFLICT",
        "OTHER",
    ] = "OTHER"


class VetoIndex:
    """The analyst's vetoes, resolved per row, most specific first.

    Four lookups in a fixed order -- exact line and direction, then either one
    widened, then the whole market. The first hit wins, which is what lets a
    market-wide VETO coexist with a per-line DOWNGRADE on the same market
    without either silently shadowing the other.

    One index, shared by the singles loop and ``draft_legs``. That sharing is
    the entire point of the class existing: on 2026-09-01 the two paths had
    separate implementations of "is this row vetoed" -- one of them being no
    implementation at all -- and the Bet Builder shipped a slip whose every leg
    the analyst had struck.
    """

    __slots__ = ("_by_key", "ignored")

    def __init__(self, vetoes: Iterable[AnalystVeto] | None = None) -> None:
        self._by_key: dict[tuple[str, str, float | None, str | None], AnalystVeto] = {}
        # Entries this index refuses to resolve, kept so the coupon header can
        # say a decision was written down and not applied. Silently dropping
        # one would be worse than either applying or refusing it.
        self.ignored: list[tuple[AnalystVeto, str]] = []
        for veto in vetoes or ():
            if veto.reason_class == "LINE_ON_MODE" and veto.line is None:
                # "The line sits on the sample's mode" is a statement about one
                # rung. Written market-wide it would strike every rung of a
                # market on a fault that by construction belongs to one of
                # them, which is the opposite of what a per-line class is for.
                self.ignored.append(
                    (veto, "LINE_ON_MODE without a line names no rung")
                )
                continue
            self._by_key.setdefault(
                (veto.event_id, veto.market, veto.line, veto.direction), veto
            )

    def __bool__(self) -> bool:
        return bool(self._by_key)

    def for_row(self, row: StatsSheetRow) -> AnalystVeto | None:
        for line, direction in (
            (row.line, row.direction),
            (None, row.direction),
            (row.line, None),
            (None, None),
        ):
            hit = self._by_key.get((row.event_id, row.market, line, direction))
            if hit is not None:
                return hit
        return None

# One step down, both directions structural rather than about the numbers --
# same shape as the SINGLE_SOURCE/DISAGREE and predicted-lineup ceilings below.
# A row already at WEAK stays WEAK: context can argue a real read down to
# marginal, never all the way to DROP, which is reserved for a sample too thin
# to mean anything at all.
_STEP_DOWN: dict[Tier, Tier] = {"CALL": "LEAN", "LEAN": "WEAK"}


def cap_tier_at_lean(tier: Tier) -> Tier:
    """A ceiling, not a step: CALL becomes LEAN and nothing else moves.

    Distinct from ``step_tier_down`` because several structural caps fire on
    one fixture at once -- a derby, in a knockout second leg, with no referee
    named -- and three reasons to doubt a fixture do not make it three tiers
    worse. Stepping per reason would have taken the Grenal's card rows from
    CALL to DROP on evidence that says "at best a lean".
    """
    return "LEAN" if tier == "CALL" else tier


def step_tier_down(tier: Tier) -> Tier:
    """One tier step down, never past WEAK. Shared by ``tier_for_row``'s own
    ``context_flags`` ceiling and ``coupons.build_coupons``'s analyst-veto
    DOWNGRADE action (docs/PLAN_BOGATE_STATYSTYKI.md Faza 5e) -- one rule,
    reused, rather than the same mapping written twice."""
    return _STEP_DOWN.get(tier, tier)

# Margin over fair odds, by tier. A CALL is corroborated and reasonably sampled,
# so it needs less headroom than a LEAN carrying a structural caveat. Both are
# above 1.0 because ``p_low`` is already an optimistic floor: its trials are not
# independent (the sample pools both teams and their h2h), so a price exactly at
# fair odds is a losing bet at the true probability.
TIER_MARGIN: dict[str, float] = {"CALL": 1.05, "LEAN": 1.10}

# Which probability the price bar is derived from. ``p_central`` is the shipped
# default since 2026-09-03; ``p_low`` was, and is kept for comparison.
#
# Measured 2026-09-02 by settling 5,036 candidate rows over 282 fixtures and
# four slates: mean claimed ``p_low`` 0.613 against a realised win rate of
# 0.848 -- a +23.5pp understatement, conservative in every market, tier,
# direction and date, and never once optimistic. ``p_central`` on the same rows
# claimed 0.849 against 0.848, an error of -0.000. Because the bar is
# ``(1/p) x margin``, a 23.5pp understatement at p~0.6 inflates the demanded
# price by 0.848/0.613 = 1.38 *before* the tier margin, so the effective demand
# is 1.45-1.52 rather than the 1.05-1.10 the margin advertises. On the
# 2026-09-02 slate that banned every one of 341 priced football rows.
#
# **It became the default on 2026-09-03, and the reason is what ``p_low`` does
# to the bar rather than what ``p_central`` promises.**
#
# The understatement was re-measured independently, on 2,669 settled candidate
# rows over 356 fixtures, and it is not a constant to be shrugged at:
#
#     p_low band   n      claimed   realised   error
#     0.50-0.60    1,229  0.563     0.784      +22.1pp
#     0.60-0.70    761    0.644     0.862      +21.8pp
#     0.70-0.80    597    0.730     0.894      +16.4pp
#
# Because the bar is ``(1/p) x margin``, a +22pp understatement at p~0.56
# inflates the demanded price by 0.784/0.563 = 1.39 *before* the tier margin is
# applied. The gate advertises 5-10% of headroom and demands 45-53%. Nothing
# chose that number and no measurement supports it; it is an artifact of
# dividing by a lower bound.
#
# What it costs is the whole file. On the 2026-09-03 slate 5 of 15 singles
# cleared the bar on ``p_low`` and 7 on ``p_central`` -- and the ten it
# rejected were priced 1.20-1.55 against p_central of 0.75-0.82, which is to
# say they were positive expectation and were refused for being cheap. The
# operator's complaint that the file is thin is this arithmetic, restated.
#
# The caution the old note recorded still stands and is not repealed: the
# settled-and-priced population returned 0.980 per unit, and a
# ``p_central x 1.05`` arm returned 1.079 on a 95% interval of [0.948, 1.227]
# that flips sign between the only two slates with real prices. That interval
# is why ``TIER_MARGIN`` is untouched -- ``p_central`` overstates by ~4.4pp on
# exactly the subset a price gate selects, and the margin is what pays for it.
# It is not a reason to keep dividing by a number that is wrong by 22pp in the
# same direction on every row, every market and every slate.
#
# ``p_low`` remains selectable and remains the honest thing to compare against;
# ``scripts/simple/backtest_slate.py`` still defaults to it so its baseline
# keeps meaning what it meant.
BAR_BASES: tuple[str, ...] = ("p_central", "p_low")


# The two caps on the bar's *input*, and why the bar needed them at all.
#
# ``p_central`` is the count model read at the sample's own centre. On a sample
# with no miss the model is fitted to values that never crossed the line, so
# the tail it reports is a property of the fit and not of anything observed:
# Potapova's 5/5 aces sample, mean 1.4, returned p_central 0.962 at 3.5 UNDER
# and demanded a minimum price of 1.14. Her 2026 season average is 3.25 and she
# had hit 10 aces in round one. Every 5/5 tennis row on the 2026-09-03 slate
# passed its bar that way.
#
# **Neither cap touches ``p_central`` itself.** It stays on the row exactly as
# computed, because it is the number the calibration reporting is measured on
# and moving it would make the next measurement uninterpretable. What moves is
# the number the bar divides into 1.
#
# 1. **Zero misses: Laplace.** ``(hits + 1) / (n + 2)`` is the posterior mean
#    of a Bernoulli rate under a uniform prior -- the standard answer to "the
#    sample says 5 out of 5, what rate is that". At 5/5 it is 0.857, at 8/8
#    0.900, at 20/20 0.955. It is not conservative in the Wilson sense; it is
#    simply the largest rate a clean sweep is evidence for, and it is *below*
#    what a fitted tail will claim on any line the sample never approached.
#    Applied as a cap and not a replacement, so a sample whose model already
#    says less than Laplace keeps the smaller number.
#
# 2. **n < 8: the bar falls back to ``p_low``.** Eight is the threshold this
#    pipeline already uses for a settled sample (``_confidence``, and CALL's
#    own n>=8). Below it the count model is being asked to describe a
#    distribution from fewer trials than it has effective parameters, and the
#    honest statement of a thin sample is its lower bound. This is the cap that
#    does the work on the audited rows: it takes Potapova's bar from 1.14 to
#    1/0.5655 x 1.10 = 1.945.
#
# The two are not alternatives and are not ordered -- the bar takes the
# smallest of everything that applies, which is the only combination that
# cannot be argued into a looser threshold by adding a rule.
BAR_ZERO_MISS_N = 8

BAR_REASON_LAPLACE = "ZERO_MISS_LAPLACE_CAP"
BAR_REASON_SMALL_SAMPLE = "SMALL_SAMPLE_P_LOW"


def laplace_rate(hits: int, sample_size: int) -> float | None:
    """``(hits + 1) / (n + 2)``, or None on an empty sample."""
    if sample_size <= 0:
        return None
    return (hits + 1) / (sample_size + 2)


def bar_input(row: StatsSheetRow, basis: str = "p_low") -> tuple[float, str | None]:
    """``(probability, why it was capped)`` for the *sample* side of the bar.

    The reason is None when nothing capped the basis, and is carried through to
    the coupon so the operator can see why a minimum moved rather than only
    that it did.

    This is the sample's own claim after the two caps and before the market
    prior; ``bar_components`` is what actually feeds ``required_odds``.
    """
    if basis == "p_central" and row.p_central is not None:
        chosen, reason = row.p_central, None
    else:
        # ``p_low`` is already the tighter bar and already the honest statement
        # of a thin sample, so neither cap can improve on it and neither is
        # reported against it.
        return row.p_low, None

    if row.sample_size > 0 and row.hits >= row.sample_size:
        cap = laplace_rate(row.hits, row.sample_size)
        if cap is not None and cap < chosen:
            chosen, reason = cap, BAR_REASON_LAPLACE
    if row.sample_size < BAR_ZERO_MISS_N and row.p_low < chosen:
        chosen, reason = row.p_low, BAR_REASON_SMALL_SAMPLE
    return chosen, reason


# --- the market prior ------------------------------------------------------
#
# For every row the 2026-09-03 audit read, the devigged Superbet pivot was
# available and disagreed with us by 20 to 50 points: cards at a 7.5 pivot
# against a sample median of 5.5, fouls 36.5 against 27.4, aces 3.5 against
# 1.4. Nothing in the pipeline used it as evidence. ``MAX_MARKET_DISAGREEMENT``
# annotated the gap, ``MAX_LADDER_SIGMA`` demoted on it, and both are
# thresholds on a number that was never allowed into the arithmetic.
#
# Genuine value *is* a disagreement, so the gate cannot simply grow teeth --
# that trade was made and reversed on 2026-09-02, and it cost the file its one
# real row. What can change is the weight: a two-sided price is a forecast made
# by somebody with more data than five matches, and a five-observation sample
# should not be allowed to overrule it outright.
#
#     w = n / (n + k)        p_shrunk = w * p_bar + (1 - w) * p_mkt
#
# The same shape as ``analyze.shrunk_centre``, one level up: that one shrinks
# the sample's *centre* toward a market-wide average, this one shrinks the
# sample's *probability* toward this fixture's own posted price. At k = 10 a
# 5-observation sample keeps a third of its own opinion and a 20-observation
# one two thirds.
#
# k is per market family and the two starting values are the handoff note's:
# 10 for football totals, 20 for the tennis markets whose value scales with how
# long the match runs. The tennis number is higher because that is where the
# sample is least likely to be measuring the right quantity -- a best-of-three
# aces sample against a best-of-five tie is the standing example, and the
# 2026-09-03 slate's four worst rows were all in this family.
#
# **These are starting values, not measured ones.** See
# docs/PLAN_EDGE_INTEGRITY_2026-09-03.md for the arm comparison; k is chosen
# from ROI intervals over the slates that have a ``superbet_offer.json``, and
# until that measurement covers more than a handful of slates the numbers here
# are a prior on a prior.
DEFAULT_SHRINK_K = 10.0

_TENNIS_LENGTH_DEPENDENT_SHRINK_K = 20.0
_LENGTH_DEPENDENT_TENNIS_MARKETS = frozenset(
    {
        "total_sets", "total_games", "games_won",
        "aces_total", "aces_for",
        "double_faults_total", "double_faults_for",
        "breaks_total",
    }
)


def shrink_k_for_market(market: str) -> float:
    """How many observations this market's own price is worth."""
    if market in _LENGTH_DEPENDENT_TENNIS_MARKETS:
        return _TENNIS_LENGTH_DEPENDENT_SHRINK_K
    return DEFAULT_SHRINK_K


class BarComponents(NamedTuple):
    """Everything that went into one row's minimum price.

    Printed in full on the coupon row, because a bar the operator cannot
    reconstruct is a number he has to take on trust -- and this one has four
    moving parts where it used to have one.
    """

    probability: float
    # The sample's own claim after the two caps, before the market prior.
    p_bar: float
    # Which cap bound ``p_bar``, or None.
    reason: str | None
    # The book's own devigged probability for this exact outcome, or None when
    # it posted only one side of the line.
    p_market: float | None
    # ``n / (n + k)``: how much of the answer is the sample's. None when there
    # is no market probability to shrink toward.
    weight: float | None


def bar_components(
    row: StatsSheetRow,
    basis: str = "p_low",
    *,
    market_probability: float | None = None,
    shrink_k: float | None = None,
    force_weight: float | None = None,
) -> BarComponents:
    """The bar's input, decomposed.

    ``market_probability`` None leaves the row priced on its sample alone,
    which is the pre-2026-09-03 behaviour and the only honest answer for a
    one-way market: we cannot shrink toward a price we cannot read.

    ``force_weight`` overrides ``n / (n + k)``. It exists for the analyst's own
    verdicts (see ``AnalystVeto.reason_class``): a sample the analyst has
    declared uninformative is worth zero observations, whatever ``n`` says, and
    that is a judgement no formula on ``n`` can express.
    """
    p_bar, reason = bar_input(row, basis)
    if market_probability is None or not 0.0 < market_probability < 1.0:
        return BarComponents(p_bar, p_bar, reason, None, None)

    if force_weight is not None:
        weight = min(1.0, max(0.0, force_weight))
    else:
        k = shrink_k_for_market(row.market) if shrink_k is None else shrink_k
        n = float(row.sample_size)
        weight = 1.0 if k <= 0 else n / (n + k)
    probability = weight * p_bar + (1.0 - weight) * market_probability
    return BarComponents(probability, p_bar, reason, market_probability, weight)


def bar_probability(
    row: StatsSheetRow,
    basis: str = "p_low",
    *,
    market_probability: float | None = None,
    shrink_k: float | None = None,
    force_weight: float | None = None,
) -> float:
    """The probability ``required_odds`` divides into 1.

    An unrecognised basis falls back to ``p_low`` rather than raising: the bar
    must never fail open into a looser threshold because a caller passed a
    typo. A row without ``p_central`` falls back the same way -- the field is
    None on every sheet recorded before 2026-09-02, and those are exactly the
    sheets the ``p_central`` arm exists to paper-trade over; ``p_low`` is the
    tighter bar, so the fallback fails closed, not open.
    """
    return bar_components(
        row,
        basis,
        market_probability=market_probability,
        shrink_k=shrink_k,
        force_weight=force_weight,
    ).probability


def required_odds(
    row: StatsSheetRow,
    tier: str,
    *,
    basis: str = "p_low",
    market_probability: float | None = None,
    shrink_k: float | None = None,
    force_weight: float | None = None,
) -> float:
    """``min_acceptable_odds`` for one row -- the single implementation.

    It had been written out three times even after the 2026-09-02 sweep that
    was supposed to collapse it: here inside ``_priced``, in
    ``coupons.required_price`` and in ``superbet_offer.min_acceptable_odds``.
    All three agreed; nothing made them agree, and one of them decides the
    ranking while another is the number printed for the operator to act on.
    """
    probability = bar_probability(
        row,
        basis,
        market_probability=market_probability,
        shrink_k=shrink_k,
        force_weight=force_weight,
    )
    if probability <= 0:
        return float("inf")
    return round((1.0 / probability) * TIER_MARGIN[tier], 4)

# Markets whose outcomes in a single football match move together. Any two legs
# drawn from here are positively correlated, which is most of what anyone would
# want to put in a same-game multi.
_CORRELATED_FOOTBALL_FAMILY = frozenset(
    {
        "corners_total", "corners_for",
        "cards_points_total", "cards_points_for",
        "cards_total", "cards_for",
        "fouls_total", "fouls_for",
        "shots_total", "shots_for",
        "shots_on_target_total", "shots_on_target_for",
        "goals_total", "goals_for",
        "goals_1h_total", "goals_2h_total",
        "offsides_total", "offsides_for", "red_cards_total",
        "player_total_shots", "player_shots_on_target",
        "player_fouls", "player_was_fouled", "player_cards",
        "player_tackles", "player_assists", "player_offsides",
    }
)

# Markets that count a *part* of what another market counts for the whole
# match: a team's goals are inside the match's goals, a half's inside the full
# ninety. Used by ``_legs_conflict`` -- an OVER on the part and an UNDER on
# its whole can name a slip that cannot be won.
_COMPONENT_OF_TOTAL = {
    "goals_for": "goals_total",
    "goals_1h_total": "goals_total",
    "goals_2h_total": "goals_total",
    "corners_for": "corners_total",
    "cards_points_for": "cards_points_total",
    "cards_for": "cards_total",
    "fouls_for": "fouls_total",
    "shots_for": "shots_total",
    "shots_on_target_for": "shots_on_target_total",
    "offsides_for": "offsides_total",
    "aces_for": "aces_total",
    "double_faults_for": "double_faults_total",
    "games_won": "total_games",
}


# How much more often two legs in one match land *together* than independence
# says they should -- measured, not assumed. See the module docstring for the
# table and the sample.
#
# These are the two numbers that make ``min_acceptable_combined_odds``
# computable at all. The module refused to compute a combined anything for as
# long as the correlation was a story rather than a measurement; once it is a
# measurement it is just a coefficient.
#
# NESTED applies when any pair of legs is arithmetically inside another in the
# same direction -- a team's goals within the match's, a half within the
# ninety. 1.045 over 1,326 such pairs. Applied to the whole slip when any one
# pair qualifies, which overstates the uplift slightly for a four-leg slip with
# one nested pair: that is the cautious direction, since a higher lambda lowers
# the bar.
CORRELATION_LAMBDA_NESTED = 1.045
# FLAT applies to everything else: separate markets in one fixture. 1.006 over
# 10,716 pairs, and 0.999-1.007 in every probability band. It is kept as a
# number rather than rounded to 1.0 so that the file states what was measured.
CORRELATION_LAMBDA_FLAT = 1.006


# --- mechanism families ----------------------------------------------------
#
# One leg per *market* is not one leg per bet. "Cards under 8.5" and "fouls
# under 36.5" in one fixture are two readings of one thing -- how rough the
# referee lets the match get -- and a slip built from both is a single bet
# sold twice, priced as though it were two.
#
# The families are the mechanisms, not the markets:
#
#   discipline  cards and fouls; a foul-heavy match is a card-heavy match, and
#               ``correlation_lambda`` already measures them landing together
#   attacking   corners, shots, shots on target, offsides; all produced by the
#               same territorial pressure
#   scoring     goals, in the match and in either half
#   length      the tennis markets that grow with how long the match runs --
#               sets, games, aces, double faults, breaks
#
# Player props keep their own family per market: two props on two different
# players are two different people's afternoons, and collapsing them would
# refuse the one kind of same-match pair that really is close to independent.
#
# What this replaced was ``one leg per (market, subject)``, which let
# 2026-09-03's Grenal slip take cards *and* fouls, and take
# ``cards_for`` Internacional alongside ``cards_points_total`` -- three legs
# and one mechanism.
MECHANISM_FAMILIES: dict[str, str] = {
    "cards_points_total": "discipline",
    "cards_points_for": "discipline",
    "cards_total": "discipline",
    "cards_for": "discipline",
    "red_cards_total": "discipline",
    "fouls_total": "discipline",
    "fouls_for": "discipline",
    "corners_total": "attacking",
    "corners_for": "attacking",
    "shots_total": "attacking",
    "shots_for": "attacking",
    "shots_on_target_total": "attacking",
    "shots_on_target_for": "attacking",
    "offsides_total": "attacking",
    "offsides_for": "attacking",
    "goals_total": "scoring",
    "goals_for": "scoring",
    "goals_1h_total": "scoring",
    "goals_2h_total": "scoring",
    "total_sets": "length",
    "total_games": "length",
    "games_won": "length",
    "aces_total": "length",
    "aces_for": "length",
    "double_faults_total": "length",
    "double_faults_for": "length",
    "breaks_total": "length",
}


def mechanism_family(row_or_leg) -> str:
    """Which mechanism this leg is a reading of.

    A player prop is its own family per (market, player): two props on two
    different people are the closest thing a same-match slip has to independent
    legs, and folding them together would delete the pairs worth having.
    """
    market = row_or_leg.market
    family = MECHANISM_FAMILIES.get(market)
    if family is not None:
        return family
    return f"{market}:{getattr(row_or_leg, 'player_name', None) or ''}"


def implies(
    first: tuple[str, float, str], second: tuple[str, float, str]
) -> bool:
    """Whether ``first`` makes ``second`` nearly certain.

    Two shapes, and both put a leg on a slip that is being paid for twice.

    **The same market at two rungs.** "Under 3.5" implies "under 4.5"; "over
    5.5" implies "over 4.5". Superbet will not accept both anyway, and
    ``duplicate_market`` already refuses them -- this states the arithmetic so
    the nesting rule below can share it.

    **A part inside its whole, same direction.** "Internacional under 3.5
    cards" and "match under 8.5 cards" are not two bets: the first is most of
    the second. On 2026-09-03 the Grenal slip carried Internacional <=3 and
    Grêmio <=5 alongside the match total <=8, which is one bet written three
    times and priced as three.

    Deliberately weaker than ``_legs_conflict``: that one refuses pairs that
    cannot both happen, this one refuses pairs that nearly always do.
    """
    market_a, line_a, direction_a = first
    market_b, line_b, direction_b = second
    if direction_a != direction_b:
        return False
    if market_a == market_b:
        return (
            line_a <= line_b if direction_a == "UNDER" else line_a >= line_b
        )
    # A part inside its whole. Only the direction in which the implication runs
    # -- a team being under its line says something about the match being under
    # its own only when the team's line is at least as large as... nothing
    # arithmetically guaranteed, in fact. What is true is that the two are
    # readings of one quantity, and the family rule above already refuses the
    # pair; this catches the case where they are the *same* quantity split.
    return _COMPONENT_OF_TOTAL.get(market_a) == market_b or (
        _COMPONENT_OF_TOTAL.get(market_b) == market_a
    )


def _is_nested(market_a: str, market_b: str) -> bool:
    """Whether one market counts a part of what the other counts.

    Both directions, plus the sibling case -- two halves of the same match are
    each inside the same total and move together for the same reason.
    """
    whole_a = _COMPONENT_OF_TOTAL.get(market_a)
    whole_b = _COMPONENT_OF_TOTAL.get(market_b)
    if whole_a == market_b or whole_b == market_a:
        return True
    return whole_a is not None and whole_a == whole_b


def correlation_lambda(legs: list["BetBuilderLeg"]) -> float:
    """The measured joint-hit uplift for this particular set of legs.

    ``CORRELATION_LAMBDA_NESTED`` as soon as *any* same-direction nested pair is
    present, ``CORRELATION_LAMBDA_FLAT`` otherwise. Opposite-direction nested
    pairs measured 0.978 -- below independence -- and are not credited: they are
    already handled by ``_legs_conflict``, which refuses the ones that cannot
    both win, and crediting an uplift below 1.0 would lower a bar on the
    strength of a negative result.
    """
    for i, a in enumerate(legs):
        for b in legs[i + 1:]:
            if a.direction == b.direction and _is_nested(a.market, b.market):
                return CORRELATION_LAMBDA_NESTED
    return CORRELATION_LAMBDA_FLAT


def _legs_conflict(
    a: tuple[str, float, str], b: tuple[str, float, str]
) -> bool:
    """Whether two ``(market, line, direction)`` legs cannot both win.

    One shape today: OVER on a component and UNDER on its whole. The part
    cannot exceed the whole, so "Valencia goals OVER 2.5" and "goals_total
    UNDER 2.5" is not a correlated pair, it is a slip that loses by
    arithmetic -- and it was drafted, labelled positively correlated, because
    the per-team and match samples are computed from different histories and
    can clear ``min_p_low`` while contradicting each other. Integer lines
    count the push as not-a-win: a slip leg that can at best push has not won.
    """
    for over, under in ((a, b), (b, a)):
        o_market, o_line, o_direction = over
        u_market, u_line, u_direction = under
        if o_direction != "OVER" or u_direction != "UNDER":
            continue
        if _COMPONENT_OF_TOTAL.get(o_market) != u_market:
            continue
        # Smallest count that wins the OVER vs largest that wins the UNDER.
        if math.floor(o_line) + 1 > math.ceil(u_line) - 1:
            return True
    return False


# The tennis equivalent, and it had no equivalent until 2026-09-01. Every one of
# these grows with match length, so two of them in one slip are close to the
# same bet twice: a straight-sets win settles "under 3.5 sets", "under 34.5
# games", "under 24.5 aces" and "under 12.5 double faults" together.
_CORRELATED_TENNIS_FAMILY = frozenset(
    {
        "total_sets", "total_games", "games_won",
        "aces_total", "aces_for",
        "double_faults_total", "double_faults_for",
        "breaks_total",
    }
)


class BetBuilderLeg(StrictBaseModel):
    """One leg, with the price it must beat on the operator's own screen."""

    event_id: str
    market: str
    line: float
    direction: Literal["OVER", "UNDER"]
    team_name: str | None = None
    player_name: str | None = None
    tier: Tier
    p_low: float
    # The sheet's own centre, carried so a slip's joint probability can be
    # built from the same basis its legs' bars are. Before 2026-09-03 only
    # ``p_low`` reached a leg, and multiplying four lower bounds compounds a
    # +22pp per-leg understatement into a bar no slip could ever clear -- the
    # 2026-09-03 file wanted 2.6-3.8 from slips whose legs multiplied to
    # 1.07-1.81. None on sheets recorded before 2026-09-02.
    p_central: float | None = None
    hit_rate: float
    sample_size: int
    fair_odds: float
    min_acceptable_odds: float
    # Copied from ``row.market_signal`` when the MARKET_CONTEXT stage ran and
    # reached a verdict on this exact row. Reported, never priced with: it does
    # not enter fair_odds or min_acceptable_odds, both of which come from p_low
    # and nothing else.
    market_verdict: str | None = None
    # The operator's own book (SUPERBET, 2026-08-31). ``superbet_availability``
    # is the field that matters: a leg whose line is not on Superbet's ladder
    # cannot go in the slip at any price, and before this existed it went in
    # looking exactly like a leg that could.
    superbet_availability: str | None = None
    superbet_price: float | None = None
    superbet_nearest_line: float | None = None
    caveats: list[str] = Field(default_factory=list)


class BetBuilderDraft(StrictBaseModel):
    """A slip to hand-assemble, and every reason to be careful with it."""

    event_id: str
    legs: list[BetBuilderLeg] = Field(default_factory=list)
    # Still typed None, and for the reason that survived the measurement: no
    # endpoint serves Superbet's Bet Builder price and nothing here can derive
    # it, because the book's own combination margin is not observable from the
    # leg prices. The bar below is what this module can honestly produce.
    combined_price: None = None
    # What every leg landing is worth, on the same basis as the legs' own bars,
    # corrected by the measured joint-hit uplift. None when any leg lacks the
    # basis probability -- an incomplete product is not a probability, and
    # silently dropping a leg from it would understate the bar.
    joint_probability: float | None = None
    # Which of the two measured lambdas was applied, so the number is auditable
    # from the artifact rather than only from this file.
    correlation_lambda: float | None = None
    # The minimum combined price that justifies the slip: margin / joint.
    # Compare it against the Bet Builder price on the operator's screen. This
    # is a threshold, never a prediction of what that screen will say.
    min_acceptable_combined_odds: float | None = None
    # What these same legs would pay placed as separate singles -- the product
    # of their Superbet prices. Not the slip's price and never labelled as one:
    # it is the alternative the slip is competing against, and the gap between
    # it and the screen's Bet Builder price is what the book charges to combine
    # them. None unless every leg is priced.
    legs_priced_separately: float | None = None
    correlation_risk: Literal["HIGH", "LOW", "NOT_APPLICABLE"] = "NOT_APPLICABLE"
    correlation_note: str = ""
    excluded: dict[str, int] = Field(default_factory=dict)
    # docs/SUPERBET_BET_BUILDER_METHOD_v3.md §44, computed. None on a draft
    # with fewer than two legs, which is not a builder.
    builder_score: float | None = None
    builder_score_parts: dict[str, float] = Field(default_factory=dict)
    # Set when §44 refused the slip. The legs stay on the draft so the refusal
    # is auditable; nothing downstream reads a draft with this set.
    builder_score_refused: bool = False


# --- the builder score (docs/SUPERBET_BET_BUILDER_METHOD_v3.md §44) --------
#
# The method document gives the weights and names the five terms; it does not
# define them numerically. What follows is this repo's definition of each, and
# the definitions are the part to argue with:
#
#   weakest leg   the smallest of the legs' bar probabilities. §44's first and
#                 largest term, for the same reason ``weakest_leg_p_low`` ranks
#                 slips: a slip settles on every leg, so it is worth the leg you
#                 are least sure about.
#   mean leg      the arithmetic mean of the same probabilities.
#   correlation   1.0 when ``correlation_risk`` is LOW or NOT_APPLICABLE, 0.4
#                 when it is HIGH. A score, so higher is better and more
#                 correlated is worse.
#   robustness    distinct mechanism families over legs. One mechanism means
#                 every leg wins or loses together, whatever the markets are
#                 called. Always 1.0 now that ``draft_legs`` refuses a second
#                 leg from one family -- kept because ``builder_score`` is
#                 callable on legs somebody else assembled.
#   data quality  the mean over legs of ``min(1, n/12)``, docked to 0.5 for any
#                 leg two providers actively contradict. Twelve because that is
#                 comfortably past the n>=8 this pipeline already treats as a
#                 settled sample.
#
# The document's three penalties: the contradiction penalty is not a penalty
# here but a refusal (``jointly_impossible`` and ``nested_leg`` remove the leg
# before it reaches a slip, which is §40 enforced rather than scored), and the
# source-conflict penalty is folded into ``data quality`` above. The tail-risk
# penalty is not implemented -- it needs a scenario model this pipeline does
# not have, and inventing one to fill a term would be worse than a term short.
# So the score is capped by what is missing, never inflated by it.
#
# 0.60 is the method document's own refusal threshold. On the five terms above
# it is roughly "every leg near 0.7, uncorrelated, well sampled" -- which is
# what a slip worth placing looks like.
BUILDER_SCORE_MIN = 0.60

_BUILDER_WEIGHTS = {
    "weakest_leg": 0.40,
    "mean_leg": 0.25,
    "correlation": 0.15,
    "robustness": 0.10,
    "data_quality": 0.10,
}


def builder_score(
    legs: list[BetBuilderLeg],
    *,
    correlation_risk: str = "NOT_APPLICABLE",
    bar_basis: str = "p_low",
) -> tuple[float | None, dict[str, float]]:
    """``(score, its five parts)``. ``(None, {})`` on fewer than two legs."""
    if len(legs) < 2:
        return None, {}

    def leg_probability(leg: BetBuilderLeg) -> float:
        if bar_basis == "p_central" and leg.p_central is not None:
            return leg.p_central
        return leg.p_low

    probabilities = [leg_probability(leg) for leg in legs]
    families = {mechanism_family(leg) for leg in legs}
    quality = []
    for leg in legs:
        own = min(1.0, leg.sample_size / 12.0)
        if any("providers disagree" in note for note in leg.caveats):
            own = min(own, 0.5)
        quality.append(own)

    parts = {
        "weakest_leg": min(probabilities),
        "mean_leg": sum(probabilities) / len(probabilities),
        "correlation": 0.4 if correlation_risk == "HIGH" else 1.0,
        "robustness": len(families) / len(legs),
        "data_quality": sum(quality) / len(quality),
    }
    score = sum(_BUILDER_WEIGHTS[name] * value for name, value in parts.items())
    return round(score, 4), {name: round(value, 4) for name, value in parts.items()}


def tier_for_row(row: StatsSheetRow) -> Tier:
    """The evidence tier from the analysts' table (``.claude/skills/bet-analysis-core/SKILL.md``), plus its two ceilings.

    | CALL | n>=8, and either the primary's sample is complete or a second provider agrees |
    | LEAN | n>=8 incomplete and uncorroborated, or n>=5 AGREE, or n 5-7 uncorroborated |
    | WEAK | n 3-4                |
    | DROP | data_quality BLOCKED or n<3 |

    **CALL used to require AGREE, and that requirement was measured and
    removed on 2026-09-02.** It had a consequence nobody chose: for football,
    AGREE means espn-football also knew the fixture, so the top tier was
    reachable only inside one corroborator's league map -- and that corroborator
    serves 6 of bzzoiro's 55 metrics and agrees with it exactly on 92-98% of
    the (match, metric) points where both report. It was not a second
    measurement; it was a second transcription, used as a gate.

    Settled against real results over five slates (5,174 rows from 312
    fixtures, p_low >= 0.50), corroboration predicts nothing:

        AGREE - SINGLE_SOURCE = +0.4pp, 95% CI [-2.3, +3.4] (clustered by
        fixture; 37.6% of resamples negative).

    What replaces it is the question AGREE was standing in for -- is this
    sample actually complete -- answered by the provider of record instead of
    by a third party's coverage. ``data_quality == "READY"`` means the primary
    served at least five matches a side on all three priority metrics
    (enrich._compute_readiness). Same measurement, same rows:

        n>=8 + READY, not DISAGREE   2,507 rows over 172 fixtures, 82.5%
        n>=8 + AGREE (the old rule)  1,184 rows over 193 fixtures, 82.4%
        difference +0.1pp, 95% CI [-2.4, +2.5]

    Twice the supply at the same hit rate, and supply is this pipeline's
    binding constraint. The rows the new rule leaves at LEAN -- n>=8 with an
    incomplete primary sample -- win 81.1%, so the discrimination runs the
    right way round.

    Restricted to sports with a primary provider, because that is where it was
    measured: the backtest settles football only (tennis markets settle from an
    endpoint it does not read), and for tennis READY still means "two providers
    agreed", which is the old condition under a different name.

    Ceilings, both structural rather than about the numbers: a row two providers
    actively contradict can never be CALL, and a player prop drawn from a
    predicted XI is capped at LEAN because the sample is fine and the premise --
    that he starts -- is a guess.

    DISAGREE keeps its demotion on weaker evidence than the above, deliberately:
    -6.0pp against SINGLE_SOURCE, 95% CI [-17.5, +4.3], 86% of resamples
    negative. That is a lean, not a proof, and it is the cautious direction.

    LEAN's third clause is the gap in ``bet-analyst.md``'s table, resolved on
    evidence 2026-09-02. An ``n`` of 5-7 that nothing corroborates matches none
    of the table's stated conditions -- above WEAK's "n 3-4", below both of
    LEAN's -- and this function had always answered LEAN by accident of how the
    branches fell.

    It was tightened to WEAK, and then **reverted after backtesting it**, which
    is the only reason this docstring is long. The case for tightening was that
    the three largest losses of 2026-09-01 were all n=5 SINGLE_SOURCE
    (Sheffield United corners, Preston shots on target, Birmingham shots). The
    case against is the category's own record: settled against real results
    over four slates (2026-08-28 to 2026-09-01), the rows the tightening
    removes won **84.4% of 77 settled bets against a claimed p_low of 0.592**,
    and at each row's own required price they would have returned +56.9% flat.
    Three losses in a category that wins 84% is what 84% looks like -- the
    expected number of losses in 77 such rows is twelve.

    Whole-file effect of the tightening, same measurement: hit rate 85.7% ->
    85.9%, and 81.4% -> 81.8% in the 0.50-0.70 band where rows are actually
    priced. It removed 34 candidate rows to move the hit rate by four tenths of
    a point, and supply is this pipeline's binding constraint, not precision.

    What actually removes those three rows is the arithmetic, not the tier:
    ``shrunk_centre`` puts all three below ``MIN_SINGLE_P_LOW`` on its own
    (0.263, 0.175, 0.320 against a floor of 0.50), so they never become
    candidates. See scripts/simple/backtest_slate.py, and
    ``test_the_thin_uncorroborated_category_is_not_a_losing_one``.
    """
    if row.data_quality == "BLOCKED" or row.sample_size < 3:
        return "DROP"
    if row.sample_size < 5:
        return "WEAK"

    corroborated = row.cross_provider_agreement == "AGREE"
    # The primary provider served a complete sample for this fixture. Only
    # meaningful where there *is* a primary: for tennis, READY is still the old
    # two-provider condition and this reduces to ``corroborated``.
    complete = row.data_quality == "READY" and row.sport in PRIMARY_PROVIDER_BY_SPORT
    if row.sample_size >= 8 and (complete or corroborated):
        tier: Tier = "CALL"
    elif row.sample_size >= 8 or corroborated:
        tier = "LEAN"
    else:
        # n of 5-7 with nothing corroborating it: LEAN, on purpose and on
        # evidence rather than by accident. Backtested against real results
        # this category wins 84.4% of 77 settled bets on a claimed 0.592 --
        # see the docstring. The Wilson bound already prices the thinness of
        # five trials; refusing the row on top of that is charging twice for
        # it.
        tier = "LEAN"

    # SINGLE_SOURCE no longer demotes: see the docstring. A row nothing
    # corroborates is not a worse row, it is a row in a competition the
    # corroborator does not cover.
    if row.cross_provider_agreement == "DISAGREE":
        tier = "LEAN" if tier == "CALL" else tier
    if row.player_id and (row.lineup_status or "") != "confirmed":
        tier = "LEAN" if tier == "CALL" else tier
    # Context (referee, injuries, form, derby, weather) may argue a row down,
    # never up and never into p_low itself -- see contracts.ContextFlag. One
    # step regardless of how many flags fired: a fixture is not worse for
    # having two reasons to doubt it than for having one.
    if any(flag.direction == "ARGUES_AGAINST" for flag in row.context_flags):
        tier = step_tier_down(tier)
    # Structural ceilings ANALYZE attached: see
    # ``StatsSheetRow.lean_ceiling_reasons``. Applied last and as a cap, so a
    # fixture with three of them is not three tiers worse than one with one.
    if row.lean_ceiling_reasons:
        tier = cap_tier_at_lean(tier)
    return tier


def _caveats(row: StatsSheetRow) -> list[str]:
    notes: list[str] = []
    if row.cross_provider_agreement == "SINGLE_SOURCE":
        notes.append("single-source: nothing corroborates this row")
    if row.cross_provider_agreement == "PARTIAL_AGREE":
        notes.append(
            f"partially corroborated: {row.corroborated_matches}/{row.sample_size} "
            "matches seen by a second provider"
        )
    if row.cross_provider_agreement == "DISAGREE":
        notes.append("providers disagree and were never averaged")
    if row.player_id and (row.lineup_status or "") != "confirmed":
        notes.append(
            f"lineup {row.lineup_status or 'unknown'}: the sample is real, the "
            "premise that he starts is a guess"
        )
    if row.sample_size < 8:
        notes.append(f"thin sample (n={row.sample_size})")
    return notes


def draft_legs(
    stats_sheet: StatsSheetV1,
    event_id: str,
    *,
    max_legs: int = 4,
    vetoes: VetoIndex | None = None,
    min_p_low: float = 0.0,
    price_for: Callable[[StatsSheetRow], tuple[str | None, float | None]] | None = None,
    require_value: bool = False,
    bar_basis: str = "p_central",
) -> BetBuilderDraft:
    """Draft up to ``max_legs`` legs for one fixture, best-evidenced first.

    Every gate a single passes, a leg passes too. That sentence is the whole
    change of 2026-09-01, and it is worth stating as an invariant because the
    file it fixes looked correct: the singles list had vetoes, a ``min_p_low``
    floor, a price check and a trivial-under demotion, the Bet Builder had none
    of them, and nothing in the artifact said so. Thirty legs went out that day;
    twenty-eight were priced below their own minimum or had no price at all, and
    the two that cleared were rows the analyst had explicitly struck.

    Only CALL and LEAN rows are eligible. A WEAK row is three or four
    observations, and ``bet-analyst.md`` already refuses to put a minimum price
    on one -- a threshold computed off four matches reads as precision that is
    not there, and putting it in a multi compounds that against three other legs.

    ``vetoes`` is the same ``VetoIndex`` the singles loop resolves against, so
    a struck row cannot reappear here wearing a different hat. ``min_p_low``
    defaults to 0.0 rather than to the singles threshold: a caller that has not
    been taught to pass one keeps the behaviour it had, and ``build_coupons``
    passes its own.

    ``price_for`` answers "what is this on the operator's screen", returning
    ``(availability, price)``. With ``require_value`` it also decides
    eligibility: a leg whose price is below ``min_acceptable_odds``, or which
    has no price at all, is not a leg. Without it the price is annotated and
    reported exactly as before -- the operator sees the number and judges it.

    Ranked by ``p_low`` within a demotion class: a trivial low-line UNDER
    (``is_trivial_under``) never leads a slip, because 20/20 on "under 4.5
    first-half goals" is a fact about football rather than a read on this
    fixture, and it is priced at 1.001 for that reason.
    """
    rows = [row for row in stats_sheet.rows if row.event_id == event_id]
    excluded: dict[str, int] = {}
    eligible: list[tuple[StatsSheetRow, Tier]] = []

    def exclude(reason: str) -> None:
        excluded[reason] = excluded.get(reason, 0) + 1

    for row in rows:
        tier = tier_for_row(row)
        veto = vetoes.for_row(row) if vetoes is not None else None
        # Before the tier gate, exactly as in the singles loop: a DOWNGRADE that
        # reaches WEAK must exclude the leg, and one that only reaches LEAN must
        # raise min_acceptable_odds from the CALL margin to the LEAN margin.
        if veto is not None and veto.action == "DOWNGRADE":
            tier = step_tier_down(tier)
        if tier in ("WEAK", "DROP"):
            exclude(f"tier_{tier.lower()}")
            continue
        if veto is not None and veto.action == "VETO":
            exclude("analyst_veto")
            continue
        if row.p_low <= 0:
            # 1/0 is not a price, and a row whose lower bound is zero is making
            # no claim to put on a slip.
            exclude("p_low_not_positive")
            continue
        if row.p_low < min_p_low:
            exclude("p_low_below_threshold")
            continue
        eligible.append((row, tier))

    # Price every eligible row once, before ranking. Whether a leg beats its own
    # threshold is a property of the leg, so it has to be known to rank it -- and
    # pricing here rather than inside the loop below means ``price_for`` is
    # called once per row instead of twice.
    def _priced(row: StatsSheetRow, tier: Tier) -> tuple[float, str | None, float | None]:
        minimum = required_odds(row, tier, basis=bar_basis)
        if price_for is None:
            return minimum, None, None
        availability, price = price_for(row)
        return minimum, availability, price

    priced: dict[int, tuple[float, str | None, float | None]] = {
        id(row): _priced(row, tier) for row, tier in eligible
    }

    def _surplus(pair: tuple[StatsSheetRow, Tier]) -> float | None:
        """How far this leg's price clears its own threshold, or None."""
        minimum, availability, price = priced[id(pair[0])]
        if availability != "OFFERED" or price is None or price < minimum:
            return None
        return round(price - minimum, 4)

    # Value first, exactly as the singles list is ranked in ``coupons.py``: a leg
    # the operator's own book prices at or above its ``min_acceptable_odds``
    # outranks one it does not, however high the second leg's ``p_low``.
    #
    # Ranking on ``-p_low`` alone filled slips with near-tautologies and hid the
    # legs worth taking. Measured 2026-09-01: all eight slips shipped 28 legs and
    # **none** beat its threshold, because "under 3.5 first-half goals" at
    # p_low 0.72 is priced 1.01 and therefore outranked
    # ``corners_for 4.5 UNDER`` at p_low 0.57 priced 2.70 -- a +0.75 surplus,
    # dropped as ``over_max_legs``. A leg that cannot be worth its price is not
    # better evidence than one that is; it is a more certain way to be paid
    # nothing.
    def _price_ratio(pair: tuple[StatsSheetRow, Tier]) -> float | None:
        """How close this leg's price comes to its own bar, as a ratio.

        ``>= 1.0`` is exactly ``_surplus``'s condition, restated so the same
        quantity can also rank the legs that miss it. Scale-free on purpose: a
        surplus of -0.30 means something different against a bar of 1.25 than
        against one of 2.05, and the second group is where every rejected leg
        lives.
        """
        minimum, availability, price = priced[id(pair[0])]
        if availability != "OFFERED" or price is None or minimum <= 0:
            return None
        return price / minimum

    value = [pair for pair in eligible if _surplus(pair) is not None]
    value_ids = {id(pair[0]) for pair in value}
    rest = [pair for pair in eligible if id(pair[0]) not in value_ids]
    value.sort(
        key=lambda pair: (
            -(_surplus(pair) or 0.0), -pair[0].p_low, pair[0].market, pair[0].line
        )
    )
    # **The legs that miss the bar are ranked by how far they miss it, not by
    # p_low.** Ranking them on p_low was the same defect the ``value`` group
    # above was fixed for on 2026-09-01, left standing in the group that
    # actually fills the slips: on a normal day nothing clears its bar, every
    # leg lands here, and p_low then sorts a 1.008-priced near-tautology above
    # every real read in the fixture.
    #
    # It is not a theoretical ordering. The 2026-09-03 file shipped eight
    # slips, six of them built entirely from legs priced 1.002-1.16 whose
    # products came to 1.07-1.34 -- while the same fixtures had legs on the
    # singles list at 1.28 and 1.23. Hibernian-Hearts drafted four legs
    # multiplying to 1.07 and left ``corners_total 7.5 OVER`` at 1.28 and
    # ``goals_total 1.5 OVER`` at 1.23 out of the slip. A slip that cannot pay
    # is not a safer slip.
    #
    # Legs with no price keep the old key and sort after the priced ones: an
    # unpriced leg has no ratio, and guessing one would rank it on nothing. The
    # trivial-UNDER demotion stays for exactly that group, which is the only
    # one that can still be led by a tautology.
    rest.sort(
        key=lambda pair: (
            _price_ratio(pair) is None,
            -(_price_ratio(pair) or 0.0),
            is_trivial_under(pair[0]),
            -pair[0].p_low,
            pair[0].market,
            pair[0].line,
        )
    )
    eligible = value + rest

    # One leg per market, and since 2026-09-03 one leg per *mechanism*: two
    # lines of the same market in one slip are the same read twice, and two
    # markets driven by the same thing are the same bet sold twice. See
    # MECHANISM_FAMILIES.
    legs: list[BetBuilderLeg] = []
    markets_used: set[str] = set()
    families_used: set[str] = set()
    for row, tier in eligible:
        if len(legs) >= max_legs:
            exclude("over_max_legs")
            continue
        key = f"{row.market}:{row.team_name or ''}:{row.player_name or ''}"
        if key in markets_used:
            exclude("duplicate_market")
            continue
        family = mechanism_family(row)
        if any(
            _legs_conflict(
                (row.market, row.line, row.direction),
                (leg.market, leg.line, leg.direction),
            )
            for leg in legs
        ):
            exclude("jointly_impossible")
            continue
        if any(
            implies((row.market, row.line, row.direction),
                    (leg.market, leg.line, leg.direction))
            or implies((leg.market, leg.line, leg.direction),
                       (row.market, row.line, row.direction))
            for leg in legs
        ):
            exclude("nested_leg")
            continue
        # Last of the three structural refusals, so the sharpest diagnosis
        # wins: a pair that cannot both happen is reported as impossible, a
        # pair where one implies the other as nested, and only what is left
        # over as two readings of one mechanism.
        if family in families_used:
            exclude("duplicate_mechanism_family")
            continue
        fair_odds = 1.0 / row.p_low
        minimum, availability, price = priced[id(row)]
        # Availability is not a value judgement and is not optional. A slip
        # is placed as one unit, so a leg the book does not carry does not
        # make the slip worse -- it makes the slip impossible. Five of the
        # eight slips shipped on 2026-09-01 contained a leg on a line
        # Superbet does not list, and each was presented as a coupon to go
        # and place. Unlike a single, there is no honest way to print that.
        if price_for is not None and availability != "OFFERED":
            exclude(f"superbet_{(availability or 'unknown').lower()}")
            continue
        if require_value and price is not None and price < minimum:
            # Below the bar but on the screen: a real answer about a real
            # market, and the operator may still want to see it. Only dropped
            # when the caller asked for a file of nothing but takeable bets.
            exclude("superbet_priced_below_threshold")
            continue
        # **A leg only joins a slip if it makes the slip better.**
        #
        # This is parlay arithmetic and not a preference. Adding a leg
        # multiplies the slip's payout by ``price`` and its probability by
        # ``p``, so it multiplies expected value by ``price x p``. Below fair
        # odds -- ``price < 1/p`` -- that product is less than one and the leg
        # *subtracts* from a slip it appears to strengthen.
        #
        # ``max_legs`` used to be a quota that got filled. On 2026-09-03 the
        # Diriyah-Al-Qadsiah slip took ``player_total_shots 0.5 OVER`` at 1.04
        # against fair odds of 1.15 as its fourth leg, lowering the slip's
        # expectation by 10% in exchange for looking like a fuller coupon.
        # Three legs that each pay for themselves beat four that do not.
        #
        # Against fair odds, with no tier margin in it, deliberately: the
        # margin is charged once at the slip level in
        # ``min_acceptable_combined_odds``. Charging it per leg as well would
        # compound the same conservatism four times, which is the mistake this
        # file has already made once with ``p_low``.
        if price is not None:
            fair = 1.0 / bar_probability(row, basis=bar_basis)
            if price <= fair:
                exclude("leg_would_lower_slip_value")
                continue

        markets_used.add(key)
        families_used.add(family)
        legs.append(
            BetBuilderLeg(
                event_id=row.event_id,
                market=row.market,
                line=row.line,
                direction=row.direction,
                team_name=row.team_name,
                player_name=row.player_name,
                tier=tier,
                p_low=row.p_low,
                p_central=row.p_central,
                hit_rate=row.hit_rate,
                sample_size=row.sample_size,
                fair_odds=round(fair_odds, 4),
                min_acceptable_odds=minimum,
                market_verdict=row.market_signal.verdict if row.market_signal else None,
                superbet_availability=availability,
                superbet_price=price,
                caveats=_caveats(row),
            )
        )

    correlated = [leg for leg in legs if leg.market in _CORRELATED_FOOTBALL_FAMILY]
    tennis_length = [leg for leg in legs if leg.market in _CORRELATED_TENNIS_FAMILY]
    if len(correlated) >= 2:
        risk = "HIGH"
        note = (
            f"{len(correlated)} of {len(legs)} legs are from the correlated "
            "football family (corners/cards/fouls/shots/goals in one match): a "
            "foul-heavy match is a card-heavy match, so these land together far "
            "more often than independence implies. The combination is therefore "
            "less unlikely than the legs suggest -- and Superbet's own Bet "
            "Builder price already reflects that. Never multiply the legs."
        )
    elif len(tennis_length) >= 2:
        # Added 2026-09-01. "Under 34.5 games" and "under 3.5 sets" were shipped
        # as a LOW-correlation pair, which is close to the most correlated pair
        # tennis has: a match that ends in three sets is a short match almost by
        # definition. There was no tennis family here at all, so every tennis
        # slip fell through to the "not from the same correlated family" branch.
        risk = "HIGH"
        note = (
            f"{len(tennis_length)} of {len(legs)} legs measure the same thing -- "
            "how long the match runs. Sets, games, aces and double faults all "
            "grow together, so a short match settles every one of these UNDERs "
            "at once and a long one settles none. Superbet's own price reflects "
            "that; the legs read as independent and are not. Never multiply them."
        )
    elif len(legs) >= 2:
        risk = "LOW"
        note = "legs are not from the same correlated family, but same-match legs are never fully independent"
    else:
        risk = "NOT_APPLICABLE"
        note = ""

    # --- the slip's own bar -------------------------------------------
    #
    # ``margin / (product of leg probabilities x measured lambda)``. Every term
    # is the same one the legs' own bars use, so a slip and its legs can never
    # disagree about what basis they were priced on.
    #
    # The margin is the *weakest* leg's, not the product of the legs' margins.
    # Compounding them charges for the same conservatism once per leg -- a
    # four-leg slip of LEANs would carry 1.10^4 = 1.46 of margin, which is a
    # bar no book pays -- and the margin exists to cover a calibration error in
    # the estimator, which is a property of the estimator and not of how many
    # times it was called. The weakest leg's tier is the slip's tier for the
    # same reason ``weakest_leg_p_low`` ranks it.
    joint: float | None = None
    lam: float | None = None
    combined_bar: float | None = None
    separately: float | None = None
    if len(legs) >= 2:
        lam = correlation_lambda(legs)
        basis_ps = [
            leg.p_central if (bar_basis == "p_central" and leg.p_central is not None)
            else leg.p_low
            for leg in legs
        ]
        if all(p > 0 for p in basis_ps):
            product = 1.0
            for value in basis_ps:
                product *= value
            # Capped at the weakest leg. A positive lambda may not push the
            # joint above the probability of the single least likely leg: the
            # slip cannot win more often than its weakest leg does, and an
            # uplift that says otherwise is arithmetic, not evidence.
            joint = min(product * lam, min(basis_ps))
            margin = max(TIER_MARGIN[leg.tier] for leg in legs)
            combined_bar = round(margin / joint, 4)
            joint = round(joint, 6)
        prices = [leg.superbet_price for leg in legs]
        if all(price is not None for price in prices):
            product = 1.0
            for price in prices:
                product *= price  # type: ignore[operator]
            separately = round(product, 4)

    # §44, last: it reads the finished slip, including its correlation verdict.
    score, parts = builder_score(legs, correlation_risk=risk, bar_basis=bar_basis)
    refused = score is not None and score < BUILDER_SCORE_MIN
    if refused:
        excluded["builder_score_below_minimum"] = 1

    return BetBuilderDraft(
        event_id=event_id,
        legs=legs,
        joint_probability=joint,
        correlation_lambda=lam,
        min_acceptable_combined_odds=combined_bar,
        legs_priced_separately=separately,
        correlation_risk=risk,  # type: ignore[arg-type]
        correlation_note=note,
        excluded=dict(sorted(excluded.items())),
        builder_score=score,
        builder_score_parts=parts,
        builder_score_refused=refused,
    )
