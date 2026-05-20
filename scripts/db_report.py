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
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from bet.db.connection import get_db  # noqa: E402
from bet.stats.rich_coverage import BASELINE_SOURCE, classify_rich_coverage, resolve_fixture_team_scope, summarize_rich_coverage  # noqa: E402
from bet.stats.fallback_chains import RICH_COMPLETION_POLICY  # noqa: E402

FOOTBALL_RICH_KEYS = {
    "corners",
    "yellow_cards",
    "red_cards",
    "shots",
    "shots_on_target",
    "fouls",
    "possession",
}


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
            """SELECT s.name, COUNT(*) FROM fixtures f
            JOIN sports s ON f.sport_id = s.id
            WHERE date(f.kickoff) = ? GROUP BY s.name ORDER BY COUNT(*) DESC""",
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


def report_rich_coverage(betting_date: str, sport: str):
    """Team_form coverage by richness bucket for a single sport."""
    print(f"=== {sport.upper()} RICH COVERAGE for {betting_date} ===\n")

    if sport == "football":
        required_keys = sorted(FOOTBALL_RICH_KEYS)
        allowed_sources = None
        baseline_sources = {BASELINE_SOURCE}
    else:
        policy = RICH_COMPLETION_POLICY.get(sport)
        if not policy:
            print(f"  No rich coverage policy for {sport}")
            return
        required_keys = list(policy["required_rich_keys"])
        allowed_sources = {policy["canonical_source"], *policy["supporting_sources"]}
        baseline_sources = set(policy.get("baseline_sources", []))

    with get_db() as conn:
        sport_row = conn.execute("SELECT id FROM sports WHERE name = ?", (sport,)).fetchone()
        if not sport_row:
            print(f"  {sport} sport not found")
            return

        scope = resolve_fixture_team_scope(conn, sport_row[0], betting_date)
        teams = scope["teams"]

        if not teams:
            print(f"  No {sport} teams for this date")
            return

        if scope["used_fallback"]:
            print(f"  No {sport} teams on {betting_date}; using latest available fixture date {scope['scope_date']}")
            print()

        team_details = []
        rich_source_presence = Counter()
        baseline_source_presence = Counter()
        failure_reasons = Counter()

        for team_id, team_name in teams:
            rows = conn.execute(
                "SELECT stat_key, source FROM team_form WHERE team_id = ? AND sport_id = ?",
                (team_id, sport_row[0]),
            ).fetchall()
            detail = classify_rich_coverage(
                rows,
                required_keys,
                allowed_sources,
                baseline_sources=baseline_sources,
            )
            detail["team"] = team_name
            team_details.append(detail)
            for source in detail["sources"]:
                if not source:
                    continue
                if detail["bucket"] == "rich" and source not in baseline_sources:
                    rich_source_presence[source] += 1
                elif detail["bucket"] == "baseline_only" and source in baseline_sources:
                    baseline_source_presence[source] += 1

            if detail["bucket"] != "rich" and detail["missing_rich_keys"]:
                failure_reasons[", ".join(detail["missing_rich_keys"][:3])] += 1

        summary = summarize_rich_coverage(team_details)
        print(f"  Total teams: {summary['total']}")
        print(f"  Eligible: {summary['eligible']}")
        print(f"  Rich: {summary['rich']}")
        print(f"  Baseline only: {summary['baseline_only']}")
        print(f"  Partial: {summary['partial']}")
        print(f"  No data: {summary['no_data']}")
        print(f"  Completion rate: {summary['completion_rate']}%")

        print("\n  Rich source presence:")
        for source in sorted(rich_source_presence):
            print(f"    {source:24s}: {rich_source_presence[source]}")

        print("\n  Baseline source presence:")
        for source in sorted(baseline_source_presence):
            print(f"    {source:24s}: {baseline_source_presence[source]}")

        if failure_reasons:
            print("\n  Failure reasons:")
            for reason in sorted(failure_reasons):
                print(f"    {reason:24s}: {failure_reasons[reason]}")


def main():
    parser = argparse.ArgumentParser(description="Quick DB reports")
    parser.add_argument(
        "--report",
        required=True,
        choices=["quality", "gaps", "scan", "source-health", "rich-coverage", "football-rich-coverage"],
    )
    parser.add_argument("--date", default=str(date.today()), help="Betting date (YYYY-MM-DD)")
    parser.add_argument("--sport", default="football", choices=sorted({"football", *RICH_COMPLETION_POLICY.keys()}))
    args = parser.parse_args()

    if args.report == "quality":
        report_quality()
    elif args.report == "gaps":
        report_gaps(args.date)
    elif args.report == "scan":
        report_scan(args.date)
    elif args.report == "source-health":
        report_source_health()
    elif args.report == "football-rich-coverage":
        report_rich_coverage(args.date, "football")
    elif args.report == "rich-coverage":
        report_rich_coverage(args.date, args.sport)


if __name__ == "__main__":
    main()
