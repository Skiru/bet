"""tennis_serve group - dev stages (pre-registration 5 / 6 / 7 / 8; STAN 1-12).

usage:
  serve_analysis.py explore                 unlimited looks (explore rows only)
  serve_analysis.py validate [--fake-y] [--limit N] [--workers W]
                                            LOGGED look (<= 3) unless --fake-y
  serve_analysis.py freeze                  fit on explore + validate -> tennis/serve_frozen.json
  serve_analysis.py power                   S5 from tennis/serve_exam_X.pkl (no outcome)

Model (pre-registration 5 / 6, "serwis: delta per cecha z logitu punktów
serwisowych z offsetem logit(p modelu) na eksploracji"): one row per
(match, server) with Sofascore serve counts; y = serve points won of n played,
binomial logit with offset = the point model's serve logit as of the start
(MatchForecast.<side>.serve_logit) and the server's OWN schedule columns
(the pre-registration names no returner term for tennis; a returner-augmented
fit is printed as an exploratory sensitivity only). An intercept is fitted as
a nuisance and never applied: the treatment arm moves the server's serve logit
by delta = sum(beta_shr * (x - mean_fit(x))) - the columns centred on the fit
rows, so the arm changes the schedule contrast only and leaves the installed
model's overall level as installed (M10). A player without calendar coverage
gets delta 0 (x1, pre-registration 4).
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import hashlib
import json
import math
import pickle
import sys
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np

REPO = Path("/Users/mkoziol/projects/bet")
D = REPO / "data/refit_2026-11-08_schedule"
sys.path[:0] = [str(REPO / "src"), str(REPO), str(D)]
import tw_analysis as twa  # noqa: E402
from bet.sofa import tennis_point_sheet as tps  # noqa: E402
from bet.sofa.epochs import (  # noqa: E402
    TENNIS_HANDICAP_POINT_MODEL_MARKETS,
    TENNIS_POINT_MODEL_MARKETS,
)
from bet.sofa.tennis_handicap_point import p_handicap  # noqa: E402
from bet.sofa.tennis_point_model import FORM_VAR, MatchForecast, market_sim  # noqa: E402
from scripts.sofa.fit_tennis_point_curves import _lines, actual  # noqa: E402
from scripts.sofa.measure_tennis_handicap_point_model import (  # noqa: E402
    _ladder,
    actual_margin,
)

T = D / "tennis"
LOOKS = D / "looks.md"
EXPLORE_FROM = int(dt.datetime(2025, 5, 1, tzinfo=dt.UTC).timestamp())
EXPLORE_END = int(dt.datetime(2025, 9, 1, tzinfo=dt.UTC).timestamp())
DEV_CUT = int(dt.datetime(2026, 1, 1, tzinfo=dt.UTC).timestamp())
TAU = 0.05
C_MAT = 0.03
COLS = ["games78", "games7d_prev", "rounds_cur", "layoff21", "ret14",
        "surface_switch", "dom_prev", "qual"]
DIRECTION = {"games78": -1, "games7d_prev": -1, "layoff21": -1, "ret14": -1}
SCORED = sorted(TENNIS_POINT_MODEL_MARKETS) + sorted(TENNIS_HANDICAP_POINT_MODEL_MARKETS)
PERM_REPS = 200


# --------------------------------------------------------------------------
# data
# --------------------------------------------------------------------------

def load_dev() -> list[dict]:
    return pickle.loads((T / "serve_dev.pkl").read_bytes())


def scoreable(r: dict) -> bool:
    """Dev match the outcome reader may grade: completed (a retirement is a
    refund - out of scoring, as SETTLE), >= 2 sets."""
    pm = r["pm"]
    return bool(pm.completed and len(pm.sets) >= 2)


def player_rows(recs: list[dict], lo: int, hi: int) -> list[dict]:
    """(match, server) rows with serve counts and server calendar coverage."""
    out = []
    for i, r in enumerate(recs):
        if not (lo <= r["ts"] < hi) or not scoreable(r):
            continue
        pm = r["pm"]
        for side, opp in (("home", "away"), ("away", "home")):
            st = pm.home if side == "home" else pm.away
            if st is None or st.played <= 0:
                continue
            f = r["feats"][side]
            if f["coverage"] != 1.0:
                continue
            fc = r["forecast"].home if side == "home" else r["forecast"].away
            pid = r["home_id"] if side == "home" else r["away_id"]
            out.append({
                "rec": i, "eid": r["event_id"], "ts": r["ts"], "side": side,
                "pid": pid, "year": dt.datetime.fromtimestamp(r["ts"], dt.UTC).year,
                "y": float(st.won), "n": float(st.played), "off": fc.serve_logit,
                "x": {c: f[c] for c in COLS},
                "xo": {c: r["feats"][opp][c] for c in COLS},
                "opp_cov": r["feats"][opp]["coverage"],
                "tier": r["tier"],
            })
    return out


def mat(rows: list[dict], cols: list[str], key: str = "x") -> np.ndarray:
    return np.array([[r[key][c] for c in cols] for r in rows], dtype=float)


# --------------------------------------------------------------------------
# binomial GLM with offset
# --------------------------------------------------------------------------

def fit_binom(y: np.ndarray, n: np.ndarray, off: np.ndarray, x: np.ndarray,
              iters: int = 50) -> tuple[np.ndarray, float]:
    """Intercept + x, offset off. Returns (b incl. intercept, loglik)."""
    xa = np.column_stack([np.ones(len(y)), x]) if x.size else np.ones((len(y), 1))
    b = np.zeros(xa.shape[1])
    b[0] = math.log(max(y.sum(), 1) / max(n.sum() - y.sum(), 1)) - float(np.mean(off))
    for _ in range(iters):
        eta = off + xa @ b
        p = 1 / (1 + np.exp(-eta))
        w = n * p * (1 - p)
        h = xa.T @ (xa * w[:, None]) + 1e-9 * np.eye(len(b))
        step = np.linalg.solve(h, xa.T @ (y - n * p))
        b += step
        if np.max(np.abs(step)) < 1e-11:
            break
    return b, loglik(y, n, off + xa @ b)


def loglik(y: np.ndarray, n: np.ndarray, eta: np.ndarray) -> float:
    return float((y * eta - n * np.logaddexp(0, eta)).sum())


def cluster_se(y: np.ndarray, n: np.ndarray, off: np.ndarray, x: np.ndarray,
               b: np.ndarray, cl: np.ndarray) -> np.ndarray:
    """Sandwich SE clustered by player (incl. intercept)."""
    xa = np.column_stack([np.ones(len(y)), x])
    p = 1 / (1 + np.exp(-(off + xa @ b)))
    h = xa.T @ (xa * (n * p * (1 - p))[:, None])
    s = xa * (y - n * p)[:, None]
    sc = np.zeros((cl.max() + 1, xa.shape[1]))
    np.add.at(sc, cl, s)
    hi = np.linalg.inv(h)
    return np.sqrt(np.clip(np.diag(hi @ (sc.T @ sc) @ hi), 0, None))


def arrays(rows: list[dict]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    y = np.array([r["y"] for r in rows])
    n = np.array([r["n"] for r in rows])
    off = np.array([r["off"] for r in rows])
    keys: dict[int, int] = {}
    cl = np.array([keys.setdefault(r["pid"], len(keys)) for r in rows])
    return y, n, off, cl


def gain(y: np.ndarray, n: np.ndarray, off: np.ndarray, x: np.ndarray) -> float:
    """In-sample deviance gain of the columns over offset + intercept."""
    _, l0 = fit_binom(y, n, off, np.empty((len(y), 0)))
    _, l1 = fit_binom(y, n, off, x)
    return 2 * (l1 - l0)


def coef_table(rows: list[dict], cols: list[str]) -> dict[str, Any]:
    y, n, off, cl = arrays(rows)
    x = mat(rows, cols)
    b, ll = fit_binom(y, n, off, x)
    se = cluster_se(y, n, off, x, b, cl)
    return {
        "intercept": [float(b[0]), float(se[0])],
        "coef": {c: [float(b[1 + k]), float(se[1 + k])] for k, c in enumerate(cols)},
        "shrunk": {c: float(b[1 + k] * TAU ** 2 / (TAU ** 2 + se[1 + k] ** 2))
                   for k, c in enumerate(cols)},
        "means": {c: float(x[:, k].mean()) for k, c in enumerate(cols)},
        "loglik": ll, "rows": len(rows), "players": int(cl.max() + 1),
    }


def permute_s1(rows: list[dict], cols: list[str], reps: int = PERM_REPS,
               seed: int = 11) -> tuple[float, float, list[float]]:
    y, n, off, _ = arrays(rows)
    x = mat(rows, cols)
    obs = gain(y, n, off, x)
    slots: dict[tuple[int, int], list[int]] = defaultdict(list)
    for i, r in enumerate(rows):
        slots[(r["pid"], r["year"])].append(i)
    groups = [np.array(v) for v in slots.values() if len(v) > 1]
    rng = np.random.default_rng(seed)
    null = []
    for _ in range(reps):
        xp = x.copy()
        for g in groups:
            xp[g] = x[rng.permutation(g)]
        null.append(gain(y, n, off, xp))
    p = (1 + sum(v >= obs for v in null)) / (1 + reps)
    return obs, p, null


def lag_games78(recs: list[dict]) -> dict[tuple[int, str], float]:
    """(rec index, side) -> the player's games78 at his previous rated match
    (previous row of the built table, any period, with coverage)."""
    last: dict[int, float] = {}
    out: dict[tuple[int, str], float] = {}
    order = sorted(range(len(recs)), key=lambda i: (recs[i]["ts"], recs[i]["event_id"]))
    k = 0
    while k < len(order):
        j = k
        while j < len(order) and recs[order[j]]["ts"] == recs[order[k]]["ts"]:
            j += 1
        for i in order[k:j]:
            r = recs[i]
            for side, pid in (("home", r["home_id"]), ("away", r["away_id"])):
                if pid in last:
                    out[(i, side)] = last[pid]
        for i in order[k:j]:
            r = recs[i]
            for side, pid in (("home", r["home_id"]), ("away", r["away_id"])):
                f = r["feats"][side]
                if f["coverage"] == 1.0:
                    last[pid] = f["games78"]
        k = j
    return out


# --------------------------------------------------------------------------
# explore
# --------------------------------------------------------------------------

def explore() -> None:
    t0 = time.time()
    recs = load_dev()
    rows = player_rows(recs, EXPLORE_FROM, EXPLORE_END)
    print(f"explore matches(dev table, window) "
          f"{sum(1 for r in recs if EXPLORE_FROM <= r['ts'] < EXPLORE_END)}; "
          f"player rows (serve counts, completed, coverage) {len(rows)}", flush=True)
    full = coef_table(rows, COLS)
    print("FULL spec coefficients (beta, cluster SE by player) / shrunk:")
    for c in COLS:
        b, s = full["coef"][c]
        print(f"  {c:15s} {b:+.5f} (SE {s:.5f})  shr {full['shrunk'][c]:+.5f}")
    print(f"  intercept {full['intercept'][0]:+.5f} (SE {full['intercept'][1]:.5f})")
    s3 = {c: {"beta": full["coef"][c][0], "direction": d,
              "match": bool(np.sign(full["coef"][c][0]) == d)}
          for c, d in DIRECTION.items()}
    drop = [c for c, v in s3.items() if not v["match"]]
    kept = [c for c in COLS if c not in drop]
    print("S3 (registered direction -1 = serve point p down):",
          {c: (round(v["beta"], 5), v["match"]) for c, v in s3.items()})
    print("M4 removed:", drop, "kept:", kept)
    red = coef_table(rows, kept)
    print("KEPT spec coefficients (beta, cluster SE) / shrunk:")
    for c in kept:
        b, s = red["coef"][c]
        print(f"  {c:15s} {b:+.5f} (SE {s:.5f})  shr {red['shrunk'][c]:+.5f}")
    s3_kept = {c: bool(np.sign(red["coef"][c][0]) == d)
               for c, d in DIRECTION.items() if c in kept}
    print("S3 on kept spec:", s3_kept)
    # S1
    obs_k, p_k, null_k = permute_s1(rows, kept)
    print(f"S1 kept spec: deviance gain {obs_k:.2f}, null mean {np.mean(null_k):.2f}, "
          f"null max {np.max(null_k):.2f}, p {p_k:.4f}", flush=True)
    obs_f, p_f, null_f = permute_s1(rows, COLS)
    print(f"S1 full spec: deviance gain {obs_f:.2f}, null mean {np.mean(null_f):.2f}, "
          f"null max {np.max(null_f):.2f}, p {p_f:.4f}", flush=True)
    # S2
    lag = lag_games78(recs)
    lrows = []
    for r in rows:
        v = lag.get((r["rec"], r["side"]))
        if v is not None:
            lrows.append({**r, "x": {**r["x"], "lag_games78": v}})
    s2: dict[str, Any] = {"rows": len(lrows)}
    if "games78" in kept:
        lt = coef_table(lrows, kept + ["lag_games78"])
        cur, lagb = lt["coef"]["games78"][0], lt["coef"]["lag_games78"][0]
        s2 |= {"beta_games78": cur, "se_games78": lt["coef"]["games78"][1],
               "beta_lag": lagb, "se_lag": lt["coef"]["lag_games78"][1],
               "pass": bool(abs(lagb) < 0.5 * abs(cur))}
        print(f"S2 rows {len(lrows)}: beta games78 {cur:+.5f} (SE {s2['se_games78']:.5f}), "
              f"lag {lagb:+.5f} (SE {s2['se_lag']:.5f}); |lag| < 0.5|beta|: {s2['pass']}")
    else:
        s2["pass"] = None
        print("S2: games78 removed by M4 - the registered lag control is undefined")
    print("S2 mechanism-free outcome: n/a for tennis (pre-registration 6)")
    # sensitivity (exploratory only, never the variant): the returner's columns
    both = [r for r in rows if r["opp_cov"] == 1.0]
    # qual is a property of the match (identical for both players): no opp_ column
    ocols = [f"opp_{c}" for c in kept if c != "qual"]
    sx = [{**r, "x": {**r["x"], **{f"opp_{c}": r["xo"][c] for c in kept}}} for r in both]
    sens = coef_table(sx, kept + ocols)
    print("SENSITIVITY (exploratory, not the variant) - own + returner columns, rows",
          len(sx))
    for c in kept + ocols:
        b, s = sens["coef"][c]
        print(f"  {c:20s} {b:+.5f} (SE {s:.5f})")
    gates = {"S1": bool(p_k < 0.05), "S2": s2["pass"],
             "S3": all(s3_kept.values()) if s3_kept else None}
    print("GATES (explore):", gates)
    res = {
        "rows": len(rows), "cols": COLS, "direction": DIRECTION, "tau": TAU,
        "full": full, "S3_full": s3, "M4_removed": drop, "kept": kept, "kept_fit": red,
        "S3_kept": s3_kept,
        "S1": {"kept": {"gain": obs_k, "p": p_k, "null_mean": float(np.mean(null_k))},
               "full": {"gain": obs_f, "p": p_f, "null_mean": float(np.mean(null_f))},
               "reps": PERM_REPS, "within": "(player, calendar year)"},
        "S2": s2, "S2_mechanism_free": "n/a (tennis, pre-registration 6)",
        "sensitivity_returner": sens, "gates": gates,
        "secs": round(time.time() - t0),
    }
    (D / "serve_explore.json").write_text(json.dumps(res, indent=1))
    print("wrote serve_explore.json, secs", res["secs"])


# --------------------------------------------------------------------------
# arms + scoring
# --------------------------------------------------------------------------

def deltas(r: dict, fit: dict[str, Any], kept: list[str]) -> tuple[float, float]:
    out = []
    for side in ("home", "away"):
        f = r["feats"][side]
        if f["coverage"] != 1.0:
            out.append(0.0)
            continue
        out.append(sum(fit["shrunk"][c] * (f[c] - fit["means"][c]) for c in kept))
    return out[0], out[1]


def treat_forecast(fc: MatchForecast, dh: float, da: float) -> MatchForecast:
    return dataclasses.replace(
        fc,
        home=dataclasses.replace(fc.home, serve_logit=fc.home.serve_logit + dh),
        away=dataclasses.replace(fc.away, serve_logit=fc.away.serve_logit + da))


_JOBS: list[tuple[dict, float, float]] = []
_FAKE = False


def _ll(p: float, y: int) -> float:
    p = min(max(p, 1e-6), 1 - 1e-6)
    return -math.log(p) if y else -math.log(1 - p)


def score_job(k: int) -> dict[str, Any]:
    """Both arms of one match with the event-id seed; lines from the BASE
    arm (fit_tennis_point_curves._lines: half lines whose base OVER p is in
    [0.10, 0.90]; handicap: measure_tennis_handicap_point_model._ladder),
    OVER side only (UNDER = 1 - p, the same log loss)."""
    r, dh, da = _JOBS[k]
    pm = r["pm"]
    eid = r["event_id"]
    fb = r["forecast"]
    ft = treat_forecast(fb, dh, da)
    pricer = tps.PointPricer({eid: fb})
    ms_b = pricer.market_sim(eid)
    ms_t = market_sim(ft, n=tps.SIMS, seed=tps.seed_of(eid))
    rng = np.random.default_rng(eid % (2 ** 31) + 99)
    sb = st = 0.0
    nl = 0
    per: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0, 0])
    for market in SCORED:
        hcp = market in TENNIS_HANDICAP_POINT_MODEL_MARKETS
        sides = (0, 1) if (hcp or market.endswith("_for")) else (None,)
        for side in sides:
            if hcp:
                value = actual_margin(pm, market, side)
                lines = _ladder(ms_b, market, side)
            else:
                value = actual(pm, market, side)
                lines = _lines(pricer, eid, market, side) if value is not None else []
            if value is None:
                continue
            for line, p_b in lines:
                p_t = (p_handicap(ms_t, market, side, line) if hcp
                       else ms_t.p_over(market, side, line))
                if p_t is None:
                    continue
                if _FAKE:
                    y = int(rng.random() < p_b)
                else:
                    y = int(value + line > 0) if hcp else int(value > line)
                lb, lt = _ll(p_b, y), _ll(p_t, y)
                sb += lb
                st += lt
                nl += 1
                fam = market
                per[fam][0] += lb
                per[fam][1] += lt
                per[fam][2] += 1
    return {"k": k, "lines": nl, "sb": sb, "st": st, "per": dict(per),
            "dh": dh, "da": da}


def run_scoring(jobs: list[tuple[dict, float, float]], workers: int,
                fake: bool) -> list[dict]:
    global _JOBS, _FAKE
    _JOBS, _FAKE = jobs, fake
    import multiprocessing as mp
    ctx = mp.get_context("fork")
    out = []
    with ProcessPoolExecutor(max_workers=workers, mp_context=ctx) as pool:
        for i, res in enumerate(pool.map(score_job, range(len(jobs)), chunksize=32)):
            out.append(res)
            if (i + 1) % 2000 == 0:
                print(f"  scored {i + 1}/{len(jobs)}", flush=True)
    return out


def spec_sha(kept: list[str]) -> str:
    return hashlib.sha256(json.dumps({
        "group": "tennis_serve", "kept": kept, "tau": TAU, "centre": "fit-row means",
        "markets": SCORED, "lines": "base arm, OVER p in [0.10, 0.90]",
        "sims": tps.SIMS, "seed": "event id"}).encode()).hexdigest()[:12]


def validate(args: list[str]) -> None:
    fake = "--fake-y" in args
    limit = int(args[args.index("--limit") + 1]) if "--limit" in args else None
    workers = int(args[args.index("--workers") + 1]) if "--workers" in args else 6
    t0 = time.time()
    ex = json.loads((D / "serve_explore.json").read_text())
    kept = ex["kept"]
    recs = load_dev()
    fit = coef_table(player_rows(recs, EXPLORE_FROM, EXPLORE_END), kept)
    va = [r for r in recs if EXPLORE_END <= r["ts"] < DEV_CUT and scoreable(r)]
    if limit:
        va = va[:limit]
    jobs = [(r, *deltas(r, fit, kept)) for r in va]
    res = run_scoring(jobs, workers, fake)
    keep = [x for x in res if x["lines"] > 0]
    rows = [va[x["k"]] for x in keep]
    diff = np.array([x["st"] - x["sb"] for x in keep])
    lines = sum(x["lines"] for x in keep)
    boot = twa.cluster_boot(diff, rows)
    lo, hi = np.quantile(boot, .025), np.quantile(boot, .975)
    per: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0, 0])
    for x in keep:
        for m, v in x["per"].items():
            for i in range(3):
                per[m][i] += v[i]
    print(("FAKE-Y (outcomes drawn from the base p; NOT a look, not logged)"
           if fake else "VALIDATE (logged look)"))
    print(f"matches {len(keep)} (of {len(va)}; no line {len(va) - len(keep)}), "
          f"lines {lines}, moved deltas {sum(1 for j in jobs if j[1] or j[2])}")
    print(f"Delta per match {diff.mean():+.6f} [{lo:+.6f}, {hi:+.6f}] "
          f"(base mean S {np.mean([x['sb'] for x in keep]):.4f})")
    for m in sorted(per):
        b, t, k = per[m]
        print(f"  {m:28s} lines {k:7d}  base LL/line {b / k:.5f}  "
              f"treat - base per line {(t - b) / k:+.7f}")
    print("secs", round(time.time() - t0))
    if fake:
        return
    line = (f"| {dt.datetime.now(dt.UTC):%Y-%m-%d %H:%MZ} | tennis_serve | validate | "
            f"spec {spec_sha(kept)} | matches {len(keep)} (lines {lines}) | "
            f"Delta {diff.mean():+.6f} [{lo:+.6f}, {hi:+.6f}] | "
            f"S4 {'pass' if diff.mean() < 0 else 'fail'} |\n")
    with LOOKS.open("a") as f:
        f.write(line)
    print(line)


def freeze() -> None:
    ex = json.loads((D / "serve_explore.json").read_text())
    kept = ex["kept"]
    recs = load_dev()
    fit = coef_table(player_rows(recs, EXPLORE_FROM, DEV_CUT), kept)
    out = {"group": "tennis_serve", "kept": kept, "tau": TAU,
           "fit_window": ["2025-05-01", "2025-12-31"], "fit": fit,
           "apply": "serve_logit += sum(shrunk[c] * (x[c] - means[c])) for a server "
                    "with calendar coverage, else 0",
           "spec": spec_sha(kept)}
    (T / "serve_frozen.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out)[:600])


# --------------------------------------------------------------------------
# power (S5) - exam X only, no outcome
# --------------------------------------------------------------------------

def power() -> None:
    t0 = time.time()
    x = pickle.loads((T / "serve_exam_X.pkl").read_bytes())
    prow = []
    for r in x:
        for side in ("home", "away"):
            f = r["feats"][side]
            fc = r["forecast"].home if side == "home" else r["forecast"].away
            prow.append((r, side, f, fc))
    cov = [t for t in prow if t[2]["coverage"] == 1.0]
    p = np.array([1 / (1 + math.exp(-t[3].serve_logit)) for t in cov])
    sv = np.array([t[3].serve_var for t in cov])
    # expected serve points per side from the base simulation (outcome-free):
    # a seeded subsample of the exam matches
    rng = np.random.default_rng(5)
    sub = rng.choice(len(x), size=min(1500, len(x)), replace=False)
    sp = []
    for k in sub:
        r = x[int(k)]
        ms = market_sim(r["forecast"], n=1000, seed=tps.seed_of(r["event_id"]))
        tot = ms.sim.serve_points.sum(axis=1).mean(axis=0)
        sp.extend([float(tot[0]), float(tot[1])])
    m = float(np.mean(sp))
    pq = float(np.mean(p * (1 - p)))
    sig2 = FORM_VAR + float(sv.mean())
    n_req = 7.85 * (1 / (m * pq) + sig2) * 1.75 / C_MAT ** 2
    n_req_form = 7.85 * (1 / (m * pq) + FORM_VAR) * 1.75 / C_MAT ** 2
    buckets = {
        "games78>=3": lambda f: f["games78"] >= 3.0,
        "layoff21": lambda f: f["layoff21"] >= 1.0,
        "ret14": lambda f: f["ret14"] >= 1.0,
        "qual": lambda f: f["qual"] >= 1.0,
    }
    counts = {b: sum(1 for t in cov if fn(t[2])) for b, fn in buckets.items()}
    match_counts = {b: sum(1 for r in x if any(
        r["feats"][s]["coverage"] == 1.0 and fn(r["feats"][s]) for s in ("home", "away")))
        for b, fn in buckets.items()}
    by_q: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for r, side, f, _ in cov:
        d = dt.datetime.fromtimestamp(r["ts"], dt.UTC)
        q = f"{d.year}Q{(d.month - 1) // 3 + 1}"
        by_q[q]["rows"] += 1
        for b, fn in buckets.items():
            by_q[q][b] += int(fn(f))
    # explore exposure (outcome-free counts of the explore fit rows' features)
    recs = load_dev()
    ex_rows = player_rows(recs, EXPLORE_FROM, EXPLORE_END)
    ex_counts = {b: sum(1 for r in ex_rows if fn(r["x"])) for b, fn in buckets.items()}
    print("S5 tennis_serve (exam X only, no outcome)")
    print(f"exam matches {len(x)}, player rows {len(prow)}, with coverage {len(cov)}")
    print(f"mean base serve-point p {p.mean():.4f}, mean p(1-p) {pq:.4f}, "
          f"mean serve points per side (base sim, {len(sub)} matches x 1000) {m:.2f}, "
          f"mean rating var {sv.mean():.4f}, FORM_VAR {FORM_VAR}")
    print(f"n_req (player-matches per bucket) = 7.85 * (1/(m p q) + sigma2) * 1.75 / "
          f"{C_MAT}^2 with sigma2 = FORM_VAR + mean serve_var = {sig2:.4f}: {n_req:.0f}")
    print(f"  sensitivity sigma2 = FORM_VAR only: {n_req_form:.0f}")
    print("exposed player rows (coverage) per bucket:", counts)
    print("exposed matches (either player) per bucket:", match_counts)
    print("S5 per bucket:", {b: v >= n_req for b, v in counts.items()},
          "-> pass" if any(v >= n_req for v in counts.values()) else "-> FAIL")
    print("explore fit rows per bucket (pre-registration 2: < 50% of n_req -> pooled "
          "or not at all; tennis_serve has no partner):", ex_counts,
          {b: v >= 0.5 * n_req for b, v in ex_counts.items()})
    print("exam rows by quarter x bucket:",
          {q: dict(v) for q, v in sorted(by_q.items())})
    res = {"n_req": n_req, "n_req_form_only": n_req_form, "m": m, "pq": pq,
           "sigma2": sig2, "p_mean": float(p.mean()), "exam_matches": len(x),
           "player_rows": len(prow), "coverage_rows": len(cov), "buckets": counts,
           "bucket_matches": match_counts, "explore_buckets": ex_counts,
           "by_quarter": {q: dict(v) for q, v in by_q.items()},
           "secs": round(time.time() - t0)}
    (T / "serve_power.json").write_text(json.dumps(res, indent=1))
    print("secs", res["secs"])


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "explore":
        explore()
    elif cmd == "validate":
        validate(sys.argv[2:])
    elif cmd == "freeze":
        freeze()
    elif cmd == "power":
        power()
    else:
        raise SystemExit(__doc__)
