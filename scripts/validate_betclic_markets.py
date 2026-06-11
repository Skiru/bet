#!/usr/bin/env python3
"""Betclic market availability scanner and coupon validator.

Pre-coupon gate: Scans Betclic.pl to determine which markets actually exist
for events in today's betting window. Flags picks that recommend markets
unavailable on Betclic.

Usage:
    # Full scan (all sports, save to DB)
    PYTHONPATH=src .venv/bin/python3 scripts/validate_betclic_markets.py \\
        --date 2026-05-18 --verbose

    # Quick scan (football only, 10 events max)
    PYTHONPATH=src .venv/bin/python3 scripts/validate_betclic_markets.py \\
        --date 2026-05-18 --sports football --max-events 10

    # Validate specific coupon
    PYTHONPATH=src .venv/bin/python3 scripts/validate_betclic_markets.py \\
        --date 2026-05-18 --validate-coupon betting/coupons/2026-05-18.md

Pipeline position: Runs AFTER gate_checker.py, BEFORE coupon_builder.py
"""
import argparse
import json
import logging
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))

from bet.scrapers.betclic import BetclicMarketChecker, COMPETITION_REGISTRY

logger = logging.getLogger(__name__)

DATA_DIR = ROOT_DIR / "betting" / "data"


# ─── Coupon parsing ──────────────────────────────────────────────────────────

def parse_coupon_picks(coupon_path: Path) -> list[dict]:
    """Parse picks from a coupon markdown file to validate against Betclic."""
    if not coupon_path.exists():
        return []

    text = coupon_path.read_text(encoding="utf-8")
    picks = []

    # Parse the PEŁNA MATRYCA table
    for line in text.split("\n"):
        if not line.startswith("|") or line.startswith("|---") or line.startswith("| #"):
            continue
        cols = [c.strip() for c in line.split("|")]
        if len(cols) < 9:
            continue
        try:
            # | # | Sport | Wydarzenie | Rynek | Kurs | Safety | Hit% | Kierunek | Uwagi |
            idx = cols[1]
            if not idx.isdigit():
                continue
            sport_emoji = cols[2]
            event = cols[3]
            market = cols[4]
            direction = cols[8] if len(cols) > 8 else ""

            # Map emoji to sport
            sport_map = {"⚽": "football", "🎾": "tennis", "🏀": "basketball",
                        "🏐": "volleyball", "🏒": "hockey"}
            sport = sport_map.get(sport_emoji.strip(), "unknown")

            # Detect market type from market name
            market_type = _detect_market_type(market, sport)

            picks.append({
                "idx": int(idx),
                "sport": sport,
                "event": event,
                "market": market,
                "market_type": market_type,
                "direction": direction,
            })
        except (ValueError, IndexError):
            continue

    return picks


def _detect_market_type(market_name: str, sport: str) -> str:
    """Detect pipeline market type from Polish market name in coupon."""
    m = market_name.lower()

    # Football statistical
    if "corner" in m or "rożn" in m:
        return "corners_total"
    if "card" in m or "kartk" in m:
        return "cards_total"
    if "shot" in m and "target" in m:
        return "shots_on_target"
    if "shot" in m:
        return "shots_total"
    if "foul" in m or "faul" in m:
        return "fouls"

    # Goals
    if "goals total" in m or "gole" in m:
        return "goals_total"
    if "btts" in m or "oba" in m:
        return "btts"

    # Tennis
    if "game" in m or "gem" in m:
        return "games_total"
    if "set" in m:
        return "sets_total"
    if "double fault" in m or "podwójn" in m:
        return "double_faults"
    if "ace" in m:
        return "aces"

    # Basketball/Volleyball
    if "point" in m or "punkt" in m:
        return "points_total"

    # Outcome
    if "handicap" in m:
        return "handicap"
    if "winner" in m or "wynik" in m:
        return "match_winner"

    return "unknown"


# ─── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Betclic market availability scanner & coupon validator"
    )
    parser.add_argument("--date", required=True, help="Betting date (YYYY-MM-DD)")
    parser.add_argument("--sports", nargs="+", default=None,
                       help="Sports to scan (default: all)")
    parser.add_argument("--max-events", type=int, default=0,
                       help="Max events per sport to check (0 = all, default: 0)")
    parser.add_argument("--validate-coupon", default=None,
                       help="Path to coupon markdown to validate")
    parser.add_argument("--output", default=None, help="Output JSON path")
    parser.add_argument("--no-db", action="store_true", help="Skip DB persistence")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    # DB connection
    db_conn = None
    db_ctx = None
    if not args.no_db:
        try:
            from bet.db.connection import get_db
            # get_db() is a generator context manager; we need to manage it manually
            # since BetclicMarketChecker holds the connection across its lifecycle
            import sqlite3 as _sqlite3
            from bet.db.connection import DEFAULT_DB_PATH, _configure_connection
            db_conn = _sqlite3.connect(str(DEFAULT_DB_PATH))
            _configure_connection(db_conn)
        except Exception as e:
            logger.warning(f"Could not connect to DB: {e}")

    print(f"\n{'='*60}")
    print(f"  BETCLIC MARKET VALIDATION — {args.date}")
    print(f"{'='*60}")

    with BetclicMarketChecker(betting_date=args.date, db_conn=db_conn) as checker:
        # Phase 1: Scan Betclic
        print(f"\n--- Phase 1: Scanning Betclic markets ---")
        checker.scan_all_sports(
            sports=args.sports,
            max_events_per_sport=args.max_events,
        )

        # Save to DB
        if db_conn:
            checker.save_to_db()

        summary = checker.build_summary()
        print(f"  Events checked: {summary['total_events']}")
        print(f"  With Statystyki: {summary['with_statistics_tab']}")
        print(f"  Without Statystyki: {summary['without_statistics_tab']}")

        # Phase 2: Validate coupon picks (if requested)
        validation_results = None
        if args.validate_coupon:
            print(f"\n--- Phase 2: Validating coupon picks ---")
            coupon_path = Path(args.validate_coupon)
            picks = parse_coupon_picks(coupon_path)
            print(f"  Parsed {len(picks)} picks from coupon")

            if picks:
                validation_results = checker.validate_picks(picks)

                # Report
                available = [v for v in validation_results if v.get("betclic_available") is True]
                unavailable = [v for v in validation_results if v.get("betclic_available") is False]
                unknown = [v for v in validation_results if v.get("betclic_available") is None]

                print(f"\n  ✅ Available: {len(available)} picks")
                print(f"  ❌ Unavailable: {len(unavailable)} picks")
                print(f"  ⚠️  Unknown: {len(unknown)} picks")

                if unavailable:
                    print(f"\n  ❌ UNAVAILABLE MARKETS:")
                    for v in unavailable:
                        print(f"     #{v['idx']} {v['event'][:40]} | "
                              f"{v['market']} | {v['betclic_note']}")

        # Phase 3: Competition profile summary
        print(f"\n--- Competition market profiles ---")
        if summary["competitions_with_stats"]:
            print(f"  ✅ WITH statistical markets:")
            for c in sorted(summary["competitions_with_stats"]):
                print(f"     • {c}")
        if summary["competitions_without_stats"]:
            print(f"  ❌ WITHOUT statistical markets:")
            for c in sorted(summary["competitions_without_stats"]):
                print(f"     • {c}")

        # Output
        output_data = {
            "date": args.date,
            "scanned_at": datetime.now(timezone.utc).isoformat(),
            "summary": summary,
            "validation": validation_results,
            "events": [r.to_dict() for r in checker.results],
        }

        output_path = args.output or str(DATA_DIR / f"betclic_market_validation_{args.date}.json")
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_text(
            json.dumps(output_data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"\n  Output: {output_path}")

    if db_conn:
        db_conn.commit()
        db_conn.close()

    # AGENT_SUMMARY
    verdict = "OK" if summary["total_events"] > 0 else "FAILED"
    unavail_count = len(unavailable) if validation_results else 0
    print(f'\nAGENT_SUMMARY:{{"verdict":"{verdict}",'
          f'"total_events":{summary["total_events"]},'
          f'"with_stats":{summary["with_statistics_tab"]},'
          f'"without_stats":{summary["without_statistics_tab"]},'
          f'"unavailable_picks":{unavail_count},'
          f'"output":"{output_path}"}}')
    sys.exit(0 if summary["total_events"] > 0 else 2)


if __name__ == "__main__":
    main()
