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
#
# Since 2026-09-06 an optional fourth key, ``"players"``, carries one box score
# per provider player id: ``{"9595": {"player_total_shots": 3.0, ...,
# "minutes_played": 90.0}}``. It is nested one level deeper than the three
# above, which is why ``Actuals`` is typed loosely -- see ``actual_value``.
#
# Why it had to exist. Player props are the largest family on the coupon file
# (6 of the 15 singles shipped on 2026-09-05, 15 of the 37 rows ever marked
# VALUE) and **not one of them had ever been settled**: bzzoiro's
# ``/events/{id}/stats/`` carries no player block, so every prop returned
# NO_DATA on every backtest since this module was written. Every constant the
# pipeline tunes -- the shrink k, the tier margins, the rung penalties -- was
# therefore fitted on the ~57% of the file that is not a prop, and the family
# that dominates it had no feedback loop at all.
Actuals = dict[str, dict]


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


# Markets that belong to one side even though their name carries no ``_for``.
#
# Only tennis's per-player games. The canonical name really is ``games_won``
# -- that is what tennis-abstract emits and what ``_SIDE_SPLIT_AS`` maps
# espn-tennis's per-side figure onto, and ``total_games_for`` does not exist in
# the vocabulary -- so the suffix rule alone reads it as a match total. That
# would settle "Lilli Tagger games_won OVER 6.5" against the *match's* 22
# games instead of her 9, scoring a straight-sets defeat as a win, on all 438
# such rows in the four slates on disk.
_PER_SIDE_MARKETS = frozenset({"games_won"})

# Every market whose subject is one footballer rather than a team or a match.
# The vocabulary is bzzoiro's ``PLAYER_STAT_MAP`` canonical names, and the
# prefix is what the pipeline itself uses to separate the family everywhere
# else, so testing on it here needs no second list to drift from.
PLAYER_MARKET_PREFIX = "player_"

# A prop leg is void, not lost, when the player did not take the field --
# Superbet returns the stake. NO_DATA is this module's "stake returned and it
# tells us nothing about the sheet", and that is exactly the right accounting:
# a row excluded from the hit rate and from the staked total, rather than a
# loss charged against a forecast that never got to be wrong.
#
# Two shapes both mean it. He is absent from the box score entirely (not in
# the squad, or the feed never listed him), or he is in it with zero minutes
# (an unused substitute, whose box score is a full row of zeroes and would
# otherwise settle every OVER as a loss and every UNDER as a win).
MINUTES_PLAYED = "minutes_played"


def player_value(
    actuals: Actuals, market: str, player_id: str | None
) -> float | None:
    """One player's figure for one prop market, or None when he did not play.

    Joined on the **provider player id** and never on a name. The coupon file
    already refuses a row whose surname is shared by two players in the fixture
    (``ambiguous_player_name``, 25 rows on 2026-09-05 alone); resolving a box
    score by name here would reintroduce exactly that ambiguity at the one
    point where getting it wrong looks like measured evidence rather than a
    gap. No id, no settlement.
    """
    if not player_id:
        return None
    players = actuals.get("players")
    if not isinstance(players, dict):
        return None
    box = players.get(str(player_id))
    if not isinstance(box, dict):
        return None
    try:
        minutes = float(box.get(MINUTES_PLAYED) or 0.0)
    except (TypeError, ValueError):
        minutes = 0.0
    if minutes <= 0:
        return None
    value = box.get(market)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# Metrics the provider omits from a match's statistics when the count was zero,
# rather than reporting a zero.
#
# ``red_cards`` is the one measured case. ``providers`` already records the
# finding for the *sample* path -- "``red_cards`` is absent from
# ``/events/{id}/stats/`` on a match with no red card ... measured over 80
# historical fixtures on 2026-09-03: 51 carried no ``red_cards`` field and the
# incidents feed confirmed zero reds in all 51" -- and the settlement path never
# learned it.
#
# What that cost. Over the 507 cached fixtures that carry a real statistics
# block, ``red_cards_total`` is present on 95 and 66 of those had a red. Read as
# "absent means unknown", the family settles **only on matches that had a red
# card**: every UNDER that would have won returns NO_DATA and every LOST one
# settles. It is missing-not-at-random in the single worst direction, and it is
# what made a bias sweep on 2026-09-06 report the sample as undercounting reds
# by a factor of two (0.35 claimed against 0.73 "actual") when the sample was
# right and the measurement was conditioned on the event having happened.
#
# Guarded by ``_has_statistics_block``: absence only means zero when the
# provider published statistics for the fixture at all. A fixture it published
# nothing for is a coverage gap and still settles NO_DATA.
ABSENT_MEANS_ZERO = frozenset(
    {
        "red_cards_total",
        "red_cards_1h_total",
        "red_cards_2h_total",
    }
)

# Any one of these present is proof the provider answered for this fixture.
# Deliberately metrics with no zero-omission behaviour of their own: every one
# of the 507 fixtures with a statistics block carries all three, and a match
# genuinely played with zero shots does not exist.
_STATISTICS_BLOCK_MARKERS = ("shots_total", "fouls_total", "corners_total")


def _has_statistics_block(actuals: Actuals) -> bool:
    """Whether the provider published match statistics for this fixture at all."""
    total = actuals.get("total")
    if not isinstance(total, dict):
        return False
    return any(total.get(marker) is not None for marker in _STATISTICS_BLOCK_MARKERS)


def actual_value(
    actuals: Actuals, market: str, side: str | None, player_id: str | None = None
) -> float | None:
    """The figure this row settles against, or None when it was not reported.

    A per-side market needs the side; a ``*_total`` market must **not** use one
    (every match has one home and one away side, so the total is neither), and
    asking for a total under a side key is the mistake that would silently
    settle "corners_total OVER 9.5" against one team's five corners.

    Per-side means ``*_for`` *or* one of ``_PER_SIDE_MARKETS`` -- see there for
    why the suffix is not sufficient.

    A ``player_*`` market is neither: it settles against one person's box score
    and needs ``player_id``. Passing one without the other returns None rather
    than falling through to the match total, which is the mistake that would
    score "Fullkrug fouls over 0.5" against the match's 23.
    """
    if market.startswith(PLAYER_MARKET_PREFIX):
        return player_value(actuals, market, player_id)
    if market.endswith("_for") or market in _PER_SIDE_MARKETS:
        if side is None:
            return None
        value = actuals.get(side, {}).get(market)
    else:
        value = actuals.get("total", {}).get(market)
    if value is None:
        if market in ABSENT_MEANS_ZERO and _has_statistics_block(actuals):
            return 0.0
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
    player_id: str | None = None,
) -> tuple[Outcome, float | None]:
    """``(outcome, actual value)`` for one sheet or coupon row.

    ``player_id`` is required by, and only used by, the ``player_*`` family.
    A prop row that reaches here without one settles NO_DATA -- see
    ``player_value`` for why a name is not accepted as a substitute.
    """
    if market.startswith(PLAYER_MARKET_PREFIX):
        value = player_value(actuals, market, player_id)
        return settle(direction, line, value), value
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
