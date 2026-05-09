#!/usr/bin/env python3
"""Persistent source health tracker — logs source availability per session.

After each scan, appends source health data to source_health_log.csv.
Scanner agent reads this before starting to prioritize healthy sources.
"""

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

LOG_PATH = Path("betting/data/source_health_log.csv")
LOG_HEADERS = [
    "date", "source_name", "sport", "status", "events_extracted", "error_message"
]

# Map URL domains to source names
DOMAIN_TO_SOURCE = {
    "betexplorer.com": "BetExplorer",
    "flashscore.com": "Flashscore",
    "sofascore.com": "Sofascore",
    "oddsportal.com": "OddsPortal",
    "soccerstats.com": "SoccerStats",
    "totalcorner.com": "TotalCorner",
    "tennisabstract.com": "TennisAbstract",
    "sportsbookreview.com": "SBR",
    "espn.com": "ESPN",
    "scoresandodds.com": "ScoresAndOdds",
    "zawodtyper.pl": "ZawodTyper",
    "typersi.pl": "Typersi",
    "meczyki.pl": "Meczyki",
    "sportsgambler.com": "Sportsgambler",
    "olbg.com": "OLBG",
    "pickswise.com": "Pickswise",
    "betideas.com": "BetIdeas",
    "betaminic.com": "Betaminic",
    "covers.com": "Covers",
    "teamrankings.com": "TeamRankings",
    "naturalstattrick.com": "NaturalStatTrick",
    "moneypuck.com": "MoneyPuck",
    "dailyfaceoff.com": "DailyFaceoff",
    "sportowefakty.wp.pl": "SportoweFakty",
}

# URL path to sport mapping
SPORT_PATTERNS = {
    "soccer": "football", "football": "football", "pilka": "football",
    "tennis": "tennis", "tenis": "tennis",
    "basketball": "basketball", "nba": "basketball",
    "hockey": "hockey", "nhl": "hockey",
    "volleyball": "volleyball",
}


def sanitize_csv_field(value: str) -> str:
    """Prevent CSV injection by escaping dangerous prefixes."""
    if value and value[0] in ("=", "+", "-", "@"):
        return f"'{value}"
    return value


def extract_domain(url: str) -> str:
    """Extract domain from URL."""
    try:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path.split("/")[0]
        # Remove www prefix
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    except Exception:
        return url


def detect_sport_from_url(url: str) -> str:
    """Detect sport from URL path."""
    url_lower = url.lower()
    for pattern, sport in SPORT_PATTERNS.items():
        if pattern in url_lower:
            return sport
    return "unknown"


def parse_scan_results(
    summary_path: Path, errors_path: Path
) -> list[dict]:
    """Merge scan_summary.json + scan_errors.json into health records."""
    records = []
    today = datetime.now().strftime("%Y-%m-%d")

    # Parse successful fetches from scan_summary
    if summary_path.exists():
        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            source_events = defaultdict(lambda: defaultdict(int))

            # scan_summary.json format: {url: [items]}
            if isinstance(summary, dict):
                for url, items in summary.items():
                    if not isinstance(items, list):
                        continue
                    domain = extract_domain(url)
                    source_name = DOMAIN_TO_SOURCE.get(domain, domain)
                    sport = detect_sport_from_url(url)
                    source_events[source_name][sport] += len(items)
            elif isinstance(summary, list):
                # Legacy format: [{event}, ...]
                for event in summary:
                    url = event.get("source_url", "")
                    sport = event.get("sport", detect_sport_from_url(url))
                    domain = extract_domain(url)
                    source_name = DOMAIN_TO_SOURCE.get(domain, domain)
                    source_events[source_name][sport] += 1

            for source_name, sports in source_events.items():
                for sport, count in sports.items():
                    records.append({
                        "date": today,
                        "source_name": source_name,
                        "sport": sport,
                        "status": "ok",
                        "events_extracted": count,
                        "error_message": "",
                    })
        except (json.JSONDecodeError, KeyError):
            pass

    # Parse failures from scan_errors
    if errors_path.exists():
        try:
            errors = json.loads(errors_path.read_text(encoding="utf-8"))
            error_list = errors if isinstance(errors, list) else errors.get("errors", [])
            for error in error_list:
                url = error.get("url", "")
                domain = extract_domain(url)
                source_name = DOMAIN_TO_SOURCE.get(domain, domain)
                sport = detect_sport_from_url(url)
                error_msg = error.get("error", "Unknown error")

                records.append({
                    "date": today,
                    "source_name": sanitize_csv_field(source_name),
                    "sport": sanitize_csv_field(sport),
                    "status": "fail",
                    "events_extracted": 0,
                    "error_message": sanitize_csv_field(error_msg[:200]),
                })
        except (json.JSONDecodeError, KeyError):
            pass

    return records


def append_to_log(records: list[dict]):
    """Append new rows to source health log CSV."""
    file_exists = LOG_PATH.exists()
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    with open(LOG_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=LOG_HEADERS)
        if not file_exists:
            writer.writeheader()
        for record in records:
            writer.writerow(record)


def get_source_reliability(days: int = 7, source: str | None = None) -> dict:
    """Query the log for recent reliability stats."""
    if not LOG_PATH.exists():
        return {"error": "No health log found", "sources": {}}

    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    stats = defaultdict(lambda: {"ok": 0, "fail": 0, "events_total": 0, "sports": set()})

    with open(LOG_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("date", "") < cutoff:
                continue
            name = row.get("source_name", "")
            if source and name.lower() != source.lower():
                continue

            status = row.get("status", "")
            stats[name][status] = stats[name].get(status, 0) + 1
            stats[name]["events_total"] += int(row.get("events_extracted", 0))
            stats[name]["sports"].add(row.get("sport", ""))

    result = {"period_days": days, "sources": {}}
    for name, s in sorted(stats.items()):
        total = s.get("ok", 0) + s.get("fail", 0)
        success_rate = s.get("ok", 0) / total if total > 0 else 0
        result["sources"][name] = {
            "total_requests": total,
            "success": s.get("ok", 0),
            "failures": s.get("fail", 0),
            "success_rate": round(success_rate * 100, 1),
            "events_total": s["events_total"],
            "sports": sorted(s["sports"] - {""}),
        }

    return result


def suggest_fallbacks(days: int = 7) -> dict:
    """Suggest sources to deprioritize based on recent failures."""
    reliability = get_source_reliability(days)
    suggestions = {"deprioritize": [], "healthy": [], "no_data": []}

    for name, stats in reliability.get("sources", {}).items():
        if stats["total_requests"] < 3:
            suggestions["no_data"].append(name)
        elif stats["success_rate"] < 50:
            suggestions["deprioritize"].append({
                "source": name,
                "success_rate": stats["success_rate"],
                "failures": stats["failures"],
            })
        else:
            suggestions["healthy"].append(name)

    return suggestions


def main():
    parser = argparse.ArgumentParser(
        description="Track source health over time for adaptive fallback chains."
    )
    parser.add_argument(
        "--log", action="store_true",
        help="Append today's session results to the health log"
    )
    parser.add_argument(
        "--report", action="store_true",
        help="Show reliability report for recent period"
    )
    parser.add_argument(
        "--suggest-fallbacks", action="store_true",
        help="Suggest sources to deprioritize"
    )
    parser.add_argument(
        "--days", type=int, default=7,
        help="Lookback period in days (default: 7)"
    )
    parser.add_argument(
        "--summary", type=Path,
        default=Path("betting/data/scan_summary.json"),
        help="Path to scan_summary.json"
    )
    parser.add_argument(
        "--errors", type=Path,
        default=Path("betting/data/scan_errors.json"),
        help="Path to scan_errors.json"
    )
    parser.add_argument(
        "--format", choices=["json", "text"], default="text",
        help="Output format"
    )
    args = parser.parse_args()

    if args.log:
        records = parse_scan_results(args.summary, args.errors)
        if records:
            append_to_log(records)
            print(f"Logged {len(records)} source health records.")
        else:
            print("No scan data to log.")

    elif args.report:
        report = get_source_reliability(args.days)
        if args.format == "json":
            # Convert sets to lists for JSON
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            print(f"═══ Source Health Report (last {args.days} days) ═══")
            if not report.get("sources"):
                print("  No data available.")
            else:
                for name, s in sorted(
                    report["sources"].items(),
                    key=lambda x: x[1]["success_rate"],
                ):
                    icon = "✓" if s["success_rate"] >= 80 else "⚠" if s["success_rate"] >= 50 else "✗"
                    print(
                        f"  {icon} {name}: {s['success_rate']}% success "
                        f"({s['success']}/{s['total_requests']}) | "
                        f"{s['events_total']} events | "
                        f"Sports: {', '.join(s['sports']) or 'N/A'}"
                    )

    elif args.suggest_fallbacks:
        suggestions = suggest_fallbacks(args.days)
        if args.format == "json":
            print(json.dumps(suggestions, indent=2, ensure_ascii=False))
        else:
            print(f"═══ Fallback Suggestions (last {args.days} days) ═══")
            if suggestions["deprioritize"]:
                print("\n⚠ DEPRIORITIZE (success <50%):")
                for s in suggestions["deprioritize"]:
                    print(f"  ✗ {s['source']}: {s['success_rate']}% ({s['failures']} failures)")
            if suggestions["healthy"]:
                print(f"\n✓ HEALTHY: {', '.join(suggestions['healthy'])}")
            if suggestions["no_data"]:
                print(f"\n? INSUFFICIENT DATA: {', '.join(suggestions['no_data'])}")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
