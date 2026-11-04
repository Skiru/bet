"""Our rating against Superbet's picture of the match - a flag on the leg,
never a gate.

Operator, 2026-11-04 ("wdróż od dzisiaj"), after FC Seoul - Thể Công - Viettel
(AFC Champions League Two, sofa:16864091): "FC Seoul - liczba goli: poniżej
3.5" @1.44 at confidence 0.751 while our rating saw the sides almost level
and Superbet priced Seoul at 1.10 to win; a week earlier (10-28,
sofa:16864128) Seoul won 5:0 in Hanoi and the same UNDER legs lost.

Measured (docs/sofa/evidence/rating_vs_market_disagreement_2026-11-04.md,
days 2026-09-24..2026-11-03, printed from 10-05; match bootstrap): D is the
market's expected goal margin for its favourite minus our rating's margin for
that same side. Legs whose correctness depends on how strong the favourite is
("dependent": the favourite's team goals UNDER, the underdog's team goals
OVER, the underdog's result - 1X2 underdog or draw, double chance underdog +
X, DNB underdog, result handicap underdog +L - and "underdog / draw or
under") realised, at D >= 1.0, about at their price and below their
confidence. Printed dependent legs, D >= 1.0 minus the D -0.5..0.5 band:
against the price dev (to 10-24) -6.1 pp [-11.7, -0.3], hold-out (from
10-25) +1.8 pp [-4.3, +7.5]; against the confidence dev -12.9 pp [-18.8,
-6.9], hold-out -3.4 pp [-9.3, +2.6]; all days -8.6 pp [-13.0, -4.7] on 963
legs / 360 matches. ROI not measurably worse (-3.6 pp [-9.3, +1.8]): the
printed number over-promises, the money is alike - the same mechanism as
bet.sofa.price_gap. Legs on the market's side (favourite OVER, favourite
wins) realised ABOVE their confidence at D >= 1 (+16.1 pp, whole ladder) and
are not flagged.

So the leg says it, and nothing moves: no leg is added, removed or re-ranked,
no confidence changes, confidence.read_value does not read it, and it is not
a read / veto ground on its own (epochs.RATING_MARKET_GAP_FROM_UTC).

The two views, exactly as the measurement built them:

- ours: the pure rating centres SHEET wrote in its notes (05_sheet.json) - the
  goals_total row's "FOOTBALL_RATING: centre .. from the rating (home X +
  away Y", else both goals_for rows' "(home X" / "(away Y", else a result
  row's "pure rating centres home X / away Y". SHEET has no structured field
  for them; `rating_view` is the one parser.
- the market's: two independent NB goal counts (r = the result model's
  FOOTBALL_RESULT_NB_R, bet.sofa.football_result) fitted by least squares on
  a 0.05..5.0 grid (step 0.025) to the devigged (proportional) 1X2 "1" / "2",
  double chance "12", both team-total ladders and the match-total ladder of
  04_offer.json. A match needs 1X2 "1" and "2", or both team totals
  (`market_observations` / the measurement's `ok`); else no entry.

Open question (suspicion, not a measurement): continental cups at D >= 1
realised -16.8 pp against the price on 14 hold-out matches (whole ladder) -
re-measure at ~100 hold-out matches.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import numpy as np
from numpy.typing import NDArray

F64 = NDArray[np.float64]

FLAG = "RATING_BELOW_MARKET_MARGIN"
# Goals: the market's margin for its favourite minus ours for that side, at or
# above which a dependent leg is flagged - fixed before the measurement looked
# at a result (the operator's question), its bucket edge.
THRESHOLD = 1.0
EVIDENCE = "docs/sofa/evidence/rating_vs_market_disagreement_2026-11-04.md"
# Printed dependent legs, D >= 1.0 minus D -0.5..0.5, hold-out from 10-25.
MEASURED_VS_CONFIDENCE_PP = -3.4
MEASURED_VS_CONFIDENCE_CI_PP = (-9.3, 2.6)
MEASURED_VS_PRICE_PP = 1.8
MEASURED_VS_PRICE_CI_PP = (-4.3, 7.5)
MEASURED_ON = ("printed football dependent legs, D >= 1.0 minus D -0.5..0.5, "
               "hold-out 2026-10-25..2026-11-03 (all days 2026-10-05..11-03: "
               "-8.6 pp [-13.0, -4.7] vs confidence on 963 legs / 360 "
               "matches); " + EVIDENCE)
WINDOW_PL = "25.10-3.11"

# The measurement's groups (its analyze.group_of / tables.DEP): full match
# only - its halves were measured apart and are not flagged.
FAV_TT_UNDER = "FAV_TT_UNDER"
DOG_TT_OVER = "DOG_TT_OVER"
DOG_RESULT = "DOG_RESULT"
DOG_OR_UNDER = "DOG_OR_UNDER"
DEPENDENT = frozenset({FAV_TT_UNDER, DOG_TT_OVER, DOG_RESULT, DOG_OR_UNDER})
GROUP_PL = {
    FAV_TT_UNDER: "faworyt - gole poniżej",
    DOG_TT_OVER: "słabszy - gole powyżej",
    DOG_RESULT: "wynik słabszego",
    DOG_OR_UNDER: "słabszy / remis lub poniżej",
}

# --- the grid fit (the measurement's build_legs.py) ---------------------------

K = 16  # goals per side 0..K-1, not renormalised (as measured)
GRID: F64 = np.round(np.arange(0.05, 5.0001, 0.025), 4)
TOTAL_LINES = (0.5, 1.5, 2.5, 3.5, 4.5, 5.5)
_MARKETS = frozenset({"result_1x2", "double_chance", "goals_for", "goals_total"})

_RE_TOTAL = re.compile(
    r"FOOTBALL_RATING: centre ([\d.]+) from the rating "
    r"\(home ([\d.]+) \+ away ([\d.]+)")
_RE_SIDE = re.compile(
    r"FOOTBALL_RATING: centre ([\d.]+) from the rating \((home|away) ([\d.]+)")
_RE_PURE = re.compile(r"pure rating centres home ([\d.]+) / away ([\d.]+)")

SOURCE_TOTAL = "05_sheet goals_total FOOTBALL_RATING note"
SOURCE_SIDES = "05_sheet goals_for FOOTBALL_RATING notes"
SOURCE_PURE = "05_sheet result note (pure rating centres)"


@dataclass(frozen=True)
class _Tables:
    pmf: F64
    surv: F64
    p_hwin: F64
    p_awin: F64
    p_draw: F64
    p_tot_over: dict[float, F64]


@lru_cache(maxsize=4)
def _tables(r: float) -> _Tables:
    p = r / (r + GRID)
    pmf = np.empty((len(GRID), K))
    pmf[:, 0] = p ** r
    for i in range(1, K):
        pmf[:, i] = pmf[:, i - 1] * (i - 1 + r) / i * (1 - p)
    cdf = np.cumsum(pmf, axis=1)
    shift = np.hstack([np.zeros((len(GRID), 1)), cdf[:, :-1]])
    p_hwin = pmf @ shift.T
    tot: dict[float, F64] = {}
    for line in TOTAL_LINES:
        m = int(math.floor(line))
        acc = np.zeros((len(GRID), len(GRID)))
        for i in range(m + 1):
            acc += np.outer(pmf[:, i], cdf[:, m - i])
        tot[line] = 1 - acc
    return _Tables(pmf, 1 - cdf, p_hwin, p_hwin.T.copy(), pmf @ pmf.T, tot)


def nb_r() -> float:
    """The NB size SHEET's result model reads (FOOTBALL_RESULT_NB_R)."""
    from bet.sofa import football_result  # leaf import, numpy already loaded
    return football_result.load_config().nb_r


def devig(over: Any, under: Any) -> float | None:
    """Proportional devig of a two-sided rung; None without both prices."""
    if not over or not under:
        return None
    a, b = 1.0 / float(over), 1.0 / float(under)
    return a / (a + b)


def fit_market(obs: Iterable[tuple[str, float, float]],
               r: float) -> tuple[float, float, int, float] | None:
    """(lambda_home, lambda_away, observations used, mean squared error) of
    the least-squares grid fit, or None when no observation was usable.
    Kinds: hwin, awin, nodraw, h_over, a_over, t_over."""
    t = _tables(r)
    sse = np.zeros((len(GRID), len(GRID)))
    n = 0
    for kind, line, p in obs:
        if kind == "hwin":
            sse += (t.p_hwin - p) ** 2
        elif kind == "awin":
            sse += (t.p_awin - p) ** 2
        elif kind == "nodraw":
            sse += (1 - t.p_draw - p) ** 2
        elif kind in ("h_over", "a_over"):
            i = int(math.floor(line))
            if i >= K - 1:
                continue
            col = t.surv[:, i]
            sse += ((col[:, None] if kind == "h_over" else col[None, :]) - p) ** 2
        elif kind == "t_over":
            if line not in t.p_tot_over:
                continue
            sse += (t.p_tot_over[line] - p) ** 2
        else:
            continue
        n += 1
    if n == 0:
        return None
    ih, ia = np.unravel_index(int(np.argmin(sse)), sse.shape)
    return float(GRID[ih]), float(GRID[ia]), n, float(sse[ih, ia] / n)


# --- the two views -----------------------------------------------------------


@dataclass(frozen=True)
class RatingView:
    home: float
    away: float
    source: str


@dataclass(frozen=True)
class EventView:
    """One match's two pictures. `sides`: goals_for subject -> home / away."""
    market_home: float
    market_away: float
    observations: int
    rmse: float
    rating: RatingView
    sides: Mapping[str, str] = field(default_factory=dict)
    home_name: str | None = None
    away_name: str | None = None

    @property
    def favourite(self) -> str:
        return "home" if self.market_home >= self.market_away else "away"

    @property
    def market_margin(self) -> float:
        return abs(self.market_home - self.market_away)

    @property
    def rating_margin(self) -> float:
        """Our expected goal margin for the market's favourite."""
        own = self.rating.home - self.rating.away
        return own if self.favourite == "home" else -own

    @property
    def d(self) -> float:
        return self.market_margin - self.rating_margin


def _notes(row: Mapping[str, Any]) -> str:
    return " | ".join(str(n) for n in row.get("notes") or [])


def rating_view(rows: Iterable[Mapping[str, Any]]
                ) -> tuple[RatingView | None, dict[str, str]]:
    """Our pure rating centres of one match from its 05_sheet rows, and the
    goals_for subject -> side map their notes give (the measurement's
    extract.py precedence: goals_total note, both goals_for notes, a result
    note). (None, map) when no row names them."""
    total: tuple[float, float] | None = None
    pure: tuple[float, float] | None = None
    side_rating: dict[str, tuple[str | None, float | None]] = {}
    for row in rows:
        market = row.get("market")
        notes = _notes(row)
        if pure is None and "pure rating centres" in notes:
            mp = _RE_PURE.search(notes)
            if mp:
                pure = (float(mp.group(1)), float(mp.group(2)))
        if market == "goals_for":
            subject = str(row.get("subject") or "")
            ms = _RE_SIDE.search(notes)
            if ms:
                side_rating[subject] = (ms.group(2), float(ms.group(3)))
            elif subject not in side_rating:
                side_rating[subject] = (None, None)
        elif market == "goals_total" and total is None:
            mt = _RE_TOTAL.search(notes)
            if mt:
                total = (float(mt.group(2)), float(mt.group(3)))
    smap = {s: side for s, (side, _) in side_rating.items() if side}
    if len(smap) == 1 and len(side_rating) == 2:
        (known, side), = smap.items()
        other = next(s for s in side_rating if s != known)
        smap[other] = "away" if side == "home" else "home"
    inv = {v: k for k, v in smap.items()}
    if total is not None:
        return RatingView(total[0], total[1], SOURCE_TOTAL), smap
    if "home" in inv and "away" in inv:
        rh, ra = side_rating[inv["home"]][1], side_rating[inv["away"]][1]
        if rh and ra:
            return RatingView(rh, ra, SOURCE_SIDES), smap
    if pure is not None:
        return RatingView(pure[0], pure[1], SOURCE_PURE), smap
    return None, smap


def market_observations(rungs: Iterable[Mapping[str, Any]],
                        sides: Mapping[str, str]
                        ) -> list[tuple[str, float, float]]:
    """The devigged observations of one 04_offer entry's rungs."""
    obs: list[tuple[str, float, float]] = []
    for rung in rungs:
        market = rung.get("market")
        if market not in _MARKETS:
            continue
        p = devig(rung.get("over_odds"), rung.get("under_odds"))
        if p is None:
            continue
        subject, line = rung.get("subject"), float(rung.get("line") or 0.0)
        if market == "result_1x2" and subject in ("1", "2"):
            obs.append(("hwin" if subject == "1" else "awin", line, p))
        elif market == "double_chance" and subject == "12":
            obs.append(("nodraw", line, p))
        elif market == "goals_for" and sides.get(str(subject)):
            obs.append(("h_over" if sides[str(subject)] == "home" else "a_over",
                        line, p))
        elif market == "goals_total":
            obs.append(("t_over", line, p))
    return obs


def fit_ok(obs: Iterable[tuple[str, float, float]]) -> bool:
    """The measurement's `ok`: 1X2 home and away, or both team totals."""
    kinds = {o[0] for o in obs}
    return ({"hwin", "awin"} <= kinds) or ({"h_over", "a_over"} <= kinds)


def event_view(sheet_rows: Iterable[Mapping[str, Any]],
               rungs: Iterable[Mapping[str, Any]] | None,
               r: float, home_name: str | None = None,
               away_name: str | None = None) -> EventView | None:
    """Both views of one match, or None when either is missing."""
    rating, smap = rating_view(sheet_rows)
    if rating is None or rungs is None:
        return None
    obs = market_observations(rungs, smap)
    if not fit_ok(obs):
        return None
    fit = fit_market(obs, r)
    if fit is None:
        return None
    lh, la, n, mse = fit
    return EventView(lh, la, n, math.sqrt(mse), rating, smap,
                     home_name, away_name)


def views_by_event(sheet: Iterable[Mapping[str, Any]],
                   offers: Iterable[Mapping[str, Any]],
                   event_ids: Iterable[int],
                   names: Mapping[int, tuple[str | None, str | None]] | None = None,
                   r: float | None = None) -> dict[int, EventView]:
    """One view per football match of `event_ids` that has both (one pass
    over the sheet and the offer; the offer's last entry of a match wins, as
    measured)."""
    wanted = {int(e) for e in event_ids}
    if not wanted:
        return {}
    rows: dict[int, list[Mapping[str, Any]]] = {}
    for row in sheet:
        if row.get("sport", "football") != "football":
            continue
        eid = row.get("sofascore_event_id")
        if eid is not None and int(eid) in wanted:
            rows.setdefault(int(eid), []).append(row)
    rungs: dict[int, list[Mapping[str, Any]]] = {}
    for entry in offers:
        eid = entry.get("sofascore_event_id")
        if eid is not None and int(eid) in rows:
            rungs[int(eid)] = list(entry.get("rungs") or [])
    size = nb_r() if r is None else r
    out: dict[int, EventView] = {}
    for eid, ev_rows in rows.items():
        home, away = (names or {}).get(eid, (None, None))
        view = event_view(ev_rows, rungs.get(eid), size, home, away)
        if view is not None:
            out[eid] = view
    return out


# --- the leg -----------------------------------------------------------------


def leg_group(leg: Mapping[str, Any], view: EventView) -> str | None:
    """The measurement's group of a leg (analyze.group_of), only for the
    groups it named dependent; None for every other leg."""
    market = str(leg.get("market") or "")
    subject = str(leg.get("subject") or "")
    direction = str(leg.get("direction") or "")
    fav = "1" if view.favourite == "home" else "2"
    dog = "2" if fav == "1" else "1"
    if market == "goals_for":
        side = view.sides.get(subject)
        if side is None:
            return None
        if ("1" if side == "home" else "2") == fav:
            return FAV_TT_UNDER if direction == "UNDER" else None
        return DOG_TT_OVER if direction == "OVER" else None
    if direction == "OVER":
        if market == "result_1x2":
            return DOG_RESULT if subject in (dog, "X") else None
        if market == "double_chance":
            return DOG_RESULT if subject == ("1X" if dog == "1" else "X2") else None
        if market == "result_handicap":
            return DOG_RESULT if subject == dog else None
        if market == "result_or_under":
            return DOG_OR_UNDER if subject in (dog, "X") else None
        if market == "dc_and_under":
            # 1X & under: the underdog's side only when the home side is it
            return DOG_OR_UNDER if subject == "1X" and dog == "1" else None
    if market == "draw_no_bet" and subject == "1":
        side = "1" if direction == "OVER" else "2"
        return DOG_RESULT if side == dog else None
    return None


def annotate(leg: Mapping[str, Any], view: EventView | None) -> dict[str, Any] | None:
    """The leg's `rating_market_gap` entry, or None (not football, no view,
    not dependent, or D below THRESHOLD)."""
    if view is None or leg.get("sport", "football") != "football":
        return None
    d = view.d
    if round(d, 9) < THRESHOLD:
        return None
    group = leg_group(leg, view)
    if group not in DEPENDENT:
        return None
    fav = view.favourite
    return {
        "flag": FLAG,
        "d": round(d, 2),
        "group": group,
        "favourite": fav,
        "favourite_name": view.home_name if fav == "home" else view.away_name,
        "market_lambda": {"home": view.market_home, "away": view.market_away},
        "market_margin": round(view.market_margin, 2),
        "market_fit": {"observations": view.observations,
                       "rmse": round(view.rmse, 4)},
        "rating_lambda": {"home": view.rating.home, "away": view.rating.away},
        "rating_margin": round(view.rating_margin, 2),
        "rating_source": view.rating.source,
        "threshold": THRESHOLD,
        "measured_vs_confidence_pp": MEASURED_VS_CONFIDENCE_PP,
        "measured_vs_confidence_ci_pp": list(MEASURED_VS_CONFIDENCE_CI_PP),
        "measured_vs_price_pp": MEASURED_VS_PRICE_PP,
        "measured_vs_price_ci_pp": list(MEASURED_VS_PRICE_CI_PP),
        "measured_on": MEASURED_ON,
    }


def annotate_legs(legs: Iterable[dict[str, Any]],
                  views: Mapping[int, EventView], active: bool) -> int:
    """Set (or clear) `rating_market_gap` on every leg in place; the count
    flagged. Inactive: every entry is removed (a day before the switch)."""
    n = 0
    for leg in legs:
        leg.pop("rating_market_gap", None)
        if not active:
            continue
        eid = leg.get("sofascore_event_id")
        view = views.get(int(eid)) if eid is not None else None
        entry = annotate(leg, view)
        if entry is not None:
            leg["rating_market_gap"] = entry
            n += 1
    return n


def _pl(x: float, fmt: str = "+.2f") -> str:
    return format(x, fmt).replace(".", ",")


def label(leg: Mapping[str, Any]) -> str:
    """The Polish sentence the PDF / HTML show beside the leg."""
    g = leg.get("rating_market_gap")
    if not isinstance(g, Mapping):
        return ""
    name = g.get("favourite_name") or (
        "gospodarze" if g.get("favourite") == "home" else "goście")
    lo, hi = g.get("measured_vs_confidence_ci_pp") or MEASURED_VS_CONFIDENCE_CI_PP
    return (f"rynek widzi faworyta ({name}) o {_pl(float(g['d']), '.1f')} gola "
            f"mocniej niż nasz rating (rynek {_pl(float(g['market_margin']))}, "
            f"rating {_pl(float(g['rating_margin']))}) - takie nogi trafiały ok. "
            f"ceny, poniżej pewności (wydrukowane {WINDOW_PL}: "
            f"{_pl(float(g['measured_vs_confidence_pp']), '+.1f')} pp wobec nóg "
            f"bez rozjazdu [{_pl(float(lo), '+.1f')}; {_pl(float(hi), '+.1f')}])")


# A day with at least this many football matches to annotate and not one view
# built is a parser that no longer reads SHEET's notes (their wording moved) -
# said aloud instead of the entries quietly vanishing.
MIN_MATCHES_FOR_DRIFT = 20


def safe_views(sheet: Iterable[Mapping[str, Any]],
               offers: Iterable[Mapping[str, Any]],
               event_ids: Iterable[int],
               names: Mapping[int, tuple[str | None, str | None]] | None = None,
               ) -> tuple[dict[int, EventView], str | None]:
    """`views_by_event` for a build stage: an annotation never stops the
    build. Returns the views and a WARN line (None when all is well): any
    error leaves the day without entries and says why; no view at all on a
    day of MIN_MATCHES_FOR_DRIFT or more matches names the likely cause."""
    wanted = {int(e) for e in event_ids}
    try:
        views = views_by_event(sheet, offers, wanted, names)
    except Exception as exc:  # noqa: BLE001 - display only, the build goes on
        return {}, (f"WARN rating_market_gap: {type(exc).__name__}: {exc} - "
                    "no leg annotated")
    if not views and len(wanted) >= MIN_MATCHES_FOR_DRIFT:
        return views, (f"WARN rating_market_gap: 0 of {len(wanted)} football "
                       "matches have both views - SHEET's rating notes or the "
                       "offer ladders no longer parse; no leg annotated")
    return views, None
