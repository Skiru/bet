"""Rank legs by how often they actually happen, not by how they price.

The coupon asks "is this worth its price". Measured on the 6,187 rows that
carry a real Superbet price, the model loses that argument to the price itself
(Brier 0.2067 against 0.1845), and ranking by surplus actively selects the
rows where it loses worst: past a model-minus-price gap of +0.10 the realised
rate falls BELOW a coin flip while the model claims 0.61 and upward.

This module asks the other question. Over 1,868,474 settled rows the model is
calibrated to within 0.3 pp everywhere up to about 0.90 — when it says 0.88 it
means 0.88. An operator who has decided to accept a shaded price is asking
exactly that, and it is a question the model can answer.

Two things this must never do, because both are how a confidence view turns
back into the coupon it replaced:

  - quote its own point estimate. Every number here is the LOWER bound of the
    measured realised rate, so a thin bucket reads as less confident, not as
    more precise.
  - claim certainty. The fitted curve tops out at 0.9202: the buckets
    0.900-0.925 and 0.925-0.950 both realise 0.9083, which is the model saying
    it has run out of resolution. A leg presented at 0.98 would be a lie of
    about seven points.
"""

from __future__ import annotations

import json
import statistics
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_CALIBRATION = Path("config/sofa_confidence_calibration.json")

# The measured disagreement ceiling. On the 6,187 rows carrying a real price,
# grouped by how far the model sat ABOVE the devigged market:
#
#     model - price     n     model says   realised
#     +0.00-0.05      1114      0.546       0.514
#     +0.05-0.10       780      0.595       0.530
#     +0.10-0.15       441      0.609       0.444
#     +0.20-0.30       255      0.677       0.400
#     +0.30 and up     328      0.800       0.451
#
# Past +0.10 the realised rate drops BELOW a coin flip while the model's claim
# keeps climbing. A leg where we say 0.81 and the book says 0.05 is not a
# shaded price being offered to us, it is our own error being offered to us.
# Accepting the book's shading and ignoring this are different decisions.
MAX_DISAGREEMENT = 0.10

# Markets that are a FUNCTION of two sides rather than a count of one thing.
# They carry 2-252 settled rows each — both_over_shots has 26, both_over_fouls
# 18 — so no market-specific curve can be fitted, and the pooled curve they
# would otherwise fall back to was measured on 1.87M single-quantity counts.
# Nothing in the artifacts can check them either: no per-side sample reaches a
# joint, which is why every one of them also carries ONE_SIDED_LADDER and
# NO_MARKET_MARGINAL on the sheet. A confidence view exists to say how often a
# thing happens; for these the honest answer is that we have not measured it.
DERIVED_PREFIXES = ("both_over_", "handicap_", "most_")


def is_derived(market: str) -> bool:
    """True for a joint/comparative market. See DERIVED_PREFIXES."""
    return market.startswith(DERIVED_PREFIXES)

# Independence holds ACROSS quantities and fails WITHIN one, and the
# difference decides whether multiplying leg probabilities is arithmetic or
# fiction. Measured on 608 specific rung pairs out of the settled cache —
# conditioned on the exact (market, line, direction), because pooling OVER and
# UNDER across lines forces lambda to 1.000 by symmetry and hides everything:
#
#     goals_for   x goals_total      84 pairs   median lambda 2.165 (max 8.37)
#     fouls_for   x fouls_total      71 pairs   median lambda 1.455
#     corners_for x corners_total    72 pairs   median lambda 1.377
#     corners_total x goals_for      27 pairs   median lambda 1.017
#     corners_for x fouls_for        78 pairs   median lambda 0.964
#     corners_total x fouls_total    79 pairs   median lambda 0.964
#
# A team's goals are part of the total goals; its corners are part of the
# total corners. Those are one quantity counted twice, and a builder that
# multiplies them tells the operator he holds four independent legs when he
# holds two. Across different quantities lambda sits in 0.95-1.02 and the
# product is right.
#
# So a builder takes at most one leg per QUANTITY family, not per market.
QUANTITY_FAMILIES: dict[str, str] = {}
for _family, _prefixes in {
    "corners": ("corners_",),
    "fouls": ("fouls_",),
    "cards": ("cards_points_", "most_cards_points"),
    # F54. A player's shots are part of his team's shots are part of the
    # match's. Without these prefixes a player row would be its own family
    # (the fallback in `quantity_family`) and a builder could multiply
    # "Romarinho over 1.5 shots" by "Criciuma over 11.5 shots" as though they
    # were two independent facts. They are one fact counted twice, which is
    # the exact error this table exists to prevent.
    "shots": (
        "shots_",
        "shots_on_target_",
        "player_shots_",
        "player_shots_on_target_",
    ),
    # An assist is a goal seen from one pass earlier: it cannot happen without
    # the goal, so it is not independent of the scoring family.
    "goals": ("goals_", "player_assists_"),
    "offsides": ("offsides_",),
    "games": ("games_", "handicap_games", "sets_"),
    "aces": ("aces_",),
    "double_faults": ("double_faults_",),
}.items():
    for _p in _prefixes:
        QUANTITY_FAMILIES[_p] = _family


def quantity_family(market: str) -> str:
    """The underlying quantity a market counts. See QUANTITY_FAMILIES.

    Falls back to the market's own name, so an unmapped market is treated as
    its own family and can still combine — never silently merged into another.
    """
    best = ""
    family = market
    for prefix, fam in QUANTITY_FAMILIES.items():
        if market.startswith(prefix) and len(prefix) > len(best):
            best, family = prefix, fam
    return family


# ---------------------------------------------------------------------------
# Gates added 2026-09-20, after a row-by-row review of that day's coupon.
# Each one is here because a specific leg on a built coupon failed it.
# ---------------------------------------------------------------------------

# The fitted curve tops out at 0.9202 (see the module docstring: the
# 0.900-0.925 and 0.925-0.950 buckets both realise 0.9083, which is the model
# saying it has run out of resolution). So the highest probability any leg is
# permitted to carry is 0.9202, and a leg priced below 1/0.9202 CANNOT have
# positive expected value under this curve — not because of the fixture, but
# because of the ceiling.
#
# `MIN_ODDS = 1.01` sat 0.077 below that. On the 2026-09-20 coupon it let 8
# legs through in 8 of 14 slips; dropping each one raised its slip's EV, in
# every case (Londrina +0.004 -> +0.097).
CONFIDENCE_CEILING = 0.9202
MIN_ODDS_FOR_CEILING = 1.0 / CONFIDENCE_CEILING

# A builder leg is built on a sample; under ten observations the mean is not
# yet a centre. The sheet's own floor is five, which is right for *reporting* a
# row and too thin for *staking* a multiplied one.
MIN_BUILDER_SAMPLE = 10

# A sample reaching back far enough describes a different squad under a
# different coach. Set to 120 days on 2026-09-20 by reasoning about the
# transfer window, then **measured** the next hour against the 5,220 settled
# legs of 2026-09-19 and moved, because the reasoning was wrong about where
# the effect sits:
#
#     oldest obs.      n    realised   declared    diff      ROI
#       <= 60d        913     0.878      0.858    +0.020    -3.0%
#       61-90d        446     0.877      0.861    +0.016    -3.8%
#       91-120d       695     0.847      0.857    -0.010    -6.6%
#      121-180d      3062     0.874      0.856    +0.018    -3.8%
#        > 180d       104     0.817      0.856    -0.039    -9.7%
#
# There is no degradation out to 180 days — the 121-180d band performs like
# the freshest one. A 120-day cut would have removed 60 of the 83 legs on
# that day's coupon while catching 6 of its 9 losses, a worse loss rate than
# the coupon's own. The effect only appears past 180 days, and even there
# n = 104, so this is a weak guard on purpose rather than a confident one.
MAX_BUILDER_SAMPLE_AGE_DAYS = 180


# How much of the ladder's price may be the bookmaker's own margin before the
# leg is called robbery and refused.
#
# Ranking legs by `leg_ev` is measured to be INVERTED, and the reason is
# structural rather than statistical. `confidence` is a step function: every
# leg landing in the same calibration bucket is handed the same number. So
# within a bucket `leg_ev = confidence * odds - 1` is a strictly increasing
# function of the price alone, and ranking by it ranks by "longest price in
# this bucket" — which is the book telling us the event is less likely than
# its bucket-mates. Measured inside each bucket, the longest-priced third
# hits less often than the shortest-priced third, every time, and the gap
# widens as the bucket rises:
#
#     bucket    n     short third    long third
#     0.811    527       0.817         0.794
#     0.836    456       0.875         0.822
#     0.858    449       0.899         0.779
#     0.884    354       0.924         0.847
#     0.906    291       0.928         0.825
#
# The devigged market price also beats our own curve outright (Brier 0.10880
# against 0.11161, on a constant-0.871 baseline of 0.11267).
#
# So singles are ranked by `confidence` and filtered on the ladder's margin
# instead. The threshold is the one place the outcomes separate: below 10.5%
# the return is flat, above it it falls by about two points.
#
#     ladder margin      n      hit      ROI
#     <= 8.0%          1683    0.905    -3.55%
#     8.0 - 9.0%       2411    0.854    -3.55%
#     9.0 - 10.5%       102    0.843    -3.38%
#     > 10.5%          1089    0.857    -5.69%
#
# Read all of the above as ONE slate: 5,220 of the 5,285 settled legs behind
# these tables are 2026-09-19. The mechanism is certain because it follows
# from the code; the magnitudes are not, and this constant should be refitted
# once a second day of legs has settled.
MAX_OVERROUND = 0.105


def overround(over_odds: float | None, under_odds: float | None) -> float | None:
    """The bookmaker's margin on a two-sided rung, or None if it is one-sided.

    A one-sided rung cannot be measured — the missing side is exactly where
    the margin would show — so it is refused rather than assumed fair.
    """
    if not over_odds or not under_odds or over_odds <= 1.0 or under_odds <= 1.0:
        return None
    return 1.0 / over_odds + 1.0 / under_odds - 1.0


def single_is_fairly_priced(leg_overround: float | None) -> bool:
    """Is this leg's ladder cheap enough to be worth showing on its own?"""
    return leg_overround is not None and leg_overround <= MAX_OVERROUND


def leg_is_ev_positive(confidence: float, odds: float) -> bool:
    """Does this leg clear its own price, using its own number?

    The check the coupon skipped. `ev_if_product_priced` is computed as
    prod(confidence * odds) - 1, so a leg with `confidence * odds < 1` drags
    the slip down by construction — the builder was reporting an EV it was
    simultaneously destroying.
    """
    return confidence * odds > 1.0


def line_is_beyond_sample(
    line: float, direction: str, sample_values: list[float]
) -> bool:
    """Is the line outside everything the sample has ever seen?

    `UNDER 5.5` on a sample whose maximum is 5 is not a measurement of the
    tail, it is an extrapolation into a region with zero observations. The
    sample reports 20/20 and says nothing, because it could not have said
    anything else.

    This is the "certainty for free" case the operator's method already names,
    and it is how AC Milan's `goals_total UNDER 5.5 @1.08` reached a coupon.
    """
    if not sample_values:
        return False
    if direction == "UNDER":
        return line > max(sample_values)
    return line < min(sample_values)


def mode_loses(line: float, direction: str, sample_values: list[float]) -> bool:
    """Does the single most frequent observation settle this leg as a loss?

    Not "is the line near the mode" — that fires on safe legs too. The
    question is whether the sample's own modal outcome is on the losing side.
    Chaco For Ever's `goals_total OVER 0.5` had a modal sample value of 0:
    the most likely single outcome, by our own evidence, loses the bet.
    """
    if not sample_values:
        return False
    mode = statistics.mode(sample_values)
    return mode <= line if direction == "OVER" else mode >= line


def builder_legs_are_coherent(legs: list[dict]) -> bool:
    """Do these legs point the same way about how busy the match will be?

    `combined_probability` multiplies, which assumes independence. Across
    quantities that holds (lambda 0.95-1.02, see QUANTITY_FAMILIES). It stops
    holding when the legs disagree about tempo: `goals UNDER` with `corners
    OVER` is a negatively correlated pair, so the product OVERSTATES the joint
    and the slip's EV is reported too high.

    Legs that agree are positively correlated, where the product UNDERSTATES —
    an error in the operator's favour, and therefore allowed.

    On 2026-09-20 three of fourteen slips mixed directions this way.
    """
    tempo = {"goals", "corners", "shots"}
    directions = {
        leg["direction"] for leg in legs if quantity_family(leg["market"]) in tempo
    }
    return len(directions) <= 1


MAX_BUILDER_LEGS = 4
MIN_BUILDER_LEGS = 2


def best_leg_per_quantity(legs: list[dict]) -> dict[str, dict]:
    """One representative per quantity family, chosen by **leg EV**.

    A builder takes at most one leg per quantity, so this choice happens before
    any ranking and silently decides what the ranking is allowed to see.
    Choosing by `confidence` is choosing by shortness of price — the two are
    near-inverses, because the book prices a near-certainty at a
    near-certainty — so a family's EV-positive leg was discarded in favour of
    its shortest-priced sibling before the EV ordering ever ran. That is the
    2026-09-20 defect surviving one level below the sort that was supposed to
    have removed it.
    """
    best: dict[str, dict] = {}
    for leg in legs:
        family = quantity_family(leg["market"])
        current = best.get(family)
        if current is None or leg["leg_ev"] > current["leg_ev"]:
            best[family] = leg
    return best


def displayed_ev(builder: dict) -> float | None:
    """The EV a builder should be *shown* with: after the correlation haircut.

    Separate from the selection key only because the two disagreed. In
    `build_coupon_pdf` the variable holding "ev_after_haircut" was named `key`
    and a per-leg loop rebound `key` to a tuple; a loop variable outlives its
    loop, so the summary row's `b.get(key, b.get("ev_if_product_priced"))`
    always fell through to the product EV. Selection was right and the printed
    number was wrong, on a page whose own text says the EV is computed from the
    post-haircut price.

    Falls back to the product EV only for an artifact written before the
    haircut existed, and that fallback is the reason the bug was invisible.
    """
    value = builder.get("ev_after_haircut")
    if value is None:
        value = builder.get("ev_if_product_priced")
    return value


@dataclass(frozen=True)
class Calibration:
    pooled: dict[str, dict]
    by_market: dict[str, dict[str, dict]]
    # Pooled per sport. The global pool is ~95% football counting markets, so
    # serving a tennis metric from it hands tennis football's shape.
    pooled_by_sport: dict[str, dict[str, dict[str, Any]]] = field(
        default_factory=dict
    )

    @staticmethod
    def load(path: Path | str = DEFAULT_CALIBRATION) -> Calibration:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        return Calibration(
            pooled=doc.get("pooled", {}),
            by_market=doc.get("by_market", {}),
            pooled_by_sport=doc.get("pooled_by_sport", {}),
        )

    @staticmethod
    def _find(curve: dict[str, dict], p: float) -> dict | None:
        for key, entry in curve.items():
            lo, hi = (float(x) for x in key.split("-"))
            if lo <= p < hi:
                return entry
        return None

    def realised(
        self, market: str, p: float, sport: str | None = None
    ) -> tuple[float, str, int] | None:
        """The measured lower bound for this market at this claimed probability.

        Returns (realised_lo95, source, n), or None when neither the market's
        own curve nor the pooled one covers the bucket — in which case the
        caller must refuse the leg rather than fall back to `p`. Falling back
        to the model's own number is precisely the untested claim this module
        exists to stop making.
        """
        own = self.by_market.get(market, {})
        entry = self._find(own, p)
        if entry is not None:
            return entry["realised_lo95"], f"market:{market}", entry["n"]

        # A market with its own curve may NOT borrow the pooled one above the
        # top of its own measured range.
        #
        # Measured 2026-09-21, and it is the whole reason empirical-frequency
        # metrics were once banned outright. `games_won_for` has 9,286 settled
        # rows and not one bucket above 0.825; its best measured bucket
        # realises 0.756. The pooled curve — 74,574 rows, almost all football
        # counting markets — says 0.905 at p=0.90. Falling through produced 12
        # tennis legs at a claimed 0.905 that this market has never once been
        # observed to deliver, which is the "0.811 against a price of 20.00"
        # failure wearing a calibration curve.
        #
        # Silence above a market's measured range is evidence, not a gap: it
        # says the model never produces a confident prediction here that
        # verifies. A hole *inside* the range is different — that is a thin
        # bucket, and the pooled curve is a reasonable stand-in for it.
        if own:
            ceiling = self._measured_ceiling(own)
            if ceiling is not None and p >= ceiling:
                return None

        # The sport's own pool before the global one. `sets_total` has 202
        # settled rows — too few for a market curve — and read 0.856 off a
        # global bucket of 64,790 rows that were almost entirely goals and
        # corners. Tennis has 56,581 settled rows of its own; there is no
        # reason to describe it with football.
        if sport:
            entry = self._find(self.pooled_by_sport.get(sport, {}), p)
            if entry is not None:
                return entry["realised_lo95"], f"pooled:{sport}", entry["n"]
        entry = self._find(self.pooled, p)
        if entry is not None:
            return entry["realised_lo95"], "pooled", entry["n"]
        return None

    def measured_ceiling(self, market: str) -> float | None:
        """Top of the range this market has evidence for, or None if no curve.

        Public because the coupon needs the same fact the confidence view
        uses: a row claiming more than its market has ever been observed to
        deliver is making a claim the settled data refuses to describe.
        """
        own = self.by_market.get(market, {})
        return self._measured_ceiling(own) if own else None

    @staticmethod
    def _measured_ceiling(curve: dict[str, dict[str, Any]]) -> float | None:
        """Top of the highest bucket this market actually has evidence for."""
        tops: list[float] = []
        for key in curve:
            _, _, hi = key.partition("-")
            try:
                tops.append(float(hi))
            except ValueError:
                continue
        return max(tops) if tops else None


def combined_probability(legs: list[float]) -> float:
    """Product, because same-match legs were measured independent (lambda 1.009)."""
    out = 1.0
    for p in legs:
        out *= p
    return out


def fair_odds(probability: float) -> float | None:
    """The price a combination would need to be worth its risk, and NOT a
    prediction of Superbet's Bet Builder price.

    Superbet prices a builder with its own correlation adjustment, so
    multiplying the leg prices would invent a number the book never quoted.
    The operator compares this against what the screen actually shows.
    """
    if probability <= 0.0:
        return None
    return round(1.0 / probability, 2)


# Superbet does not price a Bet Builder at the product of its legs: it applies
# its own correlation adjustment, and that adjustment is the whole margin.
# Measured 2026-09-20 from the operator's screenshots — the first time this
# repo ever saw a builder's real price (see reports/sofa_narzut_bet_buildera_
# 2026-09-20.md):
#
#     slip                                  legs   product   screen   markup
#     Inter Miami  goals U5.5 + 1h U2.5        2     1.754     1.60     8.8%
#     Athletico    corners 1h U6.5 + U13.5     2     1.782     1.50    15.8%
#     Flamengo     3 UNDER + corners 2h OVER   4     2.364     1.90    19.6%
#
# 12% is the middle of that range, held flat on purpose: three observations
# cannot fit a curve in leg count, and a per-leg-count table from n=3 would be
# overfitting dressed as precision. Replace with a fitted curve once enough
# screen prices are recorded.
#
# The single leg on the same screen (Londrina corners U12.5) went at exactly
# our quoted 1.37, so the leg prices are faithful. The money is in the join.
BUILDER_CORRELATION_HAIRCUT = 0.12

# Below this the empirical joint is noise, and min()-ing against it would let
# one unlucky decile veto a slip. The builder sample floor is already 10.
MIN_JOINT_SAMPLE = 8


def builder_odds(odds_product: float, screen_odds: float | None = None) -> float:
    """What a builder actually returns, per unit staked.

    `screen_odds` is the price the operator read off Superbet. When it is
    known it wins outright — a measurement beats an estimate. When it is not,
    the product is discounted by the measured correlation markup, because
    selecting on the undiscounted product is selecting on a price the book has
    never quoted.
    """
    if screen_odds is not None:
        return screen_odds
    return odds_product * (1.0 - BUILDER_CORRELATION_HAIRCUT)


def empirical_joint(
    observations: list[dict[int, float]], conditions: list[tuple[float, str]]
) -> tuple[int, int]:
    """How often did every leg of this slip hold in the SAME past match?

    `observations` is one {event_id: value} map per leg, `conditions` the
    matching (line, direction) pairs. Only matches present in every leg's
    sample can be judged, so the count is over the intersection.

    This is the question `combined_probability` cannot ask. The product
    assumes independence; the intersection observes the joint. On 2026-09-20
    the two disagreed in both directions on real slips — 58.3% product against
    4/10 observed where the legs disagreed about tempo, and 64.9% against 5/6
    where one leg nested inside another.

    Returns (hits, n). n == 0 when the samples share no match.
    """
    if not observations or len(observations) != len(conditions):
        return 0, 0
    common = set(observations[0])
    for obs in observations[1:]:
        common &= set(obs)
    hits = 0
    for event_id in common:
        if all(
            (obs[event_id] < line) if direction == "UNDER" else (obs[event_id] > line)
            for obs, (line, direction) in zip(observations, conditions)
        ):
            hits += 1
    return hits, len(common)


def joint_probability(product: float, hits: int, n: int) -> float:
    """The slip's probability, taking the more pessimistic of two estimates.

    The product and the observed joint are both estimates of the same
    quantity, and neither dominates: the product overstates legs that disagree
    about tempo and understates legs that nest. Taking the minimum refuses to
    promote a slip on a noisy ten-match high while still letting that sample
    demote one — which is the asymmetry this repo keeps paying for when it
    gets it backwards.

    The empirical side is Laplace-smoothed, so 10/10 does not assert
    certainty.
    """
    if n < MIN_JOINT_SAMPLE:
        return product
    return min(product, (hits + 1) / (n + 2))


def is_stakeable(builder: Mapping[str, Any]) -> bool:
    """Whether a builder is a bet, as the PDF — the actual coupon — decides it.

    Two conditions, and they are not the same one. `best_for_fixture` keeps a
    fixture from being staked three times over off one opinion; the EV test
    asks whether the position survives Superbet's measured markup for pricing
    a correlated slip.

    This lives here, used by both `run_confidence.py` and
    `build_coupon_pdf.py`, because it was written out twice and the two copies
    disagreed. On 2026-09-21 CONFIDENCE reported `stakeable_builders: 3` for a
    day on which the PDF staked nothing: all three builders were
    `best_for_fixture` and all three had negative EV after the haircut. One
    predicate, one answer.
    """
    if not builder.get("best_for_fixture"):
        return False
    # Older artifacts predate the haircut and carry only the product EV.
    key = (
        "ev_after_haircut" if "ev_after_haircut" in builder else "ev_if_product_priced"
    )
    ev = builder.get(key)
    return ev is not None and ev > 0
