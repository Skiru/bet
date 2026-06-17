# ruff: noqa: E501
import argparse
import json
import os
import sqlite3
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
from bet.enrichment.football.persistence import CanonicalPersistence
from bet.enrichment.football.provider import LiveAPIFootballAcquirer
from bet.enrichment.football.repository import FootballHistoryRepository
from bet.enrichment.football.service import FootballHistoryService
from bet.enrichment.football.snapshot import SnapshotService
from bet.enrichment.football.sync import FootballSyncEngine
from bet.enrichment.football.time import parse_canonical_or_offset_datetime


class Clock:
    def now_utc(self):
        raise NotImplementedError()
    def today_utc(self):
        raise NotImplementedError()


class SystemClock(Clock):
    def now_utc(self):
        import datetime
        return datetime.datetime.now(datetime.UTC)
    def today_utc(self):
        import datetime
        return datetime.datetime.now(datetime.UTC).date()


class FrozenClock(Clock):
    def __init__(self, frozen_time):
        self.frozen_time = parse_canonical_or_offset_datetime(frozen_time)
    def now_utc(self):
        return self.frozen_time
    def today_utc(self):
        return self.frozen_time.date()


@dataclass
class RuntimeOverrides:
    wrap_request: Callable[..., Any] | None = None
    clock: Any | None = None
    evidence_root: str | Path | None = None


@dataclass
class Runtime:
    conn: sqlite3.Connection
    client: APIFootballClient
    acquirer: LiveAPIFootballAcquirer
    sync_engine: FootballSyncEngine
    persistence: CanonicalPersistence
    repository: FootballHistoryRepository
    feature_builder: FootballFeatureBuilder
    snapshot_service: SnapshotService
    service: FootballHistoryService
    clock: Any


def build_runtime(
    *,
    db_path: str,
    overrides: RuntimeOverrides | None = None,
) -> Runtime:
    if overrides and overrides.evidence_root:
        os.environ["BET_EVIDENCE_ROOT"] = str(overrides.evidence_root)

    if overrides and overrides.wrap_request:
        import bet.integration.telemetry_wrapper
        bet.integration.telemetry_wrapper.wrap_request = overrides.wrap_request

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    init_db(conn)

    rate_limiter = RateLimiter()
    if overrides:
        rate_limiter.can_request = lambda *args, **kwargs: True
        rate_limiter.record_request = lambda *args, **kwargs: None
    client = APIFootballClient(rate_limiter=rate_limiter)
    acquirer = LiveAPIFootballAcquirer(client)
    sync_engine = FootballSyncEngine(conn)
    persistence = CanonicalPersistence(conn)
    repository = FootballHistoryRepository(conn)
    feature_builder = FootballFeatureBuilder(
        metrics=["goals", "shots", "shots_on_target", "possession_pct", "fouls", "yellow_cards", "red_cards", "offsides", "corners", "goalkeeper_saves"]
    )
    snapshot_service = SnapshotService(conn)

    service = FootballHistoryService(conn, acquirer, sync_engine, repository, feature_builder)

    clock = (overrides.clock if overrides and overrides.clock else SystemClock())
    if hasattr(service, "clock"):
        service.clock = clock
    if hasattr(sync_engine, "clock"):
        sync_engine.clock = clock

    return Runtime(
        conn=conn,
        client=client,
        acquirer=acquirer,
        sync_engine=sync_engine,
        persistence=persistence,
        repository=repository,
        feature_builder=feature_builder,
        snapshot_service=snapshot_service,
        service=service,
        clock=clock,
    )


def run_cli(
    argv: Sequence[str],
    *,
    overrides: RuntimeOverrides | None = None,
) -> int:
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

    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 2

    try:
        runtime = build_runtime(db_path=args.db, overrides=overrides)
        conn = runtime.conn
        service = runtime.service
    except Exception as e:
        print(json.dumps({"status": "FAILED", "error": f"Database initialization failed: {e}"}))
        return 5

    try:
        if args.command == "bootstrap":
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
                return 3
            elif res.final_status == "RATE_LIMITED":
                return 4
            elif res.final_status in ("FAILED", "PLAN_RESTRICTED"):
                return 5
            return 0

        elif args.command == "incremental-sync":
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
                return 3
            elif res.final_status == "RATE_LIMITED":
                return 4
            elif res.final_status in ("FAILED", "PLAN_RESTRICTED"):
                return 5
            return 0

        elif args.command == "replay":
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
                return 5
            return 0

        elif args.command == "build-snapshot":
            cutoff = parse_canonical_or_offset_datetime(args.analysis_cutoff_at)
            cmd = BuildSnapshotCommand(
                canonical_target_fixture_id=args.canonical_target_fixture_id,
                analysis_cutoff_at=cutoff,
                policy_version=args.policy_version,
            )
            res = service.build_snapshot(cmd)
            conn.commit()

            out = {
                "run_id": res.run_id,
                "snapshot_id": res.snapshot_id,
                "snapshot_hash": res.snapshot_hash,
                "created_or_reused": res.created_or_reused,
                "deterministic_drift": res.deterministic_drift,
            }
            print(json.dumps(out, indent=2))
            return 0

        elif args.command == "inspect":
            if args.fixture_id:
                cmd = InspectCommand(fixture_id=args.fixture_id, team_id=None)
                res = service.inspect_fixture(cmd)
            elif args.team_id:
                cmd = InspectCommand(fixture_id=None, team_id=args.team_id)
                res = service.inspect_team(cmd)
            else:
                print(json.dumps({"status": "FAILED", "error": "Must provide --fixture-id or --team-id"}))
                return 2

            from dataclasses import asdict, is_dataclass

            def dataclass_to_dict_helper(obj):
                if is_dataclass(obj):
                    return {k: dataclass_to_dict_helper(v) for k, v in asdict(obj).items()}
                if isinstance(obj, dict):
                    return {k: dataclass_to_dict_helper(v) for k, v in obj.items()}
                if isinstance(obj, (list, tuple)):
                    return [dataclass_to_dict_helper(v) for v in obj]
                return obj

            out = dataclass_to_dict_helper(res)
            print(json.dumps(out, indent=2))

            if out.get("status") == "NOT_FOUND":
                return 2
            return 0

    except ValueError as e:
        err_msg = str(e)
        if "DETERMINISTIC_DRIFT" in err_msg:
            print(json.dumps({"status": "FAILED", "error": "DETERMINISTIC_DRIFT"}))
            return 5
        elif "not found in database" in err_msg or "NOT_FOUND" in err_msg:
            print(json.dumps({"status": "NOT_FOUND", "error": err_msg}))
            return 2
        else:
            print(json.dumps({"status": "FAILED", "error": err_msg}))
            return 5
    except Exception as e:
        print(json.dumps({"status": "FAILED", "error": str(e)}))
        return 5
    finally:
        if 'conn' in locals() and conn:
            try:
                conn.close()
            except Exception:
                pass


def main():
    sys.exit(run_cli(sys.argv[1:]))


if __name__ == "__main__":
    main()
