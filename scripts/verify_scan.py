#!/usr/bin/env python3
"""Verify scan results for a given sport and date.

Replaces inline `python3 -c "..."` verification blocks that GARBLE in fish shell.
Run this as a proper CLI instead.

Usage:
    python3 scripts/verify_scan.py --sport football --date 2026-05-11
    python3 scripts/verify_scan.py --sport hockey --date 2026-05-11 --verbose
    python3 scripts/verify_scan.py --sport all --date 2026-05-11

Exit codes:
    0 = PASS
    1 = MARGINAL (minor issues)
    2 = FAIL (blocking issues)
"""

import argparse
import json
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from bet.db.connection import get_db  # noqa: E402

# Sport-specific thresholds
THRESHOLDS = {
    "football": {"min_events": 200, "marginal": 100, "required_keys": {"corners", "fouls", "yellow_cards", "shots", "shots_on_target"}},
    "basketball": {"min_events": 20, "marginal": 10, "required_keys": {"points", "rebounds", "assists", "steals", "fg_pct"}},
    "hockey": {"min_events": 10, "marginal": 5, "required_keys": {"shots", "hits", "pim", "powerplay_goals"}},
    "tennis": {"min_events": 30, "marginal": 15, "required_keys": set()},
    "volleyball": {"min_events": 15, "marginal": 5, "required_keys": {"points", "sets", "blocks", "aces"}},
}


def verify_sport(sport: str, betting_date: str, verbose: bool = False) -> dict:
    """Run all verification checks for a sport. Returns verdict dict."""
    thresholds = THRESHOLDS.get(sport, {"min_events": 10, "marginal": 5, "required_keys": set()})
    min_events = thresholds["min_events"]
    min_marginal = thresholds["marginal"]
    required_keys = thresholds["required_keys"]

    result = {
        "sport": sport,
        "date": betting_date,
        "event_count": 0,
        "phantoms": 0,
        "duplicates": 0,
        "completeness_pct": 0.0,
        "leagues_today": 0,
        "leagues_missing": 0,
        "multi_source_events": 0,
        "degraded_sources": [],
        "stat_keys_found": [],
        "issues": [],
        "verdict": "FAIL",
    }

    try:
        with get_db() as conn:
            # Event count
            c = conn.execute(
                "SELECT COUNT(*) FROM scan_results WHERE sport=? AND betting_date=?",
                (sport, betting_date),
            )
            count = c.fetchone()[0]
            result["event_count"] = count

            if count == 0:
                result["issues"].append("0 events found")
                result["verdict"] = "FAIL"
                return result

            # CHECK 1: Phantom detection
            cutoff_iso = (datetime.utcnow() - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
            cutoff_time = (datetime.utcnow() - timedelta(hours=2)).strftime("%H:%M")
            c = conn.execute(
                """SELECT COUNT(*) FROM scan_results
                WHERE sport=? AND betting_date=? AND kickoff != ''
                AND ((length(kickoff) <= 5 AND kickoff < ?) OR (length(kickoff) > 5 AND kickoff < ?))""",
                (sport, betting_date, cutoff_time, cutoff_iso),
            )
            phantoms = c.fetchone()[0]
            result["phantoms"] = phantoms

            # CHECK 2: Duplicate event_keys
            c = conn.execute(
                """SELECT source_domain, event_key, COUNT(*) as cnt FROM scan_results
                WHERE sport=? AND betting_date=? GROUP BY source_domain, event_key HAVING cnt > 1""",
                (sport, betting_date),
            )
            dupes = c.fetchall()
            result["duplicates"] = len(dupes)

            # CHECK 3: Data completeness
            c = conn.execute(
                """SELECT
                    COALESCE(SUM(CASE WHEN home_team IS NULL OR home_team='' THEN 1 ELSE 0 END), 0),
                    COALESCE(SUM(CASE WHEN away_team IS NULL OR away_team='' THEN 1 ELSE 0 END), 0),
                    COALESCE(SUM(CASE WHEN competition IS NULL OR competition='' THEN 1 ELSE 0 END), 0),
                    COALESCE(SUM(CASE WHEN kickoff IS NULL OR kickoff='' THEN 1 ELSE 0 END), 0),
                    COUNT(*)
                FROM scan_results WHERE sport=? AND betting_date=?""",
                (sport, betting_date),
            )
            no_home, no_away, no_comp, no_ko, total = c.fetchone()
            completeness = round((1 - max(no_home, no_away, no_comp, no_ko) / max(total, 1)) * 100, 1)
            result["completeness_pct"] = completeness

            # CHECK 4: League coverage vs yesterday
            c = conn.execute(
                "SELECT DISTINCT competition FROM scan_results WHERE sport=? AND betting_date=? AND competition != ''",
                (sport, betting_date),
            )
            today_leagues = set(r[0] for r in c)
            yesterday = str(date.fromisoformat(betting_date) - timedelta(days=1))
            c = conn.execute(
                "SELECT DISTINCT competition FROM scan_results WHERE sport=? AND betting_date=? AND competition != ''",
                (sport, yesterday),
            )
            yest_leagues = set(r[0] for r in c)
            missing = yest_leagues - today_leagues
            result["leagues_today"] = len(today_leagues)
            result["leagues_missing"] = len(missing)

            # CHECK 5: Cross-source coverage
            c = conn.execute(
                """SELECT event_key, COUNT(DISTINCT source_domain) as src_cnt FROM scan_results
                WHERE sport=? AND betting_date=? GROUP BY event_key HAVING src_cnt >= 2""",
                (sport, betting_date),
            )
            multi = len(c.fetchall())
            result["multi_source_events"] = multi

            # CHECK 6: Source health
            c = conn.execute(
                """SELECT source_name, consecutive_failures, total_requests, total_failures
                FROM source_health WHERE consecutive_failures > 3 ORDER BY consecutive_failures DESC LIMIT 5"""
            )
            degraded = c.fetchall()
            result["degraded_sources"] = [
                {"name": s[0], "consecutive": s[1], "total_req": s[2], "total_fail": s[3]}
                for s in degraded
            ]

            # CHECK 7: Stat keys in raw_data
            c = conn.execute(
                "SELECT raw_data FROM scan_results WHERE sport=? AND betting_date=? AND raw_data IS NOT NULL LIMIT 20",
                (sport, betting_date),
            )
            stat_keys_found = set()
            for row in c:
                try:
                    data = json.loads(row[0]) if row[0] else {}
                except (json.JSONDecodeError, TypeError):
                    data = {}
                stat_keys_found.update(data.get("stat_keys", []))
            result["stat_keys_found"] = sorted(stat_keys_found & required_keys) if required_keys else sorted(stat_keys_found)

            # Tennis: surface detection
            if sport == "tennis":
                c = conn.execute(
                    "SELECT raw_data FROM scan_results WHERE sport=? AND betting_date=? AND raw_data IS NOT NULL LIMIT 30",
                    (sport, betting_date),
                )
                surfaces = set()
                for row in c:
                    try:
                        data = json.loads(row[0]) if row[0] else {}
                    except (json.JSONDecodeError, TypeError):
                        data = {}
                    if data.get("surface"):
                        surfaces.add(data["surface"])
                result["surfaces"] = sorted(surfaces)

            # Determine issues
            issues = []
            if count < min_marginal:
                issues.append(f"only {count} events (need ≥{min_marginal})")
            if phantoms > 5:
                issues.append(f"{phantoms} phantom fixtures")
            if dupes:
                issues.append(f"{len(dupes)} duplicate event_keys")
            if completeness < 80:
                issues.append(f"completeness {completeness}%")
            if len(missing) > 3:
                issues.append(f"{len(missing)} leagues missing vs yesterday")

            result["issues"] = issues

            # Verdict
            if count >= min_events and not issues:
                result["verdict"] = "PASS"
            elif count >= min_marginal and len(issues) <= 1:
                result["verdict"] = "MARGINAL"
            else:
                result["verdict"] = "FAIL"

    except Exception as e:
        result["issues"].append(f"DB error: {e}")
        result["verdict"] = "FAIL"

    return result


def print_result(result: dict, verbose: bool = False):
    """Print human-readable verification result."""
    sport = result["sport"]
    print(f"\n{'='*50}")
    print(f"SCAN VERIFICATION: {sport.upper()} | {result['date']}")
    print(f"{'='*50}")
    print(f"Events:        {result['event_count']}")
    print(f"Phantoms:      {result['phantoms']}")
    print(f"Duplicates:    {result['duplicates']}")
    print(f"Completeness:  {result['completeness_pct']}%")
    print(f"Leagues today: {result['leagues_today']} | Missing vs yesterday: {result['leagues_missing']}")
    print(f"Multi-source:  {result['multi_source_events']}/{result['event_count']}")

    if result.get("degraded_sources"):
        print(f"\nDegraded sources ({len(result['degraded_sources'])}):")
        for s in result["degraded_sources"]:
            print(f"  {s['name']}: {s['consecutive']} consecutive failures ({s['total_fail']}/{s['total_req']} total)")
    else:
        print("Sources:       All healthy")

    if result.get("stat_keys_found"):
        print(f"Stat keys:     {result['stat_keys_found']}")
    elif result["sport"] != "tennis":
        print("Stat keys:     NONE (expected at scan phase — enrichment adds them)")

    if result["sport"] == "tennis" and "surfaces" in result:
        print(f"Surfaces:      {result.get('surfaces') or 'NONE — TennisExplorer may have failed'}")

    if result["issues"]:
        print(f"\nIssues ({len(result['issues'])}):")
        for issue in result["issues"]:
            print(f"  ⚠️  {issue}")

    print(f"\nVERDICT: {result['verdict']}")


def main():
    parser = argparse.ArgumentParser(description="Verify scan results for a sport")
    parser.add_argument("--sport", required=True, help="Sport to verify (football/basketball/hockey/tennis/volleyball/all)")
    parser.add_argument("--date", required=True, help="Betting date (YYYY-MM-DD)")
    parser.add_argument("--verbose", action="store_true", help="Show extra detail")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="Output format")
    args = parser.parse_args()

    sports = list(THRESHOLDS.keys()) if args.sport == "all" else [args.sport]
    results = []
    worst_exit = 0

    for sport in sports:
        result = verify_sport(sport, args.date, args.verbose)
        results.append(result)

        if args.format == "text":
            print_result(result, args.verbose)

        if result["verdict"] == "FAIL":
            worst_exit = max(worst_exit, 2)
        elif result["verdict"] == "MARGINAL":
            worst_exit = max(worst_exit, 1)

    if args.format == "json":
        output = results[0] if len(results) == 1 else {"results": results}
        print(json.dumps(output, indent=2))

    # AGENT_SUMMARY for structured output protocol
    summary = {
        "verdict": "FAIL" if worst_exit == 2 else ("MARGINAL" if worst_exit == 1 else "PASS"),
        "sports_checked": len(sports),
        "total_events": sum(r["event_count"] for r in results),
        "issues_total": sum(len(r["issues"]) for r in results),
    }
    print(f"\nAGENT_SUMMARY:{json.dumps(summary)}")

    sys.exit(worst_exit)


if __name__ == "__main__":
    main()
