#!/usr/bin/env python3
# ruff: noqa: E501  - report lines are tables.
"""History curves of the tennis serve markets, staged for
install_new_market_curves.py (group `tennis_serve`, which REPLACES the
markets' curves - never adds beside them).

The markets: the aces family under epochs.TENNIS_ACES_OPPONENT (aces_for /
aces_total and the per-set aces, centre x the returner's factor) and the serve
markets the replay never read before 2026-10-17 (per-set double faults, aces +
double faults match and per set). Their rows come from the cache replay
(calibrate_from_cache.iter_rows - the functions SHEET prices with), run here
over the cached tennis history alone with the live tennis rules: SAMPLES'
format / surface scoping (TENNIS_SAMPLE_SCOPE), the aces correction, the serve
bases (--tennis-serve-markets). Full-match double faults are not here: their
model did not change and the refit's own replay fits them.

Curves exactly as fit_confidence writes them (EDGES, MIN_MARKET_BUCKET,
MIN_THIN_BUCKET; every row in the top-level curves, a classed row also in its
class - tennis_women / tennis_team_cup), then each market x direction key
(and class key) judged by the ONE-SIDED holdout gate of the new markets
(scripts/sofa/new_market_gate.py: fit before --gate-cut, judged on the rows
from it; a key fails only when its curve overstates by > 2 pp at curve >=
0.70 with n >= 300, or its final curve never reaches 0.70). A key that fails
is not installed, and then neither is its market's pooled `by_market` curve
in that section (it would stand in for the failed direction); the thin
buckets install always (they only cap).

Read-only on the DB (no row written). Output: <out-dir>/tennis_serve/
curves.json and report.md.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/fit_tennis_serve_curves.py \\
        --before 2026-10-17 --out-dir data/refit_tennis_serve_2026-10-17 \\
        [--gate-cut 2026-09-01] [--played-cache <pkl>]
"""

from __future__ import annotations

import argparse
import collections
import json
import pickle
import sys
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import scripts.sofa.calibrate_from_cache as cc
from bet.sofa.atomic import write_atomic
from bet.sofa.confidence import direction_key, match_class
from bet.sofa.config import SofaConfig
from bet.sofa.tennis_aces_opponent import ACES_MARKETS
from bet.sofa.tennis_prior import load_tier_baselines
from scripts.sofa.fit_confidence import MIN_MARKET_BUCKET, MIN_THIN_BUCKET
from scripts.sofa.new_market_gate import fit_curve, gate, require_final

GROUP = "tennis_serve"
SERVE_MARKETS = frozenset(
    f"{base}_{suffix}"
    for base in ("double_faults_set1", "double_faults_set2", "serve_points",
                 "serve_points_set1", "serve_points_set2")
    for suffix in ("for", "total"))
MARKETS = ACES_MARKETS | SERVE_MARKETS
# what a refit must replay so its own curves of these markets describe the
# centre SHEET prices (prepare_refit.dropped_replay_rules)
REQUIRES = ["tennis_aces_opponent", "tennis_serve_markets",
            "tennis_sample_scope"]

# (p, won, event id, ts, class, market, direction)
Row = tuple[float, int, int, int, str | None, str, str]


def load_played(db: Path, cache: Path | None) -> list[cc.Played]:
    if cache is not None and cache.exists():
        with cache.open("rb") as fh:
            played: list[cc.Played] = pickle.load(fh)
        return played
    played = cc.load_cache(db, tennis_serve=True, sports=("tennis",))
    if cache is not None:
        cache.parent.mkdir(parents=True, exist_ok=True)
        with cache.open("wb") as fh:
            pickle.dump(played, fh)
    return played


def replay_rows(played: Sequence[cc.Played], before_ts: int,
                aces_opponent: bool = True) -> list[Row]:
    cc.TENNIS_SAMPLE_SCOPE = True
    cc.TENNIS_ACES_OPPONENT = aces_opponent
    if aces_opponent and not cc.TENNIS_ACES_TIERS:
        cc.TENNIS_ACES_TIERS = load_tier_baselines()
    held = [m for m in played if m.timestamp < before_ts]
    meta = {m.event_id: (m.timestamp, match_class(
        "tennis", m.tennis.category_name if m.tennis else "")) for m in held}
    out: list[Row] = []
    for r in cc.iter_rows(held, cc.load_baselines()):
        if r.market not in MARKETS:
            continue
        ts, klass = meta[r.event_id]
        out.append((r.p_central, int(r.won), r.event_id, ts, klass or None,
                    r.market, r.direction))
    return out


def sections(rows: Iterable[Row]) -> dict[str, Any]:
    """fit_confidence's by_market / by_market_direction /
    thin_by_market_direction, top level (every row) and per class."""
    per_market: dict[str, list[tuple[float, int]]] = collections.defaultdict(list)
    per_dir: dict[str, list[tuple[float, int]]] = collections.defaultdict(list)
    cls_market: dict[str, dict[str, list[tuple[float, int]]]] = collections.defaultdict(
        lambda: collections.defaultdict(list))
    cls_dir: dict[str, dict[str, list[tuple[float, int]]]] = collections.defaultdict(
        lambda: collections.defaultdict(list))
    for p, won, _e, _ts, klass, market, direction in rows:
        key = direction_key(market, direction)
        per_market[market].append((p, won))
        per_dir[key].append((p, won))
        if klass:
            cls_market[klass][market].append((p, won))
            cls_dir[klass][key].append((p, won))

    def three(by_m: dict[str, list[tuple[float, int]]],
              by_d: dict[str, list[tuple[float, int]]]) -> dict[str, Any]:
        thin = {}
        for k, v in by_d.items():
            full = fit_curve(v, MIN_THIN_BUCKET)
            dense = fit_curve(v, MIN_MARKET_BUCKET)
            t = {b: e for b, e in full.items() if b not in dense}
            if t:
                thin[k] = t
        return {
            "by_market": {k: c for k, v in by_m.items() if (c := fit_curve(v))},
            "by_market_direction": {k: c for k, v in by_d.items()
                                    if (c := fit_curve(v))},
            "thin_by_market_direction": thin,
        }

    out = three(per_market, per_dir)
    out["by_class"] = {k: three(cls_market[k], cls_dir[k]) for k in sorted(cls_dir)}
    return out


def gates(rows: Sequence[Row], cut_ts: int, final: dict[str, Any]) -> dict[str, Any]:
    """The one-sided holdout verdict of every direction curve in `final`."""
    out: dict[str, Any] = {}

    def judge(gk: str, klass: str | None, key: str, curve: dict[str, Any]) -> None:
        market, _, direction = key.partition("|")
        mine = [r for r in rows if r[5] == market and r[6] == direction
                and (klass is None or r[4] == klass)]
        train = fit_curve((r[0], r[1]) for r in mine if r[3] < cut_ts)
        hold = [(r[0], r[1], r[2]) for r in mine if r[3] >= cut_ts]
        out[gk] = require_final(gate(train, hold), curve)

    for key, curve in final["by_market_direction"].items():
        judge(key, None, key, curve)
    for klass, sec in final["by_class"].items():
        for key, curve in sec["by_market_direction"].items():
            judge(f"{klass}:{key}", klass, key, curve)
    return out


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db-path", default=None)
    ap.add_argument("--before", required=True)
    ap.add_argument("--gate-cut", default="2026-09-01")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--played-cache", default=None)
    args = ap.parse_args(argv)
    db = Path(args.db_path or SofaConfig.from_env().db_path)
    before_ts = int(datetime.fromisoformat(args.before).replace(tzinfo=UTC).timestamp())
    cut_ts = int(datetime.fromisoformat(args.gate_cut).replace(tzinfo=UTC).timestamp())
    played = load_played(db, Path(args.played_cache) if args.played_cache else None)
    rows = replay_rows(played, before_ts)
    print(f"tennis matches {len(played)}, serve rows {len(rows)}", file=sys.stderr)
    final = sections(rows)
    verdicts = gates(rows, cut_ts, final)
    doc = {
        "target": "sofa_confidence_calibration.json",
        "replace_markets": sorted(MARKETS),
        **final,
        "gate": verdicts,
        "fitted_from": {
            "script": "scripts/sofa/fit_tennis_serve_curves.py",
            "fitted_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
            "db_path": str(db), "before": args.before,
            "gate_cut": args.gate_cut, "rows": len(rows),
            "matches": len({r[2] for r in rows}),
            "requires_replay_flags": REQUIRES,
        },
    }
    out = Path(args.out_dir) / GROUP
    out.mkdir(parents=True, exist_ok=True)
    write_atomic(out / "curves.json", json.dumps(doc, indent=2))
    lines = [f"# tennis serve curves, rows before {args.before}, gate cut {args.gate_cut}",
             "", "| key | holdout n >= 0.70 | curve | realised | gap [95%] | verdict |",
             "|---|---|---|---|---|---|"]
    for k, g in sorted(verdicts.items()):
        ci = g.get("gap_ci95") or ["", ""]
        lines.append(f"| {k} | {g['n']} | {g.get('mean_curve')} | {g.get('realised')} | "
                     f"{g.get('gap')} [{ci[0]}, {ci[1]}] | "
                     f"{'PASS' if g['pass'] else 'FAIL: ' + str(g.get('why'))} |")
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
