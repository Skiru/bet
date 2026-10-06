"""The coupon's dials (confidence.COUPON_PROFILE) and how an artifact is read.

Since 2026-10-05 (operator): confidence >= 0.70, confidence x odds >= 0.90,
a ladder margin up to 15%, every passing single printed. An artifact carries
the dials it was built with, so an older day reads under its own.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from bet.sofa.confidence import (
    CONFIDENCE_ARTIFACT,
    COUPON_PROFILE,
    MAX_OVERROUND,
    PDF_MAX_SINGLES,
    leg_is_ev_positive,
    printed_builders,
    printed_singles,
)
from tests.sofa.confidence_day import DAY, _run, day  # noqa: F401


def test_the_coupons_dials() -> None:
    from scripts.sofa.run_confidence import DEFAULT_FLOOR

    p = COUPON_PROFILE
    assert p.floor == DEFAULT_FLOOR == 0.70
    assert (p.min_ev, p.max_overround, p.pdf_max_singles) == (0.90, 0.15, None)
    assert CONFIDENCE_ARTIFACT == "08_confidence.json"


@pytest.mark.parametrize(
    ("confidence", "odds", "clears"),
    [
        (0.80, 1.30, True),  # x = 1.04
        (0.80, 1.25, True),  # x = 1.00 exactly
        (0.75, 1.20, True),  # x = 0.90: the edge, inclusive
        (0.75, 1.19, False),  # x = 0.8925
    ],
)
def test_the_price_dial(confidence: float, odds: float, clears: bool) -> None:
    assert COUPON_PROFILE.clears_price(confidence, odds) is clears


def test_the_old_rule_is_still_strict() -> None:
    # min_ev None (the rule until 10-04, how an artifact without it is read)
    assert not leg_is_ev_positive(0.80, 1.25)
    assert leg_is_ev_positive(0.80, 1.30)


def test_a_ladder_margin_up_to_15_percent() -> None:
    """MAX_OVERROUND stays the measured 10.5% (and the reading of artifacts
    from before 2026-10-05); the coupon takes up to 15%."""
    assert MAX_OVERROUND == 0.105
    for margin, ok in [(0.0888, True), (0.105, True), (0.15, True),
                       (0.1501, False), (None, False)]:
        assert COUPON_PROFILE.single_is_fairly_priced(margin) is ok


def test_an_artifact_prints_what_its_own_limit_says() -> None:
    assert PDF_MAX_SINGLES == 30
    rows = [{"i": i} for i in range(PDF_MAX_SINGLES + 7)]
    assert printed_singles({"singles": rows}) == rows[:PDF_MAX_SINGLES]
    assert printed_singles({"singles": rows, "pdf_max_singles": None}) == rows
    assert printed_singles({"singles": rows, "pdf_max_singles": 5}) == rows[:5]
    assert printed_singles({}) == []


def test_printed_builders_follows_the_artifact() -> None:
    good = {"best_for_fixture": True, "ev_after_haircut": 0.1}
    bad = {"best_for_fixture": True, "ev_after_haircut": -0.1}
    assert printed_builders({"min_ev": None, "builders": [good, bad]}) == [good]
    assert printed_builders({"min_ev": 0.9, "builders": [good]}) == []
    assert printed_builders(
        {"min_ev": 0.9, "prints_builders": True, "builders": [good, bad]}
    ) == [good]


def test_confidence_selects_what_the_dials_say(day: Path) -> None:  # noqa: F811
    run = day / DAY
    out = _run("run_confidence.py", day, "--runs-dir", str(day))
    assert out.returncode == 0, out.stderr
    doc = json.loads((run / "08_confidence.json").read_text())
    # A clears at x > 1, B only at the 0.90 tolerance
    assert {s["sofascore_event_id"] for s in doc["singles"]} == {1, 2}
    assert (doc["profile"], doc["confidence_floor"], doc["min_ev"],
            doc["max_overround"]) == ("standard", 0.70, 0.9, 0.15)
    assert json.loads(out.stdout.strip().splitlines()[-1])["profile"] == "standard"
    assert not list(run.glob("*wariant*"))


def test_the_retired_profile_flag_is_gone(day: Path) -> None:  # noqa: F811
    out = _run("run_confidence.py", day, "--runs-dir", str(day), "--profile", "wariant")
    assert out.returncode == 2 and "--profile" in out.stderr
