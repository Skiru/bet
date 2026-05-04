#!/usr/bin/env python3
"""Persistent stats cache builder — fetches and caches team/player statistics.

Caches H2H data, team averages (L10, L5), and form across sessions with TTL.
The bet-statistician agent reads the cache before making fresh web requests.

Cache structure:
  betting/data/stats_cache/{sport}/{team_slug}.json
  TTL: 24h for form data, 7d for H2H data
"""

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

CACHE_DIR = Path("betting/data/stats_cache")
FORM_TTL_HOURS = 24
H2H_TTL_HOURS = 168  # 7 days


def slugify(name: str) -> str:
    """Convert team/player name to filesystem-safe slug."""
    slug = name.lower().strip()
    # Replace special chars with hyphens
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


def validate_sport(sport: str) -> str:
    """Validate and sanitize sport name to prevent path traversal."""
    if not sport or "/" in sport or ".." in sport or "\\" in sport:
        raise ValueError(f"Invalid sport name: {sport}")
    return slugify(sport)


def now_iso() -> str:
    """Current timestamp in ISO 8601."""
    return datetime.now(timezone.utc).isoformat()


def is_cache_valid(cache_file: Path, ttl_hours: int) -> bool:
    """Check if cache file exists and is within TTL."""
    if not cache_file.exists():
        return False

    try:
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        last_updated = data.get("last_updated", "")
        if not last_updated:
            return False
        updated_dt = datetime.fromisoformat(last_updated)
        age_hours = (datetime.now(timezone.utc) - updated_dt).total_seconds() / 3600
        return age_hours < ttl_hours
    except (json.JSONDecodeError, ValueError):
        return False


def read_cache(sport: str, team: str) -> dict | None:
    """Read cached data if valid, return None if expired or missing.

    When form TTL has expired but H2H data is still valid, returns the cache
    entry with form set to None so callers know form needs refresh but can
    still use H2H data.
    """
    sport = validate_sport(sport)
    slug = slugify(team)
    cache_file = CACHE_DIR / sport / f"{slug}.json"

    if not cache_file.exists():
        return None

    try:
        data = json.loads(cache_file.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, FileNotFoundError):
        return None

    form_valid = is_cache_valid(cache_file, FORM_TTL_HOURS)

    if form_valid:
        return data

    # Form expired — check if any H2H data is still valid
    h2h = data.get("h2h", {})
    valid_h2h = {}
    for opponent, h2h_data in h2h.items():
        h2h_updated = h2h_data.get("last_updated", "")
        if h2h_updated:
            try:
                h2h_dt = datetime.fromisoformat(h2h_updated)
                age = (datetime.now(timezone.utc) - h2h_dt).total_seconds() / 3600
                if age < H2H_TTL_HOURS:
                    valid_h2h[opponent] = h2h_data
            except ValueError:
                pass

    if valid_h2h:
        # Return with form cleared but H2H preserved
        data["form"] = {}
        data["h2h"] = valid_h2h
        return data

    return None


def update_cache(sport: str, team: str, data: dict) -> Path:
    """Write/update JSON cache file."""
    sport = validate_sport(sport)
    slug = slugify(team)
    sport_dir = CACHE_DIR / sport
    sport_dir.mkdir(parents=True, exist_ok=True)

    cache_file = sport_dir / f"{slug}.json"

    # Merge with existing data (preserve H2H from previous sessions)
    existing = {}
    if cache_file.exists():
        try:
            existing = json.loads(cache_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    # Merge H2H data (keep old H2H entries that aren't being updated)
    if "h2h" in existing and "h2h" in data:
        for opponent, h2h_data in existing["h2h"].items():
            if opponent not in data["h2h"]:
                # Check H2H TTL
                h2h_updated = h2h_data.get("last_updated", "")
                if h2h_updated:
                    try:
                        h2h_dt = datetime.fromisoformat(h2h_updated)
                        age = (datetime.now(timezone.utc) - h2h_dt).total_seconds() / 3600
                        if age < H2H_TTL_HOURS:
                            data["h2h"][opponent] = h2h_data
                    except ValueError:
                        pass

    cache_file.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return cache_file


def create_team_cache_entry(
    team: str,
    sport: str,
    form_data: dict | None = None,
    h2h_data: dict | None = None,
    sources: list[str] | None = None,
    api_source: str | None = None,
) -> dict:
    """Create a cache entry for a team."""
    entry = {
        "team": team,
        "sport": sport,
        "slug": slugify(team),
        "last_updated": now_iso(),
        "ttl_hours": FORM_TTL_HOURS,
        "form": form_data or {},
        "h2h": h2h_data or {},
        "sources": sources or [],
    }
    if api_source:
        entry["api_source"] = api_source
    return entry


def update_from_api(
    sport: str,
    team: str,
    normalized_matches: list,
    api_source: str,
    opponent: str | None = None,
    h2h_matches: list | None = None,
) -> Path:
    """Update cache with API-sourced per-match stats.

    Args:
        sport: sport name
        team: team name
        normalized_matches: list of NormalizedMatchStats (L10 for team form)
        api_source: e.g. "api-football"
        opponent: if provided, update H2H data for this opponent
        h2h_matches: list of NormalizedMatchStats for H2H meetings

    Stores per-match stats arrays AND computed averages.
    """
    from dataclasses import asdict

    # Build l10_matches from normalized data
    # Normalize stats so our team's values are always in the "home" key,
    # regardless of whether the team played home or away in the actual match.
    # This is critical because _cache_to_normalized_matches() always sets
    # home_team=team_name, so downstream _extract_stat_values() reads "home".
    team_lower = team.lower() if team else ""
    l10_matches = []
    for match in normalized_matches[:10]:
        raw_stats = getattr(match, "stats", {})
        home_team_match = getattr(match, "home_team", "")
        away_team_match = getattr(match, "away_team", "")

        # Detect if our team was the away side in this match
        is_away = (
            team_lower
            and away_team_match
            and team_lower == away_team_match.lower()
            and (not home_team_match or team_lower != home_team_match.lower())
        )

        # Normalize stats: swap home/away if our team was away
        normalized_stats = {}
        for key, value in raw_stats.items():
            if isinstance(value, dict) and "home" in value and "away" in value:
                if is_away:
                    normalized_stats[key] = {
                        "home": value.get("away", 0),
                        "away": value.get("home", 0),
                    }
                else:
                    normalized_stats[key] = value
            else:
                normalized_stats[key] = value

        # Set opponent name
        if is_away:
            opponent_name = home_team_match
        else:
            opponent_name = away_team_match or home_team_match

        match_entry = {
            "date": getattr(match, "date", ""),
            "opponent": opponent_name,
            "fixture_id": getattr(match, "fixture_id", ""),
            "stats": normalized_stats,
            "was_away": is_away,
        }
        l10_matches.append(match_entry)

    # Sort by date descending
    l10_matches.sort(key=lambda m: m.get("date", ""), reverse=True)

    # Compute L10 and L5 averages
    l10_avg = _compute_stat_averages(l10_matches)
    l5_avg = _compute_stat_averages(l10_matches[:5])

    form_data = {
        "l10_matches": l10_matches,
        "l10_avg": l10_avg,
        "l5_avg": l5_avg,
        # Keep backward compat with the old "recent_matches" key
        "recent_matches": l10_matches,
    }

    # Build H2H data if opponent provided
    h2h_data = {}
    if opponent and h2h_matches:
        opp_slug = slugify(opponent)
        h2h_entries = []
        for match in h2h_matches:
            h2h_entry = {
                "date": getattr(match, "date", ""),
                "fixture_id": getattr(match, "fixture_id", ""),
                "stats": getattr(match, "stats", {}),
            }
            h2h_entries.append(h2h_entry)

        h2h_entries.sort(key=lambda m: m.get("date", ""), reverse=True)
        h2h_avg = _compute_combined_stat_averages(h2h_entries)

        h2h_data[opp_slug] = {
            "last_updated": now_iso(),
            "matches": h2h_entries,
            "avg": h2h_avg,
        }

    # Read existing cache to preserve H2H for other opponents
    existing = read_cache(sport, team)
    existing_sources = []
    if existing:
        existing_sources = existing.get("sources", [])
        existing_h2h = existing.get("h2h", {})
        for opp_key, opp_data in existing_h2h.items():
            if opp_key not in h2h_data:
                h2h_data[opp_key] = opp_data

    sources = list(set(existing_sources + [api_source]))

    entry = create_team_cache_entry(
        team=team,
        sport=sport,
        form_data=form_data,
        h2h_data=h2h_data,
        sources=sources,
        api_source=api_source,
    )

    return update_cache(sport, team, entry)


def _compute_stat_averages(matches: list[dict]) -> dict:
    """Compute average of each stat across matches.

    For stats with home/away sub-keys, averages the team's own side.
    """
    if not matches:
        return {}

    stat_sums = {}
    stat_counts = {}

    for match in matches:
        stats = match.get("stats", {})
        for key, value in stats.items():
            if isinstance(value, dict):
                # Use home side as default (team's own stats)
                for side in ["home", "away"]:
                    combined_key = f"{key}_{side}" if len(value) > 1 else key
                    val = value.get(side)
                    if val is not None and isinstance(val, (int, float)):
                        stat_sums[combined_key] = stat_sums.get(combined_key, 0) + val
                        stat_counts[combined_key] = stat_counts.get(combined_key, 0) + 1
            elif isinstance(value, (int, float)):
                stat_sums[key] = stat_sums.get(key, 0) + value
                stat_counts[key] = stat_counts.get(key, 0) + 1

    return {
        key: round(stat_sums[key] / stat_counts[key], 2)
        for key in stat_sums
        if stat_counts.get(key, 0) > 0
    }


def _compute_combined_stat_averages(matches: list[dict]) -> dict:
    """Compute combined (home + away) stat averages for H2H matches."""
    if not matches:
        return {}

    stat_sums = {}
    stat_counts = {}

    for match in matches:
        stats = match.get("stats", {})
        for key, value in stats.items():
            if isinstance(value, dict):
                home_val = value.get("home", 0)
                away_val = value.get("away", 0)
                if isinstance(home_val, (int, float)) and isinstance(away_val, (int, float)):
                    combined_key = f"{key}_total"
                    stat_sums[combined_key] = stat_sums.get(combined_key, 0) + home_val + away_val
                    stat_counts[combined_key] = stat_counts.get(combined_key, 0) + 1
            elif isinstance(value, (int, float)):
                stat_sums[key] = stat_sums.get(key, 0) + value
                stat_counts[key] = stat_counts.get(key, 0) + 1

    return {
        key: round(stat_sums[key] / stat_counts[key], 2)
        for key in stat_sums
        if stat_counts.get(key, 0) > 0
    }


def parse_shortlist_teams(shortlist_path: Path) -> list[tuple[str, str]]:
    """Extract (sport, team) pairs from shortlist markdown file."""
    if not shortlist_path.exists():
        print(f"Shortlist file not found: {shortlist_path}", file=sys.stderr)
        return []

    text = shortlist_path.read_text(encoding="utf-8")
    teams = []

    # Detect sport sections (### Football, ### Tennis, etc.)
    current_sport = "unknown"
    for line in text.split("\n"):
        # Sport header detection
        sport_match = re.match(r"^#{1,4}\s+(?:\d+\.\s+)?(\w+)", line, re.IGNORECASE)
        if sport_match:
            sport_name = sport_match.group(1).lower()
            # Map common names
            sport_map = {
                "soccer": "football", "futbol": "football",
                "tenis": "tennis", "koszykówka": "basketball",
                "siatkówka": "volleyball", "hokej": "hockey",
                "piłka": "football",
            }
            current_sport = sport_map.get(sport_name, sport_name)

        # Team extraction from "X vs Y" patterns
        match = re.search(
            r"([A-ZÀ-Ža-zà-ž0-9\s.'&\-]+?)\s+vs\.?\s+([A-ZÀ-Ža-zà-ž0-9\s.'&\-]+?)(?:\s*[\|(]|$)",
            line,
        )
        if match:
            team_a = match.group(1).strip()
            team_b = match.group(2).strip()
            if len(team_a) > 2 and len(team_b) > 2:
                teams.append((current_sport, team_a))
                teams.append((current_sport, team_b))

    return teams


def show_cache_status() -> dict:
    """Show cache hit/miss/expired counts per sport."""
    status = {"sports": {}, "total_files": 0, "total_valid": 0, "total_expired": 0}

    if not CACHE_DIR.exists():
        return status

    for sport_dir in sorted(CACHE_DIR.iterdir()):
        if not sport_dir.is_dir() or sport_dir.name.startswith("."):
            continue

        sport_name = sport_dir.name
        files = list(sport_dir.glob("*.json"))
        valid = sum(1 for f in files if is_cache_valid(f, FORM_TTL_HOURS))
        expired = len(files) - valid

        status["sports"][sport_name] = {
            "total": len(files),
            "valid": valid,
            "expired": expired,
        }
        status["total_files"] += len(files)
        status["total_valid"] += valid
        status["total_expired"] += expired

    return status


def expire_all():
    """Clear all cache files."""
    if not CACHE_DIR.exists():
        return 0

    count = 0
    for cache_file in CACHE_DIR.rglob("*.json"):
        cache_file.unlink()
        count += 1
    return count


def main():
    parser = argparse.ArgumentParser(
        description="Build and manage persistent stats cache for betting analysis."
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Cache single team
    cache_cmd = subparsers.add_parser("cache", help="Cache a team's data")
    cache_cmd.add_argument("--team", required=True, help="Team name")
    cache_cmd.add_argument("--sport", required=True, help="Sport name")
    cache_cmd.add_argument("--opponent", help="Opponent for H2H data")
    cache_cmd.add_argument("--data", type=Path, help="JSON file with pre-collected stats")

    # Cache from shortlist
    shortlist_cmd = subparsers.add_parser(
        "shortlist", help="Cache all teams from a shortlist file"
    )
    shortlist_cmd.add_argument("file", type=Path, help="Path to shortlist markdown file")

    # Show status
    subparsers.add_parser("status", help="Show cache status")

    # Expire all
    subparsers.add_parser("expire-all", help="Clear all cache files")

    # Read cache
    read_cmd = subparsers.add_parser("read", help="Read cached data for a team")
    read_cmd.add_argument("--team", required=True, help="Team name")
    read_cmd.add_argument("--sport", required=True, help="Sport name")

    args = parser.parse_args()

    if args.command == "status":
        status = show_cache_status()
        if not status["sports"]:
            print("Cache is empty.")
        else:
            print(f"═══ Stats Cache Status ═══")
            print(f"Total: {status['total_files']} files | "
                  f"Valid: {status['total_valid']} | "
                  f"Expired: {status['total_expired']}")
            for sport, s in status["sports"].items():
                print(f"  {sport}: {s['total']} files ({s['valid']} valid, {s['expired']} expired)")

    elif args.command == "expire-all":
        count = expire_all()
        print(f"Expired {count} cache files.")

    elif args.command == "read":
        data = read_cache(args.sport, args.team)
        if data:
            print(json.dumps(data, indent=2, ensure_ascii=False))
        else:
            print(f"No valid cache for {args.team} ({args.sport})")
            sys.exit(1)

    elif args.command == "cache":
        if args.data and args.data.exists():
            stats_data = json.loads(args.data.read_text(encoding="utf-8"))
        else:
            stats_data = {}

        entry = create_team_cache_entry(
            team=args.team,
            sport=args.sport,
            form_data=stats_data.get("form", {}),
            h2h_data=stats_data.get("h2h", {}),
            sources=stats_data.get("sources", []),
        )
        path = update_cache(args.sport, args.team, entry)
        print(f"Cached: {path}")

    elif args.command == "shortlist":
        teams = parse_shortlist_teams(args.file)
        if not teams:
            print("No teams found in shortlist.")
            sys.exit(1)

        # Create empty cache entries for discovered teams
        # (Agent fills with actual data when fetching stats)
        cached = 0
        skipped = 0
        for sport, team in teams:
            slug = slugify(team)
            cache_file = CACHE_DIR / sport / f"{slug}.json"
            if is_cache_valid(cache_file, FORM_TTL_HOURS):
                skipped += 1
                continue

            entry = create_team_cache_entry(team=team, sport=sport)
            update_cache(sport, team, entry)
            cached += 1

        print(f"Shortlist: {len(teams)} teams | Cached: {cached} | Skipped (valid): {skipped}")

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
