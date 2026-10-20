"""Measure the referee term on football cards and fouls (read-only).

Docs: docs/sofa/evidence/referee_effect_2026-10-21.md. Mirrors the count
stretch measurement (scripts/sofa/fit_count_stretch.py, docs/sofa/evidence/
count_stretch_2026-10-17.md): the centre is SHEET's count centre replayed
one step ahead on the cached history (fit_count_stretch.walk: last 10
values, B15 opponent correction, market K shrink to the league rate, rating
blend where rated, cup-strength book, under --live-rules), times the
installed GAME_STATE term where the market carries it (cards_points_for,
fouls_for). The variant multiplies that centre by ratio^beta, ratio the
referee's as-of shrunk ratio (bet.sofa.referees.RefereeBook: his previous
labelled matches strictly before kick-off, each match's count over its
competition's as-of mean, (sum r_i + K) / (n + K)); no referee or no record:
ratio 1, the centre unchanged. Cards markets read the cards-points ratio,
fouls markets (full match and halves) the full-match fouls ratio.

Fit: per market, beta by Poisson pseudo-likelihood (log link, offset log
centre, covariate log ratio) on the train window, K on a grid by the same
likelihood. Test: NB log-loss of the observed count (alpha from the installed
config/sofa_count_dispersion.json, market x competition; a market the table
lacks reads a method-of-moments alpha of the train rows, the same in both
variants), new minus old, 95% bootstrap over matches (2000, seed 0); on all
test rows, on rows with a referee record, and with n_ref >= 5. After a curve:
on the Superbet-like lines of each market the NB p of OVER / UNDER is mapped
through a per-(market, direction, line) isotonic curve fitted on the train
rows of the same variant; binary log-loss delta and calibration at curve
>= 0.70 on the test rows.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_referee_effect.py \\
        measure --db-path data/refit_2026-10-17/sofa_replay.db --live-rules \\
        --cache-dir <scratch> [--json-out <file>]
    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_referee_effect.py coverage
    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_referee_effect.py \\
        live --date 2026-10-20
    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_referee_effect.py \\
        announce --days 2026-10-21 2026-10-22 2026-10-23   # live requests
"""

from __future__ import annotations

import argparse
import json
import math
import pickle
import sqlite3
import sys
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO / "src"), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import centre_replay as cr  # noqa: E402
from bet.sofa import count_dispersion  # noqa: E402
from bet.sofa import football_rating as fr  # noqa: E402
from bet.sofa import game_state as gs  # noqa: E402
from bet.sofa import referees as rf  # noqa: E402
from bet.sofa.atomic import write_bytes_atomic  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.cup_strength import load as load_cup_strength  # noqa: E402

CARDS = "cards_points"
FOULS = "fouls"
MARKETS: tuple[str, ...] = (
    "cards_points_total", "cards_points_for", "fouls_total", "fouls_for",
    "fouls_1h_total", "fouls_1h_for", "fouls_2h_total", "fouls_2h_for")
# The history metric whose match total feeds the referee's record.
FAMILY_METRIC = {CARDS: "cards_points_for", FOULS: "fouls_for"}
# Superbet-like lines (the lines the 2026-10-20 sheet carried).
LINES: dict[str, tuple[float, ...]] = {
    "cards_points_total": (2.5, 3.5, 4.5, 5.5, 6.5),
    "cards_points_for": (0.5, 1.5, 2.5, 3.5),
    "fouls_total": (20.5, 21.5, 22.5, 23.5, 24.5, 25.5),
    "fouls_for": (9.5, 10.5, 11.5, 12.5, 13.5),
    "fouls_1h_total": (9.5, 10.5, 11.5, 12.5),
    "fouls_1h_for": (4.5, 5.5, 6.5),
    "fouls_2h_total": (10.5, 11.5, 12.5, 13.5),
    "fouls_2h_for": (4.5, 5.5, 6.5),
}
K_GRID: tuple[float, ...] = (2.0, 5.0, 10.0, 20.0, 40.0, 80.0)
MIN_REF_N = 5
CURVE_FLOOR = 0.70


def family(market: str) -> str:
    return CARDS if market.startswith("cards") else FOULS


def _ts(day: str) -> int:
    return int(datetime.fromisoformat(day).replace(tzinfo=UTC).timestamp())


@dataclass(frozen=True)
class Row:
    market: str
    event_id: int
    ts: int
    competition_id: int
    y: float
    centre: float
    ref_n: int
    ref_sum: float  # sum of y_i / L_i of the referee's previous matches


def referee_reads(history: Iterable[fr.FootballResult], labels: Mapping[int, int],
                  ) -> dict[int, dict[str, rf.RefereeRead]]:
    """event id -> family -> the referee's as-of read (strictly before)."""
    def totals() -> Iterable[rf.MatchTotals]:
        for r in history:
            vals = {fam: float(sum(r.values[m])) for fam, m in FAMILY_METRIC.items()
                    if m in r.values}
            yield rf.MatchTotals(r.event_id, r.ts, r.competition_id,
                                 labels.get(r.event_id), vals)
    return {m.event_id: reads
            for m, reads in rf.walk_reads(totals(), FAMILY_METRIC)}


def centre_rows(history: list[fr.FootballResult], start: str, end: str,
                rules: Any) -> list[tuple[str, int, int, int, float, float]]:
    """(market, event, ts, competition, y, centre) - the replayed centre with
    the installed GAME_STATE term; independent of the referee labels."""
    from scripts.sofa.fit_count_stretch import walk
    from scripts.sofa.measure_game_state import k_table
    comp = {r.event_id: r.competition_id for r in history}
    game_state = gs.load_table()
    out = []
    for sr in walk(history, _ts(start), _ts(end) + 86400, MARKETS,
                   k_table(MARKETS), rules, cup_strength=load_cup_strength()):
        centre = sr.centre
        if sr.side:
            g = game_state.multiplier(sr.market, sr.supremacy)
            if g is not None:
                centre *= g
        out.append((sr.market, sr.event_id, sr.ts, comp[sr.event_id], sr.y, centre))
    return out


def attach_reads(centres: Iterable[tuple[str, int, int, int, float, float]],
                 reads: Mapping[int, Mapping[str, rf.RefereeRead]]) -> list[Row]:
    out = []
    for market, eid, ts, comp, y, centre in centres:
        rd = reads.get(eid, {}).get(family(market))
        out.append(Row(market, eid, ts, comp, y, centre,
                       rd.n if rd else 0, rd.ratio_sum if rd else 0.0))
    return out


# --- fitting ----------------------------------------------------------------

def log_ratio(n: np.ndarray, s: np.ndarray, k: float) -> np.ndarray:
    """log((s + K) / (n + K)); 0 where there is no record."""
    return np.where(n > 0, np.log((s + k) / (n + k)), 0.0)


def fit_beta(c: np.ndarray, x: np.ndarray, y: np.ndarray,
             iterations: int = 50) -> float:
    """beta maximising sum(y beta x - c exp(beta x)) (Poisson pseudo-
    likelihood, offset log c). Newton from 0."""
    beta = 0.0
    for _ in range(iterations):
        mu = c * np.exp(beta * x)
        grad = float(np.sum(x * (y - mu)))
        hess = float(np.sum(x * x * mu))
        if hess <= 0:
            return 0.0
        step = grad / hess
        beta += step
        if abs(step) < 1e-10:
            break
    return beta


def poisson_ll(c: np.ndarray, x: np.ndarray, y: np.ndarray, beta: float) -> float:
    mu = c * np.exp(beta * x)
    return float(np.sum(y * np.log(np.maximum(mu, 1e-12)) - mu))


def fit_market(c: np.ndarray, n: np.ndarray, s: np.ndarray, y: np.ndarray,
               grid: Sequence[float] = K_GRID) -> tuple[float, float, dict[str, float]]:
    """(K, beta, K -> train pseudo log-likelihood gain over beta 0)."""
    base = poisson_ll(c, np.zeros_like(c), y, 0.0)
    best: tuple[float, float, float] | None = None
    gains: dict[str, float] = {}
    for k in grid:
        x = log_ratio(n, s, k)
        b = fit_beta(c, x, y)
        ll = poisson_ll(c, x, y, b)
        gains[f"{k:g}"] = ll - base
        if best is None or ll > best[2]:
            best = (k, b, ll)
    assert best is not None
    return best[0], best[1], gains


def mom_alpha(c: np.ndarray, y: np.ndarray) -> float:
    """Method-of-moments NB alpha: var = mu + alpha mu^2."""
    num = float(np.sum((y - c) ** 2 - c))
    den = float(np.sum(c * c))
    return max(0.0, num / den) if den > 0 else 0.0


def nb_logloss_vec(y: np.ndarray, mu: np.ndarray, alpha: np.ndarray) -> np.ndarray:
    return np.array([cr.nb_logloss(float(a), float(b), float(al))
                     for a, b, al in zip(y, mu, alpha, strict=True)])


def nb_cdf(k: int, mu: float, alpha: float) -> float:
    """P(Y <= k) under NB(mu, alpha) (Poisson at alpha 0)."""
    if k < 0:
        return 0.0
    mu = max(mu, 1e-9)
    if alpha <= 1e-9:
        p = math.exp(-mu)
        total = p
        for i in range(1, k + 1):
            p *= mu / i
            total += p
        return min(1.0, total)
    r = 1.0 / alpha
    q = r / (r + mu)
    p = math.pow(q, r)
    total = p
    for i in range(1, k + 1):
        p *= (i - 1 + r) / i * (1 - q)
        total += p
    return min(1.0, total)


def isotonic(p: np.ndarray, hit: np.ndarray, bins: int = 40,
             ) -> tuple[np.ndarray, np.ndarray]:
    """(bin upper edges of p, fitted rate) - quantile bins, then pool
    adjacent violators; read with ``apply_curve``."""
    order = np.argsort(p)
    ps, hs = p[order], hit[order]
    chunks = np.array_split(np.arange(len(ps)), min(bins, max(1, len(ps))))
    edges, rates, weights = [], [], []
    for ch in chunks:
        if len(ch) == 0:
            continue
        edges.append(float(ps[ch[-1]]))
        rates.append(float(hs[ch].mean()))
        weights.append(float(len(ch)))
    # PAV
    blocks: list[list[float]] = []  # [rate, weight, last index]
    for i, (r, w) in enumerate(zip(rates, weights, strict=True)):
        blocks.append([r, w, float(i)])
        while len(blocks) > 1 and blocks[-2][0] > blocks[-1][0]:
            r2, w2, i2 = blocks.pop()
            r1, w1, _ = blocks.pop()
            blocks.append([(r1 * w1 + r2 * w2) / (w1 + w2), w1 + w2, i2])
    fitted = np.empty(len(rates))
    start = 0
    for r, _, last in blocks:
        fitted[start:int(last) + 1] = r
        start = int(last) + 1
    return np.array(edges), np.clip(fitted, 1e-4, 1 - 1e-4)


def apply_curve(curve: tuple[np.ndarray, np.ndarray], p: np.ndarray) -> np.ndarray:
    edges, rates = curve
    idx = np.minimum(np.searchsorted(edges, p, side="left"), len(rates) - 1)
    return np.asarray(rates[idx])


def _boot(groups: dict[int, list[float]]) -> list[float]:
    mean, lo, hi, _, _ = cr.boot_by_group(groups)
    return [mean, lo, hi]


def measure(rows: Sequence[Row], test_from: str, end: str,
            table: count_dispersion.DispersionTable,
            grid: Sequence[float] = K_GRID,
            fit_from: str | None = None) -> dict[str, Any]:
    """Per market: K and beta fitted on [fit_from, test_from), read on
    [test_from, end]."""
    t0, t1 = _ts(test_from), _ts(end) + 86400
    f0 = _ts(fit_from) if fit_from else 0
    out: dict[str, Any] = {}
    for market in MARKETS:
        mr = [r for r in rows if r.market == market]
        if not mr:
            continue
        ts = np.array([r.ts for r in mr])
        c = np.array([r.centre for r in mr])
        y = np.array([r.y for r in mr])
        n = np.array([r.ref_n for r in mr], dtype=float)
        s = np.array([r.ref_sum for r in mr])
        ev = np.array([r.event_id for r in mr])
        train, test = (ts >= f0) & (ts < t0), (ts >= t0) & (ts < t1)
        k, beta, gains = fit_market(c[train], n[train], s[train], y[train], grid)
        x = log_ratio(n, s, k)
        new = c * np.exp(beta * x)
        alpha_fallback = mom_alpha(c[train], y[train])
        alpha = np.array([
            (d.alpha if (d := table.read("football", market, r.competition_id))
             is not None else alpha_fallback) for r in mr])
        res: dict[str, Any] = {
            "K": k, "beta": beta, "train_ll_gain_by_K": gains,
            "train_rows": int(train.sum()), "test_rows": int(test.sum()),
            "train_with_record": int((train & (n > 0)).sum()),
            "test_with_record": int((test & (n > 0)).sum()),
            "test_with_n5": int((test & (n >= MIN_REF_N)).sum()),
            "alpha_source": ("table" if table.markets.get(market) else
                             f"train method of moments {alpha_fallback:.4f}"),
        }
        ti = np.where(test)[0]
        l_old = nb_logloss_vec(y[ti], c[ti], alpha[ti])
        l_new = nb_logloss_vec(y[ti], new[ti], alpha[ti])
        for name, mask in (("all", np.ones(len(ti), bool)),
                           ("with_record", n[ti] > 0),
                           ("n_ref_ge_5", n[ti] >= MIN_REF_N)):
            groups: dict[int, list[float]] = defaultdict(list)
            for e, d in zip(ev[ti][mask], (l_new - l_old)[mask], strict=True):
                groups[int(e)].append(float(d))
            res[f"d_logloss_{name}"] = _boot(groups)
            res[f"matches_{name}"] = len(groups)
        res["logloss_old"] = float(l_old.mean()) if len(ti) else None
        res["logloss_new"] = float(l_new.mean()) if len(ti) else None
        res["mse_old"] = float(np.mean((c[ti] - y[ti]) ** 2)) if len(ti) else None
        res["mse_new"] = float(np.mean((new[ti] - y[ti]) ** 2)) if len(ti) else None
        # spread of the multiplier on the test rows with a record
        rec = ti[n[ti] >= MIN_REF_N]
        if len(rec):
            mult = np.exp(beta * x[rec])
            res["multiplier_n5_p10_p50_p90"] = [float(v) for v in
                                                np.quantile(mult, [0.1, 0.5, 0.9])]
        res["after_curve"] = after_curve(market, c, new, y, alpha, ev, train, test, n)
        out[market] = res
        print(market, json.dumps(res), file=sys.stderr, flush=True)
    return out


def after_curve(market: str, c: np.ndarray, new: np.ndarray, y: np.ndarray,
                alpha: np.ndarray, ev: np.ndarray, train: np.ndarray,
                test: np.ndarray, n: np.ndarray) -> dict[str, Any]:
    """Per line and direction: an isotonic curve on the train rows of each
    variant, read on the test rows; binary log-loss new - old (bootstrap by
    match) and calibration at curve >= CURVE_FLOOR."""
    groups: dict[int, list[float]] = defaultdict(list)
    groups_n5: dict[int, list[float]] = defaultdict(list)
    cal: dict[str, list[float]] = {"old": [0.0, 0.0, 0.0], "new": [0.0, 0.0, 0.0]}
    cal_n5: dict[str, list[float]] = {"old": [0.0, 0.0, 0.0], "new": [0.0, 0.0, 0.0]}
    for line in LINES[market]:
        k = int(math.floor(line))
        p_old = np.array([1 - nb_cdf(k, float(m), float(a))
                          for m, a in zip(c, alpha, strict=True)])
        p_new = np.array([1 - nb_cdf(k, float(m), float(a))
                          for m, a in zip(new, alpha, strict=True)])
        over = (y > line).astype(float)
        for direction in ("OVER", "UNDER"):
            hit = over if direction == "OVER" else 1 - over
            po = p_old if direction == "OVER" else 1 - p_old
            pn = p_new if direction == "OVER" else 1 - p_new
            if train.sum() < 200 or test.sum() == 0:
                continue
            q_old = apply_curve(isotonic(po[train], hit[train]), po[test])
            q_new = apply_curve(isotonic(pn[train], hit[train]), pn[test])
            h = hit[test]
            b_old = -(h * np.log(q_old) + (1 - h) * np.log(1 - q_old))
            b_new = -(h * np.log(q_new) + (1 - h) * np.log(1 - q_new))
            n5 = n[test] >= MIN_REF_N
            for e, d, is5 in zip(ev[test], b_new - b_old, n5, strict=True):
                groups[int(e)].append(float(d))
                if is5:
                    groups_n5[int(e)].append(float(d))
            for name, q in (("old", q_old), ("new", q_new)):
                sel = q >= CURVE_FLOOR
                cal[name][0] += float(sel.sum())
                cal[name][1] += float(q[sel].sum())
                cal[name][2] += float(h[sel].sum())
                sel5 = sel & n5
                cal_n5[name][0] += float(sel5.sum())
                cal_n5[name][1] += float(q[sel5].sum())
                cal_n5[name][2] += float(h[sel5].sum())

    def _cal(d: dict[str, list[float]]) -> dict[str, Any]:
        return {v: {"n": int(a[0]),
                    "mean_curve": a[1] / a[0] if a[0] else None,
                    "realised": a[2] / a[0] if a[0] else None}
                for v, a in d.items()}

    return {"lines": list(LINES[market]),
            "d_binary_logloss": _boot(groups),
            "d_binary_logloss_n_ref_ge_5": _boot(groups_n5),
            "calibration_ge_070": _cal(cal),
            "calibration_ge_070_n_ref_ge_5": _cal(cal_n5)}


# --- coverage ---------------------------------------------------------------

def _ro(db_path: str) -> sqlite3.Connection:
    uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    return sqlite3.connect(uri, uri=True, timeout=60.0)


def season_of(ts: int) -> str:
    d = datetime.fromtimestamp(ts, UTC)
    y = d.year if d.month >= 7 else d.year - 1
    return f"{y}/{(y + 1) % 100:02d}"


def coverage(db_path: str, runs_dir: str, since: str) -> dict[str, Any]:
    """Share of football matches with statistics / incidents labelled with a
    referee, per season and for the top competitions on the boards."""
    from scripts.sofa.backfill_event_stats import board_competitions
    board = board_competitions(runs_dir)
    labels = rf.load_labels(db_path)
    conn = _ro(db_path)
    try:
        rows = conn.execute(
            "SELECT l.event_id, l.start_ts, "
            "json_extract(l.event_json, '$.tournament.uniqueTournament.id'), "
            "json_extract(l.event_json, '$.tournament.uniqueTournament.name') "
            "FROM sofa_listed_event l JOIN sofa_event_stats s "
            "ON s.sofascore_event_id = l.event_id "
            "WHERE l.sport = 'football' AND l.start_ts >= ? AND l.start_ts < ? "
            "AND ((s.statistics_json IS NOT NULL AND length(s.statistics_json) > 2) "
            "OR (s.incidents_json IS NOT NULL AND length(s.incidents_json) > 2))",
            (_ts(since), int(datetime.now(UTC).timestamp()) - 6 * 3600)).fetchall()
    finally:
        conn.close()
    seasons: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0])
    comps: dict[tuple[int, str], list[int]] = defaultdict(lambda: [0, 0])
    for eid, ts, cid, name in rows:
        on_board = cid in board
        cell = seasons[season_of(int(ts))]
        cell[0] += 1
        cell[1] += eid in labels
        if on_board:
            cell[2] += 1
            cell[3] += eid in labels
            cc = comps[(cid, name)]
            cc[0] += 1
            cc[1] += eid in labels
    top = sorted(comps.items(), key=lambda kv: -kv[1][0])[:25]
    return {
        "since": since,
        "by_season": {k: {"matches": v[0], "labelled": v[1],
                          "share": v[1] / v[0] if v[0] else None,
                          "board_matches": v[2], "board_labelled": v[3],
                          "board_share": v[3] / v[2] if v[2] else None}
                      for k, v in sorted(seasons.items())},
        "top_board_competitions": [
            {"id": cid, "name": name, "matches": v[0], "labelled": v[1],
             "share": v[1] / v[0]} for (cid, name), v in top],
        "labels_total": len(labels),
    }


def live(db_path: str, runs_dir: str, day: str) -> dict[str, Any]:
    """A day's football fixtures: referee at RESOLVE (02_fixtures.json), in
    the latest cached /event, and in the labels; with the hours before
    kick-off the cached /event was fetched."""
    fixtures = json.loads((Path(runs_dir) / day / "02_fixtures.json").read_text())
    fb = [f for f in fixtures if f.get("sport") == "football"]
    conn = _ro(db_path)
    out_rows = []
    try:
        for f in fb:
            eid = int(f["sofascore_event_id"])
            row = conn.execute(
                "SELECT fetched_at, detail_json FROM sofa_event_detail "
                "WHERE sofascore_event_id = ?", (eid,)).fetchone()
            ko = datetime.fromisoformat(str(f["kickoff_utc"]).replace("Z", "+00:00"))
            det_ref = None
            lead_h = None
            if row is not None:
                label, _ = rf.from_event_detail(eid, json.loads(row[1]), "detail")
                det_ref = label.referee_id
                fetched = datetime.fromisoformat(row[0])
                if fetched.tzinfo is None:
                    fetched = fetched.astimezone(UTC)
                lead_h = (ko - fetched).total_seconds() / 3600
            out_rows.append({"event_id": eid, "resolve": bool(f.get("referee")),
                             "detail": det_ref is not None, "lead_h": lead_h})
    finally:
        conn.close()
    labels = rf.load_labels(db_path)
    n = len(out_rows)
    return {
        "date": day, "football_fixtures": n,
        "referee_at_resolve": sum(r["resolve"] for r in out_rows),
        "referee_in_cached_event": sum(r["detail"] for r in out_rows),
        "cached_event_before_kickoff_with_referee": sum(
            r["detail"] and (r["lead_h"] or -1) > 0 for r in out_rows),
        "labelled_now": sum(r["event_id"] in labels for r in out_rows),
    }


def board_frequency(runs_dir: str) -> list[int]:
    """Football competitions by how many fixtures the RESOLVE artifacts
    held (the boards' own weight), most first."""
    count: dict[int, int] = defaultdict(int)
    for path in Path(runs_dir).glob("*/02_fixtures.json"):
        try:
            fixtures = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        for fx in fixtures:
            if fx.get("sport") == "football" and fx.get("competition_id"):
                count[int(fx["competition_id"])] += 1
    return [c for c, _ in sorted(count.items(), key=lambda kv: -kv[1])]


def card_competitions(runs_dir: str) -> list[int]:
    """Football competitions by how many events had a cards / fouls row in
    a 05_sheet.json (where Superbet offers the markets), most first."""
    count: dict[int, int] = defaultdict(int)
    for path in Path(runs_dir).glob("*/05_sheet.json"):
        fx_path = path.parent / "02_fixtures.json"
        try:
            rows = json.loads(path.read_text())
            fixtures = json.loads(fx_path.read_text())
        except (OSError, ValueError):
            continue
        comp = {f["sofascore_event_id"]: f.get("competition_id") for f in fixtures
                if f.get("sport") == "football"}
        events = {r["sofascore_event_id"] for r in rows
                  if r.get("sport") == "football"
                  and rf.family_of(str(r.get("market"))) is not None}
        for e in events:
            if comp.get(e):
                count[int(comp[e])] += 1
    return [c for c, _ in sorted(count.items(), key=lambda kv: -kv[1])]


LEAD_BUCKETS: tuple[tuple[str, float, float], ...] = (
    ("0-6h", 0, 6), ("6-24h", 6, 24), ("24-48h", 24, 48), ("48-72h", 48, 72),
    ("72h+", 72, 1e9))


def announce(days: Sequence[str], top: int, per_comp: int) -> dict[str, Any]:
    """How long before kick-off Sofascore names the referee: the not-started
    football games of the `top` competitions where Superbet offered cards /
    fouls (card_competitions) on `days`, a fresh
    /event of each (at most `per_comp` a competition-day), the share with a
    referee per hours-to-kick-off bucket. Live requests; writes nothing."""
    from bet.sofa.client import SofascoreClient
    from bet.sofa.errors import CircuitOpenError, ProviderError
    config = SofaConfig.from_env()
    client = SofascoreClient(config)
    comps = card_competitions(config.runs_dir)[:top]
    now_ts = datetime.now(UTC).timestamp()
    cells: dict[str, list[int]] = {b[0]: [0, 0] for b in LEAD_BUCKETS}
    errors = 0
    asked = 0
    try:
        for day in days:
            for comp in comps:
                try:
                    listing = client.tournament_day_events(comp, day) or {}
                except ProviderError:
                    errors += 1
                    continue
                games = [e for e in listing.get("events") or []
                         if (e.get("status") or {}).get("type") == "notstarted"
                         and isinstance(e.get("startTimestamp"), int)
                         and e["startTimestamp"] > now_ts][:per_comp]
                for ev in games:
                    try:
                        detail = client.event(int(ev["id"]))
                    except ProviderError:
                        errors += 1
                        continue
                    asked += 1
                    label, _ = rf.from_event_detail(int(ev["id"]), detail)
                    lead = (ev["startTimestamp"] - now_ts) / 3600
                    for name, lo, hi in LEAD_BUCKETS:
                        if lo <= lead < hi:
                            cells[name][0] += 1
                            cells[name][1] += label.referee_id is not None
    except CircuitOpenError:
        errors += 1
    return {"asked_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "days": list(days), "competitions": len(comps), "asked": asked,
            "errors": errors,
            "by_lead": {k: {"games": v[0], "with_referee": v[1],
                            "share": v[1] / v[0] if v[0] else None}
                        for k, v in cells.items()}}


def main() -> int:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("measure")
    m.add_argument("--db-path", default="data/refit_2026-10-17/sofa_replay.db",
                   help="the history DB (read-only; default the 2026-10-17 replay)")
    m.add_argument("--labels-db", default=None,
                   help="where the referee labels are (default SOFA_DB_PATH)")
    m.add_argument("--train-from", default="2024-10-01")
    m.add_argument("--test-from", default="2026-01-01")
    m.add_argument("--fit-from", default=None,
                   help="fit on rows from this day only (default every row "
                   "before --test-from)")
    m.add_argument("--config-markets", nargs="+", default=None,
                   help="with --write-config: write these markets whatever the "
                   "window's test (chosen on earlier out-of-sample runs)")
    m.add_argument("--write-config", metavar="FILE",
                   help="write the fitted markets whose log-loss interval is "
                   "below zero as a referee-effect config (inert while "
                   "epochs.FOOTBALL_REFEREE_FROM_UTC is None)")
    m.add_argument("--to", dest="end", default="2026-10-16")
    m.add_argument("--cache-dir", required=True,
                   help="scratch: the extended history and the rows pickle")
    m.add_argument("--json-out")
    m.add_argument("--centres-only", action="store_true",
                   help="replay and cache the centres, measure nothing")
    from scripts.sofa.measure_game_state import add_rule_args, rules_from_args
    add_rule_args(m)
    c = sub.add_parser("coverage")
    c.add_argument("--since", default="2024-07-01")
    c.add_argument("--json-out")
    lv = sub.add_parser("live")
    lv.add_argument("--date", required=True)
    an = sub.add_parser("announce")
    an.add_argument("--days", nargs="+", required=True)
    an.add_argument("--top", type=int, default=60)
    an.add_argument("--per-comp", type=int, default=6)
    args = ap.parse_args()
    config = SofaConfig.from_env()
    if args.cmd == "coverage":
        res = coverage(config.db_path, config.runs_dir, args.since)
        text = json.dumps(res, indent=1)
        print(text)
        if args.json_out:
            Path(args.json_out).write_text(text, encoding="utf-8")
        return 0
    if args.cmd == "announce":
        print(json.dumps(announce(args.days, args.top, args.per_comp), indent=1))
        return 0
    if args.cmd == "live":
        print(json.dumps(live(config.db_path, config.runs_dir, args.date), indent=1))
        return 0
    from scripts.sofa.fit_count_stretch import extend_history, extra_metrics
    rules = rules_from_args(args, args.end)
    cache = Path(args.cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    db = Path(args.db_path)
    labels = rf.load_labels(args.labels_db or config.db_path)
    print(f"labels {len(labels)}", file=sys.stderr, flush=True)
    hist_path = cache / "history_ext.pkl"
    if hist_path.exists():
        history = pickle.loads(hist_path.read_bytes())
    else:
        history = fr.load_history(db, db.parent / "cache")
        history, added = extend_history(history, db, extra_metrics(MARKETS))
        print(f"history {len(history)}, extended {added}", file=sys.stderr,
              flush=True)
        hist_path.write_bytes(pickle.dumps(history, protocol=pickle.HIGHEST_PROTOCOL))
    centres_path = cache / f"centres_{args.train_from}_{args.end}.pkl"
    if centres_path.exists():
        centres = pickle.loads(centres_path.read_bytes())
    else:
        centres = centre_rows(history, args.train_from, args.end, rules)
        centres_path.write_bytes(
            pickle.dumps(centres, protocol=pickle.HIGHEST_PROTOCOL))
    print(f"centre rows {len(centres)}", file=sys.stderr, flush=True)
    if args.centres_only:
        return 0
    rows = attach_reads(centres, referee_reads(history, labels))
    del history, centres
    print(f"rows {len(rows)}", file=sys.stderr, flush=True)
    result = measure(rows, args.test_from, args.end, count_dispersion.load_table(),
                     fit_from=args.fit_from)
    result["_setup"] = {"db_path": str(db), "labels": len(labels),
                        "replay_from": args.train_from,
                        "fit_from": args.fit_from or args.train_from,
                        "test_from": args.test_from, "to": args.end,
                        "centre_rules": rules.describe(),
                        "k_grid": list(K_GRID)}
    text = json.dumps(result, indent=1)
    if args.json_out:
        Path(args.json_out).write_text(text, encoding="utf-8")
    print(text)
    if args.write_config:
        doc = effect_config(result, args.config_markets)
        rf.parse_effect_table(doc)  # what is written must be readable
        write_bytes_atomic(Path(args.write_config),
                           (json.dumps(doc, indent=2) + "\n").encode("utf-8"))
        print(f"wrote {args.write_config}", file=sys.stderr)
    return 0


def effect_config(result: Mapping[str, Any],
                  chosen: Sequence[str] | None = None) -> dict[str, Any]:
    """The config of the markets whose test log-loss interval (all rows) is
    below zero, or of the ``chosen`` markets (selected on earlier
    out-of-sample runs, fitted on this run's window)."""
    setup = result["_setup"]

    def keep(m: str, r: Mapping[str, Any]) -> bool:
        if chosen is not None:
            return m in chosen
        return float(r["d_logloss_all"][2]) < 0

    markets = {
        m: {"family": family(m),
            "beta": round(float(r["beta"]), 6), "K": float(r["K"]),
            "n_train_rows": r["train_rows"], "n_test_rows": r["test_rows"],
            **({"d_logloss_test": [round(float(v), 6) for v in r["d_logloss_all"]]}
               if r["test_rows"] else {})}
        for m, r in result.items()
        if not m.startswith("_") and keep(m, r)}
    return {
        "_doc": ("Referee term (epochs.FOOTBALL_REFEREE, bet.sofa.referees): a "
                 "football cards / fouls centre x ratio ** beta, ratio the "
                 "referee's as-of shrunk ratio (sum r_i + K) / (n + K). INERT "
                 "while epochs.FOOTBALL_REFEREE_FROM_UTC is None. Written by "
                 "scripts/sofa/measure_referee_effect.py --write-config."),
        "fitted_from": {
            "fitted_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            **setup,
            "method": ("Poisson pseudo-likelihood, log link, offset log centre, "
                       "covariate log ratio; K on a grid"),
            "centre": ("fit_count_stretch.walk one-step-ahead count centre "
                       "x installed GAME_STATE"),
            "evidence": "docs/sofa/evidence/referee_effect_2026-10-21.md",
        },
        "unfitted_constants": list(rf.REFEREE_UNFITTED),
        "markets": markets,
    }


if __name__ == "__main__":
    sys.exit(main())
