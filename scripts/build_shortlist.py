#!/usr/bin/env python3
"""Build a ranked S2 shortlist from the market matrix.

Scores every event by data quality, competition importance, odds attractiveness,
and sport diversity, then selects the top N candidates.

Usage:
    python3 scripts/build_shortlist.py --date 2026-04-30 --top 100
    python3 scripts/build_shortlist.py --date 2026-04-30 --top 100 --stats-first
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
DATA_DIR = PROJECT_DIR / "betting" / "data"

# Add scripts dir for sibling imports
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
from generate_market_matrix import MAJOR_COMPETITIONS, _is_major_competition
from bet.stats.market_ranking import STANDARD_MARKET_LINES

from utils import normalize_team_name as _normalize_team, normalize_kickoff
from agent_output import AgentOutput, add_agent_args

from db_data_loader import load_fixtures_from_db, load_odds_from_db


# ---------------------------------------------------------------------------
# Fixture verification (§1.8)
# ---------------------------------------------------------------------------

def _load_verification_sources(date: str) -> tuple[set[str], set[str]]:
    """Load fixture keys from odds_api_snapshot and fixtures file for §1.8 verification.

    Returns (odds_api_keys, fixtures_keys) — sets of normalized 'home|away' keys.
    Uses DB-first loading via db_data_loader.
    """
    odds_keys: set[str] = set()
    fixtures_keys: set[str] = set()

    # Odds API snapshot (DB-first)
    try:
        odds_data = load_odds_from_db(date)
        items = odds_data.get("events", []) if isinstance(odds_data, dict) else (odds_data if isinstance(odds_data, list) else [])
        for ev in items:
            h = _normalize_team(ev.get("home_team", ""))
            a = _normalize_team(ev.get("away_team", ""))
            if h and a:
                odds_keys.add(f"{h}|{a}")
    except Exception:
        pass

    # Fixtures (DB-first)
    try:
        fixtures = load_fixtures_from_db(date)
        for fix in fixtures:
            h = _normalize_team(fix.get("home_team", ""))
            a = _normalize_team(fix.get("away_team", ""))
            if h and a:
                fixtures_keys.add(f"{h}|{a}")
    except Exception:
        pass

    return odds_keys, fixtures_keys


def _verify_fixture(
    home: str, away: str, odds_keys: set[str], fixtures_keys: set[str]
) -> tuple[bool, list[str]]:
    """Check if an event appears in ≥1 independent source.

    Returns (verified, sources_list).
    """
    h = _normalize_team(home)
    a = _normalize_team(away)
    key = f"{h}|{a}"
    key_rev = f"{a}|{h}"

    sources = []
    if key in odds_keys or key_rev in odds_keys:
        sources.append("odds-api")
    if key in fixtures_keys or key_rev in fixtures_keys:
        sources.append("fixtures-api")

    # Also check fuzzy (substring match for when names differ slightly)
    if not sources:
        for ok in odds_keys:
            parts = ok.split("|", 1)
            if len(parts) == 2:
                if (h in parts[0] or parts[0] in h) and (a in parts[1] or parts[1] in a):
                    sources.append("odds-api-fuzzy")
                    break
                if (h in parts[1] or parts[1] in h) and (a in parts[0] or parts[0] in a):
                    sources.append("odds-api-fuzzy")
                    break

    return bool(sources), sources


# ---------------------------------------------------------------------------
# §SCAN.9 — Protected major domestic leagues worldwide
# These leagues get +10 boost and must appear in scan when active.
# ---------------------------------------------------------------------------
PROTECTED_DOMESTIC_LEAGUES: dict[str, list[str]] = {
    "football": [
        "brasileirao", "brasileirão", "brazil serie a", "brazil serie b",
        "copa do brasil", "mls", "liga mx", "liga de expansion",
        "liga profesional", "primera division argentina", "primera nacional",
        "liga betplay", "primera a colombia", "primera a", "primera division chile",
        "chinese super league", "csl", "cfa super", "china",
        "j1 league", "j-league", "j2 league",
        "k league", "k-league",
        "saudi pro league", "spl", "roshn saudi", "saudi arabia",
        "indian super league", "isl", "india",
        "a-league",
        "egyptian premier", "egypt",
        "south african psl", "south africa",
    ],
    "basketball": [
        "cba", "nbb", "b.league", "kbl", "pba", "nbl australia", "lnbp",
    ],
    "volleyball": [
        "plusliga", "superlega", "ligue a", "superliga", "v-league",
        "superliga brazil", "bundesliga", "efeler",
    ],
    "tennis": [
        "australian open", "roland garros", "french open", "wimbledon",
        "us open", "masters", "atp 1000", "wta 1000",
    ],
    "hockey": [
        "khl",
    ],
}


def _is_protected_domestic_league(sport: str, competition: str) -> bool:
    """Check if a competition is a protected major domestic league (§SCAN.9).
    
    Normalizes separators (e.g. 'Brazil - Serie A' → 'brazil serie a') to handle
    URL-derived competition names that use ' - ' between country and league.
    """
    if not competition:
        return False
    # Normalize: remove ' - ' separators, collapse whitespace, lowercase
    comp_lower = competition.lower().replace(" - ", " ").replace("  ", " ")
    keywords = PROTECTED_DOMESTIC_LEAGUES.get(sport, [])
    return any(kw in comp_lower for kw in keywords)


# ---------------------------------------------------------------------------
# Competition tiers (higher = more important)
# ---------------------------------------------------------------------------
COMP_TIER_KEYWORDS: dict[str, list[tuple[int, list[str]]]] = {
    "football": [
        (10, ["champions league", "europa league", "conference league", "world cup",
              "euro 202", "copa america", "club world cup"]),
        (9, ["english premier league", "la liga", "laliga", "bundesliga", "serie a", "ligue 1"]),
        (8, ["eredivisie", "primeira liga", "ekstraklasa", "super lig", "championship",
             "copa libertadores", "copa sudamericana", "fa cup", "coppa italia",
             "dfb pokal", "copa del rey", "coupe de france",
             "brasileirao", "brasileirão", "brazil serie a", "brazil serie b",
             "mls", "liga mx", "liga profesional", "primera division argentina",
             "liga betplay", "chinese super league", "csl", "cfa super",
             "j1 league", "j-league", "j2 league", "k league", "k-league",
             "saudi pro league", "spl", "indian super league", "isl",
             "a-league", "egyptian premier", "south african psl"]),
        (7, ["allsvenskan", "eliteserien", "superliga",
             "belgian", "jupiler", "scottish", "swiss super league",
             "liga de expansion", "primera nacional", "copa do brasil",
             "primera division chile", "primera a colombia"]),
        (6, ["2. bundesliga", "serie b", "ligue 2", "segunda", "3. liga",
             "serie c", "national league", "league two",
             "usl championship", "nwsl", "mls next pro",
             "division 1", "division 2", "1. liga", "first division b",
             "eerste divisie", "2nd division", "3rd division",
             "veikkausliiga", "finnish", "cyprus", "cypriot",
             "israeli", "israel premier", "gibraltar",
             "faroe", "liga 1", "liga i", "romanian",
             "thai league", "persian gulf", "iran pro",
             "women super league", "wsl", "frauen bundesliga",
             "telia", "damallsvenskan"]),
        (5, ["nations league", "qualification", "friendly",
             "regionalliga", "national league north", "national league south",
             "serie d", "4th division"]),
        (3, []),  # default for any unknown football league (raised from 2)
    ],
    "tennis": [
        (10, ["grand slam", "australian open", "french open", "wimbledon", "us open",
              "roland garros"]),
        (9, ["masters 1000", "atp 1000", "wta 1000", "indian wells", "miami",
             "monte carlo", "madrid", "rome", "canada", "cincinnati", "shanghai", "paris"]),
        (8, ["atp 500", "wta 500"]),
        (7, ["atp 250", "wta 250"]),
        (5, ["challenger", "itf", "futures", "billie jean king", "laver cup",
             "olympics", "next gen"]),
    ],
    "basketball": [
        (10, ["nba playoff", "nba finals", "fiba world cup", "olympic"]),
        (9, ["nba", "euroleague"]),
        (8, ["eurocup", "ncaa", "acb", "final four",
             "cba", "nbb", "b.league", "kbl", "pba", "nbl australia"]),
        (7, ["plk", "bbl", "bcl", "fiba", "lnb", "nbl", "lnbp",
             "basket liga", "a1 ethniki", "lega 2", "pro b",
             "superleague", "bkt liga"]),
        (6, ["division 1", "liga femenina", "wbbl", "wnbl",
             "2nd division", "1st division"]),
    ],
    "volleyball": [
        (10, ["cev champions league", "world championship", "nations league finals", "olympic"]),
        (9, ["plusliga", "superlega"]),
        (8, ["serie a", "ligue a", "bundesliga", "cev"]),
        (7, ["efeler", "superliga", "plusliga playoff", "superlega playoff",
             "division 1", "liga a1", "eredivisie", "a1 ethniki"]),
        (6, ["2nd division", "division 2", "serie a2", "1st division",
             "v-league", "mestaruusliiga"]),
    ],
    "hockey": [
        (10, ["nhl playoff", "stanley cup", "iihf world"]),
        (9, ["nhl", "khl"]),
        (8, ["shl", "liiga", "del"]),
        (7, ["allsvenskan", "mestis", "1. liga", "ligue magnus",
             "erste liga", "tipsport liga", "echl", "eihl"]),
        (6, ["division 1", "2nd division", "hockeyettan", "optibet liga"]),
    ],
}

# Tier 1 = KEY sports (always prioritize); Tier 2 = support
TIER1_SPORTS = {"football", "volleyball", "basketball", "tennis", "hockey"}


def _score_competition(sport: str, competition: str) -> int:
    """Score a competition within its sport (higher = more important)."""
    if not competition:
        return 1
    # Normalize: remove ' - ' separators to handle URL-derived names
    comp_lower = competition.lower().replace(" - ", " ").replace("  ", " ")

    # Penalize clearly obscure/minor leagues — these are NEVER on Betclic
    obscure_markers = [
        "amateur", "reserve", "u19", "u20", "u21", "youth",
        "regional", "county", "division 4", "division 5",
        "sikkim", "mizoram", "manipur",  # Indian state leagues with zero data
        "women u17", "women u19", "women u20", "women reserve",
        "women amateur", "femeni u", "femenin u",  # Only YOUTH/amateur women's
    ]
    # Countries/regions whose leagues are NEVER available on Betclic
    unbettable_markers = [
        "iraq", "iraqi", "yemen", "myanmar", "cambodia", "laos",
        "ethiopia", "eritrea", "somalia", "sudan", "south sudan",
        "nicaragua", "guatemala", "honduras", "el salvador",
        "bangladesh", "nepal", "bhutan", "sri lanka",
        "mongolia", "turkmenistan", "tajikistan", "kyrgyzstan",
        "rwanda", "burundi", "malawi", "zambia", "zimbabwe",
        "mozambique", "tanzania", "uganda", "kenya",
        "liberia", "sierra leone", "guinea", "togo", "benin",
        "lesotho", "eswatini", "botswana", "namibia",
        "papua new guinea", "fiji", "samoa",
        "vietnamese", "vietnam", "v.league 2",
        "georgian", "georgia 2", "erovnuli liga 2",
        "armenian", "armenia 2",
        "lebanese", "lebanon 2",
        "jordanian", "jordan 2",
        "kuwaiti", "kuwait 2",
        "bahraini", "bahrain 2",
        "omani", "oman",
        "paraguayan 2", "division intermedia",
        "bolivian", "bolivia",
        "ecuadorian 2", "serie b ecuador",
        "venezuelan 2", "segunda division venezuela",
        "peruvian 2", "segunda division peru",
    ]
    if any(m in comp_lower for m in obscure_markers):
        return 1
    if any(m in comp_lower for m in unbettable_markers):
        return 0  # absolute zero — these should never appear in output

    tiers = COMP_TIER_KEYWORDS.get(sport, [])
    for score, keywords in tiers:
        if keywords and any(kw in comp_lower for kw in keywords):
            return score
    # Default per-sport base
    for score, keywords in tiers:
        if not keywords:
            return score
    # Fallback: check if it's in MAJOR_COMPETITIONS (broader list)
    if _is_major_competition(sport, competition):
        return 6  # recognized in MAJOR_COMPETITIONS but not in tier keywords
    return 2


def _score_event(event: dict, tipster_events: set[str]) -> float:
    """Score an event for shortlist ranking. Higher = better candidate.
    
    Scoring philosophy: BETTABILITY > data quantity.
    Events in recognized leagues on Betclic score 2-3x higher than obscure leagues.
    """
    sport = event["sport"]
    comp = event.get("competition", "")
    tier = event.get("data_tier", "FIXTURE_ONLY")
    has_odds = bool(event.get("odds_markets"))
    n_odds = len(event.get("odds_markets", []))
    has_safety = bool(event.get("safety_markets"))
    n_safety = len(event.get("safety_markets", []))

    score = 0.0

    # 1. Data tier (odds availability matters but shouldn't dominate)
    tier_scores = {"FULL": 30, "ODDS_RICH": 25, "ODDS_BASIC": 18, "STATS_ONLY": 12, "FIXTURE_ONLY": 0}
    score += tier_scores.get(tier, 0)

    # 2. Competition importance (HIGHEST weight — premier league > obscure league)
    comp_score = _score_competition(sport, comp)
    score += comp_score * 7  # max 70 (was *5=50) — league quality is THE key factor

    # 3. Sport tier bonus
    if sport in TIER1_SPORTS:
        score += 5  # reduced from 10 — sport alone shouldn't boost garbage leagues

    # 4. Number of odds markets (more = better analysis potential)
    score += min(n_odds * 2, 12)  # cap at 12

    # 5. Safety data availability — bonus only for high safety scores
    if has_safety:
        safety_markets = event.get("safety_markets", [])
        best_safety = max((m.get("safety_score", 0) for m in safety_markets), default=0)
        if best_safety >= 0.45:
            score += min(n_safety * 4, 20)  # strong edge: bonus up to 20
        elif best_safety >= 0.30:
            score += min(n_safety * 2, 10)  # moderate edge: bonus up to 10
        # below 0.30: NO bonus — weak safety = weak candidate

    # 6. Tipster coverage bonus
    home_lower = event.get("home_team", "").lower()
    away_lower = event.get("away_team", "").lower()
    event_key = f"{home_lower} vs {away_lower}"
    has_tipster = (
        event_key in tipster_events
        or home_lower in tipster_events
        or away_lower in tipster_events
    )
    if has_tipster:
        score += 15

    # 7. Odds attractiveness (sweet spot: 1.40-3.00)
    if has_odds:
        best_odds = max(
            (m.get("best_odds") or 0 for m in event["odds_markets"]), default=0
        )
        if 1.40 <= best_odds <= 3.00:
            score += 8
        elif 1.20 <= best_odds <= 4.00:
            score += 4

    # 8. BETTABILITY CHECK — is this league likely on Betclic?
    is_major = _is_major_competition(sport, comp)
    if is_major:
        score += 15  # confirmed bettable league
    elif comp_score <= 2:
        # Truly unknown league (NOT in any tier or MAJOR_COMPETITIONS) → HARD PENALTY
        score *= 0.3  # crush score to near-zero
    elif comp_score <= 4:
        # Low-tier or unrecognized default (score=3 football default) → moderate penalty
        score *= 0.5
    elif comp_score <= 5:
        # Low-tier recognized league (friendlies, regionalliga, etc.)
        score *= 0.7  # mild penalty

    # 9. Major tournament protection (§SCAN.7) — tournaments always get priority
    if comp_score >= 9:
        score += 15

    # 9b. Major domestic league protection (§SCAN.9) — top leagues worldwide
    if comp_score == 8 and _is_protected_domestic_league(sport, comp):
        score += 10

    # 10. Deep data richness boost — teams with ESPN gamelogs get better analysis
    if sport in ("basketball", "hockey") and comp_score >= 7:
        # Only boost if in a recognized league (don't boost Iraqi basketball)
        try:
            from db_data_loader import load_player_gamelogs_for_team
            home_team = event.get("home_team", "")
            if home_team:
                gamelogs = load_player_gamelogs_for_team(home_team, sport, n=1)
                if gamelogs:
                    score += 8
        except Exception:
            pass

    # BUG C fix: FIXTURE_ONLY events with no stats data should sink below data-rich events.
    if tier == "FIXTURE_ONLY":
        score *= 0.4  # harder penalty (was 0.5)

    return score


def _load_tipster_events(date: str) -> set[str]:
    """Load tipster prefetch to identify events with tipster coverage.
    
    Returns a set of normalized team name pairs like 'braga vs freiburg'.
    Parses both markdown headers AND pipe-delimited table entries (ZT format).
    """
    events = set()
    date_compact = date.replace("-", "")
    prefetch_path = DATA_DIR / f"{date_compact}_s1_tipster_prefetch.md"
    if not prefetch_path.exists():
        for p in DATA_DIR.glob(f"{date_compact}*tipster*"):
            prefetch_path = p
            break

    if prefetch_path.exists():
        text = prefetch_path.read_text(encoding="utf-8")
        for line in text.split("\n"):
            # Extract from markdown headers like "### #1 — SC Braga vs SC Freiburg"
            m = re.search(r"—\s*(.+?)\s+vs\s+(.+?)$", line, re.IGNORECASE)
            if m:
                home = m.group(1).strip().lower()
                away = m.group(2).strip().lower()
                events.add(f"{home} vs {away}")
                # Also add individual team names for fuzzy matching
                events.add(home)
                events.add(away)
                continue
            # Extract from ZT-style pipe-delimited table rows:
            # | 1 | Football | Mirassol vs Always Ready | Over 20.5 fauli @1.72 | 1.56 | FOULS ⭐ |
            # | 6 | Football | al Kholood vs al Fayha | Over 1.5 bramki ... | 1.60 | CORNERS ⭐ |
            if "|" in line and (" vs " in line or " - " in line.split("|")[2] if len(line.split("|")) > 3 else False):
                cells = [c.strip() for c in line.split("|") if c.strip()]
                # Skip header/separator rows
                if len(cells) >= 4 and not cells[0].startswith("#") and not cells[0].startswith("-"):
                    # Event is typically in cells[2] (after #, Sport)
                    match_cell = None
                    for cell_idx in range(min(len(cells), 5)):
                        if " vs " in cells[cell_idx] or " - " in cells[cell_idx]:
                            match_cell = cells[cell_idx]
                            break
                    if match_cell:
                        for sep in [" vs ", " - "]:
                            if sep in match_cell:
                                parts = match_cell.split(sep, 1)
                                if len(parts) == 2:
                                    home = re.sub(r"[#*\[\]()]", "", parts[0]).strip().lower()
                                    away = re.sub(r"[#*\[\]()]", "", parts[1]).strip().lower()
                                    if home and away and len(home) > 2 and len(away) > 2:
                                        events.add(f"{home} vs {away}")
                                        events.add(home)
                                        events.add(away)
                                break
                    continue
            # Extract from lines with " vs " or " - "
            for sep in [" vs ", " - "]:
                if sep in line.lower():
                    parts = line.lower().split(sep, 1)
                    if len(parts) == 2:
                        # Clean markdown formatting
                        home = re.sub(r"[#*\-\[\]()]", "", parts[0]).strip()
                        away = re.sub(r"[#*\-\[\]()]", "", parts[1]).strip()
                        if home and away and len(home) > 2 and len(away) > 2:
                            events.add(f"{home} vs {away}")
                            events.add(home)
                            events.add(away)
                    break
    return events

# ITF Futures filter (§SCAN — ERROR 1 prevention)
# ITF M15/W15/M25/W25/W35/W40/W50/W60/W75/M40/M50 etc. have ZERO data coverage.
# Sackmann covers ATP+WTA+Challengers. Tennis Abstract covers top players.
# ESPN covers ATP+WTA. So we ONLY block ITF Futures tier events.
# Challengers, WTA 125, Qualifying = KEEP (have data in Sackmann/TennisAbstract).
ITF_LOW_TIER_RE = re.compile(
    r"\b(itf|futures)\b"
    r"|\b[mw]\d{2,3}\b"  # M15, W15, M25, W25, W35, W40, W50, W60, W75, M40 etc.
    ,
    re.I,
)
# Events with these keywords are NEVER filtered even if regex matches
ITF_QUALIFYING_KEYWORDS = {"roland garros", "french open", "wimbledon", "us open", "australian open",
                           "olympics", "olympic", "davis cup", "billie jean king",
                           "challenger", "atp", "wta", "masters"}

def build_shortlist(
    date: str,
    top_n: int = 0,
    stats_first: bool = False,
    min_sports: int = 5,
) -> list[dict]:
    """Build a ranked shortlist of top_n events from the market matrix."""
    matrix_path = DATA_DIR / f"market_matrix_{date}.json"
    if not matrix_path.exists():
        print(f"[shortlist] ERROR: {matrix_path} not found. Run generate_market_matrix.py first.")
        sys.exit(1)

    matrix = json.loads(matrix_path.read_text(encoding="utf-8"))
    events = matrix["events"]
    print(f"[shortlist] Loaded {len(events)} events from market matrix")

    # Load tipster data for bonus scoring
    tipster_events = _load_tipster_events(date)
    print(f"[shortlist] Tipster events found: {len(tipster_events)}")

    # Score all events
    scored = []
    for event in events:
        sport = event.get("sport", "")
        comp = event.get("competition", "")
        tier = event.get("data_tier", "FIXTURE_ONLY")

        # §NO AUTO-REJECTION: ALL events are scored and included.
        # FIXTURE_ONLY events get lower scores (less data = lower confidence)
        # but are NEVER filtered out. The user decides what to bet.
        # The scoring function already penalizes low-data events.

        score = _score_event(event, tipster_events)
        scored.append((score, event))

    scored.sort(key=lambda x: -x[0])
    print(f"[shortlist] Scored {len(scored)} eligible events")

    # Garbage filter: reject entries where team names are page chrome
    _garbage_re = re.compile(
        r"today's matches|pinned leagues|my teams|advertisement|"
        r"advancing to next round|winner:|latest scores|previous match day|"
        r"there are no .* matches|sets legs points|"
        r"atp\b.*\bsingles|wta\b.*\bsingles|atp\b.*\bdoubles|wta\b.*\bdoubles|"
        r"\bdraw\s+\d{1,2}:\d{2}\b|overview|preview|head-to-head|line-ups|"
        r"completed|match stats|\bcourt\b.*\bcompleted\b|\bpuchar\b|\bpremiership league\b|"
        r"pregame report|postgame|"
        # Tipster page artifacts (v5 — garbage names in coupons)
        r"picks\s*&\s*odds|epl\s+picks|odds\s+for\s+(saturday|friday|monday|sunday|tuesday|wednesday|thursday)|"
        r"typy\s+bukmacherów|kolejka|wydarzenie|bukmacherów|"
        r"\d+\.\d{2}\s+\d+\.\d{2}|"  # embedded odds (1.68 3.75)
        r"\d+\s*'|"  # match minute markers (37 ')
        # Soccerway adapter garbage — structural HTML scraped as team names
        r"^division\s+\d|^primera\s+division$|^segunda\s+division$|^tercera\s+division$|"
        r"display\s+matches|^round\s+\d|^matchday\s+\d|^group\s+[a-z]$|"
        r"^league\s+table$|^results$|^fixtures$|^standings$|"
        # Bookmaker names scraped as team names (tennis adapter)
        r"^1xbet$|^bet365$|^unibet$|^pinnacle$|^betway$|^william\s+hill$|"
        r"^betfair$|^bwin$|^marathon\s*bet$|^betclic$|^betsson$|"
        r"^888sport$|^paddy\s+power$|^coral$|^ladbrokes$|^stake$",
        re.I,
    )
    # Bookmaker-vs-bookmaker pattern: "1xBet vs bet365"
    _bookmaker_vs_re = re.compile(
        r"\b(1xbet|bet365|unibet|pinnacle|betway|bwin|betfair|betclic|betsson|"
        r"marathon\s*bet|william\s+hill|888sport|paddy\s+power|coral|ladbrokes|stake)\b",
        re.I,
    )
    # ITF low-tier filter moved to module level

    filtered = []
    garbage_count = 0
    for score, event in scored:
        # ITF low-tier filter: skip M15/W15/M25/W25 unless Grand Slam qualifying
        if event.get("sport") == "tennis":
            comp = (event.get("competition") or "").lower()
            if ITF_LOW_TIER_RE.search(comp):
                if not any(kw in comp for kw in ITF_QUALIFYING_KEYWORDS):
                    garbage_count += 1
                    continue

        home = event.get("home_team", "")
        away = event.get("away_team", "")

        # Youth / Reserve / University filter — no data sources cover these
        _youth_re = re.compile(
            r"\bU1[2-9]\b|\bU2[0-1]\b|\bReserves?\b|\bRes\.\b|\bJunior[sy]?\b"
            r"|\bCadete[s]?\b|\bJuvenil\b|\bSub[\s-]?\d{2}\b"
            r"|\bAcademy\b.*\bU\d{2}\b|\bU\d{2}\b.*\bAcademy\b",
            re.I,
        )
        if _youth_re.search(home) or _youth_re.search(away):
            garbage_count += 1
            continue

        # Too short — structural artifacts or empty
        if len(home.strip()) < 2 or len(away.strip()) < 2:
            garbage_count += 1
            continue
        if len(home) > 60 or len(away) > 60:
            garbage_count += 1
            continue
        if _garbage_re.search(home) or _garbage_re.search(away):
            garbage_count += 1
            continue
        # Both home and away match bookmaker names → "1xBet vs bet365" garbage
        if _bookmaker_vs_re.fullmatch(home.strip()) or _bookmaker_vs_re.fullmatch(away.strip()):
            garbage_count += 1
            continue
        if " / " in home or " / " in away:
            garbage_count += 1
            continue
        if re.search(r" : .+\d{1,2}:\d{2}", home) or re.search(r" : .+\d{1,2}:\d{2}", away):
            garbage_count += 1
            continue
        # Date-prefixed team names (e.g., "CZW 30.04.2026 20:30 Northampton")
        if re.match(r"^[A-Z]{2,4}\s+\d{2}\.\d{2}\.\d{4}", home) or re.match(r"^[A-Z]{2,4}\s+\d{2}\.\d{2}\.\d{4}", away):
            garbage_count += 1
            continue
        # All-digit team names (e.g., "123") — not valid
        if re.fullmatch(r"\d+", home.strip()) or re.fullmatch(r"\d+", away.strip()):
            garbage_count += 1
            continue
        filtered.append((score, event))
    if garbage_count:
        print(f"[shortlist] Filtered {garbage_count} garbage entries")
    scored = filtered

    # Dedup: same teams in same sport = likely same event from different sources
    deduped = []
    seen_matchups: set[str] = set()
    for score, event in scored:
        home = event.get("home_team", "").lower().strip()
        away = event.get("away_team", "").lower().strip()
        sport = event.get("sport", "")
        # Normalize: remove accents, common suffixes/prefixes
        home = unicodedata.normalize("NFKD", home).encode("ascii", "ignore").decode()
        away = unicodedata.normalize("NFKD", away).encode("ascii", "ignore").decode()
        for remove in ["fc ", "sc ", "bc ", "ac ", " fc", " sc", " bc", " cf",
                       " basket", " basketball", " sk", " sk.",
                       " s.k.", " fk", " fk."]:
            home = home.replace(remove, "")
            away = away.replace(remove, "")
        # Remove city qualifiers often appended (e.g., "Zalgiris Kaunas" -> "Zalgiris")
        # and common short suffixes
        for suffix in [" kaunas", " vilnius", " moscow", " kiev",
                       " london", " paris", " madrid", " berlin"]:
            home = home.replace(suffix, "")
            away = away.replace(suffix, "")
        home = re.sub(r"\s+", " ", home).strip()
        away = re.sub(r"\s+", " ", away).strip()
        dedup_key = f"{sport}|{home}|{away}"
        # Also check reversed order (same matchup, swapped home/away from different sources)
        dedup_key_rev = f"{sport}|{away}|{home}"
        if dedup_key in seen_matchups or dedup_key_rev in seen_matchups:
            continue
        # Fuzzy substring dedup: check if either team name is a substring of an existing entry
        # Minimum length threshold of 5 to avoid false positives with short names
        # (e.g., "PSG" matching "APSG", "Bar" matching "Barca")
        MIN_FUZZY_LEN = 5
        is_dup = False
        for existing_key in seen_matchups:
            ex_parts = existing_key.split("|", 2)
            if len(ex_parts) != 3 or ex_parts[0] != sport:
                continue
            ex_home, ex_away = ex_parts[1], ex_parts[2]
            home_match = (home in ex_home or ex_home in home) and len(home) >= MIN_FUZZY_LEN and len(ex_home) >= MIN_FUZZY_LEN
            away_match = (away in ex_away or ex_away in away) and len(away) >= MIN_FUZZY_LEN and len(ex_away) >= MIN_FUZZY_LEN
            if home_match and away_match:
                is_dup = True
                break
            # Also check crossed: home↔away
            home_match_rev = (home in ex_away or ex_away in home) and len(home) >= MIN_FUZZY_LEN and len(ex_home) >= MIN_FUZZY_LEN
            away_match_rev = (away in ex_home or ex_home in away) and len(away) >= MIN_FUZZY_LEN and len(ex_away) >= MIN_FUZZY_LEN
            if home_match_rev and away_match_rev:
                is_dup = True
                break
        if is_dup:
            continue
        seen_matchups.add(dedup_key)
        deduped.append((score, event))

    print(f"[shortlist] After dedup: {len(deduped)} unique events (removed {len(scored) - len(deduped)} dupes)")
    scored = deduped

    # ── Phantom fixture detection: same team in multiple DIFFERENT matches ──
    # A team can only play ONE match per day. If it appears in 2+ different
    # matchups, all but the highest-scored fixture are phantom (scraped from
    # a different matchday).  Keep the one with the best shortlist score,
    # mark the rest as phantom-risk.
    # Exception: tennis players legitimately play singles + doubles.
    def _normalize_team(name: str) -> str:
        """Normalize team name for phantom matching (same logic as dedup)."""
        n = unicodedata.normalize("NFKD", name.lower().strip()).encode("ascii", "ignore").decode()
        for remove in ["fc ", "sc ", "bc ", "ac ", " fc", " sc", " bc", " cf",
                       " basket", " basketball", " sk", " sk.",
                       " s.k.", " fk", " fk."]:
            n = n.replace(remove, "")
        for suffix in [" kaunas", " vilnius", " moscow", " kiev",
                       " london", " paris", " madrid", " berlin"]:
            n = n.replace(suffix, "")
        return re.sub(r"\s+", " ", n).strip()

    team_best: dict[str, tuple[float, int]] = {}  # "sport|team" → (best_score, index)
    team_all: dict[str, list[int]] = {}  # "sport|team" → [indices]
    for idx, (score, event) in enumerate(scored):
        sport = event.get("sport", "")
        # Tennis: skip phantom detection — players legitimately play singles + doubles
        if sport == "tennis":
            continue
        for role in ("home_team", "away_team"):
            raw = event.get(role, "").strip()
            if not raw:
                continue
            norm = _normalize_team(raw)
            if len(norm) < 3:
                continue  # Skip very short names to avoid false positives
            team_key = f"{sport}|{norm}"
            if team_key not in team_all:
                team_all[team_key] = []
            team_all[team_key].append(idx)
            if team_key not in team_best or score > team_best[team_key][0]:
                team_best[team_key] = (score, idx)

    # Find indices to remove: team in >1 different match → keep best, drop rest
    phantom_indices: set[int] = set()
    phantom_teams: list[str] = []
    for team_key, indices in team_all.items():
        if len(indices) <= 1:
            continue
        # Check if these are actually different matchups (not just same match)
        unique_matchups: set[str] = set()
        for i in indices:
            ev = scored[i][1]
            h = _normalize_team(ev.get("home_team", ""))
            a = _normalize_team(ev.get("away_team", ""))
            matchup = f"{h}|{a}"
            unique_matchups.add(matchup)
        if len(unique_matchups) <= 1:
            continue  # Same matchup appearing multiple times = already handled by dedup
        # Different matchups! This team can't play 2+ matches in one day.
        best_idx = team_best[team_key][1]
        best_ev = scored[best_idx][1]
        for i in indices:
            if i != best_idx:
                phantom_indices.add(i)
        team_name = team_key.split("|", 1)[1]
        phantom_teams.append(team_name)

    if phantom_indices:
        pre_count = len(scored)
        scored = [(s, e) for idx, (s, e) in enumerate(scored) if idx not in phantom_indices]
        unique_phantom_teams = sorted(set(phantom_teams))
        print(f"[shortlist] ⛔ PHANTOM FIXTURE FILTER: removed {pre_count - len(scored)} events "
              f"({len(unique_phantom_teams)} teams in multiple different matches)")
        if len(unique_phantom_teams) <= 20:
            for t in unique_phantom_teams:
                print(f"  phantom team: {t}")
    else:
        print("[shortlist] ✅ No phantom fixtures detected (no team in multiple matches)")

    # Select top_n with sport diversity enforcement
    # Strategy: 2-phase selection
    #   Phase 1: guarantee minimum slots per sport (ensures ≥min_sports)
    #   Phase 2: fill remaining slots by global score with per-sport caps

    # QUALITY FLOOR: Remove events with scores too low to be useful.
    # An event in a recognized league with basic odds data scores ~50+.
    # An obscure league event with some safety data scores ~15-25.
    # Below 10 = garbage from unbettable regions after multiplier penalties.
    # NOTE: R3 compliance — threshold is LOW to avoid auto-rejection of edge cases.
    # The scoring + multipliers already push garbage down; threshold only catches absolute junk.
    MIN_SCORE_THRESHOLD = 10.0
    pre_floor_count = len(scored)
    scored = [(s, e) for s, e in scored if s >= MIN_SCORE_THRESHOLD]
    if len(scored) < pre_floor_count:
        print(f"[shortlist] Quality floor: removed {pre_floor_count - len(scored)} sub-threshold events (score < {MIN_SCORE_THRESHOLD})")

    selected = []
    sport_counts: Counter = Counter()
    selected_keys: set[str] = set()

    total_by_sport = Counter(s[1]["sport"] for s in scored)
    available_sports = sorted(total_by_sport.keys())

    # Per-sport minimum guaranteed slots
    sport_min = {}
    for sport in available_sports:
        avail = total_by_sport[sport]
        if sport in TIER1_SPORTS:
            sport_min[sport] = min(3, avail)
        else:
            sport_min[sport] = min(2, avail)

    # Phase 1: guarantee minimums for each sport (pick top-scored per sport)
    by_sport = defaultdict(list)
    for score, event in scored:
        by_sport[event["sport"]].append((score, event))

    for sport in available_sports:
        needed = sport_min[sport]
        for score, event in by_sport[sport][:needed]:
            key = f"{event.get('home_team','')}|{event.get('away_team','')}|{event.get('kickoff','')}"
            if key not in selected_keys:
                selected.append((score, event))
                selected_keys.add(key)
                sport_counts[sport] += 1

    # Phase 2: fill remaining slots by global score, cap per sport
    uncapped = top_n <= 0
    remaining = len(scored) if uncapped else (top_n - len(selected))

    if remaining > 0:
        if not uncapped:
            max_per_sport_key = max(top_n // 3, 8)  # KEY sports: max 33%
            max_per_sport_sup = max(top_n // 8, 4)  # SUPPORT sports: max ~12%
        else:
            # Even uncapped, hard cap per-sport to prevent tennis/basketball flood
            # 25% max ensures no single sport dominates when sources can't cover them
            max_per_sport = max(int(len(scored) * 0.25), 30)

        for score, event in scored:
            key = f"{event.get('home_team','')}|{event.get('away_team','')}|{event.get('kickoff','')}"
            if key in selected_keys:
                continue
            sport = event["sport"]
            if not uncapped:
                cap = max_per_sport_key if sport in TIER1_SPORTS else max_per_sport_sup
                if sport_counts[sport] >= cap:
                    continue
            else:
                if sport_counts[sport] >= max_per_sport:
                    continue
            selected.append((score, event))
            selected_keys.add(key)
            sport_counts[sport] += 1
            if not uncapped and len(selected) >= top_n:
                break

    # Re-sort by score
    selected.sort(key=lambda x: -x[0])

    n_sports_selected = len(set(e["sport"] for _, e in selected))
    print(f"[shortlist] Selected {len(selected)} events across {n_sports_selected} sports")
    if n_sports_selected < min_sports:
        print(f"[shortlist] WARNING: Only {n_sports_selected} sports (need ≥{min_sports}). "
              f"Available sports with events: {len(total_by_sport)}")

    return selected


def write_shortlist_md(
    selected: list[tuple[float, dict]],
    date: str,
    stats_first: bool = False,
) -> Path:
    """Write the shortlist markdown artifact."""
    n_events = len(selected)
    sports = sorted(set(e["sport"] for _, e in selected))
    n_sports = len(sports)

    # §1.8 fixture verification
    odds_keys, fixtures_keys = _load_verification_sources(date)

    lines = []
    lines.append(f"# S2 Shortlist — {date} v1")
    lines.append(f"**Session:** Full (06:00 CEST → 05:59 CEST next day)")
    lines.append(f"**Generated by:** `build_shortlist.py` from market matrix ({n_events} events)")
    lines.append(f"**Candidates:** {n_events} | **Sports:** {n_sports} | "
                 f"**Gate:** {'PASS' if n_sports >= 8 else 'FAIL'} (need ≥8 sports)")
    if stats_first:
        lines.append(f"**Mode:** STATS-FIRST (CHECK_BETCLIC events included)")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Summary by sport
    sport_events = defaultdict(list)
    for score, event in selected:
        sport_events[event["sport"]].append((score, event))

    lines.append("## Sport Distribution")
    lines.append("")
    lines.append("| Sport | Count | Tier | Avg Score |")
    lines.append("|-------|-------|------|-----------|")
    for sport in sports:
        evts = sport_events[sport]
        tier = "KEY" if sport in TIER1_SPORTS else "SUPPORT"
        avg_score = sum(s for s, _ in evts) / len(evts)
        lines.append(f"| {sport} | {len(evts)} | {tier} | {avg_score:.1f} |")
    lines.append("")
    lines.append("---")
    lines.append("")

    # Events grouped by sport
    candidate_num = 0
    for sport in sports:
        evts = sport_events[sport]
        sport_upper = sport.upper().replace("_", " ")
        lines.append(f"## {sport_upper} — {len(evts)} candidates")
        lines.append("")

        for score, event in evts:
            candidate_num += 1
            home = event.get("home_team", "?")
            away = event.get("away_team", "?")
            comp = event.get("competition", "Unknown")
            kickoff = event.get("kickoff", "?")
            tier = event.get("data_tier", "FIXTURE_ONLY")
            odds_mkts = event.get("odds_markets", [])
            safety_mkts = event.get("safety_markets", [])
            is_verified, ver_sources = _verify_fixture(home, away, odds_keys, fixtures_keys)

            ver_icon = "✅" if is_verified else "⚠️"
            lines.append(f"### #{candidate_num} — {home} vs {away} {ver_icon}")
            lines.append(f"- **Competition:** {comp}")
            lines.append(f"- **Kickoff:** {kickoff}")

            # Available markets
            if odds_mkts:
                mkt_names = sorted(set(m.get("market", "?") for m in odds_mkts))
                odds_range = [m.get("best_odds", 0) for m in odds_mkts if m.get("best_odds")]
                odds_str = ""
                if odds_range:
                    odds_str = f" (odds: {min(odds_range):.2f}—{max(odds_range):.2f})"
                lines.append(f"- **Available markets:** {', '.join(mkt_names[:8])}{odds_str}")
            else:
                lines.append(f"- **Available markets:** CHECK_BETCLIC (no API odds)")

            lines.append(f"- **Data tier:** {tier} | **Score:** {score:.1f}")
            if not is_verified:
                lines.append(f"- **⚠️ UNVERIFIED** — not found in odds-api or fixtures-api. Verify before S3.")

            # Safety data
            if safety_mkts:
                safety_strs = []
                for sm in safety_mkts[:4]:
                    s = f"{sm.get('market', '?')} (safety: {sm.get('safety_score', '?')})"
                    safety_strs.append(s)
                lines.append(f"- **Safety markets:** {'; '.join(safety_strs)}")

            # Statistical markets to evaluate
            std = STANDARD_MARKET_LINES.get(sport, [])
            if std:
                stat_names = [m["market"] for m in std]
                lines.append(f"- **Statistical markets to evaluate:** {', '.join(stat_names)}")

            lines.append("")

    md_text = "\n".join(lines)
    output_path = DATA_DIR / f"{date}_s2_shortlist.md"
    output_path.write_text(md_text, encoding="utf-8")
    print(f"[shortlist] Written: {output_path} ({candidate_num} candidates)")
    return output_path


def write_shortlist_json(selected: list[tuple[float, dict]], date: str) -> Path:
    """Write shortlist as JSON for downstream consumption."""

    # §1.8 fixture verification
    odds_keys, fixtures_keys = _load_verification_sources(date)
    verified_count = 0
    unverified_count = 0

    output = {
        "date": date,
        "total_candidates": len(selected),
        "sports": sorted(set(e["sport"] for _, e in selected)),
        "candidates": [],
    }
    for i, (score, event) in enumerate(selected, 1):
        home = event.get("home_team", "")
        away = event.get("away_team", "")
        is_verified, ver_sources = _verify_fixture(home, away, odds_keys, fixtures_keys)
        if is_verified:
            verified_count += 1
        else:
            unverified_count += 1

        output["candidates"].append({
            "rank": i,
            "score": round(score, 1),
            "sport": event["sport"],
            "home_team": home,
            "away_team": away,
            "competition": event.get("competition", ""),
            "kickoff": normalize_kickoff(event.get("kickoff", ""), date),
            "data_tier": event.get("data_tier", ""),
            "n_odds_markets": len(event.get("odds_markets", [])),
            "n_safety_markets": len(event.get("safety_markets", [])),
            "odds_markets": event.get("odds_markets", []),
            "safety_markets": event.get("safety_markets", []),
            "fixture_verified": is_verified,
            "verification_sources": ver_sources,
        })

    output["fixture_verification"] = {
        "verified": verified_count,
        "unverified": unverified_count,
        "pct": round(100 * verified_count / max(len(selected), 1), 1),
    }
    if unverified_count:
        print(f"[shortlist] §1.8 Fixture verification: {verified_count} verified, "
              f"{unverified_count} UNVERIFIED ({output['fixture_verification']['pct']}% verified)")

    output_path = DATA_DIR / f"{date}_s2_shortlist.json"
    output_path.write_text(
        json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"[shortlist] JSON: {output_path}")
    return output_path


def _apply_betclic_filter(selected: list[tuple[float, dict]], date: str, out) -> Path | None:
    """Filter shortlist to only events confirmed on Betclic.

    Reads betclic_market_validation_{date}.json and produces
    {date}_s2_shortlist_bettable.json with only matched events.
    """
    validation_path = DATA_DIR / f"betclic_market_validation_{date}.json"
    if not validation_path.exists():
        out.warning(f"Betclic validation not found: {validation_path} — skipping filter")
        return None

    try:
        validation = json.loads(validation_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        out.warning(f"Failed to read Betclic validation: {e}")
        return None

    # Build set of Betclic-confirmed events (normalized)
    betclic_events: dict[str, dict] = {}
    events_list = validation.get("events", validation) if isinstance(validation, dict) else validation
    for ev in events_list:
        name = ev.get("event_name", "")
        # Clean up "Obstawianie X | Bukmacher Y | Betclic Polska Bonus" format
        if "Obstawianie " in name and " | " in name:
            name = name.replace("Obstawianie ", "").split(" | ")[0]
        confirmed = ev.get("confirmed_market_types", [])
        if confirmed:
            norm = _normalize_team(name)
            betclic_events[norm] = {
                "confirmed_market_types": confirmed,
                "open_market_count": ev.get("open_market_count", 0),
            }

    # Match shortlist candidates against Betclic events
    filtered = []
    rejected_count = 0
    for score, event in selected:
        home = event.get("home_team", "")
        away = event.get("away_team", "")
        event_key = f"{_normalize_team(home)} v {_normalize_team(away)}"
        event_key_alt = f"{_normalize_team(away)} v {_normalize_team(home)}"

        match = betclic_events.get(event_key) or betclic_events.get(event_key_alt)

        # Fuzzy match: check if both team name parts appear in any Betclic event
        if not match:
            h_norm = _normalize_team(home)
            a_norm = _normalize_team(away)
            for bname, binfo in betclic_events.items():
                if h_norm and a_norm and h_norm in bname and a_norm in bname:
                    match = binfo
                    break
                if h_norm and a_norm and a_norm in bname and h_norm in bname:
                    match = binfo
                    break

        if match:
            event["betclic_confirmed"] = True
            event["betclic_market_types"] = match["confirmed_market_types"]
            event["betclic_market_count"] = match["open_market_count"]
            filtered.append((score, event))
        else:
            rejected_count += 1

    # Write bettable shortlist
    output = {
        "date": date,
        "total_candidates": len(filtered),
        "filter": "betclic_confirmed_only",
        "sports": sorted(set(e["sport"] for _, e in filtered)),
        "rejected_not_on_betclic": rejected_count,
        "candidates": [
            {
                "rank": i,
                "score": round(score, 1),
                "sport": event["sport"],
                "home_team": event.get("home_team", ""),
                "away_team": event.get("away_team", ""),
                "competition": event.get("competition", ""),
                "kickoff": normalize_kickoff(event.get("kickoff", ""), date),
                "data_tier": event.get("data_tier", ""),
                "betclic_market_types": event.get("betclic_market_types", []),
                "betclic_market_count": event.get("betclic_market_count", 0),
                "n_odds_markets": len(event.get("odds_markets", [])),
                "n_safety_markets": len(event.get("safety_markets", [])),
            }
            for i, (score, event) in enumerate(filtered, 1)
        ],
    }

    output_path = DATA_DIR / f"{date}_s2_shortlist_bettable.json"
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"\n[shortlist] BETCLIC FILTER: {len(filtered)} bettable / {rejected_count} rejected")
    print(f"[shortlist] Bettable shortlist: {output_path}")
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Build ranked S2 shortlist from market matrix")
    parser.add_argument("--date", help="Date YYYY-MM-DD (default: today)")
    parser.add_argument("--top", type=int, default=0, help="Number of candidates to select (0 = all, default: 0)")
    parser.add_argument("--stats-first", action="store_true",
                        help="Include FIXTURE_ONLY events from major competitions")
    parser.add_argument("--min-sports", type=int, default=5, help="Minimum sport diversity (default: 5)")
    parser.add_argument("--betclic-filter", action="store_true",
                        help="Filter shortlist to only Betclic-confirmed events (reads validation JSON)")
    add_agent_args(parser)
    args = parser.parse_args()

    out = AgentOutput("s1e_shortlist", verbose=args.verbose, stop_on_error=args.stop_on_error)

    date = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        out.error(f"Invalid date format '{date}'. Use YYYY-MM-DD.")
        out.summary(verdict="FAILED", metrics={"error": "invalid_date"})
        sys.exit(2)

    # V5: Input contract pre-check (warning-only, never blocks)
    _contract = AgentOutput.validate_input_contract("s1e_shortlist", date)
    if _contract["status"] != "OK":
        for _w in _contract.get("warnings", []):
            out.warning(f"Input contract: {_w}")
        for _m in _contract.get("missing", []):
            out.warning(f"Missing input: {_m}")

    out.event("start", date=date, stats_first=args.stats_first)

    selected = build_shortlist(
        date=date,
        top_n=args.top,
        stats_first=args.stats_first,
        min_sports=args.min_sports,
    )

    write_shortlist_md(selected, date, stats_first=args.stats_first)
    write_shortlist_json(selected, date)

    # Betclic filter: produce a bettable-only shortlist
    if args.betclic_filter:
        bettable_path = _apply_betclic_filter(selected, date, out)
        if bettable_path:
            out.event("betclic_filter_applied", output=str(bettable_path))

    # Save shortlist summary to DB
    try:
        from bet.db.connection import get_db
        from bet.db.repositories import PipelineRepo
        from collections import Counter as _Counter
        shortlist_stats = {
            "total_candidates": len(selected),
            "sport_distribution": dict(_Counter(e["sport"] for _, e in selected)),
            "top_10": [
                {
                    "home_team": e.get("home_team", ""),
                    "away_team": e.get("away_team", ""),
                    "sport": e.get("sport", ""),
                    "score": round(score, 1),
                }
                for score, e in selected[:10]
            ],
        }
        with get_db() as conn:
            repo = PipelineRepo(conn)
            repo.start_step(date, "s1e_shortlist")
            repo.complete_step(date, "s1e_shortlist", stats=shortlist_stats)
            conn.commit()
            out.event("db_saved", candidates=len(selected))
    except Exception as e:
        out.warning(f"DB shortlist save failed (non-fatal): {e}")

    # Summary metrics
    sport_counts = Counter(e["sport"] for _, e in selected)
    tier_counts = Counter(e["data_tier"] for _, e in selected)

    print(f"\n{'='*60}")
    print(f"SHORTLIST SUMMARY — {date}")
    print(f"{'='*60}")
    print(f"Candidates: {len(selected)} | Sports: {len(sport_counts)}")
    print(f"\nBy sport:")
    for sport, count in sport_counts.most_common():
        tier = "KEY" if sport in TIER1_SPORTS else "SUP"
        print(f"  [{tier}] {sport}: {count}")
        if args.verbose:
            out.event("sport_count", sport=sport, count=count, tier=tier)
    print(f"\nBy data tier:")
    for tier, count in tier_counts.most_common():
        print(f"  {tier}: {count}")
    print(f"\nTop 10 by score:")
    for i, (score, event) in enumerate(selected[:10], 1):
        print(f"  {i}. [{event['sport']}] {event.get('home_team','?')} vs {event.get('away_team','?')} "
              f"({event.get('competition','?')}) — score {score:.1f}, tier {event['data_tier']}")

    out.summary(
        verdict="OK" if len(selected) >= 10 else ("PARTIAL" if selected else "FAILED"),
        metrics={
            "total_candidates": len(selected),
            "sports_count": len(sport_counts),
            "sport_distribution": dict(sport_counts),
            "tier_distribution": dict(tier_counts),
            "full_data": tier_counts.get("FULL", 0),
            "partial_data": tier_counts.get("PARTIAL", 0),
            "minimal_data": tier_counts.get("MINIMAL", 0) + tier_counts.get("FIXTURE_ONLY", 0),
        },
    )

    sys.exit(0 if selected else 1)


if __name__ == "__main__":
    main()
