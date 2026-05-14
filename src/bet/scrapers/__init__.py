from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bet.scrapers.base import BaseScraper

# Lazy registry: (sport, source) → (module_path, class_name)
_SCRAPER_REGISTRY: dict[tuple[str, str], tuple[str, str]] = {
    ("football", "fbref"): ("bet.scrapers.football.fbref", "FootballFBrefScraper"),
    ("basketball", "nba-api"): ("bet.scrapers.basketball.nba_api_scraper", "BasketballNBAScraper"),
    ("basketball", "basketball-reference"): ("bet.scrapers.basketball.bball_ref", "BasketballBRefScraper"),
    ("tennis", "sackmann"): ("bet.scrapers.tennis.sackmann", "TennisSackmannScraper"),
    ("tennis", "sofascore-tennis"): ("bet.scrapers.tennis.sofascore_tennis", "TennisSofascoreScraper"),
    ("hockey", "nhl-api"): ("bet.scrapers.hockey.nhl_api", "HockeyNHLScraper"),
    ("hockey", "hockey-reference"): ("bet.scrapers.hockey.hockey_ref", "HockeyRefScraper"),
    ("volleyball", "volleybox"): ("bet.scrapers.volleyball.volleybox", "VolleyboxScraper"),
    ("volleyball", "sofascore-volleyball"): ("bet.scrapers.volleyball.sofascore_volley", "VolleySofascoreScraper"),
    # ESPN — multi-sport universal API (free, no key)
    ("football", "espn"): ("bet.scrapers.espn", "FootballESPNScraper"),
    ("basketball", "espn"): ("bet.scrapers.espn", "BasketballESPNScraper"),
    ("hockey", "espn"): ("bet.scrapers.espn", "HockeyESPNScraper"),
    ("tennis", "espn"): ("bet.scrapers.espn", "TennisESPNScraper"),
    ("volleyball", "espn"): ("bet.scrapers.espn", "VolleyballESPNScraper"),
    # Flashscore — multi-sport via curl_cffi
    ("football", "flashscore"): ("bet.scrapers.flashscore", "FootballFlashscoreScraper"),
    ("basketball", "flashscore"): ("bet.scrapers.flashscore", "BasketballFlashscoreScraper"),
    ("tennis", "flashscore"): ("bet.scrapers.flashscore", "TennisFlashscoreScraper"),
    ("hockey", "flashscore"): ("bet.scrapers.flashscore", "HockeyFlashscoreScraper"),
    ("volleyball", "flashscore"): ("bet.scrapers.flashscore", "VolleyballFlashscoreScraper"),
}


def available_scrapers() -> dict[tuple[str, str], str]:
    """Return available scrapers mapped by (sport, source) → class name."""
    return {k: v[1] for k, v in _SCRAPER_REGISTRY.items()}


def get_scraper(sport: str, source: str) -> type[BaseScraper]:
    """Factory to get the right scraper class (lazy import)."""
    try:
        module_path, class_name = _SCRAPER_REGISTRY[(sport, source)]
    except KeyError as e:
        raise ValueError(f"No scraper found for sport='{sport}', source='{source}'") from e
    mod = importlib.import_module(module_path)
    return getattr(mod, class_name)
