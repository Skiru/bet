#!/usr/bin/env python3
"""Scan Health Report — Structured health dashboard for agent-driven monitoring.

Reads scan_run_stats from DB after parallel scan completes. Produces a structured
health report that agents can evaluate to decide which sports need healing.

Usage:
    python3 scripts/scan_health_report.py --date 2026-05-07
    python3 scripts/scan_health_report.py --date 2026-05-07 --json-only

Output:
    betting/data/scan_health_{date}.json — structured health data
    stdout — human-readable health dashboard
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date as date_cls, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bet.db.connection import get_db
from bet.db.repositories import ScanResultRepo

DATA_DIR = Path(__file__).parent.parent / "betting" / "data"

# Per-sport thresholds: (min_events, target_events, critical_sport)
SPORT_THRESHOLDS: dict[str, tuple[int, int, bool]] = {
    "football": (100, 300, True),
    "tennis": (20, 80, True),
    "basketball": (15, 50, True),
    "volleyball": (10, 40, True),
    "hockey": (8, 30, True),
}

# Map scanner groups to sports covered
GROUP_TO_SPORTS: dict[str, list[str]] = {
    "football": ["football"],
    "tennis": ["tennis"],
    "basketball": ["basketball"],
    "volleyball": ["volleyball"],
    "hockey": ["hockey"],
}


def generate_health_report(betting_date: str) -> dict:
    """Generate structured health report from scan_run_stats.

    Returns dict with:
      - per_sport: health status for each scanner group
      - summary: aggregate stats
      - needs_healing: list of sports that need agent intervention
      - healing_priority: ordered list (critical first)
    """
    report = {
        "date": betting_date,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "per_sport": {},
        "summary": {},
        "needs_healing": [],
        "healing_priority": [],
        "all_healthy": True,
    }

    # Read scan_run_stats from DB
    try:
        with get_db() as conn:
            repo = ScanResultRepo(conn)
            all_stats = repo.get_run_stats(betting_date)
    except Exception as e:
        report["error"] = f"DB read failed: {e}"
        report["all_healthy"] = False
        # Fallback: check if any sport JSON exists
        return report

    # Index by scanner_group
    stats_by_group: dict[str, dict] = {}
    for stat in all_stats:
        stats_by_group[stat.scanner_group] = {
            "sport": stat.sport,
            "scanner_group": stat.scanner_group,
            "events_found": stat.events_found,
            "sources_ok": stat.sources_ok,
            "sources_failed": stat.sources_failed,
            "deep_links_found": stat.deep_links_found,
            "duration_seconds": stat.duration_seconds,
            "validation_passed": stat.validation_passed,
            "gaps_description": stat.gaps_description,
            "scan_timestamp": stat.scan_timestamp,
        }

    total_events = 0
    total_sources_ok = 0
    total_sources_failed = 0
    sports_healthy = 0
    sports_degraded = 0
    sports_failed = 0
    sports_missing = 0

    for group, (min_events, target_events, is_critical) in SPORT_THRESHOLDS.items():
        stat = stats_by_group.get(group)

        if stat is None:
            # Scanner didn't run at all
            sport_health = {
                "scanner_group": group,
                "status": "MISSING",
                "events_found": 0,
                "min_events": min_events,
                "target_events": target_events,
                "is_critical": is_critical,
                "sources_ok": 0,
                "sources_failed": 0,
                "source_failure_rate": 0,
                "duration_seconds": 0,
                "validation_passed": False,
                "gaps": ["Scanner did not execute"],
                "diagnosis": "Scanner was not launched or crashed before reporting",
                "healing_action": "re-run",
            }
            sports_missing += 1
            report["all_healthy"] = False
            report["needs_healing"].append(group)
        else:
            events = stat["events_found"]
            sources_ok = stat["sources_ok"]
            sources_failed = stat["sources_failed"]
            total_sources = sources_ok + sources_failed
            failure_rate = (sources_failed / total_sources * 100) if total_sources > 0 else 0

            # Determine status
            if stat["validation_passed"] and events >= min_events:
                if events >= target_events * 0.7:
                    status = "HEALTHY"
                    sports_healthy += 1
                else:
                    status = "DEGRADED"
                    sports_degraded += 1
                    report["all_healthy"] = False
                    report["needs_healing"].append(group)
                diagnosis = ""
                healing_action = "none"
            elif events >= min_events:
                # Has minimum events but validation failed (e.g., gaps in specific sources)
                status = "DEGRADED"
                sports_degraded += 1
                report["all_healthy"] = False
                report["needs_healing"].append(group)
                diagnosis = f"Validation failed despite {events} events. Gaps: {stat['gaps_description']}"
                healing_action = "targeted-retry"
            elif events > 0:
                # Has some events but below minimum
                status = "FAILED"
                sports_failed += 1
                report["all_healthy"] = False
                report["needs_healing"].append(group)
                diagnosis = f"Only {events}/{min_events} minimum events found"
                healing_action = "full-retry"
            else:
                # Zero events
                status = "FAILED"
                sports_failed += 1
                report["all_healthy"] = False
                report["needs_healing"].append(group)
                diagnosis = "Zero events discovered"
                healing_action = "full-retry" if is_critical else "check-seasonal"

            sport_health = {
                "scanner_group": group,
                "status": status,
                "events_found": events,
                "min_events": min_events,
                "target_events": target_events,
                "is_critical": is_critical,
                "sources_ok": sources_ok,
                "sources_failed": sources_failed,
                "source_failure_rate": round(failure_rate, 1),
                "duration_seconds": stat["duration_seconds"],
                "validation_passed": stat["validation_passed"],
                "gaps": stat["gaps_description"],
                "diagnosis": diagnosis,
                "healing_action": healing_action,
            }

            total_events += events
            total_sources_ok += sources_ok
            total_sources_failed += sources_failed

        report["per_sport"][group] = sport_health

    # Build healing priority (critical sports first, then by severity)
    priority = []
    for group in report["needs_healing"]:
        sport_data = report["per_sport"][group]
        # Score: critical=100, failed=50, degraded=20, missing=80
        score = 0
        if sport_data["is_critical"]:
            score += 100
        if sport_data["status"] == "MISSING":
            score += 80
        elif sport_data["status"] == "FAILED":
            score += 50
        elif sport_data["status"] == "DEGRADED":
            score += 20
        priority.append((score, group))

    priority.sort(reverse=True)
    report["healing_priority"] = [group for _, group in priority]

    # Summary
    total_sources = total_sources_ok + total_sources_failed
    report["summary"] = {
        "total_events": total_events,
        "total_sources_ok": total_sources_ok,
        "total_sources_failed": total_sources_failed,
        "overall_failure_rate": round(
            (total_sources_failed / total_sources * 100) if total_sources > 0 else 0, 1
        ),
        "sports_healthy": sports_healthy,
        "sports_degraded": sports_degraded,
        "sports_failed": sports_failed,
        "sports_missing": sports_missing,
        "sports_total": len(SPORT_THRESHOLDS),
        "needs_healing_count": len(report["needs_healing"]),
    }

    return report


def print_health_dashboard(report: dict) -> None:
    """Print human-readable health dashboard to stdout."""
    print("=" * 70)
    print(f"  SCAN HEALTH DASHBOARD — {report['date']}")
    print("=" * 70)
    print()

    summary = report["summary"]
    total = summary["total_events"]
    healing = summary["needs_healing_count"]
    all_ok = report["all_healthy"]

    status_icon = "🟢" if all_ok else ("🟡" if healing <= 2 else "🔴")
    print(f"  {status_icon} Overall: {total} events | "
          f"{summary['sports_healthy']}/{summary['sports_total']} healthy | "
          f"{healing} need healing")
    print(f"  Sources: {summary['total_sources_ok']} OK / "
          f"{summary['total_sources_failed']} failed "
          f"({summary['overall_failure_rate']:.0f}% failure rate)")
    print()

    # Per-sport table
    print(f"  {'Sport':<12} {'Status':<10} {'Events':<10} {'Min':<5} "
          f"{'Sources':<12} {'Duration':<8} {'Action'}")
    print(f"  {'-'*12} {'-'*10} {'-'*10} {'-'*5} {'-'*12} {'-'*8} {'-'*20}")

    for group in sorted(report["per_sport"].keys()):
        s = report["per_sport"][group]
        status_map = {
            "HEALTHY": "🟢 HEALTHY",
            "DEGRADED": "🟡 DEGRADED",
            "FAILED": "🔴 FAILED",
            "MISSING": "⚫ MISSING",
        }
        status = status_map.get(s["status"], s["status"])
        sources = f"{s['sources_ok']}/{s['sources_ok'] + s['sources_failed']}"
        duration = f"{s['duration_seconds']:.0f}s"
        action = s["healing_action"]
        crit = " ⭐" if s["is_critical"] else ""
        print(f"  {group:<12} {status:<10} {s['events_found']:<10} "
              f"{s['min_events']:<5} {sources:<12} {duration:<8} {action}{crit}")

    # Healing priority
    if report["healing_priority"]:
        print()
        print(f"  HEALING PRIORITY:")
        for i, group in enumerate(report["healing_priority"], 1):
            s = report["per_sport"][group]
            crit_tag = " [CRITICAL]" if s["is_critical"] else ""
            print(f"    {i}. {group}{crit_tag} — {s['diagnosis']}")

    print()
    print("=" * 70)


def write_health_json(report: dict, betting_date: str) -> Path:
    """Write health report to JSON file."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    output_path = DATA_DIR / f"scan_health_{betting_date}.json"
    output_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Generate scan health report")
    parser.add_argument("--date", help="Betting date YYYY-MM-DD (default: today)")
    parser.add_argument("--json-only", action="store_true",
                        help="Only write JSON, no stdout dashboard")
    args = parser.parse_args()

    betting_date = args.date or date_cls.today().isoformat()
    report = generate_health_report(betting_date)

    # Write JSON
    json_path = write_health_json(report, betting_date)

    if not args.json_only:
        print_health_dashboard(report)
        print(f"\n  Written to: {json_path}")

    # Exit code: 0 = all healthy, 1 = needs healing
    sys.exit(0 if report["all_healthy"] else 1)


if __name__ == "__main__":
    main()
