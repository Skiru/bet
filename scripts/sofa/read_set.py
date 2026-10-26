#!/usr/bin/env python3
"""The legs the analysts read, one file per sport - the C3 read set
(`confidence.legs_requiring_read`: the 20 best-value matches' unlocked
legs - 30 on an artifact built before 2026-10-27 -,
every printed builder leg, `read_requests.json`), optionally widened by a
buffer of the next matches in the same order and narrowed to the legs no
analyst has read yet.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/read_set.py --date <d> \\
        [--buffer N] [--unread] [--split K] [--out-dir <dir>]

--buffer N   also the next N matches after the required matches, in the order
             legs_requiring_read ranks them (a provisional build reshuffles
             the required ones; a buffer read now saves a C3 round later).
--unread     only legs no analyst read covers (C3's own rule,
             `veto.matching_reads`); a re-read pass after a rebuild gives the
             analysts the new legs only.
--split K    a sport with more than K matches is written in parts of at most
             K whole matches (read_set_<sport>_<i>.json), one analyst each.

The operator's requests are read from runs/sofa/<d>/read_requests.json (the
file the next rebuild applies); audit C3 reads the copy 11_coupon.json
carries - they differ only between an edit of the file and that rebuild.

A leg whose match already has an analyst's section today (analyses.json,
`bet.sofa.analyses`, recorded by merge_reads.py) carries `prior_analysis`
(report, recorded_at_utc, web_tags, context_pass; full_pass_report /
full_pass_at_utc - the newest full context pass, which a delta section never
replaces): the analyst of a re-read
round reads that section and checks only what changed since, instead of
redoing the match's dossier read and web pass (10-13..10-25: 11% of match
readings were a match already read that day).

Each match also gets its dossier (`bet.sofa.dossier`, offline: form, rest,
table, head-to-head, venue and its local hour, referee / ranking / roster,
Superbet line moves, the web checklist) in runs/sofa/<d>/dossier/, and each
leg its path in `dossier` (--no-dossier skips it; --db-path, default
$SOFA_DB_PATH or data/sofa.db). Before the dossiers, every match's
head-to-head is asked of Sofascore through the bridge (`bet.sofa.h2h` ->
runs/sofa/<d>/h2h.json; --no-h2h skips it, a failure is printed and the
dossier says h2h was not answered), and every football / hockey / basketball
match not yet started gets Sofascore's pre-match line-up
(`bet.sofa.prematch_lineups` -> runs/sofa/<d>/lineups_prematch.json, never the
cache; --no-lineups skips it). These two are the only requests it makes.

Writes <out-dir>/read_set_<sport>[_<i>].json (default runs/sofa/<d>/read_set/;
stale sport files of an earlier call are removed) and prints one line per
sport: legs, matches, file. Read-only on the day's artifacts but h2h.json
and lineups_prematch.json.
Exit 0 (an empty set too), 2 when 11_coupon.json is missing or unreadable.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_ROOT / "src"), str(_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import (  # noqa: E402
    analyses,
    dossier,
    h2h,
    prematch_lineups,
    timeutil,  # noqa: E402
)
from bet.sofa.atomic import write_atomic  # noqa: E402
from bet.sofa.confidence import (  # noqa: E402
    group_key,
    legs_requiring_read,
    load_read_requests,
    printed_singles,
    read_required_events,
    read_value,
)
from bet.sofa.veto import load_reads, matching_reads  # noqa: E402

# What an analyst needs to find the leg in the artifacts and on the screen.
FIELDS = (
    "position", "group_key", "sport", "match", "competition", "kickoff_utc",
    "sofascore_event_id", "market", "subject", "line", "direction", "period",
    "superbet_market", "superbet_selection", "confidence", "offered_odds",
    "locked", "price_gap", "superbet_event_id", "source_date", "model_p",
    "forecast_p", "calibrated_on", "sample_size", "sample_hit_rate",
    "sample_oldest_days", "sample_newest_days", "context_flags",
    # a builder leg carries `odds`; a measured-sport leg `family` / `side` /
    # `map_nr` beside its market / direction
    "odds", "family", "side", "map_nr",
)


# What a re-read needs to find the earlier section (`jq` on analyses.json).
PRIOR_FIELDS = ("report", "recorded_at_utc", "web_tags", "context_pass")


def buffer_legs(doc: dict[str, Any], n: int) -> list[dict[str, Any]]:
    """The unlocked legs of the next `n` matches after the required ones, in
    legs_requiring_read's order (coupon position, re-ranked by read_value
    when the artifact reads by value). Empty on an artifact that reads by
    position rather than by match."""
    if n <= 0 or doc.get("read_unit") != "event":
        return []
    fresh = [s for s in printed_singles(doc) if not s.get("locked")]
    ordered = sorted(fresh, key=lambda s: int(s.get("position") or 0))
    if doc.get("read_order") == "value":
        ordered.sort(key=lambda s: -read_value(s))
    events: list[str] = []
    for s in ordered:
        g = group_key(s)
        if g not in events:
            events.append(g)
    first = read_required_events(doc)
    extra = set(events[first:first + n])
    return [s for s in fresh if group_key(s) in extra]


def leg_key(leg: dict[str, Any]) -> tuple[Any, ...]:
    line = leg.get("line")
    return (int(leg["sofascore_event_id"]), str(leg["market"]),
            str(leg.get("subject") or ""),
            None if line is None else float(line), str(leg["direction"]),
            leg.get("period"))


def analyst_read(leg: dict[str, Any], reads: list[Any]) -> bool:
    """C3's rule: an analyst's read covers the leg (or it carries one)."""
    line = leg.get("line")
    covering = matching_reads(
        reads,
        sofascore_event_id=int(leg["sofascore_event_id"]),
        market=str(leg["market"]),
        subject=str(leg.get("subject") or ""),
        line=None if line is None else float(line),
        direction=str(leg["direction"]),
        period=None if leg.get("period") is None else int(leg["period"]),
    )
    carried = [r for r in leg.get("reads") or [] if isinstance(r, dict)]
    return any(r.author == "analyst" for r in covering) or any(
        r.get("author") == "analyst" for r in carried)


def read_set(run: Path, buffer: int = 0, unread: bool = False
             ) -> dict[str, list[dict[str, Any]]]:
    """{sport: [compact leg, ...]} - required legs first, then the buffer."""
    doc = json.loads((run / "11_coupon.json").read_text(encoding="utf-8"))
    requests = load_read_requests(run / "read_requests.json")
    fixtures_path = run / "02_fixtures.json"
    sport_of: dict[int, str] = {}
    if fixtures_path.exists():
        sport_of = {int(f["sofascore_event_id"]): str(f.get("sport") or "")
                    for f in json.loads(fixtures_path.read_text(encoding="utf-8"))}
    builder_of = {int(b["sofascore_event_id"]): b for b in doc.get("builders") or []
                  if b.get("sofascore_event_id") is not None}
    legs = [(x, "required") for x in legs_requiring_read(doc, requests)]
    legs += [(x, "buffer") for x in buffer_legs(doc, buffer)]
    reads = load_reads(run / "reads.json") if unread else []
    store = analyses.load(run)
    out: dict[str, list[dict[str, Any]]] = {}
    seen: set[tuple[Any, ...]] = set()
    for leg, why in legs:
        key = leg_key(leg)
        if key in seen or (unread and analyst_read(leg, reads)):
            continue
        seen.add(key)
        # a builder leg carries no `sport`: take it from its fixture
        sport = str(leg.get("sport") or sport_of.get(
            int(leg["sofascore_event_id"])) or "football")
        compact = {k: leg[k] for k in FIELDS if leg.get(k) is not None}
        # a builder leg carries neither its match's clock nor `offered_odds`:
        # one shape for every leg (the analyst's inventory reads both)
        eid = int(leg["sofascore_event_id"])
        for k in ("kickoff_utc", "competition", "match"):
            if k not in compact and builder_of.get(eid, {}).get(k) is not None:
                compact[k] = builder_of[eid][k]
        if "offered_odds" not in compact and compact.get("odds") is not None:
            compact["offered_odds"] = compact["odds"]
        compact.update(sport=sport, group_key=group_key(leg), in_set=why)
        prior = analyses.latest(store, leg["sofascore_event_id"], "analyst")
        if prior is not None:
            full = analyses.full_pass(store, leg["sofascore_event_id"]) or {}
            compact["prior_analysis"] = {
                **{k: prior.get(k) for k in PRIOR_FIELDS},
                "full_pass_report": full.get("report"),
                "full_pass_at_utc": full.get("recorded_at_utc")}
        out.setdefault(sport, []).append(compact)
    return out


def parts(legs: list[dict[str, Any]], k: int) -> list[list[dict[str, Any]]]:
    """Whole matches in their read order, at most `k` per part."""
    order: list[str] = []
    for x in legs:
        if x["group_key"] not in order:
            order.append(x["group_key"])
    if k <= 0 or len(order) <= k:
        return [legs]
    chunks = [set(order[i:i + k]) for i in range(0, len(order), k)]
    return [[x for x in legs if x["group_key"] in c] for c in chunks]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--date", required=True)
    ap.add_argument("--buffer", type=int, default=0)
    ap.add_argument("--unread", action="store_true")
    ap.add_argument("--split", type=int, default=0)
    ap.add_argument("--runs-dir", default=os.environ.get("SOFA_RUNS_DIR", "runs/sofa"))
    ap.add_argument("--out-dir")
    ap.add_argument("--db-path", default=None)
    ap.add_argument("--no-dossier", action="store_true")
    ap.add_argument("--no-h2h", action="store_true",
                    help="dossiers from the cache only, no Sofascore h2h request")
    ap.add_argument("--no-lineups", action="store_true",
                    help="no Sofascore pre-match line-up request")
    args = ap.parse_args(argv)
    frozen = timeutil.frozen_clock_refusal(args.runs_dir)
    if frozen:
        print(frozen, file=sys.stderr)
        return 2
    run = Path(args.runs_dir) / args.date
    try:
        sets = read_set(run, args.buffer, args.unread)
    except (OSError, ValueError, KeyError) as exc:
        print(f"read_set: {run}: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    out_dir = Path(args.out_dir) if args.out_dir else run / "read_set"
    out_dir.mkdir(parents=True, exist_ok=True)
    for stale in out_dir.glob("read_set_*.json"):
        stale.unlink()
    if not sets:
        print("read set: empty")
    elif not args.no_dossier:
        every = [x for legs in sets.values() for x in legs]
        if not args.no_h2h:
            print(h2h.fetch_for_legs(run, every))
        if not args.no_lineups:
            print(prematch_lineups.fetch_for_legs(run, every))
        print(dossier.attach(run, every, args.db_path))
    for sport, all_legs in sorted(sets.items()):
        chunks = parts(all_legs, args.split)
        for i, legs in enumerate(chunks, 1):
            name = f"read_set_{sport}.json" if len(chunks) == 1 else (
                f"read_set_{sport}_{i}.json")
            path = out_dir / name
            write_atomic(path, json.dumps(legs, indent=1, ensure_ascii=False) + "\n")
            why = Counter(x["in_set"] for x in legs)
            matches = len({x["group_key"] for x in legs})
            print(f"{sport}: {len(legs)} legs, {matches} matches "
                  f"({why['required']} required, {why['buffer']} buffer) -> {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
