"""Tests for build_shortlist module."""
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from build_shortlist import build_shortlist, write_shortlist_json, _score_event


# ---------------------------------------------------------------------------
# Shortlist output structure
# ---------------------------------------------------------------------------


def test_shortlist_output_has_required_keys():
    """Output JSON has `candidates` and `metadata`."""
    tmp = tempfile.mkdtemp()
    data_dir = Path(tmp)

    # Create minimal market matrix
    matrix = {
        "events": [
            {
                "sport": "football",
                "competition": "Premier League",
                "home_team": "Liverpool",
                "away_team": "Arsenal",
                "kickoff": "2099-01-01T15:00:00",
                "data_tier": "STATS_READY",
                "markets_available": ["corners", "fouls"],
                "source_count": 2,
            },
        ],
        "metadata": {"date": "2099-01-01"},
    }
    (data_dir / "market_matrix_2099-01-01.json").write_text(
        json.dumps(matrix), encoding="utf-8"
    )

    with patch("build_shortlist.DATA_DIR", data_dir):
        result = build_shortlist("2099-01-01", top_n=0, stats_first=True)

    assert isinstance(result, list)
    assert len(result) > 0

    # Write and verify JSON structure
    with patch("build_shortlist.DATA_DIR", data_dir):
        out_path = write_shortlist_json(
            [(10.0, result[0])] if isinstance(result[0], dict) else result[:1],
            "2099-01-01",
        )
    assert Path(out_path).exists()
    data = json.loads(Path(out_path).read_text(encoding="utf-8"))
    assert "candidates" in data
    assert "total_candidates" in data
    assert "date" in data
    assert "sports" in data

    import shutil
    shutil.rmtree(tmp)


# ---------------------------------------------------------------------------
# Tournament boost
# ---------------------------------------------------------------------------


def test_tournament_boost_applied():
    """Candidates with tournament keywords get score boost."""
    tournament_event = {
        "sport": "football",
        "competition": "FIFA World Cup 2026",
        "home_team": "Brazil",
        "away_team": "Germany",
        "kickoff": "2099-01-01T20:00:00",
        "data_tier": "STATS_READY",
        "markets_available": ["corners", "fouls", "goals"],
        "source_count": 3,
    }
    regular_event = {
        "sport": "football",
        "competition": "Polish Ekstraklasa",
        "home_team": "Legia",
        "away_team": "Lech",
        "kickoff": "2099-01-01T18:00:00",
        "data_tier": "STATS_READY",
        "markets_available": ["corners", "fouls", "goals"],
        "source_count": 3,
    }

    tipster_events: set[str] = set()
    tournament_score = _score_event(tournament_event, tipster_events)
    regular_score = _score_event(regular_event, tipster_events)

    # Tournament events should score higher due to competition tier boost
    assert tournament_score > regular_score
