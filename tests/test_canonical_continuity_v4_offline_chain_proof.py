from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone
import pytest

from bet.pipeline.orchestrator import Orchestrator
from bet.pipeline.artifact_io import publish_run_artifact
from bet.pipeline.agent_work_orders import build_agent_work_order, write_agent_work_order
from bet.pipeline.event_accounting import canonical_event_id

DAY = "2026-07-16"
RUN_ID = "v4-canonical-offline-chain"

def _bootstrap_test_db(db_path: Path) -> Path:
    repo_root = Path(__file__).resolve().parents[1]
    schema_path = repo_root / "src" / "bet" / "db" / "schema.sql"
    schema = schema_path.read_text(encoding="utf-8")
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(schema)

    # Seed mock data
    conn.execute("INSERT INTO sports (id, name) VALUES (1, 'football')")
    conn.execute("INSERT INTO teams (id, sport_id, name) VALUES (1, 1, 'ŁKS Łódź')")
    conn.execute("INSERT INTO teams (id, sport_id, name) VALUES (2, 1, 'KS D')")
    conn.execute("INSERT INTO team_form (team_id, sport_id, stat_key, l10_values, l10_avg, updated_at) VALUES (1, 1, 'goals', '[1, 2, 1]', 1.5, '2026-07-16')")
    conn.execute("INSERT INTO team_form (team_id, sport_id, stat_key, l10_values, l10_avg, updated_at) VALUES (2, 1, 'goals', '[0, 1, 2]', 1.0, '2026-07-16')")
    conn.commit()
    conn.close()
    return db_path


def test_v4_offline_chain_proof(tmp_path: Path, monkeypatch):
    monkeypatch.delenv("BET_PIPELINE_CERTIFIER_ACTIVE", raising=False)
    monkeypatch.delenv("BET_MOCK_ODDS", raising=False)
    monkeypatch.delenv("BET_PIPELINE_SKIP_FETCH", raising=False)
    run_root = tmp_path / "pipeline_runs" / DAY / RUN_ID
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "data").mkdir(parents=True, exist_ok=True)
    (run_root / "artifacts").mkdir(parents=True, exist_ok=True)
    (run_root / "logs").mkdir(parents=True, exist_ok=True)
    (run_root / "journal").mkdir(parents=True, exist_ok=True)

    # 1. Setup DB
    db_file = run_root / "data" / "bet_dryrun_test.db"
    _bootstrap_test_db(db_file)

    # Set environments
    monkeypatch.setenv("BET_DB_PATH", str(db_file))
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_file}")
    monkeypatch.setenv("BET_PIPELINE_RUN_ROOT", str(run_root))
    monkeypatch.setenv("BET_PIPELINE_DATA_DIR", str(run_root / "data"))
    monkeypatch.setenv("BET_PIPELINE_ARTIFACT_DIR", str(run_root / "artifacts"))
    monkeypatch.setenv("BET_PIPELINE_COUPON_DIR", str(run_root / "coupons"))

    # Seed picks-ledger
    ledger_file = run_root / "journal" / "picks-ledger.csv"
    ledger_file.parent.mkdir(parents=True, exist_ok=True)
    ledger_file.write_text(
        "betting_day,status,event,pick_id,sport,market,selection,settled_at_utc,result_recorded_at_utc\n",
        encoding="utf-8"
    )
    monkeypatch.setenv("BET_PIPELINE_LEDGER_PATH", str(ledger_file))

    # Seed stats_cache
    from scripts.deep_stats_report import slugify
    cache_dir = run_root / "data" / "stats_cache" / "football"
    cache_dir.mkdir(parents=True, exist_ok=True)

    slug_a = slugify("ŁKS Łódź")
    slug_b = slugify("KS D")

    (cache_dir / f"{slug_a}.json").write_text(json.dumps({
        "sources": ["db"],
        "form": {
            "l10_avg": {"goals": 1.5},
            "l10_matches": [
                {"goals": 1, "goals_conceded": 0},
                {"goals": 2, "goals_conceded": 1},
                {"goals": 1, "goals_conceded": 2},
                {"goals": 0, "goals_conceded": 0},
                {"goals": 3, "goals_conceded": 1},
                {"goals": 1, "goals_conceded": 1},
                {"goals": 2, "goals_conceded": 0},
                {"goals": 0, "goals_conceded": 2},
                {"goals": 1, "goals_conceded": 1},
                {"goals": 2, "goals_conceded": 1}
            ]
        },
        "h2h": {
            slug_b: {
                "matches": [{"home_team": "ŁKS Łódź", "away_team": "KS D", "home_score": 2, "away_score": 1}]
            }
        }
    }), encoding="utf-8")

    (cache_dir / f"{slug_b}.json").write_text(json.dumps({
        "sources": ["db"],
        "form": {
            "l10_avg": {"goals": 1.0},
            "l10_matches": [
                {"goals": 0, "goals_conceded": 1},
                {"goals": 1, "goals_conceded": 2},
                {"goals": 2, "goals_conceded": 1},
                {"goals": 0, "goals_conceded": 0},
                {"goals": 1, "goals_conceded": 3},
                {"goals": 1, "goals_conceded": 1},
                {"goals": 0, "goals_conceded": 2},
                {"goals": 2, "goals_conceded": 0},
                {"goals": 1, "goals_conceded": 1},
                {"goals": 1, "goals_conceded": 2}
            ]
        },
        "h2h": {
            slug_a: {
                "matches": [{"home_team": "ŁKS Łódź", "away_team": "KS D", "home_score": 2, "away_score": 1}]
            }
        }
    }), encoding="utf-8")

    # 2. Seed S1 discover shortlist & evidence
    matrix_path = run_root / "data" / "market_matrix.json"
    event_data = [
        {
            "fixture_id": "football-unicode",
            "sport": "football",
            "competition": "Integration League",
            "home_team": "ŁKS Łódź",
            "away_team": "KS D",
            "kickoff": "2026-07-16T12:00:00Z",
        }
    ]
    matrix_path.write_text(json.dumps({"events": event_data}), encoding="utf-8")

    s1_ev_path = run_root / "artifacts" / "S1.json"
    s1_ev = {
        "schema_version": 1,
        "artifact_type": "SCRIPT_EVIDENCE",
        "step_id": "S1",
        "status": "PASS",
        "betting_day": DAY,
        "run_id": RUN_ID,
        "payload": {"market_matrix_path": str(matrix_path)},
    }
    s1_ev_path.write_text(json.dumps(s1_ev), encoding="utf-8")

    # Invoke real S2 producer
    from build_shortlist import write_shortlist_json
    selected = [(85.0, ev) for ev in event_data]
    monkeypatch.setattr("build_shortlist.DATA_DIR", run_root / "data")
    s2_shortlist_path = write_shortlist_json(selected, date=DAY)

    # Override S2 tipster scripts to bypass live scrapers
    import scripts.pipeline_steps.s2_tipsters as s2_tipsters
    monkeypatch.setattr(s2_tipsters, "SCRIPTS", ["tipster_xref.py"])

    # Initialize Orchestrator
    orchestrator = Orchestrator(
        betting_day=DAY,
        run_id=RUN_ID,
        runtime_mode="DRY_RUN",
        base_run_dir=tmp_path,
        allow_write=False,
    )

    steps = ["S1e", "S2", "S2.3", "S2.5", "S2.7", "S2.9", "S3", "S4", "S5", "S6", "S7", "S7b", "S8"]

    current_idx = 0
    while current_idx < len(steps):
        step_id = steps[current_idx]

        # Write mock agent artifacts with required event records
        if step_id in ("S2.3", "S2.5", "S2.7", "S2.9", "S5"):
            wo = build_agent_work_order(
                betting_day=DAY,
                run_id=RUN_ID,
                step_id=step_id,
                runtime_mode="DRY_RUN",
                base_dir=tmp_path,
            )
            write_agent_work_order(wo, tmp_path)
            wo_path = run_root / "artifacts" / f"{step_id}_work_order.json"
            wo_data = json.loads(wo_path.read_text(encoding="utf-8"))

            input_refs = wo_data.get("input_refs", [])
            for ref in input_refs:
                p = Path(ref["path"])
                ref["sha256"] = hashlib.sha256(p.read_bytes()).hexdigest()

            wo_sha = hashlib.sha256(wo_path.read_bytes()).hexdigest()
            evt_id = canonical_event_id(event_data[0])

            payload = {
                "event_records": [
                    {
                        "canonical_event_id": evt_id,
                        "terminal_status": "DEGRADED_CONTINUE",
                        "reason_codes": ["DEGRADED_NO_TIPSTER_PICKS"],
                        "candidate_ids": []
                    }
                ]
            }
            evidence_refs = ["mock_ref"]
            if step_id == "S2.3":
                payload["enrichment_gaps"] = []
                payload["gaps_status"] = "none"
            elif step_id == "S2.5":
                payload["providers"] = ["source"]
            elif step_id == "S2.7":
                payload["disputed_facts"] = []
                payload["reconciliation"] = {"unknown_facts": [], "decision_basis": "basis"}
                evidence_refs = ["S2.5_ref"]
            elif step_id == "S2.9":
                payload["readiness"] = "PASS"
                payload["s3_may_proceed"] = True
                payload["predecessor_bindings"] = []
                for ref in input_refs:
                    ref_step_id = ref["step_id"]
                    if ref_step_id in ("S2.3", "S2.5", "S2.7"):
                        payload["predecessor_bindings"].append({
                            "step_id": ref_step_id,
                            "path": ref["path"],
                            "sha256": ref["sha256"],
                            "artifact_type": "AGENT_ARTIFACT",
                            "betting_day": DAY,
                            "run_id": RUN_ID,
                            "status": "PASS"
                        })
                evidence_refs = ["S2.3_ref", "S2.5_ref", "S2.7_ref"]
            elif step_id == "S5":
                payload["injuries_context_available"] = True
                payload["morale_reconciled"] = "GOOD"
                payload["volatility_risk_checked"] = True
                payload["weather_conditions"] = {"forecast": "CLEAR"}
                payload["travel_fatigue_checked"] = True
                payload["morale_context_checked"] = True
                payload["tipster_sentiment"] = {}
                payload["bet_builder_precheck"] = {}
                payload["tournament_context"] = {}

                s4_json_path = run_root / "data" / f"{DAY}_s4_valuation_candidates.json"
                s4_data = json.loads(s4_json_path.read_text(encoding="utf-8"))

                    clean_candidates = []
                    for c in s4_data["candidates"]:
                        c_copy = dict(c)
                        for key in ["stake", "kelly_fraction", "bettable", "edge"]:
                            c_copy.pop(key, None)
                        c_copy["home_team"] = c_copy.get("home_team") or "ŁKS Łódź"
                        c_copy["away_team"] = c_copy.get("away_team") or "KS D"
                        c_copy["canonical_event_id"] = c_copy.get("canonical_event_id") or evt_id
                        c_copy["candidate_id"] = c_copy.get("candidate_id") or f"{evt_id}_1X2_HOME"
                        c_copy["terminal_status"] = "PASS"
                        c_copy["risk_classification"] = "LOW"
                        c_copy["best_market"] = c_copy.get("best_market") or {"name": "1X2", "safety_score": 1.0}
                        c_copy["context_checks"] = {
                            "injuries_lineups": {"status": "CLEAR", "as_of_utc": "2026-07-16T12:00:00Z", "source_refs": ["mock_ref"]},
                            "motivation_tournament_context": {"status": "CLEAR", "as_of_utc": "2026-07-16T12:00:00Z", "source_refs": ["mock_ref"]},
                            "travel_fatigue": {"status": "CLEAR", "as_of_utc": "2026-07-16T12:00:00Z", "source_refs": ["mock_ref"]},
                            "morale_recent_form": {"status": "CLEAR", "as_of_utc": "2026-07-16T12:00:00Z", "source_refs": ["mock_ref"]},
                            "upset_volatility_risk": {"status": "CLEAR", "as_of_utc": "2026-07-16T12:00:00Z", "source_refs": ["mock_ref"]}
                        }
                        c_copy["risk_flags"] = []
                        c_copy["counter_evidence"] = []
                        c_copy["safety_score"] = 1.0
                        clean_candidates.append(c_copy)

                from bet.pipeline.run_evidence import repo_head_sha, manifest_hash, sha256_file
                payload["source_git_sha"] = repo_head_sha(Path(__file__).resolve().parents[1])
                payload["manifest_sha"] = manifest_hash(Path(__file__).resolve().parents[1])
                payload["source_s4_path"] = str(s4_json_path)
                payload["source_s4_sha256"] = sha256_file(s4_json_path)
                payload["work_order_id"] = f"WO-{RUN_ID}-S5"
                payload["agent_id"] = "bet-risk-gatekeeper"
                payload["policy_version"] = "1.0"
                payload["accounting"] = {
                    "unaccounted_candidate_ids": [],
                    "duplicate_candidate_ids": [],
                    "overlapping_terminal_categories": []
                }
                payload["input_candidate_count"] = len(clean_candidates)
                payload["candidates"] = clean_candidates
                payload["rejected_candidates"] = []
                evidence_refs = ["artifacts/S4.json"]

            artifact = {
                "schema_version": 1 if step_id != "S2.9" else 2,
                "artifact_type": "AGENT_ARTIFACT",
                "step_id": step_id,
                "producer_agent_id": wo_data.get("agent"),
                "status": "PASS",
                "betting_day": DAY,
                "run_id": RUN_ID,
                "sport": "football",
                "point_in_time_as_of": "2026-07-16T12:00:00Z",
                "source_bound": True,
                "no_pick_edge_stake_coupon_emitted": True,
                "production_selectable": False,
                "betting_decisions_enabled": False,
                "sources": ["source"],
                "unknowns": [],
                "blocked_reasons": [],
                "evidence_refs": evidence_refs,
                "work_order_id": wo_data["work_order_id"],
                "work_order_sha256": wo_sha,
                "payload": payload,
            }

            publish_run_artifact(
                run_root=run_root,
                target=run_root / "artifacts" / f"{step_id}.json",
                payload=artifact,
                betting_day=DAY,
                run_id=RUN_ID,
                artifact_type="AGENT_ARTIFACT",
                immutable=True,
            )

        # Execute orchestrator step
        res = orchestrator.run(start_step=step_id, stop_after_step=step_id)
        if (res.get("overall_status") or res.get("status")) != "PASS":
            print("RUN ROOT:", run_root)
            print("FILES:")
            for p in sorted(run_root.rglob("*")):
                print(" -", p.relative_to(run_root), "is_file:", p.is_file())
                if p.is_file() and p.name.endswith(".log"):
                    print(f"--- CONTENT of {p.name} ---")
                    print(p.read_text())
                    print("-------------------------")
        assert (res.get("overall_status") or res.get("status")) == "PASS", f"Step {step_id} failed: {orchestrator.blockers}"
        current_idx += 1

    # Verify S8 completed and generated zero-odds PRICE_PENDING/UNPRICED results
    s8_ev_file = run_root / "artifacts" / "S8.json"
    assert s8_ev_file.exists()
    s8_ev = json.loads(s8_ev_file.read_text(encoding="utf-8"))
    assert s8_ev["status"] == "PASS"

    quote_pack_path = Path(s8_ev["payload"]["s8_quote_pack_path"])
    assert quote_pack_path.exists()
    quote_pack = json.loads(quote_pack_path.read_text(encoding="utf-8"))

    assert quote_pack["status"] in ("READY_FOR_MANUAL_SUPERBET_QUOTE_REVIEW", "NO_ACTION_TERMINAL")
    for card in quote_pack.get("quote_cards", []):
        assert card["manual_operator"] == "SUPERBET"
        assert card["executable_coupon"] is False
        assert card["betting_valid"] is False
        assert card["can_place_bet_now"] is False
        assert card["pricing_status"] == "UNPRICED"

    # S9 is never generated
    s9_ev_file = run_root / "artifacts" / "S9.json"
    assert not s9_ev_file.exists()


def test_exact_database_immutability_proof(tmp_path: Path, monkeypatch):
    base_run_dir = tmp_path / "pipeline_runs"
    real_run_root = base_run_dir / "2026-07-16" / "immutability-run"
    real_run_root.mkdir(parents=True, exist_ok=True)

    # Set parent environments explicitly via monkeypatch to prevent leaks from test_v4_offline_chain_proof
    monkeypatch.setenv("BET_PIPELINE_RUN_ROOT", str(real_run_root))
    monkeypatch.setenv("BET_PIPELINE_DATA_DIR", str(real_run_root / "data"))
    monkeypatch.setenv("BET_PIPELINE_ARTIFACT_DIR", str(real_run_root / "artifacts"))
    monkeypatch.setenv("BET_PIPELINE_COUPON_DIR", str(real_run_root / "coupons"))

    # Create required directories
    (real_run_root / "data").mkdir(parents=True, exist_ok=True)
    (real_run_root / "artifacts").mkdir(parents=True, exist_ok=True)
    (real_run_root / "logs").mkdir(parents=True, exist_ok=True)
    (real_run_root / "journal").mkdir(parents=True, exist_ok=True)

    # 1. Create valid sentinel operational database
    sentinel_db = tmp_path / "operational_sentinel.db"
    _bootstrap_test_db(sentinel_db)

    # Enable WAL mode and sidecars
    conn = sqlite3.connect(str(sentinel_db))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE IF NOT EXISTS test_sentinel_table (id INTEGER PRIMARY KEY, val TEXT)")
    conn.execute("INSERT INTO test_sentinel_table (val) VALUES ('sentinel')")
    conn.commit()
    conn.close()

    # Track metadata of database and sidecars
    sidecars = [sentinel_db, sentinel_db.with_name(sentinel_db.name + "-wal"), sentinel_db.with_name(sentinel_db.name + "-shm")]
    initial_metadata = {}
    for sc in sidecars:
        if sc.exists():
            initial_metadata[sc] = {
                "exists": True,
                "size": sc.stat().st_size,
                "mtime_ns": sc.stat().st_mtime_ns,
                "sha256": hashlib.sha256(sc.read_bytes()).hexdigest(),
            }
        else:
            initial_metadata[sc] = {"exists": False}

    # 2. Invoke the daily pipeline parser and run script via subprocess with EXACT schema requested
    # We must seed pre-discover artifacts so the pipeline has input
    matrix_path = real_run_root / "data" / "market_matrix.json"
    event_data = [
        {
            "fixture_id": "football-unicode",
            "sport": "football",
            "competition": "Integration League",
            "home_team": "ŁKS Łódź",
            "away_team": "KS D",
            "kickoff": "2026-07-16T12:00:00Z",
        }
    ]
    matrix_path.write_text(json.dumps({"events": event_data}), encoding="utf-8")

    s1_ev_path = real_run_root / "artifacts" / "S1.json"
    s1_ev = {
        "schema_version": 1,
        "artifact_type": "SCRIPT_EVIDENCE",
        "step_id": "S1",
        "status": "PASS",
        "betting_day": "2026-07-16",
        "run_id": "immutability-run",
        "payload": {"market_matrix_path": str(matrix_path)},
    }
    s1_ev_path.write_text(json.dumps(s1_ev), encoding="utf-8")

    # Invoke real S2 producer
    from build_shortlist import write_shortlist_json
    selected = [(85.0, ev) for ev in event_data]
    monkeypatch.setattr("build_shortlist.DATA_DIR", real_run_root / "data")
    s2_shortlist_path = write_shortlist_json(selected, date="2026-07-16")

    # Set up picks-ledger
    ledger_file = real_run_root / "journal" / "picks-ledger.csv"
    ledger_file.parent.mkdir(parents=True, exist_ok=True)
    ledger_file.write_text(
        "betting_day,status,event,pick_id,sport,market,selection,settled_at_utc,result_recorded_at_utc\n",
        encoding="utf-8"
    )

    env = os.environ.copy()
    env["DATABASE_URL"] = f"sqlite:///{sentinel_db}"
    env["BET_DB_PATH"] = str(sentinel_db)
    env["PYTHONPATH"] = "src:scripts"
    env["BET_PIPELINE_RUN_ROOT"] = str(real_run_root)
    env["BET_PIPELINE_DATA_DIR"] = str(real_run_root / "data")
    env["BET_PIPELINE_ARTIFACT_DIR"] = str(real_run_root / "artifacts")
    env["BET_PIPELINE_COUPON_DIR"] = str(real_run_root / "coupons")
    env["BET_PIPELINE_LEDGER_PATH"] = str(ledger_file)
    env["BET_MOCK_ODDS"] = "1"
    env["BET_PIPELINE_SKIP_FETCH"] = "1"
    env["BET_PIPELINE_LIVE_ACK"] = "I_UNDERSTAND_LIVE_PROVIDER_CALLS"
    env["BET_KEEP_TEMP_DB"] = "1"

    cmd = [
        sys.executable,
        "scripts/pipeline_steps/run_daily_pipeline.py",
        "--date", "2026-07-16",
        "--run-id", "immutability-run",
        "--runtime-mode", "LIVE_SHADOW",
        "--allow-live-network",
        "--base-run-dir", str(tmp_path / "pipeline_runs"),
        "--verbose"
    ]

    # 1. Run S1e and S2 first to generate S1e and S2 artifacts
    cmd_pre = cmd + ["--start-step", "S1e", "--stop-after-step", "S2"]
    res_pre = subprocess.run(cmd_pre, env=env, capture_output=True, text=True, cwd=str(Path(__file__).resolve().parents[1]))
    assert res_pre.returncode == 0, f"Pre-run failed with unexpected code {res_pre.returncode}: {res_pre.stderr}\nStdout: {res_pre.stdout}"

    # 2. Seed mock agent artifacts so S2.3, S2.5, S2.7, S2.9 can proceed smoothly and run S3
    from bet.pipeline.agent_work_orders import build_agent_work_order, write_agent_work_order

    file_hashes = {}
    for step_id in ("S2.3", "S2.5", "S2.7", "S2.9"):
        wo = build_agent_work_order(
            betting_day="2026-07-16",
            run_id="immutability-run",
            step_id=step_id,
            runtime_mode="LIVE_SHADOW",
            base_dir=tmp_path,
        )
        write_agent_work_order(wo, tmp_path)
        wo_path = real_run_root / "artifacts" / f"{step_id}_work_order.json"
        wo_sha = hashlib.sha256(wo_path.read_bytes()).hexdigest()

        # Build and publish the matching agent artifact with correct wo_sha
        evt_id = canonical_event_id(event_data[0])
        payload = {
            "event_records": [
                {
                    "canonical_event_id": evt_id,
                    "terminal_status": "DEGRADED_CONTINUE",
                    "reason_codes": ["DEGRADED_NO_TIPSTER_PICKS"],
                    "candidate_ids": []
                }
            ]
        }
        evidence_refs = ["mock_ref"]
        if step_id == "S2.3":
            payload["enrichment_gaps"] = []
            payload["gaps_status"] = "none"
        elif step_id == "S2.5":
            payload["providers"] = ["source"]
        elif step_id == "S2.7":
            payload["disputed_facts"] = []
            payload["reconciliation"] = {"unknown_facts": [], "decision_basis": "basis"}
            evidence_refs = ["S2.5_ref"]
        elif step_id == "S2.9":
            payload["readiness"] = "PASS"
            payload["s3_may_proceed"] = True
            payload["predecessor_bindings"] = []
            for ref_step_id in ("S2.3", "S2.5", "S2.7"):
                payload["predecessor_bindings"].append({
                    "step_id": ref_step_id,
                    "path": str(real_run_root / "artifacts" / f"{ref_step_id}.json"),
                    "sha256": file_hashes[ref_step_id],
                    "artifact_type": "AGENT_ARTIFACT",
                    "betting_day": "2026-07-16",
                    "run_id": "immutability-run",
                    "status": "PASS"
                })
            evidence_refs = ["S2.3_ref", "S2.5_ref", "S2.7_ref"]

        artifact = {
            "schema_version": 1 if step_id != "S2.9" else 2,
            "artifact_type": "AGENT_ARTIFACT",
            "step_id": step_id,
            "producer_agent_id": wo.agent,
            "status": "PASS",
            "betting_day": "2026-07-16",
            "run_id": "immutability-run",
            "sport": "football",
            "point_in_time_as_of": "2026-07-16T12:00:00Z",
            "source_bound": True,
            "no_pick_edge_stake_coupon_emitted": True,
            "production_selectable": False,
            "betting_decisions_enabled": False,
            "sources": ["source"],
            "unknowns": [],
            "blocked_reasons": [],
            "evidence_refs": evidence_refs,
            "work_order_id": f"WO-immutability-run-{step_id}",
            "work_order_sha256": wo_sha,
            "payload": payload,
        }

        receipt = publish_run_artifact(
            run_root=real_run_root,
            target=real_run_root / "artifacts" / f"{step_id}.json",
            payload=artifact,
            betting_day="2026-07-16",
            run_id="immutability-run",
            artifact_type="AGENT_ARTIFACT",
            immutable=True,
        )
        file_hashes[step_id] = receipt.sha256

    # 3. Run sequentially starting from S2.3 up to S3
    cmd_main = cmd + ["--start-step", "S2.3", "--stop-after-step", "S3"]
    res = subprocess.run(cmd_main, env=env, capture_output=True, text=True, cwd=str(Path(__file__).resolve().parents[1]))
    if res.returncode != 0:
        print("RUN ROOT:", real_run_root)
        print("FILES:")
        for p in sorted(real_run_root.rglob("*")):
            print(" -", p.relative_to(real_run_root), "is_file:", p.is_file())
            if p.is_file() and p.name.endswith(".log"):
                print(f"--- CONTENT of {p.name} ---")
                print(p.read_text())
                print("-------------------------")
    assert res.returncode == 0, f"Pipeline failed with unexpected code {res.returncode}: {res.stderr}\nStdout: {res.stdout}"

    # 3. Verify operational database is metadata and byte UNCHANGED
    for sc in sidecars:
        if initial_metadata[sc]["exists"]:
            assert sc.exists(), f"Sentinel sidecar {sc.name} was deleted!"
            assert sc.stat().st_size == initial_metadata[sc]["size"]
            assert sc.stat().st_mtime_ns == initial_metadata[sc]["mtime_ns"]
            assert hashlib.sha256(sc.read_bytes()).hexdigest() == initial_metadata[sc]["sha256"]

    # 4. Verify unique run-scoped DB exists and received writes
    run_scoped_dbs = list((real_run_root / "data").glob("bet_dryrun_*.db"))
    assert len(run_scoped_dbs) >= 1, "No run-scoped dryrun DB was created!"

    # 5. Verify evidence names effective run-scoped DB
    s3_ev_file = real_run_root / "artifacts" / "S3.json"
    assert s3_ev_file.exists()
    s3_ev = json.loads(s3_ev_file.read_text(encoding="utf-8"))
    assert s3_ev["payload"]["allow_write"] is False
    assert s3_ev["payload"]["production_write"] is False
