"""Integration test: verify all 9 scrapers load, instantiate, and have correct interfaces."""
from __future__ import annotations

import pytest

from bet.scrapers import available_scrapers, get_scraper
from bet.scrapers.constants import SPORT_SOURCE_MAP


class TestScraperRegistry:
    def test_all_scrapers_registered(self):
        scrapers = available_scrapers()
        assert len(scrapers) == 14

    def test_sport_source_map_matches_registry(self):
        scrapers = available_scrapers()
        for sport, sources in SPORT_SOURCE_MAP.items():
            for source in sources:
                assert (sport, source) in scrapers, f"({sport}, {source}) missing from registry"

    @pytest.mark.parametrize("sport,source", list(available_scrapers().keys()))
    def test_scraper_loads(self, sport, source):
        cls = get_scraper(sport, source)
        assert cls is not None
        assert cls.sport == sport
        assert cls.source_name == source

    @pytest.mark.parametrize("sport,source", list(available_scrapers().keys()))
    def test_scraper_instantiates(self, sport, source, session_factory):
        cls = get_scraper(sport, source)
        scraper = cls(session_factory)
        assert hasattr(scraper, "scrape_team_season_stats")
        assert hasattr(scraper, "scrape_player_season_stats")
        assert callable(scraper.scrape_team_season_stats)
        assert callable(scraper.scrape_player_season_stats)

    def test_invalid_scraper_raises(self):
        with pytest.raises(ValueError, match="No scraper found"):
            get_scraper("cricket", "nonexistent")
