"""Exam data per group for scripts/sofa/measure_schedule_exam.py (evidence code).

mode "exam": opens the sealed exam outcome stores (G2) - only the exam script
calls it, once. mode "fake": every exam outcome is DRAWN from the base arm
(seeded) - a dry run of the whole P1-P6 machinery that opens no exam outcome.

Every group returns a GroupData: per-match score differences (P1), per-row
differences with strata (P5), calibrated line rows (P3 / P4, dev curves per
arm), materiality (P2) and the exam-refit signs (P6). Definitions:
pre-registration sections 8 and doprecyzowania 1-14 of
docs/sofa/history/STAN_KONTEKST_TERMINARZA_2026-11-09.md.
"""
from __future__ import annotations

import gzip
import json
import math
import pickle
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

REPO = Path("/Users/mkoziol/projects/bet")
D = REPO / "data/refit_2026-11-08_schedule"
HERE = Path(__file__).resolve().parent
for p in (str(HERE), str(REPO / "src"), str(REPO), str(REPO / "scripts/sofa")):
    if p not in sys.path:
        sys.path.insert(0, p)

import fb_analysis as fb  # noqa: E402

sys.path.insert(0, str(HERE))  # fb / fr_analysis prepend the scratch dir: keep HERE first
import fr_analysis as fra  # noqa: E402

sys.path.insert(0, str(HERE))
import nbvec  # noqa: E402
import tw_analysis as twa  # noqa: E402
from fit_confidence import EDGES, MIN_MARKET_BUCKET, MIN_POOLED_BUCKET  # noqa: E402

from bet.sofa.football_result import result_probs  # noqa: E402

EXAM_FROM = 1767225600  # 2026-01-01 00:00Z
EXAM_TO = 1793491200    # 2026-11-01 00:00Z
DEV_END = EXAM_FROM
EPS = 1e-6
FAKE_SEED = 20261109


# --------------------------------------------------------------------------
@dataclass
class Clusters:
    """Bootstrap factors: [(n_clusters, [index arrays into the match axis])]."""
    factors: list[tuple[int, list[np.ndarray]]]


@dataclass
class Lines:
    """Calibrated line rows (P3 / P4): match index, calibrated base / treat p,
    the line's outcome; rows without a curve in either arm are dropped."""
    match: np.ndarray
    cb: np.ndarray
    ct: np.ndarray
    y: np.ndarray
    dropped: int


@dataclass
class GroupData:
    name: str
    match_diff: np.ndarray            # per match: sum over g's rows of S_treat - S_base
    clusters: Clusters
    row_match: np.ndarray             # per row: its match index
    row_diff: np.ndarray              # per row: S_treat - S_base
    strata: dict[str, np.ndarray]     # stratum name -> per-row bool mask
    lines: Lines
    p2: dict[str, Any]
    p6: dict[str, Any]
    other_groups: dict[str, Any] = field(default_factory=dict)
    info: dict[str, Any] = field(default_factory=dict)


# --------------------------------------------------------------------------
def bucket(p: np.ndarray) -> np.ndarray:
    """fit_confidence.bucket_of, vectorised."""
    b = np.searchsorted(np.asarray(EDGES), p, side="right") - 1
    return np.clip(b, 0, len(EDGES) - 2)


def wilson_lo(k: np.ndarray, n: np.ndarray, z: float = 1.959964) -> np.ndarray:
    """fit_confidence.wilson_lo, vectorised (n > 0)."""
    n = n.astype(float)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    m = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return np.maximum(0.0, c - m)


class Curves:
    """Doprecyzowanie 8 P3: EDGES buckets per (market, direction) key, value =
    Wilson lo95 of the realised rate, a key bucket >= 400 rows, else the
    group's pooled bucket >= 200, else no curve (row out of P3)."""

    def __init__(self, p: np.ndarray, y: np.ndarray, key: np.ndarray, nkeys: int) -> None:
        nb = len(EDGES) - 1
        b = bucket(np.round(p, 6))
        code = key * nb + b
        n = np.bincount(code, minlength=nkeys * nb).astype(float)
        k = np.bincount(code, weights=y.astype(float), minlength=nkeys * nb)
        self.key_val = np.where(n >= MIN_MARKET_BUCKET, wilson_lo(k, np.maximum(n, 1)), np.nan)
        pn = np.bincount(b, minlength=nb).astype(float)
        pk = np.bincount(b, weights=y.astype(float), minlength=nb)
        self.pool_val = np.where(pn >= MIN_POOLED_BUCKET, wilson_lo(pk, np.maximum(pn, 1)), np.nan)
        self.nb = nb

    def apply(self, p: np.ndarray, key: np.ndarray) -> np.ndarray:
        b = bucket(np.round(p, 6))
        v = self.key_val[key * self.nb + b]
        return np.where(np.isnan(v), self.pool_val[b], v)


def ll(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    q = np.clip(p, EPS, 1 - EPS)
    return -(y * np.log(q) + (1 - y) * np.log(1 - q))


def calibrated_lines(dev: tuple, exam: tuple, nkeys: int) -> Lines:
    """dev / exam = (p_base, p_treat, y, key[, match]) line arrays."""
    pb_d, pt_d, y_d, k_d = dev
    cur_b = Curves(pb_d, y_d, k_d, nkeys)
    cur_t = Curves(pt_d, y_d, k_d, nkeys)
    pb, pt, y, k, m = exam
    cb, ct = cur_b.apply(pb, k), cur_t.apply(pt, k)
    ok = ~(np.isnan(cb) | np.isnan(ct))
    return Lines(m[ok], cb[ok], ct[ok], y[ok].astype(float), int((~ok).sum()))


def football_clusters(home: np.ndarray, away: np.ndarray) -> Clusters:
    _, h = np.unique(home, return_inverse=True)
    _, a = np.unique(away, return_inverse=True)
    return Clusters([(int(h.max()) + 1, [h]), (int(a.max()) + 1, [a])])


def tennis_clusters(home: np.ndarray, away: np.ndarray, tw: np.ndarray) -> Clusters:
    _, inv = np.unique(np.concatenate([home, away]), return_inverse=True)
    h, a = inv[: len(home)], inv[len(home):]
    _, t = np.unique(tw, return_inverse=True)
    return Clusters([(int(inv.max()) + 1, [h, a]), (int(t.max()) + 1, [t])])


# --------------------------------------------------------------------------
# football context shared by goals / football_result
_CTX: dict[str, Any] = {}


def football_ctx() -> dict[str, Any]:
    if _CTX:
        return _CTX
    feats = pickle.loads((D / "football_features.pkl").read_bytes())
    cont = {int(c) for c in json.loads(
        (REPO / "config/sofa_cup_strength.json").read_text())["competitions"]}
    prior: dict[tuple[int, int], int] = {}
    seen: dict[tuple[int, int, int], int] = defaultdict(int)
    for eid, f in sorted(feats.items(), key=lambda t: t[1]["ts"]):
        for side, tid in (("home", f["home_id"]), ("away", f["away_id"])):
            key = (tid, f["comp"], f["season"])
            prior[(eid, 0 if side == "home" else 1)] = seen[key]
            seen[key] += 1
    sup: dict[int, float] = {}
    for tier in ("dev", "exam"):
        for rec in fb.read_chunks(tier, "forecasts"):
            if rec[5] == 1 and rec[7] is not None:
                sup[rec[0]] = abs(float(rec[7]))
    dev_s = np.array([v for e, v in sup.items() if e in feats and feats[e]["ts"] < DEV_END])
    edges = np.quantile(dev_s, [1 / 3, 2 / 3])
    _CTX.update(feats=feats, cont=cont, prior=prior, sup=sup, sup_edges=edges,
                women=fb._women())
    return _CTX


def football_strata(eids: np.ndarray, comps: np.ndarray, women: np.ndarray) -> dict[str, np.ndarray]:
    c = football_ctx()
    s = np.array([c["sup"].get(int(e), np.nan) for e in eids])
    lo, hi = c["sup_edges"]
    rnd = np.array([min(c["prior"].get((int(e), 0), 99), c["prior"].get((int(e), 1), 99)) <= 2
                    for e in eids])
    cont = np.array([x is not None and int(x) in c["cont"] for x in comps], dtype=bool)
    return {"women": women, "men": ~women,
            "fav_s_t1": s < lo, "fav_s_t2": (s >= lo) & (s < hi), "fav_s_t3": s >= hi,
            "continental": cont, "domestic": ~cont, "round_le3": rnd, "round_gt3": ~rnd}


def _match_index(eids: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    u, inv = np.unique(eids, return_inverse=True)
    return u, inv


# --------------------------------------------------------------------------
def goals_rows(tier: str, mode: str) -> list[dict]:
    """fb.load for one tier (D10 centre). exam outcomes from full/exam_y only in
    mode "exam"; mode "fake" draws y from the base NB."""
    feats = football_ctx()["feats"]
    women = football_ctx()["women"]
    metrics = set(fb.GROUPS["goals"]) | {fb.total_of(m) for m in fb.GROUPS["goals"]}
    if tier == "dev":
        return [r for r in pickle.load(open(D / "fb_dev.pkl", "rb"))["rows"]
                if r["market"] in metrics]
    ys: dict = {}
    if mode == "exam":
        for e, m, s, b, a in fb.read_chunks("exam_y", "y"):
            if m in metrics:
                ys[(e, m, s, b)] = a
    rng = np.random.default_rng(FAKE_SEED)
    out = []
    for r in fb.read_chunks("exam", "rows"):
        (eid, ts, comp, sport, market, subject, book, n, mean, var, shrunk, final,
         phase, disp, emp, rp, sample, home, away, nrows) = r
        if sport != "football" or market not in metrics or book != fb.book_for(market):
            continue
        f = feats.get(eid)
        if f is None or f["national"] or ts < fb.GOALS_FROM or not (EXAM_FROM <= ts < EXAM_TO):
            continue
        centre = fb.d10_centre(market, eid, final, phase)
        alpha = disp[0] if disp else 0.0
        if mode == "exam":
            y = ys.get((eid, market, subject, book))
            if y is None:
                continue
        else:
            if alpha > 0:
                rr = 1 / alpha
                y = float(rng.negative_binomial(rr, rr / (rr + centre)))
            else:
                y = float(rng.poisson(centre))
        side = None
        if market.endswith("_for"):
            side = "home" if int(subject) == home else "away" if int(subject) == away else None
            if side is None:
                continue
        out.append({"eid": eid, "ts": ts, "comp": comp, "market": market, "side": side,
                    "y": y, "centre": centre, "alpha": alpha, "home": home, "away": away,
                    "season": f["season"], "women": comp in women})
    return out


def goals_treat(rows: list[dict], frozen: dict) -> np.ndarray:
    """Per row treated centre: `_for` x exp(t side), `_total` = sum of the sides
    each with its own t (doprecyzowanie 3) - fb.group_delta's arithmetic."""
    feats = football_ctx()["feats"]
    t = fb.side_terms(rows, feats, frozen)
    out = np.empty(len(rows))
    for i, r in enumerate(rows):
        if r["side"] is not None:
            tt = t.get((r["eid"], r["market"], r["side"]))
            out[i] = r["centre"] * math.exp(tt[0]) if tt else r["centre"]
        else:
            m = r["market"][: -len("_total")] + "_for"
            h, a = t.get((r["eid"], m, "home")), t.get((r["eid"], m, "away"))
            out[i] = (r["centre"] * (h[1] * math.exp(h[0]) + a[1] * math.exp(a[0])) / (h[1] + a[1])
                      if h and a else r["centre"])
    return out


def count_lines(rows: list[dict], mt: np.ndarray, key_of: dict[str, int],
                match: np.ndarray | None) -> tuple:
    """lines_for(base centre), both directions: (p_base, p_treat, y, key[, match])."""
    mb = np.array([r["centre"] for r in rows])
    al = np.array([r["alpha"] for r in rows])
    y = np.array([r["y"] for r in rows])
    low = np.maximum(0, np.floor(mb) - 4)
    pb = nbvec.p_lines(mb, al, low)
    pt = nbvec.p_lines(mt, al, low)
    yo = (y[:, None] > (low[:, None] + np.arange(9)[None, :])).astype(np.int8)
    mk = np.array([key_of[r["market"]] for r in rows])
    keys = np.concatenate([np.repeat(2 * mk, 9), np.repeat(2 * mk + 1, 9)])
    pbs = np.concatenate([pb.ravel(), 1 - pb.ravel()])
    pts = np.concatenate([pt.ravel(), 1 - pt.ravel()])
    ys = np.concatenate([yo.ravel(), 1 - yo.ravel()])
    if match is None:
        return pbs, pts, ys, keys
    ms = np.concatenate([np.repeat(match, 9), np.repeat(match, 9)])
    return pbs, pts, ys, keys, ms


def exposure_material(frozen: dict, rows: list[dict]) -> dict[str, Any]:
    """P2 football: any frozen |c| >= 0.03 on a column whose exposed exam rows
    (column = 1, own or opp side of the group's `_for` rows) are >= 2%."""
    feats = football_ctx()["feats"]
    n = 0
    exp_: dict[str, int] = defaultdict(int)
    for r in rows:
        if r["side"] is None:
            continue
        f = feats[r["eid"]]
        own, opp = (f["home"], f["away"]) if r["side"] == "home" else (f["away"], f["home"])
        if not (own.coverage and opp.coverage):
            continue
        n += 1
        io, ip = own.indicators(), opp.indicators()
        for c in fb.COLS:
            exp_[f"own_{c}"] += int(bool(io[c]))
            exp_[f"opp_{c}"] += int(bool(ip[c]))
    hits = []
    for m, cf in frozen.items():
        for name, c in cf.items():
            share = exp_.get(name, 0) / max(n, 1)
            if abs(c) >= 0.03 and share >= 0.02:
                hits.append({"metric": m, "coef": name, "c": c, "exposed_share": share})
    return {"material": bool(hits), "hits": hits, "rows": n,
            "exposure": {k: v / max(n, 1) for k, v in exp_.items()}}


def refit_signs(rows: list[dict], frozen: dict, p2_hits: list[dict], metric_key: str = "market") -> dict:
    """P6: unshrunk exam refit of each material (metric, coefficient) - the sign
    against the frozen (dev) one."""
    feats = football_ctx()["feats"]
    out = []
    by_metric: dict[str, list[dict]] = defaultdict(list)
    for h in p2_hits:
        by_metric[h["metric"]].append(h)
    for m, hs in by_metric.items():
        rs = fb.metric_rows(rows, m, EXAM_FROM, EXAM_TO, feats)
        if len(rs) < 2000:
            for h in hs:
                out.append({**h, "exam_b": None, "same_sign": False, "note": "< 2000 rows"})
            continue
        b, se, names, _ = fb.fit_metric(rs, feats)
        for h in hs:
            v = float(b[names.index(h["coef"])])
            out.append({**h, "exam_b": v, "exam_se": float(se[names.index(h["coef"])]),
                        "same_sign": bool(np.sign(v) == np.sign(h["c"]))})
    return {"pass": bool(out) and all(o["same_sign"] for o in out), "coefs": out}


def group_goals(mode: str) -> GroupData:
    frozen_all = json.loads((D / "fb_frozen.json").read_text())["coef"]
    frozen = {m: frozen_all[m] for m in fb.GROUPS["goals"]}
    ex = goals_rows("exam", mode)
    mt = goals_treat(ex, frozen)
    y = np.array([r["y"] for r in ex])
    mb = np.array([r["centre"] for r in ex])
    al = np.array([r["alpha"] for r in ex])
    row_diff = fb.nb_logscore(y, mt, al) - fb.nb_logscore(y, mb, al)
    eids = np.array([r["eid"] for r in ex])
    u, inv = _match_index(eids)
    match_diff = np.bincount(inv, weights=row_diff, minlength=len(u))
    first = {}
    for i, e in enumerate(inv):
        first.setdefault(int(e), i)
    fi = np.array([first[k] for k in range(len(u))])
    home = np.array([ex[i]["home"] for i in fi])
    away = np.array([ex[i]["away"] for i in fi])
    strata = football_strata(eids, np.array([r["comp"] for r in ex]),
                             np.array([r["women"] for r in ex]))
    markets = sorted({m for m in fb.GROUPS["goals"]} | {fb.total_of(m) for m in fb.GROUPS["goals"]})
    key_of = {m: i for i, m in enumerate(markets)}
    dev = goals_rows("dev", mode)
    dev_lines = count_lines(dev, goals_treat(dev, frozen), key_of, None)
    lines = calibrated_lines(dev_lines, count_lines(ex, mt, key_of, inv), 2 * len(markets))
    del dev, dev_lines
    p2 = exposure_material(frozen, ex)
    p6 = refit_signs(ex, frozen, p2["hits"])
    return GroupData("goals", match_diff, football_clusters(home, away), inv, row_diff, strata,
                     lines, p2, p6,
                     other_groups={"all": "0 by construction: path (i) touches only goals rows (D3)"},
                     info={"rows": len(ex), "matches": len(u)})


# --------------------------------------------------------------------------
def fr_forecasts(tier: str) -> list:
    return list(fra.forecasts(tier))


def fr_rows(tier: str, mode: str) -> list[tuple]:
    """(eid, ts, comp, home, away, lh, la, th, ta, outcome) per match."""
    c = football_ctx()
    feats = c["feats"]
    cf = json.loads((D / "fr_frozen.json").read_text())["coef"]
    if tier == "dev":
        ys = pickle.loads((D / "fr_dev_y.pkl").read_bytes())
        lo, hi = fb.GOALS_FROM, DEV_END
    else:
        ys = pickle.loads((D / "full/exam_y/fr_y.pkl").read_bytes()) if mode == "exam" else None
        lo, hi = EXAM_FROM, EXAM_TO
    rng = np.random.default_rng(FAKE_SEED + 1)
    out = []
    for eid, ts, comp, home, away, book, cents, sup in fr_forecasts(tier):
        f = feats.get(eid)
        lh, la = cents.get(("goals_for", "side_a")), cents.get(("goals_for", "side_b"))
        if f is None or f["national"] or lh is None or la is None or not (lo <= ts < hi):
            continue
        th, ta = fra.side_t(feats, eid, "home", cf), fra.side_t(feats, eid, "away", cf)
        if ys is not None:
            if eid not in ys:
                continue
            hg, ag = ys[eid]
            res = "1" if hg > ag else "2" if ag > hg else "X"
            goals = (hg, ag)
        else:
            pb = result_probs(lh, la, fra.R)
            res = str(rng.choice(["1", "X", "2"], p=[pb["1"], pb["X"], pb["2"]]))
            goals = None
        out.append((eid, ts, comp, home, away, lh, la, th, ta, res, goals))
    return out


def fr_lines(rows: list[tuple], match: np.ndarray | None) -> tuple:
    sel = ["1", "X", "2"]
    pb, pt, y, k, m = [], [], [], [], []
    for i, (eid, ts, comp, home, away, lh, la, th, ta, res, _g) in enumerate(rows):
        b = result_probs(lh, la, fra.R)
        t = result_probs(lh * math.exp(th), la * math.exp(ta), fra.R)
        for j, s in enumerate(sel):
            pb.append(b[s])
            pt.append(t[s])
            y.append(1 if res == s else 0)
            k.append(j)
            if match is not None:
                m.append(match[i])
    arr = (np.array(pb), np.array(pt), np.array(y), np.array(k))
    return arr if match is None else (*arr, np.array(m))


def group_football_result(mode: str) -> GroupData:
    c = football_ctx()
    cf = json.loads((D / "fr_frozen.json").read_text())["coef"]
    ex = fr_rows("exam", mode)
    ln = fr_lines(ex, np.arange(len(ex)))
    pb, pt, y = ln[0].reshape(-1, 3), ln[1].reshape(-1, 3), ln[2].reshape(-1, 3)
    row_diff = (-np.log((pt * y).sum(1))) - (-np.log((pb * y).sum(1)))
    eids = np.array([r[0] for r in ex])
    strata = football_strata(eids, np.array([r[2] for r in ex]),
                             np.array([r[2] in c["women"] for r in ex]))
    dev = fr_rows("dev", "dev")
    lines = calibrated_lines(fr_lines(dev, None), ln, 3)
    # P2: frozen |c| >= 0.03 on a column exposed in >= 2% of exam match-sides
    feats = c["feats"]
    n = 0
    exp_: dict[str, int] = defaultdict(int)
    for r in ex:
        f = feats[r[0]]
        for own, opp in ((f["home"], f["away"]), (f["away"], f["home"])):
            if not (own.coverage and opp.coverage):
                continue
            n += 1
            io, ip = own.indicators(), opp.indicators()
            for col in fb.COLS:
                exp_[f"own_{col}"] += int(bool(io[col]))
                exp_[f"opp_{col}"] += int(bool(ip[col]))
    hits = [{"metric": "goals_for(rating)", "coef": k, "c": v, "exposed_share": exp_.get(k, 0) / max(n, 1)}
            for k, v in cf.items() if abs(v) >= 0.03 and exp_.get(k, 0) / max(n, 1) >= 0.02]
    p2 = {"material": bool(hits), "hits": hits, "sides": n}
    # P6: exam refit of the goals term on the rating centres (exam goals)
    if mode == "exam":
        rows6 = []
        for eid, ts, comp, home, away, lh, la, th, ta, res, g in ex:
            for side, cc, yy in (("home", lh, g[0]), ("away", la, g[1])):
                rows6.append({"eid": eid, "ts": ts, "comp": comp, "market": "goals_for", "side": side,
                              "y": float(yy), "centre": cc, "alpha": 0.0, "home": home, "away": away,
                              "season": feats[eid]["season"]})
        rs = fb.metric_rows(rows6, "goals_for", EXAM_FROM, EXAM_TO, feats)
        b, se, names, _ = fb.fit_metric(rs, feats)
        co = [{**h, "exam_b": float(b[names.index(h["coef"])]),
               "same_sign": bool(np.sign(b[names.index(h["coef"])]) == np.sign(h["c"]))} for h in hits]
        p6 = {"pass": bool(co) and all(x["same_sign"] for x in co), "coefs": co}
    else:
        p6 = {"pass": None, "coefs": [], "note": "fake mode: no exam goals"}
    home = np.array([r[3] for r in ex])
    away = np.array([r[4] for r in ex])
    m = np.arange(len(ex))
    return GroupData("football_result", row_diff.copy(), football_clusters(home, away), m, row_diff,
                     strata, lines, p2, p6,
                     other_groups={"all": "0 by construction: path (ii) touches only rating-result rows (D3)"},
                     info={"matches": len(ex)})


# --------------------------------------------------------------------------
_TW: dict[str, Any] = {}


def tw_data(mode: str) -> dict[str, Any]:
    if _TW:
        return _TW
    fz = json.loads((D / "tennis/tw_frozen.json").read_text())
    arms = {a: {t: np.array(v) for t, v in fz[a].items()} for a in ("base", "treat")}
    x = [r for r in pickle.loads((D / "tennis/tw_exam_X.pkl").read_bytes()) if r["best_of"] == 3]
    pb, pt = twa.arm_p(arms, x)
    if mode == "exam":
        ys = pickle.loads((D / "tennis/tw_exam_y.pkl").read_bytes())
        keep = [i for i, r in enumerate(x) if r["event_id"] in ys]
        y = np.array([float(ys[x[i]["event_id"]]) for i in keep])
    else:
        rng = np.random.default_rng(FAKE_SEED + 2)
        keep = list(range(len(x)))
        y = (rng.random(len(x)) < pb).astype(float)
    x = [x[i] for i in keep]
    pb, pt = pb[keep], pt[keep]
    dev = [r for r in twa.load_dev() if r["best_of"] == 3]
    db, dt_ = twa.arm_p(arms, dev)
    _TW.update(arms=arms, x=x, pb=pb, pt=pt, y=y, dev=dev, db=db, dt=dt_,
               dy=np.array([r["y"] for r in dev], dtype=float))
    return _TW


def tennis_strata(rows: list[dict]) -> dict[str, np.ndarray]:
    tier = np.array([r["tier"] for r in rows])
    fem = np.array([bool(r.get("female")) for r in rows])
    return {"ITF": tier == "ITF", "CH": tier == "CH", "TOUR": tier == "TOUR",
            "women": fem, "men": ~fem}


TW_BUCKETS = {"games78>=3 either": ("max_games78", 3.0, "d_games78"),
              "layoff21 either": ("max_layoff21", 1.0, "d_layoff21"),
              "ret14 either": ("max_ret14", 1.0, "d_ret14")}


def tw_p2(x: list[dict], dp: np.ndarray) -> dict[str, Any]:
    hits = []
    for name, (col, thr, coef) in TW_BUCKETS.items():
        m = np.array([r["sched"][col] >= thr for r in x])
        share = float(m.mean())
        mad = float(np.abs(dp[m]).mean()) if m.any() else 0.0
        if share >= 0.02 and mad >= 0.01:
            hits.append({"bucket": name, "coef": coef, "share": share, "mean_abs_dp": mad})
    return {"material": bool(hits), "hits": hits,
            "buckets": {n: {"share": float(np.mean([r["sched"][c] >= t for r in x])),
                            "mean_abs_dp": float(np.abs(dp[np.array([r["sched"][c] >= t for r in x])]).mean())}
                        for n, (c, t, _) in TW_BUCKETS.items()}}


def pooled_treat(arms_treat: dict[str, np.ndarray], rows: list[dict]) -> dict[str, float]:
    n: dict[str, int] = defaultdict(int)
    for r in rows:
        n[r["tier"]] += 1
    tot = sum(n[t] for t in arms_treat)
    return {c: float(sum(arms_treat[t][1 + twa.TREAT.index(c)] * n[t] / tot for t in arms_treat))
            for c in twa.SCHED}


def tw_p6(td: dict[str, Any], p2: dict[str, Any], mode: str) -> dict[str, Any]:
    if mode != "exam":
        return {"pass": None, "coefs": [], "note": "fake mode"}
    rows = [{**r, "y": float(v)} for r, v in zip(td["x"], td["y"], strict=True)]
    refit = twa.fit_arms(rows)["treat"]
    ex = pooled_treat(refit, rows)
    dv = pooled_treat(td["arms"]["treat"], td["dev"])
    co = [{**h, "dev": dv[h["coef"]], "exam": ex[h["coef"]],
           "same_sign": bool(np.sign(dv[h["coef"]]) == np.sign(ex[h["coef"]]))} for h in p2["hits"]]
    return {"pass": bool(co) and all(c["same_sign"] for c in co), "coefs": co}


def group_tennis_winner(mode: str, games: GroupData | None = None) -> GroupData:
    td = tw_data(mode)
    x, pb, pt, y = td["x"], td["pb"], td["pt"], td["y"]
    row_diff = twa.logloss(pt, y) - twa.logloss(pb, y)
    m = np.arange(len(x))
    cl = tennis_clusters(np.array([r["home_id"] for r in x]), np.array([r["away_id"] for r in x]),
                         np.array([r["tournament_id"] * 10000 + twa.week(r["ts"]) for r in x]))
    # line rows: each player's p (home p, away 1 - p), one key
    dev_l = (np.concatenate([td["db"], 1 - td["db"]]), np.concatenate([td["dt"], 1 - td["dt"]]),
             np.concatenate([td["dy"], 1 - td["dy"]]), np.zeros(2 * len(td["dev"]), dtype=int))
    ex_l = (np.concatenate([pb, 1 - pb]), np.concatenate([pt, 1 - pt]), np.concatenate([y, 1 - y]),
            np.zeros(2 * len(x), dtype=int), np.concatenate([m, m]))
    lines = calibrated_lines(dev_l, ex_l, 1)
    p2 = tw_p2(x, pt - pb)
    p6 = tw_p6(td, p2, mode)
    other = {}
    if games is not None:
        other["tennis_games_sets"] = {"row_match": games.row_match, "row_diff": games.row_diff,
                                      "clusters": games.clusters}
    return GroupData("tennis_winner", row_diff.copy(), cl, m, row_diff, tennis_strata(x), lines,
                     p2, p6, other_groups=other, info={"matches": len(x)})


def tg_rows(tier: str, mode: str) -> tuple[list[tuple], np.ndarray]:
    X = pickle.loads((D / f"tennis/tg_{tier}_X.pkl").read_bytes())
    if tier == "exam" and mode != "exam":
        rng = np.random.default_rng(FAKE_SEED + 3)
        return X, (rng.random(len(X)) < np.array([r[9] for r in X])).astype(float)
    store = "exam_y" if tier == "exam" else "dev"
    want = {(r[0], r[5], str(r[6])) for r in X}
    ys = {}
    for e, mk, s, b, a in fb.read_chunks(store, "y"):
        if (e, mk, str(s)) in want:
            ys[(e, mk, str(s))] = a
    keep = [r for r in X if (r[0], r[5], str(r[6])) in ys]
    y = np.array([1.0 if ys[(r[0], r[5], str(r[6]))] > r[8] else 0.0 for r in keep])
    return keep, y


TG_MARKETS = ["games_won_for", "games_won_set1_for", "games_won_set2_for", "games_won_set3_for"]


def group_tennis_games(mode: str) -> GroupData:
    td = tw_data(mode)
    by_eid = {r["event_id"]: r for r in td["x"]}
    X, y = tg_rows("exam", mode)
    keep = [i for i, r in enumerate(X) if r[0] in by_eid]
    X = [X[i] for i in keep]
    y = y[keep]
    p0 = np.array([r[9] for r in X])
    p1 = np.array([r[10] for r in X])
    row_diff = ll(p1, y) - ll(p0, y)
    eids = np.array([r[0] for r in X])
    u, inv = np.unique(eids, return_inverse=True)
    match_diff = np.bincount(inv, weights=row_diff, minlength=len(u))
    first: dict[int, int] = {}
    for i, e in enumerate(inv):
        first.setdefault(int(e), i)
    fi = np.array([first[k] for k in range(len(u))])
    cl = tennis_clusters(np.array([X[i][2] for i in fi]), np.array([X[i][3] for i in fi]),
                         np.array([X[i][4] * 10000 + twa.week(X[i][1]) for i in fi]))
    key = np.array([TG_MARKETS.index(r[5]) for r in X])
    dX, dy = tg_rows("dev", "dev")
    dk = np.array([TG_MARKETS.index(r[5]) for r in dX])
    dev_l = (np.concatenate([[r[9] for r in dX], [1 - r[9] for r in dX]]),
             np.concatenate([[r[10] for r in dX], [1 - r[10] for r in dX]]),
             np.concatenate([dy, 1 - dy]), np.concatenate([2 * dk, 2 * dk + 1]))
    ex_l = (np.concatenate([p0, 1 - p0]), np.concatenate([p1, 1 - p1]), np.concatenate([y, 1 - y]),
            np.concatenate([2 * key, 2 * key + 1]), np.concatenate([inv, inv]))
    lines = calibrated_lines(dev_l, ex_l, 2 * len(TG_MARKETS))
    # P2: the winner's buckets on the games rows (mean |dp| of the lines)
    hits = []
    for name, (col, thr, coef) in TW_BUCKETS.items():
        mm = np.array([by_eid[r[0]]["sched"][col] >= thr for r in X])
        share_m = float(np.mean([by_eid[e]["sched"][col] >= thr for e in u]))
        mad = float(np.abs(p1 - p0)[mm].mean()) if mm.any() else 0.0
        if share_m >= 0.02 and mad >= 0.01:
            hits.append({"bucket": name, "coef": coef, "share": share_m, "mean_abs_dp": mad})
    p2 = {"material": bool(hits), "hits": hits}
    p6 = tw_p6(td, {"hits": hits}, mode)
    strata = tennis_strata([by_eid[e] for e in eids])
    return GroupData("tennis_games_sets", match_diff, cl, inv, row_diff, strata, lines, p2, p6,
                     info={"matches": len(u), "lines": len(X)})
