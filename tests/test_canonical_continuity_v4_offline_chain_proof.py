from __future__ import annotations

import hashlib
import json
from pathlib import Path

from bet.pipeline.agent_artifact_contracts import validate_agent_artifact_for_work_order
from bet.pipeline.agent_work_orders import (
    build_agent_work_order,
    write_agent_work_order,
)
from bet.pipeline.artifact_gate import (
    PipelineReadinessStatus,
    evaluate_gate_before_step,
)
from bet.pipeline.canonical_continuity import file_sha256
from bet.pipeline.event_accounting import EventAccountingLedger, canonical_event_id

DAY = "2026-07-15"
RUN_ID = "run-v4-integration-proof"


def _seed_s1_events() -> list[dict]:
    return [
        {
            "fixture_id": "football-unicode",
            "sport": "football",
            "competition": "Integration League",
            "home_team": "ŁKS Łódź",
            "away_team": "KS D",
            "kickoff": "2026-07-15T12:00:00Z",
        },
        {
            "fixture_id": "football-tz",
            "sport": "football",
            "competition": "Integration League",
            "home_team": "Team B",
            "away_team": "Team C",
            "kickoff": "2026-07-15T14:00:00+02:00",
        },
        {
            "fixture_id": "football-normal",
            "sport": "football",
            "competition": "Integration League",
            "home_team": "Team D",
            "away_team": "Team E",
            "kickoff": "2026-07-15T16:00:00Z",
        },
    ]


def test_v4_offline_chain_proof(tmp_path: Path):
    # 1. Fresh run root (which contains pipeline_runs/DAY/RUN_ID/)
    run_root = tmp_path

    art_dir = run_root / "pipeline_runs" / DAY / RUN_ID / "artifacts"
    data_dir = run_root / "pipeline_runs" / DAY / RUN_ID / "data"
    art_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    # Setup standard env
    # (Unused child_env removed)

    # 2. Setup S1 evidence & S1 matrix output on disk
    matrix_path = data_dir / "market_matrix.json"
    events = _seed_s1_events()
    matrix_path.write_text(json.dumps({"events": events}), encoding="utf-8")

    s1_ev_path = art_dir / "S1.json"
    s1_ev_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifact_type": "SCRIPT_EVIDENCE",
                "step_id": "S1",
                "status": "PASS",
                "betting_day": DAY,
                "run_id": RUN_ID,
                "payload": {"market_matrix_path": str(matrix_path)},
            }
        ),
        encoding="utf-8",
    )

    # S1e Universe creation and event accounting initialization
    universe_path = data_dir / f"{DAY}_s1e_event_universe.json"
    e_ids = [canonical_event_id(e) for e in events]

    s1e_universe_data = {
        "schema_version": 1,
        "artifact_type": "S1E_EVENT_UNIVERSE_LEDGER",
        "betting_day": DAY,
        "run_id": RUN_ID,
        "source_s1_evidence_path": str(s1_ev_path),
        "source_s1_evidence_sha256": hashlib.sha256(
            s1_ev_path.read_bytes()
        ).hexdigest(),
        "source_s1_path": str(matrix_path),
        "source_s1_sha256": hashlib.sha256(matrix_path.read_bytes()).hexdigest(),
        "after_dedup_count": len(e_ids),
        "canonical_event_ids": e_ids,
        "events": events,
        "zero_event_universe": False,
        "discovery_attempted": True,
    }
    universe_path.write_text(json.dumps(s1e_universe_data), encoding="utf-8")

    s1e_ev_path = art_dir / "S1e.json"
    s1e_ev_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifact_type": "SCRIPT_EVIDENCE",
                "step_id": "S1e",
                "status": "PASS",
                "betting_day": DAY,
                "run_id": RUN_ID,
                "payload": {
                    "s1e_json_output": str(universe_path),
                    "s1e_output_path": str(universe_path),
                    "s1e_output_sha256": hashlib.sha256(
                        universe_path.read_bytes()
                    ).hexdigest(),
                    "after_dedup_count": len(e_ids),
                    "event_records": [
                        {
                            "canonical_event_id": eid,
                            "terminal_status": "CONTINUE",
                            "reason_codes": [],
                            "candidate_ids": [],
                        }
                        for eid in e_ids
                    ],
                },
            }
        ),
        encoding="utf-8",
    )

    # Initialize ledger from S1e universe
    ledger = EventAccountingLedger.initialize(
        run_root, universe_path, betting_day=DAY, run_id=RUN_ID
    )

    # 3. S2 Step with matched tipster picks or degraded check
    s2_shortlist_path = data_dir / f"{DAY}_s2_shortlist.json"
    s2_shortlist_path.write_text(
        json.dumps(
            {"artifact_type": "S2_SHORTLIST", "total_candidates": 0, "candidates": []}
        ),
        encoding="utf-8",
    )

    s2_ev_path = art_dir / "S2.json"
    s2_ev_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "artifact_type": "SCRIPT_EVIDENCE",
                "step_id": "S2",
                "status": "PASS",
                "betting_day": DAY,
                "run_id": RUN_ID,
                "payload": {
                    "s2_output_path": str(s2_shortlist_path),
                    "s2_shortlist_path": str(s2_shortlist_path),
                    "s2_output_sha256": hashlib.sha256(
                        s2_shortlist_path.read_bytes()
                    ).hexdigest(),
                    "event_records": [
                        {
                            "canonical_event_id": eid,
                            "terminal_status": "DEGRADED_CONTINUE",
                            "reason_codes": ["DEGRADED_NO_TIPSTER_PICKS"],
                            "candidate_ids": [],
                        }
                        for eid in e_ids
                    ],
                    "outcome": "DEGRADED_NO_TIPSTER_PICKS",
                },
            }
        ),
        encoding="utf-8",
    )

    # Record S2 boundary in ledger
    ledger.record_boundary(
        "S2", records=json.loads(s2_ev_path.read_text())["payload"]["event_records"]
    )

    # 4. Agent artifact steps (S2.3, S2.5, S2.7, S2.9)
    pred_data = {}
    for sid in ("S2.3", "S2.5", "S2.7"):
        # Create work order
        wo = build_agent_work_order(
            betting_day=DAY,
            run_id=RUN_ID,
            step_id=sid,
            runtime_mode="DRY_RUN",
            base_dir=run_root,
        )
        write_agent_work_order(wo, run_root)

        # Save mock PASS predecessor file
        p_path = art_dir / f"{sid}.json"
        p_data = {
            "schema_version": 1,
            "artifact_type": "AGENT_ARTIFACT",
            "step_id": sid,
            "status": "PASS",
            "betting_day": DAY,
            "run_id": RUN_ID,
            "sport": "Football",
            "point_in_time_as_of": "2026-07-15T12:00:00Z",
            "source_bound": True,
            "no_pick_edge_stake_coupon_emitted": True,
            "production_selectable": False,
            "betting_decisions_enabled": False,
            "sources": ["source"],
            "unknowns": [],
            "blocked_reasons": [],
            "evidence_refs": [],
            "work_order_id": wo.work_order_id,
            "work_order_sha256": file_sha256(
                work_order_path_for(run_root, DAY, RUN_ID, sid)
            ),
            "payload": {
                "event_records": [
                    {
                        "canonical_event_id": eid,
                        "terminal_status": "DEGRADED_CONTINUE",
                        "reason_codes": ["DEGRADED_NO_TIPSTER_PICKS"],
                        "candidate_ids": [],
                    }
                    for eid in e_ids
                ],
                "enrichment_gaps": [] if sid == "S2.3" else None,
                "providers": ["source"] if sid == "S2.5" else None,
                "disputed_facts": [] if sid == "S2.7" else None,
                "reconciliation": {"unknown_facts": [], "decision_basis": "basis"}
                if sid == "S2.7"
                else None,
            },
        }
        p_data["payload"] = {
            k: v for k, v in p_data["payload"].items() if v is not None
        }
        p_path.write_text(json.dumps(p_data), encoding="utf-8")

        # Record boundary
        ledger.record_boundary(sid, records=p_data["payload"]["event_records"])

        p_sha = hashlib.sha256(p_path.read_bytes()).hexdigest()
        pred_data[sid] = {"path": str(p_path), "sha256": p_sha}

    # Now create S2.9 work order and artifact
    s29_wo = build_agent_work_order(
        betting_day=DAY,
        run_id=RUN_ID,
        step_id="S2.9",
        runtime_mode="DRY_RUN",
        base_dir=run_root,
    )
    # Patch input refs in work order data to refer to S2.3, S2.5, S2.7 mock files
    s29_wo_json = s29_wo.to_jsonable()
    s29_wo_json["input_refs"] = [
        {
            "step_id": sid,
            "path": pred_data[sid]["path"],
            "sha256": pred_data[sid]["sha256"],
            "artifact_kind": "AGENT_ARTIFACT",
        }
        for sid in ("S2.3", "S2.5", "S2.7")
    ]

    s29_wo_path = work_order_path_for(run_root, DAY, RUN_ID, "S2.9")
    s29_wo_path.write_text(json.dumps(s29_wo_json), encoding="utf-8")

    s29_path = art_dir / "S2.9.json"
    s29_data = {
        "schema_version": 1,
        "artifact_type": "AGENT_ARTIFACT",
        "step_id": "S2.9",
        "status": "PASS",
        "betting_day": DAY,
        "run_id": RUN_ID,
        "sport": "Football",
        "point_in_time_as_of": "2026-07-15T12:00:00Z",
        "source_bound": True,
        "no_pick_edge_stake_coupon_emitted": True,
        "production_selectable": False,
        "betting_decisions_enabled": False,
        "sources": ["source"],
        "unknowns": [],
        "blocked_reasons": [],
        "evidence_refs": [
            "artifact_S2.3_run-smoke",
            "artifact_S2.5_run-smoke",
            "artifact_S2.7_run-smoke",
        ],
        "work_order_id": s29_wo.work_order_id,
        "work_order_sha256": file_sha256(s29_wo_path),
        "payload": {
            "readiness": "PASS",
            "s3_may_proceed": True,
            "event_records": [
                {
                    "canonical_event_id": eid,
                    "terminal_status": "DEGRADED_CONTINUE",
                    "reason_codes": ["DEGRADED_NO_TIPSTER_PICKS"],
                    "candidate_ids": [],
                }
                for eid in e_ids
            ],
            "predecessor_bindings": [
                {
                    "step_id": sid,
                    "path": pred_data[sid]["path"],
                    "sha256": pred_data[sid]["sha256"],
                    "artifact_type": "AGENT_ARTIFACT",
                    "betting_day": DAY,
                    "run_id": RUN_ID,
                    "status": "PASS",
                }
                for sid in ("S2.3", "S2.5", "S2.7")
            ],
        },
    }
    s29_path.write_text(json.dumps(s29_data), encoding="utf-8")

    # Validate S2.9 using direct validation
    errors = validate_agent_artifact_for_work_order(s29_data, s29_wo_json)
    assert errors == [], f"S2.9 validation errors: {errors}"

    # 5. Evaluate gate S3 requires S2.9
    decision = evaluate_gate_before_step("S3", run_root, DAY, RUN_ID)
    assert decision.verdict == PipelineReadinessStatus.PASS, (
        f"S3 Gate check failed: {decision.failed_requirements}"
    )

    # 12. Tamper with one predecessor and prove BLOCK
    pred_path_to_tamper = Path(pred_data["S2.3"]["path"])
    pred_path_to_tamper.write_text(
        pred_path_to_tamper.read_text().replace("Football", "Soccer"), encoding="utf-8"
    )

    decision_after_tamper = evaluate_gate_before_step("S3", run_root, DAY, RUN_ID)
    assert decision_after_tamper.verdict == PipelineReadinessStatus.BLOCK, (
        "Gate should block after predecessor tampering!"
    )


def work_order_path_for(
    base_dir: Path, betting_day: str, run_id: str, step_id: str
) -> Path:
    return (
        base_dir
        / "pipeline_runs"
        / betting_day
        / run_id
        / "artifacts"
        / f"{step_id}_work_order.json"
    )
