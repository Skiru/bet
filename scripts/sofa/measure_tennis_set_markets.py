#!/usr/bin/env python3
"""B5 (audit 2026-10-13) - tennis per-set games and sets_total: the rating's
neighbours against the players' own samples. Read-only evidence.

Nothing here writes a config, a curve, a run artifact or a database. The
question (docs/sofa/evidence/tennis_set_markets_2026-10-13.md, registered
before this ran): is ``MatchForecast.read`` - the share of the 600 historical
matches with the nearest win probability on the winning side of the line, the
estimator that replaced the sample for games_won_for on 2026-10-07 - a better
probability than SHEET's sample estimator for

    games_set1_total  games_set2_total  games_won_set1_for
    games_won_set2_for  games_won_set3_for  sets_total

at the lines Superbet quotes?

Walk forward over ``tennis_rating.load_history`` (the sheet's population):
each test match is forecast from ``AsOfRating.model_at(day 00:00Z)`` with the
scoped tier x gender table (the production rule) and coefficients /
``tier_start`` refitted on matches before the window (``clean_config`` of
measure_tennis_outcome_model: no look-ahead). The sample estimator is SHEET's
stats-only path, rebuilt from the same history: each player's last 10
completed best-of-three matches on the fixture's surface family before the
kickoff, the total pooled over both players (one match once, both sides
>= MIN_SAMPLE), the centre shrunk to the prior with K (tennis), p =
``engine.p_empirical_centred_raw`` (the same tilt), F35's refusals.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_tennis_set_markets.py \\
        [--db data/sofa.db] [--out-dir data/audit_2026-10-13/b5] [--boot 2000]

Writes ``rows.npz``, ``results.json`` and ``report.md`` into ``--out-dir``.
Exit 0 OK, 2 on a failure.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from collections import defaultdict, deque
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import tennis_rating as tr  # noqa: E402
from bet.sofa.confidence import line_is_beyond_sample, mode_loses  # noqa: E402
from bet.sofa.config import config_path  # noqa: E402
from bet.sofa.engine import (  # noqa: E402
    _tilted_weights,
    outside_model_resolution,
    winning_boundary,
)
from bet.sofa.tennis_prior import tier_key  # noqa: E402
from scripts.sofa.measure_tennis_outcome_model import (  # noqa: E402
    clean_config,
    is_team_cup,
    load,
)

FloatArr = npt.NDArray[np.float64]
IntArr = npt.NDArray[np.int64]

DEFAULT_OUT = "data/audit_2026-10-13/b5"
WINDOWS: tuple[tuple[str, str, str], ...] = (
    ("W1", "2026-03-01", "2026-06-15"),
    ("W2", "2026-06-15", "2026-10-13"),
)
SAMPLE_N = 10  # config.sample_n
MIN_SAMPLE = 5  # config.min_sample
K_TENNIS = 5.0  # sofa_engine_constants K_CENTRE.by_sport.tennis (read in main)
PRINT = 0.70
SET_LINES = (6.5, 7.5, 8.5, 9.5, 10.5, 12.5)
SET_FOR_LINES = (2.5, 3.5, 4.5, 5.5, 6.5)
MARKET_LINES: dict[str, tuple[float, ...]] = {
    "games_set1_total": SET_LINES,
    "games_set2_total": SET_LINES,
    "games_won_set1_for": SET_FOR_LINES,
    "games_won_set2_for": SET_FOR_LINES,
    "games_won_set3_for": SET_FOR_LINES,
    "sets_total": (2.5,),
}
MARKETS: tuple[str, ...] = tuple(MARKET_LINES)
SUBJECT = frozenset({"games_won_set1_for", "games_won_set2_for", "games_won_set3_for"})
DIRECTIONS = ("OVER", "UNDER")


# ---------------------------------------------------------------- pure parts


def past_values(sets: Sequence[tuple[int, int]]) -> dict[str, float]:
    """Every B5 quantity of one finished best-of-three match from the first
    listed side's view (the caller flips), as extract_metric reads it: the
    games of a set from the set score; no set-three games for a straight-sets
    match or a match tiebreak (a 1-0 third set)."""
    s1, s2 = sets[0], sets[1]
    out = {
        "games_set1_total": float(s1[0] + s1[1]),
        "games_set2_total": float(s2[0] + s2[1]),
        "games_won_set1_for": float(s1[0]),
        "games_won_set2_for": float(s2[0]),
        "sets_total": float(len(sets)),
    }
    if len(sets) == 3 and sorted(sets[2]) != [0, 1]:
        out["games_won_set3_for"] = float(sets[2][0])
    return out


def flip(sets: Sequence[tuple[int, int]]) -> tuple[tuple[int, int], ...]:
    return tuple((b, a) for a, b in sets)


def sample_p(
    values: Sequence[float], centre: float, boundary: float, direction: str,
    weights: list[float] | None,
) -> float:
    """engine.p_empirical_centred_raw with the tilt's weights computed once a
    sample (they do not depend on the line). ``weights`` is
    ``_tilted_weights(values, centre)``; pinned against the engine in
    tests/sofa/test_audit_2026_10_13_tennis.py."""
    def wins(v: float) -> bool:
        return v > boundary if direction == "OVER" else v < boundary

    mean = statistics.mean(values)
    if centre - mean == 0.0:
        return sum(1 for v in values if wins(v)) / len(values)
    if weights is not None:
        return sum(w for w, v in zip(weights, values, strict=True) if wins(v))
    edge = max(values) if centre >= max(values) else min(values)
    return 1.0 if wins(edge) else 0.0


def sample_row_p(
    values: Sequence[float], prior: float | None, k: float, line: float,
    direction: str, weights: list[float] | None,
) -> float | None:
    """SHEET's stats-only p of one tennis empirical row, or None where F35
    refuses it (the sample's frequency or p outside the model's band)."""
    n = len(values)
    boundary = winning_boundary(line, "OVER" if direction == "OVER" else "UNDER")
    hits = sum(
        1 for v in values
        if (v > boundary if direction == "OVER" else v < boundary))
    if outside_model_resolution(hits / n):
        return None
    mean = statistics.mean(values)
    centre = mean if prior is None else (n / (n + k)) * mean + (k / (n + k)) * prior
    p = sample_p(values, centre, boundary, direction, weights)
    return None if outside_model_resolution(p) else p


def centre_of(values: Sequence[float], prior: float | None, k: float) -> float:
    mean = statistics.mean(values)
    n = len(values)
    return mean if prior is None else (n / (n + k)) * mean + (k / (n + k)) * prior


def won(value: float, line: float, direction: str) -> int:
    return int(value > line) if direction == "OVER" else int(value < line)


def ll(p: FloatArr, y: FloatArr) -> FloatArr:
    q = np.clip(p, 1e-6, 1 - 1e-6)
    out: FloatArr = -(y * np.log(q) + (1 - y) * np.log(1 - q))
    return out


def boot_mean_diff(
    match: IntArr, d: FloatArr, boot: int, seed: int = 0
) -> tuple[float, float, float]:
    """Mean of ``d`` per row and its 95% interval, resampling matches."""
    if d.size == 0:
        return math.nan, math.nan, math.nan
    _, inv = np.unique(match, return_inverse=True)
    m = int(inv.max()) + 1
    s = np.bincount(inv, weights=d, minlength=m)
    n = np.bincount(inv, minlength=m).astype(np.float64)
    rng = np.random.default_rng(seed)
    est = np.empty(boot)
    for b in range(boot):
        idx = rng.integers(0, m, m)
        est[b] = s[idx].sum() / n[idx].sum()
    lo, hi = np.percentile(est, [2.5, 97.5])
    return float(d.mean()), float(lo), float(hi)


# ---------------------------------------------------------------- history


@dataclass
class PlayerLog:
    """A player's completed best-of-three matches, newest last."""

    rows: deque[tuple[int, int, str, dict[str, float]]] = field(
        default_factory=lambda: deque(maxlen=400))


def sample_for(
    log: PlayerLog, surface: str, before_ts: int, market: str
) -> list[tuple[int, float]]:
    """(event id, value) of the player's last SAMPLE_N matches on the surface
    family before the kickoff - SAMPLES takes the events, then the metric, so
    a match without the quantity (set three) is a gap, not a substitute."""
    out: list[tuple[int, float]] = []
    taken = 0
    for ts, eid, surf, values in reversed(log.rows):
        if ts >= before_ts or surf != surface:
            continue
        taken += 1
        if market in values:
            out.append((eid, values[market]))
        if taken >= SAMPLE_N:
            break
    return out


def is_bo3_complete(r: tr.TennisResult) -> bool:
    won_sets = max(sum(a > b for a, b in r.sets), sum(b > a for a, b in r.sets))
    return r.completed and won_sets == 2 and len(r.sets) <= 3


def load_priors() -> tuple[dict[str, float], dict[str, Any]]:
    baselines = json.loads(config_path("sofa_league_baselines.json").read_text())
    glob: dict[str, float] = {}
    for m in MARKETS:
        entry = (baselines.get(m) or {}).get("global")
        if isinstance(entry, dict) and isinstance(entry.get("mean"), int | float):
            glob[m] = float(entry["mean"])
    tiers = json.loads(config_path("sofa_tennis_tier_baselines.json").read_text())
    return glob, tiers.get("metrics") or {}


def prior_of(
    market: str, category: str, surface: str, glob: Mapping[str, float],
    tiers: Mapping[str, Any],
) -> float | None:
    """sets_total: the gender x tier x surface prior (tennis_prior); the set
    games: the global baseline (what 99% / 78% of live rows read); set three
    has none."""
    if market == "sets_total":
        key = tier_key(category, surface)
        entry = (tiers.get(market) or {}).get(key) if key else None
        if isinstance(entry, Mapping) and isinstance(entry.get("mean"), int | float):
            return float(entry["mean"])
    return glob.get(market)


# ---------------------------------------------------------------- the walk


ROW_FIELDS = ("event", "ts", "window", "market", "line", "dir", "side", "tier",
              "y", "p_old", "p_new", "beyond", "mode", "n")


def walk(
    history: Sequence[tr.TennisResult],
    meta: Mapping[int, tuple[str, str]],
    window: str,
    test_from: int,
    test_to: int,
    k: float,
    glob: Mapping[str, float],
    tiers: Mapping[str, Any],
) -> tuple[dict[str, list[Any]], dict[str, int]]:
    coefficients, tier_start = clean_config(history, test_from)
    rating = tr.AsOfRating(history, coefficients, tr.V5_FEATURES, True, tier_start)
    logs: dict[int, PlayerLog] = defaultdict(PlayerLog)
    out: dict[str, list[Any]] = {f: [] for f in ROW_FIELDS}
    skips: dict[str, int] = defaultdict(int)
    win_code = {"W1": 1, "W2": 2}[window]
    j = 0
    for r in history:
        if r.ts >= test_to:
            break
        # the players' logs hold every completed bo3 match before this one
        while j < len(history) and history[j].ts < r.ts:
            h = history[j]
            j += 1
            if is_bo3_complete(h):
                logs[h.home_id].rows.append(
                    (h.ts, h.event_id, h.surface, past_values(h.sets)))
                logs[h.away_id].rows.append(
                    (h.ts, h.event_id, h.surface, past_values(flip(h.sets))))
        if r.ts < test_from:
            continue
        cat, text = meta.get(r.event_id, ("", ""))
        if is_team_cup(text):
            skips["team_cup"] += 1
            continue
        if not is_bo3_complete(r):
            skips["not_bo3_completed"] += 1
            continue
        day = r.ts - r.ts % 86400
        fc = rating.model_at(day).forecast(
            r.home_id, r.away_id, cat, r.surface, datetime.fromtimestamp(r.ts, UTC))
        if fc is None or not fc.neighbours_home:
            skips["unrated"] += 1
            continue
        actual_home = past_values(r.sets)
        actual_away = past_values(flip(r.sets))
        tier_c = tr.TIERS.index(r.tier) if r.tier in tr.TIERS else -1
        for market in MARKETS:
            sides: tuple[tuple[str | None, int, dict[str, float]], ...]
            if market in SUBJECT:
                sides = (("side_a", r.home_id, actual_home),
                         ("side_b", r.away_id, actual_away))
            else:
                sides = ((None, 0, actual_home),)
            for side, player, actual in sides:
                if market not in actual:
                    continue  # set three not played: void
                if side is None:
                    sa = sample_for(logs[r.home_id], r.surface, r.ts, market)
                    sb = sample_for(logs[r.away_id], r.surface, r.ts, market)
                    if len(sa) < MIN_SAMPLE or len(sb) < MIN_SAMPLE:
                        values: list[float] | None = None
                    else:
                        pooled = {e: v for e, v in (*sa, *sb)}
                        values = list(pooled.values())
                else:
                    own = sample_for(logs[player], r.surface, r.ts, market)
                    values = [v for _, v in own] if len(own) >= MIN_SAMPLE else None
                if values is not None and all(v == 0.0 for v in values):
                    values = None  # ALL_ZERO_SAMPLE
                prior = prior_of(market, cat, r.surface, glob, tiers)
                weights = None
                if values is not None:
                    c = centre_of(values, prior, k)
                    weights = _tilted_weights(values, c)
                for line in MARKET_LINES[market]:
                    for direction in DIRECTIONS:
                        p_old = (
                            sample_row_p(values, prior, k, line, direction, weights)
                            if values is not None else None)
                        p_new = fc.read(market, side, line, direction)
                        if p_new is not None and outside_model_resolution(p_new):
                            p_new = None
                        if p_old is None and p_new is None:
                            continue
                        out["event"].append(r.event_id)
                        out["ts"].append(r.ts)
                        out["window"].append(win_code)
                        out["market"].append(MARKETS.index(market))
                        out["line"].append(line)
                        out["dir"].append(0 if direction == "OVER" else 1)
                        out["side"].append(0 if side in (None, "side_a") else 1)
                        out["tier"].append(tier_c)
                        out["y"].append(won(actual[market], line, direction))
                        out["p_old"].append(math.nan if p_old is None else p_old)
                        out["p_new"].append(math.nan if p_new is None else p_new)
                        out["beyond"].append(
                            -1 if values is None
                            else int(line_is_beyond_sample(line, direction, values)))
                        out["mode"].append(
                            -1 if values is None
                            else int(mode_loses(line, direction, values)))
                        out["n"].append(0 if values is None else len(values))
    return out, dict(skips)


# ---------------------------------------------------------------- scoring


def score(rows: Mapping[str, Any], boot: int) -> dict[str, Any]:
    res: dict[str, Any] = {}
    p_old, p_new = rows["p_old"], rows["p_new"]
    y = rows["y"].astype(np.float64)
    for mi, market in enumerate(MARKETS):
        mk = rows["market"] == mi
        both = mk & ~np.isnan(p_old) & ~np.isnan(p_new)
        entry: dict[str, Any] = {
            "rows_old": int((mk & ~np.isnan(p_old)).sum()),
            "rows_new": int((mk & ~np.isnan(p_new)).sum()),
            "rows_both": int(both.sum()),
            "matches_both": int(np.unique(rows["event"][both]).size),
        }
        if both.sum() == 0:
            res[market] = entry
            continue
        d = ll(p_new[both], y[both]) - ll(p_old[both], y[both])
        entry["ll_old"] = float(ll(p_old[both], y[both]).mean())
        entry["ll_new"] = float(ll(p_new[both], y[both]).mean())
        entry["diff"] = boot_mean_diff(rows["event"][both], d, boot)
        for w, wname in ((1, "W1"), (2, "W2")):
            sel = both & (rows["window"] == w)
            if sel.sum():
                dw = ll(p_new[sel], y[sel]) - ll(p_old[sel], y[sel])
                entry[f"diff_{wname}"] = boot_mean_diff(rows["event"][sel], dw, boot)
                entry[f"matches_{wname}"] = int(np.unique(rows["event"][sel]).size)
        # calibration of the print zone, each estimator on its own rows
        for name, p in (("old", p_old), ("new", p_new)):
            z = mk & ~np.isnan(p) & (p >= PRINT)
            if z.sum():
                gap = y[z] - p[z]
                entry[f"print_{name}"] = {
                    "rows": int(z.sum()),
                    "matches": int(np.unique(rows["event"][z]).size),
                    "mean_p": float(p[z].mean()),
                    "realised": float(y[z].mean()),
                    "gap": boot_mean_diff(rows["event"][z], gap, boot),
                }
                gated = z & (rows["beyond"] == 1)
                moded = z & (rows["mode"] == 1)
                anyg = z & ((rows["beyond"] == 1) | (rows["mode"] == 1))
                kept = z & ~((rows["beyond"] == 1) | (rows["mode"] == 1))
                entry[f"gates_{name}"] = {
                    "LINE_BEYOND_SAMPLE": int(gated.sum()),
                    "MODE_LOSES": int(moded.sum()),
                    "either": int(anyg.sum()),
                    "no_sample": int((z & (rows["beyond"] == -1)).sum()),
                    "realised_removed": float(y[anyg].mean()) if anyg.sum() else None,
                    "mean_p_removed": float(p[anyg].mean()) if anyg.sum() else None,
                    "realised_kept": float(y[kept].mean()) if kept.sum() else None,
                    "mean_p_kept": float(p[kept].mean()) if kept.sum() else None,
                }
        res[market] = entry
    return res


def _ci(t: Sequence[float] | None, scale: float = 1e4) -> str:
    if not t:
        return "-"
    return f"{t[0] * scale:+.1f} [{t[1] * scale:+.1f}; {t[2] * scale:+.1f}]"


def render(results: Mapping[str, Any]) -> str:
    lines = ["# B5 - wynik pomiaru (log-loss, nowy - obecny, 1e-4 nat)", ""]
    lines.append("| rynek | wiersze obu | mecze | LL obecny | LL nowy | "
                 "różnica [95%] | W1 | W2 |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for m, e in results["markets"].items():
        if "diff" not in e:
            lines.append(f"| {m} | 0 | 0 | - | - | - | - | - |")
            continue
        lines.append(
            f"| {m} | {e['rows_both']} | {e['matches_both']} | {e['ll_old']:.4f} "
            f"| {e['ll_new']:.4f} | {_ci(e['diff'])} | {_ci(e.get('diff_W1'))} "
            f"| {_ci(e.get('diff_W2'))} |")
    lines.append("")
    lines.append(
        "Strefa druku (p >= 0,70): wiersze, zrealizowane - p [95%] (pp), bramki")
    for m, e in results["markets"].items():
        for name in ("old", "new"):
            pz = e.get(f"print_{name}")
            g = e.get(f"gates_{name}")
            if pz is None or g is None:
                continue
            lines.append(
                f"- {m} {name}: {pz['rows']} wierszy / {pz['matches']} meczów, "
                f"p {pz['mean_p']:.3f}, zreal. {pz['realised']:.3f}, "
                f"{_ci(pz['gap'], 100)} pp; "
                f"LINE_BEYOND_SAMPLE {g['LINE_BEYOND_SAMPLE']}, "
                f"MODE_LOSES {g['MODE_LOSES']}, razem {g['either']}, bez próbki "
                f"{g['no_sample']}")
    return "\n".join(lines) + "\n"


def _day_ts(day: str) -> int:
    return int(datetime.strptime(day, "%Y-%m-%d").replace(tzinfo=UTC).timestamp())


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", default=None, help="default: SOFA_DB_PATH / data/sofa.db")
    ap.add_argument("--out-dir", default=DEFAULT_OUT)
    ap.add_argument("--boot", type=int, default=2000)
    ap.add_argument("--rows", default=None, help="score saved rows.npz only")
    args = ap.parse_args(argv)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    if args.rows:
        loaded = np.load(args.rows)
        rows = {k: loaded[k] for k in loaded.files}
        meta_out: dict[str, Any] = json.loads(
            (out / "walk.json").read_text()) if (out / "walk.json").exists() else {}
    else:
        from bet.sofa.config import SofaConfig

        db = args.db or SofaConfig.from_env().db_path
        constants = json.loads(config_path("sofa_engine_constants.json").read_text())
        k = float(constants["K_CENTRE"]["by_sport"].get("tennis", K_TENNIS))
        glob, tiers = load_priors()
        history, meta = load(str(db))
        print(f"history {len(history)} matches ({time.time() - t0:.0f}s)", flush=True)
        parts: list[dict[str, list[Any]]] = []
        meta_out = {"db": str(db), "k": k, "priors": glob, "skips": {}}
        for name, a, b in WINDOWS:
            part, skips = walk(history, meta, name, _day_ts(a), _day_ts(b), k,
                               glob, tiers)
            parts.append(part)
            meta_out["skips"][name] = skips
            print(f"{name}: {len(part['event'])} rows, skips {skips} "
                  f"({time.time() - t0:.0f}s)", flush=True)
        rows = {
            f: np.asarray([v for p in parts for v in p[f]],
                          dtype=np.float64 if f in ("line", "p_old", "p_new")
                          else np.int64)
            for f in ROW_FIELDS
        }
        np.savez_compressed(out / "rows.npz", **rows)
        (out / "walk.json").write_text(json.dumps(meta_out, indent=1))
    results = {**meta_out, "boot": args.boot, "markets": score(rows, args.boot)}
    (out / "results.json").write_text(json.dumps(results, indent=1))
    (out / "report.md").write_text(render(results))
    print(render(results))
    print(f"wrote {out} ({time.time() - t0:.0f}s)", flush=True)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED: {exc!r}", file=sys.stderr)
        raise SystemExit(2) from exc
