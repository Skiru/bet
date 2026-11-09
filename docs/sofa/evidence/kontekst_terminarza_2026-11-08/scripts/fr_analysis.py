"""football_result (path ii): goals term fitted against the recorded RATING
goals centres (D3 ii), applied to lh / la of football_result.result_probs;
score = 1X2 multinomial log loss per match (doprecyzowanie 7).

  load | explore | validate | freeze      (exam: measure_schedule_exam.py)
"""
from __future__ import annotations

import datetime as dt
import gzip
import hashlib
import json
import math
import pickle
import sys
from pathlib import Path

import numpy as np

D = Path("/Users/mkoziol/projects/bet/data/refit_2026-11-08_schedule")
sys.path[:0] = [str(D)]
import fb_analysis as fb  # noqa: E402
from bet.sofa.football_result import load_config, result_probs  # noqa: E402

BOOK = fb.book_for("result_1x2")
R = load_config().nb_r
DEV_END = int(dt.datetime(2026, 1, 1, tzinfo=dt.UTC).timestamp())


def forecasts(tier: str):  # type: ignore[no-untyped-def]
    for p in sorted((D / "full" / tier / "forecasts").glob("*.pkl.gz")):
        for rec in pickle.load(gzip.open(p)):
            if rec[5] == BOOK:
                yield rec


def load() -> None:
    feats = pickle.loads((D / "football_features.pkl").read_bytes())
    ys = pickle.loads((D / "fr_dev_y.pkl").read_bytes())
    rows = []
    for eid, ts, comp, home, away, book, cents, sup in forecasts("dev"):
        f = feats.get(eid)
        lh, la = cents.get(("goals_for", "side_a")), cents.get(("goals_for", "side_b"))
        if f is None or f["national"] or lh is None or la is None or eid not in ys:
            continue
        hg, ag = ys[eid]
        for side, c, y in (("home", lh, hg), ("away", la, ag)):
            rows.append({"eid": eid, "ts": ts, "comp": comp, "market": "goals_for",
                         "side": side, "y": float(y), "centre": c, "alpha": 0.0,
                         "home": home, "away": away, "season": f["season"]})
    pickle.dump(rows, open(D / "fr_dev.pkl", "wb"))
    print("rows", len(rows))


def fit(rows, feats, lo, hi):  # type: ignore[no-untyped-def]
    rs = fb.metric_rows(rows, "goals_for", lo, hi, feats)
    b, se, names, (y, off, x, g, a) = fb.fit_metric(rs, feats)
    return b, se, names, (y, off, x, g, a)


def explore() -> None:
    rows = pickle.load(open(D / "fr_dev.pkl", "rb"))
    feats = pickle.loads((D / "football_features.pkl").read_bytes())
    b, se, names, (y, off, x, g, a) = fit(rows, feats, 0, fb.EXPLORE_END)
    _, fe0 = fb.fit_poisson(y, off, np.zeros((len(y), 0)), g)
    gain, _ = fb.deviance_gain(y, off, x, g, fe0)
    rng = np.random.default_rng(17)
    order = np.argsort(g, kind="stable")
    blocks = np.split(order, np.flatnonzero(np.diff(g[order])) + 1)
    null = []
    for _ in range(200):
        perm = np.empty(len(y), dtype=np.int64)
        for blk in blocks:
            perm[blk] = rng.permutation(blk)
        null.append(fb.deviance_gain(y, off, x[perm], g, fe0)[0])
    p_s1 = (1 + sum(v >= gain for v in null)) / 201
    s3 = {c: [float(b[names.index(f"own_{c}")]), bool(b[names.index(f"own_{c}")] <= 0)]
          for c in fb.OWN_DOWN + fb.OWN_DOWN_LAYOFF}
    print("rows", len(y), "gain", round(gain, 1), "S1 p", round(p_s1, 4))
    print("coef", {n: (round(float(v), 4), round(float(s), 4)) for n, v, s in zip(names, b, se, strict=True)})
    print("S3", s3)
    (D / "fr_explore.json").write_text(json.dumps({"gain": gain, "S1_p": p_s1, "S3": s3}, indent=1))


def coef_dict(b, se, names, drop):  # type: ignore[no-untyped-def]
    return {n: v * fb.TAU ** 2 / (fb.TAU ** 2 + s ** 2)
            for n, v, s in zip(names, b, se, strict=True) if n not in drop}


def side_t(feats, eid, side, cf):  # type: ignore[no-untyped-def]
    f = feats[eid]
    own, opp = (f["home"], f["away"]) if side == "home" else (f["away"], f["home"])
    if not (own.coverage and opp.coverage):
        return 0.0
    io, ip = own.indicators(), opp.indicators()
    return (sum(cf.get(f"own_{c}", 0.0) * io[c] for c in fb.COLS)
            + sum(cf.get(f"opp_{c}", 0.0) * ip[c] for c in fb.COLS))


def match_scores(fcs, feats, cf, ys):  # type: ignore[no-untyped-def]
    """[(eid, home, away, logloss_treat - logloss_base)]"""
    out = []
    for eid, ts, comp, home, away, book, cents, sup in fcs:
        f = feats.get(eid)
        lh, la = cents.get(("goals_for", "side_a")), cents.get(("goals_for", "side_b"))
        if f is None or f["national"] or lh is None or la is None or eid not in ys:
            continue
        hg, ag = ys[eid]
        res = "1" if hg > ag else "2" if ag > hg else "X"
        pb = result_probs(lh, la, R)[res]
        th, ta = side_t(feats, eid, "home", cf), side_t(feats, eid, "away", cf)
        pt = result_probs(lh * math.exp(th), la * math.exp(ta), R)[res]
        out.append((eid, home, away, -math.log(pt) + math.log(pb)))
    return out


def validate(drop_json: str) -> None:
    rows = pickle.load(open(D / "fr_dev.pkl", "rb"))
    feats = pickle.loads((D / "football_features.pkl").read_bytes())
    drop = set(json.loads(drop_json))
    b, se, names, _ = fit(rows, feats, 0, fb.EXPLORE_END)
    cf = coef_dict(b, se, names, drop)
    ys = pickle.loads((D / "fr_dev_y.pkl").read_bytes())
    fcs = [r for r in forecasts("dev") if fb.EXPLORE_END <= r[1] < DEV_END]
    sc = match_scores(fcs, feats, cf, ys)
    diff = np.array([s[3] for s in sc])
    bt = fb.boot2(diff, [(s[1], s[2]) for s in sc])
    spec = hashlib.sha256(json.dumps({"COLS": fb.COLS, "drop": sorted(drop), "tau": fb.TAU}).encode()).hexdigest()[:12]
    line = (f"| {dt.datetime.now(dt.UTC):%Y-%m-%d %H:%MZ} | football_result | validate | spec {spec} | "
            f"matches {len(diff)} | Delta {diff.mean():+.6f} [{np.quantile(bt, .025):+.6f}, "
            f"{np.quantile(bt, .975):+.6f}] | S4 {'pass' if diff.mean() < 0 else 'fail'} |\n")
    with fb.LOOKS.open("a") as f:
        f.write(line)
    print(line, end="")


def freeze(drop_json: str) -> None:
    rows = pickle.load(open(D / "fr_dev.pkl", "rb"))
    feats = pickle.loads((D / "football_features.pkl").read_bytes())
    b, se, names, _ = fit(rows, feats, 0, DEV_END)
    cf = coef_dict(b, se, names, set(json.loads(drop_json)))
    (D / "fr_frozen.json").write_text(json.dumps({"tau": fb.TAU, "book": BOOK, "nb_r": R, "coef": cf}, indent=1))
    print(cf)


if __name__ == "__main__":
    cmd = sys.argv[1]
    {"load": load, "explore": explore}.get(cmd, lambda: None)()
    if cmd == "validate":
        validate(sys.argv[2])
    if cmd == "freeze":
        freeze(sys.argv[2])
