"""Football card points by half, red cards and penalties by side / half
(epochs.FOOTBALL_CARD_HALVES; off = None, and nothing here is reached: OFFER
maps no such rung, SHEET prices no such row).

Superbet posts, and sofa did not read (inventory 2026-10-14..20, class C):

    "1. połowa - liczba kartek"                       cards_points_1h_total
    "1. połowa - <T> liczba kartek"                   cards_points_1h_for
    "2. połowa - liczba kartek"                       cards_points_2h_total
    "2. połowa - <T> liczba kartek"                   cards_points_2h_for
    "1. / 2. połowa - najwięcej kartek"  1 / 2 / remis  most_cards_points_1h / _2h
    "1. / 2. połowa - liczba kartek - handicap"  "<T> (-0.5)"
                                                      handicap_cards_points_1h / _2h
    "Liczba czerwonych kartek <T>"                    red_cards_for
    "1.połowa - liczba czerwonych kartek"             red_cards_1h_total
    "1.połowa - liczba czerwonych kartek <T>"         red_cards_1h_for
    "<T> - liczba przyznanych rzutów karnych"         penalties_for
    "1.połowa - liczba przyznanych rzutów karnych"    penalties_1h_total
    "1.połowa - <T> - liczba przyznanych rzutów karnych"  penalties_1h_for
    "Obie drużyny otrzymają czerwoną kartkę"  Tak / Nie   both_red_cards

Grading (metrics.CARD_INCIDENT_SCOPES through extract_metric, SETTLE's
generic path): card points of a half by metrics.calculate_cards_points_by_half
- komunikat 06/2022 section 2 points, each card in the half it was SHOWN in
(the split of a two-yellow dismissal is the documented assumption there);
red cards and penalties by side / first half off football_incidents.
read_incidents (regular time, full feed only).

Price (no sample, no price - a rating-only market, tennis_winner.
RATING_ONLY_MARKETS; the confidence is the market's own Superbet lines,
NO_LINE_EVIDENCE until they accumulate, or a history curve once installed):

  card halves   per side an NB count whose mean is the side's full-match
                card-points rating centre (football_rating, cards_points_for)
                x the competition's as-of share of card points shown in that
                half (shrunk toward the gender's with SHARE_M matches); r per
                half fitted on the history (HALF_NB_R). Totals convolve the
                two sides; most / handicap read their joint (independent).
  reds / pens   the competition's as-of rate of the event in that scope,
                shrunk toward the gender's with BASE_M matches (the 10-14
                incident markets' league model; a side's rate pools home and
                away sides).

Measured walk forward (scripts/sofa/measure_football_card_halves.py,
docs/sofa/evidence/football_card_halves_2026-10-21.md).
"""

from __future__ import annotations

import json
import math
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from bet.sofa.contracts import GapReason
from bet.sofa.football_incidents import _fold, read_incidents
from bet.sofa.game_state import clamp_supremacy
from bet.sofa.market_mapper import DERIVED_DRAW_SUBJECT
from bet.sofa.metrics import calculate_cards_points_by_half

CARDS_1H_TOTAL = "cards_points_1h_total"
CARDS_1H_FOR = "cards_points_1h_for"
CARDS_2H_TOTAL = "cards_points_2h_total"
CARDS_2H_FOR = "cards_points_2h_for"
MOST_1H = "most_cards_points_1h"
MOST_2H = "most_cards_points_2h"
HCP_1H = "handicap_cards_points_1h"
HCP_2H = "handicap_cards_points_2h"
RED_FOR = "red_cards_for"
RED_1H_TOTAL = "red_cards_1h_total"
RED_1H_FOR = "red_cards_1h_for"
PEN_FOR = "penalties_for"
PEN_1H_TOTAL = "penalties_1h_total"
PEN_1H_FOR = "penalties_1h_for"
BOTH_RED = "both_red_cards"

CARD_COUNT_MARKETS = frozenset({CARDS_1H_TOTAL, CARDS_1H_FOR, CARDS_2H_TOTAL,
                                CARDS_2H_FOR})
CARD_JOINT_MARKETS = frozenset({MOST_1H, MOST_2H, HCP_1H, HCP_2H})
EVENT_MARKETS = frozenset({RED_FOR, RED_1H_TOTAL, RED_1H_FOR, PEN_FOR,
                           PEN_1H_TOTAL, PEN_1H_FOR, BOTH_RED})
MARKETS = CARD_COUNT_MARKETS | CARD_JOINT_MARKETS | EVENT_MARKETS
# The markets of the match, not of one side (subject "", or most_'s
# "1" / "2" / draw).
TOTAL_MARKETS = frozenset({CARDS_1H_TOTAL, CARDS_2H_TOTAL, MOST_1H, MOST_2H,
                           RED_1H_TOTAL, PEN_1H_TOTAL, BOTH_RED})
# The half each card market reads.
HALF_OF = {CARDS_1H_TOTAL: 1, CARDS_1H_FOR: 1, MOST_1H: 1, HCP_1H: 1,
           CARDS_2H_TOTAL: 2, CARDS_2H_FOR: 2, MOST_2H: 2, HCP_2H: 2}
# The side metric of a most_ / handicap_ market (market_mapper.derived_base
# + "_for"): SETTLE grades them through _settle_derived and extract_metric.
SIDE_METRIC_OF = {MOST_1H: CARDS_1H_FOR, HCP_1H: CARDS_1H_FOR,
                  MOST_2H: CARDS_2H_FOR, HCP_2H: CARDS_2H_FOR}

# The lines the measurement covered (Superbet's); another line is not priced.
CARD_TOTAL_LINES = {1: (0.5, 1.5, 2.5, 3.5), 2: (0.5, 1.5, 2.5, 3.5, 4.5)}
CARD_SIDE_LINES = (0.5, 1.5)
HCP_LINES = (-0.5, 0.5)
EVENT_LINES = {RED_FOR: (0.5, 1.5)}
DEFAULT_EVENT_LINES = (0.5,)

SHARE_M = 30.0
BASE_M = 30.0
MIN_GENDER_MATCHES = 200
# NB r of a side's card points in a half - fitted on the history 2025-08-01
# .. 2026-02-28 (maximum likelihood on the grid 0.5 .. 50, 1e6; scripts/sofa/
# measure_football_card_halves.py, 24,729 matches): the first half's best is
# the grid's Poisson end, the second half's 12. Out of sample (2026-03-01 ..
# 10-13, 25,211 matches) the second half's NB 12 beats its Poisson by
# -0.0104 [-0.0117, -0.0092] total log-loss a match.
HALF_NB_R: dict[int, float] = {1: 1e6, 2: 12.0}
PMF_MAX = 40
CARD_HALVES_NOTE = "FOOTBALL_CARD_HALVES"
# SHARE_M / BASE_M are chosen shrink weights, not fitted (CLAUDE.md: never strip).
UNFITTED_CONSTANTS = ("FOOTBALL_CARD_HALVES_SHARE_M", "FOOTBALL_INCIDENT_BASE_M")


# --- the count -----------------------------------------------------------------


def nb_pmf(mean: float, r: float, kmax: int = PMF_MAX) -> list[float]:
    """P(X = 0..kmax-1) for an NB count of `mean` with dispersion `r`
    (variance mean + mean^2 / r; r >= 1e6 is the Poisson)."""
    if not (math.isfinite(mean) and mean >= 0):
        raise ValueError(f"mean must be >= 0, got {mean!r}")
    if not (math.isfinite(r) and r > 0):
        raise ValueError(f"NB r must be positive, got {r!r}")
    if mean == 0:
        return [1.0] + [0.0] * (kmax - 1)
    q = mean / (r + mean)
    p = math.exp(r * math.log(r / (r + mean)))
    out = [p]
    for k in range(kmax - 1):
        p *= (k + r) / (k + 1) * q
        out.append(p)
    return out


def half_count_pmf(mean: float, r: float) -> list[float]:
    """nb_pmf with the tail beyond PMF_MAX folded into the last value."""
    pmf = nb_pmf(mean, r, PMF_MAX)
    pmf[-1] += max(0.0, 1.0 - sum(pmf))
    return pmf


def p_over(pmf: Sequence[float], line: float) -> float:
    """P(X > line) for a half line (X >= floor(line) + 1)."""
    k = math.floor(line) + 1
    return min(1.0, max(0.0, 1.0 - sum(pmf[:k])))


def total_pmf(a: Sequence[float], b: Sequence[float]) -> list[float]:
    out = [0.0] * (len(a) + len(b) - 1)
    for i, x in enumerate(a):
        if x == 0.0:
            continue
        for j, y in enumerate(b):
            out[i + j] += x * y
    return out


def margin_probs(a: Sequence[float], b: Sequence[float]) -> dict[int, float]:
    """P(home - away = d) of two independent counts."""
    out: dict[int, float] = {}
    for i, x in enumerate(a):
        if x == 0.0:
            continue
        for j, y in enumerate(b):
            out[i - j] = out.get(i - j, 0.0) + x * y
    return out


# --- OFFER -----------------------------------------------------------------------

_HALF_CARDS = "liczba kartek"
_RED = "liczba czerwonych kartek"
_PEN = "liczba przyznanych rzutow karnych"
_BOTH_RED = "obie druzyny otrzymaja czerwona kartke"


def _line(text: str | None) -> float | None:
    if text in (None, ""):
        return None
    try:
        line = float(str(text).replace(",", "."))
    except ValueError:
        return None
    if not math.isfinite(line) or line < 0 or line % 1 != 0.5:
        return None
    return line


def _ou(selection: str) -> str | None:
    if selection.startswith("ponizej"):
        return "UNDER"
    if selection.startswith("powyzej"):
        return "OVER"
    return None


def _side(name: str, listing_names: Sequence[str]) -> str | None:
    """The listing's own spelling of `name` when it is one of the two sides
    (folded equality, both names needed; nothing guessed)."""
    names = [n for n in listing_names if n]
    if len(names) != 2 or _fold(names[0]) == _fold(names[1]):
        return None
    want = _fold(name)
    for n in names:
        if want and _fold(n) == want:
            return n.strip()
    return None


def _half_prefix(folded: str) -> tuple[int | None, str]:
    """(1 / 2, the rest) for "1. polowa - ..." / "1.polowa - ...", else
    (None, folded)."""
    for half in (1, 2):
        for prefix in (f"{half}. polowa - ", f"{half}.polowa - "):
            if folded.startswith(prefix):
                return half, folded[len(prefix):]
    return None, folded


def classify_card_half(
    market_name: str | None,
    selection_name: str | None,
    line_text: str | None,
    listing_names: Sequence[str],
) -> tuple[str, str, float, str] | None:
    """(market, subject, line, OVER / UNDER) for one odd of the markets of
    this module, or None. A team subject must be one of Superbet's own two
    listing names; the line of an O/U is the specialBetValue and must agree
    with the selection's own number."""
    folded = _fold(market_name)
    selection = _fold(selection_name)
    if not folded or not selection or ";" in folded:
        return None
    if folded == _BOTH_RED:
        if selection == "tak":
            return (BOTH_RED, "", 0.5, "OVER")
        if selection == "nie":
            return (BOTH_RED, "", 0.5, "UNDER")
        return None
    half, rest = _half_prefix(folded)
    # most / handicap of a half
    if half is not None and rest == "najwiecej kartek":
        if selection in ("1", "2"):
            return (MOST_1H if half == 1 else MOST_2H, selection, 0.0, "OVER")
        if selection in ("remis", "x"):
            return (MOST_1H if half == 1 else MOST_2H, DERIVED_DRAW_SUBJECT, 0.0,
                    "OVER")
        return None
    if half is not None and rest == "liczba kartek - handicap":
        raw_sel = " ".join(str(selection_name or "").split())
        if not raw_sel.endswith(")") or " (" not in raw_sel:
            return None
        team_text, _, tail = raw_sel.rpartition(" (")
        try:
            hline = float(tail[:-1].replace(",", "."))
        except ValueError:
            return None
        team = _side(team_text, listing_names)
        if team is None or hline not in HCP_LINES:
            return None
        return (HCP_1H if half == 1 else HCP_2H, team, hline, "OVER")
    direction = _ou(selection)
    line = _line(line_text)
    if direction is None or line is None:
        return None
    # the selection's own number must be the line ("poniżej 1.5")
    sel_num = selection.split()[-1] if selection.split() else ""
    if _line(sel_num) != line:
        return None
    # "1. polowa - liczba kartek", "1. polowa - <T> liczba kartek" (a team
    # is read folded and answered in the listing's own spelling)
    if half is not None and rest == _HALF_CARDS:
        return (CARDS_1H_TOTAL if half == 1 else CARDS_2H_TOTAL, "", line, direction)
    if half is not None and rest.endswith(" " + _HALF_CARDS):
        team = _side(rest[: -len(" " + _HALF_CARDS)], listing_names)
        if team is None:
            return None
        return (CARDS_1H_FOR if half == 1 else CARDS_2H_FOR, team, line, direction)
    # red cards
    if half == 1 and rest == _RED:
        return (RED_1H_TOTAL, "", line, direction)
    if half == 1 and rest.startswith(_RED + " "):
        team = _side(rest[len(_RED) + 1:], listing_names)
        return (RED_1H_FOR, team, line, direction) if team else None
    if half is None and folded.startswith(_RED + " "):
        team = _side(folded[len(_RED) + 1:], listing_names)
        return (RED_FOR, team, line, direction) if team else None
    # penalties awarded
    if half == 1 and rest == _PEN:
        return (PEN_1H_TOTAL, "", line, direction)
    if half == 1 and rest.endswith(" - " + _PEN):
        team = _side(rest[: -len(" - " + _PEN)], listing_names)
        return (PEN_1H_FOR, team, line, direction) if team else None
    if half is None and folded.endswith(" - " + _PEN):
        team = _side(folded[: -len(" - " + _PEN)], listing_names)
        return (PEN_FOR, team, line, direction) if team else None
    return None


# --- SHEET: the as-of rates ------------------------------------------------------


@dataclass
class _Rate:
    n: int = 0
    k: int = 0


@dataclass
class _Share:
    n: int = 0
    half1: float = 0.0
    whole: float = 0.0

    def share(self) -> float | None:
        return self.half1 / self.whole if self.whole > 0 else None


@dataclass
class CardHalfRates:
    """As-of first-half card-points shares and event rates, per competition
    and per gender (bet.sofa.football_card_halves)."""

    share_comp: dict[int, _Share] = field(default_factory=dict)
    share_gender: dict[bool, _Share] = field(default_factory=dict)
    event_comp: dict[tuple[str, float, int], _Rate] = field(default_factory=dict)
    event_gender: dict[tuple[str, float, bool], _Rate] = field(default_factory=dict)
    women_comp: dict[int, bool] = field(default_factory=dict)

    def half_share(self, competition_id: int, half: int) -> float | None:
        """The competition's as-of share of card points shown in `half`,
        shrunk toward the gender's with SHARE_M matches; None: no gender
        share behind it."""
        women = self.women_comp.get(competition_id, False)
        g = self.share_gender.get(women)
        gs = g.share() if g is not None and g.n >= MIN_GENDER_MATCHES else None
        if gs is None:
            return None
        loc = self.share_comp.get(competition_id)
        ls = loc.share() if loc is not None else None
        s = gs if loc is None or ls is None else (
            (loc.n * ls + SHARE_M * gs) / (loc.n + SHARE_M))
        return s if half == 1 else 1.0 - s

    def p_over(self, market: str, competition_id: int, line: float) -> float | None:
        """P(over `line`) of an event market (a side's rate pools both
        sides), or None: an unmeasured line or a thin gender rate."""
        if market not in EVENT_MARKETS:
            return None
        if line not in EVENT_LINES.get(market, DEFAULT_EVENT_LINES):
            return None
        women = self.women_comp.get(competition_id, False)
        g = self.event_gender.get((market, line, women))
        if g is None or g.n < MIN_GENDER_MATCHES:
            return None
        gp = (g.k + 0.5) / (g.n + 1.0)
        loc = self.event_comp.get((market, line, competition_id))
        if loc is None or loc.n == 0:
            return gp
        return (loc.k + BASE_M * gp) / (loc.n + BASE_M)

    def n_comp(self, market: str, competition_id: int, line: float) -> int:
        loc = self.event_comp.get((market, line, competition_id))
        return loc.n if loc is not None else 0

    def add_cards(self, comp: int, women: bool,
                  halves: tuple[tuple[float, float], tuple[float, float]]) -> None:
        self.women_comp[comp] = women
        h1 = halves[0][0] + halves[0][1]
        whole = h1 + halves[1][0] + halves[1][1]
        for s in (self.share_comp.setdefault(comp, _Share()),
                  self.share_gender.setdefault(women, _Share())):
            s.n += 1
            s.half1 += h1
            s.whole += whole

    def add_events(
        self, comp: int, women: bool,
        reds: tuple[int, int], reds_1h: tuple[int, int],
        pens: tuple[int, int], pens_1h: tuple[int, int],
    ) -> None:
        self.women_comp[comp] = women
        outcomes: list[tuple[str, float, int]] = [
            (RED_1H_TOTAL, 0.5, int(sum(reds_1h) > 0.5)),
            (PEN_1H_TOTAL, 0.5, int(sum(pens_1h) > 0.5)),
            (BOTH_RED, 0.5, int(reds[0] >= 1 and reds[1] >= 1)),
        ]
        for i in (0, 1):
            outcomes += [
                (RED_FOR, 0.5, int(reds[i] > 0.5)),
                (RED_FOR, 1.5, int(reds[i] > 1.5)),
                (RED_1H_FOR, 0.5, int(reds_1h[i] > 0.5)),
                (PEN_FOR, 0.5, int(pens[i] > 0.5)),
                (PEN_1H_FOR, 0.5, int(pens_1h[i] > 0.5)),
            ]
        for market, line, y in outcomes:
            for rate in (self.event_comp.setdefault((market, line, comp), _Rate()),
                         self.event_gender.setdefault((market, line, women), _Rate())):
                rate.n += 1
                rate.k += y


def load_rates(db_path: str, history: Sequence[Any], before_ts: int) -> CardHalfRates:
    """CardHalfRates as of `before_ts` from the football history SHEET holds
    (``football_rating.load_history``) and the cached incident lists (the
    database opened read-only). Card shares read the matches whose
    cards_points_for the history admitted; event rates the full feeds."""
    wanted: dict[int, tuple[int, bool, Any, Any]] = {}
    for r in history:
        if r.ts >= before_ts:
            continue
        goals = r.values.get("goals_for")
        cards = r.values.get("cards_points_for")
        if goals is not None or cards is not None:
            wanted[r.event_id] = (r.competition_id, r.women, goals, cards)
    rates = CardHalfRates()
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        for eid, raw in conn.execute(
            "SELECT sofascore_event_id, incidents_json FROM sofa_event_stats "
            "WHERE incidents_json IS NOT NULL"
        ):
            meta = wanted.get(eid)
            if meta is None:
                continue
            try:
                inc = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(inc, dict):
                continue
            add_match(rates, meta[0], meta[1], inc, meta[2], meta[3])
    finally:
        conn.close()
    return rates


def add_match(
    rates: CardHalfRates, comp: int, women: bool, inc: Mapping[str, Any],
    goals: tuple[float, float] | None, cards: tuple[float, float] | None,
) -> None:
    """Count one history match into the rates (cards: the history's own
    full-match card points - (0, 0) stands for yellowCards 0)."""
    if cards is not None:
        stats = {"yellowCards": (0.0, 0.0) if sum(cards) == 0 else (1.0, 0.0)}
        halves = calculate_cards_points_by_half(dict(inc), stats)
        if not isinstance(halves, GapReason):
            rates.add_cards(comp, women, halves)
    if goals is not None:
        rec = read_incidents(inc, goals)
        if (rec is not None and rec.full_feed and rec.red_cards is not None
                and rec.red_cards_1h is not None and rec.penalties is not None
                and rec.penalties_1h is not None):
            rates.add_events(comp, women, rec.red_cards, rec.red_cards_1h,
                             rec.penalties, rec.penalties_1h)


# --- SHEET: the price of one rung ------------------------------------------------


def half_side_pmfs(
    ca: float, cb: float, share: float, half: int
) -> tuple[list[float], list[float]]:
    """The two sides' card-points pmfs in `half` from their full-match
    rating centres and the half's share."""
    r = HALF_NB_R[half]
    return half_count_pmf(ca * share, r), half_count_pmf(cb * share, r)


def card_half_p(
    market: str,
    side: str | None,
    subject: str,
    line: float,
    centres: tuple[float, float],
    share: float,
) -> float | None:
    """P(OVER) of a card-points count rung, or P(the selection) of a most_ /
    handicap_ rung (OVER only), or None: an unmeasured line or an unknown
    subject. `side` is "side_a" / "side_b" for a per-side or handicap rung."""
    half = HALF_OF.get(market)
    if half is None:
        return None
    a, b = half_side_pmfs(centres[0], centres[1], share, half)
    if market in (CARDS_1H_TOTAL, CARDS_2H_TOTAL):
        if line not in CARD_TOTAL_LINES[half]:
            return None
        return p_over(total_pmf(a, b), line)
    if market in (CARDS_1H_FOR, CARDS_2H_FOR):
        if line not in CARD_SIDE_LINES or side not in ("side_a", "side_b"):
            return None
        return p_over(a if side == "side_a" else b, line)
    margin = margin_probs(a, b)
    if market in (MOST_1H, MOST_2H):
        if subject == "1":
            return sum(p for d, p in margin.items() if d > 0)
        if subject == "2":
            return sum(p for d, p in margin.items() if d < 0)
        if subject == DERIVED_DRAW_SUBJECT:
            return margin.get(0, 0.0)
        return None
    # handicap: the subject's own count beats the other's by more than -line
    if line not in HCP_LINES or side not in ("side_a", "side_b"):
        return None
    sign = 1 if side == "side_a" else -1
    return sum(p for d, p in margin.items() if sign * d > -line)


def card_halves_note(market: str, subject: str, p: float, detail: str) -> str:
    return (
        f"{CARD_HALVES_NOTE}: {market} {subject or 'match'} p {p:.4f} from "
        f"{detail}; no sample, no price - the confidence is the market's "
        "history curve where one is installed, else its own Superbet lines "
        "(epochs.FOOTBALL_CARD_HALVES)"
    )


# --- epochs.FOOTBALL_CARD_HALVES_TERMS: the side events' game state ---------
# p = 1 - exp(-lambda_L x exp(beta x s)), lambda_L = -ln(1 - p_L) the
# competition's as-of intensity of the 0.5 selection, s the side's expected
# goal difference (FootballForecast.supremacy, clamped at
# game_state.MAX_SUPREMACY). beta by Poisson pseudo-likelihood on the event
# counts of 2025-08-01..2026-02-28, offset log lambda_L
# (scripts/sofa/measure_football_side_terms.py); scored out of sample on
# 03-01..10-13 (match bootstrap): penalties_for -0.0037 [-0.0043, -0.0031],
# penalties_1h_for -0.0018 [-0.0022, -0.0013], red_cards_for -0.0007
# [-0.0010, -0.0003]. red_cards_1h_for and the first-half totals: no term
# measured better with an interval excluding zero - they keep the flat rate.
SIDE_EVENT_SUP_BETA: Mapping[str, float] = {
    PEN_FOR: 0.2760, PEN_1H_FOR: 0.3077, RED_FOR: -0.1717}
SIDE_EVENT_LINE = 0.5


def side_event_p(market: str, line: float, p_flat: float,
                 supremacy: float | None) -> float | None:
    """The 0.5 selection's OVER p with the side's game state, or None (not a
    market / line of the term, or no supremacy): the caller keeps p_flat."""
    beta = SIDE_EVENT_SUP_BETA.get(market)
    if (beta is None or line != SIDE_EVENT_LINE or supremacy is None
            or not 0.0 < p_flat < 1.0):
        return None
    lam = -math.log(1.0 - p_flat) * math.exp(beta * clamp_supremacy(supremacy))
    return 1.0 - math.exp(-lam)
