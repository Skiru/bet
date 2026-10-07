"""C3 asks an analyst's read only of the best 30 official singles and every
builder leg (the operator's order of 2026-10-05, once the official page
limit was lifted). A WATCH / NO_BET still blocks any printed leg."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bet.sofa.confidence import READ_REQUIRED_SINGLES, legs_requiring_read
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


def read(eid: int, verdict: str = "KEEP", author: str = "analyst") -> dict[str, Any]:
    return {
        "sofascore_event_id": eid,
        "market": None,
        "subject": None,
        "line": None,
        "direction": None,
        "verdict": verdict,
        "author": author,
        "reason": "r",
    }


def doc(n: int) -> dict[str, Any]:
    return {
        "singles": [single(i) for i in range(n)],
        "builders": [],
        "pdf_max_singles": None,
    }


def test_only_the_best_30_singles_need_a_read(tmp_path: Path) -> None:
    assert READ_REQUIRED_SINGLES == 30
    d = doc(40)
    assert len(legs_requiring_read(d)) == 30
    (tmp_path / "reads.json").write_text(json.dumps([read(i) for i in range(30)]))
    assert av.audit_reads(tmp_path, d, "official") == []
    # one of the best 30 unread is a finding; one of the rest is not
    (tmp_path / "reads.json").write_text(
        json.dumps([read(i) for i in range(40) if i != 5])
    )
    found = av.audit_reads(tmp_path, d, "official")
    assert len(found) == 1 and "H5 - A5" in found[0]


def test_a_watch_blocks_any_printed_leg_even_beyond_30(tmp_path: Path) -> None:
    d = doc(40)
    reads = [read(i) for i in range(30)] + [read(35, "WATCH", "verifier")]
    (tmp_path / "reads.json").write_text(json.dumps(reads))
    found = av.audit_reads(tmp_path, d, "official")
    assert len(found) == 1 and "printed despite" in found[0] and "H35" in found[0]


def test_every_builder_leg_still_needs_a_read(tmp_path: Path) -> None:
    d = doc(1)
    leg = {k: single(7)[k] for k in ("market", "subject", "line", "direction")}
    d["builders"] = [
        {
            "sofascore_event_id": 7,
            "match": "H7 - A7",
            "best_for_fixture": True,
            "ev_after_haircut": 0.1,
            "legs": [{**leg, "odds": 1.3, "confidence": 0.8}],
        }
    ]
    (tmp_path / "reads.json").write_text(json.dumps([read(0)]))
    found = av.audit_reads(tmp_path, d, "official")
    assert len(found) == 1 and "H7 - A7" in found[0]


def test_u3_reads_a_bucket_edge_p_both_ways() -> None:
    """2026-10-07: Galorys - Gremio printed 0.8375 off p = 0.8499.. and its
    forecast_p was printed 0.85, which reads the bucket above (0.8478): the
    audit called its own rounding a defect."""
    from types import SimpleNamespace

    from scripts.sofa.audit_variants import confidence_reading

    def read(p: float):  # type: ignore[no-untyped-def]
        return SimpleNamespace(value=0.8478 if p >= 0.85 else 0.8375)

    assert confidence_reading(read, 0.85, 0.8375).value == 0.8375
    assert confidence_reading(read, 0.85, 0.8478).value == 0.8478
    # a p well inside a bucket is not excused by the rounding window
    assert confidence_reading(read, 0.80, 0.8478).value == 0.8375
    assert confidence_reading(lambda p: None, 0.85, 0.8375) is None
