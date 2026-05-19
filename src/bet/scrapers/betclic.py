"""Betclic.pl market availability scraper.

Production-grade module for detecting which betting markets are available
on Betclic for a given event/competition. Uses curl_cffi with Chrome
impersonation to fetch Angular SSR pages and extract market data from
embedded script tags.

Architecture:
    - BetclicSession: HTTP session with retries, rate limiting, impersonation
    - BetclicMarketChecker: High-level API for market availability checking
    - DB persistence: stores observations in betclic_markets table
    - Competition registry: maps known leagues to Betclic URLs

Key insight (2026-05-18):
    Betclic adds statistical markets (corners, cards, shots, fouls) via
    "Statystyki" tab only ~24-48h before kickoff. Matches further out have
    only basic markets. Validation MUST run on the betting day.

This module does NOT scrape odds (forbidden per R12 — all picks CONDITIONAL).
It detects WHICH MARKET TYPES EXIST so the pipeline can avoid recommending
markets that don't exist on Betclic.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

try:
    from curl_cffi import requests as c_requests
    from curl_cffi.requests import Session as CurlSession
except ImportError:
    c_requests = None
    CurlSession = None
    logger.warning("curl_cffi not installed — betclic market checker unavailable")


# ═══════════════════════════════════════════════════════════════════════════════
# CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

BASE_URL = "https://www.betclic.pl"

# Sport URL segments used in match page URLs
SPORT_URL_SEGMENTS = {
    "football": "pilka-nozna-sfootball",
    "tennis": "tenis-stennis",
    "basketball": "koszykowka-sbasketball",
    "volleyball": "siatkowka-svolleyball",
    "hockey": "hokej-sice_hockey",
}

# Sport listing page slugs (different from URL segments!)
SPORT_LISTING_SLUGS = {
    "football": "pilka-nozna-s1",
    "tennis": "tenis-s2",
    "basketball": "koszykowka-s4",
    "volleyball": "siatkowka-s8",
    "hockey": "hokej-na-lodzie-s13",
}

# Tab name → pipeline market categories
TAB_MARKET_CATEGORIES = {
    "Statystyki": ["corners", "corners_total", "corners_1h", "cards_total",
                   "yellow_cards", "red_card", "fouls", "shots_on_target",
                   "shots_total", "offsides"],
    "Gole": ["goals_total", "goals_1h", "goals_2h", "btts", "team_goals",
             "goals_total_regulation"],
    "Wynik": ["match_winner", "double_chance", "draw_no_bet"],
    "Wynik / Handicap": ["handicap", "asian_handicap"],
    "Strzelcy": ["goalscorer", "anytime_goalscorer"],
    "Metoda gola": ["goal_method"],
    "MyCombi": ["bet_builder", "mycombi"],
    "Sety": ["sets_total", "set_winner"],
    "Gemy": ["games_total", "game_handicap"],
    "Punkty": ["points_total", "quarter_total", "half_total"],
}

# Betclic PL market name → pipeline market type
MARKET_NAME_TO_TYPE = {
    # Football: statistical
    "1. połowa - Rzuty rożne": "corners_1h",
    "Rzuty rożne": "corners_total",
    "Rzuty rożne Powyżej/Poniżej": "corners_total",
    "Liczba celnych strzałów zawodnika (OPTA)": "shots_on_target_player",
    "Czerwona kartka": "red_card",
    "Żółte kartki": "yellow_cards",
    "Kartki": "cards_total",
    "Faule": "fouls",
    # Football: goals
    "Gole Powyżej/Poniżej": "goals_total",
    "Gole 1. połowa": "goals_1h",
    "Gole 2. połowa": "goals_2h",
    "Oba zespoły strzelą gola": "btts",
    "Oba zespoły strzelą gola lub Powyżej 2,5 gola w meczu": "btts_or_over",
    "Liczba goli (regulaminowy czas)": "goals_total_regulation",
    # Football: outcome
    "Wynik meczu (z wyłączeniem dogrywki)": "match_winner",
    "Podwójna Szansa": "double_chance",
    "Handicap": "handicap",
    "Dokładny wynik": "correct_score",
    # Tennis
    "Sety Powyżej/Poniżej": "sets_total",
    "Gemy Powyżej/Poniżej": "games_total",
    "Asy Powyżej/Poniżej": "aces",
    "Podwójne błędy Powyżej/Poniżej": "double_faults",
    # Basketball
    "Punkty Powyżej/Poniżej": "points_total",
    "Punkty 1. połowa": "points_1h",
    # Volleyball
    "Sety": "sets_total",
    "Punkty": "points_total",
}

# Pipeline market type → Betclic detection info
MARKET_DETECTION_RULES = {
    # Football statistical
    "corners": {"requires_tab": "Statystyki", "keywords": ["rożn", "corner"]},
    "corners_total": {"requires_tab": "Statystyki", "keywords": ["rożn"]},
    "corners_1h": {"requires_tab": "Statystyki", "keywords": ["rożn", "połowa"]},
    "cards_total": {"requires_tab": "Statystyki", "keywords": ["kartek", "kartk"]},
    "yellow_cards": {"requires_tab": "Statystyki", "keywords": ["żółt"]},
    "red_card": {"requires_tab": "Statystyki", "keywords": ["czerwona"]},
    "fouls": {"requires_tab": "Statystyki", "keywords": ["faul"]},
    "shots_on_target": {"requires_tab": "Statystyki", "keywords": ["strzał", "celny"]},
    "shots_total": {"requires_tab": "Statystyki", "keywords": ["strzał"]},
    "offsides": {"requires_tab": "Statystyki", "keywords": ["spalon"]},
    # Football goals — always available when event has markets
    "goals_total": {"requires_tab": "Gole", "keywords": ["gol", "powyżej"]},
    "goals_1h": {"requires_tab": "Gole", "keywords": ["połowa", "gol"]},
    "goals_2h": {"requires_tab": "Gole", "keywords": ["połowa", "gol"]},
    "btts": {"requires_tab": "Gole", "keywords": ["oba"]},
    "team_goals": {"requires_tab": "Gole", "keywords": ["liczba goli"]},
    # Football outcome
    "match_winner": {"requires_tab": "Wynik", "keywords": ["wynik"]},
    "double_chance": {"requires_tab": "Wynik", "keywords": ["szansa", "podwójn"]},
    "handicap": {"requires_tab": "Wynik / Handicap", "keywords": ["handicap"]},
    # Tennis
    "games_total": {"requires_tab": None, "keywords": ["gem"]},
    "sets_total": {"requires_tab": None, "keywords": ["set"]},
    "aces": {"requires_tab": "Statystyki", "keywords": ["as", "aces"]},
    "double_faults": {"requires_tab": "Statystyki", "keywords": ["podwójn", "błęd"]},
    # Basketball
    "points_total": {"requires_tab": None, "keywords": ["punkt"]},
    # Volleyball
    "sets": {"requires_tab": None, "keywords": ["set"]},
    "points": {"requires_tab": None, "keywords": ["punkt"]},
}

# Non-market tabs to filter out
NON_MARKET_TABS = frozenset([
    "Zakłady sportowe", "Live", "Misje", "Gry karciane", "Produkty",
])

# Rate limits
MIN_REQUEST_DELAY = 0.8   # minimum seconds between requests
MAX_RETRIES = 3
RETRY_BACKOFF = 2.0       # exponential backoff multiplier

# Cache validity
CACHE_HOURS = 6  # don't re-fetch same event within this window

# Market count threshold
STATISTICAL_MARKETS_THRESHOLD = 200


# ═══════════════════════════════════════════════════════════════════════════════
# COMPETITION REGISTRY
# ═══════════════════════════════════════════════════════════════════════════════

# Maps (sport, league_name_pattern) → Betclic competition URL path
# Used to discover events from specific competitions we care about
COMPETITION_REGISTRY = {
    "football": [
        ("Premier League", "/pilka-nozna-sfootball/premier-league-c3"),
        ("La Liga", "/pilka-nozna-sfootball/hiszpania-laliga-c4"),
        ("Serie A", "/pilka-nozna-sfootball/wlochy-serie-a-c7"),
        ("Bundesliga", "/pilka-nozna-sfootball/niemcy-bundesliga-c5"),
        ("Ligue 1", "/pilka-nozna-sfootball/francja-ligue-1-c6"),
        ("Ekstraklasa", "/pilka-nozna-sfootball/polska-ekstraklasa-c221"),
        ("Eredivisie", "/pilka-nozna-sfootball/holandia-eredivisie-c10"),
        ("Liga Mistrzów", "/pilka-nozna-sfootball/liga-mistrzow-c65"),
        ("Liga Europy", "/pilka-nozna-sfootball/liga-europy-c3453"),
        ("Liga Konferencji", "/pilka-nozna-sfootball/liga-konferencji-c4698"),
        ("Championship", "/pilka-nozna-sfootball/anglia-championship-c36"),
        ("Serie B", "/pilka-nozna-sfootball/wlochy-serie-b-c22"),
        ("2. Bundesliga", "/pilka-nozna-sfootball/niemcy-2-bundesliga-c39"),
        ("DFB Pokal", "/pilka-nozna-sfootball/niemcy-puchar-c55"),
        ("Puchar Króla", "/pilka-nozna-sfootball/hiszpania-puchar-krola-c66"),
        ("MLS", "/pilka-nozna-sfootball/usa-mls-c231"),
        ("Brasileirão", "/pilka-nozna-sfootball/brazylia-serie-a-c18"),
        ("Liga MX", "/pilka-nozna-sfootball/meksyk-liga-mx-c229"),
        ("Allsvenskan", "/pilka-nozna-sfootball/szwecja-allsvenskan-c13"),
        ("Superliga Dania", "/pilka-nozna-sfootball/dania-superliga-c77"),
    ],
    "tennis": [
        ("Roland Garros", "/tenis-stennis/atp-roland-garros-c1119"),
        ("Roland Garros WTA", "/tenis-stennis/wta-roland-garros-c1120"),
        ("Wimbledon", "/tenis-stennis/atp-wimbledon-c89"),
        ("US Open", "/tenis-stennis/atp-us-open-c1081"),
        ("Australian Open", "/tenis-stennis/atp-australian-open-c152"),
        ("ATP Masters", "/tenis-stennis/atp-masters-1000-c1135"),
    ],
    "basketball": [
        ("NBA", "/koszykowka-sbasketball/usa-nba-c19"),
        ("Euroleague", "/koszykowka-sbasketball/euroliga-c60"),
        ("PLK", "/koszykowka-sbasketball/polska-plk-c2285"),
        ("BBL", "/koszykowka-sbasketball/niemcy-bundesliga-c1263"),
        ("ACB", "/koszykowka-sbasketball/hiszpania-liga-acb-c118"),
    ],
    "volleyball": [
        ("PlusLiga", "/siatkowka-svolleyball/polska-plusliga-c2371"),
        ("Serie A Volley", "/siatkowka-svolleyball/wlochy-superlega-c2497"),
        ("Bundesliga Volley", "/siatkowka-svolleyball/niemcy-bundesliga-c2476"),
    ],
    "hockey": [
        ("NHL", "/hokej-sice_hockey/usa-nhl-c20"),
        ("KHL", "/hokej-sice_hockey/rosja-khl-c2365"),
        ("Mistrzostwa Świata", "/hokej-sice_hockey/mistrzostwa-swiata-c108"),
        ("SHL", "/hokej-sice_hockey/szwecja-shl-c2364"),
    ],
}

# Competitions known to NEVER have statistical markets regardless of timing
NEVER_HAS_STATISTICS = {
    "hockey": {"all"},  # Hockey on Betclic never has corners/cards/shots/fouls
}


# ═══════════════════════════════════════════════════════════════════════════════
# DATA CLASSES
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class BetclicMarketInfo:
    """Market availability information for a single event."""
    event_id: str = ""
    event_name: str = ""
    event_url: str = ""
    sport: str = ""
    competition_id: str = ""
    competition_name: str = ""
    match_date: str = ""
    tabs: list[str] = field(default_factory=list)
    market_names: list[str] = field(default_factory=list)
    open_market_count: int = 0
    has_statistics_tab: bool = False
    has_corners: bool = False
    has_cards: bool = False
    has_shots: bool = False
    has_fouls: bool = False
    fetched_at: str = ""

    def to_dict(self) -> dict:
        return {
            "event_id": self.event_id,
            "event_name": self.event_name,
            "event_url": self.event_url,
            "sport": self.sport,
            "competition_id": self.competition_id,
            "competition_name": self.competition_name,
            "match_date": self.match_date,
            "tabs": self.tabs,
            "market_names": self.market_names,
            "open_market_count": self.open_market_count,
            "has_statistics_tab": self.has_statistics_tab,
            "has_corners": self.has_corners,
            "has_cards": self.has_cards,
            "has_shots": self.has_shots,
            "has_fouls": self.has_fouls,
            "fetched_at": self.fetched_at,
        }

    def is_market_available(self, market_type: str) -> tuple[bool | None, str]:
        """Check if a specific pipeline market type is available.

        Returns (available, explanation).
        available: True/False/None (unknown).
        """
        rule = MARKET_DETECTION_RULES.get(market_type)
        if not rule:
            return None, f"No detection rule for '{market_type}'"

        required_tab = rule["requires_tab"]
        keywords = rule["keywords"]

        # Check if sport never has this market category
        sport_never = NEVER_HAS_STATISTICS.get(self.sport, set())
        if sport_never and ("all" in sport_never or market_type in sport_never):
            if required_tab == "Statystyki":
                return False, f"❌ {self.sport} never has statistical markets on Betclic"

        # Check tab requirement
        if required_tab == "Statystyki":
            if not self.has_statistics_tab:
                return False, f"❌ No 'Statystyki' tab — {market_type} unavailable"
            # If Statystyki tab IS present, all stat markets are available
            return True, "✅ Statystyki tab present → market available"
        elif required_tab and required_tab not in self.tabs:
            # For non-Statystyki tabs, check if tab exists
            if self.open_market_count == 0:
                return None, "⚠️ No market data loaded (event may not be open yet)"
            return False, f"❌ Tab '{required_tab}' not found"

        # Keyword check in market names
        market_text = " ".join(self.market_names).lower()
        if any(kw in market_text for kw in keywords):
            return True, "✅ Market confirmed in market names"

        # Tab present → likely available
        if required_tab and required_tab in self.tabs:
            return True, f"✅ Tab '{required_tab}' present"

        # Fallback: check market count
        if self.open_market_count >= STATISTICAL_MARKETS_THRESHOLD:
            return True, f"✅ High market count ({self.open_market_count}) suggests availability"

        return None, "⚠️ Cannot confirm availability"


# ═══════════════════════════════════════════════════════════════════════════════
# HTTP SESSION
# ═══════════════════════════════════════════════════════════════════════════════

class BetclicSession:
    """HTTP session for Betclic with retries, rate limiting, and impersonation."""

    def __init__(self, delay: float = MIN_REQUEST_DELAY):
        if CurlSession is None:
            raise ImportError("curl_cffi required — install with: pip install curl_cffi")
        self._session = CurlSession(impersonate="chrome110")
        self._session.headers.update({
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pl-PL,pl;q=0.9,en-US;q=0.7",
            "Cache-Control": "no-cache",
        })
        self._delay = delay
        self._last_request_time = 0.0
        self._request_count = 0

    def get(self, url: str, timeout: int = 20) -> Optional[str]:
        """Fetch URL with retry and rate limiting. Returns HTML or None."""
        self._rate_limit()

        for attempt in range(MAX_RETRIES):
            try:
                r = self._session.get(url, timeout=timeout)
                self._request_count += 1

                if r.status_code == 200:
                    return r.text
                elif r.status_code == 429:
                    wait = RETRY_BACKOFF ** (attempt + 1)
                    logger.warning(f"Rate limited (429), waiting {wait:.1f}s...")
                    time.sleep(wait)
                    continue
                elif r.status_code in (403, 503):
                    logger.warning(f"HTTP {r.status_code} for {url} — blocked or maintenance")
                    return None
                else:
                    logger.warning(f"HTTP {r.status_code} for {url}")
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(RETRY_BACKOFF ** attempt)
                    continue
            except Exception as e:
                logger.error(f"Request error (attempt {attempt+1}): {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_BACKOFF ** attempt)
                continue

        return None

    def _rate_limit(self):
        """Enforce minimum delay between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self._delay:
            time.sleep(self._delay - elapsed)
        self._last_request_time = time.time()

    @property
    def request_count(self) -> int:
        return self._request_count

    def close(self):
        """Close the session."""
        if self._session:
            self._session.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


# ═══════════════════════════════════════════════════════════════════════════════
# PARSER
# ═══════════════════════════════════════════════════════════════════════════════

def parse_event_page(html: str) -> Optional[BetclicMarketInfo]:
    """Parse a Betclic event page HTML and extract market availability.

    Extraction strategy:
    1. Tabs from HTML class="tab_label" (always present)
    2. Match metadata from Angular state script (~500K chars)
    3. Market names from "marketId"/"marketName" pairs in script
    4. Statistical market detection from tab presence + keywords
    """
    # 1. Extract tabs
    all_tabs = re.findall(r'class="tab_label"[^>]*>([^<]+)', html)
    market_tabs = [t for t in all_tabs if t not in NON_MARKET_TABS]

    info = BetclicMarketInfo(
        tabs=market_tabs,
        has_statistics_tab="Statystyki" in all_tabs,
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )

    # 2. Find the Angular state script (large, contains "marketName")
    market_script = None
    for m in re.finditer(r"<script[^>]*>(.*?)</script>", html, re.DOTALL):
        content = m.group(1)
        if "marketName" in content and len(content) > 30000:
            market_script = content
            break

    if not market_script:
        # Still useful: we have tabs. Try title for event name.
        title = re.search(r"<title>([^<]+)</title>", html)
        if title:
            info.event_name = title.group(1).split(" - Betclic")[0].strip()
        return info

    # 3. Extract match metadata
    match_m = re.search(
        r'"matchId":"(\d+)","(?:matchN|n)ame":"([^"]+)","matchDateUtc":"([^"]+)"',
        market_script,
    )
    if match_m:
        info.event_id = match_m.group(1)
        info.event_name = match_m.group(2)
        info.match_date = match_m.group(3)

    comp_m = re.search(
        r'"competition":\{"id":"(\d+)","name":"([^"]+)","sport":\{"code":"([^"]+)"',
        market_script,
    )
    if comp_m:
        info.competition_id = comp_m.group(1)
        info.competition_name = comp_m.group(2)
        info.sport = comp_m.group(3)

    # Open market count
    omc = re.search(r'"openMarketCount":(\d+)', market_script)
    if omc:
        info.open_market_count = int(omc.group(1))

    # 4. Extract market names
    market_names = set()
    for _, name in re.findall(r'"marketId":"(\d+)","marketName":"([^"]+)"', market_script):
        market_names.add(name)

    # Also search "name" fields that match market keywords
    market_keywords = [
        "gol", "wynik", "rzut", "rożn", "kartek", "kartk", "faul",
        "strzał", "handicap", "szans", "połow", "set", "gem", "punkt",
        "aces", "podwójn", "błęd",
    ]
    for name in re.findall(r'"name":"([^"]+)"', market_script):
        if any(kw in name.lower() for kw in market_keywords) and len(name) > 3:
            market_names.add(name)

    info.market_names = sorted(market_names)

    # 5. Detect statistical market availability
    if info.has_statistics_tab:
        info.has_corners = True
        info.has_cards = True
        info.has_shots = True
        info.has_fouls = True
    else:
        all_text = " ".join(info.market_names).lower()
        info.has_corners = "rożn" in all_text or "corner" in all_text
        info.has_cards = "kartek" in all_text or "kartk" in all_text or "czerwona" in all_text
        info.has_shots = "strzał" in all_text or "celny" in all_text
        info.has_fouls = "faul" in all_text

    return info


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN CHECKER CLASS
# ═══════════════════════════════════════════════════════════════════════════════

class BetclicMarketChecker:
    """High-level API for checking Betclic market availability.

    Usage:
        checker = BetclicMarketChecker(betting_date="2026-05-18")
        # Check single event
        info = checker.check_event("/pilka-nozna-sfootball/premier-league-c3/...")
        # Check competition
        events = checker.check_competition("football", "Premier League")
        # Full scan
        results = checker.scan_all_sports()
        # Persist to DB
        checker.save_to_db()
    """

    def __init__(self, betting_date: str, db_conn: Optional[sqlite3.Connection] = None):
        self._date = betting_date
        self._session = BetclicSession()
        self._results: list[BetclicMarketInfo] = []
        self._db = db_conn
        self._cache: dict[str, BetclicMarketInfo] = {}  # event_url → info

    @property
    def results(self) -> list[BetclicMarketInfo]:
        return self._results

    def check_event(self, event_path: str) -> Optional[BetclicMarketInfo]:
        """Fetch and parse a single event page."""
        # Check cache
        if event_path in self._cache:
            return self._cache[event_path]

        # Check DB cache
        if self._db:
            cached = self._load_from_db(event_path)
            if cached:
                self._cache[event_path] = cached
                return cached

        url = f"{BASE_URL}{event_path}"
        html = self._session.get(url)
        if not html:
            return None

        info = parse_event_page(html)
        if info:
            info.event_url = event_path
            self._cache[event_path] = info
            self._results.append(info)

        return info

    def discover_competition_events(self, competition_url: str) -> list[str]:
        """Get all event URLs from a competition page."""
        url = f"{BASE_URL}{competition_url}"
        html = self._session.get(url)
        if not html:
            return []

        links = re.findall(r'href="(/[^"]*-m\d+)"', html)
        return list(set(links))

    def check_competition(self, sport: str, league_pattern: str) -> list[BetclicMarketInfo]:
        """Check all events in a competition matching the pattern."""
        registry = COMPETITION_REGISTRY.get(sport, [])
        comp_url = None
        for name, url in registry:
            if league_pattern.lower() in name.lower():
                comp_url = url
                break

        if not comp_url:
            logger.warning(f"No Betclic URL for {sport}/{league_pattern}")
            return []

        event_paths = self.discover_competition_events(comp_url)
        logger.info(f"  {league_pattern}: {len(event_paths)} events found")

        results = []
        for path in event_paths:
            info = self.check_event(path)
            if info:
                results.append(info)

        return results

    def scan_sport(self, sport: str, max_events: int = 30) -> list[BetclicMarketInfo]:
        """Scan a single sport: discover events from listing + registered competitions."""
        results = []
        event_paths = set()

        # From sport listing page (shows live + imminent matches)
        slug = SPORT_LISTING_SLUGS.get(sport)
        if slug:
            url = f"{BASE_URL}/{slug}"
            html = self._session.get(url)
            if html:
                links = re.findall(r'href="(/[^"]*-m\d+)"', html)
                event_paths.update(links)

        # From registered competitions
        for comp_name, comp_url in COMPETITION_REGISTRY.get(sport, []):
            comp_events = self.discover_competition_events(comp_url)
            event_paths.update(comp_events)
            if len(event_paths) >= max_events * 2:
                break

        logger.info(f"  {sport}: {len(event_paths)} unique events discovered")

        # Check each event
        checked = 0
        for path in list(event_paths)[:max_events]:
            info = self.check_event(path)
            if info:
                results.append(info)
            checked += 1
            if checked % 10 == 0:
                logger.info(f"    checked {checked}/{min(len(event_paths), max_events)}")

        return results

    def scan_all_sports(
        self,
        sports: list[str] | None = None,
        max_events_per_sport: int = 25,
    ) -> list[BetclicMarketInfo]:
        """Full scan across all (or specified) sports."""
        if sports is None:
            sports = list(SPORT_URL_SEGMENTS.keys())

        all_results = []
        for sport in sports:
            logger.info(f"Scanning {sport}...")
            sport_results = self.scan_sport(sport, max_events=max_events_per_sport)
            all_results.extend(sport_results)
            logger.info(f"  → {len(sport_results)} events checked, "
                       f"{sum(1 for r in sport_results if r.has_statistics_tab)} with Statystyki tab")

        return all_results

    def validate_picks(self, picks: list[dict]) -> list[dict]:
        """Validate coupon picks against observed market availability.

        Each pick should have:
            - 'event' or 'home_team'+'away_team': event identifier
            - 'market_type': pipeline market type (e.g., 'corners_total')

        Returns picks annotated with:
            - 'betclic_available': True/False/None
            - 'betclic_note': explanation
            - 'betclic_open_markets': count
        """
        validated = []
        for pick in picks:
            pick = dict(pick)  # copy
            event_name = (pick.get("event") or
                         f"{pick.get('home_team', '')} - {pick.get('away_team', '')}").strip()
            market_type = pick.get("market_type", "")

            # Find matching event in results
            match = self._find_event(event_name)

            if match:
                available, note = match.is_market_available(market_type)
                pick["betclic_available"] = available
                pick["betclic_note"] = note
                pick["betclic_open_markets"] = match.open_market_count
                pick["betclic_has_stats"] = match.has_statistics_tab
                pick["betclic_tabs"] = match.tabs
            else:
                pick["betclic_available"] = None
                pick["betclic_note"] = "⚠️ Event not found on Betclic"
                pick["betclic_open_markets"] = 0

            validated.append(pick)
        return validated

    def _find_event(self, event_name: str) -> Optional[BetclicMarketInfo]:
        """Find best matching event from results using fuzzy matching."""
        if not event_name or not self._results:
            return None

        event_lower = event_name.lower().strip()

        # Exact substring match first
        for info in self._results:
            if (event_lower in info.event_name.lower() or
                    info.event_name.lower() in event_lower):
                return info

        # Token overlap matching
        event_tokens = set(re.split(r'[\s\-–vs]+', event_lower))
        best_match = None
        best_score = 0

        for info in self._results:
            info_tokens = set(re.split(r'[\s\-–vs]+', info.event_name.lower()))
            overlap = len(event_tokens & info_tokens)
            if overlap > best_score and overlap >= 2:
                best_score = overlap
                best_match = info

        return best_match

    # ─── DB persistence ───────────────────────────────────────────────────

    def save_to_db(self, conn: Optional[sqlite3.Connection] = None):
        """Persist all results to betclic_markets table."""
        db = conn or self._db
        if not db:
            logger.warning("No DB connection — cannot persist results")
            return

        saved = 0
        for info in self._results:
            if not info.event_id:
                continue
            try:
                db.execute(
                    """INSERT OR REPLACE INTO betclic_markets
                    (betclic_event_id, event_name, event_url, sport,
                     competition_id, competition_name, match_date,
                     open_market_count, has_statistics_tab, has_corners,
                     has_cards, has_shots, has_fouls,
                     tabs_json, market_names_json, fetched_at, betting_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        info.event_id, info.event_name, info.event_url,
                        info.sport, info.competition_id, info.competition_name,
                        info.match_date, info.open_market_count,
                        int(info.has_statistics_tab), int(info.has_corners),
                        int(info.has_cards), int(info.has_shots), int(info.has_fouls),
                        json.dumps(info.tabs, ensure_ascii=False),
                        json.dumps(info.market_names, ensure_ascii=False),
                        info.fetched_at, self._date,
                    ),
                )
                saved += 1
            except sqlite3.Error as e:
                logger.error(f"DB error saving {info.event_name}: {e}")

        db.commit()
        logger.info(f"Saved {saved} events to betclic_markets")

        # Update competition profiles
        self._update_competition_profiles(db)

    def _update_competition_profiles(self, db: sqlite3.Connection):
        """Aggregate per-competition market availability profiles."""
        comp_data: dict[str, dict] = defaultdict(lambda: {
            "sport": "", "competition_name": "", "has_stats_count": 0,
            "total": 0, "market_sum": 0, "tabs": [], "url": "",
        })

        for info in self._results:
            key = f"{info.sport}:{info.competition_id}"
            d = comp_data[key]
            d["sport"] = info.sport
            d["competition_name"] = info.competition_name
            d["total"] += 1
            d["market_sum"] += info.open_market_count
            if info.has_statistics_tab:
                d["has_stats_count"] += 1
            if not d["tabs"] and info.tabs:
                d["tabs"] = info.tabs

        for key, d in comp_data.items():
            sport, comp_id = key.split(":", 1)
            if d["total"] == 0:
                continue
            has_stats = d["has_stats_count"] > 0
            avg_markets = d["market_sum"] // d["total"]

            try:
                db.execute(
                    """INSERT OR REPLACE INTO betclic_competition_profiles
                    (sport, competition_id, competition_name,
                     typically_has_statistics, typically_has_corners,
                     typically_has_cards, typically_has_shots, typically_has_fouls,
                     avg_open_markets, typical_tabs_json,
                     observations_count, last_observed_at, last_betting_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        sport, comp_id, d["competition_name"],
                        int(has_stats), int(has_stats), int(has_stats),
                        int(has_stats), int(has_stats),
                        avg_markets,
                        json.dumps(d["tabs"], ensure_ascii=False),
                        d["total"],
                        datetime.now(timezone.utc).isoformat(),
                        self._date,
                    ),
                )
            except sqlite3.Error as e:
                logger.error(f"DB error updating profile {key}: {e}")

        db.commit()

    def _load_from_db(self, event_path: str) -> Optional[BetclicMarketInfo]:
        """Check if event was already fetched today (cache)."""
        if not self._db:
            return None
        try:
            row = self._db.execute(
                """SELECT betclic_event_id, event_name, event_url, sport,
                          competition_id, competition_name, match_date,
                          open_market_count, has_statistics_tab, has_corners,
                          has_cards, has_shots, has_fouls,
                          tabs_json, market_names_json, fetched_at
                   FROM betclic_markets
                   WHERE event_url = ? AND betting_date = ?""",
                (event_path, self._date),
            ).fetchone()
            if not row:
                return None
            return BetclicMarketInfo(
                event_id=row[0], event_name=row[1], event_url=row[2],
                sport=row[3], competition_id=row[4], competition_name=row[5],
                match_date=row[6], open_market_count=row[7],
                has_statistics_tab=bool(row[8]), has_corners=bool(row[9]),
                has_cards=bool(row[10]), has_shots=bool(row[11]),
                has_fouls=bool(row[12]),
                tabs=json.loads(row[13]) if row[13] else [],
                market_names=json.loads(row[14]) if row[14] else [],
                fetched_at=row[15],
            )
        except sqlite3.Error:
            return None

    def get_competition_profile(self, sport: str, competition_id: str) -> Optional[dict]:
        """Get stored competition profile from DB."""
        if not self._db:
            return None
        try:
            row = self._db.execute(
                """SELECT typically_has_statistics, typically_has_corners,
                          typically_has_cards, typically_has_shots,
                          typically_has_fouls, avg_open_markets,
                          typical_tabs_json, observations_count
                   FROM betclic_competition_profiles
                   WHERE sport = ? AND competition_id = ?""",
                (sport, competition_id),
            ).fetchone()
            if not row:
                return None
            return {
                "has_statistics": bool(row[0]),
                "has_corners": bool(row[1]),
                "has_cards": bool(row[2]),
                "has_shots": bool(row[3]),
                "has_fouls": bool(row[4]),
                "avg_open_markets": row[5],
                "typical_tabs": json.loads(row[6]) if row[6] else [],
                "observations": row[7],
            }
        except sqlite3.Error:
            return None

    def build_summary(self) -> dict:
        """Build summary statistics for the scan."""
        by_sport = defaultdict(lambda: {"total": 0, "with_stats": 0, "without_stats": 0})
        by_comp = defaultdict(lambda: {
            "sport": "", "total": 0, "with_stats": 0, "tabs": [], "avg_markets": 0,
        })

        for r in self._results:
            by_sport[r.sport]["total"] += 1
            if r.has_statistics_tab:
                by_sport[r.sport]["with_stats"] += 1
            else:
                by_sport[r.sport]["without_stats"] += 1

            key = f"{r.sport}:{r.competition_name}"
            by_comp[key]["sport"] = r.sport
            by_comp[key]["total"] += 1
            if r.has_statistics_tab:
                by_comp[key]["with_stats"] += 1
            if not by_comp[key]["tabs"] and r.tabs:
                by_comp[key]["tabs"] = r.tabs
            by_comp[key]["avg_markets"] += r.open_market_count

        # Average markets
        for v in by_comp.values():
            if v["total"] > 0:
                v["avg_markets"] = v["avg_markets"] // v["total"]

        return {
            "total_events": len(self._results),
            "with_statistics_tab": sum(1 for r in self._results if r.has_statistics_tab),
            "without_statistics_tab": sum(1 for r in self._results if not r.has_statistics_tab),
            "by_sport": dict(by_sport),
            "by_competition": dict(by_comp),
            "competitions_with_stats": [
                k for k, v in by_comp.items() if v["with_stats"] > 0
            ],
            "competitions_without_stats": [
                k for k, v in by_comp.items() if v["with_stats"] == 0
            ],
            "requests_made": self._session.request_count,
        }

    def close(self):
        self._session.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


# ═══════════════════════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTIONS (backward compatible)
# ═══════════════════════════════════════════════════════════════════════════════

def check_event_markets(event_path: str) -> Optional[BetclicMarketInfo]:
    """Quick single-event check (creates temporary session)."""
    if c_requests is None:
        return None
    session = BetclicSession()
    try:
        url = f"{BASE_URL}{event_path}"
        html = session.get(url)
        if not html:
            return None
        info = parse_event_page(html)
        if info:
            info.event_url = event_path
        return info
    finally:
        session.close()


def fetch_competition_events(competition_url: str) -> list[str]:
    """Quick competition event discovery (creates temporary session)."""
    if c_requests is None:
        return []
    session = BetclicSession()
    try:
        url = f"{BASE_URL}{competition_url}"
        html = session.get(url)
        if not html:
            return []
        return list(set(re.findall(r'href="(/[^"]*-m\d+)"', html)))
    finally:
        session.close()


# ═══════════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    """CLI entry point."""
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Betclic market availability checker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Full scan for today
  %(prog)s --date 2026-05-18 --verbose

  # Single sport
  %(prog)s --date 2026-05-18 --sports football --verbose

  # Check single event
  %(prog)s --date 2026-05-18 --event-url /pilka-nozna-sfootball/premier-league-c3/...

  # Check specific competition
  %(prog)s --date 2026-05-18 --competition "Premier League" --sport football
        """,
    )
    parser.add_argument("--date", required=True, help="Betting date (YYYY-MM-DD)")
    parser.add_argument("--sports", nargs="+", default=None,
                       help="Sports to scan (default: all 5)")
    parser.add_argument("--sport", default=None, help="Single sport (with --competition)")
    parser.add_argument("--competition", default=None, help="Competition name pattern")
    parser.add_argument("--event-url", default=None, help="Check single event URL path")
    parser.add_argument("--max-events", type=int, default=25,
                       help="Max events per sport (default: 25)")
    parser.add_argument("--output", default=None, help="Output JSON path")
    parser.add_argument("--no-db", action="store_true", help="Skip DB persistence")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    # DB connection
    db_conn = None
    if not args.no_db:
        try:
            from bet.db.connection import DEFAULT_DB_PATH, _configure_connection
            import sqlite3 as _sqlite3
            db_conn = _sqlite3.connect(str(DEFAULT_DB_PATH))
            _configure_connection(db_conn)
        except Exception as e:
            logger.warning(f"Could not connect to DB: {e}")

    with BetclicMarketChecker(betting_date=args.date, db_conn=db_conn) as checker:
        if args.event_url:
            # Single event
            info = checker.check_event(args.event_url)
            if info:
                print(json.dumps(info.to_dict(), indent=2, ensure_ascii=False))
            else:
                print("ERROR: Could not fetch/parse event", file=sys.stderr)
                sys.exit(1)
            return

        if args.competition and args.sport:
            # Single competition
            results = checker.check_competition(args.sport, args.competition)
            logger.info(f"Checked {len(results)} events in {args.competition}")
        else:
            # Full scan
            checker.scan_all_sports(
                sports=args.sports,
                max_events_per_sport=args.max_events,
            )

        # Save to DB
        if db_conn and not args.no_db:
            checker.save_to_db()

        # Build summary
        summary = checker.build_summary()

        # Output JSON
        output_data = {
            "date": args.date,
            "scanned_at": datetime.now(timezone.utc).isoformat(),
            "summary": summary,
            "events": [r.to_dict() for r in checker.results],
        }

        output_path = args.output or f"betting/data/betclic_markets_{args.date}.json"
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(
            json.dumps(output_data, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        # Print report
        print(f"\n{'='*60}")
        print(f"  BETCLIC MARKET SCAN — {args.date}")
        print(f"{'='*60}")
        print(f"  Events checked: {summary['total_events']}")
        print(f"  With Statystyki: {summary['with_statistics_tab']}")
        print(f"  Without Statystyki: {summary['without_statistics_tab']}")
        print(f"  HTTP requests: {summary['requests_made']}")

        if summary["competitions_with_stats"]:
            print(f"\n  ✅ Competitions WITH statistical markets:")
            for c in summary["competitions_with_stats"]:
                print(f"     • {c}")

        if summary["competitions_without_stats"]:
            print(f"\n  ❌ Competitions WITHOUT statistical markets:")
            for c in summary["competitions_without_stats"]:
                print(f"     • {c}")

        print(f"\n  Output: {output_path}")

        # AGENT_SUMMARY
        print(f'\nAGENT_SUMMARY:{{"verdict":"OK",'
              f'"total_events":{summary["total_events"]},'
              f'"with_stats":{summary["with_statistics_tab"]},'
              f'"without_stats":{summary["without_statistics_tab"]},'
              f'"requests":{summary["requests_made"]},'
              f'"output":"{output_path}"}}')

    if db_conn:
        db_conn.commit()
        db_conn.close()


if __name__ == "__main__":
    main()
