"""Football count / goals groups (path (i)) - dev stages (pre-registration 5, 6, 8).

  load    : records (full/dev rows + y) x football_features -> fb_dev.npz-like pickle
  explore : per metric Poisson GLM, offset log(final centre), team-season FE;
            S1 permutation (FE fixed), S2 lag + mechanism-free, S3 signs
  validate: fit on explore, score on validate -> S4 (one LOGGED look per group)
  freeze  : fit on dev, shrink, write frozen coefficients
  power   : S5 from exam X (rows + forecasts; no y)

--fake-y (plumbing test only): y := Poisson(centre), never a look at outcomes.
"""
from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import json
import math
import pickle
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

REPO = Path("/Users/mkoziol/projects/bet")
sys.path[:0] = [str(REPO / "src"), str(REPO)]
from bet.sofa import epochs  # noqa: E402
from bet.sofa.schedule_features import FOOTBALL_COLUMNS  # noqa: E402

D = REPO / "data/refit_2026-11-08_schedule"
LOOKS = D / "looks.md"
EXPLORE_END = int(dt.datetime(2025, 9, 1, tzinfo=dt.UTC).timestamp())
COUNT_FROM = int(dt.datetime(2025, 1, 1, tzinfo=dt.UTC).timestamp())
GOALS_FROM = int(dt.datetime(2024, 7, 1, tzinfo=dt.UTC).timestamp())
TAU = 0.05
# R5_season_start: season_early rows take no layoff term (pre-registration 5)
COLS = [c for c in FOOTBALL_COLUMNS if c != "R5_season_start"]
GROUPS = {
    "goals": ["goals_for", "goals_1h_for", "goals_2h_for"],
    "corners": ["corners_for", "corners_1h_for", "corners_2h_for"],
    "shots_sot": ["shots_for", "shots_1h_for", "shots_2h_for", "shots_on_target_for",
                  "shots_on_target_1h_for", "shots_on_target_2h_for"],
    "cards_fouls": ["cards_points_for", "fouls_for", "fouls_1h_for", "fouls_2h_for"],
    "offsides": ["offsides_for", "offsides_1h_for", "offsides_2h_for"],
}
METRIC_GROUP = {m: g for g, ms in GROUPS.items() for m in ms}
ATTACK = {"goals", "corners", "shots_sot"}
OWN_DOWN = ["R1", "R2", "cont_prev4", "et_prev", "dense14"]
OWN_DOWN_LAYOFF = ["R5_winter", "R5_other"]  # goals / corners only
FAMS = epochs.FOOTBALL_FORM_TABLE_FAMILIES


def total_of(metric: str) -> str:
    return metric[: -len("_for")] + "_total"


def book_for(market: str) -> int:
    return 2 if f"{market}|OVER" in FAMS else 1


_D10: dict = {}


def d10_centre(market: str, eid: int, final: float, phase_mult: float) -> float:
    """D10: the season phase refitted on dev (season_phase_dev.json) replaces the
    installed one - the phase is the chain's last, purely multiplicative step."""
    if not _D10:
        _D10["c"] = {m: v["coefficients"] for m, v in json.loads(
            (D / "season_phase_dev.json").read_text())["markets"].items()}
        _D10["lab"] = pickle.loads((D / "phase_labels.pkl").read_bytes())
    cm = _D10["c"].get(market)
    if cm is None:
        return final
    lab = _D10["lab"].get(eid)
    c = cm.get(lab, 0.0) if lab not in (None, "mid") else 0.0
    return final / phase_mult * math.exp(c)


def read_chunks(tier: str, kind: str):  # type: ignore[no-untyped-def]
    d = D / "full" / tier / kind
    for p in sorted(d.glob("*.pkl.gz")):
        yield from pickle.load(gzip.open(p))


def load(fake_y: bool = False, src: str = "full") -> None:
    feats = pickle.loads((D / "football_features.pkl").read_bytes())
    women = _women()
    want = set(METRIC_GROUP) | {total_of(m) for m in METRIC_GROUP}
    ys = {}
    if not fake_y:
        for e, m, s, b, a in read_chunks("dev", "y"):
            if m in want:
                ys[(e, m, s, b)] = a
    rng = np.random.default_rng(0)
    out = []
    for r in read_chunks("dev", "rows") if src == "full" else _smoke_rows():
        (eid, ts, comp, sport, market, subject, book, n, mean, var, shrunk, final,
         phase, disp, emp, rp, sample, home, away, nrows) = r
        if sport != "football" or market not in want or book != book_for(market):
            continue
        f = feats.get(eid)
        if f is None or f["national"]:
            continue
        floor = COUNT_FROM if not market.startswith("goals") else GOALS_FROM
        if ts < floor:
            continue
        y = (float(rng.poisson(final)) if fake_y else ys.get((eid, market, subject, book)))
        if y is None:
            continue
        side = None
        if market.endswith("_for"):
            side = "home" if int(subject) == home else "away" if int(subject) == away else None
            if side is None:
                continue
        out.append({"eid": eid, "ts": ts, "comp": comp, "market": market, "side": side,
                    "y": y, "centre": d10_centre(market, eid, final, phase), "alpha": disp[0] if disp else 0.0,
                    "home": home, "away": away, "season": f["season"],
                    "women": comp in women})
    pickle.dump({"rows": out, "fake": fake_y}, open(D / "fb_dev.pkl", "wb"))
    print("rows", len(out), "fake" if fake_y else "")


def _smoke_rows():  # type: ignore[no-untyped-def]
    for p in sorted((D / "smoke/dev/rows").glob("*.pkl.gz")):
        yield from pickle.load(gzip.open(p))


def _women() -> frozenset[int]:
    from bet.sofa.confidence import WOMEN_COMPETITION_IDS
    return frozenset(WOMEN_COMPETITION_IDS)


def design(rows: list[dict], feats: dict) -> tuple[np.ndarray, list[str]]:
    names = [f"own_{c}" for c in COLS] + [f"opp_{c}" for c in COLS]
    x = np.zeros((len(rows), len(names)))
    for i, r in enumerate(rows):
        f = feats[r["eid"]]
        own, opp = (f["home"], f["away"]) if r["side"] == "home" else (f["away"], f["home"])
        if not (own.coverage and opp.coverage):
            continue  # x1: dropped by the caller via cov mask
        io, ip = own.indicators(), opp.indicators()
        x[i] = [io[c] for c in COLS] + [ip[c] for c in COLS]
    return x, names


def coverage(rows: list[dict], feats: dict) -> np.ndarray:
    return np.array([feats[r["eid"]]["home"].coverage and feats[r["eid"]]["away"].coverage
                     for r in rows])


def fe_keys(rows: list[dict]) -> np.ndarray:
    keys = {}
    out = np.empty(len(rows), dtype=np.int64)
    for i, r in enumerate(rows):
        team = r["home"] if r["side"] == "home" else r["away"]
        out[i] = keys.setdefault((team, r["season"]), len(keys))
    return out


def fit_poisson(y: np.ndarray, off: np.ndarray, x: np.ndarray, g: np.ndarray,
                fe: np.ndarray | None = None, iters: int = 25) -> tuple[np.ndarray, np.ndarray]:
    """Poisson with offset and group FE (alternating). fe given -> held fixed."""
    k = x.shape[1]
    b = np.zeros(k)
    fixed = fe is not None
    a = fe.copy() if fe is not None else np.zeros(g.max() + 1)
    for _ in range(iters):
        if not fixed:
            mu0 = np.exp(off + x @ b)
            a = np.log((np.bincount(g, y, len(a)) + 0.5) / (np.bincount(g, mu0, len(a)) + 0.5))
        if k == 0:
            break
        eta = off + a[g] + x @ b
        mu = np.exp(eta)
        grad = x.T @ (y - mu)
        h = x.T @ (x * mu[:, None]) + 1e-6 * np.eye(k)
        step = np.linalg.solve(h, grad)
        b += step
        if np.max(np.abs(step)) < 1e-8:
            break
    return b, a


def cluster_se(y: np.ndarray, off: np.ndarray, x: np.ndarray, g: np.ndarray,
               a: np.ndarray, b: np.ndarray, cl: np.ndarray) -> np.ndarray:
    mu = np.exp(off + a[g] + x @ b)
    h = x.T @ (x * mu[:, None]) + 1e-6 * np.eye(x.shape[1])
    s = x * (y - mu)[:, None]
    sc = np.zeros((cl.max() + 1, x.shape[1]))
    np.add.at(sc, cl, s)
    meat = sc.T @ sc
    hi = np.linalg.inv(h)
    return np.sqrt(np.clip(np.diag(hi @ meat @ hi), 0, None))


def deviance_gain(y, off, x, g, fe):  # type: ignore[no-untyped-def]
    b, _ = fit_poisson(y, off, x, g, fe=fe)
    mu0 = np.exp(off + fe[g])
    mu1 = np.exp(off + fe[g] + x @ b)
    return float((y * np.log(mu1 / mu0) - (mu1 - mu0)).sum()), b


def team_cluster(rows: list[dict]) -> np.ndarray:
    keys = {}
    return np.array([keys.setdefault(r["home"] if r["side"] == "home" else r["away"], len(keys))
                     for r in rows])


def metric_rows(rows, metric, lo, hi, feats):  # type: ignore[no-untyped-def]
    rs = [r for r in rows if r["market"] == metric and lo <= r["ts"] < hi and r["side"]]
    cov = coverage(rs, feats)
    return [r for r, c in zip(rs, cov, strict=True) if c]


def fit_metric(rs, feats):  # type: ignore[no-untyped-def]
    y = np.array([r["y"] for r in rs])
    off = np.log(np.array([r["centre"] for r in rs]))
    x, names = design(rs, feats)
    g = fe_keys(rs)
    b, a = fit_poisson(y, off, x, g)
    se = cluster_se(y, off, x, g, a, b, team_cluster(rs))
    return b, se, names, (y, off, x, g, a)


def explore() -> None:
    data = pickle.load(open(D / "fb_dev.pkl", "rb"))
    rows = data["rows"]
    feats = pickle.loads((D / "football_features.pkl").read_bytes())
    res = {}
    rng = np.random.default_rng(13)
    only = sys.argv[2].split(",") if len(sys.argv) > 2 else list(GROUPS)
    for group, metrics in GROUPS.items():
        if group not in only:
            continue
        gain_real = 0.0
        null = np.zeros(200)
        coefs = {}
        for m in metrics:
            rs = metric_rows(rows, m, 0, EXPLORE_END, feats)
            if len(rs) < 2000:
                print(group, m, "rows", len(rs), "skipped (< 2000)")
                continue
            b, se, names, (y, off, x, g, a) = fit_metric(rs, feats)
            _, fe0 = fit_poisson(y, off, np.zeros((len(y), 0)), g)
            gr, _ = deviance_gain(y, off, x, g, fe0)
            gain_real += gr
            coefs[m] = {n: [float(v), float(s)] for n, v, s in zip(names, b, se, strict=True)}
            # S1: permute the feature rows within team-season (FE fixed at the null fit)
            order = np.argsort(g, kind="stable")
            bounds = np.flatnonzero(np.diff(g[order])) + 1
            blocks = np.split(order, bounds)
            for k in range(200):
                perm = np.empty(len(y), dtype=np.int64)
                for blk in blocks:
                    perm[blk] = rng.permutation(blk)
                null[k] += deviance_gain(y, off, x[perm], g, fe0)[0]
            print(group, m, "rows", len(rs), "gain", round(gr, 1), flush=True)
        if not coefs:
            continue
        p_s1 = (1 + int((null >= gain_real).sum())) / 201
        # S3: registered directions (attack groups), pooled by inverse variance
        s3 = {}
        if group in ATTACK:
            for c in OWN_DOWN + (OWN_DOWN_LAYOFF if group in ("goals", "corners") else []):
                vals = [(v[0], v[1]) for cf in coefs.values() for n, v in cf.items()
                        if n == f"own_{c}" and v[1] > 0]
                if vals:
                    w = np.array([1 / s ** 2 for _, s in vals])
                    est = float(np.dot(w, [v for v, _ in vals]) / w.sum())
                    s3[c] = [est, est <= 0]
        res[group] = {"gain": gain_real, "S1_p": p_s1, "S3": s3, "coefs": coefs}
        print(group, "S1 p", round(p_s1, 4), "S3", {k: (round(v[0], 4), v[1]) for k, v in s3.items()})
    res.update(s2(rows, feats))
    (D / ("fb_explore.json" if len(only) == len(GROUPS) else f"fb_explore_{'_'.join(only)}.json")).write_text(json.dumps(res, indent=1))


def s2(rows, feats):  # type: ignore[no-untyped-def]
    """Lagged control (own R1 of the side's previous match) and the
    mechanism-free outcome (the opponent's offsides vs own R1), on explore."""
    prev = {}
    by_team = defaultdict(list)
    for eid, f in feats.items():
        by_team[f["home_id"]].append((f["ts"], eid, "home"))
        by_team[f["away_id"]].append((f["ts"], eid, "away"))
    for lst in by_team.values():
        lst.sort()
        for (_, e0, s0), (_, e1, s1) in zip(lst, lst[1:], strict=False):
            prev[(e1, s1)] = feats[e0][s0]
    out = {}
    for m in ("goals_for", "corners_for", "shots_for"):
        rs = metric_rows(rows, m, 0, EXPLORE_END, feats)
        rs = [r for r in rs if (r["eid"], r["side"]) in prev]
        if len(rs) < 2000:
            continue
        y = np.array([r["y"] for r in rs])
        off = np.log(np.array([r["centre"] for r in rs]))
        x, names = design(rs, feats)
        lag = np.array([[int(prev[(r["eid"], r["side"])].rest_bucket == "R1")] for r in rs])
        g = fe_keys(rs)
        b, a = fit_poisson(y, off, np.hstack([x, lag]), g)
        out[f"S2_lag_{m}"] = [float(b[names.index("own_R1")]), float(b[-1])]
    rs = metric_rows(rows, "offsides_for", 0, EXPLORE_END, feats)
    if len(rs) >= 2000:
        b, se, names, _ = fit_metric(rs, feats)
        i = names.index("opp_R1")
        out["S2_mechfree_opp_R1_offsides"] = [float(b[i]), float(se[i])]
    print({k: [round(v, 4) for v in vv] for k, vv in out.items()})
    return out


def nb_logscore(y: np.ndarray, mu: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    """-log NB pmf (Poisson where alpha == 0)."""
    gammaln = np.vectorize(math.lgamma, otypes=[float])
    out = np.empty(len(y))
    pois = alpha <= 1e-9
    yp, mp = y[pois], mu[pois]
    out[pois] = -(yp * np.log(mp) - mp - gammaln(yp + 1))
    yn, mn, an = y[~pois], mu[~pois], alpha[~pois]
    r = 1 / an
    out[~pois] = -(gammaln(yn + r) - gammaln(r) - gammaln(yn + 1)
                   + r * np.log(r / (r + mn)) + yn * np.log(mn / (r + mn)))
    return out


def shrunk(coefs: dict) -> dict:
    return {m: {n: v * TAU ** 2 / (TAU ** 2 + s ** 2) for n, (v, s) in cf.items()}
            for m, cf in coefs.items()}


def side_terms(rows, feats, frozen):  # type: ignore[no-untyped-def]
    """t per (eid, metric, side) for _for rows with coverage."""
    t = {}
    for r in rows:
        if r["side"] is None or r["market"] not in frozen:
            continue
        f = feats[r["eid"]]
        own, opp = (f["home"], f["away"]) if r["side"] == "home" else (f["away"], f["home"])
        if not (own.coverage and opp.coverage):
            continue
        io, ip = own.indicators(), opp.indicators()
        cf = frozen[r["market"]]
        t[(r["eid"], r["market"], r["side"])] = (
            sum(cf.get(f"own_{c}", 0.0) * io[c] for c in COLS)
            + sum(cf.get(f"opp_{c}", 0.0) * ip[c] for c in COLS), r["centre"])
    return t


def group_delta(rows, feats, frozen, group, lo, hi):  # type: ignore[no-untyped-def]
    """Per match summed NB log score treat - base over the group's _for and
    _total rows (pre-registration 8; doprecyzowanie 3)."""
    metrics = [m for m in GROUPS[group] if m in frozen]
    sel = [r for r in rows if lo <= r["ts"] < hi
           and (r["market"] in metrics or r["market"] in {total_of(m) for m in metrics})]
    t = side_terms(sel, feats, frozen)
    mu_t = []
    for r in sel:
        if r["side"] is not None:
            tt = t.get((r["eid"], r["market"], r["side"]))
            mu_t.append(r["centre"] * math.exp(tt[0]) if tt else r["centre"])
        else:
            m = r["market"][: -len("_total")] + "_for"
            h, a = t.get((r["eid"], m, "home")), t.get((r["eid"], m, "away"))
            if h and a:
                ratio = (h[1] * math.exp(h[0]) + a[1] * math.exp(a[0])) / (h[1] + a[1])
                mu_t.append(r["centre"] * ratio)
            else:
                mu_t.append(r["centre"])
    y = np.array([r["y"] for r in sel])
    mb = np.array([r["centre"] for r in sel])
    al = np.array([r["alpha"] for r in sel])
    d = nb_logscore(y, np.array(mu_t), al) - nb_logscore(y, mb, al)
    per = defaultdict(float)
    meta = {}
    for r, v in zip(sel, d, strict=True):
        per[r["eid"]] += v
        meta[r["eid"]] = (r["home"], r["away"])
    eids = list(per)
    return np.array([per[e] for e in eids]), [meta[e] for e in eids], len(sel)


def boot2(diff: np.ndarray, pairs: list, reps: int = 2000, seed: int = 5) -> np.ndarray:
    if len(diff) == 0:
        return np.full(reps, np.nan)
    rng = np.random.default_rng(seed)
    hs = {h for h, _ in pairs}
    as_ = {a for _, a in pairs}
    hi = {h: i for i, h in enumerate(sorted(hs))}
    ai = {a: i for i, a in enumerate(sorted(as_))}
    h = np.array([hi[x] for x, _ in pairs])
    a = np.array([ai[x] for _, x in pairs])
    out = np.empty(reps)
    for k in range(reps):
        wh = rng.multinomial(len(hi), np.full(len(hi), 1 / len(hi)))
        wa = rng.multinomial(len(ai), np.full(len(ai), 1 / len(ai)))
        w = wh[h] * wa[a]
        out[k] = (w * diff).sum() / max(w.sum(), 1)
    return out


def fit_frozen(rows, feats, lo, hi, drop):  # type: ignore[no-untyped-def]
    out = {}
    for group, metrics in GROUPS.items():
        for m in metrics:
            rs = metric_rows(rows, m, lo, hi, feats)
            if len(rs) < 2000:
                continue
            b, se, names, _ = fit_metric(rs, feats)
            cf = {n: (float(v), float(s)) for n, v, s in zip(names, b, se, strict=True)}
            for n in drop.get(group, []):
                cf.pop(n, None)
            out[m] = cf
    return shrunk(out)


def validate(groups: list[str], drop_json: str) -> None:
    data = pickle.load(open(D / "fb_dev.pkl", "rb"))
    assert not data["fake"] or "--fake-y" in sys.argv
    rows = data["rows"]
    feats = pickle.loads((D / "football_features.pkl").read_bytes())
    drop = json.loads(drop_json)
    frozen = fit_frozen(rows, feats, 0, EXPLORE_END, drop)
    end = int(dt.datetime(2026, 1, 1, tzinfo=dt.UTC).timestamp())
    spec = hashlib.sha256(json.dumps({"COLS": COLS, "drop": drop, "tau": TAU}).encode()).hexdigest()[:12]
    for group in groups:
        diff, pairs, nrows = group_delta(rows, feats, frozen, group, EXPLORE_END, end)
        bt = boot2(diff, pairs)
        line = (f"| {dt.datetime.now(dt.UTC):%Y-%m-%d %H:%MZ} | {group} | validate"
                f"{' FAKE' if data['fake'] else ''} | spec {spec} | matches {len(diff)} rows {nrows} | "
                f"Delta {diff.mean():+.6f} [{np.quantile(bt, .025):+.6f}, {np.quantile(bt, .975):+.6f}] | "
                f"S4 {'pass' if diff.mean() < 0 else 'fail'} |\n")
        if not data["fake"]:
            with LOOKS.open("a") as f:
                f.write(line)
        print(line, end="")


def freeze(drop_json: str) -> None:
    rows = pickle.load(open(D / "fb_dev.pkl", "rb"))["rows"]
    feats = pickle.loads((D / "football_features.pkl").read_bytes())
    end = int(dt.datetime(2026, 1, 1, tzinfo=dt.UTC).timestamp())
    frozen = fit_frozen(rows, feats, 0, end, json.loads(drop_json))
    (D / "fb_frozen.json").write_text(json.dumps({"tau": TAU, "cols": COLS, "coef": frozen}, indent=1))
    print("frozen metrics", list(frozen))


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "load":
        load(fake_y="--fake-y" in sys.argv, src="smoke" if "--smoke" in sys.argv else "full")
    elif cmd == "explore":
        explore()
    elif cmd == "validate":
        validate(sys.argv[2].split(","), sys.argv[3])
    elif cmd == "freeze":
        freeze(sys.argv[2])
