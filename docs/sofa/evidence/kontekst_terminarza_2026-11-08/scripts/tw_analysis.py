"""Tennis winner group - dev stages (pre-registration 5, 6, 8; S1-S5).

  explore : fit both arms on explore (<= 2025-08-31), S1 permutation, S2 lag,
            S3 signs (in-sample, unlimited looks)
  validate: fit on explore, score on validate (2025-09..12) -> S4; one LOGGED look
  freeze  : fit both arms on dev (explore + validate) -> frozen coefficients
  power   : S5 from the outcome-free exam X file
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import pickle
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

D = Path("/Users/mkoziol/projects/bet/data/refit_2026-11-08_schedule")
T = D / "tennis"
LOOKS = D / "looks.md"
EXPLORE_END = int(dt.datetime(2025, 9, 1, tzinfo=dt.UTC).timestamp())
BASE = ["lp_t", "lps", "dmin78", "drest", "dn7", "dform", "dhigh", "dtour"]
KEEP = [c for c in BASE if c not in ("dmin78", "drest", "dn7")]
SCHED = ["d_games78", "d_rounds_cur", "d_layoff21", "d_ret14",
         "d_surface_switch", "d_dom_prev"]
TREAT = KEEP + SCHED
DIRECTION = {"d_games78": -1, "d_layoff21": -1, "d_ret14": -1}
PLAYER_COLS = ["games78", "games7d_prev", "rounds_cur", "layoff21", "ret14",
               "surface_switch", "dom_prev"]


def logistic(x: np.ndarray, y: np.ndarray, iters: int = 30) -> np.ndarray:
    xa = np.column_stack([np.ones(len(x)), x])
    b = np.zeros(xa.shape[1])
    for _ in range(iters):
        p = 1 / (1 + np.exp(-(xa @ b)))
        w = p * (1 - p)
        h = xa.T @ (xa * w[:, None]) + 1e-8 * np.eye(len(b))
        step = np.linalg.solve(h, xa.T @ (y - p))
        b += step
        if np.max(np.abs(step)) < 1e-10:
            break
    return b


def predict(b: np.ndarray, x: np.ndarray) -> np.ndarray:
    z = b[0] + x @ b[1:]
    return np.clip(1 / (1 + np.exp(-z)), 1e-12, 1 - 1e-12)


def matrix(rows: list[dict], names: list[str]) -> np.ndarray:
    out = np.empty((len(rows), len(names)))
    for i, r in enumerate(rows):
        for j, n in enumerate(names):
            out[i, j] = r["base"][n] if n in r["base"] else r["sched"][n]
    return out


def fit_arms(rows: list[dict]) -> dict[str, dict[str, np.ndarray]]:
    """Per tier, best of three only (fit_coefficients); treatment on rows with
    calendar coverage only (coverage False -> base p, pre-registration 4)."""
    out: dict[str, dict[str, np.ndarray]] = {"base": {}, "treat": {}}
    by = defaultdict(list)
    for r in rows:
        if r["best_of"] == 3:
            by[r["tier"]].append(r)
    for tier, rs in by.items():
        y = np.array([r["y"] for r in rs])
        out["base"][tier] = logistic(matrix(rs, BASE), y)
        cov = [r for r in rs if r["sched"]["coverage"] == 1.0]
        out["treat"][tier] = logistic(matrix(cov, TREAT), np.array([r["y"] for r in cov]))
    return out


def arm_p(arms: dict, rows: list[dict]) -> tuple[np.ndarray, np.ndarray]:
    pb = np.empty(len(rows))
    pt = np.empty(len(rows))
    by = defaultdict(list)
    for i, r in enumerate(rows):
        by[r["tier"]].append(i)
    for tier, idx in by.items():
        rs = [rows[i] for i in idx]
        b = predict(arms["base"][tier], matrix(rs, BASE))
        t = predict(arms["treat"][tier], matrix(rs, TREAT))
        cov = np.array([r["sched"]["coverage"] == 1.0 for r in rs])
        pb[idx] = b
        pt[idx] = np.where(cov, t, b)
    return pb, pt


def logloss(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    return -(y * np.log(p) + (1 - y) * np.log(1 - p))


def week(ts: int) -> int:
    return ts // (7 * 86400)


def cluster_boot(diff: np.ndarray, rows: list[dict], reps: int = 2000,
                 seed: int = 7) -> np.ndarray:
    """Two-way (pigeonhole) bootstrap: player clusters (each match's two
    players, weight = product of their multiplicities) x tournament-week."""
    rng = np.random.default_rng(seed)
    players = sorted({r["home_id"] for r in rows} | {r["away_id"] for r in rows})
    pidx = {p: i for i, p in enumerate(players)}
    tw = sorted({(r["tournament_id"], week(r["ts"])) for r in rows})
    tidx = {k: i for i, k in enumerate(tw)}
    h = np.array([pidx[r["home_id"]] for r in rows])
    a = np.array([pidx[r["away_id"]] for r in rows])
    t = np.array([tidx[(r["tournament_id"], week(r["ts"]))] for r in rows])
    out = np.empty(reps)
    for k in range(reps):
        wp = rng.multinomial(len(players), np.full(len(players), 1 / len(players)))
        wt = rng.multinomial(len(tw), np.full(len(tw), 1 / len(tw)))
        w = wp[h] * wp[a] * wt[t]
        out[k] = (w * diff).sum() / w.sum() if w.sum() > 0 else 0.0
    return out


def load_dev() -> list[dict]:
    return pickle.loads((T / "tw_dev.pkl").read_bytes())


def per_player(r: dict, side: str) -> dict[str, float]:
    s = r["sched"]
    sign = 1 if side == "home" else -1
    return {c: (s[f"s_{c}"] + sign * s[f"d_{c}"]) / 2 for c in PLAYER_COLS}


def with_player_cols(rows: list[dict], cols: dict[tuple[int, str], dict]) -> list[dict]:
    out = []
    for i, r in enumerate(rows):
        h, a = cols[(i, "home")], cols[(i, "away")]
        s = dict(r["sched"])
        for c in PLAYER_COLS:
            s[f"d_{c}"] = h[c] - a[c]
        out.append({**r, "sched": s})
    return out


def explore() -> None:
    rows = [r for r in load_dev() if r["ts"] < EXPLORE_END]
    fit = [r for r in rows if r["best_of"] == 3 and r["sched"]["coverage"] == 1.0]
    y = np.array([r["y"] for r in fit])
    arms = fit_arms(fit)
    pb, pt = arm_p(arms, fit)
    gain = float((logloss(pb, y) - logloss(pt, y)).sum())
    print("explore rows", len(rows), "fit rows", len(fit), "in-sample LL gain", round(gain, 2))
    for tier, b in arms["treat"].items():
        print(tier, {n: round(float(v), 4) for n, v in zip(TREAT, b[1:], strict=True)})
    # S3 signs: pooled over tiers (n-weighted)
    pooled = defaultdict(float)
    ntier = defaultdict(int)
    for r in fit:
        ntier[r["tier"]] += 1
    for tier, b in arms["treat"].items():
        for n, v in zip(TREAT, b[1:], strict=True):
            pooled[n] += v * ntier[tier] / len(fit)
    s3 = {n: (pooled[n], np.sign(pooled[n]) == d) for n, d in DIRECTION.items()}
    print("S3", {k: (round(v[0], 4), bool(v[1])) for k, v in s3.items()})
    # S1 permutation within player-season: shuffle each player's columns among
    # that player's matches of the same calendar year, recompute differences
    rng = np.random.default_rng(11)
    slots: dict[tuple[int, int], list[tuple[int, str]]] = defaultdict(list)
    base_cols = {}
    for i, r in enumerate(fit):
        yr = dt.datetime.fromtimestamp(r["ts"], dt.UTC).year
        for side, pid in (("home", r["home_id"]), ("away", r["away_id"])):
            slots[(pid, yr)].append((i, side))
            base_cols[(i, side)] = per_player(r, side)
    null = []
    for _ in range(200):
        perm = {}
        for keys in slots.values():
            order = rng.permutation(len(keys))
            for k, j in zip(keys, order, strict=True):
                perm[k] = base_cols[keys[j]]
        prow = with_player_cols(fit, perm)
        pa = fit_arms(prow)
        b0, t0 = arm_p(pa, prow)
        null.append(float((logloss(b0, y) - logloss(t0, y)).sum()))
    p_s1 = (1 + sum(g >= gain for g in null)) / (1 + len(null))
    print("S1 p", round(p_s1, 4), "null mean", round(float(np.mean(null)), 2))
    # S2 lagged control: the player's games78 at his previous rated match
    last: dict[int, float] = {}
    lag_rows = []
    for i, r in sorted(enumerate(fit), key=lambda t: t[1]["ts"]):
        h = base_cols[(i, "home")]
        a = base_cols[(i, "away")]
        lh = last.get(r["home_id"])
        la = last.get(r["away_id"])
        if lh is not None and la is not None:
            s = dict(r["sched"])
            s["d_lag_games78"] = lh - la
            lag_rows.append({**r, "sched": s})
        last[r["home_id"]] = h["games78"]
        last[r["away_id"]] = a["games78"]
    ly = np.array([r["y"] for r in lag_rows])
    names = TREAT + ["d_lag_games78"]
    b = logistic(matrix(lag_rows, names), ly)
    cur, lag = b[1 + names.index("d_games78")], b[1 + names.index("d_lag_games78")]
    print("S2 beta games78", round(float(cur), 4), "lag", round(float(lag), 4),
          "pass", bool(abs(lag) < 0.5 * abs(cur)))
    res = {"gain": gain, "S1_p": p_s1, "S2": [float(cur), float(lag)],
           "S3": {k: [float(v[0]), bool(v[1])] for k, v in s3.items()}}
    (T / "tw_explore.json").write_text(json.dumps(res, indent=1))


def validate() -> None:
    dev = load_dev()
    ex = [r for r in dev if r["ts"] < EXPLORE_END]
    va = [r for r in dev if r["ts"] >= EXPLORE_END and r["best_of"] == 3]
    arms = fit_arms(ex)
    pb, pt = arm_p(arms, va)
    y = np.array([r["y"] for r in va])
    diff = logloss(pt, y) - logloss(pb, y)
    boot = cluster_boot(diff, va)
    spec = hashlib.sha256(json.dumps({"BASE": BASE, "TREAT": TREAT}).encode()).hexdigest()[:12]
    line = (f"| {dt.datetime.now(dt.UTC):%Y-%m-%d %H:%MZ} | tennis_winner | validate | spec {spec} | "
            f"n {len(va)} | Delta {diff.mean():+.6f} [{np.quantile(boot, .025):+.6f}, "
            f"{np.quantile(boot, .975):+.6f}] | S4 {'pass' if diff.mean() < 0 else 'fail'} |\n")
    with LOOKS.open("a") as f:
        f.write(line)
    print(line)


def freeze() -> None:
    arms = fit_arms(load_dev())
    out = {arm: {t: [float(v) for v in b] for t, b in tiers.items()}
           for arm, tiers in arms.items()}
    out["names"] = {"base": BASE, "treat": TREAT}
    (T / "tw_frozen.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out)[:400])


def power() -> None:
    x = pickle.loads((T / "tw_exam_X.pkl").read_bytes())
    x = [r for r in x if r["best_of"] == 3]
    need = int(4900 * 1.75)
    buckets = {
        "games78>=3 either": sum(1 for r in x if r["sched"]["max_games78"] >= 3.0),
        "layoff21 either": sum(1 for r in x if r["sched"]["max_layoff21"] >= 1.0),
        "ret14 either": sum(1 for r in x if r["sched"]["max_ret14"] >= 1.0),
    }
    print("exam rows", len(x), "need per bucket", need, buckets)


if __name__ == "__main__":
    {"explore": explore, "validate": validate, "freeze": freeze, "power": power}[sys.argv[1]]()
