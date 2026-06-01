"""Coupon builder: construct coupons from signals.

Simple constructor that builds single-event coupons. Later PRs will add
combination logic and stake/risk calculations.
"""
from __future__ import annotations

import uuid
from typing import List

from ..contracts import Signal, Coupon


def build_coupons(signals: List[Signal], max_picks: int = 10) -> List[Coupon]:
    coupons: List[Coupon] = []
    # group signals into single-pick coupons up to max_picks
    for s in signals[:max_picks]:
        c = Coupon(id=str(uuid.uuid4()), picks=[s], stake=1.0)
        coupons.append(c)
    return coupons
