#!/usr/bin/env python3
"""Quick DB reports for pipeline monitoring.

Replaces inline `python3 -c "from bet.db.connection..."` blocks
that GARBLE in fish shell.

Usage:
    python3 scripts/db_report.py --report quality
    python3 scripts/db_report.py --report gaps --date 2026-05-11
    python3 scripts/db_report.py --report scan --date 2026-05-11
    python3 scripts/db_report.py --report source-health

Exit codes:
    0 = Report generated successfully
    1 = Issues found
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from bet.db.connection import get_db  # noqa: E402


def report_quality():
    """Data quality overview — row counts for all tables."""
    tables = [
        "sports", "teams", "competitions", "fixtures", "team_form", "match_stats",
        "league_profiles", "standings", "odds_history", "scan_results", "source_health",
        "analysis_results", "gate_results", "coupons", "bets", "espn_predictions",
        "player_gamelogs", "pipeline_runs",
    ]
    print("=== DATA QUALITY REPORT ===\n")
    with get_db() as conn:
        for t in tables:
            try:
                count = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                print(f"  {t:30s}: {count:>8} rows")
            except Exception:
                print(f"  {t:30s}: TABLE MISSING")


def report_gaps(betting_date: str):
    """Fixtures missing team_form data."""
    print(f"=== GAP ANALYSIS for {betting_date} ===\n")
    with get_db() as conn:
        gaps = conn.execute(
            """SELECT f.id, t1.name, t2.name, s.name as sport
            FROM fixtures f
            JOIN teams t1 ON f.home_team_id = t1.id
            JOIN teams t2 ON f.away_team_id = t2.id
            JOIN sports s ON f.sport_id = s.id
            LEFT JOIN team_form tf ON tf.team_id = t1.id
            WHERE date(f.kickoff) = ? AND tf.id IS NULL""",
            (betting_date,),
        ).fetchall()
        print(f"  Fixtures missing home team_form: {len(gaps)}")
        for g in gaps[:15]:
            print(f"    {g[3]}: {g[1]} vs {g[2]}")

        # Also check away team gaps
        gaps_away = conn.execute(
            """SELECT f.id, t1.name, t2.name, s.name as sport
            FROM fixtures f
            JOIN teams t1 ON f.home_team_id = t1.id
            JOIN teams t2 ON f.away_team_id = t2.id
            JOIN sports s ON f.sport_id = s.id
            LEFT JOIN team_form tf ON tf.team_id = t2.id
            WHERE date(f.kickoff) = ? AND tf.id IS NULL""",
            (betting_date,),
        ).fetchall()
        print(f"  Fixtures missing away team_form: {len(gaps_away)}")


def report_scan(betting_date: str):
    """Scan results summary for a date."""
    print(f"=== SCAN RESULTS for {betting_date} ===\n")
    with get_db() as conn:
        # Scan run stats
        try:
            c = conn.execute(
                "SELECT sport, events_found, sources_ok, sources_failed FROM scan_run_stats WHERE betting_date=? ORDER BY sport",
                (betting_date,),
            )
            rows = c.fetchall()
            if rows:
                print("  Scan run stats:")
                for row in rows:
                    print(f"    {row[0]:15s}: {row[1]:>6} events, {row[2]:>3} OK, {row[3]:>2} failed")
            else:
                print("  No scan_run_stats for this date")
        except Exception:
            print("  scan_run_stats table not available")

        # Scan results by sport
        c = conn.execute(
            "SELECT sport, COUNT(*) FROM scan_results WHERE betting_date=? GROUP BY sport ORDER BY COUNT(*) DESC",
            (betting_date,),
        )
        rows = c.fetchall()
        print(f"\n  Scan results by sport:")
        for row in rows:
            print(f"    {row[0]:15s}: {row[1]}")
        if not rows:
            print("    (none)")

        # Fixtures
        c = conn.execute(
            "SELECT sport, COUNT(*) FROM fixtures WHERE date(kickoff) = ? GROUP BY sport ORDER BY COUNT(*) DESC",
            (betting_date,),
        )
        rows = c.fetchall()
        total = sum(r[1] for r in rows)
        print(f"\n  Fixtures total: {total}")
        for row in rows:
            print(f"    {row[0]:15s}: {row[1]}")


def report_source_health():
    """Source health overview."""
    print("=== SOURCE HEALTH ===\n")
    with get_db() as conn:
        c = conn.execute(
            """SELECT source_name, total_requests, total_failures,
            ROUND(total_failures*100.0/MAX(total_requests,1),1) as fail_pct
            FROM source_health ORDER BY total_requests DESC LIMIT 20"""
        )
        for row in c:
            print(f"  {row[0]:30s}: {row[1]:>5} req, {row[2]:>3} fail ({row[3]}%)")


def main():
    parser = argparse.ArgumentParser(description="Quick DB reports")
    parser.add_argument("--report", required=True, choices=["quality", "gaps", "scan", "source-health"])
    parser.add_argument("--date", default=str(date.today()), help="Betting date (YYYY-MM-DD)")
    args = parser.parse_args()

    if args.report == "quality":
        report_quality()
    elif args.report == "gaps":
        report_gaps(args.date)
    elif args.report == "scan":
        report_scan(args.date)
    elif args.report == "source-health":
        report_source_health()


if __name__ == "__main__":
    main()
