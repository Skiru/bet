"""``fair_odds`` and ``min_acceptable_odds`` must describe the same row.

Both the coupon and the Bet Builder draft used to report
``fair_odds = 1 / p_low`` while computing the bar -- and therefore
``min_acceptable_odds`` -- from ``bar_probability``, which is p_central-based
since the switch recorded in project memory. Two consequences, and the second
is the one that showed:

* the two fields described different probabilities, so the margin implied
  between them was not the tier margin;
* Wilson's lower bound underflows towards zero on a sample with no hit, so the
  field printed astronomical numbers. On 2026-09-07 the ``goals_total 5.5
  OVER`` leg drafted for Getafe - Celta reported fair odds of **4.9e+16**
  beside a ``min_acceptable_odds`` of 22.0, off ``p_low = 2.06e-17`` at 0/11.

``draft_legs`` had already been using the bar probability for exactly this
quantity in its own "would this leg lower the slip's value" gate, so the
reported number disagreed with the number the code decided on.

These tests read the generated artifacts rather than the functions, because
the defect was a *reported* value and a unit test on the helper would have
passed throughout.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DATE = "2026-09-07"
RUN = ROOT / "runs" / DATE

# ``bar_for`` charges this on top of the fair price for a CALL; a LEAN pays
# more. Read from the module so the test cannot drift from the code.
def _margins():
    from bet.simple_stats.coupons import TIER_MARGIN

    return TIER_MARGIN


@pytest.fixture(scope="module")
def coupons() -> dict:
    path = RUN / f"{DATE}_coupons.json"
    if not path.exists():
        pytest.skip(f"{path.name} not on disk")
    return json.loads(path.read_text(encoding="utf-8"))


def test_no_single_reports_an_absurd_fair_price(coupons) -> None:
    """The symptom, stated as a bound a real price can never exceed."""
    for single in coupons["singles"]:
        fair = single["fair_odds"]
        assert 1.0 <= fair < 1000.0, (
            f"single #{single['rank']} {single['market']} reports fair odds "
            f"{fair}, which is not a price. p_low={single['p_low']}"
        )


def test_fair_odds_is_the_reciprocal_of_the_bar_probability(coupons) -> None:
    """The invariant that keeps the two fields about the same row."""
    checked = 0
    for single in coupons["singles"]:
        bar_p = single.get("bar_probability")
        if not bar_p:
            continue
        checked += 1
        assert single["fair_odds"] == pytest.approx(1.0 / bar_p, rel=1e-3), (
            f"single #{single['rank']} {single['market']}: fair_odds "
            f"{single['fair_odds']} is not 1/bar_probability ({1.0 / bar_p:.4f})"
        )
    assert checked, "no coupon row carried a bar_probability"


def test_the_minimum_is_the_fair_price_plus_the_tier_margin(coupons) -> None:
    """And so the margin between them is the tier's, not an artefact.

    This is the half that would have caught the original defect: with
    ``fair_odds`` on p_low and the minimum on the bar, the ratio between them
    was whatever the gap between the two probabilities happened to be.
    """
    margins = _margins()
    for single in coupons["singles"]:
        expected = margins.get(single["tier"])
        if expected is None:
            continue
        ratio = single["min_acceptable_odds"] / single["fair_odds"]
        assert ratio == pytest.approx(expected, rel=1e-3), (
            f"single #{single['rank']} {single['market']} is {single['tier']}: "
            f"min/fair is {ratio:.4f}, expected the tier margin {expected}"
        )
