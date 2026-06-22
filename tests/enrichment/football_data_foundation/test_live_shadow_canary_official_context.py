import os
from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch
import pytest

import bet.enrichment.football_data_foundation.live_shadow_canary.official_context as oc
from bet.enrichment.football_data_foundation.live_shadow_canary.official_context import build_official_worldcup_fixture_context
from bet.enrichment.football_data_foundation.live_shadow_canary.official_context import OfficialContextUnavailableError


def test_build_official_fixture_context_norway_senegal_success(tmp_path: Path) -> None:
    fixture_dir = Path("tests/fixtures/enrichment/football_data_foundation/live_shadow_canary")
    html_path = fixture_dir / "fifa_match_centre_norway_senegal.html"
    mock_html = html_path.read_bytes()

    # Mock urlopen
    mock_resp = MagicMock()
    mock_resp.read.return_value = mock_html
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        context = build_official_worldcup_fixture_context(tmp_path)
        
        mock_urlopen.assert_called_once()
        
        assert context.home_team == "Norway"
        assert context.away_team == "Senegal"
        assert context.match_id == "400021491"
        assert context.kickoff_at == "2026-06-22T20:00:00Z"
        assert context.venue == "Ullevaal Stadion"
        assert context.city == "Oslo"
        assert context.fixture_slug == "worldcup2026-norway-senegal"
        assert context.selectable_for_production is False

        # Verify only sanitized json is written to tmp_path, NO raw html is persisted
        assert (tmp_path / "official_context_sanitized.json").exists()
        assert len(list(tmp_path.glob("*.html"))) == 0


def test_build_official_fixture_context_non_fifa_rejected(tmp_path: Path) -> None:
    # Set non-FIFA URL
    with patch.dict(os.environ, {"FOOTBALL_ENRICHMENT_CANARY_OFFICIAL_MATCH_URL": "https://notfifa.com/en/match"}):
        with pytest.raises(OfficialContextUnavailableError) as exc_info:
            build_official_worldcup_fixture_context(tmp_path)
        assert "not start with an allowed official prefix" in str(exc_info.value)


def test_build_official_fixture_context_bs4_missing_fallback(tmp_path: Path) -> None:
    fixture_dir = Path("tests/fixtures/enrichment/football_data_foundation/live_shadow_canary")
    html_path = fixture_dir / "fifa_match_centre_norway_senegal.html"
    mock_html = html_path.read_bytes()

    mock_resp = MagicMock()
    mock_resp.read.return_value = mock_html
    mock_resp.__enter__.return_value = mock_resp

    # Temporarily set _HAS_BS4 to False to simulate BeautifulSoup missing
    with patch("urllib.request.urlopen", return_value=mock_resp):
        with patch.object(oc, "_HAS_BS4", False):
            context = build_official_worldcup_fixture_context(tmp_path)
            
            # Should fall back to stdlib HTMLParser and succeed!
            assert context.home_team == "Norway"
            assert context.away_team == "Senegal"
            assert context.match_id == "400021491"
            assert context.kickoff_at == "2026-06-22T20:00:00Z"
            assert context.venue == "Ullevaal Stadion"
            assert context.city == "Oslo"


def test_build_official_fixture_context_failure_does_not_fake(tmp_path: Path) -> None:
    # HTML missing metadata completely
    mock_html = b"<div>Completely un-related HTML data structure</div>"
    
    mock_resp = MagicMock()
    mock_resp.read.return_value = mock_html
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        with pytest.raises(OfficialContextUnavailableError):
            build_official_worldcup_fixture_context(tmp_path)


def test_build_official_fixture_context_poland_mexico_legacy(tmp_path: Path) -> None:
    fixture_dir = Path("tests/fixtures/enrichment/football_data_foundation/live_shadow_canary")
    html_path = fixture_dir / "fifa_schedule_minimal.html"
    mock_html = html_path.read_bytes()

    mock_resp = MagicMock()
    mock_resp.read.return_value = mock_html
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        context = build_official_worldcup_fixture_context(tmp_path)
        
        assert context.home_team == "Poland"
        assert context.away_team == "Mexico"
        assert context.kickoff_at == "2026-06-15T18:00:00Z"
        assert context.venue == "Azteca"
