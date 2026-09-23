"""The `wariant` confidence profile, end to end (2026-09-23).

The operator asked for a permanent variant: confidence >= 0.65 and a price up
to 10% below the one its own confidence asks for (confidence x odds >= 0.90).
Measured before it was added (scripts/sofa/sweep_confidence_gates.py): -3.2%
per bet on 5,802 bets against the official -2.9% on 1,655. So it is built as a
VARIANT - its own artifacts, its own PDF, graded beside the official coupon -
and these tests pin the one property that matters most: building it never
touches the official coupon's files.
"""

from __future__ import annotations

import json
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
    leg_is_ev_positive,
)
from bet.sofa.contracts import SheetRow
from bet.sofa.db import migrate

REPO = Path(__file__).resolve().parents[2]
DAY = "2026-01-01"


# ---------------------------------------------------------------------------
# the profiles themselves
# ---------------------------------------------------------------------------


def test_the_official_profile_is_what_the_stage_always_did() -> None:
    from scripts.sofa.run_confidence import DEFAULT_FLOOR

    std = PROFILES["standard"]
    assert std.floor == DEFAULT_FLOOR == 0.70
    assert std.min_ev is None
    assert confidence_artifact(std) == "08_confidence.json"
    assert std.pdf_suffix == ""


def test_the_variant_is_the_operators_setting_and_writes_elsewhere() -> None:
    var = PROFILES["wariant"]
    assert (var.floor, var.min_ev) == (0.65, 0.90)
    assert confidence_artifact(var) == "08_confidence_wariant.json"
    assert var.pdf_suffix == "_WARIANT"


@pytest.mark.parametrize(
    ("confidence", "odds", "standard", "wariant"),
    [
        (0.80, 1.30, True, True),  # x = 1.04
        (0.80, 1.25, False, True),  # x = 1.00 exactly: official is strict
        (0.75, 1.20, False, True),  # x = 0.90: the variant's edge, inclusive
        (0.75, 1.19, False, False),  # x = 0.8925
    ],
)
def test_the_price_dial(
    confidence: float, odds: float, standard: bool, wariant: bool
) -> None:
    assert PROFILES["standard"].clears_price(confidence, odds) is standard
    assert PROFILES["standard"].clears_price(confidence, odds) is leg_is_ev_positive(
        confidence, odds
    )
    assert PROFILES["wariant"].clears_price(confidence, odds) is wariant


# ---------------------------------------------------------------------------
# end to end: one day, both profiles
# ---------------------------------------------------------------------------

NOW = datetime.now(UTC)
KICKOFF = "2099-01-01T20:00:00Z"

# Row A passes only the variant's FLOOR (confidence ~0.66, x > 1).
# Row B passes the official floor but only the variant's PRICE (x ~0.95).
P_A, ODDS_A, UNDER_A = 0.66, 1.62, 2.30
P_B, ODDS_B, UNDER_B = 0.72, 1.30, 3.30


def _fixture(eid: int) -> dict[str, Any]:
    return {
        "sofascore_event_id": eid,
        "superbet_event_ids": [f"s{eid}"],
        "sport": "football",
        "kickoff_utc": KICKOFF,
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
        "superbet_kickoff_utc": KICKOFF,
        "kickoff_disagreement_h": 0.0,
    }


def _sheet_row(eid: int, p: float, odds: float, market_p: float) -> dict[str, Any]:
    row = {
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
        "market_p": market_p,
        "ladder_centre": None,
        "ladder_sigma": None,
        "p_bar": p - 0.02,
        "bar_reason": "none",
        "required_odds": 1.1 / (p - 0.02),
        "offered_odds": odds,
        "edge": 0.0,
        "surplus": 0.0,
        "verdict": "BELOW_BAR",
        "notes": [],
    }
    SheetRow.model_validate(row)  # the shape the stages really read
    return row


def _samples(eid: int) -> dict[str, Any]:
    # 20 recent matches, 15 of them over 1.5: mode wins, line inside the sample.
    values = [2, 3, 2, 3, 4, 2, 1, 3, 2, 0, 2, 3, 1, 2, 5, 2, 1, 3, 2, 1]
    obs = [
        {
            "sofascore_event_id": eid * 100 + i,
            "match_date_utc": (NOW - timedelta(days=3 + i))
            .isoformat()
            .replace("+00:00", "Z"),
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


def _offer(eid: int, over: float, under: float) -> dict[str, Any]:
    return {
        "sofascore_event_id": eid,
        "status": "PRICED",
        "unmapped_markets": [],
        "price_collisions": [],
        "rungs": [
            {
                "market": "goals_total",
                "subject": "",
                "line": 1.5,
                "over_odds": over,
                "under_odds": under,
                "fetched_at_utc": NOW.isoformat().replace("+00:00", "Z"),
            }
        ],
    }


def _run(
    script: str, runs: Path, *extra: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, f"scripts/sofa/{script}", "--date", DAY, *extra],
        cwd=REPO,
        capture_output=True,
        text=True,
        env={"PYTHONPATH": "src:.", "PATH": "/usr/bin:/bin", **(env or {})},
    )


@pytest.fixture()
def day(tmp_path: Path) -> Path:
    cal = Calibration.load()
    # Preconditions on the fitted curve: if a refit moves these buckets the
    # rows below stop testing what their names say, and this says so first.
    conf_a = cal.realised("goals_total", P_A, "football")
    conf_b = cal.realised("goals_total", P_B, "football")
    assert conf_a is not None and 0.65 <= conf_a[0] < 0.70, conf_a
    assert conf_b is not None and conf_b[0] >= 0.70, conf_b
    assert conf_a[0] * ODDS_A > 1.0, conf_a[0] * ODDS_A
    assert 0.90 <= conf_b[0] * ODDS_B < 1.0, conf_b[0] * ODDS_B

    run = tmp_path / DAY
    run.mkdir()
    (run / "02_fixtures.json").write_text(json.dumps([_fixture(1), _fixture(2)]))
    (run / "03_samples.json").write_text(json.dumps([_samples(1), _samples(2)]))
    (run / "04_offer.json").write_text(
        json.dumps([_offer(1, ODDS_A, UNDER_A), _offer(2, ODDS_B, UNDER_B)])
    )
    (run / "05_sheet.json").write_text(
        json.dumps(
            [
                _sheet_row(1, P_A, ODDS_A, P_A - 0.03),
                _sheet_row(2, P_B, ODDS_B, P_B - 0.03),
            ]
        )
    )
    (run / "vetoes.json").write_text("[]")
    return tmp_path


def _singles(path: Path) -> set[int]:
    return {s["sofascore_event_id"] for s in json.loads(path.read_text())["singles"]}


def test_each_profile_selects_what_its_dials_say(day: Path) -> None:
    run = day / DAY
    std = _run("run_confidence.py", day, "--runs-dir", str(day))
    assert std.returncode == 0, std.stderr
    assert _singles(run / "08_confidence.json") == set()
    assert not (run / "08_confidence_wariant.json").exists()

    var = _run("run_confidence.py", day, "--runs-dir", str(day), "--profile", "wariant")
    assert var.returncode == 0, var.stderr
    assert _singles(run / "08_confidence_wariant.json") == {1, 2}
    doc = json.loads((run / "08_confidence_wariant.json").read_text())
    assert (doc["profile"], doc["confidence_floor"], doc["min_ev"]) == (
        "wariant",
        0.65,
        0.9,
    )
    assert doc["max_overround"] == 0.15
    assert json.loads((run / "08_confidence.json").read_text())["max_overround"] == 0.105
    assert json.loads(std.stdout.strip().splitlines()[-1])["profile"] == "standard"


def test_building_the_variant_never_touches_the_official_files(day: Path) -> None:
    run = day / DAY
    assert _run("run_confidence.py", day, "--runs-dir", str(day)).returncode == 0
    assert _run("build_coupon_pdf.py", day, "--runs-dir", str(day)).returncode == 0
    before = {
        p.name: p.read_bytes()
        for p in run.iterdir()
        if p.name.startswith(("08_confidence.", "KUPON_"))
    }
    assert set(before) == {"08_confidence.json", "08_confidence.md", f"KUPON_{DAY}.pdf"}

    assert (
        _run(
            "run_confidence.py", day, "--runs-dir", str(day), "--profile", "wariant"
        ).returncode
        == 0
    )
    pdf = _run(
        "build_coupon_pdf.py", day, "--runs-dir", str(day), "--profile", "wariant"
    )
    assert pdf.returncode == 0, pdf.stderr

    assert (run / f"KUPON_{DAY}_WARIANT.pdf").stat().st_size > 0
    assert (run / "08_confidence_wariant.md").exists()
    for name, data in before.items():
        assert (run / name).read_bytes() == data, f"{name} was rewritten"


def test_a_variant_artifact_cannot_print_under_the_official_banner(day: Path) -> None:
    run = day / DAY
    assert (
        _run(
            "run_confidence.py", day, "--runs-dir", str(day), "--profile", "wariant"
        ).returncode
        == 0
    )
    (run / "08_confidence.json").write_bytes(
        (run / "08_confidence_wariant.json").read_bytes()
    )
    pdf = _run("build_coupon_pdf.py", day, "--runs-dir", str(day))
    assert pdf.returncode == 2
    assert "built with profile 'wariant'" in pdf.stderr
    assert not (run / f"KUPON_{DAY}.pdf").exists()


def test_settlement_grades_the_variant_beside_the_coupon(day: Path) -> None:
    assert _run("run_confidence.py", day, "--runs-dir", str(day)).returncode == 0
    assert (
        _run(
            "run_confidence.py", day, "--runs-dir", str(day), "--profile", "wariant"
        ).returncode
        == 0
    )

    db = day / "s.db"
    migrate(str(db))
    con = sqlite3.connect(db)
    for eid, actual in ((1, 3.0), (2, 1.0)):  # A wins, B loses
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
                0.7,
                0.68,
                0.65,
                actual,
                "WIN" if actual > 1.5 else "LOSS",
                NOW.isoformat(),
                ODDS_A if eid == 1 else ODDS_B,
                "BELOW_BAR",
            ),
        )
    con.commit()
    con.close()

    out = day / "report.md"
    rep = _run(
        "audit_settlement.py",
        day,
        "--out",
        str(out),
        env={"SOFA_RUNS_DIR": str(day), "SOFA_DB_PATH": str(db)},
    )
    assert rep.returncode == 0, rep.stderr
    text = out.read_text()
    assert "## 7d. WARIANT" in text
    section = text.split("## 7d. WARIANT", 1)[1].split("## 8.", 1)[0]
    assert "| pojedynczych na kuponie | 2 |" in section
    assert "| weszło / nie weszło | 1 / 1 |" in section
    # both rows are variant-only: the official coupon printed neither
    assert (
        "**tylko w wariancie** (nie ma ich na oficjalnym kuponie): 2 pozycji" in section
    )
    assert f"{ODDS_A - 2.0:+.2f} j." in section


def _pdf_text(path: Path) -> str:
    from pypdf import PdfReader

    return " ".join(p.extract_text() for p in PdfReader(str(path)).pages)


def test_the_variant_pdf_explains_its_own_rule_and_prints_no_builders(
    day: Path,
) -> None:
    run = day / DAY
    assert (
        _run(
            "run_confidence.py", day, "--runs-dir", str(day), "--profile", "wariant"
        ).returncode
        == 0
    )
    # A stakeable builder in the variant artifact must still not be printed.
    doc = json.loads((run / "08_confidence_wariant.json").read_text())
    doc["builders"] = [
        {
            "sofascore_event_id": 1,
            "match": "Home 1 - Away 1",
            "best_for_fixture": True,
            "ev_after_haircut": 0.2,
            "n_legs": 2,
            "legs": doc["singles"][:1] * 2,
            "combined_probability": 0.6,
            "fair_odds": 1.67,
            "odds_if_product": 2.3,
            "odds_after_haircut": 2.0,
            "empirical_joint_hits": 0,
            "empirical_joint_n": 0,
        }
    ]
    (run / "08_confidence_wariant.json").write_text(json.dumps(doc))
    pdf = _run(
        "build_coupon_pdf.py", day, "--runs-dir", str(day), "--profile", "wariant"
    )
    assert pdf.returncode == 0, pdf.stderr
    text = _pdf_text(run / f"KUPON_{DAY}_WARIANT.pdf")
    assert "WARIANT" in text and "To nie jest oficjalny kupon" in text
    assert "0 zakładów łączonych" in text
    assert "poniżej uczciwego" in text
    # the official rule's sentence would contradict the rows printed under it
    assert "poniżej nie" not in text


def test_settlement_grades_only_the_singles_the_pdf_printed(tmp_path: Path) -> None:
    from bet.sofa.confidence import PDF_MAX_SINGLES

    run = tmp_path / DAY
    run.mkdir()
    n = PDF_MAX_SINGLES + 5
    singles = [
        {
            "sofascore_event_id": 1000 + i,
            "market": "goals_total",
            "subject": "",
            "line": 1.5,
            "direction": "OVER",
            "confidence": 0.7,
            "offered_odds": 1.4,
        }
        for i in range(n)
    ]
    (run / "02_fixtures.json").write_text("[]")
    (run / "05_sheet.json").write_text("[]")
    (run / "08_confidence_wariant.json").write_text(
        json.dumps(
            {
                "profile": "wariant",
                "confidence_floor": 0.65,
                "min_ev": 0.9,
                "singles": singles,
                "legs": [],
                "builders": [],
            }
        )
    )
    db = tmp_path / "s.db"
    migrate(str(db))
    con = sqlite3.connect(db)
    for s in singles:  # every one of them won
        con.execute(
            "insert into sofa_settled_row (run_date, sofascore_event_id, sport,"
            " market, subject, line, direction, sample_size, sample_mean,"
            " sample_sd, p_central, p_bar, actual_value, outcome, settled_at)"
            " values (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                DAY,
                s["sofascore_event_id"],
                "football",
                "goals_total",
                "",
                1.5,
                "OVER",
                20,
                2.6,
                1.2,
                0.7,
                0.68,
                3.0,
                "WIN",
                NOW.isoformat(),
            ),
        )
    con.commit()
    con.close()
    out = tmp_path / "r.md"
    rep = _run(
        "audit_settlement.py",
        tmp_path,
        "--out",
        str(out),
        env={"SOFA_RUNS_DIR": str(tmp_path), "SOFA_DB_PATH": str(db)},
    )
    assert rep.returncode == 0, rep.stderr
    section = out.read_text().split("## 7d. WARIANT", 1)[1].split("## 8.", 1)[0]
    assert f"| pojedynczych na kuponie | {PDF_MAX_SINGLES} |" in section
    assert f"| weszło / nie weszło | {PDF_MAX_SINGLES} / 0 |" in section
    assert f"Artefakt wariantu miał {n} pojedynczych" in section
    # No official artifact that day: the "what the variant adds" line would be
    # a comparison against nothing, so it is replaced, not printed.
    assert "tylko w wariancie" not in section
    assert "Brak `08_confidence.json`" in section


def test_the_variant_accepts_a_dearer_ladder_and_the_coupon_does_not() -> None:
    """2026-09-23: the operator's variant takes a ladder margin up to 15%; the
    official coupon keeps 10.5%, which held on all five settled days."""
    from bet.sofa.confidence import MAX_OVERROUND

    std, var = PROFILES["standard"], PROFILES["wariant"]
    assert std.max_overround == MAX_OVERROUND == 0.105
    assert var.max_overround == 0.15
    for margin, in_std, in_var in [
        (0.0888, True, True), (0.105, True, True), (0.1117, False, True),
        (0.15, False, True), (0.1501, False, False), (None, False, False),
    ]:
        assert std.single_is_fairly_priced(margin) is in_std
        assert var.single_is_fairly_priced(margin) is in_var
