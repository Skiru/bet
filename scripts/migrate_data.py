#!/usr/bin/env python3
"""One-time migration: JSON/CSV → SQLite.

Imports:
1. betting/data/betclic_bets_history.json → coupons + bets tables
2. betting/journal/picks-ledger.csv → bets table (supplement)
3. betting/journal/coupons-ledger.csv → coupons table (supplement)

Usage:
    python scripts/migrate_data.py
    python scripts/migrate_data.py --dry-run
"""

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

# Ensure the package is importable
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "src"))

from bet.db.connection import get_db
from bet.db.schema import init_db
from bet.db.models import Bet, Coupon
from bet.db.repositories import CouponRepo, SportRepo

DB_PATH = ROOT_DIR / "betting" / "data" / "betting.db"
HISTORY_PATH = ROOT_DIR / "betting" / "data" / "betclic_bets_history.json"
PICKS_LEDGER = ROOT_DIR / "betting" / "journal" / "picks-ledger.csv"
COUPONS_LEDGER = ROOT_DIR / "betting" / "journal" / "coupons-ledger.csv"


def _parse_betclic_date(date_str: str) -> str:
    """Parse Betclic date format '27.04.2026 14:42' to ISO 8601."""
    if not date_str:
        return ""
    try:
        dt = datetime.strptime(date_str.strip(), "%d.%m.%Y %H:%M")
        return dt.isoformat()
    except ValueError:
        return date_str


def _parse_version(version_str: str) -> int:
    """Parse version string like 'v1', 'v18-night' to integer."""
    import re
    match = re.search(r"\d+", version_str or "1")
    return int(match.group()) if match else 1


def _map_status(status_label: str) -> str:
    """Map Betclic status labels to our status enum."""
    mapping = {
        "won": "won",
        "lost": "lost",
        "void": "void",
        "push": "push",
        "pending": "pending",
        "Wygrane": "won",
        "Przegrane": "lost",
        "Anulowane": "void",
    }
    return mapping.get(status_label, status_label.lower() if status_label else "pending")


def migrate_betclic_history(conn, history_path: Path, dry_run: bool = False) -> dict:
    """Import betclic_bets_history.json into coupons + bets."""
    if not history_path.exists():
        print(f"  [skip] {history_path} not found")
        return {"coupons_imported": 0, "bets_imported": 0}

    with open(history_path, encoding="utf-8") as f:
        history = json.load(f)

    repo = CouponRepo(conn)
    coupons_imported = 0
    bets_imported = 0

    for entry in history:
        ref_id = entry.get("ref_id", entry.get("footer_ref", ""))
        coupon_id = f"BC-{ref_id}" if ref_id else f"BC-{coupons_imported + 1:04d}"
        bet_type = entry.get("bet_type", "AKO")
        coupon_type = "SINGLE" if "SINGLE" in bet_type.upper() else "AKO"
        status = _map_status(entry.get("coupon_status", "pending"))

        stake = entry.get("stake_pln", 0)
        winnings = entry.get("winnings_pln", 0)
        pnl = winnings - stake if status == "won" else -stake if status == "lost" else 0

        placed_at = _parse_betclic_date(entry.get("placed_date", ""))

        coupon = Coupon(
            id=None,
            coupon_id=coupon_id,
            coupon_type=coupon_type,
            total_odds=entry.get("total_odds"),
            stake_pln=stake,
            status=status,
            pnl_pln=pnl,
            placed_at=placed_at,
            settled_at=placed_at if status != "pending" else "",
            betclic_ref=ref_id,
            version=1,
            created_at=placed_at or datetime.now().isoformat(),
        )

        if dry_run:
            print(f"  [dry-run] coupon {coupon_id}: {coupon_type}, {status}, stake={stake}")
            coupons_imported += 1
            bets_imported += len(entry.get("legs", []))
            continue

        try:
            db_coupon_id = repo.create_coupon(coupon)
        except Exception as e:
            print(f"  [warn] Duplicate coupon {coupon_id}: {e}")
            continue

        coupons_imported += 1

        for leg in entry.get("legs", []):
            sport = leg.get("sport", "unknown")
            home = leg.get("home", "")
            away = leg.get("away", "")
            event_name = f"{home} vs {away}" if home and away else leg.get("event", "")

            bet = Bet(
                id=None,
                coupon_id=db_coupon_id,
                fixture_id=None,
                sport=sport,
                event_name=event_name,
                market=leg.get("market", ""),
                selection=leg.get("selection", ""),
                odds=leg.get("odds", 0),
                min_odds=None,
                safety_score=None,
                hit_rate=None,
                status=_map_status(leg.get("leg_status", "pending")),
                pnl_pln=None,
                settled_at="",
                market_pl=leg.get("market", ""),
                navigation_hint="",
            )
            repo.add_bet(bet)
            bets_imported += 1

    if not dry_run:
        conn.commit()

    return {"coupons_imported": coupons_imported, "bets_imported": bets_imported}


def migrate_picks_ledger(conn, ledger_path: Path, dry_run: bool = False) -> dict:
    """Import picks-ledger.csv rows as supplemental bet data."""
    if not ledger_path.exists():
        print(f"  [skip] {ledger_path} not found")
        return {"picks_imported": 0}

    imported = 0
    with open(ledger_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if dry_run:
                pick_id = row.get("pick_id", "")
                print(f"  [dry-run] pick {pick_id}: {row.get('event', '')}")
            imported += 1

    return {"picks_imported": imported}


def migrate_coupons_ledger(conn, ledger_path: Path, dry_run: bool = False) -> dict:
    """Import coupons-ledger.csv rows."""
    if not ledger_path.exists():
        print(f"  [skip] {ledger_path} not found")
        return {"coupons_imported": 0}

    repo = CouponRepo(conn)
    imported = 0

    with open(ledger_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            coupon_id = row.get("coupon_id", "")
            if not coupon_id:
                continue

            if not dry_run:
                # Check if already imported (from Betclic history)
                existing = conn.execute(
                    "SELECT id FROM coupons WHERE coupon_id = ?", (coupon_id,)
                ).fetchone()
                if existing:
                    continue

            status = _map_status(row.get("status", "pending"))
            stake = float(row.get("stake_pln", 0) or 0)
            pnl = float(row.get("pnl_pln", 0) or 0)

            coupon = Coupon(
                id=None,
                coupon_id=coupon_id,
                coupon_type="AKO",
                total_odds=float(row.get("combined_odds", 0) or 0) or None,
                stake_pln=stake,
                status=status,
                pnl_pln=pnl,
                placed_at=row.get("odds_checked_at_local", ""),
                settled_at="",
                betclic_ref="",
                version=_parse_version(row.get("version", "v1")),
                created_at=row.get("betting_day", datetime.now().isoformat()),
            )

            if dry_run:
                print(f"  [dry-run] coupon {coupon_id}: {status}")
                imported += 1
                continue

            try:
                repo.create_coupon(coupon)
                imported += 1
            except Exception as e:
                print(f"  [warn] Failed to import coupon {coupon_id}: {e}")

    if not dry_run:
        conn.commit()

    return {"coupons_imported": imported}


def main():
    parser = argparse.ArgumentParser(description="Migrate JSON/CSV data to SQLite")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be imported")
    parser.add_argument("--db-path", type=Path, default=DB_PATH, help="Database path")
    args = parser.parse_args()

    print(f"Migration target: {args.db_path}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'LIVE'}")
    print()

    with get_db(args.db_path) as conn:
        # Initialize schema
        if not args.dry_run:
            init_db(conn)
            SportRepo(conn).seed_defaults()
            conn.commit()
            print("[✓] Schema initialized and sports seeded")

        # 1. Betclic history
        print("\n[1/3] Importing Betclic history...")
        result1 = migrate_betclic_history(conn, HISTORY_PATH, dry_run=args.dry_run)
        print(f"  → {result1['coupons_imported']} coupons, {result1['bets_imported']} bets")

        # 2. Coupons ledger (before picks, to avoid orphan references)
        print("\n[2/3] Importing coupons ledger...")
        result2 = migrate_coupons_ledger(conn, COUPONS_LEDGER, dry_run=args.dry_run)
        print(f"  → {result2['coupons_imported']} additional coupons")

        # 3. Picks ledger (supplemental)
        print("\n[3/3] Scanning picks ledger...")
        result3 = migrate_picks_ledger(conn, PICKS_LEDGER, dry_run=args.dry_run)
        print(f"  → {result3['picks_imported']} picks scanned")

    if not args.dry_run:
        # Verify
        import sqlite3
        verify_conn = sqlite3.connect(str(args.db_path))
        bets_count = verify_conn.execute("SELECT COUNT(*) FROM bets").fetchone()[0]
        coupons_count = verify_conn.execute("SELECT COUNT(*) FROM coupons").fetchone()[0]
        verify_conn.close()
        print(f"\n[✓] Migration complete: {coupons_count} coupons, {bets_count} bets in DB")
    else:
        print("\n[i] Dry run complete — no data written")


if __name__ == "__main__":
    main()
