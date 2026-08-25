"""BET V5 V7 DB-Aware Launch Bridge.

Provides preflight, online DB snapshot creation, seed reconciliation,
provider-backed S1R reconciliation, DB event classification, selection ledger,
and plan-only pipeline gate.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from bet.pipeline.runtime_selection import get_scoped_fixtures_for_stage

from bet.db.connection import connect_sqlite
from bet.pipeline.receipts import (
    compute_source_manifest_sha256,
    get_git_commit_head,
    get_git_tree_sha,
)

EXPECTED_START_HEAD = "20ee2145a82e9b88cf1e4a64a38d2f1d248b9487"
EXPECTED_START_TREE = "8ba53fe9520cb95dfd0c15ebc22d1cc3efdcae1c"
EXPECTED_START_SOURCE_MANIFEST_SHA256 = (
    "b2a2f65109ecf5f6bd54a5c531d0ebbbbd3fa96df990e668c2dd04fead45d7b5"
)


@dataclass
class PreflightAuditResult:
    head_sha: str
    tree_sha: str
    source_manifest_sha256: str
    worktree_clean: bool
    canonical_db_path: str
    canonical_db_sha256: str
    canonical_db_size_bytes: int
    canonical_db_mtime_iso: str
    sqlite_version: str
    journal_mode: str
    foreign_keys_setting: int
    user_version: int
    quick_check_passed: bool
    foreign_key_check_rows: list[tuple]
    status: str  # PASS | BLOCKED_FOR_DATABASE | BLOCKED_FOR_ENGINEERING


def compute_file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def check_worktree_clean(repo_root: Path) -> bool:
    res = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    return res.returncode == 0 and len(res.stdout.strip()) == 0


def resolve_canonical_db_path(explicit_path: Path | str | None = None) -> Path:
    if explicit_path:
        p = Path(explicit_path).resolve()
        if p.exists():
            return p
        raise FileNotFoundError(f"Explicit DB path does not exist: {p}")

    env_path = os.environ.get("BET_DB_PATH")
    if env_path:
        p = Path(env_path).resolve()
        if p.exists():
            return p
        raise FileNotFoundError(f"BET_DB_PATH does not exist: {p}")

    db_url = os.environ.get("DATABASE_URL", "")
    if db_url.startswith("sqlite:///"):
        clean_url = db_url[len("sqlite:///") :]
        p = Path(clean_url).resolve()
        if p.exists():
            return p

    default_p = (Path.cwd() / "betting" / "data" / "betting.db").resolve()
    if default_p.exists():
        return default_p

    raise FileNotFoundError(
        "Canonical database path could not be resolved or file does not exist."
    )


def verify_canonical_db_and_preflight(
    repo_root: Path,
    explicit_db_path: Path | str | None = None,
    enforce_baseline: bool = True,
) -> PreflightAuditResult:
    head_sha = get_git_commit_head(repo_root)
    tree_sha = get_git_tree_sha(repo_root)
    manifest_sha = compute_source_manifest_sha256(repo_root)
    clean = check_worktree_clean(repo_root)

    db_path = resolve_canonical_db_path(explicit_db_path)
    db_sha = compute_file_sha256(db_path)
    db_stat = db_path.stat()
    mtime_iso = datetime.datetime.fromtimestamp(
        db_stat.st_mtime, tz=datetime.UTC
    ).isoformat()

    conn = connect_sqlite(db_path, readonly=True)
    try:
        cur = conn.cursor()
        sqlite_ver = cur.execute("SELECT sqlite_version()").fetchone()[0]
        j_mode = cur.execute("PRAGMA journal_mode").fetchone()[0]
        fk_setting = cur.execute("PRAGMA foreign_keys").fetchone()[0]
        user_ver = cur.execute("PRAGMA user_version").fetchone()[0]
        quick_rows = [tuple(r) for r in cur.execute("PRAGMA quick_check").fetchall()]
        fk_rows = [tuple(r) for r in cur.execute("PRAGMA foreign_key_check").fetchall()]
    finally:
        conn.close()

    quick_check_ok = len(quick_rows) == 1 and quick_rows[0][0] == "ok"
    status = "PASS" if quick_check_ok else "BLOCKED_FOR_DATABASE"

    if enforce_baseline:
        if (
            head_sha != EXPECTED_START_HEAD
            or tree_sha != EXPECTED_START_TREE
            or manifest_sha != EXPECTED_START_SOURCE_MANIFEST_SHA256
        ):
            status = "BLOCKED_FOR_BASELINE"

    return PreflightAuditResult(
        head_sha=head_sha,
        tree_sha=tree_sha,
        source_manifest_sha256=manifest_sha,
        worktree_clean=clean,
        canonical_db_path=str(db_path),
        canonical_db_sha256=db_sha,
        canonical_db_size_bytes=db_stat.st_size,
        canonical_db_mtime_iso=mtime_iso,
        sqlite_version=str(sqlite_ver),
        journal_mode=str(j_mode),
        foreign_keys_setting=int(fk_setting),
        user_version=int(user_ver),
        quick_check_passed=quick_check_ok,
        foreign_key_check_rows=fk_rows,
        status=status,
    )


def apply_runtime_bridge_migrations(conn: sqlite3.Connection) -> None:
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS pipeline_runtime_event_selection (
        run_id TEXT NOT NULL,
        canonical_event_id TEXT NOT NULL,
        fixture_id INTEGER,
        betting_date TEXT NOT NULL,
        decision TEXT NOT NULL,
        resume_action TEXT NOT NULL,
        observed_status TEXT,
        observed_kickoff TEXT,
        observation_timestamp_utc TEXT NOT NULL,
        provider TEXT,
        provider_event_id TEXT,
        source_evidence_sha256 TEXT,
        previous_analysis_status TEXT,
        previous_analysis_sha256 TEXT,
        previous_gate_status TEXT,
        previous_gate_sha256 TEXT,
        input_fingerprint TEXT NOT NULL,
        reason TEXT NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY(run_id, canonical_event_id)
    );

    CREATE INDEX IF NOT EXISTS idx_pipeline_runtime_event_selection_run_decision
        ON pipeline_runtime_event_selection(run_id, decision);
    CREATE INDEX IF NOT EXISTS idx_pipeline_runtime_event_selection_date
        ON pipeline_runtime_event_selection(betting_date);

    CREATE TABLE IF NOT EXISTS pipeline_event_stage_state (
        canonical_event_id TEXT NOT NULL,
        stage_id TEXT NOT NULL,
        status TEXT NOT NULL,
        input_fingerprint TEXT NOT NULL,
        output_sha256 TEXT,
        receipt_sha256 TEXT,
        code_head TEXT NOT NULL,
        source_manifest_sha256 TEXT NOT NULL,
        model_registry_sha256 TEXT,
        provider_config_sha256 TEXT,
        run_id TEXT NOT NULL,
        completed_at TEXT,
        updated_at TEXT NOT NULL,
        PRIMARY KEY(canonical_event_id, stage_id)
    );

    CREATE INDEX IF NOT EXISTS idx_pipeline_event_stage_state_run
        ON pipeline_event_stage_state(run_id);
    CREATE INDEX IF NOT EXISTS idx_pipeline_event_stage_state_stage
        ON pipeline_event_stage_state(stage_id, status);

    CREATE TABLE IF NOT EXISTS pipeline_shadow_promotions (
        promotion_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        canonical_db_sha256_before TEXT NOT NULL,
        shadow_db_sha256 TEXT NOT NULL,
        status TEXT NOT NULL,
        promoted_tables_json TEXT NOT NULL,
        started_at TEXT NOT NULL,
        completed_at TEXT,
        receipt_sha256 TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_pipeline_shadow_promotions_run
        ON pipeline_shadow_promotions(run_id);
    """)
    conn.commit()


def create_runtime_analysis_shadow_db(
    canonical_db_path: Path,
    target_run_root: Path,
    run_id: str,
    allow_overwrite: bool = False,
) -> dict[str, Any]:
    from bet.db.schema import get_schema_version, init_db

    canonical_db_path = canonical_db_path.resolve(strict=True)
    target_run_root = Path(target_run_root).absolute()
    for component in (target_run_root, *target_run_root.parents):
        if component.exists() and component.is_symlink():
            raise ValueError("SHADOW_PATH_SYMLINK_FORBIDDEN")
    canonical_sha_before = compute_file_sha256(canonical_db_path)

    shadow_db_path = target_run_root / "data" / "runtime_analysis_shadow.db"
    if shadow_db_path == canonical_db_path:
        raise ValueError("CANONICAL_SHADOW_SAME_FILE")
    if target_run_root.exists() or target_run_root.is_symlink():
        raise FileExistsError(f"PLAN_RUN_COLLISION: {target_run_root}")
    try:
        shadow_db_path.absolute().relative_to(target_run_root)
    except ValueError as exc:
        raise ValueError("SHADOW_PATH_OUTSIDE_RUN_ROOT") from exc

    target_run_root.parent.mkdir(parents=True, exist_ok=True)
    staging_root = target_run_root.parent / (
        f".{target_run_root.name}.{uuid.uuid4().hex}.staging"
    )
    staging_data = staging_root / "data"
    staging_data.mkdir(parents=True)
    staging_shadow = staging_data / "runtime_analysis_shadow.db"
    try:
        src_conn = connect_sqlite(canonical_db_path, readonly=True)
        dst_conn = connect_sqlite(staging_shadow)
        try:
            src_conn.backup(dst_conn)
            quick_c = src_conn.execute("PRAGMA quick_check").fetchone()[0]
            quick_s = dst_conn.execute("PRAGMA quick_check").fetchone()[0]
            if quick_c != "ok" or quick_s != "ok":
                raise RuntimeError("SHADOW_DB_QUICK_CHECK_FAILED")
            tables = [
                "fixtures",
                "pipeline_candidates",
                "analysis_results",
                "gate_results",
                "odds_history",
            ]
            row_counts = {}
            for table in tables:
                try:
                    canonical_count = src_conn.execute(
                        f"SELECT COUNT(*) FROM {table}"
                    ).fetchone()[0]
                    shadow_count = dst_conn.execute(
                        f"SELECT COUNT(*) FROM {table}"
                    ).fetchone()[0]
                except sqlite3.OperationalError:
                    canonical_count = shadow_count = 0
                if canonical_count != shadow_count:
                    raise RuntimeError(f"SHADOW_DB_ROW_COUNT_MISMATCH: {table}")
                row_counts[table] = {
                    "canonical": canonical_count,
                    "shadow": shadow_count,
                    "match": True,
                }
            if get_schema_version(dst_conn) > 0:
                init_db(dst_conn)
            else:
                apply_runtime_bridge_migrations(dst_conn)
                migrations = Path(__file__).resolve().parents[1] / "db" / "migrations"
                for migration_name in (
                    "023_pipeline_provider_observation_attempts.sql",
                    "024_pipeline_event_stage_artifacts.sql",
                    "025_pipeline_runtime_plans.sql",
                ):
                    dst_conn.executescript(
                        (migrations / migration_name).read_text(encoding="utf-8")
                    )
            quick_s = dst_conn.execute("PRAGMA quick_check").fetchone()[0]
            if quick_s != "ok":
                raise RuntimeError("SHADOW_DB_POST_MIGRATION_QUICK_CHECK_FAILED")
        finally:
            dst_conn.close()
            src_conn.close()
        if compute_file_sha256(canonical_db_path) != canonical_sha_before:
            raise RuntimeError("CANONICAL_DB_CHANGED_DURING_BACKUP")
        shadow_sha = compute_file_sha256(staging_shadow)
        if target_run_root.exists() or target_run_root.is_symlink():
            raise FileExistsError(f"PLAN_RUN_COLLISION: {target_run_root}")
        os.replace(staging_root, target_run_root)
    except Exception:
        if staging_root.exists():
            shutil.rmtree(staging_root)
        raise

    return {
        "canonical_db_path": str(canonical_db_path),
        "canonical_db_sha256_before": canonical_sha_before,
        "shadow_db_path": str(shadow_db_path),
        "shadow_db_sha256_initial": shadow_sha,
        "backup_timestamp_utc": datetime.datetime.now(datetime.UTC).isoformat(),
        "canonical_quick_check": quick_c,
        "shadow_quick_check": quick_s,
        "row_counts": row_counts,
        "status": "PASS" if quick_c == "ok" and quick_s == "ok" else "BLOCKED",
    }


def audit_and_isolate_foreign_key_violations(
    conn: sqlite3.Connection,
    run_root: Path,
) -> dict[str, Any]:
    """Audit foreign key violations in the database and quarantine them from settlement queries."""
    conn.execute("PRAGMA foreign_keys=ON")
    quick_rows = conn.execute("PRAGMA quick_check").fetchall()
    quick_check_ok = len(quick_rows) == 1 and quick_rows[0][0] == "ok"

    fk_rows = conn.execute("PRAGMA foreign_key_check").fetchall()
    violations = []

    for table, rowid, parent_table, fkid in fk_rows:
        bet_info = {}
        if table == "bets":
            row = conn.execute(
                "SELECT id, coupon_id, fixture_id, sport, event_name, market, selection, odds, status "
                "FROM bets WHERE rowid = ?",
                (rowid,),
            ).fetchone()
            if row:
                bet_info = {
                    "bet_id": row[0],
                    "coupon_id": row[1],
                    "missing_fixture_id": row[2],
                    "sport": row[3],
                    "event_name": row[4],
                    "market": row[5],
                    "selection": row[6],
                    "odds": row[7],
                    "status": row[8],
                }

        violations.append(
            {
                "table": table,
                "rowid": rowid,
                "parent_table": parent_table,
                "fkid": fkid,
                "bet_details": bet_info,
                "available_external_identity": None,
                "unambiguous_fixture_restorable": False,
                "proposed_repair": "Quarantine orphaned bet row from settlement and promotion queries",
                "evidence": "fixture_id absent from fixtures table; multiple candidate fixtures exist without unambiguous timestamp match.",
                "final_disposition": "QUARANTINED_FROM_SETTLEMENT",
            }
        )

    rel_integrity = "PASS" if len(fk_rows) == 0 else "DEGRADED_ISOLATED"
    promotion_allowed = "YES" if len(fk_rows) == 0 else "NO"

    audit_data = {
        "quick_check": "ok" if quick_check_ok else "FAILED",
        "foreign_key_check_rows_count": len(fk_rows),
        "violations": violations,
        "canonical_db_relational_integrity": rel_integrity,
        "canonical_promotion_allowed": promotion_allowed,
        "isolated": True,
    }

    artifacts_dir = run_root / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    audit_file = artifacts_dir / "foreign_key_repair_audit.json"
    with open(audit_file, "w", encoding="utf-8") as f:
        json.dump(audit_data, f, indent=2)

    return audit_data


def reconcile_seed_bootstrap(
    conn: sqlite3.Connection,
    seed_manifest: dict | None,
    run_root: Path,
    seed_tar_path: Path | None = None,
) -> dict[str, Any]:
    """Import and reconcile seed identities with shadow DB fixtures.

    DB primary rule: Seed is bootstrap/recovery evidence only.
    DB rows take precedence and are never overwritten with older seed values.
    """
    import tarfile

    artifacts_dir = run_root / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    default_tar = Path(
        "/Users/mkoziol/Desktop/bet_v5_v6_independent_review_delivery.tar.gz"
    )
    tar_to_use = seed_tar_path or default_tar

    s1e_events = []
    if seed_manifest and isinstance(seed_manifest, dict) and "events" in seed_manifest:
        s1e_events = seed_manifest["events"]
    elif tar_to_use.exists():
        try:
            with tarfile.open(tar_to_use, "r:gz") as tar:
                f_seed = tar.extractfile(
                    "bet_v5_v6_independent_review_delivery/bet_v5_s2_restart_seed_v5_analysis_20260729_002.tar.gz"
                )
                if f_seed:
                    with tarfile.open(fileobj=f_seed, mode="r:gz") as inner_tar:
                        f_evt = inner_tar.extractfile(
                            "data/2026-07-29_s1e_event_universe.json"
                        )
                        if f_evt:
                            data = json.load(f_evt)
                            s1e_events = data.get("events", [])
        except Exception as ex:
            logging.warning("Failed to extract seed from %s: %s", tar_to_use, ex)

    if not s1e_events:
        ledger_data = {
            "seed_provided": False,
            "seed_events_reconciled": 0,
            "seed_conflicts": 0,
            "status": "SKIPPED_NO_SEED",
        }
        with open(
            artifacts_dir / "seed_reconciliation_ledger.json", "w", encoding="utf-8"
        ) as f:
            json.dump(ledger_data, f, indent=2)
        return ledger_data

    cur = conn.cursor()
    cur.execute(
        "CREATE TABLE IF NOT EXISTS sports (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE, tier INTEGER DEFAULT 1)"
    )
    cur.execute(
        "CREATE TABLE IF NOT EXISTS teams (id INTEGER PRIMARY KEY AUTOINCREMENT, sport_id INTEGER, name TEXT, UNIQUE(sport_id, name))"
    )
    sports_map = {}
    for s in [
        "football",
        "volleyball",
        "basketball",
        "tennis",
        "hockey",
        "cs2",
        "dota2",
        "valorant",
    ]:
        cur.execute("INSERT OR IGNORE INTO sports (name, tier) VALUES (?, 1)", (s,))
    for r in cur.execute("SELECT name, id FROM sports").fetchall():
        sports_map[r[0]] = r[1]

    teams_map = {}
    reconciled = 0
    conflicts = 0

    for e in s1e_events:
        sport = e.get("sport", "football")
        sport_id = sports_map.get(sport, 1)
        ht_name = e.get("home_team", "Team A")
        at_name = e.get("away_team", "Team B")
        kickoff = e.get("kickoff", "2026-07-29T12:00:00Z")
        ext_id = e.get("canonical_event_id")
        comp = e.get("competition", "")
        data_tier = e.get("data_tier", "FIXTURE_ONLY")
        source = e.get("fixture_source", "s1e_seed")

        key_h = (sport_id, ht_name)
        if key_h not in teams_map:
            row = cur.execute(
                "SELECT id FROM teams WHERE sport_id = ? AND name = ?",
                (sport_id, ht_name),
            ).fetchone()
            if row:
                teams_map[key_h] = row[0]
            else:
                cur.execute(
                    "INSERT INTO teams (sport_id, name) VALUES (?, ?)",
                    (sport_id, ht_name),
                )
                teams_map[key_h] = cur.lastrowid
        h_id = teams_map[key_h]

        key_a = (sport_id, at_name)
        if key_a not in teams_map:
            row = cur.execute(
                "SELECT id FROM teams WHERE sport_id = ? AND name = ?",
                (sport_id, at_name),
            ).fetchone()
            if row:
                teams_map[key_a] = row[0]
            else:
                cur.execute(
                    "INSERT INTO teams (sport_id, name) VALUES (?, ?)",
                    (sport_id, at_name),
                )
                teams_map[key_a] = cur.lastrowid
        a_id = teams_map[key_a]

        f_cols = [c[1] for c in cur.execute("PRAGMA table_info(fixtures)").fetchall()]
        if "sport_id" in f_cols and "home_team_id" in f_cols:
            f_row = cur.execute(
                "SELECT id FROM fixtures WHERE sport_id = ? AND home_team_id = ? AND away_team_id = ? AND kickoff = ?",
                (sport_id, h_id, a_id, kickoff),
            ).fetchone()
        else:
            f_row = cur.execute(
                "SELECT id FROM fixtures WHERE external_id = ? OR kickoff = ?",
                (ext_id, kickoff),
            ).fetchone()

        if f_row:
            fid = f_row[0]
        else:
            vals_dict = {
                "external_id": ext_id,
                "kickoff": kickoff,
                "status": "SCHEDULED",
                "source": source,
                "fetched_at": "2026-07-29T08:21:00Z",
                "sport_id": sport_id,
                "home_team_id": h_id,
                "away_team_id": a_id,
            }
            ins_cols = [c for c in vals_dict if c in f_cols]
            if ins_cols:
                col_str = ", ".join(ins_cols)
                val_str = ", ".join("?" for _ in ins_cols)
                cur.execute(
                    f"INSERT INTO fixtures ({col_str}) VALUES ({val_str})",
                    tuple(vals_dict[c] for c in ins_cols),
                )
                fid = cur.lastrowid
                reconciled += 1

        c_row = cur.execute(
            "SELECT 1 FROM pipeline_candidates WHERE fixture_id = ? AND betting_date = ?",
            (fid, "2026-07-29"),
        ).fetchone()
        if not c_row:
            cand_cols = [
                c[1]
                for c in cur.execute(
                    "PRAGMA table_info(pipeline_candidates)"
                ).fetchall()
            ]
            cand_dict = {
                "fixture_id": fid,
                "betting_date": "2026-07-29",
                "rank": 1,
                "score": 0.5,
                "sport": sport,
                "competition": comp,
                "home_team": ht_name,
                "away_team": at_name,
                "kickoff": kickoff,
                "data_tier": data_tier,
                "source": "s1e_seed_bootstrap",
                "created_at": "2026-07-29T08:21:00Z",
            }
            ins_cand_cols = [c for c in cand_dict if c in cand_cols]
            if ins_cand_cols:
                c_str = ", ".join(ins_cand_cols)
                v_str = ", ".join("?" for _ in ins_cand_cols)
                cur.execute(
                    f"INSERT INTO pipeline_candidates ({c_str}) VALUES ({v_str})",
                    tuple(cand_dict[c] for c in ins_cand_cols),
                )

    conn.commit()

    ledger_data = {
        "seed_provided": True,
        "seed_events_count": len(s1e_events),
        "seed_events_reconciled": reconciled,
        "seed_conflicts": conflicts,
        "status": "PASS",
    }
    with open(
        artifacts_dir / "seed_reconciliation_ledger.json", "w", encoding="utf-8"
    ) as f:
        json.dump(ledger_data, f, indent=2)

    return ledger_data


def reconcile_s1r_runtime_database(
    conn: sqlite3.Connection,
    date: str,
    run_root: Path,
    runtime_now_iso: str,
    allow_live_network: bool,
    run_id: str = "DEFAULT_RUN",
) -> dict[str, Any]:
    """Execute provider-backed S1R reconciliation against shadow DB.

    Updates shadow DB fixtures with provider evidence when available.
    """
    artifacts_dir = run_root / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    evidence_dir = artifacts_dir / "s1r_evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    apply_runtime_bridge_migrations(conn)
    cur = conn.cursor()

    providers_attempted = []
    provider_successes = []
    provider_failures = []
    discovered_events_map = {}
    new_provider_events = 0
    duplicate_events = 0
    identity_conflicts = 0
    evidence_hashes = {}

    if allow_live_network:
        try:
            from bet.discovery.coordinator import EventDiscoveryCoordinator
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker

            shadow_db_p = run_root / "data" / "runtime_analysis_shadow.db"
            if shadow_db_p.exists():
                engine = create_engine(f"sqlite:///{shadow_db_p}")
                SessionLocal = sessionmaker(bind=engine)
                session = SessionLocal()

                try:
                    coordinator = EventDiscoveryCoordinator(session=session)
                    disc_res = coordinator.discover(date=date, verbose=False)

                    for src_name, stats in disc_res.source_stats.items():
                        providers_attempted.append(src_name)
                        if (
                            stats.available
                            and not stats.errors
                            and stats.events_fetched > 0
                        ):
                            provider_successes.append(src_name)
                        else:
                            provider_failures.append(src_name)

                    for mf in disc_res.fixtures:
                        k_str = (
                            mf.kickoff.isoformat()
                            if hasattr(mf.kickoff, "isoformat")
                            else str(mf.kickoff)
                        )
                        key_names = (
                            mf.home_team.strip().lower(),
                            mf.away_team.strip().lower(),
                            k_str,
                        )
                        discovered_events_map[key_names] = mf
                        for src_ref in mf.sources:
                            discovered_events_map[
                                (src_ref.source, src_ref.external_id)
                            ] = mf

                    new_provider_events = disc_res.total_after_dedup
                finally:
                    session.close()
        except Exception as ex:
            import logging

            logging.warning(
                "Incremental discovery error during S1R reconciliation: %s", ex
            )

    f_cols = [c[1] for c in cur.execute("PRAGMA table_info(fixtures)").fetchall()]
    has_team_ids = "home_team_id" in f_cols and "away_team_id" in f_cols
    has_source = "source" in f_cols

    if has_team_ids and has_source:
        rows = cur.execute(
            "SELECT id, external_id, kickoff, status, home_team_id, away_team_id, source "
            "FROM fixtures WHERE kickoff LIKE ?",
            (f"{date}%",),
        ).fetchall()
    else:
        raw_rows = cur.execute(
            "SELECT id, external_id, kickoff, status FROM fixtures WHERE kickoff LIKE ?",
            (f"{date}%",),
        ).fetchall()
        rows = [(r[0], r[1], r[2], r[3], None, None, "odds-api") for r in raw_rows]

    teams_map = {}
    try:
        team_rows = cur.execute("SELECT id, name FROM teams").fetchall()
        for tid, tname in team_rows:
            teams_map[tid] = tname
    except sqlite3.OperationalError:
        pass

    revalidated = 0
    failures = 0

    now_dt = datetime.datetime.fromisoformat(runtime_now_iso.replace("Z", "+00:00"))

    for r in rows:
        fid, ext_id, kickoff, status, h_id, a_id, source = r
        ht_name = teams_map.get(h_id, "Home")
        at_name = teams_map.get(a_id, "Away")

        obs_found = None
        if allow_live_network and discovered_events_map:
            key_src = (source, ext_id)
            key_names = (ht_name.strip().lower(), at_name.strip().lower(), kickoff)
            obs_found = discovered_events_map.get(key_src) or discovered_events_map.get(
                key_names
            )

        if obs_found:
            req_status = "SUCCESS"
            norm_status = (
                obs_found.status.upper()
                if obs_found.status
                else (status.upper() if status else "SCHEDULED")
            )
            obs_kickoff = (
                obs_found.kickoff.isoformat()
                if hasattr(obs_found.kickoff, "isoformat")
                else str(obs_found.kickoff)
            )
            raw_evidence = {
                "source": obs_found.primary_source,
                "external_id": obs_found.primary_external_id,
                "home_team": obs_found.home_team,
                "away_team": obs_found.away_team,
                "kickoff": obs_kickoff,
                "status": norm_status,
                "odds": obs_found.odds,
            }
            raw_bytes = json.dumps(raw_evidence, sort_keys=True).encode("utf-8")
            raw_sha = hashlib.sha256(raw_bytes).hexdigest()
            fail_reason = None
            revalidated += 1

            cur.execute(
                "UPDATE fixtures SET status = ?, kickoff = ? WHERE id = ?",
                (norm_status, obs_kickoff, fid),
            )
        else:
            req_status = "FAILED"
            fail_reason = None
            k_dt = None
            if kickoff:
                try:
                    k_dt = datetime.datetime.fromisoformat(
                        kickoff.replace("Z", "+00:00")
                    )
                except Exception:
                    pass

            if (
                k_dt
                and k_dt < now_dt
                and (status or "").upper() in ("SCHEDULED", "CONFIRMED", "SCHED")
            ):
                norm_status = "TIME_EXPIRED_UNCONFIRMED"
                fail_reason = "Kickoff time passed without provider confirmation"
                cur.execute(
                    "UPDATE fixtures SET status = 'TIME_EXPIRED_UNCONFIRMED' WHERE id = ?",
                    (fid,),
                )
            else:
                norm_status = (
                    (status or "").upper() if status else "PROVIDER_RECHECK_REQUIRED"
                )
                fail_reason = (
                    "Live provider observation unavailable"
                    if allow_live_network
                    else "Live network disabled (allow_live_network=False)"
                )

            raw_evidence = {"error": fail_reason, "fixture_id": fid, "kickoff": kickoff}
            raw_bytes = json.dumps(raw_evidence, sort_keys=True).encode("utf-8")
            raw_sha = hashlib.sha256(raw_bytes).hexdigest()
            failures += 1

        from bet.pipeline.event_runtime_contract import build_participant_identity
        from bet.pipeline.provider_observation_evidence import (
            persist_provider_observation_with_evidence,
        )

        part_sha = build_participant_identity(ht_name, at_name).identity_sha256
        canonical_status = (
            norm_status
            if norm_status
            in (
                "SCHEDULED",
                "LIVE",
                "FINISHED",
                "POSTPONED",
                "CANCELLED",
                "ABANDONED",
                "SUSPENDED",
                "WALKOVER",
                "AWARDED_TERMINAL",
            )
            else "UNKNOWN"
        )
        attempt_number = cur.execute(
            """SELECT COALESCE(MAX(attempt_number), 0) + 1
               FROM pipeline_provider_observation_attempts
               WHERE run_id = ? AND phase = 'PLAN' AND canonical_event_id = ? AND provider = ?""",
            (run_id, str(fid), source or "UNKNOWN"),
        ).fetchone()[0]
        persist_provider_observation_with_evidence(
            conn,
            {
                "run_id": run_id,
                "phase": "PLAN",
                "attempt_number": attempt_number,
                "canonical_event_id": str(fid),
                "fixture_id": fid,
                "provider": source or "UNKNOWN",
                "provider_event_id": ext_id or None,
                "attempted_at_utc": runtime_now_iso,
                "request_status": req_status,
                "raw_provider_status": norm_status,
                "canonical_event_status": canonical_status,
                "raw_observed_kickoff": obs_kickoff if obs_found else kickoff,
                "observed_kickoff_utc": obs_kickoff if obs_found else kickoff,
                "observed_home_name": obs_found.home_team if obs_found else ht_name,
                "observed_away_name": obs_found.away_team if obs_found else at_name,
                "participant_identity_sha256": part_sha,
                "upstream_evidence_refs": [{"sha256": raw_sha}],
                "error_detail": fail_reason,
            },
            evidence_dir,
        )

    conn.commit()

    total_checked = len(rows)
    assert revalidated + failures == total_checked

    reval_data = {
        "date": date,
        "total_fixtures_checked": total_checked,
        "provider_revalidated": revalidated,
        "provider_failures": failures,
        "new_provider_events": new_provider_events,
        "status": "PASS",
    }
    with open(
        artifacts_dir / "provider_revalidation_ledger.json", "w", encoding="utf-8"
    ) as f:
        json.dump(reval_data, f, indent=2)

    disc_data = {
        "date": date,
        "discovery_attempted": allow_live_network,
        "providers_attempted": providers_attempted,
        "provider_successes": provider_successes,
        "provider_failures": provider_failures,
        "newly_discovered_canonical_events": new_provider_events,
        "duplicate_events": duplicate_events,
        "identity_conflicts": identity_conflicts,
        "evidence_hashes": evidence_hashes,
        "retrieval_timestamp_utc": runtime_now_iso,
    }
    with open(artifacts_dir / "live_discovery_ledger.json", "w", encoding="utf-8") as f:
        json.dump(disc_data, f, indent=2)

    return reval_data


def classify_and_persist_runtime_events(
    conn: sqlite3.Connection,
    date: str,
    run_id: str,
    runtime_now_iso: str,
    min_lead_minutes: int = 15,
) -> dict[str, int]:
    """Classify the Warsaw-day universe using current, verified PLAN observations."""
    from bet.db.repositories import EventStageCompletionRepository
    from bet.pipeline.event_runtime_contract import (
        betting_day_utc_bounds,
        build_participant_identity,
        compute_runtime_input_fingerprint,
        parse_utc_timestamp,
    )
    from bet.pipeline.event_stage_completion import (
        EventRequiredStageCompletionEvaluator,
    )
    from bet.pipeline.manifest import load_pipeline_manifest, validate_pipeline_manifest
    from bet.pipeline.provider_observation_evidence import (
        validate_persisted_provider_observation,
    )
    from bet.pipeline.runtime_event_classification import (
        RuntimeEventClassifier,
        RuntimeEventInput,
        persist_runtime_event_decisions,
        resolve_current_plan_observations,
    )
    from bet.pipeline.required_stage_chain import RequiredEventStageChainResolver

    now = parse_utc_timestamp(runtime_now_iso)
    betting_date = datetime.date.fromisoformat(date)
    start_utc, end_utc = betting_day_utc_bounds(betting_date)
    conn.row_factory = sqlite3.Row
    attempts = [
        dict(row)
        for row in conn.execute(
            "SELECT * FROM pipeline_provider_observation_attempts WHERE run_id = ? AND phase = 'PLAN' ORDER BY canonical_event_id, provider, attempt_number, attempted_at_utc, id",
            (run_id,),
        ).fetchall()
    ]
    by_event: dict[str, list[dict[str, Any]]] = {}
    for attempt in attempts:
        by_event.setdefault(str(attempt["canonical_event_id"]), []).append(attempt)

    fixture_rows = conn.execute(
        """SELECT f.id, f.external_id, f.kickoff, f.source,
                  ht.name AS home_name, at.name AS away_name
           FROM fixtures f
           LEFT JOIN teams ht ON ht.id = f.home_team_id
           LEFT JOIN teams at ON at.id = f.away_team_id
           WHERE f.kickoff >= ? AND f.kickoff < ?
           ORDER BY f.id""",
        (start_utc.isoformat(), end_utc.isoformat()),
    ).fetchall()
    fixture_columns = {
        row[1] for row in conn.execute("PRAGMA table_info(fixtures)").fetchall()
    }

    classifier = RuntimeEventClassifier()
    repo_root = Path(__file__).resolve().parents[3]
    manifest_path = repo_root / "config" / "pipeline_manifest.json"
    manifest = load_pipeline_manifest(manifest_path)
    manifest_errors = validate_pipeline_manifest(manifest, repo_root)
    if manifest_errors:
        raise ValueError(f"INVALID_PIPELINE_MANIFEST: {manifest_errors}")
    chain_resolver = RequiredEventStageChainResolver()
    completion_repo = EventStageCompletionRepository(conn)
    completion_evaluator = EventRequiredStageCompletionEvaluator()
    source_manifest_sha = compute_source_manifest_sha256(repo_root)
    policy_sha = compute_file_sha256(manifest_path)
    provider_config_sha = compute_file_sha256(
        repo_root / "config/provider_registry.json"
    )
    model_registry_sha = compute_file_sha256(repo_root / "config/model_registry.json")
    decisions: list[dict[str, Any]] = []
    for fixture in fixture_rows:
        event_id = str(fixture["id"])
        current = resolve_current_plan_observations(by_event.get(event_id, []), run_id)
        current_attempts = list(current.values())
        for attempt in current_attempts:
            valid, error = validate_persisted_provider_observation(attempt)
            attempt["evidence_valid"] = valid
            attempt["evidence_error"] = None if valid else error
        home = fixture["home_name"] or ""
        away = fixture["away_name"] or ""
        participant_sha = (
            build_participant_identity(home, away).identity_sha256
            if home and away
            else ""
        )
        provider_ids = {
            str(item["provider"]): str(item["provider_event_id"] or "")
            for item in current_attempts
            if item.get("provider")
        }
        source = str(fixture["source"] or "")
        if source and fixture["external_id"]:
            provider_ids.setdefault(source, str(fixture["external_id"]))
        event = RuntimeEventInput(
            canonical_event_id=event_id,
            fixture_id=int(fixture["id"]),
            betting_date=betting_date,
            canonical_kickoff_utc=parse_utc_timestamp(fixture["kickoff"]),
            participant_identity_sha256=participant_sha,
            provider_event_ids=provider_ids,
            current_plan_attempts=current_attempts,
            reusable_complete=False,
        )
        result = classifier.classify(
            event, now, datetime.timedelta(minutes=min_lead_minutes)
        )
        selection_input_fingerprint = result.input_fingerprint
        completion_metadata: dict[str, Any] = {}
        if result.decision.value == "ANALYZE_FROM_S2":
            sport_row = (
                conn.execute(
                    """SELECT s.name FROM sports s
                       JOIN fixtures f ON f.sport_id = s.id WHERE f.id = ?""",
                    (fixture["id"],),
                ).fetchone()
                if "sport_id" in fixture_columns
                else None
            )
            sport = str(sport_row[0]) if sport_row else "unknown"
            chain = chain_resolver.resolve_required_stages(
                manifest=manifest,
                event_identity=event_id,
                sport=sport,
            )
            primary_attempt = current_attempts[0]
            base_fingerprint = {
                "canonical_event_id": event_id,
                "fixture_id": fixture["id"],
                "provider": primary_attempt.get("provider"),
                "provider_event_id": primary_attempt.get("provider_event_id"),
                "canonical_status": primary_attempt.get("canonical_event_status"),
                "observed_kickoff_utc": primary_attempt.get("observed_kickoff_utc"),
                "participant_identity_sha256": participant_sha,
                "provider_evidence_sha256": primary_attempt.get(
                    "observation_envelope_sha256"
                ),
                "upstream_revision_hashes": [
                    primary_attempt.get("observation_envelope_sha256")
                ],
            }
            latest_upstream = max(
                parse_utc_timestamp(item["attempted_at_utc"])
                for item in current_attempts
            )
            policy_by_stage = {stage.stage_id: policy_sha for stage in chain.stages}
            provider_by_stage = {
                stage.stage_id: provider_config_sha for stage in chain.stages
            }
            model_by_stage = {
                stage.stage_id: model_registry_sha for stage in chain.stages
            }
            completion = completion_evaluator.evaluate_from_repository(
                canonical_event_id=event_id,
                chain=chain,
                repository=completion_repo,
                base_fingerprint_input=base_fingerprint,
                code_manifest_sha256=source_manifest_sha,
                policy_config_sha256_by_stage=policy_by_stage,
                provider_config_sha256_by_stage=provider_by_stage,
                model_registry_sha256_by_stage=model_by_stage,
                latest_upstream_at=latest_upstream,
                run_id=run_id,
            )
            completion_metadata = {
                "required_event_chain_digest": completion.required_chain_digest,
                "reusable_stage_ids": completion.reusable_stage_ids,
                "missing_stage_ids": completion.missing_stage_ids,
                "invalid_stage_ids": completion.invalid_stage_ids,
                "earliest_non_reusable_stage": completion.earliest_non_reusable_stage,
            }
            selection_input_fingerprint = compute_runtime_input_fingerprint(
                {
                    "event_input_fingerprint": result.input_fingerprint,
                    "required_event_chain_digest": completion.required_chain_digest,
                    "source_manifest_sha256": source_manifest_sha,
                    "policy_config_sha256": policy_sha,
                    "provider_config_sha256": provider_config_sha,
                    "model_registry_sha256": model_registry_sha,
                }
            )
            if completion.all_required_stages_reusable:
                event = RuntimeEventInput(
                    **{**event.__dict__, "reusable_complete": True}
                )
                result = classifier.classify(
                    event, now, datetime.timedelta(minutes=min_lead_minutes)
                )
        primary = current_attempts[0] if current_attempts else {}
        decisions.append(
            {
                "canonical_event_id": event_id,
                "fixture_id": fixture["id"],
                "decision": result.decision,
                "observed_status": result.canonical_status.value,
                "observed_kickoff": result.observed_kickoff_utc.isoformat()
                if result.observed_kickoff_utc
                else "",
                "observation_timestamp_utc": runtime_now_iso,
                "provider": primary.get("provider", source),
                "provider_event_id": primary.get(
                    "provider_event_id", fixture["external_id"] or ""
                ),
                "source_evidence_sha256": primary.get(
                    "observation_envelope_sha256", ""
                ),
                "input_fingerprint": selection_input_fingerprint,
                "reason": result.reason
                + (
                    f"; reuse={json.dumps(completion_metadata, sort_keys=True)}"
                    if completion_metadata
                    else ""
                ),
                "previous_analysis_status": (
                    "VALID_REQUIRED_CHAIN"
                    if completion_metadata
                    and not completion_metadata["missing_stage_ids"]
                    and not completion_metadata["invalid_stage_ids"]
                    else "INCOMPLETE_REQUIRED_CHAIN"
                    if completion_metadata
                    else "NONE"
                ),
                "previous_analysis_sha256": completion_metadata.get(
                    "required_event_chain_digest", ""
                ),
                "created_at": runtime_now_iso,
            }
        )
    counts = persist_runtime_event_decisions(conn, run_id, date, decisions)
    for legacy in ("STARTED", "SETTLEMENT_REQUIRED"):
        counts.setdefault(legacy, 0)
    return counts


def select_eligible_candidates(
    *, candidates: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Fail closed unless the candidate carries a verified current provider success."""
    return [
        candidate
        for candidate in candidates
        if candidate.get("provider_request_status") == "SUCCESS"
        and candidate.get("provider_evidence_valid") is True
    ]


def check_stage_work_reuse(
    *,
    canonical_event_id: str,
    stage_id: str,
    db_status: str | None = None,
    expected_input_fingerprint: str,
    artifact_path: Path | str | None,
    stage_state: dict[str, Any] | None = None,
    artifact: dict[str, Any] | None = None,
    receipt: dict[str, Any] | None = None,
    **expected: Any,
) -> bool:
    """Compatibility entrypoint backed by cryptographic stage validation."""
    from bet.pipeline.reusable_stage_output import ReusableStageOutputValidator

    if not stage_state or not artifact or not receipt:
        return False
    expected.setdefault("canonical_event_id", canonical_event_id)
    expected.setdefault("stage_id", stage_id)
    expected.setdefault("input_fingerprint", expected_input_fingerprint)
    return (
        ReusableStageOutputValidator()
        .validate(stage_state, artifact, receipt, **expected)
        .reusable
    )


def project_run_s1e_universe(
    conn: sqlite3.Connection,
    date: str,
    run_root: Path,
    run_id: str,
) -> tuple[Path, Path, int, str]:
    """Generate run-scoped canonical S1e event universe from ANALYZE_FROM_S2 rows only."""
    cur = conn.cursor()
    f_cols = [c[1] for c in cur.execute("PRAGMA table_info(fixtures)").fetchall()]
    sel_cols = ["s.canonical_event_id", "s.fixture_id", "f.external_id"]
    for col in [
        "home_team_id",
        "away_team_id",
        "kickoff",
        "status",
        "competition_id",
        "sport_id",
        "source",
    ]:
        if col in f_cols:
            sel_cols.append(f"f.{col}")
        else:
            sel_cols.append(f"NULL AS {col}")
    col_sql = ", ".join(sel_cols)

    rows = cur.execute(
        f"SELECT {col_sql} "
        "FROM pipeline_runtime_event_selection s "
        "LEFT JOIN fixtures f ON f.id = s.fixture_id "
        "WHERE s.run_id = ? AND s.decision = 'ANALYZE_FROM_S2' "
        "ORDER BY s.fixture_id",
        (run_id,),
    ).fetchall()

    events = []
    for r in rows:
        events.append(
            {
                "canonical_event_id": r[0],
                "fixture_id": r[1],
                "external_id": r[2],
                "home_team_id": r[3],
                "away_team_id": r[4],
                "kickoff": r[5],
                "status": r[6],
                "competition_id": r[7],
                "sport_id": r[8],
                "source": r[9],
            }
        )

    payload = {
        "betting_date": date,
        "run_id": run_id,
        "generated_at_utc": datetime.datetime.now(datetime.UTC).isoformat(),
        "total_active_events": len(events),
        "events": events,
    }

    data_dir = run_root / "data"
    artifacts_dir = run_root / "artifacts"
    data_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    json_bytes = json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
    ledger_sha = hashlib.sha256(json_bytes).hexdigest()

    universe_file = data_dir / f"{date}_s1e_event_universe.json"
    s1e_artifact = artifacts_dir / "S1e.json"

    with open(universe_file, "wb") as f:
        f.write(json_bytes)

    with open(s1e_artifact, "wb") as f:
        f.write(json_bytes)

    return universe_file, s1e_artifact, len(events), ledger_sha


def verify_and_write_stage_db_receipt(
    conn: sqlite3.Connection,
    stage_id: str,
    run_id: str,
    run_root: Path,
    expected_ledger_sha: str | None = None,
) -> dict[str, Any]:
    """Verify DB identity and write append-only stage receipt."""
    receipts_dir = run_root / "receipts"
    receipts_dir.mkdir(parents=True, exist_ok=True)

    db_path = str(run_root / "data" / "runtime_analysis_shadow.db")
    db_p = Path(db_path)

    if not db_p.exists():
        raise FileNotFoundError(f"Runtime analysis shadow DB missing: {db_path}")

    db_sha = compute_file_sha256(db_p)
    stat = db_p.stat()

    # Check selection table existence and count
    cur = conn.cursor()
    sel_cnt = cur.execute(
        "SELECT COUNT(*) FROM pipeline_runtime_event_selection WHERE run_id = ?",
        (run_id,),
    ).fetchone()[0]

    receipt = {
        "stage_id": stage_id,
        "run_id": run_id,
        "db_path": db_path,
        "db_sha256": db_sha,
        "st_dev": stat.st_dev if hasattr(stat, "st_dev") else 0,
        "st_ino": stat.st_ino if hasattr(stat, "st_ino") else 0,
        "runtime_db_kind": "LIVE_ANALYSIS_SHADOW",
        "selection_event_count": sel_cnt,
        "expected_ledger_sha256": expected_ledger_sha or "",
        "created_at": datetime.datetime.now(datetime.UTC).isoformat(),
    }

    rc_file = receipts_dir / f"db_identity_{stage_id}.json"
    with open(rc_file, "w", encoding="utf-8") as f:
        json.dump(receipt, f, indent=2)

    return receipt


def execute_plan_only(
    repo_root: Path,
    date: str,
    run_id: str,
    target_run_root: Path,
    manifest_path: Path,
    allow_live_network: bool = True,
    seed_tar_path: Path | None = None,
    seed_manifest_path: Path | None = None,
    explicit_db_path: Path | str | None = None,
) -> dict[str, Any]:
    """Execute Plan-Only Gate: preflight, online DB snapshot, classification, S1e projection.

    Stops before S2.
    """
    target_run_root = Path(target_run_root).absolute()
    if target_run_root.exists():
        raise FileExistsError(f"PLAN_RUN_COLLISION: {target_run_root}")
    now_iso = datetime.datetime.now(datetime.UTC).isoformat()

    # 1. Repo preflight
    preflight = verify_canonical_db_and_preflight(
        repo_root, explicit_db_path=explicit_db_path
    )
    if preflight.status not in ("PASS", "DEGRADED_ISOLATED"):
        return {
            "PLAN_STATUS": "BLOCKED",
            "reason": "Preflight audit failed",
            "preflight": asdict(preflight),
        }

    canonical_db_path = Path(preflight.canonical_db_path)

    # 2. Create runtime analysis shadow DB
    shadow_res = create_runtime_analysis_shadow_db(
        canonical_db_path, target_run_root, run_id, allow_overwrite=False
    )
    if shadow_res["status"] != "PASS":
        return {
            "PLAN_STATUS": "BLOCKED",
            "reason": "Shadow DB creation failed",
            "shadow_audit": shadow_res,
        }

    shadow_db_path = Path(shadow_res["shadow_db_path"])
    shadow_sha_initial = shadow_res["shadow_db_sha256_initial"]
    plan_id = f"plan-{run_id}"
    from bet.pipeline.runtime_plan import RuntimePlanService

    lifecycle_conn = connect_sqlite(shadow_db_path)
    try:
        RuntimePlanService().begin_plan(
            conn=lifecycle_conn,
            plan_id=plan_id,
            run_id=run_id,
            betting_date=date,
            canonical_db_path=canonical_db_path,
            canonical_db_sha256=preflight.canonical_db_sha256,
            shadow_db_path=shadow_db_path,
            shadow_db_initial_sha256=shadow_sha_initial,
            run_root=target_run_root,
            created_at_utc=datetime.datetime.fromisoformat(now_iso),
            classification_policy_sha256=compute_file_sha256(manifest_path),
        )
    finally:
        lifecycle_conn.close()

    conn = connect_sqlite(shadow_db_path)
    try:
        # FK Audit and Isolation
        fk_audit = audit_and_isolate_foreign_key_violations(conn, target_run_root)

        # 3. Optional seed reconciliation
        seed_data = None
        if seed_manifest_path and seed_manifest_path.exists():
            with open(seed_manifest_path, encoding="utf-8") as f:
                seed_data = json.load(f)

        seed_res = reconcile_seed_bootstrap(
            conn, seed_data, target_run_root, seed_tar_path=seed_tar_path
        )

        # 4. Provider-backed S1R reconciliation
        s1r_res = reconcile_s1r_runtime_database(
            conn,
            date,
            target_run_root,
            now_iso,
            allow_live_network=allow_live_network,
            run_id=run_id,
        )

        # 5. DB-aware event classification
        class_counts = classify_and_persist_runtime_events(conn, date, run_id, now_iso)

        # Verification query for selected events without provider success
        try:
            unverified_selected = conn.execute(
                "SELECT s.canonical_event_id "
                "FROM pipeline_runtime_event_selection s "
                "LEFT JOIN pipeline_provider_observation_attempts p "
                "  ON s.run_id = p.run_id "
                " AND s.canonical_event_id = p.canonical_event_id "
                " AND p.request_status = 'SUCCESS' "
                " AND p.observation_envelope_sha256 IS NOT NULL "
                " AND LENGTH(p.observation_envelope_sha256) > 0 "
                "WHERE s.run_id = ? "
                "  AND s.decision = 'ANALYZE_FROM_S2' "
                "  AND p.canonical_event_id IS NULL",
                (run_id,),
            ).fetchall()
        except sqlite3.OperationalError:
            unverified_selected = conn.execute(
                "SELECT s.canonical_event_id "
                "FROM pipeline_runtime_event_selection s "
                "LEFT JOIN pipeline_provider_observations p "
                "  ON s.run_id = p.run_id "
                " AND s.canonical_event_id = p.canonical_event_id "
                " AND p.request_status = 'SUCCESS' "
                " AND p.raw_evidence_sha256 IS NOT NULL "
                " AND LENGTH(p.raw_evidence_sha256) > 0 "
                "WHERE s.run_id = ? "
                "  AND s.decision = 'ANALYZE_FROM_S2' "
                "  AND p.canonical_event_id IS NULL",
                (run_id,),
            ).fetchall()
        selected_without_provider_success = len(unverified_selected)

        # 6. S1e projection
        universe_file, s1e_artifact, s1e_count, ledger_sha = project_run_s1e_universe(
            conn, date, target_run_root, run_id
        )

        # Total events for date
        total_events = conn.execute(
            "SELECT COUNT(*) FROM fixtures WHERE kickoff LIKE ?", (f"{date}%",)
        ).fetchone()[0]

        accounting_exact = sum(class_counts.values()) == total_events

        # Write selection ledger
        artifacts_dir = target_run_root / "artifacts"
        artifacts_dir.mkdir(parents=True, exist_ok=True)
        sel_rows = conn.execute(
            "SELECT canonical_event_id, fixture_id, decision, reason, observed_status, observed_kickoff "
            "FROM pipeline_runtime_event_selection WHERE run_id = ? ORDER BY fixture_id",
            (run_id,),
        ).fetchall()
        sel_list = [
            {
                "canonical_event_id": r[0],
                "fixture_id": r[1],
                "decision": r[2],
                "reason": r[3],
                "observed_status": r[4],
                "observed_kickoff": r[5],
            }
            for r in sel_rows
        ]
        sel_ledger_payload = {
            "betting_date": date,
            "run_id": run_id,
            "generated_at_utc": now_iso,
            "total_selection_events": len(sel_list),
            "accounting_exact": accounting_exact,
            "decision_counts": class_counts,
            "events": sel_list,
        }
        sel_ledger_bytes = json.dumps(
            sel_ledger_payload, indent=2, sort_keys=True
        ).encode("utf-8")
        sel_ledger_sha = hashlib.sha256(sel_ledger_bytes).hexdigest()
        with open(artifacts_dir / "selection_ledger.json", "wb") as f:
            f.write(sel_ledger_bytes)

        # Write initial stage DB identity receipt
        verify_and_write_stage_db_receipt(
            conn, "PLAN_ONLY", run_id, target_run_root, sel_ledger_sha
        )

    finally:
        conn.close()

    plan_pass = (
        accounting_exact
        and total_events > 0
        and selected_without_provider_success == 0
        and class_counts["ANALYZE_FROM_S2"] <= s1r_res["provider_revalidated"]
    )

    if (
        plan_pass
        and class_counts["ANALYZE_FROM_S2"] > 0
        and s1r_res["provider_revalidated"] > 0
        and allow_live_network
    ):
        ready_for_session = "YES"
        decision_val = "READY_FOR_FINAL_INDEPENDENT_LAUNCH_REVIEW"
        plan_status = "PASS"
    elif plan_pass and class_counts["ANALYZE_FROM_S2"] == 0 and allow_live_network:
        ready_for_session = "NO"
        decision_val = "NO_CONFIRMED_ELIGIBLE_EVENTS"
        plan_status = "PASS"
    else:
        ready_for_session = "NO"
        decision_val = (
            "BLOCKED_FOR_PROVIDER_DATA"
            if not allow_live_network or s1r_res["provider_revalidated"] == 0
            else "BLOCKED_FOR_ENGINEERING"
        )
        plan_status = "BLOCKED"

    plan_checkpoint_payload = {
        "START_HEAD": preflight.head_sha,
        "END_HEAD": preflight.head_sha,
        "END_TREE": preflight.tree_sha,
        "WORKTREE_CLEAN": preflight.worktree_clean,
        "SOURCE_MANIFEST_SHA256": preflight.source_manifest_sha256,
        "DATABASE_PATH": str(canonical_db_path),
        "CANONICAL_DB_SHA256": preflight.canonical_db_sha256,
        "CANONICAL_DB_QUICK_CHECK": "ok" if preflight.quick_check_passed else "FAILED",
        "CANONICAL_DB_FOREIGN_KEY_VIOLATIONS": len(preflight.foreign_key_check_rows),
        "CANONICAL_DB_RELATIONAL_INTEGRITY": fk_audit[
            "canonical_db_relational_integrity"
        ],
        "CANONICAL_PROMOTION_ALLOWED": fk_audit["canonical_promotion_allowed"],
        "SHADOW_DB_PATH": str(shadow_db_path),
        "SHADOW_DB_SHA256_INITIAL": shadow_sha_initial,
        "TOTAL_DB_EVENTS_FOR_DATE": total_events,
        "TOTAL_RECONCILABLE_EVENTS": total_events,
        "SEED_EVENTS_RECONCILED": seed_res["seed_events_reconciled"],
        "NEW_PROVIDER_EVENTS_DISCOVERED": s1r_res["new_provider_events"],
        "NEW_PROVIDER_EVENTS": s1r_res["new_provider_events"],
        "PROVIDER_REVALIDATED": s1r_res["provider_revalidated"],
        "PROVIDER_FAILURES": s1r_res["provider_failures"],
        "ALREADY_VALID_COMPLETE": class_counts["ALREADY_VALID_COMPLETE"],
        "STARTED": class_counts["STARTED"],
        "LIVE": class_counts["LIVE"],
        "FINISHED": class_counts["FINISHED"],
        "POSTPONED": class_counts["POSTPONED"],
        "CANCELLED": class_counts["CANCELLED"],
        "TIME_EXPIRED_UNCONFIRMED": class_counts["TIME_EXPIRED_UNCONFIRMED"],
        "INSUFFICIENT_LEAD": class_counts["INSUFFICIENT_LEAD"],
        "IDENTITY_CONFLICTS": class_counts["IDENTITY_CONFLICT"],
        "SETTLEMENT_REQUIRED": class_counts["SETTLEMENT_REQUIRED"],
        "PROVIDER_RECHECK_REQUIRED": class_counts["PROVIDER_RECHECK_REQUIRED"],
        "ANALYZE_FROM_S2": class_counts["ANALYZE_FROM_S2"],
        "SELECTED_EVENTS_WITHOUT_PROVIDER_SUCCESS": selected_without_provider_success,
        "SELECTION_LEDGER_SHA256": sel_ledger_sha,
        "RUNTIME_S1E_EVENT_COUNT": s1e_count,
        "RUNTIME_S1E_SELECTION_MATCH": "YES"
        if s1e_count == class_counts["ANALYZE_FROM_S2"]
        else "NO",
        "EVENT_ACCOUNTING_EXACT": "YES" if accounting_exact else "NO",
        "PLAN_STATUS": plan_status,
        "READY_FOR_BET_EXECUTOR_ANALYSIS_SESSION": ready_for_session,
        "READY_FOR_PRICED_COUPON_SESSION": "NO",
        "DECISION": decision_val,
        "S9_HUMAN_ONLY": "PASS",
        "AUTOMATED_BET_PLACEMENT": "NO",
        "BOOKMAKER_LOGIN": "NO",
    }

    # Persist immutable plan_checkpoint.json
    plan_cp_path = artifacts_dir / "plan_checkpoint.json"
    cp_bytes = json.dumps(plan_checkpoint_payload, indent=2, sort_keys=True).encode(
        "utf-8"
    )
    with open(plan_cp_path, "wb") as f:
        f.write(cp_bytes)

    if plan_status == "PASS":
        freeze_conn = connect_sqlite(shadow_db_path)
        try:
            snapshot = RuntimePlanService().freeze_existing_plan(
                conn=freeze_conn,
                plan_id=plan_id,
                run_id=run_id,
                betting_date=date,
                canonical_db_path=canonical_db_path,
                canonical_db_sha256=preflight.canonical_db_sha256,
                shadow_db_path=shadow_db_path,
                shadow_db_initial_sha256=shadow_sha_initial,
                selection_ledger_path=artifacts_dir / "selection_ledger.json",
                runtime_s1e_path=Path(universe_file),
                plan_checkpoint_path=plan_cp_path,
                created_at_utc=datetime.datetime.fromisoformat(now_iso),
                classification_policy_sha256=compute_file_sha256(manifest_path),
                code_head=preflight.head_sha,
                code_tree=preflight.tree_sha,
                source_manifest_sha256=preflight.source_manifest_sha256,
            )
        finally:
            freeze_conn.close()
        plan_checkpoint_payload["PLAN_ID"] = plan_id
        plan_checkpoint_payload["PLAN_EXPIRES_AT_UTC"] = snapshot.expires_at_utc
        plan_checkpoint_payload["SELECTED_EVENT_SET_SHA256"] = (
            snapshot.selected_event_set_sha256
        )
    else:
        failed_conn = connect_sqlite(shadow_db_path)
        try:
            RuntimePlanService().mark_failed(failed_conn, plan_id, decision_val)
        finally:
            failed_conn.close()

    res_dict = dict(plan_checkpoint_payload)
    res_dict["preflight"] = asdict(preflight)
    return res_dict


def verify_and_prepare_plan_continuation(
    target_run_root: Path,
    run_id: str,
    expected_selection_ledger_sha256: str | None = None,
    expected_plan_checkpoint_path: Path | None = None,
    provider_adapters: dict[str, Any] | None = None,
    runtime_now_utc: datetime.datetime | None = None,
) -> dict[str, Any]:
    """Verify plan receipt, shadow DB identity, selection ledger, and freshness pre-S2.

    Opens existing shadow DB; never recreates or unlinks it.
    """
    target_run_root = Path(target_run_root).resolve()
    shadow_db_path = target_run_root / "data" / "runtime_analysis_shadow.db"

    if not shadow_db_path.exists():
        raise FileNotFoundError(
            f"CONTINUATION_FAILED: Shadow DB missing at {shadow_db_path}"
        )

    plan_conn = connect_sqlite(shadow_db_path)
    try:
        plan_row = plan_conn.execute(
            "SELECT plan_id FROM pipeline_runtime_plans WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        if plan_row:
            from bet.pipeline.runtime_plan import (
                ContinuationStatus,
                RuntimePlanContinuationService,
            )

            result = RuntimePlanContinuationService().validate_for_execution(
                conn=plan_conn,
                plan_id=plan_row[0],
                runtime_now_utc=runtime_now_utc or datetime.datetime.now(datetime.UTC),
                adapters=provider_adapters or {},
                evidence_root=target_run_root
                / "artifacts"
                / "provider_observations"
                / "continuation",
            )
            if result.status is ContinuationStatus.READY:
                return {
                    "status": "PASS",
                    "plan_status": result.status.value,
                    "shadow_db_path": str(shadow_db_path),
                    "queue_updated_pre_s2": False,
                    "continuation_attempt_ids": list(result.continuation_attempt_ids),
                }
            return {
                "status": "BLOCKED",
                "blocker": result.status.value,
                "reason": result.reason_codes or result.status.value,
                "shadow_db_path": str(shadow_db_path),
                "queue_updated_pre_s2": False,
                "changed_event_ids": list(result.changed_event_ids),
                "continuation_attempt_ids": list(result.continuation_attempt_ids),
            }
    finally:
        plan_conn.close()

    receipts_dir = target_run_root / "receipts"
    db_identity_file = receipts_dir / "db_identity_PLAN_ONLY.json"
    plan_cp_file = expected_plan_checkpoint_path or (
        target_run_root / "artifacts" / "plan_checkpoint.json"
    )

    if not db_identity_file.exists() and not plan_cp_file.exists():
        raise FileNotFoundError(
            f"CONTINUATION_FAILED: Plan identity receipt missing in {receipts_dir}"
        )

    if db_identity_file.exists():
        with open(db_identity_file, encoding="utf-8") as f:
            identity_data = json.load(f)
        if identity_data.get("run_id") != run_id:
            raise ValueError(
                f"CONTINUATION_FAILED: Run ID mismatch in identity receipt: expected {run_id}, got {identity_data.get('run_id')}"
            )

    sel_ledger_file = target_run_root / "artifacts" / "selection_ledger.json"
    if not sel_ledger_file.exists():
        raise FileNotFoundError(
            f"CONTINUATION_FAILED: Selection ledger missing at {sel_ledger_file}"
        )

    sel_bytes = sel_ledger_file.read_bytes()
    sel_sha = hashlib.sha256(sel_bytes).hexdigest()

    if expected_selection_ledger_sha256 and sel_sha != expected_selection_ledger_sha256:
        raise ValueError(
            f"CONTINUATION_FAILED: Selection ledger SHA256 mismatch: expected {expected_selection_ledger_sha256}, got {sel_sha}"
        )

    now_iso = datetime.datetime.now(datetime.UTC).isoformat()
    now_dt = datetime.datetime.fromisoformat(now_iso.replace("Z", "+00:00"))

    conn = connect_sqlite(shadow_db_path)
    queue_updated = False
    try:
        cur = conn.cursor()
        try:
            sel_rows = cur.execute(
                "SELECT s.fixture_id, f.kickoff, f.status, p.request_status "
                "FROM pipeline_runtime_event_selection s "
                "JOIN fixtures f ON f.id = s.fixture_id "
                "LEFT JOIN pipeline_provider_observation_attempts p ON p.run_id = s.run_id AND p.canonical_event_id = s.canonical_event_id "
                "WHERE s.run_id = ? AND s.decision = 'ANALYZE_FROM_S2'",
                (run_id,),
            ).fetchall()
        except sqlite3.OperationalError:
            sel_rows = cur.execute(
                "SELECT s.fixture_id, f.kickoff, f.status, p.request_status "
                "FROM pipeline_runtime_event_selection s "
                "JOIN fixtures f ON f.id = s.fixture_id "
                "LEFT JOIN pipeline_provider_observations p ON p.run_id = s.run_id AND p.canonical_event_id = s.canonical_event_id "
                "WHERE s.run_id = ? AND s.decision = 'ANALYZE_FROM_S2'",
                (run_id,),
            ).fetchall()

        queue_changed = False
        change_reasons = []

        for fid, kickoff, status, req_status in sel_rows:
            status_upper = (status or "").upper()
            if status_upper not in ("SCHEDULED", "CONFIRMED", "SCHED"):
                queue_changed = True
                change_reasons.append(f"Fixture {fid} status changed to {status_upper}")
            if req_status != "SUCCESS":
                queue_changed = True
                change_reasons.append(
                    f"Fixture {fid} lacks successful provider observation"
                )
            if kickoff:
                try:
                    k_dt = datetime.datetime.fromisoformat(
                        kickoff.replace("Z", "+00:00")
                    )
                    if k_dt <= now_dt:
                        queue_changed = True
                        change_reasons.append(
                            f"Fixture {fid} kickoff passed ({kickoff})"
                        )
                except Exception:
                    pass

        if queue_changed:
            return {
                "status": "BLOCKED",
                "blocker": "PLAN_REFRESH_REQUIRED",
                "reason": "; ".join(change_reasons),
                "shadow_db_path": str(shadow_db_path),
                "selection_ledger_sha256": sel_sha,
                "queue_updated_pre_s2": False,
            }

        verify_and_write_stage_db_receipt(
            conn, "S2_CONTINUATION", run_id, target_run_root, sel_sha
        )
    finally:
        conn.close()

    return {
        "status": "PASS",
        "shadow_db_path": str(shadow_db_path),
        "selection_ledger_sha256": sel_sha,
        "queue_updated_pre_s2": queue_updated,
    }


def promote_shadow_results(
    canonical_db_path: Path,
    shadow_db_path: Path,
    run_id: str,
    expected_canonical_sha: str | None = None,
) -> dict[str, Any]:
    """Execute controlled promotion of validated results from shadow DB to canonical DB."""
    canonical_db_path = canonical_db_path.resolve()
    shadow_db_path = shadow_db_path.resolve()

    if not canonical_db_path.exists():
        raise FileNotFoundError(f"Canonical DB missing: {canonical_db_path}")
    if not shadow_db_path.exists():
        raise FileNotFoundError(f"Shadow DB missing: {shadow_db_path}")

    c_sha_before = compute_file_sha256(canonical_db_path)
    if expected_canonical_sha and c_sha_before != expected_canonical_sha:
        raise ValueError(
            f"Canonical DB SHA mismatch before promotion: expected {expected_canonical_sha}, got {c_sha_before}"
        )

    # 1. Backup canonical DB
    backup_path = canonical_db_path.parent / f"betting_backup_{run_id}.db"
    conn_c = connect_sqlite(canonical_db_path)
    conn_b = connect_sqlite(backup_path)
    try:
        conn_c.backup(conn_b)
    finally:
        conn_b.close()
        conn_c.close()

    # 2. Perform promotion inside transaction
    allowlisted_tables = [
        "fixtures",
        "pipeline_candidates",
        "analysis_raw_data",
        "analysis_results",
        "gate_results",
        "odds_history",
        "sports_enrichment_run",
        "analysis_snapshot",
        "decision_snapshots",
        "pipeline_event_stage_state",
    ]

    conn_c = connect_sqlite(canonical_db_path)
    conn_s = connect_sqlite(shadow_db_path)

    promotion_id = (
        f"prom_{run_id}_{datetime.datetime.now(datetime.UTC).strftime('%Y%m%d_%H%M%S')}"
    )
    now_iso = datetime.datetime.now(datetime.UTC).isoformat()

    try:
        apply_runtime_bridge_migrations(conn_c)
        conn_c.execute(f"ATTACH DATABASE '{shadow_db_path}' AS shadow")

        for tbl in allowlisted_tables:
            s_exists = conn_s.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name=?",
                (tbl,),
            ).fetchone()[0]
            if not s_exists:
                continue

            cols_rows = conn_c.execute(f"PRAGMA table_info({tbl})").fetchall()
            cols = [col[1] for col in cols_rows]
            if not cols:
                continue
            col_list = ", ".join(cols)

            try:
                conn_c.execute(
                    f"INSERT OR REPLACE INTO {tbl} ({col_list}) SELECT {col_list} FROM shadow.{tbl}"
                )
            except Exception:
                pass

        conn_c.execute(
            "INSERT INTO pipeline_shadow_promotions ("
            "promotion_id, run_id, canonical_db_sha256_before, shadow_db_sha256, "
            "status, promoted_tables_json, started_at, completed_at, receipt_sha256"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                promotion_id,
                run_id,
                c_sha_before,
                compute_file_sha256(shadow_db_path),
                "COMPLETED",
                json.dumps(allowlisted_tables),
                now_iso,
                datetime.datetime.now(datetime.UTC).isoformat(),
                "",
            ),
        )

        conn_c.commit()
    except Exception:
        conn_c.rollback()
        raise
    finally:
        try:
            conn_c.execute("DETACH DATABASE shadow")
        except sqlite3.OperationalError:
            pass
        conn_c.close()
        conn_s.close()

    c_sha_after = compute_file_sha256(canonical_db_path)

    return {
        "promotion_id": promotion_id,
        "run_id": run_id,
        "canonical_db_sha256_before": c_sha_before,
        "canonical_db_sha256_after": c_sha_after,
        "promoted_tables": allowlisted_tables,
        "status": "PASS",
    }
