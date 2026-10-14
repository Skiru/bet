"""Football markets read off Sofascore's incident list - the readers.

Superbet posts, and sofa does not read, a family of football markets whose
outcome lives only in the incident list (``sofa_event_stats.incidents_json``,
``market_coverage`` families ``fb.goal_timing``, ``fb.red_cards``,
``fb.penalties``):

    "1. gol"                              which side scores first / "nikt"
    "1. gol (przedziały 10/15-minutowe)"  the band of the first goal's minute
    "Liczba czerwonych kartek"            red cards in the match, O/U 0.5 / 1.5
    "Liczba przyznanych rzutów karnych"   penalties awarded, O/U 0.5 / 1.5

This module holds only what the incident list says about one match, in
regular time (Superbet settles football on 90 minutes plus added time:
an incident at ``time`` > 90 is extra time and does not count; a shootout is
never a penalty "awarded"), read by the measurement
``scripts/sofa/measure_football_incidents.py`` and, behind
``epochs.FOOTBALL_INCIDENT_MARKETS_FROM_UTC`` (None), by OFFER / SHEET /
SETTLE (the second half of this module). Evidence:
docs/sofa/evidence/football_incidents_tennis_sets_2026-10-14.md.

Feed completeness. Sofascore's lower-league feeds carry goals and dismissals
only (``metrics.cards_not_recorded``): a missed penalty or a red card is
there sometimes. A list is read as a record of red cards and penalties only
when it carries a substitution (``metrics.INCIDENT_FEED_DETAIL``) - the
pipeline's own "full feed" rule; otherwise the reader says None.
"""

from __future__ import annotations

import json
import math
import sqlite3
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from bet.sofa.football_result import ResultConfig
from bet.sofa.market_mapper import fold
from bet.sofa.metrics import (
    INCIDENT_FEED_DETAIL,
    _is_staff_card,
    goal_score_inconsistent,
    regulation_score,
)

REGULATION_MINUTES = 90
FIRST_GOAL_HOME = "home"
FIRST_GOAL_AWAY = "away"
FIRST_GOAL_NONE = "none"
RED_CLASSES = frozenset({"red", "yellowRed"})


@dataclass(frozen=True)
class IncidentRecord:
    """What one match's incident list says, in regular time."""

    first_goal: str  # FIRST_GOAL_HOME / FIRST_GOAL_AWAY / FIRST_GOAL_NONE
    first_goal_minute: float | None  # 0-based minute of play, added time inside
    goals: tuple[int, int]  # regular-time goals by the incident scores
    goal_minutes: tuple[float, ...]  # every regular-time goal, band minutes
    full_feed: bool
    red_cards: tuple[int, int] | None  # None: not a full feed
    penalties: tuple[int, int] | None  # awarded (scored + missed); None: not full


def _listed(incidents: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    raw = (incidents or {}).get("incidents")
    if not isinstance(raw, list):
        return []
    return [i for i in raw if isinstance(i, dict)]


def _num(x: Any) -> float | None:
    if isinstance(x, int | float) and not isinstance(x, bool):
        return float(x)
    return None


def _order(inc: Mapping[str, Any]) -> tuple[int, float, float] | None:
    """(half, clock minute, added) of an incident: the order of play.

    Sofascore's ``time`` N is the N-th minute (N-1:00..N-1:59); the second
    half's clock restarts at 45:00, so a first-half added-time incident
    (``time`` 45, ``addedTime`` 3, ``timeSeconds`` ~2880) must sort before a
    second-half one at 46' (~2760 s): the half comes first."""
    t = _num(inc.get("time"))
    if t is None:
        return None
    half = 1 if t <= 45 else 2
    secs = _num(inc.get("timeSeconds"))
    added = _num(inc.get("addedTime")) or 0.0
    if added >= 900:  # the period marker's 999
        added = 0.0
    clock = secs / 60.0 if secs is not None else max(t - 1.0, 0.0) + added
    return half, clock, added


def band_minute(order: tuple[int, float, float]) -> float:
    """The minute a band market reads: first-half added time stays in the
    first half's last band (Superbet "30:00 - 45:00+"), second-half added
    time in the last ("75:00 - 90:00+")."""
    half, clock, _ = order
    return min(clock, 44.999) if half == 1 else max(clock, 45.0)


def _regular(inc: Mapping[str, Any]) -> bool:
    t = inc.get("time")
    return (
        isinstance(t, int | float)
        and not isinstance(t, bool)
        and t <= REGULATION_MINUTES
    )


def is_full_feed(incidents: Mapping[str, Any] | None) -> bool:
    return any(
        i.get("incidentType") == INCIDENT_FEED_DETAIL for i in _listed(incidents)
    )


def read_incidents(
    incidents: Mapping[str, Any] | None,
    regulation_goals: tuple[float, float] | None,
) -> IncidentRecord | None:
    """The match's first goal, red cards and penalties in regular time, or
    None when the list cannot be trusted for the first goal: no list, a goal
    without a score or a time, or regular-time goal scores that do not end on
    ``regulation_goals`` (the listing's 90-minute score)."""
    listed = _listed(incidents)
    if not listed or regulation_goals is None:
        return None
    goals = [
        i
        for i in listed
        if i.get("incidentType") == "goal"
        and not i.get("rescinded", False)
        and _regular(i)
    ]
    timed: list[tuple[tuple[int, float, float], int, int]] = []
    for g in goals:
        o = _order(g)
        hs, as_ = g.get("homeScore"), g.get("awayScore")
        if o is None or not isinstance(hs, int) or not isinstance(as_, int):
            return None
        timed.append((o, hs, as_))
    # Scores never go down: ties in the clock are broken by the running total.
    timed.sort(key=lambda x: (x[0], x[1] + x[2]))
    want = (int(regulation_goals[0]), int(regulation_goals[1]))
    if len(timed) != want[0] + want[1]:
        return None
    if timed:
        if (timed[-1][1], timed[-1][2]) != want:
            return None
        first = timed[0]
        if (first[1], first[2]) == (1, 0):
            side = FIRST_GOAL_HOME
        elif (first[1], first[2]) == (0, 1):
            side = FIRST_GOAL_AWAY
        else:
            return None
        minute: float | None = band_minute(first[0])
    else:
        side, minute = FIRST_GOAL_NONE, None
    full = is_full_feed(incidents)
    reds = pens = None
    if full:
        rh = ra = ph = pa = 0
        for i in listed:
            if not _regular(i):
                continue
            kind, cls = i.get("incidentType"), i.get("incidentClass")
            home = bool(i.get("isHome"))
            if (
                kind == "card"
                and cls in RED_CLASSES
                and not i.get("rescinded", False)
                and not _is_staff_card(i)
            ):
                rh, ra = (rh + 1, ra) if home else (rh, ra + 1)
            elif (
                kind == "goal" and cls == "penalty" and not i.get("rescinded", False)
            ) or kind == "inGamePenalty":
                ph, pa = (ph + 1, pa) if home else (ph, pa + 1)
        reds, pens = (rh, ra), (ph, pa)
    minutes = tuple(band_minute(t[0]) for t in timed)
    return IncidentRecord(side, minute, want, minutes, full, reds, pens)


def band_index(minute: float | None, edges: Sequence[float]) -> int:
    """Index of the first-goal band: 0..len(edges)-2 for a goal in
    [edges[i], edges[i+1]), len(edges)-1 for no goal. The last edge is open
    (added time of the second half falls in the last band)."""
    if minute is None:
        return len(edges) - 1
    for i in range(len(edges) - 2, -1, -1):
        if minute >= edges[i]:
            return i
    return 0


# =============================================================================
# The wired markets (epochs.FOOTBALL_INCIDENT_MARKETS_FROM_UTC; off = None, and
# nothing below is reached: OFFER maps no such rung, SHEET prices no such row).
#
# Measured 2026-06-09..2026-10-14, walk-forward (docs/sofa/evidence/
# football_incidents_tennis_sets_2026-10-14.md): at p >= 0.70 the first goal
# (n 1,376, +1.0 pp), the red cards O/U 0.5 / 1.5 and the penalties O/U 0.5 /
# 1.5 (league model, n 9,518-10,778, +0.2..+1.0 pp) met the bar (|realised -
# p| <= 2 pp with n >= 300). The first-goal minute bands never reach 0.70 and
# are NOT wired.
#
# Shapes (Superbet, unmapped_prices of 2026-10-14):
#   "1. gol"  selections: the two listing names and "nikt" (specialBetValue
#             "1"): market first_goal, subject "1" / "2" / "nikt", line 0.5,
#             OVER only - one-sided (no single price is the complement), so
#             CONFIDENCE never prints it as a single without a history curve.
#   "Liczba czerwonych kartek", "Liczba przyznanych rzutów karnych":
#             "Poniżej / Powyżej X.5": red_cards_total / penalties_total,
#             subject "", two-sided rungs. Halves and per-team variants are
#             other questions and stay unmapped.
#
# Price. first_goal: P(none) = P(0, 0) of the double chance's NB goals on
# the PURE rating centres (bet.sofa.football_result, r from its config);
# P(side first) = (1 - P(none)) x its share of the expected goals. Red cards
# and penalties: the competition's as-of rate of the event (full-feed matches
# before the day), shrunk toward the gender's rate with BASE_M matches - no
# sample, no price. All three are rating-only markets
# (tennis_winner.RATING_ONLY_MARKETS): no sample, no pool, own curve only;
# with no curve installed CONFIDENCE reads their own Superbet lines -
# NO_LINE_EVIDENCE until a bucket holds enough of them.
# =============================================================================

FIRST_GOAL = "first_goal"
RED_CARDS = "red_cards_total"
PENALTIES = "penalties_total"
INCIDENT_MARKETS = frozenset({FIRST_GOAL, RED_CARDS, PENALTIES})
FG_HOME, FG_AWAY, FG_NONE = "1", "2", "nikt"
FG_SUBJECTS = (FG_HOME, FG_AWAY, FG_NONE)
FG_LINE = 0.5
# The lines the measurement covered; another line is not priced.
COUNT_LINES = (0.5, 1.5)
BASE_M = 30.0
MIN_GENDER_MATCHES = 200
INCIDENT_NOTE = "FOOTBALL_INCIDENT_MARKETS"
INCIDENT_RULE_FIELD = "incident_rule"
# BASE_M is a chosen shrink weight, not fitted (CLAUDE.md: never strip).
UNFITTED_CONSTANTS = ("FOOTBALL_INCIDENT_BASE_M",)

_FG_MARKET = "1. gol"
_COUNT_MARKETS = {
    "liczba czerwonych kartek": RED_CARDS,
    "liczba przyznanych rzutow karnych": PENALTIES,
}
_SUBJECT_TO_RECORD = {
    FG_HOME: FIRST_GOAL_HOME,
    FG_AWAY: FIRST_GOAL_AWAY,
    FG_NONE: FIRST_GOAL_NONE,
}


def _fold(text: str | None) -> str:
    return " ".join(fold(text).split())


def classify_incident(
    market_name: str | None,
    selection_name: str | None,
    line_text: str | None,
    listing_names: Sequence[str],
) -> tuple[str, str, float, str] | None:
    """(market, subject, line, OVER / UNDER) for one odd of the three wired
    football incident markets, or None. The first goal's team is found by
    Superbet's own listing names (both needed; nothing guessed)."""
    folded = _fold(market_name)
    selection = _fold(selection_name)
    if folded == _FG_MARKET:
        if selection == FG_NONE:
            return (FIRST_GOAL, FG_NONE, FG_LINE, "OVER")
        names = [_fold(n) for n in listing_names if n]
        if len(names) != 2 or names[0] == names[1] or not selection:
            return None
        if selection == names[0]:
            return (FIRST_GOAL, FG_HOME, FG_LINE, "OVER")
        if selection == names[1]:
            return (FIRST_GOAL, FG_AWAY, FG_LINE, "OVER")
        return None
    market = _COUNT_MARKETS.get(folded)
    if market is None or line_text in (None, ""):
        return None
    try:
        line = float(str(line_text).replace(",", "."))
    except ValueError:
        return None
    if not math.isfinite(line) or line < 0 or line % 1 != 0.5:
        return None
    if selection.startswith("ponizej"):
        return (market, "", line, "UNDER")
    if selection.startswith("powyzej"):
        return (market, "", line, "OVER")
    return None


def first_goal_probs(lh: float, la: float, r: float) -> dict[str, float]:
    """P(home first), P(away first), P(no goal) for expected goals `lh` /
    `la`, NB with dispersion `r` per side, independent sides."""
    if not (math.isfinite(lh) and math.isfinite(la) and lh > 0 and la > 0):
        raise ValueError(f"goal means must be positive, got {lh!r}, {la!r}")
    if not (math.isfinite(r) and r > 0):
        raise ValueError(f"NB dispersion r must be positive, got {r!r}")
    p0h = math.exp(r * math.log(r / (r + lh)))
    p0a = math.exp(r * math.log(r / (r + la)))
    none = p0h * p0a
    return {
        FG_HOME: (1 - none) * lh / (lh + la),
        FG_AWAY: (1 - none) * la / (lh + la),
        FG_NONE: none,
    }


@dataclass
class _Count:
    n: int = 0
    o05: int = 0
    o15: int = 0

    def add(self, total: int) -> None:
        self.n += 1
        self.o05 += total >= 1
        self.o15 += total >= 2

    def k(self, line: float) -> int:
        return self.o05 if line == 0.5 else self.o15


@dataclass
class IncidentRates:
    """As-of counts of full-feed matches with a red card / a penalty, per
    competition and per gender (the measurement's ``league`` model)."""

    by_comp: dict[tuple[str, int], _Count]
    by_gender: dict[tuple[str, bool], _Count]
    women_comp: dict[int, bool]

    def p_over(self, market: str, competition_id: int, line: float) -> float | None:
        """P(the match total > line), or None: an unmeasured line, or fewer
        than MIN_GENDER_MATCHES matches behind the gender's rate."""
        if market not in (RED_CARDS, PENALTIES) or line not in COUNT_LINES:
            return None
        women = self.women_comp.get(competition_id, False)
        glob = self.by_gender.get((market, women))
        if glob is None or glob.n < MIN_GENDER_MATCHES:
            return None
        g = (glob.k(line) + 0.5) / (glob.n + 1.0)
        loc = self.by_comp.get((market, competition_id))
        if loc is None or loc.n == 0:
            return g
        return (loc.k(line) + BASE_M * g) / (loc.n + BASE_M)

    def n_comp(self, market: str, competition_id: int) -> int:
        loc = self.by_comp.get((market, competition_id))
        return loc.n if loc is not None else 0

    def add(self, comp: int, women: bool, rec: IncidentRecord) -> None:
        """Count one match (a curve replay adds them as of each day)."""
        self.women_comp[comp] = women
        for market, pair in ((RED_CARDS, rec.red_cards), (PENALTIES, rec.penalties)):
            if pair is None:
                continue
            total = pair[0] + pair[1]
            self.by_comp.setdefault((market, comp), _Count()).add(total)
            self.by_gender.setdefault((market, women), _Count()).add(total)


def rates_from_records(
    matches: Sequence[tuple[int, bool, IncidentRecord]],
) -> IncidentRates:
    """IncidentRates of (competition id, women, record) - full feeds only."""
    rates = IncidentRates({}, {}, {})
    for comp, women, rec in matches:
        rates.add(comp, women, rec)
    return rates


def load_rates(db_path: str, history: Sequence[Any], before_ts: int) -> IncidentRates:
    """IncidentRates as of `before_ts` from the football history SHEET holds
    (``football_rating.load_history``: competition, gender, 90-minute goals)
    and the cached incident lists (the database opened read-only)."""
    wanted: dict[int, tuple[int, bool, tuple[float, float]]] = {}
    for r in history:
        goals = r.values.get("goals_for") if r.ts < before_ts else None
        if goals is not None:
            wanted[r.event_id] = (r.competition_id, r.women, goals)
    out: list[tuple[int, bool, IncidentRecord]] = []
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
                rec = read_incidents(json.loads(raw), meta[2])
            except ValueError:
                continue
            if rec is not None and rec.full_feed:
                out.append((meta[0], meta[1], rec))
    finally:
        conn.close()
    return rates_from_records(out)


@dataclass(frozen=True)
class IncidentPricing:
    """What SHEET prices the incident markets with: the as-of rates and the
    double chance's NB dispersion (config/sofa_football_result.json)."""

    rates: IncidentRates
    result: ResultConfig


def incident_note(market: str, subject: str, p: float, detail: str) -> str:
    return (
        f"{INCIDENT_NOTE}: {market} {subject or 'match'} p {p:.4f} from {detail}; "
        "no sample, no price - no curve installed, the confidence is the "
        "market's own Superbet lines (epochs.FOOTBALL_INCIDENT_MARKETS)"
    )


# --- settlement -----------------------------------------------------------------


def incident_value(
    market: str,
    subject: str,
    event: Mapping[str, Any],
    incidents: Mapping[str, Any] | None,
) -> float | str:
    """The graded value of one incident-market row (first_goal: 1 / 0 for the
    subject; red_cards_total / penalties_total: the regular-time match total),
    or the reason it cannot be graded."""
    if market not in INCIDENT_MARKETS:
        return "NOT_AN_INCIDENT_MARKET"
    ev = dict(event)
    if goal_score_inconsistent(ev):
        return "INTERNAL_INCONSISTENT"
    rec = read_incidents(incidents, regulation_score(ev))
    if rec is None:
        return "INCIDENTS_UNREADABLE"
    if market == FIRST_GOAL:
        want = _SUBJECT_TO_RECORD.get(subject)
        if want is None:
            return "UNKNOWN_SUBJECT"
        return 1.0 if rec.first_goal == want else 0.0
    pair = rec.red_cards if market == RED_CARDS else rec.penalties
    if pair is None:
        return "INCIDENTS_PARTIAL_FEED"
    return float(pair[0] + pair[1])
