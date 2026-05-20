#!/usr/bin/env python3
"""Orchestrate multi-API stats fetching for discovered fixtures.

Usage:
    python3 scripts/fetch_api_stats.py --date 2026-04-28
    python3 scripts/fetch_api_stats.py --fixtures betting/data/fixtures_2026-04-28.json
    python3 scripts/fetch_api_stats.py --date 2026-04-28 --sports football,basketball
    python3 scripts/fetch_api_stats.py --usage
"""

import argparse
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

# Imports from project
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).parent))
from bet.api_clients import get_client, RateLimiter, CLIENT_REGISTRY
from bet.api_clients.base_client import APIRateLimitError, APIError
from bet.stats.fallback_chains import (
    EXPECTED_STATS_PER_SPORT,
    FALLBACK_CHAINS,
    TIER_1_SPORTS,
)
from normalize_stats import NormalizedMatchStats, build_safety_score_input
from bet.stats.market_ranking import SPORT_MARKETS
from build_stats_cache import (
    read_cache,
    update_cache,
    create_team_cache_entry,
    slugify,
)

DATA_DIR = ROOT / "betting" / "data"

# --- ESPN Stats client (player gamelogs, splits, leaders) ---
try:
    sys.path.insert(0, str(ROOT / "src"))
    from bet.api_clients.espn_stats import ESPNStatsClient
    _HAS_ESPN_STATS = True
except ImportError:
    _HAS_ESPN_STATS = False

# --- DB support (optional — falls back gracefully) ---
try:
    if "src" not in sys.path[0]:
        sys.path.insert(0, str(ROOT / "src"))
    from bet.db.connection import get_db
    from bet.db.repositories import SportRepo, TeamRepo, StatsRepo, FixtureRepo
    from bet.db.models import TeamForm
    _HAS_DB = True
except ImportError:
    _HAS_DB = False


def fetch_league_leaders_for_sport(sport: str, league: str) -> dict | None:
    """Fetch and cache league statistical leaders for context.

    Called once per league per pipeline run.
    Stores in: betting/data/stats_cache/espn/{sport}/{league}/leaders.json

    Returns dict of leader categories or None on failure.
    """
    if not _HAS_ESPN_STATS:
        return None

    cache_path = DATA_DIR / "stats_cache" / "espn" / sport / league / "leaders.json"

    # Check if already fetched today (6-hour TTL)
    if cache_path.exists():
        import time as _time
        age_hours = (_time.time() - cache_path.stat().st_mtime) / 3600
        if age_hours < 6:
            return json.loads(cache_path.read_text())

    client = ESPNStatsClient()
    try:
        leaders = client.get_league_leaders(sport, league)
        if leaders:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(leaders, ensure_ascii=False, indent=2))
            print(f"[leaders] Fetched {len(leaders)} leader entries for {sport}/{league}")
            return leaders
    except Exception as e:
        print(f"[leaders] Error fetching leaders for {sport}/{league}: {e}")

    return None


def fetch_player_gamelogs(sport: str, league: str, team_id: str, team_name: str) -> list[dict]:
    """Fetch gamelogs for top players on a team (NBA/NHL only).

    Gets team leaders first, then fetches gamelogs for top 3 scorers.
    Stores in: betting/data/stats_cache/espn/{sport}/players/{athlete_id}/gamelog.json

    Only for sports where gamelogs are available (basketball, hockey).
    """
    if not _HAS_ESPN_STATS:
        return []

    if sport not in ("basketball", "hockey"):
        return []

    client = ESPNStatsClient()

    # Get team leaders to identify top players
    try:
        team_leaders = client.get_team_leaders(sport, league, team_id)
    except Exception as e:
        print(f"[gamelogs] Error getting team leaders for {team_name}: {e}")
        return []

    if not team_leaders:
        return []

    # Extract top 3 athlete IDs from leaders
    athlete_ids = []
    for category in team_leaders:
        if isinstance(category, dict):
            leaders = category.get("leaders", [])
            for leader in leaders[:3]:
                aid = leader.get("athlete", {}).get("id", "")
                if aid and aid not in athlete_ids:
                    athlete_ids.append(aid)
        if len(athlete_ids) >= 3:
            break

    # Fetch gamelogs for each top player
    results = []
    for athlete_id in athlete_ids[:3]:
        try:
            gamelog = client.get_player_gamelog(sport, league, athlete_id)
            if gamelog:
                # Cache the gamelog
                cache_dir = DATA_DIR / "stats_cache" / "espn" / sport / "players" / str(athlete_id)
                cache_dir.mkdir(parents=True, exist_ok=True)
                (cache_dir / "gamelog.json").write_text(json.dumps(gamelog, ensure_ascii=False, indent=2))
                results.append({"athlete_id": athlete_id, "games": len(gamelog)})
                print(f"[gamelogs] Fetched {len(gamelog)} games for athlete {athlete_id}")
        except Exception as e:
            print(f"[gamelogs] Error fetching gamelog for athlete {athlete_id}: {e}")

    return results


def fetch_team_stats(
    client, team_name: str, sport: str, last_n: int = 10, competition: str = ""
) -> list[NormalizedMatchStats]:
    """Fetch last N matches with stats for a team.

    1. Resolve team ID
    2. Get last N finished fixtures
    3. For each fixture, get detailed stats (budget-aware)
    4. Return list of NormalizedMatchStats
    """
    # Resolve team ID (pass competition for ESPN league hint)
    try:
        team_id = client.resolve_team_id(team_name, competition=competition)
    except TypeError:
        # Clients that don't accept competition kwarg
        team_id = client.resolve_team_id(team_name)
    if not team_id:
        print(f"[fetch] Could not resolve team ID for '{team_name}'")
        return []

    # Get last N finished fixtures
    try:
        fixtures = client.get_team_last_fixtures(team_id, last_n=last_n)
    except (APIRateLimitError, APIError) as e:
        print(f"[fetch] Error getting fixtures for '{team_name}': {e}")
        return []

    if not fixtures:
        print(f"[fetch] No recent fixtures found for '{team_name}'")
        return []

    # Fetch detailed stats per fixture (budget-aware: stop on rate limit)
    match_stats = []
    for fixture in fixtures:
        fixture_id = _get_fixture_value(fixture, "fixture_id")
        kickoff = _get_fixture_value(fixture, "kickoff")
        if not fixture_id:
            continue
        try:
            stats = client.get_fixture_stats(fixture_id)
        except APIRateLimitError:
            print(f"[fetch] Rate limited — returning {len(match_stats)} partial stats for '{team_name}'")
            break
        except APIError as e:
            print(f"[fetch] Error fetching stats for fixture {fixture_id}: {e}")
            continue

        normalized = _normalize_match_stats_payload(stats, fixture_id, sport, kickoff)
        if normalized:
            match_stats.append(normalized)

    return match_stats


def fetch_h2h_stats(
    client, team1_name: str, team2_name: str, sport: str, last_n: int = 10, competition: str = ""
) -> list[NormalizedMatchStats]:
    """Fetch H2H meetings with stats."""
    try:
        team1_id = client.resolve_team_id(team1_name, competition=competition)
        team2_id = client.resolve_team_id(team2_name, competition=competition)
    except TypeError:
        team1_id = client.resolve_team_id(team1_name)
        team2_id = client.resolve_team_id(team2_name)

    if not team1_id or not team2_id:
        print(f"[fetch] Could not resolve team IDs for H2H: '{team1_name}' vs '{team2_name}'")
        return []

    try:
        h2h_fixtures = client.get_h2h(team1_id, team2_id, last_n=last_n)
    except (APIRateLimitError, APIError) as e:
        print(f"[fetch] Error getting H2H fixtures: {e}")
        return []

    if not h2h_fixtures:
        return []

    # Fetch stats for each H2H fixture (budget-aware)
    match_stats = []
    for fixture in h2h_fixtures:
        fixture_id = _get_fixture_value(fixture, "fixture_id")
        kickoff = _get_fixture_value(fixture, "kickoff")
        if not fixture_id:
            continue
        try:
            stats = client.get_fixture_stats(fixture_id)
        except APIRateLimitError:
            print(f"[fetch] Rate limited — returning {len(match_stats)} partial H2H stats")
            break
        except APIError:
            continue

        normalized = _normalize_match_stats_payload(stats, fixture_id, sport, kickoff)
        if normalized:
            match_stats.append(normalized)

    return match_stats


def _get_fixture_value(fixture, key: str) -> str:
    """Read fixture metadata from either a dict or dataclass-like object."""
    key_aliases = {
        "fixture_id": ("fixture_id", "external_id", "id"),
        "kickoff": ("kickoff", "date"),
    }
    candidates = key_aliases.get(key, (key,))

    if isinstance(fixture, dict):
        for candidate in candidates:
            value = fixture.get(candidate)
            if value:
                return str(value)
        return ""

    for candidate in candidates:
        value = getattr(fixture, candidate, "")
        if value:
            return str(value)
    return ""


def _normalize_match_stats_payload(stats, fixture_id: str, sport: str, kickoff: str) -> NormalizedMatchStats | None:
    """Normalize provider stats payloads to a single NormalizedMatchStats object."""
    if not stats:
        return None

    payload = stats[0] if isinstance(stats, list) else stats
    if not payload:
        return None

    if isinstance(payload, NormalizedMatchStats):
        if not payload.date and kickoff:
            payload.date = kickoff[:10]
        return payload

    if isinstance(payload, dict):
        source = payload.get("source", "")
        payload_sport = payload.get("sport", sport) or sport
        home_team = payload.get("home_team") or payload.get("home_team_name", "")
        away_team = payload.get("away_team") or payload.get("away_team_name", "")
        date = payload.get("date", "") or (kickoff[:10] if kickoff else "")
        payload_stats = payload.get("stats", {})
        payload_fixture_id = payload.get("fixture_id") or payload.get("external_id") or fixture_id
    else:
        source = getattr(payload, "source", "")
        payload_sport = getattr(payload, "sport", sport) or sport
        home_team = getattr(payload, "home_team", "") or getattr(payload, "home_team_name", "")
        away_team = getattr(payload, "away_team", "") or getattr(payload, "away_team_name", "")
        date = getattr(payload, "date", "") or (kickoff[:10] if kickoff else "")
        payload_stats = getattr(payload, "stats", {})
        payload_fixture_id = getattr(payload, "fixture_id", "") or getattr(payload, "external_id", "") or fixture_id

    return NormalizedMatchStats(
        fixture_id=str(payload_fixture_id),
        source=str(source),
        sport=str(payload_sport),
        home_team=str(home_team),
        away_team=str(away_team),
        date=str(date),
        stats=payload_stats if isinstance(payload_stats, dict) else {},
    )


def _store_in_cache(
    sport: str,
    team_name: str,
    team_matches: list[NormalizedMatchStats],
    api_source: str,
    opponent: str | None = None,
    h2h_matches: list[NormalizedMatchStats] | None = None,
) -> None:
    """Store fetched stats in the stats cache using the extended format."""
    from build_stats_cache import update_from_api

    # Debug: log match stats availability
    stat_counts = []
    for m in team_matches:
        s = getattr(m, "stats", {})
        stat_counts.append(len(s) if isinstance(s, dict) else 0)
    total_stats = sum(stat_counts)
    if not team_matches:
        print(f"[cache] SKIP {sport}/{team_name}: 0 matches from {api_source}")
        return
    if total_stats == 0:
        print(f"[cache] WARNING {sport}/{team_name}: {len(team_matches)} matches but 0 stat keys from {api_source}")

    try:
        path = update_from_api(
            sport=sport,
            team=team_name,
            normalized_matches=team_matches,
            api_source=api_source,
            opponent=opponent,
            h2h_matches=h2h_matches,
        )
        print(f"[cache] OK {sport}/{team_name}: {len(team_matches)} matches, {total_stats} total stat keys → {path}")
    except Exception as e:
        print(f"[cache] ERROR {sport}/{team_name}: {e}")

    # --- DB: persist match_stats rows for each match ---
    _persist_match_stats_to_db(sport, team_name, team_matches, api_source)

    # --- DB: persist per-match stat arrays to team_form.l10_values ---
    _save_per_match_stat_arrays(sport, team_name, team_matches, api_source)

    # --- Audit stat extraction completeness ---
    _audit_stat_extraction(sport, team_name, team_matches, api_source)


def _persist_match_stats_to_db(
    sport: str,
    team_name: str,
    matches: list[NormalizedMatchStats],
    api_source: str,
) -> None:
    """Write per-match stat rows to match_stats table in DB."""
    if not _HAS_DB or not matches:
        return

    try:
        with get_db() as conn:
            sport_repo = SportRepo(conn)
            team_repo = TeamRepo(conn)
            stats_repo = StatsRepo(conn)

            sport_obj = sport_repo.get_by_name(sport.lower())
            if not sport_obj:
                return

            team_obj = team_repo.find_or_create(team_name, sport_obj.id)

            rows: list[tuple[int, int, str, float, str]] = []
            for match in matches:
                raw_stats = getattr(match, "stats", {})
                if not raw_stats:
                    continue

                # We need a fixture_id — try to resolve from the match metadata
                home = getattr(match, "home_team", "")
                away = getattr(match, "away_team", "")
                match_date = getattr(match, "date", "")

                if not home or not away or not match_date:
                    continue

                # Resolve opponent team to find fixture
                fixture_repo = FixtureRepo(conn)

                fixture = fixture_repo.get_by_teams_and_date(
                    home, away, match_date[:10], sport_obj.id
                )
                if not fixture:
                    # Fixture not in DB yet — skip match_stats (team_form is
                    # still saved by build_stats_cache._persist_to_db)
                    continue

                # Use per-match source so mixed-source batches attribute each
                # stat row to its actual provider rather than the batch default.
                match_source = getattr(match, "source", None) or api_source

                for stat_key, value in raw_stats.items():
                    if isinstance(value, dict):
                        # home/away sub-keys
                        home_val = value.get("home")
                        away_val = value.get("away")
                        if isinstance(home_val, (int, float)):
                            home_team_obj = team_repo.find_or_create(home, sport_obj.id)
                            rows.append((fixture.id, home_team_obj.id, stat_key, float(home_val), match_source))
                        if isinstance(away_val, (int, float)):
                            away_team_obj = team_repo.find_or_create(away, sport_obj.id)
                            rows.append((fixture.id, away_team_obj.id, stat_key, float(away_val), match_source))
                    elif isinstance(value, (int, float)):
                        rows.append((fixture.id, team_obj.id, stat_key, float(value), match_source))

            if rows:
                stats_repo.bulk_save_match_stats(rows)
                print(f"[cache] DB: saved {len(rows)} match_stats rows for {sport}/{team_name}")
    except Exception as e:
        print(f"[cache] DB match_stats error (non-fatal): {e}")


def _save_per_match_stat_arrays(
    sport: str,
    team_name: str,
    matches: list[NormalizedMatchStats],
    api_source: str,
) -> None:
    """Save per-match stat VALUE ARRAYS to team_form.l10_values in DB.

    This ensures l10_values contains real per-match data (e.g. corners: [7,8,5,9,6])
    rather than just averages. Critical for three-way cross-check.
    """
    if not _HAS_DB or not matches:
        return

    try:
        with get_db() as conn:
            sport_repo = SportRepo(conn)
            team_repo = TeamRepo(conn)
            stats_repo = StatsRepo(conn)

            sport_obj = sport_repo.get_by_name(sport.lower())
            if not sport_obj:
                return

            team_obj = team_repo.find_or_create(team_name, sport_obj.id)
            team_lower = team_name.lower()
            now_ts = datetime.now(timezone.utc).isoformat()

            # Collect per-stat arrays across all matches.
            # stat_sources tracks the first match source that contributes each
            # stat_key so team_form rows carry accurate per-key provenance.
            stat_arrays: dict[str, list[float]] = {}
            stat_sources: dict[str, str] = {}
            for match in matches[:10]:
                raw_stats = getattr(match, "stats", {})
                if not raw_stats:
                    continue

                match_source = getattr(match, "source", None) or api_source
                home_team = getattr(match, "home_team", "")
                is_away = (
                    team_lower
                    and home_team
                    and team_lower != home_team.lower()
                )

                for stat_key, value in raw_stats.items():
                    if isinstance(value, dict):
                        val = value.get("away" if is_away else "home")
                    elif isinstance(value, (int, float)):
                        val = value
                    else:
                        continue

                    if val is not None:
                        try:
                            stat_arrays.setdefault(stat_key, []).append(float(val))
                            # Record first-contributing source per stat_key.
                            stat_sources.setdefault(stat_key, match_source)
                        except (ValueError, TypeError):
                            pass

            # Save each stat key as a TeamForm row with full l10_values array
            from bet.db.models import TeamForm

            for stat_key, values in stat_arrays.items():
                l10 = values[:10]
                l5 = values[:5]
                l10_avg = round(sum(l10) / len(l10), 2) if l10 else None
                l5_avg = round(sum(l5) / len(l5), 2) if l5 else None

                trend = ""
                if l10_avg and l5_avg:
                    diff = l5_avg - l10_avg
                    if abs(diff) < 0.3:
                        trend = "stable"
                    else:
                        trend = "rising" if diff > 0 else "falling"

                form = TeamForm(
                    id=None,
                    team_id=team_obj.id,
                    sport_id=sport_obj.id,
                    stat_key=stat_key,
                    l10_values=l10,
                    l5_values=l5,
                    l10_avg=l10_avg,
                    l5_avg=l5_avg,
                    h2h_values=[],
                    h2h_opponent_id=None,
                    trend=trend,
                    updated_at=now_ts,
                    source=stat_sources.get(stat_key, api_source),
                )
                stats_repo.save_team_form(form)

            conn.commit()
            if stat_arrays:
                print(f"[cache] DB team_form arrays: {len(stat_arrays)} stat keys for {sport}/{team_name}")
    except Exception as e:
        print(f"[cache] DB team_form arrays error (non-fatal): {e}")


def _audit_stat_extraction(
    sport: str,
    team_name: str,
    matches: list[NormalizedMatchStats],
    api_source: str,
) -> dict:
    """Audit what stats were actually captured vs expected for a sport.

    Returns dict with captured keys, missing keys, and coverage percentage.
    """
    expected = set(EXPECTED_STATS_PER_SPORT.get(sport, []))
    if not expected:
        return {"sport": sport, "team": team_name, "status": "no_expected_stats_defined"}

    captured: set[str] = set()
    for match in matches:
        raw_stats = getattr(match, "stats", {})
        for key, value in raw_stats.items():
            if isinstance(value, dict):
                if value.get("home") is not None or value.get("away") is not None:
                    captured.add(key)
            elif isinstance(value, (int, float)):
                captured.add(key)

    missing = expected - captured
    coverage = round(len(expected & captured) / len(expected) * 100, 1) if expected else 0

    result = {
        "sport": sport,
        "team": team_name,
        "api_source": api_source,
        "expected_keys": sorted(expected),
        "captured_keys": sorted(captured),
        "missing_keys": sorted(missing),
        "extra_keys": sorted(captured - expected),
        "coverage_pct": coverage,
    }

    if missing:
        print(f"[audit] {sport}/{team_name} via {api_source}: {coverage}% coverage, "
              f"missing: {', '.join(sorted(missing))}")

    return result


def enrich_fixture(fixture: dict, rate_limiter: RateLimiter, chain_filter: set | None = None) -> dict:
    """Enrich a single fixture with stats from the best available API.

    1. Determine sport
    2. Get fallback chain (optionally filtered by chain_filter)
    3. Try each API in chain
    4. Build safety score input
    5. Store in cache
    6. Return enriched data with status

    Args:
        chain_filter: If set, only try API names in this set. Use to restrict
                      to ESPN-only (Phase 1) or non-ESPN (Phase 2) enrichment.
    """
    sport = fixture.get("sport", "football").lower()
    home_team = fixture.get("home_team", "")
    away_team = fixture.get("away_team", "")
    competition = fixture.get("competition", "")
    fixture_id = fixture.get("fixture_id", "")

    result = {
        "fixture_id": fixture_id,
        "sport": sport,
        "home_team": home_team,
        "away_team": away_team,
        "competition": competition,
        "status": "skipped",
        "api_source": None,
        "team_a_matches": 0,
        "team_b_matches": 0,
        "h2h_matches": 0,
        "safety_input_built": False,
    }

    if not home_team or not away_team:
        result["status"] = "failed"
        result["error"] = "Missing team names"
        return result

    chain = FALLBACK_CHAINS.get(sport, [])
    if chain_filter:
        chain = [api for api in chain if api in chain_filter]
    if not chain:
        result["status"] = "skipped"
        result["error"] = f"No API coverage for sport: {sport}"
        return result

    for api_name in chain:
        if api_name not in CLIENT_REGISTRY:
            continue

        if not rate_limiter.can_request(api_name):
            continue

        try:
            client = get_client(api_name, rate_limiter)
        except (ValueError, Exception) as e:
            print(f"[enrich] Error creating client {api_name}: {e}")
            continue

        # Check if the client is available (has API key or doesn't need one)
        if not client.is_available():
            continue

        # Fetch team A stats
        team_a_stats = fetch_team_stats(client, home_team, sport, competition=competition)

        # Fetch team B stats
        team_b_stats = fetch_team_stats(client, away_team, sport, competition=competition)

        # Fetch H2H
        h2h_stats = fetch_h2h_stats(client, home_team, away_team, sport, competition=competition)

        # Check if we got anything useful
        if not team_a_stats and not team_b_stats:
            print(f"[enrich] No stats from {api_name} for {home_team} vs {away_team}")
            continue

        # Store in cache
        if team_a_stats:
            _store_in_cache(
                sport, home_team, team_a_stats, api_name,
                opponent=away_team, h2h_matches=h2h_stats,
            )
        if team_b_stats:
            _store_in_cache(
                sport, away_team, team_b_stats, api_name,
                opponent=home_team, h2h_matches=h2h_stats,
            )

        result["api_source"] = api_name
        result["team_a_matches"] = len(team_a_stats)
        result["team_b_matches"] = len(team_b_stats)
        result["h2h_matches"] = len(h2h_stats)

        # Build safety score input
        safety_input = build_safety_score_input(
            sport=sport,
            team_a=home_team,
            team_b=away_team,
            competition=competition,
            team_a_matches=team_a_stats,
            team_b_matches=team_b_stats,
            h2h_matches=h2h_stats,
            source=api_name,
        )

        if safety_input:
            result["status"] = "enriched"
            result["safety_input_built"] = True
            result["markets_built"] = len(safety_input.get("markets", []))
        elif team_a_stats or team_b_stats:
            result["status"] = "partial"
        else:
            result["status"] = "failed"

        # Success (full or partial) — don't try next API in chain
        break

    return result


def fetch_stats_for_date(
    date: str,
    sports: list[str] | None = None,
    rate_limiter: RateLimiter | None = None,
) -> dict:
    """Main entry: fetch stats for all fixtures on a date.

    1. Load fixtures from fixtures_{date}.json (or discover)
    2. Filter by sports if specified
    3. Sort by enrichment priority (Tier 1 sports first)
    4. For each fixture, enrich with stats
    5. Save summary to api_stats_summary_{date}.json
    6. Return summary dict
    """
    if rate_limiter is None:
        rate_limiter = RateLimiter()

    # DB-first: try loading fixtures from DB
    fixtures = None
    try:
        from db_data_loader import load_fixtures_from_db
        db_fixtures = load_fixtures_from_db(date)
        if db_fixtures:
            print(f"[fetch_stats] DB: loaded {len(db_fixtures)} fixtures")
            fixtures = db_fixtures
    except Exception as e:
        print(f"[fetch_stats] DB read failed, falling back to JSON: {e}")

    # JSON fallback
    if not fixtures:
        fixtures_file = DATA_DIR / f"fixtures_{date}.json"

        if fixtures_file.exists():
            try:
                fixtures_data = json.loads(fixtures_file.read_text(encoding="utf-8"))
                fixtures = fixtures_data.get("fixtures", [])
                print(f"[fetch_stats] Loaded {len(fixtures)} fixtures from {fixtures_file}")
            except (json.JSONDecodeError, OSError) as e:
                print(f"[fetch_stats] Error reading {fixtures_file}: {e}")
                fixtures = []
        else:
            # Try to discover fixtures
            print(f"[fetch_stats] No fixtures file found, running discovery for {date}")
            try:
                from discover_fixtures import discover_all_fixtures
                discovered = discover_all_fixtures(date, sports)
                fixtures = [
                    asdict(f) if hasattr(f, "__dataclass_fields__") else f
                    for f in discovered
                ]
            except Exception as e:
                print(f"[fetch_stats] Discovery failed: {e}")
                fixtures = []

    # Filter by sports
    if sports:
        sports_lower = {s.lower() for s in sports}
        fixtures = [
            f for f in fixtures
            if f.get("sport", "").lower() in sports_lower
        ]

    # Sort: Tier 1 sports first, then alphabetically
    def sort_key(f):
        sport = f.get("sport", "").lower()
        tier = 0 if sport in TIER_1_SPORTS else 1
        return (tier, sport, f.get("competition", ""), f.get("home_team", ""))

    fixtures.sort(key=sort_key)

    if not fixtures:
        print("[fetch_stats] No fixtures to enrich")
        return {
            "date": date,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_fixtures": 0,
            "counts": {"enriched": 0, "partial": 0, "failed": 0, "skipped": 0},
            "results": [],
        }

    results = []
    counts = {"enriched": 0, "partial": 0, "failed": 0, "skipped": 0}
    counts_lock = threading.Lock()

    # --- Identify ESPN APIs (free, unlimited) vs rate-limited APIs ---
    espn_apis = {api for apis in FALLBACK_CHAINS.values() for api in apis if api.startswith("espn-")}
    non_espn_apis = {api for apis in FALLBACK_CHAINS.values() for api in apis if not api.startswith("espn-")}

    # Split fixtures: those with ESPN coverage vs those without
    espn_eligible = []
    no_espn_fixtures = []
    for f in fixtures:
        sport = f.get("sport", "").lower()
        chain = FALLBACK_CHAINS.get(sport, [])
        if any(api in espn_apis for api in chain):
            espn_eligible.append(f)
        else:
            no_espn_fixtures.append(f)

    print(f"[fetch_stats] {len(fixtures)} total fixtures: {len(espn_eligible)} ESPN-eligible, {len(no_espn_fixtures)} non-ESPN")

    # --- Phase 1: ESPN enrichment (free, unlimited, 8 workers) ---
    espn_enriched_ids: set[str] = set()
    phase1_results: list[dict] = []

    def _enrich_one_espn(fixture: dict) -> dict:
        """Try ESPN-only enrichment for a single fixture."""
        try:
            return enrich_fixture(fixture, rate_limiter, chain_filter=espn_apis)
        except Exception as e:
            home = fixture.get("home_team", "?")
            away = fixture.get("away_team", "?")
            return {
                "fixture_id": fixture.get("fixture_id", ""),
                "sport": fixture.get("sport", ""),
                "home_team": home,
                "away_team": away,
                "status": "failed",
                "error": str(e),
            }

    if espn_eligible:
        print(f"[Phase 1] ESPN enrichment: {len(espn_eligible)} fixtures with 8 workers")
        with ThreadPoolExecutor(max_workers=8) as executor:
            future_to_fix = {
                executor.submit(_enrich_one_espn, f): f for f in espn_eligible
            }
            processed = 0
            for future in as_completed(future_to_fix):
                input_fixture = future_to_fix[future]
                result = future.result()
                phase1_results.append(result)
                processed += 1
                status = result.get("status", "skipped")
                if status in ("enriched", "partial"):
                    # Track by INPUT fixture_id (not output — mocks may return wrong id)
                    fid = input_fixture.get("fixture_id", "")
                    if fid:
                        espn_enriched_ids.add(fid)
                if processed % 100 == 0:
                    enriched_so_far = len(espn_enriched_ids)
                    print(f"[Phase 1] Progress: {processed}/{len(espn_eligible)} processed, {enriched_so_far} enriched")

        p1_enriched = sum(1 for r in phase1_results if r.get("status") in ("enriched", "partial"))
        print(f"[Phase 1] ESPN done: {p1_enriched}/{len(espn_eligible)} enriched")

    # --- Phase 2: Rate-limited APIs for ESPN misses + non-ESPN sports ---
    espn_missed = [
        f for f in espn_eligible
        if f.get("fixture_id", "") not in espn_enriched_ids
    ]
    phase2_fixtures = espn_missed + no_espn_fixtures

    phase2_results: list[dict] = []
    if phase2_fixtures:
        # Group by sport for rate-limited parallel enrichment
        sport_groups: dict[str, list[dict]] = {}
        for fixture in phase2_fixtures:
            sport = fixture.get("sport", "").lower()
            sport_groups.setdefault(sport, []).append(fixture)

        print(f"[Phase 2] Rate-limited APIs: {len(phase2_fixtures)} fixtures across {len(sport_groups)} sports")

        def _enrich_sport_group(sport: str, sport_fixtures: list[dict]) -> list[dict]:
            """Enrich all fixtures for a single sport using non-ESPN APIs."""
            sport_results = []
            for fixture in sport_fixtures:
                try:
                    result = enrich_fixture(fixture, rate_limiter, chain_filter=non_espn_apis)
                    sport_results.append(result)
                except Exception as e:
                    home = fixture.get("home_team", "?")
                    away = fixture.get("away_team", "?")
                    print(f"[Phase 2] Error enriching {home} vs {away}: {e}")
                    sport_results.append({
                        "fixture_id": fixture.get("fixture_id", ""),
                        "sport": sport,
                        "home_team": home,
                        "away_team": away,
                        "status": "failed",
                        "error": str(e),
                    })
            return sport_results

        max_workers = min(len(sport_groups), 4)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_sport = {
                executor.submit(_enrich_sport_group, sport, sport_fixtures): sport
                for sport, sport_fixtures in sport_groups.items()
            }
            for future in as_completed(future_to_sport):
                sport = future_to_sport[future]
                try:
                    sport_results = future.result()
                    phase2_results.extend(sport_results)
                    p2_enriched = sum(1 for r in sport_results if r.get("status") in ("enriched", "partial"))
                    print(f"[Phase 2] {sport}: {p2_enriched}/{len(sport_results)} enriched")
                except Exception as e:
                    print(f"[Phase 2] ERROR enriching {sport}: {e}")

    # --- Merge results ---
    # Phase 1 results for successfully enriched fixtures
    for r in phase1_results:
        fid = r.get("fixture_id", "")
        if fid in espn_enriched_ids:
            results.append(r)
            with counts_lock:
                counts[r.get("status", "skipped")] = counts.get(r.get("status", "skipped"), 0) + 1

    # Phase 2 results (ESPN misses now enriched by rate-limited APIs, or still failed)
    for r in phase2_results:
        results.append(r)
        with counts_lock:
            counts[r.get("status", "skipped")] = counts.get(r.get("status", "skipped"), 0) + 1

    # ESPN misses that Phase 2 didn't pick up (no rate-limited API either)
    phase2_fids = {r.get("fixture_id", "") for r in phase2_results}
    for r in phase1_results:
        fid = r.get("fixture_id", "")
        if fid not in espn_enriched_ids and fid not in phase2_fids:
            results.append(r)
            with counts_lock:
                counts[r.get("status", "skipped")] = counts.get(r.get("status", "skipped"), 0) + 1

    # --- Phase 3: Player gamelogs & league leaders (ESPN supplementary) ---
    if _HAS_ESPN_STATS:
        try:
            from bet.api_clients.espn import get_espn_league_for_competition

            # Collect unique sport/league pairs
            leagues_seen: set[tuple[str, str]] = set()
            for fixture in fixtures:
                sport = fixture.get("sport", "").lower()
                competition = fixture.get("competition", "")
                if sport and competition:
                    leagues_seen.add((sport, competition))

            # Fetch league leaders (once per league)
            for sport, comp in leagues_seen:
                espn_league = get_espn_league_for_competition(comp)
                if espn_league:
                    fetch_league_leaders_for_sport(sport, espn_league)
        except Exception as e:
            print(f"[Phase 3] League leaders/gamelogs error (non-fatal): {e}")

    # Build summary
    summary = {
        "date": date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "total_fixtures": len(fixtures),
        "counts": counts,
        "results": results,
    }

    # Save summary
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    summary_path = DATA_DIR / f"api_stats_summary_{date}.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"[fetch_stats] Summary saved to {summary_path}")
    print(f"[fetch_stats] Results: {counts}")

    return summary


def show_usage(rate_limiter: RateLimiter):
    """Print API usage summary."""
    summary = rate_limiter.get_usage_summary()
    print("\n=== API Usage Summary ===")
    for api, info in summary.items():
        print(f"  {api}: {info['used']}/{info['limit']} (remaining: {info['remaining']})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch stats from APIs")
    parser.add_argument("--date", help="Date YYYY-MM-DD")
    parser.add_argument("--fixtures", help="Path to fixtures JSON file")
    parser.add_argument("--sports", help="Comma-separated sports filter")
    parser.add_argument("--usage", action="store_true", help="Show API usage summary")
    args = parser.parse_args()

    rate_limiter = RateLimiter()

    if args.usage:
        show_usage(rate_limiter)
        sys.exit(0)

    if not args.date and not args.fixtures:
        # Default to today
        args.date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    sports = args.sports.split(",") if args.sports else None

    if args.fixtures:
        fixtures_path = Path(args.fixtures)
        if not fixtures_path.exists():
            print(f"Error: fixtures file not found: {fixtures_path}")
            sys.exit(1)
        fixtures_data = json.loads(fixtures_path.read_text(encoding="utf-8"))
        fixtures = fixtures_data.get("fixtures", fixtures_data if isinstance(fixtures_data, list) else [])
        if sports:
            sports_lower = {s.lower() for s in sports}
            fixtures = [f for f in fixtures if f.get("sport", "").lower() in sports_lower]

        # Enrich from fixture list
        results = []
        for fixture in fixtures:
            result = enrich_fixture(fixture, rate_limiter)
            results.append(result)
            print(f"  {result['home_team']} vs {result['away_team']}: {result['status']}")

        # Determine date for summary filename
        date = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
        summary = {
            "date": date,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "total_fixtures": len(fixtures),
            "results": results,
        }
        summary_path = DATA_DIR / f"api_stats_summary_{date}.json"
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(
            json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"\nSummary saved to {summary_path}")
    else:
        result = fetch_stats_for_date(args.date, sports, rate_limiter)

    show_usage(rate_limiter)
