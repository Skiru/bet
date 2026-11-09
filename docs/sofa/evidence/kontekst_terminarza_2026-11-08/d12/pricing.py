"""D12: price a path (ii) row from its noted pure centres, base or corrected."""
from __future__ import annotations
import json, math, pickle, re, sys
from functools import lru_cache
from pathlib import Path
REPO = Path("/Users/mkoziol/projects/bet")
sys.path[:0] = [str(REPO / "src"), str(REPO)]
from bet.sofa import football_sim_sheet as fss  # noqa: E402
from bet.sofa.epochs import FOOTBALL_SIM_MARKETS  # noqa: E402
from bet.sofa.football_1x2_dnb import probabilities as p1x2  # noqa: E402
from bet.sofa.football_1x2_dnb import row_p as p1x2_row  # noqa: E402
from bet.sofa.football_incidents import first_goal_probs  # noqa: E402
from bet.sofa.football_result import result_probs  # noqa: E402
from bet.sofa.football_score_markets import row_p as score_row_p  # noqa: E402
from bet.sofa.football_score_markets import score_grid  # noqa: E402
from bet.sofa.football_sim import Centres  # noqa: E402

D12 = REPO / "data/refit_2026-11-08_schedule/d12"
FROZEN = json.loads((REPO / "docs/sofa/evidence/kontekst_terminarza_2026-11-08/frozen/fr_frozen.json").read_text())
COEF = FROZEN["coef"]
COLS = ("R1", "R2", "R4_intl", "R4_other", "R5_season_start", "R5_winter", "R5_other",
        "cont_prev4", "cont_prev4_x_R1", "et_prev", "dense14", "cont_next4")
FLOOR_SIM = {"team_scores_both_halves", "half_goals_combo", "btts_any_half", "btts_halves"}
DC = {"double_chance"}
R1X2 = {"result_1x2", "draw_no_bet"}
SCORE = {"btts_or_over", "dc_and_over", "dc_and_under", "result_handicap", "result_or_btts",
         "result_or_clean_sheet", "result_or_over", "result_or_under"}
FG = {"first_goal"}
NONSIM = DC | R1X2 | SCORE | FG
SIM = set(FOOTBALL_SIM_MARKETS)
SIM_SCOPE = SIM - FLOOR_SIM
SCOPE = NONSIM | SIM_SCOPE

RE_PURE = re.compile(r"pure rating centres home ([\d.]+) / away ([\d.]+)")
RE_R = re.compile(r"NB goals \(r ([\d.]+)\)")
RE_SIM = re.compile(r"pure rating goals centres home ([\d.]+) / away ([\d.]+), card points (default|([\d.]+) / ([\d.]+))")
RE_SIMS = re.compile(r"from (\d+) simulated matches")

_feats = pickle.loads((D12 / "features_d12.pkl").read_bytes())["features"]


def side_t(eid: int, side: str) -> float | None:
    f = _feats.get(eid)
    if f is None:
        return None
    if f["national"]:
        return 0.0
    own, opp = (f["home"], f["away"]) if side == "home" else (f["away"], f["home"])
    if not (own.coverage and opp.coverage):
        return 0.0
    io, ip = own.indicators(), opp.indicators()
    return (sum(COEF.get(f"own_{c}", 0.0) * io[c] for c in COLS)
            + sum(COEF.get(f"opp_{c}", 0.0) * ip[c] for c in COLS))


def terms(eid: int) -> tuple[float, float, str]:
    th, ta = side_t(eid, "home"), side_t(eid, "away")
    if th is None or ta is None:
        return 0.0, 0.0, "no_calendar"
    f = _feats[eid]
    if f["national"]:
        return 0.0, 0.0, "national"
    if not (f["home"].coverage and f["away"].coverage):
        return 0.0, 0.0, "no_coverage"
    return th, ta, "ok"


@lru_cache(maxsize=None)
def _params():
    return fss.load_params()

_pricer = None


def pricer():
    global _pricer
    if _pricer is None:
        _pricer = fss.SimPricer(_params())
    return _pricer


def note_of(row) -> str:
    return " | ".join(str(n) for n in row.get("notes") or [])


def centres(row):
    """(lh, la, r_or_None, cards_or_None, kind) from the row's note."""
    n = note_of(row)
    if row["market"] in SIM:
        m = RE_SIM.search(n)
        if not m:
            return None
        cards = None if m.group(3) == "default" else (float(m.group(4)), float(m.group(5)))
        return float(m.group(1)), float(m.group(2)), None, cards, "sim"
    m = RE_PURE.search(n)
    r = RE_R.search(n)
    if not m or not r:
        return None
    return float(m.group(1)), float(m.group(2)), float(r.group(1)), None, "nb"


def price(row, lh: float, la: float, r: float | None, cards) -> float | None:
    mk, sub, line, dr = row["market"], row.get("subject") or "", float(row["line"]), row["direction"]
    if mk in DC:
        return result_probs(lh, la, r)[sub]
    if mk in R1X2:
        return p1x2_row(mk, sub, dr, p1x2(lh, la, r))
    if mk in SCORE:
        return score_row_p(mk, sub, line, score_grid(lh, la, r))
    if mk in FG:
        return first_goal_probs(lh, la, r, exact=False)[sub]
    if mk in SIM:
        c = Centres(goals=(lh, la), halves={}, cards=cards)
        return pricer().p(int(row["sofascore_event_id"]), c, mk, sub, dr)
    return None
