"""Shared builders for the coupon / ledger / sport-day tests: a coupon
artifact on disk, settled rows in a scratch database, Superbet snapshot
records of a measured sport."""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from bet.sofa import sport_day as sd

DATE = "2026-09-30"
AT = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)


def iso(at: datetime) -> str:
    return at.isoformat().replace("+00:00", "Z")


def official_single(
    eid: int,
    market: str,
    odds: float,
    conf: float,
    kickoff: datetime = AT + timedelta(hours=6),
) -> dict[str, Any]:
    return {
        "sofascore_event_id": eid,
        "match": f"H{eid} - A{eid}",
        "competition": "Liga",
        "sport": "football",
        "kickoff_utc": iso(kickoff),
        "market": market,
        "subject": "",
        "line": 7.5,
        "direction": "OVER",
        "confidence": conf,
        "offered_odds": odds,
        "overround": 0.08,
    }


def builder(eid: int, stakeable: bool) -> dict[str, Any]:
    return {
        "sofascore_event_id": eid,
        "match": f"H{eid} - A{eid}",
        "kickoff_utc": iso(AT + timedelta(hours=5)),
        "n_legs": 2,
        "combined_probability": 0.55,
        "odds_if_product": 2.10,
        "odds_after_haircut": 1.85,
        "ev_after_haircut": 0.02 if stakeable else -0.03,
        "best_for_fixture": True,
        "legs": [
            {
                "market": "corners_total",
                "subject": "",
                "line": 7.5,
                "direction": "OVER",
            },
            {"market": "goals_total", "subject": "", "line": 3.5, "direction": "UNDER"},
        ],
    }


def write_official(
    root: Path,
    singles: list[dict[str, Any]],
    builders: list[dict[str, Any]] | None = None,
    pdf: bool = True,
) -> Path:
    run = root / DATE
    run.mkdir(parents=True, exist_ok=True)
    (run / "05_sheet.json").write_text("[]", encoding="utf-8")
    doc = {
        "profile": "standard",
        "created_at_utc": iso(AT - timedelta(hours=1)),
        "pdf_max_singles": 30,
        "prints_builders": True,
        "min_ev": None,
        "singles": singles,
        "builders": builders or [],
        "unfitted_constants": ["K_PRICE"],
    }
    later = (AT - timedelta(minutes=50)).timestamp()
    (run / "08_confidence.json").write_text(json.dumps(doc), encoding="utf-8")
    os.utime(run / "05_sheet.json", (later - 60, later - 60))
    os.utime(run / "08_confidence.json", (later, later))
    if pdf:
        (run / f"KUPON_{DATE}.pdf").write_bytes(b"%PDF official")
        os.utime(run / f"KUPON_{DATE}.pdf", (later + 5, later + 5))
    return run


def write_db(root: Path, rows: list[dict[str, Any]], date: str = DATE) -> str:
    """The rows where 7c reads them: sofa_settled_row in the database - not
    07_settled.json, which regrade_settled.py does not correct."""
    import sqlite3

    db = root / "sofa.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS sofa_settled_row (run_date TEXT, "
        "sofascore_event_id INTEGER, market TEXT, subject TEXT, line REAL, "
        "direction TEXT, outcome TEXT)"
    )
    conn.executemany(
        "INSERT INTO sofa_settled_row VALUES (?,?,?,?,?,?,?)",
        [
            (
                date,
                r["sofascore_event_id"],
                r["market"],
                r["subject"],
                r["line"],
                r["direction"],
                r["outcome"],
            )
            for r in rows
        ],
    )
    conn.commit()
    conn.close()
    return str(db)


def settled_row(
    eid: int, market: str, outcome: str, line: float = 7.5, direction: str = "OVER"
) -> dict[str, Any]:
    return {
        "sofascore_event_id": eid,
        "market": market,
        "subject": "",
        "line": line,
        "direction": direction,
        "outcome": outcome,
    }


def hline(
    eid: str,
    market_id: int,
    family: str,
    side: str,
    odds: float,
    line: float | None = None,
    period: int = 0,
    subject: str = "",
) -> dict[str, Any]:
    return {
        "superbet_event_id": eid,
        "market_id": market_id,
        "family": family,
        "period": period,
        "subject": subject,
        "line": line,
        "side": side,
        "odds": odds,
    }


def snap(
    eid: str,
    lines: list[dict[str, Any]],
    fetched: datetime,
    kickoff: datetime = AT + timedelta(hours=6),
) -> dict[str, Any]:
    return {
        "fetched_at_utc": iso(fetched),
        "superbet_event_id": eid,
        "match_name": f"Home {eid}·Away {eid}",
        "team1": f"Home {eid}",
        "team2": f"Away {eid}",
        "kickoff_utc": iso(kickoff),
        "tournament": "Liga",
        "lines": lines,
    }


def total_pair(
    eid: str, over: float, under: float, line: float = 5.5
) -> list[dict[str, Any]]:
    return [
        hline(eid, 623, "total", "OVER", over, line),
        hline(eid, 623, "total", "UNDER", under, line),
    ]


def write_snaps(
    root: Path, sport: sd.SportKey, date: str, snaps: list[dict[str, Any]]
) -> Path:
    d = sd.day_dir(str(root), sport, date)
    d.mkdir(parents=True, exist_ok=True)
    with (d / "snapshots.jsonl").open("a", encoding="utf-8") as fh:
        fh.write("".join(json.dumps(r) + "\n" for r in snaps))
    return d
