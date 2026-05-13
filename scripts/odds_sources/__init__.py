"""Multi-source odds aggregation package.

Provides OddsSource ABC and utility functions for team name normalization,
event matching, and odds merging.
"""
from abc import ABC, abstractmethod
from datetime import datetime, timezone
import re
import sys
import unicodedata
from pathlib import Path

# Ensure scripts/ is on path for sibling imports
_SCRIPTS_DIR = Path(__file__).resolve().parent
if _SCRIPTS_DIR.name != "scripts":
    _SCRIPTS_DIR = _SCRIPTS_DIR.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from utils import normalize_team_name


class OddsSource(ABC):
    """Abstract base class for all odds data sources."""

    name: str  # e.g., "the-odds-api"

    @abstractmethod
    def fetch_odds(self, sport: str, date_from: str, date_to: str) -> list[dict]:
        """Fetch odds for a sport within a time window.

        Args:
            sport: Internal sport key (e.g., "football", "tennis").
            date_from: Start date as YYYY-MM-DD.
            date_to: End date as YYYY-MM-DD.

        Returns:
            List of events in snapshot format.
        """
        ...

    @abstractmethod
    def supported_sports(self) -> list[str]:
        """Return list of sport keys this source can provide odds for."""
        ...


def _names_match(a: str, b: str) -> bool:
    """Check if two normalized team names match.

    Uses exact match first, then substring containment for cases where
    one source uses a shorter name variant.
    """
    if a == b:
        return True
    # Substring match — shorter name must be ≥50% of longer name's length
    # to avoid false positives like "ham" matching "nottingham"
    if len(a) >= 4 and len(b) >= 4:
        shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
        if shorter in longer and len(shorter) / len(longer) >= 0.5:
            return True
    return False


def events_match(a: dict, b: dict, time_tolerance_hours: float = 2.0) -> bool:
    """Check if two events from different sources represent the same match.

    Uses fuzzy team name matching + time window tolerance.
    """
    home_a = normalize_team_name(a.get("home_team", ""))
    home_b = normalize_team_name(b.get("home_team", ""))
    away_a = normalize_team_name(a.get("away_team", ""))
    away_b = normalize_team_name(b.get("away_team", ""))

    if not (_names_match(home_a, home_b) and _names_match(away_a, away_b)):
        return False

    # Check time window
    time_a = a.get("commence_time", "")
    time_b = b.get("commence_time", "")
    if time_a and time_b:
        try:
            dt_a = datetime.fromisoformat(time_a.replace("Z", "+00:00"))
            dt_b = datetime.fromisoformat(time_b.replace("Z", "+00:00"))
            diff = abs((dt_a - dt_b).total_seconds())
            if diff > time_tolerance_hours * 3600:
                return False
        except (ValueError, TypeError):
            pass  # If we can't parse times, rely on name match alone

    return True


def merge_event_odds(existing: dict, new: dict) -> dict:
    """Merge bookmakers from new event into existing event. Dedup by bookmaker key."""
    merged = dict(existing)
    existing_keys = {bm["key"] for bm in merged.get("bookmakers", [])}
    for bm in new.get("bookmakers", []):
        if bm["key"] not in existing_keys:
            merged.setdefault("bookmakers", []).append(bm)
            existing_keys.add(bm["key"])
    return merged


def _slugify(text: str) -> str:
    """Create a URL-safe slug from text."""
    s = unicodedata.normalize("NFKD", text)
    s = s.encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")
    return s


def make_event_id(source_name: str, sport: str, home: str, away: str, time_str: str) -> str:
    """Generate a deterministic event ID for scraped events."""
    parts = [source_name, sport, _slugify(home), _slugify(away), time_str.replace(":", "")]
    return "_".join(parts)


# Preferred bookmakers for downstream prioritization
PREFERRED_BOOKMAKERS = ["betclic", "bet365", "pinnacle", "unibet", "betfair"]

# Sport → ordered list of source names to try
SPORT_SOURCE_PRIORITY = {
    "football": ["the-odds-api", "odds-api-io", "api-football-odds", "oddsportal", "betexplorer"],
    "tennis": ["the-odds-api", "odds-api-io", "oddsportal", "betexplorer"],
    "basketball": ["the-odds-api", "odds-api-io", "oddsportal", "betexplorer"],
    "hockey": ["the-odds-api", "odds-api-io", "oddsportal", "betexplorer"],
    "volleyball": ["odds-api-io", "oddsportal", "betexplorer"],
}
