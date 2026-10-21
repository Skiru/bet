#!/usr/bin/env python3
"""LATE_RESOLVE: re-ask RESOLVE for the day's board entries the morning could
not bridge, and carry only the NEW fixtures through OFFER -> SAMPLES -> SHEET.

    PYTHONPATH=src:. .venv/bin/python scripts/sofa/run_late_resolve.py \\
        --date <d> [--dry-run]

Run by `rebuild_day.py` (bet.sofa.rebuild_plan, after ensure_bridge) while the
switch epochs.LATE_RESOLVE_FROM_UTC is on and the day holds an unbridged board
entry that has not started (or a fixture an earlier late pass left half-way).
By hand: ensure_bridge.py first.

1. candidates (bet.sofa.late_resolve.candidates): 01_board.json entries no
   fixture bridges whose board start is > 20 min ahead; a 00:00Z placeholder
   is skipped;
2. RESOLVE's own `_resolve_one` on them (scripts/sofa/run_resolve.py), with
   the listings read fresh (LATE_LISTING_TTL_MIN) - an unverified name's
   entity miss is still honoured and no miss is wiped; the breaker opening
   stops the pass;
3. a Sofascore event the day already holds is left alone (no old fixture
   changes); a new one is kept only when every clock is > 20 min ahead, and
   appended to 02_fixtures.json;
4. run_offer.py / run_samples.py / run_sheet.py --event-ids <the new ids>:
   each merges its new entries / rows into 04 / 03 / 05, every other
   fixture's kept as it was (late_resolve.merge_by_event). A step exiting 2
   stops the steps after it; the next pass carries the events on
   (late_resolve.json).

Exit: 0 OK (also: switch off, nothing to ask), 1 PARTIAL (gaps; a step
PARTIAL), 2 FAILED (breaker open, a step failed, unreadable inputs).
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parents[2]
for _p in (str(_REPO), str(_REPO / "src")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from bet.sofa import epochs  # noqa: E402
from bet.sofa import fixture_status as fs  # noqa: E402
from bet.sofa import late_resolve as lr  # noqa: E402
from bet.sofa.artifact_guard import incomplete_reason  # noqa: E402
from bet.sofa.atomic import write_atomic  # noqa: E402
from bet.sofa.config import SofaConfig  # noqa: E402
from bet.sofa.contracts import BoardFixture, Fixture  # noqa: E402
from bet.sofa.stage import set_stage  # noqa: E402
from bet.sofa.timeutil import frozen_clock_refusal, now  # noqa: E402

STAGE = "LATE_RESOLVE"
STEPS = (("OFFER", "scripts/sofa/run_offer.py"),
         ("SAMPLES", "scripts/sofa/run_samples.py"),
         ("SHEET", "scripts/sofa/run_sheet.py"))


def _z(at: Any) -> str:
    return str(at.isoformat()).replace("+00:00", "Z")


def emit(verdict: str, metrics: dict[str, Any], output_path: str | None) -> int:
    print("SOFA_SUMMARY: " + json.dumps({
        "stage": STAGE, "verdict": verdict, "metrics": metrics,
        "output_path": output_path}), flush=True)
    return {"OK": 0, "PARTIAL": 1}.get(verdict, 2)


def step_summary(lines: list[str]) -> dict[str, Any] | None:
    found: dict[str, Any] | None = None
    for line in lines:
        if line.startswith("SOFA_SUMMARY:"):
            try:
                doc = json.loads(line.split(":", 1)[1])
            except ValueError:
                continue
            if isinstance(doc, dict):
                found = doc
    return found


def run_step(script: str, date: str,
             ids: list[int]) -> tuple[int, dict[str, Any] | None]:
    """One stage as a subprocess (fresh code), its output passed through."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(_REPO / "src"), str(_REPO)]
        + ([env["PYTHONPATH"]] if env.get("PYTHONPATH") else []))
    argv = [sys.executable, script, "--date", date,
            "--event-ids", ",".join(str(i) for i in ids)]
    proc = subprocess.Popen(argv, cwd=_REPO, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True)
    assert proc.stdout is not None
    lines: list[str] = []
    for line in proc.stdout:
        # the stage's own summary would be read as this step's: indent it
        print(f"  | {line.rstrip()}", flush=True)
        lines.append(line.rstrip("\n"))
    return proc.wait(), step_summary(lines)


def samples_faulted(summary: dict[str, Any] | None) -> bool:
    """SAMPLES could not ask Sofascore for some fixture (breaker / provider
    fault): its entries are BLOCKED, so the events stay pending."""
    metrics = (summary or {}).get("metrics") or {}
    return bool(metrics.get("breaker_open")
                or metrics.get("provider_fault_fixtures"))


def main() -> int:
    set_stage(STAGE)
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--date", default=now().strftime("%Y-%m-%d"))
    ap.add_argument("--dry-run", action="store_true",
                    help="list what would be asked; no network, nothing written")
    args = ap.parse_args()

    config = SofaConfig.from_env()
    frozen = frozen_clock_refusal(config.runs_dir)
    if frozen:
        print(frozen, file=sys.stderr)
        return 2
    at = now()
    run = Path(config.runs_dir) / args.date
    fixtures_path = run / "02_fixtures.json"
    if not epochs.late_resolve(args.date, at):
        return emit("OK", {"switch": "off (epochs.LATE_RESOLVE_FROM_UTC)"}, None)
    board_path = run / "01_board.json"
    if not board_path.exists() or not fixtures_path.exists():
        print(f"{board_path} or {fixtures_path} missing", file=sys.stderr)
        return emit("FAILED", {"error": "board / fixtures missing"}, None)
    refusal = incomplete_reason(fixtures_path)
    if refusal:
        print(refusal, file=sys.stderr)
        return emit("FAILED", {"error": "02_fixtures.json incomplete"}, None)

    board = json.loads(board_path.read_text(encoding="utf-8"))
    fixtures = json.loads(fixtures_path.read_text(encoding="utf-8"))
    found = lr.candidates(board, fixtures, at)
    record = lr.load_record(run)
    samples_path = run / "03_samples.json"
    sampled = ({int(s["sofascore_event_id"])
                for s in json.loads(samples_path.read_text(encoding="utf-8"))}
               if samples_path.exists() else set())
    status = fs.load(run)
    pending = lr.pending_fixtures(fixtures, sampled, lr.unfinished(record),
                                  status, at)
    metrics: dict[str, Any] = {**found.summary(), "pending_from_earlier": len(pending)}
    for entry in found.entries:
        print(f"LATE_CANDIDATE {entry['sport']} {entry['kickoff_utc']} "
              f"{entry['match_name']} superbet={entry['superbet_event_id']}",
              flush=True)
    if not found.entries and not pending:
        return emit("OK", {**metrics, "new_fixtures": 0}, str(fixtures_path))
    if args.dry_run:
        return emit("OK", {**metrics, "dry_run": True}, None)

    new: dict[int, Fixture] = {}
    gaps: Counter[str] = Counter()
    breaker_open = False
    already_known = 0
    if found.entries:
        # the RESOLVE machinery itself; imported here so the dry run and the
        # switch-off path never open a client
        from bet.sofa.cache import SofaCache
        from bet.sofa.client import SofascoreClient
        from bet.sofa.resolve import SofaResolver
        from scripts.sofa.run_resolve import (
            learn_tournaments,
            merge_duplicate_listing,
            resolve_board_concurrently,
        )

        fresh_config = dataclasses.replace(
            config,
            events_ttl_min=min(config.events_ttl_min, lr.LATE_LISTING_TTL_MIN),
            listing_miss_ttl_min=min(config.listing_miss_ttl_min,
                                     lr.LATE_LISTING_TTL_MIN))
        client = SofascoreClient(fresh_config)
        cache = SofaCache(fresh_config)
        resolver = SofaResolver(fresh_config, client, cache)
        boards = [BoardFixture.model_validate_json(json.dumps(e))
                  for e in found.entries]
        known = {int(f["sofascore_event_id"]) for f in fixtures}
        tournaments: list[tuple[str, int | None, int, str | None, int]] = []
        for outcome in resolve_board_concurrently(boards, resolver, client, cache,
                                                  fresh_config):
            if outcome.circuit_open:
                breaker_open = True
                break
            if outcome.gap is not None:
                gaps[outcome.gap.value] += 1
                if outcome.error:
                    print(f"PROVIDER_ERROR {outcome.board.match_name}: "
                          f"{outcome.error}", file=sys.stderr)
                continue
            assert outcome.event_id is not None and outcome.fixture is not None
            eid = int(outcome.event_id)
            if eid in known:
                # an old fixture is never changed, not even by a second
                # Superbet id (its offer / samples / sheet stay as they are)
                already_known += 1
                continue
            if eid in new:
                merge_duplicate_listing(new[eid], outcome.board)
            else:
                new[eid] = outcome.fixture
                print(f"LATE_RESOLVED {outcome.fixture.sport} {eid} "
                      f"{outcome.fixture.home_name} - {outcome.fixture.away_name} "
                      f"({outcome.fixture.competition_name}) "
                      f"identity={outcome.fixture.identity}", flush=True)
            tournaments.append((str(outcome.fixture.sport), outcome.board.tournament_id,
                                int(outcome.fixture.competition_id),
                                outcome.fixture.competition_name, eid))
        if tournaments:
            learn_tournaments(config.db_path, tournaments)

    added = {eid: f for eid, f in new.items()
             if lr.fixture_open(f.model_dump(mode="json"), status, at)}
    metrics.update({
        "resolved_new": len(new), "already_known_event": already_known,
        "skipped_started_after_resolve": len(new) - len(added),
        "new_fixtures": len(added),
        "new_by_sport": dict(Counter(str(f.sport) for f in added.values())),
        "gaps": dict(gaps), "breaker_open": breaker_open,
    })
    if added:
        # re-read: the file as it stands now, only appended to
        current = json.loads(fixtures_path.read_text(encoding="utf-8"))
        held = {int(f["sofascore_event_id"]) for f in current}
        extra = [f.model_dump(mode="json") for eid, f in added.items()
                 if eid not in held]
        write_atomic(fixtures_path, json.dumps(current + extra, indent=2))
        for eid in added:
            record.setdefault("events", {})[str(eid)] = {
                "added_at_utc": _z(at), "sheet_at_utc": None}
    work = sorted(set(added) | set(pending))
    steps: dict[str, int] = {}
    ok = True
    for name, script in STEPS if work else ():
        code, summary = run_step(script, args.date, work)
        steps[name] = code
        print(f"LATE_STEP {name}: exit {code}", flush=True)
        if code >= 2 or (name == "SAMPLES" and samples_faulted(summary)):
            ok = False
        if code >= 2:
            break
    if work and ok:
        for eid in work:
            record.setdefault("events", {}).setdefault(
                str(eid), {"added_at_utc": None})["sheet_at_utc"] = _z(now())
    record.setdefault("passes", []).append({
        "at_utc": _z(at), "candidates": len(found.entries),
        "new_event_ids": sorted(added), "pending_event_ids": pending,
        "steps": steps, "gaps": dict(gaps), "breaker_open": breaker_open})
    write_atomic(run / lr.RECORD_FILE, json.dumps(record, indent=2))
    metrics["steps"] = steps
    if breaker_open or any(c >= 2 for c in steps.values()):
        verdict = "FAILED"
    elif gaps or any(c == 1 for c in steps.values()) or not ok:
        verdict = "PARTIAL"
    else:
        verdict = "OK"
    return emit(verdict, metrics, str(fixtures_path))


if __name__ == "__main__":
    sys.exit(main())
