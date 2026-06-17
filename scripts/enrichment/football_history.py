import argparse
import json
import sqlite3
import sys

from bet.api_clients.api_football import APIFootballClient
from bet.api_clients.rate_limiter import RateLimiter
from bet.enrichment.football.features import FootballFeatureBuilder
from bet.enrichment.football.provider import APIFootballOrchestrator
from bet.enrichment.football.repository import FootballHistoryRepository
from bet.enrichment.football.service import FootballHistoryService
from bet.enrichment.football.sync import FootballSyncEngine


def main():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")

    bootstrap_parser = subparsers.add_parser("bootstrap")
    bootstrap_parser.add_argument("--db", required=True)
    bootstrap_parser.add_argument("--competition-id", required=True)
    bootstrap_parser.add_argument("--season", type=int, required=True)
    bootstrap_parser.add_argument("--from", dest="from_date", required=True)
    bootstrap_parser.add_argument("--to", dest="to_date", required=True)
    bootstrap_parser.add_argument("--max-fixtures", type=int, default=100)
    bootstrap_parser.add_argument("--max-http-attempts", type=int, default=100)
    bootstrap_parser.add_argument("--max-fallback-stats-calls", type=int, default=100)

    inc_parser = subparsers.add_parser("incremental-sync")
    inc_parser.add_argument("--db", required=True)
    inc_parser.add_argument("--competition-id", required=True)
    inc_parser.add_argument("--season", type=int, required=True)
    inc_parser.add_argument("--correction-lookback-days", type=int, default=3)
    inc_parser.add_argument("--max-fixtures", type=int, default=100)
    inc_parser.add_argument("--max-http-attempts", type=int, default=100)
    inc_parser.add_argument("--daily-quota-reserve", type=int, default=5)
    inc_parser.add_argument("--minute-quota-reserve", type=int, default=1)

    replay_parser = subparsers.add_parser("replay")
    replay_parser.add_argument("--db", required=True)
    replay_parser.add_argument("--evidence-bundle", action="append", required=True)

    snap_parser = subparsers.add_parser("build-snapshot")
    snap_parser.add_argument("--db", required=True)
    snap_parser.add_argument("--canonical-target-fixture-id", type=int, required=True)
    snap_parser.add_argument("--analysis-cutoff-at", required=True)
    snap_parser.add_argument("--policy-version", required=True)

    inspect_parser = subparsers.add_parser("inspect")
    inspect_parser.add_argument("--db", required=True)
    inspect_parser.add_argument("--fixture-id", type=int)
    inspect_parser.add_argument("--team-id", type=int)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    conn = sqlite3.connect(args.db)
    # Enable WAL and foreign keys
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")

    rate_limiter = RateLimiter()
    client = APIFootballClient(rate_limiter=rate_limiter)
    orchestrator = APIFootballOrchestrator(client)
    sync_engine = FootballSyncEngine(conn)
    repository = FootballHistoryRepository(conn)
    feature_builder = FootballFeatureBuilder(
        metrics=["shots", "shots_on_target", "possession_pct", "fouls", "yellow_cards", "red_cards", "offsides", "corners", "goalkeeper_saves"]
    )

    service = FootballHistoryService(conn, orchestrator, sync_engine, repository, feature_builder)

    try:
        if args.command == "bootstrap":
            res = service.bootstrap(
                args.competition_id, args.season, args.from_date, args.to_date,
                args.max_fixtures, args.max_http_attempts, args.max_fallback_stats_calls
            )
            print(json.dumps(res, indent=2))
            if res.get("status") in ("BLOCKED", "FAILED", "RATE_LIMITED"):
                sys.exit(1)
        elif args.command == "incremental-sync":
            res = service.incremental_sync(
                args.competition_id, args.season, args.correction_lookback_days,
                args.max_fixtures, args.max_http_attempts, args.daily_quota_reserve, args.minute_quota_reserve
            )
            print(json.dumps(res, indent=2))
            if res.get("status") in ("BLOCKED", "FAILED", "RATE_LIMITED"):
                sys.exit(1)
        elif args.command == "replay":
            res = service.replay(args.evidence_bundle)
            print(json.dumps(res, indent=2))
            if res.get("status") != "COMPLETE":
                sys.exit(1)
        elif args.command == "build-snapshot":
            res = service.build_snapshot(
                args.canonical_target_fixture_id, args.analysis_cutoff_at, args.policy_version
            )
            print(json.dumps(res, indent=2))
            if res.get("status") != "COMPLETE":
                sys.exit(1)
        elif args.command == "inspect":
            res = service.inspect(args.fixture_id, args.team_id)
            print(json.dumps(res, indent=2))
    except Exception as e:
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        conn.close()

if __name__ == "__main__":
    main()
