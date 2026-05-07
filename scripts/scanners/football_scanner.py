"""Football scanner module."""
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BASE.parent / "src"))

try:
    from .base_scanner import BaseSportScanner
    from . import register_scanner
except ImportError:
    from scanners.base_scanner import BaseSportScanner
    from scanners import register_scanner


class FootballScanner(BaseSportScanner):
    """Football-specific scanner — Tier 1 sport, broadest coverage."""

    def __init__(self):
        self._extra_urls: list[str] = []

    @property
    def sport_name(self) -> str:
        return "football"

    @property
    def scanner_group(self) -> str:
        return "football"

    @property
    def urls(self) -> list[str]:
        return [
            # FlashScore — top leagues + Poland deep
            "https://www.flashscore.com/football/poland/",
            "https://www.flashscore.com/football/poland/ekstraklasa/",
            "https://www.flashscore.com/football/poland/division-1/",
            "https://www.flashscore.com/football/poland/division-2/",
            "https://www.flashscore.com/football/poland/polish-cup/",
            "https://www.flashscore.com/football/england/premier-league/",
            "https://www.flashscore.com/football/spain/laliga/",
            "https://www.flashscore.com/football/germany/bundesliga/",
            "https://www.flashscore.com/football/italy/serie-a/",
            "https://www.flashscore.com/football/france/ligue-1/",
            "https://www.flashscore.com/football/romania/",
            "https://www.flashscore.com/football/serbia/",
            "https://www.flashscore.com/football/croatia/",
            "https://www.flashscore.com/football/hungary/",
            "https://www.flashscore.com/football/czech-republic/",
            "https://www.flashscore.com/football/slovakia/",
            "https://www.flashscore.com/football/ukraine/",
            "https://www.flashscore.com/football/bulgaria/",
            "https://www.flashscore.com/football/cyprus/",
            "https://www.flashscore.com/football/iceland/",
            "https://www.flashscore.com/football/finland/",
            "https://www.flashscore.com/football/norway/",
            "https://www.flashscore.com/football/sweden/",
            "https://www.flashscore.com/football/denmark/",
            "https://www.flashscore.com/football/switzerland/",
            "https://www.flashscore.com/football/austria/",
            "https://www.flashscore.com/football/greece/",
            "https://www.flashscore.com/football/scotland/",
            "https://www.flashscore.com/football/belgium/",
            "https://www.flashscore.com/football/netherlands/",
            "https://www.flashscore.com/football/turkey/",
            "https://www.flashscore.com/football/england/championship/",
            "https://www.flashscore.com/football/england/league-one/",
            "https://www.flashscore.com/football/germany/2-bundesliga/",
            "https://www.flashscore.com/football/italy/serie-b/",
            "https://www.flashscore.com/football/france/ligue-2/",
            "https://www.flashscore.com/football/spain/laliga2/",
            "https://www.flashscore.com/football/portugal/",
            "https://www.flashscore.com/football/brazil/",
            "https://www.flashscore.com/football/brazil/serie-a/",
            "https://www.flashscore.com/football/argentina/",
            "https://www.flashscore.com/football/argentina/liga-profesional/",
            "https://www.flashscore.com/football/uruguay/",
            "https://www.flashscore.com/football/mexico/",
            "https://www.flashscore.com/football/usa/",
            "https://www.flashscore.com/football/usa/mls/",
            "https://www.flashscore.com/football/japan/",
            "https://www.flashscore.com/football/south-korea/",
            "https://www.flashscore.com/football/china/",
            "https://www.flashscore.com/football/indonesia/",
            "https://www.flashscore.com/football/australia/",
            "https://www.flashscore.com/football/south-africa/",
            # Betclic
            "https://www.betclic.pl/pilka-nozna-s1",
            # OddsPortal
            "https://www.oddsportal.com/football/",
            # BetExplorer
            "https://www.betexplorer.com/soccer/",
            # Stats sources
            "https://www.soccerstats.com/",
            "https://totalcorner.com/match/today",
            "https://www.soccerway.com/",
            # Forebet
            "https://www.forebet.com/en/football-tips-and-predictions-for-today",
            # Scores24
            "https://scores24.live/en/soccer",
            # WhoScored
            "https://www.whoscored.com/Previews",
        ]

    @property
    def timeout_per_page(self) -> int:
        return 45

    @property
    def max_deep_links(self) -> int:
        return 50

    @property
    def required_stat_keys(self) -> list[str]:
        return ["corners", "fouls", "yellow_cards", "shots", "shots_on_target", "possession"]

    @property
    def min_expected_events(self) -> int:
        return 200

    def get_fallback_urls(self) -> list[str]:
        return [
            "https://totalcorner.com/",
            "https://www.flashscore.com/football/europe/champions-league-women/",
            "https://www.flashscore.com/football/england/wsl-women/",
        ]


register_scanner("football", FootballScanner)
