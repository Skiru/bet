"""Tests for fetch_odds_api_io.py — AGENT_SUMMARY output and error handling."""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def test_agent_summary_emitted_on_missing_key(capsys, monkeypatch):
    """Script should emit AGENT_SUMMARY with FAILED verdict when API key is missing."""
    mock_client = MagicMock()
    mock_client.is_available.return_value = False

    with patch("fetch_odds_api_io.OddsAPIioClient", return_value=mock_client), \
         pytest.raises(SystemExit) as exc_info:
        monkeypatch.setattr(
            "sys.argv",
            ["fetch_odds_api_io.py", "--date", "2026-05-14", "--verbose"],
        )
        from fetch_odds_api_io import main
        main()

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "AGENT_SUMMARY:" in captured.out


def test_agent_summary_ok_on_success(capsys, monkeypatch):
    """Script should emit AGENT_SUMMARY with OK verdict on successful scan."""
    mock_client = MagicMock()
    mock_client.is_available.return_value = True

    fake_snapshot = {
        "total_events_with_odds": 42,
        "total_value_bets": 5,
        "events": [
            {"_our_sport": "football", "home": "A", "away": "B"},
            {"_our_sport": "basketball", "home": "C", "away": "D"},
        ],
        "value_bets": [],
    }

    with patch("fetch_odds_api_io.OddsAPIioClient", return_value=mock_client), \
         patch("fetch_odds_api_io.fetch_odds_snapshot", return_value=fake_snapshot), \
         patch("fetch_odds_api_io._persist_io_odds_to_db"):
        monkeypatch.setattr(
            "sys.argv",
            ["fetch_odds_api_io.py", "--date", "2026-05-14", "--verbose"],
        )
        from fetch_odds_api_io import main
        main()

    captured = capsys.readouterr()
    assert "AGENT_SUMMARY:" in captured.out
    assert '"verdict": "OK"' in captured.out or '"verdict":"OK"' in captured.out
