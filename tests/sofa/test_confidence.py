"""The confidence view: reliability, not value.

Measured on the 6,187 rows carrying a real Superbet price, the model loses to
the price (Brier 0.2067 against 0.1845), and ranking by surplus selects where
it loses worst — past a model-minus-price gap of +0.10 the realised rate falls
below a coin flip. Calibration is the other question, and over 1,868,474
settled rows the model answers it to within 0.3 pp up to about 0.90.

These tests pin the three things that would quietly turn this back into the
coupon it replaces: quoting the point estimate, claiming certainty, and
multiplying legs that are one quantity counted twice.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bet.sofa.confidence import (
    MAX_BUILDER_LEGS,
    Calibration,
    combined_probability,
    fair_odds,
    quantity_family,
)

REPO = Path(__file__).resolve().parents[2]
CAL = REPO / "config" / "sofa_confidence_calibration.json"


@pytest.fixture(scope="module")
def cal() -> Calibration:
    return Calibration.load(CAL)


def test_the_curve_is_fitted_from_the_settled_rows() -> None:
    doc = json.loads(CAL.read_text(encoding="utf-8"))
    assert doc["fitted_from"]["scored_rows"] > 1_000_000
    assert doc["pooled"], "a confidence view with no measurement is a guess"


def test_it_reports_the_lower_bound_not_its_own_best_case(cal: Calibration) -> None:
    doc = json.loads(CAL.read_text(encoding="utf-8"))
    for bucket in doc["pooled"].values():
        assert bucket["realised_lo95"] <= bucket["realised"]
    got = cal.realised("goals_total", 0.93)
    assert got is not None
    realised_lo, source, n = got
    assert source.startswith("market:")
    assert 0.0 < realised_lo < 1.0


def test_there_is_no_certainty_above_about_0_92(cal: Calibration) -> None:
    """The model runs out of resolution; the view must not pretend otherwise.

    The fitted buckets 0.900-0.925 and 0.925-0.950 both realise 0.9083 — more
    claimed probability buying no more realised outcome. A leg presented at
    0.98 would be a lie of about seven points.
    """
    for claimed in (0.93, 0.96, 0.99):
        got = cal.realised("goals_total", claimed)
        assert got is not None
        realised_lo, _, _ = got
        assert realised_lo < 0.95, f"claimed {claimed} came back as {realised_lo}"


def test_an_uncalibrated_bucket_is_refused_not_guessed(cal: Calibration) -> None:
    """None means refuse. Falling back to the model's own number is the bug."""
    empty = Calibration(pooled={}, by_market={})
    assert empty.realised("goals_total", 0.9) is None


def test_a_team_total_and_the_match_total_are_one_quantity() -> None:
    """lambda 2.165 measured, up to 8.37. Multiplying them sells 2 legs as 4."""
    assert quantity_family("goals_for") == quantity_family("goals_total")
    assert quantity_family("goals_1h_total") == quantity_family("goals_total")
    assert quantity_family("corners_for") == quantity_family("corners_1h_total")
    assert quantity_family("fouls_for") == quantity_family("fouls_total")


def test_different_quantities_stay_separable() -> None:
    """lambda 0.95-1.02 measured across these, so the product is right."""
    assert quantity_family("corners_total") != quantity_family("goals_total")
    assert quantity_family("fouls_total") != quantity_family("corners_total")
    assert quantity_family("cards_points_total") != quantity_family("fouls_total")


def test_an_unmapped_market_is_its_own_family_not_someone_elses() -> None:
    assert quantity_family("some_new_metric") == "some_new_metric"
    assert quantity_family("xg_total") == "xg_total"


def test_combining_legs_lowers_the_probability() -> None:
    """The arithmetic the operator most needs to see: 3 legs at 0.90 is 0.729."""
    assert combined_probability([0.9, 0.9, 0.9]) == pytest.approx(0.729)
    assert combined_probability([0.9] * 4) == pytest.approx(0.6561)
    assert combined_probability([0.92, 0.88]) == pytest.approx(0.8096)


def test_fair_odds_is_not_a_predicted_builder_price() -> None:
    """Superbet applies its own correlation adjustment to a builder, so this
    is what the combination must pay, not what it will be offered at."""
    assert fair_odds(0.729) == pytest.approx(1.37, abs=0.01)
    assert fair_odds(0.0) is None


def test_the_builder_leg_cap_is_small_for_a_reason() -> None:
    """Legs multiply: at a realised ceiling near 0.92, five legs is a coin flip."""
    assert MAX_BUILDER_LEGS <= 4
    assert combined_probability([0.92] * 5) < 0.67


def test_only_one_builder_per_fixture_is_stakeable() -> None:
    """The 2-, 3- and 4-leg builders off one fixture are nested, not distinct.

    They come from the same ranked pool, so the 2-leg is a subset of the
    4-leg. Marking them all stakeable turned 54 fixtures into 79 "bets" on
    2026-09-19, with 46 of 148 legs repeated across slips — one opinion sold
    at three stakes.
    """
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[2] / "scripts" / "sofa" / "run_confidence.py"
    ).read_text()
    assert "best_for_fixture" in src

    run = Path("runs/sofa/2026-09-19/08_confidence.json")
    if not run.exists():
        pytest.skip("no live artifact in this checkout")
    doc = json.loads(run.read_text(encoding="utf-8"))
    stakeable = [b for b in doc["builders"] if b.get("best_for_fixture")]
    seen = [b["sofascore_event_id"] for b in stakeable]
    assert len(seen) == len(set(seen)), "a fixture may be staked at most once"


def test_joint_markets_are_refused_not_pooled() -> None:
    """both_over_* / handicap_* / most_* carry 2-252 settled rows each.

    They are a function of two sides, not a count of one thing, so the pooled
    curve — fitted on 1.87M single-quantity counts — says nothing about them,
    and no per-side sample in the artifacts can check them. both_over_shots
    has 26 settled rows and was reaching the top of the builder list.
    """
    from bet.sofa.confidence import is_derived

    for market in ("both_over_shots", "both_over_goals", "handicap_corners",
                   "most_cards_points"):
        assert is_derived(market)
    for market in ("goals_total", "corners_for", "goals_1h_total"):
        assert not is_derived(market)

    run = Path("runs/sofa/2026-09-19/08_confidence.json")
    if not run.exists():
        pytest.skip("no live artifact in this checkout")
    doc = json.loads(run.read_text(encoding="utf-8"))
    assert not [l for l in doc["legs"] if is_derived(l["market"])]
    assert not [
        x for b in doc["builders"] for x in b["legs"] if is_derived(x["market"])
    ]


def test_coupon_selects_on_a_price_the_book_actually_quotes() -> None:
    """`ev_if_product_priced` must not decide what reaches the coupon.

    Superbet's correlation markup was measured at 8.8-19.6% on 2026-09-20.
    At the smallest of those, 2 of the 300 builders generated on 2026-09-19
    stayed positive — so ranking and filtering on the undiscounted product
    admitted slips that were already negative when the screen quoted them.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    conf = (root / "scripts" / "sofa" / "run_confidence.py").read_text()
    assert 'builders.sort(key=lambda b: (-b["ev_after_haircut"]' in conf

    pdf = (root / "scripts" / "sofa" / "build_coupon_pdf.py").read_text()
    assert '"ev_after_haircut"' in pdf


def test_builder_internals_do_not_reach_the_artifact() -> None:
    """The per-leg match map is working state, not a published field."""
    from pathlib import Path

    src = (
        Path(__file__).resolve().parents[2] / "scripts" / "sofa" / "run_confidence.py"
    ).read_text()
    assert 'leg.pop("_obs_by_match", None)' in src

    run = Path("runs/sofa/2026-09-19/08_confidence.json")
    if not run.exists():
        pytest.skip("no live artifact in this checkout")
    doc = json.loads(run.read_text(encoding="utf-8"))
    assert all("_obs_by_match" not in leg for leg in doc["legs"])
