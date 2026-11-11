"""Lesser-loss legs: a printed single whose Superbet market carries a low
margin, whose confidence sits close to its price and whose own sample is long.

Annotation only (epochs.LESSER_LOSS_MARK_FROM_UTC, operator 2026-11-11: "chcę
mieć to zaznaczane na kuponie"): no leg is added, removed or re-ranked, no
confidence moves, nothing reads it to decide a read, a veto or a builder.

Measured 2026-11-11 on the printed singles of 10-30..11-10 graded in
13_results.json (64,546 legs, before the 12% tax): ten leg fields were cut
into quintiles on 10-30..11-04 (dev) and the same cuts read on 11-05..11-10
(hold-out). Three separated legs at one price in both halves - the market's
overround, confidence minus 1/odds and the sample length; the thresholds
below are the dev quintile edges, frozen. Legs passing all three:
dev -3.2% [-5.9, -0.4] (1,569 legs / 628 matches), hold-out -1.7%
[-4.6, +1.0] (1,579 / 580) against -5.4% / -5.1% for every leg. Chosen from
ten fields, so part of it may be selection; judged forward by
T-LESSER-LOSS-flag (config/sofa_test_registry.json).

A marked leg at confidence >= 0.85 is the "pewna" tier (operator 2026-11-11:
"lepiej mieć mniejszą cenę ale stabilny system wygrywania"): dev 312 legs /
237 matches 90.1% won, ROI +0.6% [-3.2, +4.2]; hold-out 332 / 231, 90.4%,
+0.6% [-3.1, +3.9] (before the tax). The 0.85 edge was chosen after both
halves were seen - the forward test is its only honest judge. The plain mark
is still a loss before the tax, and every tier is about -11..-14% after it -
the mark says "loses less" / "wins more often", never "has an edge".
docs/sofa/evidence/mniej_zle_nogi_2026-11-11.md.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

RULE = "lesser_loss_v1"
# Frozen 2026-11-11 (dev quintile edges, never refitted on the hold-out).
MAX_OVERROUND = 0.086
MIN_CONFIDENCE_MINUS_PRICE = -0.047
MIN_SAMPLE = 20
# The "pewna" tier: a marked leg at this confidence or above (2026-11-11,
# chosen after the halves were seen; T-LESSER-LOSS-flag judges it forward).
STRONG_MIN_CONFIDENCE = 0.85

# The measurement the sentence quotes (before the tax).
HOLDOUT_ROI_PCT = -1.7
HOLDOUT_ROI_CI_PCT = (-4.6, 1.0)
ALL_LEGS_ROI_PCT = -5.1
WINDOW_PL = "11-05..11-10"
STRONG_HIT_PCT = 90.4
STRONG_ROI_PCT = 0.6
STRONG_ROI_CI_PCT = (-3.1, 3.9)


def annotate(leg: Mapping[str, Any]) -> dict[str, Any] | None:
    """The mark of one printed single, or None when it misses a threshold
    or lacks a field (a one-sided market has no overround: never marked)."""
    overround = leg.get("overround")
    odds = leg.get("offered_odds")
    confidence = leg.get("confidence")
    sample = leg.get("sample_size")
    if overround is None or odds is None or confidence is None or sample is None:
        return None
    try:
        ovr = float(overround)
        price = float(odds)
        conf = float(confidence)
        n = int(sample)
    except (TypeError, ValueError):
        return None
    if price <= 1.0:
        return None
    d = conf - 1.0 / price
    if ovr >= MAX_OVERROUND or d < MIN_CONFIDENCE_MINUS_PRICE or n < MIN_SAMPLE:
        return None
    return {
        "rule": RULE,
        "tier": "pewna" if conf >= STRONG_MIN_CONFIDENCE else "mniej_zla",
        "overround": round(ovr, 4),
        "confidence_minus_price": round(d, 4),
        "sample_size": n,
    }


def _pl(x: float, fmt: str = ".1f") -> str:
    return format(x, fmt).replace(".", ",").replace("-", "−")


def label(leg: Mapping[str, Any]) -> str:
    """The Polish sentence the PDF / HTML show beside a marked leg."""
    m = leg.get("lesser_loss")
    if not isinstance(m, Mapping):
        return ""
    head = (f"marża {_pl(100 * float(m['overround']))}%, pewność "
            f"{_pl(100 * float(m['confidence_minus_price']), '+.1f')} pp od "
            f"ceny, próbka {int(m['sample_size'])}")
    if m.get("tier") == "pewna":
        lo, hi = STRONG_ROI_CI_PCT
        return (f"PEWNA mniej zła noga ({head}, pewność >= 0,85) - takie nogi "
                f"wchodziły w {_pl(STRONG_HIT_PCT)}%, ROI "
                f"{_pl(STRONG_ROI_PCT, '+.1f')}% [{_pl(lo, '+.1f')}; "
                f"{_pl(hi, '+.1f')}] ({WINDOW_PL}, przed podatkiem; próg 0,85 "
                f"wybrany po obejrzeniu danych - test na przyszłych dniach)")
    lo, hi = HOLDOUT_ROI_CI_PCT
    return (f"mniej zła noga ({head}) - takie nogi traciły "
            f"{_pl(HOLDOUT_ROI_PCT, '+.1f')}% [{_pl(lo, '+.1f')}; "
            f"{_pl(hi, '+.1f')}] wobec {_pl(ALL_LEGS_ROI_PCT, '+.1f')}% "
            f"wszystkich ({WINDOW_PL}, przed podatkiem) - nadal strata, "
            f"nie przewaga")
