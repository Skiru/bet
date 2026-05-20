#!/usr/bin/env python3
"""No-write probe for rich-stat coverage.

This script inspects recent finished fixtures for a sport, classifies coverage
into rich/baseline_only/partial/no_data, and never writes to the DB or cache.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from bet.db.connection import get_db
from bet.stats.fallback_chains import RICH_COMPLETION_POLICY
from bet.stats.rich_coverage import classify_rich_coverage, resolve_fixture_team_scope, summarize_rich_coverage


def _get_sport_id(sport: str) -> int | None:
    with get_db() as conn:
        row = conn.execute("SELECT id FROM sports WHERE name = ?", (sport,)).fetchone()
        return row[0] if row else None


def _get_teams_for_date(sport: str, betting_date: str) -> list[tuple[int, str]]:
    sport_id = _get_sport_id(sport)
    if not sport_id:
        return []
    with get_db() as conn:
        return conn.execute(
            "SELECT DISTINCT t.id, t.name FROM fixtures f "
            "JOIN teams t ON t.id IN (f.home_team_id, f.away_team_id) "
            "WHERE date(f.kickoff) = ? AND f.sport_id = ? ORDER BY t.name",
            (betting_date, sport_id),
        ).fetchall()


def probe_rich_coverage(sport: str, betting_date: str, limit: int = 10) -> dict:
    policy = RICH_COMPLETION_POLICY.get(sport)
    if not policy:
        return {"sport": sport, "status": "unsupported_sport", "error": f"No rich policy for {sport}"}

    required_keys = list(policy["required_rich_keys"])
    allowed_sources = {policy["canonical_source"], *policy["supporting_sources"]}
    baseline_sources = set(policy.get("baseline_sources", []))
    source_presence = Counter()
    failure_reasons = Counter()
    team_details = []
    teams = _get_teams_for_date(sport, betting_date)[:limit]
    scope = {
        "teams": teams,
        "scope_date": betting_date,
        "used_fallback": False,
    }

    sport_id = _get_sport_id(sport)
    if sport_id is None:
        return {"sport": sport, "status": "failed", "error": f"Sport not found: {sport}"}

    with get_db() as conn:
        if not teams:
            scope = resolve_fixture_team_scope(conn, sport_id, betting_date, limit=limit)
            teams = scope["teams"]
        for team_id, team_name in teams:
            rows = conn.execute(
                "SELECT stat_key, source FROM team_form WHERE team_id = ? AND sport_id = ?",
                (team_id, sport_id),
            ).fetchall()
            detail = classify_rich_coverage(
                rows,
                required_keys,
                allowed_sources,
                baseline_sources=baseline_sources,
            )
            detail["team"] = team_name
            detail["team_id"] = team_id
            team_details.append(detail)
            for source in detail["sources"]:
                if source:
                    source_presence[source] += 1

            if detail["bucket"] != "rich" and detail["missing_rich_keys"]:
                failure_reasons[", ".join(detail["missing_rich_keys"][:3])] += 1

    summary = summarize_rich_coverage(team_details)
    return {
        "sport": sport,
        "date": betting_date,
        "scope_date": scope["scope_date"],
        "used_fallback": scope["used_fallback"],
        "source_choice": policy["canonical_source"],
        "fixtures_scanned": summary["total"],
        "eligible": summary["eligible"],
        "rich": summary["rich"],
        "baseline_only": summary["baseline_only"],
        "partial": summary["partial"],
        "no_data": summary["no_data"],
        "completion_rate": summary["completion_rate"],
        "source_presence": dict(source_presence),
        "failure_reasons": dict(failure_reasons),
        "required_rich_keys": required_keys,
        "team_details": summary["team_details"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe rich-stat coverage without writing data")
    parser.add_argument("--date", default=str(date.today()), help="Betting date (YYYY-MM-DD)")
    parser.add_argument("--sport", required=True, choices=sorted(RICH_COMPLETION_POLICY.keys()))
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    result = probe_rich_coverage(args.sport, args.date, limit=args.limit)
    if args.verbose:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(
            f"{result['sport']} {result['date']}: source={result['source_choice']} "
            f"scope={result['scope_date']} fallback={str(result['used_fallback']).lower()} "
            f"fixtures={result['fixtures_scanned']} eligible={result['eligible']} rich={result['rich']} "
            f"baseline_only={result['baseline_only']} partial={result['partial']} no_data={result['no_data']} "
            f"completion={result['completion_rate']}%"
        )


if __name__ == "__main__":
    main()