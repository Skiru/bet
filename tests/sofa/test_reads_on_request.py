"""Reads on request (operator 2026-11-02): /sofa-day prints without the
analysts; a read-set leg printed unread is a C3 note, never a defect, while
a refusing read still fails C3 and the switch reads the day and the clock."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bet.sofa import epochs
from scripts.sofa import audit_variants as av


def single(eid: int) -> dict[str, Any]:
    return {
        "sofascore_event_id": eid,
        "match": f"H{eid} - A{eid}",
        "market": "corners_total",
        "subject": "",
        "line": 8.5,
        "direction": "OVER",
        "confidence": 0.8,
        "offered_odds": 1.3,
        "kickoff_utc": "2099-01-01T20:00:00Z",
    }


def read(eid: int, verdict: str) -> dict[str, Any]:
    return {
        "sofascore_event_id": eid, "market": None, "subject": None,
        "line": None, "direction": None, "verdict": verdict,
        "author": "verifier", "reason": "r",
    }


def doc(n: int) -> dict[str, Any]:
    return {"singles": [single(i) for i in range(n)], "builders": [],
            "pdf_max_singles": None}


def test_no_reads_json_is_a_note_on_request(tmp_path: Path) -> None:
    av.notes.clear()
    assert av.audit_reads(tmp_path, doc(5), "official", on_request=True) == []
    assert any("reads on request" in n for n in av.notes)
    found = av.audit_reads(tmp_path, doc(5), "official")
    assert len(found) == 1 and "reads.json missing" in found[0]


def test_unread_legs_counted_refusal_still_fails(tmp_path: Path) -> None:
    av.notes.clear()
    (tmp_path / "reads.json").write_text(json.dumps([read(3, "NO_BET")]))
    found = av.audit_reads(tmp_path, doc(5), "official", on_request=True)
    assert len(found) == 1 and "printed despite" in found[0] and "H3" in found[0]
    assert any("5 read-set legs printed unread" in n for n in av.notes)


def test_switch_reads_day_and_clock() -> None:
    on = datetime(2026, 11, 2, 8, 0, tzinfo=UTC)
    assert epochs.reads_on_request("2026-11-02", on)
    assert not epochs.reads_on_request("2026-11-01", on)
    before = datetime(2026, 11, 1, 23, 0, tzinfo=UTC)
    assert not epochs.reads_on_request("2026-11-02", before)
