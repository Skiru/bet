"""Which of two legs at the same price is the surer one (operator, 2026-10-08).

The coupon prints every leg that clears its bars, and the legs of one match
come at near-equal prices on different variables (2026-10-07, Internacional -
Corinthians: total cards over 3.5 @1.13-1.16 and Corinthians cards under 4.5
@1.19-1.21 sat in one slip). The operator's rule: when two legs cost the same,
the page proposes the one with the greater chance of landing. This module
names that leg; it selects nothing and removes nothing (annotation only, like
`leg_relations`).

The proposal is the **confidence** the coupon already prints, because that is
the best-measured ranking there is (`scripts/sofa/measure_peer_choice.py`,
`docs/sofa/evidence/peer_choice_2026-10-08.md`): on 57,791 settled pairs of
football / tennis legs of one match priced within `PEER_BAND` of each other
(20 days, exactly one of the two won) the more confident leg won 53.4%
[95% 52.2, 54.7], and no statistic of the sample, no metadata of the
tournament and no form feature added anything out of sample. In hockey,
basketball and volleyball the same pairs show no measurable edge
(2,894 pairs, 49.7% [45.9, 53.6]). The edge is real and small; the page says
so and does not dress the proposal as more.

Two legs are peers when they are different variables of one match (the same
variable at two rungs is a ladder - `leg_relations.ladders`) and their prices
lie within `PEER_BAND`. Peers are read per leg, so there are no window edges:
a leg is PREFERRED when no peer has a higher confidence.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from bet.sofa.confidence import coupon_sort_key, group_key
from bet.sofa.leg_relations import leg_ref, quantity_key

# Prices within this distance are "the same price". Measured, not tuned: the
# pairs in the evidence are exactly the ones with |odds a - odds b| <= 0.06.
PEER_BAND = 0.06

# A sample this thin is said on the line (it is not a gate: measured, the own
# sample size adds nothing to the confidence out of sample).
THIN_SAMPLE = 12


def _odds(leg: Mapping[str, Any]) -> float | None:
    value = leg.get("offered_odds", leg.get("odds"))
    return None if value is None else float(value)


def _variable(leg: Mapping[str, Any]) -> str:
    key = quantity_key(leg)
    if key is not None:
        return key
    return "|".join(str(leg.get(k) or "") for k in (
        "sport", "market", "family", "period", "subject"))


def _view(leg: Mapping[str, Any]) -> dict[str, Any]:
    out = {**leg_ref(leg), "confidence": float(leg["confidence"]),
           "odds": _odds(leg)}
    n = leg.get("sample_size")
    if n is not None:
        out["sample_size"] = n
    if leg.get("sample_hit_rate") is not None:
        out["sample_hit_rate"] = leg["sample_hit_rate"]
    return out


def annotate(singles: Sequence[dict[str, Any]]) -> int:
    """Put `peer` on every printed leg that has a peer, in place; return how
    many legs carry it. `peer`: `preferred`, `peers` (how many other variables
    within the band), `best` (the surest peer or the leg itself), `d_confidence`
    (this leg minus the best, 0 when preferred), `band`."""
    by_match: dict[str, list[dict[str, Any]]] = {}
    for leg in singles:
        leg.pop("peer", None)
        if _odds(leg) is not None and leg.get("confidence") is not None:
            by_match.setdefault(group_key(leg), []).append(leg)
    marked = 0
    for legs in by_match.values():
        if len(legs) < 2:
            continue
        for leg in legs:
            o = float(_odds(leg) or 0.0)
            var = _variable(leg)
            best_of: dict[str, dict[str, Any]] = {}
            for other in legs:
                other_var = _variable(other)
                if other_var == var:
                    continue
                if abs(float(_odds(other) or 0.0) - o) > PEER_BAND + 1e-9:
                    continue
                cur = best_of.get(other_var)
                if cur is None or coupon_sort_key(other) < coupon_sort_key(cur):
                    best_of[other_var] = other
            if not best_of:
                continue
            surest = min(best_of.values(), key=coupon_sort_key)
            preferred = coupon_sort_key(leg) < coupon_sort_key(surest)
            top = leg if preferred else surest
            leg["peer"] = {
                "preferred": preferred,
                "peers": len(best_of),
                "best": _view(top),
                "d_confidence": round(
                    float(leg["confidence"]) - float(top["confidence"]), 4),
                "band": [round(o - PEER_BAND, 2), round(o + PEER_BAND, 2)],
            }
            marked += 1
    return marked


def label(leg: Mapping[str, Any]) -> str:
    """The note the page prints under a leg (plain text, Polish), or ''."""
    peer = leg.get("peer")
    if not peer:
        return ""
    k = int(peer["peers"])
    if peer["preferred"]:
        return (f"★ najpewniejsza z {k + 1} nóg tego meczu w pasie kursu "
                f"{peer['band'][0]:.2f}–{peer['band'][1]:.2f}")
    best = peer["best"]
    sub = f" {best['subject']}" if best.get("subject") else ""
    pos = f" #{best['position']}" if best.get("position") else ""
    return (f"słabsza o {abs(float(peer['d_confidence'])):.3f} niż ★{pos} "
            f"{best['market']}{sub} {best['line']} {best['direction']} "
            f"(kurs {best['odds']})")
