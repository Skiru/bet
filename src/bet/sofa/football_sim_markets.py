"""Football path markets read by OFFER and graded by SETTLE - behind
``epochs.FOOTBALL_SIM_FROM_UTC`` (``epochs.football_sim``); off, nothing here
is reached and OFFER / SHEET / SETTLE are what they were.

Superbet posts these markets and, before the switch, OFFER only recorded
their prices (``unmapped_prices``). Their outcome is a fact about the path of
the 90 minutes - the half-time score, the 90-minute score, and (only for the
first goal of the first half, when the score cannot decide it) the order of
the goals. SHEET prices them from the minute-by-minute simulator
(bet.sofa.football_sim, bet.sofa.football_sim_sheet).

Shapes (Superbet, ``unmapped_prices`` 2026-10-14 .. 11-05; the listing's
side order ``listing_names`` = home, away; a team selection is matched to it
by the folded name, exactly - nothing guessed):

    htft                    "1. połowa/mecz" "1/1" .. "2/2": subject the
                            selection ("X" upper case), OVER only.
    result_1h / result_2h   "1.połowa - 1X2" / "2.połowa - 1X2": <home> /
                            "remis" / <away> -> subject "1" / "X" / "2" (the
                            half's own goals), OVER only.
    higher_scoring_half     "Połowa z większą liczbą goli": "1.Połowa" /
                            "remis" / "2.Połowa" -> "1H" / "X" / "2H", OVER only.
    team_scores_both_halves "<team> zdobędzie gola w obu połowach" tak / nie:
                            subject "1" / "2" (the team), OVER = tak, UNDER =
                            nie - one two-sided rung.
    btts_halves             "Obie drużyny strzelą gola - 1.połowa/2.połowa"
                            "Tak/Tak" .. "Nie/Nie": subject the selection,
                            OVER only.
    btts_any_half           "Obie drużyny strzelą w przynajmniej jednej
                            połowie meczu" tak / nie: subject "", OVER = tak,
                            UNDER = nie.
    first_goal_1h           "1. połowa - 1. gol": <home> / <away> / "nikt" ->
                            "1" / "2" / "nikt", OVER only.
    half_goals_combo        "1.połowa liczba goli & 2.połowa liczba goli"
                            "poniżej 0.5 & powyżej 1.5" -> subject
                            "U0.5/O1.5" (first half, second half), OVER only.

Every row has line 0.5 and is graded on the event indicator (1 / 0). Not
read: the half double chances, the half handicaps, the HT/FT combinations
with goals or double chance, the minute bands, the last goal, the exact
scores and the team-scoped half totals (other questions, not measured).

Settlement (``sim_value``): Superbet settles football on the 90 minutes
plus added time (``metrics.regulation_score`` - after extra time the
``normaltime`` score); an own goal counts for the side it is credited to and
a penalty is a goal (both are in the score). The first half is the
listing's ``period1``, the second the 90-minute score minus it. Refused,
never guessed: goal fields that disagree (``metrics.goal_score_inconsistent``),
no ``period1``, a first half above the 90 minutes, a ``period1`` the
incidents' HT marker contradicts (``metrics.half_time_disagrees``). The first
goal of the first half: a goalless first half is "nikt" and a first half only
one side scored in is that side's, from the score alone (a readable incident
list that puts another number of goals in the first half refuses it); when
both scored in it the timed goal incidents decide
(``football_incidents.read_incidents`` -
the running score, so an own goal is the credited side's), and incidents that
contradict the score are no grade.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from bet.sofa.epochs import FOOTBALL_SIM_MARKETS
from bet.sofa.market_mapper import fold
from bet.sofa.metrics import (
    goal_score_inconsistent,
    half_time_disagrees,
    regulation_score,
)

HTFT = "htft"
RESULT_1H = "result_1h"
RESULT_2H = "result_2h"
HIGHER_HALF = "higher_scoring_half"
TEAM_BOTH_HALVES = "team_scores_both_halves"
BTTS_HALVES = "btts_halves"
BTTS_ANY_HALF = "btts_any_half"
FIRST_GOAL_1H = "first_goal_1h"
HALF_GOALS_COMBO = "half_goals_combo"
MARKETS = FOOTBALL_SIM_MARKETS
assert MARKETS == frozenset({
    HTFT, RESULT_1H, RESULT_2H, HIGHER_HALF, TEAM_BOTH_HALVES, BTTS_HALVES,
    BTTS_ANY_HALF, FIRST_GOAL_1H, HALF_GOALS_COMBO})

LINE = 0.5
# The two yes / no markets: one two-sided rung (OVER = tak, UNDER = nie).
TWO_SIDED = frozenset({TEAM_BOTH_HALVES, BTTS_ANY_HALF})
HTFT_SUBJECTS = tuple(f"{a}/{b}" for a in "1X2" for b in "1X2")
RESULT_SUBJECTS = ("1", "X", "2")
HALF_SUBJECTS = ("1H", "X", "2H")
SIDE_SUBJECTS = ("1", "2")
BTTS_HALVES_SUBJECTS = ("Tak/Tak", "Tak/Nie", "Nie/Tak", "Nie/Nie")
FG1H_NONE = "nikt"
FG1H_SUBJECTS = ("1", "2", FG1H_NONE)
COMBO_LINES = (0.5, 1.5, 2.5, 3.5)

NOTE = "FOOTBALL_SIM"

_HTFT = "1. polowa/mecz"
_RESULT_HALF = {"1.polowa - 1x2": RESULT_1H, "2.polowa - 1x2": RESULT_2H}
_HIGHER = "polowa z wieksza liczba goli"
_HIGHER_SEL = {"1.polowa": "1H", "2.polowa": "2H", "remis": "X"}
_TEAM_BOTH = re.compile(r"^(?P<team>.+) zdobedzie gola w obu polowach$")
_BTTS_HALVES = "obie druzyny strzela gola - 1.polowa/2.polowa"
_BTTS_ANY = "obie druzyny strzela w przynajmniej jednej polowie meczu"
_FG1H = "1. polowa - 1. gol"
_COMBO = "1.polowa liczba goli & 2.polowa liczba goli"
_COMBO_SEL = re.compile(
    r"^(?P<a>powyzej|ponizej) (?P<l1>\d+\.5) & (?P<b>powyzej|ponizej) (?P<l2>\d+\.5)$")
_COMBO_SUBJECT = re.compile(r"^(?P<a>[OU])(?P<l1>\d+\.5)/(?P<b>[OU])(?P<l2>\d+\.5)$")
_YES, _NO = "tak", "nie"
_DRAW = "remis"


def _fold(text: str | None) -> str:
    return " ".join(fold(text).split())


def _side(selection: str, listing_names: Sequence[str]) -> str | None:
    """"1" / "2" when the folded selection is exactly one listing name."""
    names = [_fold(n) for n in listing_names if n]
    if len(names) != 2 or names[0] == names[1] or not selection:
        return None
    if selection == names[0]:
        return "1"
    if selection == names[1]:
        return "2"
    return None


def classify(
    market_name: str | None,
    selection_name: str | None,
    listing_names: Sequence[str],
) -> tuple[str, str, float, str] | None:
    """(market, subject, line, OVER / UNDER) of one Superbet odd of the path
    markets, or None (any other market, or a selection that does not read)."""
    folded = _fold(market_name)
    sel = _fold(selection_name)
    if not folded or not sel:
        return None
    if folded == _HTFT:
        subject = sel.upper()
        return (HTFT, subject, LINE, "OVER") if subject in HTFT_SUBJECTS else None
    half = _RESULT_HALF.get(folded)
    if half is not None:
        if sel == _DRAW:
            return half, "X", LINE, "OVER"
        side = _side(sel, listing_names)
        return None if side is None else (half, side, LINE, "OVER")
    if folded == _HIGHER:
        key = _HIGHER_SEL.get(sel)
        return None if key is None else (HIGHER_HALF, key, LINE, "OVER")
    if folded == _BTTS_HALVES:
        subject = "/".join(p.capitalize() for p in sel.split("/"))
        return ((BTTS_HALVES, subject, LINE, "OVER")
                if subject in BTTS_HALVES_SUBJECTS else None)
    if folded == _BTTS_ANY:
        if sel == _YES:
            return BTTS_ANY_HALF, "", LINE, "OVER"
        if sel == _NO:
            return BTTS_ANY_HALF, "", LINE, "UNDER"
        return None
    if folded == _FG1H:
        if sel == FG1H_NONE:
            return FIRST_GOAL_1H, FG1H_NONE, LINE, "OVER"
        side = _side(sel, listing_names)
        return None if side is None else (FIRST_GOAL_1H, side, LINE, "OVER")
    if folded == _COMBO:
        m = _COMBO_SEL.match(sel)
        if m is None:
            return None
        l1, l2 = float(m.group("l1")), float(m.group("l2"))
        if l1 not in COMBO_LINES or l2 not in COMBO_LINES:
            return None
        a = "O" if m.group("a") == "powyzej" else "U"
        b = "O" if m.group("b") == "powyzej" else "U"
        return HALF_GOALS_COMBO, f"{a}{l1:g}/{b}{l2:g}", LINE, "OVER"
    team = _TEAM_BOTH.match(folded)
    if team is not None:
        side = _side(team.group("team"), listing_names)
        if side is None:
            return None
        if sel == _YES:
            return TEAM_BOTH_HALVES, side, LINE, "OVER"
        if sel == _NO:
            return TEAM_BOTH_HALVES, side, LINE, "UNDER"
    return None


def combo_lines(subject: str) -> tuple[str, float, str, float] | None:
    """("O" / "U", first-half line, "O" / "U", second-half line) of a
    half_goals_combo subject, or None."""
    m = _COMBO_SUBJECT.match(subject)
    if m is None:
        return None
    return m.group("a"), float(m.group("l1")), m.group("b"), float(m.group("l2"))


def valid_subject(market: str, subject: str) -> bool:
    if market == HTFT:
        return subject in HTFT_SUBJECTS
    if market in (RESULT_1H, RESULT_2H):
        return subject in RESULT_SUBJECTS
    if market == HIGHER_HALF:
        return subject in HALF_SUBJECTS
    if market == TEAM_BOTH_HALVES:
        return subject in SIDE_SUBJECTS
    if market == BTTS_HALVES:
        return subject in BTTS_HALVES_SUBJECTS
    if market == BTTS_ANY_HALF:
        return subject == ""
    if market == FIRST_GOAL_1H:
        return subject in FG1H_SUBJECTS
    if market == HALF_GOALS_COMBO:
        got = combo_lines(subject)
        return got is not None and got[1] in COMBO_LINES and got[3] in COMBO_LINES
    return False


def _sign(x: int) -> str:
    return "1" if x > 0 else "2" if x < 0 else "X"


def path_holds(market: str, subject: str, ht: tuple[int, int],
               ft: tuple[int, int], first_1h: str | None) -> bool | None:
    """Did the OVER of (market, subject) happen on a match with half-time
    score ``ht``, 90-minute score ``ft`` and first goal of the first half
    ``first_1h`` ("1" / "2" / "nikt"; None = not known)? None: cannot tell."""
    h1, a1 = ht
    h2, a2 = ft[0] - h1, ft[1] - a1
    if market == HTFT:
        return f"{_sign(h1 - a1)}/{_sign(ft[0] - ft[1])}" == subject
    if market == RESULT_1H:
        return _sign(h1 - a1) == subject
    if market == RESULT_2H:
        return _sign(h2 - a2) == subject
    if market == HIGHER_HALF:
        t1, t2 = h1 + a1, h2 + a2
        return ("1H" if t1 > t2 else "2H" if t2 > t1 else "X") == subject
    if market == TEAM_BOTH_HALVES:
        first, second = (h1, h2) if subject == "1" else (a1, a2)
        return first > 0 and second > 0
    if market == BTTS_HALVES:
        b1, b2 = h1 > 0 and a1 > 0, h2 > 0 and a2 > 0
        return f"{'Tak' if b1 else 'Nie'}/{'Tak' if b2 else 'Nie'}" == subject
    if market == BTTS_ANY_HALF:
        return (h1 > 0 and a1 > 0) or (h2 > 0 and a2 > 0)
    if market == FIRST_GOAL_1H:
        return None if first_1h is None else first_1h == subject
    if market == HALF_GOALS_COMBO:
        got = combo_lines(subject)
        if got is None:
            return None
        a, l1, b, l2 = got
        o1, o2 = h1 + a1 > l1, h2 + a2 > l2
        return (o1 == (a == "O")) and (o2 == (b == "O"))
    return None


def first_goal_1h(ht: tuple[int, int], ft: tuple[int, int],
                  incidents: Mapping[str, Any] | None) -> str | None:
    """"1" / "2" / "nikt": who scored the first goal of the first half; None
    when it cannot be told (both sides scored in the first half and the
    incidents do not read, or contradict the score)."""
    from bet.sofa.football_incidents import read_incidents

    h1, a1 = ht
    from_score: str | None
    if h1 + a1 == 0:
        from_score = FG1H_NONE
    elif a1 == 0:
        from_score = "1"
    elif h1 == 0:
        from_score = "2"
    else:
        from_score = None
    rec = read_incidents(incidents, (float(ft[0]), float(ft[1]))) if incidents else None
    from_list: str | None = None
    if rec is not None:
        first_half_goals = sum(1 for m in rec.goal_minutes if m < 45.0)
        if first_half_goals != h1 + a1:
            # the incidents put another number of goals in the first half
            # than period1 says: one of the two is wrong - no grade
            return None
        if first_half_goals == 0:
            from_list = FG1H_NONE
        else:
            from_list = {"home": "1", "away": "2"}.get(rec.first_goal)
    if from_score is not None:
        if from_list is not None and from_list != from_score:
            return None  # the list contradicts the score
        return from_score
    return from_list


def sim_value(market: str, subject: str, event: Mapping[str, Any],
              incidents: Mapping[str, Any] | None) -> float | str:
    """1.0 / 0.0: did the OVER of the row happen (graded at line 0.5), or
    the reason it cannot be graded."""
    if market not in MARKETS:
        return "NOT_A_SIM_MARKET"
    if not valid_subject(market, subject):
        return "UNKNOWN_SUBJECT"
    ev = dict(event)
    if goal_score_inconsistent(ev):
        return "INTERNAL_INCONSISTENT"
    score = regulation_score(ev)
    if score is None:
        return "NO_REGULATION_SCORE"
    p1h = (ev.get("homeScore") or {}).get("period1")
    p1a = (ev.get("awayScore") or {}).get("period1")
    if not isinstance(p1h, int | float) or not isinstance(p1a, int | float) \
            or isinstance(p1h, bool) or isinstance(p1a, bool):
        return "NO_HALF_TIME_SCORE"
    ht = (int(p1h), int(p1a))
    ft = (int(score[0]), int(score[1]))
    if ht[0] > ft[0] or ht[1] > ft[1] or min(ht) < 0:
        return "HALF_ABOVE_MATCH"
    if half_time_disagrees(ev, dict(incidents) if incidents else None):
        return "HALF_TIME_DISAGREES"
    first = first_goal_1h(ht, ft, incidents) if market == FIRST_GOAL_1H else None
    held = path_holds(market, subject, ht, ft, first)
    if held is None:
        return "FIRST_GOAL_UNREADABLE" if market == FIRST_GOAL_1H else "UNREADABLE"
    return 1.0 if held else 0.0


# --- what the simulator reads (bet.sofa.football_sim.path_outcomes) ------------


def path_spec(market: str, subject: str, direction: str
              ) -> tuple[str, Any, str] | None:
    """(kind, param, outcome key) of ``football_sim.path_outcomes`` whose
    event is the row's selection, or None."""
    if not valid_subject(market, subject):
        return None
    if market in TWO_SIDED:
        if direction not in ("OVER", "UNDER"):
            return None
        answer = "tak" if direction == "OVER" else "nie"
        if market == TEAM_BOTH_HALVES:
            return "team_both_halves", 0 if subject == "1" else 1, answer
        return "btts_any_half", None, answer
    if direction != "OVER":
        return None
    if market == HTFT:
        return "htft", None, subject
    if market in (RESULT_1H, RESULT_2H):
        return "half_result", 1 if market == RESULT_1H else 2, subject
    if market == HIGHER_HALF:
        return "higher_half", None, subject
    if market == BTTS_HALVES:
        return "btts_halves", None, subject
    if market == FIRST_GOAL_1H:
        return "first_goal_1h", None, "none" if subject == FG1H_NONE else subject
    got = combo_lines(subject)
    if got is None:
        return None
    a, l1, b, l2 = got
    return "half_totals", (l1, l2), f"{a}/{b}"


_WHAT = {
    HTFT: "HT/FT {s}",
    RESULT_1H: "1st-half result {s}",
    RESULT_2H: "2nd-half result {s}",
    HIGHER_HALF: "higher-scoring half {s}",
    TEAM_BOTH_HALVES: "side {s} scores in both halves",
    BTTS_HALVES: "both score 1st/2nd half {s}",
    BTTS_ANY_HALF: "both score in at least one half",
    FIRST_GOAL_1H: "first goal of the 1st half {s}",
    HALF_GOALS_COMBO: "1st / 2nd half goals {s}",
}


def describe(market: str, subject: str, direction: str) -> str:
    what = _WHAT.get(market, market).format(s=subject)
    if market in TWO_SIDED:
        what += " - yes" if direction == "OVER" else " - no"
    return what


# --- Superbet's own words (bet.sofa.superbet_names) ------------------------------


def superbet_words(market: str, subject: str, direction: str,
                   sides: tuple[str, str] | None) -> tuple[str, str] | None:
    """(market name, selection) as Superbet's screen writes the row - the
    names ``classify`` reads; None when a side's name is needed and unknown."""
    if not valid_subject(market, subject):
        return None

    def team(code: str) -> str | None:
        if sides is None:
            return None
        return sides[0] if code == "1" else sides[1]

    if market == HTFT and direction == "OVER":
        return "1. połowa/mecz", subject
    if market in (RESULT_1H, RESULT_2H) and direction == "OVER":
        name = "1.połowa - 1X2" if market == RESULT_1H else "2.połowa - 1X2"
        sel = "remis" if subject == "X" else team(subject)
        return None if sel is None else (name, sel)
    if market == HIGHER_HALF and direction == "OVER":
        return "Połowa z większą liczbą goli", {
            "1H": "1.Połowa", "2H": "2.Połowa", "X": "remis"}[subject]
    if market == TEAM_BOTH_HALVES and direction in ("OVER", "UNDER"):
        who = team(subject)
        if who is None:
            return None
        return (f"{who} zdobędzie gola w obu połowach",
                "tak" if direction == "OVER" else "nie")
    if market == BTTS_HALVES and direction == "OVER":
        return "Obie drużyny strzelą gola - 1.połowa/2.połowa", subject
    if market == BTTS_ANY_HALF and direction in ("OVER", "UNDER"):
        return ("Obie drużyny strzelą w przynajmniej jednej połowie meczu",
                "tak" if direction == "OVER" else "nie")
    if market == FIRST_GOAL_1H and direction == "OVER":
        sel = FG1H_NONE if subject == FG1H_NONE else team(subject)
        return None if sel is None else ("1. połowa - 1. gol", sel)
    if market == HALF_GOALS_COMBO and direction == "OVER":
        got = combo_lines(subject)
        if got is None:
            return None
        a, l1, b, l2 = got
        word = {"O": "powyżej", "U": "poniżej"}
        return ("1.połowa liczba goli & 2.połowa liczba goli",
                f"{word[a]} {l1:g} & {word[b]} {l2:g}")
    return None
