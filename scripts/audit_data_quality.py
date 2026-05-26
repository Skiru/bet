#!/usr/bin/env python3
"""Data quality audit for team_form enrichment data."""
import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bet.db.connection import get_db
from bet.stats.value_ranges import SPORT_VALUE_RANGES
from bet.stats.stat_validation import detect_contamination, VALID_STATS
from bet.stats.market_ranking import SPORT_STAT_KEYS


def audit_fake_l10(conn) -> dict[str, int]:
    query = """
    SELECT s.name as sport, COUNT(*) as cnt
    FROM team_form tf
    JOIN sports s ON tf.sport_id = s.id
    WHERE json_array_length(tf.l10_values) <= 1
    GROUP BY s.name
    """
    cursor = conn.execute(query)
    return {row["sport"]: row["cnt"] for row in cursor.fetchall()}


def audit_contamination(conn) -> tuple[dict[str, int], list[int]]:
    query = """
    SELECT tf.id, s.name as sport, tf.stat_key, t.name as team_name
    FROM team_form tf
    JOIN sports s ON tf.sport_id = s.id
    JOIN teams t ON tf.team_id = t.id
    """
    cursor = conn.execute(query)
    
    issues_by_sport = {}
    contaminated_ids = []
    
    for row in cursor.fetchall():
        sport = row["sport"]
        stat_key = row["stat_key"]
        
        # detect_contamination returns boolean True if contaminated/mismatch
        # We need to check if the stat_key fits the sport
        is_contam = False
        res = detect_contamination(sport, [stat_key])
        if res:
           is_contam = True
           
        if is_contam:
            issues_by_sport[sport] = issues_by_sport.get(sport, 0) + 1
            contaminated_ids.append(row["id"])
            
    return issues_by_sport, contaminated_ids


def audit_stale_data(conn) -> dict[str, int]:
    query = """
    SELECT s.name as sport, COUNT(DISTINCT tf.team_id) as stale_count
    FROM team_form tf
    JOIN sports s ON tf.sport_id = s.id
    JOIN fixtures f ON (f.home_team_id = tf.team_id OR f.away_team_id = tf.team_id)
    WHERE f.kickoff > datetime('now') AND f.kickoff < datetime('now', '+7 days')
      AND tf.updated_at < datetime('now', '-7 days')
    GROUP BY s.name
    """
    cursor = conn.execute(query)
    return {row["sport"]: row["stale_count"] for row in cursor.fetchall()}


def audit_source_concentration(conn) -> dict[str, dict]:
    query = """
    SELECT s.name as sport, tf.source, COUNT(*) as cnt
    FROM team_form tf
    JOIN sports s ON tf.sport_id = s.id
    GROUP BY s.name, tf.source
    """
    cursor = conn.execute(query)
    
    results = {}
    for row in cursor.fetchall():
        sport = row["sport"]
        source = row["source"]
        cnt = row["cnt"]
        if sport not in results:
            results[sport] = {"total": 0, "sources": {}}
        results[sport]["total"] += cnt
        results[sport]["sources"][source] = cnt
        
    concentration_by_sport = {}
    for sport, data in results.items():
        total = data["total"]
        max_source_cnt = max(data["sources"].values())
        percentage = (max_source_cnt / total) * 100 if total > 0 else 0
        concentration_by_sport[sport] = percentage
        
    return concentration_by_sport


def audit_coverage(conn) -> dict[str, dict]:
    query_fixtures = """
    SELECT s.name, COUNT(DISTINCT t.id) as teams_with_fixtures
    FROM fixtures f
    JOIN sports s ON f.sport_id = s.id
    JOIN teams t ON (t.id = f.home_team_id OR t.id = f.away_team_id)
    WHERE f.kickoff > datetime('now') AND f.kickoff < datetime('now', '+7 days')
    GROUP BY s.name
    """
    cursor = conn.execute(query_fixtures)
    fixtures_by_sport = {row["name"]: row["teams_with_fixtures"] for row in cursor.fetchall()}
    
    query_data = """
    SELECT s.name, COUNT(DISTINCT tf.team_id) as teams_with_data
    FROM team_form tf
    JOIN sports s ON tf.sport_id = s.id
    GROUP BY s.name
    """
    cursor = conn.execute(query_data)
    data_by_sport = {row["name"]: row["teams_with_data"] for row in cursor.fetchall()}
    
    all_sports = set(fixtures_by_sport.keys()) | set(data_by_sport.keys())
    
    coverage_by_sport = {}
    for sport in all_sports:
        teams_with_fixtures = fixtures_by_sport.get(sport, 0)
        teams_with_data = data_by_sport.get(sport, 0)
        perc = (teams_with_data / teams_with_fixtures * 100) if teams_with_fixtures > 0 else 100.0
        if teams_with_fixtures == 0 and teams_with_data == 0:
            perc = 0.0
        coverage_by_sport[sport] = {
            "teams": teams_with_fixtures, 
            "teams_with_data": teams_with_data, 
            "coverage": perc
        }
    return coverage_by_sport


def audit_value_ranges(conn) -> dict[str, int]:
    query = """
    SELECT s.name as sport, tf.stat_key, tf.l10_values
    FROM team_form tf
    JOIN sports s ON tf.sport_id = s.id
    """
    cursor = conn.execute(query)
    violations_by_sport = {}
    
    for row in cursor.fetchall():
        sport = row["sport"]
        stat_key = row["stat_key"]
        
        try:
            l10_values = json.loads(row["l10_values"])
        except (ValueError, TypeError):
            continue
            
        ranges = SPORT_VALUE_RANGES.get(sport, {})
        allowed_range = ranges.get(stat_key)
        
        has_violation = False
        if allowed_range and isinstance(l10_values, list):
            min_val, max_val = allowed_range
            for val in l10_values:
                if val is not None and (val < min_val or val > max_val):
                    has_violation = True
                    break
                    
        if has_violation:
            violations_by_sport[sport] = violations_by_sport.get(sport, 0) + 1
            
    return violations_by_sport


def get_health_status(fake_cnt, contam_cnt, stale_cnt, coverage) -> str:
    if contam_cnt > 0 or fake_cnt > 300 or (fake_cnt > 0 and fake_cnt >= coverage.get('teams_with_data', 0) * 0.5):
        return "CRITICAL"
    if coverage.get('coverage', 0) < 50 or fake_cnt > 0 or stale_cnt > 0:
        return "WARNING"
    return "GOOD"
    

def main():
    parser = argparse.ArgumentParser(description="Data Quality Audit")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--fix", action="store_true", help="Delete contaminated entries")
    args = parser.parse_args()

    with get_db() as conn:
        conn.row_factory = __import__('sqlite3').Row
        
        fake_l10 = audit_fake_l10(conn)
        contamination, contaminated_ids = audit_contamination(conn)
        stale_data = audit_stale_data(conn)
        source_concentration = audit_source_concentration(conn)
        coverage = audit_coverage(conn)
        value_violations = audit_value_ranges(conn)
    
    all_sports = set()
    for d in (fake_l10, contamination, stale_data, source_concentration, coverage, value_violations):
        all_sports.update(d.keys())
        
    print("═══════════════════════════════════════════")
    print("  DATA QUALITY AUDIT REPORT")
    print("═══════════════════════════════════════════")
    print()
    print(f"{'SPORT':<14} {'TEAMS':<7} {'COVERAGE':<9} {'FAKE_L10':<9} {'CONTAMINATED':<13} {'STALE':<6} {'HEALTH'}")
    print("────────────────────────────────────────────────────────────────────")
    
    agent_summary = {
        "overall_health": "GOOD",
        "sports": {},
        "total_issues": 0
    }
    
    total_issues = 0
    issues_messages = []
    
    for sport in sorted(all_sports):
        cov_data = coverage.get(sport, {"teams": 0, "teams_with_data": 0, "coverage": 0})
        teams_cnt = cov_data["teams"]
        cov_perc = cov_data["coverage"]
        fake_cnt = fake_l10.get(sport, 0)
        contam_cnt = contamination.get(sport, 0)
        stale_cnt = stale_data.get(sport, 0)
        viol_cnt = value_violations.get(sport, 0)
        conc_perc = source_concentration.get(sport, 0)
        
        health = get_health_status(fake_cnt, contam_cnt, stale_cnt, cov_data)
        if health == "CRITICAL":
            agent_summary["overall_health"] = "CRITICAL"
        elif health == "WARNING" and agent_summary["overall_health"] == "GOOD":
            agent_summary["overall_health"] = "WARNING"
            
        print(f"{sport:<14} {teams_cnt:<7} {int(cov_perc):>2}% {' ' * 5} {fake_cnt:<9} {contam_cnt:<13} {stale_cnt:<6} {health}")
        
        sport_summary = {
            "coverage": int(cov_perc),
            "fake_l10": fake_cnt,
            "contaminated": contam_cnt,
            "stale": stale_cnt,
            "value_range_violations": viol_cnt,
            "health": health
        }
        
        agent_summary["sports"][sport] = sport_summary
        
        if health == "CRITICAL" or health == "WARNING":
            if contam_cnt > 0:
                issues_messages.append(f"  [{health}] {sport}: {contam_cnt} contaminated entries")
                total_issues += contam_cnt
            if fake_cnt > 0:
                issues_messages.append(f"  [{health}] {sport}: {fake_cnt} fake L10 entries (n<=1 arrays)")
                total_issues += fake_cnt
            if stale_cnt > 0:
                issues_messages.append(f"  [{health}] {sport}: {stale_cnt} stale entries")
                total_issues += stale_cnt
            if viol_cnt > 0:
                issues_messages.append(f"  [{health}] {sport}: {viol_cnt} value range violations")
                total_issues += viol_cnt
            if conc_perc > 90:
                issues_messages.append(f"  [{health}] {sport}: source concentration >90% ({int(conc_perc)}%)")
                total_issues += 1
                sport_summary["source_concentration"] = int(conc_perc)

    agent_summary["total_issues"] = total_issues

    if issues_messages:
        print("\nISSUES FOUND:")
        for msg in issues_messages:
            print(msg)
            
    print(f"\nAGENT_SUMMARY:{json.dumps(agent_summary, separators=(',', ':'))}")
    
    if args.fix and contaminated_ids:
        ans = input(f"\nFound {len(contaminated_ids)} contaminated entries. Delete them? (y/N): ")
        if ans.lower() == 'y':
            with get_db() as conn:
                placeholder = ','.join(['?']*len(contaminated_ids))
                conn.execute(f"DELETE FROM team_form WHERE id IN ({placeholder})", contaminated_ids)
                conn.commit()
            print("Deleted contaminated entries.")

if __name__ == "__main__":
    main()