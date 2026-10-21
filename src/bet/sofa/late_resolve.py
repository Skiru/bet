"""The late RESOLVE pass: which board entries to re-ask, and the merges that
add the new fixtures' rows without touching the old ones.

RESOLVE runs once, in the morning. An ITF match Sofascore creates after that
run - or a football fixture it lists late - never reaches a fixture, so none
of its legs can print (measured 2026-10-21: 39 of 65 tennis entries lost
10-07..10-20 had a Sofascore id above every id their day's RESOLVE bridged).
`scripts/sofa/run_late_resolve.py` re-asks RESOLVE later in the day for the
board entries that have no fixture and have not started, and carries only
the NEW fixtures through OFFER -> SAMPLES -> SHEET (`--event-ids`), each
merged into its artifact by `merge_by_event`: a row of a fixture the morning
already held is kept as it was, byte for byte in its parsed form.

Offline: no network, no DB. Switch: epochs.LATE_RESOLVE_FROM_UTC.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from bet.sofa import fixture_status as fs
from bet.sofa.locked_print import starts_after

# An entry starting sooner is not re-asked: CONFIDENCE refuses a leg 15 min
# before its start, and OFFER's late refresh skips the same 20 min
# (rebuild_plan.OFFER_MIN_MINUTES_TO_KICKOFF; a test pins the two).
MIN_MINUTES_TO_KICKOFF = 20
# The late pass reads a listing (and a 404'd listing page) fresh when the
# cached copy is older than this. The morning's copy is what missed the
# match: RESOLVE's own TTLs (6 h listing, 12 h 404) would hand it back
# unchanged until the evening. An entity MISS keeps its own TTL (RESOLVE's
# semantics: a verified name ignores it, an unverified one honours it).
LATE_LISTING_TTL_MIN = 30
# runs/sofa/<d>/late_resolve.json: every pass (when, what it asked, what it
# added, each stage's exit) and every event it added with the time its SHEET
# ran - a pass that failed half-way is carried on by the next one.
RECORD_FILE = "late_resolve.json"


def _utc(raw: Any) -> datetime:
    return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).astimezone(UTC)


def _is_midnight(t: datetime) -> bool:
    # run_resolve.is_midnight_placeholder, without importing a script
    return (t.hour, t.minute, t.second) == (0, 0, 0)


@dataclass
class Candidates:
    """The board entries a late pass re-asks, and why the others are not."""

    entries: list[dict[str, Any]] = field(default_factory=list)
    bridged: int = 0
    started: int = 0
    midnight_placeholder: int = 0

    def summary(self) -> dict[str, int]:
        return {"candidates": len(self.entries), "already_bridged": self.bridged,
                "skipped_started": self.started,
                "skipped_midnight_placeholder": self.midnight_placeholder}


def candidates(board: Iterable[Mapping[str, Any]],
               fixtures: Iterable[Mapping[str, Any]],
               now: datetime) -> Candidates:
    """Board entries no fixture bridges (by Superbet id) whose start is more
    than MIN_MINUTES_TO_KICKOFF ahead. An unbridged entry has only the
    board's clock; a 00:00:00Z ITF placeholder (run_resolve.
    is_midnight_placeholder) is no clock - CONFIDENCE would read it as
    started - so it is skipped and counted."""
    bridged = {str(s) for f in fixtures for s in f.get("superbet_event_ids") or []}
    cutoff = now + timedelta(minutes=MIN_MINUTES_TO_KICKOFF)
    out = Candidates()
    for entry in board:
        if str(entry.get("superbet_event_id")) in bridged:
            out.bridged += 1
            continue
        kickoff = _utc(entry["kickoff_utc"])
        if _is_midnight(kickoff):
            out.midnight_placeholder += 1
            continue
        if kickoff <= cutoff:
            out.started += 1
            continue
        out.entries.append(dict(entry))
    return out


def fixture_open(fixture: Mapping[str, Any], status: Mapping[int, Mapping[str, Any]],
                 now: datetime) -> bool:
    """Every clock the pipeline holds for the fixture (locked_print.
    starts_after: Sofascore's, Superbet's, FIXTURE_CHECK's fresh start) is
    more than MIN_MINUTES_TO_KICKOFF ahead."""
    eid = fixture.get("sofascore_event_id")
    entry = status.get(int(eid)) if eid is not None else None
    return starts_after(fixture, None, entry,
                        now + timedelta(minutes=MIN_MINUTES_TO_KICKOFF))


def pending_fixtures(fixtures: Iterable[Mapping[str, Any]],
                     sampled_ids: set[int],
                     unfinished_ids: set[int],
                     status: Mapping[int, Mapping[str, Any]],
                     now: datetime) -> list[int]:
    """Open fixtures a previous late pass added and did not carry through
    SHEET (`unfinished_ids`, from RECORD_FILE), and open fixtures on
    02_fixtures.json with no 03_samples.json entry at all (the morning's
    SAMPLES writes one for every fixture). The next pass carries them on
    instead of leaving them without rows."""
    return [int(f["sofascore_event_id"]) for f in fixtures
            if (int(f["sofascore_event_id"]) not in sampled_ids
                or int(f["sofascore_event_id"]) in unfinished_ids)
            and fixture_open(f, status, now)]


def unfinished(record: Mapping[str, Any]) -> set[int]:
    """Events a late pass added whose SHEET has not run (RECORD_FILE)."""
    events = record.get("events") or {}
    return {int(k) for k, v in events.items() if not (v or {}).get("sheet_at_utc")}


def load_record(run: Path) -> dict[str, Any]:
    path = run / RECORD_FILE
    if not path.exists():
        return {"events": {}, "passes": []}
    try:
        doc = _load(path)
    except (OSError, ValueError):
        return {"events": {}, "passes": []}
    return doc if isinstance(doc, dict) else {"events": {}, "passes": []}


def merge_by_event(previous: list[dict[str, Any]], fresh: list[dict[str, Any]],
                   event_ids: set[int]) -> tuple[list[dict[str, Any]], int]:
    """`previous` with every row of `event_ids` replaced by `fresh`'s rows.

    The rows of every other fixture are kept as they were and in their
    order - the late pass may add a fixture's rows, never re-price the
    morning's. A fresh row of an event outside `event_ids` is a caller's
    defect and raises. Returns the merged list and how many previous rows
    were replaced (non-zero only when a pending fixture had partial rows)."""
    stray = {r.get("sofascore_event_id") for r in fresh} - set(event_ids)
    if stray:
        shown = sorted(map(str, stray))
        raise ValueError(f"fresh rows outside the late pass's events: {shown}")
    kept = [r for r in previous if r.get("sofascore_event_id") not in event_ids]
    return kept + fresh, len(previous) - len(kept)


def parse_event_ids(raw: str | None) -> set[int] | None:
    """`--event-ids 1,2,3` -> {1, 2, 3}; None when the option is absent. An
    empty value is an empty set (the stage then touches nothing)."""
    if raw is None:
        return None
    return {int(x) for x in raw.split(",") if x.strip()}


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def observe_work(runs_dir: str | Path, date: str, now: datetime) -> tuple[int, int]:
    """(board entries to re-ask, pending fixtures) for the rebuild plan.
    Read-only; (0, 0) without a board or a fixtures file."""
    run = Path(runs_dir) / date
    board_path, fixtures_path = run / "01_board.json", run / "02_fixtures.json"
    if not board_path.exists() or not fixtures_path.exists():
        return 0, 0
    fixtures = _load(fixtures_path) or []
    found = candidates(_load(board_path) or [], fixtures, now)
    samples_path = run / "03_samples.json"
    pending: list[int] = []
    if samples_path.exists():
        sampled = {int(s["sofascore_event_id"]) for s in _load(samples_path) or []}
        pending = pending_fixtures(fixtures, sampled, unfinished(load_record(run)),
                                   fs.load(run), now)
    return len(found.entries), len(pending)
