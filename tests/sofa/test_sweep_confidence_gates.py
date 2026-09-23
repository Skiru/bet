"""The gate sweep's arithmetic: overround rebuild, curve lookup, the gates."""

from __future__ import annotations

import pytest

from bet.sofa.engine import devig
from scripts.sofa.sweep_confidence_gates import (
    PRODUCTION,
    Curve,
    Row,
    bucket_of,
    overround_from_devig,
    passes,
    profit,
    wilson_lo,
)


@pytest.mark.parametrize(
    ("a", "b"), [(1.36, 2.87), (1.43, 2.57), (1.85, 1.95), (1.10, 6.5)]
)
def test_overround_is_rebuilt_from_one_side_and_its_devig(a: float, b: float) -> None:
    """The other price is not stored; power devig lets us recover the margin."""
    pair = devig(a, b)
    assert pair is not None
    got = overround_from_devig(a, pair[0])
    assert got == pytest.approx(1 / a + 1 / b - 1, abs=1e-9)


def test_overround_refuses_nonsense() -> None:
    assert overround_from_devig(1.0, 0.5) is None
    assert overround_from_devig(2.0, 0.0) is None


def test_low_buckets_are_not_one_flat_bucket() -> None:
    """Production's single 0-0.60 bucket makes every long shot look +EV."""
    assert bucket_of(0.10) != bucket_of(0.55)
    assert bucket_of(0.72) == bucket_of(0.74)


def test_curve_falls_back_market_then_sport_then_global() -> None:
    hits = [("m", "tennis", 0.72, i % 4 != 0) for i in range(500)]
    hits += [("other", "tennis", 0.52, True) for _ in range(250)]
    curve = Curve(hits)
    own = curve.lookup("m", "tennis", 0.73)
    assert own == pytest.approx(wilson_lo(375, 500))
    # no own bucket at 0.52 and 0.52 is BELOW m's measured range: sport pool
    assert curve.lookup("m", "tennis", 0.52) == pytest.approx(wilson_lo(250, 250))
    # above m's own range: refused, never borrowed
    assert curve.lookup("m", "tennis", 0.95) is None


def _row(p: float = 0.8, mp: float = 0.75, odds: float = 1.3, won: bool = True) -> Row:
    return Row("2026-09-19", 1, "football", "goals_total", p, mp, odds, won)


def test_passes_applies_every_dial() -> None:
    r = _row()
    assert passes(0.80, r, 0.08, PRODUCTION)  # 0.80 x 1.3 = 1.04
    assert not passes(0.69, r, 0.08, PRODUCTION)  # floor
    assert not passes(0.76, _row(odds=1.2), 0.08, PRODUCTION)  # 0.912 < 1.0
    assert not passes(0.80, _row(p=0.9, mp=0.7), 0.08, PRODUCTION)  # disagree 0.2
    assert not passes(0.80, r, 0.11, PRODUCTION)  # overround > 0.105
    assert not passes(0.80, r, None, PRODUCTION)  # unknown overround refused
    assert passes(0.80, r, None, (0.70, 1.0, 0.10, None, None))  # dial off
    assert not passes(0.80, r, 0.08, (0.70, 1.0, 0.10, 0.105, 1.25))  # max odds


def test_profit_is_flat_stake() -> None:
    assert profit(_row(odds=1.5, won=True)) == pytest.approx(0.5)
    assert profit(_row(odds=1.5, won=False)) == -1.0
