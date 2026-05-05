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
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent
DATA_DIR = ROOT_DIR / "betting" / "data"

sys.path.insert(0, str(SCRIPTS_DIR))

try:
    from fetch_with_playwright import fetch
except Exception:
    import requests
    def fetch(url: str) -> str:
        resp = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
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
}

OUTCOME_MARKETS = {
    "winner", "zwycięzca", "1x2", "ml", "moneyline",
    "draw", "remis", "btts", "obie strzelą",
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
        "sports": ["football", "tennis", "basketball", "volleyball", "hockey", "handball", "esports", "speedway"],
        "accuracy_tracked": True,
    },
    {
        "name": "Typersi",
        "url": "https://typersi.pl/",
        "language": "pl",
        "parser": "typersi",
        "sports": ["football", "tennis", "basketball", "volleyball"],
        "accuracy_tracked": False,
    },
    {
        "name": "Sportsgambler",
        "url": "https://www.sportsgambler.com/predictions/today/",
        "language": "en",
        "parser": "sportsgambler",
        "sports": ["football", "tennis", "basketball", "hockey", "baseball", "handball", "mma"],
        "accuracy_tracked": False,
    },
    {
        "name": "PicksWise",
        "urls": [
            "https://www.pickswise.com/soccer/predictions/",
            "https://www.pickswise.com/tennis/predictions/",
            "https://www.pickswise.com/nba/predictions/",
            "https://www.pickswise.com/nhl/predictions/",
            "https://www.pickswise.com/mlb/predictions/",
        ],
        "language": "en",
        "parser": "pickswise",
        "sports": ["football", "tennis", "basketball", "hockey", "baseball"],
        "accuracy_tracked": True,
    },
    {
        "name": "BetIdeas",
        "urls": [
            "https://www.betideas.com/tips/football",
            "https://www.betideas.com/tips/tennis",
            "https://www.betideas.com/tips/basketball",
        ],
        "language": "en",
        "parser": "betideas",
        "sports": ["football", "tennis", "basketball"],
        "accuracy_tracked": True,
    },
    {
        "name": "OLBG",
        "url": "https://www.olbg.com/tips",
        "language": "en",
        "parser": "olbg",
        "sports": ["football", "tennis", "basketball", "hockey", "horse_racing"],
        "accuracy_tracked": True,
    },
    {
        "name": "Tipstrr",
        "url": "https://www.tipstrr.com/tips",
        "language": "en",
        "parser": "tipstrr",
        "sports": ["football", "tennis", "basketball", "snooker", "darts"],
        "accuracy_tracked": True,
    },
    {
        "name": "Feedinco",
        "url": "https://www.feedinco.com/",
        "language": "en",
        "parser": "feedinco",
        "sports": ["football"],
        "accuracy_tracked": False,
    },
    {
        "name": "BettingClosed",
        "url": "https://www.bettingclosed.com/",
        "language": "en",
        "parser": "bettingclosed",
        "sports": ["football"],
        "accuracy_tracked": False,
    },
    {
        "name": "Tips180",
        "url": "https://tips180.com/",
        "language": "en",
        "parser": "tips180",
        "sports": ["football"],
        "accuracy_tracked": False,
    },
    {
        "name": "GosuGamers",
        "url": "https://www.gosugamers.net/predictions",
        "language": "en",
        "parser": "gosugamers",
        "sports": ["esports"],
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
# HTML parsers — extract structured picks from fetched HTML
# ---------------------------------------------------------------------------

def classify_market(market_text: str) -> str:
    """Classify market as 'statistical' or 'outcome'."""
    lower = market_text.lower()
    for keyword in STATISTICAL_MARKETS:
        if keyword in lower:
            return "statistical"
    return "outcome"


def extract_direction(market_text: str) -> str:
    """Extract direction from market text."""
    lower = market_text.lower()
    if any(w in lower for w in ["over", "powyżej", "więcej", "o ", "+"]):
        return "OVER"
    if any(w in lower for w in ["under", "poniżej", "mniej", "u "]):
        return "UNDER"
    if any(w in lower for w in ["win", "wygra", "zwycięstwo", "1", "2"]):
        return "WIN"
    if any(w in lower for w in ["draw", "remis", "x"]):
        return "DRAW"
    return "OTHER"


def extract_odds_from_text(text: str) -> float | None:
    """Extract decimal odds from text like 'kurs 1.85' or '@1.85' or '1.85'."""
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
        "tennis": ["tennis", "tenis", "atp", "wta", "roland", "wimbledon"],
        "basketball": ["basketball", "koszykówka", "nba", "euroleague", "plk"],
        "volleyball": ["volleyball", "siatkówka", "plusliga", "superlega"],
        "hockey": ["hockey", "hokej", "nhl", "khl"],
        "baseball": ["baseball", "mlb"],
        "handball": ["handball", "piłka ręczna", "ehf"],
        "esports": ["esports", "cs2", "counter-strike", "lol", "dota"],
        "snooker": ["snooker"],
        "darts": ["darts", "rzutki", "pdc"],
        "mma": ["mma", "ufc", "bellator"],
        "table_tennis": ["table tennis", "tenis stołowy"],
        "speedway": ["speedway", "żużel"],
        "padel": ["padel"],
    }
    for sport, keywords in sport_keywords.items():
        for kw in keywords:
            if kw in combined:
                return sport
    return "football"


def parse_generic_tipster_html(html: str, site_name: str, url: str) -> list[TipsterPick]:
    """Generic HTML parser that extracts tipster picks using common patterns.

    This handles the majority of tipster sites that follow similar HTML structures.
    Works as a fallback when no site-specific parser is available.
    """
    picks = []
    now_iso = datetime.now(timezone.utc).isoformat()

    # Pattern 1: Look for match/event blocks
    # Common structures: <div class="prediction">, <article>, <div class="tip">, etc.
    event_patterns = [
        # "Team A vs Team B" or "Team A - Team B"
        r'(?:^|\n|>)\s*([A-Z][A-Za-zÀ-ž\s\.\-\']+?)\s+(?:vs?\.?|[-–—])\s+([A-Z][A-Za-zÀ-ž\s\.\-\']+?)(?:\s*[<\n,;])',
        # With competition prefix: "Premier League: Team A vs Team B"
        r'([A-Za-zÀ-ž\s]+?):\s*([A-Z][A-Za-zÀ-ž\s\.\-\']+?)\s+(?:vs?\.?|[-–—])\s+([A-Z][A-Za-zÀ-ž\s\.\-\']+?)(?:\s*[<\n])',
    ]

    # Extract text blocks that look like predictions
    # Strip HTML tags for text analysis
    text = re.sub(r'<[^>]+>', ' ', html)
    text = re.sub(r'\s+', ' ', text)

    # Split into potential prediction blocks
    blocks = re.split(r'(?=(?:[A-Z][a-z]+\s+){1,3}(?:vs|[-–])\s+)', text)

    for block in blocks[:200]:  # Limit to prevent excessive processing
        if len(block) < 20:
            continue

        # Try to extract event
        match = re.search(
            r'([A-Z][A-Za-zÀ-ž\s\.\-\']{2,30}?)\s+(?:vs?\.?|[-–—])\s+([A-Z][A-Za-zÀ-ž\s\.\-\']{2,30})',
            block
        )
        if not match:
            continue

        home = match.group(1).strip()
        away = match.group(2).strip()
        event = f"{home} vs {away}"

        # Extract market/pick from surrounding text
        market_text = block[match.end():match.end() + 200] if match.end() + 200 <= len(block) else block[match.end():]

        # Look for Over/Under with numbers
        ou_match = re.search(
            r'(?:over|under|powyżej|poniżej|o |u )\s*(\d+\.?\d*)',
            market_text, re.IGNORECASE
        )
        market = ou_match.group(0).strip() if ou_match else "N/A"

        odds = extract_odds_from_text(block)
        accuracy = extract_accuracy_from_text(block)
        sport = detect_sport(block, url)
        stats = extract_stats_cited(block)

        # Extract reasoning (text after the pick)
        reasoning_start = match.end()
        reasoning = block[reasoning_start:reasoning_start + 500].strip()
        reasoning = re.sub(r'\s+', ' ', reasoning)

        if len(home) > 2 and len(away) > 2:
            picks.append(TipsterPick(
                source_site=site_name,
                tipster_name=site_name,
                sport=sport,
                event=event,
                home_team=home,
                away_team=away,
                competition="",
                market=market,
                market_type=classify_market(market),
                direction=extract_direction(market),
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

    ZawodTyper uses lazy-loaded blocks with tipster predictions.
    Each prediction has: event, tipster name, pick, odds, reasoning, accuracy%.
    """
    picks = []
    now_iso = datetime.now(timezone.utc).isoformat()

    # ZawodTyper structure: <div class="tip-block"> or similar
    # Look for Polish prediction patterns
    # Typical: "Mecz: TeamA - TeamB", "Typ: Over 9.5 CK", "Kurs: 1.85"

    # Extract prediction blocks between common delimiters
    text = re.sub(r'<[^>]+>', '\n', html)
    text = re.sub(r'\n{3,}', '\n\n', text)

    # Find match blocks — ZawodTyper typically has blocks with tipster info
    blocks = re.split(r'(?=(?:Typ dnia|Typer:|Mecz:|Match:))', text)

    for block in blocks[:100]:
        if len(block) < 30:
            continue

        # Extract event
        event_match = re.search(
            r'([A-ZÀ-Ž][A-Za-zÀ-ž\s\.\-\']{2,30}?)\s*[-–—]\s*([A-ZÀ-Ž][A-Za-zÀ-ž\s\.\-\']{2,30})',
            block
        )
        if not event_match:
            continue

        home = event_match.group(1).strip()
        away = event_match.group(2).strip()

        # Extract tipster name
        tipster_match = re.search(r'(?:Typer|Tipster|Autor):\s*(\S+)', block, re.IGNORECASE)
        tipster_name = tipster_match.group(1) if tipster_match else "ZawodTyper"

        # Extract pick/market
        pick_match = re.search(
            r'(?:Typ|Pick|Zakład):\s*(.+?)(?:\n|$)',
            block, re.IGNORECASE
        )
        market = pick_match.group(1).strip() if pick_match else ""

        odds = extract_odds_from_text(block)
        accuracy = extract_accuracy_from_text(block)
        sport = detect_sport(block)
        stats = extract_stats_cited(block)

        # Reasoning — look for argument/justification text
        reasoning_match = re.search(
            r'(?:Argument|Uzasadnienie|Dlaczego|Reasoning):\s*(.+?)(?:\n\n|$)',
            block, re.IGNORECASE | re.DOTALL
        )
        reasoning = reasoning_match.group(1).strip()[:500] if reasoning_match else block[:300].strip()

        if len(home) > 2 and len(away) > 2:
            picks.append(TipsterPick(
                source_site="ZawodTyper",
                tipster_name=tipster_name,
                sport=sport,
                event=f"{home} vs {away}",
                home_team=home,
                away_team=away,
                competition="",
                market=market,
                market_type=classify_market(market),
                direction=extract_direction(market),
                odds=odds,
                reasoning=reasoning,
                accuracy_pct=accuracy,
                confidence="medium" if accuracy and accuracy > 55 else "low",
                stats_cited=stats,
                fetch_time=now_iso,
            ))

    return picks


# ---------------------------------------------------------------------------
# Fetcher — parallel fetch with error handling
# ---------------------------------------------------------------------------

def fetch_site(site_config: dict, date: datetime) -> dict:
    """Fetch a single tipster site and parse its picks.

    Returns dict with: site_name, url, status, picks, error, fetch_time_ms.
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
        for url in urls:
            result["url"] = url
            try:
                html = fetch(url)
                if not html or len(html) < 100:
                    continue

                # Route to appropriate parser
                parser = site_config.get("parser", "generic")
                if parser == "zawodtyper":
                    picks = parse_zawodtyper_html(html)
                else:
                    picks = parse_generic_tipster_html(html, site_name, url)

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
# Main orchestrator
# ---------------------------------------------------------------------------

def run_tipster_aggregation(
    date: str,
    max_workers: int = 5,
    sport_filter: str | None = None,
) -> dict:
    """Run full tipster aggregation pipeline.

    1. Build URLs for all tipster sites
    2. Fetch in parallel (ThreadPoolExecutor)
    3. Parse picks from each site
    4. Compute consensus
    5. Combine with stats
    6. Save output

    Returns summary dict.
    """
    try:
        from zoneinfo import ZoneInfo
    except ImportError:
        from backports.zoneinfo import ZoneInfo

    date_obj = datetime.strptime(date, "%Y-%m-%d")
    date_obj = date_obj.replace(tzinfo=ZoneInfo("Europe/Warsaw"))

    print(f"[tipster] Starting aggregation for {date}")
    print(f"[tipster] Sites to fetch: {len(TIPSTER_SITES)}")
    print(f"[tipster] Workers: {max_workers}")

    # Parallel fetch
    all_results = []
    all_picks = []
    errors = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(fetch_site, site, date_obj): site["name"]
            for site in TIPSTER_SITES
        }

        for future in as_completed(futures):
            site_name = futures[future]
            try:
                result = future.result()
                all_results.append(result)
                all_picks.extend(result.get("picks", []))
                status = result["status"]
                count = result["pick_count"]
                ms = result["fetch_time_ms"]
                print(f"  [{status}] {site_name}: {count} picks ({ms}ms)")
                if result.get("error"):
                    errors.append(f"{site_name}: {result['error']}")
            except Exception as e:
                print(f"  [error] {site_name}: {e}")
                errors.append(f"{site_name}: {str(e)[:200]}")

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
    print(f"\n[tipster] Saved: {output_json}")

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
    print(f"[tipster] Saved: {output_md}")

    print(f"\n[tipster] Summary: {total_picks} picks from {sites_ok} sites, "
          f"{len(consensus)} events, {statistical_picks} statistical markets")

    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Tipster Aggregator — parallel fetch and consensus")
    parser.add_argument("--date", help="Date (YYYY-MM-DD)")
    parser.add_argument("--workers", type=int, default=5, help="Max parallel workers (default: 5)")
    parser.add_argument("--sport", help="Filter by sport (e.g., football)")
    args = parser.parse_args()

    if not args.date:
        try:
            from zoneinfo import ZoneInfo
        except ImportError:
            from backports.zoneinfo import ZoneInfo
        args.date = datetime.now(ZoneInfo("Europe/Warsaw")).strftime("%Y-%m-%d")

    run_tipster_aggregation(args.date, max_workers=args.workers, sport_filter=args.sport)


if __name__ == "__main__":
    main()
