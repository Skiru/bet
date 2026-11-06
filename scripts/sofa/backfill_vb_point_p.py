"""The rally-point model's p of every settled Superbet volleyball line of
epochs.VB_POINT_MODEL_MARKETS (bet.sofa.vb_point_pricer.BACKFILL), so
fit_line_evidence.py reads these keys' line evidence at the model's own p.

Each line's event is forecast as of its Sofascore start from the cached
history (read-only; score_model.load_events -> sport_confidence.parse_history
with the golden-set rule, the matches before the start teaching) and
simulated as SPORT_CONFIDENCE simulates it (vb_point_pricer.VbPricer: 4,000
matches, seed = Sofascore event id, Superbet's team1 orientation). Only lines
the table does not hold yet are priced (a day once priced stays as priced);
`--seed-jsonl` adds the measurement's own p (measure_volleyball_point_model.py
--stage superbet: volleyball_sb_dev.jsonl / volleyball_sb_holdout.jsonl) for
the keys it has.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/backfill_vb_point_p.py \\
        --before <D> [--seed-jsonl <f> ...] [--dry-run]

Run by refresh_line_evidence.py (step 1b) while epochs.VB_POINT_MODEL is on
for <D>. Exit 0 OK, 2 FAILED.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from collections.abc import Iterator, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import epochs  # noqa: E402
from bet.sofa import vb_point_pricer as vpp  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402

# The first day with settled Superbet volleyball lines (SHADOW's measurement).
FIRST_DAY = "2026-09-29"


def _utc(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


def settled_lines(runs_dir: Path, before: str
                  ) -> Iterator[tuple[str, Mapping[str, Any], Mapping[str, Any]]]:
    """(day, event, graded line) of every WIN / LOSS in-scope line of a
    pinned, oriented event, days FIRST_DAY .. before (exclusive)."""
    root = runs_dir / "shadow" / "volleyball"
    if not root.exists():
        return
    for day_dir in sorted(root.iterdir()):
        d = day_dir.name
        if not (len(d) == 10 and FIRST_DAY <= d < before):
            continue
        path = day_dir / "settled.json"
        if not path.exists():
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        for ev in (doc.get("events") or {}).values():
            if not ev.get("pinned_id") or ev.get("orientation_unclear"):
                continue
            for g in ev.get("graded") or []:
                if g.get("outcome") not in ("WIN", "LOSS"):
                    continue
                if not vpp.in_scope("volleyball", int(g.get("market_id") or 0)):
                    continue
                yield d, ev, g


def key_of(day: str, g: Mapping[str, Any]) -> str:
    return vpp.backfill_key(day, g["superbet_event_id"], g["market_id"],
                            g.get("period"), g.get("subject"), g.get("line"),
                            g["side"])


def seed(table: dict[str, float], paths: list[str]) -> int:
    added = 0
    for raw_path in paths:
        with open(raw_path, encoding="utf-8") as fh:
            for raw in fh:
                r = json.loads(raw)
                if not vpp.in_scope("volleyball", int(r["market_id"])):
                    continue
                sb = str(r["game"]).split(":")[2]
                k = vpp.backfill_key(r["day"], sb, r["market_id"], r["period"],
                                     r["subject"], r["line"], r["side"])
                if k not in table and r.get("p_new") is not None:
                    table[k] = round(float(r["p_new"]), 6)
                    added += 1
    return added


def price_missing(table: dict[str, float], runs_dir: Path, before: str,
                  db_path: str) -> dict[str, int]:
    from bet.sofa import shadow
    from bet.sofa import sport_confidence as scf
    from bet.sofa.comparability import competition_id
    from bet.sofa.score_model import load_events

    todo: dict[int, list[tuple[str, Mapping[str, Any], Mapping[str, Any]]]] = (
        defaultdict(list))
    counts = {"lines": 0, "had": 0, "priced": 0, "no_forecast": 0, "no_p": 0}
    for d, ev, g in settled_lines(runs_dir, before):
        counts["lines"] += 1
        if key_of(d, g) in table:
            counts["had"] += 1
            continue
        todo[int(ev["sofascore_event_id"])].append((d, ev, g))
    if not todo:
        return counts
    sp = shadow.SPORTS["volleyball"]
    events = load_events(db_path, sp)
    history = vpp.history_matches(scf.parse_history(events, sp, golden_set=True))
    women = vpp.women_by_team(history)
    by_id = {m.event_id: m for m in history}
    fixtures = []
    for sid, group in todo.items():
        ev = group[0][1]
        start = ev.get("sofascore_start_utc") or ev.get("kickoff_utc")
        cached = events.get(sid)
        comp = (by_id[sid].competition if sid in by_id
                else competition_id(cached) if cached is not None else None)
        m = (vpp.fixture_match(sid, _utc(str(start)), ev.get("sofascore_home_id"),
                               ev.get("sofascore_away_id"), comp, women)
             if start else None)
        if m is None:
            counts["no_forecast"] += len(group)
            continue
        fixtures.append(m)
    pricer = vpp.VbPricer(vpp.forecast_fixtures(history, fixtures))
    for sid, group in todo.items():
        for d, ev, g in group:
            if sid not in pricer.forecasts:
                continue
            p = pricer.p(sid, bool(ev.get("home_is_team1", True)),
                         int(g["market_id"]), int(g.get("period") or 0),
                         str(g.get("subject") or ""), g.get("line"), str(g["side"]))
            if p is None:
                counts["no_p"] += 1
                continue
            table[key_of(d, g)] = round(p, 6)
            counts["priced"] += 1
    return counts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--before", required=True)
    ap.add_argument("--seed-jsonl", action="append", default=[])
    ap.add_argument("--out", default=None, help="default vb_point_pricer.BACKFILL")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    config = SofaConfig.from_env()
    out = Path(args.out) if args.out else vpp.BACKFILL
    try:
        table = vpp.load_backfill(out)
        seeded = seed(table, args.seed_jsonl)
        counts = price_missing(table, Path(config.runs_dir), args.before,
                               config.db_path)
        if not args.dry_run:
            vpp.write_backfill(table, out)
    except Exception as exc:  # noqa: BLE001 - one verdict line, then exit 2
        print(json.dumps({"stage": "VB_POINT_BACKFILL", "verdict": "FAILED",
                          "error": repr(exc)}))
        return 2
    print(json.dumps({"stage": "VB_POINT_BACKFILL", "verdict": "OK",
                      "switch_on": epochs.vb_point_model(args.before),
                      "seeded": seeded, "metrics": counts, "keys": len(table),
                      "output_path": None if args.dry_run else str(out)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
