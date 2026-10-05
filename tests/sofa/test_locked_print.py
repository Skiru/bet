"""A leg printed before its match started counts (operator, 2026-10-05).

A rebuild of CONFIDENCE after the first kickoffs used to drop every printed
leg whose match had started, so 7c / 7d and the ledger never graded it (10-03:
1 official and 66 WARIANT legs; 10-04: 21 WARIANT legs). bet.sofa.locked_print
carries such legs over from the previous artifact of the same profile, as
printed. These tests pin: the carry-over, no duplicate, the page's room, a
pre-start removal staying removed, an artifact with nothing locked unchanged,
the graders grading a locked leg, and the audits not flagging it.
"""

from __future__ import annotations

import dataclasses
import json
import os
import sqlite3
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from bet.sofa.confidence import (
    PROFILES,
    Calibration,
    confidence_artifact,
    printed_singles,
)
from bet.sofa.db import migrate
from bet.sofa.locked_print import carry_over, leg_key, printed_leg_keys

REPO = Path(__file__).resolve().parents[2]
DAY = "2026-01-01"
T0 = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)
# Fixture 2 kicks off first; the rebuild at T1 is five minutes into it.
KICKOFF = {1: "2026-01-01T18:00:00Z", 2: "2026-01-01T11:00:00Z"}
T1 = datetime(2026, 1, 1, 11, 5, tzinfo=UTC)
# Row 1 passes only the variant's floor, row 2 the official floor (both print
# in the WARIANT, which is profile-stable while the official dials move).
P = {1: 0.66, 2: 0.72}
ODDS = {1: (1.62, 2.30), 2: (1.30, 3.30)}


def _z(t: datetime) -> str:
    return t.isoformat().replace("+00:00", "Z")


def _fixture(eid: int) -> dict[str, Any]:
    return {
        "sofascore_event_id": eid,
        "superbet_event_ids": [f"s{eid}"],
        "sport": "football",
        "kickoff_utc": KICKOFF[eid],
        "home_name": f"Home {eid}",
        "away_name": f"Away {eid}",
        "home_entity_id": eid * 10,
        "away_entity_id": eid * 10 + 1,
        "competition_name": "Test League",
        "competition_id": 9,
        "season_id": 9,
        "category_name": "Test",
        "identity": "CONFIRMED",
        "round_number": None,
        "round_name": None,
        "cup_round_type": None,
        "previous_leg_event_id": None,
        "venue_name": None,
        "referee": None,
        "ground_type": None,
        "default_period_count": 2,
        "superbet_kickoff_utc": KICKOFF[eid],
        "kickoff_disagreement_h": 0.0,
    }


def _sheet_row(eid: int) -> dict[str, Any]:
    p = P[eid]
    return {
        "sofascore_event_id": eid,
        "sport": "football",
        "market": "goals_total",
        "subject": "",
        "line": 1.5,
        "direction": "OVER",
        "sample_size": 20,
        "sample_mean": 2.6,
        "sample_sd": 1.2,
        "centre": 2.6,
        "p_central": p,
        "market_p": p - 0.03,
        "ladder_centre": None,
        "ladder_sigma": None,
        "p_bar": p - 0.02,
        "bar_reason": "none",
        "required_odds": 1.1 / (p - 0.02),
        "offered_odds": ODDS[eid][0],
        "edge": 0.0,
        "surplus": 0.0,
        "verdict": "BELOW_BAR",
        "notes": [],
    }


def _samples(eid: int) -> dict[str, Any]:
    values = [2, 3, 2, 3, 4, 2, 1, 3, 2, 0, 2, 3, 1, 2, 5, 2, 1, 3, 2, 1]
    obs = [
        {
            "sofascore_event_id": eid * 100 + i,
            "match_date_utc": _z(T0 - timedelta(days=3 + i)),
            "opponent": "X",
            "value": float(v),
            "minutes": None,
            "competition_id": 9,
            "season_id": 9,
            "venue": None,
        }
        for i, v in enumerate(values)
    ]
    return {
        "sofascore_event_id": eid,
        "readiness": "READY",
        "gaps": [],
        "players": {},
        "metrics": {
            "goals_total": {
                "metric": "goals_total",
                "side_a": obs[:10],
                "side_b": obs[10:],
                "h2h": [],
            }
        },
    }


def _write_offer(run: Path, at: datetime) -> None:
    (run / "04_offer.json").write_text(
        json.dumps(
            [
                {
                    "sofascore_event_id": eid,
                    "status": "PRICED",
                    "unmapped_markets": [],
                    "price_collisions": [],
                    "rungs": [
                        {
                            "market": "goals_total",
                            "subject": "",
                            "line": 1.5,
                            "over_odds": ODDS[eid][0],
                            "under_odds": ODDS[eid][1],
                            "fetched_at_utc": _z(at - timedelta(minutes=1)),
                        }
                    ],
                }
                for eid in (1, 2)
            ]
        )
    )


@pytest.fixture()
def day(tmp_path: Path) -> Path:
    cal = Calibration.load()
    for eid in (1, 2):  # the rows print in the WARIANT on today's curve
        got = cal.realised("goals_total", P[eid], "football")
        assert got is not None and got[0] >= 0.65, got
        assert got[0] * ODDS[eid][0] >= 0.90, got
    run = tmp_path / DAY
    run.mkdir()
    (run / "02_fixtures.json").write_text(json.dumps([_fixture(1), _fixture(2)]))
    (run / "03_samples.json").write_text(json.dumps([_samples(1), _samples(2)]))
    (run / "05_sheet.json").write_text(json.dumps([_sheet_row(1), _sheet_row(2)]))
    (run / "vetoes.json").write_text("[]")
    return tmp_path


def _build(
    runs: Path,
    at: datetime,
    monkeypatch: pytest.MonkeyPatch,
    profile: str = "wariant",
    printed: bool = True,
) -> dict[str, Any]:
    """One CONFIDENCE build; `printed` marks it as having reached a PDF (a
    KUPON file at least as new as the artifact) - what the next build's
    carry-over asks before it locks anything."""
    from scripts.sofa import run_confidence

    _write_offer(runs / DAY, at)
    monkeypatch.setenv("SOFA_NOW", _z(at))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_confidence.py",
            "--date",
            DAY,
            "--runs-dir",
            str(runs),
            "--profile",
            profile,
        ],
    )
    assert run_confidence.main() == 0
    name = confidence_artifact(PROFILES[profile])
    path = runs / DAY / name
    if printed:
        pdf = runs / DAY / f"KUPON_{DAY}{PROFILES[profile].pdf_suffix}.pdf"
        if not pdf.exists():
            pdf.write_bytes(b"%PDF-1.4 stub")
        t = path.stat().st_mtime + 1
        os.utime(pdf, (t, t))
    doc: dict[str, Any] = json.loads(path.read_text())
    return doc


def _keys(items: list[dict[str, Any]]) -> list[tuple[Any, ...]]:
    return [leg_key(x) for x in items]


# ---------------------------------------------------------------------------
# CONFIDENCE
# ---------------------------------------------------------------------------


def test_a_started_printed_leg_is_carried_over_as_printed(
    day: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = _build(day, T0, monkeypatch)
    assert {s["sofascore_event_id"] for s in printed_singles(first)} == {1, 2}
    printed2 = next(s for s in first["singles"] if s["sofascore_event_id"] == 2)

    second = _build(day, T1, monkeypatch)
    singles = second["singles"]
    # Locked first, then the fresh ones.
    assert singles[0]["sofascore_event_id"] == 2 and singles[0]["locked"] is True
    assert {
        k: v
        for k, v in singles[0].items()
        if k not in ("locked", "printed_at_utc", "printed_under")
    } == printed2
    assert singles[0]["printed_at_utc"] == first["created_at_utc"]
    assert singles[0]["printed_under"] == {
        "confidence_floor": 0.65,
        "min_ev": 0.9,
        "max_overround": 0.15,
    }
    assert [s["sofascore_event_id"] for s in singles[1:]] == [1]
    assert "locked" not in singles[1]
    assert second["locked_singles"] == 1 and second["locked_from_utc"] == _z(T0)
    # The leg row is carried too, so the PDF and 7b find it.
    assert any(x.get("locked") and x["sofascore_event_id"] == 2 for x in second["legs"])

    # A third rebuild keeps the build it was really printed in.
    third = _build(day, T1 + timedelta(minutes=30), monkeypatch)
    assert third["singles"][0]["printed_at_utc"] == first["created_at_utc"]


def test_a_locked_leg_is_never_duplicated(
    day: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _build(day, T0, monkeypatch)
    second = _build(day, T1, monkeypatch)
    for part in ("singles", "legs"):
        keys = _keys(second[part])
        assert len(keys) == len(set(keys)), part
    third = _build(day, T1 + timedelta(minutes=10), monkeypatch)
    keys = _keys(third["singles"])
    assert len(keys) == len(set(keys)) == 2


def test_locked_legs_take_the_room_first(
    day: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    one = dataclasses.replace(PROFILES["wariant"], pdf_max_singles=1)
    monkeypatch.setitem(PROFILES, "wariant", one)
    first = _build(day, T0, monkeypatch)
    # Ranked by confidence: fixture 2 (official floor) wins the one slot.
    assert [s["sofascore_event_id"] for s in printed_singles(first)] == [2]
    second = _build(day, T1, monkeypatch)
    # Fixture 2 is locked and fills the page; fixture 1 is in the artifact
    # but not printed - no room left.
    assert [s["sofascore_event_id"] for s in printed_singles(second)] == [2]
    assert [s["sofascore_event_id"] for s in second["singles"]] == [2, 1]
    assert second["pdf_max_singles"] == 1


def test_a_lowered_page_limit_never_pushes_a_locked_leg_off(
    day: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    two = dataclasses.replace(PROFILES["wariant"], pdf_max_singles=2)
    monkeypatch.setitem(PROFILES, "wariant", two)
    _build(day, T0, monkeypatch)
    monkeypatch.setitem(
        PROFILES, "wariant", dataclasses.replace(two, pdf_max_singles=1)
    )
    both_started = datetime(2026, 1, 1, 18, 5, tzinfo=UTC)
    after = _build(day, both_started, monkeypatch)
    assert after["pdf_max_singles"] == 2
    assert {s["sofascore_event_id"] for s in printed_singles(after)} == {1, 2}
    assert all(s["locked"] for s in printed_singles(after))


def test_a_leg_removed_before_its_start_stays_removed(
    day: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _build(day, T0, monkeypatch)
    run = day / DAY
    # Fixture 1 (not started at T1) is vetoed: the rebuild drops it for good.
    # Fixture 2 (started) gets a NO_BET read after its start: it stays.
    (run / "vetoes.json").write_text(
        json.dumps(
            [
                {
                    "sofascore_event_id": 1,
                    "market": None,
                    "subject": None,
                    "line": None,
                    "direction": None,
                    "reason_class": "CONTEXT",
                    "reason": "rotation",
                    "context": None,
                }
            ]
        )
    )
    (run / "reads.json").write_text(
        json.dumps(
            [
                {
                    "sofascore_event_id": 2,
                    "market": None,
                    "subject": None,
                    "line": None,
                    "direction": None,
                    "verdict": "NO_BET",
                    "author": "verifier",
                    "reason": "late read",
                }
            ]
        )
    )
    second = _build(day, T1, monkeypatch)
    assert [s["sofascore_event_id"] for s in second["singles"]] == [2]
    assert second["singles"][0]["locked"] is True
    assert second["locked_late_refusals"] == [
        {
            "key": [2, "goals_total", "", 1.5, "OVER"],
            "as": "single",
            "refusal": "READ_NO_BET",
        },
    ]
    # Still removed on the next rebuild, after fixture 1 started too: it was
    # not printed by the build before its start, so there is nothing to lock.
    later = _build(day, datetime(2026, 1, 1, 18, 5, tzinfo=UTC), monkeypatch)
    assert [s["sofascore_event_id"] for s in later["singles"]] == [2]


def test_an_artifact_with_nothing_locked_is_what_it_was(
    day: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = _build(day, T0, monkeypatch)
    again = _build(day, T0 + timedelta(minutes=5), monkeypatch)
    for doc in (first, again):
        assert not [k for k in doc if k.startswith("locked")]
        for part in ("singles", "legs"):
            for x in doc[part]:
                assert not {"locked", "printed_at_utc", "printed_under"} & set(x)
    strip = {"created_at_utc"}
    assert {k: v for k, v in first.items() if k not in strip} == {
        k: v for k, v in again.items() if k not in strip
    }


def test_nothing_is_carried_from_another_profile_or_from_the_future() -> None:
    prev = {
        "profile": "wariant",
        "created_at_utc": _z(T0),
        "pdf_max_singles": None,
        "confidence_floor": 0.65,
        "min_ev": 0.9,
        "max_overround": 0.15,
        "legs": [],
        "builders": [],
        "singles": [
            {
                "sofascore_event_id": 2,
                "market": "goals_total",
                "subject": "",
                "line": 1.5,
                "direction": "OVER",
                "kickoff_utc": KICKOFF[2],
            }
        ],
    }
    always = lambda eid, ko: True  # noqa: E731
    assert carry_over(prev, "standard", T1, always).singles == []
    assert carry_over(prev, "wariant", T0 - timedelta(minutes=1), always).singles == []
    assert len(carry_over(prev, "wariant", T1, always).singles) == 1
    assert carry_over(None, "wariant", T1, always).singles == []


def test_a_started_printed_builder_is_carried_whole() -> None:
    leg = {
        "market": "goals_total",
        "subject": "",
        "line": 1.5,
        "direction": "OVER",
        "confidence": 0.8,
        "odds": 1.4,
    }
    leg2 = {**leg, "market": "corners_total", "line": 8.5}
    full = [
        {**x, "sofascore_event_id": 2, "offered_odds": x["odds"], "implied_p": 0.7}
        for x in (leg, leg2)
    ]
    builder = {
        "sofascore_event_id": 2,
        "match": "Home 2 - Away 2",
        "kickoff_utc": KICKOFF[2],
        "legs": [leg, leg2],
        "n_legs": 2,
        "best_for_fixture": True,
        "ev_after_haircut": 0.05,
        "odds_if_product": 1.96,
    }
    prev = {
        "profile": "standard",
        "created_at_utc": _z(T0),
        "prints_builders": True,
        "confidence_floor": 0.7,
        "min_ev": None,
        "max_overround": 0.105,
        "singles": [],
        "legs": full,
        "builders": [builder],
    }
    got = carry_over(prev, "standard", T1, lambda eid, ko: eid == 2)
    assert len(got.builders) == 1 and got.builders[0]["locked"] is True
    assert got.builders[0]["legs"] == [leg, leg2]
    assert got.builder_fixtures == {2}
    assert {leg_key(x) for x in got.legs} == {leg_key(x) for x in full}
    assert printed_leg_keys(prev) == {leg_key(x) for x in full}
    # Not started: nothing to lock.
    assert not carry_over(prev, "standard", T1, lambda eid, ko: False)


# ---------------------------------------------------------------------------
# readers
# ---------------------------------------------------------------------------


def _settle_rows(db: Path, outcomes: dict[int, str]) -> None:
    migrate(str(db))
    con = sqlite3.connect(db)
    for eid, outcome in outcomes.items():
        con.execute(
            "insert into sofa_settled_row (run_date, sofascore_event_id, sport,"
            " competition_id, market, subject, line, direction, sample_size,"
            " sample_mean, sample_sd, p_central, p_bar, market_p, actual_value,"
            " outcome, settled_at, offered_odds, verdict) values"
            " (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                DAY,
                eid,
                "football",
                9,
                "goals_total",
                "",
                1.5,
                "OVER",
                20,
                2.6,
                1.2,
                P[eid],
                P[eid] - 0.02,
                P[eid] - 0.03,
                3.0 if outcome == "WIN" else 1.0,
                outcome,
                _z(T1),
                ODDS[eid][0],
                "BELOW_BAR",
            ),
        )
    con.commit()
    con.close()


def _locked_day(day: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    _build(day, T0, monkeypatch)
    (day / DAY / "vetoes.json").write_text(
        json.dumps(
            [
                {
                    "sofascore_event_id": 1,
                    "market": None,
                    "subject": None,
                    "line": None,
                    "direction": None,
                    "reason_class": "OTHER",
                    "reason": "x",
                    "context": None,
                }
            ]
        )
    )
    doc = _build(day, T1, monkeypatch)
    assert [(s["sofascore_event_id"], s.get("locked")) for s in doc["singles"]] == [
        (2, True)
    ]
    return doc


def test_settlement_and_the_ledger_grade_a_locked_leg(
    day: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _locked_day(day, monkeypatch)
    db = day / "s.db"
    _settle_rows(db, {2: "WIN"})

    from scripts.sofa.record_results import confidence_rows

    rows = {r["variant"]: r for r in confidence_rows(str(day), DAY, str(db))}
    singles = rows["wariant"]["singles"]
    assert (singles["settled"], singles["won"]) == (1, 1), singles

    out = day / "report.md"
    rep = subprocess.run(
        [
            sys.executable,
            "scripts/sofa/audit_settlement.py",
            "--date",
            DAY,
            "--out",
            str(out),
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        env={
            "PYTHONPATH": "src:.",
            "PATH": "/usr/bin:/bin",
            "SOFA_RUNS_DIR": str(day),
            "SOFA_DB_PATH": str(db),
        },
    )
    assert rep.returncode == 0, rep.stderr
    section = out.read_text().split("## 7d. WARIANT", 1)[1].split("## 8.", 1)[0]
    assert "| pojedynczych na kuponie | 1 |" in section
    assert "| weszło / nie weszło | 1 / 0 |" in section


def test_settle_grades_a_printed_rung_the_final_sheet_left_unpriced(
    day: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.sofa.run_settle import printed_keys, rows_to_consider

    _locked_day(day, monkeypatch)
    sheet = [_sheet_row(1), {**_sheet_row(2), "offered_odds": None}]
    keys = printed_keys(day / DAY)
    assert keys == {(2, "goals_total", "", 1.5, "OVER")}
    got = rows_to_consider(sheet, include_unpriced=False, printed=keys)
    assert [r["sofascore_event_id"] for r in got] == [1, 2]
    # Without printed keys the old selection stands.
    assert [
        r["sofascore_event_id"] for r in rows_to_consider(sheet, include_unpriced=False)
    ] == [1]


def test_audit_variants_checks_a_locked_leg_against_its_own_build(
    day: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.sofa.audit_variants import audit_confidence

    _locked_day(day, monkeypatch)
    c2 = [f for f in audit_confidence(str(day), DAY, "wariant") if f.startswith("C2")]
    assert c2 == []

    path = day / DAY / "08_confidence_wariant.json"
    doc = json.loads(path.read_text())
    # A locked leg printed after its kickoff is still a defect.
    doc["singles"][0]["printed_at_utc"] = KICKOFF[2]
    path.write_text(json.dumps(doc))
    c2 = [f for f in audit_confidence(str(day), DAY, "wariant") if f.startswith("C2")]
    assert len(c2) == 1 and "printed after its kickoff" in c2[0]
    # And one without its print stamp cannot be checked: a finding.
    del doc["singles"][0]["printed_at_utc"]
    path.write_text(json.dumps(doc))
    c2 = [f for f in audit_confidence(str(day), DAY, "wariant") if f.startswith("C2")]
    assert len(c2) == 1 and "locked without printed_at_utc" in c2[0]


def test_c3_does_not_flag_a_locked_leg_for_a_read_after_its_start(
    tmp_path: Path,
) -> None:
    from scripts.sofa import audit_variants as av

    single = {
        "sofascore_event_id": 2,
        "match": "Home 2 - Away 2",
        "market": "goals_total",
        "subject": "",
        "line": 1.5,
        "direction": "OVER",
        "kickoff_utc": KICKOFF[2],
    }
    reads = [
        {
            "sofascore_event_id": 2,
            "market": None,
            "subject": None,
            "line": None,
            "direction": None,
            "verdict": "KEEP",
            "author": "analyst",
            "reason": "ok",
        },
        {
            "sofascore_event_id": 2,
            "market": None,
            "subject": None,
            "line": None,
            "direction": None,
            "verdict": "NO_BET",
            "author": "verifier",
            "reason": "after the start",
        },
    ]
    (tmp_path / "reads.json").write_text(json.dumps(reads))
    av.notes.clear()
    locked_doc = {"singles": [{**single, "locked": True}], "builders": []}
    assert av.audit_reads(tmp_path, locked_doc, "official") == []
    assert len(av.notes) == 1 and "locked" in av.notes[0]
    # The same read on a leg printed by THIS build is a defect, as before.
    fresh = av.audit_reads(tmp_path, {"singles": [single], "builders": []}, "official")
    assert len(fresh) == 1 and "printed despite READ_NO_BET" in fresh[0]


def test_wszystkie_and_closing_capture_read_a_locked_leg_verbatim(
    day: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from bet.sofa.multi_coupon import official_positions
    from scripts.sofa.capture_closing import printed_legs

    doc = _locked_day(day, monkeypatch)
    pos = official_positions(doc, T1)["singles"]
    assert [p["source"] for p in pos] == doc["singles"]
    assert pos[0]["odds"] == ODDS[2][0] and pos[0]["started"] is True
    legs = printed_legs(day / DAY)
    assert [(v, leg["sofascore_event_id"]) for v, leg in legs] == [("wariant", 2)]


def test_the_pdf_prints_a_locked_leg_marked(
    day: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pypdf import PdfReader

    _locked_day(day, monkeypatch)
    pdf = subprocess.run(
        [
            sys.executable,
            "scripts/sofa/build_coupon_pdf.py",
            "--date",
            DAY,
            "--runs-dir",
            str(day),
            "--profile",
            "wariant",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        env={"PYTHONPATH": "src:.", "PATH": "/usr/bin:/bin", "SOFA_NOW": _z(T1)},
    )
    assert pdf.returncode == 0, pdf.stderr
    # A locked leg started on purpose: no "late print" warning for it.
    assert "WARNING" not in pdf.stderr
    text = " ".join(
        p.extract_text()
        for p in PdfReader(str(day / DAY / f"KUPON_{DAY}_WARIANT.pdf")).pages
    )
    flat = " ".join(text.split())
    assert "w grze - wydrukowane przed startem" in flat
    assert "wydruk 10:00Z" in flat
    assert "start przed renderem PDF" not in flat


def test_a_started_printed_builder_survives_the_rebuild_and_prints(
    day: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from pypdf import PdfReader

    first = _build(day, T0, monkeypatch)
    one = next(x for x in first["legs"] if x["sofascore_event_id"] == 2)
    leg = {k: one[k] for k in ("market", "subject", "line", "direction", "confidence")}
    leg["odds"] = one["offered_odds"]
    leg["unfitted_constants"] = []
    builder = {
        "sofascore_event_id": 2,
        "match": "Home 2 - Away 2",
        "competition": "Test League",
        "kickoff_utc": one["kickoff_utc"],
        "legs": [leg, leg],
        "n_legs": 2,
        "combined_probability": 0.6,
        "product_probability": 0.6,
        "empirical_joint_hits": 0,
        "empirical_joint_n": 0,
        "fair_odds": 1.67,
        "odds_if_product": 2.3,
        "ev_if_product_priced": 0.3,
        "haircut": 0.12,
        "odds_after_haircut": 2.0,
        "ev_after_haircut": 0.2,
        "best_for_fixture": True,
    }
    first["builders"] = [builder]
    (day / DAY / "08_confidence_wariant.json").write_text(json.dumps(first))

    second = _build(day, T1, monkeypatch)
    assert second["locked_builders"] == 1
    got = second["builders"][0]
    assert got["locked"] is True and got["printed_at_utc"] == first["created_at_utc"]
    assert {
        k: v
        for k, v in got.items()
        if k not in ("locked", "printed_at_utc", "printed_under")
    } == builder
    assert sum(1 for b in second["builders"] if b["sofascore_event_id"] == 2) == 1

    pdf = subprocess.run(
        [
            sys.executable,
            "scripts/sofa/build_coupon_pdf.py",
            "--date",
            DAY,
            "--runs-dir",
            str(day),
            "--profile",
            "wariant",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        env={"PYTHONPATH": "src:.", "PATH": "/usr/bin:/bin", "SOFA_NOW": _z(T1)},
    )
    assert pdf.returncode == 0, pdf.stderr
    text = " ".join(
        p.extract_text()
        for p in PdfReader(str(day / DAY / f"KUPON_{DAY}_WARIANT.pdf")).pages
    )
    flat = " ".join(text.split())
    # The header count, the single and the builder.
    assert flat.count("w grze - wydrukowane przed startem") == 3


def test_a_build_that_never_reached_a_pdf_locks_nothing(
    day: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The provisional build before the analysts' read is never rendered: a
    leg the operator never saw on a PDF is not locked when its match starts
    (review 2026-10-05)."""
    _build(day, T0, monkeypatch, printed=False)
    second = _build(day, T1, monkeypatch)
    assert not any(s.get("locked") for s in second["singles"])
    assert "locked_singles" not in second


def test_an_unprinted_build_still_carries_what_it_had_locked(
    day: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = _build(day, T0, monkeypatch)  # printed
    second = _build(day, T1, monkeypatch, printed=False)  # locks 2, no PDF
    assert second["singles"][0]["locked"] is True
    third = _build(day, T1 + timedelta(minutes=5), monkeypatch)
    locked = [s for s in third["singles"] if s.get("locked")]
    assert [s["sofascore_event_id"] for s in locked] == [2]
    assert locked[0]["printed_at_utc"] == first["created_at_utc"]


def _late_doc() -> dict[str, Any]:
    def single(eid: int, kickoff: str) -> dict[str, Any]:
        return {"sofascore_event_id": eid, "match": f"M{eid}",
                "market": "games_won_for", "subject": "a", "line": 11.5,
                "direction": "UNDER",
                "kickoff_utc": kickoff, "confidence": 0.8, "odds": 1.3}
    return {"profile": "standard", "epoch": "stats_only", "pdf_max_singles": None,
            "created_at_utc": "2026-10-05T08:40:41Z",
            "pdf_rendered_at_utc": "2026-10-05T09:19:49Z",
            # 1 started before the render, 2 after it, 3 was locked earlier
            "singles": [single(1, "2026-10-05T09:00:00Z"),
                        single(2, "2026-10-05T09:30:00Z"),
                        {**single(3, "2026-10-05T08:00:00Z"),
                         "locked": True, "printed_at_utc": "2026-10-05T07:00:00Z"}]}


def test_a_leg_whose_match_started_before_the_pdf_render_is_not_locked():
    # 10-05: the PDF was rendered 09:19:49Z; twelve tennis legs starting
    # 09:00-09:10Z were locked with printed_at_utc 09:19:49Z and C2 flagged
    # them "printed after its kickoff". The operator's rule counts a leg
    # printed BEFORE its start only.
    now = datetime(2026, 10, 5, 10, 18, tzinfo=UTC)
    out = carry_over(_late_doc(), "standard", now, lambda eid, ko: True)
    assert sorted(s["sofascore_event_id"] for s in out.singles) == [2, 3]
    # the earlier print's stamp is kept, not moved to this render
    stamps = {s["sofascore_event_id"]: s["printed_at_utc"] for s in out.singles}
    assert stamps[3] == "2026-10-05T07:00:00Z"
    late = [(x["sofascore_event_id"], x["printed_at_utc"])
            for x in out.printed_after_start]
    assert late == [(1, "2026-10-05T09:19:49Z")]


def test_printed_after_start_survives_the_merge_once():
    from bet.sofa.locked_print import merge_locked

    now = datetime(2026, 10, 5, 10, 18, tzinfo=UTC)
    a = carry_over(_late_doc(), "standard", now, lambda eid, ko: True)
    b = carry_over(_late_doc(), "standard", now, lambda eid, ko: True)
    assert len(merge_locked(a, b).printed_after_start) == 1
