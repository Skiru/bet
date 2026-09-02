"""What actually happened to a row, and what that says about the sheet.

The pipeline's whole claim is that ``p_low`` is a *lower bound* on a row's win
probability. Nothing in it checked that claim until this module existed: the
2026-09-01 losses were found by reading eight screenshots by hand, and eight
screenshots is the entire ledger. The dossiers, event lists and coupon files for
every past run are on disk, and every one of those fixtures has since been
played -- so the claim is checkable over hundreds of rows rather than seven, and
with certainty rather than by inference.

Pure on purpose: no network, no clock, no DB. ``actuals`` is handed in as the
provider already reports it (``providers._bzzoiro_match_stats`` returns exactly
this shape), so a settlement can be re-run months later from a recorded
artifact, and the arithmetic here can be tested without a fixture that pretends
to be an API. ``scripts/simple/backtest_slate.py`` is the part that fetches.

Push is a real outcome and not a rounding detail. Superbet posts whole-number
lines on several markets (corners 9, cards 4, goals 3), a stake is returned when
the count lands exactly there, and scoring one as a loss would understate every
configuration that reaches those lines -- so ``PUSH`` is its own verdict and is
excluded from hit rate rather than counted against it.
"""
from __future__ import annotations

from typing import Literal

from bet.simple_stats.providers import _normalize_team_name, _team_matches

Outcome = Literal["WON", "LOST", "PUSH", "NO_DATA"]

# ``{"home": {...}, "away": {...}, "total": {...}}``, each keyed by canonical
# metric name -- ``*_for`` names under the two sides, ``*_total`` names under
# "total". That is ``_bzzoiro_match_stats``'s own return shape, unchanged.
Actuals = dict[str, dict[str, float]]


def team_side(
    team_name: str | None, home_team: str | None, away_team: str | None
) -> str | None:
    """"home"/"away" for a per-team row's subject, or None if it is not decidable.

    Matched with ``providers._team_matches``, the pipeline's own team-identity
    test, rather than with a plain normalized-string equality: the coupon file
    carries our spelling and the event list the provider's, and they differ by
    a club prefix or suffix often enough to matter ("KS Lechia Gdansk" against
    "Lechia Gdansk", "Manchester Utd" against "Manchester United"). Exact
    equality left those unsettled; ``_team_matches`` is already hardened
    against the direction that would be far worse here, a fragment carrying a
    whole name ("Botafogo-SP" does not match "Botafogo RJ").

    **A name that matches both sides returns None.** In a settlement a false
    positive is not a missing row, it is a row scored against the wrong team
    while looking exactly like evidence -- so an ambiguous match is refused,
    the same rule ``_opponent_of`` follows for the same reason.
    """
    if not team_name:
        return None
    wanted = _normalize_team_name(team_name)
    matches_home = bool(home_team) and _team_matches(
        wanted, _normalize_team_name(home_team or "")
    )
    matches_away = bool(away_team) and _team_matches(
        wanted, _normalize_team_name(away_team or "")
    )
    if matches_home and not matches_away:
        return "home"
    if matches_away and not matches_home:
        return "away"
    return None


def actual_value(
    actuals: Actuals, market: str, side: str | None
) -> float | None:
    """The figure this row settles against, or None when it was not reported.

    A ``*_for`` market needs the side; a ``*_total`` market must **not** use one
    (every match has one home and one away side, so the total is neither), and
    asking for a total under a side key is the mistake that would silently
    settle "corners_total OVER 9.5" against one team's five corners.
    """
    if market.endswith("_for"):
        if side is None:
            return None
        value = actuals.get(side, {}).get(market)
    else:
        value = actuals.get("total", {}).get(market)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def settle(direction: str, line: float, value: float | None) -> Outcome:
    """One bet's outcome at one line.

    ``value is None`` is ``NO_DATA`` and never ``LOST``. A market the provider
    did not report is a coverage gap in *this* module, not a failed bet, and
    folding the two together would make every configuration look worse in
    proportion to how many exotic markets it reached.
    """
    if value is None:
        return "NO_DATA"
    if value == line:
        return "PUSH"
    if direction == "OVER":
        return "WON" if value > line else "LOST"
    if direction == "UNDER":
        return "WON" if value < line else "LOST"
    return "NO_DATA"


def settle_row(
    *,
    market: str,
    line: float,
    direction: str,
    actuals: Actuals,
    team_name: str | None = None,
    home_team: str | None = None,
    away_team: str | None = None,
) -> tuple[Outcome, float | None]:
    """``(outcome, actual value)`` for one sheet or coupon row."""
    side = team_side(team_name, home_team, away_team) if team_name else None
    if team_name and side is None:
        return "NO_DATA", None
    value = actual_value(actuals, market, side)
    return settle(direction, line, value), value


def hit_rate(outcomes: list[Outcome]) -> tuple[int, int, float | None]:
    """``(won, decided, rate)`` -- pushes and gaps excluded from both.

    ``None`` when nothing was decided, rather than 0.0: a configuration that
    emitted ten rows and could settle none of them has an unknown hit rate, and
    printing 0% for it would read as ten losses.
    """
    won = sum(1 for o in outcomes if o == "WON")
    decided = won + sum(1 for o in outcomes if o == "LOST")
    if decided == 0:
        return won, 0, None
    return won, decided, won / decided


def profit(
    outcomes: list[Outcome], prices: list[float | None], stake: float = 1.0
) -> tuple[float, float, int]:
    """``(staked, returned, priced)`` at flat stakes.

    A row with no price is skipped entirely rather than staked at evens: the
    single most common reason a row has no price is that Superbet never posted
    its line, and a bet that could not be placed must not appear in the return
    of a strategy either way. ``PUSH`` returns the stake, which is what the book
    does.
    """
    staked = returned = 0.0
    priced = 0
    for outcome, price in zip(outcomes, prices):
        if price is None or outcome == "NO_DATA":
            continue
        priced += 1
        staked += stake
        if outcome == "WON":
            returned += stake * price
        elif outcome == "PUSH":
            returned += stake
    return staked, returned, priced
