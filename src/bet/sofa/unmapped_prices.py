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


def record(
    sofascore_event_id: int,
    superbet_event_id: str,
    item: Mapping[str, Any],
    fetched_at: datetime,
) -> dict[str, Any]:
    """One unmapped Superbet odd as it is written: who, what, at what price."""
    out: dict[str, Any] = {
        "sofascore_event_id": int(sofascore_event_id),
        "superbet_event_id": str(superbet_event_id),
        "fetched_at_utc": fetched_at.isoformat().replace("+00:00", "Z"),
    }
    for key in FIELDS:
        if item.get(key) is not None:
            out[key] = item[key]
    return out


def write(
    run_dir: Path, records: Iterable[Mapping[str, Any]], stamp: datetime
) -> Path | None:
    """Append one run's records as a new file; None when there is nothing.

    A file of the same stamp is never overwritten: a second writer in the
    same microsecond gets a suffix instead.
    """
    rows = list(records)
    if not rows:
        return None
    folder = run_dir / DIRNAME
    folder.mkdir(parents=True, exist_ok=True)
    base = stamp.strftime("%Y%m%dT%H%M%S.%fZ")
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


def read(run_dir: Path) -> Iterator[dict[str, Any]]:
    """Every recorded odd of the day, oldest file first."""
    folder = run_dir / DIRNAME
    if not folder.is_dir():
        return
    for path in sorted(folder.glob("*.jsonl.gz")):
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    yield json.loads(line)
