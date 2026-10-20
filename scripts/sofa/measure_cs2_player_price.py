#!/usr/bin/env python3
# ruff: noqa: E501  - report lines are tables.
"""CS2 player lines: does the model discriminate within Superbet's price?
(read-only evidence; an AUDIT on our settled days, never a curve source).

Population: every graded CS2 player side (player_kills / deaths / assists /
headshots) in runs/sofa/cs2/<d>/settled.json with WIN / LOSS, its price
`odds`, the other side's `partner_odds` and the engine's `model_p`
(settle_cs2.attach_model: the estimator of the day the game was offered,
history cut at min(Superbet kickoff, Sofascore start) - 60 s, this series
excluded). The price is the last pre-start snapshot (cs2.latest_pre_kickoff):
both sides of a line come from the same snapshot record.

Per family and direction: n lines / matches / days, the devigged price p
(proportional and power), model p, log-loss / Brier / AUC, calibration by
bucket; out of sample (leave-one-day-out and walk-forward by day) logistic
blends y ~ logit(price) [+ logit(model)] with the delta log-loss against the
price alone and a match-level bootstrap 95% interval; realised minus price
in quintiles of model - price; overround; ROI at the price where
model > price by X. One row per side is written to --out-dir as
cs2_player_lines.jsonl.gz with schema.json beside it.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_cs2_player_price.py \\
        --from 2026-09-28 --to 2026-10-19 [--out-dir d] [--reps 2000] \\
        [--db-path data/sofa.db]   # opened read-only (mode=ro), for player ids only
"""

from __future__ import annotations

import argparse
import gzip
import json
import sqlite3
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa.cs2 import esports_name  # noqa: E402

FAMILIES = ("player_kills", "player_deaths", "player_assists", "player_headshots")
EDGES = [0.0, 0.30, 0.40, 0.45, 0.50, 0.55, 0.60, 0.70, 0.75, 0.80, 1.01]
GAPS = (0.0, 0.03, 0.05, 0.10)
SCHEMA = {
    "date": "settled.json day (runs/sofa/cs2/<date>)",
    "superbet_event_id": "Superbet event id",
    "sofascore_event_id": "pinned Sofascore series id",
    "match": "Superbet match name",
    "kickoff_utc": "Superbet kickoff",
    "fetched_at_utc": "the last pre-start snapshot that priced this side",
    "minutes_before_kickoff": "kickoff - fetched_at, minutes",
    "family": "player_kills | player_deaths | player_assists | player_headshots",
    "map_nr": "map number (Superbet)",
    "subject": "player nickname as Superbet writes it",
    "player_ids": "Sofascore player_id(s) with this folded nickname in the graded series' own lineups (cs2_player_map); >1 = namesakes in one series",
    "line": "the line",
    "side": "OVER | UNDER",
    "odds": "this side's price",
    "partner_odds": "the other side's price, same snapshot",
    "overround": "1/odds + 1/partner_odds - 1",
    "p_prop": "proportional devig of this side",
    "p_power": "power devig of this side",
    "model_p": "engine's pre-game p of this side (settle_cs2.attach_model)",
    "model": "engine model name (round_exposure / count ...)",
    "model_n": "engine sample size",
    "actual": "the player's stat on the map",
    "y": "1 WIN, 0 LOSS",
}


def power_devig(o1: float, o2: float) -> float:
    a, b = 1.0 / o1, 1.0 / o2
    lo, hi = 0.5, 5.0
    for _ in range(80):
        k = (lo + hi) / 2
        if a ** k + b ** k > 1.0:
            lo = k
        else:
            hi = k
    return float(a ** ((lo + hi) / 2))


def esports_fold(name: str) -> str:
    return str(esports_name(name))


def load(runs: Path, d0: str, d1: str, db: str | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    day = date.fromisoformat(d0)
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True) if db else None
    fold_cache: dict[str, str] = {}
    while day <= date.fromisoformat(d1):
        ds = day.isoformat()
        day += timedelta(days=1)
        path = runs / "cs2" / ds / "settled.json"
        if not path.exists():
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        for eid, ev in (doc.get("events") or {}).items():
            names: dict[str, set[int]] = defaultdict(set)
            sid = ev.get("sofascore_event_id")
            graded = [g for g in ev.get("graded") or []
                      if g.get("family") in FAMILIES and g.get("outcome") in ("WIN", "LOSS")
                      and g.get("odds") and g.get("partner_odds") and g.get("model_p") is not None]
            if not graded:
                continue
            if conn is not None and isinstance(sid, int):
                for pid, pname in conn.execute(
                        "SELECT DISTINCT p.player_id, p.player_name FROM cs2_player_map p "
                        "JOIN cs2_map m USING (game_id) WHERE m.sofascore_event_id = ?", (sid,)):
                    key = fold_cache.setdefault(pname, esports_fold(pname))
                    names[key].add(int(pid))
            ko = datetime.fromisoformat(str(ev["kickoff_utc"]).replace("Z", "+00:00"))
            for g in graded:
                o, po = float(g["odds"]), float(g["partner_odds"])
                fa = datetime.fromisoformat(str(g["fetched_at_utc"]).replace("Z", "+00:00"))
                subj = str(g.get("subject") or "")
                fs = fold_cache.setdefault(subj, esports_fold(subj))
                rows.append({
                    "date": ds, "superbet_event_id": str(eid), "sofascore_event_id": sid,
                    "match": ev.get("match_name"), "kickoff_utc": ev.get("kickoff_utc"),
                    "fetched_at_utc": g["fetched_at_utc"],
                    "minutes_before_kickoff": round((ko - fa).total_seconds() / 60, 1),
                    "family": g["family"], "map_nr": int(g.get("map_nr") or 0),
                    "subject": subj, "player_ids": sorted(names.get(fs, set())),
                    "line": g.get("line"), "side": g["side"], "odds": o, "partner_odds": po,
                    "overround": round(1 / o + 1 / po - 1, 5),
                    "p_prop": round((1 / o) / (1 / o + 1 / po), 5),
                    "p_power": round(power_devig(o, po), 5),
                    "model_p": float(g["model_p"]), "model": g.get("model"),
                    "model_n": g.get("model_n"), "actual": g.get("actual"),
                    "y": 1 if g["outcome"] == "WIN" else 0})
    return rows


# --- metrics -------------------------------------------------------------------

def clip(p: np.ndarray) -> np.ndarray:
    return np.asarray(np.clip(p, 1e-4, 1 - 1e-4))


def logit(p: np.ndarray) -> np.ndarray:
    p = clip(p)
    return np.asarray(np.log(p / (1 - p)))


def ll_vec(p: np.ndarray, y: np.ndarray) -> np.ndarray:
    p = clip(p)
    return np.asarray(-(y * np.log(p) + (1 - y) * np.log(1 - p)))


def auc(s: np.ndarray, y: np.ndarray) -> float:
    pos, neg = s[y == 1], s[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    order = np.argsort(np.concatenate([pos, neg]), kind="mergesort")
    allv = np.concatenate([pos, neg])[order]
    ranks = np.empty(len(allv))
    i = 0
    while i < len(allv):  # average ranks for ties
        j = i
        while j + 1 < len(allv) and allv[j + 1] == allv[i]:
            j += 1
        ranks[i:j + 1] = (i + j) / 2 + 1
        i = j + 1
    r = np.empty(len(allv))
    r[order] = ranks
    return float((r[:len(pos)].sum() - len(pos) * (len(pos) + 1) / 2) / (len(pos) * len(neg)))


def fit_logit(xm: np.ndarray, y: np.ndarray, ridge: float = 1e-3) -> np.ndarray:
    w = np.zeros(xm.shape[1])
    for _ in range(50):
        p = 1 / (1 + np.exp(-(xm @ w)))
        g = xm.T @ (p - y) + ridge * w
        h = (xm * (p * (1 - p))[:, None]).T @ xm + ridge * np.eye(xm.shape[1])
        step = np.linalg.solve(h, g)
        w -= step
        if np.abs(step).max() < 1e-8:
            break
    return w


def design(lp: np.ndarray, lm: np.ndarray | None) -> np.ndarray:
    cols = [np.ones_like(lp), lp] + ([lm] if lm is not None else [])
    return np.column_stack(cols)


def oos_preds(days: np.ndarray, lp: np.ndarray, lm: np.ndarray, y: np.ndarray,
              mode: str) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """(mask, p price-only recal, p blend, p model-only recal) out of sample."""
    pa = np.full(len(y), np.nan)
    pb = np.full(len(y), np.nan)
    pc = np.full(len(y), np.nan)
    for d in sorted(set(days)):
        test = days == d
        train = days != d if mode == "lodo" else days < d
        if train.sum() < 200 or len(set(y[train])) < 2:
            continue
        for out, lmx, base in ((pa, None, lp), (pb, lm, lp), (pc, None, lm)):
            w = fit_logit(design(base[train], None if lmx is None else lmx[train]), y[train])
            out[test] = 1 / (1 + np.exp(-(design(base[test], None if lmx is None else lmx[test]) @ w)))
    mask = ~np.isnan(pa)
    return mask, pa, pb, pc


def boot_mean(vals: np.ndarray, groups: np.ndarray, reps: int, rng: np.random.Generator,
              weights: np.ndarray | None = None) -> tuple[float, float, float]:
    """Mean of vals (weighted by `weights` as denominators) with a cluster bootstrap."""
    w = np.ones_like(vals) if weights is None else weights
    ug, inv = np.unique(groups, return_inverse=True)
    sv = np.bincount(inv, weights=vals, minlength=len(ug))
    sw = np.bincount(inv, weights=w, minlength=len(ug))
    point = sv.sum() / sw.sum()
    idx = rng.integers(0, len(ug), size=(reps, len(ug)))
    stats = sv[idx].sum(1) / sw[idx].sum(1)
    return float(point), float(np.quantile(stats, 0.025)), float(np.quantile(stats, 0.975))


def f3(x: float) -> str:
    return "nan" if x != x else f"{x:.4f}"


def ci(t: tuple[float, float, float], k: int = 4) -> str:
    return f"{t[0]:+.{k}f} [{t[1]:+.{k}f}, {t[2]:+.{k}f}]"


def report(rows: list[dict[str, Any]], reps: int, seed: int) -> dict[str, Any]:
    rng = np.random.default_rng(seed)
    out: dict[str, Any] = {}
    fams = list(FAMILIES) + ["ALL"]
    print(f"rows (sides) {len(rows)}; days {len({r['date'] for r in rows})} "
          f"({min(r['date'] for r in rows)}..{max(r['date'] for r in rows)}); "
          f"matches {len({r['superbet_event_id'] for r in rows})}")
    mbk = np.array([r["minutes_before_kickoff"] for r in rows])
    print(f"price age before kickoff, minutes: p10 {np.quantile(mbk, .1):.0f} median {np.median(mbk):.0f} "
          f"p90 {np.quantile(mbk, .9):.0f}; models: "
          + ", ".join(f"{m} {sum(1 for r in rows if r['model'] == m)}" for m in sorted({str(r['model']) for r in rows})))
    for fam in fams:
        fr = [r for r in rows if fam == "ALL" or r["family"] == fam]
        if not fr:
            continue
        print(f"\n=== {fam} ===")
        res: dict[str, Any] = {}
        # descriptive, per direction
        print("dir    n_lines matches days  overround(mean/med)  p_prop  p_power  model  realised | LL price  LL model | Brier price Brier model | AUC price AUC model")
        for side in ("OVER", "UNDER"):
            s = [r for r in fr if r["side"] == side]
            if not s:
                continue
            y = np.array([r["y"] for r in s], float)
            pp = np.array([r["p_prop"] for r in s])
            pw = np.array([r["p_power"] for r in s])
            pm = np.array([r["model_p"] for r in s])
            ov = np.array([r["overround"] for r in s])
            d = {"n": len(s), "matches": len({r["superbet_event_id"] for r in s}),
                 "days": len({r["date"] for r in s}), "overround_mean": float(ov.mean()),
                 "overround_median": float(np.median(ov)), "p_prop": float(pp.mean()),
                 "p_power": float(pw.mean()), "model": float(pm.mean()), "realised": float(y.mean()),
                 "ll_price": float(ll_vec(pp, y).mean()), "ll_power": float(ll_vec(pw, y).mean()),
                 "ll_model": float(ll_vec(pm, y).mean()),
                 "brier_price": float(((pp - y) ** 2).mean()), "brier_model": float(((pm - y) ** 2).mean()),
                 "auc_price": auc(pp, y), "auc_model": auc(pm, y)}
            res[side] = d
            print(f"{side:5s} {d['n']:7d} {d['matches']:7d} {d['days']:4d}   {d['overround_mean']:.4f}/{d['overround_median']:.4f}"
                  f"      {d['p_prop']:.4f}  {d['p_power']:.4f}  {d['model']:.4f}  {d['realised']:.4f} | "
                  f"{d['ll_price']:.4f}  {d['ll_model']:.4f} | {d['brier_price']:.4f}  {d['brier_model']:.4f} | "
                  f"{f3(d['auc_price'])}  {f3(d['auc_model'])}")
        # calibration by bucket (OVER and UNDER, each scorer)
        for side in ("OVER", "UNDER"):
            s = [r for r in fr if r["side"] == side]
            y = np.array([r["y"] for r in s], float)
            for name, key in (("price", "p_prop"), ("model", "model_p")):
                p = np.array([r[key] for r in s])
                cells = []
                for lo, hi in zip(EDGES, EDGES[1:], strict=False):
                    m = (p >= lo) & (p < hi)
                    if m.sum():
                        cells.append(f"{lo:.2f}-{hi:.2f}: {int(y[m].sum())}/{int(m.sum())} ({y[m].mean():.3f} vs {p[m].mean():.3f})")
                print(f"  calib {side} {name}: " + "; ".join(cells))
                res.setdefault("calibration", {}).setdefault(side, {})[name] = cells
        # OOS blend on OVER-oriented lines (the UNDER is its complement; y_under = 1 - y_over)
        s = [r for r in fr if r["side"] == "OVER"]
        y = np.array([r["y"] for r in s], float)
        lp = logit(np.array([r["p_prop"] for r in s]))
        lm = logit(np.array([r["model_p"] for r in s]))
        days = np.array([r["date"] for r in s])
        grp = np.array([r["superbet_event_id"] for r in s])
        famcol = None
        if fam == "ALL":  # family intercepts and slopes are not pooled: fit per family within folds
            famcol = np.array([r["family"] for r in s])
        for mode in ("lodo", "walk"):
            if famcol is None:
                mask, pa, pb, pc = oos_preds(days, lp, lm, y, mode)
            else:
                mask = np.zeros(len(y), bool)
                pa, pb, pc = (np.full(len(y), np.nan) for _ in range(3))
                for f in FAMILIES:
                    fm = famcol == f
                    m2, a2, b2, c2 = oos_preds(days[fm], lp[fm], lm[fm], y[fm], mode)
                    idx = np.where(fm)[0]
                    mask[idx] = m2
                    pa[idx], pb[idx], pc[idx] = a2, b2, c2
            raw = 1 / (1 + np.exp(-lp))
            yy, g = y[mask], grp[mask]
            l_raw = ll_vec(raw[mask], yy)
            l_a = ll_vec(pa[mask], yy)
            l_b = ll_vec(pb[mask], yy)
            l_c = ll_vec(pc[mask], yy)
            dd: dict[str, Any] = {"n": int(mask.sum()), "matches": int(len(set(g))),
                  "ll_price_raw": float(l_raw.mean()), "ll_price_recal": float(l_a.mean()),
                  "ll_blend": float(l_b.mean()), "ll_model_recal": float(l_c.mean()),
                  "delta_blend_vs_price_recal": boot_mean(l_b - l_a, g, reps, rng),
                  "delta_blend_vs_price_raw": boot_mean(l_b - l_raw, g, reps, rng),
                  "delta_model_recal_vs_price_raw": boot_mean(l_c - l_raw, g, reps, rng),
                  "auc_blend": auc(pb[mask], yy), "auc_price": auc(raw[mask], yy)}
            if famcol is None:
                w = fit_logit(design(lp, lm), y)
                dd["full_sample_coef"] = {"intercept": float(w[0]), "logit_price": float(w[1]), "logit_model": float(w[2])}
            res[f"oos_{mode}"] = dd
            print(f"  OOS {mode}: n {dd['n']} matches {dd['matches']}; LL price raw {dd['ll_price_raw']:.5f}, "
                  f"price recal {dd['ll_price_recal']:.5f}, blend {dd['ll_blend']:.5f}, model recal {dd['ll_model_recal']:.5f}")
            print(f"     dLL blend - price recal {ci(dd['delta_blend_vs_price_recal'], 5)}; "
                  f"blend - price raw {ci(dd['delta_blend_vs_price_raw'], 5)}; model recal - price raw {ci(dd['delta_model_recal_vs_price_raw'], 5)}; "
                  f"AUC blend {dd['auc_blend']:.4f} vs price {dd['auc_price']:.4f}"
                  + (f"; full-sample coef {dd['full_sample_coef']}" if "full_sample_coef" in dd else ""))
        # gap quintiles and ROI, per direction (each side its own bet)
        for side in ("OVER", "UNDER"):
            s = [r for r in fr if r["side"] == side]
            y = np.array([r["y"] for r in s], float)
            pp = np.array([r["p_prop"] for r in s])
            pm = np.array([r["model_p"] for r in s])
            o = np.array([r["odds"] for r in s])
            g = np.array([r["superbet_event_id"] for r in s])
            gap = pm - pp
            qs = np.quantile(gap, [0.2, 0.4, 0.6, 0.8])
            qi = np.searchsorted(qs, gap, side="right")
            qcells: list[dict[str, Any]] = []
            for q in range(5):
                m = qi == q
                rp = boot_mean(y[m] - pp[m], g[m], reps, rng)
                roi = boot_mean(y[m] * o[m] - 1, g[m], reps, rng)
                qcells.append({"q": q + 1, "n": int(m.sum()), "gap_mean": float(gap[m].mean()),
                              "price": float(pp[m].mean()), "realised": float(y[m].mean()),
                              "realised_minus_price": rp, "roi": roi})
            res.setdefault("gap_quintiles", {})[side] = qcells
            print(f"  gap quintiles {side} (model - price): " + " | ".join(
                f"Q{c['q']} n{c['n']} gap{c['gap_mean']:+.3f} real-price {ci(c['realised_minus_price'], 3)} roi {ci(c['roi'], 3)}" for c in qcells))
            rois: list[dict[str, Any]] = []
            for x in GAPS:
                m = gap > x
                if m.sum() < 10:
                    continue
                r_ = boot_mean(y[m] * o[m] - 1, g[m], reps, rng)
                rp = boot_mean(y[m] - pp[m], g[m], reps, rng)
                rois.append({"gap_gt": x, "n": int(m.sum()), "matches": int(len(set(g[m]))), "roi": r_, "realised_minus_price": rp})
            r_all = boot_mean(y * o - 1, g, reps, rng)
            rois.append({"gap_gt": None, "n": len(y), "matches": int(len(set(g))), "roi": r_all})
            res.setdefault("roi", {})[side] = rois
            print(f"  ROI {side}: " + " | ".join(
                f"{'all' if c['gap_gt'] is None else 'gap>' + str(c['gap_gt'])} n{c['n']}/{c['matches']}m {ci(c['roi'], 3)}" for c in rois))
        out[fam] = res
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--from", dest="d0", default="2026-09-28")
    ap.add_argument("--to", dest="d1", default="2026-10-19")
    ap.add_argument("--runs-dir", default=str(_REPO / "runs" / "sofa"))
    ap.add_argument("--db-path", default=str(_REPO / "data" / "sofa.db"),
                    help="opened read-only; '' skips the player-id lookup")
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--reps", type=int, default=2000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--json-out", default=None)
    a = ap.parse_args()
    rows = load(Path(a.runs_dir), a.d0, a.d1, a.db_path or None)
    if not rows:
        print("no rows")
        return 1
    if a.out_dir:
        od = Path(a.out_dir)
        od.mkdir(parents=True, exist_ok=True)
        with gzip.open(od / "cs2_player_lines.jsonl.gz", "wt", encoding="utf-8") as fh:
            for r in rows:
                fh.write(json.dumps(r) + "\n")
        (od / "schema.json").write_text(json.dumps(SCHEMA, indent=1), encoding="utf-8")
    msum = defaultdict(list)
    for r in rows:
        msum[(r["superbet_event_id"], r["family"], r["map_nr"], r["subject"], r["line"])].append(r["model_p"])
    bad = sum(1 for v in msum.values() if len(v) == 2 and abs(sum(v) - 1) > 1e-3)
    multi = sum(1 for r in rows if len(r["player_ids"]) > 1)
    none = sum(1 for r in rows if not r["player_ids"])
    print(f"pairs {sum(1 for v in msum.values() if len(v) == 2)}, model OVER+UNDER != 1: {bad}; "
          f"sides whose nickname has >1 player id in its own series: {multi}; with none found: {none}")
    res = report(rows, a.reps, a.seed)
    if a.json_out:
        Path(a.json_out).write_text(json.dumps(res, indent=1, default=float), encoding="utf-8")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # pragma: no cover
        print(f"FAILED {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
