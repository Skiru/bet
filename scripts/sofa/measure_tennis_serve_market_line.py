#!/usr/bin/env python3
# ruff: noqa: E501  - report lines are tables.
"""The tennis serve curves at Superbet's own lines - the check
`T-TENNIS-SERVE-MARKET-LINE` (config/sofa_test_registry.json) and the
measurement behind docs/sofa/evidence/tennis_aces_opponent_2026-10-17.md.

For every settled tennis line of the serve markets (sofa_settled_row, run_date
in [--from, --to], WIN / LOSS, a price) the confidence CONFIDENCE would print -
Calibration.realised then LineEvidence.read (v2, the bucket design effect),
the leg's class from the day's 02_fixtures.json - is computed twice: with the
installed curves and with the staged ones (`--staged`, a directory holding
tennis_serve/curves.json; merged into a temporary copy of config/ by
install_new_market_curves.py, never into config/). Legs kept where the
confidence is >= 0.70 and confidence x odds >= 0.90; reported: n, matches,
confidence, realised, realised minus confidence [95% over matches], 1/odds,
ROI.

The aces markets are re-priced by SHEET itself (run_sheet.process_fixture on
the day's 02 / 03 / 04 artifacts, stats-only) with and without
epochs.TENNIS_ACES_OPPONENT: a sample written before 2026-10-13 has no
`against`, so it is filled from the cache (the opponent's aces in that match,
what SAMPLES writes since) - `--no-fill-against` leaves such samples raw.

Read-only: the DB is opened read-only; config/ is never written.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/measure_tennis_serve_market_line.py \\
        --from 2026-10-06 --to 2026-10-16 \\
        --staged data/refit_tennis_serve_2026-10-17 [--md-out f]
"""

from __future__ import annotations

import argparse
import json
import math
import random
import shutil
import sqlite3
import sys
import tempfile
from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from pydantic import RootModel

from bet.sofa.confidence import Calibration, direction_key, match_class
from bet.sofa.config import SofaConfig, config_path
from bet.sofa.contracts import Fixture, FixtureOffer, FixtureSamples
from bet.sofa.line_evidence import LineEvidence, evidence_key
from bet.sofa.tennis_aces_opponent import ACES_MARKETS
from scripts.sofa import install_new_market_curves as inst
from scripts.sofa import run_sheet as rs
from scripts.sofa.fit_tennis_serve_curves import SERVE_MARKETS

FLOOR = 0.70
MIN_X = 0.90
CAL_FILE = "sofa_confidence_calibration.json"


@dataclass(frozen=True)
class Line:
    event_id: int
    market: str
    direction: str
    klass: str | None
    p: float
    odds: float
    won: bool


def days(start: str, end: str) -> list[str]:
    d0, d1 = date.fromisoformat(start), date.fromisoformat(end)
    return [(d0 + timedelta(n)).isoformat() for n in range((d1 - d0).days + 1)]


def staged_calibration(staged: Path) -> Calibration:
    """The installed calibration with the staged tennis_serve group merged,
    in a temporary directory (the installer's own merge, its tests skipped)."""
    with tempfile.TemporaryDirectory() as tmp:
        cfg = Path(tmp) / "config"
        cfg.mkdir()
        shutil.copy2(config_path(CAL_FILE), cfg / CAL_FILE)
        rc = inst.main(["--dir", str(staged), "--config-dir", str(cfg),
                        "--backup-dir", str(Path(tmp) / "backup"), "--confirm",
                        "--test-cmd", f"{sys.executable} -c pass"])
        if rc != 0:
            raise SystemExit(f"staged curves did not merge (exit {rc})")
        return Calibration.load(cfg / CAL_FILE)


def classes(runs: Path, ds: Sequence[str]) -> dict[int, str | None]:
    out: dict[int, str | None] = {}
    for d in ds:
        path = runs / d / "02_fixtures.json"
        if not path.exists():
            continue
        for fx in json.loads(path.read_text(encoding="utf-8")):
            out[int(fx["sofascore_event_id"])] = match_class(
                "tennis", fx.get("category_name") or "") or None
    return out


def settled(db: sqlite3.Connection, ds: Sequence[str], markets: frozenset[str],
            klass: dict[int, str | None]) -> list[Line]:
    marks = ",".join("?" * len(markets))
    rows = db.execute(
        "SELECT sofascore_event_id, market, direction, p_central, offered_odds,"
        " outcome FROM sofa_settled_row WHERE sport = 'tennis' AND run_date "
        f"BETWEEN ? AND ? AND outcome IN ('WIN','LOSS') AND offered_odds IS NOT "
        f"NULL AND market IN ({marks})", (ds[0], ds[-1], *sorted(markets)))
    return [Line(e, m, d, klass.get(e), float(p), float(o), out == "WIN")
            for e, m, d, p, o, out in rows]


class AcesRepricer:
    """SHEET's aces rows of the days with / without the returner factor."""

    def __init__(self, db: sqlite3.Connection, fill_against: bool) -> None:
        self.db = db
        self.fill = fill_against
        cfg = SofaConfig.from_env()
        self.cfg = cfg
        self.kw: dict[str, Any] = dict(
            baselines=rs.load_baselines(cfg), reliability=rs.load_reliability(cfg),
            engine_constants=rs.load_engine_constants(cfg), vetoes=[], config=cfg,
            tennis_tiers=rs.load_tennis_tier_baselines(cfg), stats_only=True)
        self._pairs: dict[int, tuple[float, float] | None] = {}

    def _aces(self, event_id: int) -> tuple[float, float] | None:
        if event_id not in self._pairs:
            row = self.db.execute(
                "SELECT statistics_json FROM sofa_event_stats WHERE "
                "sofascore_event_id = ?", (event_id,)).fetchone()
            pair = None
            if row and row[0]:
                for period in json.loads(row[0]).get("statistics", []):
                    if period.get("period") != "ALL":
                        continue
                    for group in period.get("groups", []):
                        for item in group.get("statisticsItems", []):
                            if item.get("key") == "aces":
                                pair = (float(item["homeValue"]),
                                        float(item["awayValue"]))
            self._pairs[event_id] = pair
        return self._pairs[event_id]

    def _filled(self, samples: FixtureSamples) -> FixtureSamples:
        ms = samples.metrics.get("aces_for")
        if not self.fill or ms is None:
            return samples

        def fix(obs: list[Any]) -> list[Any]:
            out = []
            for o in obs:
                pair = self._aces(o.sofascore_event_id) if o.against is None else None
                if pair is not None and o.value in pair:
                    o = o.model_copy(update={
                        "against": pair[1] if o.value == pair[0] else pair[0]})
                out.append(o)
            return out
        return samples.model_copy(update={"metrics": {
            **samples.metrics,
            "aces_for": ms.model_copy(update={"side_a": fix(ms.side_a),
                                              "side_b": fix(ms.side_b)})}})

    def lines(self, runs: Path, ds: Sequence[str]) -> list[tuple[Line, float]]:
        """(the line with the old p, the corrected p) per settled aces line."""
        out: list[tuple[Line, float]] = []
        for d in ds:
            base = runs / d
            if not (base / "03_samples.json").exists():
                continue
            fixtures = RootModel[list[Fixture]].model_validate_json(
                (base / "02_fixtures.json").read_text(encoding="utf-8")).root
            samples = {s.sofascore_event_id: s for s in RootModel[list[FixtureSamples]]
                       .model_validate_json((base / "03_samples.json")
                                            .read_text(encoding="utf-8")).root}
            offers = {o.sofascore_event_id: o for o in RootModel[list[FixtureOffer]]
                      .model_validate_json((base / "04_offer.json")
                                           .read_text(encoding="utf-8")).root}
            for fx in fixtures:
                eid = fx.sofascore_event_id
                if (fx.sport != "tennis" or eid not in samples or eid not in offers
                        or not any(r.market in ACES_MARKETS for r in offers[eid].rungs)):
                    continue
                s = self._filled(samples[eid])
                priced: dict[tuple[str, str, float, str], dict[bool, Any]] = defaultdict(dict)
                for on in (False, True):
                    rows, _ = rs.process_fixture(fx, s, offers[eid],
                                                 aces_opponent_on=on, **self.kw)
                    for r in rows:
                        if r.market in ACES_MARKETS and r.offered_odds:
                            priced[(r.market, r.subject, r.line, r.direction)][on] = r
                klass = match_class("tennis", fx.category_name or "") or None
                for (m, subj, line, dr), arms in priced.items():
                    if False not in arms or True not in arms:
                        continue
                    res = self.db.execute(
                        "SELECT outcome FROM sofa_settled_row WHERE "
                        "sofascore_event_id = ? AND market = ? AND subject = ? AND "
                        "line = ? AND direction = ? AND outcome IN ('WIN','LOSS')",
                        (eid, m, subj, line, dr)).fetchone()
                    if res is None:
                        continue
                    old = arms[False]
                    out.append((Line(eid, m, dr, klass, old.p_central,
                                     float(old.offered_odds), res[0] == "WIN"),
                                arms[True].p_central))
        return out


def confidence(cal: Calibration, ev: LineEvidence, ln: Line, p: float) -> float | None:
    hit = cal.realised(ln.market, p, "tennis", ln.direction, ln.klass)
    read = ev.read("tennis", evidence_key(direction_key(ln.market, ln.direction),
                                          ln.klass), p, hit, ln.odds)
    return None if read is None else read.value


def summary(picked: list[tuple[Line, float]]) -> str:
    if not picked:
        return "| 0 | - | - | - | - | - | - |"
    by: dict[int, list[float]] = defaultdict(list)
    for ln, c in picked:
        by[ln.event_id].append(ln.won - c)
    keys = list(by)
    rng = random.Random(1)
    draws = []
    for _ in range(1000):
        s = [x for k in (rng.choice(keys) for _ in keys) for x in by[k]]
        draws.append(sum(s) / len(s))
    draws.sort()
    n = len(picked)
    conf = sum(c for _, c in picked) / n
    hit = sum(ln.won for ln, _ in picked) / n
    roi = sum((ln.odds - 1) if ln.won else -1 for ln, _ in picked) / n
    inv = sum(1 / ln.odds for ln, _ in picked) / n
    return (f"| {n} | {len(keys)} | {conf:.3f} | {hit:.3f} | {hit - conf:+.3f} "
            f"[{draws[25]:+.3f}, {draws[974]:+.3f}] | {inv:.3f} | {roi:+.3f} |")


def printing(cal: Calibration, ev: LineEvidence,
             items: Sequence[tuple[Line, float]]) -> list[tuple[Line, float]]:
    out = []
    for ln, p in items:
        c = confidence(cal, ev, ln, p)
        if c is not None and c >= FLOOR and c * ln.odds >= MIN_X:
            out.append((ln, c))
    return out


def log_loss(p: float, won: bool) -> float:
    q = min(max(p if won else 1 - p, 1e-4), 1.0)
    return -math.log(q)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--from", dest="start", required=True)
    ap.add_argument("--to", dest="end", required=True)
    ap.add_argument("--staged", required=True)
    ap.add_argument("--runs-dir", default=None)
    ap.add_argument("--db-path", default=None)
    ap.add_argument("--no-fill-against", action="store_true")
    ap.add_argument("--md-out", default=None)
    args = ap.parse_args(argv)
    cfg = SofaConfig.from_env()
    runs = Path(args.runs_dir or cfg.runs_dir)
    db = sqlite3.connect(f"file:{args.db_path or cfg.db_path}?mode=ro", uri=True)
    ds = days(args.start, args.end)
    installed = Calibration.load(config_path(CAL_FILE))
    staged = staged_calibration(Path(args.staged))
    ev = LineEvidence.load(v2=True, bucket_deff=True)
    klass = classes(runs, ds)
    head = ("| arm | legs | matches | confidence | realised | gap [95%] | "
            "1/odds | ROI |\n|---|---|---|---|---|---|---|---|")
    out = [f"# Tennis serve curves at Superbet's lines, {args.start}..{args.end}", "",
           "## Per-set aces / double faults and serve points (p unchanged)", "",
           head]
    serve = [(ln, ln.p) for ln in settled(db, ds, SERVE_MARKETS - ACES_MARKETS, klass)]
    out.append("| installed curves " + summary(printing(installed, ev, serve)))
    out.append("| staged curves " + summary(printing(staged, ev, serve)))
    aces = AcesRepricer(db, not args.no_fill_against).lines(runs, ds)
    ll = [log_loss(p1, ln.won) - log_loss(ln.p, ln.won) for ln, p1 in aces]
    out += ["", f"## Aces, SHEET re-priced ({len(aces)} lines, "
            f"{len({ln.event_id for ln, _ in aces})} matches; log-loss corrected - "
            f"raw {sum(ll) / max(len(ll), 1):+.4f})", "", head]
    out.append("| installed curves, raw p " + summary(
        printing(installed, ev, [(ln, ln.p) for ln, _ in aces])))
    out.append("| installed curves, corrected p " + summary(
        printing(installed, ev, aces)))
    out.append("| staged curves, corrected p " + summary(printing(staged, ev, aces)))
    text = "\n".join(out)
    print(text)
    if args.md_out:
        Path(args.md_out).write_text(text + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
