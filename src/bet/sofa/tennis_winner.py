"""Tennis match winner ("Zwycięzca") from the as-of rating - audit 2026-10-13 D2.

Behind ``epochs.TENNIS_MATCH_WINNER_FROM_UTC`` (``epochs.tennis_match_winner``);
off, nothing here is reached and OFFER / SHEET / CONFIDENCE are what they were.

Shape. Superbet posts the tennis winner as one market "Zwycięzca" with two
selections, "1" and "2" - the first and second name of the listing's own
``matchName`` (tests/sofa/golden/offer_mappable_items.json, Zverev - Bublik).
It is read as ONE two-sided rung so the ladder margin (``confidence.overround``)
judges it like every other leg:

    market  ``match_won_for``   the subject's matches won in this match
    subject the listing's FIRST name (selection "1")
    line    0.5
    OVER    the subject wins  (selection "1"'s price)
    UNDER   the subject loses = the other player wins (selection "2"'s price)

SETTLE grades it like any per-side metric (``metrics.extract_metric``, the
listing's ``winnerCode``); a retirement, a walkover, a cancellation are
refunds before any grade (``settle.REFUND_REASONS``).

Price. ``p_central`` is the rating's own probability of the side winning
(``MatchForecast.p_side_wins``): the logistic of the Elo features SHEET
already computes, never blended with a price. There is no sample behind it -
the sample gates of CONFIDENCE (extremum, mode, size, age) are about count
samples and the curve was not fitted under them, so a rating-only market
skips them (``RATING_ONLY_MARKETS``). The confidence is the market's own
history curve (``match_won_for`` in by_market, women in
by_class.tennis_women), fitted on the replay of the as-of rating by
scripts/sofa/fit_tennis_winner_curve.py, read from its own curve only
(``confidence.OWN_CURVE_ONLY``), then line evidence as for every key.
Evidence: docs/sofa/evidence/tennis_match_winner_2026-10-13.md.
"""

from __future__ import annotations

from collections.abc import Sequence

from bet.sofa.football_result import DOUBLE_CHANCE
from bet.sofa.market_mapper import fold

MATCH_WON_FOR = "match_won_for"
WINNER_LINE = 0.5
# Markets priced by a rating alone, with no sample behind them: SAMPLES does
# not build one, SHEET needs none, CONFIDENCE's sample gates do not apply,
# no pool stands in for their curve (confidence.OWN_CURVE_ONLY). The football
# double chance (bet.sofa.football_result, epochs.FOOTBALL_RESULT_MARKETS) is
# one too; without that switch no such rung or row exists.
RATING_ONLY_MARKETS = frozenset({MATCH_WON_FOR, DOUBLE_CHANCE})
# The sheet note a winner row carries (and the rule it was priced under).
WINNER_NOTE = "TENNIS_MATCH_WINNER"

_WINNER_MARKET = "zwyciezca"
_SELECTION_DIRECTION = {"1": "OVER", "2": "UNDER"}


def classify_winner(
    market_name: str | None,
    selection_name: str | None,
    listing_names: Sequence[str],
) -> tuple[str, str, float, str] | None:
    """(match_won_for, first name, 0.5, OVER / UNDER) for one odd of the
    tennis "Zwycięzca" market, or None.

    Only the bare market name and the selections "1" / "2": "Zwycięzca &
    każdy z graczy wygra seta", "Zwycięzcy setów" and the set winners are
    other questions. Without both listing names the subject is unknown and
    nothing is guessed."""
    if fold(market_name) != _WINNER_MARKET:
        return None
    direction = _SELECTION_DIRECTION.get(fold(selection_name))
    if direction is None:
        return None
    names = [n for n in listing_names if n]
    if len(names) != 2:
        return None
    return (MATCH_WON_FOR, names[0], WINNER_LINE, direction)


def winner_p(p_side: float, direction: str) -> float:
    """P(selection wins) for a side that wins the match with ``p_side``."""
    return p_side if direction == "OVER" else 1.0 - p_side


def winner_note(p_side: float, side: str, rated_home: int, rated_away: int,
                table_scope: str) -> str:
    who = "home" if side == "side_a" else "away"
    return (
        f"{WINNER_NOTE}: rating p {p_side:.4f} that the {who} player wins "
        f"(MatchForecast.p_side_wins, no price), rated matches "
        f"{rated_home}/{rated_away}, table {table_scope}; no sample - the "
        "confidence is the match_won_for history curve "
        "(epochs.TENNIS_MATCH_WINNER)"
    )
