"""Superbet's prices on the markets OFFER does not read - recorded, never used.

OFFER keeps only the NAME of a market it cannot classify (`unmapped_markets`
in 04_offer.json). A market we later learn to model then has no price history
at all, so its line evidence (bet.sofa.line_evidence: offsets, price bands)
starts from zero on the day it is switched on - 2026-10-14: the outside-box
shot markets had a working model and not one settled Superbet line to judge
it against.

Every OFFER run therefore appends the unmapped odds it saw to
`runs/sofa/<d>/unmapped_prices/<ts>.jsonl.gz`: one file per run, one line
per odd, append-only (a rebuild's refresh adds a file, nothing is rewritten).
Pre-match only - `superbet.odds_items` has already dropped in-play odds.
Nothing in the pipeline reads these files to price or print anything; they
are the raw material of a future measurement.

The measured sports record theirs too (pokrycie_sportow_2026-11-05, gap 5):
SHADOW (hockey / basketball / volleyball) and the CS2 snapshot write every
odd of a market they do not read, from the payload already fetched (no extra
request), one file per snapshot and sport under the event's day,
`<sport>_<ts>.jsonl.gz`. Their records carry `sport` and Superbet's
`marketId`; `sofascore_event_id` is null (the id is pinned later by
SPORT_IDENTITY - join on `superbet_event_id`). `read(run_dir)` reads OFFER's
files only; `read(run_dir, sport)` one sport's.
"""

from __future__ import annotations

import gzip
import json
from collections.abc import Iterable, Iterator, Mapping
from datetime import datetime
from pathlib import Path
from typing import Any

DIRNAME = "unmapped_prices"
FIELDS = ("marketName", "name", "specialBetValue", "price", "status",
          "offerStateId", "outcomeId")
# The measured sports' records also keep Superbet's market id (SHADOW reads
# its markets by id).
SPORT_FIELDS = (*FIELDS, "marketId")


def record(
    sofascore_event_id: int | None,
    superbet_event_id: str,
    item: Mapping[str, Any],
    fetched_at: datetime,
    sport: str | None = None,
) -> dict[str, Any]:
    """One unmapped Superbet odd as it is written: who, what, at what price.
    With `sport` (SHADOW / CS2) the record names it and keeps `marketId`;
    without it (OFFER) the record is what it always was."""
    out: dict[str, Any] = {
        "sofascore_event_id": (None if sofascore_event_id is None
                               else int(sofascore_event_id)),
        "superbet_event_id": str(superbet_event_id),
        "fetched_at_utc": fetched_at.isoformat().replace("+00:00", "Z"),
    }
    if sport is not None:
        out["sport"] = sport
    for key in (FIELDS if sport is None else SPORT_FIELDS):
        if item.get(key) is not None:
            out[key] = item[key]
    return out


def write(
    run_dir: Path, records: Iterable[Mapping[str, Any]], stamp: datetime,
    sport: str | None = None,
) -> Path | None:
    """Append one run's records as a new file; None when there is nothing.
    With `sport` the file is `<sport>_<ts>.jsonl.gz`.

    A file of the same stamp is never overwritten: a second writer in the
    same microsecond gets a suffix instead.
    """
    rows = list(records)
    if not rows:
        return None
    folder = run_dir / DIRNAME
    folder.mkdir(parents=True, exist_ok=True)
    base = stamp.strftime("%Y%m%dT%H%M%S.%fZ")
    if sport is not None:
        base = f"{sport}_{base}"
    path = folder / f"{base}.jsonl.gz"
    n = 1
    while path.exists():
        path = folder / f"{base}_{n}.jsonl.gz"
        n += 1
    tmp = path.with_suffix(".tmp")
    with gzip.open(tmp, "wt", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    tmp.replace(path)
    return path


def files(run_dir: Path, sport: str | None = None) -> list[Path]:
    """The day's files, oldest first: OFFER's (named by their stamp alone)
    without `sport`, else that sport's `<sport>_` files."""
    folder = run_dir / DIRNAME
    if not folder.is_dir():
        return []
    if sport is not None:
        return sorted(folder.glob(f"{sport}_*.jsonl.gz"))
    return sorted(p for p in folder.glob("*.jsonl.gz") if p.name[:1].isdigit())


def read(run_dir: Path, sport: str | None = None) -> Iterator[dict[str, Any]]:
    """Every recorded odd of the day, oldest file first: OFFER's without
    `sport`, else that sport's."""
    for path in files(run_dir, sport):
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    yield json.loads(line)
