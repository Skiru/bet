"""Settlement preparation stage: prepare settlement plans for built coupons.

For refactor purposes this produces a mocked expected payout formula (stake * avg_confidence * 2)
"""
from __future__ import annotations

from typing import List

from ..contracts import Coupon, SettlementPlan


def prepare_settlement(coupons: List[Coupon]) -> List[SettlementPlan]:
    plans: List[SettlementPlan] = []
    for c in coupons:
        avg_conf = sum(s.confidence for s in c.picks) / len(c.picks)
        expected_payout = c.stake * avg_conf * 2
        plans.append(SettlementPlan(coupon_id=c.id, expected_payout=expected_payout, settled=False, details={"num_picks": len(c.picks)}))
    return plans
