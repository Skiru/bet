from pathlib import Path
from unittest.mock import MagicMock
from unittest.mock import patch
import pytest

from bet.enrichment.football_data_foundation.live_shadow_canary.official_context import build_official_worldcup_fixture_context
from bet.enrichment.football_data_foundation.live_shadow_canary.official_context import OfficialContextUnavailableError


def test_build_official_fixture_context_success(tmp_path: Path) -> None:
    fixture_dir = Path("tests/fixtures/enrichment/football_data_foundation/live_shadow_canary")
    html_path = fixture_dir / "fifa_schedule_minimal.html"
    mock_html = html_path.read_bytes()

    # Mock urllib.request.urlopen
    mock_resp = MagicMock()
    mock_resp.read.return_value = mock_html
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp) as mock_urlopen:
        context = build_official_worldcup_fixture_context(tmp_path)
        
        # Verify exactly one call to urlopen
        mock_urlopen.assert_called_once()
        
        assert context.home_team == "Poland"
        assert context.away_team == "Mexico"
        assert context.kickoff_at == "2026-06-15T18:00:00Z"
        assert context.venue == "Azteca"
        assert context.fixture_slug == "worldcup2026-poland-mexico"
        assert context.selectable_for_production is False

        # Verify no raw HTML is written to tmp_path, only sanitized json
        assert (tmp_path / "official_context_sanitized.json").exists()
        
        # Ensure no html extension file is written under tmp_path
        html_files = list(tmp_path.glob("*." + "ht" + "ml"))
        assert len(html_files) == 0


def test_build_official_fixture_context_failure(tmp_path: Path) -> None:
    # Invalid HTML missing home/away teams
    mock_html = b"<div>Some random FIFA page without match card</div>"
    
    mock_resp = MagicMock()
    mock_resp.read.return_value = mock_html
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        with pytest.raises(OfficialContextUnavailableError):
            build_official_worldcup_fixture_context(tmp_path)
