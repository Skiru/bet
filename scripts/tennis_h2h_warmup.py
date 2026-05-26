"""Tennis H2H Warmup — Pre-caches head-to-head data for tennis shortlist candidates.

Run AFTER S1 discovery and S2 shortlist, BEFORE S3 deep stats.
Proactively fetches H2H data for all tennis matchups so deep_stats_report
doesn't hit H2H-BLIND, and gate_checker doesn't trigger ZT#3-EXT rejections.

Fallback chain (tennis-specific):
  L1: DB cache (already have H2H in team_form?)
  L2: tennis-abstract get_h2h() (primary — per-match H2H with serve stats)
  L3: SofaScore event H2H API (uses event_id from fixtures table)
  L4: DuckDuckGo web search (free, no API key, parses snippets)

Usage:
  PYTHONPATH=src .venv/bin/python scripts/tennis_h2h_warmup.py --date 2026-05-21 --verbose
  PYTHONPATH=src .venv/bin/python scripts/tennis_h2h_warmup.py --date 2026-05-21 --dry-run

Output: AGENT_SUMMARY JSON with enrichment stats.
"""

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Ensure project paths
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bet.db.connection import get_db
from bet.db.repositories import SportRepo, TeamRepo, StatsRepo, FixtureRepo
from bet.db.models import TeamForm
from bet.api_clients import get_client, RateLimiter
from bet.api_clients.base_client import APIRateLimitError, APIError
from bet.stats.ddg_h2h_search import search_tennis_h2h, convert_h2h_to_stat_values

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
MAX_DDG_SEARCHES = 50  # Increased for tennis (many events per day)
SOFASCORE_DELAY = 1.5
TENNIS_ABSTRACT_DELAY = 0.8


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_tennis_name(name: str) -> str:
    """Normalize tennis player name from DB format to search format.

    DB may store as "Surname, Firstname" → convert to "Firstname Surname".
    Also handles "Surname, F." abbreviations.
    """
    name = name.strip()
    if ", " in name:
        parts = name.split(", ", 1)
        if len(parts) == 2:
            surname, firstname = parts
            # Skip if firstname is very short (abbreviation like "A.")
            if len(firstname) > 2:
                return f"{firstname} {surname}"
    return name


def get_tennis_shortlist_pairs(date: str) -> list[dict]:
    """Get tennis matchups from today's shortlist that need H2H data.

    Returns list of dicts: [{
        "player_a": str, "player_b": str,
        "team_a_id": int, "team_b_id": int,
        "event_id": str | None (SofaScore),
        "has_h2h": bool
    }]
    """
    pairs = []

    with get_db() as db:
        sport_repo = SportRepo(db)
        tennis = sport_repo.get_by_name("tennis")
        if not tennis:
            return []

        # Get today's tennis fixtures with team info
        rows = db.execute(
            """
            SELECT f.external_id, t1.id, t1.name, t2.id, t2.name
            FROM fixtures f
            JOIN teams t1 ON f.home_team_id = t1.id
            JOIN teams t2 ON f.away_team_id = t2.id
            WHERE f.sport_id = ? AND date(f.kickoff) = ?
            """,
            (tennis.id, date),
        ).fetchall()

        for event_id, t1_id, t1_name, t2_id, t2_name in rows:
            # Skip doubles (contain " / " or " & ")
            if " / " in t1_name or " & " in t1_name:
                continue
            if " / " in t2_name or " & " in t2_name:
                continue

            # Check if we already have H2H in team_form
            existing = db.execute(
                """
                SELECT COUNT(*) FROM team_form
                WHERE team_id = ? AND h2h_opponent_id = ? AND sport_id = ?
                AND h2h_values IS NOT NULL AND h2h_values != '[]'
                """,
                (t1_id, t2_id, tennis.id),
            ).fetchone()[0]

            pairs.append({
                "player_a": t1_name,
                "player_b": t2_name,
                "team_a_id": t1_id,
                "team_b_id": t2_id,
                "event_id": event_id,
                "has_h2h": existing > 0,
            })

    return pairs


def try_tennis_abstract_h2h(
    player_a: str,
    player_b: str,
    rate_limiter: RateLimiter,
) -> list | None:
    """L2: Try tennis-abstract for H2H matches."""
    try:
        client = get_client("tennis-abstract", rate_limiter=rate_limiter)
        if not client.is_available():
            return None

        time.sleep(TENNIS_ABSTRACT_DELAY)
        h2h_matches = client.get_h2h(player_a, player_b, last_n=10)
        if h2h_matches:
            return h2h_matches
    except APIRateLimitError:
        logger.warning("tennis-abstract rate-limited (429)")
        return None
    except Exception as e:
        logger.debug(f"tennis-abstract H2H failed: {e}")
    return None


def try_sofascore_event_h2h(
    event_id: str | None,
    player_a: str,
    player_b: str,
    rate_limiter: RateLimiter,
) -> list[dict] | None:
    """L3: Try SofaScore event H2H API.

    Returns list of meeting dicts with sets/games data.
    """
    if not event_id:
        return None

    try:
        client = get_client("sofascore", rate_limiter=rate_limiter)
        time.sleep(SOFASCORE_DELAY)
        data = client.get_event_h2h(event_id)

        if not data:
            return None

        # Parse SofaScore H2H response
        meetings = []
        # SofaScore returns {"teamDuel": {...}, "managerDuel": {...}}
        # or list of past events between these teams
        events = data.get("events", [])
        if not events:
            # Try alternative structure
            team_duel = data.get("teamDuel", {})
            if team_duel:
                # Has wins/draws/losses summary
                meetings_info = {
                    "total_meetings": (
                        team_duel.get("homeWins", 0)
                        + team_duel.get("awayWins", 0)
                        + team_duel.get("draws", 0)
                    ),
                    "player_a_wins": team_duel.get("homeWins", 0),
                    "player_b_wins": team_duel.get("awayWins", 0),
                }
                if meetings_info["total_meetings"] > 0:
                    return [meetings_info]
                return None

        for event in events[:10]:
            home_score = event.get("homeScore", {})
            away_score = event.get("awayScore", {})

            # Tennis: periods are sets
            periods = home_score.get("period1", 0) is not None
            total_sets = 0
            total_games = 0

            for i in range(1, 6):
                h_set = home_score.get(f"period{i}")
                a_set = away_score.get(f"period{i}")
                if h_set is not None and a_set is not None:
                    total_sets += 1
                    total_games += h_set + a_set

            winner = None
            h_total = home_score.get("current", 0)
            a_total = away_score.get("current", 0)
            if h_total > a_total:
                winner = "home"
            elif a_total > h_total:
                winner = "away"

            meetings.append({
                "total_sets": total_sets if total_sets > 0 else None,
                "total_games": total_games if total_games > 0 else None,
                "winner": winner,
                "date": event.get("startTimestamp", ""),
            })

        return meetings if meetings else None

    except Exception as e:
        logger.debug(f"SofaScore event H2H failed for {event_id}: {e}")
        return None


def try_ddg_h2h(
    player_a: str,
    player_b: str,
    ddg_budget: dict,
) -> dict | None:
    """L4: DuckDuckGo web search for H2H data."""
    if ddg_budget["used"] >= ddg_budget["max"]:
        logger.debug(f"DDG budget exhausted ({ddg_budget['used']}/{ddg_budget['max']})")
        return None

    ddg_budget["used"] += 1
    result = search_tennis_h2h(player_a, player_b)
    return result


def save_h2h_to_db(
    player_a: str,
    player_b: str,
    team_a_id: int,
    team_b_id: int,
    sport_id: int,
    meetings: list[dict],
    source: str,
) -> bool:
    """Save H2H data to team_form table.

    Stores total_games and total_sets as separate stat_key entries.
    """
    try:
        with get_db() as conn:
            stats_repo = StatsRepo(conn)

            stat_entries = {"total_games": [], "total_sets": []}

            # Extended H2H stats from tennis-abstract (serve-specific)
            extended_stat_entries = {
                "h2h_aces": [],
                "h2h_double_faults": [],
                "h2h_first_serve_pct": [],
            }

            for meeting in meetings:
                if isinstance(meeting, dict):
                    tg = meeting.get("total_games")
                    ts = meeting.get("total_sets")
                    if tg is not None:
                        stat_entries["total_games"].append(float(tg))
                    if ts is not None:
                        stat_entries["total_sets"].append(float(ts))
                        
                    # Extended serve stats (from tennis-abstract H2H)
                    if meeting.get("aces") is not None:
                        extended_stat_entries["h2h_aces"].append(float(meeting["aces"]))
                    if meeting.get("double_faults") is not None or meeting.get("df") is not None:
                        val = meeting.get("double_faults") or meeting.get("df")
                        extended_stat_entries["h2h_double_faults"].append(float(val))
                    if meeting.get("first_serve_pct") is not None:
                        extended_stat_entries["h2h_first_serve_pct"].append(float(meeting["first_serve_pct"]))

            # Merge for processing
            for k, v in extended_stat_entries.items():
                if v:
                    stat_entries[k] = v

            saved_any = False
            for stat_key, values in stat_entries.items():
                if not values:
                    continue

                form = TeamForm(
                    id=None,
                    team_id=team_a_id,
                    sport_id=sport_id,
                    stat_key=stat_key,
                    l10_values=[],
                    l5_values=[],
                    l10_avg=None,
                    l5_avg=None,
                    h2h_values=values[:10],
                    h2h_opponent_id=team_b_id,
                    trend="stable",
                    updated_at=_now_iso(),
                    source=f"h2h-warmup-{source}",
                )
                stats_repo.save_team_form(form)
                saved_any = True

                # Also save reverse direction
                form_reverse = TeamForm(
                    id=None,
                    team_id=team_b_id,
                    sport_id=sport_id,
                    stat_key=stat_key,
                    l10_values=[],
                    l5_values=[],
                    l10_avg=None,
                    l5_avg=None,
                    h2h_values=values[:10],
                    h2h_opponent_id=team_a_id,
                    trend="stable",
                    updated_at=_now_iso(),
                    source=f"h2h-warmup-{source}",
                )
                stats_repo.save_team_form(form_reverse)

            conn.commit()
            return saved_any

    except Exception as e:
        logger.error(f"Failed to save H2H for {player_a} vs {player_b}: {e}")
        return False


def save_normalized_h2h_to_db(
    player_a: str,
    player_b: str,
    team_a_id: int,
    team_b_id: int,
    sport_id: int,
    h2h_matches: list,
    source: str,
) -> bool:
    """Save NormalizedMatchStats H2H to team_form (for tennis-abstract results)."""
    try:
        from build_stats_cache import update_from_api

        update_from_api(
            sport="tennis",
            team=player_a,
            normalized_matches=[],
            api_source=source,
            opponent=player_b,
            h2h_matches=h2h_matches,
        )
        return True
    except Exception as e:
        logger.error(f"Failed to save normalized H2H: {e}")
        return False


def run_warmup(date: str, verbose: bool = False, dry_run: bool = False,
               skip_sofascore: bool = False, only_players: list[str] | None = None) -> dict:
    """Main warmup function — enriches H2H for all tennis shortlist pairs.

    Returns summary dict for AGENT_SUMMARY.
    """
    if verbose:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    else:
        logging.basicConfig(level=logging.WARNING)

    print(f"\n{'='*60}")
    print(f"  TENNIS H2H WARMUP — {date}")
    print(f"{'='*60}\n")

    # Get pairs needing H2H
    pairs = get_tennis_shortlist_pairs(date)
    total_pairs = len(pairs)
    already_cached = sum(1 for p in pairs if p["has_h2h"])
    needs_h2h = [p for p in pairs if not p["has_h2h"]]

    print(f"Total tennis singles fixtures: {total_pairs}")
    print(f"Already have H2H: {already_cached}")
    print(f"Need H2H enrichment: {len(needs_h2h)}")

    if dry_run:
        print(f"\n[DRY RUN] Would attempt H2H for {len(needs_h2h)} pairs")
        for p in needs_h2h[:20]:
            print(f"  - {p['player_a']} vs {p['player_b']} (event_id={p['event_id']})")
        return {
            "total_pairs": total_pairs,
            "already_cached": already_cached,
            "needs_h2h": len(needs_h2h),
            "dry_run": True,
        }

    # Filter to specific players if requested
    if only_players:
        only_lower = [p.lower() for p in only_players]
        needs_h2h = [
            p for p in needs_h2h
            if any(
                name in p["player_a"].lower() or name in p["player_b"].lower()
                for name in only_lower
            )
        ]
        print(f"Filtered to {len(needs_h2h)} pairs matching player filter")

    # Deduplicate: same normalized pair should only be processed once
    seen_pairs = set()
    deduped = []
    for p in needs_h2h:
        key = tuple(sorted([
            _normalize_tennis_name(p["player_a"]).lower(),
            _normalize_tennis_name(p["player_b"]).lower(),
        ]))
        if key not in seen_pairs:
            seen_pairs.add(key)
            deduped.append(p)
    if len(deduped) < len(needs_h2h):
        print(f"Deduplicated: {len(needs_h2h)} → {len(deduped)} unique pairs")
    needs_h2h = deduped

    # Get tennis sport_id
    with get_db() as db:
        sport_repo = SportRepo(db)
        tennis = sport_repo.get_by_name("tennis")
        sport_id = tennis.id if tennis else None

    if not sport_id:
        print("ERROR: Tennis sport not found in DB")
        return {"error": "tennis sport not found"}

    # Initialize fallback resources
    rate_limiter = RateLimiter()
    ddg_budget = {"max": MAX_DDG_SEARCHES, "used": 0}

    # Track results per source
    results = {
        "tennis-abstract": {"attempted": 0, "success": 0},
        "sofascore": {"attempted": 0, "success": 0},
        "ddg": {"attempted": 0, "success": 0},
        "total_enriched": 0,
        "total_failed": 0,
    }

    # Track if tennis-abstract is rate-limited
    ta_blocked = False

    print(f"\nStarting H2H enrichment for {len(needs_h2h)} pairs...\n")

    for i, pair in enumerate(needs_h2h):
        player_a = _normalize_tennis_name(pair["player_a"])
        player_b = _normalize_tennis_name(pair["player_b"])
        team_a_id = pair["team_a_id"]
        team_b_id = pair["team_b_id"]
        event_id = pair["event_id"]

        if verbose:
            print(f"[{i+1}/{len(needs_h2h)}] {player_a} vs {player_b}", end=" → ")

        enriched = False

        # L2: tennis-abstract
        if not ta_blocked:
            results["tennis-abstract"]["attempted"] += 1
            h2h_matches = try_tennis_abstract_h2h(player_a, player_b, rate_limiter)
            if h2h_matches is None and not ta_blocked:
                # Check if it was a rate limit (the function logs it)
                # After first 429, mark as blocked
                pass
            elif h2h_matches == []:
                # No H2H found (players never met) — still not blocked
                pass
            elif h2h_matches:
                results["tennis-abstract"]["success"] += 1
                saved = save_normalized_h2h_to_db(
                    player_a, player_b, team_a_id, team_b_id,
                    sport_id, h2h_matches, "tennis-abstract",
                )
                if saved:
                    enriched = True
                    results["total_enriched"] += 1
                    if verbose:
                        print(f"✓ tennis-abstract ({len(h2h_matches)} meetings)")
                    continue

        # L3: SofaScore event H2H
        if not skip_sofascore:
            results["sofascore"]["attempted"] += 1
            ss_meetings = try_sofascore_event_h2h(event_id, player_a, player_b, rate_limiter)
            if ss_meetings:
                results["sofascore"]["success"] += 1
                saved = save_h2h_to_db(
                    player_a, player_b, team_a_id, team_b_id,
                    sport_id, ss_meetings, "sofascore",
                )
                if saved:
                    enriched = True
                    results["total_enriched"] += 1
                    if verbose:
                        print(f"✓ sofascore ({len(ss_meetings)} meetings)")
                    continue

        # L4: DuckDuckGo search
        results["ddg"]["attempted"] += 1
        ddg_data = try_ddg_h2h(player_a, player_b, ddg_budget)
        if ddg_data and ddg_data.get("total_meetings", 0) > 0:
            results["ddg"]["success"] += 1
            # Convert DDG meetings to format for DB
            meetings_for_db = ddg_data.get("meetings", [])
            if not meetings_for_db and ddg_data.get("total_meetings", 0) > 0:
                # Only have win/loss summary, no per-match data
                # Store as a summary entry
                meetings_for_db = [{
                    "total_sets": None,
                    "total_games": None,
                    "player_a_wins": ddg_data["player_a_wins"],
                    "player_b_wins": ddg_data["player_b_wins"],
                }]

            if meetings_for_db:
                saved = save_h2h_to_db(
                    player_a, player_b, team_a_id, team_b_id,
                    sport_id, meetings_for_db, "ddg-search",
                )
                if saved:
                    enriched = True
                    results["total_enriched"] += 1
                    if verbose:
                        total = ddg_data.get("total_meetings", 0)
                        print(f"✓ DDG ({total} meetings, src={ddg_data.get('source', '?')})")
                    continue

        if not enriched:
            results["total_failed"] += 1
            if verbose:
                print("✗ no H2H found (all sources exhausted)")

    # Summary
    print(f"\n{'='*60}")
    print(f"  H2H WARMUP COMPLETE")
    print(f"{'='*60}")
    print(f"  Total pairs needing H2H: {len(needs_h2h)}")
    print(f"  Successfully enriched:   {results['total_enriched']}")
    print(f"  Failed (no data):        {results['total_failed']}")
    print(f"\n  Source breakdown:")
    print(f"    tennis-abstract: {results['tennis-abstract']['success']}/{results['tennis-abstract']['attempted']}")
    print(f"    sofascore:       {results['sofascore']['success']}/{results['sofascore']['attempted']}")
    print(f"    DDG search:      {results['ddg']['success']}/{results['ddg']['attempted']}")
    print(f"    DDG budget:      {ddg_budget['used']}/{ddg_budget['max']}")
    print()

    summary = {
        "date": date,
        "total_tennis_pairs": total_pairs,
        "already_cached": already_cached,
        "attempted": len(needs_h2h),
        "enriched": results["total_enriched"],
        "failed": results["total_failed"],
        "sources": {
            "tennis_abstract": results["tennis-abstract"],
            "sofascore": results["sofascore"],
            "ddg": results["ddg"],
        },
        "ddg_budget_used": ddg_budget["used"],
    }

    print(f"AGENT_SUMMARY:{json.dumps(summary)}")
    return summary


def main():
    parser = argparse.ArgumentParser(description="Tennis H2H Warmup")
    parser.add_argument("--date", required=True, help="Betting date (YYYY-MM-DD)")
    parser.add_argument("--verbose", action="store_true", help="Verbose output")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without doing it")
    parser.add_argument("--max-ddg", type=int, default=MAX_DDG_SEARCHES, help="Max DDG searches")
    parser.add_argument("--skip-sofascore", action="store_true", help="Skip SofaScore (often 403)")
    parser.add_argument("--players", nargs="*", help="Only enrich these player surnames")
    args = parser.parse_args()

    run_warmup(
        args.date,
        verbose=args.verbose,
        dry_run=args.dry_run,
        skip_sofascore=args.skip_sofascore,
        only_players=args.players,
    )


if __name__ == "__main__":
    main()
