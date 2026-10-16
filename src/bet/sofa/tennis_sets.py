"""Tennis set winner and exact score in sets from the as-of rating.

Behind ``epochs.TENNIS_SET_MARKETS_FROM_UTC`` (``epochs.tennis_set_markets``);
off (None, the default), nothing here is reached and OFFER / SAMPLES / SHEET
/ CONFIDENCE are what they were. Follows the match winner
(``bet.sofa.tennis_winner``, audit 2026-10-13 D2) exactly: a rating-only
market (``tennis_winner.RATING_ONLY_MARKETS``), no sample, no pool, its own
curve or nothing (``confidence.OWN_CURVE_ONLY``).

Evidence (walk-forward 2026-06-09..2026-10-14, the sheet's own as-of rating,
``scripts/sofa/measure_tennis_outcome_model.py``; docs/sofa/evidence/
football_incidents_tennis_sets_2026-10-14.md): set-1 winner log-loss -0.0908
vs the class base rate, at p >= 0.70 0.788 forecast / 0.799 realised
(n 12,174); set-2 winner -0.0902, 0.793 / 0.797 (n 12,502); exact sets
-0.1427, 0.786 / 0.802 (n 4,107 selections). All three met the bar
(|realised - p| <= 2 pp with n >= 300 at p >= 0.70).

Shapes (Superbet, unmapped_prices of 2026-10-14):

    "X. set - zwycięzca"  selections "1. set - <name>" / "2. set - <name>"
        market ``set1_won_for`` / ``set2_won_for``, subject the listing's
        FIRST name, line 0.5, OVER = he wins the set, UNDER = the other
        player's price - one two-sided rung, like the match winner.
        A "3. set - <name>" selection (void unless played) is not read.
    "Dokładny wynik"  selections "2:0" / "2:1" / "1:2" / "0:2" (the listing's
        first name first)
        market ``set_score``, subject "<first name> a:b", line 0.5, OVER only
        (one-sided: no single price is its complement - CONFIDENCE never
        prints it without a history curve).

Price. From the rating's 600 neighbours of the HOME player
(``MatchForecast.neighbours_home``): P(home wins set N) = the share of
neighbours who won their set N, smoothed (k + 0.5) / (n + 1); the exact
score shares smoothed (k + 0.5) / (n + 2) - the measurement's arithmetic.
Best of three only (``run_sheet.tennis_forecast`` gives no forecast for a
best-of-five).

Settlement. From the listing's set scores (``homeScore.periodN``); a
retirement / walkover is refunded before any grade (settle.REFUND_REASONS).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from bet.sofa.market_mapper import fold

SET1_WON_FOR = "set1_won_for"
SET2_WON_FOR = "set2_won_for"
SET_SCORE = "set_score"
# epochs.TENNIS_SET_COMPLEMENTS: NOT this exact score, read from the player
# named in the subject - always "<name> 0:2" (OVER = he wins at least a set;
# "not X 2:0" is "not Y 0:2" of the other player, one rung, never two) - the
# complement of a set_score selection, which Superbet quotes two-sided as
# "<name> wygra seta" / "<name> wygra bez straty seta" / "Handicap setowy" /
# "<name> liczba setów" 0.5 (classify_set_complement). Only its OVER is
# priced (its UNDER is the set_score selection itself, already read).
SET_SCORE_NOT = "set_score_not"
SET_WINNER_MARKETS = {1: SET1_WON_FOR, 2: SET2_WON_FOR}
SET_MARKETS = frozenset({SET1_WON_FOR, SET2_WON_FOR, SET_SCORE, SET_SCORE_NOT})
COMPLEMENT_SCORE = "0:2"
COMPLEMENT_NOTE = "TENNIS_SET_COMPLEMENTS"
COMPLEMENT_RULE_FIELD = "set_complement_rule"
SET_LINE = 0.5
SCORES = ("2:0", "2:1", "1:2", "0:2")
SET_NOTE = "TENNIS_SET_MARKETS"
SET_RULE_FIELD = "set_market_rule"

_SET_WINNER_MARKET = "x. set - zwyciezca"
_SCORE_MARKET = "dokladny wynik"
_SET_SELECTION = re.compile(r"^([12])\. set - (.+)$")


def _fold(text: str | None) -> str:
    return " ".join(fold(text).split())


def classify_set_market(
    market_name: str | None,
    selection_name: str | None,
    listing_names: Sequence[str],
) -> tuple[str, str, float, str] | None:
    """(market, subject, 0.5, OVER / UNDER) for one odd of the tennis set
    winner or exact sets score, or None. Without both listing names the
    subject is unknown and nothing is guessed."""
    folded = _fold(market_name)
    if folded not in (_SET_WINNER_MARKET, _SCORE_MARKET):
        return None
    names = [n for n in listing_names if n]
    if len(names) != 2 or _fold(names[0]) == _fold(names[1]):
        return None
    selection = _fold(selection_name)
    if folded == _SET_WINNER_MARKET:
        m = _SET_SELECTION.match(selection)
        if m is None:
            return None
        market = SET_WINNER_MARKETS[int(m.group(1))]
        who = m.group(2).strip()
        if who == _fold(names[0]):
            return (market, names[0], SET_LINE, "OVER")
        if who == _fold(names[1]):
            return (market, names[0], SET_LINE, "UNDER")
        return None
    if selection not in SCORES:
        return None
    return (SET_SCORE, score_subject(names[0], selection), SET_LINE, "OVER")


_WINS_A_SET = re.compile(r"^(.+) wygra seta$")
_WINS_TO_NIL = re.compile(r"^(.+) wygra bez straty seta$")
_SETS_COUNT = re.compile(r"^(.+) liczba setow$")
_SET_HANDICAP = "handicap setowy"
_SET_HANDICAP_SEL = re.compile(r"^(.+) \((-?)1\.5\)$")
_YES, _NO = "tak", "nie"


def classify_set_complement(
    market_name: str | None,
    selection_name: str | None,
    listing_names: Sequence[str],
) -> tuple[str, str, float, str] | None:
    """(set_score_not, "<name> 0:2", 0.5, OVER / UNDER) for one odd of a
    two-sided market that splits a match at one player's 0:2
    (epochs.TENNIS_SET_COMPLEMENTS), or None:

        "<X> wygra seta"            Tak = not X 0:2 (OVER), Nie = X 0:2
        "<X> wygra bez straty seta" Nie = not X 2:0 = not Y 0:2 (OVER of
                                    the other player's rung), Tak = UNDER
        "<X> liczba setów"          Powyżej 0.5 = not X 0:2, Poniżej 0.5
        "Handicap setowy"           "<X> (1.5)" = not X 0:2,
                                    "<Y> (-1.5)" = Y 2:0 = X 0:2 (UNDER)

    `name` is the listing name (both must be known and differ); a name in
    the market that is neither side is no row (never guessed)."""
    names = [n for n in listing_names if n]
    if len(names) != 2 or _fold(names[0]) == _fold(names[1]):
        return None
    by_fold = {_fold(n): n for n in names}
    folded, sel = _fold(market_name), _fold(selection_name)

    def other(name: str) -> str:
        return names[1] if name == names[0] else names[0]

    def rung(name: str, over: bool) -> tuple[str, str, float, str]:
        return (SET_SCORE_NOT, score_subject(name, COMPLEMENT_SCORE), SET_LINE,
                "OVER" if over else "UNDER")

    m = _WINS_A_SET.match(folded)
    if m and m.group(1) in by_fold and sel in (_YES, _NO):
        return rung(by_fold[m.group(1)], sel == _YES)
    m = _WINS_TO_NIL.match(folded)
    if m and m.group(1) in by_fold and sel in (_YES, _NO):
        return rung(other(by_fold[m.group(1)]), sel == _NO)
    m = _SETS_COUNT.match(folded)
    if m and m.group(1) in by_fold and sel in ("powyzej 0.5", "ponizej 0.5"):
        return rung(by_fold[m.group(1)], sel.startswith("powyzej"))
    if folded == _SET_HANDICAP:
        s = _SET_HANDICAP_SEL.match(sel)
        if s is None or s.group(1) not in by_fold:
            return None
        who = by_fold[s.group(1)]
        if s.group(2) == "-":
            return rung(other(who), False)
        return rung(who, True)
    return None


def complement_note(subject: str, p: float, side: str, pool: int,
                    table_scope: str) -> str:
    who = "home" if side == "side_a" else "away"
    return (
        f"{COMPLEMENT_NOTE}: not {subject} ({who}) p {p:.4f} = 1 - the exact "
        f"score's share of the rating's {pool} neighbours (table "
        f"{table_scope}); no sample, no price (epochs.TENNIS_SET_COMPLEMENTS)"
    )


def score_subject(first_name: str, score: str) -> str:
    return f"{first_name} {score}"


def split_score_subject(subject: str) -> tuple[str, str] | None:
    """(the player the score is read from, "a:b"), or None."""
    name, _, score = subject.rpartition(" ")
    if not name or score not in SCORES:
        return None
    return name, score


def flip(score: str) -> str:
    a, b = score.split(":")
    return f"{b}:{a}"


# --- price (from the home player's neighbours) ---------------------------------


def _wins(games: tuple[int, int]) -> bool:
    return games[0] > games[1]


def won_match(o: Any) -> bool:
    """A neighbour outcome's player won the match: two sets of three (the
    measurement's ``_won_match``; a match tiebreak counts as one game)."""
    won = _wins(o.set1) + _wins(o.set2)
    if o.sets == 2:
        return bool(won == 2)
    third_for = o.games_for - o.set1[0] - o.set2[0]
    third_against = o.games_against - o.set1[1] - o.set2[1]
    return bool(third_for > third_against)


def set_win_p(neighbours_home: Sequence[Any], set_index: int) -> float | None:
    """P(the HOME player wins set `set_index`), smoothed; None with no pool."""
    n = len(neighbours_home)
    if n == 0 or set_index not in SET_WINNER_MARKETS:
        return None
    k = sum(1 for o in neighbours_home if _wins(o.set1 if set_index == 1 else o.set2))
    return (k + 0.5) / (n + 1.0)


def score_probs(neighbours_home: Sequence[Any]) -> dict[str, float] | None:
    """P of each exact best-of-three score from the HOME player's side."""
    n = len(neighbours_home)
    if n == 0:
        return None
    ks = dict.fromkeys(SCORES, 0)
    for o in neighbours_home:
        won = won_match(o)
        if o.sets == 2:
            ks["2:0" if won else "0:2"] += 1
        else:
            ks["2:1" if won else "1:2"] += 1
    return {s: (k + 0.5) / (n + 2.0) for s, k in ks.items()}


def set_note(
    market: str, subject: str, p: float, side: str, pool: int, table_scope: str
) -> str:
    who = "home" if side == "side_a" else "away"
    return (
        f"{SET_NOTE}: {market} {subject} ({who}) p {p:.4f} from the rating's "
        f"{pool} neighbours (table {table_scope}); no sample, no price - the "
        "confidence is the market's history curve where one is installed "
        "(2026-10-15), else its own Superbet lines "
        "(epochs.TENNIS_SET_MARKETS)"
    )


# --- settlement -----------------------------------------------------------------


def _periods(event: Mapping[str, Any]) -> list[tuple[int, int]] | None:
    home = event.get("homeScore") or {}
    away = event.get("awayScore") or {}
    out: list[tuple[int, int]] = []
    for i in range(1, 6):
        h, a = home.get(f"period{i}"), away.get(f"period{i}")
        if h is None and a is None:
            break
        if not isinstance(h, int) or not isinstance(a, int):
            return None
        out.append((h, a))
    return out


def set_value(
    market: str, subject_is_home: bool, score: str | None, event: Mapping[str, Any]
) -> float | str:
    """The graded value of one set-market row (1 / 0), or why not.

    set1/2_won_for: did the subject win that set; set_score: did the match
    end `score` read from the subject's side. Best of three only."""
    periods = _periods(event)
    if periods is None or len(periods) < 2:
        return "SET_SCORES_ABSENT"
    if any(h == a for h, a in periods):
        return "SET_SCORES_INCONSISTENT"
    if market in (SET1_WON_FOR, SET2_WON_FOR):
        h, a = periods[0] if market == SET1_WON_FOR else periods[1]
        return 1.0 if (h > a) == subject_is_home else 0.0
    if market not in (SET_SCORE, SET_SCORE_NOT) or score not in SCORES:
        return "NOT_A_SET_MARKET"
    home_sets = sum(1 for h, a in periods if h > a)
    away_sets = len(periods) - home_sets
    if max(home_sets, away_sets) != 2 or len(periods) > 3:
        return "NOT_BEST_OF_THREE"
    mine, theirs = (home_sets, away_sets) if subject_is_home else (away_sets, home_sets)
    hit = f"{mine}:{theirs}" == score
    if market == SET_SCORE_NOT:  # epochs.TENNIS_SET_COMPLEMENTS
        hit = not hit
    return 1.0 if hit else 0.0
