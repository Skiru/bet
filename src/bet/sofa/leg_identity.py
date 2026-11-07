"""One event under two market names (audit 2026-11-07).

Superbet lists some events under more than one market: "both teams score in
at least one half: no" is "both teams score 1st half / 2nd half: No/No";
"<team> over 0.5 goals" is "<team> wins or both teams score"; "not 0-0" is
goals over 0.5, "1 or over 0.5", "2 or over 0.5" and "BTTS or over 0.5";
a hockey handicap +0.5 is the double chance; a volleyball set handicap +2.5
is "wins a set"; a best-of-3 CS2 maps handicap +1.5 is "maps over 0.5". Two
such legs are ONE bet on one outcome. Before SAME_EVENT_DEDUP both printed,
and the ledger counted the outcome twice (616 football pairs 10-15..11-06,
about 175 in the sports; scratch audit 2026-11-07).

`event_key(leg)` names the event a leg wins on, so that two legs of one
match with the same key are the same bet. It is computed by LOGIC, never
from settled rows (the rows' agreement also holds for a draw-refunded DNB,
which is not the same bet):

* football goal markets: the leg is graded, with the graders SETTLE uses
  (football_score_markets.event_mask, football_sim_markets.path_holds and
  the plain counts), on every half-time / full-time path with 0..N goals per
  team per half (and who scored first in the first half); the key is that
  outcome vector. A vector constant on the paths (a line beyond them) has
  no key;
* hockey (regulation and periods) and basketball (first half, quarters 1-3 -
  never the full game, whose handicap counts overtime and whose 1X2 does
  not, nor the second half / 4th quarter, where overtime's place in
  Superbet's handicap is not verified):
  1X2, double chance and half-goal handicaps as the set of margins
  team1 - team2 they win on;
* volleyball: winner, set handicap, "wins a set" and exact sets as the set
  of best-of-five set scores they win on;
* CS2: match winner, maps handicap, team maps and exact maps as the set of
  best-of-3 map scores - only when the leg says it is best of 3.

Anything else has no key (None) and is never deduplicated. `dedupe` keeps
one leg per (match, key): a locked leg always stays and a fresh leg of its
event goes; a fresh leg of an event a read refused goes too; among fresh
legs one already on a printed render stays, else the higher price (the same
outcome at a better price), on a tie the lower confidence (the price may
only lower a confidence), then the market name.
"""

from __future__ import annotations

import hashlib
import itertools
from collections.abc import Callable, Iterable, Mapping, Sequence
from functools import lru_cache
from typing import Any

from bet.sofa import football_score_markets as fsm
from bet.sofa import football_sim_markets as sim
from bet.sofa.football_result import KMAX
from bet.sofa.superbet_names import Sides, side_of


def _match_sides(leg: Mapping[str, Any]) -> Sides | None:
    parts = str(leg.get("match") or "").split(" - ")
    if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
        return None
    return parts[0].strip(), parts[1].strip()

REMOVED_FIELD = "removed_as_same_event"

# goals per team per half on the enumerated paths: lines on the coupon stop
# at 5.5; a leg whose outcome is constant on these paths has no key
_N = 6

# (h1, a1, h2, a2, first scorer of the first half: "1" / "2" / "nikt")
_State = tuple[int, int, int, int, str]


def _states() -> list[_State]:
    out: list[_State] = []
    for h1, a1, h2, a2 in itertools.product(range(_N + 1), repeat=4):
        if h1 + a1 == 0:
            firsts = [sim.FG1H_NONE]
        elif a1 == 0:
            firsts = ["1"]
        elif h1 == 0:
            firsts = ["2"]
        else:
            firsts = ["1", "2"]
        out.extend((h1, a1, h2, a2, f) for f in firsts)
    return out


_STATES = _states()

def _goals(s: _State) -> tuple[int, int, int, int]:
    return s[0], s[1], s[2], s[3]


_COUNT_MARKETS: dict[str, Callable[[_State], int]] = {
    "goals_total": lambda s: sum(_goals(s)),
    "goals_1h_total": lambda s: s[0] + s[1],
    "goals_2h_total": lambda s: s[2] + s[3],
}
# (first half, second half) of side 0 = home / 1 = away
_SIDE_COUNT_MARKETS: dict[str, Callable[[_State, int], int]] = {
    "goals_for": lambda s, i: _goals(s)[i] + _goals(s)[i + 2],
    "goals_1h_for": lambda s, i: _goals(s)[i],
    "goals_2h_for": lambda s, i: _goals(s)[i + 2],
}
_BOTH_OVER: dict[str, Callable[[_State], int]] = {
    "both_over_goals": lambda s: min(s[0] + s[2], s[1] + s[3]),
    "both_over_goals_1h": lambda s: min(s[0], s[1]),
    "both_over_goals_2h": lambda s: min(s[2], s[3]),
}


def _sign(x: int) -> str:
    return "1" if x > 0 else "2" if x < 0 else "X"


def _sides_answer(subject: str, leg: Mapping[str, Any],
                  board: Sides | None) -> int | None:
    """0 / 1 for the side a subject names - by Superbet's own side names
    (the board RESOLVE joined) and by the leg's match (Sofascore's names);
    None when neither answers or the two disagree."""
    answers: set[int] = set()
    for sides in (board, _match_sides(leg)):
        if sides is not None:
            got = side_of(subject, sides)
            if got is not None:
                answers.add(got)
    return answers.pop() if len(answers) == 1 else None


def _side_index(leg: Mapping[str, Any], board: Sides | None) -> int | None:
    """0 = home, 1 = away for a football leg whose subject names a team."""
    return _sides_answer(str(leg.get("subject") or ""), leg, board)


@lru_cache(maxsize=4096)
def _football_vector(market: str, subject: str, side: int | None,
                     line: float) -> tuple[bool | None, ...] | None:
    """The OVER's outcome on every path, or None when the market is not one
    this module grades."""
    held: Callable[[_State], bool | None]
    if market in _COUNT_MARKETS:
        count = _COUNT_MARKETS[market]
        held = lambda s: count(s) > line  # noqa: E731
    elif market in _SIDE_COUNT_MARKETS:
        if side is None:
            return None
        side_count = _SIDE_COUNT_MARKETS[market]
        held = lambda s: side_count(s, side) > line  # noqa: E731
    elif market in _BOTH_OVER:
        both = _BOTH_OVER[market]
        held = lambda s: both(s) > line  # noqa: E731
    elif market == "result_1x2" and subject in ("1", "X", "2"):
        held = lambda s: _sign(s[0] + s[2] - s[1] - s[3]) == subject  # noqa: E731
    elif market == "double_chance" and subject in ("1X", "X2", "12"):
        held = lambda s: _sign(s[0] + s[2] - s[1] - s[3]) in subject  # noqa: E731
    elif market in fsm.MARKETS:
        if not fsm.valid_rung(market, subject, line):
            return None
        mask = fsm.event_mask(market, subject, line, max(KMAX, 2 * _N))
        held = lambda s: bool(mask[s[0] + s[2], s[1] + s[3]])  # noqa: E731
    elif market in sim.MARKETS:
        if not sim.valid_subject(market, subject):
            return None
        held = lambda s: sim.path_holds(  # noqa: E731
            market, subject, (s[0], s[1]), (s[0] + s[2], s[1] + s[3]), s[4])
    else:
        return None
    return tuple(held(s) for s in _STATES)


def _football_key(leg: Mapping[str, Any], board: Sides | None) -> str | None:
    market = str(leg.get("market") or "")
    subject = str(leg.get("subject") or "")
    direction = str(leg.get("direction") or "")
    if direction not in ("OVER", "UNDER"):
        return None
    raw = leg.get("line")
    try:
        line = 0.5 if raw is None else float(raw)
    except (TypeError, ValueError):
        return None
    side = _side_index(leg, board) if market in _SIDE_COUNT_MARKETS else None
    vector = _football_vector(market, subject, side, line)
    if vector is None:
        return None
    if direction == "UNDER":
        vector = tuple(None if v is None else not v for v in vector)
    if len(set(vector)) < 2:
        return None  # constant on the paths: nothing to tell it by
    bits = "".join("1" if v else "0" if v is False else "-" for v in vector)
    return "football:" + hashlib.sha1(bits.encode()).hexdigest()


# --- the measured sports -----------------------------------------------------

_MARGINS = range(-60, 61)


def _margin_scope(sport: str, family: str, period: int) -> tuple[str, str] | None:
    """(scope, base) of a 1X2 / double chance / handicap family whose margin
    is regulation-only in every member, else None."""
    for base in ("double_chance", "handicap", "1x2"):
        if family.endswith(base):
            prefix = family[: -len(base)]
            break
    else:
        return None
    if sport == "hockey":
        if prefix in ("", "result_") and period == 0:
            return "reg", base
        if prefix == "period_" and period > 0:
            return f"p{period}", base
        return None
    if sport == "basketball":
        # never a period overtime may touch (the second half, the 4th
        # quarter): our grader reads regulation there, Superbet's rule for
        # its handicap is not verified (review 2026-11-07) - no key, no drop
        if prefix == "quarter_" and 0 < period < 4:
            return f"q{period}", base
        if prefix == "h1_":
            return "h1", base
        return None
    return None


def _margin_wins(base: str, side: str, line: float | None, d: int) -> bool | None:
    if base == "1x2":
        return {"T1": d > 0, "DRAW": d == 0, "T2": d < 0}.get(side)
    if base == "double_chance":
        return {"1X": d >= 0, "X2": d <= 0, "12": d != 0}.get(side)
    if base == "handicap" and line is not None and line != int(line):
        # team1's handicap for both sides (shadow.grade)
        return {"T1": d + line > 0, "T2": d + line < 0}.get(side)
    return None


def _margin_key(leg: Mapping[str, Any], sport: str) -> str | None:
    family = str(leg.get("family") or leg.get("market") or "")
    try:
        period = int(leg.get("period") or 0)
    except (TypeError, ValueError):
        return None
    scope = _margin_scope(sport, family, period)
    if scope is None:
        return None
    side = str(leg.get("side") or leg.get("direction") or "")
    raw_line = leg.get("line")
    line = float(raw_line) if raw_line is not None else None
    wins = [d for d in _MARGINS if _margin_wins(scope[1], side, line, d)]
    if not wins or len(wins) == len(_MARGINS):
        return None
    if _margin_wins(scope[1], side, line, 0) is None:
        return None
    return f"{sport}:{scope[0]}:" + ",".join(str(d) for d in wins)


_VB_SCORES: tuple[tuple[int, int], ...] = (
    (3, 0), (3, 1), (3, 2), (2, 3), (1, 3), (0, 3))
_CS2_BO3: tuple[tuple[int, int], ...] = ((2, 0), (2, 1), (1, 2), (0, 2))


def _team_of(leg: Mapping[str, Any], subject: str,
             board: Sides | None) -> str | None:
    if subject in ("T1", "T2"):
        return subject
    got = _sides_answer(subject, leg, board)
    return None if got is None else ("T1", "T2")[got]


def _score_wins(family: str, leg: Mapping[str, Any], board: Sides | None,
                score: tuple[int, int],
                sets_family: str, team_family: str, exact_family: str,
                winner_families: tuple[str, ...]) -> bool | None:
    t1, t2 = score
    d = t1 - t2
    side = str(leg.get("side") or leg.get("direction") or "")
    raw_line = leg.get("line")
    line = float(raw_line) if raw_line is not None else None
    if family in winner_families:
        return {"T1": d > 0, "T2": d < 0}.get(side)
    if family == sets_family:
        if line is None or line == int(line):
            return None
        return {"T1": d + line > 0, "T2": d + line < 0}.get(side)
    if family == exact_family:
        return f"{t1}:{t2}" == side
    if family == team_family:
        team = _team_of(leg, str(leg.get("subject") or ""), board)
        if team is None:
            return None
        won = t1 if team == "T1" else t2
        if side in ("YES", "NO"):  # volleyball "wins a set"
            return (won >= 1) == (side == "YES")
        if side in ("OVER", "UNDER") and line is not None:
            return (won > line) == (side == "OVER")
    return None


def _scores_key(leg: Mapping[str, Any], sport: str,
                board: Sides | None) -> str | None:
    family = str(leg.get("family") or leg.get("market") or "")
    try:
        period = int(leg.get("period") or 0)
    except (TypeError, ValueError):
        return None
    if period != 0:
        return None
    if sport == "volleyball":
        scores = _VB_SCORES
        spec = ("set_handicap", "team_wins_set", "exact_sets", ("winner",))
    elif sport == "cs2":
        if leg.get("best_of") != 3:
            return None  # a format nobody told us is not guessed
        scores = _CS2_BO3
        spec = ("maps_handicap", "team_maps", "exact_maps", ("match_winner",))
    else:
        return None
    if family not in (spec[0], spec[1], spec[2], *spec[3]):
        return None
    outcomes = [_score_wins(family, leg, board, s, *spec) for s in scores]
    if any(o is None for o in outcomes) or all(outcomes) or not any(outcomes):
        return None
    won = [f"{a}:{b}" for (a, b), o in zip(scores, outcomes, strict=True) if o]
    return f"{sport}:" + ",".join(won)


def event_key(leg: Mapping[str, Any], board: Sides | None = None) -> str | None:
    """The event the leg wins on, comparable between legs of ONE match;
    None = not known to this module (never deduplicated). `board`:
    Superbet's (side_a, side_b) of the match (superbet_names.board_sides),
    for a subject that names a team."""
    sport = str(leg.get("sport") or "")
    if sport == "football":
        return _football_key(leg, board)
    if sport in ("hockey", "basketball"):
        return _margin_key(leg, sport)
    if sport in ("volleyball", "cs2"):
        return _scores_key(leg, sport, board)
    return None


def _board_of(leg: Mapping[str, Any],
              boards: Mapping[int, Sides] | None) -> Sides | None:
    if not boards:
        return None
    try:
        return boards.get(int(leg.get("sofascore_event_id") or 0))
    except (TypeError, ValueError):
        return None


def _match(leg: Mapping[str, Any]) -> str:
    return str(leg.get("group_key") or f"sofa:{leg.get('sofascore_event_id')}")


def price(leg: Mapping[str, Any]) -> float:
    for k in ("offered_odds", "odds"):
        v = leg.get(k)
        if isinstance(v, (int, float)):
            return float(v)
    return 0.0


def _brief(leg: Mapping[str, Any]) -> dict[str, Any]:
    return {k: leg.get(k) for k in (
        "sofascore_event_id", "sport", "market", "family", "subject",
        "direction", "side", "line", "period", "confidence") if k in leg} | {
        "odds": price(leg)}


def dedupe(locked: Sequence[Mapping[str, Any]],
           fresh: Iterable[dict[str, Any]],
           boards: Mapping[int, Sides] | None = None,
           refused: Sequence[Mapping[str, Any]] = (),
           shown: Callable[[Mapping[str, Any]], bool] | None = None,
           ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(fresh legs kept, legs removed as the same event). Locked legs are
    never touched; a fresh leg whose event a locked leg of its match holds
    goes; so does one whose event a read or a veto refused (`refused`, the
    coupon's removed_by_reads: the twin was never in front of an analyst,
    so it must not print the refused outcome under another name - review
    2026-11-07). Among fresh legs of one event a leg already on a printed
    render (`shown`) stays first - the operator may have bet the leg he saw
    and the other was never read - then the best (see the module doc).
    Each removed leg carries `same_event_as` (the leg kept or refused) and
    `same_event_refused` when a read refused the event."""
    fresh = list(fresh)
    held: dict[tuple[str, str], Mapping[str, Any]] = {}
    refused_keys: set[tuple[str, str]] = set()
    for leg in locked:
        key = event_key(leg, _board_of(leg, boards))
        if key is not None:
            held.setdefault((_match(leg), key), leg)
    for leg in refused:
        key = event_key(leg, _board_of(leg, boards))
        if key is not None and (_match(leg), key) not in held:
            held[(_match(leg), key)] = leg
            refused_keys.add((_match(leg), key))
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    keyless: list[dict[str, Any]] = []
    order: dict[int, int] = {id(leg): i for i, leg in enumerate(fresh)}
    for leg in fresh:
        key = event_key(leg, _board_of(leg, boards))
        if key is None:
            keyless.append(leg)
        else:
            groups.setdefault((_match(leg), key), []).append(leg)
    kept: list[dict[str, Any]] = list(keyless)
    removed: list[dict[str, Any]] = []
    for gk, legs in groups.items():
        if gk in held:
            winner: Mapping[str, Any] = held[gk]
            losers = legs
        else:
            ranked = sorted(legs, key=lambda x: (
                not (shown is not None and shown(x)),
                -price(x), float(x.get("confidence") or 0.0),
                str(x.get("market") or x.get("family") or ""),
                str(x.get("subject") or ""), str(x.get("direction") or "")))
            winner, losers = ranked[0], ranked[1:]
            kept.append(ranked[0])
        for leg in losers:
            removed.append({**leg, "same_event_as": _brief(winner),
                            "same_event_key": gk[1],
                            **({"same_event_refused": True}
                               if gk in refused_keys else {})})
    kept.sort(key=lambda x: order[id(x)])
    return kept, removed
