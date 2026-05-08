#!/usr/bin/env python3
"""Aggressive tennis stats enrichment — builds deep L10 for all shortlisted players.

Scrapes ESPN scoreboard across 45+ days to build proper match history for
every tennis player in the shortlist. This ensures the pipeline has enough
data (≥10 matches per player) to evaluate 3+ markets (Total Games, Player Games,
Total Sets) and pass the INSUFFICIENT_MARKETS gate.

Usage:
    python3 scripts/enrich_tennis_stats.py --date 2026-05-07
    python3 scripts/enrich_tennis_stats.py --date 2026-05-07 --force  # ignore cache TTL
    python3 scripts/enrich_tennis_stats.py --date 2026-05-07 --players "Arnaldi,Tabilo"
"""

import argparse
import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import requests
from build_stats_cache import (
    CACHE_DIR,
    FORM_TTL_HOURS,
    slugify,
    validate_sport,
    is_cache_valid,
    update_cache,
    create_team_cache_entry,
    read_cache,
    now_iso,
)

DATA_DIR = Path(__file__).parent.parent / "betting" / "data"
ESPN_BASE = "http://site.api.espn.com/apis/site/v2/sports/tennis"
HEADERS = {"Accept": "application/json"}

# Scan 60 days back — dense for recent (every day), sparser for older
LOOKBACK_DAYS = 60
MIN_MATCHES_TARGET = 10


def _fetch_scoreboard(league: str, date_str: str) -> dict:
    """Fetch ESPN tennis scoreboard for a date (YYYYMMDD format)."""
    url = f"{ESPN_BASE}/{league}/scoreboard"
    try:
        r = requests.get(url, params={"dates": date_str}, headers=HEADERS, timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception:
        return {}


def _build_all_matches_index(leagues: list[str] = None) -> dict[str, list[dict]]:
    """Build a complete index: player_name → [match_data, ...] across 60 days.

    This is the AGGRESSIVE approach: fetch all scoreboard data once,
    then index by player name for O(1) lookup per player.
    """
    if leagues is None:
        leagues = ["atp", "wta"]

    today = datetime.now(timezone.utc).date()
    # Dense scanning: every day for last 21 days, then every 3 days for older
    dates_to_scan = [today - timedelta(days=d) for d in range(0, 22)]
    dates_to_scan += [today - timedelta(days=d) for d in range(24, LOOKBACK_DAYS + 1, 3)]

    # player_name_lower → [match_entries]
    player_index: dict[str, list[dict]] = {}
    seen_comp_ids: set[str] = set()
    total_matches = 0

    print(f"[enrich-tennis] Scanning {len(dates_to_scan)} dates × {len(leagues)} leagues...")

    for league in leagues:
        for scan_date in dates_to_scan:
            date_str = scan_date.strftime("%Y%m%d")
            data = _fetch_scoreboard(league, date_str)
            if not data:
                continue

            for event in data.get("events", []):
                for grouping in event.get("groupings", []):
                    for comp in grouping.get("competitions", []):
                        comp_id = str(comp.get("id", ""))
                        if comp_id in seen_comp_ids:
                            continue

                        status = comp.get("status", {}).get("type", {})
                        if status.get("state") != "post":
                            continue

                        competitors = comp.get("competitors", [])
                        if len(competitors) < 2:
                            continue

                        seen_comp_ids.add(comp_id)
                        total_matches += 1

                        # Extract match data from linescores
                        match_data = _extract_match_data(comp, league)
                        if not match_data:
                            continue

                        # Index by BOTH player names
                        for player_name in [match_data["home_name"], match_data["away_name"]]:
                            key = player_name.lower().strip()
                            if key:
                                player_index.setdefault(key, []).append(match_data)

            # Brief pause to be polite to ESPN
            time.sleep(0.1)

    print(f"[enrich-tennis] Indexed {total_matches} completed matches across {len(player_index)} players")
    return player_index


def _extract_match_data(comp: dict, league: str) -> dict | None:
    """Extract complete match data from a competition entry."""
    competitors = comp.get("competitors", [])
    if len(competitors) < 2:
        return None

    comp_id = str(comp.get("id", ""))
    match_date = comp.get("date", comp.get("startDate", ""))
    if match_date:
        match_date = match_date[:10]  # YYYY-MM-DD

    home_c = competitors[0]
    away_c = competitors[1]

    home_ath = home_c.get("athlete", {})
    away_ath = away_c.get("athlete", {})

    home_name = home_ath.get("displayName", "")
    away_name = away_ath.get("displayName", "")

    if not home_name or not away_name:
        return None

    # Parse linescores → derive stats
    home_ls = home_c.get("linescores", [])
    away_ls = away_c.get("linescores", [])

    home_games = sum(int(s.get("value", 0)) for s in home_ls)
    away_games = sum(int(s.get("value", 0)) for s in away_ls)
    home_sets = sum(1 for s in home_ls if s.get("winner", False))
    away_sets = sum(1 for s in away_ls if s.get("winner", False))
    total_sets_played = max(len(home_ls), len(away_ls))

    return {
        "fixture_id": comp_id,
        "date": match_date,
        "league": league,
        "home_name": home_name,
        "away_name": away_name,
        "home_id": str(home_ath.get("id", "")),
        "away_id": str(away_ath.get("id", "")),
        "stats": {
            "sets_won": {"home": float(home_sets), "away": float(away_sets)},
            "games_won": {"home": float(home_games), "away": float(away_games)},
            "total_games": {"home": float(home_games), "away": float(away_games)},
            "total_sets": {"home": float(total_sets_played), "away": float(total_sets_played)},
        },
        "total_games_combined": float(home_games + away_games),
    }


def _build_player_form(player_name: str, matches: list[dict]) -> dict:
    """Build form data (L10/L5 averages) for a player from their match history."""
    # Sort by date descending
    sorted_matches = sorted(matches, key=lambda m: m.get("date", ""), reverse=True)

    # Deduplicate by fixture_id
    seen_ids = set()
    unique_matches = []
    for m in sorted_matches:
        fid = m.get("fixture_id", "")
        if fid not in seen_ids:
            seen_ids.add(fid)
            unique_matches.append(m)

    # Take up to 15 for L10 + trend analysis
    recent = unique_matches[:15]
    if not recent:
        return {}

    # Build l10_matches entries
    l10_entries = []
    for match in recent[:10]:
        # Determine which side this player was on
        is_home = match["home_name"].lower().strip() == player_name.lower().strip()
        side = "home" if is_home else "away"
        opp_side = "away" if is_home else "home"

        opponent = match[opp_side + "_name"]
        stats_entry = {}

        for stat_key, stat_vals in match["stats"].items():
            if isinstance(stat_vals, dict):
                stats_entry[stat_key] = stat_vals

        l10_entries.append({
            "date": match["date"],
            "opponent": opponent,
            "fixture_id": match["fixture_id"],
            "stats": stats_entry,
            "was_away": not is_home,
        })

    # Compute averages
    l10_avg = _compute_averages(l10_entries, player_name)
    l5_avg = _compute_averages(l10_entries[:5], player_name)

    return {
        "l10_matches": l10_entries,
        "l10_avg": l10_avg,
        "l5_avg": l5_avg,
        "recent_matches": l10_entries[:5],
    }


def _compute_averages(entries: list[dict], player_name: str) -> dict:
    """Compute stat averages from match entries."""
    if not entries:
        return {}

    # Accumulate stats
    stat_sums: dict[str, float] = {}
    stat_counts: dict[str, int] = {}

    for entry in entries:
        is_away = entry.get("was_away", False)
        side = "away" if is_away else "home"

        stats = entry.get("stats", {})
        for stat_key, stat_vals in stats.items():
            if not isinstance(stat_vals, dict):
                continue
            # Player's own value
            player_val = stat_vals.get(side, 0)
            key = f"{stat_key}_{side}"
            stat_sums[key] = stat_sums.get(key, 0) + player_val
            stat_counts[key] = stat_counts.get(key, 0) + 1

            # Also store combined (for total markets)
            opp_side = "away" if side == "home" else "home"
            opp_val = stat_vals.get(opp_side, 0)
            combined_key = f"{stat_key}"
            stat_sums[combined_key] = stat_sums.get(combined_key, 0) + player_val + opp_val
            stat_counts[combined_key] = stat_counts.get(combined_key, 0) + 1

    averages = {}
    for key, total in stat_sums.items():
        count = stat_counts.get(key, 1)
        averages[key] = round(total / count, 1)

    return averages


def _update_player_cache(player_name: str, form_data: dict, force: bool = False) -> bool:
    """Write player form data to stats cache."""
    sport = "tennis"
    slug = slugify(player_name)
    cache_file = CACHE_DIR / sport / f"{slug}.json"

    # Check if cache is still valid (unless forcing)
    if not force and is_cache_valid(cache_file, FORM_TTL_HOURS):
        # Check if existing cache has enough matches
        existing = read_cache(sport, player_name)
        if existing:
            existing_form = existing.get("form", {})
            existing_l10 = existing_form.get("l10_matches", [])
            if len(existing_l10) >= MIN_MATCHES_TARGET:
                return False  # Already good

    # Create/update cache entry
    cache_dir = CACHE_DIR / sport
    cache_dir.mkdir(parents=True, exist_ok=True)

    cache_entry = {
        "team": player_name,
        "sport": sport,
        "slug": slug,
        "last_updated": now_iso(),
        "ttl_hours": FORM_TTL_HOURS,
        "form": form_data,
        "api_source": "espn-tennis-enriched",
    }

    cache_file.write_text(json.dumps(cache_entry, indent=2, ensure_ascii=False), encoding="utf-8")

    # Persist to DB
    try:
        from build_stats_cache import _persist_to_db
        _persist_to_db(sport, player_name, cache_entry)
    except Exception as e:
        print(f"[enrich-tennis] DB write failed for {player_name}: {e}")

    return True


def get_shortlisted_tennis_players(date: str) -> list[str]:
    """Extract all tennis player names from today's shortlist."""

    # Try multiple filename patterns (pipeline uses YYYY-MM-DD, legacy uses YYYYMMDD)
    patterns = [
        DATA_DIR / f"{date}_s2_shortlist.json",
        DATA_DIR / f"{date.replace('-', '')}_s2_shortlist.json",
    ]

    shortlist_data = None
    for pattern in patterns:
        if pattern.exists():
            shortlist_data = json.loads(pattern.read_text(encoding="utf-8"))
            break

    if not shortlist_data:
        print(f"[enrich-tennis] No shortlist found for {date}")
        return []

    players = set()
    for candidate in shortlist_data.get("candidates", []):
        if candidate.get("sport") != "tennis":
            continue
        home = candidate.get("home_team", "")
        away = candidate.get("away_team", "")
        if home:
            players.add(home)
        if away:
            players.add(away)

    return sorted(players)


def main():
    parser = argparse.ArgumentParser(description="Enrich tennis stats cache with deep historical data")
    parser.add_argument("--date", required=True, help="Target date (YYYY-MM-DD)")
    parser.add_argument("--force", action="store_true", help="Ignore cache TTL, re-fetch everything")
    parser.add_argument("--players", help="Comma-separated player names (override shortlist)")
    parser.add_argument("--all-indexed", action="store_true",
                        help="Update ALL players found in ESPN data (not just shortlisted)")
    args = parser.parse_args()

    # Get target players
    if args.players:
        target_players = [p.strip() for p in args.players.split(",")]
    else:
        target_players = get_shortlisted_tennis_players(args.date)

    if not target_players and not args.all_indexed:
        print("[enrich-tennis] No tennis players found in shortlist. Use --players or --all-indexed.")
        return

    print(f"[enrich-tennis] Target: {len(target_players)} players from shortlist")
    print(f"[enrich-tennis] Building 60-day match index from ESPN...")

    # STEP 1: Build complete player index from ESPN (one-time bulk fetch)
    player_index = _build_all_matches_index(["atp", "wta"])

    # STEP 2: Update cache for each target player
    updated = 0
    insufficient = 0

    players_to_process = target_players if not args.all_indexed else list(player_index.keys())

    for player_name in players_to_process:
        key = player_name.lower().strip()
        matches = player_index.get(key, [])

        if not matches:
            # Try fuzzy match (last name only)
            last_name = key.split()[-1] if " " in key else key
            for idx_key, idx_matches in player_index.items():
                if last_name in idx_key:
                    matches = idx_matches
                    break

        if len(matches) < 3:
            insufficient += 1
            continue

        # Build form data
        form_data = _build_player_form(player_name, matches)
        if not form_data or not form_data.get("l10_matches"):
            insufficient += 1
            continue

        # Update cache
        display_name = player_name
        # Try to get proper display name from match data
        for m in matches:
            if m["home_name"].lower().strip() == key:
                display_name = m["home_name"]
                break
            elif m["away_name"].lower().strip() == key:
                display_name = m["away_name"]
                break

        if _update_player_cache(display_name, form_data, force=args.force):
            updated += 1
            n_matches = len(form_data.get("l10_matches", []))
            avg_games = form_data.get("l10_avg", {}).get("total_games", 0)
            print(f"  ✅ {display_name}: {n_matches} matches, avg total_games={avg_games}")

    print(f"\n[enrich-tennis] DONE: {updated} updated, {insufficient} insufficient data")
    print(f"[enrich-tennis] Players in index: {len(player_index)}")

    # STEP 3: Summary stats
    good_coverage = sum(
        1 for p in target_players
        if len(player_index.get(p.lower().strip(), [])) >= MIN_MATCHES_TARGET
    )
    print(f"[enrich-tennis] Coverage: {good_coverage}/{len(target_players)} players have ≥{MIN_MATCHES_TARGET} matches")


if __name__ == "__main__":
    main()
