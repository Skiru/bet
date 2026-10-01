"""Shadow measurement for ice hockey, basketball and volleyball.

Superbet prices graded against Sofascore scores, outside the coupon on
purpose - the CS2 measurement's design (src/bet/sofa/cs2.py) applied to three
team sports Superbet posts in volume (2026-09-29: hockey 49 events in 16
tournaments, basketball 70 in 31, volleyball 49 in 23). The question comes
before any model: on the markets Superbet posts, does the devigged price
already match what happens? If it does, as in football, a sample has nothing
to add and the sport earns no place on the coupon.

Two stages use this module, neither in DEFAULT_SEQUENCE:

    SHADOW         scripts/sofa/run_shadow.py     Superbet only, several a day
    SHADOW_SETTLE  scripts/sofa/settle_shadow.py  Sofascore via the bridge, D-1

and `scripts/sofa/audit_shadow.py` reports on what they wrote.

What each source was checked against (live, 2026-09-29):

- Superbet sportId 3 is "Hokej na lodzie", 4 "Koszykówka", 1 "Siatkówka"
  (its /v2/pl-PL/struct). The e-sports twins (157 e-hockey, 70 e-basketball)
  are simulations and are never read.
- A market is identified by its `marketId`, which is one id per market type
  across every event (788 is "N. kwarta - liczba punktów" for any N, with the
  quarter in `quarternr`). Per-team markets carry one id per side - 658 is
  always the first-named team's goals, 652 the second's - checked on every
  event of the sample; the side is still re-read from the market name and a
  disagreement drops the line.
- Handicaps quote both outcomes under team1's `hcp`, as in CS2: hockey
  "Ocelari Trinec (-3.5)" / "Rytiri Kladno (3.5)" both carry hcp -3.5.
- Sofascore scores come from /event/{id}: `period1..N` and `current` per side.
  An overtime goal is in `current` but in no period, and the `overtime` key
  is not always printed: HC Motor U20 - Dukla Jihlava U20 (AET) was 1+2+0 = 3 in
  periods, normaltime 3, current 4. Regulation is therefore the sum of the
  regulation periods, and must equal `normaltime` where Sofascore prints it.
- Superbet names a market "(z dogrywką)" when overtime counts (every
  full-game basketball market does; hockey's winner says "z dogrywką i
  rzutami karnymi"). A market without it counts regulation time. That is
  unambiguous for a full game and for hockey's periods (overtime is a period
  of its own). For basketball's Q4 and second half the name alone does not
  say whether overtime is appended, so a line there is ungradeable when the
  game went to overtime and graded otherwise.

Read: two-way lines (winner incl. overtime, totals, team totals, handicaps,
draw-no-bet, odd/even, volleyball's "set on extra points"), and since
2026-09-30 the 1X2s and volleyball's exact set score, each devigged over its
WHOLE outcome group (cs2.group_fair) - a 1X2 missing its draw is no price,
never a two-way one. Player lines are read from the box score.

Not read, each for a reason (measured on the live board 2026-09-30):
- double chance (hockey 606/616, basketball 201797/230595): overlapping
  outcomes, not a partition - it is the 1X2 re-sold, and the 1X2 is read;
- first goal (666, 643) and race to N points (750): need the order of
  scoring, which the stored score does not have;
- basketball milestone props ("Punkty zawodnika" 5+, 235311-235315,
  238440-238446): one-sided, nothing to devig against;
- double-double (233573): two-way, but needs five box-score keys not yet
  checked against the team totals;
- combinations (a ";" in the name, 2312xx / 2397xx): a Bet Builder price;
- hockey 613 / 617 / 621 / 653: the overtime-inclusive ("z dogrywka")
  families, not mapped - the hockey totals read above (623, 658, 652, 604)
  are regulation-time. The NHL is posted ONLY with these, so no NHL total is
  measured at all (review 2026-10-01).
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Literal

from bet.sofa.cs2 import (
    Shape,
    complete_group,
    exact_score,
    grade_side,
    group_fair,
    group_overround,
    parity_side,
)

SportKey = Literal["hockey", "basketball", "volleyball"]


@dataclass(frozen=True)
class ShadowSport:
    key: SportKey
    superbet_id: int
    sofascore_slug: str
    # Regulation periods for hockey/basketball; volleyball has sets instead.
    regulation_periods: int | None
    # Sofascore status descriptions of a plainly finished match. Anything else
    # "finished" - a walkover, an awarded match, a retirement - is UNUSUAL and
    # never graded.
    finished_descriptions: frozenset[str]
    # Basketball's Q4 and second half carry no "(z dogrywką)" and it is not
    # said whether overtime is appended to them; hockey's overtime is its own
    # period and never part of the third.
    last_period_ambiguous_with_ot: bool = False


SPORTS: dict[SportKey, ShadowSport] = {
    "hockey": ShadowSport(
        "hockey", 3, "ice-hockey", 3, frozenset({"Ended", "AET", "AP"})
    ),
    "basketball": ShadowSport(
        "basketball", 4, "basketball", 4, frozenset({"Ended", "AET"}), True
    ),
    "volleyball": ShadowSport(
        "volleyball", 1, "volleyball", None, frozenset({"Ended"})
    ),
}
SPORT_BY_SUPERBET_ID: dict[int, ShadowSport] = {
    s.superbet_id: s for s in SPORTS.values()
}

VOID_AFTER = timedelta(hours=48)
# A basketball or hockey game runs ~2.5 h with breaks, volleyball 2 h.
SETTLE_AFTER = timedelta(hours=4)

Kind = Literal[
    "winner",
    "total",
    "team_total",
    "handicap",
    "dnb",
    "three_way",  # 1X2: T1 / DRAW / T2, devigged over all three
    "odd_even",  # ODD / EVEN of a total, or of a team's own (team set)
    "yes_no",  # YES / NO: volleyball "set decided on extra points"
    "exact",  # exact score in sets, "3:1" = team1 first; the whole score set
]
# Kinds whose quantity does not depend on which side is team1, so a game whose
# orientation cannot be told still grades them (with no team of their own).
ORIENTATION_FREE: frozenset[str] = frozenset({"total", "odd_even", "yes_no"})


@dataclass(frozen=True)
class MarketSpec:
    family: str
    kind: Kind
    # "full" (incl. overtime), "reg" (regulation), "period" (period, quarter
    # or set named by `period_key`), "h1" / "h2" (basketball halves),
    # "sets" (volleyball: the quantity is sets, not points).
    scope: str
    period_key: str | None = None
    team: Literal["T1", "T2"] | None = None


def _m(
    family: str,
    kind: Kind,
    scope: str,
    period_key: str | None = None,
    team: Literal["T1", "T2"] | None = None,
) -> MarketSpec:
    return MarketSpec(family, kind, scope, period_key, team)


MARKETS: dict[SportKey, dict[int, MarketSpec]] = {
    "hockey": {
        630: _m("winner", "winner", "full"),
        623: _m("total", "total", "reg"),
        658: _m("team_total", "team_total", "reg", team="T1"),
        652: _m("team_total", "team_total", "reg", team="T2"),
        604: _m("handicap", "handicap", "reg"),
        649: _m("period_total", "total", "period", "periodnr"),
        674: _m("period_team_total", "team_total", "period", "periodnr", "T1"),
        638: _m("period_team_total", "team_total", "period", "periodnr", "T2"),
        678: _m("period_handicap", "handicap", "period", "periodnr"),
        662: _m("period_dnb", "dnb", "period", "periodnr"),
        # 1X2 checked live 2026-09-30: "Mecz" 1 / X / 2 (code 1 / 0 / 2), a
        # draw priced (4.2), so regulation time; per period the same.
        640: _m("result_1x2", "three_way", "reg"),
        660: _m("period_1x2", "three_way", "period", "periodnr"),
    },
    "basketball": {
        759: _m("winner", "winner", "full"),
        753: _m("total", "total", "full"),
        768: _m("handicap", "handicap", "full"),
        758: _m("team_total", "team_total", "full", team="T1"),
        776: _m("team_total", "team_total", "full", team="T2"),
        748: _m("h1_total", "total", "h1"),
        773: _m("h1_handicap", "handicap", "h1"),
        200804: _m("h1_team_total", "team_total", "h1", team="T1"),
        200797: _m("h1_team_total", "team_total", "h1", team="T2"),
        765: _m("h1_dnb", "dnb", "h1"),
        233404: _m("h2_total", "total", "h2"),
        233405: _m("h2_handicap", "handicap", "h2"),
        233806: _m("h2_team_total", "team_total", "h2", team="T1"),
        233807: _m("h2_team_total", "team_total", "h2", team="T2"),
        233499: _m("h2_dnb", "dnb", "h2"),
        788: _m("quarter_total", "total", "period", "quarternr"),
        774: _m("quarter_handicap", "handicap", "period", "quarternr"),
        200802: _m("quarter_team_total", "team_total", "period", "quarternr", "T1"),
        200795: _m("quarter_team_total", "team_total", "period", "quarternr", "T2"),
        772: _m("quarter_dnb", "dnb", "period", "quarternr"),
        # Checked live 2026-09-30. "Mecz" prices a draw (X 12.0), so it is
        # regulation; 233400 names the teams and "Remis" with no code.
        777: _m("result_1x2", "three_way", "reg"),
        763: _m("h1_1x2", "three_way", "h1"),
        233400: _m("h2_1x2", "three_way", "h2"),
        779: _m("quarter_1x2", "three_way", "period", "quarternr"),
        775: _m("odd_even", "odd_even", "full"),
        230634: _m("team_odd_even", "odd_even", "full", team="T1"),
        230640: _m("team_odd_even", "odd_even", "full", team="T2"),
    },
    "volleyball": {
        745: _m("winner", "winner", "sets"),
        230058: _m("sets_total", "total", "sets"),
        100082: _m("set_handicap", "handicap", "sets"),
        230060: _m("points_total", "total", "full"),
        1069: _m("points_handicap", "handicap", "full"),
        744: _m("set_winner", "dnb", "period", "setnr"),
        782: _m("set_points_total", "total", "period", "setnr"),
        # Checked live 2026-09-30: "Dokładny wynik" 3:0 / 3:1 / ... (code
        # "30"), team1 first; parity per match and per set; 100077 "Czy N. set
        # zostanie rozstrzygnięty na dodatkowe punkty przewagi?" Tak / Nie.
        785: _m("exact_sets", "exact", "sets"),
        200896: _m("points_odd_even", "odd_even", "full"),
        781: _m("set_points_odd_even", "odd_even", "period", "setnr"),
        100077: _m("set_extra_points", "yes_no", "period", "setnr"),
    },
}
PARTNER = {"OVER": "UNDER", "UNDER": "OVER", "T1": "T2", "T2": "T1"}


@dataclass(frozen=True)
class PlayerSpec:
    """A two-way player line: the quantity is the sum of `keys` in the
    player's `/event/{id}/lineups` statistics.

    `name` is Superbet's market name, lowercased, and must match exactly - the
    id alone could be re-used. Every one of these is "(z dogrywką)", and a
    hockey line excludes the shootout ("Rzuty karne nie są brane pod uwagę"),
    as Sofascore's player statistics do.
    """

    family: str
    keys: tuple[str, ...]
    name: str


def _p(family: str, name: str, *keys: str) -> PlayerSpec:
    return PlayerSpec(family, keys, name)


# Measured live 2026-09-29 on the next day's board (both sides quoted on every
# line), and each Sofascore key checked against the team: the players' sum
# equalled the team's `/statistics` value (hockey shots / hits / blocked,
# basketball assists / blocks / steals / threes) or the final score
# (basketball points) on every one of 12 team-games; a goalie's `saves` is
# the opponent's shots minus the goals he let in.
_B = "zawodnik - liczba "
_Z = " (z dogrywką)"
PLAYER_MARKETS: dict[SportKey, dict[int, PlayerSpec]] = {
    "hockey": {
        236265: _p("player_points", _B + "punktów" + _Z, "points"),
        236264: _p("player_assists", _B + "asyst" + _Z, "assists"),
        230023: _p("player_shots_on_goal", "celne strzały zawodnika" + _Z, "shots"),
        232584: _p(
            "player_pp_points", _B + "punktów w przewadze" + _Z, "powerPlayPoints"
        ),
        232585: _p(
            "player_plus_minus",
            "bilans goli (+/-) zawodnika na lodzie" + _Z,
            "plusMinus",
        ),
        232586: _p(
            "player_blocked_shots", _B + "zablokowanych strzałów" + _Z, "blocked"
        ),
        236939: _p(
            "player_faceoff_wins", _B + "wygranych wznowień" + _Z, "faceOffWins"
        ),
        236940: _p("player_hits", _B + "hits" + _Z, "hits"),
        230026: _p("player_goalie_saves", "obronione strzały bramkarza" + _Z, "saves"),
    },
    "basketball": {
        **{
            mid: _p("player_points", _B + "punktów" + _Z, "points")
            for mid in (233565, 239934)
        },
        **{
            mid: _p("player_assists", _B + "asyst" + _Z, "assists")
            for mid in (233566, 239935)
        },
        **{
            mid: _p("player_rebounds", _B + "zbiórek" + _Z, "rebounds")
            for mid in (233567, 239936)
        },
        **{
            mid: _p(
                "player_threes",
                _B + "trafionych rzutów za 3pkt" + _Z,
                "threePointsMade",
            )
            for mid in (233568, 233857)
        },
        **{
            mid: _p(
                "player_pts_reb_ast",
                _B + "punktów + zbiórek + asyst" + _Z,
                "points",
                "rebounds",
                "assists",
            )
            for mid in (233569, 239940)
        },
        **{
            mid: _p(
                "player_reb_ast", _B + "zbiórek + asyst" + _Z, "rebounds", "assists"
            )
            for mid in (233570, 239939)
        },
        **{
            mid: _p("player_pts_ast", _B + "punktów + asyst" + _Z, "points", "assists")
            for mid in (233571, 239937)
        },
        **{
            mid: _p(
                "player_pts_reb", _B + "punktów + zbiórek" + _Z, "points", "rebounds"
            )
            for mid in (233572, 239938)
        },
        235217: _p("player_blocks", _B + "bloków" + _Z, "blocks"),
        235218: _p("player_steals", _B + "przechwytów" + _Z, "steals"),
    },
    "volleyball": {},
}


def is_player_line(sport: SportKey, market_id: int) -> bool:
    return market_id in PLAYER_MARKETS[sport]


def group_shape(sport: SportKey, market_id: int) -> Shape:
    """The outcome shape a market's sides must make up (player lines: two)."""
    spec = MARKETS[sport].get(market_id)
    if spec is not None and spec.kind == "three_way":
        return "three"
    if spec is not None and spec.kind == "exact":
        return "exact"
    return "two"


_HCP_IN_NAME = re.compile(r"\((-?\d+(?:\.\d+)?)\)")


@dataclass(frozen=True)
class ShadowLine:
    """One side (outcome) of one Superbet line: a two-way pair, a 1X2, or an
    exact-score set."""

    superbet_event_id: str
    market_id: int
    family: str
    period: int  # 0 = not a period market
    subject: str  # "T1" / "T2" for a team total, else ""
    line: float | None  # a total, or team1's handicap; None for winner / dnb
    side: str  # OVER / UNDER / T1 / T2 / DRAW / ODD / EVEN / YES / NO / "3:1"
    odds: float

    def key(self) -> tuple[int, int, str, float | None]:
        return (self.market_id, self.period, self.subject, self.line)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _num(raw: object) -> float | None:
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return None


def _direction(text: str) -> str | None:
    lowered = text.lower()
    under, over = "poniż" in lowered, "powyż" in lowered
    if under == over:
        return None
    return "UNDER" if under else "OVER"


def _team_side(text: str, team1: str, team2: str) -> str | None:
    """Which team a text names; the longer name wins when one contains the
    other ("Dynamo" / "Dynamo Pardubice"), and naming both is no answer."""
    hits = [(len(t), s) for t, s in ((team1, "T1"), (team2, "T2")) if t and t in text]
    if not hits:
        return None
    if len(hits) == 2 and hits[0][0] == hits[1][0]:
        return None
    return max(hits)[1]


_CODE_SIDE = {"+": "OVER", "-": "UNDER", "1": "T1", "2": "T2"}


def parse_line(
    item: dict[str, Any], sport: SportKey, event_id: str, team1: str, team2: str
) -> ShadowLine | None:
    """One Superbet odds item as a gradeable line, or None if it is not one.

    The side is read twice - from Superbet's outcome `code` and from the
    outcome's text - and the line is dropped when the two disagree, or when
    the only reading is the one that could be wrong.
    """
    try:
        market_id = int(item.get("marketId") or 0)
    except (TypeError, ValueError):
        return None
    spec = MARKETS[sport].get(market_id)
    if spec is None:
        player_spec = PLAYER_MARKETS[sport].get(market_id)
        if player_spec is None:
            return None
        return _parse_player_line(item, player_spec, event_id, market_id)
    market = str(item.get("marketName") or "")
    if ";" in market or "price_boost" in str(item.get("tags") or ""):
        return None
    if item.get("status") not in (None, "active"):
        return None
    odds = _num(item.get("price"))
    if odds is None or odds <= 1.0:
        return None
    specifiers = item.get("specifiers") or {}
    name = str(item.get("name") or "")
    info = str(item.get("info") or "")
    period = 0
    if spec.period_key:
        raw_period = _num(specifiers.get(spec.period_key))
        if raw_period is None or raw_period < 1:
            return None
        period = int(raw_period)

    code = str(item.get("code") or "")
    if spec.kind in ("three_way", "odd_even", "yes_no", "exact"):
        side = _wide_side(spec.kind, code, name, info, team1, team2)
        if side is None:
            return None
        if spec.team is not None:
            if _team_side(market, team1, team2) != spec.team:
                return None
        return ShadowLine(
            event_id, market_id, spec.family, period, spec.team or "", None, side, odds
        )
    from_code = _CODE_SIDE.get(str(item.get("code")))
    if spec.kind in ("total", "team_total"):
        from_text = _direction(name) or _direction(info)
        value = _num(specifiers.get("total"))
    else:
        # Winner / dnb / handicap outcomes name the team.
        from_text = _team_side(name, team1, team2) or _team_side(info, team1, team2)
        value = _num(specifiers.get("hcp")) if spec.kind == "handicap" else None
    if from_code is not None and from_text is not None and from_code != from_text:
        return None
    side = from_text or from_code
    if side is None:
        return None
    if spec.kind in ("total", "team_total", "handicap") and value is None:
        return None
    if spec.kind in ("winner", "dnb") and side not in ("T1", "T2"):
        return None
    if spec.kind in ("total", "team_total") and side not in ("OVER", "UNDER"):
        return None
    if spec.kind == "handicap":
        # The outcome's own number must be hcp (team1) or -hcp (team2).
        m = _HCP_IN_NAME.search(name)
        assert value is not None
        if m is None or float(m.group(1)) != (value if side == "T1" else -value):
            return None
    subject = ""
    if spec.kind == "team_total":
        assert spec.team is not None
        # The market name must name the team the id says it is about.
        if _team_side(market, team1, team2) != spec.team:
            return None
        subject = spec.team
    return ShadowLine(
        event_id, market_id, spec.family, period, subject, value, side, odds
    )


_THREE_WAY_CODE = {"1": "T1", "0": "DRAW", "2": "T2"}
_THREE_WAY_TOKEN = {"1": "T1", "X": "DRAW", "2": "T2"}
_PARITY_CODE = {"1": "ODD", "2": "EVEN"}


def _wide_side(
    kind: str, code: str, name: str, info: str, team1: str, team2: str
) -> str | None:
    """The side of a 1X2 / parity / yes-no / exact-score outcome, read from
    the text and from Superbet's `code`; a disagreement drops it."""
    from_code: str | None
    if kind == "three_way":
        token = name.rsplit("-", 1)[-1].strip()
        lowered = (name + " " + info).lower()
        from_text = (
            _THREE_WAY_TOKEN.get(token)
            or ("DRAW" if "remis" in lowered else None)
            or _team_side(name, team1, team2)
            or _team_side(info, team1, team2)
        )
        from_code = _THREE_WAY_CODE.get(code)
    elif kind == "odd_even":
        from_text = parity_side(name + " " + info)
        from_code = _PARITY_CODE.get(code)
    elif kind == "yes_no":
        answer = name.strip().lower()
        from_text = {"tak": "YES", "nie": "NO"}.get(answer)
        from_code = None
    else:  # exact
        score = exact_score(name.strip())
        if score is None:
            return None
        from_text = name.strip()
        from_code = from_text if code in ("", f"{score[0]}{score[1]}") else "MISMATCH"
    if from_code is not None and from_text is not None and from_code != from_text:
        return None
    return from_text or from_code


def _parse_player_line(
    item: dict[str, Any], spec: PlayerSpec, event_id: str, market_id: int
) -> ShadowLine | None:
    """One side of a player line. The side is read from the text only: the
    outcome `code` of these markets is not the +/- of a total ("6-", "9-")."""
    market = str(item.get("marketName") or "")
    if market.strip().lower() != spec.name:
        return None
    if "price_boost" in str(item.get("tags") or ""):
        return None
    if item.get("status") not in (None, "active"):
        return None
    odds = _num(item.get("price"))
    if odds is None or odds <= 1.0:
        return None
    specifiers = item.get("specifiers") or {}
    player = str(specifiers.get("player") or "").strip()
    value = _num(specifiers.get("total"))
    if not player or value is None:
        return None
    name = str(item.get("name") or "")
    side = _direction(name) or _direction(str(item.get("info") or ""))
    if side is None:
        return None
    # The outcome must name the same player and the same number.
    if player.lower() not in name.lower():
        return None
    numbers = re.findall(r"-?\d+(?:\.\d+)?", name.split(" - ")[-1])
    if not numbers or float(numbers[-1]) != value:
        return None
    return ShadowLine(event_id, market_id, spec.family, 0, player, value, side, odds)


def parse_event(
    items: list[dict[str, Any]],
    sport: SportKey,
    event_id: str,
    team1: str,
    team2: str,
) -> list[ShadowLine]:
    """Every gradeable line whose two sides are both quoted exactly once."""
    by_key: dict[tuple[int, int, str, float | None], dict[str, list[ShadowLine]]] = {}
    for item in items:
        parsed = parse_line(item, sport, event_id, team1, team2)
        if parsed is not None:
            by_key.setdefault(parsed.key(), {}).setdefault(parsed.side, []).append(
                parsed
            )
    out: list[ShadowLine] = []
    for key, sides in by_key.items():
        if not complete_group(set(sides), group_shape(sport, key[0])):
            continue
        if any(len(v) != 1 for v in sides.values()):
            continue
        out.extend(v[0] for v in sides.values())
    return out


# --- snapshots ---------------------------------------------------------------


def _utc(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


SideKey = tuple[int, int, str, float | None, str]


@dataclass
class SnapshotEvent:
    """One Superbet event, with each side at the last price seen pre-start."""

    superbet_event_id: str
    match_name: str
    team1: str
    team2: str
    kickoff_utc: str
    tournament: str | None
    sides: dict[SideKey, ShadowLine] = field(default_factory=dict)
    fetched_at: dict[SideKey, str] = field(default_factory=dict)
    # The snapshot file the event was read from (set by sport_coupon).
    source_date: str | None = None


def latest_pre_kickoff(
    snapshots: list[dict[str, Any]],
    start_utc: dict[str, datetime] | None = None,
) -> dict[str, SnapshotEvent]:
    """Each event as its last pre-start snapshot quoted it.

    The last snapshot replaces every earlier one whole, not line by line: a
    line Superbet took down before the start (a total ladder that recentred
    from 5.5 to 6.5) is not graded at the price it had hours earlier. The
    kickoff is the latest record's: a rescheduled game keeps its newest time,
    and a record taken at or after it is not a pre-match price.

    `start_utc` is Sofascore's start per event, where SHADOW_SETTLE knows it.
    The clock is then the EARLIER of the two, as football's
    (coupon.effective_kickoff): a game that began before Superbet's time was
    being quoted in play, and that quote is not the pre-match price.
    """
    latest: dict[str, tuple[datetime, str]] = {}
    for snap in snapshots:
        eid = snap["superbet_event_id"]
        at = _utc(snap["fetched_at_utc"])
        if eid not in latest or at >= latest[eid][0]:
            latest[eid] = (at, snap["kickoff_utc"])
    events: dict[str, SnapshotEvent] = {}
    for snap in sorted(snapshots, key=lambda s: _utc(s["fetched_at_utc"])):
        eid = snap["superbet_event_id"]
        kickoff = latest[eid][1]
        clock = _utc(kickoff)
        if start_utc and eid in start_utc:
            clock = min(clock, start_utc[eid])
        if _utc(snap["fetched_at_utc"]) >= clock:
            continue
        ev = events.setdefault(
            eid,
            SnapshotEvent(
                eid,
                snap["match_name"],
                snap["team1"],
                snap["team2"],
                kickoff,
                snap.get("tournament"),
            ),
        )
        ev.sides.clear()
        ev.fetched_at.clear()
        for raw in snap["lines"]:
            line = ShadowLine(**raw)
            key = (*line.key(), line.side)
            ev.sides[key] = line
            ev.fetched_at[key] = snap["fetched_at_utc"]
    return events


# --- the result ----------------------------------------------------------------


@dataclass(frozen=True)
class GameResult:
    """One finished game, oriented to Superbet's team1 / team2."""

    # Per-period (hockey period, basketball quarter, volleyball set) points.
    t1_periods: tuple[int, ...]
    t2_periods: tuple[int, ...]
    t1_full: int  # incl. overtime (hockey: incl. a shootout's deciding goal)
    t2_full: int
    winner: Literal["T1", "T2"] | None  # None: a regulation draw
    overtime: bool


def _periods(score: dict[str, Any]) -> list[int | None]:
    out: list[int | None] = []
    for n in range(1, 10):
        raw = score.get(f"period{n}")
        if raw is None:
            break
        out.append(raw if isinstance(raw, int) else None)
    return out


def build_result(
    detail: dict[str, Any], sport: ShadowSport, home_is_t1: bool
) -> GameResult | None:
    """The finished game's score, or None if it does not add up.

    Hockey / basketball: exactly the regulation periods, their sum equal to
    `normaltime` where printed, and `current` no lower than regulation.
    Volleyball: every set a clear win, and the sets won equal to `current`.
    """
    home = detail.get("homeScore") or {}
    away = detail.get("awayScore") or {}
    hp, ap = _periods(home), _periods(away)
    if not hp or len(hp) != len(ap) or any(v is None for v in hp + ap):
        return None
    h_periods = [int(v) for v in hp if v is not None]
    a_periods = [int(v) for v in ap if v is not None]
    h_cur, a_cur = home.get("current"), away.get("current")
    if not isinstance(h_cur, int) or not isinstance(a_cur, int):
        return None
    code = detail.get("winnerCode")
    if code not in (1, 2, 3):
        return None
    home_won: bool | None = None if code == 3 else code == 1

    if sport.regulation_periods is None:  # volleyball
        h_sets = sum(1 for h, a in zip(h_periods, a_periods, strict=True) if h > a)
        a_sets = sum(1 for h, a in zip(h_periods, a_periods, strict=True) if a > h)
        if h_sets + a_sets != len(h_periods) or (h_sets, a_sets) != (h_cur, a_cur):
            return None
        if home_won is None or (h_sets > a_sets) != home_won:
            return None
        overtime = False
    else:
        if len(h_periods) != sport.regulation_periods:
            return None
        h_reg, a_reg = sum(h_periods), sum(a_periods)
        for side, reg in ((home, h_reg), (away, a_reg)):
            normal = side.get("normaltime")
            if normal is not None and normal != reg:
                return None
        if h_cur < h_reg or a_cur < a_reg:
            return None
        # Beyond regulation when the score moved past it, or when Sofascore
        # says so: a shootout's deciding goal is not always added to current.
        described = (detail.get("status") or {}).get("description") in ("AET", "AP")
        overtime = (h_cur, a_cur) != (h_reg, a_reg) or described
        if overtime and (h_reg != a_reg or home_won is None):
            # Overtime is only played from a level score, and decides it.
            return None
        shootout = (detail.get("status") or {}).get("description") == "AP"
        if overtime and not shootout and (h_cur > a_cur) != home_won:
            return None
        # Where Sofascore prints `overtime` (NHL AET 0/1, WNBA AET 13/5,
        # checked 2026-09-29) current is regulation plus it - plus one for the
        # shootout's winner (NHL AP: 3+0+1 / 3+0+0, penalties 1/0).
        if "overtime" in home and "overtime" in away:
            for side, reg, won in (
                (home, h_reg, home_won),
                (away, a_reg, not home_won),
            ):
                ot = side.get("overtime")
                if not isinstance(ot, int):
                    return None
                allowed = {reg + ot, reg + ot + 1} if shootout and won else {reg + ot}
                if side.get("current") not in allowed:
                    return None
        if not overtime:
            level = h_reg == a_reg
            # A level regulation score with no overtime is a draw (a league
            # that allows one); anything else must agree with the winner.
            if level != (home_won is None):
                return None
            if not level and (h_reg > a_reg) != home_won:
                return None

    if home_is_t1:
        t1p, t2p, t1f, t2f = h_periods, a_periods, h_cur, a_cur
    else:
        t1p, t2p, t1f, t2f = a_periods, h_periods, a_cur, h_cur
    winner: Literal["T1", "T2"] | None = (
        None if home_won is None else ("T1" if home_won == home_is_t1 else "T2")
    )
    return GameResult(tuple(t1p), tuple(t2p), t1f, t2f, winner, overtime)


def _pair(
    result: GameResult, spec: MarketSpec, period: int, sport: ShadowSport
) -> tuple[int, int] | None:
    """(team1, team2) of the quantity a market is about, or None when the
    game does not answer it (a set not played, an ambiguous last period)."""
    t1, t2 = result.t1_periods, result.t2_periods
    ambiguous = result.overtime and sport.last_period_ambiguous_with_ot
    if spec.scope == "full":
        if sport.regulation_periods is None:  # volleyball: points over all sets
            return sum(t1), sum(t2)
        return result.t1_full, result.t2_full
    if spec.scope == "reg":
        return sum(t1), sum(t2)
    if spec.scope == "sets":
        s1 = sum(1 for a, b in zip(t1, t2, strict=True) if a > b)
        return s1, len(t1) - s1
    if spec.scope == "h1":
        return sum(t1[:2]), sum(t2[:2])
    if spec.scope == "h2":
        if ambiguous:
            return None
        return sum(t1[2:4]), sum(t2[2:4])
    if spec.scope == "period":
        if period < 1 or period > len(t1):
            return None
        if ambiguous and period == sport.regulation_periods:
            return None
        return t1[period - 1], t2[period - 1]
    return None


def actual_value(
    line: ShadowLine, result: GameResult, sport: ShadowSport
) -> float | None:
    """The quantity a line is graded on, or None if the game cannot tell.

    Totals: the total (or the team's own). Winner, dnb and handicap: team1
    minus team2 - except a winner, which is Sofascore's winner (a hockey
    shootout is decided outside the score).
    """
    spec = MARKETS[sport.key][line.market_id]
    if spec.kind == "winner" and spec.scope == "full":
        if result.winner is None:
            return None
        return 1.0 if result.winner == "T1" else -1.0
    pair = _pair(result, spec, line.period, sport)
    if pair is None:
        return None
    a, b = pair
    if spec.kind == "exact":
        score = exact_score(line.side)
        return None if score is None else (1.0 if score == (a, b) else 0.0)
    if spec.kind == "yes_no":
        # Extra points: the set ran past its target, which only a 24-24
        # (14-14) level score allows. The deciding set is played to 15 - the
        # 5th of a best-of-5, the 3rd of a best-of-3: the winner's sets
        # count says which format was played.
        sets = list(zip(result.t1_periods, result.t2_periods, strict=True))
        k = max(sum(1 for x, y in sets if x > y), sum(1 for x, y in sets if y > x))
        target = 15 if k > 1 and line.period == 2 * k - 1 else 25
        return 1.0 if max(a, b) > target else 0.0
    if spec.kind == "odd_even":
        if spec.team is not None:
            return float(a if spec.team == "T1" else b)
        return float(a + b)
    if spec.kind == "total":
        return float(a + b)
    if spec.kind == "team_total":
        return float(a if line.subject == "T1" else b)
    return float(a - b)


@dataclass(frozen=True)
class PlayerBox:
    """Both squads' `/lineups` statistics for one finished game.

    `ok` is False when the box does not add up to the score - basketball's
    points to the final score, hockey's goals to it (a shootout's deciding
    goal may or may not be in `current`) - and then no player line of the
    game is graded.
    """

    players: dict[str, dict[str, Any]]
    ok: bool
    reason: str = ""


def _squad(lineups: dict[str, Any], side: str) -> list[tuple[str, dict[str, Any]]]:
    out: list[tuple[str, dict[str, Any]]] = []
    for entry in (lineups.get(side) or {}).get("players") or []:
        if not isinstance(entry, dict):
            continue
        player = entry.get("player")
        name = player.get("name") if isinstance(player, dict) else None
        if isinstance(name, str) and name.strip():
            stats = entry.get("statistics")
            out.append((name, stats if isinstance(stats, dict) else {}))
    return out


def build_player_box(
    lineups: dict[str, Any] | None, detail: dict[str, Any], sport: ShadowSport
) -> PlayerBox | None:
    """The game's player statistics, checked against its score."""
    from bet.sofa.names import normalize_name

    if not isinstance(lineups, dict):
        return None
    sides = {side: _squad(lineups, side) for side in ("home", "away")}
    if not sides["home"] or not sides["away"]:
        return None
    players: dict[str, dict[str, Any]] = {}
    homonyms: set[str] = set()
    for squad in sides.values():
        for name, stats in squad:
            key = normalize_name(name)
            if key in players:
                # Same name twice (either squad): the line cannot say whose.
                homonyms.add(key)
            players[key] = stats
    for key in homonyms:
        del players[key]
    shootout = (detail.get("status") or {}).get("description") == "AP"
    code = detail.get("winnerCode")
    for side, score_key, won in (
        ("home", "homeScore", code == 1),
        ("away", "awayScore", code == 2),
    ):
        current = (detail.get(score_key) or {}).get("current")
        if not isinstance(current, int):
            return PlayerBox(players, False, "no score")
        key = "points" if sport.key == "basketball" else "goals"
        summed = sum(
            int(v) for _, st in sides[side] if isinstance(v := st.get(key), int)
        )
        allowed = {current, current - 1} if shootout and won else {current}
        if summed not in allowed:
            return PlayerBox(
                players, False, f"{side} {key} {summed} vs score {current}"
            )
    return PlayerBox(players, True)


def player_value(
    line: ShadowLine, box: PlayerBox, sport: ShadowSport
) -> float | Literal["DNP", "UNMATCHED", "NO_STAT"]:
    """The player's quantity, or why there is none. A player who did not
    take the ice / court is DNP - Superbet voids his line, it does not settle
    it at zero."""
    from bet.sofa.players import match_player

    matched = match_player(line.subject, box.players)
    if matched is None:
        return "UNMATCHED"
    stats = box.players[matched]
    played = stats.get("secondsPlayed")
    if not isinstance(played, int | float) or isinstance(played, bool) or played <= 0:
        return "DNP"
    spec = PLAYER_MARKETS[sport.key][line.market_id]
    total = 0.0
    for key in spec.keys:
        value = stats.get(key)
        if isinstance(value, bool) or not isinstance(value, int | float):
            return "NO_STAT"
        total += float(value)
    return total


Outcome = Literal["WIN", "LOSS", "VOID"]


def grade(line: ShadowLine, actual: float, three_way: bool = False) -> Outcome:
    """WIN / LOSS / VOID for this side, given the quantity's actual value.

    For winner / dnb / handicap `actual` is team1 minus team2 and `line.line`
    is team1's handicap (None for winner and dnb, so a level dnb is VOID). In
    a 1X2 (`three_way`) a level score is the DRAW side's win. Parity takes the
    quantity; yes/no and an exact score take an indicator (cs2.grade_side).
    """
    out = grade_side(line.side, actual, line.line, three_way)
    assert out in ("WIN", "LOSS", "VOID")
    return out  # type: ignore[return-value]


def settle_event(
    ev: SnapshotEvent,
    result: GameResult,
    sport: ShadowSport,
    totals_only: bool = False,
    clock: datetime | None = None,
    box: PlayerBox | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Grade every priced pair of one event. Both sides of a pair or neither.

    `totals_only` grades just the match / period totals, which do not depend
    on which Sofascore side is Superbet's team1 - for a game whose orientation
    cannot be told. `clock` is the pre-match clock the price's age is taken
    against: Superbet's kickoff unless the game began earlier.
    """
    start = clock or _utc(ev.kickoff_utc)
    rows: list[dict[str, Any]] = []
    counts = {
        "void": 0,
        "ungradeable": 0,
        "unpaired": 0,
        "needs_orientation": 0,
        "player_no_box": 0,
        "player_unmatched": 0,
        "player_dnp": 0,
    }
    groups: dict[tuple[Any, ...], dict[str, ShadowLine]] = {}
    for key, line in ev.sides.items():
        groups.setdefault(key[:4], {})[line.side] = line
    for key, line in ev.sides.items():
        is_player = is_player_line(sport.key, line.market_id)
        # A player line is about a named person, not a side: orientation
        # does not touch it.
        spec = None if is_player else MARKETS[sport.key][line.market_id]
        if (
            totals_only
            and spec is not None
            and (spec.kind not in ORIENTATION_FREE or spec.team is not None)
        ):
            counts["needs_orientation"] += 1
            continue
        group = groups[key[:4]]
        group_odds = {s: ln.odds for s, ln in group.items()}
        fair = group_fair(group_odds, group_shape(sport.key, line.market_id))
        if fair is None:
            counts["unpaired"] += 1
            continue
        actual: float | None
        if is_player:
            if box is None or not box.ok:
                counts["player_no_box"] += 1
                continue
            got = player_value(line, box, sport)
            if got == "DNP":
                counts["player_dnp"] += 1
                continue
            if got == "UNMATCHED":
                counts["player_unmatched"] += 1
                continue
            if got == "NO_STAT":
                counts["ungradeable"] += 1
                continue
            assert isinstance(got, float)
            actual = got
        else:
            actual = actual_value(line, result, sport)
        if actual is None:
            counts["ungradeable"] += 1
            continue
        outcome = grade(line, actual, spec is not None and spec.kind == "three_way")
        if outcome == "VOID":
            counts["void"] += 1
            continue
        row: dict[str, Any] = {
            **line.as_dict(),
            "fair_p": fair[line.side],
            "overround": group_overround(group_odds),
            "fetched_at_utc": ev.fetched_at[key],
            "minutes_before_kickoff": round(
                (start - _utc(ev.fetched_at[key])).total_seconds() / 60
            ),
            "actual": actual,
            "overtime": result.overtime,
            "outcome": outcome,
        }
        if len(group) == 2:
            row["partner_odds"] = next(
                o for s, o in group_odds.items() if s != line.side
            )
        else:
            row["group_odds"] = group_odds
        rows.append(row)
    return rows, counts


EventState = Literal["FINISHED", "PENDING", "VOID", "UNUSUAL"]


def event_state(
    detail: dict[str, Any], sport: ShadowSport, kickoff: datetime, now: datetime
) -> EventState:
    """Where the game stands. FINISHED only for a plainly ended game."""
    status = detail.get("status") or {}
    kind = status.get("type")
    if kind == "finished":
        if status.get("description") in sport.finished_descriptions:
            return "FINISHED"
        return "UNUSUAL"
    if kind in ("canceled", "cancelled", "abandoned"):
        return "VOID"
    if kind in ("notstarted", "postponed", "delayed") and now - kickoff > VOID_AFTER:
        return "VOID"
    return "PENDING"


# --- files ------------------------------------------------------------------------

SNAPSHOTS_FILE = "snapshots.jsonl"
SETTLED_FILE = "settled.json"


def shadow_day_dir(runs_dir: str, sport: SportKey, date: str) -> Path:
    """runs/sofa/shadow/<sport>/<date>/ - beside the day, never inside it, so
    nothing written here can be read by a stage that builds the coupon."""
    return Path(runs_dir) / "shadow" / sport / date
