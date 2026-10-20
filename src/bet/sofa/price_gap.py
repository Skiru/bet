"""A confidence above the price - a flag on the leg, never a gate.

Operator, 2026-10-12 (after the 10-11 slips: about 23 of his 33 singles were
legs whose confidence sat well above Superbet's price): show it on the leg,
change nothing else.

Measured (scripts/sofa/measure_price_gap.py, printed football / tennis singles
of 2026-10-09..10-11, match bootstrap): a leg whose confidence exceeds 1/odds
by more than GAP realised below its confidence - football 458 legs in 269
matches, -6.8 pp [-12.0, -2.1]; tennis 52 legs in 35 matches, -18.6 pp
[-31.0, -5.9] - and about at its price; the other printed legs were calibrated
(football +0.3 pp [-1.4, +1.9], 3,830 legs). The same sign on every day of
10-07..10-11 (-18, -10, -12, -8, -5 pp) and in every disagreement bin of the
settled sheet rows the line evidence is fitted on.

Their ROI was not measurably worse (football -1.1% [-8.2, +5.2] against
-3.8% for the rest; tennis -16.0% [-35.0, +2.6], 52 legs): it is the printed
number that over-promises, which matters to a reader who multiplies
confidences into a slip. Neither cure measured out of sample earned a place
(walk-forward 10-09..10-11, evidence fitted on the days before each test day,
docs/sofa/evidence/price_gap_2026-10-12.md): a stricter price-band cap dropped
15% of the legs (4,595 -> 3,896), which had NOT done worse (ROI -0.6% against
-4.4% kept), and left the flagged group at -6.8 pp (from -8.0); an offset per
disagreement bin corrected half of it (-9.4 -> -5.1 pp on the legs it lowered)
and dropped 178 legs that had not done worse either (+2.2% against -4.0%).
So the leg says it, and nothing moves: no leg is added, removed or re-ranked
and no confidence changes (epochs.PRICE_GAP_FLAG_FROM_UTC).

Hockey / basketball / volleyball legs carry no flag: measured the same
way on their printed legs of 10-09..10-11 (graded by coupon_sports), hockey's
over-price legs realised at their confidence (32 legs, -1.2 pp [-15.1, +11.9];
the other 813 +0.0 pp), and basketball overstated on both sides of the price
alike (-14.9 pp on 52, -18.2 pp on 50 legs) - the flag would point at half a
problem that is not about the price; volleyball (6) too few.

CS2 carries it from epochs.CS2_PRICE_GAP_FROM_UTC (operator, 2026-10-20, after
"BBL liczba map: powyżej 0.5" @1.44 lost; that leg itself sat 0.024 above its
price and is not flagged). Its printed legs were too few (80), so it was
measured on every settled Superbet CS2 line whose model p the installed curve
puts on the coupon's floor and x (scripts/sofa/measure_cs2_price_gap.py,
09-28..10-19, series bootstrap, line evidence not applied): above the price
238 lines in 77 series realised -18.6 pp [-27.1, -10.1] below their
confidence, -2.1 pp from Superbet's de-margined price; the other 234 +2.2 pp
[-7.1, +10.7]. ROI -8.8% [-23.1, +4.9] against -0.6% - again the number, not
measurably the money. A CS2 leg is flagged only when the build asks for it
(`extra`), so a day built before the switch keeps its read order.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

FLAG = "CONFIDENCE_ABOVE_PRICE"
# Confidence minus 1/odds (the raw price, margin included) above which a leg
# is flagged; the measured group (module doc) is exactly this one.
GAP = 0.03
WINDOW = "10-09..10-11"
# sport -> (realised minus confidence in pp, its 95% interval, legs, matches)
MEASURED: dict[str, tuple[float, tuple[float, float], int, int]] = {
    "football": (-6.8, (-12.0, -2.1), 458, 269),
    "tennis": (-18.6, (-31.0, -5.9), 52, 35),
    "cs2": (-18.6, (-27.1, -10.1), 238, 77),
}
# flagged only from their own switch (epochs.price_gap_sports)
LATER_SPORTS = frozenset({"cs2"})
WINDOWS = {"cs2": "09-28..10-19"}
UNITS = {"cs2": ("linii Superbetu", "series")}
SPORT_PL = {"football": "piłka", "tennis": "tenis", "cs2": "CS2"}


def over_price(leg: Mapping[str, Any],
               extra: frozenset[str] = frozenset()) -> float | None:
    """Confidence minus 1/odds of a measured sport's leg; None otherwise. A
    LATER_SPORTS sport counts only when `extra` names it."""
    sport = leg.get("sport", "football")
    if sport not in MEASURED or (sport in LATER_SPORTS and sport not in extra):
        return None
    conf, odds = leg.get("confidence"), leg.get("offered_odds")
    if conf is None or not odds or float(odds) <= 1.0:
        return None
    return float(conf) - 1.0 / float(odds)


def annotate(leg: Mapping[str, Any],
             extra: frozenset[str] = frozenset()) -> dict[str, Any] | None:
    """The leg's `price_gap` entry, or None when it is not above its price."""
    gap = over_price(leg, extra)
    if gap is None or round(gap, 9) <= GAP:
        return None
    sport = str(leg.get("sport", "football"))
    point, (lo, hi), legs, matches = MEASURED[sport]
    return {
        "flag": FLAG,
        "over_price": round(gap, 4),
        "measured_gap_pp": point,
        "measured_ci_pp": [lo, hi],
        "measured_on": (f"{sport} {legs} {'lines' if sport in UNITS else 'legs'} / "
                        f"{matches} {UNITS.get(sport, ('', 'matches'))[1]}, "
                        f"{WINDOWS.get(sport, WINDOW)}"),
    }


def label(leg: Mapping[str, Any]) -> str:
    """The Polish sentence the PDF / HTML / md show beside the leg."""
    pg = leg.get("price_gap")
    if not pg:
        return ""
    sport = str(leg.get("sport", "football"))
    _, _, legs, _ = MEASURED.get(sport, (0.0, (0.0, 0.0), 0, 0))
    return (f"pewność {float(pg['over_price']):+.2f} ponad cenę - takie nogi "
            f"trafiały ~{abs(round(float(pg['measured_gap_pp']))):.0f} pp poniżej "
            f"pewności, około ceny ({SPORT_PL.get(sport, sport)}, {legs} "
            f"{UNITS.get(sport, ('nóg', ''))[0]} {WINDOWS.get(sport, WINDOW)})")
