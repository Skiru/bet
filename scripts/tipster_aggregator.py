#!/usr/bin/env python3
"""Tipster Aggregator — parallel fetch, parse, and consensus scoring from all tipster sites.

Fetches today's picks from ALL configured tipster sites in parallel using
ThreadPoolExecutor, parses structured picks (sport, event, market, odds,
reasoning, accuracy), computes consensus, and combines tipster arguments
with statistical calculations.

Sites covered:
  Polish: ZawodTyper, Typersi
  English: PicksWise, BetIdeas, Sportsgambler
  Exotic: Feedinco, BettingClosed

Usage:
    python3 scripts/tipster_aggregator.py --date 2026-05-04
    python3 scripts/tipster_aggregator.py --date 2026-05-04 --workers 8
    python3 scripts/tipster_aggregator.py --date 2026-05-04 --sport football
"""

import argparse
import html as html_module
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

# Playwright-based client for JS-rendered tipster sites
_pw_client = None

def _get_pw_client():
    """Lazy-init shared TipsterPlaywrightClient.

    Only called before the sequential Playwright loop — not thread-safe by design.
    """
    global _pw_client
    if _pw_client is None:
        try:
            from bet.api_clients.tipster_playwright import TipsterPlaywrightClient
            _pw_client = TipsterPlaywrightClient()
            _log("[tipster] Playwright client initialized")
        except Exception as e:
            _log(f"[tipster] Playwright unavailable ({e}), falling back to HTTP")
    return _pw_client

def _cleanup_pw_client():
    """Clean up Playwright browser resources."""
    global _pw_client
    if _pw_client is not None:
        try:
            _pw_client.close()
        except Exception:
            pass
        _pw_client = None

def fetch(url: str, **kwargs) -> str:
    """HTTP fetch for tipster pages (fallback when Playwright unavailable)."""
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
        "wait_after_load": 6000,  # AJAX cards need extra time to render
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


# Phrases that indicate garbage reasoning (ads, navigation, boilerplate)
_GARBAGE_REASONING_PHRASES = {
    "sign up", "claim now", "no deposit", "free bet", "bonus code",
    "gold coins", "sweeps coins", "sign up now", "join now",
    "best bets run", "try free", "free for 3 days", "subscribe",
    "data-driven picks", "delivered daily",
    "promo code", "bonus spins", "bet $20", "get $100",
    "cookie", "privacy policy", "terms of service",
    "copyright", "all rights reserved", "telegram channel",
    "our newsletter", "follow us", "download app",
    "view prediction", "view tips", "read more",
    "aktualizacja:", "timestamps", "page not found",
    "społecznościowy", "serwis informacyjno",
}

# Minimum meaningful reasoning: must have at least some analytical content
_REASONING_SIGNAL_WORDS = {
    "win", "lose", "draw", "goal", "corner", "card", "foul", "shot",
    "form", "home", "away", "attack", "defend", "h2h", "head-to-head",
    "average", "scored", "conceded", "possession", "record", "streak",
    "odds", "value", "underdog", "favourite", "favorite",
    "expect", "predict", "likely", "confident", "back", "pick",
    "over", "under", "total", "handicap", "spread",
    "last", "recent", "previous", "match", "season",
    "injury", "missing", "suspended", "lineup",
    "strong", "weak", "dominate", "struggle",
    # Polish equivalents
    "bramk", "gol", "wynik", "forma", "mecz", "kartek", "rzut",
    "faul", "strzał", "średni", "obroni", "posiadan", "sezon",
    "kontuzj", "zawieszeni", "składu", "dominuj", "silny",
    "słab", "przewag", "wygr", "przegr", "remis", "bramkarz",
    "atak", "obron", "strategia", "taktyk", "trener",
}


def _is_garbage_reasoning(text: str) -> bool:
    """Check if reasoning text is garbage (ads, navigation, boilerplate).

    Returns True if the text should be rejected as non-analytical.
    """
    lower = text.lower()

    # Contains garbage phrases
    for phrase in _GARBAGE_REASONING_PHRASES:
        if phrase in lower:
            return True

    # Mostly digits/punctuation (garbled HTML artifacts)
    alpha_chars = sum(1 for c in text if c.isalpha())
    if len(text) > 0 and alpha_chars / len(text) < 0.5:
        return True

    # Starts with a URL or contains mostly URLs
    if lower.startswith(("http", "www.", "/")):
        return True

    return False


def _has_analytical_content(text: str) -> bool:
    """Check if reasoning text contains actual analytical content.

    Returns True if the text appears to be genuine sports analysis.
    """
    lower = text.lower()
    signal_count = sum(1 for word in _REASONING_SIGNAL_WORDS if word in lower)
    # Need at least 2 signal words to qualify as analytical
    return signal_count >= 2


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

        # Reasoning — text after the event, validated for quality
        reasoning_raw = after_text[:500].strip()
        reasoning_raw = re.sub(r'\s+', ' ', reasoning_raw)
        if reasoning_raw.startswith((",", ".", ";", ":")):
            reasoning_raw = reasoning_raw[1:].strip()
        # Only keep reasoning if it's genuine analysis, not garbage
        if _is_garbage_reasoning(reasoning_raw) or not _has_analytical_content(reasoning_raw):
            reasoning = ""
        else:
            reasoning = reasoning_raw[:500]

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

        # Build meaningful reasoning: tipster accuracy + market context
        reasoning_parts = []
        if accuracy:
            reasoning_parts.append(f"Tipster accuracy: {accuracy}% (tracked)")
        if type_text and type_text != market:
            reasoning_parts.append(f"Pick: {type_text}")
        # Look for any analysis text in the block (beyond just accuracy)
        analysis_match = re.search(
            r'(?:argument|uzasadnienie|dlaczego|opis|komentarz)[:\s]*(.+?)(?:\n|$)',
            block_text, re.IGNORECASE
        )
        if analysis_match:
            reasoning_parts.append(analysis_match.group(1).strip()[:300])
        reasoning = " | ".join(reasoning_parts) if reasoning_parts else type_text[:200]

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
            reasoning=reasoning[:500],
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


def _extract_sportsgambler_pred_urls(html: str) -> list[str]:
    """Extract individual prediction page URLs from Sportsgambler listing."""
    urls = []
    seen = set()
    # Pattern: /betting-tips/sport/team-vs-team-prediction-...-YYYY-MM-DD/
    for m in re.finditer(r'href="(/betting-tips/[^"]*prediction[^"]*2026[^"]*)"', html):
        url = m.group(1)
        if url not in seen:
            seen.add(url)
            urls.append(f"https://www.sportsgambler.com{url}")
    return urls


def parse_sportsgambler_detail_html(html: str, url: str) -> list[TipsterPick]:
    """Parse a Sportsgambler individual prediction page — rich analysis text.

    These pages have: match preview paragraphs, head-to-head stats, team form,
    predicted lineups, and explicit prediction with odds.
    """
    picks = []
    now_iso = datetime.now(timezone.utc).isoformat()

    # Extract team names from URL: .../team1-vs-team2-prediction-...
    url_match = re.search(r'/betting-tips/(\w+)/([\w-]+)-vs-([\w-]+)-prediction', url)
    if not url_match:
        return picks

    sport_slug = url_match.group(1)
    home_slug = url_match.group(2).replace("-", " ").title()
    away_slug = url_match.group(3).replace("-", " ").title()

    sport = "football"
    if sport_slug in ("tennis",):
        sport = "tennis"
    elif sport_slug in ("basketball",):
        sport = "basketball"
    elif sport_slug in ("hockey", "ice-hockey"):
        sport = "hockey"
    elif sport_slug in ("volleyball",):
        sport = "volleyball"

    # Try extracting from <title> for better team names
    title_match = re.search(r'<title>([^<]+)</title>', html)
    if title_match:
        title = title_match.group(1)
        t_vs = re.search(r'([A-ZÀ-Ž][A-Za-zÀ-ž\s\.]+?)\s+vs?\s+([A-ZÀ-Ž][A-Za-zÀ-ž\s\.]+?)(?:\s+Prediction|\s+[-|])', title)
        if t_vs:
            home_slug = t_vs.group(1).strip()
            away_slug = t_vs.group(2).strip()

    if _is_garbage_event(home_slug, away_slug):
        return picks

    # Extract all meaningful paragraphs (analysis text)
    paras = re.findall(r'<p[^>]*>(.*?)</p>', html, re.DOTALL)
    analysis_lines = []
    for p in paras:
        text = re.sub(r'<[^>]+>', '', p).strip()
        # Keep paragraphs that look like analysis (>60 chars, not ads/navigation)
        if len(text) > 60 and not _is_garbage_reasoning(text):
            analysis_lines.append(text)

    reasoning = " ".join(analysis_lines[:5])[:800] if analysis_lines else ""

    # Extract specific prediction/pick
    pred_match = re.search(
        r"(?:our|we)\s+(?:predict|pick|back|tip|select|expect|think)[^.]*\.",
        reasoning, re.IGNORECASE
    )
    main_prediction = pred_match.group(0).strip() if pred_match else ""

    # Extract market picks (over/under, corners, etc.)
    market_picks = re.findall(
        r'(?:over|under)\s+\d+\.?\d*\s+(?:goals?|corners?|cards?|fouls?|shots?)',
        html, re.IGNORECASE
    )
    # Odds extraction
    odds_match = re.search(
        r'(?:odds?\s+(?:of\s+)?|@\s*|at\s+)(\d+\.\d{1,2})',
        reasoning, re.IGNORECASE
    )
    odds = float(odds_match.group(1)) if odds_match else None
    if odds and (odds < 1.01 or odds > 50):
        odds = None

    # Primary pick: the main prediction
    market = main_prediction[:80] if main_prediction else "N/A"
    if not main_prediction and market_picks:
        market = market_picks[0]

    stats = extract_stats_cited(reasoning)

    picks.append(TipsterPick(
        source_site="Sportsgambler",
        tipster_name="Sportsgambler",
        sport=sport,
        event=f"{home_slug} vs {away_slug}",
        home_team=home_slug,
        away_team=away_slug,
        competition="",
        market=market,
        market_type=classify_market(market, reasoning),
        direction=extract_direction(market, reasoning),
        odds=odds,
        reasoning=reasoning,
        accuracy_pct=None,
        confidence="high" if main_prediction else "medium",
        stats_cited=stats,
        fetch_time=now_iso,
    ))

    # Additional picks from market_picks (statistical markets)
    seen_markets = {market.lower()}
    for mp in market_picks[:3]:
        if mp.lower() in seen_markets:
            continue
        seen_markets.add(mp.lower())
        picks.append(TipsterPick(
            source_site="Sportsgambler",
            tipster_name="Sportsgambler",
            sport=sport,
            event=f"{home_slug} vs {away_slug}",
            home_team=home_slug,
            away_team=away_slug,
            competition="",
            market=mp,
            market_type="statistical",
            direction=extract_direction(mp, ""),
            odds=None,
            reasoning=f"Market pick from analysis: {mp}",
            accuracy_pct=None,
            confidence="medium",
            stats_cited=[],
            fetch_time=now_iso,
        ))

    return picks


def parse_sportsgambler_html(html: str) -> list[TipsterPick]:
    """Parse Sportsgambler predictions listing page.

    Extracts prediction page URLs from the listing. Individual pages are
    fetched separately in the fetch_site loop for rich analysis text.
    This function only extracts basic events from the listing as fallback.
    """
    picks = []
    now_iso = datetime.now(timezone.utc).isoformat()

    # Extract prediction URLs for follow-up fetching (stored in picks metadata)
    _year = str(datetime.now().year)
    pred_pattern = re.compile(
        rf'<a[^>]*href="(/betting-tips/[^"]+prediction[^"]*{_year}[^"]*)"[^>]*>'
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
        home = away = competition = ""
        for i, line in enumerate(lines):
            if line.lower() in ("vs", "v", "vs."):
                if i > 0 and i < len(lines) - 1:
                    home = lines[i - 1]
                    away = lines[i + 1]
                    if i >= 2:
                        competition = lines[i - 2]
                break

        if not home or not away:
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
        if _is_garbage_event(home, away):
            continue

        event_key = f"{home.lower()}|{away.lower()}"
        if event_key in seen_events:
            continue
        seen_events.add(event_key)

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


def _extract_pickswise_news_urls(html: str) -> list[str]:
    """Extract news article URLs from PicksWise listing page.

    These /news/ articles contain rich per-match analysis text that is
    server-rendered (unlike /predictions/ pages which need Playwright).
    """
    urls: list[str] = []
    try:
        nd_match = re.search(
            r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>',
            html, re.DOTALL,
        )
        if nd_match:
            nd = json.loads(nd_match.group(1))
            # News article hrefs appear throughout the JSON
            raw = nd_match.group(1)
            for m in re.finditer(r'"href":"(/news/[^"]+)"', raw):
                href = m.group(1)
                # Skip category pages like /news/soccer/ or /news/nba/
                # Real articles have long slugs: /news/premier-league-predictions-...
                parts = [p for p in href.strip("/").split("/") if p]
                if len(parts) < 2 or len(parts[1]) < 20:
                    continue
                full = f"https://www.pickswise.com{href}"
                if full not in urls:
                    urls.append(full)
    except Exception:
        pass

    # Also try href attributes in rendered HTML
    for m in re.finditer(r'href="(/news/[^"]+prediction[^"]+)"', html, re.IGNORECASE):
        full = f"https://www.pickswise.com{m.group(1)}"
        if full not in urls:
            urls.append(full)

    return urls


def parse_pickswise_news_html(html: str, url: str) -> list[TipsterPick]:
    """Parse PicksWise news article pages for per-match analysis.

    These articles have structure:
      <h2><b>Pick: Team A ML/spread/over over Team B (odds)</b></h2>
      <p><span>Analysis paragraph 1</span></p>
      <p><span>Analysis paragraph 2</span></p>
    """
    picks: list[TipsterPick] = []
    now_iso = datetime.now(timezone.utc).isoformat()
    sport = detect_sport("", url)

    # Split HTML into lines for section parsing
    # Find all h2 sections that look like picks
    sections = re.split(r'<h2[^>]*>', html)

    for section in sections[1:]:  # skip content before first h2
        # Extract pick header
        header_match = re.match(r'(.*?)</h2>', section, re.DOTALL)
        if not header_match:
            continue
        header_raw = header_match.group(1)
        header_text = re.sub(r'<[^>]+>', '', header_raw).strip()

        # Must look like a pick: "best bet: X over/vs Y" or "pick: X ..." with odds
        if not header_text or len(header_text) < 10:
            continue

        # Extract teams and market from header
        # Patterns: "EPL best bet: Team A ML over Team B (-120)"
        #           "Pick: Team A vs Team B Over 2.5 (+110)"
        team_match = re.search(
            r'(?:best bet|pick|prediction)[:\s]+(.+?)\s+(?:over|vs\.?|v)\s+(.+?)(?:\s*\(([+-]?\d+)\))?$',
            header_text, re.IGNORECASE,
        )

        if not team_match:
            # Try simpler pattern: "Team A vs Team B - Pick"
            team_match = re.search(
                r'(.+?)\s+(?:over|vs\.?|v)\s+(.+?)(?:\s*\(([+-]?\d+)\))?$',
                header_text, re.IGNORECASE,
            )

        if not team_match:
            continue

        market_and_team_a = team_match.group(1).strip()
        team_b_raw = team_match.group(2).strip()
        odds_str = team_match.group(3)

        # Parse American odds
        odds_val = None
        if odds_str:
            try:
                american = int(odds_str)
                if american > 0:
                    odds_val = round(1 + american / 100, 2)
                else:
                    odds_val = round(1 + 100 / abs(american), 2)
            except ValueError:
                pass

        # Extract team names: market_and_team_a might be "Man City ML" or "Over 2.5 goals Man City"
        # team_b_raw might be "Arsenal (-120)" (already stripped odds) or "Arsenal"
        team_b = re.sub(r'\s*\([+-]?\d+\)\s*$', '', team_b_raw).strip()

        # Try to separate market from team_a: look for known market keywords at end
        market_kw = re.search(
            r'\b(ML|moneyline|spread|over|under|BTTS|draw|win|double chance|'
            r'total|handicap|goals|points|sets)\b.*$',
            market_and_team_a, re.IGNORECASE,
        )
        if market_kw:
            market_text = market_kw.group(0).strip()
            team_a = market_and_team_a[:market_kw.start()].strip()
        else:
            market_text = header_text
            team_a = market_and_team_a

        # Clean team names
        team_a = re.sub(r'\s+', ' ', team_a).strip()
        team_b = re.sub(r'\s+', ' ', team_b).strip()

        if not team_a or not team_b or len(team_a) < 2 or len(team_b) < 2:
            continue
        if _is_garbage_event(team_a, team_b):
            continue

        # Extract analysis paragraphs after the h2 until next h2 or end
        body_section = section[header_match.end():]
        # Stop at next h2 or at "Read our full" / "Also read" patterns
        next_section = re.search(r'<h2[^>]*>', body_section)
        if next_section:
            body_section = body_section[:next_section.start()]

        # Extract text from <p> and <span> tags
        paragraphs = re.findall(r'<(?:p|span)[^>]*>(.*?)</(?:p|span)>', body_section, re.DOTALL)
        reasoning_parts: list[str] = []
        for p in paragraphs:
            text = re.sub(r'<[^>]+>', ' ', p).strip()
            text = re.sub(r'\s+', ' ', text)
            # Decode HTML entities
            text = html_module.unescape(text)
            # Skip short fragments, promo text, "Read our full" links
            if len(text) < 20:
                continue
            if re.search(r'Read our full|Also read|gambling problem|promo|courtesy of .* at the time', text, re.IGNORECASE):
                continue
            reasoning_parts.append(text)

        reasoning_text = " ".join(reasoning_parts)[:1200]

        if len(reasoning_text) < 30:
            continue

        event_name = f"{team_a} vs {team_b}"
        picks.append(TipsterPick(
            source_site="PicksWise",
            tipster_name="PicksWise Expert",
            sport=sport,
            event=event_name,
            home_team=team_a,
            away_team=team_b,
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


def _extract_betideas_detail_urls(html: str) -> list[str]:
    """Extract individual match prediction URLs from BetIdeas listing page.

    BetIdeas match pages have pattern: /league/team-a-vs-team-b-1234567
    These are rendered in listing pages via AJAX (football-backend plugin).
    """
    urls: list[str] = []
    seen = set()
    for m in re.finditer(r'href="(https?://betideas\.com/[^"]*-vs-[^"]*)"', html):
        url = m.group(1).rstrip("/")
        if url not in seen:
            seen.add(url)
            urls.append(url)
    # Also check relative URLs
    for m in re.finditer(r'href="(/[^"]*-vs-[^"]*)"', html):
        url = f"https://betideas.com{m.group(1).rstrip('/')}"
        if url not in seen:
            seen.add(url)
            urls.append(url)
    return urls


def parse_betideas_detail_html(html: str, url: str) -> list[TipsterPick]:
    """Parse BetIdeas individual match prediction page for analysis.

    These pages have rich <p> content with match preview, H2H, form,
    key players, and betting analysis.
    """
    picks: list[TipsterPick] = []
    now_iso = datetime.now(timezone.utc).isoformat()
    sport = detect_sport("", url)

    # Extract teams from URL: /league/team-a-vs-team-b-1234567
    url_parts = url.rstrip("/").split("/")
    slug = url_parts[-1] if url_parts else ""
    vs_match = re.match(r'^(.+?)-vs-(.+?)(?:-(\d+))?$', slug)
    if not vs_match:
        return picks

    home = vs_match.group(1).replace("-", " ").strip().title()
    away = vs_match.group(2).replace("-", " ").strip().title()

    # Handle common abbreviations
    for abbr in ["Fc", "Sc", "Ac", "Utd"]:
        home = home.replace(f" {abbr}", f" {abbr.upper()}")
        away = away.replace(f" {abbr}", f" {abbr.upper()}")

    if _is_garbage_event(home, away):
        return picks

    # Extract paragraphs with analysis text
    paragraphs = re.findall(r'<p>([^<]+)</p>', html)
    reasoning_parts: list[str] = []
    for p in paragraphs:
        text = html_module.unescape(p).strip()
        text = re.sub(r'\s+', ' ', text)
        if len(text) < 30:
            continue
        # Skip boilerplate
        if re.search(
            r'gambling problem|responsible|18\+|sign up|bonus|cookie|'
            r'Betting odds description|fractional odds|following are the',
            text, re.IGNORECASE,
        ):
            continue
        reasoning_parts.append(text)

    reasoning_text = " ".join(reasoning_parts)[:1500]
    if len(reasoning_text) < 50:
        return picks

    # Try to extract odds from the page
    odds_val = None
    odds_match = re.search(r'class="fbbackend-decimal-odds[^"]*"[^>]*>([^<]+)', html)
    if odds_match:
        try:
            odds_val = float(odds_match.group(1).strip())
        except ValueError:
            pass

    event_name = f"{home} vs {away}"
    picks.append(TipsterPick(
        source_site="BetIdeas",
        tipster_name="BetIdeas Expert",
        sport=sport,
        event=event_name,
        home_team=home,
        away_team=away,
        competition="",
        market="Match Preview",
        market_type="outcome",
        direction="OTHER",
        odds=odds_val,
        reasoning=reasoning_text,
        accuracy_pct=None,
        confidence="medium",
        stats_cited=extract_stats_cited(reasoning_text),
        fetch_time=now_iso,
    ))

    return picks


def _extract_feedinco_pred_urls(html: str) -> list[str]:
    """Extract prediction page URLs from Feedinco homepage.

    Feedinco lists today's predictions as /predictions/YYYY-MM-DD/Team-vs-Team-prediction
    """
    urls: list[str] = []
    seen = set()
    for m in re.finditer(r'href="(/predictions/\d{4}-\d{2}-\d{2}/[^"]+prediction)"', html):
        path = m.group(1)
        full = f"https://www.feedinco.com{path}"
        if full not in seen:
            seen.add(full)
            urls.append(full)
    return urls


def parse_feedinco_detail_html(html: str, url: str) -> list[TipsterPick]:
    """Parse Feedinco individual prediction page — rich match preview.

    These Angular SSR pages have a "Match Preview" section with detailed
    multi-paragraph analysis including form, H2H, tactical insights, and
    a predicted score.
    """
    picks: list[TipsterPick] = []
    now_iso = datetime.now(timezone.utc).isoformat()
    sport = detect_sport("", url)

    # Extract teams from URL: /predictions/2026-05-18/Arsenal-vs-Burnley-prediction
    url_match = re.search(r'/predictions/[\d-]+/(.+?)-vs-(.+?)-prediction', url)
    if not url_match:
        return picks

    home = url_match.group(1).replace("-", " ").strip()
    away = url_match.group(2).replace("-", " ").strip()

    if _is_garbage_event(home, away):
        return picks

    # Find the Match Preview section and extract text
    preview_idx = html.find("Match Preview")
    if preview_idx < 0:
        preview_idx = html.find("match preview")
    if preview_idx < 0:
        # Try to find any substantial text block
        preview_idx = 0

    content_section = html[preview_idx:preview_idx + 20000]

    # Extract text from <p> tags (may contain <a> links inside)
    paragraphs = re.findall(r'<p[^>]*>(.*?)</p>', content_section, re.DOTALL)
    reasoning_parts: list[str] = []
    for p in paragraphs:
        # Strip HTML tags but keep text
        text = re.sub(r'<[^>]+>', ' ', p).strip()
        text = re.sub(r'\s+', ' ', text)
        text = html_module.unescape(text)
        if len(text) < 30:
            continue
        if re.search(r'gambling|cookie|privacy|sign up|18\+|terms', text, re.IGNORECASE):
            continue
        reasoning_parts.append(text)

    reasoning_text = " ".join(reasoning_parts)[:1500]
    if len(reasoning_text) < 50:
        return picks

    # Try to extract predicted score from the analysis
    market_text = "Match Preview"
    score_match = re.search(r'(\d+)[–-](\d+)\s*(?:correct score|in favor|prediction)', reasoning_text)
    if score_match:
        market_text = f"Correct Score: {home} {score_match.group(1)}-{score_match.group(2)} {away}"

    event_name = f"{home} vs {away}"
    picks.append(TipsterPick(
        source_site="Feedinco",
        tipster_name="Feedinco Expert",
        sport=sport,
        event=event_name,
        home_team=home,
        away_team=away,
        competition="",
        market=market_text,
        market_type=classify_market(market_text, reasoning_text),
        direction=extract_direction(market_text, reasoning_text),
        odds=None,
        reasoning=reasoning_text,
        accuracy_pct=None,
        confidence="medium",
        stats_cited=extract_stats_cited(reasoning_text),
        fetch_time=now_iso,
    ))

    return picks


def _extract_bettingclosed_pred_urls(html: str) -> list[str]:
    """Extract prediction page URLs from BettingClosed homepage."""
    urls: list[str] = []
    seen = set()
    for m in re.finditer(r'href="(/prediction/\d+/[^"]+)"', html):
        path = m.group(1)
        full = f"https://www.bettingclosed.com{path}"
        if full not in seen:
            seen.add(full)
            urls.append(full)
    return urls


def parse_bettingclosed_detail_html(html: str, url: str) -> list[TipsterPick]:
    """Parse BettingClosed prediction page for structured predictions.

    These pages have: 1x2 prediction, recommended bet, correct score,
    odds, and team names. No narrative analysis — just formatted prediction data.
    """
    picks: list[TipsterPick] = []
    now_iso = datetime.now(timezone.utc).isoformat()
    sport = detect_sport("", url)

    # Extract team names from page
    home_match = re.search(r'class="homeTeamName"[^>]*>([^<]+)', html)
    away_match = re.search(r'class="awayTeamName"[^>]*>([^<]+)', html)
    if not home_match or not away_match:
        # Try URL pattern: /prediction/id/team1-team2
        url_match = re.search(r'/prediction/\d+/(.+)', url)
        if url_match:
            slug = url_match.group(1)
            parts = slug.split("-", 1) if "-" in slug else [slug, ""]
            if len(parts) == 2:
                home = parts[0].replace("-", " ").title()
                away = parts[1].replace("-", " ").title()
            else:
                return picks
        else:
            return picks
    else:
        home = home_match.group(1).strip()
        away = away_match.group(1).strip()

    if _is_garbage_event(home, away):
        return picks

    # Extract predictions
    reasoning_parts: list[str] = []

    # Main prediction from h2: "Prediction Team1-Team2: 1x (Odd 1)"
    pred_match = re.search(r'<h2[^>]*>Prediction\s+[^:]+:\s*([^<(]+)\s*\(Odd\s*([\d.]+)\)', html)
    if not pred_match:
        # Fallback without odds
        pred_match = re.search(r'<h2[^>]*>Prediction\s+[^:]+:\s*([^<]+?)\s*</h2>', html)
    if pred_match:
        prediction = pred_match.group(1).strip()
        odds_str = pred_match.group(2) if pred_match.lastindex and pred_match.lastindex >= 2 else None
        reasoning_parts.append(f"Main prediction: {prediction}")
        if odds_str:
            reasoning_parts.append(f"Odds: {odds_str}")

    # Recommended prediction
    rec_match = re.search(r'Prediction\s+Recommended[^:]*:\s*<strong[^>]*>([^<]+)', html)
    if rec_match:
        recommended = rec_match.group(1).strip()
        reasoning_parts.append(f"Recommended bet: {recommended}")

    # Gol/NoGol prediction
    gol_match = re.search(r'Prediction\s+Gol/NoGol[^:]*:\s*<strong[^>]*>([^<]+)', html)
    if gol_match:
        reasoning_parts.append(f"BTTS prediction: {gol_match.group(1).strip()}")

    # Under/Over prediction
    ou_match = re.search(r'Prediction\s+Under/Over[^:]*:\s*<strong[^>]*>([^<]+)', html)
    if ou_match:
        reasoning_parts.append(f"Over/Under prediction: {ou_match.group(1).strip()}")

    # Correct score
    score_match = re.search(r'Prediction correct score:\s*</h\d>\s*(\d+)\s*-\s*(\d+)', html, re.DOTALL)
    if not score_match:
        score_match = re.search(r'correct score[^<]*<[^>]*>(\d+)\s*-\s*(\d+)', html, re.IGNORECASE)
    if score_match:
        reasoning_parts.append(f"Predicted correct score: {home} {score_match.group(1)}-{score_match.group(2)} {away}")

    # Extract competition
    comp_match = re.search(r'class="titleChampionTxt"[^>]*>.*?<a[^>]*>([^<]+)', html, re.DOTALL)
    competition = comp_match.group(1).strip() if comp_match else ""

    reasoning_text = ". ".join(reasoning_parts)
    if not reasoning_text:
        return picks

    # Try to parse odds from the prediction
    odds_val = None
    if pred_match and pred_match.lastindex and pred_match.lastindex >= 2:
        try:
            odds_val = float(pred_match.group(2))
        except (ValueError, IndexError):
            pass

    # Determine market from prediction
    market_text = pred_match.group(1).strip() if pred_match else "Match Prediction"

    event_name = f"{home} vs {away}"
    picks.append(TipsterPick(
        source_site="BettingClosed",
        tipster_name="BettingClosed",
        sport=sport,
        event=event_name,
        home_team=home,
        away_team=away,
        competition=competition,
        market=market_text,
        market_type=classify_market(market_text, reasoning_text),
        direction=extract_direction(market_text, reasoning_text),
        odds=odds_val,
        reasoning=reasoning_text,
        accuracy_pct=None,
        confidence="medium",
        stats_cited=[],
        fetch_time=now_iso,
    ))

    return picks


# Per-site fetch timeout (seconds) — prevents one slow site from blocking the whole run
SITE_FETCH_TIMEOUT = 45  # hard cap per site in ThreadPoolExecutor
PLAYWRIGHT_TIMEOUT = 15  # per-page Playwright navigation timeout
PLAYWRIGHT_RETRIES = 1   # single retry (was 2 — doubled wallclock for failing sites)


def _log(msg: str) -> None:
    """Print with immediate flush so agent sees output in real time."""
    print(msg, flush=True)


def fetch_site(site_config: dict, date: datetime) -> dict:
    """Fetch a single tipster site — Playwright first, HTTP fallback.

    Returns dict with: site_name, url, status, picks, error, fetch_time_ms.
    Uses TipsterPlaywrightClient for JS-rendered DOM extraction.
    Falls back to HTTP + regex parsing if Playwright unavailable.
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
        date_str = date.strftime("%Y-%m-%d")

        # --- PRIMARY: Playwright DOM extraction ---
        pw = _get_pw_client()
        if pw is not None:
            try:
                pw_picks = pw.fetch_site(site_config, date_str)
                if pw_picks:
                    result["picks"] = pw_picks
                    result["pick_count"] = len(pw_picks)
                    result["status"] = "success"

                    # --- Post-Playwright enrichment: follow detail pages for rich analysis ---
                    parser = site_config.get("parser", "generic")
                    elapsed = time.time() - start
                    remaining = SITE_FETCH_TIMEOUT - elapsed - 2

                    if remaining > 5 and parser in ("sportsgambler", "pickswise", "betideas", "feedinco", "bettingclosed"):
                        _log(f"  [tipster] {site_name}: enriching with detail pages ({remaining:.0f}s budget)")
                        try:
                            detail_urls = []
                            detail_parser = None
                            max_pages = 8

                            if parser == "betideas":
                                # BetIdeas: detail URLs come from Playwright picks (AJAX-rendered)
                                detail_urls = [p.get("detail_url") for p in pw_picks if p.get("detail_url")]
                                detail_parser = parse_betideas_detail_html
                                max_pages = 6
                            else:
                                # Other sites: fetch listing page via HTTP to extract detail URLs
                                if parser == "pickswise":
                                    listing_url = "https://www.pickswise.com/soccer/"
                                else:
                                    listing_url = site_config.get("url", site_config.get("urls", [""])[0] if "urls" in site_config else "")
                                listing_html = fetch(listing_url) if listing_url else ""

                                if parser == "sportsgambler":
                                    detail_urls = _extract_sportsgambler_pred_urls(listing_html) if listing_html else []
                                    detail_parser = parse_sportsgambler_detail_html
                                elif parser == "pickswise":
                                    detail_urls = _extract_pickswise_news_urls(listing_html) if listing_html else []
                                    detail_parser = parse_pickswise_news_html
                                    max_pages = 5
                                elif parser == "feedinco":
                                    detail_urls = _extract_feedinco_pred_urls(listing_html) if listing_html else []
                                    detail_parser = parse_feedinco_detail_html
                                elif parser == "bettingclosed":
                                    detail_urls = _extract_bettingclosed_pred_urls(listing_html) if listing_html else []
                                    detail_parser = parse_bettingclosed_detail_html

                            _log(f"  [tipster] {site_name}: found {len(detail_urls)} detail pages to follow")
                            enriched = 0
                            for detail_url in detail_urls[:max_pages]:
                                if time.time() - start > SITE_FETCH_TIMEOUT - 3:
                                    break
                                try:
                                    detail_html = fetch(detail_url)
                                    if detail_html and len(detail_html) > 3000:
                                        detail_picks = detail_parser(detail_html, detail_url)
                                        if detail_picks:
                                            result["picks"].extend([p.to_dict() for p in detail_picks])
                                            enriched += len(detail_picks)
                                except Exception as e:
                                    _log(f"  [tipster] {site_name}: detail page failed: {detail_url} — {e}")
                                    continue
                            if enriched:
                                result["pick_count"] = len(result["picks"])
                                _log(f"  [tipster] {site_name}: enriched with {enriched} detail picks (total: {result['pick_count']})")
                        except Exception as e:
                            _log(f"  [tipster] {site_name}: detail enrichment failed: {e}")

                    result["fetch_time_ms"] = int((time.time() - start) * 1000)
                    return result
                else:
                    _log(f"  [tipster] {site_name}: Playwright returned 0 picks, trying HTTP fallback")
            except Exception as e:
                _log(f"  [tipster] {site_name}: Playwright failed ({e}), trying HTTP fallback")

        # --- FALLBACK: HTTP + regex parsing ---
        urls = []
        if "url_builder" in site_config and site_config["url_builder"] == "zawodtyper":
            urls = [build_zawodtyper_url(date)]
        elif "urls" in site_config:
            urls = site_config["urls"]
        elif "url" in site_config:
            urls = [site_config["url"]]

        all_picks = []
        fetch_errors = 0
        for url_idx, url in enumerate(urls):
            elapsed = time.time() - start
            if elapsed > SITE_FETCH_TIMEOUT - 5:
                _log(f"  [tipster] {site_name}: time budget exhausted ({elapsed:.0f}s), skipping remaining URLs")
                break
            if len(urls) > 1:
                _log(f"  [tipster] {site_name}: fetching URL {url_idx + 1}/{len(urls)} ({elapsed:.0f}s elapsed)")
            result["url"] = url
            try:
                html = fetch(url)
                if not html or len(html) < 100:
                    _log(f"  [tipster] {site_name}: {url} returned {len(html) if html else 0} bytes (skipped)")
                    continue

                parser = site_config.get("parser", "generic")
                if parser == "zawodtyper":
                    picks = parse_zawodtyper_html(html)
                elif parser == "pickswise":
                    picks = parse_pickswise_html(html, url)
                    # Follow news article pages (SSR — rich analysis text)
                    news_urls = _extract_pickswise_news_urls(html)
                    _log(f"  [tipster] {site_name}: found {len(news_urls)} news articles to follow")
                    for nidx, news_url in enumerate(news_urls[:5]):
                        if time.time() - start > SITE_FETCH_TIMEOUT - 5:
                            _log(f"  [tipster] {site_name}: time budget reached at {nidx}/{len(news_urls)} articles")
                            break
                        try:
                            news_html = fetch(news_url)
                            if news_html and len(news_html) > 5000:
                                news_picks = parse_pickswise_news_html(news_html, news_url)
                                if news_picks:
                                    picks.extend(news_picks)
                                    _log(f"    ✓ {news_url.split('/')[-2][:50]}: {len(news_picks)} picks with analysis")
                        except Exception as e:
                            _log(f"    ✗ {news_url.split('/')[-2][:50]}: {str(e)[:60]}")
                            continue
                elif parser == "sportsgambler":
                    picks = parse_sportsgambler_html(html)
                    # Follow individual prediction pages for rich analysis
                    detail_urls = _extract_sportsgambler_pred_urls(html)
                    _log(f"  [tipster] {site_name}: found {len(detail_urls)} prediction pages to follow")
                    for didx, detail_url in enumerate(detail_urls[:8]):
                        if time.time() - start > SITE_FETCH_TIMEOUT - 5:
                            _log(f"  [tipster] {site_name}: time budget reached, stopping at {didx}/{len(detail_urls)} detail pages")
                            break
                        try:
                            detail_html = fetch(detail_url)
                            if detail_html and len(detail_html) > 5000:
                                detail_picks = parse_sportsgambler_detail_html(detail_html, detail_url)
                                if detail_picks:
                                    picks.extend(detail_picks)
                                    _log(f"    ✓ {detail_url.split('/')[-2]}: {len(detail_picks)} picks with analysis")
                        except Exception as e:
                            _log(f"    ✗ {detail_url.split('/')[-2]}: {str(e)[:80]}")
                            continue
                elif parser == "betideas":
                    picks = parse_generic_tipster_html(html, site_name, url)
                    # Follow individual match detail pages for rich analysis
                    detail_urls = _extract_betideas_detail_urls(html)
                    _log(f"  [tipster] {site_name}: found {len(detail_urls)} match detail pages")
                    for didx, detail_url in enumerate(detail_urls[:6]):
                        if time.time() - start > SITE_FETCH_TIMEOUT - 5:
                            _log(f"  [tipster] {site_name}: time budget reached at {didx}/{len(detail_urls)} pages")
                            break
                        try:
                            detail_html = fetch(detail_url)
                            if detail_html and len(detail_html) > 5000:
                                detail_picks = parse_betideas_detail_html(detail_html, detail_url)
                                if detail_picks:
                                    picks.extend(detail_picks)
                                    _log(f"    ✓ {detail_url.split('/')[-1][:50]}: {len(detail_picks)} picks with analysis")
                        except Exception as e:
                            _log(f"    ✗ {detail_url.split('/')[-1][:50]}: {str(e)[:60]}")
                            continue
                elif parser == "feedinco":
                    picks = parse_generic_tipster_html(html, site_name, url)
                    # Follow individual prediction pages for rich analysis
                    pred_urls = _extract_feedinco_pred_urls(html)
                    _log(f"  [tipster] {site_name}: found {len(pred_urls)} prediction pages")
                    for pidx, pred_url in enumerate(pred_urls[:8]):
                        if time.time() - start > SITE_FETCH_TIMEOUT - 5:
                            _log(f"  [tipster] {site_name}: time budget reached at {pidx}/{len(pred_urls)} pages")
                            break
                        try:
                            pred_html = fetch(pred_url)
                            if pred_html and len(pred_html) > 5000:
                                pred_picks = parse_feedinco_detail_html(pred_html, pred_url)
                                if pred_picks:
                                    picks.extend(pred_picks)
                                    _log(f"    ✓ {pred_url.split('/')[-1][:50]}: {len(pred_picks)} picks")
                        except Exception as e:
                            _log(f"    ✗ {pred_url.split('/')[-1][:50]}: {str(e)[:60]}")
                            continue
                elif parser == "bettingclosed":
                    picks = parse_generic_tipster_html(html, site_name, url)
                    # Follow individual prediction pages for structured data
                    pred_urls = _extract_bettingclosed_pred_urls(html)
                    _log(f"  [tipster] {site_name}: found {len(pred_urls)} prediction pages")
                    for pidx, pred_url in enumerate(pred_urls[:8]):
                        if time.time() - start > SITE_FETCH_TIMEOUT - 5:
                            _log(f"  [tipster] {site_name}: time budget reached at {pidx}/{len(pred_urls)} pages")
                            break
                        try:
                            pred_html = fetch(pred_url)
                            if pred_html and len(pred_html) > 3000:
                                pred_picks = parse_bettingclosed_detail_html(pred_html, pred_url)
                                if pred_picks:
                                    picks.extend(pred_picks)
                                    _log(f"    ✓ {pred_url.split('/')[-1][:40]}: {len(pred_picks)} picks")
                        except Exception as e:
                            _log(f"    ✗ {pred_url.split('/')[-1][:40]}: {str(e)[:60]}")
                            continue
                else:
                    picks = parse_generic_tipster_html(html, site_name, url)

                if not picks:
                    _log(f"  [tipster] {site_name}: {url} fetched {len(html)} bytes but parser returned 0 picks")

                all_picks.extend(picks)

            except Exception as e:
                result["error"] = f"Fetch failed for {url}: {str(e)[:200]}"
                fetch_errors += 1
                continue

        result["picks"] = [p.to_dict() for p in all_picks]
        result["pick_count"] = len(all_picks)
        # Mark as "error" if all URLs failed with fetch errors, "empty" if fetched but no picks parsed
        if all_picks:
            result["status"] = "success"
        elif fetch_errors > 0 and fetch_errors >= len(urls):
            result["status"] = "error"
        else:
            result["status"] = "empty"

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
            # Require >=2 unique sources for positive boost (single-source = no consensus)
            "confidence_adj": (
                +0.5 if agreement_pct >= 70 and total >= 2
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

    # Merge Gemini picks and skip sites already fetched by Gemini
    all_results = []
    all_picks = list(gemini_picks)
    errors = []
    gemini_sites = {p.get("source_site", "") for p in gemini_picks}
    sites_to_fetch = [s for s in TIPSTER_SITES if s["name"] not in gemini_sites]

    if gemini_sites:
        _log(f"[tipster] Gemini already fetched {len(gemini_sites)} sites, skipping: {', '.join(gemini_sites)}")

    # Parallel fetch — NOTE: Playwright is NOT thread-safe, so if Playwright is active,
    # the per-site fetch_site() will use Playwright sequentially (one browser context at a time)
    # and only fall back to HTTP for parallel fetching when Playwright is unavailable.

    # Check if Playwright is available — if so, fetch sequentially for safety
    pw = _get_pw_client()
    if pw is not None:
        _log(f"[tipster] Playwright active — fetching {len(sites_to_fetch)} sites sequentially")
        for site in sites_to_fetch:
            result = fetch_site(site, date_obj)
            all_results.append(result)
            all_picks.extend(result.get("picks", []))
            status = result["status"]
            count = result["pick_count"]
            ms = result["fetch_time_ms"]
            _log(f"  [{status}] {site['name']}: {count} picks ({ms}ms)")
            if result.get("error"):
                errors.append(f"{site['name']}: {result['error']}")
    else:
        _log(f"[tipster] No Playwright — fetching {len(sites_to_fetch)} sites in parallel ({max_workers} workers)")
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(fetch_site, site, date_obj): site["name"]
                for site in sites_to_fetch
            }

            try:
                for future in as_completed(futures, timeout=SITE_FETCH_TIMEOUT + 10):
                    site_name = futures[future]
                    try:
                        result = future.result(timeout=5)
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

    # Save tipster picks, consensus, and pipeline step to DB (R2) via TipsterRepo
    try:
        from bet.db.connection import get_db
        from bet.db.repositories import PipelineRepo, TipsterRepo
        with get_db() as conn:
            tipster_repo = TipsterRepo(conn)
            picks_saved = tipster_repo.save_picks(date, all_picks)
            consensus_saved = tipster_repo.save_consensus(date, consensus)

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
        _log(f"[tipster] DB: saved {picks_saved} picks + {consensus_saved} consensus entries")
    except Exception as e:
        print(f"  ⚠ DB tipster save failed (non-fatal): {e}")

    _cleanup_pw_client()

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
