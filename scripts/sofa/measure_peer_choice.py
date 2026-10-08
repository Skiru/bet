#!/usr/bin/env python3
"""Which of two legs at the same price is the surer one - the evidence.

Read-only. Nothing here selects, gates or fits anything the pipeline prints;
it is the measurement behind bet.sofa.peer_choice and bet.sofa.stakes
(operator, 2026-10-08: "jak masz dwie nogi po 1.2 to musisz mi zaproponowac te
ktora ma wieksza pewnosc wejscia, na bazie glebokiej analizy statystyk oraz
metadanych jak ranga turnieju").

Sections (--sections, default all but `stakes`, which parses the event
statistics of ~130k matches and takes a few minutes):

  pairs    football / tennis: every pair of legs of ONE match that are different
           variables, priced within PEER_BAND, p_bar >= 0.70, exactly one of
           the two won. How often does the leg a rule prefers win? Rules: the
           pipeline's own number (p_bar), the sample's hit rate, its size,
           total-vs-side, OVER / UNDER, margin in sd, near misses. 95% bands
           are a bootstrap over MATCHES (the pairs of a match are not
           independent).
  features per-leg out-of-sample (leave-one-day-out) log-loss of
           y ~ logit(p_bar) + extra features: sample size, own hit rate, near
           misses, share of the sample from the same competition, tournament
           popularity (Sofascore userCount), reserve / women / cup / national
           flags, venue hit rate, recent form.
  cells    realised minus p_bar per (sport, market, direction) with >= 150
           legs at p_bar >= 0.75, bootstrap over matches.
  sports   hockey / basketball / volleyball: the same pairs on SHADOW's
           Superbet-priced settled sides joined to the replay's p.
  stakes   the football history (data/cache/football_history.pkl) as league
           tables; matches played for something (bet.sofa.stakes) against the
           league-season mean of the others.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_peer_choice.py \\
        [--sections pairs,features,cells,sports] [--md-out f] [--json-out f]

Rows come from `sofa_settled_row` (this pipeline's days, other days under other
rules: a ranking audit, never a fit). Needs numpy and pandas.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sqlite3
import sys
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402
import pandas as pd  # type: ignore[import-untyped]  # noqa: E402

from bet.sofa.peer_choice import PEER_BAND  # noqa: E402

SEED = 20261008
BOOT = 300
MIN_P = 0.70


# ---------------------------------------------------------------- statistics


def boot_ratio(
    num: np.ndarray, den: np.ndarray, cluster: np.ndarray, rounds: int = BOOT
) -> tuple[float, float, float]:
    """sum(num) / sum(den) with a 95% percentile band, resampling whole
    clusters (matches)."""
    _, inv = np.unique(cluster, return_inverse=True)
    sn = np.bincount(inv, weights=num)
    sd = np.bincount(inv, weights=den)
    point = float(sn.sum() / sd.sum())
    rng = np.random.default_rng(SEED)
    k = len(sn)
    draws = []
    for _ in range(rounds):
        idx = rng.integers(0, k, k)
        draws.append(sn[idx].sum() / sd[idx].sum())
    return point, float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))


def rule_accuracy(
    pairs: pd.DataFrame, score_a: pd.Series, score_b: pd.Series
) -> dict[str, Any]:
    """Among the pairs the rule can order (scores differ): how often the leg it
    prefers is the one that won. `pairs.ya` = 1 when leg a won (exactly one
    did); `pairs.cluster` the match."""
    ok = (score_a != score_b).to_numpy()
    q = pairs[ok]
    win = (score_a[ok] > score_b[ok]).to_numpy() == (q.ya == 1).to_numpy()
    if len(q) == 0:
        return {"pairs": 0, "matches": 0, "acc": None, "lo": None, "hi": None}
    acc, lo, hi = boot_ratio(win.astype(float), np.ones(len(q)), q.cluster.to_numpy())
    return {
        "pairs": int(len(q)),
        "matches": int(q.cluster.nunique()),
        "acc": acc,
        "lo": lo,
        "hi": hi,
    }


def make_pairs(
    legs: pd.DataFrame, key: list[str], variable: str, band: float = PEER_BAND
) -> pd.DataFrame:
    """Pairs of legs of one `key` group (a match) that are different
    `variable`s, priced within `band`, exactly one of them won."""
    out: list[dict[str, Any]] = []
    cols = [c for c in legs.columns]
    for gk, g in legs.groupby(key):
        if len(g) < 2:
            continue
        rows = g.to_dict("records")
        for i in range(len(rows)):
            for j in range(i + 1, len(rows)):
                a, b = rows[i], rows[j]
                if a[variable] == b[variable] or a["y"] == b["y"]:
                    continue
                if abs(a["odds"] - b["odds"]) > band + 1e-9:
                    continue
                rec: dict[str, Any] = {
                    "cluster": "|".join(
                        map(str, gk if isinstance(gk, tuple) else (gk,))
                    ),
                    "ya": a["y"],
                }
                for c in cols:
                    rec[f"{c}_a"] = a[c]
                    rec[f"{c}_b"] = b[c]
                out.append(rec)
    return pd.DataFrame(out)


def fit_logit(x: np.ndarray, y: np.ndarray, l2: float = 1.0) -> np.ndarray:
    xx = np.c_[np.ones(len(x)), x]
    w = np.zeros(xx.shape[1])
    pen = np.eye(xx.shape[1]) * l2
    pen[0, 0] = 0.0
    for _ in range(50):
        p = 1.0 / (1.0 + np.exp(-xx @ w))
        h = xx.T @ (xx * (p * (1 - p) + 1e-9)[:, None]) + pen
        w = w + np.linalg.solve(h, xx.T @ (y - p) - pen @ w)
    return w


def predict(w: np.ndarray, x: np.ndarray) -> np.ndarray:
    z: np.ndarray = np.c_[np.ones(len(x)), x] @ w
    return np.asarray(1.0 / (1.0 + np.exp(-z)))


def logloss(y: np.ndarray, p: np.ndarray) -> float:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def auc(y: np.ndarray, p: np.ndarray) -> float:
    r = pd.Series(p).rank().to_numpy()
    n1 = float(y.sum())
    n0 = len(y) - n1
    return float((r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


def cv_by_day(df: pd.DataFrame, cols: list[str]) -> tuple[float, float, int]:
    """Leave-one-day-out log-loss and AUC of y ~ cols."""
    y = df.y.to_numpy(float)
    x = df[cols].to_numpy(float)
    pred = np.full(len(df), np.nan)
    for day in sorted(df.day.unique()):
        te = (df.day == day).to_numpy()
        if te.sum() == 0 or (~te).sum() < 500:
            continue
        mu = x[~te].mean(0)
        sd = x[~te].std(0) + 1e-9
        w = fit_logit((x[~te] - mu) / sd, y[~te])
        pred[te] = predict(w, (x[te] - mu) / sd)
    ok = ~np.isnan(pred)
    return logloss(y[ok], pred[ok]), auc(y[ok], pred[ok]), int(ok.sum())


def logit(p: Any) -> Any:
    p = np.clip(p, 1e-3, 1 - 1e-3)
    return np.log(p / (1 - p))


# ---------------------------------------------------------------------- data


def load_rows(db_path: str) -> pd.DataFrame:
    """Settled football / tennis rungs priced 1.05-1.6, from the live DB read
    read-only (a minute on the full database)."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    df = pd.read_sql_query(
        "select run_date as day, sofascore_event_id as ev, sport, competition_id "
        "as comp, market, subject, line, direction, sample_size as n, "
        "sample_mean as mean, sample_sd as sd, p_central, p_bar, market_p, "
        "outcome, offered_odds as odds from sofa_settled_row "
        "where outcome in ('WIN','LOSS') and offered_odds between 1.05 and 1.6",
        conn,
    )
    conn.close()
    df["subject"] = df.subject.fillna("")
    df["y"] = (df.outcome == "WIN").astype(int)
    return df[df.p_bar >= 0.65].reset_index(drop=True)


def sample_features(rows: pd.DataFrame, runs_dir: str) -> pd.DataFrame:
    """The own-sample features of each row, rebuilt from the day's SAMPLES the
    way CONFIDENCE reads them (run_confidence.side_observations)."""
    from pydantic import RootModel

    from bet.sofa.contracts import Fixture
    from scripts.sofa.run_sheet import determine_side

    out: list[dict[str, Any]] = []
    for day, g in rows.groupby("day"):
        rd = Path(runs_dir) / str(day)
        if (
            not (rd / "03_samples.json").exists()
            or not (rd / "02_fixtures.json").exists()
        ):
            continue
        fx = {
            f.sofascore_event_id: f
            for f in RootModel[list[Fixture]]
            .model_validate_json((rd / "02_fixtures.json").read_bytes())
            .root
        }
        sm = {
            s["sofascore_event_id"]: s
            for s in json.loads((rd / "03_samples.json").read_text("utf-8"))
        }
        for r in g.itertuples():
            f = fx.get(r.ev)
            s = sm.get(r.ev)
            mv = ((s or {}).get("metrics") or {}).get(r.market)
            if not f or not mv:
                continue
            if r.subject:
                side = determine_side(r.subject, f)
                obs = list(mv.get(side) or []) if side else []
            else:
                seen: set[int] = set()
                obs = []
                for k in ("side_a", "side_b", "h2h"):
                    for o in mv.get(k) or []:
                        if o["sofascore_event_id"] not in seen:
                            seen.add(o["sofascore_event_id"])
                            obs.append(o)
            obs = [o for o in obs if o.get("value") is not None]
            if len(obs) < 3:
                continue
            v = np.array([o["value"] for o in obs], float)
            hit = (v > r.line) if r.direction == "OVER" else (v < r.line)
            gap = np.abs(v - r.line)
            rec: dict[str, Any] = {
                "day": day,
                "ev": r.ev,
                "sport": r.sport,
                "comp": f.competition_id,
                "market": r.market,
                "subject": r.subject,
                "line": r.line,
                "direction": r.direction,
                "n": len(v),
                "k": int(hit.sum()),
                "hr": float(hit.mean()),
                "near": int((~hit & (gap <= 1.0)).sum()),
                "worst": float(np.where(~hit, gap, 0).max()),
                "comp_same": float(
                    np.mean([o.get("competition_id") == f.competition_id for o in obs])
                ),
                "mean": float(v.mean()),
                "sd": float(v.std(ddof=1)) if len(v) > 1 else float("nan"),
                "p_bar": r.p_bar,
                "odds": r.odds,
                "y": r.y,
                "cname": f.competition_name or "",
                "natl": bool(f.national_teams),
            }
            if r.subject and r.sport == "football" and len(obs) >= 6:
                today = "home" if determine_side(r.subject, f) == "side_a" else "away"
                ven = np.array([o.get("venue") == today for o in obs])
                order = np.argsort(pd.to_datetime([o["match_date_utc"] for o in obs]))[
                    ::-1
                ]
                rec["hr_venue"] = float(hit[ven].mean()) if ven.sum() >= 3 else np.nan
                rec["hr_recent"] = float(hit[order][:5].mean())
            out.append(rec)
    df = pd.DataFrame(out)
    df["side"] = (df.subject != "").astype(int)
    df["var"] = df.market + "|" + df.subject
    df["lp"] = logit(df.p_bar)
    df["lh"] = logit((df.k + 1) / (df.n + 2))
    df["small"] = (df.n <= 10).astype(int)
    z = np.where(df.direction == "OVER", df["mean"] - df.line, df.line - df["mean"])
    df["z"] = (
        pd.Series(z / df.sd.replace(0, np.nan), index=df.index).fillna(0).clip(-5, 5)
    )
    df["pc_gap"] = df.p_bar - df.hr
    df["worst"] = df.worst.clip(0, 10)
    return df


# ------------------------------------------------------------------ sections


def section_pairs(feat: pd.DataFrame) -> dict[str, Any]:
    legs = feat[(feat.p_bar >= MIN_P) & (feat.odds <= 1.6)].reset_index(drop=True)
    pr = make_pairs(
        legs[
            [
                "day",
                "ev",
                "sport",
                "var",
                "odds",
                "y",
                "p_bar",
                "hr",
                "n",
                "side",
                "z",
                "near",
            ]
        ].assign(over=(legs.direction == "OVER").astype(int)),
        ["day", "ev"],
        "var",
    )
    out: dict[str, Any] = {"pairs_total": int(len(pr))}
    for sport in ("football", "tennis", "all"):
        q = pr if sport == "all" else pr[pr.sport_a == sport]
        q = q.reset_index(drop=True)
        rules = {
            "p_bar (the pipeline's confidence)": (q.p_bar_a, q.p_bar_b),
            "own hit rate k/n": (q.hr_a, q.hr_b),
            "larger own sample n": (q.n_a, q.n_b),
            "total preferred over a side": (-q.side_a, -q.side_b),
            "OVER preferred": (q.over_a, q.over_b),
            "UNDER preferred": (-q.over_a, -q.over_b),
            "larger margin in sd": (q.z_a, q.z_b),
            "fewer near misses": (-q.near_a, -q.near_b),
        }
        res = {k: rule_accuracy(q, a, b) for k, (a, b) in rules.items()}
        gap = (q.p_bar_a - q.p_bar_b).abs()
        res["p_bar, gap >= 0.04"] = rule_accuracy(
            q[gap >= 0.04].reset_index(drop=True),
            q[gap >= 0.04].p_bar_a.reset_index(drop=True),
            q[gap >= 0.04].p_bar_b.reset_index(drop=True),
        )
        out[sport] = res
    return out


FEATURE_SETS = {
    "p_bar only": ["lp"],
    "+ own hit rate": ["lp", "lh"],
    "+ sample size / side": ["lp", "small", "side"],
    "+ near misses": ["lp", "near", "worst"],
    "+ share of sample from this competition": ["lp", "comp_same"],
    "+ model - sample gap": ["lp", "pc_gap"],
    "+ margin in sd": ["lp", "z"],
    "everything above": [
        "lp",
        "lh",
        "small",
        "side",
        "near",
        "worst",
        "comp_same",
        "pc_gap",
        "z",
    ],
}


def competition_meta(db_path: str, runs_dir: str) -> dict[str, Any]:
    """competition_id -> {users}: Sofascore's own popularity count of the
    tournament (`uniqueTournament.userCount`), from one listed event of each
    competition the fixtures name. Competitions whose events are not in the
    listing table have none."""
    rep: dict[int, int] = {}
    for f in sorted(glob.glob(f"{runs_dir}/*/02_fixtures.json")):
        try:
            for x in json.load(open(f, encoding="utf-8")):
                rep[x["competition_id"]] = x["sofascore_event_id"]
        except (OSError, ValueError, KeyError):
            continue
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    out: dict[str, Any] = {}
    for cid, ev in rep.items():
        r = conn.execute(
            "select event_json from sofa_listed_event where event_id=?", (ev,)
        ).fetchone()
        if not r:
            continue
        e = json.loads(r[0])
        e = e.get("event", e)
        u = (e.get("tournament") or {}).get("uniqueTournament") or {}
        if u.get("id") == cid:
            out[str(cid)] = {"users": u.get("userCount")}
    conn.close()
    return out


def section_features(feat: pd.DataFrame, comp_meta: dict[str, Any]) -> dict[str, Any]:
    d = feat[(feat.p_bar >= MIN_P) & (feat.odds <= 1.6)].copy()
    out: dict[str, Any] = {}
    users = d.comp.map(lambda c: (comp_meta.get(str(c)) or {}).get("users"))
    d["has_u"] = users.notna().astype(int)
    d["lu"] = np.log10(users.fillna(users.median()) + 1)
    nm = d.cname.str.lower()
    d["reserve"] = nm.str.contains("reserve|u1[0-9]|u2[0-9]|youth|junior|sub-").astype(
        int
    )
    d["women"] = nm.str.contains("women|femin|w75|w50|w25|w15|w100|w35|w60").astype(int)
    d["cup"] = nm.str.contains(
        "cup|copa|pokal|coupe|knockout|play-?off|relegation|promotion"
    ).astype(int)
    d["natl"] = d.natl.astype(int)
    meta = {
        "+ tournament popularity (Sofascore userCount)": ["lp", "lu", "has_u"],
        "+ reserve / women / cup": ["lp", "reserve", "women", "cup"],
        # National-team matches come in a few days of the history: a fold that
        # holds one is predicted from days that hold none (a flag that does not
        # generalise, not a flag that helps).
        "+ national team": ["lp", "natl"],
    }
    for sport in ("football", "tennis"):
        x = d[d.sport == sport].reset_index(drop=True)
        res = {}
        for name, cols in {**FEATURE_SETS, **meta}.items():
            ll, au, n = cv_by_day(x, cols)
            res[name] = {"logloss": ll, "auc": au, "n": n}
        out[sport] = res
    fx = d[(d.sport == "football") & (d.side == 1)].dropna(subset=["hr_venue"]).copy()
    fx["lv"] = logit(np.clip(fx.hr_venue, 0.05, 0.95))
    fx["lr"] = logit(np.clip(fx.hr_recent, 0.05, 0.95))
    fx = fx.reset_index(drop=True)
    out["football_side_form"] = {
        name: dict(zip(("logloss", "auc", "n"), cv_by_day(fx, cols)))
        for name, cols in {
            "p_bar only": ["lp"],
            "+ venue hit rate": ["lp", "lv"],
            "+ last-5 hit rate": ["lp", "lr"],
        }.items()
    }
    return out


def section_cells(feat: pd.DataFrame) -> list[dict[str, Any]]:
    d = feat[(feat.p_bar >= 0.75) & (feat.odds <= 1.6)].copy()
    d["cell"] = d.sport + "|" + d.market + "|" + d.direction
    out = []
    for cell, g in d.groupby("cell"):
        if len(g) < 150 or g.ev.nunique() < 60:
            continue
        cl = (g.day + g.ev.astype(str)).to_numpy()
        gap, lo, hi = boot_ratio((g.y - g.p_bar).to_numpy(), np.ones(len(g)), cl)
        out.append(
            {
                "cell": cell,
                "legs": int(len(g)),
                "matches": int(g.ev.nunique()),
                "p": float(g.p_bar.mean()),
                "hit": float(g.y.mean()),
                "gap": gap,
                "lo": lo,
                "hi": hi,
            }
        )
    return sorted(out, key=lambda r: r["gap"])


def section_sports(runs_dir: str, evidence_dir: str) -> dict[str, Any]:
    res: dict[str, Any] = {}
    allp = []
    for sport in ("basketball", "hockey", "volleyball"):
        p: dict[tuple[Any, ...], float] = {}
        path = Path(evidence_dir) / f"{sport}_superbet_settled.jsonl"
        if not path.exists():
            continue
        for line in path.open(encoding="utf-8"):
            r = json.loads(line)
            p[
                (
                    r["date"],
                    r["game"].split(":")[-1],
                    r["family"],
                    r["period"],
                    r["subject"],
                    r["line"],
                    r["side"],
                )
            ] = r["p"]
        legs = []
        for f in sorted(glob.glob(f"{runs_dir}/shadow/{sport}/*/settled.json")):
            day = f.split("/")[-2]
            try:
                d = json.load(open(f, encoding="utf-8"))
            except (OSError, ValueError):
                continue
            for e in d["events"].values():
                for g in e.get("graded") or []:
                    if g.get("outcome") not in ("WIN", "LOSS"):
                        continue
                    k = (
                        day,
                        str(g["superbet_event_id"]),
                        g["family"],
                        g["period"],
                        g["subject"],
                        g["line"],
                        g["side"],
                    )
                    if k in p and p[k] >= MIN_P and g["odds"] <= 1.6:
                        legs.append(
                            {
                                "sport": sport,
                                "day": day,
                                "ev": g["superbet_event_id"],
                                "var": f"{g['family']}|{g['period']}|{g['subject']}",
                                "odds": g["odds"],
                                "p": p[k],
                                "y": int(g["outcome"] == "WIN"),
                            }
                        )
        df = pd.DataFrame(legs)
        if df.empty:
            continue
        pr = make_pairs(df, ["sport", "day", "ev"], "var")
        if pr.empty:
            continue
        res[sport] = {
            "legs": int(len(df)),
            "p": float(df.p.mean()),
            "hit": float(df.y.mean()),
            **rule_accuracy(pr, pr.p_a, pr.p_b),
        }
        allp.append(pr)
    if allp:
        pr = pd.concat(allp, ignore_index=True)
        res["all"] = rule_accuracy(pr, pr.p_a, pr.p_b)
    return res


def stakes_tables(history_pkl: str) -> pd.DataFrame:
    """One pass over every league-season: the stakes flags of each match as of
    its kickoff (progress >= bet.sofa.stakes.MIN_PROGRESS, >= MIN_TEAMS)."""
    import pickle
    from collections import defaultdict

    from bet.sofa import stakes as st

    _, history = pickle.loads(Path(history_pkl).read_bytes())
    tables = st.build_tables(history)
    out = []
    for (comp, season), matches in tables.items():
        teams = {t for m in matches for t in (m[1], m[2])}
        n = len(teams)
        if n < st.MIN_TEAMS or len(matches) < n * 3:
            continue
        pts: dict[int, int] = defaultdict(int)
        played: dict[int, int] = defaultdict(int)
        zone = 3 if n <= 16 else 4
        full = 2 * (n - 1)
        for ts, h, a, hg, ag in matches:
            if sum(played.values()) / n / full >= st.MIN_PROGRESS and len(pts) == n:
                order = sorted(pts, key=lambda t: -pts[t])
                line = (pts[order[n - zone - 1]] + pts[order[n - zone]]) / 2
                top = (pts[order[3]] + pts[order[4]]) / 2
                out.append(
                    (
                        comp,
                        season,
                        ts,
                        h,
                        a,
                        abs(pts[h] - line) <= st.NEAR_POINTS
                        and abs(pts[a] - line) <= st.NEAR_POINTS,
                        abs(pts[h] - top) <= st.NEAR_POINTS
                        and abs(pts[a] - top) <= st.NEAR_POINTS,
                    )
                )
            pts[h] += 3 if hg > ag else 1 if hg == ag else 0
            pts[a] += 3 if ag > hg else 1 if hg == ag else 0
            played[h] += 1
            played[a] += 1
    return pd.DataFrame(out, columns=["comp", "season", "ts", "h", "a", "six", "top"])


def section_stakes(db_path: str, history_pkl: str) -> dict[str, Any]:
    fl = stakes_tables(history_pkl)
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    # the pickle has no event id in the flag table: join on (ts, teams) through history
    import pickle

    _, history = pickle.loads(Path(history_pkl).read_bytes())
    key = {
        (r.competition_id, r.season_id, r.ts, r.home_id, r.away_id): r.event_id
        for r in history
        if getattr(r, "season_id", None) is not None
    }
    fl["ev"] = [
        key.get((c, s, t, h, a))
        for c, s, t, h, a in zip(fl.comp, fl.season, fl.ts, fl.h, fl.a, strict=True)
    ]
    fl = fl.dropna(subset=["ev"]).astype({"ev": int})
    rows = []
    for i in range(0, len(fl), 500):
        chunk = fl.ev.iloc[i : i + 500].tolist()
        q = ",".join("?" * len(chunk))
        for ev, js in conn.execute(
            f"select sofascore_event_id, statistics_json from sofa_event_stats "
            f"where sofascore_event_id in ({q}) and statistics_json is not null",
            chunk,
        ):
            try:
                d = json.loads(js)
            except ValueError:
                continue
            vals: dict[str, float] = {}
            for per in d.get("statistics", []):
                if per.get("period") != "ALL":
                    continue
                for gr in per.get("groups", []):
                    for it in gr.get("statisticsItems", []):
                        if it.get("key") in (
                            "cornerKicks",
                            "fouls",
                            "yellowCards",
                            "redCards",
                            "totalShotsOnGoal",
                            "shotsOnGoal",
                        ):
                            try:
                                vals[it["key"]] = float(it["homeValue"]) + float(
                                    it["awayValue"]
                                )
                            except (KeyError, TypeError, ValueError):
                                pass
            if "cornerKicks" in vals:
                rows.append({"ev": ev, **vals})
    conn.close()
    st = pd.DataFrame(rows)
    g = {
        r.event_id: sum(r.values["goals_for"])
        for r in history
        if r.values.get("goals_for")
    }
    d = fl.merge(st, on="ev")
    d["goals"] = d.ev.map(g)
    d["cards"] = d.get("yellowCards", 0).fillna(0) + d.get("redCards", 0).fillna(0)
    d["ls"] = d.comp.astype(str) + "_" + d.season.astype(str)
    rename = {
        "fouls": "fouls",
        "cornerKicks": "corners",
        "totalShotsOnGoal": "shots",
        "shotsOnGoal": "sot",
    }
    d = d.rename(columns=rename)
    out: dict[str, Any] = {
        "matches_with_stats": int(len(d)),
        "league_seasons": int(d.ls.nunique()),
    }
    rng = np.random.default_rng(SEED)
    for flag in ("six", "top"):
        res = {}
        for m in ("cards", "fouls", "corners", "goals", "shots", "sot"):
            x = d.dropna(subset=[m]).copy()
            base = x[~x[flag]].groupby("ls")[m].mean()
            x["res"] = x[m] - x.ls.map(base)
            x = x.dropna(subset=["res"])
            a, b = x[x[flag]], x[~x[flag]]
            groups = {k: v for k, v in x.groupby("ls")}
            keys = list(groups)
            draws = []
            for _ in range(BOOT):
                pick = [groups[keys[i]] for i in rng.integers(0, len(keys), len(keys))]
                p = pd.concat(pick)
                draws.append(p[p[flag]].res.mean() - p[~p[flag]].res.mean())
            res[m] = {
                "flagged": int(len(a)),
                "diff": float(a.res.mean() - b.res.mean()),
                "lo": float(np.percentile(draws, 2.5)),
                "hi": float(np.percentile(draws, 97.5)),
                "sd_units": float((a.res.mean() - b.res.mean()) / x[m].std()),
            }
        out[flag] = res
    return out


# -------------------------------------------------------------------- report


def pct(x: float | None) -> str:
    return "-" if x is None else f"{100 * x:.1f}%"


def render(res: dict[str, Any]) -> str:
    lines = [
        "# Która z dwóch nóg po tym samym kursie jest pewniejsza - pomiar",
        "",
        "Wygenerowane przez `scripts/sofa/measure_peer_choice.py` (tylko odczyt)."
        f" Para = dwie różne zmienne jednego meczu, kurs w pasie ±{PEER_BAND}, "
        f"`p_bar` ≥ {MIN_P}, dokładnie jedna z dwóch weszła; przedziały 95% to "
        "bootstrap po meczach.",
        "",
    ]
    if "pairs" in res:
        lines += ["## 1. Którą nogę wskazuje reguła i jak często ta noga wygrywa", ""]
        for sport in ("football", "tennis", "all"):
            lines += [
                f"### {sport}",
                "",
                "| reguła | par | meczów | trafia | 95% |",
                "|---|---|---|---|---|",
            ]
            for rule, r in res["pairs"][sport].items():
                lines.append(
                    f"| {rule} | {r['pairs']} | {r['matches']} | {pct(r['acc'])} | "
                    f"[{pct(r['lo'])}; {pct(r['hi'])}] |"
                )
            lines.append("")
    if "features" in res:
        lines += [
            "## 2. Czy jakakolwiek cecha poprawia pewność poza próbą",
            "",
            "Leave-one-day-out, log-loss (niżej = lepiej) i AUC.",
            "",
        ]
        for sport in ("football", "tennis", "football_side_form"):
            lines += [
                f"### {sport}",
                "",
                "| cechy | log-loss | AUC | nóg |",
                "|---|---|---|---|",
            ]
            for name, r in res["features"][sport].items():
                lines.append(
                    f"| {name} | {r['logloss']:.4f} | {r['auc']:.4f} | {r['n']} |"
                )
            lines.append("")
    if "cells" in res:
        lines += [
            "## 3. Rynki: zrealizowane minus `p_bar` (p_bar ≥ 0,75, ≥150 nóg)",
            "",
            "| komórka | nóg | meczów | p | trafia | różnica | 95% |",
            "|---|---|---|---|---|---|---|",
        ]
        for r in res["cells"]:
            lines.append(
                f"| {r['cell']} | {r['legs']} | {r['matches']} | {r['p']:.3f} | "
                f"{r['hit']:.3f} | {r['gap']:+.3f} | [{r['lo']:+.3f}; {r['hi']:+.3f}] |"
            )
        lines.append("")
    if "sports" in res:
        lines += [
            "## 4. Hokej, koszykówka, siatkówka (nogi z ceną Superbetu + p z repleju)",
            "",
            "| sport | nóg | p | trafia | par | gier | wyższe p wygrywa | 95% |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for sport, r in res["sports"].items():
            lines.append(
                f"| {sport} | {r.get('legs', '-')} | "
                f"{'-' if 'p' not in r else format(r['p'], '.3f')} | "
                f"{'-' if 'hit' not in r else format(r['hit'], '.3f')} | "
                f"{r['pairs']} | "
                f"{r['matches']} | {pct(r['acc'])} | [{pct(r['lo'])}; {pct(r['hi'])}] |"
            )
        lines.append("")
    if "stakes" in res:
        s = res["stakes"]
        lines += [
            "## 5. Mecz o coś (bet.sofa.stakes): reszta względem średniej ligi-sezonu",
            "",
            f"{s['matches_with_stats']} meczów ze statystykami w {s['league_seasons']} "
            "ligosezonach; bootstrap po ligosezonach.",
            "",
        ]
        for flag, title in (("six", "STAKES_SIX_POINTER"), ("top", "STAKES_TOP4")):
            lines += [
                f"### {title}",
                "",
                "| statystyka | meczów | różnica | 95% | w sd |",
                "|---|---|---|---|---|",
            ]
            for m, r in s[flag].items():
                lines.append(
                    f"| {m} | {r['flagged']} | {r['diff']:+.3f} | "
                    f"[{r['lo']:+.3f}; {r['hi']:+.3f}] | {r['sd_units']:+.2f} |"
                )
            lines.append("")
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db-path", default=os.environ.get("SOFA_DB_PATH", "data/sofa.db"))
    ap.add_argument("--runs-dir", default=os.environ.get("SOFA_RUNS_DIR", "runs/sofa"))
    ap.add_argument(
        "--evidence-dir", default="data/line_evidence/rows_before_2026-10-08"
    )
    ap.add_argument("--sections", default="pairs,features,cells,sports")
    ap.add_argument("--history-pkl", default="data/cache/football_history.pkl")
    ap.add_argument("--md-out", default=None)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()
    want = {s.strip() for s in args.sections.split(",") if s.strip()}
    res: dict[str, Any] = {}
    feat = None
    if want & {"pairs", "features", "cells"}:
        rows = load_rows(args.db_path)
        feat = sample_features(rows, args.runs_dir)
        print(
            f"legs with a rebuilt sample: {len(feat)} on {feat.day.nunique()} days",
            file=sys.stderr,
        )
    if feat is not None and "pairs" in want:
        res["pairs"] = section_pairs(feat)
    if feat is not None and "features" in want:
        meta = competition_meta(args.db_path, args.runs_dir)
        res["features"] = section_features(feat, meta)
    if feat is not None and "cells" in want:
        res["cells"] = section_cells(feat)
    if "sports" in want:
        res["sports"] = section_sports(args.runs_dir, args.evidence_dir)
    if "stakes" in want:
        res["stakes"] = section_stakes(args.db_path, args.history_pkl)
    md = render(res)
    if args.md_out:
        Path(args.md_out).write_text(md, encoding="utf-8")
    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps(res, indent=1, default=float), "utf-8"
        )
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
