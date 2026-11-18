"""Per-SIDE stakes state of a football match as of its kick-off, from the
results played before it (points only). The frozen module of the
pre-registration docs/sofa/evidence/stakes_prereg_football_2026-11-18.md
(section 4; docs/sofa/evidence/stakes_football_2026-11-18/stakes_state.py,
sha256 99e81fe7...) carried here with its logic unchanged - only this
docstring, line breaks and one local name (T) differ
(tests/sofa/test_stakes_groups.py checks the two agree). For national
teams these definitions are the display-only flag's
(bet.sofa.stakes_groups, epochs.STAKES_GROUPS_FROM_UTC).

States: MUST_WIN (pooled: a win - or at least a point - is needed to keep an
open target alive), ALIVE (reference), SECURED, DEAD, AMBIGUOUS (excluded).

A group = (uniqueTournament, season, tournament) round robin. Boundaries B =
the positions k whose crossing carries a consequence ("finish in the top k").
For the side s and each outcome o in {W, D, L} of the match itself:
  possible_k(o): some completion of the other remaining fixtures leaves s in
                 the top k;
  certain_k(o):  every completion does.
Ties on points at a boundary are resolved twice: optimistic (s wins every
tie) and pessimistic (s loses every tie). Exception: when an H2H object is
passed (UEFA competitions, head-to-head first), a tie is ordered by the
head-to-head mini-table (points, goal difference, goals) - only when every
meeting among the tied teams was played before kick-off and the order is
strict; overall goal difference is never coded.

Exact enumeration of the remaining fixtures (W/D/L each) when they number
<= EXACT_MAX; otherwise bounds (the others' mutual fixtures ignored), which
can only leave a decided side ALIVE, never declare an undecided side decided.

State of a side under one tie mode:
  every k in B decided (certain for all o, or impossible for all o):
      SECURED if s is certainly above at least one k, else DEAD;
  else MUST_WIN if some open k is possible after W but not after D, or
                possible after D but not after L;
  else ALIVE.
Final: both modes agree -> that state; one mode MUST_WIN and the other
SECURED / DEAD -> MUST_WIN with tb=True (e.g. "win by 3"); any other
disagreement -> AMBIGUOUS (tb=True).
"""
from __future__ import annotations

import itertools
from collections import defaultdict
from collections.abc import Sequence

EXACT_MAX = 8


class H2H:
    """Head-to-head mini-table among tied teams, from the matches PLAYED
    before kick-off only. order() answers only when every pairing among the
    tied teams has been played legs_per_pair times (so nothing still to be
    played - the match itself included - can change it) and (h2h points,
    h2h goal difference, h2h goals) orders them strictly; else None."""

    def __init__(self, played: Sequence[tuple[int, int, int, int]],
                 legs_per_pair: int) -> None:
        self.played = played
        self.legs = legs_per_pair

    def order(self, tied: Sequence[int]) -> list[int] | None:
        tset = set(tied)
        cnt: dict[frozenset[int], int] = defaultdict(int)
        pts: dict[int, list[int]] = {t: [0, 0, 0] for t in tset}
        for h, a, hg, ag in self.played:
            if h in tset and a in tset:
                cnt[frozenset((h, a))] += 1
                pts[h][0] += 3 if hg > ag else 1 if hg == ag else 0
                pts[a][0] += 3 if ag > hg else 1 if hg == ag else 0
                pts[h][1] += hg - ag
                pts[a][1] += ag - hg
                pts[h][2] += hg
                pts[a][2] += ag
        for x, y in itertools.combinations(sorted(tset), 2):
            if cnt[frozenset((x, y))] < self.legs:
                return None
        keys = {t: tuple(pts[t]) for t in tset}
        if len(set(keys.values())) < len(tset):
            return None
        return sorted(tset, key=lambda t: keys[t], reverse=True)


PTS = {"W": (3, 0), "D": (1, 1), "L": (0, 3)}


def _rank_ok(final: dict[int, int], s: int, k: int, optimistic: bool,
             h2h: H2H | None = None) -> bool:
    ps = final[s]
    if h2h is not None:
        tied = [t for t, p in final.items() if p == ps]
        if len(tied) > 1:
            order = h2h.order(tied)
            if order is not None:
                above = sum(1 for t, p in final.items() if p > ps) + order.index(s)
                return above < k
    if optimistic:
        above = sum(1 for t, p in final.items() if t != s and p > ps)
    else:
        above = sum(1 for t, p in final.items() if t != s and p >= ps)
    return above < k


def side_state(points: dict[int, int], remaining: Sequence[tuple[int, int]],
               match: tuple[int, int], side: int, bounds: Sequence[int],
               optimistic: bool, h2h: H2H | None = None) -> str:
    """points: as of kick-off (every team of the group, 0 if none);
    remaining: the other fixtures not yet played (pairs), the match excluded."""
    h, a = match
    opp = a if side == h else h
    poss: dict[tuple[int, str], bool] = {}
    cert: dict[tuple[int, str], bool] = {}
    for o in ("W", "D", "L"):
        own_pts, opp_pts = PTS[o]
        base = dict(points)
        base[side] += own_pts
        base[opp] += opp_pts
        if len(remaining) <= EXACT_MAX:
            res = {k: [False, True] for k in bounds}
            for outs in itertools.product((0, 1, 2), repeat=len(remaining)):
                fin = dict(base)
                for (x, y), r in zip(remaining, outs, strict=True):
                    if r == 0:
                        fin[x] += 3
                    elif r == 1:
                        fin[x] += 1
                        fin[y] += 1
                    else:
                        fin[y] += 3
                for k in bounds:
                    ok = _rank_ok(fin, side, k, optimistic, h2h)
                    res[k][0] |= ok
                    res[k][1] &= ok
            for k in bounds:
                poss[(k, o)], cert[(k, o)] = res[k]
        else:
            left: dict[int, int] = defaultdict(int)
            for x, y in remaining:
                left[x] += 1
                left[y] += 1
            best = base[side] + 3 * left[side]
            worst = base[side]
            for k in bounds:
                if optimistic:
                    sure_above = sum(1 for t, p in base.items()
                                     if t != side and p > best)
                    can_reach = sum(1 for t, p in base.items()
                                    if t != side and p + 3 * left[t] > worst)
                else:
                    sure_above = sum(1 for t, p in base.items()
                                     if t != side and p >= best)
                    can_reach = sum(1 for t, p in base.items()
                                    if t != side and p + 3 * left[t] >= worst)
                poss[(k, o)] = sure_above < k
                cert[(k, o)] = can_reach < k
    open_k = [k for k in bounds
              if not (all(cert[(k, o)] for o in "WDL")
                      or not any(poss[(k, o)] for o in "WDL"))]
    if not open_k:
        if any(all(cert[(k, o)] for o in "WDL") for k in bounds):
            return "SECURED"
        return "DEAD"
    if any(poss[(k, "W")] and not poss[(k, "D")] for k in open_k):
        return "MUST_WIN"
    if any(poss[(k, "D")] and not poss[(k, "L")] for k in open_k):
        return "MUST_WIN"  # NEED_POINT pooled into MUST_WIN (operator 2026-11-18)
    return "ALIVE"


def final_state(points: dict[int, int], remaining: Sequence[tuple[int, int]],
                match: tuple[int, int], side: int, bounds: Sequence[int],
                h2h: H2H | None = None) -> tuple[str, bool]:
    """(state, tiebreak_dependent). h2h only for competitions whose first
    tiebreak is head-to-head (UEFA's); bounds mode never reads it."""
    opt = side_state(points, remaining, match, side, bounds, True, h2h)
    pes = side_state(points, remaining, match, side, bounds, False, h2h)
    if opt == pes:
        return opt, False
    needy = {"MUST_WIN"}
    decided = {"SECURED", "DEAD"}
    if opt in needy and pes in decided:
        return opt, True       # e.g. "win by 3": the win is needed either way
    if pes in needy and opt in decided:
        return pes, True       # e.g. a loss by 2+ would cost the target
    return "AMBIGUOUS", True
