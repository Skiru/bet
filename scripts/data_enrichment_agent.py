#!/usr/bin/env python3
"""Self-healing data enrichment agent — fetches missing team stats via Playwright.

When the deep analysis pipeline encounters teams/events with missing statistics,
this agent fetches data from internet sources (Flashscore first, Sofascore fallback),
parses sport-specific stats, and saves results to both DB and JSON stats cache.

Usage:
    python3 scripts/data_enrichment_agent.py --team "FC Barcelona" --sport football
    python3 scripts/data_enrichment_agent.py --batch betting/data/missing_teams.json
    python3 scripts/data_enrichment_agent.py --date 2026-05-08
"""

import argparse
import concurrent.futures
import json
import logging
import re
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))
sys.path.insert(0, str(ROOT_DIR / "scripts"))

from fetch_with_playwright import fetch  # noqa: E402

from bet.db.connection import get_db  # noqa: E402
from bet.db.models import TeamForm  # noqa: E402
from bet.db.repositories import SportRepo, StatsRepo, TeamRepo  # noqa: E402
from bet.stats.market_ranking import SPORT_STAT_KEYS  # noqa: E402

logger = logging.getLogger(__name__)

DATA_DIR = ROOT_DIR / "betting" / "data"
CACHE_DIR = DATA_DIR / "stats_cache"

# Rate-limit tracking per domain (thread-safe)
_last_request_time: dict[str, float] = {}
_rate_lock = threading.Lock()
_RATE_LIMIT_SECONDS = 1.5


# ---------------------------------------------------------------------------
# Slugify
# ---------------------------------------------------------------------------

def _slugify(name: str) -> str:
    """Convert team/player name to URL slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    return slug.strip("-")


# ---------------------------------------------------------------------------
# URL builders
# ---------------------------------------------------------------------------

def _build_flashscore_url(team_name: str, sport: str) -> str:
    """Build Flashscore URL from team name."""
    slug = _slugify(team_name)
    if sport == "tennis":
        return f"https://www.flashscore.com/player/{slug}/"
    return f"https://www.flashscore.com/team/{slug}/"


def _build_sofascore_url(team_name: str, sport: str) -> str:
    """Build Sofascore URL from team name (best-effort — ID unknown)."""
    slug = _slugify(team_name)
    return f"https://www.sofascore.com/team/{sport}/{slug}/0"


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

def _rate_limit(domain: str) -> None:
    """Enforce per-domain rate limit (thread-safe)."""
    with _rate_lock:
        now = time.time()
        last = _last_request_time.get(domain, 0.0)
        wait = _RATE_LIMIT_SECONDS - (now - last)
        if wait > 0:
            time.sleep(wait)
        _last_request_time[domain] = time.time()


# ---------------------------------------------------------------------------
# HTML parsers
# ---------------------------------------------------------------------------

def _parse_flashscore_stats(html: str, sport: str) -> dict:
    """Extract L10 stats from Flashscore team page HTML.

    Uses regex patterns to extract statistical data from Flashscore's
    rendered HTML. Returns dict of stat_key -> list of match values.
    """
    stats: dict[str, list[float]] = {}
    stat_keys = SPORT_STAT_KEYS.get(sport, [])

    if not html or len(html) < 500:
        return stats

    # Flashscore renders stats in structured divs/tables.
    # Look for patterns like "Corners: 7" or stat values in table cells.
    for key in stat_keys:
        values = _extract_stat_values(html, key, sport)
        if values:
            stats[key] = values

    return stats


def _extract_stat_values(html: str, stat_key: str, sport: str) -> list[float]:
    """Extract numeric values for a stat key from HTML."""
    values: list[float] = []

    # Map stat keys to common labels in HTML
    label_map = {
        "corners": r"(?:corners?|corner\s*kicks?)",
        "fouls": r"(?:fouls?|foul\s*committed)",
        "yellow_cards": r"(?:yellow\s*cards?|bookings?)",
        "red_cards": r"(?:red\s*cards?|sending\s*off)",
        "shots": r"(?:shots?|total\s*shots?)",
        "shots_on_target": r"(?:shots?\s*on\s*target|on\s*target)",
        "possession": r"(?:possession|ball\s*possession)",
        "goals": r"(?:goals?|score)",
        "offsides": r"(?:offsides?)",
        "saves": r"(?:saves?|goalkeeper\s*saves?)",
        "points": r"(?:points?|total\s*points?|pts)",
        "rebounds": r"(?:rebounds?|reb)",
        "assists": r"(?:assists?|ast)",
        "steals": r"(?:steals?|stl)",
        "blocks": r"(?:blocks?|blk)",
        "turnovers": r"(?:turnovers?|tov)",
        "aces": r"(?:aces?)",
        "double_faults": r"(?:double\s*faults?|df)",
        "games_won": r"(?:games?\s*won)",
        "sets_won": r"(?:sets?\s*won)",
        "total_games": r"(?:total\s*games?)",
        "hits": r"(?:hits?)",
        "pim": r"(?:pim|penalty\s*minutes?|penalties\s*in\s*minutes?)",
        "runs": r"(?:runs?)",
        "strikeouts": r"(?:strikeouts?|k|so)",
        "walks": r"(?:walks?|bb)",
        "total_runs": r"(?:total\s*runs?)",
        "home_runs": r"(?:home\s*runs?|hr)",
        "penalties": r"(?:penalties?|penalty)",
        "suspensions": r"(?:suspensions?|2min)",
        "total_goals": r"(?:total\s*goals?)",
        "attack_pct": r"(?:attack\s*%|attack\s*pct|attack\s*efficiency)",
        "total_points": r"(?:total\s*points?)",
        "errors": r"(?:errors?)",
        "frames_won": r"(?:frames?\s*won)",
        "centuries": r"(?:centuries?|century\s*breaks?)",
        "highest_break": r"(?:highest?\s*break)",
        "total_frames": r"(?:total\s*frames?)",
        "fifty_plus_breaks": r"(?:50\+?\s*breaks?|fifty\s*plus)",
        "legs_won": r"(?:legs?\s*won)",
        "checkout_pct": r"(?:checkout\s*%|checkout\s*pct)",
        "one_eighties": r"(?:180s?|one\s*eight(?:y|ies))",
        "avg_score": r"(?:avg\s*score|average\s*score|average)",
        "total_legs": r"(?:total\s*legs?)",
        "maps_won": r"(?:maps?\s*won)",
        "rounds_won": r"(?:rounds?\s*won)",
        "kills": r"(?:kills?)",
        "total_maps": r"(?:total\s*maps?)",
        "total_rounds": r"(?:total\s*rounds?)",
        "break_points_won": r"(?:break\s*points?\s*won|bp\s*won)",
        "first_serve_pct": r"(?:1st\s*serve\s*%|first\s*serve\s*%)",
        "fg_pct": r"(?:fg\s*%|field\s*goal\s*%)",
        "three_pct": r"(?:3pt\s*%|three\s*point\s*%|3p%)",
        "ft_pct": r"(?:ft\s*%|free\s*throw\s*%)",
        "faceoff_pct": r"(?:faceoff\s*%|fo%|face\s*off)",
        "powerplay_goals": r"(?:powerplay\s*goals?|pp\s*goals?|ppg)",
        "points_per_set": r"(?:points?\s*per\s*set)",
        "total_sets": r"(?:total\s*sets?)",
        "takedowns": r"(?:takedowns?|td)",
        "sig_strikes": r"(?:sig\.?\s*strikes?|significant\s*strikes?)",
        "submission_attempts": r"(?:submission\s*attempts?|sub\s*att)",
        "rounds": r"(?:rounds?)",
        "control_time": r"(?:control\s*time|ctrl\s*time)",
        "break_points": r"(?:break\s*points?|bp)",
        "heat_points": r"(?:heat\s*points?)",
        "heat_wins": r"(?:heat\s*wins?)",
    }

    pattern = label_map.get(stat_key, re.escape(stat_key.replace("_", " ")))

    # Pattern 1: "Label: value" or "Label value" in text
    matches = re.findall(
        pattern + r"[:\s]*(\d+(?:\.\d+)?)",
        html,
        re.IGNORECASE,
    )
    for m in matches:
        try:
            values.append(float(m))
        except ValueError:
            continue

    # Pattern 2: Table cells with stat name and values in adjacent cells
    cell_pattern = (
        r"(?:<td[^>]*>.*?" + pattern + r".*?</td>\s*<td[^>]*>\s*(\d+(?:\.\d+)?)\s*</td>)"
    )
    cell_matches = re.findall(cell_pattern, html, re.IGNORECASE | re.DOTALL)
    for m in cell_matches:
        try:
            v = float(m)
            if v not in values:
                values.append(v)
        except ValueError:
            continue

    # Deduplicate and keep last 10
    return values[:10]


def _parse_sofascore_stats(html: str, sport: str) -> dict:
    """Extract stats from Sofascore HTML (fallback parser)."""
    # Sofascore uses similar patterns — reuse core extraction logic
    return _parse_flashscore_stats(html, sport)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_avg(values: list) -> float | None:
    nums = [v for v in values if isinstance(v, (int, float))]
    if not nums:
        return None
    return round(sum(nums) / len(nums), 2)


def _compute_trend(l10_values: list[float], l5_values: list[float]) -> str:
    """Determine trend: rising, falling, or stable."""
    l10_avg = _safe_avg(l10_values)
    l5_avg = _safe_avg(l5_values)
    if l10_avg is None or l5_avg is None:
        return "stable"
    diff = l5_avg - l10_avg
    if abs(diff) < 0.3:
        return "stable"
    return "rising" if diff > 0 else "falling"


# ---------------------------------------------------------------------------
# Save functions
# ---------------------------------------------------------------------------

def _save_to_cache(team_name: str, sport: str, stats: dict, source: str) -> None:
    """Save stats to JSON cache file for backward compatibility."""
    slug = _slugify(team_name)
    sport_dir = CACHE_DIR / sport
    sport_dir.mkdir(parents=True, exist_ok=True)
    cache_path = sport_dir / f"{slug}.json"

    # Load existing cache if present
    existing = {}
    if cache_path.exists():
        try:
            existing = json.loads(cache_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            existing = {}

    # Build form data
    form_data = {}
    for stat_key, values in stats.items():
        l10 = values[:10]
        l5 = values[:5] if len(values) >= 5 else values
        form_data[stat_key] = {
            "l10_avg": _safe_avg(l10),
            "l5_avg": _safe_avg(l5),
        }

    l10_matches = []
    if stats:
        # Build per-match dicts from parallel value lists
        max_matches = max(len(v) for v in stats.values())
        for i in range(min(max_matches, 10)):
            match_stats = {}
            for key, vals in stats.items():
                if i < len(vals):
                    match_stats[key] = vals[i]
            if match_stats:
                l10_matches.append(match_stats)

    # Merge sources
    sources = existing.get("sources", [])
    if source not in sources:
        sources.append(source)
    if "enrichment-agent" not in sources:
        sources.append("enrichment-agent")

    cache_data = {
        "team": team_name,
        "sport": sport,
        "sources": sources,
        "form": {
            "l10_avg": {k: v["l10_avg"] for k, v in form_data.items()},
            "l5_avg": {k: v["l5_avg"] for k, v in form_data.items()},
            "l10_matches": l10_matches,
        },
        "enriched_at": _now_iso(),
    }

    cache_path.write_text(
        json.dumps(cache_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("Saved cache: %s", cache_path)


def _save_to_db(team_name: str, sport: str, stats: dict, source: str) -> None:
    """Save stats to SQLite DB via StatsRepo.save_team_form()."""
    try:
        with get_db() as conn:
            sport_repo = SportRepo(conn)
            team_repo = TeamRepo(conn)
            stats_repo = StatsRepo(conn)

            sport_obj = sport_repo.get_by_name(sport)
            if not sport_obj:
                logger.warning("Sport '%s' not found in DB", sport)
                return

            team = team_repo.find_or_create(team_name, sport_obj.id)

            for stat_key, values in stats.items():
                l10 = values[:10]
                l5 = values[:5] if len(values) >= 5 else values
                trend = _compute_trend(l10, l5)

                form = TeamForm(
                    id=None,
                    team_id=team.id,
                    sport_id=sport_obj.id,
                    stat_key=stat_key,
                    l10_values=l10,
                    l5_values=l5,
                    l10_avg=_safe_avg(l10),
                    l5_avg=_safe_avg(l5),
                    h2h_values=[],
                    h2h_opponent_id=None,
                    trend=trend,
                    updated_at=_now_iso(),
                    source=source,
                )
                stats_repo.save_team_form(form)

            logger.info("Saved to DB: %s (%s) — %d stat keys", team_name, sport, len(stats))
    except Exception as exc:
        logger.error("DB save failed for %s: %s", team_name, exc)


# ---------------------------------------------------------------------------
# Fetch helpers
# ---------------------------------------------------------------------------

def _try_flashscore(team_name: str, sport: str) -> tuple[dict, str | None]:
    """Fetch stats from Flashscore. Returns (stats_dict, error_or_None)."""
    url = _build_flashscore_url(team_name, sport)
    _rate_limit("flashscore.com")
    try:
        html = fetch(url, save_snapshot=False)
        if html is None:
            return {}, "CAPTCHA or empty response from Flashscore"
        stats = _parse_flashscore_stats(html, sport)
        return stats, None
    except Exception as exc:
        return {}, f"Flashscore fetch error: {exc}"


def _try_sofascore(team_name: str, sport: str) -> tuple[dict, str | None]:
    """Fetch stats from Sofascore (fallback). Returns (stats_dict, error_or_None)."""
    url = _build_sofascore_url(team_name, sport)
    _rate_limit("sofascore.com")
    try:
        html = fetch(url, save_snapshot=False)
        if html is None:
            return {}, "CAPTCHA or empty response from Sofascore"
        stats = _parse_sofascore_stats(html, sport)
        return stats, None
    except Exception as exc:
        return {}, f"Sofascore fetch error: {exc}"


# ---------------------------------------------------------------------------
# Core enrichment functions
# ---------------------------------------------------------------------------

def enrich_team(team_name: str, sport: str, max_retries: int = 2) -> dict:
    """Fetch and save stats for a single team.

    Returns: {
        "team": team_name,
        "sport": sport,
        "status": "enriched" | "partial" | "failed",
        "stats_found": {"corners": 8.5, ...},
        "source": "flashscore" | "sofascore",
        "error": None | "description"
    }
    """
    result = {
        "team": team_name,
        "sport": sport,
        "status": "failed",
        "stats_found": {},
        "source": None,
        "error": None,
    }

    stat_keys = SPORT_STAT_KEYS.get(sport, [])
    if not stat_keys:
        result["error"] = f"No stat keys defined for sport: {sport}"
        return result

    errors = []

    # Try Flashscore first (most reliable)
    for attempt in range(1, max_retries + 1):
        stats, err = _try_flashscore(team_name, sport)
        if stats:
            source = "flashscore"
            result["source"] = source
            # Determine status
            found_keys = set(stats.keys())
            expected_keys = set(stat_keys)
            if found_keys >= expected_keys:
                result["status"] = "enriched"
            elif found_keys:
                result["status"] = "partial"
            else:
                continue  # retry

            result["stats_found"] = {
                k: _safe_avg(v) for k, v in stats.items() if v
            }

            # Save to both cache and DB
            _save_to_cache(team_name, sport, stats, source)
            _save_to_db(team_name, sport, stats, "enrichment-agent")
            return result

        if err:
            errors.append(err)
        if attempt < max_retries:
            time.sleep(1.0)

    # Fallback: try Sofascore
    for attempt in range(1, max_retries + 1):
        stats, err = _try_sofascore(team_name, sport)
        if stats:
            source = "sofascore"
            result["source"] = source
            found_keys = set(stats.keys())
            if found_keys:
                result["status"] = "partial" if found_keys < set(stat_keys) else "enriched"
            result["stats_found"] = {
                k: _safe_avg(v) for k, v in stats.items() if v
            }

            _save_to_cache(team_name, sport, stats, source)
            _save_to_db(team_name, sport, stats, "enrichment-agent")
            return result

        if err:
            errors.append(err)
        if attempt < max_retries:
            time.sleep(1.0)

    result["error"] = "; ".join(errors) if errors else "No data found from any source"
    return result


def enrich_h2h(team_a: str, team_b: str, sport: str) -> dict:
    """Fetch H2H stats between two teams.

    Returns: {
        "team_a": ..., "team_b": ...,
        "status": "enriched" | "failed",
        "meetings_found": 5,
        "h2h_stats": {...}
    }
    """
    result = {
        "team_a": team_a,
        "team_b": team_b,
        "sport": sport,
        "status": "failed",
        "meetings_found": 0,
        "h2h_stats": {},
        "error": None,
    }

    # Build H2H URL — Flashscore pattern
    slug_a = _slugify(team_a)
    slug_b = _slugify(team_b)
    url = f"https://www.flashscore.com/h2h/{slug_a}/{slug_b}/"
    _rate_limit("flashscore.com")

    try:
        html = fetch(url, save_snapshot=False)
        if html is None:
            result["error"] = "CAPTCHA or empty response for H2H page"
            return result

        # Parse H2H data
        stats = _parse_flashscore_stats(html, sport)
        if stats:
            result["status"] = "enriched"
            result["h2h_stats"] = {
                k: _safe_avg(v) for k, v in stats.items() if v
            }
            # Count meetings from data density
            if stats:
                max_vals = max(len(v) for v in stats.values())
                result["meetings_found"] = max_vals

            # Save H2H to DB
            _save_h2h_to_db(team_a, team_b, sport, stats)
        else:
            result["error"] = "No H2H stats parsed from page"

    except Exception as exc:
        result["error"] = f"H2H fetch error: {exc}"

    return result


def _save_h2h_to_db(
    team_a: str, team_b: str, sport: str, stats: dict
) -> None:
    """Save H2H stats to DB."""
    try:
        with get_db() as conn:
            sport_repo = SportRepo(conn)
            team_repo = TeamRepo(conn)
            stats_repo = StatsRepo(conn)

            sport_obj = sport_repo.get_by_name(sport)
            if not sport_obj:
                return

            t_a = team_repo.find_or_create(team_a, sport_obj.id)
            t_b = team_repo.find_or_create(team_b, sport_obj.id)

            for stat_key, values in stats.items():
                form = TeamForm(
                    id=None,
                    team_id=t_a.id,
                    sport_id=sport_obj.id,
                    stat_key=stat_key,
                    l10_values=[],
                    l5_values=[],
                    l10_avg=None,
                    l5_avg=None,
                    h2h_values=values[:10],
                    h2h_opponent_id=t_b.id,
                    trend="stable",
                    updated_at=_now_iso(),
                    source="enrichment-agent",
                )
                stats_repo.save_team_form(form)

            logger.info("Saved H2H to DB: %s vs %s (%s)", team_a, team_b, sport)
    except Exception as exc:
        logger.error("H2H DB save failed: %s", exc)


def batch_enrich(teams: list[dict], max_workers: int = 4) -> list[dict]:
    """Enrich multiple teams in parallel.

    Input: [{"team": "FC Barcelona", "sport": "football", "missing": ["corners", "fouls"]}]
    Returns: list of enrich_team results
    """
    results = []

    # Use ThreadPoolExecutor but respect rate limits via _rate_limit()
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {}
        for entry in teams:
            team_name = entry.get("team", "")
            sport = entry.get("sport", "")
            if not team_name or not sport:
                results.append({
                    "team": team_name,
                    "sport": sport,
                    "status": "failed",
                    "stats_found": {},
                    "source": None,
                    "error": "Missing team name or sport",
                })
                continue
            fut = executor.submit(enrich_team, team_name, sport)
            futures[fut] = entry

        for fut in concurrent.futures.as_completed(futures):
            try:
                res = fut.result()
                results.append(res)
            except Exception as exc:
                entry = futures[fut]
                results.append({
                    "team": entry.get("team", ""),
                    "sport": entry.get("sport", ""),
                    "status": "failed",
                    "stats_found": {},
                    "source": None,
                    "error": str(exc),
                })

    return results


# ---------------------------------------------------------------------------
# Auto-detect missing teams from shortlist
# ---------------------------------------------------------------------------

def _detect_missing_from_shortlist(date_str: str) -> list[dict]:
    """Scan shortlist for candidates with missing stats cache."""
    # Try both date formats: YYYY-MM-DD (pipeline) and YYYYMMDD (legacy)
    shortlist_path = DATA_DIR / f"{date_str}_s2_shortlist.json"
    if not shortlist_path.exists():
        shortlist_path = DATA_DIR / f"{date_str.replace('-', '')}_s2_shortlist.json"
    if not shortlist_path.exists():
        logger.warning("Shortlist not found: %s", shortlist_path)
        return []

    try:
        data = json.loads(shortlist_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.error("Failed to read shortlist: %s", exc)
        return []

    candidates = data.get("candidates", [])
    missing = []

    for c in candidates:
        sport = c.get("sport", "")
        stat_keys = SPORT_STAT_KEYS.get(sport, [])
        if not stat_keys:
            continue

        for team_field in ("home_team", "away_team", "home", "away", "team_a", "team_b"):
            team_name = c.get(team_field, "")
            if not team_name:
                continue

            slug = _slugify(team_name)
            cache_path = CACHE_DIR / sport / f"{slug}.json"
            if not cache_path.exists():
                missing.append({
                    "team": team_name,
                    "sport": sport,
                    "missing": stat_keys,
                })

    # Deduplicate by (team, sport)
    seen = set()
    deduped = []
    for entry in missing:
        key = (entry["team"], entry["sport"])
        if key not in seen:
            seen.add(key)
            deduped.append(entry)

    return deduped


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Self-healing data enrichment agent"
    )
    parser.add_argument("--team", help="Single team name to enrich")
    parser.add_argument("--sport", help="Sport for --team mode")
    parser.add_argument("--batch", help="Path to JSON file with teams to enrich")
    parser.add_argument("--date", help="Auto-detect missing teams from shortlist (YYYY-MM-DD)")
    parser.add_argument("--h2h", nargs=2, metavar=("TEAM_A", "TEAM_B"), help="Fetch H2H stats")
    parser.add_argument("--workers", type=int, default=4, help="Max parallel workers")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    if args.team:
        if not args.sport:
            print("ERROR: --sport required with --team", file=sys.stderr)
            sys.exit(1)
        result = enrich_team(args.team, args.sport)
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif args.h2h:
        if not args.sport:
            print("ERROR: --sport required with --h2h", file=sys.stderr)
            sys.exit(1)
        result = enrich_h2h(args.h2h[0], args.h2h[1], args.sport)
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif args.batch:
        batch_path = Path(args.batch)
        if not batch_path.exists():
            print(f"ERROR: Batch file not found: {batch_path}", file=sys.stderr)
            sys.exit(1)
        try:
            teams = json.loads(batch_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"ERROR: Failed to read batch file: {exc}", file=sys.stderr)
            sys.exit(1)
        results = batch_enrich(teams, max_workers=args.workers)
        print(json.dumps(results, indent=2, ensure_ascii=False))

        # Summary
        enriched = sum(1 for r in results if r["status"] == "enriched")
        partial = sum(1 for r in results if r["status"] == "partial")
        failed = sum(1 for r in results if r["status"] == "failed")
        print(f"\nSummary: {enriched} enriched, {partial} partial, {failed} failed", file=sys.stderr)

    elif args.date:
        missing = _detect_missing_from_shortlist(args.date)
        if not missing:
            print(f"No missing teams found for {args.date}")
            sys.exit(0)
        print(f"Found {len(missing)} teams with missing stats", file=sys.stderr)
        results = batch_enrich(missing, max_workers=args.workers)
        print(json.dumps(results, indent=2, ensure_ascii=False))

        enriched = sum(1 for r in results if r["status"] == "enriched")
        partial = sum(1 for r in results if r["status"] == "partial")
        failed = sum(1 for r in results if r["status"] == "failed")
        print(f"\nSummary: {enriched} enriched, {partial} partial, {failed} failed", file=sys.stderr)

    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
