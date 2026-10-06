"""One coupon (operator, 2026-10-05/06): the WARIANT, WARIANT WSZYSTKIE and
the separate per-sport coupons were retired and their code deleted. Their
days stay in the ledger as recorded rows; nothing rebuilds or grades them."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from bet.sofa import confidence, epochs

REPO = Path(__file__).resolve().parents[2]
RETIRED = [
    "scripts/sofa/run_multi_coupon.py",
    "scripts/sofa/settle_multi_coupon.py",
    "scripts/sofa/run_sport_coupon.py",
    "scripts/sofa/settle_sport_coupon.py",
    "scripts/sofa/fit_sport_price_calibration.py",
    "src/bet/sofa/multi_coupon.py",
    "src/bet/sofa/sport_coupon.py",
    "config/sofa_sport_price_calibration.json",
]


@pytest.mark.parametrize("path", RETIRED)
def test_a_retired_variant_stays_deleted(path: str) -> None:
    assert not (REPO / path).exists()


def test_the_coupon_has_one_profile() -> None:
    assert not hasattr(confidence, "PROFILES")
    p = confidence.COUPON_PROFILE
    assert (p.name, p.floor, p.min_ev, p.max_overround) == ("standard", 0.70, 0.90, 0.15)


def test_the_sports_are_on_the_coupon_from_their_epoch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert epochs.SPORTS_ON_COUPON_FROM_UTC is None or epochs.sports_on_coupon(
        "2026-10-05", epochs.SPORTS_ON_COUPON_FROM_UTC)
    cut = datetime(2026, 10, 6, 12, tzinfo=UTC)
    monkeypatch.setattr(epochs, "SPORTS_ON_COUPON_FROM_UTC", cut)
    assert epochs.sports_on_coupon("2026-10-06", cut)
    assert not epochs.sports_on_coupon("2026-10-06", cut - timedelta(minutes=1))
