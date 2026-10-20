"""Measure two refinements of the football card-halves package
(epochs.FOOTBALL_CARD_HALVES), walk forward, out of sample. Read-only.

(1) Side events (penalties_for, red_cards_for and their first half; the
    first-half totals): today p = the competition's as-of shrunk rate of the
    selection (football_card_halves.CardHalfRates.p_over). Candidates scale
    the league's intensity lambda_L = -ln(1 - p_L) per side by
    exp(beta . x), x from what the sheet knows before the match:
      - goals: log(the side's rating goals_for centre / the competition's
        as-of goals per side);
      - sup:   the side's expected goal difference (clamped, game_state);
      - own:   log of the side's own shrunk event rate over the league's;
      - fouls: log of the side's own shrunk fouls_for over the league's;
      - ref:   log of the referee's as-of cards ratio (referees.RefereeBook,
        K 10).
    beta: Poisson pseudo-likelihood on the event counts of the fit window,
    log link, offset log lambda_L; scored on the test window by log-loss
    (match-clustered bootstrap) and calibration of UNDER / OVER >= 0.70. A
    total's lambda is lambda_L x the mean of its sides' multipliers.

(2) Card halves: today a side's half centre = its raw rating cards centre x
    the competition's half share. Candidate: the full-match LIVE centre
    (fit_count_stretch.walk's SHEET centre x GAME_STATE x the referee term x
    the closeness stretch, the installed tables) x the same share - and the
    same with the three terms' coefficients refitted on the fit window only
    (out of sample: the installed ones were fitted on windows overlapping
    the test). NB r per half fitted on the fit window per model.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_football_side_terms.py \\
        --db data/sofa.db --history data/cache/football_history.pkl \\
        --records <scratch>/card_halves_records.pkl \\
        [--features <scratch>/side_terms.pkl] [--json-out f]

--records: measure_football_card_halves.py's --cache pickle (per-match half
card points, reds, penalties). --features caches the walk (read / written).
Exit 0 OK, 2 on a failure.
"""

from __future__ import annotations

import argparse
import json
import math
import pickle
import sys
from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import football_rating as fr  # noqa: E402
from bet.sofa import referees  # noqa: E402
from bet.sofa.closeness_stretch import load_table as load_closeness  # noqa: E402
from bet.sofa.cup_strength import apply as apply_cup_strength  # noqa: E402
from bet.sofa.cup_strength import load as load_cup_strength  # noqa: E402
from bet.sofa.football_card_halves import half_count_pmf  # noqa: E402
from bet.sofa.game_state import clamp_supremacy  # noqa: E402
from bet.sofa.game_state import load_table as load_game_state  # noqa: E402
from scripts.sofa.fit_count_stretch import walk  # noqa: E402
from scripts.sofa.measure_dependence_goals import load_pickle, note, ts_of  # noqa: E402
from scripts.sofa.measure_football_card_halves import (  # noqa: E402
    R_GRID,
    CardRec,
    _Share,
    _shrunk_share,
)
from scripts.sofa.measure_game_state import k_table, rules_as_of  # noqa: E402

F64 = NDArray[np.float64]

SHARE_M = 30.0   # as football_card_halves.SHARE_M
BASE_M = 30.0    # as football_card_halves.BASE_M
TEAM_M = 20.0    # chosen: a side's own rate shrunk to the league's
GOALS_M = 30.0   # chosen: the competition's goals per side shrunk to the gender's
REF_K = 10.0     # referees: the installed K of cards_points
LIVE_RULES_DAY = "2026-10-20"
CARD = "cards_points_for"
FEATS = ("goals", "goals_lr", "sup", "own", "fouls", "ref")
# name, kind, scope, sided
EVENTS = (
    ("penalties_for", "pens", "match", True),
    ("penalties_1h_for", "pens", "1h", True),
    ("penalties_1h_total", "pens", "1h", False),
    ("red_cards_for", "reds", "match", True),
    ("red_cards_1h_for", "reds", "1h", True),
    ("red_cards_1h_total", "reds", "1h", False),
)
FEATURE_SETS: Mapping[str, Mapping[str, tuple[str, ...]]] = {
    "pens": {"goals": ("goals",), "goals_lr": ("goals_lr",), "own": ("own",),
             "goals+own": ("goals", "own"), "goals_lr+own": ("goals_lr", "own"),
             "sup": ("sup",)},
    "reds": {"sup": ("sup",), "own": ("own",), "fouls": ("fouls",),
             "ref": ("ref",), "sup+own": ("sup", "own"),
             "sup+own+fouls+ref": ("sup", "own", "fouls", "ref")},
}


@dataclass
class _Mean:
    n: float = 0.0
    s: float = 0.0

    def add(self, v: float, w: float = 1.0) -> None:
        self.n += w
        self.s += v

    def shrunk(self, prior: float, m: float) -> float:
        return (self.s + m * prior) / (self.n + m)

    def mean(self) -> float | None:
        return self.s / self.n if self.n > 0 else None


def _pair(rec: CardRec, kind: str, scope: str) -> tuple[int, int] | None:
    if kind == "reds":
        return rec.reds if scope == "match" else rec.reds_1h
    return rec.pens if scope == "match" else rec.pens_1h


def _ratio(own: _Mean, league: float, m: float) -> float:
    if league <= 0:
        return 1.0
    return own.shrunk(league, m) / league


# ------------------------------------------------------------------ the walk


def collect(history: Sequence[fr.FootballResult], recs: Mapping[int, CardRec],
            labels: Mapping[int, int], start: int, end: int,
            ) -> dict[str, Any]:
    """Cards rows (per match) and event rows (per match), every feature read
    before the match; a kick-off second is read whole before it is added."""
    note("live centre walk (fit_count_stretch.walk, live rules)")
    rules = rules_as_of(LIVE_RULES_DAY,
                        datetime.fromisoformat("2026-10-21T00:00:00+00:00"))
    cup = load_cup_strength(None)
    live: dict[tuple[int, str], tuple[float, float]] = {}
    for row in walk(history, start, end, (CARD,), k_table((CARD,)), rules,
                    cup_strength=cup):
        live[(row.event_id, row.side)] = (row.centre, row.supremacy)
    note(f"live centres {len(live)}")

    book = apply_cup_strength(fr.RatingBook(shared_league_link=True), cup)
    rbook = referees.RefereeBook(referees.FAMILY_METRIC)
    comp_share: dict[int, _Share] = {}
    glob_share: dict[bool, _Share] = defaultdict(_Share)
    comp_goals: dict[int, _Mean] = defaultdict(_Mean)
    glob_goals: dict[bool, _Mean] = defaultdict(_Mean)
    comp_fouls: dict[int, _Mean] = defaultdict(_Mean)
    glob_fouls: dict[bool, _Mean] = defaultdict(_Mean)
    team_fouls: dict[int, _Mean] = defaultdict(_Mean)
    # event key "kind:scope" -> per side counts
    comp_ev: dict[tuple[str, int], _Mean] = defaultdict(_Mean)
    glob_ev: dict[tuple[str, bool], _Mean] = defaultdict(_Mean)
    team_ev: dict[tuple[str, int], _Mean] = defaultdict(_Mean)
    # selection rates (count > 0.5), as CardHalfRates.p_over
    comp_sel: dict[tuple[str, int], _Mean] = defaultdict(_Mean)
    glob_sel: dict[tuple[str, bool], _Mean] = defaultdict(_Mean)
    cards_rows: list[dict[str, Any]] = []
    event_rows: list[dict[str, Any]] = []
    pending: list[fr.FootballResult] = []
    ts_now = -1
    keep = ("goals_for", CARD, "fouls_for")

    def add(res: fr.FootballResult) -> None:
        book.update(replace(res, values={k: res.values[k] for k in keep
                                         if k in res.values}))
        vals = {fam: float(sum(res.values[m]))
                for fam, m in referees.FAMILY_METRIC.items() if m in res.values}
        rbook.update(labels.get(res.event_id), res.competition_id, vals)
        g = res.values.get("goals_for")
        if g is not None:
            for v in g:
                comp_goals[res.competition_id].add(float(v))
                glob_goals[res.women].add(float(v))
        f = res.values.get("fouls_for")
        if f is not None:
            for team, v in zip((res.home_id, res.away_id), f, strict=True):
                comp_fouls[res.competition_id].add(float(v))
                glob_fouls[res.women].add(float(v))
                team_fouls[team].add(float(v))
        rec = recs.get(res.event_id)
        if rec is None:
            return
        if rec.halves is not None:
            (h1h, h1a), (h2h, h2a) = rec.halves
            comp_share.setdefault(res.competition_id, _Share()).add(
                h1h + h1a, h2h + h2a)
            glob_share[res.women].add(h1h + h1a, h2h + h2a)
        for kind in ("pens", "reds"):
            for scope in ("match", "1h"):
                pair = _pair(rec, kind, scope)
                if pair is None:
                    continue
                key = f"{kind}:{scope}"
                for team, v in zip((res.home_id, res.away_id), pair, strict=True):
                    comp_ev[(key, res.competition_id)].add(float(v))
                    glob_ev[(key, res.women)].add(float(v))
                    team_ev[(key, team)].add(float(v))
                    comp_sel[(key, res.competition_id)].add(float(v > 0.5))
                    glob_sel[(key, res.women)].add(float(v > 0.5))
                tot = pair[0] + pair[1]
                comp_sel[(key + ":tot", res.competition_id)].add(float(tot > 0.5))
                glob_sel[(key + ":tot", res.women)].add(float(tot > 0.5))

    def gender_rate(table: Mapping[tuple[str, bool], _Mean], key: str,
                    women: bool) -> float | None:
        g = table.get((key, women))
        if g is None or g.n < 200:
            return None
        return (g.s + 0.5) / (g.n + 1.0)

    for res in history:
        if res.ts >= end:
            break
        if res.ts != ts_now:
            for p in pending:
                add(p)
            pending = []
            ts_now = res.ts
        pending.append(res)
        if res.ts < start:
            continue
        rec = recs.get(res.event_id)
        if rec is None:
            continue
        fc = fr.FootballForecast(book, res.competition_id, res.home_id,
                                 res.away_id, rated_scope=fr.RATED_SCOPE_MARKETS)
        sup_a = fc.supremacy("side_a")
        ga = fc.centre("goals_for", "side_a")
        gb = fc.centre("goals_for", "side_b")
        rid = labels.get(res.event_id)
        rread = rbook.read(rid, res.competition_id, "cards_points")
        ref_ratio = rread.ratio(REF_K) if rid is not None and rread.n > 0 else 1.0
        gg = glob_goals[res.women].mean()
        lg_goals = (comp_goals[res.competition_id].shrunk(gg, GOALS_M)
                    if gg is not None else None)
        gf = glob_fouls[res.women].mean()
        lg_fouls = (comp_fouls[res.competition_id].shrunk(gf, GOALS_M)
                    if gf is not None else None)
        common = {"ts": res.ts, "eid": res.event_id, "women": res.women,
                  "ref_ratio": ref_ratio, "ref_n": rread.n if rid else 0,
                  "sup_a": sup_a}
        # ---- cards
        ca = fc.centre(CARD, "side_a")
        cb = fc.centre(CARD, "side_b")
        la = live.get((res.event_id, "side_a"))
        lb = live.get((res.event_id, "side_b"))
        if (rec.halves is not None and ca is not None and cb is not None
                and la is not None and lb is not None):
            gsh = glob_share[res.women]
            csh = comp_share.get(res.competition_id)
            cards_rows.append({
                **common, "halves": rec.halves,
                "y": tuple(float(v) for v in res.values[CARD]),
                "rating": (ca[0], cb[0]), "live": (la[0], lb[0]),
                "sup": (la[1], lb[1]),
                "share1": _shrunk_share(csh, gsh, 1, SHARE_M),
            })
        # ---- events
        if rec.reds is None or sup_a is None or ga is None or gb is None:
            continue
        erow: dict[str, Any] = {**common, "y": {}, "pL": {}, "x": {}}
        for kind in ("pens", "reds"):
            for scope in ("match", "1h"):
                pair = _pair(rec, kind, scope)
                key = f"{kind}:{scope}"
                gr = gender_rate(glob_sel, key, res.women)
                grt = gender_rate(glob_sel, key + ":tot", res.women)
                ge = glob_ev.get((key, res.women))
                if pair is None or gr is None or grt is None or ge is None:
                    continue
                p_side = comp_sel[(key, res.competition_id)].shrunk(gr, BASE_M)
                p_tot = comp_sel[(key + ":tot", res.competition_id)].shrunk(grt, BASE_M)
                lg_ev = comp_ev[(key, res.competition_id)].shrunk(
                    ge.s / ge.n, BASE_M)
                xs = []
                lr = book.league_rates(res.competition_id, "goals_for")
                for side, team, g in (("side_a", res.home_id, ga[0]),
                                      ("side_b", res.away_id, gb[0])):
                    sup = sup_a if side == "side_a" else -sup_a
                    lr_side = (None if lr is None
                               else lr[0] if side == "side_a" else lr[1])
                    xs.append({
                        "goals_lr": (math.log(g / lr_side)
                                     if lr_side and g > 0 else 0.0),
                        "goals": (math.log(g / lg_goals) if lg_goals and g > 0
                                  else 0.0),
                        "sup": clamp_supremacy(sup),
                        "own": math.log(_ratio(team_ev[(key, team)], lg_ev, TEAM_M))
                        if lg_ev > 0 else 0.0,
                        "fouls": math.log(_ratio(team_fouls[team], lg_fouls, TEAM_M))
                        if lg_fouls else 0.0,
                        "ref": math.log(ref_ratio),
                    })
                erow["y"][key] = (float(pair[0]), float(pair[1]))
                erow["pL"][key] = (p_side, p_tot)
                erow["x"][key] = xs
        if erow["y"]:
            event_rows.append(erow)
    note(f"cards rows {len(cards_rows)} event rows {len(event_rows)}")
    return {"cards": cards_rows, "events": event_rows}


# ------------------------------------------------------------------ fitting


def poisson_fit(x: F64, y: F64, offset: F64, iters: int = 50) -> F64:
    """beta of y ~ Poisson(exp(offset + x beta)), IRLS / Newton."""
    beta = np.zeros(x.shape[1])
    for _ in range(iters):
        mu = np.exp(offset + x @ beta)
        grad = x.T @ (y - mu)
        hess = (x * mu[:, None]).T @ x + 1e-9 * np.eye(x.shape[1])
        step = np.linalg.solve(hess, grad)
        beta = beta + step
        if float(np.max(np.abs(step))) < 1e-9:
            break
    return beta


def cluster_ci(delta: F64, groups: F64, reps: int, seed: int = 20261021,
               ) -> list[float]:
    """95% interval of mean(delta), resampling whole matches."""
    uniq, inv = np.unique(groups, return_inverse=True)
    sums = np.bincount(inv, weights=delta)
    cnts = np.bincount(inv).astype(float)
    rng = np.random.default_rng(seed)
    n = len(uniq)
    means = []
    for _ in range(reps):
        idx = rng.integers(0, n, n)
        means.append(float(sums[idx].sum() / cnts[idx].sum()))
    return [float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))]


def cal070(p: F64, y: F64) -> dict[str, Any]:
    m = p >= 0.70
    n = int(m.sum())
    out: dict[str, Any] = {"n_ge_070": n}
    if n:
        out["p"] = round(float(p[m].mean()), 4)
        out["realised"] = round(float(y[m].mean()), 4)
        out["gap_pp"] = round(100.0 * (out["realised"] - out["p"]), 2)
    return out


def _bll(p: F64, y: F64) -> F64:
    p = np.clip(p, 1e-9, 1 - 1e-9)
    out: F64 = -(y * np.log(p) + (1 - y) * np.log(1 - p))
    return out


def score_events(rows: Sequence[dict[str, Any]], split: int, reps: int,
                 ) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for name, kind, scope, sided in EVENTS:
        key = f"{kind}:{scope}"
        part = [r for r in rows if key in r["y"]]
        fit = [r for r in part if r["ts"] < split]
        test = [r for r in part if r["ts"] >= split]
        res: dict[str, Any] = {"n_fit_matches": len(fit),
                               "n_test_matches": len(test)}

        def side_arrays(rs: Sequence[dict[str, Any]], feats: tuple[str, ...],
                        ) -> tuple[F64, F64, F64, F64]:
            xs, ys, off, eid = [], [], [], []
            for r in rs:
                p_side = r["pL"][key][0]
                lam = -math.log(max(1e-9, 1.0 - p_side))
                for i in (0, 1):
                    xs.append([r["x"][key][i][f] for f in feats])
                    ys.append(r["y"][key][i])
                    off.append(math.log(lam))
                    eid.append(r["eid"])
            return (np.array(xs, dtype=float), np.array(ys), np.array(off),
                    np.array(eid, dtype=float))

        for model, feats in FEATURE_SETS[kind].items():
            xf, yf, of, _ = side_arrays(fit, feats)
            beta = poisson_fit(xf, yf, of)
            res.setdefault("beta", {})[model] = [round(float(b), 4) for b in beta]
        # scoring on the test window
        if sided:
            xt, yt, ot, et = side_arrays(test, FEATS)
            yb = (yt > 0.5).astype(float)
            p_flat = 1.0 - np.exp(-np.exp(ot))
            base = _bll(p_flat, yb)
            res["flat"] = {"ll": round(float(base.mean()), 6),
                           "under": cal070(1 - p_flat, 1 - yb),
                           "over": cal070(p_flat, yb),
                           "p_sd": round(float(p_flat.std()), 4)}
            for model, feats in FEATURE_SETS[kind].items():
                cols = [FEATS.index(f) for f in feats]
                beta = np.array(res["beta"][model])
                lam = np.exp(ot + xt[:, cols] @ beta)
                p = 1.0 - np.exp(-lam)
                d = _bll(p, yb) - base
                res[model] = {"d_ll": round(float(d.mean()), 6),
                              "ci": [round(v, 6) for v in cluster_ci(d, et, reps)],
                              "under": cal070(1 - p, 1 - yb),
                              "p_sd": round(float(p.std()), 4)}
        else:
            # total: lambda_L(total) x the mean of the sides' multipliers
            yb_l, pf_l, e_l = [], [], []
            mult_x: list[list[list[float]]] = []
            for r in test:
                p_tot = r["pL"][key][1]
                yb_l.append(float(sum(r["y"][key]) > 0.5))
                pf_l.append(p_tot)
                e_l.append(r["eid"])
                mult_x.append([[r["x"][key][i][f] for f in
                                FEATS]
                               for i in (0, 1)])
            yb = np.array(yb_l)
            p_flat = np.array(pf_l)
            et = np.array(e_l, dtype=float)
            xm = np.array(mult_x)  # (n, 2, 5)
            base = _bll(p_flat, yb)
            res["flat"] = {"ll": round(float(base.mean()), 6),
                           "under": cal070(1 - p_flat, 1 - yb),
                           "p_sd": round(float(p_flat.std()), 4)}
            side_name = name.replace("_total", "_for")
            betas = out.get(side_name, {}).get("beta", res["beta"])
            for model, feats in FEATURE_SETS[kind].items():
                cols = [FEATS.index(f) for f in feats]
                beta = np.array(betas[model])
                mult = np.exp(xm[:, :, cols] @ beta).mean(axis=1)
                lam = -np.log(np.clip(1 - p_flat, 1e-9, 1)) * mult
                p = 1.0 - np.exp(-lam)
                d = _bll(p, yb) - base
                res[model] = {"d_ll": round(float(d.mean()), 6),
                              "ci": [round(v, 6) for v in cluster_ci(d, et, reps)],
                              "under": cal070(1 - p, 1 - yb),
                              "p_sd": round(float(p.std()), 4)}
        out[name] = res
    return out


# ------------------------------------------------------------------ cards


def card_terms(rows: Sequence[dict[str, Any]], split: int,
               ) -> Callable[[dict[str, Any]], tuple[dict[str, tuple[float, float]],
                                                     dict[str, Any]]]:
    """model -> (side A, side B) full-match centres for a row."""
    gs = load_game_state()
    cl = load_closeness()
    ref = referees.load_effect_table().markets[CARD]
    b_gs = gs.betas[CARD]
    # refit the three terms on the fit window: y ~ Poisson(live x exp(b_gs s
    # + b_ref log ratio + g1 |s_home| + g2 s_home^2))
    xs, ys, off = [], [], []
    for r in rows:
        if r["ts"] >= split:
            continue
        sh = clamp_supremacy(r["sup"][0])
        for i in (0, 1):
            s = clamp_supremacy(r["sup"][i])
            xs.append([s, math.log(r["ref_ratio"]), abs(sh), sh * sh])
            ys.append(r["y"][i])
            off.append(math.log(max(r["live"][i], 1e-6)))
    beta = poisson_fit(np.array(xs), np.array(ys), np.array(off))
    info = {"installed": {"game_state": b_gs, "referee_beta": ref.beta,
                          "referee_k": ref.k,
                          "closeness": cl.describe(CARD)},
            "refit_on_fit_window": [round(float(b), 5) for b in beta],
            "n_fit_sides": len(ys)}

    def centres(r: dict[str, Any]) -> dict[str, tuple[float, float]]:
        sh = clamp_supremacy(r["sup"][0])
        cl_m = cl.multiplier(CARD, r["sup"][0]) or 1.0
        rr = r["ref_ratio"]
        out: dict[str, tuple[float, float]] = {}
        out["rating"] = r["rating"]
        out["live_raw"] = r["live"]
        inst, oos, rat_t = [], [], []
        for i in (0, 1):
            s = clamp_supremacy(r["sup"][i])
            m_inst = math.exp(b_gs * s) * (rr ** ref.beta) * cl_m
            m_oos = math.exp(beta[0] * s + beta[1] * math.log(rr)
                             + beta[2] * abs(sh) + beta[3] * sh * sh)
            inst.append(r["live"][i] * m_inst)
            oos.append(r["live"][i] * m_oos)
            rat_t.append(r["rating"][i] * m_inst)
        out["live"] = (inst[0], inst[1])
        out["live_oos"] = (oos[0], oos[1])
        out["rating_terms"] = (rat_t[0], rat_t[1])
        return out

    return lambda r: (centres(r), info)


CARD_MODELS = ("rating", "live_raw", "live", "live_oos", "rating_terms")
LINES = {1: (0.5, 1.5, 2.5, 3.5), 2: (0.5, 1.5, 2.5, 3.5, 4.5)}
SIDE_LINES = (0.5, 1.5)


def _nll(pmf: Sequence[float], k: int) -> float:
    return -math.log(max(pmf[k] if k < len(pmf) else 1e-12, 1e-12))


def score_cards(rows: Sequence[dict[str, Any]], split: int, reps: int,
                ) -> dict[str, Any]:
    terms = card_terms(rows, split)
    cen = []
    info: dict[str, Any] = {}
    for r in rows:
        c, info = terms(r)
        cen.append(c)
    out: dict[str, Any] = {"terms": info}
    fit_idx = [i for i, r in enumerate(rows) if r["ts"] < split]
    test_idx = [i for i, r in enumerate(rows) if r["ts"] >= split]
    rng = np.random.default_rng(20261021)
    sub = (rng.choice(fit_idx, 20000, replace=False) if len(fit_idx) > 20000
           else np.array(fit_idx))
    eids = np.array([rows[i]["eid"] for i in test_idx], dtype=float)
    for half in (1, 2):
        res: dict[str, Any] = {"n_test_matches": len(test_idx)}
        lls: dict[str, tuple[F64, F64]] = {}
        for model in CARD_MODELS:
            def lam(i: int, model: str = model) -> tuple[float, float]:
                s1 = rows[i]["share1"]
                s = s1 if half == 1 else 1.0 - s1
                a, b = cen[i][model]
                return a * s, b * s
            # r on the fit window
            best_r, best_ll = 1e6, math.inf
            for rr in R_GRID:
                tot = 0.0
                for i in sub:
                    la, lb = lam(int(i))
                    ya, yb = rows[int(i)]["halves"][half - 1]
                    tot += (_nll(half_count_pmf(la, rr), int(ya))
                            + _nll(half_count_pmf(lb, rr), int(yb)))
                if tot < best_ll:
                    best_r, best_ll = rr, tot
            side_l, tot_l = [], []
            sel: dict[str, tuple[list[float], list[float]]] = defaultdict(
                lambda: ([], []))
            for i in test_idx:
                la, lb = lam(i)
                ya, yb = rows[i]["halves"][half - 1]
                pa = half_count_pmf(la, best_r)
                pb = half_count_pmf(lb, best_r)
                side_l.append(_nll(pa, int(ya)) + _nll(pb, int(yb)))
                pt = np.convolve(pa, pb)
                tot_l.append(_nll(list(pt), int(ya + yb)))
                for line in LINES[half]:
                    po = float(max(0.0, 1.0 - pt[: math.floor(line) + 1].sum()))
                    yo = float(ya + yb > line)
                    for d, p, y in (("OVER", po, yo), ("UNDER", 1 - po, 1 - yo)):
                        sel[f"total|{d}"][0].append(p)
                        sel[f"total|{d}"][1].append(y)
                for line in SIDE_LINES:
                    for pm, yy in ((pa, ya), (pb, yb)):
                        po = float(max(0.0, 1.0 - sum(pm[: math.floor(line) + 1])))
                        yo = float(yy > line)
                        for d, p, y in (("OVER", po, yo), ("UNDER", 1 - po, 1 - yo)):
                            sel[f"for|{d}"][0].append(p)
                            sel[f"for|{d}"][1].append(y)
            lls[model] = (np.array(side_l), np.array(tot_l))
            res[model] = {
                "r": best_r,
                "side_ll": round(float(np.mean(side_l)), 6),
                "total_ll": round(float(np.mean(tot_l)), 6),
                "cal_ge_070": {k: cal070(np.array(v[0]), np.array(v[1]))
                               for k, v in sorted(sel.items())},
            }
        for model in CARD_MODELS[1:]:
            ds = lls[model][0] - lls["rating"][0]
            dt = lls[model][1] - lls["rating"][1]
            res[f"{model}_minus_rating"] = {
                "side_ll": round(float(ds.mean()), 6),
                "side_ci": [round(v, 6) for v in cluster_ci(ds, eids, reps)],
                "total_ll": round(float(dt.mean()), 6),
                "total_ci": [round(v, 6) for v in cluster_ci(dt, eids, reps)],
            }
        out[f"half{half}"] = res
    return out


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db", required=True)
    ap.add_argument("--history", default="data/cache/football_history.pkl")
    ap.add_argument("--records", required=True)
    ap.add_argument("--features", default=None)
    ap.add_argument("--fit-from", default="2025-08-01")
    ap.add_argument("--test-from", default="2026-03-01")
    ap.add_argument("--test-to", default="2026-10-14")
    ap.add_argument("--boot", type=int, default=500)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)
    try:
        feats: dict[str, Any] | None = None
        if args.features and Path(args.features).exists():
            feats = pickle.loads(Path(args.features).read_bytes())
        if feats is None:
            history = load_pickle(Path(args.history))
            recs = pickle.loads(Path(args.records).read_bytes())
            labels = referees.load_labels(args.db)
            note(f"history {len(history)} records {len(recs)} labels {len(labels)}")
            feats = collect(history, recs, labels, ts_of(args.fit_from),
                            ts_of(args.test_to))
            del history
            if args.features:
                Path(args.features).write_bytes(pickle.dumps(feats))
        split = ts_of(args.test_from)
        out: dict[str, Any] = {
            "args": vars(args),
            "at": datetime.now(UTC).isoformat(timespec="seconds"),
            "unfitted_constants": ["TEAM_M", "GOALS_M"],
        }
        note("events")
        out["events"] = score_events(feats["events"], split, args.boot)
        note("cards")
        out["cards"] = score_cards(feats["cards"], split, args.boot)
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
