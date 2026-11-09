"""F3 descriptives on EXPLORE only (ts < 2025-09-01 00:00Z); not gates.

Rows: fb_dev.pkl (dev rows with y, D10 centres), filtered to explore; metrics
goals_for, corners_for, shots_for (+ goals_1h_for / goals_2h_for for halves).
Coverage of both sides as in fb.metric_rows. Fits: fb.fit_metric (Poisson,
offset log centre, team-season FE, cluster SE by team).

 1. within-match contrast: per match with both sides' rows,
    dz = [log(yh+.5) - log(ch)] - [log(ya+.5) - log(ca)] on
    dx_c = own_c(home) - own_c(away), c in R1, R2, cont_prev4, OLS with intercept,
    HC1 SE (one observation per match = cluster by match); beside FE GLM own, opp
    and own - opp (the within-match slope estimates own - opp).
 2. strata refits: women / men; continental / domestic (comp in
    config/sofa_cup_strength.json competitions); |supremacy| terciles (rec[7] of
    full/dev/forecasts book 1, boundaries from explore goals_for matches); round
    <= 3 vs > 3 (side's earlier matches in (comp, season) in football_features <= 2).
 3. dispersion: Pearson chi2/df of the FE fit (df = n - k - #FE), and with the
    recorded NB alpha; mean squared Pearson residual per own rest bucket.
 4. halves: goals_1h_for vs goals_2h_for own R1 / R2 / cont_prev4.
"""
from __future__ import annotations

import bisect
import datetime as dt
import gzip
import json
import math
import pickle
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

D = Path("/Users/mkoziol/projects/bet/data/refit_2026-11-08_schedule")
REPO = Path("/Users/mkoziol/projects/bet")
sys.path[:0] = [str(D)]
import fb_analysis as fb  # noqa: E402

OUT = D / "desc"
METRICS = ["goals_for", "corners_for", "shots_for"]
HALVES = ["goals_1h_for", "goals_2h_for"]
C3 = ["R1", "R2", "cont_prev4"]
REPORT = ["own_R1", "own_R2", "own_cont_prev4", "own_R5_other"]
MIN_FIT = 1000


def coef(b, se, names, keys):  # type: ignore[no-untyped-def]
    return {k: [float(b[names.index(k)]), float(se[names.index(k)])] for k in keys}


def contrast(rs, feats):  # type: ignore[no-untyped-def]
    by = defaultdict(dict)
    for r in rs:
        by[r["eid"]][r["side"]] = r
    dz, dx = [], []
    for e, sides in by.items():
        if "home" not in sides or "away" not in sides:
            continue
        h, a = sides["home"], sides["away"]
        f = feats[e]
        ih, ia = f["home"].indicators(), f["away"].indicators()
        dz.append(math.log(h["y"] + 0.5) - math.log(h["centre"])
                  - math.log(a["y"] + 0.5) + math.log(a["centre"]))
        dx.append([ih[c] - ia[c] for c in C3])
    y = np.array(dz)
    x = np.column_stack([np.ones(len(y)), np.array(dx)])
    xtx_i = np.linalg.inv(x.T @ x)
    b = xtx_i @ x.T @ y
    e = y - x @ b
    n, k = x.shape
    meat = (x * e[:, None] ** 2).T @ x
    v = xtx_i @ meat @ xtx_i * n / (n - k)
    se = np.sqrt(np.diag(v))
    return {"matches": n, "intercept": [float(b[0]), float(se[0])],
            **{c: [float(b[i + 1]), float(se[i + 1])] for i, c in enumerate(C3)}}


def dispersion(rs, fit, feats):  # type: ignore[no-untyped-def]
    b, se, names, (y, off, x, g, a) = fit
    mu = np.exp(off + a[g] + x @ b)
    al = np.array([r["alpha"] for r in rs])
    df = len(y) - x.shape[1] - len(np.unique(g))
    p = (y - mu) ** 2 / mu
    pnb = (y - mu) ** 2 / (mu + al * mu ** 2)
    buck = defaultdict(list)
    for i, r in enumerate(rs):
        f = feats[r["eid"]]
        buck[f[r["side"]].rest_bucket].append(i)
    per = {k: {"n": len(ix), "pearson_mean_sq": float(p[ix].mean()),
               "nb_mean_sq": float(pnb[ix].mean())} for k, ix in sorted(buck.items(), key=str)}
    return {"n": int(len(y)), "df": int(df), "alpha_mean": float(al.mean()),
            "pearson_chi2_df": float(p.sum() / df), "nb_chi2_df": float(pnb.sum() / df),
            "per_own_rest_bucket": per}


def sup_by_event() -> dict[int, float]:
    out = {}
    for p in sorted((D / "full/dev/forecasts").glob("*.pkl.gz")):
        for rec in pickle.load(gzip.open(p)):
            if rec[1] >= fb.EXPLORE_END:
                continue
            if rec[5] == 1 and rec[7] is not None:
                out[rec[0]] = abs(float(rec[7]))
    return out


def round_index(feats) -> dict[tuple[int, str], int]:  # type: ignore[no-untyped-def]
    """(eid, side) -> the side's earlier events in (comp, season) in football_features."""
    seq = defaultdict(list)
    for e, f in feats.items():
        for s, t in (("home", f["home_id"]), ("away", f["away_id"])):
            seq[(t, f["comp"], f["season"])].append((f["ts"], e, s))
    out = {}
    for lst in seq.values():
        lst.sort()
        for i, (_, e, s) in enumerate(lst):
            out[(e, s)] = i
    return out


def main() -> None:
    OUT.mkdir(exist_ok=True)
    feats = pickle.loads((D / "football_features.pkl").read_bytes())
    data = pickle.load(open(D / "fb_dev.pkl", "rb"))
    assert not data["fake"]
    rows = [r for r in data["rows"] if r["ts"] < fb.EXPLORE_END
            and r["market"] in set(METRICS + HALVES)]
    del data
    cont = {int(c) for c in json.loads((REPO / "config/sofa_cup_strength.json").read_text())["competitions"]}
    sup = sup_by_event()
    rnd = round_index(feats)
    res: dict = {"explore_end_utc": "2025-09-01T00:00Z", "metrics": {}}
    by_metric = {m: fb.metric_rows(rows, m, 0, fb.EXPLORE_END, feats) for m in METRICS + HALVES}
    g_eids = {r["eid"] for r in by_metric["goals_for"]}
    sv = sorted(sup[e] for e in g_eids if e in sup)
    edges = [sv[len(sv) // 3], sv[2 * len(sv) // 3]]
    res["sup_tercile_edges"] = edges
    res["sup_coverage"] = {"goals_for_matches": len(g_eids),
                           "with_sup": sum(1 for e in g_eids if e in sup)}
    for m in METRICS:
        rs = by_metric[m]
        fit = fb.fit_metric(rs, feats)
        b, se, names, _ = fit
        fe = {f"{w}_{c}": [float(b[names.index(f'{w}_{c}')]), float(se[names.index(f'{w}_{c}')])]
              for c in C3 for w in ("own", "opp")}
        out = {"rows": len(rs), "fe": fe,
               "fe_own_minus_opp": {c: fe[f"own_{c}"][0] - fe[f"opp_{c}"][0] for c in C3},
               "fe_report": coef(b, se, names, REPORT),
               "contrast": contrast(rs, feats),
               "dispersion": dispersion(rs, fit, feats), "strata": {}}

        def stratum(rr):  # type: ignore[no-untyped-def]
            if len(rr) < MIN_FIT:
                return {"rows": len(rr), "skipped": f"< {MIN_FIT}"}
            bb, ss, nn, _ = fb.fit_metric(rr, feats)
            return {"rows": len(rr), **coef(bb, ss, nn, REPORT)}

        st = out["strata"]
        st["women"] = stratum([r for r in rs if r["women"]])
        st["men"] = stratum([r for r in rs if not r["women"]])
        st["continental"] = stratum([r for r in rs if r["comp"] in cont])
        st["domestic"] = stratum([r for r in rs if r["comp"] not in cont])
        for i, lab in enumerate(["sup_T1_low", "sup_T2_mid", "sup_T3_high"]):
            st[lab] = stratum([r for r in rs if r["eid"] in sup
                               and bisect.bisect_right(edges, sup[r["eid"]]) == i])
        st["sup_missing"] = {"rows": sum(1 for r in rs if r["eid"] not in sup)}
        st["round_le3"] = stratum([r for r in rs if rnd.get((r["eid"], r["side"]), 0) <= 2])
        st["round_gt3"] = stratum([r for r in rs if rnd.get((r["eid"], r["side"]), 0) > 2])
        res["metrics"][m] = out
        print(m, "done", len(rs), flush=True)
    halves = {}
    for m in HALVES:
        rs = by_metric[m]
        b, se, names, _ = fb.fit_metric(rs, feats)
        halves[m] = {"rows": len(rs), **coef(b, se, names, [f"own_{c}" for c in C3])}
    halves["diff_1h_minus_2h_naive_z"] = {
        c: (halves["goals_1h_for"][f"own_{c}"][0] - halves["goals_2h_for"][f"own_{c}"][0])
        / math.sqrt(halves["goals_1h_for"][f"own_{c}"][1] ** 2 + halves["goals_2h_for"][f"own_{c}"][1] ** 2)
        for c in C3}
    res["halves"] = halves
    (OUT / "f3_desc.json").write_text(json.dumps(res, indent=1))
    (OUT / "f3_desc.md").write_text(md(res))
    print(md(res))


def f(v):  # type: ignore[no-untyped-def]
    return f"{v[0]:+.4f} ({v[1]:.4f})"


def md(res: dict) -> str:
    L = ["# F3 descriptives (explore only, ts < 2025-09-01 00:00Z)", "",
         f"Generated {dt.datetime.now(dt.UTC):%Y-%m-%d %H:%MZ} by `desc/f3_desc.py`. Descriptive, not gates. "
         "Coefficients: estimate (SE); FE fits = `fb.fit_metric` (cluster SE by team).", "",
         "## 1. Within-match contrast vs FE GLM", "",
         "Contrast: OLS of dz = [log(y+.5) - log(centre)]_home - [..]_away on own-indicator differences "
         "(home - away), intercept, HC1 SE (one obs per match). Its slope estimates own - opp on a "
         "log(y+.5) scale; FE GLM columns are on the Poisson log scale.", "",
         "| metric | col | contrast | matches | FE own | FE opp | FE own-opp |", "|---|---|---|---|---|---|---|"]
    for m, o in res["metrics"].items():
        for c in C3:
            L.append(f"| {m} | {c} | {f(o['contrast'][c])} | {o['contrast']['matches']} | "
                     f"{f(o['fe'][f'own_{c}'])} | {f(o['fe'][f'opp_{c}'])} | {o['fe_own_minus_opp'][c]:+.4f} |")
    L += ["", f"|supremacy| tercile edges (explore goals_for matches): {res['sup_tercile_edges']}; "
          f"coverage {res['sup_coverage']}", "", "## 2. Strata (FE refit per stratum)", ""]
    for m, o in res["metrics"].items():
        L += [f"### {m}", "", "| stratum | rows | " + " | ".join(REPORT) + " |",
              "|---|---|" + "---|" * len(REPORT)]
        L.append(f"| all | {o['rows']} | " + " | ".join(f(o['fe_report'][k]) for k in REPORT) + " |")
        for s, v in o["strata"].items():
            if "skipped" in v or len(v) == 1:
                L.append(f"| {s} | {v['rows']} | " + " | ".join(
                    v.get("skipped", "not fitted") for _ in REPORT) + " |")
            else:
                flag = " (<2000)" if v["rows"] < 2000 else ""
                L.append(f"| {s} | {v['rows']}{flag} | " + " | ".join(f(v[k]) for k in REPORT) + " |")
        L.append("")
    L += ["## 3. Dispersion (FE fit)", "",
          "| metric | n | df | Pearson chi2/df (Poisson) | mean recorded alpha | chi2/df with NB alpha |",
          "|---|---|---|---|---|---|"]
    for m, o in res["metrics"].items():
        d = o["dispersion"]
        L.append(f"| {m} | {d['n']} | {d['df']} | {d['pearson_chi2_df']:.4f} | {d['alpha_mean']:.4f} | "
                 f"{d['nb_chi2_df']:.4f} |")
    L += ["", "Per own rest bucket, mean squared Pearson residual (no df correction; Poisson / NB):", ""]
    for m, o in res["metrics"].items():
        L.append(f"- {m}: " + "; ".join(
            f"{k} n {v['n']} {v['pearson_mean_sq']:.3f} / {v['nb_mean_sq']:.3f}"
            for k, v in o["dispersion"]["per_own_rest_bucket"].items()))
    h = res["halves"]
    L += ["", "## 4. Halves (goals)", "", "| col | goals_1h_for | goals_2h_for | naive z (1H-2H) |",
          "|---|---|---|---|"]
    for c in C3:
        L.append(f"| own_{c} | {f(h['goals_1h_for'][f'own_{c}'])} | {f(h['goals_2h_for'][f'own_{c}'])} | "
                 f"{h['diff_1h_minus_2h_naive_z'][c]:+.2f} |")
    L += ["", f"Rows: goals_1h_for {h['goals_1h_for']['rows']}, goals_2h_for {h['goals_2h_for']['rows']}. "
          "The z treats the halves as independent (they share matches) - indicative only.", ""]
    return "\n".join(L)


if __name__ == "__main__":
    main()
