"""Every priced row of a day and what the confidence stage did with it.

The operator (2026-10-21): "you compute markets but don't show them - why
compute them?". CONFIDENCE and SPORT_CONFIDENCE refused thousands of rows a
day and kept only a count per reason; this records the reason per row:

    08_refusals.json         football / tennis - one row per 05_sheet.json row
                             (CONFIDENCE, scripts/sofa/run_confidence.py)
    08_refusals_sports.json  hockey / basketball / volleyball / CS2 - one row per
                             priced Superbet side SPORT_CONFIDENCE read
                             (scripts/sofa/run_sport_confidence.py)

Both have the same compact shape: `events` (match, start, sport) and `rows`,
arrays in the order of `COLUMNS`. `reason` None = the row passed every gate
of its stage and became a leg (whether it then printed is COUPON_ASSEMBLY's
and the page's question, read from 11_coupon.json). `p` is the statistics'
probability (football / tennis `p_central`, a sport's model p), `confidence`
the calibrated number where the stage got that far.

**Display only.** The coupon page (bet.sofa.coupon_html, "Wszystkie wyceny")
reads these files; no gate, no stage and no grader does. Recording a row
changes no leg: the counts the stages published before (`refused`) are the
same numbers, kept by the same call.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, MutableMapping
from pathlib import Path
from typing import Any

FILE = "08_refusals.json"
SPORTS_FILE = "08_refusals_sports.json"
COLUMNS = ("event", "market", "market_id", "period", "subject", "line",
           "direction", "odds", "p", "confidence", "reason")
EVENT_FIELDS = ("sport", "sofascore_event_id", "superbet_event_id", "match",
                "competition", "kickoff_utc")
NOTE = ("display only - read by the coupon page (bet.sofa.coupon_html), "
        "never by a gate; reason null = the row passed every gate of its stage")


def _round(value: Any, digits: int = 4) -> float | None:
    try:
        return None if value is None else round(float(value), digits)
    except (TypeError, ValueError):
        return None


class RefusalRecord:
    """The rows of one stage run, each with the reason it stopped at.

    `counts` (optional): the stage's own counter, incremented by `refuse` -
    the one call that counts and records, so the two cannot disagree.
    `start` opens a row, `odds` / `confidence` update it as the stage learns
    them, `refuse` / `passed` close it."""

    def __init__(self, counts: MutableMapping[str, int] | None = None) -> None:
        self.counts = counts
        self.events: list[dict[str, Any]] = []
        self._event_index: dict[tuple[Any, ...], int] = {}
        self.rows: list[list[Any]] = []
        self._row: list[Any] | None = None
        self.odds: float | None = None
        self.confidence: float | None = None
        self._p: float | None = None

    def event(self, key: tuple[Any, ...], info: Mapping[str, Any]) -> int:
        """The index of an event in `events` (added on first sight)."""
        idx = self._event_index.get(key)
        if idx is None:
            idx = len(self.events)
            self._event_index[key] = idx
            self.events.append({k: info.get(k) for k in EVENT_FIELDS})
        return idx

    def start(self, event: int, market: str, market_id: int | None,
              period: int | None, subject: str, line: Any, direction: str,
              odds: Any, p: Any) -> None:
        self._row = [event, market, market_id, period, subject or "",
                     None if line is None else float(line), direction]
        self.odds = None if odds is None else float(odds)
        self.confidence = None
        self._p = _round(p)

    def _close(self, reason: str | None) -> None:
        if self._row is None:
            return
        self.rows.append([*self._row, self.odds, self._p,
                          _round(self.confidence), reason])
        self._row = None

    def refuse(self, reason: str) -> None:
        """Count the refusal (the stage's counter) and record the open row."""
        if self.counts is not None:
            self.counts[reason] = self.counts.get(reason, 0) + 1
        self._close(reason)

    def passed(self, note: str | None = None) -> None:
        """The open row became a leg; `note`: why it still cannot print as a
        single (a ladder too dear), None when nothing in this stage stops it."""
        self._close(note)

    def doc(self, date: str, created_at_utc: str, stage: str) -> dict[str, Any]:
        return {"date": date, "created_at_utc": created_at_utc, "stage": stage,
                "note": NOTE, "columns": list(COLUMNS), "events": self.events,
                "rows": self.rows}


def dumps(doc: Mapping[str, Any]) -> str:
    """One row per line: compact, and a diff still reads row by row."""
    head = {k: v for k, v in doc.items() if k not in ("events", "rows")}
    parts = [json.dumps(head, ensure_ascii=False)[:-1]]
    for key in ("events", "rows"):
        items = doc.get(key) or []
        body = ",\n".join(json.dumps(x, ensure_ascii=False, separators=(",", ":"))
                          for x in items)
        parts.append(f',\n"{key}":[\n{body}\n]')
    return "".join(parts) + "}\n"


def load(path: Path) -> dict[str, Any] | None:
    """A refusal file, or None when absent / unreadable (a day built before
    the record existed)."""
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(doc, dict) or doc.get("columns") != list(COLUMNS):
        return None
    return doc


def rows_as_dicts(doc: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The rows as dicts with their event's fields (tests, the page)."""
    events = doc.get("events") or []
    out = []
    for raw in doc.get("rows") or []:
        row = dict(zip(COLUMNS, raw, strict=True))
        out.append({**events[int(row["event"])], **row})
    return out
