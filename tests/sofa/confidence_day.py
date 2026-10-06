"""One CONFIDENCE day on disk for the end-to-end tests: two football legs on
goals_total 1.5 OVER, built so the installed curve prints both on the coupon.

Row A clears the coupon at x > 1; row B only at the coupon's tolerance
(0.90 <= x < 1). The `day` fixture checks those preconditions against the
installed calibration first: a refit that moves the buckets says so here,
not as a mysterious failure downstream.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from bet.sofa.confidence import Calibration
from bet.sofa.contracts import SheetRow

REPO = Path(__file__).resolve().parents[2]
DAY = "2026-01-01"
NOW = datetime.now(UTC)
KICKOFF = "2099-01-01T20:00:00Z"

P_A, ODDS_A, UNDER_A = 0.72, 1.40, 2.75
P_B, ODDS_B, UNDER_B = 0.78, 1.20, 4.00


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
    conf_a = cal.realised("goals_total", P_A, "football")
    conf_b = cal.realised("goals_total", P_B, "football")
    assert conf_a is not None and conf_a[0] >= 0.70, conf_a
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


def _pdf_text(path: Path) -> str:
    from pypdf import PdfReader

    return " ".join(p.extract_text() for p in PdfReader(str(path)).pages)
