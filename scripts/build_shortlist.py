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
# Competition tiers (higher = more important)
# ---------------------------------------------------------------------------
COMP_TIER_KEYWORDS: dict[str, list[tuple[int, list[str]]]] = {
    "football": [
        (10, ["champions league", "europa league", "conference league", "world cup",
              "euro 202", "copa america", "club world cup"]),
        (9, ["english premier league", "la liga", "laliga", "bundesliga", "serie a", "ligue 1"]),
        (8, ["eredivisie", "primeira liga", "ekstraklasa", "super lig", "championship",
             "copa libertadores", "copa sudamericana", "fa cup", "coppa italia",
             "dfb pokal", "copa del rey", "coupe de france"]),
        (7, ["mls", "brasileirao", "allsvenskan", "eliteserien", "superliga",
             "belgian", "jupiler", "scottish", "swiss super league"]),
        (6, ["2. bundesliga", "serie b", "ligue 2", "segunda", "liga mx"]),
        (5, ["k-league", "j-league", "a-league", "nations league", "qualification",
             "1. liga", "first division b", "eerste divisie"]),
        (3, []),  # default for any unknown football league (raised from 2)
    ],
    "tennis": [
        (10, ["grand slam", "australian open", "french open", "wimbledon", "us open",
              "roland garros"]),
        (9, ["masters 1000", "atp 1000", "wta 1000", "indian wells", "miami",
             "monte carlo", "madrid", "rome", "canada", "cincinnati", "shanghai", "paris"]),
        (8, ["atp 500", "wta 500"]),
        (7, ["atp 250", "wta 250"]),
        (5, ["challenger", "itf"]),
    ],
    "basketball": [
        (10, ["nba playoff", "nba finals", "fiba world cup", "olympic"]),
        (9, ["nba", "euroleague"]),
        (8, ["eurocup", "ncaa", "acb", "final four"]),
        (7, ["plk", "bbl", "bcl", "fiba", "lnb", "nbl"]),
    ],
    "volleyball": [
        (10, ["cev champions league", "world championship", "nations league finals", "olympic"]),
        (9, ["plusliga", "superlega"]),
        (8, ["serie a", "ligue a", "bundesliga", "cev"]),
        (7, ["efeler", "superliga", "plusliga playoff", "superlega playoff"]),
    ],
    "hockey": [
        (10, ["nhl playoff", "stanley cup", "iihf world"]),
        (9, ["nhl", "khl"]),
        (8, ["shl", "liiga", "del"]),
    ],
    "handball": [
        (10, ["ehf champions league final four", "world championship"]),
        (9, ["ehf champions league"]),
        (8, ["ehf", "bundesliga", "starligue"]),
        (7, ["liga asobal", "superliga"]),
    ],
    "baseball": [
        (10, ["world series", "mlb playoff"]),
        (9, ["mlb"]),
        (7, ["npb", "kbo"]),
    ],
    "snooker": [
        (10, ["world championship"]),
        (9, ["masters", "champion of champions", "uk championship"]),
        (7, ["grand prix", "open", "trophy", "classic"]),
    ],
    "darts": [
        (10, ["world championship", "grand slam"]),
        (9, ["pdc", "premier league"]),
        (7, ["world grand prix", "players championship"]),
    ],
    "esports": [
        (10, ["major", "worlds", "the international"]),
        (8, ["champions", "blast premier"]),
        (6, ["esl", "blast", "iem", "pgl"]),
    ],
    "mma": [
        (10, ["ufc numbered", "ufc ppv"]),
        (9, ["ufc"]),
        (7, ["bellator", "pfl", "one"]),
    ],
    "table_tennis": [
        (10, ["world championship", "wtt grand smash", "olympic"]),
        (8, ["wtt champions"]),
        (6, ["wtt star contender", "wtt"]),
    ],
    "padel": [
        (10, ["premier padel major"]),
        (8, ["premier padel"]),
        (6, ["world padel tour"]),
    ],
    "speedway": [
        (10, ["speedway gp"]),
        (8, ["ekstraliga"]),
        (6, ["sec"]),
    ],
}

# Tier 1 = KEY sports (always prioritize); Tier 2 = support
TIER1_SPORTS = {"football", "volleyball", "basketball", "tennis"}


def _score_competition(sport: str, competition: str) -> int:
    """Score a competition within its sport (higher = more important)."""
    if not competition:
        return 1
    comp_lower = competition.lower()

    # Penalize clearly obscure/minor leagues
    obscure_markers = [
        "amateur", "reserve",
        "regional", "county", "division 4",
        "sikkim", "mizoram", "manipur",  # Indian state leagues with zero data
    ]
    if any(m in comp_lower for m in obscure_markers):
        return 1

    tiers = COMP_TIER_KEYWORDS.get(sport, [])
    for score, keywords in tiers:
        if keywords and any(kw in comp_lower for kw in keywords):
            return score
    # Default per-sport base
    for score, keywords in tiers:
        if not keywords:
            return score
    return 2


def _score_event(event: dict, tipster_events: set[str]) -> float:
    """Score an event for shortlist ranking. Higher = better candidate."""
    sport = event["sport"]
    comp = event.get("competition", "")
    tier = event.get("data_tier", "FIXTURE_ONLY")
    has_odds = bool(event.get("odds_markets"))
    n_odds = len(event.get("odds_markets", []))
    has_safety = bool(event.get("safety_markets"))
    n_safety = len(event.get("safety_markets", []))

    score = 0.0

    # 1. Data tier (odds availability matters but shouldn't dominate)
    tier_scores = {"FULL": 30, "ODDS_RICH": 25, "ODDS_BASIC": 18, "STATS_ONLY": 12, "FIXTURE_ONLY": 5}
    score += tier_scores.get(tier, 0)

    # 2. Competition importance (HIGHEST weight — premier league > obscure league)
    comp_score = _score_competition(sport, comp)
    score += comp_score * 5  # max 50

    # 3. Sport tier bonus
    if sport in TIER1_SPORTS:
        score += 10

    # 4. Number of odds markets (more = better analysis potential)
    score += min(n_odds * 2, 12)  # cap at 12

    # 5. Safety data availability
    score += min(n_safety * 3, 15)  # cap at 15

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

    # 8. Minor league value edge (§SCAN.8) — less popular leagues have more mispricing
    if comp_score <= 7 and comp_score >= 3 and (has_safety or n_odds > 0):
        # Non-top-tier league WITH data coverage = value edge
        score += 6

    # 9. Major tournament protection (§SCAN.7) — tournaments always get priority
    if comp_score >= 9:
        # Major tournament event — ensure it never gets dropped
        score += 15

    # 10. Deep data richness boost — teams with ESPN gamelogs get better analysis
    if sport in ("basketball", "hockey", "baseball"):
        try:
            from db_data_loader import load_player_gamelogs_for_team
            home_team = event.get("home_team", "")
            if home_team:
                gamelogs = load_player_gamelogs_for_team(home_team, sport, n=1)
                if gamelogs:
                    score += 8  # Rich per-player data = higher analysis confidence
        except Exception:
            pass

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


def build_shortlist(
    date: str,
    top_n: int = 0,
    stats_first: bool = False,
    min_sports: int = 8,
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
        r"\d+\s*'",  # match minute markers (37 ')
        re.I,
    )
    filtered = []
    garbage_count = 0
    for score, event in scored:
        home = event.get("home_team", "")
        away = event.get("away_team", "")
        if len(home) > 60 or len(away) > 60:
            garbage_count += 1
            continue
        if _garbage_re.search(home) or _garbage_re.search(away):
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

    # Select top_n with sport diversity enforcement
    # Strategy: 2-phase selection
    #   Phase 1: guarantee minimum slots per sport (ensures ≥min_sports)
    #   Phase 2: fill remaining slots by global score with per-sport caps
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
            max_per_sport_key = max(top_n // 4, 8)  # KEY sports: max 25%
            max_per_sport_sup = max(top_n // 8, 4)  # SUPPORT sports: max ~12%

        for score, event in scored:
            key = f"{event.get('home_team','')}|{event.get('away_team','')}|{event.get('kickoff','')}"
            if key in selected_keys:
                continue
            sport = event["sport"]
            if not uncapped:
                cap = max_per_sport_key if sport in TIER1_SPORTS else max_per_sport_sup
                if sport_counts[sport] >= cap:
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


def main():
    parser = argparse.ArgumentParser(description="Build ranked S2 shortlist from market matrix")
    parser.add_argument("--date", help="Date YYYY-MM-DD (default: today)")
    parser.add_argument("--top", type=int, default=0, help="Number of candidates to select (0 = all, default: 0)")
    parser.add_argument("--stats-first", action="store_true",
                        help="Include FIXTURE_ONLY events from major competitions")
    parser.add_argument("--min-sports", type=int, default=8, help="Minimum sport diversity (default: 8)")
    args = parser.parse_args()

    date = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", date):
        print(f"[shortlist] ERROR: Invalid date format '{date}'. Use YYYY-MM-DD.")
        sys.exit(1)

    selected = build_shortlist(
        date=date,
        top_n=args.top,
        stats_first=args.stats_first,
        min_sports=args.min_sports,
    )

    write_shortlist_md(selected, date, stats_first=args.stats_first)
    write_shortlist_json(selected, date)

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
            print(f"  → DB: saved shortlist summary ({len(selected)} candidates)")
    except Exception as e:
        print(f"  ⚠ DB shortlist save failed (non-fatal): {e}")

    # Summary
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
    print(f"\nBy data tier:")
    for tier, count in tier_counts.most_common():
        print(f"  {tier}: {count}")
    print(f"\nTop 10 by score:")
    for i, (score, event) in enumerate(selected[:10], 1):
        print(f"  {i}. [{event['sport']}] {event.get('home_team','?')} vs {event.get('away_team','?')} "
              f"({event.get('competition','?')}) — score {score:.1f}, tier {event['data_tier']}")


if __name__ == "__main__":
    main()
