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
from typing import Any

# Ensure scripts/ is on path for sibling imports
_SCRIPTS_DIR = Path(__file__).resolve().parent
if _SCRIPTS_DIR.name != "scripts":
    _SCRIPTS_DIR = _SCRIPTS_DIR.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from utils import normalize_team_name

try:
    from bet.odds_merge import merge_event_odds as _market_safe_merge_event_odds
except ImportError:
    _market_safe_merge_event_odds = None


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
    """Merge bookmaker odds without dropping additional markets from the same bookmaker."""
    try:
        from bet.odds_merge import merge_event_odds as _market_safe_merge_event_odds_runtime

        return _market_safe_merge_event_odds_runtime(existing, new)
    except ImportError:
        return _merge_event_odds_market_safe_fallback(existing, new)


def _merge_event_odds_market_safe_fallback(existing: dict, new: dict) -> dict:
    merged = dict(existing)
    merged_bookmakers = [
        _normalise_bookmaker(bookmaker) for bookmaker in list(existing.get("bookmakers", []) or [])
    ]
    bookmaker_index = {bookmaker["key"]: bookmaker for bookmaker in merged_bookmakers}

    for bookmaker in list(new.get("bookmakers", []) or []):
        normalised = _normalise_bookmaker(bookmaker)
        key = normalised["key"]
        if key not in bookmaker_index:
            bookmaker_index[key] = normalised
            merged_bookmakers.append(normalised)
            continue
        bookmaker_index[key]["markets"] = _fallback_merge_markets(
            bookmaker_index[key].get("markets", []),
            normalised.get("markets", []),
        )

    merged["bookmakers"] = merged_bookmakers
    return merged


def _normalise_bookmaker(bookmaker: dict[str, Any]) -> dict[str, Any]:
    normalised = dict(bookmaker)
    normalised["key"] = _slugify(str(bookmaker.get("key") or bookmaker.get("title") or ""))
    normalised["markets"] = _fallback_merge_markets([], list(bookmaker.get("markets", []) or []))
    return normalised


def _canonical_market_key(value: Any) -> str:
    raw = _slugify(str(value or ""))
    aliases = {
        "moneyline": "h2h",
        "match_winner": "h2h",
        "winner": "h2h",
        "1x2": "h2h",
        "h2h": "h2h",
        "over_under": "totals",
        "over_under_totals": "totals",
        "totals": "totals",
        "total": "totals",
        "overunder": "totals",
        "spreads": "spreads",
        "spread": "spreads",
        "handicap": "spreads",
    }
    return aliases.get(raw, raw)


def _fallback_merge_markets(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    market_index: dict[str, dict[str, Any]] = {}
    for market in list(left or []) + list(right or []):
        market_dict = dict(market)
        key = _canonical_market_key(market_dict.get("key") or market_dict.get("name"))
        if not key:
            continue
        if key not in market_index:
            market_index[key] = {**market_dict, "key": key, "outcomes": []}
            merged.append(market_index[key])
        market_index[key]["outcomes"] = _fallback_merge_outcomes(
            market_index[key].get("outcomes", []),
            list(market_dict.get("outcomes", []) or []),
        )
    return merged


def _fallback_merge_outcomes(left: list[dict[str, Any]], right: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: dict[tuple[str, str], int] = {}
    for outcome in list(left or []) + list(right or []):
        outcome_dict = dict(outcome)
        name = _slugify(str(outcome_dict.get("name") or outcome_dict.get("label") or ""))
        point = str(outcome_dict.get("point", ""))
        if not name:
            continue
        dedupe_key = (name, point)
        if dedupe_key in seen:
            merged[seen[dedupe_key]] = outcome_dict
            continue
        seen[dedupe_key] = len(merged)
        merged.append(outcome_dict)
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
PREFERRED_BOOKMAKERS = [
    "superbet.pl",
    "superbet",
    "superbet_pl",
    "superbet-pl",
    "betclic_fr",
    "betclic",
    "betclic_pl",
    "bet365",
    "pinnacle",
    "unibet",
    "betfair",
]

# Sport → ordered list of source names to try
SPORT_SOURCE_PRIORITY = {
    "football": ["oddspapi", "the-odds-api-betclic", "odds-api-io", "the-odds-api", "api-football-odds"],
    "tennis": ["oddspapi", "the-odds-api-betclic", "odds-api-io", "the-odds-api"],
    "basketball": ["oddspapi", "the-odds-api-betclic", "odds-api-io", "the-odds-api"],
    "hockey": ["oddspapi", "the-odds-api-betclic", "odds-api-io", "the-odds-api"],
    "volleyball": ["oddspapi", "odds-api-io"],
    "cs2": ["oddspapi", "odds-api-io"],
    "dota2": ["oddspapi", "odds-api-io"],
    "valorant": ["oddspapi", "odds-api-io"],
}
