#!/usr/bin/env python3
"""Read-only measurement: football card points by half, red cards and
penalties by side / half (epochs.FOOTBALL_CARD_HALVES).

Evidence, not a price (a ``measure_*`` script): nothing here writes a config,
a curve, a run artifact or a database row. Questions:

1. How often does the half rule matter - a two-yellow dismissal whose first
   yellow came in the other half, a counted card with no match time, a card
   at 45+N - and do the halves add up to the full-match card points?
2. Card points in a half (Superbet "1. / 2. połowa - [<T>] liczba kartek"):
   which centre forecasts them better, walk forward, out of sample -
     share   the side's full-match rating centre (football_rating, the
             cards_points_for centre SHEET prices) x the competition's as-of
             share of card points shown in that half (shrunk toward the
             gender's share with SHARE_M matches);
     sample  the side's own as-of half sample (last SAMPLE_N matches' half
             points, shrunk toward the competition's per-side half mean with
             SAMPLE_K matches);
     team    the rating centre x the side's own as-of half share (shrunk
             toward the competition's with TEAM_SHARE_M matches);
   each with an NB count whose r is fitted per half on the fit window (and
   Poisson for reference); per side and the convolved match total, count
   log-loss (match bootstrap 95% CI of the difference), calibration of the
   Superbet lines at p >= 0.70, most / handicap 0.5 of the half.
3. Red cards / penalties by side and in the first half, both teams carded red:
   the competition's as-of rate (shrunk toward the gender's, BASE_M) against
   the gender's rate (base), the venue-split competition rate and the team's
   own rate (TEAM_M); calibration at p >= 0.70.

Walk forward: matches in time order; the rating book (cards_points_for) and
every frequency are updated only after a match was priced. Incident lists:
``sofa_event_stats.incidents_json`` (``mode=ro``) through
``metrics.calculate_cards_points_by_half`` and
``football_incidents.read_incidents``; the zero-card test of
calculate_cards_points reads the history's own cards_points_for (0, 0) as
"yellowCards 0" - the parsed history kept only matches whose card value was
admitted.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_football_card_halves.py \\
        --db data/sofa.db --history data/cache/football_history.pkl \\
        --cache <scratch>/card_halves_records.pkl \\
        [--fit-from 2025-08-01] [--test-from 2026-03-01] [--test-to 2026-10-14] \\
        [--json-out f]

Exit 0 OK, 2 on a failure.
"""

from __future__ import annotations

import argparse
import json
import math
import pickle
import sqlite3
import sys
from collections import defaultdict, deque
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import football_rating as fr  # noqa: E402
from bet.sofa.contracts import GapReason  # noqa: E402
from bet.sofa.football_card_halves import (  # noqa: E402
    half_count_pmf,
    nb_pmf,
)
from bet.sofa.football_incidents import read_incidents  # noqa: E402
from bet.sofa.metrics import (  # noqa: E402
    _incident_player_key,
    _is_staff_card,
    calculate_cards_points,
    calculate_cards_points_by_half,
    card_half,
)
from scripts.sofa.measure_dependence_goals import load_pickle, note, ts_of  # noqa: E402
from scripts.sofa.measure_football_incidents import boot_ci, calib  # noqa: E402

F64 = NDArray[np.float64]

SHARE_M = 30.0
SAMPLE_N = 10
SAMPLE_K = 5.0
TEAM_SHARE_M = 10.0
BASE_M = 30.0
TEAM_M = 20.0
MIN_TEAM = 5
R_GRID = (0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0, 12.0, 20.0, 50.0, 1e6)
LINES_TOTAL = {1: (0.5, 1.5, 2.5, 3.5), 2: (0.5, 1.5, 2.5, 3.5, 4.5)}
LINES_SIDE = (0.5, 1.5)
MODELS = ("share", "sample", "team")


@dataclass(frozen=True)
class CardRec:
    halves: tuple[tuple[float, float], tuple[float, float]] | None
    reason: str | None
    yr: int  # yellowRed incidents counted
    yr_cross: int  # ... whose player's yellow was in the other half
    yr_alone: int  # ... with no yellow of that player in the list
    no_time: int  # counted player cards with no match time
    at_45_added: int  # cards at 45+N
    cards: int
    sum_ok: bool | None  # halves add up to the full-match points
    reds: tuple[int, int] | None
    reds_1h: tuple[int, int] | None
    pens: tuple[int, int] | None
    pens_1h: tuple[int, int] | None


def card_record(
    inc: dict[str, Any],
    cards_pair: tuple[float, float] | None,
    goals: tuple[float, float] | None,
) -> CardRec:
    stats = (
        None if cards_pair is None
        else {"yellowCards": (0.0, 0.0) if sum(cards_pair) == 0 else (1.0, 0.0)}
    )
    halves = calculate_cards_points_by_half(inc, stats) if cards_pair else None
    reason = halves.value if isinstance(halves, GapReason) else None
    if isinstance(halves, GapReason):
        halves = None
    cards = [
        i for i in inc.get("incidents", [])
        if i.get("incidentType") == "card" and not i.get("rescinded", False)
        and not _is_staff_card(i)
    ]
    yhalf: dict[str, set[int | None]] = defaultdict(set)
    for i in cards:
        if i.get("incidentClass") == "yellow":
            k = _incident_player_key(i)
            if k:
                yhalf[k].add(card_half(i))
    yr = yr_cross = yr_alone = 0
    for i in cards:
        if i.get("incidentClass") != "yellowRed":
            continue
        yr += 1
        k = _incident_player_key(i)
        seen = yhalf.get(k or "", set())
        if not seen:
            yr_alone += 1
        elif card_half(i) not in seen:
            yr_cross += 1
    no_time = sum(1 for i in cards if card_half(i) is None)
    at45 = sum(
        1 for i in cards
        if i.get("time") == 45 and isinstance(i.get("addedTime"), int | float)
        and 0 < float(i["addedTime"]) < 900
    )
    sum_ok = None
    if halves is not None:
        whole = calculate_cards_points(inc, stats)
        if not isinstance(whole, GapReason):
            sum_ok = abs(sum(halves[0]) + sum(halves[1]) - sum(whole)) < 1e-9
    rec = read_incidents(inc, goals) if goals is not None else None
    full = rec is not None and rec.full_feed
    return CardRec(
        halves, reason, yr, yr_cross, yr_alone, no_time, at45, len(cards), sum_ok,
        rec.red_cards if full and rec else None,
        rec.red_cards_1h if full and rec else None,
        rec.penalties if full and rec else None,
        rec.penalties_1h if full and rec else None,
    )


def load_records(db: str, history: Sequence[fr.FootballResult]) -> dict[int, CardRec]:
    wanted = {
        r.event_id: (r.values.get("cards_points_for"), r.values.get("goals_for"))
        for r in history
    }
    out: dict[int, CardRec] = {}
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
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
            if not isinstance(inc, dict) or not inc.get("incidents"):
                continue
            out[eid] = card_record(inc, meta[0], meta[1])
    finally:
        conn.close()
    note(f"incident records {len(out)}")
    return out


# ------------------------------------------------------------------ the walk


class _Share:
    """Running card points of a half against the whole, in matches."""

    def __init__(self) -> None:
        self.n = 0
        self.half = [0.0, 0.0]
        self.whole = 0.0

    def add(self, h1: float, h2: float) -> None:
        self.n += 1
        self.half[0] += h1
        self.half[1] += h2
        self.whole += h1 + h2

    def share(self, half: int) -> float | None:
        return self.half[half - 1] / self.whole if self.whole > 0 else None


def _shrunk_share(local: _Share | None, glob: _Share, half: int, m: float) -> float:
    g = glob.share(half)
    g = 0.4 if g is None else g
    if local is None or local.n == 0 or local.share(half) is None:
        return g
    s = local.share(half)
    assert s is not None
    return (local.n * s + m * g) / (local.n + m)


def walk_cards(
    history: Sequence[fr.FootballResult],
    recs: dict[int, CardRec],
    fit_from: int,
    test_to: int,
) -> list[dict[str, Any]]:
    book = fr.RatingBook()
    comp_share: dict[int, _Share] = {}
    glob_share: dict[bool, _Share] = defaultdict(_Share)
    team_share: dict[int, _Share] = {}
    team_hist: dict[int, deque[tuple[float, float]]] = defaultdict(
        lambda: deque(maxlen=SAMPLE_N))
    comp_side_half: dict[int, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
    rows: list[dict[str, Any]] = []
    for res in history:
        if res.ts >= test_to:
            break
        cards = res.values.get("cards_points_for")
        if cards is None:
            continue
        rec = recs.get(res.event_id)
        halves = rec.halves if rec is not None else None
        if halves is not None and res.ts >= fit_from:
            fc = fr.FootballForecast(
                book, res.competition_id, res.home_id, res.away_id,
                rated_scope=fr.RATED_SCOPE_MARKETS)
            ca = fc.centre("cards_points_for", "side_a")
            cb = fc.centre("cards_points_for", "side_b")
            th, ta = team_hist[res.home_id], team_hist[res.away_id]
            if (ca is not None and cb is not None
                    and len(th) >= MIN_TEAM and len(ta) >= MIN_TEAM):
                row: dict[str, Any] = {
                    "ts": res.ts, "eid": res.event_id, "women": res.women,
                    "halves": halves, "c": (ca[0], cb[0]),
                }
                csh = comp_share.get(res.competition_id)
                gsh = glob_share[res.women]
                cs = comp_side_half[res.competition_id]
                for half in (1, 2):
                    s = _shrunk_share(csh, gsh, half, SHARE_M)
                    row[f"share_{half}"] = (ca[0] * s, cb[0] * s)
                    lg = cs[half - 1] / cs[2] if cs[2] > 0 else None
                    if lg is None:
                        g = gsh.share(half) or 0.4
                        lg = g * (ca[0] + cb[0]) / 2
                    lam = []
                    tsh = []
                    for team, c in ((res.home_id, ca[0]), (res.away_id, cb[0])):
                        past = team_hist[team]
                        tot = sum(p[half - 1] for p in past)
                        lam.append((tot + SAMPLE_K * lg) / (len(past) + SAMPLE_K))
                        tsh.append(c * _shrunk_share(
                            team_share.get(team), _ShareProxy(s),
                            half, TEAM_SHARE_M))
                    row[f"sample_{half}"] = tuple(lam)
                    row[f"team_{half}"] = tuple(tsh)
                rows.append(row)
        # ---- update after pricing
        book.update(replace(res, values={"cards_points_for": cards}))
        if halves is None:
            continue
        (h1h, h1a), (h2h, h2a) = halves
        comp_share.setdefault(res.competition_id, _Share()).add(h1h + h1a, h2h + h2a)
        glob_share[res.women].add(h1h + h1a, h2h + h2a)
        cs = comp_side_half[res.competition_id]
        cs[0] += h1h + h1a
        cs[1] += h2h + h2a
        cs[2] += 2
        for team, a, b in ((res.home_id, h1h, h2h), (res.away_id, h1a, h2a)):
            team_share.setdefault(team, _Share()).add(a, b)
            team_hist[team].append((a, b))
    return rows


class _ShareProxy(_Share):
    """A fixed share standing in for the 'global' of a team's shrink."""

    def __init__(self, s: float) -> None:
        super().__init__()
        self._s = s

    def share(self, half: int) -> float | None:
        return self._s


# ------------------------------------------------------------------ scoring


def _side_ll(lams: F64, ys: F64, r: float) -> F64:
    out = np.empty(len(lams))
    for i, (lam, y) in enumerate(zip(lams, ys, strict=True)):
        pmf = nb_pmf(float(lam), r, int(y) + 1)
        out[i] = -math.log(max(pmf[int(y)], 1e-12))
    return out


def fit_r(rows: Sequence[dict[str, Any]], model: str, half: int) -> float:
    lams = np.array([v for r in rows for v in r[f"{model}_{half}"]])
    ys = np.array([v for r in rows for v in r["halves"][half - 1]])
    if len(lams) > 20000:
        idx = np.random.default_rng(20261021).choice(len(lams), 20000, replace=False)
        lams, ys = lams[idx], ys[idx]
    best = min(R_GRID, key=lambda rr: float(_side_ll(lams, ys, rr).mean()))
    return float(best)


def _p_over(pmf: Sequence[float], line: float) -> float:
    k = math.floor(line) + 1
    return float(max(0.0, 1.0 - sum(pmf[:k])))


def score_cards(
    rows: Sequence[dict[str, Any]], rs: dict[tuple[str, int], float], reps: int
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for half in (1, 2):
        per_model: dict[str, dict[str, Any]] = {}
        side_ll: dict[str, F64] = {}
        tot_ll: dict[str, F64] = {}
        for model in MODELS + ("share_poisson",):
            base_model = "share" if model == "share_poisson" else model
            r = 1e6 if model == "share_poisson" else rs[(base_model, half)]
            sl: list[float] = []
            tl: list[float] = []
            sel_p: dict[str, list[float]] = defaultdict(list)
            sel_y: dict[str, list[float]] = defaultdict(list)
            for row in rows:
                la, lb = row[f"{base_model}_{half}"]
                ya, yb = row["halves"][half - 1]
                pa = half_count_pmf(la, r)
                pb = half_count_pmf(lb, r)
                ia, ib = int(ya), int(yb)
                ma = (pa[ia] if ia < len(pa) else 1e-12)
                mb = (pb[ib] if ib < len(pb) else 1e-12)
                sl.append(-math.log(max(ma, 1e-12)) - math.log(max(mb, 1e-12)))
                tot = np.convolve(pa, pb)
                it = ia + ib
                tl.append(-math.log(max(tot[it] if it < len(tot) else 1e-12, 1e-12)))
                for line in LINES_TOTAL[half]:
                    p = _p_over(list(tot), line)
                    y = float(ya + yb > line)
                    sel_p[f"total_{line:g}_OVER"].append(p)
                    sel_y[f"total_{line:g}_OVER"].append(y)
                    sel_p[f"total_{line:g}_UNDER"].append(1 - p)
                    sel_y[f"total_{line:g}_UNDER"].append(1 - y)
                for line in LINES_SIDE:
                    for pm, yy in ((pa, ya), (pb, yb)):
                        p = _p_over(list(pm), line)
                        y = float(yy > line)
                        sel_p[f"side_{line:g}_OVER"].append(p)
                        sel_y[f"side_{line:g}_OVER"].append(y)
                        sel_p[f"side_{line:g}_UNDER"].append(1 - p)
                        sel_y[f"side_{line:g}_UNDER"].append(1 - y)
                # most / handicap 0.5 of the half (independent sides)
                joint = np.outer(pa, pb)
                diff = np.subtract.outer(np.arange(len(pa)), np.arange(len(pb)))
                ph = float(joint[diff > 0].sum())
                pdraw = float(joint[diff == 0].sum())
                pw = 1.0 - ph - pdraw
                for key, p, y in (
                    ("most_1", ph, float(ya > yb)), ("most_X", pdraw, float(ya == yb)),
                    ("most_2", pw, float(yb > ya)),
                    ("hcp_home_-0.5", ph, float(ya > yb)),
                    ("hcp_home_+0.5", ph + pdraw, float(ya >= yb)),
                    ("hcp_away_-0.5", pw, float(yb > ya)),
                    ("hcp_away_+0.5", pw + pdraw, float(yb >= ya)),
                ):
                    sel_p[key].append(p)
                    sel_y[key].append(y)
            side_ll[model] = np.array(sl)
            tot_ll[model] = np.array(tl)
            per_model[model] = {
                "r": r,
                "side_ll": float(np.mean(sl)),
                "total_ll": float(np.mean(tl)),
                "selections": {
                    k: _cal070(np.array(sel_p[k]), np.array(sel_y[k]))
                    for k in sorted(sel_p)
                },
                "pooled_lines": calib(
                    np.concatenate([np.array(sel_p[k]) for k in sel_p
                                    if k.startswith(("total_", "side_"))]),
                    np.concatenate([np.array(sel_y[k]) for k in sel_y
                                    if k.startswith(("total_", "side_"))])),
            }
        diffs = {}
        for model in ("sample", "team", "share_poisson"):
            diffs[f"{model}_minus_share"] = {
                "side_ll": float((side_ll[model] - side_ll["share"]).mean()),
                "side_ci": boot_ci(side_ll[model] - side_ll["share"], reps),
                "total_ll": float((tot_ll[model] - tot_ll["share"]).mean()),
                "total_ci": boot_ci(tot_ll[model] - tot_ll["share"], reps),
            }
        realised = np.array([sum(r["halves"][half - 1]) for r in rows])
        out[f"half{half}"] = {
            "n_matches": len(rows),
            "mean_total": float(realised.mean()) if len(rows) else math.nan,
            "models": per_model,
            "diffs": diffs,
        }
    return out


def _cal070(p: F64, y: F64) -> dict[str, Any]:
    m = p >= 0.70
    n = int(m.sum())
    out: dict[str, Any] = {"n": len(p), "n_ge_070": n}
    if n:
        out["p_ge_070"] = float(p[m].mean())
        out["realised_ge_070"] = float(y[m].mean())
        out["gap_pp"] = 100.0 * (out["realised_ge_070"] - out["p_ge_070"])
    return out


# ------------------------------------------------------------------ reds / pens

EVENT_SCOPES = (
    # name, kind, scope (match / 1h), side?, line
    ("red_cards_for_0.5", "reds", "match", True, 0.5),
    ("red_cards_for_1.5", "reds", "match", True, 1.5),
    ("red_cards_1h_total_0.5", "reds", "1h", False, 0.5),
    ("red_cards_1h_for_0.5", "reds", "1h", True, 0.5),
    ("penalties_for_0.5", "pens", "match", True, 0.5),
    ("penalties_1h_total_0.5", "pens", "1h", False, 0.5),
    ("penalties_1h_for_0.5", "pens", "1h", True, 0.5),
    ("both_red_cards", "both", "match", False, 0.5),
)


@dataclass
class _Rate:
    n: float = 0.0
    k: float = 0.0


def _pair(rec: CardRec, kind: str, scope: str) -> tuple[int, int] | None:
    if kind in ("reds", "both"):
        return rec.reds if scope == "match" else rec.reds_1h
    return rec.pens if scope == "match" else rec.pens_1h


def walk_events(
    history: Sequence[fr.FootballResult],
    recs: dict[int, CardRec],
    test_from: int,
    test_to: int,
) -> dict[str, list[dict[str, float]]]:
    comp: dict[tuple[str, int, str], _Rate] = defaultdict(_Rate)  # venue "" pooled
    glob: dict[tuple[str, bool, str], _Rate] = defaultdict(_Rate)
    team: dict[tuple[str, int], _Rate] = defaultdict(_Rate)
    rows: dict[str, list[dict[str, float]]] = defaultdict(list)

    def shr(loc: _Rate, g: float, m: float) -> float:
        return (loc.k + m * g) / (loc.n + m)

    for res in history:
        if res.ts >= test_to:
            break
        rec = recs.get(res.event_id)
        if rec is None or rec.reds is None:
            continue
        for name, kind, scope, sided, line in EVENT_SCOPES:
            pair = _pair(rec, kind, scope)
            if pair is None:
                continue
            if kind == "both":
                outcomes = [("", float(pair[0] >= 1 and pair[1] >= 1), 0)]
            elif sided:
                outcomes = [("h", float(pair[0] > line), res.home_id),
                            ("a", float(pair[1] > line), res.away_id)]
            else:
                outcomes = [("", float(pair[0] + pair[1] > line), 0)]
            if res.ts >= test_from:
                for venue, y, tid in outcomes:
                    gp = glob[(name, res.women, "")]
                    g = (gp.k + 0.5) / (gp.n + 1.0)
                    if gp.n < 200:
                        continue
                    lg = shr(comp[(name, res.competition_id, "")], g, BASE_M)
                    row = {"y": y, "base": g, "league": lg, "eid": float(res.event_id)}
                    if venue:
                        gv = glob[(name, res.women, venue)]
                        gvr = (gv.k + 0.5) / (gv.n + 1.0)
                        row["venue"] = shr(comp[(name, res.competition_id, venue)],
                                           gvr, BASE_M)
                        row["team"] = shr(team[(name, tid)], lg, TEAM_M)
                    if kind == "both":
                        a = shr(comp[("red_cards_for_0.5", res.competition_id, "")],
                                (glob[("red_cards_for_0.5", res.women, "")].k + 0.5)
                                / (glob[("red_cards_for_0.5", res.women, "")].n + 1.0),
                                BASE_M)
                        row["product"] = a * a
                    rows[name].append(row)
            for venue, y, tid in outcomes:
                for key in ((name, res.competition_id, ""),
                            (name, res.competition_id, venue)):
                    comp[key].n += 1
                    comp[key].k += y
                for gkey in ((name, res.women, ""), (name, res.women, venue)):
                    glob[gkey].n += 1
                    glob[gkey].k += y
                if venue:
                    team[(name, tid)].n += 1
                    team[(name, tid)].k += y
    return rows


def score_events(rows: dict[str, list[dict[str, float]]], reps: int) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, part in rows.items():
        if not part:
            continue
        y = np.array([r["y"] for r in part])
        res: dict[str, Any] = {"n": len(part), "realised_over": float(y.mean())}

        def ll(p: F64) -> F64:
            p = np.clip(p, 1e-9, 1 - 1e-9)
            out_: F64 = -(y * np.log(p) + (1 - y) * np.log(1 - p))
            return out_

        base = ll(np.array([r["base"] for r in part]))
        for model in ("league", "venue", "team", "product"):
            if model not in part[0]:
                continue
            p = np.array([r[model] for r in part])
            lm = ll(p)
            res[model] = {
                "ll": float(lm.mean()),
                "d_vs_base": float((lm - base).mean()),
                "ci": boot_ci(lm - base, reps),
                "under_ge_070": _cal070(1 - p, 1 - y),
                "over_ge_070": _cal070(p, y),
            }
        out[name] = res
    return out


# ------------------------------------------------------------------ main


def diagnostics(recs: dict[int, CardRec]) -> dict[str, Any]:
    halves = [r for r in recs.values() if r.halves is not None]
    yr_matches = [r for r in halves if r.yr]
    return {
        "records": len(recs),
        "with_halves": len(halves),
        "reasons": dict(sorted(
            ((k, sum(1 for r in recs.values() if r.reason == k))
             for k in {r.reason for r in recs.values() if r.reason}),
            key=lambda kv: -kv[1])),
        "sum_ok": sum(1 for r in halves if r.sum_ok),
        "sum_bad": sum(1 for r in halves if r.sum_ok is False),
        "matches_with_yellowred": len(yr_matches),
        "matches_with_cross_half_yellowred": sum(1 for r in halves if r.yr_cross),
        "matches_with_lone_yellowred": sum(1 for r in halves if r.yr_alone),
        "cross_share_of_matches": (
            sum(1 for r in halves if r.yr_cross) / len(halves) if halves else math.nan),
        "matches_with_card_at_45_added": sum(1 for r in halves if r.at_45_added),
        "cards_in_matches_with_halves": sum(r.cards for r in halves),
        "cards_at_45_added": sum(r.at_45_added for r in halves),
        "matches_refused_no_time": sum(
            1 for r in recs.values() if r.reason == GapReason.CARD_HALF_UNKNOWN.value),
        "full_feed_event_records": sum(1 for r in recs.values() if r.reds is not None),
    }


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", required=True)
    ap.add_argument("--history", default="data/cache/football_history.pkl")
    ap.add_argument("--cache", default=None,
                    help="pickle of the parsed incident records (read / written)")
    ap.add_argument("--fit-from", default="2025-08-01")
    ap.add_argument("--test-from", default="2026-03-01")
    ap.add_argument("--test-to", default="2026-10-14")
    ap.add_argument("--boot", type=int, default=500)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)
    try:
        history = load_pickle(Path(args.history))
        note(f"history {len(history)} matches")
        recs: dict[int, CardRec] | None = None
        if args.cache and Path(args.cache).exists():
            recs = pickle.loads(Path(args.cache).read_bytes())
        if recs is None:
            recs = load_records(args.db, history)
            if args.cache:
                Path(args.cache).write_bytes(pickle.dumps(recs))
        fit_from, t_from, t_to = (ts_of(args.fit_from), ts_of(args.test_from),
                                  ts_of(args.test_to))
        out: dict[str, Any] = {
            "args": vars(args),
            "constants": {"SHARE_M": SHARE_M, "SAMPLE_N": SAMPLE_N,
                          "SAMPLE_K": SAMPLE_K,
                          "TEAM_SHARE_M": TEAM_SHARE_M, "BASE_M": BASE_M,
                          "TEAM_M": TEAM_M},
            "unfitted_constants": ["SHARE_M", "SAMPLE_K", "TEAM_SHARE_M", "BASE_M",
                                   "TEAM_M"],
            "diagnostics": diagnostics(recs),
        }
        note("cards walk")
        rows = walk_cards(history, recs, fit_from, t_to)
        fit_rows = [r for r in rows if r["ts"] < t_from]
        test_rows = [r for r in rows if r["ts"] >= t_from]
        note(f"card rows fit {len(fit_rows)} test {len(test_rows)}")
        rs = {(m, h): fit_r(fit_rows, m, h) for m in MODELS for h in (1, 2)}
        out["nb_r"] = {f"{m}_{h}": v for (m, h), v in rs.items()}
        out["cards"] = score_cards(test_rows, rs, args.boot)
        men = [r for r in test_rows if not r["women"]]
        out["cards_men"] = score_cards(men, rs, 200)
        note("events walk")
        ev = walk_events(history, recs, fit_from, t_to)
        out["events"] = score_events(ev, args.boot)
        text = json.dumps(out, indent=1, default=str)
        if args.json_out:
            Path(args.json_out).write_text(text)
        print(text)
    except Exception as exc:  # pragma: no cover - a measurement crash
        print(f"FAILED: {exc!r}", file=sys.stderr)
        raise
    return 0


if __name__ == "__main__":
    sys.exit(main())
