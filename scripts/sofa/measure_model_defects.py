#!/usr/bin/env python3
"""The deferred model defects and the context features, measured out of sample.

Plan docs/sofa/PLAN_2026-10-05_PRODUCTION_GRADE.md, F2.2 and F3.2. Every
measurement here is offline: the DB is opened read-only, nothing the pipeline
reads is written, and no constant is fitted into config/. The report is
docs/sofa/evidence/model_defects_2026-10-05.md.

Subcommands (each prints a markdown table; --out appends it to a file):

  nb-variance --sport football|tennis
      SHEET's negative binomial at a centre the prior has moved: the sample's
      raw variance (the 09-25 defect) against the dispersion-preserving
      variance (engine.sheet_predictive_sd, football since 2026-10-02). The
      centre is the K_CENTRE shrink to the prior SHEET uses (football: the
      competition baseline of config/sofa_league_baselines.json; tennis: the
      tier baseline of config/sofa_tennis_tier_baselines.json), the sample is
      SAMPLES' (football: comparability's same-competition goal rule; tennis:
      the player's last ten best-of-three matches on a comparable surface).
      Scored by the NB log-loss of the realised count and the Brier score of
      P(value > line) on the metric's usual lines.

  promotion
      A side whose sample holds league matches of ANOTHER league of its own
      country and who has never played the fixture's league before this
      season (promoted or relegated): the usual sample against the same
      sample without the other division's matches.

  context --feature knockout|round|rest|referee|missing
      One context feature at a time, as a multiplicative correction of the
      sample mean, log(lam) = log(sample mean) + a + b . x, fitted on one
      event-id half and scored on the other (both ways). Compared with the
      intercept alone (a), so a global bias of the sample mean is never
      credited to the feature.

  bench-cards
      Cards to unused substitutes (Superbet's rules do not count them; the
      staff cards have been dropped since 2026-10-02) - how often and how
      much, on the events whose /lineups are cached.

Lower is better in every column; d = candidate - current; 95% intervals
resample whole matches (scripts/sofa/measure_sample_composition.paired_interval).

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_model_defects.py \\
        --db /path/to/sofa.db nb-variance --sport football [--out f.md]
"""

from __future__ import annotations

import argparse
import bisect
import json
import math
import sqlite3
import statistics
import sys
from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402

from bet.sofa.comparability import (  # noqa: E402
    SAME_COMPETITION_METRICS,
    MatchKind,
    is_friendly_event,
    pick_same_competition,
)
from bet.sofa.engine import (  # noqa: E402
    nb_survival,
    predictive_sd,
    sheet_predictive_sd,
)
from bet.sofa.metrics import (  # noqa: E402
    extract_flat_statistics,
    extract_metric,
    infer_best_of,
)
from bet.sofa.schedule import CONGESTED_7D, LONG_LAYOFF_DAYS  # noqa: E402
from bet.sofa.settle import is_completed_event, surfaces_comparable  # noqa: E402
from bet.sofa.tennis_prior import tier_key  # noqa: E402
from scripts.sofa.measure_sample_composition import (  # noqa: E402
    LINES,
    Past,
    Target,
    before,
    load,
    paired_interval,
    poisson_logloss,
)

DB = Path("data/sofa.db")
BASELINES = _REPO / "config" / "sofa_league_baselines.json"
TIER_BASELINES = _REPO / "config" / "sofa_tennis_tier_baselines.json"
ENGINE_CONSTANTS = _REPO / "config" / "sofa_engine_constants.json"
SEED = 20261005

# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def nb_logpmf(y: int, mean: float, var: float) -> float:
    """log P(X = y) of the count SHEET prices: NB above the mean, Poisson at it."""
    mean = max(mean, 1e-6)
    if var <= mean * (1.0 + 1e-9):
        return -mean + y * math.log(mean) - math.lgamma(y + 1)
    r = mean * mean / (var - mean)
    p = r / (r + mean)
    return (
        math.lgamma(y + r) - math.lgamma(r) - math.lgamma(y + 1)
        + r * math.log(p) + y * math.log1p(-p)
    )


def nb_scores(mean: float, sd: float, y: float, lines: Sequence[float]) -> list[float]:
    """[NB log-loss, Brier of P(> line) for each line] of one forecast."""
    var = sd * sd
    out = [-nb_logpmf(int(round(y)), mean, var)]
    for line in lines:
        p_over = nb_survival(mean, var, math.floor(line))
        out.append((p_over - (1.0 if y > line else 0.0)) ** 2)
    return out


def interval_table(
    title: str,
    cols: Sequence[str],
    base: np.ndarray,
    cand: np.ndarray,
    ids: np.ndarray,
    mask: np.ndarray | None = None,
) -> list[str]:
    """One markdown block: current, candidate, d with a 95% interval per
    column, and the d of the two event-id halves on the first column."""
    if mask is not None:
        base, cand, ids = base[mask], cand[mask], ids[mask]
    if len(ids) == 0:
        return [f"### {title}: no case", ""]
    rng = np.random.default_rng(SEED)
    out = [
        f"### {title}: {len(ids)} cases, {len(set(ids.tolist()))} matches", "",
        "| column | current | candidate | d [95%] | d even id | d odd id |",
        "|---|---|---|---|---|---|",
    ]
    parity = ids % 2
    for j, col in enumerate(cols):
        diff = cand[:, j] - base[:, j]
        lo, hi = paired_interval(diff, ids, rng)
        even = diff[parity == 0].mean() if (parity == 0).any() else float("nan")
        odd = diff[parity == 1].mean() if (parity == 1).any() else float("nan")
        out.append(
            f"| {col} | {base[:, j].mean():.5f} | {cand[:, j].mean():.5f} | "
            f"{diff.mean():+.5f} [{lo:+.5f}; {hi:+.5f}] | {even:+.5f} | {odd:+.5f} |"
        )
    out.append("")
    return out


# ---------------------------------------------------------------------------
# A Poisson GLM with an offset - the context features' correction
# ---------------------------------------------------------------------------


def poisson_glm(
    x: np.ndarray, y: np.ndarray, offset: np.ndarray, iters: int = 50,
    ridge: float = 1e-6,
) -> np.ndarray:
    """beta of log E[y] = offset + x . beta, by Newton (IRLS)."""
    beta = np.zeros(x.shape[1])
    beta[0] = math.log(max(y.sum(), 1e-9) / max(np.exp(offset).sum(), 1e-9))
    for _ in range(iters):
        eta = np.clip(offset + x @ beta, -30, 30)
        mu = np.exp(eta)
        grad = x.T @ (y - mu)
        hess = (x * mu[:, None]).T @ x + ridge * np.eye(x.shape[1])
        step = np.linalg.solve(hess, grad)
        beta += step
        if np.max(np.abs(step)) < 1e-9:
            break
    return beta


def crossfit_feature(
    lam0: np.ndarray, y: np.ndarray, x: np.ndarray, ids: np.ndarray
) -> tuple[np.ndarray, np.ndarray, list[np.ndarray]]:
    """Poisson log-loss per case of the intercept-only correction and of the
    intercept + feature correction, each fitted on the other event-id half.

    `x` holds the feature columns only (no intercept). Returns (base loss,
    feature loss, the feature betas fitted on each half)."""
    offset = np.log(np.maximum(lam0, 0.05))
    ones = np.ones((len(y), 1))
    full = np.hstack([ones, x])
    base_loss = np.empty(len(y))
    feat_loss = np.empty(len(y))
    betas: list[np.ndarray] = []
    fold = ids % 2
    for f in (0, 1):
        train, test = fold != f, fold == f
        if not train.any() or not test.any():
            continue
        b0 = poisson_glm(ones[train], y[train], offset[train])
        b1 = poisson_glm(full[train], y[train], offset[train])
        betas.append(b1)
        for loss, design, beta in ((base_loss, ones, b0), (feat_loss, full, b1)):
            lam = np.exp(np.clip(offset[test] + design[test] @ beta, -30, 30))
            loss[test] = [poisson_logloss(float(m), float(k))
                          for m, k in zip(lam, y[test], strict=True)]
    return base_loss, feat_loss, betas


def one_hot(labels: Sequence[str], reference: str) -> tuple[np.ndarray, list[str]]:
    """Dummy columns of every label but `reference`."""
    names = sorted({lab for lab in labels if lab != reference})
    x = np.zeros((len(labels), len(names)))
    index = {n: i for i, n in enumerate(names)}
    for row, lab in enumerate(labels):
        if lab in index:
            x[row, index[lab]] = 1.0
    return x, names


# ---------------------------------------------------------------------------
# Football samples, read as SAMPLES reads them
# ---------------------------------------------------------------------------


def football_sample(
    history: Sequence[Past], t: Target, metric: str, n: int = 10
) -> list[Past]:
    """SAMPLES' sample of one side: friendlies out, the goal markets from the
    fixture's competition on a league fixture (comparability)."""
    b = before(history, t.ts, metric)
    if metric in SAME_COMPETITION_METRICS and t.kind is MatchKind.REGULAR:
        picked = pick_same_competition(
            b, t.competition, n, lambda p: p.competition,
            lambda p: p.kind is MatchKind.REGULAR,
        )
        if picked is not None:
            return picked
    return [p for p in b if p.kind is not MatchKind.FRIENDLY][:n]


def window(targets: Iterable[Target], start: str, end: str) -> list[Target]:
    lo = int(datetime.fromisoformat(start).replace(tzinfo=UTC).timestamp())
    hi = int(datetime.fromisoformat(end).replace(tzinfo=UTC).timestamp()) + 86400
    return [t for t in targets if lo <= t.ts < hi]


def side_cases(
    history: dict[int, list[Past]], t: Target, metric: str, minimum: int = 5
) -> list[tuple[list[float], float, int]]:
    """(sample values, realised, team) per case: one per match for a total
    (the two sides' pooled values, as SHEET pools them), one per side for a
    `_for`. A side below `minimum` gives no case."""
    stat, _, scope = metric.rpartition("_")
    pair = t.values.get(stat)
    if pair is None:
        return []
    a = football_sample(history.get(t.home, []), t, metric)
    b = football_sample(history.get(t.away, []), t, metric)
    if scope == "total":
        if len(a) < minimum or len(b) < minimum:
            return []
        seen: set[int] = set()
        vals: list[float] = []
        for p in a + b:
            if p.event_id in seen:
                continue
            seen.add(p.event_id)
            vals.append(p.value(metric) or 0.0)
        return [(vals, pair[0] + pair[1], 0)]
    out = []
    for own, y, team in ((a, pair[0], t.home), (b, pair[1], t.away)):
        if len(own) >= minimum:
            out.append(([p.value(metric) or 0.0 for p in own], y, team))
    return out


# ---------------------------------------------------------------------------
# F2.2 (1): NB variance at a moved centre
# ---------------------------------------------------------------------------

FOOTBALL_NB_METRICS = (
    "goals_for", "goals_total", "goals_1h_for", "goals_1h_total",
    "goals_2h_for", "corners_for", "offsides_total", "offsides_for",
)
NB_LINES: dict[str, tuple[float, ...]] = {
    **LINES,
    "goals_1h_total": (0.5, 1.5),
    "aces_for": (2.5, 4.5, 6.5),
    "aces_total": (5.5, 8.5, 11.5),
    "double_faults_for": (1.5, 2.5, 3.5),
    "double_faults_total": (3.5, 5.5),
    "games_total": (20.5, 22.5, 24.5),
}


def k_centre(sport: str) -> float:
    doc = json.loads(ENGINE_CONSTANTS.read_text())
    entry = doc.get("K_CENTRE") or {}
    value = (entry.get("by_sport") or {}).get(sport, entry.get("value"))
    if not isinstance(value, int | float):
        raise ValueError(f"K_CENTRE for {sport} is not fitted")
    return float(value)


def nb_variance_case(
    market: str, sport: str, values: Sequence[float], y: float, prior: float,
    k: float, lines: Sequence[float],
) -> tuple[list[float], list[float], float] | None:
    """(scores with the raw variance, with the scaled variance, centre/mean)."""
    n = len(values)
    mean = statistics.mean(values)
    if n < 2 or mean <= 0 or all(v == 0.0 for v in values):
        return None
    var = statistics.variance(values)
    w = n / (n + k)
    centre = w * mean + (1.0 - w) * prior
    raw_sd = predictive_sd(var, mean, n)
    # sheet_predictive_sd scales for football only; ask it as football so the
    # candidate is the very function SHEET calls, for either sport.
    scaled_sd = sheet_predictive_sd(market, "football", mean, var, n, centre)
    return (
        nb_scores(centre, raw_sd, y, lines),
        nb_scores(centre, scaled_sd, y, lines),
        centre / mean,
    )


NbCase = tuple[int, list[float], list[float], float]


def nb_report(
    rows: dict[str, list[NbCase]],
    label: str,
) -> list[str]:
    text: list[str] = []
    for market, cases in rows.items():
        if not cases:
            continue
        ids = np.asarray([c[0] for c in cases])
        base = np.asarray([c[1] for c in cases])
        cand = np.asarray([c[2] for c in cases])
        ratio = np.asarray([c[3] for c in cases])
        cols = ["NB logloss"] + [f"brier_{x}" for x in NB_LINES[market]]
        text += interval_table(f"{label} {market} - all", cols, base, cand, ids)
        moved = np.abs(ratio - 1.0) > 0.2
        if moved.any():
            text += interval_table(
                f"{label} {market} - centre moved > 20%", cols, base, cand, ids, moved
            )
    return text


def nb_football(args: argparse.Namespace) -> list[str]:
    baselines = json.loads(BASELINES.read_text())
    k = k_centre("football")
    history, targets, _ = load(args.db, True, MatchKind.REGULAR)
    rows: dict[str, list[NbCase]] = defaultdict(list)
    for t in window(targets, args.start, args.end):
        for market in FOOTBALL_NB_METRICS:
            entry = (baselines.get(market) or {}).get(str(t.competition))
            mean_ = entry.get("mean") if isinstance(entry, dict) else None
            if not isinstance(mean_, int | float):
                continue
            for vals, y, _team in side_cases(history, t, market):
                got = nb_variance_case(market, "football", vals, y,
                                       float(mean_), k, NB_LINES[market])
                if got is not None:
                    rows[market].append((t.event_id, got[0], got[1], got[2]))
    return [
        f"## NB variance at a moved centre - football, {args.start}..{args.end}",
        "",
        f"centre = n/(n+{k:g}) sample mean + rest competition baseline; current = "
        "raw sample variance (the 09-25 defect, SHEET before 2026-10-02), "
        "candidate = engine.sheet_predictive_sd (variance scaled by centre/mean).",
        "",
        *nb_report(rows, "football"),
    ]


TENNIS_NB_METRICS = (
    "aces_for", "aces_total", "double_faults_for", "double_faults_total",
    "games_total",
)


@dataclass(frozen=True, slots=True)
class TennisPast:
    ts: int
    event_id: int
    surface: str | None
    best_of: int | None
    values: dict[str, float]


def load_tennis(db: Path) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]]]:
    """Completed singles events (listing) and their flat statistics."""
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    events: dict[int, dict[str, Any]] = {}
    for (js,) in con.execute(
        "SELECT event_json FROM sofa_listed_event WHERE sport = 'tennis'"
    ):
        e = json.loads(js)
        if not isinstance(e.get("id"), int) or not is_completed_event(e):
            continue
        if (e.get("homeTeam") or {}).get("type") != 1:
            continue  # doubles
        if is_friendly_event(e, "tennis"):
            continue
        events[e["id"]] = e
    flat: dict[int, dict[str, Any]] = {}
    ids = list(events)
    for i in range(0, len(ids), 900):
        chunk = ids[i:i + 900]
        for eid, sj in con.execute(
            "SELECT sofascore_event_id, statistics_json FROM sofa_event_stats "
            f"WHERE sofascore_event_id IN ({','.join('?' * len(chunk))})", chunk
        ):
            if sj:
                try:
                    flat[eid] = extract_flat_statistics(json.loads(sj))
                except ValueError:
                    pass
    ordered = sorted(events.values(),
                     key=lambda e: (e.get("startTimestamp") or 0, e["id"]))
    return ordered, flat


def nb_tennis(args: argparse.Namespace) -> list[str]:
    tiers = json.loads(TIER_BASELINES.read_text()).get("metrics") or {}
    k = k_centre("tennis")
    events, flat = load_tennis(args.db)
    lo = int(datetime.fromisoformat(args.start).replace(tzinfo=UTC).timestamp())
    hi = int(datetime.fromisoformat(args.end).replace(tzinfo=UTC).timestamp()) + 86400
    hist: dict[int, list[TennisPast]] = defaultdict(list)
    rows: dict[str, list[NbCase]] = defaultdict(list)
    for e in events:
        ts = int(e.get("startTimestamp") or 0)
        surface = e.get("groundType")
        best_of = infer_best_of(e)
        stats = flat.get(e["id"], {})
        category = ((e.get("tournament") or {}).get("category") or {}).get("name")
        tkey = tier_key(category, surface)
        side_vals: list[dict[str, float]] = []
        for is_home in (True, False):
            vals: dict[str, float] = {}
            for m in TENNIS_NB_METRICS:
                v = extract_metric(m, "tennis", stats, None, e, is_home)
                if isinstance(v, float):
                    vals[m] = v
            side_vals.append(vals)
        pids: list[int] = [
            pid if isinstance(pid := (e.get(s) or {}).get("id"), int) else 0
            for s in ("homeTeam", "awayTeam")
        ]
        if lo <= ts < hi and best_of == 3 and surface and tkey and all(pids):
            scoped = [
                [p for p in hist[pid] if p.best_of == 3
                 and surfaces_comparable(p.surface, surface)][-10:]
                for pid in pids
            ]
            for m in TENNIS_NB_METRICS:
                prior = ((tiers.get(m) or {}).get(tkey) or {}).get("mean")
                if not isinstance(prior, int | float):
                    continue
                if m.endswith("_total"):
                    y = side_vals[0].get(m)
                    pool = {p.event_id: p.values[m] for s in scoped for p in s
                            if m in p.values}
                    own = [[p for p in s if m in p.values] for s in scoped]
                    cases = (
                        [(list(pool.values()), y)]
                        if y is not None and all(len(o) >= 5 for o in own) else []
                    )
                else:
                    cases = []
                    for idx in (0, 1):
                        y = side_vals[idx].get(m)
                        vals_ = [p.values[m] for p in scoped[idx] if m in p.values]
                        if y is not None and len(vals_) >= 5:
                            cases.append((vals_, y))
                for vals_, y_ in cases:
                    assert y_ is not None
                    got = nb_variance_case(m, "tennis", vals_, y_, prior, k,
                                           NB_LINES[m])
                    if got is not None:
                        rows[m].append((e["id"], got[0], got[1], got[2]))
        for idx, pid in enumerate(pids):
            if pid:
                hist[pid].append(
                    TennisPast(ts, e["id"], surface, best_of, side_vals[idx]))
    return [
        f"## NB variance at a moved centre - tennis, {args.start}..{args.end}",
        "",
        f"centre = n/(n+{k:g}) sample mean + rest tier baseline (gender x tier x "
        "surface, best of three); sample = the player's last ten best-of-three "
        "matches on a comparable surface; current = raw variance (SHEET today "
        "for tennis), candidate = variance scaled by centre/mean.",
        "",
        *nb_report(rows, "tennis"),
    ]


# ---------------------------------------------------------------------------
# F2.2 (2): promotion / relegation inside a sample
# ---------------------------------------------------------------------------


def first_seen(history: Sequence[Past]) -> dict[int, int]:
    """competition -> the side's first match in it (REGULAR only)."""
    out: dict[int, int] = {}
    for p in history:
        if p.kind is MatchKind.REGULAR and p.competition not in out:
            out[p.competition] = p.ts
    return out


def other_division(
    sample: Sequence[Past], t: Target, history: Sequence[Past],
    season_start: dict[int, int], minimum: int = 3,
) -> bool:
    """Does this side's sample hold >= `minimum` league matches of another
    league of the fixture's own country, while the side never played the
    fixture's league before this season (promoted or relegated)?

    The second condition keeps a split season (Apertura / Clausura are two
    competitions of one category) and a domestic second competition from
    reading as a move between divisions."""
    if t.category is None:
        return False
    other = sum(
        1 for p in sample
        if p.kind is MatchKind.REGULAR and p.competition != t.competition
        and p.category == t.category
    )
    if other < minimum:
        return False
    start = season_start.get(t.season) if t.season is not None else None
    if start is None:
        return False
    earlier = [p for p in history if p.ts < start]
    if not earlier:
        return False  # no history before this season: nothing says "new"
    return not any(
        p.competition == t.competition and p.kind is MatchKind.REGULAR
        for p in earlier
    )


PROMOTION_METRICS = (
    "goals_for", "goals_total", "corners_for", "corners_total", "shots_for",
    "fouls_for", "yellow_cards_for",
)


def promotion(args: argparse.Namespace) -> list[str]:
    history, targets, season_start = load(args.db, True, MatchKind.REGULAR)
    seen_cache: dict[int, dict[int, int]] = {}
    text = [
        f"## Promotion / relegation inside a sample, {args.start}..{args.end}",
        "",
        "flagged = the side's sample holds >= 3 league matches of another league "
        "of its country and the side has no league match of the fixture's "
        "league before this season; current = SAMPLES' sample; candidate = the "
        "same newest ten without the other division's league matches (the usual "
        "sample when fewer than 5 remain). Poisson log-loss of the sample mean.",
        "",
        "| metric | flagged cases | share of all | mean residual current [95%] | "
        "d logloss [95%] | d even | d odd |",
        "|---|---|---|---|---|---|---|",
    ]
    rng = np.random.default_rng(SEED)
    chosen = window(targets, args.start, args.end)
    for metric in PROMOTION_METRICS:
        stat, _, scope = metric.rpartition("_")
        ids: list[int] = []
        base: list[float] = []
        cand: list[float] = []
        resid: list[float] = []
        total = 0
        for t in chosen:
            pair = t.values.get(stat)
            if pair is None:
                continue
            sides = [(t.home, pair[0]), (t.away, pair[1])]
            samples = []
            flagged = False
            for team, _y in sides:
                h = history.get(team, [])
                s = football_sample(h, t, metric)
                samples.append((team, h, s))
                if len(s) >= 5:
                    flagged |= other_division(s, t, h, season_start)
            if any(len(s) < 5 for _, _, s in samples):
                continue
            total += 1 if scope == "total" else 2
            if not flagged:
                continue

            def fixed(team: int, h: Sequence[Past], s: Sequence[Past]) -> list[Past]:
                b = before(h, t.ts, metric)
                keep = [p for p in b if p.kind is not MatchKind.FRIENDLY
                        and not (p.kind is MatchKind.REGULAR
                                 and p.competition != t.competition
                                 and p.category == t.category)][:10]
                return keep if len(keep) >= 5 else list(s)

            if scope == "total":
                cur = [p.value(metric) or 0.0 for _, _, s in samples for p in s]
                new = [p.value(metric) or 0.0 for team, h, s in samples
                       for p in fixed(team, h, s)]
                y = pair[0] + pair[1]
                cases = [(cur, new, y)]
            else:
                cases = []
                for (team, h, s), (_, y) in zip(samples, sides, strict=True):
                    if other_division(s, t, h, season_start):
                        cases.append((
                            [p.value(metric) or 0.0 for p in s],
                            [p.value(metric) or 0.0 for p in fixed(team, h, s)],
                            y))
            for cur, new, y in cases:
                lam0, lam1 = statistics.mean(cur), statistics.mean(new)
                ids.append(t.event_id)
                base.append(poisson_logloss(lam0, y))
                cand.append(poisson_logloss(lam1, y))
                resid.append(y - lam0)
        if not ids:
            text.append(f"| {metric} | 0 | 0 | - | - | - | - |")
            continue
        g = np.asarray(ids)
        d = np.asarray(cand) - np.asarray(base)
        r = np.asarray(resid)
        lo, hi = paired_interval(d, g, rng)
        rlo, rhi = paired_interval(r, g, rng)
        text.append(
            f"| {metric} | {len(ids)} | {len(ids) / max(total, 1):.2%} | "
            f"{r.mean():+.3f} [{rlo:+.3f}; {rhi:+.3f}] | "
            f"{d.mean():+.5f} [{lo:+.5f}; {hi:+.5f}] | "
            f"{d[g % 2 == 0].mean():+.5f} | {d[g % 2 == 1].mean():+.5f} |"
        )
        print(text[-1], flush=True)
    text.append("")
    del seen_cache
    return text


# ---------------------------------------------------------------------------
# F3.2: context features
# ---------------------------------------------------------------------------

CONTEXT_METRICS = ("goals_total", "goals_for", "corners_total", "yellow_cards_total")
REST_BINS = ((0, 4, "<4"), (4, 8, "4-7"), (8, 15, "8-14"),
             (15, LONG_LAYOFF_DAYS, "15-20"), (LONG_LAYOFF_DAYS, 10_000, ">=21"))


def rest(history: Sequence[Past], ts: int) -> tuple[float | None, int]:
    """Days since the side's last non-friendly match, and its matches in 7 d
    (bet.sofa.schedule's reading, as measure_schedule_context.rest_days)."""
    keys = [p.ts for p in history]
    prior = [p for p in history[: bisect.bisect_left(keys, ts)]
             if p.kind is not MatchKind.FRIENDLY]
    if not prior:
        return None, 0
    return (ts - prior[-1].ts) / 86400, sum(1 for p in prior if ts - p.ts <= 7 * 86400)


def rest_label(days: float | None) -> str:
    if days is None:
        return "unknown"
    for lo, hi, name in REST_BINS:
        if lo <= days < hi:
            return name
    return "unknown"


def season_rounds(targets: Iterable[Target]) -> dict[tuple[int, int | None], int]:
    """(competition, season) -> the season's expected length in rounds: the
    highest league round of the competition's PREVIOUS season in the cache.

    Not the season's own highest round: in a season still being played that
    is the newest round so far, and "the last two rounds" would then be the
    two newest matches of every league - information the fixture's own day
    does not have. A season with no previous season in the cache has no
    length and gets no label."""
    top: dict[tuple[int, int | None], int] = {}
    first: dict[tuple[int, int | None], int] = {}
    for t in targets:
        if t.round is not None and t.kind is MatchKind.REGULAR and t.season is not None:
            key = (t.competition, t.season)
            top[key] = max(top.get(key, 0), t.round)
            first[key] = min(first.get(key, t.ts), t.ts)
    by_comp: dict[int, list[tuple[int, int | None]]] = defaultdict(list)
    for season_key in first:
        by_comp[season_key[0]].append(season_key)
    out: dict[tuple[int, int | None], int] = {}
    for keys in by_comp.values():
        keys.sort(key=lambda k: first[k])
        for prev, cur in zip(keys, keys[1:], strict=False):
            out[cur] = top[prev]
    return out


def round_label(t: Target, rounds: dict[tuple[int, int | None], int]) -> str | None:
    last = rounds.get((t.competition, t.season))
    if t.round is None or not last or last < 10:
        return None
    if t.round <= 3:
        return "rounds 1-3"
    if t.round > last:
        return None  # longer than last season: a changed format, no reading
    if t.round > last - 2:
        return "last 2 rounds"
    if t.round / last >= 0.8:
        return "last 20%"
    return "mid season"


def load_referees(db: Path) -> dict[int, tuple[float, int]]:
    """event -> (referee's career yellow cards per game, games) from
    /event/{id} payloads in sofa_event_detail. The career numbers are the
    referee's at the time of the fetch (most fetches are before kick-off; a
    later one includes this match - one game in ~100, noted in the report)."""
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    out: dict[int, tuple[float, int]] = {}
    for eid, js in con.execute(
        "SELECT sofascore_event_id, detail_json FROM sofa_event_detail "
        "WHERE detail_json LIKE '%\"referee\"%'"
    ):
        ref = ((json.loads(js).get("event") or {}).get("referee")) or {}
        games, yellow = ref.get("games"), ref.get("yellowCards")
        if isinstance(games, int) and games >= 10 and isinstance(yellow, int):
            out[int(eid)] = (yellow / games, games)
    return out


def missing_counts(lineups: dict[str, Any]) -> tuple[int, int] | None:
    """(home, away) players listed `missing` (not `doubtful`) in /lineups."""
    sides = []
    for side in ("home", "away"):
        mp = (lineups.get(side) or {}).get("missingPlayers")
        if mp is None:
            return None
        sides.append(sum(1 for m in mp if m.get("type") == "missing"))
    return sides[0], sides[1]


def load_missing(db: Path) -> dict[int, tuple[int, int]]:
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    out: dict[int, tuple[int, int]] = {}
    for eid, js in con.execute(
        "SELECT sofascore_event_id, lineups_json FROM sofa_event_stats "
        "WHERE lineups_json LIKE '%missingPlayers%'"
    ):
        got = missing_counts(json.loads(js))
        if got is not None:
            out[int(eid)] = got
    return out


def context(args: argparse.Namespace) -> list[str]:
    feature = args.feature
    kind = None if feature == "knockout" else MatchKind.REGULAR
    history, targets, season_start = load(args.db, True, kind)
    chosen = window(targets, args.start, args.end)
    rounds = season_rounds(targets) if feature == "round" else {}
    referees = load_referees(args.db) if feature == "referee" else {}
    missing = load_missing(args.db) if feature == "missing" else {}
    rng = np.random.default_rng(SEED)
    text = [
        f"## Context feature `{feature}`, {args.start}..{args.end}",
        "",
        "log(lam) = log(sample mean) + a + b.x, fitted on one event-id half, "
        "scored on the other; d = Poisson log-loss with the feature - with the "
        "intercept alone; 95% resampling matches.",
        "",
        "| metric | cases | matches | d logloss [95%] | d even | d odd | "
        "feature coefficients (half 0 / half 1) |",
        "|---|---|---|---|---|---|---|",
    ]
    metrics = ("yellow_cards_total", "yellow_cards_for") if feature == "referee" \
        else ("goals_for",) if feature == "missing" else CONTEXT_METRICS
    for metric in metrics:
        lam0: list[float] = []
        ys: list[float] = []
        ids: list[int] = []
        feats: list[Any] = []
        for t in chosen:
            if feature == "referee" and t.event_id not in referees:
                continue
            if feature == "missing" and t.event_id not in missing:
                continue
            cases = side_cases(history, t, metric)
            if not cases:
                continue
            x: Any
            for vals, y, team in cases:
                if feature in ("knockout", "round", "rest"):
                    if feature == "knockout":
                        x = t.kind.value
                    elif feature == "round":
                        x = round_label(t, rounds)
                        if x is None:
                            continue
                    else:
                        ra, wa = rest(history.get(t.home, []), t.ts)
                        rb, wb = rest(history.get(t.away, []), t.ts)
                        if team == 0:
                            known = [r for r in (ra, rb) if r is not None]
                            x = rest_label(min(known) if known else None)
                        else:
                            own, other = (ra, rb) if team == t.home else (rb, ra)
                            x = f"own {rest_label(own)}"
                        if max(wa, wb) >= CONGESTED_7D:
                            x += " +congested"
                elif feature == "referee":
                    rate, _games = referees[t.event_id]
                    x = [math.log(max(rate, 0.5))]
                elif feature == "promotion":
                    flags = {}
                    for side in (t.home, t.away):
                        h = history.get(side, [])
                        s_ = football_sample(h, t, metric)
                        flags[side] = other_division(s_, t, h, season_start)
                    if team == 0:
                        x = [float(flags[t.home] or flags[t.away])]
                    else:
                        opp = t.away if team == t.home else t.home
                        x = [float(flags[team]), float(flags[opp])]
                else:
                    mh, ma = missing[t.event_id]
                    own, opp = (mh, ma) if team == t.home else (ma, mh)
                    x = [float(min(own, 8)), float(min(opp, 8))]
                lam0.append(statistics.mean(vals))
                ys.append(y)
                ids.append(t.event_id)
                feats.append(x)
        if len(ids) < 50:
            text.append(f"| {metric} | {len(ids)} | - | too few cases | | | |")
            continue
        if feature in ("knockout", "round", "rest"):
            labels = [str(f) for f in feats]
            ref = max(set(labels), key=labels.count)
            xmat, names = one_hot(labels, ref)
        else:
            xmat = np.asarray(feats, dtype=float)
            if feature != "promotion":
                xmat = xmat - xmat.mean(axis=0)
            names = (
                ["log ref yellow/game"] if feature == "referee"
                else ["own missing", "opponent missing"] if feature == "missing"
                else ["either side other division"] if xmat.shape[1] == 1
                else ["own other division", "opponent other division"]
            )
        g = np.asarray(ids)
        base, feat, betas = crossfit_feature(
            np.asarray(lam0), np.asarray(ys), xmat, g)
        d = feat - base
        lo, hi = paired_interval(d, g, rng)
        coef = " / ".join(
            ", ".join(f"{n}={b:+.3f}" for n, b in zip(names, beta[1:], strict=True))
            for beta in betas
        )
        if feature in ("knockout", "round", "rest"):
            coef = f"reference `{ref}`; " + coef
        text.append(
            f"| {metric} | {len(ids)} | {len(set(ids))} | "
            f"{d.mean():+.5f} [{lo:+.5f}; {hi:+.5f}] | "
            f"{d[g % 2 == 0].mean():+.5f} | {d[g % 2 == 1].mean():+.5f} | {coef} |"
        )
        print(text[-1], flush=True)
    text.append("")
    return text


# ---------------------------------------------------------------------------
# F2.2 (3): cards to the bench
# ---------------------------------------------------------------------------


def unused_substitutes(lineups: dict[str, Any]) -> set[int]:
    """Player ids on the bench who never came on (no minutes in /lineups)."""
    out: set[int] = set()
    for side in ("home", "away"):
        for row in (lineups.get(side) or {}).get("players") or []:
            pid = (row.get("player") or {}).get("id")
            minutes = (row.get("statistics") or {}).get("minutesPlayed")
            if row.get("substitute") and isinstance(pid, int) and not minutes:
                out.add(pid)
    return out


def bench_card_points(incidents: dict[str, Any], bench: set[int]) -> float:
    """Card points (yellow 1, red 2, second yellow up to 3) shown to `bench`."""
    pts = 0.0
    for inc in incidents.get("incidents") or []:
        if inc.get("incidentType") != "card" or inc.get("rescinded"):
            continue
        pid = (inc.get("player") or {}).get("id")
        if pid not in bench:
            continue
        cls = inc.get("incidentClass")
        pts += {"yellow": 1.0, "red": 2.0, "yellowRed": 2.0}.get(str(cls), 0.0)
    return pts


def bench_cards(args: argparse.Namespace) -> list[str]:
    con = sqlite3.connect(f"file:{args.db}?mode=ro", uri=True)
    events = with_bench = 0
    points: list[float] = []
    for _eid, inc_js, lu_js in con.execute(
        "SELECT sofascore_event_id, incidents_json, lineups_json "
        "FROM sofa_event_stats WHERE lineups_json IS NOT NULL "
        "AND incidents_json IS NOT NULL AND lineups_json LIKE '%minutesPlayed%'"
    ):
        try:
            lu, inc = json.loads(lu_js), json.loads(inc_js)
        except ValueError:
            continue
        if not isinstance(inc, dict) or not inc.get("incidents"):
            continue
        events += 1
        p = bench_card_points(inc, unused_substitutes(lu))
        if p:
            with_bench += 1
            points.append(p)
    return [
        "## Cards to unused substitutes (football /lineups in the cache)", "",
        f"events with lineups (minutesPlayed) and incidents: {events}; with a card "
        f"to an unused substitute: {with_bench} ({with_bench / max(events, 1):.2%}); "
        f"points per such event: {statistics.mean(points) if points else 0:.2f}; "
        f"mean over all events: {sum(points) / max(events, 1):.4f} card points.",
        "",
    ]


# ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    ap.add_argument("--db", type=Path, default=DB)
    ap.add_argument("--start", default="2025-08-01")
    ap.add_argument("--end", default="2026-10-03")
    ap.add_argument("--out", type=Path, default=None)
    sub = ap.add_subparsers(dest="cmd", required=True)
    nb = sub.add_parser("nb-variance")
    nb.add_argument("--sport", choices=("football", "tennis"), required=True)
    sub.add_parser("promotion")
    ctx = sub.add_parser("context")
    ctx.add_argument("--feature", required=True,
                     choices=("knockout", "round", "rest", "referee", "missing",
                              "promotion"))
    sub.add_parser("bench-cards")
    args = ap.parse_args(argv)
    if not args.db.exists():
        print(f"no DB at {args.db}", file=sys.stderr)
        return 2
    runners: dict[str, Callable[[argparse.Namespace], list[str]]] = {
        "promotion": promotion, "context": context, "bench-cards": bench_cards,
    }
    if args.cmd == "nb-variance":
        text = nb_football(args) if args.sport == "football" else nb_tennis(args)
    else:
        text = runners[args.cmd](args)
    body = "\n".join(text)
    print(body)
    if args.out:
        with args.out.open("a", encoding="utf-8") as f:
            f.write(body + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
