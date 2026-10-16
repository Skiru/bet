"""Football "or" result markets, the underdog's European handicap and the
double chance & goals pairs that clear their gate, from the pure rating -
behind ``epochs.FOOTBALL_SCORE_MARKETS_FROM_UTC``
(``epochs.football_score_markets``); off (None), nothing here is reached and
OFFER / SHEET / CONFIDENCE / SETTLE are what they were.

Evidence: docs/sofa/evidence/football_score_markets_2026-10-16.md (history
curves fitted before 2026-09-01 on the replay's pure rating centres, gated
one-sided on 2026-09-01..2026-10-13, scripts/sofa/fit_score_market_curves.py;
Superbet's own lines of 2026-10-14..15 read the same way).

Every market is an event on the 90-minute score, priced like the double
chance (``football_result``): independent NB goals per side on the PURE
rating centres, r from config/sofa_football_result.json. No sample, no
price: a rating-only market (``tennis_winner.RATING_ONLY_MARKETS``) with its
own curve or nothing (``confidence.OWN_CURVE_ONLY``).

Shapes (Superbet, unmapped_prices of 2026-10-15; S = "1" home, "X" draw,
"2" away; a team selection is matched to a board side like the DNB,
``football_1x2_dnb.dnb_side``):

    result_or_over    subject S, line L: OVER = S or more than L goals.
                      OVER  "Mecz lub liczba goli (L)" "<S> lub powyżej L",
                            "<team> wygra lub powyżej X goli w meczu" /
                            "Remis lub powyżej X goli w meczu" "L - Tak";
                      UNDER the latter's "L - Nie" (the rung's complement,
                            so the margin judges it) - a price, never a row.
    result_or_under   likewise with "poniżej" (S or fewer than L goals).
    btts_or_over      subject "", line L: both score or more than L goals -
                      "Obie drużyny strzelą gola lub powyżej L gola" tak / nie.
    result_or_btts    subject S, line 0.5: S or both score -
                      "<team> wygra lub obie drużyny strzelą gola" /
                      "Remis lub obie drużyny strzelą gola" Tak / Nie.
    result_or_clean_sheet  subject S, line 0.5: S or either side keeps a
                      clean sheet ("... lub którakolwiek drużyna zachowa
                      czyste konto" Tak / Nie).
    result_handicap   subject the side given +L, line L in HANDICAP_LINES
                      (1.5 / 2.5 / 3.5): OVER = that side's goals + L beat
                      the other's ("Handicap" "<team> (L)"), UNDER = the
                      other side at -L ("<other> (-L)"). +0.5 is the double
                      chance (already read) and is left out.
    dc_and_over       subject "12", line L: "Podwójna szansa & liczba goli
                      (L)" "12 & powyżej L" - OVER only (one-sided).
    dc_and_under      subject "1X", line L: "1X & poniżej L" - OVER only.

Only the OVER of every rung is priced (an UNDER is a price for the margin:
the complements are the "&" family, measured below 0.70 or overstating).
The other "&" selections, X2 & under, the favourite's handicap, parity,
intervals and exact scores are not read (measured failing, never reaching
0.70, or never printing at Superbet's prices).

Confidence: a curve per slice ("<market>@<subject>@<line>|OVER",
``curve_market``); a men's leg in the as-of early season phase reads the
class ``season_early`` (``leg_class``), a women's match the class
``women``. A slice or class without a curve refuses the leg.

Settlement: regular time (``metrics.regulation_score``), like the double
chance; the row's value is the event indicator 1 / 0, graded at 0.5
whatever the rung's goals line (``value_line``).
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

import numpy as np

from bet.sofa.football_1x2_dnb import dnb_side
from bet.sofa.football_result import KMAX, count_pmf
from bet.sofa.market_mapper import fold
from bet.sofa.season_phase import PHASE_EARLY

RESULT_OR_OVER = "result_or_over"
RESULT_OR_UNDER = "result_or_under"
BTTS_OR_OVER = "btts_or_over"
RESULT_OR_BTTS = "result_or_btts"
RESULT_OR_CLEAN_SHEET = "result_or_clean_sheet"
HANDICAP_RESULT = "result_handicap"
DC_AND_OVER = "dc_and_over"
DC_AND_UNDER = "dc_and_under"
MARKETS = frozenset({
    RESULT_OR_OVER, RESULT_OR_UNDER, BTTS_OR_OVER, RESULT_OR_BTTS,
    RESULT_OR_CLEAN_SHEET, HANDICAP_RESULT, DC_AND_OVER, DC_AND_UNDER})
RESULT_SUBJECTS = ("1", "X", "2")
SIDE_SUBJECTS = ("1", "2")
GOAL_LINES = (0.5, 1.5, 2.5, 3.5, 4.5, 5.5)
HANDICAP_LINES = (1.5, 2.5, 3.5)
EVENT_LINE = 0.5  # the line of a rung with no goals line, and every grade's
DC_SUBJECT = {DC_AND_OVER: "12", DC_AND_UNDER: "1X"}

NOTE = "FOOTBALL_SCORE_MARKETS"
RULE_FIELD = "score_market_rule"
# A men's leg in the as-of early season phase reads its own curves, like
# 1X2 / DNB (football_1x2_dnb.curve_class): on the holdout most slices
# overstated there by 1-5 pp under the all-phase curve.
CLASS_SEASON_EARLY = "season_early"

_LUB = re.compile(r"^(.+) lub (powyzej|ponizej) (\d+(?:\.5))$")
_MECZ_LUB = re.compile(r"^mecz lub liczba goli \((\d+(?:\.5))\)$")
_WYGRA_LUB = re.compile(r"^(.+?)(?: wygra)? lub (powyzej|ponizej) x goli w meczu$")
_LINE_ANSWER = re.compile(r"^(\d+(?:\.5)) - (tak|nie)$")
_BTTS_LUB = re.compile(r"^obie druzyny strzela gola lub powyzej (\d+(?:\.5)) gola$")
_OR_BTTS = re.compile(r"^(.+?)(?: wygra)? lub obie druzyny strzela gola$")
_OR_CLEAN = re.compile(
    r"^(.+?)(?: wygra)? lub ktorakolwiek druzyna zachowa czyste konto$")
_HANDICAP_SEL = re.compile(r"^(.+) \((-?)(\d+(?:\.5))\)$")
_DC_GOALS = re.compile(r"^podwojna szansa & liczba goli \((\d+(?:\.5))\)$")
_DC_SEL = re.compile(r"^(1x|x2|12) & (powyzej|ponizej) (\d+(?:\.5))$")
_DRAW = "remis"
_HANDICAP = "handicap"
_YES, _NO = "tak", "nie"


def _fold(text: str | None) -> str:
    return " ".join(fold(text).split())


def _line(text: str, allowed: tuple[float, ...] = GOAL_LINES) -> float | None:
    value = float(text)
    return value if value in allowed else None


def _subject(who: str, home: str | None, away: str | None) -> str | None:
    """"X" for the draw, "1" / "2" for a name matching exactly one board
    side, else None (never guessed)."""
    if who == _DRAW:
        return "X"
    return dnb_side(who, home, away)


def classify(
    market_name: str | None, selection_name: str | None,
    home: str | None = None, away: str | None = None,
) -> list[tuple[str, str, float, str]]:
    """Every (market, subject, line, OVER/UNDER) one Superbet odd feeds, []
    for anything else (`home` / `away` are the board's side names)."""
    mn, sel = _fold(market_name), _fold(selection_name)
    if not mn or not sel:
        return []
    m = _MECZ_LUB.match(mn)
    if m:
        s = _LUB.match(sel)
        if s is None or s.group(3) != m.group(1):
            return []
        subject = _subject(s.group(1), home, away)
        line = _line(s.group(3))
        if subject is None or line is None:
            return []
        market = RESULT_OR_OVER if s.group(2) == "powyzej" else RESULT_OR_UNDER
        return [(market, subject, line, "OVER")]
    m = _WYGRA_LUB.match(mn)
    if m:
        s = _LINE_ANSWER.match(sel)
        subject = _subject(m.group(1), home, away)
        if s is None or subject is None:
            return []
        line = _line(s.group(1))
        if line is None:
            return []
        market = RESULT_OR_OVER if m.group(2) == "powyzej" else RESULT_OR_UNDER
        return [(market, subject, line, "OVER" if s.group(2) == _YES else "UNDER")]
    m = _BTTS_LUB.match(mn)
    if m:
        line = _line(m.group(1))
        if line is None or sel not in (_YES, _NO):
            return []
        return [(BTTS_OR_OVER, "", line, "OVER" if sel == _YES else "UNDER")]
    for pattern, market in ((_OR_BTTS, RESULT_OR_BTTS),
                            (_OR_CLEAN, RESULT_OR_CLEAN_SHEET)):
        m = pattern.match(mn)
        if m:
            subject = _subject(m.group(1), home, away)
            if subject is None or sel not in (_YES, _NO):
                return []
            return [(market, subject, EVENT_LINE,
                     "OVER" if sel == _YES else "UNDER")]
    if mn == _HANDICAP:
        s = _HANDICAP_SEL.match(sel)
        if s is None:
            return []
        side = dnb_side(s.group(1), home, away)
        line = _line(s.group(3), HANDICAP_LINES)
        if side is None or line is None:
            return []
        if s.group(2) == "-":  # the other side's +L, read as its UNDER
            return [(HANDICAP_RESULT, "2" if side == "1" else "1", line, "UNDER")]
        return [(HANDICAP_RESULT, side, line, "OVER")]
    m = _DC_GOALS.match(mn)
    if m:
        s = _DC_SEL.match(sel)
        if s is None or s.group(3) != m.group(1):
            return []
        line = _line(s.group(3))
        pair = (s.group(1).upper(), s.group(2))
        if line is None:
            return []
        if pair == ("12", "powyzej"):
            return [(DC_AND_OVER, "12", line, "OVER")]
        if pair == ("1X", "ponizej"):
            return [(DC_AND_UNDER, "1X", line, "OVER")]
    return []


def is_market(market_name: str | None) -> bool:
    """A market name this module may read (whatever its selection)."""
    mn = _fold(market_name)
    return bool(
        _MECZ_LUB.match(mn) or _WYGRA_LUB.match(mn) or _BTTS_LUB.match(mn)
        or _OR_BTTS.match(mn) or _OR_CLEAN.match(mn) or mn == _HANDICAP
        or _DC_GOALS.match(mn))


def valid_rung(market: str, subject: str, line: float) -> bool:
    """A rung this module prices."""
    if market in (RESULT_OR_OVER, RESULT_OR_UNDER):
        return subject in RESULT_SUBJECTS and line in GOAL_LINES
    if market == BTTS_OR_OVER:
        return subject == "" and line in GOAL_LINES
    if market in (RESULT_OR_BTTS, RESULT_OR_CLEAN_SHEET):
        return subject in RESULT_SUBJECTS and line == EVENT_LINE
    if market == HANDICAP_RESULT:
        return subject in SIDE_SUBJECTS and line in HANDICAP_LINES
    if market in DC_SUBJECT:
        return subject == DC_SUBJECT[market] and line in GOAL_LINES
    return False


# --- the event on a score grid ------------------------------------------------


def event_mask(market: str, subject: str, line: float,
               kmax: int = KMAX) -> np.ndarray[Any, np.dtype[np.bool_]]:
    """(kmax+1, kmax+1) bool: home goals i, away goals j for which the rung's
    OVER wins."""
    if not valid_rung(market, subject, line):
        raise ValueError(f"not a score-market rung: {market} {subject!r} {line}")
    i = np.arange(kmax + 1)[:, None]
    j = np.arange(kmax + 1)[None, :]
    total = i + j
    result = {"1": i > j, "X": i == j, "2": i < j}
    btts = (i > 0) & (j > 0)
    if market == RESULT_OR_OVER:
        mask = result[subject] | (total > line)
    elif market == RESULT_OR_UNDER:
        mask = result[subject] | (total < line)
    elif market == BTTS_OR_OVER:
        mask = btts | (total > line)
    elif market == RESULT_OR_BTTS:
        mask = result[subject] | btts
    elif market == RESULT_OR_CLEAN_SHEET:
        mask = result[subject] | ~btts
    elif market == HANDICAP_RESULT:
        mask = (i + line > j) if subject == "1" else (j + line > i)
    elif market == DC_AND_OVER:
        mask = (i != j) & (total > line)
    else:  # DC_AND_UNDER
        mask = (i >= j) & (total < line)
    out: np.ndarray[Any, np.dtype[np.bool_]] = np.broadcast_to(
        mask, (kmax + 1, kmax + 1)).copy()
    return out


def score_grid(lh: float, la: float, r: float) -> np.ndarray[Any, np.dtype[np.float64]]:
    """The 90-minute score's joint pmf for expected home / away goals."""
    if not (lh > 0 and la > 0):
        raise ValueError(f"goals centres must be positive: {lh} / {la}")
    pa = count_pmf(np.array([lh]), r)[0]
    pb = count_pmf(np.array([la]), r)[0]
    grid: np.ndarray[Any, np.dtype[np.float64]] = pa[:, None] * pb[None, :]
    return grid


def row_p(market: str, subject: str, line: float,
          grid: np.ndarray[Any, np.dtype[np.float64]]) -> float:
    """P of the rung's OVER on a score grid."""
    return float(grid[event_mask(market, subject, line, grid.shape[0] - 1)].sum())


def outcome(market: str, subject: str, line: float,
            home_goals: float, away_goals: float) -> int:
    """1 when the rung's OVER won on the 90-minute score, else 0."""
    if not valid_rung(market, subject, line):
        raise ValueError(f"not a score-market rung: {market} {subject!r} {line}")
    h, a = int(home_goals), int(away_goals)
    k = max(h, a, KMAX)
    return int(bool(event_mask(market, subject, line, k)[h, a]))


# The curve of a score market is fitted and read per SLICE - market, subject
# and line (docs/sofa/evidence/football_score_markets_2026-10-16.md: one
# curve over a market's lines hid -3..-9 pp slices - the NB tail at the high
# "or over" lines, the draw's "or" markets - inside a pooled gap of -0.5 pp).
# The row keeps its market (OFFER, SETTLE, line evidence read that); only the
# curve lookup reads "<market>@<subject or ->@<line>" (confidence.curve_market).
SLICE_SEP = "@"


def curve_market(market: str, subject: str, line: float) -> str:
    """The calibration key's market of one score-market rung."""
    return f"{market}{SLICE_SEP}{subject or '-'}{SLICE_SEP}{line:g}"


def is_curve_slice(name: str) -> bool:
    return SLICE_SEP in name and name.split(SLICE_SEP, 1)[0] in MARKETS


def value_line(row: Mapping[str, Any]) -> float:
    """The line a row's 1 / 0 value is graded against (always 0.5)."""
    del row
    return EVENT_LINE


_WHAT = {
    RESULT_OR_OVER: "{s} or over {l} goals",
    RESULT_OR_UNDER: "{s} or under {l} goals",
    BTTS_OR_OVER: "both score or over {l} goals",
    RESULT_OR_BTTS: "{s} or both score",
    RESULT_OR_CLEAN_SHEET: "{s} or a clean sheet",
    HANDICAP_RESULT: "side {s} at +{l}",
    DC_AND_OVER: "12 and over {l} goals",
    DC_AND_UNDER: "1X and under {l} goals",
}


def note(market: str, subject: str, line: float, p: float, lh: float,
         la: float, r: float) -> str:
    what = _WHAT[market].format(s=subject, l=f"{line:g}")
    return (f"{NOTE}: {what} p {p:.4f} from NB goals (r {r:g}) on the pure "
            f"rating centres home {lh:.3f} / away {la:.3f}; no sample, no "
            "price (epochs.FOOTBALL_SCORE_MARKETS)")


def leg_class(row: Mapping[str, Any], klass: str | None) -> str | None:
    """The curve class CONFIDENCE reads a sheet row with: `klass`
    (confidence.match_class) for every row, except a men's score-market row
    SHEET priced under the switch (`score_market_rule`) in an early-phase
    fixture (`result_phase`), which reads CLASS_SEASON_EARLY. A row without
    the marker (the switch off) is untouched."""
    if (klass is None and row.get("market") in MARKETS
            and row.get(RULE_FIELD) and row.get("result_phase") == PHASE_EARLY):
        return CLASS_SEASON_EARLY
    return klass


def display_market(leg: Mapping[str, Any]) -> str | None:
    """How the PDF / HTML name a score-market or set_score_not leg - in
    Superbet's own words, the side by name (the first / second name of
    `match`), "(Tak)" for the OVER this module prices; None for any other
    market. The line column beside it still prints "<line> OVER"."""
    from bet.sofa.tennis_sets import SET_SCORE_NOT, split_score_subject

    market = str(leg.get("market") or "")
    subject = str(leg.get("subject") or "")
    if market == SET_SCORE_NOT:
        parsed = split_score_subject(subject)
        return f"{parsed[0]} wygra seta (Tak)" if parsed else None
    if market not in MARKETS:
        return None
    teams = str(leg.get("match") or "").split(" - ", 1)
    home = teams[0].strip() if len(teams) == 2 else "gospodarz"
    away = teams[1].strip() if len(teams) == 2 else "gość"
    name = {"1": home, "X": "remis", "2": away}.get(subject, subject)
    line = f"{float(leg.get('line') or 0):g}"
    if market == RESULT_OR_OVER:
        return f"Mecz lub liczba goli: {name} lub powyżej {line} (Tak)"
    if market == RESULT_OR_UNDER:
        return f"Mecz lub liczba goli: {name} lub poniżej {line} (Tak)"
    if market == BTTS_OR_OVER:
        return f"Obie drużyny strzelą gola lub powyżej {line} gola (Tak)"
    if market == RESULT_OR_BTTS:
        wins = "" if subject == "X" else "wygra "
        return f"{name} {wins}lub obie drużyny strzelą gola (Tak)"
    if market == RESULT_OR_CLEAN_SHEET:
        return (f"{name} {'' if subject == 'X' else 'wygra '}lub którakolwiek "
                "drużyna zachowa czyste konto (Tak)")
    if market == HANDICAP_RESULT:
        return f"Handicap: {name} (+{line})"
    if market == DC_AND_OVER:
        return f"Podwójna szansa & liczba goli: 12 & powyżej {line}"
    return f"Podwójna szansa & liczba goli: 1X & poniżej {line}"
