#!/usr/bin/env python3
"""Read-only measurement: football markets read off the incident list.

Evidence, not a price (a ``measure_*`` script): nothing here writes a config,
a curve, a run artifact or a database row. The question: can sofa price, as
of each match, the incident markets Superbet posts and sofa leaves unmapped
(``market_coverage`` families fb.goal_timing, fb.red_cards, fb.penalties) -

    first_goal   "1. gol": home / away / nikt                     (3 classes)
    fg_band15    "1. gol (przedziały 15-minutowe)": 6 bands + none (7)
    fg_band10    "1. gol (przedziały 10-minutowe)": 9 bands + none (10)
    reds_o05     "Liczba czerwonych kartek" O/U 0.5 (match)
    reds_o15     "Liczba czerwonych kartek" O/U 1.5
    pens_o05     "Liczba przyznanych rzutów karnych" O/U 0.5 (match)
    pens_o15     "Liczba przyznanych rzutów karnych" O/U 1.5

- well enough that the forecasts at >= 0.70 are calibrated (|realised -
forecast| <= 2 pp with n >= 300), the bar for wiring a market?

History. The football history SHEET parses (``data/cache/football_history.pkl``,
read-only; friendlies already out) gives the fixtures, the 90-minute goals and
the rating; the incident lists come from ``sofa_event_stats.incidents_json``
(the database opened ``mode=ro``) through ``bet.sofa.football_incidents``
(regular time only; a first goal whose incident scores do not end on the
listing's 90-minute score is no record; red cards and penalties only from a
full feed - a list with a substitution).

Walk forward. Matches in time order; the rating book (goals_for, as
``measure_football_result_model.collect_rows``) and every frequency are
updated only after the match was priced.

Models.
  first goal   independent NB goals (r from config/sofa_football_result.json,
               the double-chance model's) on the PURE rating centres
               ``FootballForecast.centre("goals_for", side)``: P(none) =
               P(0, 0); P(home first) = (1 - P(none)) * lh / (lh + la).
  bands        a Poisson-process reading of the same match: P(no goal by t)
               = P(none) ** F(t), F(t) the as-of share of all regular-time
               goals scored before minute t (one global goal-time curve).
  reds / pens  ``league``: the competition's as-of rate of the event, shrunk
               toward the gender's as-of rate with BASE_M matches; ``team``:
               a Poisson count whose mean is the mean of the two sides' as-of
               match totals (each shrunk toward the league mean with TEAM_M
               matches).
  base         the gender's as-of frequency (reds / pens) or the
               competition's as-of frequency shrunk toward the gender's
               (first goal, bands).

Report per market: n, log-loss model - base (match bootstrap 95% CI;
negative = the model is better), calibration of every selection by p bucket
with the Wilson 95% lower bound of the realised rate, the share of
selections at p >= 0.70 and the forecast / realised there.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_football_incidents.py \\
        --db /path/to/sofa.db [--history data/cache/football_history.pkl] \\
        [--test-from 2026-06-09] [--test-to 2026-10-14] \\
        [--json-out f] [--md-out f]

Exit 0 OK, 2 on a failure.
"""

from __future__ import annotations

import argparse
import json
import math
import sqlite3
import sys
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import football_rating as fr  # noqa: E402
from bet.sofa.football_incidents import (  # noqa: E402
    FIRST_GOAL_AWAY,
    FIRST_GOAL_HOME,
    FIRST_GOAL_NONE,
    IncidentRecord,
    band_index,
    read_incidents,
)
from bet.sofa.football_result import load_config  # noqa: E402
from scripts.sofa.measure_dependence_goals import load_pickle, note, ts_of  # noqa: E402

F64 = NDArray[np.float64]

DEFAULT_HISTORY = Path("data/cache/football_history.pkl")
BASE_M = 30.0
TEAM_M = 20.0
PRINT_FLOOR = 0.70
CAL_GAP_PP = 2.0
CAL_MIN_N = 300
BAND15 = (0.0, 15.0, 30.0, 45.0, 60.0, 75.0, 1e9)
BAND10 = (0.0, 10.0, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0, 1e9)
FG_CLASSES = (FIRST_GOAL_HOME, FIRST_GOAL_AWAY, FIRST_GOAL_NONE)
BUCKETS = (0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 1.0001)
CURVE_GRID = 181  # w(t) on minutes 0..90 in half-minute steps


# ------------------------------------------------------------------ helpers


def wilson_lower(k: float, n: int, z: float = 1.96) -> float:
    if n <= 0:
        return math.nan
    p = k / n
    den = 1.0 + z * z / n
    centre = p + z * z / (2 * n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (centre - half) / den


def nb_zero(mean: F64 | float, r: float) -> F64:
    m = np.maximum(np.asarray(mean, dtype=np.float64), 0.0)
    out: F64 = np.exp(r * np.log(r / (r + m)))
    return out


def poisson_ge(lam: float, k: int) -> float:
    """P(X >= k), X ~ Poisson(lam)."""
    lam = max(lam, 0.0)
    term, cdf = math.exp(-lam), 0.0
    for i in range(k):
        cdf += term
        term *= lam / (i + 1)
    return max(0.0, 1.0 - cdf)


@dataclass
class Freq:
    n: int = 0
    counts: dict[str, float] = field(default_factory=lambda: defaultdict(float))

    def add(self, key: str, w: float = 1.0) -> None:
        self.counts[key] += w

    def rate(self, key: str) -> float:
        return self.counts.get(key, 0.0) / self.n if self.n else math.nan


def shrunk(
    local: Freq | None, glob: Freq, key: str, m: float = BASE_M, classes: int = 2
) -> float:
    g = (glob.counts.get(key, 0.0) + 0.5) / (glob.n + 0.5 * classes)
    if local is None or local.n == 0:
        return g
    return (local.counts.get(key, 0.0) + m * g) / (local.n + m)


# ------------------------------------------------------------------ data


def load_records(
    db: str, wanted: dict[int, tuple[float, float]]
) -> dict[int, IncidentRecord]:
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    out: dict[int, IncidentRecord] = {}
    seen = 0
    try:
        for eid, raw in conn.execute(
            "SELECT sofascore_event_id, incidents_json FROM sofa_event_stats "
            "WHERE incidents_json IS NOT NULL"
        ):
            goals = wanted.get(eid)
            if goals is None:
                continue
            seen += 1
            try:
                inc = json.loads(raw)
            except ValueError:
                continue
            rec = read_incidents(inc, goals)
            if rec is not None:
                out[eid] = rec
    finally:
        conn.close()
    note(f"incident lists for {seen} history matches, {len(out)} readable")
    return out


# ------------------------------------------------------------------ the walk


def walk(
    history: Sequence[fr.FootballResult],
    records: dict[int, IncidentRecord],
    test_from: int,
    test_to: int,
    r: float,
) -> dict[str, Any]:
    book = fr.RatingBook()
    lg: dict[str, dict[int, Freq]] = defaultdict(dict)  # first goal / bands
    gl: dict[str, dict[bool, Freq]] = defaultdict(lambda: defaultdict(Freq))
    # reds / pens: per competition, gender, team - sums of match totals
    ev_lg: dict[str, dict[int, Freq]] = defaultdict(dict)
    ev_gl: dict[str, dict[bool, Freq]] = defaultdict(lambda: defaultdict(Freq))
    team_tot: dict[str, dict[int, list[float]]] = defaultdict(
        lambda: defaultdict(lambda: [0.0, 0.0])
    )
    goal_minutes = np.zeros(CURVE_GRID)  # histogram of every goal's minute
    n_goal_minutes = 0
    rows: list[dict[str, Any]] = []
    for res in history:
        if res.ts >= test_to:
            break
        g = res.values.get("goals_for")
        rec = records.get(res.event_id)
        if rec is not None and res.ts >= test_from and g is not None:
            row = _price(
                book,
                res,
                rec,
                lg,
                gl,
                ev_lg,
                ev_gl,
                team_tot,
                goal_minutes,
                n_goal_minutes,
                r,
            )
            if row is not None:
                rows.append(row)
        # ---- update after pricing
        if g is not None:
            book.update(replace(res, values={"goals_for": g}))
        if rec is None:
            continue
        for market, key in (
            ("first_goal", rec.first_goal),
            ("band15", str(band_index(rec.first_goal_minute, BAND15))),
            ("band10", str(band_index(rec.first_goal_minute, BAND10))),
        ):
            f = lg[market].setdefault(res.competition_id, Freq())
            f.n += 1
            f.add(key)
            gf = gl[market][res.women]
            gf.n += 1
            gf.add(key)
        for minute in rec.goal_minutes:
            goal_minutes[min(int(minute * 2), CURVE_GRID - 1)] += 1
            n_goal_minutes += 1
        for ev, pair in (("reds", rec.red_cards), ("pens", rec.penalties)):
            if pair is None:
                continue
            tot = float(pair[0] + pair[1])
            for f in (
                ev_lg[ev].setdefault(res.competition_id, Freq()),
                ev_gl[ev][res.women],
            ):
                f.n += 1
                f.add("sum", tot)
                f.add("o05", float(tot >= 1))
                f.add("o15", float(tot >= 2))
            for team in (res.home_id, res.away_id):
                t = team_tot[ev][team]
                t[0] += tot
                t[1] += 1
    return {"rows": rows}


def goal_share(goal_minutes: F64, n: int, t: float) -> float | None:
    """F(t): the as-of share of all regular-time goals scored before minute t
    (the shape of the goal intensity over the match; None below 2,000 goals)."""
    if n < 2000:
        return None
    idx = min(int(t * 2), CURVE_GRID)
    return float(goal_minutes[:idx].sum()) / n


def _price(
    book: fr.RatingBook,
    res: fr.FootballResult,
    rec: IncidentRecord,
    lg: dict[str, dict[int, Freq]],
    gl: dict[str, dict[bool, Freq]],
    ev_lg: dict[str, dict[int, Freq]],
    ev_gl: dict[str, dict[bool, Freq]],
    team_tot: dict[str, dict[int, list[float]]],
    goal_minutes: F64,
    n_goal_minutes: int,
    r: float,
) -> dict[str, Any] | None:
    fc = fr.FootballForecast(book, res.competition_id, res.home_id, res.away_id)
    ch, ca = fc.centre("goals_for", "side_a"), fc.centre("goals_for", "side_b")
    row: dict[str, Any] = {
        "eid": res.event_id,
        "ts": res.ts,
        "women": res.women,
        "comp": res.competition_id,
        "link": fc.fixture_link(),
        "y_fg": FG_CLASSES.index(rec.first_goal),
        "y_b15": band_index(rec.first_goal_minute, BAND15),
        "y_b10": band_index(rec.first_goal_minute, BAND10),
        "full": rec.full_feed,
    }
    # ---- first goal and bands (rated fixtures only)
    if ch is not None and ca is not None:
        lh, la = ch[0], ca[0]
        p00 = float(nb_zero(lh, r) * nb_zero(la, r))
        row["m_fg"] = [(1 - p00) * lh / (lh + la), (1 - p00) * la / (lh + la), p00]
        # A Poisson-process reading of the bands: with P(no goal in 90) = p00
        # and F(t) the as-of share of the goal intensity spent by t,
        # P(no goal by t) = p00 ** F(t).
        shares = {
            t: goal_share(goal_minutes, n_goal_minutes, t)
            for t in {*BAND15[1:-1], *BAND10[1:-1]}
        }
        if all(v is not None for v in shares.values()):
            for name, edges in (("b15", BAND15), ("b10", BAND10)):
                surv = (
                    [1.0]
                    + [p00 ** float(shares[t] or 0.0) for t in edges[1:-1]]
                    + [p00]
                )
                probs = [surv[i] - surv[i + 1] for i in range(len(surv) - 1)]
                probs.append(p00)
                row[f"m_{name}"] = probs
    for name, market, k in (
        ("fg", "first_goal", 3),
        ("b15", "band15", len(BAND15)),
        ("b10", "band10", len(BAND10)),
    ):
        f = lg[market].get(res.competition_id)
        glob = gl[market][res.women]
        keys = [*FG_CLASSES] if name == "fg" else [str(i) for i in range(k)]
        base = [shrunk(f, glob, key, classes=k) for key in keys]
        s = sum(base)
        row[f"b_{name}"] = [b / s for b in base]
    # ---- reds / pens (full feeds only)
    for ev, pair in (("reds", rec.red_cards), ("pens", rec.penalties)):
        if pair is None:
            continue
        tot = pair[0] + pair[1]
        row[f"y_{ev}"] = tot
        glob = ev_gl[ev][res.women]
        if glob.n < 200:
            continue
        loc = ev_lg[ev].get(res.competition_id)
        for line, key in (("o05", "o05"), ("o15", "o15")):
            row[f"b_{ev}_{line}"] = shrunk(None, glob, key)
            row[f"l_{ev}_{line}"] = shrunk(loc, glob, key)
        # team model: Poisson on the mean of the sides' shrunk match totals
        g_mean = glob.counts["sum"] / glob.n
        l_mean = (
            (loc.counts["sum"] + BASE_M * g_mean) / (loc.n + BASE_M)
            if loc is not None
            else g_mean
        )
        sides = []
        for team in (res.home_id, res.away_id):
            t = team_tot[ev].get(team, [0.0, 0.0])
            sides.append((t[0] + TEAM_M * l_mean) / (t[1] + TEAM_M))
        lam = 0.5 * (sides[0] + sides[1])
        row[f"t_{ev}_o05"] = poisson_ge(lam, 1)
        row[f"t_{ev}_o15"] = poisson_ge(lam, 2)
    return row


# ------------------------------------------------------------------ scoring


def _ll(p: F64) -> F64:
    out: F64 = -np.log(np.clip(p, 1e-12, 1.0))
    return out


def boot_ci(delta: F64, reps: int, seed: int = 20261014) -> list[float]:
    if len(delta) == 0:
        return [math.nan, math.nan]
    rng = np.random.default_rng(seed)
    n = len(delta)
    means = np.array([delta[rng.integers(0, n, n)].mean() for _ in range(reps)])
    return [float(np.percentile(means, 2.5)), float(np.percentile(means, 97.5))]


def calib(p: F64, y: F64) -> dict[str, Any]:
    """Buckets of every selection, Wilson lower bound, and the >= 0.70 range."""
    buckets = []
    for lo, hi in zip(BUCKETS[:-1], BUCKETS[1:], strict=True):
        m = (p >= lo) & (p < hi)
        n = int(m.sum())
        if n == 0:
            continue
        k = float(y[m].sum())
        buckets.append(
            {
                "lo": lo,
                "hi": min(hi, 1.0),
                "n": n,
                "p": float(p[m].mean()),
                "realised": k / n,
                "wilson_lo": wilson_lower(k, n),
                "gap_pp": 100.0 * (k / n - float(p[m].mean())),
            }
        )
    hi_m = p >= PRINT_FLOOR
    n_hi = int(hi_m.sum())
    out: dict[str, Any] = {
        "buckets": buckets,
        "n_ge_070": n_hi,
        "share_ge_070": float(hi_m.mean()) if len(p) else math.nan,
    }
    if n_hi:
        k = float(y[hi_m].sum())
        out.update(
            {
                "p_ge_070": float(p[hi_m].mean()),
                "realised_ge_070": k / n_hi,
                "wilson_lo_ge_070": wilson_lower(k, n_hi),
                "gap_ge_070_pp": 100.0 * (k / n_hi - float(p[hi_m].mean())),
            }
        )
        out["calibrated"] = bool(
            n_hi >= CAL_MIN_N and abs(out["gap_ge_070_pp"]) <= CAL_GAP_PP
        )
    else:
        out["calibrated"] = False
    return out


def score_multi(
    rows: Sequence[dict[str, Any]], name: str, ykey: str, reps: int
) -> dict[str, Any]:
    use = [r for r in rows if f"m_{name}" in r]
    if not use:
        return {"n": 0}
    pm = np.array([r[f"m_{name}"] for r in use], dtype=np.float64)
    pb = np.array([r[f"b_{name}"] for r in use], dtype=np.float64)
    y = np.array([r[ykey] for r in use], dtype=np.int64)
    idx = np.arange(len(use))
    llm, llb = _ll(pm[idx, y]), _ll(pb[idx, y])
    onehot = (np.arange(pm.shape[1])[None, :] == y[:, None]).astype(float)
    out = {
        "n": len(use),
        "ll_model": float(llm.mean()),
        "ll_base": float(llb.mean()),
        "d_vs_base": float((llm - llb).mean()),
        "ci": boot_ci(llm - llb, reps),
        "realised_shares": [float(v) for v in onehot.mean(axis=0)],
        "model": calib(pm.reshape(-1), onehot.reshape(-1)),
        "base": calib(pb.reshape(-1), onehot.reshape(-1)),
    }
    # per-class at >= 0.70 (which selection carries the printable mass)
    per: dict[str, Any] = {}
    for c in range(pm.shape[1]):
        m = pm[:, c] >= PRINT_FLOOR
        if m.any():
            per[str(c)] = {
                "n": int(m.sum()),
                "p": float(pm[m, c].mean()),
                "realised": float(onehot[m, c].mean()),
            }
    out["per_class_ge_070"] = per
    return out


def score_binary(
    rows: Sequence[dict[str, Any]], ev: str, line: str, reps: int
) -> dict[str, Any]:
    key = f"b_{ev}_{line}"
    use = [r for r in rows if key in r]
    if not use:
        return {"n": 0}
    k = 1 if line == "o05" else 2
    y = np.array([float(r[f"y_{ev}"] >= k) for r in use])
    out: dict[str, Any] = {"n": len(use), "realised_over": float(y.mean())}
    base = np.array([r[key] for r in use])
    llb = -(y * np.log(base) + (1 - y) * np.log(1 - base))
    out["ll_base"] = float(llb.mean())
    for model, prefix in (("league", "l"), ("team", "t")):
        p = np.clip(np.array([r[f"{prefix}_{ev}_{line}"] for r in use]), 1e-9, 1 - 1e-9)
        llm = -(y * np.log(p) + (1 - y) * np.log(1 - p))
        # both directions of the rung as selections: OVER p, UNDER 1 - p
        flat_p = np.concatenate([p, 1 - p])
        flat_y = np.concatenate([y, 1 - y])
        out[model] = {
            "ll": float(llm.mean()),
            "d_vs_base": float((llm - llb).mean()),
            "ci": boot_ci(llm - llb, reps),
            "calibration": calib(flat_p, flat_y),
        }
    return out


def run(args: argparse.Namespace) -> dict[str, Any]:
    history = load_pickle(Path(args.history))
    note(f"history {len(history)} matches")
    t_from, t_to = ts_of(args.test_from), ts_of(args.test_to)
    wanted = {
        r.event_id: r.values["goals_for"]
        for r in history
        if "goals_for" in r.values and r.ts < t_to
    }
    records = load_records(args.db, wanted)
    r_nb = (
        load_config(args.result_config).nb_r
        if args.result_config
        else load_config().nb_r
    )
    rows = walk(history, records, t_from, t_to, r_nb)["rows"]
    note(f"test rows {len(rows)}")
    out: dict[str, Any] = {
        "history": str(args.history),
        "db": str(args.db),
        "test_from": args.test_from,
        "test_to": args.test_to,
        "nb_r": r_nb,
        "constants": {
            "BASE_M": BASE_M,
            "TEAM_M": TEAM_M,
            "PRINT_FLOOR": PRINT_FLOOR,
            "CAL_GAP_PP": CAL_GAP_PP,
            "CAL_MIN_N": CAL_MIN_N,
        },
        "unfitted_constants": ["BASE_M", "TEAM_M"],
        "records": len(records),
        "test_rows": len(rows),
        "full_feed_rows": sum(1 for r in rows if r["full"]),
    }
    full = [rec for rec in records.values() if rec.full_feed]
    out["full_feed_records"] = len(full)
    out["full_feed_red_match_rate"] = (
        sum(1 for rec in full if rec.red_cards and sum(rec.red_cards) > 0) / len(full)
        if full
        else math.nan
    )
    out["full_feed_pen_match_rate"] = (
        sum(1 for rec in full if rec.penalties and sum(rec.penalties) > 0) / len(full)
        if full
        else math.nan
    )
    out["markets"] = {}
    for split, sel in (
        ("ALL", lambda r: True),
        ("men", lambda r: not r["women"]),
        ("women", lambda r: r["women"]),
        ("unlinked_out", lambda r: r["link"] != fr.UNLINKED),
    ):
        part = [r for r in rows if sel(r)]
        m: dict[str, Any] = {
            "first_goal": score_multi(part, "fg", "y_fg", args.boot),
            "fg_band15": score_multi(part, "b15", "y_b15", args.boot),
            "fg_band10": score_multi(part, "b10", "y_b10", args.boot),
        }
        for ev in ("reds", "pens"):
            for line in ("o05", "o15"):
                m[f"{ev}_{line}"] = score_binary(part, ev, line, args.boot)
        out["markets"][split] = m
    return out


# ------------------------------------------------------------------ markdown


def _ci(c: Sequence[float]) -> str:
    return f"[{1e4 * c[0]:+.0f}, {1e4 * c[1]:+.0f}]"


def _cal_lines(c: dict[str, Any]) -> list[str]:
    lines = [
        "| p | n | śr. p | realizacja | Wilson dolna | różnica pp |",
        "|---|---|---|---|---|---|",
    ]
    for b in c["buckets"]:
        if b["hi"] <= 0.5:
            continue
        lines.append(
            f"| {b['lo']:.2f}-{b['hi']:.2f} | {b['n']} | {b['p']:.3f} | "
            f"{b['realised']:.3f} | {b['wilson_lo']:.3f} | {b['gap_pp']:+.1f} |"
        )
    return lines


def _ge(c: dict[str, Any]) -> str:
    if not c.get("n_ge_070"):
        return "0 selekcji >= 0,70"
    return (
        f"{c['n_ge_070']} selekcji >= 0,70 ({100 * c['share_ge_070']:.1f}%), "
        f"p {c['p_ge_070']:.3f} / realizacja {c['realised_ge_070']:.3f} "
        f"(Wilson {c['wilson_lo_ge_070']:.3f}, {c['gap_ge_070_pp']:+.1f} pp) - "
        f"{'skalibrowane' if c['calibrated'] else 'NIE spełnia progu'}"
    )


def markdown(res: dict[str, Any]) -> str:
    lines = [
        f"# Piłka - rynki z incydentów (pomiar {res['test_from']} .. {res['test_to']})",
        "",
        f"Wiersze testu: {res['test_rows']} (pełny zapis incydentów: "
        f"{res['full_feed_rows']}); NB r {res['nb_r']}. Log-loss w 1e-4 nat, "
        "ujemne = model lepszy od bazy; CI = bootstrap meczów 95%.",
        "",
    ]
    for split, ms in res["markets"].items():
        lines += [
            f"## {split}",
            "",
            "| rynek | n | model - baza [CI] | >= 0,70 |",
            "|---|---|---|---|",
        ]
        for name in ("first_goal", "fg_band15", "fg_band10"):
            m = ms[name]
            if not m.get("n"):
                continue
            lines.append(
                f"| {name} | {m['n']} | {1e4 * m['d_vs_base']:+.0f} {_ci(m['ci'])} "
                f"| {_ge(m['model'])} |"
            )
        for name in ("reds_o05", "reds_o15", "pens_o05", "pens_o15"):
            m = ms[name]
            if not m.get("n"):
                continue
            for model in ("league", "team"):
                lines.append(
                    f"| {name} ({model}) | {m['n']} | "
                    f"{1e4 * m[model]['d_vs_base']:+.0f} {_ci(m[model]['ci'])} | "
                    f"{_ge(m[model]['calibration'])} |"
                )
        lines.append("")
        if split == "ALL":
            for name in ("first_goal",):
                lines += [
                    f"### {name} - kalibracja (każda selekcja)",
                    "",
                    *_cal_lines(ms[name]["model"]),
                    "",
                ]
            for name in ("reds_o05", "pens_o05"):
                for model in ("league", "team"):
                    lines += [
                        f"### {name} ({model}) - kalibracja (OVER i UNDER)",
                        "",
                        *_cal_lines(ms[name][model]["calibration"]),
                        "",
                    ]
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--db", required=True)
    ap.add_argument("--history", default=str(DEFAULT_HISTORY))
    ap.add_argument("--result-config", default=None)
    ap.add_argument("--test-from", default="2026-06-09")
    ap.add_argument("--test-to", default="2026-10-14")
    ap.add_argument("--boot", type=int, default=500)
    ap.add_argument("--json-out", default=None)
    ap.add_argument("--md-out", default=None)
    args = ap.parse_args(argv)
    res = run(args)
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(res, indent=1))
    md = markdown(res)
    if args.md_out:
        Path(args.md_out).write_text(md)
    print(md)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED: {exc!r}", file=sys.stderr)
        raise SystemExit(2) from exc
