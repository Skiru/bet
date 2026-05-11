#!/usr/bin/env python3
"""Multi-source odds aggregator CLI.

Replaces manual fetch_odds_api.py calls by querying multiple odds sources
in priority order per sport, merging events, and producing backward-compatible
output files.

Usage:
    python3 scripts/fetch_odds_multi.py                        # full scan
    python3 scripts/fetch_odds_multi.py --sports volleyball    # specific sport
    python3 scripts/fetch_odds_multi.py --sources the-odds-api,oddsportal  # specific sources
    python3 scripts/fetch_odds_multi.py --dry-run              # show plan, no API calls
    python3 scripts/fetch_odds_multi.py --no-window            # don't filter by time window
"""

import argparse
import csv
import json
import sys
import traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "betting" / "data"
CONFIG_DIR = ROOT_DIR / "config"
SCRIPTS_DIR = Path(__file__).resolve().parent

# --- DB dual-write support (optional — falls back gracefully) ---
try:
    sys.path.insert(0, str(ROOT_DIR / "src"))
    from bet.db.connection import get_db
    from bet.db.repositories import SportRepo, TeamRepo, FixtureRepo, OddsRepo
    from bet.db.models import Fixture, OddsRecord
    _HAS_DB = True
except ImportError:
    _HAS_DB = False

# Ensure scripts/ is importable
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from odds_sources import (
    SPORT_SOURCE_PRIORITY,
    events_match,
    merge_event_odds,
)

# ---------------------------------------------------------------------------
# Source registry — lazy-loaded to avoid import errors when a source is broken
# ---------------------------------------------------------------------------

_SOURCE_MODULES = {
    "the-odds-api": ("odds_sources.the_odds_api", "SOURCE"),
    "odds-api-io": ("odds_sources.odds_api_io_source", "SOURCE"),
    "api-football-odds": ("odds_sources.api_football_odds", "SOURCE"),
    "oddsportal": ("odds_sources.oddsportal_scraper", "SOURCE"),
    "betexplorer": ("odds_sources.betexplorer_scraper", "SOURCE"),
    "betclic": ("odds_sources.betclic_scraper", "SOURCE"),
}


def _load_source(name: str):
    """Lazily import and return a source instance, or None on failure."""
    if name not in _SOURCE_MODULES:
        return None
    module_path, attr = _SOURCE_MODULES[name]
    try:
        import importlib
        mod = importlib.import_module(module_path)
        return getattr(mod, attr)
    except Exception as exc:
        print(f"  [WARNING] Could not load source '{name}': {exc}")
        return None


def load_configured_sports() -> list[str]:
    """Load sport list from betting_config.json."""
    config_file = CONFIG_DIR / "betting_config.json"
    if not config_file.exists():
        print(f"[WARNING] {config_file} not found — using defaults")
        return list(SPORT_SOURCE_PRIORITY.keys())
    with open(config_file) as f:
        cfg = json.load(f)
    return cfg.get("sports", list(SPORT_SOURCE_PRIORITY.keys()))


def extract_best_odds(event: dict) -> dict:
    """Extract market-best odds from an event's bookmakers (same logic as fetch_odds_api.py)."""
    result = {
        "id": event.get("id", ""),
        "home_team": event.get("home_team", ""),
        "away_team": event.get("away_team", ""),
        "commence_time": event.get("commence_time", ""),
        "markets": {},
    }
    for market_type in ["h2h", "totals", "spreads"]:
        best = {}
        for bm in event.get("bookmakers", []):
            for market in bm.get("markets", []):
                if market["key"] != market_type:
                    continue
                for outcome in market.get("outcomes", []):
                    key = outcome.get("name", "unknown")
                    if "point" in outcome:
                        key = f"{outcome['name']}_{outcome['point']}"
                    price = outcome.get("price", 0)
                    if not price:
                        continue
                    if key not in best or price > best[key]["price"]:
                        best[key] = {
                            "price": price,
                            "bookmaker": bm["title"],
                            "point": outcome.get("point"),
                        }
        if best:
            result["markets"][market_type] = best
    return result


def _persist_odds_to_db(events: list[dict]) -> None:
    """Dual-write odds data to SQLite knowledge base.

    For each event with bookmaker odds, resolves teams and fixture,
    then saves individual OddsRecord entries.
    """
    if not _HAS_DB:
        return

    now_ts = datetime.now(timezone.utc).isoformat()

    with get_db() as conn:
        sport_repo = SportRepo(conn)
        team_repo = TeamRepo(conn)
        fixture_repo = FixtureRepo(conn)
        odds_repo = OddsRepo(conn)

        saved = 0
        for ev in events:
            sport_name = ev.get("_our_sport", "")
            home_name = ev.get("home_team", "")
            away_name = ev.get("away_team", "")
            kickoff = ev.get("commence_time", "")

            if not sport_name or not home_name or not away_name or not kickoff:
                continue

            sport_obj = sport_repo.get_by_name(sport_name)
            if not sport_obj:
                continue

            home_team = team_repo.find_or_create(home_name, sport_obj.id)
            away_team = team_repo.find_or_create(away_name, sport_obj.id)

            fixture = Fixture(
                id=None,
                sport_id=sport_obj.id,
                competition_id=None,
                home_team_id=home_team.id,
                away_team_id=away_team.id,
                kickoff=kickoff,
                status="scheduled",
                external_id=ev.get("id", ""),
                source=ev.get("_source", "odds_multi"),
                fetched_at=now_ts,
            )
            fixture_id = fixture_repo.upsert(fixture)

            # Save odds from each bookmaker
            for bm in ev.get("bookmakers", []):
                bm_name = bm.get("title", bm.get("key", "unknown"))
                for market in bm.get("markets", []):
                    market_key = market.get("key", "")
                    for outcome in market.get("outcomes", []):
                        price = outcome.get("price", 0)
                        if not price:
                            continue
                        selection = outcome.get("name", "")
                        line = outcome.get("point")

                        record = OddsRecord(
                            id=None,
                            fixture_id=fixture_id,
                            bookmaker=bm_name,
                            market=market_key,
                            selection=selection,
                            odds=price,
                            line=line,
                            fetched_at=now_ts,
                            is_closing=False,
                        )
                        odds_repo.save_odds(record)
                        saved += 1

        if saved:
            print(f"  [DB] Persisted {saved} odds records to knowledge base")


def run_multi_scan(
    sport_filter: list[str] | None = None,
    source_filter: list[str] | None = None,
    dry_run: bool = False,
    use_window: bool = True,
):
    """Run multi-source odds scan."""
    now = datetime.now(timezone.utc)

    # Betting day window: 04:00 UTC today → 03:59 UTC tomorrow (= 06:00–05:59 CEST)
    if use_window:
        date_from = now.strftime("%Y-%m-%d")
        date_to = (now + timedelta(hours=24)).strftime("%Y-%m-%d")
    else:
        date_from = ""
        date_to = ""

    # Determine sports to scan
    all_sports = load_configured_sports()
    if sport_filter:
        all_sports = [s for s in all_sports if s in sport_filter]

    print(f"\n{'=' * 80}")
    print(f"MULTI-SOURCE ODDS AGGREGATOR @ {now.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"{'=' * 80}")
    print(f"Sports: {', '.join(all_sports)}")
    if use_window:
        print(f"Window: {date_from} → {date_to}")
    else:
        print("Window: disabled (all events)")

    # Build scan plan
    scan_plan: dict[str, list[str]] = {}
    for sport in all_sports:
        sources = SPORT_SOURCE_PRIORITY.get(sport, [])
        if source_filter:
            sources = [s for s in sources if s in source_filter]
        if sources:
            scan_plan[sport] = sources

    print(f"\nScan plan ({len(scan_plan)} sports):")
    for sport, sources in scan_plan.items():
        print(f"  {sport}: {' → '.join(sources)}")

    if dry_run:
        print("\n[DRY RUN] No API calls made.")
        return

    # Scan all sources per sport
    all_events: list[dict] = []
    provenance: dict[str, dict[str, int]] = {}  # sport → {source → count}
    total_by_source: dict[str, int] = {}
    errors: list[dict] = []

    for sport, sources in scan_plan.items():
        print(f"\n--- {sport.upper()} ---")
        sport_events: list[dict] = []
        provenance[sport] = {}

        for source_name in sources:
            source = _load_source(source_name)
            if source is None:
                continue

            if sport not in source.supported_sports():
                print(f"  {source_name}: sport not supported — skipping")
                continue

            try:
                fetched = source.fetch_odds(sport, date_from, date_to)
                new_count = 0

                for ev in fetched:
                    # Ensure required fields
                    ev.setdefault("_our_sport", sport)
                    ev.setdefault("_sport_key", ev.get("sport_key", f"{source_name}_{sport}"))
                    ev.setdefault("_source", source_name)

                    # Check for match with existing events
                    matched = False
                    for i, existing in enumerate(sport_events):
                        if events_match(existing, ev):
                            sport_events[i] = merge_event_odds(existing, ev)
                            matched = True
                            break

                    if not matched:
                        sport_events.append(ev)
                        new_count += 1

                provenance[sport][source_name] = new_count
                total_by_source[source_name] = total_by_source.get(source_name, 0) + new_count
                print(f"  {source_name}: {len(fetched)} fetched, {new_count} new events")

            except Exception as exc:
                print(f"  {source_name}: ERROR — {exc}")
                errors.append({
                    "source": source_name,
                    "sport": sport,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                })

        all_events.extend(sport_events)
        print(f"  → {len(sport_events)} total events for {sport}")

    # -----------------------------------------------------------------------
    # Save outputs (backward compatible)
    # -----------------------------------------------------------------------
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # 1) odds_api_snapshot.json — SAME format as fetch_odds_api.py
    snapshot = {
        "timestamp": now.isoformat(),
        "credits_used_this_scan": 0,  # multi-source doesn't track per-credit
        "credits_remaining": "N/A",
        "total_events": len(all_events),
        "events": all_events,
    }
    snapshot_file = DATA_DIR / "odds_api_snapshot.json"
    snapshot_file.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False))

    # 2) odds_api_summary.csv — SAME columns as fetch_odds_api.py
    summary_file = DATA_DIR / "odds_api_summary.csv"
    with open(summary_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "sport", "sport_key", "home", "away", "commence_time",
            "h2h_home", "h2h_away", "total_line", "over_price",
            "over_book", "under_price", "under_book",
        ])
        for ev in all_events:
            best = extract_best_odds(ev)
            h2h = best["markets"].get("h2h", {})
            totals = best["markets"].get("totals", {})

            h2h_home = h2h.get(ev.get("home_team", ""), {}).get("price", "")
            h2h_away = h2h.get(ev.get("away_team", ""), {}).get("price", "")

            over_keys = [k for k in totals if k.startswith("Over")]
            under_keys = [k for k in totals if k.startswith("Under")]

            total_line = ""
            over_price = ""
            over_book = ""
            under_price = ""
            under_book = ""

            if over_keys:
                ok = sorted(over_keys)[0]
                over_price = totals[ok]["price"]
                over_book = totals[ok]["bookmaker"]
                total_line = totals[ok].get("point", "")
            if under_keys:
                uk = sorted(under_keys)[0]
                under_price = totals[uk]["price"]
                under_book = totals[uk]["bookmaker"]

            writer.writerow([
                ev.get("_our_sport", ""),
                ev.get("_sport_key", ev.get("sport_key", "")),
                ev.get("home_team", ""),
                ev.get("away_team", ""),
                ev.get("commence_time", ""),
                h2h_home, h2h_away,
                total_line, over_price, over_book,
                under_price, under_book,
            ])

    # 3) odds_multi_sources.json — provenance log
    provenance_data = {
        "timestamp": now.isoformat(),
        "sources_used": sorted(total_by_source.keys()),
        "per_sport": provenance,
        "total_events": len(all_events),
        "total_by_source": total_by_source,
    }
    if errors:
        provenance_data["errors"] = errors
    provenance_file = DATA_DIR / "odds_multi_sources.json"
    provenance_file.write_text(json.dumps(provenance_data, indent=2, ensure_ascii=False))

    # Dual-write to DB (non-blocking)
    try:
        _persist_odds_to_db(all_events)
    except Exception as db_exc:
        print(f"  [DB WARNING] Odds DB write failed: {db_exc}")

    # Print summary
    print(f"\n{'=' * 80}")
    print(f"SUMMARY: {len(all_events)} events across {len(scan_plan)} sports")
    print(f"Sources used: {', '.join(sorted(total_by_source.keys()))}")
    for src, cnt in sorted(total_by_source.items(), key=lambda x: -x[1]):
        print(f"  {src}: {cnt} events")
    if errors:
        print(f"Errors: {len(errors)}")
    print(f"\nData saved:")
    print(f"  Snapshot: {snapshot_file}")
    print(f"  CSV:      {summary_file}")
    print(f"  Sources:  {provenance_file}")
    print(f"{'=' * 80}\n")

    return all_events


def main():
    from agent_output import AgentOutput, add_agent_args

    parser = argparse.ArgumentParser(
        description="Multi-source odds aggregator — fetches odds from multiple sources in priority order"
    )
    parser.add_argument(
        "--sports", type=str, default=None,
        help="Comma-separated sports to scan (e.g., volleyball,football)",
    )
    parser.add_argument(
        "--sources", type=str, default=None,
        help="Comma-separated sources to use (e.g., the-odds-api,oddsportal)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show scan plan without making API calls",
    )
    parser.add_argument(
        "--no-window", action="store_true",
        help="Don't filter by betting day time window",
    )
    add_agent_args(parser)
    args = parser.parse_args()

    out = AgentOutput("s4_fetch_odds_multi", verbose=args.verbose, stop_on_error=args.stop_on_error)

    sport_filter = None
    if args.sports:
        sport_filter = [s.strip() for s in args.sports.split(",")]

    source_filter = None
    if args.sources:
        source_filter = [s.strip() for s in args.sources.split(",")]

    events = run_multi_scan(
        sport_filter=sport_filter,
        source_filter=source_filter,
        dry_run=args.dry_run,
        use_window=not args.no_window,
    )

    total_events = len(events) if events else 0

    # Count sources from provenance file
    sources_used = []
    source_counts = {}
    try:
        prov_path = DATA_DIR / "odds_multi_sources.json"
        if prov_path.exists():
            prov = json.loads(prov_path.read_text(encoding="utf-8"))
            sources_used = prov.get("sources_used", [])
            source_counts = prov.get("total_by_source", {})
    except Exception:
        pass

    verdict = "OK" if total_events > 0 else "PARTIAL"

    out.summary(
        verdict=verdict,
        metrics={
            "total_events": total_events,
            "sources_used": len(sources_used),
            "source_breakdown": source_counts,
        },
    )

    sys.exit(0 if total_events > 0 else 1)


if __name__ == "__main__":
    main()
