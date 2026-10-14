"""Football 1X2 (home / away win) and draw no bet from the pure rating, with
a season-phase curve class - behind ``epochs.FOOTBALL_RESULT_1X2_DNB_FROM_UTC``
(``epochs.football_result_1x2_dnb``); off (None), nothing here is reached and
OFFER / SHEET / CONFIDENCE are what they were.

Evidence: docs/sofa/evidence/football_1x2_dnb_phase_2026-10-15.md (the curve
fitted per class on the history before 2026-09-01, gated one-sided on
2026-09-01..2026-10-13, scripts/sofa/fit_result_1x2_dnb_curve.py); why a
phase class: docs/sofa/evidence/football_result_phase_2026-10-13.md (the
history curve overstated DNB at the season start while the raw NB p was
calibrated).

Shape. Superbet posts the full-match result as "Mecz" ("1" / "X" / "2") and
draw no bet as "Zakład bez remisu" with the two TEAM NAMES as selections
(tests/sofa/golden/offer_mappable_items.json, Villarreal - Napoli: 1.59 /
2.25); the halves ("1.połowa - zakład bez remisu") are other questions.

    result_1x2   subject "1" / "2" (home / away win), line 0.5, OVER only:
                 OVER = "Mecz" "1" / "2"; UNDER = the double chance that
                 leaves it out ("Podwójna szansa" "X2" / "1X") - the rung's
                 complement, so the ladder margin judges it. Only the OVER is
                 priced (the UNDER is the double chance's own row).
    draw_no_bet  subject "1", line 0.5, two-sided: OVER = the home side,
                 UNDER = the away side - one rung of the two DNB prices, so
                 each side reads its own curve (``draw_no_bet|OVER`` /
                 ``|UNDER``) and the margin is the DNB book's.

Which DNB selection is the home side: the selection name is a team name; it
is matched against the board's home / away names (``market_mapper.fold``,
equal or one containing the other), and a selection matching neither or
both is dropped (never guessed).

Price. P from independent NB goals on the PURE rating centres
(``football_result.result_probs``, r from config/sofa_football_result.json):
result_1x2 "1" = P(home win); draw_no_bet OVER = P(home | no draw) =
h / (h + a), UNDER = a / (h + a).

Confidence. Both are rating-only markets (own curve or nothing). A men's
match whose as-of season phase (``season_phase.SeasonPhaseIndex.phase``) is
``early`` reads the class ``season_early`` (``curve_class``); a women's
match the class ``women``; every other men's match the unclassed curve.

Settlement. Regular time (90 minutes + added time), like the double chance
(``metrics.regulation_score``). A DNB draw is a refund: the leg is VOID
(``metrics.result_1x2_dnb_value`` returns None on a draw and SETTLE names it
``DNB_DRAW_REFUND``).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from bet.sofa.football_result import result_probs
from bet.sofa.market_mapper import fold
from bet.sofa.season_phase import PHASE_EARLY

RESULT_1X2 = "result_1x2"
DRAW_NO_BET = "draw_no_bet"
MARKETS = frozenset({RESULT_1X2, DRAW_NO_BET})
LINE = 0.5
RESULT_SIDES = ("1", "2")
DNB_SUBJECT = "1"  # the DNB rung: OVER home, UNDER away
# The double chance selection that leaves a 1X2 outcome out (the UNDER of
# result_1x2 "1" / "2").
COMPLEMENT_DC = {"1": "X2", "2": "1X"}
_RESULT_BY_DC = {v: k for k, v in COMPLEMENT_DC.items()}

CLASS_SEASON_EARLY = "season_early"
CLASS_WOMEN = "women"

# The note and row marker a row carries.
NOTE = "FOOTBALL_RESULT_1X2_DNB"
RULE_FIELD = "result_1x2_dnb_rule"
# The refund reason SETTLE writes for a drawn DNB leg.
DNB_DRAW_REFUND = "DNB_DRAW_REFUND"

_MECZ = "mecz"
_DC = "podwojna szansa"
_DNB = "zaklad bez remisu"


def classify(
    market_name: str | None, selection_name: str | None,
    home: str | None = None, away: str | None = None,
) -> list[tuple[str, str, float, str]]:
    """Every (market, subject, line, OVER/UNDER) one Superbet odd feeds:
    "Mecz" 1 / 2 -> result_1x2 OVER; "Podwójna szansa" X2 / 1X -> the
    result_1x2 UNDER; "Zakład bez remisu" <home> / <away> -> draw_no_bet
    OVER / UNDER (`home` / `away` are the board's side names). [] for
    anything else."""
    folded = fold(market_name)
    sel = str(selection_name or "").strip()
    if folded == _MECZ and sel in RESULT_SIDES:
        return [(RESULT_1X2, sel, LINE, "OVER")]
    if folded == _DC and sel.upper() in _RESULT_BY_DC:
        return [(RESULT_1X2, _RESULT_BY_DC[sel.upper()], LINE, "UNDER")]
    if folded == _DNB:
        side = dnb_side(sel, home, away)
        if side is not None:
            return [(DRAW_NO_BET, DNB_SUBJECT, LINE,
                     "OVER" if side == "1" else "UNDER")]
    return []


def is_market(market_name: str | None) -> bool:
    return fold(market_name) in (_MECZ, _DC, _DNB)


def dnb_side(selection: str, home: str | None, away: str | None) -> str | None:
    """"1" / "2" when the selection names exactly one board side, else None."""
    s = fold(selection)
    if not s:
        return None

    def same(name: str | None) -> bool:
        n = fold(name)
        return bool(n) and (n == s or n in s or s in n)

    h, a = same(home), same(away)
    if h == a:
        return None
    return "1" if h else "2"


def probabilities(lh: float, la: float, r: float) -> dict[str, float]:
    """P of every priced selection: result_1x2 "1" / "2", DNB home / away."""
    pr = result_probs(lh, la, r)
    h, a = pr["1"], pr["2"]
    return {"1x2:1": h, "1x2:2": a,
            "dnb:1": h / (h + a), "dnb:2": a / (h + a)}


def row_p(market: str, subject: str, direction: str,
          probs: dict[str, float]) -> float | None:
    """The p of one (market, subject, direction) row, None when not priced."""
    if market == RESULT_1X2 and direction == "OVER" and subject in RESULT_SIDES:
        return probs[f"1x2:{subject}"]
    if market == DRAW_NO_BET and subject == DNB_SUBJECT:
        return probs["dnb:1" if direction == "OVER" else "dnb:2"]
    return None


def outcome(market: str, subject: str, direction: str,
            home_goals: float, away_goals: float) -> int | None:
    """1 won / 0 lost on the 90-minute score; None = a DNB draw (refund)."""
    if market == RESULT_1X2:
        if subject not in RESULT_SIDES:
            raise ValueError(f"not a 1X2 side: {subject!r}")
        won = (home_goals > away_goals if subject == "1"
               else away_goals > home_goals)
        return int(won) if direction == "OVER" else int(not won)
    if market == DRAW_NO_BET:
        if home_goals == away_goals:
            return None
        home_won = home_goals > away_goals
        return int(home_won if direction == "OVER" else not home_won)
    raise ValueError(f"not a 1X2 / DNB market: {market!r}")


def curve_class(women: bool, phase: str | None) -> str | None:
    """The calibration class a leg reads: women, else season_early for an
    early-phase men's match, else None (the unclassed curve)."""
    if women:
        return CLASS_WOMEN
    if phase == PHASE_EARLY:
        return CLASS_SEASON_EARLY
    return None


def note(market: str, subject: str, direction: str, p: float, lh: float,
         la: float, r: float, phase: str | None) -> str:
    what = (f"1X2 {subject} win" if market == RESULT_1X2
            else f"draw no bet {'home' if direction == 'OVER' else 'away'}")
    return (f"{NOTE}: {what} p {p:.4f} from NB goals (r {r:g}) on the pure "
            f"rating centres home {lh:.3f} / away {la:.3f}; season phase "
            f"{phase or 'none'}; no sample, no price "
            "(epochs.FOOTBALL_RESULT_1X2_DNB)")


def leg_class(row: Mapping[str, Any], klass: str | None) -> str | None:
    """The curve class CONFIDENCE reads a sheet row with: `klass`
    (confidence.match_class) for every row, except a men's 1X2 / DNB row
    SHEET priced under the switch (`result_1x2_dnb_rule`) in an early-phase
    fixture (`result_phase`), which reads CLASS_SEASON_EARLY. A row without
    the marker (the switch off) is untouched."""
    if (klass is None and row.get("market") in MARKETS
            and row.get(RULE_FIELD) and row.get("result_phase") == PHASE_EARLY):
        return CLASS_SEASON_EARLY
    return klass
