#!/usr/bin/env python3
"""Deep Analysis Pool Generator — produces 20+ deeply analyzed statistical events.

This is the PRIMARY output of the betting analysis engine. Each event shows ALL
statistical markets ranked by safety score with L10/H2H/L5 averages, hit rates,
three-way checks, and odds when available.

Usage:
    python3 scripts/deep_analysis_pool.py --date 2026-04-28
    python3 scripts/deep_analysis_pool.py --date 2026-04-28 --min-events 20
    python3 scripts/deep_analysis_pool.py --date 2026-04-28 --sports football,basketball,hockey
    python3 scripts/deep_analysis_pool.py --date 2026-04-28 --cache-only
"""

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from normalize_stats import build_safety_input
from compute_safety_scores import rank_markets

from db_data_loader import load_fixtures_from_db, load_odds_from_db

DATA_DIR = Path(__file__).parent.parent / "betting" / "data"


def load_odds_snapshot(date: str | None = None) -> dict:
    """Load odds and return lookup dict keyed by normalized "home|away".

    Uses DB-first loading via load_odds_from_db when date is provided,
    falls back to direct JSON read when date is None (backward compat).
    """
    try:
        if date is not None:
            data = load_odds_from_db(date)
        else:
            # Try DB with today's date as best-effort
            try:
                from datetime import date as _date_cls
                data = load_odds_from_db(_date_cls.today().isoformat())
                if data and data.get("events"):
                    print(f"[pool] DB: loaded odds for {len(data['events'])} events (no date specified, using today)")
            except Exception:
                data = None
            if not data or not data.get("events"):
                odds_path = DATA_DIR / "odds_api_snapshot.json"
                if not odds_path.exists():
                    return {}
                data = json.loads(odds_path.read_text(encoding="utf-8"))
    except Exception:
        return {}

    odds_lookup: dict = {}
    items: list = []
    if isinstance(data, dict):
        if "events" in data and isinstance(data["events"], list):
            items = data["events"]
        else:
            for sport_data in data.values():
                if isinstance(sport_data, list):
                    items.extend(sport_data)
    elif isinstance(data, list):
        items = data
    for event in items:
        home = _normalize_team(event.get("home_team", ""))
        away = _normalize_team(event.get("away_team", ""))
        if home and away:
            odds_lookup[f"{home}|{away}"] = event
    return odds_lookup


from utils import normalize_team_name as _normalize_team


def _fuzzy_odds_lookup(home: str, away: str, odds_lookup: dict) -> dict:
    """Find odds for a fixture using fuzzy matching.

    Tries exact match first, then normalized match, then substring containment.
    """
    # Exact case-insensitive
    key_exact = f"{home.lower()}|{away.lower()}"
    if key_exact in odds_lookup:
        return odds_lookup[key_exact]

    # Normalized match
    key_norm = f"{_normalize_team(home)}|{_normalize_team(away)}"
    if key_norm in odds_lookup:
        return odds_lookup[key_norm]

    # Substring containment — find best match
    home_norm = _normalize_team(home)
    away_norm = _normalize_team(away)
    for key, event in odds_lookup.items():
        parts = key.split("|", 1)
        if len(parts) != 2:
            continue
        k_home, k_away = parts
        if ((home_norm in k_home or k_home in home_norm) and len(home_norm) >= 3 and
                (away_norm in k_away or k_away in away_norm) and len(away_norm) >= 3):
            return event

    return {}


def load_api_stats_summary(date: str) -> dict:
    """Load API stats enrichment summary."""
    summary_path = DATA_DIR / f"api_stats_summary_{date}.json"
    if not summary_path.exists():
        return {}
    try:
        return json.loads(summary_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def analyze_fixture(fixture: dict, odds_lookup: dict) -> dict | None:
    """Analyze a single fixture: build safety score input from cache, run rank_markets().

    1. Extract sport, team_a, team_b, competition from fixture
    2. Call build_safety_input_from_cache() to get safety score input
    3. If insufficient data, return None
    4. Call rank_markets() from compute_safety_scores
    5. Attach odds from odds_lookup if available
    6. Compute EV: EV = (safety_score * odds) - 1 for best market
    7. Determine data quality: FULL (API + H2H + odds), PARTIAL, THIN
    8. Return analysis dict
    """
    sport = fixture.get("sport", "football")
    home_team = fixture.get("home_team", fixture.get("home", ""))
    away_team = fixture.get("away_team", fixture.get("away", ""))
    competition = fixture.get("competition", fixture.get("league", ""))
    kickoff = fixture.get("kickoff", fixture.get("date", ""))
    fixture_id = fixture.get("fixture_id", fixture.get("id", ""))
    source = fixture.get("source", "")

    if not home_team or not away_team:
        return None

    # Build safety score input from cache
    safety_input = build_safety_input(sport, home_team, away_team, competition)

    # If no cached stats, still include the fixture with minimal data
    # so it appears in the analysis pool (user decides, not auto-rejection)
    if safety_input is None:
        # Return a minimal event so fixtures aren't silently dropped
        return {
            "fixture_id": str(fixture_id),
            "sport": sport,
            "competition": competition,
            "home_team": home_team,
            "away_team": away_team,
            "kickoff": kickoff,
            "data_quality": "NO_CACHE",
            "sources": [source] if source else [],
            "best_market": None,
            "all_markets": [],
            "odds": {},
            "ev": None,
            "markdown_table": "",
            "cache_miss": True,
        }

    # Run safety score calculator
    result = rank_markets(safety_input)

    if not result or not result.get("ranking"):
        # Still return fixture even without ranking — it exists
        return {
            "fixture_id": str(fixture_id),
            "sport": sport,
            "competition": competition,
            "home_team": home_team,
            "away_team": away_team,
            "kickoff": kickoff,
            "data_quality": "NO_RANKING",
            "sources": [source] if source else [],
            "best_market": None,
            "all_markets": [],
            "odds": {},
            "ev": None,
            "markdown_table": "",
            "cache_miss": False,
        }

    # Find odds — use fuzzy matching to handle name variations
    odds_data = _fuzzy_odds_lookup(home_team, away_team, odds_lookup)

    # Fallback: scan odds from stats_cache when API odds unavailable
    scan_odds = {}
    if not odds_data:
        try:
            from build_stats_cache import read_cache, slugify
            cache_a = read_cache(sport, home_team)
            if cache_a and cache_a.get("scan_odds"):
                scan_odds = cache_a["scan_odds"]
        except Exception:
            pass

    best_market = result["ranking"][0] if result["ranking"] else None

    # Determine data quality
    has_h2h = best_market and not best_market.get("h2h_blind", True)
    has_odds = bool(odds_data)
    has_odds = bool(odds_data) or bool(scan_odds)
    if has_h2h and has_odds:
        data_quality = "FULL"
    elif has_h2h or (len(result.get("ranking", [])) >= 3):
        data_quality = "PARTIAL"
    else:
        data_quality = "THIN"

    # Build event dict
    event: dict = {
        "fixture_id": str(fixture_id),
        "sport": sport,
        "competition": competition,
        "home_team": home_team,
        "away_team": away_team,
        "kickoff": kickoff,
        "data_quality": data_quality,
        "sources": [source] if source else [],
        "best_market": None,
        "all_markets": [],
        "odds": {},
        "scan_odds": scan_odds if scan_odds else {},
        "ev": None,
        "cache_miss": False,
    }

    if best_market:
        event["best_market"] = {
            "name": f"{best_market['name']} {best_market['line']}",
            "direction": best_market["direction"],
            "safety_score": best_market["safety_score"],
            "l10_avg": best_market["combined_avg"],
            "h2h_avg": best_market.get("h2h_avg"),
            "l5_avg": result.get("three_way_check", {}).get("l5_avg"),
            "hit_rate_l10": best_market["hit_rate_l10"],
            "hit_rate_h2h": best_market["hit_rate_h2h"],
            "three_way": result.get("three_way_check", {}).get("alignment", "N/A"),
            "margin": best_market["margin"],
        }

    # All markets
    for mkt in result.get("ranking", []):
        event["all_markets"].append({
            "rank": mkt["rank"],
            "name": f"{mkt['name']} {mkt['line']}",
            "direction": mkt["direction"],
            "safety": mkt["safety_score"],
            "l10_avg": mkt["combined_avg"],
            "team_a_avg": mkt.get("team_a_avg"),
            "team_b_avg": mkt.get("team_b_avg"),
            "h2h_avg": mkt.get("h2h_avg"),
            "hit_l10": mkt["hit_rate_l10"],
            "hit_h2h": mkt["hit_rate_h2h"],
            "hit_l5": mkt.get("hit_rate_l5", "N/A"),
            "margin": mkt["margin"],
            "h2h_blind": mkt.get("h2h_blind", False),
        })

    event["markdown_table"] = result.get("markdown_ranking_table", "")

    # Compute EV from odds data — only when odds can be meaningfully matched
    # The odds API provides h2h (match winner) and totals (goals O/U) markets
    # Match our best_market to the appropriate odds market key
    if best_market and odds_data:
        best_name_lower = (best_market.get("name", "") or "").lower()
        bookmakers = odds_data.get("bookmakers", [])

        # Determine which odds market key matches our best market
        matching_key = None
        # Totals markets: goals, points, runs, sets, games, corners, cards,
        # fouls, shots — any statistical total can use the "totals" odds line
        # as a proxy for EV direction (Over/Under pricing)
        totals_keywords = (
            "total", "over", "under", "corner", "card", "foul",
            "shot", "goal", "point", "run", "set", "game",
            "ace", "rebound", "assist",
        )
        if any(kw in best_name_lower for kw in totals_keywords):
            matching_key = "totals"
        elif any(kw in best_name_lower for kw in ("winner", "1x2", "match_winner", "moneyline", "ml")):
            matching_key = "h2h"

        if matching_key:
            for bm in bookmakers:
                for market in bm.get("markets", []):
                    if market.get("key") == matching_key:
                        for outcome in market.get("outcomes", []):
                            price = outcome.get("price")
                            if price and isinstance(price, (int, float)):
                                event["odds"]["market_best"] = max(
                                    event["odds"].get("market_best", 0), price
                                )

            market_best = event["odds"].get("market_best")
            if market_best and best_market.get("safety_score"):
                safety = best_market["safety_score"]
                event["ev"] = round(safety * market_best - 1, 4)

    # Fallback: compute EV from scan odds when API odds unavailable
    if event.get("ev") is None and scan_odds and best_market and best_market.get("safety_score"):
        # Use W1 odds as proxy for match-level pricing
        scan_price = scan_odds.get("w1") or scan_odds.get("w2")
        if scan_price and isinstance(scan_price, (int, float)) and scan_price > 1.0:
            safety = best_market["safety_score"]
            event["ev"] = round(safety * scan_price - 1, 4)
            event["odds"]["scan_best"] = scan_price

    return event


def generate_analysis_pool(
    date: str,
    sports: list[str] | None = None,
    min_events: int = 20,
    cache_only: bool = False,
) -> dict:
    """Generate the full analysis pool.

    1. Load fixtures
    2. Filter by sports if specified
    3. For each fixture, analyze (build safety input from cache + rank markets)
    4. Rank all events by best market safety score
    5. Return pool dict
    """
    fixtures = load_fixtures_from_db(date)
    if not fixtures:
        print(f"[pool] No fixtures for {date}")
        return {
            "date": date,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "api_usage": {},
            "total_fixtures_discovered": 0,
            "total_fixtures_with_data": 0,
            "total_events_in_pool": 0,
            "events": [],
        }

    if sports:
        fixtures = [f for f in fixtures if f.get("sport", "football") in sports]

    odds_lookup = load_odds_snapshot(date)

    # Group fixtures by sport for parallel processing
    sport_groups: dict[str, list[dict]] = {}
    for fixture in fixtures:
        sport = fixture.get("sport", "football")
        sport_groups.setdefault(sport, []).append(fixture)

    print(f"[pool] Processing {len(fixtures)} fixtures across {len(sport_groups)} sports in parallel")

    events: list[dict] = []
    skipped = 0

    if not sport_groups:
        print("[pool] No fixtures to analyze")
        return {
            "date": date,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "api_usage": {},
            "total_fixtures_discovered": 0,
            "total_fixtures_with_data": 0,
            "total_events_in_pool": 0,
            "events": [],
        }

    def _analyze_sport_group(sport_fixtures: list[dict]) -> list[dict]:
        """Analyze all fixtures for a single sport."""
        results = []
        for fixture in sport_fixtures:
            try:
                event = analyze_fixture(fixture, odds_lookup)
                if event:
                    results.append(event)
            except Exception as e:
                home = fixture.get('home_team', fixture.get('home', '?'))
                away = fixture.get('away_team', fixture.get('away', '?'))
                print(f"[pool] Error analyzing {home} vs {away}: {e}")
        return results

    max_workers = min(len(sport_groups), 4)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_sport = {
            executor.submit(_analyze_sport_group, sport_fixtures): sport
            for sport, sport_fixtures in sport_groups.items()
        }
        for future in as_completed(future_to_sport):
            sport = future_to_sport[future]
            try:
                sport_events = future.result()
                events.extend(sport_events)
                sport_count = len(sport_groups[sport])
                print(f"[pool] {sport}: {len(sport_events)}/{sport_count} fixtures analyzed")
            except Exception as e:
                print(f"[pool] ERROR analyzing {sport}: {e}")
                skipped += len(sport_groups.get(sport, []))

    # Sort by best market safety score (desc)
    events.sort(
        key=lambda e: (
            e.get("best_market", {}).get("safety_score", 0)
            if e.get("best_market")
            else 0
        ),
        reverse=True,
    )

    # Add rank
    for i, event in enumerate(events, 1):
        event["rank"] = i

    # Load rate limiter for usage summary
    api_usage: dict = {}
    try:
        from api_clients import RateLimiter

        rl = RateLimiter()
        api_usage = rl.get_usage_summary()
    except Exception:
        pass

    pool = {
        "date": date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "api_usage": api_usage,
        "total_fixtures_discovered": len(fixtures),
        "total_fixtures_with_data": len(events),
        "total_events_in_pool": len(events),
        "events": events,
    }

    return pool


def write_pool_json(pool: dict, date: str) -> Path:
    """Write analysis pool to JSON."""
    output_path = DATA_DIR / f"analysis_pool_{date}.json"
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(pool, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"[pool] JSON: {output_path} ({pool['total_events_in_pool']} events)")
    return output_path


def write_pool_markdown(pool: dict, date: str) -> Path:
    """Write human-readable analysis pool markdown."""
    lines: list[str] = []
    lines.append(f"# Analysis Pool — {date}")
    lines.append(
        f"Generated: {pool.get('generated_at', 'N/A')} | "
        f"Fixtures: {pool.get('total_fixtures_discovered', 0)} discovered, "
        f"{pool.get('total_fixtures_with_data', 0)} enriched, "
        f"{pool.get('total_events_in_pool', 0)} in pool"
    )
    lines.append("")

    # API Usage table
    api_usage = pool.get("api_usage", {})
    if api_usage:
        lines.append("## API Usage")
        lines.append("| API | Used | Remaining | Limit |")
        lines.append("|-----|------|-----------|-------|")
        for api, info in api_usage.items():
            if isinstance(info, dict):
                lines.append(
                    f"| {api} | {info.get('used', 0)} | "
                    f"{info.get('remaining', '?')} | {info.get('limit', '?')} |"
                )
        lines.append("")

    lines.append("---")
    lines.append("")

    # Events
    for event in pool.get("events", []):
        rank = event.get("rank", "?")
        home = event.get("home_team", "?")
        away = event.get("away_team", "?")
        comp = event.get("competition", "")
        kickoff = event.get("kickoff", "")
        sport = event.get("sport", "")
        quality = event.get("data_quality", "")

        best = event.get("best_market", {})

        # Confidence indicator based on safety score
        safety = best.get("safety_score", 0) if best else 0
        if safety >= 0.80:
            conf_tag = "HIGH CONFIDENCE"
        elif safety >= 0.65:
            conf_tag = "MEDIUM CONFIDENCE"
        elif safety >= 0.50:
            conf_tag = "LOW CONFIDENCE"
        else:
            conf_tag = "THIN DATA"

        lines.append(
            f"## #{rank} — {home} vs {away} | {comp} | {kickoff} | {sport.upper()} | {conf_tag}"
        )

        if best:
            ev_str = ""
            if event.get("ev") is not None:
                ev_str = f" | EV: {event['ev']:+.1%}"
            lines.append(
                f"**BEST: {best.get('name', '?')} {best.get('direction', '?')}** | "
                f"Safety: {best.get('safety_score', '?')} | "
                f"3-Way: {best.get('three_way', 'N/A')}{ev_str}"
            )
            lines.append(
                f"Data: {quality} | L10 avg: {best.get('l10_avg', '?')} | "
                f"H2H avg: {best.get('h2h_avg', 'N/A')} | "
                f"L5 avg: {best.get('l5_avg', 'N/A')} | "
                f"Margin: {best.get('margin', '?')}"
            )

        lines.append("")

        # All markets table
        all_markets = event.get("all_markets", [])
        if all_markets:
            lines.append(
                "| # | Market | Dir | L10 avg | TeamA | TeamB | H2H avg | Hit L10 | Hit H2H | Safety | Margin |"
            )
            lines.append(
                "|---|--------|-----|---------|-------|-------|---------|---------|---------|--------|--------|"
            )
            for mkt in all_markets:
                h2h_avg = mkt.get("h2h_avg")
                h2h_str = f"{h2h_avg}" if h2h_avg is not None else "N/A"
                ta = mkt.get("team_a_avg", "—")
                tb = mkt.get("team_b_avg", "—")
                blind = " *" if mkt.get("h2h_blind") else ""
                lines.append(
                    f"| {mkt.get('rank', '?')} | {mkt.get('name', '?')} | "
                    f"{mkt.get('direction', '?')} | {mkt.get('l10_avg', '?')} | "
                    f"{ta} | {tb} | "
                    f"{h2h_str}{blind} | {mkt.get('hit_l10', 'N/A')} | "
                    f"{mkt.get('hit_h2h', 'N/A')} | {mkt.get('safety', '?')} | "
                    f"{mkt.get('margin', '?')} |"
                )

        lines.append("")
        lines.append("---")
        lines.append("")

    # Summary
    lines.append("## Summary")
    lines.append(f"- Total events analyzed: {pool.get('total_events_in_pool', 0)}")
    sports_set = set(e.get("sport", "?") for e in pool.get("events", []))
    lines.append(f"- Sports covered: {', '.join(sorted(sports_set))}")

    quality_counts: dict[str, int] = {}
    for e in pool.get("events", []):
        q = e.get("data_quality", "?")
        quality_counts[q] = quality_counts.get(q, 0) + 1
    lines.append(
        f"- Data quality: {', '.join(f'{q}: {c}' for q, c in quality_counts.items())}"
    )

    md_text = "\n".join(lines)
    output_path = DATA_DIR / f"analysis_pool_{date}.md"
    output_path.write_text(md_text, encoding="utf-8")
    print(f"[pool] Markdown: {output_path}")
    return output_path


# CLI
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate deep analysis pool")
    parser.add_argument("--date", help="Date YYYY-MM-DD (default: today)")
    parser.add_argument(
        "--min-events", type=int, default=20, help="Minimum events target"
    )
    parser.add_argument("--sports", help="Comma-separated sports filter")
    parser.add_argument(
        "--cache-only",
        action="store_true",
        help="Use cached stats only, no new API calls",
    )
    args = parser.parse_args()

    date = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sports = args.sports.split(",") if args.sports else None

    pool = generate_analysis_pool(date, sports, args.min_events, args.cache_only)

    write_pool_json(pool, date)
    write_pool_markdown(pool, date)

    print(f"\n[pool] Analysis complete: {pool['total_events_in_pool']} events in pool")
    if pool["total_events_in_pool"] < args.min_events:
        print(
            f"[pool] WARNING: Only {pool['total_events_in_pool']} events, "
            f"target was {args.min_events}"
        )
        print(
            "[pool] Tip: Run fetch_api_stats.py first to enrich more fixtures with API data"
        )
