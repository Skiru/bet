#!/usr/bin/env python3
"""Tipster Aggregator — parallel fetch, parse, and consensus scoring from all tipster sites.

Fetches today's picks from ALL configured tipster sites in parallel using
ThreadPoolExecutor, parses structured picks (sport, event, market, odds,
reasoning, accuracy), computes consensus, and combines tipster arguments
with statistical calculations.

Sites covered:
  Polish: ZawodTyper, Typersi, Meczyki
  English: OLBG, PicksWise, BetIdeas, Sportsgambler, Tipstrr
  Exotic: Feedinco, BettingClosed, Tips180
  Esports: GosuGamers

Usage:
    python3 scripts/tipster_aggregator.py --date 2026-05-04
    python3 scripts/tipster_aggregator.py --date 2026-05-04 --workers 8
    python3 scripts/tipster_aggregator.py --date 2026-05-04 --sport football
"""

import argparse
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "betting" / "data"

sys.path.insert(0, str(SCRIPTS_DIR))
sys.path.insert(0, str(ROOT_DIR / "src"))

import requests as _requests

def fetch(url: str, **kwargs) -> str:
    """HTTP fetch for tipster pages (no Playwright)."""
    resp = _requests.get(url, timeout=30, headers={
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })
    resp.raise_for_status()
    return resp.text

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class TipsterPick:
    """A single tipster pick with reasoning."""
    source_site: str
    tipster_name: str
    sport: str
    event: str  # "Team A vs Team B"
    home_team: str
    away_team: str
    competition: str
    market: str  # e.g., "Corners O9.5", "Over 22.5 games"
    market_type: str  # "statistical" or "outcome"
    direction: str  # "OVER", "UNDER", "WIN", "DRAW", etc.
    odds: float | None
    reasoning: str  # Full tipster reasoning/argument
    accuracy_pct: float | None  # Tipster tracked accuracy
    confidence: str  # "high", "medium", "low"
    stats_cited: list[str] = field(default_factory=list)  # Specific stats mentioned
    fetch_time: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TipsterConsensus:
    """Consensus result for an event across tipsters."""
    event: str
    sport: str
    competition: str
    home_team: str
    away_team: str
    total_tipsters: int
    picks: list[TipsterPick]
    consensus_market: str | None  # Most agreed-upon market
    consensus_direction: str | None
    agreement_pct: float  # % of tipsters agreeing
    statistical_picks_count: int  # How many target statistical markets
    has_reasoning: bool  # At least 1 tipster gave reasoning


# ---------------------------------------------------------------------------
# Polish month/weekday names for ZawodTyper URL construction
# ---------------------------------------------------------------------------

POLISH_MONTHS = {
    1: "stycznia", 2: "lutego", 3: "marca", 4: "kwietnia",
    5: "maja", 6: "czerwca", 7: "lipca", 8: "sierpnia",
    9: "wrzesnia", 10: "pazdziernika", 11: "listopada", 12: "grudnia",
}

POLISH_WEEKDAYS = {
    0: "poniedzialek", 1: "wtorek", 2: "sroda", 3: "czwartek",
    4: "piatek", 5: "sobota", 6: "niedziela",
}

# Market type classification
STATISTICAL_MARKETS = {
    "corners", "corner", "rzuty rożne", "rożne", "ck",
    "fouls", "foul", "faule",
    "cards", "card", "kartki", "żółte",
    "shots", "shot", "strzały",
    "games", "game", "gemy",
    "sets", "set", "sety",
    "frames", "frame", "frejmy",
    "points", "point", "punkty",
    "180s", "legs", "legi",
    "aces", "ace", "asy",
    "rebounds", "rebound", "zbiórki",
    "totals", "total", "łącznie",
    "over", "under", "powyżej", "poniżej",
    "handicap",
    # Hockey statistical markets
    "power play", "powerplay", "pp", "penalty minutes", "pim",
    "face-off", "faceoff", "puck line",
    # Volleyball statistical markets
    "blocks", "block", "digs", "dig", "spikes", "spike",
    "serve", "rallies", "rally",
    # Basketball statistical markets
    "assists", "assist", "steals", "steal",
    "turnovers", "turnover", "free throws", "three-pointers", "3-pointers",
    # Tennis statistical markets
    "double faults", "break points", "first serve",
}

OUTCOME_MARKETS = {
    "winner", "zwycięzca", "1x2", "ml", "moneyline", "money line",
    "draw", "remis", "btts", "obie strzelą", "both teams to score",
    "double chance", "podwójna szansa",
    "draw no bet", "dnb",
}


# ---------------------------------------------------------------------------
# Site configurations
# ---------------------------------------------------------------------------

TIPSTER_SITES = [
    {
        "name": "ZawodTyper",
        "url_template": "https://www.zawodtyper.pl/typy-dnia-{day}-{month}-{weekday}/",
        "url_builder": "zawodtyper",
        "language": "pl",
        "parser": "zawodtyper",
        "sports": ["football", "tennis", "basketball", "volleyball", "hockey"],
        "accuracy_tracked": True,
        "wait_after_load": 3000,
    },
    {
        "name": "Typersi",
        "url": "https://typersi.pl/",
        "language": "pl",
        "parser": "typersi",
        "sports": ["football", "tennis", "basketball", "volleyball", "hockey"],
        "accuracy_tracked": False,
        "wait_after_load": 3000,
    },
    {
        "name": "Sportsgambler",
        "url": "https://www.sportsgambler.com/predictions/today/",
        "language": "en",
        "parser": "sportsgambler",
        "sports": ["football", "tennis", "basketball", "hockey", "volleyball"],
        "accuracy_tracked": False,
    },
    {
        "name": "PicksWise",
        "urls": [
            "https://www.pickswise.com/soccer/predictions/",
            "https://www.pickswise.com/tennis/predictions/",
            "https://www.pickswise.com/nba/predictions/",
            "https://www.pickswise.com/nhl/predictions/",
            "https://www.pickswise.com/volleyball/predictions/",
        ],
        "language": "en",
        "parser": "pickswise",
        "sports": ["football", "tennis", "basketball", "hockey", "volleyball"],
        "accuracy_tracked": True,
    },
    {
        "name": "BetIdeas",
        "urls": [
            "https://www.betideas.com/tips/football",
            "https://www.betideas.com/tips/tennis",
            "https://www.betideas.com/tips/basketball",
            "https://www.betideas.com/tips/hockey",
            "https://www.betideas.com/tips/volleyball",
        ],
        "language": "en",
        "parser": "betideas",
        "sports": ["football", "tennis", "basketball", "hockey", "volleyball"],
        "accuracy_tracked": True,
    },
    {
        "name": "OLBG",
        "url": "https://www.olbg.com/tips",
        "language": "en",
        "parser": "olbg",
        "sports": ["football", "tennis", "basketball", "hockey", "volleyball"],
        "accuracy_tracked": True,
    },
    {
        "name": "Tipstrr",
        "url": "https://www.tipstrr.com/tips",
        "language": "en",
        "parser": "tipstrr",
        "sports": ["football", "tennis", "basketball", "volleyball", "hockey"],
        "accuracy_tracked": True,
    },
    {
        "name": "Feedinco",
        "url": "https://www.feedinco.com/",
        "language": "en",
        "parser": "feedinco",
        "sports": ["football", "tennis", "basketball", "volleyball", "hockey"],
        "accuracy_tracked": False,
    },
    {
        "name": "BettingClosed",
        "url": "https://www.bettingclosed.com/",
        "language": "en",
        "parser": "bettingclosed",
        "sports": ["football", "tennis", "basketball", "volleyball", "hockey"],
        "accuracy_tracked": False,
    },
    {
        "name": "Tips180",
        "url": "https://tips180.com/",
        "language": "en",
        "parser": "tips180",
        "sports": ["football", "tennis", "basketball", "volleyball", "hockey"],
        "accuracy_tracked": False,
    },
]


# ---------------------------------------------------------------------------
# URL builders
# ---------------------------------------------------------------------------

def build_zawodtyper_url(date: datetime) -> str:
    """Build ZawodTyper daily URL with Polish month/weekday names."""
    day = date.day
    month = POLISH_MONTHS.get(date.month, "")
    weekday = POLISH_WEEKDAYS.get(date.weekday(), "")
    return f"https://www.zawodtyper.pl/typy-dnia-{day}-{month}-{weekday}/"


# ---------------------------------------------------------------------------
# Garbage filters — reject false positive event matches
# ---------------------------------------------------------------------------

GARBAGE_WORDS = {
    "prediction", "predictions", "betting", "tips", "picks", "odds",
    "livescore", "flashscore", "tomorrow", "yesterday", "today",
    "premier league", "championship", "la liga", "serie a", "bundesliga",
    "ligue 1", "champions league", "europa league", "nfl", "nba", "nhl",
    "total odds", "free tips", "best bets", "accumulator", "acca",
    "registration", "login", "sign up", "join now", "bonus", "promo",
    "cookie", "privacy", "terms", "contact", "about us", "faq",
    "zawód typer", "największa społeczność", "wydarzenie",
    "april dot balls", "boundaries", "football match",
    "latest betting tips", "world crypto",
    "latest betting", "latest tips", "latest predictions",
    "april latest betting",
}

# Words to strip from captured team names (suffixes, longest first)
TEAM_NAME_STRIP_WORDS = [
    "bet tip on", "bet tip",
    "tips", "tip", "prediction", "predictions", "odds",
    "bet",
]

# League abbreviation prefixes to strip
LEAGUE_PREFIXES = {
    "epl", "fra", "ita", "esp", "ger", "neth", "por", "sco",
    "bel", "tur", "gre", "sui", "aut", "nor", "swe", "den",
    "fin", "la liga", "serie a",
}

# Two-word league prefixes that need special handling
TWO_WORD_PREFIXES = ["la liga", "serie a"]

GARBAGE_TEAM_NAMES = {
    "prediction", "predictions", "betting", "tips", "bet", "vs",
    "free", "today", "tomorrow", "yesterday", "home", "away",
    "livescore", "flashscore", "score", "total", "odds",
    "mls", "nba", "nhl", "nfl", "afl", "usa",
    "fc usa", "mls v",
    "page not found", "betideas", "view predict",
}

# Regex for trailing prediction codes (X2, 1X, O1.5, U2.5, O, X, etc.)
_PRED_CODE_RE = re.compile(r'\s+(?:[12X]{1,2}|[OU]\d*\.?\d*|GG|NG|BTTS)\s*$', re.IGNORECASE)


def _is_garbage_event(home: str, away: str, block: str = "") -> bool:
    """Check if an extracted event is likely garbage (navigation, headers, etc.)."""
    h = home.strip().lower()
    a = away.strip().lower()

    # Too short team names
    if len(h) < 3 or len(a) < 3:
        return True

    # Team name IS a garbage word
    if h in GARBAGE_TEAM_NAMES or a in GARBAGE_TEAM_NAMES:
        return True

    # Event text matches garbage patterns (whole-word match for short words)
    event_text = f"{h} vs {a}"
    for gw in GARBAGE_WORDS:
        if len(gw) <= 5:
            # Short words need word-boundary check to avoid "bet" matching "Betis"
            if re.search(r'\b' + re.escape(gw) + r'\b', event_text):
                return True
        else:
            if gw in event_text:
                return True

    # Contains garbage words as the entire team name
    if h in GARBAGE_WORDS or a in GARBAGE_WORDS:
        return True

    # Contains newlines or tabs (HTML artifact)
    if "\n" in home or "\n" in away or "\t" in home or "\t" in away:
        return True

    # Very long team names are likely paragraphs
    if len(home) > 40 or len(away) > 40:
        return True

    # Team name contains "View Predict" or "View Tips" (BetIdeas listing artifacts)
    for part in (h, a):
        if "view predict" in part or "view tips" in part or "page not found" in part:
            return True
        # Contains promo/article language
        if any(x in part for x in ["betting site", "bookmaker", "telegram", "fanpage",
                                    "guide", "reviews", "advice", "service",
                                    "previews", "incredibly", "free prediction",
                                    "prediction site", "worrying", "this guide"]):
            return True

    # Team name contains country + league pattern (e.g., "Spain LaLiga")
    if re.search(r'\b(?:spain|england|germany|italy|france|portugal|scotland|netherlands)\b', a) and re.search(r'(?:liga|league|premier|division|serie)', a):
        return True

    # Team name looks like a sentence/description (common in BetIdeas tipster profiles)
    _SENTENCE_WORDS = {"the", "with", "behind", "just", "this", "has", "can", "not",
                       "all", "hit", "man", "turns", "expert", "insiders", "jackpot",
                       "goldmine", "bookie", "club", "deliver", "profits", "account",
                       "accurate", "excellent", "website", "top", "big", "at",
                       "their", "our", "your", "his", "her", "its", "from"}
    for part in (h, a):
        words = part.split()
        if len(words) >= 3 and sum(1 for w in words if w in _SENTENCE_WORDS) >= 2:
            return True
        # Single-word team name that's a common English word (not a team name)
        if len(words) == 1 and part in {"turns", "top", "website", "cash",
                                         "deliver", "excellent", "accurate",
                                         "dimers", "profits"}:
            return True

    return False


def _clean_team_name(name: str) -> str:
    """Clean up a captured team name by removing common artifacts.

    Strips league abbreviation prefixes (EPL, FRA, etc.) and
    navigation suffixes (Tips, Bet tip on, etc.).
    """
    cleaned = name.strip()

    # Strip trailing prediction codes (e.g., "Aston Villa X2" → "Aston Villa")
    cleaned = _PRED_CODE_RE.sub('', cleaned).strip()

    # Strip league prefix (e.g., "EPL Burnley" → "Burnley")
    # Check two-word prefixes first
    lower_cleaned = cleaned.lower()
    for prefix in TWO_WORD_PREFIXES:
        if lower_cleaned.startswith(prefix + " "):
            cleaned = cleaned[len(prefix):].strip()
            break
    else:
        parts = cleaned.split()
        if len(parts) >= 2 and parts[0].lower() in LEAGUE_PREFIXES:
            cleaned = " ".join(parts[1:])

    # Strip suffixes iteratively (e.g., "Aston Villa Bet tip on Odds" → "Aston Villa")
    changed = True
    while changed:
        changed = False
        lower = cleaned.lower()
        for suffix in TEAM_NAME_STRIP_WORDS:  # Already ordered longest-first
            if lower.endswith(" " + suffix) or lower == suffix:
                cleaned = cleaned[:len(cleaned) - len(suffix)].strip()
                changed = True
                break
        # Also strip trailing "Odds"
        if cleaned.lower().endswith(" odds"):
            cleaned = cleaned[:-5].strip()
            changed = True

    # Strip "Tips Country" suffix (e.g., "Zurich Tips Switzerland" → "Zurich")
    tips_match = re.search(r'\s+Tips?\s+\w+$', cleaned, re.IGNORECASE)
    if tips_match:
        cleaned = cleaned[:tips_match.start()].strip()

    # Strip trailing "Odds" word
    if cleaned.lower().endswith(" odds"):
        cleaned = cleaned[:-5].strip()

    return cleaned


# ---------------------------------------------------------------------------
# HTML parsers — extract structured picks from fetched HTML
# ---------------------------------------------------------------------------

def classify_market(market_text: str, context: str = "") -> str:
    """Classify market as 'statistical' or 'outcome'.

    Priority: market text takes precedence over context.
    Outcome keywords checked first on market text to prevent context pollution
    (e.g. 'over' in context shouldn't override 'Double Chance' in market).
    """
    market_lower = market_text.lower()

    # 1. Check market text for explicit outcome keywords first
    for keyword in OUTCOME_MARKETS:
        if keyword in market_lower:
            return "outcome"

    # 2. Check market text for statistical keywords
    for keyword in STATISTICAL_MARKETS:
        if keyword in market_lower:
            return "statistical"

    # 3. Only use context when market is N/A or empty
    if market_text in ("N/A", "") and context:
        ctx_lower = context.lower()
        for keyword in STATISTICAL_MARKETS:
            if keyword in ctx_lower:
                return "statistical"

    return "outcome"


def extract_direction(market_text: str, context: str = "") -> str:
    """Extract direction from market text, with optional context fallback."""
    combined = (market_text + " " + context).lower()
    if any(w in combined for w in ["over", "powyżej", "więcej"]):
        return "OVER"
    if any(w in combined for w in ["under", "poniżej", "mniej"]):
        return "UNDER"
    if any(w in combined for w in ["btts", "both teams to score", "obie strzelą"]):
        return "BTTS"
    if any(w in combined for w in ["double chance", "podwójna szansa", "win or tie", "win or draw"]):
        return "DC"
    if any(w in combined for w in ["draw no bet", "dnb"]):
        return "DNB"
    if any(w in combined for w in [" win", "wygra", "zwycięstwo", "moneyline"]):
        return "WIN"
    if any(w in combined for w in ["draw", "remis"]):
        return "DRAW"
    return "OTHER"


def extract_odds_from_text(text: str) -> float | None:
    """Extract decimal odds from text like 'kurs 1.85' or '@1.85' or '1.85'.

    Also handles American odds: '+130' → 2.30, '-150' → 1.67.
    """
    patterns = [
        r'@\s*(\d+\.\d+)',
        r'kurs\s*[:=]?\s*(\d+\.\d+)',
        r'odds?\s*[:=]?\s*(\d+\.\d+)',
        r'\b(\d+\.\d{2})\b',
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            val = float(match.group(1))
            if 1.01 <= val <= 100.0:
                return val

    # American odds in parentheses: (+130), (-150)
    american_match = re.search(r'\(([+-]\d{3,4})\)', text)
    if american_match:
        american = int(american_match.group(1))
        if american > 0:
            return round(1 + american / 100, 2)
        elif american < 0:
            return round(1 + 100 / abs(american), 2)

    return None


def extract_accuracy_from_text(text: str) -> float | None:
    """Extract accuracy percentage from text like '73%' or 'skuteczność: 73%'."""
    patterns = [
        r'(\d{1,3})\s*%',
        r'skuteczność\s*[:=]?\s*(\d{1,3})',
        r'accuracy\s*[:=]?\s*(\d{1,3})',
        r'hit\s*rate\s*[:=]?\s*(\d{1,3})',
        r'(\d{1,3})\s*/\s*\d+',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            val = float(match.group(1))
            if 0 < val <= 100:
                return val
    return None


def extract_stats_cited(text: str) -> list[str]:
    """Extract specific statistics cited in tipster reasoning."""
    stats = []
    patterns = [
        r'(\d+\.?\d*)\s*(?:corners?|ck|rożn)',
        r'(\d+\.?\d*)\s*(?:fouls?|faul)',
        r'(\d+\.?\d*)\s*(?:cards?|kart)',
        r'(\d+\.?\d*)\s*(?:shots?|strzał)',
        r'(\d+\.?\d*)\s*(?:games?|gem)',
        r'(\d+\.?\d*)\s*(?:sets?|set)',
        r'(\d+\.?\d*)\s*(?:points?|punkt)',
        r'(\d+\.?\d*)\s*(?:frames?|frejm)',
        r'(\d+/\d+)\s*(?:meczów|matches|games)',
        r'średni[ao]?\s*[:=]?\s*(\d+\.?\d*)',
        r'average\s*[:=]?\s*(\d+\.?\d*)',
        r'last\s*\d+\s*[:=]?\s*(\d+\.?\d*)',
    ]
    for pattern in patterns:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for m in matches:
            stats.append(m if isinstance(m, str) else str(m))
    return stats[:10]  # Cap at 10


def detect_sport(text: str, url: str = "") -> str:
    """Detect sport from text content and URL."""
    combined = (text + " " + url).lower()
    sport_keywords = {
        "tennis": ["tennis", "tenis", "atp", "wta", "roland", "wimbledon", "grand slam",
                    "challenger", "itf", "davis cup", "billie jean king",
                    "przełamań", "przełamanie", "gemów", "gem", "setów",
                    "break point", "double fault"],
        "basketball": ["basketball", "koszykówka", "nba", "euroleague", "plk", "ncaa",
                        "fiba", "acb", "bbl", "lnb", "nbl"],
        "volleyball": ["volleyball", "siatkówka", "plusliga", "superlega",
                        "siatk", "v-league", "serie a volley", "ligue a", "efeler",
                        "mestaruusliiga", "eredivisie volley", "bundesliga volley"],
        "hockey": ["hockey", "hokej", "nhl", "khl",
                    "shl", "liiga", "extraliga", "allsvenskan", "mestis", "eihl", "del"],
    }
    for sport, keywords in sport_keywords.items():
        for kw in keywords:
            if kw in combined:
                return sport
    # Check URL path for sport hints
    if "/soccer/" in url or "/football/" in url or "/futbol/" in url:
        return "football"
    if "/tennis/" in url:
        return "tennis"
    if "/nba/" in url or "/basketball/" in url:
        return "basketball"
    if "/nhl/" in url or "/hockey/" in url:
        return "hockey"
    return "football"


def _extract_market_from_text(text: str) -> str:
    """Extract market from surrounding text using multiple patterns.

    Returns the best market string found, or 'N/A' if nothing detected.
    """
    patterns = [
        # Corners / Cards / Fouls / Shots with Over/Under
        (r'(?:corners?|ck|rożn\w*)\s*(?:over|under|o|u)\s*(\d+\.?\d*)', lambda m: f"Corners {m.group(0).strip()}"),
        (r'(?:over|under|o|u)\s*(\d+\.?\d*)\s*(?:corners?|ck|rożn\w*)', lambda m: f"Corners {m.group(0).strip()}"),
        (r'(?:cards?|kart\w*|yellow)\s*(?:over|under|o|u)\s*(\d+\.?\d*)', lambda m: f"Cards {m.group(0).strip()}"),
        (r'(?:over|under|o|u)\s*(\d+\.?\d*)\s*(?:cards?|kart\w*)', lambda m: f"Cards {m.group(0).strip()}"),
        (r'(?:fouls?|faul\w*)\s*(?:over|under|o|u)\s*(\d+\.?\d*)', lambda m: f"Fouls {m.group(0).strip()}"),
        (r'(?:shots?\s*(?:on\s*target)?)\s*(?:over|under|o|u)\s*(\d+\.?\d*)', lambda m: f"Shots {m.group(0).strip()}"),
        # Games / Sets / Points (tennis, volleyball, basketball)
        (r'(?:total\s*)?(?:games?|gemy?)\s*(?:over|under|o|u)\s*(\d+\.?\d*)', lambda m: f"Games {m.group(0).strip()}"),
        (r'(?:over|under|o|u)\s*(\d+\.?\d*)\s*(?:total\s*)?(?:games?|gemy?)', lambda m: f"Games {m.group(0).strip()}"),
        (r'(?:total\s*)?(?:sets?|sety?)\s*(?:over|under|o|u)\s*(\d+\.?\d*)', lambda m: f"Sets {m.group(0).strip()}"),
        (r'(?:total\s*)?(?:points?|punkt\w*)\s*(?:over|under|o|u)\s*(\d+\.?\d*)', lambda m: f"Points {m.group(0).strip()}"),
        # Generic Over/Under with number (goals, total)
        (r'(?:over|powyżej)\s+(\d+\.?\d+)\s*(?:goals?|gol\w*|bramk\w*)?', lambda m: f"Over {m.group(1)}"),
        (r'(?:under|poniżej)\s+(\d+\.?\d+)\s*(?:goals?|gol\w*|bramk\w*)?', lambda m: f"Under {m.group(1)}"),
        # BTTS
        (r'(?:btts|both\s*teams?\s*(?:to\s*)?score|obie\s*strzela?ą?)', lambda m: "BTTS"),
        # Double Chance
        (r'(?:double\s*chance|podwójna\s*szansa|1x|x2)', lambda m: f"Double Chance {m.group(0).strip()}"),
        # Draw No Bet
        (r'(?:draw\s*no\s*bet|dnb)', lambda m: "Draw No Bet"),
        # Handicap
        (r'(?:handicap|hc)\s*[+-]?\s*(\d+\.?\d*)', lambda m: f"Handicap {m.group(0).strip()}"),
        # Winner / ML
        (r'(?:to\s*win|winner|zwycięzca|wygra)', lambda m: f"Winner {m.group(0).strip()}"),
    ]

    text_lower = text.lower()
    for pattern, formatter in patterns:
        match = re.search(pattern, text_lower, re.IGNORECASE)
        if match:
            return formatter(match)

    return "N/A"


def parse_generic_tipster_html(html: str, site_name: str, url: str) -> list[TipsterPick]:
    """Generic HTML parser that extracts tipster picks using common patterns.

    This handles the majority of tipster sites that follow similar HTML structures.
    Works as a fallback when no site-specific parser is available.
    Applies garbage filters to reject false positive matches.
    """
    picks = []
    now_iso = datetime.now(timezone.utc).isoformat()

    # Strip HTML tags but preserve line breaks from block elements
    text = re.sub(r'<(?:br|hr|/p|/div|/li|/tr|/td|/th|/h[1-6])[^>]*>', '\n', html, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    # Collapse all whitespace to single spaces for reliable regex matching
    # (newlines in team names cause false garbage filter rejections)
    text = re.sub(r'\s+', ' ', text)

    # Split into potential prediction blocks — look for "vs" or " - " patterns
    # More selective: require at least one capitalized word on each side
    event_pattern = re.compile(
        r'([A-ZÀ-Ž][A-Za-zÀ-ž\.]+(?:\s+[A-Za-zÀ-ž\.]+){0,4}?)'
        r'\s+(?:vs\.?|v\.?|[-–—]|@)\s+'
        r'([A-ZÀ-Ž][A-Za-zÀ-ž\.]+(?:\s+[A-Za-zÀ-ž\.]+){0,4})',
        re.UNICODE
    )

    # Remove the old dash_pattern — now unified in event_pattern above
    seen_events = set()  # Deduplicate

    all_matches = list(event_pattern.finditer(text))

    for match in all_matches:
        home = _clean_team_name(match.group(1))
        away = _clean_team_name(match.group(2))

        # Reject false positives from dash separator
        if home.lower() == away.lower():
            continue
        if re.fullmatch(r'\d+', home.strip()) or re.fullmatch(r'\d+', away.strip()):
            continue

        # Apply garbage filter
        if _is_garbage_event(home, away, text[match.start():match.end()+200]):
            continue

        # Deduplicate
        event_key = f"{home.lower()}|{away.lower()}"
        if event_key in seen_events:
            continue
        seen_events.add(event_key)

        # Extract context: 200 chars before and 500 after the match
        ctx_start = max(0, match.start() - 200)
        ctx_end = min(len(text), match.end() + 500)
        context = text[ctx_start:ctx_end]

        # Extract market from context
        after_text = text[match.end():min(len(text), match.end() + 500)]
        market = _extract_market_from_text(after_text)
        if market == "N/A":
            # Also try before the match (some sites put the pick before the event)
            before_text = text[max(0, match.start() - 200):match.start()]
            market = _extract_market_from_text(before_text)

        sport = detect_sport(context, url)
        odds = extract_odds_from_text(context)
        accuracy = extract_accuracy_from_text(context)
        stats = extract_stats_cited(context)
        mtype = classify_market(market, context)
        direction = extract_direction(market, context)

        # Reasoning — text after the event
        reasoning = after_text[:500].strip()
        reasoning = re.sub(r'\s+', ' ', reasoning)
        # Trim reasoning to remove HTML artifacts
        if reasoning.startswith((",", ".", ";", ":")):
            reasoning = reasoning[1:].strip()

        picks.append(TipsterPick(
            source_site=site_name,
            tipster_name=site_name,
            sport=sport,
            event=f"{home} vs {away}",
            home_team=home,
            away_team=away,
            competition="",
            market=market,
            market_type=mtype,
            direction=direction,
            odds=odds,
            reasoning=reasoning[:500],
            accuracy_pct=accuracy,
            confidence="medium",
            stats_cited=stats,
            fetch_time=now_iso,
        ))

    return picks


def parse_zawodtyper_html(html: str) -> list[TipsterPick]:
    """Parse ZawodTyper daily tips page.

    ZawodTyper uses structural HTML with id="match-name{ID}" for event names
    and id="type{ID}" for pick/market, both inside class="searched-in" divs.
    Falls back to text-based parsing if structural extraction fails.
    """
    picks = []
    now_iso = datetime.now(timezone.utc).isoformat()

    # Method 1: Structural parsing via match-name/type ID pairs
    match_ids = re.findall(r'id="match-name(\d+)"', html)

    seen_events = set()
    for mid in match_ids:
        # Extract match text from searched-in div
        mp = re.search(
            rf'id="match-name{mid}"[^>]*>.*?class="searched-in[^"]*"[^>]*>(.*?)</div>',
            html, re.DOTALL
        )
        if not mp:
            continue
        match_text = re.sub(r'<[^>]+>', '', mp.group(1)).strip()
        if not match_text:
            continue

        # Extract type/pick text
        tp = re.search(
            rf'id="type{mid}"[^>]*>.*?class="searched-in[^"]*"[^>]*>(.*?)</div>',
            html, re.DOTALL
        )
        type_text = re.sub(r'<[^>]+>', '', tp.group(1)).strip() if tp else ""

        # Parse team names from match text (Team A - Team B or Team A vs Team B)
        event_match = re.search(
            r'(.+?)\s*[-–—]\s*(.+)',
            match_text
        )
        if not event_match:
            event_match = re.search(r'(.+?)\s+vs\.?\s+(.+)', match_text, re.IGNORECASE)
        if not event_match:
            continue

        home = event_match.group(1).strip()
        away = event_match.group(2).strip()

        if _is_garbage_event(home, away):
            continue

        # Deduplicate by event+type combo
        event_key = f"{home.lower()}|{away.lower()}|{type_text.lower()}"
        if event_key in seen_events:
            continue
        seen_events.add(event_key)

        # Extract context around this block for odds/accuracy
        block_start = html.find(f'id="match-name{mid}"')
        block_end = min(len(html), block_start + 3000)
        block = html[block_start:block_end]
        block_text = re.sub(r'<[^>]+>', ' ', block)

        # Use type_text as market if available, otherwise extract from context
        market = type_text if type_text else "N/A"
        if market in ("1", "2", "X", "1X", "X2", "12"):
            # Pure outcome picks
            market = f"Winner: {market}"

        odds = extract_odds_from_text(block_text)
        accuracy = extract_accuracy_from_text(block_text)
        sport = detect_sport(match_text + " " + type_text)
        stats = extract_stats_cited(type_text + " " + block_text)

        picks.append(TipsterPick(
            source_site="ZawodTyper",
            tipster_name="ZawodTyper",
            sport=sport,
            event=f"{home} vs {away}",
            home_team=home,
            away_team=away,
            competition="",
            market=market,
            market_type=classify_market(market, type_text),
            direction=extract_direction(market, type_text),
            odds=odds,
            reasoning=type_text[:500],
            accuracy_pct=accuracy,
            confidence="medium" if accuracy and accuracy > 55 else "low",
            stats_cited=stats,
            fetch_time=now_iso,
        ))

    # Method 2: Fallback to text-based parsing if structural found < 3 picks
    if len(picks) < 3:
        text = re.sub(r'<(?:br|hr|/p|/div|/li|/tr)[^>]*>', '\n', html, flags=re.IGNORECASE)
        text = re.sub(r'<[^>]+>', '\n', text)
        text = re.sub(r'\n{3,}', '\n\n', text)

        blocks = re.split(r'(?=(?:Typ dnia|Typer:|Mecz:|Mój typ))', text)

        for block in blocks[:100]:
            if len(block) < 30:
                continue

            event_match = re.search(
                r'([A-ZÀ-Ž][A-Za-zÀ-ž\.\s]{2,30}?)\s*[-–—]\s*([A-ZÀ-Ž][A-Za-zÀ-ž\.\s]{2,30})',
                block
            )
            if not event_match:
                continue

            home = event_match.group(1).strip()
            away = event_match.group(2).strip()

            if _is_garbage_event(home, away, block):
                continue

            event_key = f"{home.lower()}|{away.lower()}"
            if event_key in seen_events:
                continue
            seen_events.add(event_key)

            tipster_match = re.search(r'(?:Typer|Tipster|Autor):\s*(\S+)', block, re.IGNORECASE)
            tipster_name = tipster_match.group(1) if tipster_match else "ZawodTyper"

            pick_match = re.search(
                r'(?:Typ|Pick|Zakład|Mój typ)[:\s]+(.+?)(?:\n|$)',
                block, re.IGNORECASE
            )
            market_raw = pick_match.group(1).strip() if pick_match else ""
            market = _extract_market_from_text(block) if not market_raw else market_raw
            if not market:
                market = "N/A"

            odds = extract_odds_from_text(block)
            accuracy = extract_accuracy_from_text(block)
            sport = detect_sport(block)
            stats = extract_stats_cited(block)

            reasoning_match = re.search(
                r'(?:Argument|Uzasadnienie|Dlaczego|Reasoning|spodziew)[:\s]*(.+?)(?:\n\n|$)',
                block, re.IGNORECASE | re.DOTALL
            )
            reasoning = reasoning_match.group(1).strip()[:500] if reasoning_match else ""

            picks.append(TipsterPick(
                source_site="ZawodTyper",
                tipster_name=tipster_name,
                sport=sport,
                event=f"{home} vs {away}",
                home_team=home,
                away_team=away,
                competition="",
                market=market,
                market_type=classify_market(market, block),
                direction=extract_direction(market, block),
                odds=odds,
                reasoning=reasoning,
                accuracy_pct=accuracy,
                confidence="medium" if accuracy and accuracy > 55 else "low",
                stats_cited=stats,
                fetch_time=now_iso,
            ))

    return picks


# ---------------------------------------------------------------------------
# Site-specific parsers
# ---------------------------------------------------------------------------

def parse_pickswise_html(html: str, url: str) -> list[TipsterPick]:
    """Parse PicksWise predictions using __NEXT_DATA__ JSON + article content.

    PicksWise (Next.js) stores event data in __NEXT_DATA__ → sportPredictions.
    Individual prediction pages have pick details in rendered HTML.
    """
    picks = []
    now_iso = datetime.now(timezone.utc).isoformat()

    # Detect sport from URL
    sport = detect_sport("", url)

    # Method 1: Parse __NEXT_DATA__ for event listings
    nd_match = re.search(
        r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>',
        html, re.DOTALL
    )

    if nd_match:
        try:
            nd = json.loads(nd_match.group(1))
            state = nd.get("props", {}).get("pageProps", {}).get("initialState", {})

            # Get sportPredictions — listing pages
            sp = state.get("sportPredictions", {})
            for page_key, page_data in sp.items():
                if not isinstance(page_data, list):
                    continue
                for day_group in page_data:
                    predictions = day_group.get("predictions", [])
                    for pred in predictions:
                        event_name = pred.get("event", "")
                        if " vs " not in event_name and " v " not in event_name:
                            continue
                        parts = re.split(r'\s+vs?\.?\s+', event_name, maxsplit=1)
                        if len(parts) != 2:
                            continue
                        home, away = parts[0].strip(), parts[1].strip()
                        if _is_garbage_event(home, away):
                            continue

                        picks.append(TipsterPick(
                            source_site="PicksWise",
                            tipster_name="PicksWise",
                            sport=sport,
                            event=event_name,
                            home_team=home,
                            away_team=away,
                            competition="",
                            market="N/A",
                            market_type="outcome",
                            direction="OTHER",
                            odds=None,
                            reasoning=pred.get("title", ""),
                            accuracy_pct=None,
                            confidence="medium",
                            stats_cited=[],
                            fetch_time=now_iso,
                        ))
        except (json.JSONDecodeError, KeyError):
            pass

    # Method 2: Parse JSON-LD SportsEvent data
    ld_blocks = re.findall(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.DOTALL
    )
    for block in ld_blocks:
        try:
            d = json.loads(block)
            if d.get("@type") != "SportsEvent":
                continue
            event_name = d.get("name", "")
            if " vs " not in event_name:
                continue
            parts = event_name.split(" vs ", 1)
            home, away = parts[0].strip(), parts[1].strip()
            if _is_garbage_event(home, away):
                continue
            # Skip if already found via __NEXT_DATA__
            event_key = f"{home.lower()}|{away.lower()}"
            if any(f"{p.home_team.lower()}|{p.away_team.lower()}" == event_key for p in picks):
                continue

            picks.append(TipsterPick(
                source_site="PicksWise",
                tipster_name="PicksWise",
                sport=sport,
                event=event_name,
                home_team=home,
                away_team=away,
                competition="",
                market="N/A",
                market_type="outcome",
                direction="OTHER",
                odds=None,
                reasoning=d.get("description", ""),
                accuracy_pct=None,
                confidence="medium",
                stats_cited=[],
                fetch_time=now_iso,
            ))
        except (json.JSONDecodeError, KeyError):
            continue

    # Method 3: Parse rendered pick details (individual prediction pages)
    # Look for "Expert Predictions" section with pick blocks
    expert_idx = html.find("Expert Predictions")
    if expert_idx >= 0:
        pred_section = html[expert_idx:expert_idx + 10000]
        pred_text = re.sub(r'<[^>]+>', '\n', pred_section)
        pred_lines = [l.strip() for l in pred_text.split('\n') if l.strip()]

        # Look for pick patterns: "Double Chance Pick", "Over/Under Pick", etc.
        pick_type = None
        pick_value = None
        odds_val = None
        reasoning_lines = []
        in_reasoning = False

        for line in pred_lines:
            # Detect pick type header
            if re.search(r'(?:Pick|Best Bet|Prediction)\s*$', line, re.IGNORECASE):
                # Save previous pick if exists
                if pick_type and pick_value:
                    # Find associated event from JSON-LD or picks
                    event_name = ""
                    home_t = away_t = ""
                    if picks:
                        event_name = picks[0].event
                        home_t = picks[0].home_team
                        away_t = picks[0].away_team

                    market_text = f"{pick_type}: {pick_value}"
                    reasoning_text = " ".join(reasoning_lines)[:500]

                    if home_t and away_t:
                        picks.append(TipsterPick(
                            source_site="PicksWise",
                            tipster_name="PicksWise Expert",
                            sport=sport,
                            event=event_name,
                            home_team=home_t,
                            away_team=away_t,
                            competition="",
                            market=market_text,
                            market_type=classify_market(market_text, reasoning_text),
                            direction=extract_direction(market_text, reasoning_text),
                            odds=odds_val,
                            reasoning=reasoning_text,
                            accuracy_pct=None,
                            confidence="high",
                            stats_cited=extract_stats_cited(reasoning_text),
                            fetch_time=now_iso,
                        ))

                pick_type = line
                pick_value = None
                odds_val = None
                reasoning_lines = []
                in_reasoning = False
                continue

            if pick_type and not pick_value:
                # Next non-empty line after pick type = the pick value
                if line and not line.startswith("("):
                    pick_value = line
                    continue
                elif line.startswith("("):
                    # Odds in parentheses
                    odds_match = re.search(r'[+-]?\d+', line)
                    if odds_match:
                        american = int(odds_match.group())
                        if american > 0:
                            odds_val = 1 + american / 100
                        else:
                            odds_val = 1 + 100 / abs(american)
                    continue

            if line == "Reasoning":
                in_reasoning = True
                continue

            if in_reasoning:
                if len(line) > 10:
                    reasoning_lines.append(line)

        # Save last pick
        if pick_type and pick_value and picks:
            event_name = picks[0].event
            home_t = picks[0].home_team
            away_t = picks[0].away_team
            market_text = f"{pick_type}: {pick_value}"
            reasoning_text = " ".join(reasoning_lines)[:500]

            if home_t and away_t:
                picks.append(TipsterPick(
                    source_site="PicksWise",
                    tipster_name="PicksWise Expert",
                    sport=sport,
                    event=event_name,
                    home_team=home_t,
                    away_team=away_t,
                    competition="",
                    market=market_text,
                    market_type=classify_market(market_text, reasoning_text),
                    direction=extract_direction(market_text, reasoning_text),
                    odds=odds_val,
                    reasoning=reasoning_text,
                    accuracy_pct=None,
                    confidence="high",
                    stats_cited=extract_stats_cited(reasoning_text),
                    fetch_time=now_iso,
                ))

    return picks


def parse_sportsgambler_html(html: str) -> list[TipsterPick]:
    """Parse Sportsgambler predictions listing page.

    Sportsgambler shows match cards with team names, competition, and time.
    Actual predictions (1X2, Over/Under) are on individual match pages.
    We extract events + any visible prediction data from the listing.
    """
    picks = []
    now_iso = datetime.now(timezone.utc).isoformat()

    # Pattern: Sportsgambler uses divs with team logos, competition, and "vs"
    # Structure: competition → time → home team → "vs" → away team → "Predictions"
    # Extract from the prediction link blocks
    pred_pattern = re.compile(
        r'<a[^>]*href="(/betting-tips/[^"]+predictions/[^"]+)"[^>]*>'
        r'(.*?)</a>',
        re.DOTALL
    )

    seen_events = set()
    for link_match in pred_pattern.finditer(html):
        link_url = link_match.group(1)
        link_content = link_match.group(2)

        # Clean content
        text = re.sub(r'<img[^>]*>', '', link_content)
        text = re.sub(r'<[^>]+>', '\n', text)
        lines = [l.strip() for l in text.split('\n') if l.strip()]

        if len(lines) < 2:
            continue

        # Look for "vs" or team name patterns
        # Lines typically: time, competition, team1, "vs", team2
        home = away = competition = ""
        for i, line in enumerate(lines):
            if line.lower() in ("vs", "v", "vs."):
                if i > 0 and i < len(lines) - 1:
                    home = lines[i - 1]
                    away = lines[i + 1]
                    # Competition is usually 2 lines before home
                    if i >= 2:
                        competition = lines[i - 2]
                break

        if not home or not away:
            # Try alternative: team names separated by "vs" in a single line
            for line in lines:
                vs_match = re.search(
                    r'([A-ZÀ-Ž][A-Za-zÀ-ž\.\s]+?)\s+vs\.?\s+([A-ZÀ-Ž][A-Za-zÀ-ž\.\s]+)',
                    line
                )
                if vs_match:
                    home = vs_match.group(1).strip()
                    away = vs_match.group(2).strip()
                    break

        if not home or not away:
            continue

        # Apply garbage filter
        if _is_garbage_event(home, away):
            continue

        # Deduplicate
        event_key = f"{home.lower()}|{away.lower()}"
        if event_key in seen_events:
            continue
        seen_events.add(event_key)

        # Detect sport from URL
        sport = "football"
        if "/tennis/" in link_url:
            sport = "tennis"
        elif "/basketball/" in link_url or "/nba/" in link_url:
            sport = "basketball"
        elif "/hockey/" in link_url or "/nhl/" in link_url:
            sport = "hockey"

        picks.append(TipsterPick(
            source_site="Sportsgambler",
            tipster_name="Sportsgambler",
            sport=sport,
            event=f"{home} vs {away}",
            home_team=home,
            away_team=away,
            competition=competition,
            market="N/A",
            market_type="outcome",
            direction="OTHER",
            odds=None,
            reasoning=f"Prediction available: {link_url}",
            accuracy_pct=None,
            confidence="medium",
            stats_cited=[],
            fetch_time=now_iso,
        ))

    # Also parse the broader match listing (non-link blocks with "vs")
    # These are match cards that might not be wrapped in prediction links
    vs_pattern = re.compile(
        r'([A-ZÀ-Ž][A-Za-zÀ-ž\.\s\']+?)\s+vs\.?\s+([A-ZÀ-Ž][A-Za-zÀ-ž\.\s\']+)',
        re.UNICODE
    )
    text = re.sub(r'<[^>]+>', '\n', html)
    for match in vs_pattern.finditer(text):
        home = match.group(1).strip()
        away = match.group(2).strip()
        if _is_garbage_event(home, away):
            continue
        event_key = f"{home.lower()}|{away.lower()}"
        if event_key in seen_events:
            continue
        seen_events.add(event_key)

        context = text[max(0, match.start() - 200):match.end() + 300]
        sport = detect_sport(context)

        picks.append(TipsterPick(
            source_site="Sportsgambler",
            tipster_name="Sportsgambler",
            sport=sport,
            event=f"{home} vs {away}",
            home_team=home,
            away_team=away,
            competition="",
            market="N/A",
            market_type="outcome",
            direction="OTHER",
            odds=None,
            reasoning="",
            accuracy_pct=None,
            confidence="low",
            stats_cited=[],
            fetch_time=now_iso,
        ))

    return picks


# ---------------------------------------------------------------------------
# Fetcher — parallel fetch with error handling
# ---------------------------------------------------------------------------

def _extract_pickswise_pred_urls(html: str) -> list[str]:
    """Extract individual prediction page URLs from PicksWise listing page."""
    urls = []
    try:
        nd_match = re.search(
            r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>',
            html, re.DOTALL
        )
        if nd_match:
            nd = json.loads(nd_match.group(1))
            state = nd.get("props", {}).get("pageProps", {}).get("initialState", {})
            sp = state.get("sportPredictions", {})
            for page_data_list in sp.values():
                if not isinstance(page_data_list, list):
                    continue
                for day_group in page_data_list:
                    for pred in day_group.get("predictions", []):
                        href = pred.get("href", "")
                        if href and "/predictions/" in href:
                            urls.append(f"https://www.pickswise.com{href}")
    except Exception:
        pass

    # Also try JSON-LD SportsEvent URLs
    ld_blocks = re.findall(
        r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html, re.DOTALL
    )
    seen = set(urls)
    for block in ld_blocks:
        try:
            d = json.loads(block)
            if d.get("@type") == "SportsEvent":
                url = d.get("url", "")
                if url and "/predictions/" in url:
                    full = f"https://www.pickswise.com{url}" if url.startswith("/") else url
                    if full not in seen:
                        urls.append(full)
                        seen.add(full)
        except Exception:
            continue

    return urls


# Per-site fetch timeout (seconds) — prevents one slow site from blocking the whole run
SITE_FETCH_TIMEOUT = 45  # hard cap per site in ThreadPoolExecutor
PLAYWRIGHT_TIMEOUT = 15  # per-page Playwright navigation timeout
PLAYWRIGHT_RETRIES = 1   # single retry (was 2 — doubled wallclock for failing sites)


def _log(msg: str) -> None:
    """Print with immediate flush so agent sees output in real time."""
    print(msg, flush=True)


def fetch_site(site_config: dict, date: datetime) -> dict:
    """Fetch a single tipster site and parse its picks.

    Returns dict with: site_name, url, status, picks, error, fetch_time_ms.
    For PicksWise: also follows individual prediction page URLs.
    """
    site_name = site_config["name"]
    start = time.time()

    result = {
        "site_name": site_name,
        "url": "",
        "status": "pending",
        "picks": [],
        "pick_count": 0,
        "error": None,
        "fetch_time_ms": 0,
    }

    try:
        # Build URL(s)
        urls = []
        if "url_builder" in site_config and site_config["url_builder"] == "zawodtyper":
            urls = [build_zawodtyper_url(date)]
        elif "urls" in site_config:
            urls = site_config["urls"]
        elif "url" in site_config:
            urls = [site_config["url"]]

        all_picks = []
        for url_idx, url in enumerate(urls):
            # Time budget check — bail out if site is taking too long
            elapsed = time.time() - start
            if elapsed > SITE_FETCH_TIMEOUT - 5:
                _log(f"  [tipster] {site_name}: time budget exhausted ({elapsed:.0f}s), skipping remaining URLs")
                break
            if len(urls) > 1:
                _log(f"  [tipster] {site_name}: fetching URL {url_idx + 1}/{len(urls)} ({elapsed:.0f}s elapsed)")
            result["url"] = url
            try:
                # JS-heavy sites need longer settle time for AJAX content
                wait_ms = site_config.get("wait_after_load", 500)
                html = fetch(url, timeout=PLAYWRIGHT_TIMEOUT, retries=PLAYWRIGHT_RETRIES,
                             wait_after_load=wait_ms)
                if not html or len(html) < 100:
                    _log(f"  [tipster] {site_name}: {url} returned {len(html) if html else 0} bytes (skipped)")
                    continue

                # Route to appropriate parser
                parser = site_config.get("parser", "generic")
                if parser == "zawodtyper":
                    picks = parse_zawodtyper_html(html)
                elif parser == "pickswise":
                    picks = parse_pickswise_html(html, url)
                    # Follow individual prediction page URLs for actual picks
                    pred_urls = _extract_pickswise_pred_urls(html)
                    for pidx, pred_url in enumerate(pred_urls[:3]):  # Limit to 3 per sport page
                        # Bail out if site is taking too long
                        if time.time() - start > SITE_FETCH_TIMEOUT - 5:
                            _log(f"  [tipster] {site_name}: time cap reached, stopping pred URL crawl at {pidx}/{len(pred_urls)}")
                            break
                        try:
                            pred_html = fetch(pred_url, timeout=PLAYWRIGHT_TIMEOUT, retries=PLAYWRIGHT_RETRIES)
                            if pred_html:
                                pred_picks = parse_pickswise_html(pred_html, pred_url)
                                picks.extend(pred_picks)
                        except Exception:
                            continue
                elif parser == "sportsgambler":
                    picks = parse_sportsgambler_html(html)
                else:
                    picks = parse_generic_tipster_html(html, site_name, url)

                if not picks:
                    _log(f"  [tipster] {site_name}: {url} fetched {len(html)} bytes but parser returned 0 picks")

                all_picks.extend(picks)

            except Exception as e:
                result["error"] = f"Fetch failed for {url}: {str(e)[:200]}"
                continue

        result["picks"] = [p.to_dict() for p in all_picks]
        result["pick_count"] = len(all_picks)
        result["status"] = "success" if all_picks else "empty"

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)[:500]

    result["fetch_time_ms"] = int((time.time() - start) * 1000)
    return result


# ---------------------------------------------------------------------------
# Consensus computation
# ---------------------------------------------------------------------------

def compute_consensus(all_picks: list[dict]) -> list[dict]:
    """Group picks by event and compute tipster consensus.

    For each event, determines:
    - How many tipsters covered it
    - What markets they recommended
    - Agreement percentage
    - Statistical vs outcome market split
    """
    from collections import defaultdict

    event_groups = defaultdict(list)
    for pick in all_picks:
        # Normalize event key
        home = pick.get("home_team", "").strip().lower()
        away = pick.get("away_team", "").strip().lower()
        if home and away:
            key = f"{home}|{away}"
            event_groups[key].append(pick)

    consensus_list = []
    for key, picks in event_groups.items():
        if not picks:
            continue

        first = picks[0]

        # Count market directions
        direction_counts = defaultdict(int)
        market_counts = defaultdict(int)
        statistical_count = 0

        for p in picks:
            d = p.get("direction", "OTHER")
            m = p.get("market", "N/A")
            direction_counts[d] += 1
            market_counts[m] += 1
            if p.get("market_type") == "statistical":
                statistical_count += 1

        # Find most common market and direction
        most_common_market = max(market_counts, key=market_counts.get) if market_counts else None
        most_common_dir = max(direction_counts, key=direction_counts.get) if direction_counts else None

        total = len(picks)
        max_agreement = max(direction_counts.values()) if direction_counts else 0
        agreement_pct = round(max_agreement / total * 100, 1) if total > 0 else 0

        consensus_list.append({
            "event": first.get("event", ""),
            "sport": first.get("sport", "football"),
            "competition": first.get("competition", ""),
            "home_team": first.get("home_team", ""),
            "away_team": first.get("away_team", ""),
            "total_tipsters": total,
            "consensus_market": most_common_market,
            "consensus_direction": most_common_dir,
            "agreement_pct": agreement_pct,
            "statistical_picks": statistical_count,
            "outcome_picks": total - statistical_count,
            "has_reasoning": any(p.get("reasoning", "").strip() for p in picks),
            "tipster_sources": list({p.get("source_site", "") for p in picks}),
            "picks": picks,
            # Confidence adjustment based on §4 methodology
            "confidence_adj": (
                +0.5 if agreement_pct >= 70
                else -1.0 if agreement_pct <= 30 and total >= 3
                else 0.0
            ),
        })

    # Sort by: statistical picks count (desc), agreement (desc), tipster count (desc)
    consensus_list.sort(
        key=lambda c: (c["statistical_picks"], c["agreement_pct"], c["total_tipsters"]),
        reverse=True,
    )

    return consensus_list


# ---------------------------------------------------------------------------
# Integration with probability engine
# ---------------------------------------------------------------------------

def combine_tipster_with_stats(consensus: list[dict], stats_cache_dir: Path | None = None) -> list[dict]:
    """Combine tipster consensus with statistical analysis.

    For each consensus entry:
    1. Check if tipsters recommended a STATISTICAL market
    2. If so, note the specific stats they cited
    3. Cross-reference with safety scores if available
    4. Generate "tipster-enhanced" entries for the shortlist
    """
    enhanced = []
    for entry in consensus:
        enhancement = {
            "event": entry["event"],
            "sport": entry["sport"],
            "home_team": entry["home_team"],
            "away_team": entry["away_team"],
            "tipster_signal": "strong" if entry["agreement_pct"] >= 70 else (
                "moderate" if entry["agreement_pct"] >= 50 else "weak"
            ),
            "tipster_market": entry["consensus_market"],
            "tipster_direction": entry["consensus_direction"],
            "tipster_count": entry["total_tipsters"],
            "statistical_focus": entry["statistical_picks"] > entry["outcome_picks"],
            "confidence_adjustment": entry["confidence_adj"],
            "reasoning_available": entry["has_reasoning"],
            "sources": entry["tipster_sources"],
        }

        # Extract best reasoning from picks
        best_reasoning = ""
        best_stats = []
        for pick in entry.get("picks", []):
            if isinstance(pick, dict):
                r = pick.get("reasoning", "")
                if len(r) > len(best_reasoning):
                    best_reasoning = r
                stats = pick.get("stats_cited", [])
                best_stats.extend(stats)

        enhancement["best_reasoning"] = best_reasoning[:500]
        enhancement["stats_cited"] = list(set(best_stats))[:10]

        enhanced.append(enhancement)

    return enhanced


# ---------------------------------------------------------------------------
# DB table setup for tipster data (R2)
# ---------------------------------------------------------------------------

def _ensure_tipster_tables(conn):
    """Create tipster_picks and tipster_consensus tables if they don't exist."""
    conn.execute("""CREATE TABLE IF NOT EXISTS tipster_picks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        betting_date TEXT NOT NULL,
        source_site TEXT NOT NULL,
        tipster_name TEXT,
        sport TEXT,
        event TEXT,
        home_team TEXT NOT NULL,
        away_team TEXT NOT NULL,
        competition TEXT,
        market TEXT,
        market_type TEXT,
        direction TEXT,
        odds REAL,
        reasoning TEXT,
        accuracy_pct REAL,
        confidence REAL,
        stats_cited TEXT,
        fetch_time TEXT,
        created_at TEXT DEFAULT (datetime('now'))
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tipster_picks_date ON tipster_picks(betting_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tipster_picks_teams ON tipster_picks(home_team, away_team)")

    conn.execute("""CREATE TABLE IF NOT EXISTS tipster_consensus (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        betting_date TEXT NOT NULL,
        event TEXT,
        sport TEXT,
        competition TEXT,
        home_team TEXT NOT NULL,
        away_team TEXT NOT NULL,
        total_tipsters INTEGER,
        consensus_market TEXT,
        consensus_direction TEXT,
        agreement_pct REAL,
        statistical_picks INTEGER,
        outcome_picks INTEGER,
        has_reasoning INTEGER DEFAULT 0,
        tipster_sources TEXT,
        confidence_adj REAL DEFAULT 0.0,
        created_at TEXT DEFAULT (datetime('now'))
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tipster_consensus_date ON tipster_consensus(betting_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tipster_consensus_teams ON tipster_consensus(home_team, away_team)")


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

def run_tipster_aggregation(
    date: str,
    max_workers: int = 5,
    sport_filter: str | None = None,
    use_gemini: bool = False,
) -> dict:
    """Run full tipster aggregation pipeline.

    1. Build URLs for all tipster sites
    2. Fetch in parallel (ThreadPoolExecutor) — or via Gemini if --use-gemini
    3. Parse picks from each site
    4. Compute consensus
    5. Combine with stats
    6. Save output

    Args:
        use_gemini: When True, use Gemini URL reading instead of BS4 HTML parsing.
                    Falls back to BS4 per-site on Gemini failure.

    Returns summary dict.
    """
    try:
        from bet.config import get_tz
    except ImportError:
        from zoneinfo import ZoneInfo
        get_tz = lambda: ZoneInfo("Europe/Warsaw")

    date_obj = datetime.strptime(date, "%Y-%m-%d")
    date_obj = date_obj.replace(tzinfo=get_tz())

    _log(f"[tipster] Starting aggregation for {date}")
    _log(f"[tipster] Sites to fetch: {len(TIPSTER_SITES)}")
    _log(f"[tipster] Workers: {max_workers}")
    _log(f"[tipster] Gemini mode: {'ON' if use_gemini else 'OFF'}")
    _log(f"[tipster] Per-site timeout: {SITE_FETCH_TIMEOUT}s, Playwright: {PLAYWRIGHT_TIMEOUT}s")

    # --- Gemini path (feature flag) ---
    gemini_picks = []
    gemini_success = 0
    gemini_fallback = 0
    if use_gemini:
        try:
            from gemini_tipster_reader import read_tipster_page, convert_to_tipster_pick
            _log("[tipster] Gemini tipster reader loaded — will try Gemini first per site")
            for site in TIPSTER_SITES:
                site_url = site.get("url", "")
                if not site_url:
                    continue
                result = read_tipster_page(site_url, site["name"], sport_filter, date)
                if result.picks:
                    gemini_success += 1
                    for p in result.picks:
                        pick_dict = convert_to_tipster_pick(p, site["name"], date)
                        gemini_picks.append(pick_dict)
                    _log(f"  [gemini] {site['name']}: {len(result.picks)} picks extracted")
                else:
                    gemini_fallback += 1
                    _log(f"  [gemini-fallback] {site['name']}: no picks, will use BS4")
        except ImportError:
            _log("[tipster] gemini_tipster_reader not available — falling back to BS4")
            use_gemini = False
        except Exception as e:
            _log(f"[tipster] Gemini failed: {e} — falling back to BS4")
            use_gemini = False

    # Parallel fetch
    all_results = []
    all_picks = []
    errors = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(fetch_site, site, date_obj): site["name"]
            for site in TIPSTER_SITES
        }

        try:
            for future in as_completed(futures, timeout=SITE_FETCH_TIMEOUT + 10):
                site_name = futures[future]
                try:
                    result = future.result(timeout=5)  # result should be ready since as_completed returned it
                    all_results.append(result)
                    all_picks.extend(result.get("picks", []))
                    status = result["status"]
                    count = result["pick_count"]
                    ms = result["fetch_time_ms"]
                    _log(f"  [{status}] {site_name}: {count} picks ({ms}ms)")
                    if result.get("error"):
                        errors.append(f"{site_name}: {result['error']}")
                except TimeoutError:
                    _log(f"  [timeout] {site_name}: exceeded {SITE_FETCH_TIMEOUT}s — skipped")
                    errors.append(f"{site_name}: timeout after {SITE_FETCH_TIMEOUT}s")
                except Exception as e:
                    _log(f"  [error] {site_name}: {e}")
                    errors.append(f"{site_name}: {str(e)[:200]}")
        except FuturesTimeoutError:
            # Overall timeout — cancel remaining futures
            pending = [f for f in futures if not f.done()]
            pending_names = [futures[f] for f in pending]
            _log(f"  [TIMEOUT] Global timeout reached. Pending: {', '.join(pending_names)}")
            for f in pending:
                f.cancel()
            errors.extend(f"{n}: global timeout" for n in pending_names)

    # Filter by sport if requested
    if sport_filter:
        all_picks = [p for p in all_picks if p.get("sport") == sport_filter]

    # Compute consensus
    consensus = compute_consensus(all_picks)

    # Combine with stats
    enhanced = combine_tipster_with_stats(consensus)

    # Summary
    total_picks = len(all_picks)
    statistical_picks = sum(1 for p in all_picks if p.get("market_type") == "statistical")
    sites_ok = sum(1 for r in all_results if r["status"] == "success")
    sites_empty = sum(1 for r in all_results if r["status"] == "empty")
    sites_error = sum(1 for r in all_results if r["status"] == "error")

    summary = {
        "date": date,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "sites_total": len(TIPSTER_SITES),
        "sites_success": sites_ok,
        "sites_empty": sites_empty,
        "sites_error": sites_error,
        "total_picks": total_picks,
        "statistical_picks": statistical_picks,
        "outcome_picks": total_picks - statistical_picks,
        "events_covered": len(consensus),
        "events_with_consensus": sum(1 for c in consensus if c["agreement_pct"] >= 60),
        "errors": errors,
        "site_results": all_results,
        "consensus": consensus,
        "enhanced_entries": enhanced,
        "all_picks": all_picks,
    }

    # Save outputs
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    output_json = DATA_DIR / f"{date}_tipster_consensus.json"
    output_json.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    _log(f"\n[tipster] Saved: {output_json}")

    # Generate markdown summary
    md_lines = [
        f"# Tipster Consensus — {date}",
        "",
        f"Sites fetched: {sites_ok}/{len(TIPSTER_SITES)} success, {sites_empty} empty, {sites_error} errors",
        f"Total picks: {total_picks} ({statistical_picks} statistical, {total_picks - statistical_picks} outcome)",
        f"Events covered: {len(consensus)}",
        f"Events with ≥60% consensus: {sum(1 for c in consensus if c['agreement_pct'] >= 60)}",
        "",
        "## Consensus Table",
        "",
        "| # | Sport | Event | Market | Direction | Tipsters | Agreement | Stat? | Signal |",
        "|---|-------|-------|--------|-----------|----------|-----------|-------|--------|",
    ]

    for i, c in enumerate(consensus[:50], 1):
        stat_flag = "✅" if c["statistical_picks"] > c["outcome_picks"] else "⚠️"
        signal = "🟢" if c["agreement_pct"] >= 70 else ("🟡" if c["agreement_pct"] >= 50 else "🔴")
        md_lines.append(
            f"| {i} | {c['sport']} | {c['event'][:40]} | {c.get('consensus_market', 'N/A')[:30]} | "
            f"{c.get('consensus_direction', 'N/A')} | {c['total_tipsters']} | {c['agreement_pct']}% | "
            f"{stat_flag} | {signal} |"
        )

    md_lines.extend([
        "",
        "## Errors",
        "",
    ])
    for err in errors:
        md_lines.append(f"- {err[:200]}")

    output_md = DATA_DIR / f"{date}_tipster_consensus.md"
    output_md.write_text("\n".join(md_lines), encoding="utf-8")
    _log(f"[tipster] Saved: {output_md}")

    _log(f"\n[tipster] Summary: {total_picks} picks from {sites_ok} sites, "
         f"{len(consensus)} events, {statistical_picks} statistical markets")

    # Save tipster picks, consensus, and pipeline step to DB (R2)
    try:
        from bet.db.connection import get_db
        from bet.db.repositories import PipelineRepo
        with get_db() as conn:
            _ensure_tipster_tables(conn)

            # Clear old entries for this date
            conn.execute("DELETE FROM tipster_picks WHERE betting_date = ?", (date,))
            conn.execute("DELETE FROM tipster_consensus WHERE betting_date = ?", (date,))

            # Insert picks
            for pick in all_picks:
                conn.execute("""
                    INSERT INTO tipster_picks (betting_date, source_site, tipster_name, sport, event,
                        home_team, away_team, competition, market, market_type, direction, odds,
                        reasoning, accuracy_pct, confidence, stats_cited, fetch_time)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    date,
                    pick.get("source_site", ""),
                    pick.get("tipster_name", ""),
                    pick.get("sport", ""),
                    pick.get("event", ""),
                    pick.get("home_team", ""),
                    pick.get("away_team", ""),
                    pick.get("competition", ""),
                    pick.get("market", ""),
                    pick.get("market_type", ""),
                    pick.get("direction", ""),
                    pick.get("odds"),
                    pick.get("reasoning", ""),
                    pick.get("accuracy_pct"),
                    pick.get("confidence"),
                    json.dumps(pick.get("stats_cited", [])) if isinstance(pick.get("stats_cited"), list) else pick.get("stats_cited", ""),
                    pick.get("fetch_time", ""),
                ))

            # Insert consensus
            for ce in consensus:
                conn.execute("""
                    INSERT INTO tipster_consensus (betting_date, event, sport, competition,
                        home_team, away_team, total_tipsters, consensus_market, consensus_direction,
                        agreement_pct, statistical_picks, outcome_picks, has_reasoning,
                        tipster_sources, confidence_adj)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    date,
                    ce.get("event", ""),
                    ce.get("sport", ""),
                    ce.get("competition", ""),
                    ce.get("home_team", ""),
                    ce.get("away_team", ""),
                    ce.get("total_tipsters", 0),
                    ce.get("consensus_market", ""),
                    ce.get("consensus_direction", ""),
                    ce.get("agreement_pct", 0),
                    ce.get("statistical_picks", 0),
                    ce.get("outcome_picks", 0),
                    1 if ce.get("has_reasoning") else 0,
                    json.dumps(ce.get("tipster_sources", [])),
                    ce.get("confidence_adj", 0.0),
                ))

            # Pipeline step tracking
            tipster_stats = {
                "total_tipsters": sites_ok,
                "sites_total": len(TIPSTER_SITES),
                "sites_error": sites_error,
                "total_picks": total_picks,
                "statistical_picks": statistical_picks,
                "events_covered": len(consensus),
                "consensus_picks": sum(1 for c in consensus if c["agreement_pct"] >= 60),
            }
            repo = PipelineRepo(conn)
            repo.start_step(date, "s2_tipster")
            repo.complete_step(date, "s2_tipster", stats=tipster_stats)
            conn.commit()
        _log(f"[tipster] DB: saved {len(all_picks)} picks + {len(consensus)} consensus entries")
    except Exception as e:
        print(f"  ⚠ DB tipster save failed (non-fatal): {e}")

    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    from agent_output import AgentOutput, add_agent_args

    global SITE_FETCH_TIMEOUT
    parser = argparse.ArgumentParser(description="Tipster Aggregator — parallel fetch and consensus")
    parser.add_argument("--date", help="Date (YYYY-MM-DD)")
    parser.add_argument("--workers", type=int, default=5, help="Max parallel workers (default: 5)")
    parser.add_argument("--sport", help="Filter by sport (e.g., football)")
    parser.add_argument("--use-gemini", action="store_true",
                        help="Use Gemini URL reading instead of BS4 HTML parsing (feature flag)")
    parser.add_argument("--site-timeout", type=int, default=None,
                        help=f"Per-site timeout in seconds (default: {SITE_FETCH_TIMEOUT})")
    add_agent_args(parser)
    args = parser.parse_args()

    out = AgentOutput("s2_tipster", verbose=args.verbose, stop_on_error=args.stop_on_error)

    if args.site_timeout:
        SITE_FETCH_TIMEOUT = args.site_timeout

    if not args.date:
        try:
            from bet.config import get_tz
        except ImportError:
            from zoneinfo import ZoneInfo
            get_tz = lambda: ZoneInfo("Europe/Warsaw")
        args.date = datetime.now(get_tz()).strftime("%Y-%m-%d")

    result = run_tipster_aggregation(args.date, max_workers=args.workers,
                                     sport_filter=args.sport,
                                     use_gemini=getattr(args, "use_gemini", False))

    sites_ok = result.get("sites_success", 0)
    out.summary(
        verdict="OK" if sites_ok > 0 else "FAILED",
        metrics={
            "sites_success": sites_ok,
            "sites_error": result.get("sites_error", 0),
            "total_picks": result.get("total_picks", 0),
            "statistical_picks": result.get("statistical_picks", 0),
            "events_covered": result.get("events_covered", 0),
            "events_with_consensus": result.get("events_with_consensus", 0),
        },
    )
    sys.exit(0 if sites_ok > 0 else 1)


if __name__ == "__main__":
    main()
