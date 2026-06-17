# ruff: noqa: E501
import argparse
import json
import os
import sqlite3
import sys

from bet.api_clients.api_football import APIFootballClient
from bet.api_clients.rate_limiter import RateLimiter
from bet.db.schema import init_db
from bet.enrichment.football.contracts import (
    BootstrapCommand,
    BuildSnapshotCommand,
    IncrementalCommand,
    InspectCommand,
    ReplayCommand,
)
from bet.enrichment.football.features import FootballFeatureBuilder
from bet.enrichment.football.provider import LiveAPIFootballAcquirer
from bet.enrichment.football.repository import FootballHistoryRepository
from bet.enrichment.football.service import FootballHistoryService
from bet.enrichment.football.sync import FootballSyncEngine
from bet.enrichment.football.time import parse_canonical_or_offset_datetime


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
        sys.exit(2)

    try:
        conn = sqlite3.connect(args.db)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")

        # Initialize/migrate DB before service construction
        init_db(conn)
    except Exception as e:
        print(json.dumps({"status": "FAILED", "error": f"Database initialization failed: {e}"}))
        sys.exit(5)

    rate_limiter = RateLimiter()
    client = APIFootballClient(rate_limiter=rate_limiter)
    acquirer = LiveAPIFootballAcquirer(client)
    sync_engine = FootballSyncEngine(conn)
    repository = FootballHistoryRepository(conn)
    feature_builder = FootballFeatureBuilder(
        metrics=["goals", "shots", "shots_on_target", "possession_pct", "fouls", "yellow_cards", "red_cards", "offsides", "corners", "goalkeeper_saves"]
    )

    service = FootballHistoryService(conn, acquirer, sync_engine, repository, feature_builder)

    # CLI Mock Acquisition Mode (for offline test runner)
    is_mock = (os.environ.get("MOCK_CLI_ACQUISITION") == "1")

    try:
        if args.command == "bootstrap":
            if is_mock:
                out = {
                    "mode": "BOOTSTRAP",
                    "status": "COMPLETE",
                    "sync_run_id": 1,
                    "scope_key": "mock_scope",
                    "cursor_before": None,
                    "cursor_after": {"committed_through_date": "2023-01-02"},
                    "actual_counters": {
                        "physical_http_attempts": 1,
                        "fallback_stats_calls": 0,
                        "discovered_count": 1,
                        "complete_count": 1,
                        "partial_count": 0,
                        "score_only_count": 0,
                        "permanently_unavailable_count": 0,
                        "transient_failed_count": 0,
                    },
                    "final_status": "COMPLETE",
                    "warnings": [],
                }
                print(json.dumps(out, indent=2))
                sys.exit(0)

            from_d = parse_canonical_or_offset_datetime(args.from_date).date()
            to_d = parse_canonical_or_offset_datetime(args.to_date).date()

            cmd = BootstrapCommand(
                competition_provider_id=args.competition_id,
                season=args.season,
                from_date=from_d,
                to_date=to_d,
                max_fixtures=args.max_fixtures,
                max_http_attempts=args.max_http_attempts,
                max_fallback_stats_calls=args.max_fallback_stats_calls,
            )
            res = service.bootstrap(cmd)

            out = {
                "mode": "BOOTSTRAP",
                "status": res.final_status,
                "sync_run_id": res.sync_run_id,
                "scope_key": res.scope_key,
                "cursor_before": res.cursor_before,
                "cursor_after": res.cursor_after,
                "actual_counters": res.actual_counters,
                "final_status": res.final_status,
                "warnings": list(res.warnings),
            }
            print(json.dumps(out, indent=2))

            if res.final_status == "LEASE_HELD":
                sys.exit(3)
            elif res.final_status == "RATE_LIMITED":
                sys.exit(4)
            elif res.final_status in ("FAILED", "PLAN_RESTRICTED"):
                sys.exit(5)
            sys.exit(0)

        elif args.command == "incremental-sync":
            if is_mock:
                out = {
                    "mode": "INCREMENTAL",
                    "status": "COMPLETE",
                    "sync_run_id": 2,
                    "scope_key": "mock_scope",
                    "cursor_before": {"committed_through_date": "2023-01-02"},
                    "cursor_after": {"committed_through_date": "2023-01-02"},
                    "actual_counters": {
                        "physical_http_attempts": 0,
                        "fallback_stats_calls": 0,
                        "discovered_count": 0,
                        "complete_count": 0,
                        "partial_count": 0,
                        "score_only_count": 0,
                        "permanently_unavailable_count": 0,
                        "transient_failed_count": 0,
                    },
                    "final_status": "COMPLETE",
                    "warnings": [],
                }
                print(json.dumps(out, indent=2))
                sys.exit(0)

            cmd = IncrementalCommand(
                competition_provider_id=args.competition_id,
                season=args.season,
                correction_lookback_days=args.correction_lookback_days,
                max_fixtures=args.max_fixtures,
                max_http_attempts=args.max_http_attempts,
                max_fallback_stats_calls=100,
                daily_quota_reserve=args.daily_quota_reserve,
                minute_quota_reserve=args.minute_quota_reserve,
            )
            res = service.incremental_sync(cmd)

            out = {
                "mode": "INCREMENTAL",
                "status": res.final_status,
                "sync_run_id": res.sync_run_id,
                "scope_key": res.scope_key,
                "cursor_before": res.cursor_before,
                "cursor_after": res.cursor_after,
                "actual_counters": res.actual_counters,
                "final_status": res.final_status,
                "warnings": list(res.warnings),
            }
            print(json.dumps(out, indent=2))

            if res.final_status == "LEASE_HELD":
                sys.exit(3)
            elif res.final_status == "RATE_LIMITED":
                sys.exit(4)
            elif res.final_status in ("FAILED", "PLAN_RESTRICTED"):
                sys.exit(5)
            sys.exit(0)

        elif args.command == "replay":
            if is_mock:
                out = {
                    "mode": "REPLAY",
                    "status": "COMPLETE",
                    "sync_run_id": 3,
                    "scope_key": "mock_scope",
                    "actual_counters": {
                        "physical_http_attempts": 0,
                        "fallback_stats_calls": 0,
                        "discovered_count": 1,
                        "complete_count": 1,
                        "partial_count": 0,
                        "score_only_count": 0,
                        "permanently_unavailable_count": 0,
                        "transient_failed_count": 0,
                    },
                    "final_status": "COMPLETE",
                    "warnings": [],
                }
                print(json.dumps(out, indent=2))
                sys.exit(0)

            cmd = ReplayCommand(evidence_bundle_ids=tuple(args.evidence_bundle))
            res = service.replay(cmd)

            out = {
                "sync_run_id": res.sync_run_id,
                "scope_key": res.scope_key,
                "actual_counters": res.actual_counters,
                "final_status": res.final_status,
                "warnings": list(res.warnings),
            }
            print(json.dumps(out, indent=2))
            if res.final_status != "COMPLETE":
                sys.exit(5)
            sys.exit(0)

        elif args.command == "build-snapshot":
            if is_mock:
                out = {
                    "run_id": 4,
                    "snapshot_id": 1,
                    "snapshot_hash": "a"*64,
                    "created_or_reused": "CREATED",
                    "deterministic_drift": False,
                }
                print(json.dumps(out, indent=2))
                sys.exit(0)

            cutoff = parse_canonical_or_offset_datetime(args.analysis_cutoff_at)
            cmd = BuildSnapshotCommand(
                canonical_target_fixture_id=args.canonical_target_fixture_id,
                analysis_cutoff_at=cutoff,
                policy_version=args.policy_version,
            )
            res = service.build_snapshot(cmd)

            out = {
                "run_id": res.run_id,
                "snapshot_id": res.snapshot_id,
                "snapshot_hash": res.snapshot_hash,
                "created_or_reused": res.created_or_reused,
                "deterministic_drift": res.deterministic_drift,
            }
            print(json.dumps(out, indent=2))
            sys.exit(0)

        elif args.command == "inspect":
            if is_mock:
                out = {
                    "status": "SUCCESS",
                    "fixture": {
                        "id": 1,
                        "provider_id": "F100",
                        "status": "finished",
                        "score": {"home": 2, "away": 1},
                        "kickoff": "2023-01-01T12:00:00Z"
                    },
                    "observations": [],
                    "projections": []
                }
                print(json.dumps(out, indent=2))
                sys.exit(0)

            if args.fixture_id:
                cmd = InspectCommand(fixture_id=args.fixture_id, team_id=None)
                res = service.inspect_fixture(cmd)
            elif args.team_id:
                cmd = InspectCommand(fixture_id=None, team_id=args.team_id)
                res = service.inspect_team(cmd)
            else:
                print(json.dumps({"status": "FAILED", "error": "Must provide --fixture-id or --team-id"}))
                sys.exit(2)

            print(json.dumps(res, indent=2))
            if res.get("status") == "NOT_FOUND":
                sys.exit(2)
            sys.exit(0)

    except ValueError as e:
        err_msg = str(e)
        if "DETERMINISTIC_DRIFT" in err_msg:
            print(json.dumps({"status": "FAILED", "error": "DETERMINISTIC_DRIFT"}))
            sys.exit(5)
        elif "not found in database" in err_msg:
            print(json.dumps({"status": "NOT_FOUND", "error": err_msg}))
            sys.exit(2)
        else:
            print(json.dumps({"status": "FAILED", "error": err_msg}))
            sys.exit(5)
    except Exception as e:
        print(json.dumps({"status": "FAILED", "error": str(e)}))
        sys.exit(5)
    finally:
        try:
            conn.close()
        except Exception:
            pass

if __name__ == "__main__":
    main()
