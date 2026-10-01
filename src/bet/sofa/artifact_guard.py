"""A day artifact that a stage left half-written must not feed the next stage.

RESOLVE writes 02_fixtures.json in a `finally` (F15) so an exception does not
throw away the fixtures already resolved. That is right for RESOLVE and wrong
for everything that reads the file afterwards: on 2026-10-01 a
`sqlite3.OperationalError: database is locked` stopped RESOLVE after 15 of
461 board fixtures, the finally wrote those 15, and OFFER and SAMPLES then
priced and sampled the 15 and overwrote the day's 04_offer.json and
03_samples.json with them. Nothing said the slate was a stub.

So a stage that dies leaves a marker beside its artifact, and every stage that
builds the day's product refuses to read an artifact with a marker. A clean
re-run of the writing stage removes it. The marker is a file of its own rather
than a field inside the artifact because 02_fixtures.json is a bare list that
two dozen readers parse with a strict schema.
"""

from __future__ import annotations

import json
from pathlib import Path

from bet.sofa.atomic import write_atomic
from bet.sofa.timeutil import now

MARKER_SUFFIX = ".INCOMPLETE"


def marker_path(artifact: Path) -> Path:
    return artifact.with_name(artifact.name + MARKER_SUFFIX)


def mark_incomplete(artifact: Path, *, stage: str, reason: str) -> Path:
    """Record that `stage` wrote `artifact` without finishing."""
    path = marker_path(artifact)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(path, json.dumps(
            {
                "artifact": artifact.name,
                "stage": stage,
                "reason": reason,
                "marked_at_utc": now().isoformat(),
            },
            indent=2,
        ))
    return path


def clear_incomplete(artifact: Path) -> None:
    marker_path(artifact).unlink(missing_ok=True)


def incomplete_reason(artifact: Path) -> str | None:
    """The refusal line for a reader, or None when the artifact is whole."""
    path = marker_path(artifact)
    if not path.exists():
        return None
    try:
        info = json.loads(path.read_text(encoding="utf-8"))
        stage, reason = info.get("stage", "?"), info.get("reason", "?")
    except (OSError, ValueError):
        stage, reason = "?", "marker unreadable"
    return (
        f"UPSTREAM_INCOMPLETE {artifact.name}: {stage} did not finish ({reason}); "
        f"re-run {stage} before this stage - the artifact is a partial slate"
    )
