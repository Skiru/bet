"""Tests for context checks and upset risk modules."""
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import db_data_loader
from context_checks import run_context_checks
from upset_risk import run_upset_risk


# ---------------------------------------------------------------------------
# Context checks
# ---------------------------------------------------------------------------


def test_context_checks_no_data():
    """Empty state with no data files — should not crash."""
    tmp = tempfile.mkdtemp()
    with patch("context_checks.DATA_DIR", Path(tmp)):
        success, summary = run_context_checks("2099-01-01", {})
    assert success is True
    assert isinstance(summary, str)
    import shutil
    shutil.rmtree(tmp)


# ---------------------------------------------------------------------------
# Upset risk
# ---------------------------------------------------------------------------


def test_upset_risk_no_candidates():
    """Empty candidates (no S3 data) — should not crash."""
    tmp = tempfile.mkdtemp()
    with patch("upset_risk.DATA_DIR", Path(tmp)):
        success, summary = run_upset_risk("2099-01-01", {})
    assert success is True
    assert isinstance(summary, str)
    import shutil
    shutil.rmtree(tmp)


def test_upset_risk_with_candidates():
    """S3 data with candidates — should score them without crashing."""
    tmp = tempfile.mkdtemp()
    data_dir = Path(tmp)
    s3_data = {
        "analyses": [
            {
                "sport": "football",
                "event": "Team A vs Team B",
                "markets": [{"name": "Corners", "safety_score": 0.75}],
            },
            {
                "sport": "tennis",
                "event": "Player X vs Player Y",
                "markets": [{"name": "Total Games", "safety_score": 0.60}],
            },
        ]
    }
    (data_dir / "2099-01-01_s3_deep_stats.json").write_text(
        json.dumps(s3_data), encoding="utf-8"
    )
    with patch("upset_risk.DATA_DIR", data_dir):
        success, summary = run_upset_risk("2099-01-01", {})
    assert success is True
    assert isinstance(summary, str)
    import shutil
    shutil.rmtree(tmp)


def _candidate(home: str, away: str, *, fixture_id: int) -> dict:
    return {
        "sport": "football",
        "fixture_id": fixture_id,
        "home_team": home,
        "away_team": away,
        "kickoff": "2099-01-01T12:00:00",
        "ranking": [{"name": "Corners", "safety_score": 0.7, "combined_avg": 10.0, "combined_avg_l5": 10.0}],
        "h2h": {"meetings": [1, 2, 3]},
        "context_flags": [],
    }


def test_context_checks_preserve_json_candidate_universe_on_partial_db(monkeypatch, tmp_path):
    date = "2099-01-01"
    s3_path = tmp_path / f"{date}_s3_deep_stats.json"
    s3_path.write_text(
        json.dumps(
            {
                "analyses": [
                    _candidate("Alpha", "Beta", fixture_id=1),
                    _candidate("Gamma", "Delta", fixture_id=2),
                    _candidate("Eta", "Theta", fixture_id=3),
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / f"weather_{date}.json").write_text(
        json.dumps(
            {
                "venues": {
                    "Alpha vs Beta": {"flags": ["wind"]},
                }
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / f"espn_enrichment_{date}.json").write_text(
        json.dumps({"injuries": {}}),
        encoding="utf-8",
    )

    monkeypatch.setattr(db_data_loader, "DATA_DIR", tmp_path)
    monkeypatch.setattr(
        db_data_loader,
        "_load_analysis_results_raw_from_db",
        lambda _: [
            _candidate("Alpha", "Beta", fixture_id=1),
            _candidate("Gamma", "Delta", fixture_id=2),
        ],
    )

    with patch("context_checks.DATA_DIR", tmp_path):
        success, summary = run_context_checks(date, {})

    assert success is True
    assert isinstance(summary, str)
    saved = json.loads(s3_path.read_text(encoding="utf-8"))
    assert len(saved["analyses"]) == 3
    assert saved["analyses"][0]["context_flags"]


def test_upset_risk_preserves_json_candidate_universe_on_partial_db(monkeypatch, tmp_path):
    date = "2099-01-01"
    s3_path = tmp_path / f"{date}_s3_deep_stats.json"
    s3_path.write_text(
        json.dumps(
            {
                "analyses": [
                    _candidate("Alpha", "Beta", fixture_id=1),
                    _candidate("Gamma", "Delta", fixture_id=2),
                    _candidate("Eta", "Theta", fixture_id=3),
                ]
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(db_data_loader, "DATA_DIR", tmp_path)
    monkeypatch.setattr(
        db_data_loader,
        "_load_analysis_results_raw_from_db",
        lambda _: [
            _candidate("Alpha", "Beta", fixture_id=1),
            _candidate("Gamma", "Delta", fixture_id=2),
        ],
    )

    with patch("upset_risk.DATA_DIR", tmp_path):
        success, summary = run_upset_risk(date, {})

    assert success is True
    assert "3 candidates scored" in summary
    saved = json.loads(s3_path.read_text(encoding="utf-8"))
    assert len(saved["analyses"]) == 3
    assert all("upset_risk" in candidate for candidate in saved["analyses"])
