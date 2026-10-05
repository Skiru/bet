"""How two legs of one match relate (plan 2026-10-05 production grade, F4.1).

The coupon prints every leg that clears its bars, and on 2026-10-05 98 of its
157 positions stood on 39 ladders - the same count of one match bought at two
or more rungs - and 20 pairs were the OVER and the UNDER of one count. Nothing
on the page said so: U2.5 and U3.5 goals of one match read as two bets, while
the first implies the second. This module names the relation of any two legs
of one fixture, so the coupon can say it (annotation only - it selects
nothing).

A leg is reduced to a **proposition about a quantity**: the quantity (sport,
statistic, period, form, subject) and the set of its values on which the leg
wins. The quantity is derived from the market map, never from the market's
name: the football / tennis metrics (`bet.sofa.metrics`, the statistic
Sofascore counts and whether it is the match total or a side's), the football
player props (`bet.sofa.players`), the derived markets (`bet.sofa.derived`
via `market_mapper.derived_base` / `derived_side_metric`: both_over = the
smaller side's count, most / handicap = the difference of the sides), and the
measured sports' families (`bet.sofa.shadow.MARKETS` / `PLAYER_MARKETS`,
`bet.sofa.cs2.FAMILIES`) with their period and side.

Labels (`RELATIONS`):

* SAME_VARIABLE_IMPLIES - one quantity, and one leg's winning values are
  inside the other's: U2.5 => U3.5, O2.5 => O1.5 (`implies` says which way;
  `equivalent` when both hold).
* SAME_VARIABLE_EXCLUSIVE - one quantity, the winning values are disjoint:
  O2.5 / U2.5 (`complement`: one of the two always wins), O3.5 / U2.5.
* SAME_VARIABLE_OVERLAP - one quantity, both can win and neither implies the
  other: O1.5 and U3.5.
* DEPENDENT - a known structural link between two different quantities: a
  total and a side's count of it, a half and the full match, a set and the
  match, a team's count and its player's, corners and shots, cards and fouls,
  games and sets, the derived markets and their components, a map and the
  series.
* INDEPENDENT_ASSUMED - no structural link is known. It is an assumption, not
  a measurement: every two legs of one match share the match.

Measured where it matters, assumed where it is not: nothing here claims a
correlation coefficient, only an identity or a named structural link.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from bet.sofa.market_mapper import (
    DERIVED_DRAW_SUBJECT,
    MATCH_MARKET_NAMES,
    PLAYER_MARKET_NAMES,
    TEAM_MARKET_PATTERNS,
    derived_base,
    derived_side_metric,
    fold,
)
from bet.sofa.metrics import FOOTBALL_METRICS, TENNIS_METRICS
from bet.sofa.players import PLAYER_METRICS

SAME_VARIABLE_IMPLIES = "SAME_VARIABLE_IMPLIES"
SAME_VARIABLE_EXCLUSIVE = "SAME_VARIABLE_EXCLUSIVE"
SAME_VARIABLE_OVERLAP = "SAME_VARIABLE_OVERLAP"
DEPENDENT = "DEPENDENT"
INDEPENDENT_ASSUMED = "INDEPENDENT_ASSUMED"
RELATIONS = (
    SAME_VARIABLE_IMPLIES,
    SAME_VARIABLE_EXCLUSIVE,
    SAME_VARIABLE_OVERLAP,
    DEPENDENT,
    INDEPENDENT_ASSUMED,
)
SAME_VARIABLE = frozenset(
    {SAME_VARIABLE_IMPLIES, SAME_VARIABLE_EXCLUSIVE, SAME_VARIABLE_OVERLAP}
)

# ---------------------------------------------------------------------------
# Periods: a period is a set of atomic segments, so "part of" and "disjoint"
# are set operations, whatever the sport.
# ---------------------------------------------------------------------------

_FOOTBALL_ALL = frozenset({"1H", "2H"})
_TENNIS_ALL = frozenset({f"SET{i}" for i in range(1, 6)})
_VOLLEY_ALL = frozenset({f"SET{i}" for i in range(1, 6)})
_CS2_ALL = frozenset({f"MAP{i}" for i in range(1, 6)})
_HOCKEY_REG = frozenset({"P1", "P2", "P3"})
_BASKET_REG = frozenset({"Q1", "Q2", "Q3", "Q4"})

# A segment that is played only on some results of the earlier ones (a third
# tennis set, a fourth volleyball set, a third CS2 map): two legs on disjoint
# periods are still linked when one of them may not be played at all.
_CONDITIONAL_SEGMENTS = frozenset(
    {"SET3", "SET4", "SET5", "MAP3", "MAP4", "MAP5", "OT"}
)


def _football_period(spec: Mapping[str, Any], market: str) -> frozenset[str]:
    period = spec.get("period")
    if period == "1ST" or "_1h_" in market or market.endswith("_1h"):
        return frozenset({"1H"})
    if period == "2ND" or "_2h_" in market or market.endswith("_2h"):
        return frozenset({"2H"})
    return _FOOTBALL_ALL


def _tennis_period(spec: Mapping[str, Any]) -> frozenset[str]:
    if spec.get("set_index"):
        return frozenset({f"SET{int(spec['set_index'])}"})
    period = spec.get("period")
    if period == "1ST":
        return frozenset({"SET1"})
    if period == "2ND":
        return frozenset({"SET2"})
    if period == "3RD":
        return frozenset({"SET3"})
    return _TENNIS_ALL


# ---------------------------------------------------------------------------
# Statistics. The canonical name of what is counted: the Sofascore key of the
# metric, with the listing-derived sources folded onto one name per count.
# ---------------------------------------------------------------------------

_SOURCE_STAT = {
    "goals_from_listing": "goals",
    "goals_1h_from_listing": "goals",
    "goals_2h_from_listing": "goals",
    "gamesWon": "games",
    "games_from_listing": "games",
    "sets_from_listing": "sets",
    "cards_points_from_incidents": "cards_points",
    "aces_plus_double_faults": "serve_points",
}

# A football player prop's Sofascore key -> the team statistic it is part of.
_PLAYER_TEAM_STAT = {
    "totalShots": "totalShotsOnGoal",
    "onTargetScoringAttempt": "shotsOnGoal",
    "goalAssist": "goal_assists",
    "fouls": "fouls",
    "totalTackle": "totalTackle",
    "interceptionWon": "interceptions",
    "totalOffside": "offsides",
}

# Known structural links between two DIFFERENT statistics of one sport, with
# the reason printed beside the label. Symmetric. Not a correlation estimate.
_LINKS: dict[str, dict[frozenset[str], str]] = {
    "football": {
        frozenset({"goals", "shotsOnGoal"}): "a goal is a shot on target",
        frozenset({"goals", "totalShotsOnGoal"}): "a goal is a shot",
        frozenset({"shotsOnGoal", "totalShotsOnGoal"}): "shots on target are shots",
        frozenset({"goalkeeperSaves", "shotsOnGoal"}):
            "saves = the opponent's shots on target minus goals",
        frozenset({"goalkeeperSaves", "goals"}):
            "saves = the opponent's shots on target minus goals",
        frozenset({"goalkeeperSaves", "totalShotsOnGoal"}): "a save is a shot",
        frozenset({"cornerKicks", "totalShotsOnGoal"}):
            "corners follow blocked and saved shots",
        frozenset({"cornerKicks", "shotsOnGoal"}): "corners follow saved shots",
        frozenset({"cornerKicks", "goalkeeperSaves"}):
            "a saved shot can go out for a corner",
        frozenset({"goalKicks", "totalShotsOnGoal"}):
            "a shot off target is a goal kick",
        frozenset({"expectedGoals", "goals"}): "xG is counted over the goal chances",
        frozenset({"expectedGoals", "totalShotsOnGoal"}):
            "xG is counted over the shots",
        frozenset({"expectedGoals", "shotsOnGoal"}): "xG is counted over the shots",
        frozenset({"fouls", "cards_points"}): "cards are given for fouls",
        frozenset({"goal_assists", "goals"}): "an assist is a goal",
    },
    "tennis": {
        frozenset({"games", "sets"}): "sets are won in games",
        frozenset({"games", "tiebreaks"}): "a tiebreak is played at 6-6 in games",
        frozenset({"sets", "tiebreaks"}): "a tiebreak decides a set",
        frozenset({"aces", "serve_points"}): "aces + double faults is the sum",
        frozenset({"doubleFaults", "serve_points"}): "aces + double faults is the sum",
        frozenset({"aces", "games"}): "aces are served in service games",
        frozenset({"doubleFaults", "games"}):
            "double faults are served in service games",
        frozenset({"serve_points", "games"}): "served in service games",
        frozenset({"aces", "sets"}): "more sets, more service games",
        frozenset({"doubleFaults", "sets"}): "more sets, more service games",
        frozenset({"serve_points", "sets"}): "more sets, more service games",
    },
}

# ---------------------------------------------------------------------------
# The measured sports. `bet.sofa.shadow.MARKETS` gives each family its kind
# (total, team_total, handicap, winner, dnb, three_way, odd_even, yes_no,
# exact) and scope; the score's statistic is the sport's own.
# ---------------------------------------------------------------------------

_SCORE_STAT = {"hockey": "goals", "basketball": "points", "volleyball": "points"}

# A player prop's statistic -> the score it feeds (DEPENDENT on the score);
# the rest of a sport's player statistics have no structural link to it.
_PLAYER_FEEDS_SCORE = {
    "hockey": frozenset({"points", "assists", "shots", "powerPlayPoints",
                         "plusMinus", "saves"}),
    "basketball": frozenset({"points", "threePointsMade", "assists"}),
    "volleyball": frozenset(),
}

# CS2: every statistic is counted over the rounds played - maps are won in
# rounds, kills / deaths / headshots / assists happen in rounds.
_CS2_FAMILY = {
    "match_winner": ("maps", "diff"),
    "maps_total": ("maps", "total"),
    "maps_handicap": ("maps", "diff"),
    "team_maps": ("maps", "side"),
    "exact_maps": ("maps", "exact"),
    "rounds_total": ("rounds", "total"),
    "rounds_handicap": ("rounds", "diff"),
    "team_rounds": ("rounds", "side"),
    "map_winner": ("rounds", "diff"),
    "map_rounds_total": ("rounds", "total"),
    "map_rounds_handicap": ("rounds", "diff"),
    "map_team_rounds": ("rounds", "side"),
    "map_rounds_odd_even": ("rounds", "parity"),
    "team_kills": ("kills", "side"),
    "player_kills": ("kills", "player"),
    "player_deaths": ("deaths", "player"),
    "player_headshots": ("headshots", "player"),
    "player_assists": ("assists", "player"),
}


@dataclass(frozen=True)
class Quantity:
    """What a leg is a claim about."""

    sport: str
    stat: str
    period: frozenset[str]
    # total | side | player | diff (side a minus side b) | min (the smaller
    # side) | parity | exact | yes_no
    form: str
    subject: str = ""  # the side / player for side, player and parity-of-side
    integer: bool = True

    def key(self) -> str:
        per = "+".join(sorted(self.period))
        return f"{self.sport}|{self.stat}|{per}|{self.form}|{self.subject}"


@dataclass(frozen=True)
class Proposition:
    """A leg as "the quantity takes one of these values"."""

    quantity: Quantity
    # Interval (integer: inclusive bounds; real: open bounds), None = unbounded.
    lo: float | None = None
    hi: float | None = None
    # A categorical outcome (parity, exact score, yes / no) instead.
    values: frozenset[str] | None = None
    # A difference's orientation: the subject whose side is "a" (most_ /
    # handicap_ name a team; the measured sports read team1 - team2).
    orient: str = ""


@dataclass(frozen=True)
class Relation:
    label: str
    reason: str
    implies: str | None = None  # "a=>b" | "b=>a" | "equivalent"
    complement: bool = False

    def as_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"relation": self.label, "reason": self.reason}
        if self.implies:
            out["implies"] = self.implies
        if self.complement:
            out["complement"] = True
        return out


def _fold_subject(subject: Any) -> str:
    return fold(str(subject or ""))


def _over_under(direction: str, line: float, integer: bool,
                lower: float | None = 0.0) -> tuple[float | None, float | None]:
    """The winning values of OVER / UNDER `line` as (lo, hi)."""
    if direction == "OVER":
        return (math.floor(line) + 1.0 if integer else line), None
    hi = (math.ceil(line) - 1.0) if integer else line
    return lower, hi


# ---------------------------------------------------------------------------
# Leg -> proposition
# ---------------------------------------------------------------------------


def _sheet_sport(leg: Mapping[str, Any]) -> str:
    sport = str(leg.get("sport") or "")
    if sport:
        return sport
    market = str(leg.get("market") or "")
    base = derived_base(market)
    side = derived_side_metric(base) if base else ""
    if market in TENNIS_METRICS or side in TENNIS_METRICS:
        return "tennis"
    return "football"


def _metric_quantity(sport: str, metric: str, subject: str) -> Quantity | None:
    """A football / tennis metric (or player prop) as its quantity."""
    if sport == "football" and metric in PLAYER_METRICS:
        src = str(PLAYER_METRICS[metric]["sofascore"])
        return Quantity(sport, _PLAYER_TEAM_STAT.get(src, src), _FOOTBALL_ALL,
                        "player", subject)
    table = FOOTBALL_METRICS if sport == "football" else TENNIS_METRICS
    spec = table.get(metric)
    if spec is None:
        return None
    src = str(spec["sofascore"])
    stat = _SOURCE_STAT.get(src, src)
    period = (_football_period(spec, metric) if sport == "football"
              else _tennis_period(spec))
    if spec.get("is_total"):
        return Quantity(sport, stat, period, "total", "",
                        integer=stat != "expectedGoals")
    return Quantity(sport, stat, period, "side", subject,
                    integer=stat != "expectedGoals")


def _sheet_proposition(leg: Mapping[str, Any]) -> Proposition | None:
    sport = _sheet_sport(leg)
    market = str(leg.get("market") or "")
    subject = _fold_subject(leg.get("subject"))
    direction = str(leg.get("direction") or "")
    line = float(leg.get("line") or 0.0)
    base = derived_base(market)
    if base is not None:
        side_q = _metric_quantity(sport, derived_side_metric(base), "")
        if side_q is None:
            return None
        if market.startswith("both_over_"):
            q = Quantity(sport, side_q.stat, side_q.period, "min", "", side_q.integer)
            lo, hi = _over_under(direction, line, q.integer)
            return Proposition(q, lo, hi)
        q = Quantity(sport, side_q.stat, side_q.period, "diff", "", side_q.integer)
        if market.startswith("most_"):
            if subject in (fold(DERIVED_DRAW_SUBJECT), "draw", "remis", "x"):
                return Proposition(q, 0.0, 0.0)
            return Proposition(q, *_strict_above(0.0, q.integer), orient=subject)
        # handicap_: "S (h)" wins when S's count minus the other's > -h.
        return Proposition(q, *_strict_above(-line, q.integer), orient=subject)
    plain = _metric_quantity(sport, market, subject)
    if plain is None:
        return None
    lo, hi = _over_under(direction, line, plain.integer)
    return Proposition(plain, lo, hi)


def _strict_above(t: float, integer: bool) -> tuple[float | None, float | None]:
    return (math.floor(t) + 1.0 if integer else t), None


def _strict_below(t: float, integer: bool) -> tuple[float | None, float | None]:
    return None, (math.ceil(t) - 1.0 if integer else t)


def _diff_side(side: str, threshold: float) -> tuple[float | None, float | None] | None:
    """team1 - team2 > threshold for T1, < threshold for T2, == 0 for DRAW."""
    if side == "T1":
        return _strict_above(threshold, True)
    if side == "T2":
        return _strict_below(threshold, True)
    if side == "DRAW":
        return 0.0, 0.0
    return None


def _shadow_period(sport: str, scope: str, period: int) -> frozenset[str]:
    if sport == "hockey":
        return {"full": _HOCKEY_REG | {"OT"}, "reg": _HOCKEY_REG}.get(
            scope, frozenset({f"P{period}"}))
    if sport == "basketball":
        if scope == "full":
            return _BASKET_REG | {"OT"}
        if scope == "reg":
            return _BASKET_REG
        if scope == "h1":
            return frozenset({"Q1", "Q2"})
        if scope == "h2":
            return frozenset({"Q3", "Q4"})
        return frozenset({f"Q{period}"})
    # volleyball
    if scope in ("full", "sets"):
        return _VOLLEY_ALL
    return frozenset({f"SET{period}"})


def _shadow_spec(sport: str, family: str) -> tuple[str, str] | None:
    from bet.sofa.shadow import MARKETS

    for key, specs in MARKETS.items():
        if key != sport:
            continue
        for spec in specs.values():
            if spec.family == family:
                return str(spec.kind), str(spec.scope)
    return None


def _shadow_player_keys(sport: str, family: str) -> tuple[str, ...] | None:
    from bet.sofa.shadow import PLAYER_MARKETS

    for key, players in PLAYER_MARKETS.items():
        if key != sport:
            continue
        for spec in players.values():
            if spec.family == family:
                return tuple(spec.keys)
    return None


def _shadow_proposition(leg: Mapping[str, Any]) -> Proposition | None:
    sport = str(leg["sport"])
    family = str(leg.get("family") or leg.get("market") or "")
    side = str(leg.get("side") or leg.get("direction") or "")
    period_n = int(leg.get("period") or 0)
    line = leg.get("line")
    subject = _fold_subject(leg.get("subject"))
    keys = _shadow_player_keys(sport, family)
    if keys is not None:
        q = Quantity(sport, "player:" + "+".join(keys),
                     _shadow_period(sport, "full", 0), "player", subject)
        lo, hi = _over_under(side, float(line or 0.0), True)
        return Proposition(q, lo, hi)
    spec = _shadow_spec(sport, family)
    if spec is None:
        return None
    kind, scope = spec
    stat = "sets" if scope == "sets" else _SCORE_STAT[sport]
    period = _shadow_period(sport, scope, period_n)
    if kind in ("total", "team_total"):
        form, subj = ("total", "") if kind == "total" else ("side", subject)
        q = Quantity(sport, stat, period, form, subj)
        if side not in ("OVER", "UNDER"):
            return None
        lo, hi = _over_under(side, float(line or 0.0), True)
        return Proposition(q, lo, hi)
    if kind == "odd_even":
        q = Quantity(sport, stat, period, "parity", subject)
        return Proposition(q, values=frozenset({side}))
    if kind == "yes_no":
        q = Quantity(sport, "extra_points", period, "yes_no", "")
        return Proposition(q, values=frozenset({side}))
    if kind == "exact":
        q = Quantity(sport, stat, period, "exact", "")
        return Proposition(q, values=frozenset({side}))
    q = Quantity(sport, stat, period, "diff", "")
    # The line is team1's handicap: T1 wins when team1 - team2 > -line.
    threshold = -float(line) if (kind == "handicap" and line is not None) else 0.0
    bounds = _diff_side(side, threshold)
    if bounds is None:
        return None
    return Proposition(q, *bounds, orient="t1")


def _cs2_proposition(leg: Mapping[str, Any]) -> Proposition | None:
    family = str(leg.get("family") or leg.get("market") or "")
    known = _CS2_FAMILY.get(family)
    if known is None:
        return None
    stat, form = known
    side = str(leg.get("side") or leg.get("direction") or "")
    map_nr = int(leg.get("map_nr") or leg.get("period") or 0)
    period = frozenset({f"MAP{map_nr}"}) if map_nr else _CS2_ALL
    subject = _fold_subject(leg.get("subject"))
    line = leg.get("line")
    if form in ("total", "side", "player"):
        q = Quantity("cs2", stat, period, form, "" if form == "total" else subject)
        if side not in ("OVER", "UNDER"):
            return None
        lo, hi = _over_under(side, float(line or 0.0), True)
        return Proposition(q, lo, hi)
    if form in ("parity", "exact"):
        return Proposition(Quantity("cs2", stat, period, form, ""),
                           values=frozenset({side}))
    q = Quantity("cs2", stat, period, "diff", "")
    handicap = family.endswith("_handicap") and line is not None
    threshold = -float(line or 0.0) if handicap else 0.0
    bounds = _diff_side(side, threshold)
    if bounds is None:
        return None
    return Proposition(q, *bounds, orient="t1")


def proposition(leg: Mapping[str, Any]) -> Proposition | None:
    """The leg as a proposition, or None for a market not in the map."""
    sport = str(leg.get("sport") or "")
    if sport == "cs2":
        return _cs2_proposition(leg)
    if sport in _SCORE_STAT:
        return _shadow_proposition(leg)
    return _sheet_proposition(leg)


def quantity_key(leg: Mapping[str, Any]) -> str | None:
    """One id per variable of a match's legs (the ladder key of F4.2)."""
    p = proposition(leg)
    return None if p is None else p.quantity.key()


# ---------------------------------------------------------------------------
# Relation of two propositions
# ---------------------------------------------------------------------------


def _negate(p: Proposition) -> Proposition:
    lo = None if p.hi is None else -p.hi
    hi = None if p.lo is None else -p.lo
    return Proposition(p.quantity, lo, hi, p.values, p.orient)


def _orient(a: Proposition, b: Proposition) -> Proposition:
    """b on a's orientation of a difference (a draw is symmetric)."""
    if (a.quantity.form == "diff" and a.orient and b.orient
            and a.orient != b.orient and not (b.lo == 0.0 and b.hi == 0.0)):
        return _negate(b)
    return b


def _inside(a: Proposition, b: Proposition) -> bool:
    """Every winning value of a wins b."""
    lo_ok = b.lo is None or (a.lo is not None and a.lo >= b.lo)
    hi_ok = b.hi is None or (a.hi is not None and a.hi <= b.hi)
    return lo_ok and hi_ok


def _empty(p: Proposition) -> bool:
    if p.lo is None or p.hi is None:
        return False
    return p.lo > p.hi if p.quantity.integer else p.lo >= p.hi


def _disjoint(a: Proposition, b: Proposition) -> bool:
    lo = max((x for x in (a.lo, b.lo) if x is not None), default=None)
    hi = min((x for x in (a.hi, b.hi) if x is not None), default=None)
    if lo is None or hi is None:
        return False
    if a.quantity.integer:
        return lo > hi
    # Real-valued (xG): open bounds; a closed point (a draw) is not used.
    return lo >= hi


def _covers_all(a: Proposition, b: Proposition) -> bool:
    """Do a and b together cover every value (one of them always wins)?"""
    floor = None if a.quantity.form == "diff" else 0.0
    for x, y in ((a, b), (b, a)):
        x_from_bottom = x.lo is None or (floor is not None and x.lo <= floor)
        if x_from_bottom and x.hi is not None and y.hi is None and y.lo is not None:
            step = 1.0 if a.quantity.integer else 0.0
            if y.lo <= x.hi + step:
                return True
    return False


def _same_variable(a: Proposition, b: Proposition) -> Relation:
    stat = a.quantity.stat
    if a.values is not None or b.values is not None:
        va, vb = a.values or frozenset(), b.values or frozenset()
        if va == vb:
            return Relation(SAME_VARIABLE_IMPLIES, f"the same outcome of {stat}",
                            implies="equivalent")
        if not (va & vb):
            whole = {"ODD", "EVEN"} if a.quantity.form == "parity" else (
                {"YES", "NO"} if a.quantity.form == "yes_no" else set())
            return Relation(SAME_VARIABLE_EXCLUSIVE,
                            f"two outcomes of {stat} that cannot both happen",
                            complement=bool(whole) and (va | vb) == whole)
        return Relation(SAME_VARIABLE_OVERLAP, f"overlapping outcomes of {stat}")
    b = _orient(a, b)
    if _empty(a) or _empty(b) or _disjoint(a, b):
        return Relation(SAME_VARIABLE_EXCLUSIVE,
                        f"one {a.quantity.form} of {stat}: the two cannot both win",
                        complement=_covers_all(a, b))
    a_in_b, b_in_a = _inside(a, b), _inside(b, a)
    if a_in_b and b_in_a:
        return Relation(SAME_VARIABLE_IMPLIES, f"the same claim about {stat}",
                        implies="equivalent")
    if a_in_b:
        return Relation(SAME_VARIABLE_IMPLIES,
                        f"one {a.quantity.form} of {stat}: "
                        "the first implies the second",
                        implies="a=>b")
    if b_in_a:
        return Relation(SAME_VARIABLE_IMPLIES,
                        f"one {a.quantity.form} of {stat}: "
                        "the second implies the first",
                        implies="b=>a")
    return Relation(SAME_VARIABLE_OVERLAP,
                    f"one {a.quantity.form} of {stat}: both can win, neither implies")


def _link(qa: Quantity, qb: Quantity) -> str | None:
    """A structural link between two different statistics, or None."""
    if qa.sport == "cs2":
        return "every CS2 statistic is counted over the rounds played"
    if qa.sport in _SCORE_STAT:
        sa, sb = qa.stat, qb.stat
        score = {_SCORE_STAT[qa.sport], "sets", "extra_points"}
        if sa in score and sb in score:
            return "sets, points and extra points are one score"
        feeds = _PLAYER_FEEDS_SCORE[qa.sport]
        for ps, other in ((sa, sb), (sb, sa)):
            if ps.startswith("player:") and other in score:
                if set(ps.removeprefix("player:").split("+")) & feeds:
                    return "a player's count feeds the score"
        if sa.startswith("player:") and sb.startswith("player:"):
            ka = set(sa.removeprefix("player:").split("+"))
            kb = set(sb.removeprefix("player:").split("+"))
            if ka & kb:
                return "player statistics sharing a component"
        return None
    return _LINKS.get(qa.sport, {}).get(frozenset({qa.stat, qb.stat}))


def _period_relation(pa: frozenset[str], pb: frozenset[str]) -> str:
    if pa == pb:
        return "same"
    if pa & pb:
        return "nested"
    if (pa | pb) & _CONDITIONAL_SEGMENTS:
        return "conditional"
    return "disjoint"


def relate_propositions(a: Proposition, b: Proposition) -> Relation:
    qa, qb = a.quantity, b.quantity
    if qa.sport != qb.sport:
        return Relation(INDEPENDENT_ASSUMED, "different sports")
    if qa == qb:
        return _same_variable(a, b)
    periods = _period_relation(qa.period, qb.period)
    if qa.stat == qb.stat:
        if periods == "disjoint":
            return Relation(INDEPENDENT_ASSUMED,
                            f"{qa.stat} in two disjoint periods (assumed)")
        if periods == "conditional":
            return Relation(DEPENDENT, f"{qa.stat}: a later set / map / overtime "
                            "is played only on some results of the earlier ones")
        if periods == "nested":
            return Relation(DEPENDENT, f"{qa.stat}: a part of the period and the whole")
        forms = {qa.form, qb.form}
        if forms == {"player"}:
            return Relation(INDEPENDENT_ASSUMED,
                            f"{qa.stat} of two players (assumed)")
        if forms == {"side"}:
            return Relation(DEPENDENT, f"{qa.stat}: two sides of one count")
        if qa.form == qb.form == "parity":
            return Relation(DEPENDENT, f"{qa.stat}: the parity of a total and a side")
        return Relation(DEPENDENT,
                        f"{qa.stat}: {qa.form} and {qb.form} of one count")
    reason = _link(qa, qb)
    pair = " and ".join(sorted((qa.stat, qb.stat)))
    if reason is None:
        return Relation(INDEPENDENT_ASSUMED,
                        f"{pair}: no known structural link (assumed)")
    if periods == "disjoint":
        return Relation(INDEPENDENT_ASSUMED, f"{pair} in disjoint periods (assumed)")
    return Relation(DEPENDENT, f"{pair}: {reason}")


def relate(a: Mapping[str, Any], b: Mapping[str, Any]) -> Relation:
    """The relation of two legs of ONE fixture. Never raises on a market:
    one outside the map is INDEPENDENT_ASSUMED and says so."""
    pa, pb = proposition(a), proposition(b)
    if pa is None or pb is None:
        missing = [str(x.get("market") or x.get("family"))
                   for x, p in ((a, pa), (b, pb)) if p is None]
        return Relation(INDEPENDENT_ASSUMED,
                        f"not in the market map: {', '.join(missing)} (assumed)")
    return relate_propositions(pa, pb)


# ---------------------------------------------------------------------------
# The market map's keys (the test runs every pair of them)
# ---------------------------------------------------------------------------


def mapped_sheet_markets() -> list[tuple[str, str]]:
    """(sport, market) for every football / tennis market the mapper can
    emit: the match and team names, the player props, and the derived
    families over every side metric of the sport."""
    out: set[tuple[str, str]] = set()
    for metric in [*MATCH_MARKET_NAMES.values(),
                   *(m for _, m in TEAM_MARKET_PATTERNS)]:
        out.add(("tennis" if metric in TENNIS_METRICS else "football", metric))
    for metric in FOOTBALL_METRICS:
        out.add(("football", metric))
    for metric in TENNIS_METRICS:
        out.add(("tennis", metric))
    for metric in PLAYER_MARKET_NAMES.values():
        out.add(("football", metric))
    for sport, table in (("football", FOOTBALL_METRICS), ("tennis", TENNIS_METRICS)):
        for metric, spec in table.items():
            if spec.get("is_total") or not metric.endswith("_for"):
                continue
            stem = metric.removesuffix("_for")
            base = "games" if stem == "games_won" else stem
            if derived_side_metric(base) != metric:
                continue
            for prefix in ("both_over_", "most_", "handicap_"):
                out.add((sport, prefix + base))
    return sorted(out)


def mapped_sport_markets() -> list[tuple[str, str]]:
    """(sport, family) of every measured-sport market."""
    from bet.sofa.cs2 import FAMILIES
    from bet.sofa.shadow import MARKETS, PLAYER_MARKETS

    out: set[tuple[str, str]] = set()
    for sport, specs in MARKETS.items():
        out.update((sport, s.family) for s in specs.values())
    for sport, players in PLAYER_MARKETS.items():
        out.update((sport, p.family) for p in players.values())
    out.update(("cs2", f) for f in FAMILIES)
    return sorted(out)


# ---------------------------------------------------------------------------
# The coupon: relations of every pair of a match's legs, and the ladders
# ---------------------------------------------------------------------------


def leg_ref(leg: Mapping[str, Any]) -> dict[str, Any]:
    """How the artifact names a leg in a relation (position when numbered)."""
    out: dict[str, Any] = {
        "position": leg.get("position"),
        "market": leg.get("market") or leg.get("family"),
        "subject": leg.get("subject") or "",
        "line": leg.get("line"),
        "direction": leg.get("direction") or leg.get("side"),
    }
    if leg.get("period"):
        out["period"] = leg.get("period")
    if leg.get("locked"):
        out["locked"] = True
    return out


def _group(leg: Mapping[str, Any]) -> str:
    return str(leg.get("group_key") or f"sofa:{int(leg['sofascore_event_id'])}")


def match_relations(singles: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Per match with two or more legs: every pair and its relation."""
    by_match: dict[str, list[Mapping[str, Any]]] = {}
    for leg in singles:
        by_match.setdefault(_group(leg), []).append(leg)
    out: list[dict[str, Any]] = []
    for key, legs in by_match.items():
        if len(legs) < 2:
            continue
        pairs = []
        for i in range(len(legs)):
            for j in range(i + 1, len(legs)):
                rel = relate(legs[i], legs[j])
                pairs.append({"a": leg_ref(legs[i]), "b": leg_ref(legs[j]),
                              **rel.as_dict()})
        counts: dict[str, int] = {}
        for p in pairs:
            counts[p["relation"]] = counts.get(p["relation"], 0) + 1
        out.append({"group_key": key, "match": legs[0].get("match", ""),
                    "legs": len(legs), "pairs": pairs, "counts": counts})
    return out


def ladders(singles: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Legs of one match that are the same variable, two or more of them: a
    ladder of rungs or an OVER + UNDER pair - one decision, not independent
    bets. In the order the legs are given (the coupon's)."""
    groups: dict[tuple[str, str], list[Mapping[str, Any]]] = {}
    for leg in singles:
        qk = quantity_key(leg)
        if qk is None:
            continue
        groups.setdefault((_group(leg), qk), []).append(leg)
    out = []
    for (gk, qk), legs in groups.items():
        if len(legs) < 2:
            continue
        dirs = {str(x.get("direction") or x.get("side") or "") for x in legs}
        rels = [relate(legs[i], legs[j]).label
                for i in range(len(legs)) for j in range(i + 1, len(legs))]
        out.append({
            "group_key": gk,
            "match": legs[0].get("match", ""),
            "variable": qk,
            "label": variable_label(legs[0]),
            "rungs": [leg_ref(x) for x in legs],
            "n_rungs": len(legs),
            "over_under_pair": {"OVER", "UNDER"} <= dirs,
            "exclusive_pairs": rels.count(SAME_VARIABLE_EXCLUSIVE),
        })
    return out


def variable_label(leg: Mapping[str, Any]) -> str:
    """The variable a ladder is about, as the PDF names it."""
    market = str(leg.get("market") or leg.get("family") or "")
    subject = str(leg.get("subject") or "")
    if market.startswith(("most_", "handicap_")):
        return f"różnica {derived_base(market)}"
    if leg.get("sport") in _SCORE_STAT or leg.get("sport") == "cs2":
        label = str(leg.get("display_market") or market)
        return label.split(" — ")[0]
    return f"{market} ({subject})" if subject else market


def ladder_index(singles: Iterable[Mapping[str, Any]]) -> dict[int, int]:
    """id(leg) -> its ladder's number (1..), only for legs on a ladder."""
    legs = list(singles)
    numbered: dict[tuple[str, str], int] = {}
    counts: dict[tuple[str, str], int] = {}
    keys: list[tuple[str, str] | None] = []
    for leg in legs:
        qk = quantity_key(leg)
        k = None if qk is None else (_group(leg), qk)
        keys.append(k)
        if k is not None:
            counts[k] = counts.get(k, 0) + 1
    out: dict[int, int] = {}
    for leg, k in zip(legs, keys, strict=True):
        if k is None or counts[k] < 2:
            continue
        if k not in numbered:
            numbered[k] = len(numbered) + 1
        out[id(leg)] = numbered[k]
    return out


def one_rung_per_variable(
    singles: Sequence[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """The OFF-by-default ladder form "one_rung" (F4.2, the operator's
    decision, plan section 5 point 1): one leg per variable of a match, the
    highest x = confidence x odds (then confidence, then the coupon's order).
    Locked legs are never touched. Returns (kept, dropped) in input order."""
    best: dict[tuple[str, str], tuple[float, float, int]] = {}
    for i, leg in enumerate(singles):
        qk = quantity_key(leg)
        if qk is None or leg.get("locked"):
            continue
        k = (_group(leg), qk)
        odds = float(leg.get("offered_odds") or leg.get("odds") or 0.0)
        score = (float(leg["confidence"]) * odds, float(leg["confidence"]), -i)
        if k not in best or score > best[k]:
            best[k] = score
    kept, dropped = [], []
    for i, leg in enumerate(singles):
        qk = quantity_key(leg)
        if qk is None or leg.get("locked"):
            kept.append(leg)
            continue
        if best[(_group(leg), qk)][2] == -i:
            kept.append(leg)
        else:
            dropped.append({**leg, "refusal": "LADDER_FORM_ONE_RUNG"})
    return kept, dropped
