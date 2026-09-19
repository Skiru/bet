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
from dataclasses import dataclass
from pathlib import Path

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
    "goals": ("goals_",),
    "corners": ("corners_",),
    "fouls": ("fouls_",),
    "cards": ("cards_points_", "most_cards_points"),
    "shots": ("shots_", "shots_on_target_"),
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


MAX_BUILDER_LEGS = 4
MIN_BUILDER_LEGS = 2


@dataclass(frozen=True)
class Calibration:
    pooled: dict[str, dict]
    by_market: dict[str, dict[str, dict]]

    @staticmethod
    def load(path: Path | str = DEFAULT_CALIBRATION) -> "Calibration":
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        return Calibration(pooled=doc.get("pooled", {}), by_market=doc.get("by_market", {}))

    @staticmethod
    def _find(curve: dict[str, dict], p: float) -> dict | None:
        for key, entry in curve.items():
            lo, hi = (float(x) for x in key.split("-"))
            if lo <= p < hi:
                return entry
        return None

    def realised(self, market: str, p: float) -> tuple[float, str, int] | None:
        """The measured lower bound for this market at this claimed probability.

        Returns (realised_lo95, source, n), or None when neither the market's
        own curve nor the pooled one covers the bucket — in which case the
        caller must refuse the leg rather than fall back to `p`. Falling back
        to the model's own number is precisely the untested claim this module
        exists to stop making.
        """
        entry = self._find(self.by_market.get(market, {}), p)
        if entry is not None:
            return entry["realised_lo95"], f"market:{market}", entry["n"]
        entry = self._find(self.pooled, p)
        if entry is not None:
            return entry["realised_lo95"], "pooled", entry["n"]
        return None


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
