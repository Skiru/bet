"""Does knowing a football team's actual starting XI improve pre-match
forecasts of its counting statistics? Measured, out of sample - read-only.

The question is the UPPER BOUND for using Sofascore's predicted lineups: a
predicted XI can only be worse than the XI that actually started. If the real
XI adds nothing to a simple as-of forecast, the idea is closed.

``collect`` reads every finished, non-friendly football match with a cached
squad list (``calibrate_from_cache.player_targets``: one listing per match,
friendlies out by ``samples.FRIENDLY_COMPETITION_IDS`` - the same id list
``bet.sofa.comparability`` reads) and writes one line per team-match:

* the team's counts (``metrics.extract_metric``: shots, shots on target,
  corners, fouls, goals, card points) and its XI (``substitute`` false),
  with each player's minutes, shots and position;

and then, per team-match, AS OF the match (only strictly earlier matches of
that team that carry a lineup), over its last ``--window`` such matches:

* ``miss``     - start share of the regulars not in today's XI: sum over
  absent players of starts/N, divided by sum over all of starts/N
  (11 when every match is counted);
* ``miss_core`` - share of the core regulars (start share >= 0.7 over the
  window) not in today's XI - the "a key man is out" feature;
* ``miss_att`` - the absent players' share of the team's shots over the
  window (sum of their shots / team's shots in those matches);
* ``miss_def`` - ``miss`` restricted to goalkeepers and defenders;
* ``changes``  - starters not in the previous XI, / 11;
* baseline means: the team's mean count for and against over the same
  window, home flag.

``analyse`` fits, per target, a Poisson log-linear model on the TRAIN rows

    baseline : log mu = b0 + b1 log(for_T) + b2 log(against_O) + b3 home
                        + b4 knockout (comparability.is_knockout: a cup round
                          is known pre-match and is when sides rotate)
    augmented: baseline + own (miss, miss_core, miss_att, miss_def, changes)
                        + the opponent's same five

(own absences for the team's own count; the opponent's absences read the
"against" side: a weakened defence lets more shots in) and judges both on
the TEST rows: Poisson and negative-binomial log-loss (dispersion fitted on
train per arm, method of moments) and Brier at typical Superbet lines, the
delta augmented - baseline (negative = the XI helps), a 95% interval from
resampling whole matches. Two splits: by time (``--split``) and by event-id
parity (even train, odd test). Also: the distribution of ``miss``, the
centre change per +10 pp of missing regulars, the delta inside large
absences, and a player-side check - when a team's top shooter does not start,
do the other starters out-shoot their raw share of the team's actual shots?
(the m = 0 analogue of ``bet.sofa.player_share``; measured, not implemented).

Baseline is deliberately simple (no SHEET replay, no league prior, no rating):
the absence terms are tested against an as-of rolling mean only. A gain here
is necessary, not sufficient, for a gain over SHEET.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_lineup_absence.py \\
        collect --db-path data/sofa.db --out <features.jsonl.gz>
    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_lineup_absence.py \\
        analyse --features <features.jsonl.gz> --split 2026-04-01 [--json <out>]

The DB is opened read-only (``mode=ro`` URI); nothing the pipeline reads is
written.
"""

from __future__ import annotations

import argparse
import collections
import gzip
import json
import math
import sqlite3
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO / "src"), str(_REPO)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np  # noqa: E402
from numpy.typing import NDArray  # noqa: E402

from bet.sofa.comparability import is_knockout  # noqa: E402
from bet.sofa.metrics import extract_flat_statistics, extract_metric  # noqa: E402
from scripts.sofa import calibrate_from_cache as cfc  # noqa: E402

FloatArray = NDArray[np.float64]

TARGETS: tuple[str, ...] = (
    "shots_for", "shots_on_target_for", "corners_for", "fouls_for",
    "goals_for", "cards_points_for",
)
LINES: dict[str, tuple[float, ...]] = {
    "shots_for": (10.5, 12.5),
    "shots_on_target_for": (3.5, 4.5),
    "corners_for": (4.5, 5.5),
    "fouls_for": (10.5, 12.5),
    "goals_for": (0.5, 1.5),
    "cards_points_for": (1.5, 2.5),
}
FEATURES: tuple[str, ...] = ("miss", "miss_core", "miss_att", "miss_def", "changes")
CORE_SHARE = 0.7
MIN_HISTORY = 5
MAX_GAP_DAYS = 45
BOOT = 1000


# ---------------------------------------------------------------- collect


def _player_shots(stats: dict[str, Any]) -> float:
    value = stats.get("totalShots")
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    parts = [stats.get(k) for k in ("onTargetScoringAttempt", "shotOffTarget",
                                    "blockedScoringAttempt")]
    return float(sum(p for p in parts
                     if isinstance(p, int | float) and not isinstance(p, bool)))


def _side_lineup(lineups: dict[str, Any] | None, side: str) -> dict[str, Any] | None:
    """{xi: [ids], players: {id: [minutes, shots, pos, started]}} or None."""
    block = (lineups or {}).get(side) or {}
    players: dict[str, list[Any]] = {}
    xi: list[int] = []
    for entry in block.get("players") or []:
        player = (entry or {}).get("player") or {}
        pid = player.get("id")
        if not isinstance(pid, int):
            continue
        stats = entry.get("statistics") or {}
        minutes = stats.get("minutesPlayed")
        mins = float(minutes) if isinstance(minutes, int | float) else 0.0
        pos = str(entry.get("position") or player.get("position") or "")[:1].upper()
        start = entry.get("substitute") is False
        if start:
            xi.append(pid)
        players[str(pid)] = [mins, _player_shots(stats), pos, start]
    if len(xi) != 11:
        return None
    return {"xi": xi, "players": players}


def _team_id(event: dict[str, Any], side: str) -> int | None:
    team = event.get(f"{side}Team") or {}
    tid = team.get("id")
    return tid if isinstance(tid, int) else None


def _features(history: list[dict[str, Any]], xi: list[int]) -> dict[str, float]:
    """Absence features of today's XI against the team's earlier matches
    (``history`` newest last)."""
    n = len(history)
    starts: collections.Counter[int] = collections.Counter()
    shots: collections.Counter[int] = collections.Counter()
    pos: dict[int, str] = {}
    team_shots = 0.0
    for rec in history:
        for pid_s, (_mins, sh, p, start) in rec["players"].items():
            pid = int(pid_s)
            if start:
                starts[pid] += 1
            shots[pid] += sh
            team_shots += sh
            if p:
                pos[pid] = p
    today = set(xi)
    total = sum(starts.values()) / n
    missing = sum(c for pid, c in starts.items() if pid not in today) / n
    def_total = sum(c for pid, c in starts.items() if pos.get(pid) in ("G", "D")) / n
    def_missing = sum(c for pid, c in starts.items()
                      if pid not in today and pos.get(pid) in ("G", "D")) / n
    core = [pid for pid, c in starts.items() if c / n >= CORE_SHARE]
    core_missing = (sum(1 for pid in core if pid not in today) / len(core)
                    if core else 0.0)
    att_missing = (sum(s for pid, s in shots.items() if pid not in today) / team_shots
                   if team_shots > 0 else 0.0)
    prev = set(history[-1]["xi"])
    return {
        "miss": missing / total if total > 0 else 0.0,
        "miss_core": core_missing,
        "miss_att": att_missing,
        "miss_def": def_missing / def_total if def_total > 0 else 0.0,
        "changes": len(today - prev) / 11.0,
    }


def _shooter_check(history: list[dict[str, Any]], today: dict[str, Any],
                   team_shots_today: float | None) -> dict[str, Any] | None:
    """Top shooter of the window absent or present; the other starters'
    actual shots vs raw share x the team's actual shots today."""
    if team_shots_today is None or team_shots_today <= 0:
        return None
    p_shots: collections.Counter[int] = collections.Counter()
    p_team: collections.Counter[int] = collections.Counter()
    p_starts: collections.Counter[int] = collections.Counter()
    for rec in history:
        tshots = sum(v[1] for v in rec["players"].values())
        for pid_s, (_m, sh, _p, start) in rec["players"].items():
            if start:
                pid = int(pid_s)
                p_starts[pid] += 1
                p_shots[pid] += sh
                p_team[pid] += tshots
    regular = [pid for pid, c in p_starts.items() if c >= MIN_HISTORY]
    if not regular:
        return None
    top = max(regular, key=lambda pid: p_shots[pid] / p_team[pid] if p_team[pid] else 0)
    if p_team[top] <= 0 or p_shots[top] / p_team[top] < 0.15:
        return None
    xi = set(today["xi"])
    predicted = 0.0
    actual = 0.0
    for pid in xi:
        if pid == top or p_starts[pid] < 3 or p_team[pid] <= 0:
            continue
        share = p_shots[pid] / p_team[pid]
        predicted += share * team_shots_today
        actual += float(today["players"][str(pid)][1])
    if predicted <= 0:
        return None
    return {"top_absent": top not in xi, "pred": predicted, "act": actual}


def collect(db_path: Path, out: Path, window: int) -> collections.Counter[str]:
    counts: collections.Counter[str] = collections.Counter()
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    targets = cfc.player_targets(conn, counts)
    print(f"{len(targets)} football matches with a squad list", file=sys.stderr,
          flush=True)
    by_team: dict[int, list[dict[str, Any]]] = collections.defaultdict(list)
    for i, event in enumerate(targets):
        if i % 5000 == 0:
            print(f"  read {i}/{len(targets)}", file=sys.stderr, flush=True)
        eid = int(event["id"])
        row = conn.execute(
            "SELECT statistics_json, incidents_json, lineups_json FROM "
            "sofa_event_stats WHERE sofascore_event_id = ?", (eid,)).fetchone()
        if row is None or not row[2]:
            counts["no_row"] += 1
            continue
        stats = json.loads(row[0]) if row[0] else None
        incidents = json.loads(row[1]) if row[1] else None
        lineups = json.loads(row[2])
        flat = extract_flat_statistics(stats)
        for side, is_home in (("home", True), ("away", False)):
            tid = _team_id(event, side)
            lu = _side_lineup(lineups, side)
            if tid is None or lu is None:
                counts["side_without_xi"] += 1
                continue
            vals: dict[str, float | None] = {}
            against: dict[str, float | None] = {}
            for metric in TARGETS:
                v = extract_metric(metric, "football", flat, incidents, event, is_home)
                o = extract_metric(metric, "football", flat, incidents, event,
                                   not is_home)
                vals[metric] = float(v) if isinstance(v, int | float) else None
                against[metric] = float(o) if isinstance(o, int | float) else None
            by_team[tid].append({
                "event_id": eid, "ts": int(event["startTimestamp"]),
                "team": tid, "opp": _team_id(event, "away" if is_home else "home"),
                "home": is_home, "knockout": is_knockout(event), "for": vals,
                "against": against, **lu,
            })
    # as-of features
    per_event: dict[int, dict[int, dict[str, Any]]] = collections.defaultdict(dict)
    shooter: list[dict[str, Any]] = []
    for tid, recs in by_team.items():
        recs.sort(key=lambda r: (r["ts"], r["event_id"]))
        for j, rec in enumerate(recs):
            history = [h for h in recs[max(0, j - window):j]
                       if rec["ts"] - h["ts"] <= 365 * 86400]
            if len(history) < MIN_HISTORY or \
                    rec["ts"] - history[-1]["ts"] > MAX_GAP_DAYS * 86400:
                counts["thin_history"] += 1
                continue
            feats = _features(history, rec["xi"])
            means_for: dict[str, float | None] = {}
            means_against: dict[str, float | None] = {}
            for metric in TARGETS:
                f = [h["for"][metric] for h in history if h["for"][metric] is not None]
                a = [h["against"][metric] for h in history
                     if h["against"][metric] is not None]
                means_for[metric] = sum(f) / len(f) if len(f) >= MIN_HISTORY else None
                means_against[metric] = (sum(a) / len(a) if len(a) >= MIN_HISTORY
                                         else None)
            per_event[rec["event_id"]][tid] = {
                "event_id": rec["event_id"], "ts": rec["ts"], "team": tid,
                "opp": rec["opp"], "home": rec["home"],
                "knockout": rec["knockout"], "y": rec["for"],
                "mean_for": means_for, "mean_against": means_against,
                "n_hist": len(history), **feats,
            }
            check = _shooter_check(history, rec, rec["for"]["shots_for"])
            if check is not None:
                shooter.append({"event_id": rec["event_id"], "ts": rec["ts"], **check})
    with gzip.open(out, "wt") as fh:
        for eid, sides in per_event.items():
            if len(sides) != 2:
                counts["one_side_only"] += 1
                continue
            pair = list(sides.values())
            for me, opp in ((pair[0], pair[1]), (pair[1], pair[0])):
                row = dict(me)
                row["opp_mean_against"] = opp["mean_against"]
                for feat in FEATURES:
                    row[f"opp_{feat}"] = opp[feat]
                fh.write(json.dumps({"kind": "team", **row}) + "\n")
                counts["team_rows"] += 1
        for s in shooter:
            fh.write(json.dumps({"kind": "shooter", **s}) + "\n")
            counts["shooter_rows"] += 1
    return counts


# ---------------------------------------------------------------- analyse


def _fit_poisson(x: FloatArray, y: FloatArray, iters: int = 50) -> FloatArray:
    """IRLS for log mu = x @ beta, a small ridge for stability."""
    beta: FloatArray = np.zeros(x.shape[1], dtype=np.float64)
    beta[0] = math.log(max(float(y.mean()), 1e-3))
    ridge = 1e-6 * np.eye(x.shape[1])
    for _ in range(iters):
        eta = np.clip(x @ beta, -10, 10)
        mu = np.exp(eta)
        z = eta + (y - mu) / mu
        xtw = x.T * mu
        new = np.linalg.solve(xtw @ x + ridge, xtw @ z)
        if float(np.max(np.abs(new - beta))) < 1e-8:
            return np.asarray(new, dtype=np.float64)
        beta = np.asarray(new, dtype=np.float64)
    return np.asarray(beta, dtype=np.float64)


def _lgamma(v: FloatArray) -> FloatArray:
    return np.asarray(np.vectorize(math.lgamma)(v), dtype=np.float64)


def _poisson_nll(y: FloatArray, mu: FloatArray) -> FloatArray:
    return np.asarray(mu - y * np.log(mu) + _lgamma(y + 1.0), dtype=np.float64)


def _nb_nll(y: FloatArray, mu: FloatArray, alpha: float) -> FloatArray:
    if alpha <= 1e-6:
        return _poisson_nll(y, mu)
    r = 1.0 / alpha
    ll = (_lgamma(y + r) - math.lgamma(r) - _lgamma(y + 1.0)
          + r * np.log(r / (r + mu)) + y * np.log(mu / (r + mu)))
    return np.asarray(-ll, dtype=np.float64)


def _nb_over(line: float, mu: FloatArray, alpha: float) -> FloatArray:
    """P(Y > line) under NB(mu, alpha) (Poisson when alpha ~ 0)."""
    k_max = int(math.floor(line))
    cdf = np.zeros_like(mu)
    if alpha <= 1e-6:
        term = np.exp(-mu)
        for k in range(k_max + 1):
            if k > 0:
                term = term * mu / k
            cdf += term
        return np.asarray(1.0 - cdf, dtype=np.float64)
    r = 1.0 / alpha
    p = r / (r + mu)
    term = np.power(p, r)
    for k in range(k_max + 1):
        if k > 0:
            term = term * (k - 1 + r) / k * (1 - p)
        cdf += term
    return np.asarray(1.0 - cdf, dtype=np.float64)


def _alpha(y: FloatArray, mu: FloatArray) -> float:
    return max(float(np.mean(((y - mu) ** 2 - mu) / mu ** 2)), 0.0)


def _design(rows: Sequence[dict[str, Any]], metric: str,
            augmented: bool) -> FloatArray:
    cols: list[list[float]] = []
    for r in rows:
        f = max(float(r["mean_for"][metric]), 0.1)
        a = max(float(r["opp_mean_against"][metric]), 0.1)
        c = [1.0, math.log(f), math.log(a), 1.0 if r["home"] else 0.0,
             1.0 if r["knockout"] else 0.0]
        if augmented:
            c += [float(r[k]) for k in FEATURES]
            c += [float(r[f"opp_{k}"]) for k in FEATURES]
        cols.append(c)
    return np.asarray(cols, dtype=np.float64)


def _boot(per_match: dict[int, float], n_rows: int,
          rng: np.random.Generator) -> tuple[float, float, float]:
    vals = np.asarray(list(per_match.values()), dtype=np.float64)
    point = float(vals.sum() / n_rows)
    rows_per = n_rows / len(vals)
    draws = []
    for _ in range(BOOT):
        idx = rng.integers(0, len(vals), len(vals))
        draws.append(float(vals[idx].sum() / (rows_per * len(vals))))
    lo, hi = np.percentile(draws, [2.5, 97.5])
    return point, float(lo), float(hi)


def _evaluate(train: list[dict[str, Any]], test: list[dict[str, Any]], metric: str,
              rng: np.random.Generator) -> dict[str, Any]:
    def usable(r: dict[str, Any]) -> bool:
        return (r["y"][metric] is not None and r["mean_for"][metric] is not None
                and r["opp_mean_against"][metric] is not None)

    tr = [r for r in train if usable(r)]
    te = [r for r in test if usable(r)]
    ytr = np.asarray([r["y"][metric] for r in tr], dtype=np.float64)
    yte = np.asarray([r["y"][metric] for r in te], dtype=np.float64)
    out: dict[str, Any] = {"train_rows": len(tr), "test_rows": len(te),
                           "test_matches": len({r["event_id"] for r in te})}
    res: dict[str, dict[str, Any]] = {}
    for arm, aug in (("base", False), ("aug", True)):
        beta = _fit_poisson(_design(tr, metric, aug), ytr)
        mu_tr = np.exp(_design(tr, metric, aug) @ beta)
        alpha = _alpha(ytr, mu_tr)
        mu = np.exp(_design(te, metric, aug) @ beta)
        res[arm] = {"beta": beta, "alpha": alpha, "mu": mu,
                    "pois": _poisson_nll(yte, mu), "nb": _nb_nll(yte, mu, alpha)}
        out[f"{arm}_alpha"] = round(alpha, 4)
        out[f"{arm}_nb_logloss"] = round(float(res[arm]["nb"].mean()), 5)
    beta_aug = res["aug"]["beta"]
    names = [*FEATURES, *(f"opp_{k}" for k in FEATURES)]
    out["coef"] = {n: round(float(b), 4) for n, b in zip(names, beta_aug[5:],
                                                          strict=True)}
    out["centre_per_10pp"] = {
        n: round(math.exp(0.1 * float(b)) - 1, 4)
        for n, b in zip(names, beta_aug[5:], strict=True)}
    eids = [int(r["event_id"]) for r in te]

    def per_match(values: FloatArray, mask: FloatArray | None = None
                  ) -> tuple[dict[int, float], int]:
        acc: dict[int, float] = collections.defaultdict(float)
        n = 0
        for i, e in enumerate(eids):
            if mask is not None and not mask[i]:
                continue
            acc[e] += float(values[i])
            n += 1
        return acc, n

    for loss in ("pois", "nb"):
        d = res["aug"][loss] - res["base"][loss]
        acc, n = per_match(d)
        out[f"delta_{loss}"] = [round(v, 5) for v in _boot(acc, n, rng)]
    core = np.asarray([r["miss_core"] for r in te], dtype=np.float64)
    big = core >= 0.3
    if int(big.sum()) >= 200:
        d = res["aug"]["nb"] - res["base"]["nb"]
        acc, n = per_match(d, big.astype(np.float64))
        out["delta_nb_core_ge_0.3"] = [round(v, 5) for v in _boot(acc, n, rng)]
        out["rows_core_ge_0.3"] = int(big.sum())
    for line in LINES[metric]:
        hit = (yte > line).astype(np.float64)
        briers = {arm: (_nb_over(line, res[arm]["mu"], res[arm]["alpha"]) - hit) ** 2
                  for arm in ("base", "aug")}
        acc, n = per_match(briers["aug"] - briers["base"])
        out[f"delta_brier_{line}"] = [round(v, 6) for v in _boot(acc, n, rng)]
        out[f"base_brier_{line}"] = round(float(briers["base"].mean()), 5)
    return out


def _date(ts: int) -> str:
    return datetime.fromtimestamp(ts, UTC).date().isoformat()


def analyse(features: Path, split: str) -> dict[str, Any]:
    teams: list[dict[str, Any]] = []
    shooter: list[dict[str, Any]] = []
    with gzip.open(features, "rt") as fh:
        for line in fh:
            rec = json.loads(line)
            (teams if rec.pop("kind") == "team" else shooter).append(rec)
    split_ts = int(datetime.fromisoformat(split).replace(tzinfo=UTC).timestamp())
    rng = np.random.default_rng(20261023)
    miss = np.asarray([r["miss"] for r in teams], dtype=np.float64)
    report: dict[str, Any] = {
        "team_rows": len(teams), "matches": len({r["event_id"] for r in teams}),
        "first": _date(min(r["ts"] for r in teams)),
        "last": _date(max(r["ts"] for r in teams)),
        "split": split,
        "miss_quantiles": {q: round(float(np.quantile(miss, q / 100)), 3)
                           for q in (10, 25, 50, 75, 90, 95, 99)},
        "miss_share_ge": {t: round(float((miss >= t).mean()), 4)
                          for t in (0.1, 0.2, 0.3, 0.5)},
        "time": {}, "parity": {},
    }
    core_all = np.asarray([r["miss_core"] for r in teams], dtype=np.float64)
    report["miss_core_share_ge"] = {t: round(float((core_all >= t).mean()), 4)
                                    for t in (0.1, 0.2, 0.3, 0.5)}
    for feat in ("miss_core", "miss_att", "miss_def", "changes"):
        arr = np.asarray([r[feat] for r in teams], dtype=np.float64)
        report[f"{feat}_quantiles"] = {q: round(float(np.quantile(arr, q / 100)), 3)
                                       for q in (50, 90, 99)}
    train_t = [r for r in teams if r["ts"] < split_ts]
    test_t = [r for r in teams if r["ts"] >= split_ts]
    train_p = [r for r in teams if r["event_id"] % 2 == 0]
    test_p = [r for r in teams if r["event_id"] % 2 == 1]
    for metric in TARGETS:
        print(f"  {metric}", file=sys.stderr, flush=True)
        report["time"][metric] = _evaluate(train_t, test_t, metric, rng)
        report["parity"][metric] = _evaluate(train_p, test_p, metric, rng)
    # player side
    sh: dict[str, Any] = {}
    for absent in (True, False):
        rows = [s for s in shooter if s["top_absent"] is absent]
        by_match: dict[int, list[float]] = collections.defaultdict(lambda: [0.0, 0.0])
        for s in rows:
            by_match[s["event_id"]][0] += s["act"]
            by_match[s["event_id"]][1] += s["pred"]
        vals = np.asarray(list(by_match.values()), dtype=np.float64)
        ratio = float(vals[:, 0].sum() / vals[:, 1].sum())
        draws = []
        for _ in range(BOOT):
            idx = rng.integers(0, len(vals), len(vals))
            draws.append(float(vals[idx, 0].sum() / vals[idx, 1].sum()))
        lo, hi = np.percentile(draws, [2.5, 97.5])
        sh["absent" if absent else "present"] = {
            "team_rows": len(rows), "actual_over_share_pred": round(ratio, 4),
            "ci": [round(float(lo), 4), round(float(hi), 4)]}
    report["top_shooter"] = sh
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect")
    c.add_argument("--db-path", type=Path, default=_REPO / "data" / "sofa.db")
    c.add_argument("--out", type=Path, required=True)
    c.add_argument("--window", type=int, default=10)
    a = sub.add_parser("analyse")
    a.add_argument("--features", type=Path, required=True)
    a.add_argument("--split", default="2026-04-01")
    a.add_argument("--json", type=Path)
    args = parser.parse_args(argv)
    if args.cmd == "collect":
        counts = collect(args.db_path, args.out, args.window)
        print(json.dumps(dict(counts), indent=1))
        return 0
    report = analyse(args.features, args.split)
    text = json.dumps(report, indent=1)
    if args.json:
        args.json.write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
