"""A Sofascore tennis set score, read as games.

Sofascore puts a 10-point match tiebreak - the super tiebreak that replaces
the deciding set in ITF, UTR, Davis Cup and exhibition formats - in the same
`periodN` field as a set, with no marker: 6-4 6-7(3) 10-5 is
`period3 = 10 / 5` (event 16498311). Summing periods as games then reads
that match as 22 games won by the winner instead of 13.

Measured 2026-09-29 over the cached singles history: every set scored above
7 is either such a deciding match tiebreak (3,281 ITF matches, 5.1% of ITF
singles and 12.3% of ITF three-setters) or a UTS exhibition quarter, which is
not a set at all. No advantage set (8-6, 10-8 played out in games) occurs.

Sofascore's own `gamesWon` statistic counts the match tiebreak as ONE game
(e.g. 7 : 8 after 6-1 0-6 and a tiebreak); so does bet365's rule. Superbet's
rule for games markets is UNVERIFIED - its general regulamin does not state
it - so this follows the statistic the rest of the pipeline already reads.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# The winner of a match tiebreak reaches at least 10 points; a real set ends
# at 7 at most (tiebreak at 6-6 in every format Superbet prices).
MATCH_TIEBREAK_MIN_POINTS = 10
MAX_SET_GAMES = 7


def is_match_tiebreak(sets: list[tuple[int, int]], index: int) -> bool:
    """Is sets[index] a deciding 10-point match tiebreak rather than a set?

    Only the third set of a match level at one set all can be one.
    """
    if index != 2 or len(sets) != 3:
        return False
    first, second = sets[0], sets[1]
    level = (first[0] > first[1]) != (second[0] > second[1])
    h, a = sets[2]
    return level and max(h, a) >= MATCH_TIEBREAK_MIN_POINTS and h != a


def set_games(
    home_score: Mapping[str, Any], away_score: Mapping[str, Any]
) -> list[tuple[int, int]] | None:
    """Games per set, a match tiebreak counted as one game to its winner.

    None when the score is not a set score at all (a UTS quarter, a value
    that is not an integer): an unreadable score produces no observation
    rather than a wrong one.
    """
    raw: list[tuple[int, int]] = []
    for i in range(1, 6):
        key = f"period{i}"
        if key in home_score and key in away_score:
            try:
                raw.append((int(home_score[key]), int(away_score[key])))
            except (TypeError, ValueError):
                return None
    out: list[tuple[int, int]] = []
    for i, (h, a) in enumerate(raw):
        if max(h, a) <= MAX_SET_GAMES:
            out.append((h, a))
        elif is_match_tiebreak(raw, i):
            out.append((1, 0) if h > a else (0, 1))
        else:
            return None
    return out


def match_tiebreak_sets(
    home_score: Mapping[str, Any], away_score: Mapping[str, Any]
) -> set[int]:
    """1-based indices of the sets that were match tiebreaks."""
    raw: list[tuple[int, int]] = []
    for i in range(1, 6):
        key = f"period{i}"
        if key in home_score and key in away_score:
            try:
                raw.append((int(home_score[key]), int(away_score[key])))
            except (TypeError, ValueError):
                return set()
    return {i + 1 for i in range(len(raw)) if is_match_tiebreak(raw, i)}
