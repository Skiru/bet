#!/usr/bin/env python3
# ruff: noqa: E501  - report lines are tables.
"""Out-of-sample measurement of epochs.TENNIS_ACES_OPPONENT on the cache replay.

The replay (calibrate_from_cache.iter_rows, the functions SHEET prices with)
is run twice over the cached tennis history - the server's sample alone, and
the centre x the returner's factor (bet.sofa.tennis_aces_opponent) - with
SAMPLES' tennis scoping (TENNIS_SAMPLE_SCOPE) and the serve markets replayed
(--tennis-serve-markets) in both. Each arm's rows are calibrated the way
CONFIDENCE reads a curve: the bucket realised rate per market x direction
(x the women's class, fit_confidence.event_class) fitted on the rows before
``--cut``, read on the rows from it. Reported per market, new minus old:

  * calibrated log-loss on every replayed line, and on the market-like lines
    only (the old arm's p_over in [0.35, 0.65] - Superbet quotes one line near
    the middle, where the history curve's easy rungs are absent);
  * at calibrated confidence >= 0.70 on the market-like lines: n, confidence,
    realised (what would reach the coupon's floor and how it holds).

95% intervals from resampling whole matches. Read-only: the DB is read, no
row written. The tennis history is loaded once and pickled to
``--played-cache``.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_tennis_aces_opponent.py \\
        --cut 2026-01-01 [--played-cache data/cache/tennis_played.pkl] \\
        [--md-out f] [--json-out f]
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import pickle
import random
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import scripts.sofa.calibrate_from_cache as cc
from bet.sofa.confidence import match_class
from bet.sofa.config import SofaConfig
from bet.sofa.tennis_prior import load_tier_baselines
from scripts.sofa.fit_confidence import EDGES, bucket_of

ACES = ("aces_for", "aces_total", "aces_set1_for", "aces_set1_total",
        "aces_set2_for", "aces_set2_total")
MARKETS = ACES
MIN_BUCKET = 50
FLOOR = 0.70


@dataclass(frozen=True)
class Row:
    event_id: int
    ts: int
    market: str
    subject: str
    line: float
    direction: str
    p: float
    won: bool


def load_played(db_path: Path, cache: Path | None) -> list[cc.Played]:
    if cache is not None and cache.exists():
        with cache.open("rb") as fh:
            played: list[cc.Played] = pickle.load(fh)
        return played
    played = cc.load_cache(db_path, tennis_serve=True, sports=("tennis",))
    if cache is not None:
        cache.parent.mkdir(parents=True, exist_ok=True)
        with cache.open("wb") as fh:
            pickle.dump(played, fh)
    return played


def tennis_classes(played: Iterable[cc.Played]) -> dict[int, str]:
    """event id -> match class, from the category name as run_confidence
    reads it (fit_confidence.event_class)."""
    out: dict[int, str] = {}
    for m in played:
        if m.tennis is not None:
            klass = match_class("tennis", m.tennis.category_name)
            if klass:
                out[m.event_id] = klass
    return out


def replay(played: list[cc.Played], on: bool) -> list[Row]:
    cc.TENNIS_SAMPLE_SCOPE = True
    cc.TENNIS_ACES_OPPONENT = on
    ts = {m.event_id: m.timestamp for m in played}
    out: list[Row] = []
    for r in cc.iter_rows(played, cc.load_baselines()):
        if r.market in MARKETS:
            out.append(Row(r.event_id, ts[r.event_id], r.market, r.subject,
                           r.line, r.direction, r.p_central, r.won))
    return out


def key_of(r: Row, classes: dict[int, str]) -> str:
    klass = classes.get(r.event_id)
    return f"{klass + ':' if klass else ''}{r.market}|{r.direction}"


def fit_curves(rows: Iterable[Row], classes: dict[int, str]) -> dict[str, dict[int, float]]:
    counts: dict[str, dict[int, list[int]]] = collections.defaultdict(
        lambda: collections.defaultdict(lambda: [0, 0]))
    for r in rows:
        c = counts[key_of(r, classes)][bucket_of(r.p)]
        c[0] += int(r.won)
        c[1] += 1
    return {k: {b: kn[0] / kn[1] for b, kn in v.items() if kn[1] >= MIN_BUCKET}
            for k, v in counts.items()}


def calibrated(r: Row, curves: dict[str, dict[int, float]],
               classes: dict[int, str]) -> float:
    hit = curves.get(key_of(r, classes), {}).get(bucket_of(r.p))
    return r.p if hit is None else hit


def ll(p: float, won: bool) -> float:
    p = min(max(p, 1e-4), 1 - 1e-4)
    return -math.log(p if won else 1 - p)


def boot(diffs: dict[int, list[float]], b: int = 1000) -> tuple[float, float, float]:
    keys = list(diffs)
    tot = sum(sum(v) for v in diffs.values())
    n = sum(len(v) for v in diffs.values())
    rng = random.Random(7)
    stats = []
    for _ in range(b):
        s = n_ = 0.0
        for k in (rng.choice(keys) for _ in keys):
            s += sum(diffs[k])
            n_ += len(diffs[k])
        stats.append(s / n_)
    stats.sort()
    return tot / n, stats[int(0.025 * b)], stats[int(0.975 * b) - 1]


def middle_keys(rows: Sequence[Row]) -> set[tuple[int, str, str, float]]:
    """The market-like lines: the old arm's OVER p in [0.35, 0.65]."""
    return {(r.event_id, r.market, r.subject, r.line) for r in rows
            if r.direction == "OVER" and 0.35 <= r.p <= 0.65}


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--db-path", default=None)
    ap.add_argument("--cut", default="2026-01-01")
    ap.add_argument("--played-cache", default=None)
    ap.add_argument("--md-out", default=None)
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args(argv)
    db = Path(args.db_path or SofaConfig.from_env().db_path)
    cut = int(datetime.fromisoformat(args.cut).replace(tzinfo=UTC).timestamp())
    cc.TENNIS_ACES_TIERS = load_tier_baselines()
    played = load_played(db, Path(args.played_cache) if args.played_cache else None)
    print(f"tennis matches held: {len(played)}", file=sys.stderr)
    classes = tennis_classes(played)
    old = replay(played, on=False)
    new = replay(played, on=True)
    print(f"rows old {len(old)} new {len(new)}", file=sys.stderr)
    mid = middle_keys(old)
    report: dict[str, Any] = {"cut": args.cut, "markets": {}}
    lines = [f"# TENNIS_ACES_OPPONENT, cache replay, train < {args.cut}, test >= {args.cut}", "",
             "| market | test rows | matches | dLL all lines [95%] | mid rows | dLL mid lines [95%] | old >=0.70 mid: n / conf / real | new >=0.70 mid: n / conf / real |",
             "|---|---|---|---|---|---|---|---|"]
    for market in MARKETS:
        arms = {}
        for name, rows in (("old", old), ("new", new)):
            rs = [r for r in rows if r.market == market]
            curves = fit_curves((r for r in rs if r.ts < cut), classes)
            arms[name] = {(r.event_id, r.subject, r.line, r.direction):
                          (calibrated(r, curves, classes), r)
                          for r in rs if r.ts >= cut}
        common = arms["old"].keys() & arms["new"].keys()
        if not common:
            continue
        d_all: dict[int, list[float]] = collections.defaultdict(list)
        d_mid: dict[int, list[float]] = collections.defaultdict(list)
        top: dict[str, list[tuple[float, bool]]] = {"old": [], "new": []}
        for k in common:
            (po, ro), (pn, _) = arms["old"][k], arms["new"][k]
            diff = ll(pn, ro.won) - ll(po, ro.won)
            d_all[ro.event_id].append(diff)
            if (ro.event_id, market, ro.subject, ro.line) in mid:
                d_mid[ro.event_id].append(diff)
                for name, p in (("old", po), ("new", pn)):
                    if p >= FLOOR:
                        top[name].append((p, ro.won))
        a = boot(d_all)
        m = boot(d_mid) if d_mid else (float("nan"),) * 3

        def t(xs: list[tuple[float, bool]]) -> str:
            if not xs:
                return "0"
            return (f"{len(xs)} / {sum(p for p, _ in xs) / len(xs):.3f} / "
                    f"{sum(w for _, w in xs) / len(xs):.3f}")
        n_mid = sum(len(v) for v in d_mid.values())
        lines.append(
            f"| {market} | {len(common):,} | {len(d_all):,} | {a[0]:+.5f} [{a[1]:+.5f}, {a[2]:+.5f}] "
            f"| {n_mid:,} | {m[0]:+.5f} [{m[1]:+.5f}, {m[2]:+.5f}] | {t(top['old'])} | {t(top['new'])} |")
        report["markets"][market] = {
            "test_rows": len(common), "matches": len(d_all),
            "dll_all": a, "mid_rows": n_mid, "dll_mid": m,
            "old_top": t(top["old"]), "new_top": t(top["new"])}
    lines += ["", f"Buckets: {EDGES}; a bucket with < {MIN_BUCKET} train rows reads the raw p."]
    text = "\n".join(lines)
    print(text)
    if args.md_out:
        Path(args.md_out).write_text(text + "\n", encoding="utf-8")
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
