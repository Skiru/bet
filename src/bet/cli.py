"""CLI entry point for the betting system.

Usage:
    bet run [--date YYYY-MM-DD] [--resume]
    bet settle [--date YYYY-MM-DD]
    bet status [--date YYYY-MM-DD]
    bet history
    bet health
    bet migrate
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import date, datetime, timedelta

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore[no-redef]

from bet.config import BettingConfig


def _betting_day(tz_name: str = "Europe/Warsaw") -> date:
    """Current betting day (06:00 boundary).

    Before 06:00 Warsaw time → yesterday's betting day.
    """
    tz = ZoneInfo(tz_name)
    now = datetime.now(tz)
    if now.hour < 6:
        return (now - timedelta(days=1)).date()
    return now.date()


def _parse_date(date_str: str | None, config: BettingConfig) -> date:
    """Parse --date arg or default to today's betting day."""
    if date_str:
        return date.fromisoformat(date_str)
    return _betting_day(config.timezone)


def cmd_run(args: argparse.Namespace) -> None:
    """Run the full 5-step pipeline."""
    config = BettingConfig.load()
    target = _parse_date(args.date, config)

    from bet.pipeline.orchestrator import run_pipeline

    result = asyncio.run(
        run_pipeline(
            target_date=target,
            config=config,
            resume=args.resume,
        )
    )

    coupons = result.get("coupons_built", 0)
    fixtures = result.get("total_fixtures", 0)
    print(f"Done: {fixtures} fixtures, {coupons} coupons built", file=sys.stderr)


def cmd_settle(args: argparse.Namespace) -> None:
    """Settle a specific day's bets."""
    config = BettingConfig.load()
    target = _parse_date(args.date, config)

    from bet.db.connection import get_db
    from bet.db.schema import init_db
    from bet.settlement.settler import settle_day

    with get_db(config.db_path) as conn:
        init_db(conn)
        conn.commit()
        result = asyncio.run(settle_day(target, conn))

    settled = result.get("settled", 0)
    pending = result.get("still_pending", 0)
    pnl = result.get("pnl", 0)
    print(f"Settled: {settled}, pending: {pending}, PnL: {pnl:+.2f} PLN")


def cmd_status(args: argparse.Namespace) -> None:
    """Show pipeline status for a date."""
    config = BettingConfig.load()
    target = _parse_date(args.date, config)

    from bet.db.connection import get_db
    from bet.db.schema import init_db
    from bet.pipeline.orchestrator import get_pipeline_status

    with get_db(config.db_path) as conn:
        init_db(conn)
        steps = get_pipeline_status(target, conn)

    if not steps:
        print(f"No pipeline run found for {target}")
        return

    print(f"Pipeline status for {target}:")
    for step_info in steps:
        status = step_info["status"]
        step = step_info["step"]
        elapsed = ""
        if step_info["started_at"] and step_info["completed_at"]:
            try:
                s = datetime.fromisoformat(step_info["started_at"])
                e = datetime.fromisoformat(step_info["completed_at"])
                elapsed = f" ({(e - s).total_seconds():.1f}s)"
            except (ValueError, TypeError):
                pass
        error = f" ERROR: {step_info['error_message']}" if step_info.get("error_message") else ""
        print(f"  {step:<12} {status:<10}{elapsed}{error}")


def cmd_history(args: argparse.Namespace) -> None:
    """Show bet/coupon history summary from DB."""
    config = BettingConfig.load()

    from bet.db.connection import get_db
    from bet.db.schema import init_db

    with get_db(config.db_path) as conn:
        init_db(conn)

        row = conn.execute(
            "SELECT COUNT(*) as cnt, "
            "SUM(CASE WHEN status='won' THEN 1 ELSE 0 END) as won, "
            "SUM(CASE WHEN status='lost' THEN 1 ELSE 0 END) as lost, "
            "COALESCE(SUM(pnl_pln), 0) as total_pnl, "
            "COALESCE(SUM(stake_pln), 0) as total_staked "
            "FROM coupons"
        ).fetchone()

        total = row["cnt"]
        won = row["won"] or 0
        lost = row["lost"] or 0
        pnl = row["total_pnl"]
        staked = row["total_staked"]

        if total == 0:
            print("No coupons in database.")
            return

        hit_rate = won / (won + lost) * 100 if (won + lost) > 0 else 0
        roi = pnl / staked * 100 if staked > 0 else 0

        print(f"Coupons: {total} ({won}W / {lost}L)")
        print(f"Hit rate: {hit_rate:.1f}%")
        print(f"Staked: {staked:.2f} PLN | PnL: {pnl:+.2f} PLN | ROI: {roi:.1f}%")

        # Sport breakdown
        sport_rows = conn.execute(
            "SELECT sport, COUNT(*) as cnt, "
            "SUM(CASE WHEN status='won' THEN 1 ELSE 0 END) as won, "
            "SUM(CASE WHEN status='lost' THEN 1 ELSE 0 END) as lost "
            "FROM bets WHERE status IN ('won', 'lost') "
            "GROUP BY sport ORDER BY cnt DESC"
        ).fetchall()

        if sport_rows:
            print("\nSport breakdown:")
            for sr in sport_rows:
                t = sr["won"] + sr["lost"]
                r = sr["won"] / t * 100 if t > 0 else 0
                print(f"  {sr['sport']:<15} {sr['won']}W/{sr['lost']}L = {r:.0f}%")


def cmd_health(args: argparse.Namespace) -> None:
    """Show source health status."""
    config = BettingConfig.load()

    from bet.db.connection import get_db
    from bet.db.repositories import SourceHealthRepo
    from bet.db.schema import init_db

    with get_db(config.db_path) as conn:
        init_db(conn)
        health_repo = SourceHealthRepo(conn)
        sources = health_repo.get_all_health()

    if not sources:
        print("No source health data recorded.")
        return

    print(f"{'Source':<25} {'Requests':>8} {'Failures':>8} {'Consec':>6} {'Avg ms':>8}")
    print("-" * 60)
    for s in sources:
        print(
            f"{s['source_name']:<25} "
            f"{s['total_requests']:>8} "
            f"{s['total_failures']:>8} "
            f"{s['consecutive_failures']:>6} "
            f"{s['avg_response_ms'] or 0:>8.0f}"
        )


def cmd_migrate(args: argparse.Namespace) -> None:
    """Run data migration from JSON/CSV to SQLite."""
    config = BettingConfig.load()

    from bet.db.connection import get_db
    from bet.db.schema import init_db

    with get_db(config.db_path) as conn:
        init_db(conn)
        conn.commit()

    print(f"Database initialized at {config.db_path}")
    print("For full migration from legacy data, run: python scripts/migrate_data.py")


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="bet",
        description="Betting system CLI",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # bet run
    run_parser = subparsers.add_parser("run", help="Run full pipeline")
    run_parser.add_argument("--date", type=str, default=None, help="Target date (YYYY-MM-DD)")
    run_parser.add_argument("--resume", action="store_true", help="Resume from last completed step")
    run_parser.set_defaults(func=cmd_run)

    # bet settle
    settle_parser = subparsers.add_parser("settle", help="Settle a specific day")
    settle_parser.add_argument("--date", type=str, default=None, help="Date to settle (YYYY-MM-DD)")
    settle_parser.set_defaults(func=cmd_settle)

    # bet status
    status_parser = subparsers.add_parser("status", help="Show pipeline status")
    status_parser.add_argument("--date", type=str, default=None, help="Date to check (YYYY-MM-DD)")
    status_parser.set_defaults(func=cmd_status)

    # bet history
    history_parser = subparsers.add_parser("history", help="Show bet/coupon history")
    history_parser.set_defaults(func=cmd_history)

    # bet health
    health_parser = subparsers.add_parser("health", help="Show source health")
    health_parser.set_defaults(func=cmd_health)

    # bet migrate
    migrate_parser = subparsers.add_parser("migrate", help="Run data migration")
    migrate_parser.set_defaults(func=cmd_migrate)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
