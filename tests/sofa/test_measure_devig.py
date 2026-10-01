"""scripts/sofa/measure_devig.py - power vs proportional vs Shin."""

import pytest

from scripts.sofa.measure_devig import all_methods, shin


def test_every_method_returns_a_distribution():
    ps = all_methods([1.50, 2.60])
    assert ps is not None
    for m in ("power", "proportional", "shin"):
        assert sum(ps[m]) == pytest.approx(1.0, abs=1e-9)


def test_the_methods_differ_on_a_longshot_the_way_the_literature_says():
    ps = all_methods([1.10, 7.00])
    assert ps is not None
    # proportional leaves the most on the longshot; power and Shin take it off
    assert ps["proportional"][1] > ps["shin"][1]
    assert ps["proportional"][1] > ps["power"][1]
    assert ps["worst"][1] == min(ps["power"][1], ps["proportional"][1], ps["shin"][1])


def test_shin_without_a_margin_is_the_implied_probability():
    assert shin([0.4, 0.6]) == pytest.approx([0.4, 0.6])
